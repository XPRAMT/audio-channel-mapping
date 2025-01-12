import socket
import struct
import threading
from zeroconf import Zeroconf, ServiceInfo
import a_shared
import subprocess
import json

# 獲取本機的區域網 IP
def get_local_ip():
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        try:
            # 連接到一個外部地址以獲取本機 IP，但不發送任何數據
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
        except Exception:
            return "127.0.0.1"  # 回退到回環地址
# 獲取client的MAC
def get_mac_address(ip):
    try:
        # 執行 arp 命令以解析 IP 對應的 MAC 地址
        output = subprocess.check_output(f"arp -a {ip}", shell=True, text=True)
        for line in output.split("\n"):
            if ip in line:
                return line.split()[1]  # 假設第三欄是 MAC 地址
    except Exception as e:
        print(f"[ERRO] retrieving MAC address: {e}")
        return ip
    
#啟動 mDNS 服務廣播
def start_mdns():
    global HOST_IP,PORT
    ######################
    hostname = socket.gethostname()
    SERVICE_TYPE = "_vol-ctrl._tcp.local."
    SERVICE_INSTANCE_NAME = f"{hostname}.{SERVICE_TYPE}"
    HOST_IP = get_local_ip()
    PORT = 25505
    ######################
    zeroconf = Zeroconf()
    service_info = ServiceInfo(
        SERVICE_TYPE,
        SERVICE_INSTANCE_NAME,
        addresses=[socket.inet_aton(HOST_IP)],
        port=PORT,
        properties={"description": "Test mDNS Service"},
    )
    zeroconf.register_service(service_info)
    print(f"[INFO] 已廣播服務: {SERVICE_INSTANCE_NAME}")
    return zeroconf

def handle_client(client_socket, client_IP):
    global clients_lock
    client_MAC = get_mac_address(client_IP)  # 獲取 MAC 地址
    # 處理每個客戶端的連接
    print(f"[INFO] 客戶端已連接 IP: {client_IP} MAC: {client_MAC}")
    with clients_lock:
        a_shared.clients[client_IP] = {'socket':client_socket,'MAC':client_MAC}
    try:
        while True:
            dataLen = int.from_bytes(client_socket.recv(2), byteorder='big')
            data = client_socket.recv(dataLen).decode('utf-8')
            if not data:
                break
            # 將位元組資料解包
            recvDict = json.loads(data)
            if 'mediaKey' in recvDict:
                a_shared.to_GUI.put([6,recvDict['mediaKey']])
            else:
                a_shared.clients[client_IP].update(recvDict)
                if client_MAC in a_shared.AllDevS:
                    #print(f'Receive vol from {client_IP} {header.volume}')
                    a_shared.AllDevS[client_MAC].update({'volume':recvDict['volume']})
                    a_shared.to_GUI.put([4,[client_MAC,recvDict['volume']]])
                    a_shared.VolChanger = client_MAC
                    a_shared.to_volume.put([3,'Resacn'])
                else:
                    a_shared.to_GUI.put([3,'Resacn'])
    except Exception as e:
        print(f'處理回傳值錯誤:{e}')
    finally:
        print(f"[INFO] 客戶端已斷開  IP: {client_IP} MAC: {client_MAC}")
        a_shared.to_GUI.put([3,'Resacn'])
        with clients_lock:
            a_shared.clients.pop(client_IP,None) #移除clients
        client_socket.close()

# 發送消息
def send_message(): 
    global clients_lock
    while True:
        IP,isVol,data = a_shared.to_server.get()
        client = a_shared.clients.get(IP)
        if client:
            with clients_lock:
                if isVol:
                    outdata = data
                else: # 計算總數據大小（header + data）,打包總大小為 4 字節
                    size_prefix = struct.pack('!I',(a_shared.HEADER_SIZE + len(data)) )
                    outdata = (size_prefix + a_shared.Header.serialize() + data)
                #發送
                try:
                    client['socket'].sendall(outdata) #TCP
                    #udp_socket.sendto(outdata, client['socket'].getsockname()) #UDP
                except Exception as e:
                    print(f'Send Data Error:{e}')

def start_server():
    global clients_lock,udp_socket
    # 啟動mDNS
    zeroconf = start_mdns()
    # 啟動主機服務
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.bind((HOST_IP, PORT))
    server_socket.listen(5)
    # 初始化 UDP 
    udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp_socket.bind((HOST_IP, PORT))
    print(f"[INFO] 已啟動主機，正在監聽 {HOST_IP}:{PORT}")
    clients_lock = threading.Lock()
    # 接收資料queue
    threading.Thread(target=send_message, daemon=True).start()
    #處理客戶端的連接
    try:
        while True:
            client_socket, client_address = server_socket.accept() 
            threading.Thread( # 為每個連線啟動一個線程
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


