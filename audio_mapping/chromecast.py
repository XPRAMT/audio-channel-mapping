import queue
import socket
import struct
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import numpy as np
import pychromecast

from . import shared

HTTP_PORT_OFFSET = 100
STREAM_PATH_PREFIX = "/chromecast"
CONTENT_TYPE = "audio/wav"
SUPPORTED_SAMPLE_RATES = (44100, 48000, 88200, 96000)
DISCOVERY_INTERVAL = 30

_browser = None
_cast_infos = {}
_streams = {}
_http_server = None
_http_thread = None
_http_lock = threading.Lock()


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


def make_wav_header(sample_rate, channels=2, byte_per_sample=2):
    data_size = 0xFFFFFFFF
    block_align = channels * byte_per_sample
    byte_rate = sample_rate * block_align
    bits_per_sample = byte_per_sample * 8
    return (
        b"RIFF" + struct.pack("<I", data_size) +
        b"WAVEfmt " +
        struct.pack("<IHHIIHH", 16, 1, channels, sample_rate, byte_rate, block_align, bits_per_sample) +
        b"data" + struct.pack("<I", data_size)
    )


def float32_to_pcm16(data):
    samples = np.frombuffer(data, dtype=np.float32)
    if samples.size == 0:
        return b""
    samples = np.nan_to_num(samples, nan=0.0, posinf=1.0, neginf=-1.0)
    samples = np.clip(samples, -1.0, 1.0)
    return (samples * 32767).astype("<i2").tobytes()


class PcmBroadcaster:
    def __init__(self):
        self.clients = set()
        self.lock = threading.Lock()
        self.closed = False
        self.header_cache = bytearray()
        self.header_cache_limit = 65536

    def add_client(self):
        client_queue = queue.Queue(maxsize=256)
        with self.lock:
            if self.closed:
                client_queue.put_nowait(None)
            else:
                self.clients.add(client_queue)
                if self.header_cache:
                    client_queue.put_nowait(bytes(self.header_cache))
        return client_queue

    def remove_client(self, client_queue):
        with self.lock:
            self.clients.discard(client_queue)

    def publish(self, data):
        with self.lock:
            if len(self.header_cache) < self.header_cache_limit:
                remaining = self.header_cache_limit - len(self.header_cache)
                self.header_cache.extend(data[:remaining])
            clients = list(self.clients)
        for client_queue in clients:
            try:
                client_queue.put_nowait(data)
            except queue.Full:
                try:
                    client_queue.get_nowait()
                    client_queue.put_nowait(data)
                except queue.Empty:
                    pass

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


class ChromecastStream:
    def __init__(self, dev_id, cast_info, sample_rate):
        self.dev_id = dev_id
        self.cast_info = cast_info
        self.sample_rate = sample_rate
        self.broadcaster = PcmBroadcaster()
        self.cast = None
        self.header_sent = False
        self.started = False

    def start(self):
        if self.started:
            return
        ensure_http_server()
        zconf = _browser.zc if _browser else None
        self.cast = pychromecast.Chromecast(self.cast_info, zconf=zconf)
        self.cast.wait(timeout=10)
        local_ip = local_ip_for_target(self.cast_info.host)
        port = shared.Config.get("port", 25505) + HTTP_PORT_OFFSET
        url = f"http://{local_ip}:{port}{stream_path(self.dev_id)}"
        media = self.cast.media_controller
        media.play_media(
            url,
            CONTENT_TYPE,
            title="Audio Mapping",
            stream_type="LIVE",
            autoplay=True,
        )
        self.started = True
        print(f"[Chromecast] start {self.cast_info.friendly_name} {self.sample_rate}Hz {url}")

    def publish_audio(self, data):
        if not self.header_sent:
            self.broadcaster.publish(make_wav_header(self.sample_rate))
            self.header_sent = True
        self.broadcaster.publish(float32_to_pcm16(data))

    def stop(self):
        try:
            if self.cast:
                self.cast.media_controller.stop()
        except Exception as error:
            print(f"[Chromecast] stop error: {error}")
        self.broadcaster.close()
        self.started = False
        self.header_sent = False


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
                client_queue = stream.broadcaster.add_client()
                self.send_response(200)
                self.send_header("Content-Type", CONTENT_TYPE)
                self.send_header("Cache-Control", "no-cache, no-store")
                self.send_header("Connection", "close")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                try:
                    while True:
                        chunk = client_queue.get()
                        if chunk is None:
                            break
                        self.wfile.write(chunk)
                        self.wfile.flush()
                except (ConnectionError, BrokenPipeError, OSError):
                    pass
                finally:
                    stream.broadcaster.remove_client(client_queue)

        _http_server = ThreadingHTTPServer(("", port), Handler)
        _http_thread = threading.Thread(target=_http_server.serve_forever, daemon=True)
        _http_thread.start()
        print(f"[Chromecast] HTTP server started on port {port}")


def update_discovered_devices(devices):
    changed = False
    current_ids = set()
    for device in devices:
        dev_id = f"chromecast:{device.uuid}"
        current_ids.add(dev_id)
        _cast_infos[dev_id] = device
        client = {
            "type": "chromecast",
            "MAC": dev_id,
            "name": f"Chromecast - {device.friendly_name}",
            "host": device.host,
            "port": device.port,
            "uuid": str(device.uuid),
            "volume": 1.0,
            "maxVol": 100,
            "chList": ["FL", "FR"],
        }
        if shared.clients.get(dev_id) != client:
            shared.clients[dev_id] = client
            changed = True
    for dev_id, client in list(shared.clients.items()):
        if client.get("type") == "chromecast" and dev_id not in current_ids:
            shared.clients.pop(dev_id, None)
            _cast_infos.pop(dev_id, None)
            changed = True
    if changed:
        shared.to_GUI.put([3, "Rescan"])


def discover_once(timeout=5):
    global _browser
    devices, browser = pychromecast.discovery.discover_chromecasts(timeout=timeout)
    if _browser:
        try:
            _browser.stop_discovery()
        except Exception:
            pass
    _browser = browser
    update_discovered_devices(devices)
    print(f"[Chromecast] found {len(devices)} device(s)")


def discovery_loop():
    while True:
        try:
            discover_once()
        except Exception as error:
            print(f"[Chromecast] discovery error: {error}")
        time.sleep(DISCOVERY_INTERVAL)


def sender_loop():
    while True:
        command = shared.to_chromecast.get()
        action = command[0]
        if action == "start":
            _, dev_id, sample_rate = command
            cast_info = _cast_infos.get(dev_id)
            if not cast_info:
                print(f"[Chromecast] missing cast info: {dev_id}")
                continue
            stream = _streams.get(dev_id)
            if stream and stream.sample_rate != sample_rate:
                stream.stop()
                _streams.pop(dev_id, None)
                stream = None
            if not stream:
                stream = ChromecastStream(dev_id, cast_info, sample_rate)
                _streams[dev_id] = stream
            try:
                stream.start()
            except Exception as error:
                print(f"[Chromecast] start error: {error}")
        elif action == "audio":
            _, dev_id, data = command
            stream = _streams.get(dev_id)
            if stream and stream.started:
                stream.publish_audio(data)
        elif action == "stop":
            _, dev_id = command
            stream = _streams.pop(dev_id, None)
            if stream:
                stream.stop()
        elif action == "stop_all":
            for dev_id, stream in list(_streams.items()):
                stream.stop()
                _streams.pop(dev_id, None)


def start_chromecast():
    threading.Thread(target=sender_loop, daemon=True).start()
    threading.Thread(target=discovery_loop, daemon=True).start()
