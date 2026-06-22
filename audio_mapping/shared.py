import queue
import json
###########Queue###########
to_GUI = queue.Queue()
to_server = queue.Queue()
to_chromecast = queue.Queue()
to_volume = queue.Queue()
to_mapping = queue.Queue()
###########Arg#############
clients = {}
Config = {}
AllDevS = {}
VolChanger = ''
UDP_PORT_OFFSET = 1  # UDP port = TCP port + 1
###########Flag############
isloopback = True
SliderOn = True
callbackOn = True
NETWORK_DEBUG = True  # 設為 True 時顯示所有 TCP 收發訊息
###########Class############
class AudioHeader:
    """音訊狀態容器，用於跨模組共享並序列化為 JSON 狀態封包"""
    def __init__(self):
        self.sampleRate = 48000
        self.blockSize = 320
        self.channels = 2
        self.volume = 0.0
        self.startStop = False
        self.isPlaying = False

    def to_state_json(self) -> str:
        """輸出完整狀態 JSON（不含 type 前綴）"""
        return json.dumps({
            "sampleRate": self.sampleRate,
            "blockSize":  self.blockSize,
            "channels":   self.channels,
            "volume":     self.volume,
            "startStop":  self.startStop,
            "isPlaying":  self.isPlaying
        })

    def to_volume_json(self) -> str:
        """輸出僅音量變更的 JSON"""
        return json.dumps({"type": "volume", "volume": self.volume})

Header = AudioHeader()