from comtypes import COMObject,CoCreateInstance,CLSCTX_ALL,CLSCTX_INPROC_SERVER
from pycaw import pycaw
from pycaw.constants import CLSID_MMDeviceEnumerator
import time

class AudioEndpointVolumeCallback(COMObject):
    _com_interfaces_ = [pycaw.IAudioEndpointVolumeCallback]
    def OnNotify(self, pNotify):
        global Vol_switch
        Vol_switch=True

Vol_settings=[]
def VolumeSettings(vol_settings):
    global Vol_settings,Vol_switch
    Vol_settings=vol_settings
    Vol_switch=True

def setVol():
    global Vol_settings,devicelist
    # 取得主音量
    vol,mute = GetMainvol()
    # 設定音量
    for name,gain,switch in Vol_settings:
        if switch:
            for device in devicelist:
                if name == device.FriendlyName:
                    device_enumerator = CoCreateInstance(CLSID_MMDeviceEnumerator,pycaw.IMMDeviceEnumerator,CLSCTX_INPROC_SERVER)
                    Device = device_enumerator.GetDevice(device.id)
                    try:
                        interface = Device.Activate(pycaw.IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
                        volume = interface.QueryInterface(pycaw.IAudioEndpointVolume)
                        volume.SetMasterVolumeLevelScalar(vol*gain, None)
                        volume.SetMute(mute,None)
                    except Exception as e:
                        #print(e)
                        pass
def GetMainvol():
    Device = pycaw.AudioUtilities.GetSpeakers()
    interface = Device.Activate(pycaw.IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
    volume = interface.QueryInterface(pycaw.IAudioEndpointVolume)
    return volume.GetMasterVolumeLevelScalar(),volume.GetMute()

def VolumeSync():
    global Vol_switch,devicelist,isStop
    devicelist = pycaw.AudioUtilities.GetAllDevices()
    # 音量變化回呼
    devices = pycaw.AudioUtilities.GetSpeakers()
    interface = devices.Activate(pycaw.IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
    volume = interface.QueryInterface(pycaw.IAudioEndpointVolume)
    callback = AudioEndpointVolumeCallback()
    volume.RegisterControlChangeNotify(callback)
    Vol_switch = False
    isStop = False
    # 持續
    while not isStop:
        if Vol_switch:
            setVol()
            Vol_switch = False
        time.sleep(0.1)

def Stop():
    global isStop
    isStop = True
