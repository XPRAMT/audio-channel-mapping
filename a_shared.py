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
    sampleRate: int
    blockSize: int
    channels: int
    volume: float
    startStop: bool
    # 格式
    FORMAT = '!IIIf?'
    SIZE = struct.calcsize(FORMAT)

    def serialize(self) -> bytes:
        return struct.pack(
            self.FORMAT,
            self.sampleRate,
            self.blockSize,
            self.channels,
            self.volume,
            self.startStop
        )

Header = AudioHeader(sampleRate=48000, blockSize=320, channels=2, volume=0, startStop=False)
HEADER_SIZE = AudioHeader.SIZE
header_prefix = struct.pack('!I', HEADER_SIZE)