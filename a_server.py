import socket
import struct
import threading
import time
from zeroconf import Zeroconf, ServiceInfo
import a_shared
import subprocess
import json

# 獲取本機的區域網 IP
def get_local_ip():
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        try:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
        except Exception:
            return "127.0.0.1"

# 獲取client的MAC
def get_mac_address(ip):
    try:
        output = subprocess.check_output(f"arp -a {ip}", shell=True, text=True)
        for line in output.split("\n"):
            if ip in line:
                return line.split()[1]
    except Exception as e:
        print(f"[ERRO] retrieving MAC address: {e}")
        return ip

# 啟動 mDNS 服務廣播
def start_mdns():
    global HOST_IP, PORT
    hostname = socket.gethostname()
    SERVICE_TYPE = "_vol-ctrl._tcp.local."
    SERVICE_INSTANCE_NAME = f"{hostname}.{SERVICE_TYPE}"
    HOST_IP = get_local_ip()
    PORT = a_shared.Config.get('port', 25505)
    zeroconf = Zeroconf()
    service_info = ServiceInfo(
        SERVICE_TYPE,
        SERVICE_INSTANCE_NAME,
        addresses=[socket.inet_aton(HOST_IP)],
        port=PORT,
        properties={"description": "Audio Mapping Service"},
    )
    zeroconf.register_service(service_info)
    print(f"[INFO] 已廣播服務: {SERVICE_INSTANCE_NAME} 端口: {PORT}")
    return zeroconf

def handle_client(client_socket, client_IP):
    global clients_lock
    client_MAC = get_mac_address(client_IP)
    print(f"[INFO] 客戶端已連接 IP: {client_IP} MAC: {client_MAC}")
    with clients_lock:
        a_shared.clients[client_IP] = {'socket': client_socket, 'MAC': client_MAC}
    try:
        while True:
            # 讀取 2 位元組長度前綴
            len_bytes = client_socket.recv(2)
            if not len_bytes or len(len_bytes) < 2:
                break
            dataLen = int.from_bytes(len_bytes, byteorder='big')
            # 讀取 JSON 本體
            data = b''
            while len(data) < dataLen:
                chunk = client_socket.recv(dataLen - len(data))
                if not chunk:
                    break
                data += chunk
            if not data:
                break
            recvDict = json.loads(data.decode('utf-8'))

            if a_shared.NETWORK_DEBUG:
                print(f'[TCP←] {client_IP}:{client_MAC} {json.dumps(recvDict, ensure_ascii=False)}')

            # 交握：儲存 udpPort
            if 'udpPort' in recvDict:
                with clients_lock:
                    a_shared.clients[client_IP]['udpPort'] = recvDict['udpPort']
                print(f"[INFO] Client UDP port: {recvDict['udpPort']}")

            if 'mediaKey' in recvDict:
                a_shared.to_GUI.put([6, recvDict['mediaKey']])
            elif 'startStop' in recvDict:
                if not a_shared.Header.startStop:
                    # 全域未串流 → 直接觸發開始
                    a_shared.to_GUI.put([7, client_MAC])
                elif client_MAC in a_shared.Config.get('devList', []):
                    # 全域串流中且客戶端在 devList → 觸發停止
                    a_shared.to_GUI.put([7, client_MAC])
                else:
                    # 全域串流中但客戶端不在 devList → 加入並重新掃描
                    a_shared.Config.setdefault('devList', []).append(client_MAC)
                    a_shared.to_GUI.put([3, 'Resacn'])
                    print(f"[INFO] 客戶端 {client_MAC} 加入串流")
            else:
                a_shared.clients[client_IP].update(recvDict)
                if client_MAC in a_shared.AllDevS:
                    a_shared.AllDevS[client_MAC].update({'volume': recvDict['volume']})
                    a_shared.to_GUI.put([4, [client_MAC, recvDict['volume']]])
                    a_shared.VolChanger = client_MAC
                    a_shared.to_volume.put([3, 'Resacn'])
                else:
                    a_shared.to_GUI.put([3, 'Resacn'])
    except Exception as e:
        print(f'處理回傳值錯誤: {e}')
    finally:
        print(f"[INFO] 客戶端已斷開  IP: {client_IP} MAC: {client_MAC}")
        a_shared.to_GUI.put([3, 'Resacn'])
        with clients_lock:
            a_shared.clients.pop(client_IP, None)
        client_socket.close()

# 發送消息（TCP JSON 狀態 + UDP 音頻）
def send_message():
    global clients_lock, udp_socket
    udp_seq = 0
    stream_start_time = 0
    while True:
        IP, msg_type, data = a_shared.to_server.get()
        client = a_shared.clients.get(IP)
        if not client:
            continue
        with clients_lock:
            if msg_type == 'state':
                # === TCP: 完整狀態 JSON（startStop 依客戶端是否在串流中決定） ===
                client_MAC = client.get('MAC', '')
                is_streaming = (a_shared.Header.startStop
                                and client_MAC in a_shared.Config.get('devList', []))
                json_str = json.dumps({
                    "type": "state",
                    "sampleRate": a_shared.Header.sampleRate,
                    "blockSize":  a_shared.Header.blockSize,
                    "channels":   a_shared.Header.channels,
                    "volume":     client.get('volume', a_shared.Header.volume),
                    "startStop":  is_streaming,
                    "isPlaying":  a_shared.Header.isPlaying
                })
                payload = json_str.encode('utf-8')
                outdata = len(payload).to_bytes(2, 'big') + payload
                if a_shared.NETWORK_DEBUG:
                    print(f'[TCP→] {IP} {json_str}')
                try:
                    client['socket'].sendall(outdata)
                except Exception as e:
                    print(f'TCP Send State Error: {e}')
            elif msg_type == 'volume':
                # === TCP: 僅音量 JSON ===
                json_str = a_shared.Header.to_volume_json()
                payload = json_str.encode('utf-8')
                outdata = len(payload).to_bytes(2, 'big') + payload
                if a_shared.NETWORK_DEBUG:
                    print(f'[TCP→] {IP} {json_str}')
                try:
                    client['socket'].sendall(outdata)
                except Exception as e:
                    print(f'TCP Send Volume Error: {e}')
            else:
                # === UDP: 音頻封包 ===
                udp_port = client.get('udpPort')
                if not udp_port:
                    continue
                # 追蹤串流開始時間
                if a_shared.Header.startStop and stream_start_time == 0:
                    stream_start_time = int(time.time() * 1000)
                elif not a_shared.Header.startStop:
                    stream_start_time = 0
                    udp_seq = 0
                # 封裝 UDP 封包: [seq:4][timestamp_ms:4][pcm_data:N]
                timestamp = int(time.time() * 1000) - stream_start_time if stream_start_time else 0
                header = struct.pack('!II', udp_seq, timestamp)
                packet = header + data
                try:
                    udp_socket.sendto(packet, (IP, udp_port))
                    udp_seq = (udp_seq + 1) & 0xFFFFFFFF
                except Exception as e:
                    print(f'UDP Send Error: {e}')

def start_server():
    global clients_lock, udp_socket
    # 啟動 mDNS
    zeroconf = start_mdns()
    UDP_PORT = PORT + a_shared.UDP_PORT_OFFSET
    # 啟動 TCP 伺服器
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_socket.bind((HOST_IP, PORT))
    server_socket.listen(5)
    # 初始化 UDP socket（音頻通道，端口 = TCP + 1）
    udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp_socket.bind((HOST_IP, UDP_PORT))
    print(f"[INFO] TCP 監聽 {HOST_IP}:{PORT}  |  UDP 發送端口 {HOST_IP}:{UDP_PORT}")
    clients_lock = threading.Lock()
    # 啟動發送執行緒
    threading.Thread(target=send_message, daemon=True).start()
    # 處理客戶端連線
    try:
        while True:
            client_socket, client_address = server_socket.accept()
            threading.Thread(
                target=handle_client,
                args=(client_socket, client_address[0]),
                daemon=True
            ).start()
    finally:
        server_socket.close()
        udp_socket.close()
        zeroconf.unregister_all_services()
        zeroconf.close()
        print("[INFO] 伺服器已終止")


