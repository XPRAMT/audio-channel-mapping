import queue
import socket
import struct
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import numpy as np
import pychromecast
from zeroconf import Zeroconf

from . import shared

HTTP_PORT_OFFSET = 100
STREAM_PATH_PREFIX = "/chromecast"
CONTENT_TYPE = "audio/wav"
CHROMECAST_BYTE_PER_SAMPLE = 3
SUPPORTED_SAMPLE_RATES = (44100, 48000, 88200, 96000)
CAST_WAIT_TIMEOUT = 1.5
DISCOVERY_INTERVAL = 5
VOLUME_SYNC_INTERVAL = 0.5
VOLUME_EPSILON = 0.005
VOLUME_SET_SUPPRESS_SECONDS = 1.5
HTTP_CLIENT_QUEUE_SIZE = 8
DISCOVERY_MISS_LIMIT = 3

_cast_infos = {}
_streams = {}
_volume_set_suppress_until = {}
_pending_volumes = {}
_discovery_misses = {}
_volume_next_send_at = {}
_pending_audio = {}
_smtc_states = {}  # dev_id -> previous player_state
_zconf = Zeroconf()
_http_server = None
_http_thread = None
_http_lock = threading.Lock()
_last_log_time = None
_log_lock = threading.Lock()


def log(message):
    global _last_log_time
    now = time.perf_counter()
    local_time = time.localtime()
    ms = int((time.time() % 1) * 1000)
    with _log_lock:
        delta_ms = 0 if _last_log_time is None else int((now - _last_log_time) * 1000)
        _last_log_time = now
    print(f"[Chromecast][{time.strftime('%H:%M:%S', local_time)}.{ms:03d}][+{delta_ms}ms] {message}")


def get_zconf():
    global _zconf
    if getattr(_zconf, "done", False):
        _zconf = Zeroconf()
    return _zconf


def choose_sample_rate(source_rate):
    source_rate = int(source_rate)
    if source_rate in SUPPORTED_SAMPLE_RATES:
        return source_rate
    return min(SUPPORTED_SAMPLE_RATES, key=lambda rate: abs(rate - source_rate))


def local_ip_for_target(target_host):
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.connect((target_host, 8009))
        return sock.getsockname()[0]


def stream_path(dev_id):
    return f"{STREAM_PATH_PREFIX}/{dev_id}.wav"


def read_device_volume(cast_info, fallback=1.0):
    try:
        cast = pychromecast.Chromecast(cast_info, zconf=get_zconf())
        cast.wait(timeout=5)
        status = cast.status
        volume = getattr(status, "volume_level", None)
        cast.disconnect()
        if volume is None:
            return fallback
        return max(0.0, min(1.0, float(volume)))
    except Exception as error:
        log(f"read volume error: {error}")
        return fallback


def set_device_volume(cast_info, volume):
    try:
        cast = pychromecast.Chromecast(cast_info, zconf=get_zconf())
        cast.wait(timeout=5)
        cast.set_volume(max(0.0, min(1.0, float(volume))))
        cast.disconnect()
    except Exception as error:
        log(f"set device volume error: {error}")


def read_stream_volume(stream, fallback=1.0):
    try:
        status = stream.cast.status if stream and stream.cast else None
        volume = getattr(status, "volume_level", None)
        if volume is None:
            return fallback
        return max(0.0, min(1.0, float(volume)))
    except Exception as error:
        log(f"sync volume error: {error}")
        return fallback


def update_client_volume(dev_id, volume, notify_gui=True):
    client = shared.clients.get(dev_id)
    if not client:
        return
    old_volume = float(client.get("volume", 1.0))
    if abs(old_volume - volume) < VOLUME_EPSILON:
        return
    client["volume"] = volume
    if dev_id in shared.AllDevS:
        shared.AllDevS[dev_id]["volume"] = volume
    if notify_gui:
        shared.to_GUI.put([4, [dev_id, volume]])
        shared.VolChanger = dev_id


def send_volume_now(dev_id, volume):
    _volume_set_suppress_until[dev_id] = time.time() + VOLUME_SET_SUPPRESS_SECONDS
    stream = _streams.get(dev_id)
    if stream:
        stream.set_volume(volume)
    else:
        cast_info = _cast_infos.get(dev_id)
        if cast_info:
            set_device_volume(cast_info, volume)


def make_wav_header(sample_rate, channels=2, byte_per_sample=CHROMECAST_BYTE_PER_SAMPLE):
    data_size = 0xFFFFFFFF
    block_align = channels * byte_per_sample
    byte_rate = sample_rate * block_align
    bits_per_sample = byte_per_sample * 8
    cb_size = 22
    fmt_size = 18 + cb_size
    channel_mask = 3 if channels == 2 else 0
    pcm_guid = struct.pack("<IHH8s", 1, 0x0000, 0x0010, b"\x80\x00\x00\xaa\x00\x38\x9b\x71")
    return (
        b"RIFF" + struct.pack("<I", data_size) +
        b"WAVEfmt " +
        struct.pack("<IHHIIHH", fmt_size, 0xFFFE, channels, sample_rate, byte_rate, block_align, bits_per_sample) +
        struct.pack("<HH", cb_size, bits_per_sample) +
        struct.pack("<I", channel_mask) +
        pcm_guid +
        b"data" + struct.pack("<I", data_size)
    )


def float32_to_pcm24(data):
    samples = np.frombuffer(data, dtype=np.float32)
    if samples.size == 0:
        return b""
    samples = np.nan_to_num(samples, nan=0.0, posinf=1.0, neginf=-1.0)
    samples = np.clip(samples, -1.0, 1.0)
    int_samples = (samples * 8388607).astype("<i4")
    bytes4 = int_samples.tobytes()
    return b"".join(bytes4[index:index + 3] for index in range(0, len(bytes4), 4))


class PcmBroadcaster:
    def __init__(self):
        self.clients = set()
        self.lock = threading.Lock()
        self.closed = False
        self.header = b""
        self.packet_count = 0
        self.packet_size = 0
        self.dev_id = "unknown"

    def add_client(self):
        client_queue = queue.Queue(maxsize=HTTP_CLIENT_QUEUE_SIZE)
        with self.lock:
            if self.closed:
                client_queue.put_nowait(None)
            else:
                self.clients.add(client_queue)
                if self.header:
                    client_queue.put_nowait(self.header)
        return client_queue

    def remove_client(self, client_queue):
        with self.lock:
            self.clients.discard(client_queue)

    def publish(self, data):
        self.packet_count += 1
        self.packet_size = len(data)
        if self.packet_count % 100 == 0:
            log(f"output {self.packet_count} packets last size {self.packet_size} bytes")
        with self.lock:
            clients = list(self.clients)
        for client_queue in clients:
            while True:
                try:
                    client_queue.put_nowait(data)
                    break
                except queue.Full:
                    try:
                        client_queue.get_nowait()
                    except queue.Empty:
                        break

    def clear_audio_backlog(self):
        with self.lock:
            clients = list(self.clients)
        for client_queue in clients:
            while client_queue.qsize() > 1:
                try:
                    client_queue.get_nowait()
                except queue.Empty:
                    break

    def close(self):
        with self.lock:
            self.closed = True
            clients = list(self.clients)
            self.clients.clear()
        for client_queue in clients:
            try:
                client_queue.put_nowait(None)
            except queue.Full:
                pass

    def set_header(self, header):
        with self.lock:
            self.header = header


class ChromecastStream:
    def __init__(self, dev_id, cast_info, sample_rate):
        self.dev_id = dev_id
        self.cast_info = cast_info
        self.sample_rate = sample_rate
        self.broadcaster = PcmBroadcaster()
        self.broadcaster.dev_id = dev_id
        self.cast = None
        self.header_sent = False
        self.started = False
        self.play_thread = None
        self.logged_first_audio = False
        self._last_session_check = 0

    def start(self):
        if self.started:
            return
        ensure_http_server()
        self.broadcaster.close()
        self.broadcaster = PcmBroadcaster()
        self.broadcaster.dev_id = self.dev_id
        self.header_sent = False
        self.logged_first_audio = False
        self.broadcaster.clear_audio_backlog()
        header = make_wav_header(self.sample_rate)
        self.broadcaster.set_header(header)
        self.broadcaster.publish(header)
        self.header_sent = True
        self.started = True
        log(f"stream ready {self.cast_info.friendly_name} {self.sample_rate}Hz")
        self.play_thread = threading.Thread(target=self._connect_and_play, daemon=True)
        self.play_thread.start()

    def _connect_and_play(self):
        try:
            log(f"connect start {self.cast_info.friendly_name}")
            cast = pychromecast.Chromecast(self.cast_info, zconf=get_zconf())
            cast.wait(timeout=CAST_WAIT_TIMEOUT)
            log(f"cast wait done {self.cast_info.friendly_name}")
            self.cast = cast
            local_ip = local_ip_for_target(self.cast_info.host)
            port = shared.Config.get("port", 25505) + HTTP_PORT_OFFSET
            url = f"http://{local_ip}:{port}{stream_path(self.dev_id)}"
            media = cast.media_controller
            media.play_media(
                url,
                CONTENT_TYPE,
                title="Audio Mapping",
                stream_type="LIVE",
                autoplay=True,
            )
            log(f"play_media sent {self.cast_info.friendly_name} {self.sample_rate}Hz {url}")
            media.block_until_active(timeout=3)
            media.play()
            log(f"media play sent")
        except Exception as error:
            log(f"connect/play error: {error}")

    def set_volume(self, volume):
        if not self.cast:
            return
        try:
            self.cast.set_volume(max(0.0, min(1.0, float(volume))))
        except Exception as error:
            log(f"volume error: {error}")

    def publish_audio(self, data):
        if not self.logged_first_audio:
            self.logged_first_audio = True
            log(f"first mapped audio {len(data)} bytes")
        # 檢查 Chromecast session 是否 IDLE，若是則重新 play_media
        now = time.time()
        if now - self._last_session_check > 2 and self.cast:
            self._last_session_check = now
            try:
                state = self.cast.media_controller.status.player_state
                if state == "IDLE":
                    log(f"session idle on publish, reloading")
                    local_ip = local_ip_for_target(self.cast_info.host)
                    port = shared.Config.get("port", 25505) + HTTP_PORT_OFFSET
                    url = f"http://{local_ip}:{port}{stream_path(self.dev_id)}"
                    self.cast.media_controller.play_media(url, CONTENT_TYPE, title="Audio Mapping", stream_type="LIVE", autoplay=True)
                    self.cast.media_controller.block_until_active(timeout=3)
                    self.cast.media_controller.play()
                    log(f"session reloaded on publish")
            except Exception:
                pass
        self.broadcaster.clear_audio_backlog()
        self.broadcaster.publish(float32_to_pcm24(data))

    def stop(self):
        self.started = False
        self.broadcaster.close()
        self.header_sent = False
        self.logged_first_audio = False
        self.broadcaster = PcmBroadcaster()
        self.broadcaster.dev_id = self.dev_id
        log(f"broadcaster stopped, cast connection kept")

    def resume(self):
        if self.started:
            return
        ensure_http_server()
        self.broadcaster.close()
        self.broadcaster = PcmBroadcaster()
        self.broadcaster.dev_id = self.dev_id
        self.header_sent = False
        self.logged_first_audio = False
        self.broadcaster.clear_audio_backlog()
        header = make_wav_header(self.sample_rate)
        self.broadcaster.set_header(header)
        self.broadcaster.publish(header)
        self.header_sent = True
        self.started = True
        log(f"stream resumed {self.cast_info.friendly_name}")
        if self.cast:
            try:
                # 檢查 session 是否還在，若已 IDLE 需重新 play_media
                need_reload = True
                try:
                    state = self.cast.media_controller.status.player_state
                    if state == "PAUSED":
                        need_reload = False
                except Exception:
                    pass
                if need_reload:
                    local_ip = local_ip_for_target(self.cast_info.host)
                    port = shared.Config.get("port", 25505) + HTTP_PORT_OFFSET
                    url = f"http://{local_ip}:{port}{stream_path(self.dev_id)}"
                    self.cast.media_controller.play_media(url, CONTENT_TYPE, title="Audio Mapping", stream_type="LIVE", autoplay=True)
                    log(f"play_media sent (resume reload)")
                    self.cast.media_controller.block_until_active(timeout=3)
                    log(f"media active (resume)")
                self.cast.media_controller.play()
                log(f"media play sent (resume)")
            except Exception as error:
                log(f"resume play error: {error}")


def ensure_http_server():
    global _http_server, _http_thread
    with _http_lock:
        if _http_server:
            return
        port = shared.Config.get("port", 25505) + HTTP_PORT_OFFSET

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, fmt, *args):
                return

            def do_GET(self):
                prefix = f"{STREAM_PATH_PREFIX}/"
                if not self.path.startswith(prefix) or not self.path.endswith(".wav"):
                    self.send_error(404)
                    return
                dev_id = self.path[len(prefix):-4]
                stream = _streams.get(dev_id)
                if not stream:
                    self.send_error(404)
                    return
                log(f"HTTP GET {self.path}")
                client_queue = stream.broadcaster.add_client()
                self.send_response(200)
                self.send_header("Content-Type", CONTENT_TYPE)
                self.send_header("Cache-Control", "no-cache, no-store")
                self.send_header("Connection", "close")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                try:
                    logged_first_write = False
                    while True:
                        chunk = client_queue.get()
                        if chunk is None:
                            break
                        if not logged_first_write:
                            logged_first_write = True
                            log(f"HTTP first write {len(chunk)} bytes")
                        self.wfile.write(chunk)
                        self.wfile.flush()
                except (ConnectionError, BrokenPipeError, OSError):
                    pass
                finally:
                    stream.broadcaster.remove_client(client_queue)

        _http_server = ThreadingHTTPServer(("", port), Handler)
        _http_thread = threading.Thread(target=_http_server.serve_forever, daemon=True)
        _http_thread.start()
        log(f"HTTP server started on port {port}")


def update_discovered_devices(devices):
    changed = False
    current_ids = set()
    for device in devices:
        dev_id = f"chromecast:{device.uuid}"
        current_ids.add(dev_id)
        _discovery_misses.pop(dev_id, None)
        _cast_infos[dev_id] = device
        old_client = shared.clients.get(dev_id, {})
        volume = read_device_volume(device, old_client.get("volume", 1.0))
        client_info = {
            "type": "chromecast",
            "MAC": dev_id,
            "name": device.friendly_name,
            "host": device.host,
            "port": device.port,
            "uuid": str(device.uuid),
            "maxVol": 100,
            "chList": ["FL", "FR"],
        }
        if not old_client:
            shared.clients[dev_id] = {**client_info, "volume": volume}
            changed = True
        else:
            for key, value in client_info.items():
                if old_client.get(key) != value:
                    old_client[key] = value
                    changed = True
            update_client_volume(dev_id, volume)
    for dev_id, client in list(shared.clients.items()):
        if client.get("type") == "chromecast" and dev_id not in current_ids:
            misses = _discovery_misses.get(dev_id, 0) + 1
            _discovery_misses[dev_id] = misses
            if misses >= DISCOVERY_MISS_LIMIT:
                shared.clients.pop(dev_id, None)
                _cast_infos.pop(dev_id, None)
                _discovery_misses.pop(dev_id, None)
                changed = True
    if changed:
        shared.to_GUI.put([3, "Rescan"])
    return changed


def discover_once(timeout=5):
    devices, browser = pychromecast.discovery.discover_chromecasts(timeout=timeout)
    try:
        if update_discovered_devices(devices):
            log(f"found {len(devices)} device(s)")
    finally:
        browser.stop_discovery()
        get_zconf()


def discovery_loop():
    while True:
        try:
            discover_once()
        except Exception as error:
            log(f"discovery error: {error}")
        time.sleep(DISCOVERY_INTERVAL)


def sender_loop():
    while True:
        command = shared.to_chromecast.get()
        action = command[0]
        if action == "start":
            _, dev_id, sample_rate = command
            cast_info = _cast_infos.get(dev_id)
            if not cast_info:
                log(f"missing cast info: {dev_id}")
                continue
            log(f"start request {dev_id} {sample_rate}Hz")
            stream = _streams.get(dev_id)
            if stream:
                if stream.sample_rate != sample_rate:
                    stream.stop()
                    _streams.pop(dev_id, None)
                    stream = ChromecastStream(dev_id, cast_info, sample_rate)
                    _streams[dev_id] = stream
                else:
                    try:
                        stream.resume()
                        _pending_audio.pop(dev_id, None)
                        continue
                    except Exception as error:
                        log(f"resume error: {error}, falling back to new stream")
                        stream.stop()
                        _streams.pop(dev_id, None)
                        stream = None
            if not stream:
                stream = ChromecastStream(dev_id, cast_info, sample_rate)
                _streams[dev_id] = stream
            try:
                stream.start()
                _pending_audio.pop(dev_id, None)
            except Exception as error:
                log(f"start error: {error}")
        elif action == "audio":
            _, dev_id, data = command
            publish_audio(dev_id, data)
        elif action == "volume":
            _, dev_id, volume = command
            update_client_volume(dev_id, volume, notify_gui=False)
            now = time.time()
            next_send_at = _volume_next_send_at.get(dev_id, 0)
            if now >= next_send_at:
                send_volume_now(dev_id, volume)
                _volume_next_send_at[dev_id] = now + VOLUME_SYNC_INTERVAL
                _pending_volumes.pop(dev_id, None)
            else:
                _pending_volumes[dev_id] = volume
        elif action == "stop":
            _, dev_id = command
            stream = _streams.get(dev_id)
            if stream:
                stream.stop()
        elif action == "stop_all":
            for dev_id, stream in list(_streams.items()):
                stream.stop()


def start_chromecast():
    threading.Thread(target=sender_loop, daemon=True).start()
    threading.Thread(target=discovery_loop, daemon=True).start()
    threading.Thread(target=volume_sender_loop, daemon=True).start()
    threading.Thread(target=volume_sync_loop, daemon=True).start()
    threading.Thread(target=chromecast_smtc_loop, daemon=True).start()


def publish_audio(dev_id, data):
    stream = _streams.get(dev_id)
    if stream and stream.started:
        stream.publish_audio(data)
    else:
        _pending_audio[dev_id] = data


def volume_sender_loop():
    while True:
        try:
            now = time.time()
            for dev_id, volume in list(_pending_volumes.items()):
                if now < _volume_next_send_at.get(dev_id, 0):
                    continue
                _pending_volumes.pop(dev_id, None)
                send_volume_now(dev_id, volume)
                _volume_next_send_at[dev_id] = now + VOLUME_SYNC_INTERVAL
        except Exception as error:
            log(f"volume sender loop error: {error}")
        time.sleep(VOLUME_SYNC_INTERVAL)


def volume_sync_loop():
    while True:
        try:
            for dev_id, client in list(shared.clients.items()):
                if client.get("type") != "chromecast":
                    continue
                if time.time() < _volume_set_suppress_until.get(dev_id, 0):
                    continue
                fallback = float(client.get("volume", 1.0))
                stream = _streams.get(dev_id)
                if stream and stream.started:
                    volume = read_stream_volume(stream, fallback)
                else:
                    cast_info = _cast_infos.get(dev_id)
                    if not cast_info:
                        continue
                    volume = read_device_volume(cast_info, fallback)
                update_client_volume(dev_id, volume)
        except Exception as error:
            log(f"volume sync loop error: {error}")
        time.sleep(VOLUME_SYNC_INTERVAL)


def chromecast_smtc_loop():
    """Monitor Chromecast playback state and forward play/pause to SMTC."""
    while True:
        try:
            for dev_id, stream in list(_streams.items()):
                if not stream.started or not stream.cast:
                    continue
                try:
                    status = stream.cast.media_controller.status
                    state = getattr(status, "player_state", None)
                except Exception:
                    continue
                if not state:
                    continue
                prev = _smtc_states.get(dev_id)
                if prev is not None and prev != state:
                    if (prev == "PLAYING" and state in ("PAUSED", "IDLE")) or \
                       (state == "PLAYING" and prev in ("PAUSED", "IDLE")):
                        log(f"smtc play/pause state {prev} -> {state}")
                        shared.to_GUI.put([6, 'play/pause'])
                _smtc_states[dev_id] = state
        except Exception as error:
            log(f"smtc loop error: {error}")
        time.sleep(0.5)
