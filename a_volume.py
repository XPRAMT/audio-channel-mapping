from comtypes import COMObject,CoCreateInstance,CLSCTX_ALL,CLSCTX_INPROC_SERVER
from pycaw import pycaw
from pycaw.constants import CLSID_MMDeviceEnumerator
from pycaw.api.audioclient import IAudioClient
from ctypes import POINTER, cast, Structure
from ctypes.wintypes import WORD, DWORD
import time
import copy
import a_shared

# 定義常量
WAVE_FORMAT_EXTENSIBLE = 0xFFFE  # WAVE_FORMAT_EXTENSIBLE 格式標籤
# 定義 WAVEFORMATEX 結構
class WAVEFORMATEX(Structure):
    _fields_ = [
        ("wFormatTag", WORD),
        ("nChannels", WORD),
        ("nSamplesPerSec", DWORD),
        ("nAvgBytesPerSec", DWORD),
        ("nBlockAlign", WORD),
        ("wBitsPerSample", WORD),
        ("cbSize", WORD),
    ]

# 定義 WAVEFORMATEXTENSIBLE 結構
class WAVEFORMATEXTENSIBLE(Structure):
    _fields_ = [
        ("Format", WAVEFORMATEX),
        ("dwChannelMask", DWORD)  # 聲道掩碼
    ]

def parse_channel_mask(channel_mask):
    # 聲道對應的標誌和名稱
    channel_mapping = {
        0x1: "FL",   # Front Left
        0x2: "FR",   # Front Right
        0x4: "CNT",  # Center
        0x8: "SW",   # Subwoofer / Low Frequency Effects
        0x10: "BL",  # Back Left
        0x20: "BR",  # Back Right
        0x40: "FLC", # Front Left of Center
        0x80: "FRC", # Front Right of Center
        0x100: "BC", # Back Center
        0x200: "SL", # Side Left
        0x400: "SR", # Side Right
        0x800: "TC", # Top Center
        0x1000: "TFL", # Top Front Left
        0x2000: "TFC", # Top Front Center
        0x4000: "TFR", # Top Front Right
        0x8000: "TBL", # Top Back Left
        0x10000: "TBC", # Top Back Center
        0x20000: "TBR", # Top Back Right
    }

    # 解析輸入的 channel_mask
    channelsList = []
    for bitmask, name in channel_mapping.items():
        if channel_mask & bitmask:  # 如果該位存在
            channelsList.append(name)

    return channelsList

# 音量事件回調
class AudioEndpointVolumeCallback(COMObject):
    _com_interfaces_ = [pycaw.IAudioEndpointVolumeCallback]
    def __init__(self, devName):
        super().__init__()
        self.devName = devName
    def OnNotify(self, _):
        MainOnNotify(self.devName)

def MainOnNotify(devName):
    if a_shared.callbackOn:
        vol = getDevVol(devName)
        a_shared.AllDevS[devName]['volume'] = vol
        a_shared.to_GUI.put([4,[devName,vol]])
        a_shared.VolChanger = devName
    a_shared.callbackOn = True

def getDevVol(devName):
        return DevS[devName]['volPoint'].GetMasterVolumeLevelScalar()

def setDevVol(devName,vol):
    def PrintVol(vol,name,Xput='[○---]'):
        print(f'{Xput} {name} {round(vol*100)}%')
    # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # 
    if devName in a_shared.AllDevS:
        a_shared.AllDevS[devName]['volume'] = vol
        IP = a_shared.AllDevS[devName]['IP']
        if IP:
            # 發送音量到Client
            a_shared.clients[IP]['volume'] = vol
            a_shared.Header.volume = vol
            a_shared.to_server.put([IP,True,a_shared.header_prefix + a_shared.Header.serialize()])
        else:
            a_shared.callbackOn = False
            # 設定本機裝置
            try:
                DevS[devName]['volPoint'].SetMasterVolumeLevelScalar(vol, None)
                if vol == 0:
                    DevS[devName]['volPoint'].SetMute(1,None)
                else:
                    DevS[devName]['volPoint'].SetMute(0,None)
            except:
                return
    #PrintVol(vol,devName,'[---○]')

tmpScales = {}
def syncVol():
    global tmpScales
    VolChanger = a_shared.VolChanger
    if VolChanger in a_shared.AllDevS:
        PreVol = tmpAllDevS[VolChanger]['volume']
        CurVol = a_shared.AllDevS[VolChanger]['volume']
        nameFlag=True
        for devName in a_shared.AllDevS:
            # 組合名稱
            if nameFlag:
                coName=devName+VolChanger
            else:
                coName=VolChanger+devName
            # 處理音量變化
            if a_shared.AllDevS[devName]['switch'] and a_shared.AllDevS[VolChanger]['switch'] and (devName!=VolChanger):
                def editTmpScale(scale = None):
                    if scale:
                        if nameFlag: # 寫入tmpScales
                            tmpScales[coName] = scale/1
                        else:
                            tmpScales[coName] = 1/scale
                        #print(f'寫入tmpScales:{tmpScales[coName]:.10f} {nameFlag}')
                    else:
                        if nameFlag: # 讀取tmpScales
                            tmpScale = tmpScales.get(coName,1)
                        else:
                            tmpScale = 1/tmpScales.get(coName,1)
                        #print(f'讀取tmpScales:{tmpScale:.10f} {nameFlag}')
                        return tmpScale
                # ＃ ＃ # # ＃ ＃ # # ＃ ＃ # # ＃ ＃ # # ＃ ＃
                # # 計算scale
                scale = tmpAllDevS[devName]['volume']/(PreVol+0.00000000001)
                if 0.9 < scale < 1.1: #吸附
                    scale = 1
                if not coName in tmpScales:
                    editTmpScale(scale)
                # 檢查scale
                tmpScale = editTmpScale()
                newVol = min(CurVol*tmpScale, 1)
                setDevVol(devName,newVol)
                a_shared.to_GUI.put([4,[devName,newVol]])
                #print(f'change slider {devName} {newVol} by {VolChanger}' )

            # 關閉,移除設定
            if not (a_shared.AllDevS[devName]['switch'] and a_shared.AllDevS[VolChanger]['switch']):
                tmpScales.pop(coName,None)
                #print(f'移除 {coName}')

            # 是VolChanger
            if devName == VolChanger:
                nameFlag=False
                
def volSyncMain():
    global Stop,tmpAllDevS,initiDev,DevS
    initiDev = True
    while True:
        DevS = {}
        DevEnumerator = CoCreateInstance(CLSID_MMDeviceEnumerator,pycaw.IMMDeviceEnumerator,CLSCTX_INPROC_SERVER)
        for device in pycaw.AudioUtilities.GetAllDevices():
            state = device.state
            devName = device.FriendlyName
            if state == pycaw.AudioDeviceState.Active and (devName not in DevS):
                DevS[devName] = {}
                #io = pycaw.AudioUtilities.GetEndpointDataFlow(device.id,1) # 0:output,1:input
                Device = DevEnumerator.GetDevice(device.id)
                try:
                    # 添加音量介面
                    EndpointVol = Device.Activate(pycaw.IAudioEndpointVolume._iid_, CLSCTX_ALL, None).QueryInterface(pycaw.IAudioEndpointVolume)
                    DevS[devName]['volPoint'] = EndpointVol
                    # 添加callback
                    callback = AudioEndpointVolumeCallback(devName)
                    EndpointVol.RegisterControlChangeNotify(callback)
                    # 讀取音量
                    DevS[devName]['volume'] = EndpointVol.GetMasterVolumeLevelScalar()
                    # 解析聲道資訊
                    Client = Device.Activate(IAudioClient._iid_, CLSCTX_ALL, None).QueryInterface(IAudioClient)
                    wave_format = Client.GetMixFormat()
                    # 轉型為 WAVEFORMATEXTENSIBLE
                    wave_extensible = cast(wave_format, POINTER(WAVEFORMATEXTENSIBLE))
                    channel_mask = wave_extensible.contents.dwChannelMask
                    DevS[devName]['chList'] = parse_channel_mask(channel_mask)
                    #print('chs: ',a_shared.AllDevS[devName]['chList'])
                except Exception as e:
                    print(f'[ERRO] initi {device.FriendlyName}: {e}')
                    pass
                    
        initiDev = False
        # 開始偵測音量變化
        tmpAllDevS = copy.deepcopy(a_shared.AllDevS)
        a_shared.VolChanger = ''
        Stop = False
        while not Stop:
            if a_shared.AllDevS != tmpAllDevS:
                syncVol()
            tmpAllDevS = copy.deepcopy(a_shared.AllDevS)
            time.sleep(0.05)



        