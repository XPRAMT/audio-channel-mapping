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
inputDevName = ''
VolChanger = ''
###########Flag############
input_class_loopback = True
SliderOn = True
callbackOn = True
###########Class############
@dataclass
class AudioHeader:
    sample_rate: int
    block_size: int
    channels: int
    maxVol: int
    volume: float
    # 格式
    FORMAT = '!IIIIf' #5*4 Bytes
    SIZE = struct.calcsize(FORMAT)

    def serialize(self) -> bytes: # 將 header 序列化為固定格式的二進制數據。
        return struct.pack(self.FORMAT, self.sample_rate, self.block_size,
                            self.channels ,self.maxVol ,self.volume)

    @staticmethod
    def deserialize(data: bytes): # 從二進制數據反序列化為 AudioHeader 對象。
        if len(data) != AudioHeader.SIZE:
            raise ValueError(f"Data must be exactly {AudioHeader.SIZE} bytes")
        sample_rate, block_size, channels, maxVol, volume = struct.unpack(AudioHeader.FORMAT, data)
        return AudioHeader(sample_rate, block_size, channels, maxVol, volume)
    
Header = AudioHeader(sample_rate=48000, block_size=320, channels=2, maxVol=100, volume=0)
HEADER_SIZE = AudioHeader.SIZE
header_prefix = struct.pack('!I', HEADER_SIZE)
header_bytes = Header.serialize()