import queue
import struct
from dataclasses import dataclass
###########Queue###########
to_GUI = queue.Queue()
to_server = queue.Queue()
to_volume = queue.Queue()
to_mapping = queue.Queue()
###########Arg#############
clients = {}
Config = {}
AllDevS = {}
VolChanger = ''
###########Flag############
isloopback = True
SliderOn = True
callbackOn = True
###########Class############
@dataclass
class AudioHeader:
    sample_rate: int
    block_size: int
    channels: int
    volume: float
    # 格式
    FORMAT = '!IIIf' #4*4 Bytes
    SIZE = struct.calcsize(FORMAT)

    def serialize(self) -> bytes: # 將 header 序列化為固定格式的二進制數據。
        return struct.pack(self.FORMAT, self.sample_rate, self.block_size,
                            self.channels ,self.volume)

Header = AudioHeader(sample_rate=48000, block_size=320, channels=2, volume=0)
HEADER_SIZE = AudioHeader.SIZE
header_prefix = struct.pack('!I', HEADER_SIZE)