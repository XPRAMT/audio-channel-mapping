from comtypes import COMObject,CoCreateInstance,CLSCTX_ALL,CLSCTX_INPROC_SERVER
from pycaw import pycaw
from pycaw.constants import CLSID_MMDeviceEnumerator
import time
import copy
import a_shared
 
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

def initVol():
    for devName in VolCtrlItf:
        MainOnNotify(devName)
    
def getDevVol(devName):
        return VolCtrlItf[devName].GetMasterVolumeLevelScalar()

def setDevVol(devName,vol):
    def PrintVol(vol,name,Xput='[○---]'):
        print(f'{Xput} {name} {round(vol*100)}%')
    # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # 
    if devName in a_shared.AllDevS:
        a_shared.AllDevS[devName]['volume'] = vol
        IP = a_shared.AllDevS[devName]['IP']
        if IP:
            # 發送音量到Client
            a_shared.clients[devName]['header'].volume = vol
            a_shared.to_server.put([IP,True,a_shared.header_prefix + a_shared.clients[devName]['header'].serialize()])
        else:
            a_shared.callbackOn = False
            # 設定本機裝置
            try:
                VolCtrlItf[devName].SetMasterVolumeLevelScalar(vol, None)
                if vol == 0:
                    VolCtrlItf[devName].SetMute(1,None)
                else:
                    VolCtrlItf[devName].SetMute(0,None)
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
                
def volSync():
    global Stop,tmpAllDevS,VolCtrlItf,callbacks
    while True:
        # 為每個裝置綁定音量介面
        VolCtrlItf={}
        DevEnumerator = CoCreateInstance(CLSID_MMDeviceEnumerator,pycaw.IMMDeviceEnumerator,CLSCTX_INPROC_SERVER)
        for device in pycaw.AudioUtilities.GetAllDevices():
            if device.FriendlyName in a_shared.AllDevS:
                devName = device.FriendlyName
                if not (a_shared.AllDevS[devName]['IP'] or devName in VolCtrlItf):
                    Device = DevEnumerator.GetDevice(device.id)
                    try:
                        interface = Device.Activate(pycaw.IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
                        VolCtrlItf[devName]=interface.QueryInterface(pycaw.IAudioEndpointVolume)
                        #print(f'[INFO] Add {devName}')
                    except Exception as e:
                        #print(f'[ERROR] initi {device.FriendlyName}: {e}')
                        pass
        # 為每個裝置綁定回調
        callbacks = {}
        for devName in VolCtrlItf:
            callbacks[devName] = AudioEndpointVolumeCallback(devName)
            VolCtrlItf[devName].RegisterControlChangeNotify(callbacks[devName])
        initVol()
        # 開始偵測音量變化
        tmpAllDevS = copy.deepcopy(a_shared.AllDevS)
        a_shared.VolChanger = ''
        Stop = False
        while not Stop:
            if a_shared.AllDevS != tmpAllDevS:
                syncVol()
            tmpAllDevS = copy.deepcopy(a_shared.AllDevS)
            time.sleep(0.05)



        