import queue
import struct
from dataclasses import dataclass

to_GUI = queue.Queue()
to_server = queue.Queue()
to_volume = queue.Queue()
to_mapping = queue.Queue()


AllDevS = {}
inputDevName = ''
ScanColDown = False

@dataclass
class AudioHeader:
    sample_rate: int
    block_size: int
    channels: int
    volume: int
    # 格式
    FORMAT = '!IIII' #4*4=16bytes
    SIZE = struct.calcsize(FORMAT)

    def serialize(self) -> bytes: # 將 header 序列化為固定格式的二進制數據。
        return struct.pack(self.FORMAT, self.sample_rate, self.block_size, self.channels ,self.volume)

    @staticmethod
    def deserialize(data: bytes): # 從二進制數據反序列化為 AudioHeader 對象。
        if len(data) != AudioHeader.SIZE:
            raise ValueError(f"Data must be exactly {AudioHeader.SIZE} bytes")
        sample_rate, block_size, channels, volume = struct.unpack(AudioHeader.FORMAT, data)
        return AudioHeader(sample_rate, block_size, channels, volume)
    
Header = AudioHeader(sample_rate=48000, block_size=1024, channels=2, volume=0)
HEADER_SIZE = AudioHeader.SIZE
header_prefix = struct.pack('!I', HEADER_SIZE)
header_bytes = Header.serialize()