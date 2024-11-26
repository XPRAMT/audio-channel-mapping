import socket
import struct
import threading
from zeroconf import Zeroconf, ServiceInfo
import a_shared

connected_clients = {}

# 獲取本機的區域網 IP
def get_local_ip():
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        try:
            # 連接到一個外部地址以獲取本機 IP，但不發送任何數據
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
        except Exception:
            return "127.0.0.1"  # 回退到回環地址

def recvall(sock, n):
    # Helper function to receive n bytes or return None if EOF is hit
    data = b''
    while len(data) < n:
        packet = sock.recv(n - len(data))
        if not packet:
            return None
        data += packet
    return data

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
    print(f"\n[INFO] 已廣播服務: {SERVICE_INSTANCE_NAME}",end='\r')
    return zeroconf

def handle_client(client_socket, client_address):
    global clients_lock, connected_clients
    # 處理每個客戶端的連接
    print(f"\n[INFO] 客戶端已連接 {client_address}",end='\r')
    a_shared.to_GUI.put([3,client_address])
    with clients_lock:
        connected_clients[client_address[0]]=client_socket
    try:
        while True:
            # 接收4位元組的整數
            data = recvall(client_socket, 4)
            if not data:
                break
            # 將位元組資料解包為整數
            (number,) = struct.unpack('!i', data)
            # 接收数据
            a_shared.to_volume.put([client_address[0],number])
            #print(f'[○---] {client_socket.getpeername()[0]}: {number}%')
    except:
        pass
    finally:
        print(f"\n[INFO] 客戶端已斷開 {client_address}",end='\r')
        a_shared.to_GUI.put([3,client_address])
        with clients_lock:
            connected_clients.pop(client_address[0],None) #移除clients
        client_socket.close()

# 廣播
def send_message(): #向所有已連接的客戶端發送消息
    global clients_lock, connected_clients
    while True:
        IP,isVol,data = a_shared.to_server.get()
        client_socket = connected_clients.get(IP)
        if client_socket:
            with clients_lock:
                if isVol:
                    outdata = data
                else: # 計算總數據大小（header + data）,打包總大小為 4 字節
                    size_prefix = struct.pack('!I',(a_shared.HEADER_SIZE + len(data)) )
                    outdata = (size_prefix + a_shared.header_bytes + data)
                try:
                    client_socket.sendall(outdata) #TCP
                    #udp_socket.sendto(outdata, client_socket.getpeername()) #UDP
                except Exception as e:
                    print(f'Send Data Error:/n{e}')

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
    print(f"\n[INFO] 已啟動主機，正在監聽 {HOST_IP}:{PORT}")
    clients_lock = threading.Lock()
    # 接收資料queue
    threading.Thread(target=send_message, daemon=True).start()
    #處理客戶端的連接
    try:
        while True:
            client_socket, client_address = server_socket.accept() 
            threading.Thread( # 為每個連線啟動一個線程
                target=handle_client,
                args=(client_socket, client_address),
                daemon=True
            ).start()
    finally:
        server_socket.close()
        udp_socket.close()
        zeroconf.unregister_all_services()
        zeroconf.close()
        print("\n[INFO] 伺服器已終止",end='\r')