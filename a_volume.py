from comtypes import COMObject,CoCreateInstance,CLSCTX_ALL,CLSCTX_INPROC_SERVER
from pycaw import pycaw
from pycaw.constants import CLSID_MMDeviceEnumerator

import threading
import time
import copy
import a_shared

def Device_to_volume(Device):
    interface = Device.Activate(pycaw.IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
    return interface.QueryInterface(pycaw.IAudioEndpointVolume) #volume
 
mainDev = Device_to_volume(pycaw.AudioUtilities.GetSpeakers())

class AudioEndpointVolumeCallback(COMObject):
    _com_interfaces_ = [pycaw.IAudioEndpointVolumeCallback]
    def OnNotify(self, _):
        global VolChanger
        # 取得音量資訊
        MainVol,_ = Mainvol()
        VirMainVol = round(a_shared.AllDevS[a_shared.inputDevName]['volume'],2)
        if  VirMainVol != round(MainVol,2):
            a_shared.AllDevS[a_shared.inputDevName]['volume'] = MainVol
            a_shared.to_GUI.put([4,int(MainVol*100)])
            VolChanger = a_shared.inputDevName

def queue_volume():
    global VolChanger
    while True:
        DevName,vol = a_shared.to_volume.get()
        a_shared.AllDevS[a_shared.inputDevName]['volume'] = vol/100
        a_shared.AllDevS[DevName]['volume'] = vol/100
        VolChanger = DevName

threading.Thread(target=queue_volume, daemon=True).start()

def setVol():
    global VolChanger,mainDev
    print(f'============{time.ctime(time.time())}============') 
    def PrintVol(vol,name,Xput='[○---]'):
        print(f'{"-" * 45}{int(vol*100)}%',end='\r')
        print(f'{Xput} {name}')
    # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # 
    VirMainVol = a_shared.AllDevS[a_shared.inputDevName]['volume']
    _,MainMute = Mainvol()
    tmpVolChanger = copy.deepcopy(VolChanger)
    PrintVol(VirMainVol,VolChanger)
    for devName in a_shared.AllDevS:
        IP     = a_shared.AllDevS[devName]['IP']
        switch = a_shared.AllDevS[devName]['switch']
        gain   = a_shared.AllDevS[devName]['volume']
        if switch and devName!=tmpVolChanger:
            if IP:
                # 發送音量到Client
                a_shared.Header.volume = int(VirMainVol*gain*100)
                a_shared.to_server.put([IP,True,a_shared.header_prefix + a_shared.Header.serialize()])
                PrintVol(VirMainVol*gain,devName,'[---○]')
            else:
                try:
                    volume = VolCtrlItf[devName]
                    if devName == a_shared.inputDevName:
                            volume.SetMasterVolumeLevelScalar(VirMainVol, None)
                            a_shared.to_GUI.put([4,int(VirMainVol*100)])
                            PrintVol(VirMainVol,devName,'[---○]')
                    else:
                        volume.SetMasterVolumeLevelScalar(VirMainVol*gain, None)
                        volume.SetMute(MainMute,None)
                        PrintVol(VirMainVol*gain,devName,'[---○]')
                except Exception as e:
                    print(f'Set Vol Error:\n{e}')
                    
def Mainvol(vol=None):
    global mainDev
    if vol==None:
        return mainDev.GetMasterVolumeLevelScalar(),mainDev.GetMute()
    else:
        mainDev.SetMasterVolumeLevelScalar(vol, None)
        if vol == 0:
            mainDev.SetMute(1,None)
        else:
            mainDev.SetMute(0,None)
        
def VolumeSync():
    global VolChanger,mainDev,Stop,tmpVolSettings,VolCtrlItf,callback
    while True:
        # 初始化資源
        VolCtrlItf={}
        DevEnumerator = CoCreateInstance(CLSID_MMDeviceEnumerator,pycaw.IMMDeviceEnumerator,CLSCTX_INPROC_SERVER)
        for device in pycaw.AudioUtilities.GetAllDevices():
            try:
                VolCtrlItf[device.FriendlyName]=Device_to_volume(DevEnumerator.GetDevice(device.id))
            except Exception as e:
                #print(f'[ERROR] init Vol:/n{e}')
                pass
        mainDev = Device_to_volume(pycaw.AudioUtilities.GetSpeakers())
        callback = AudioEndpointVolumeCallback()
        mainDev.RegisterControlChangeNotify(callback)
        VolChanger = ''
        Stop = False
        #print("\n[INFO] 已啟動音量同步",end='\r')
        # 持續
        tmpVolSettings = copy.deepcopy(a_shared.AllDevS)
        while not Stop:
            if a_shared.AllDevS != tmpVolSettings:
                setVol()
            tmpVolSettings = copy.deepcopy(a_shared.AllDevS)
            time.sleep(0.05)
        #print("\n[INFO] 初始化音量同步",end='\r')
        # 釋放資源
        try:
            if mainDev and callback:
                mainDev.UnregisterControlChangeNotify(callback)
        except Exception as release_error:
            print(f"[ERROR] 釋放資源時發生錯誤: {release_error}")

        