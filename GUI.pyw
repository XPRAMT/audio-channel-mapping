from PyQt6 import QtWidgets,QtCore,QtGui
import qfluentwidgets
from functools import partial
import pyaudiowpatch as pyaudio
import time,json,queue,threading,sys,os,ctypes
import re
import a_shared
import a_mapping
import a_volume
import a_server
import copy
import winreg
import requests
import keyboard
ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('xpramt.audio.channel.mapping')
##########參數##########
curVersion = "3.2"
appName = "AudioMapping"
coName = ''
CheckBoxs = {}
VolSlider = {}
list_Row = []
##########FUN##########
def ScanClicked(tmpMapRunning=False):
    "掃描 (是否運作)"
    global timerIsReset,loaded_config
    button_scan.setEnabled(False)
    if not tmpMapRunning:
        tmpMapRunning = a_mapping.isRunning
    # 讀取配置
    loaded_config = config_file()
    # 重置狀態
    a_mapping.Start = False
    a_volume.Stop = True
    a_volume.initiDev = True
    # 等待重置
    def isReset():
        if not (a_mapping.isRunning or a_volume.initiDev):
            timerIsReset.stop()
            
            list_audio_devices()
            ShortMesg.put(app.translate("", "Scan successful"))
            LayoutClicked()
            Auto_Apply()
            if tmpMapRunning and len(list_Row)>1:
                a_mapping.outputDevs = copy.deepcopy(outputDevs)
                a_mapping.inputDev = inputDev
                a_mapping.Start = True
            button_scan.setEnabled(True)

    timerIsReset = QtCore.QTimer()
    timerIsReset.timeout.connect(isReset)
    timerIsReset.start(100)

def switch_inputDev():
    """切換輸入類型🎧/🎙️"""
    a_shared.isloopback = not a_shared.isloopback
    if a_shared.isloopback:
        button_switch.setText('🎧➞🎙️')
    else:
        button_switch.setText('🎙️➞🎧')
    ScanClicked()

def list_audio_devices():
    """列出音訊裝置"""
    global inputDev,inputDevID,CheckBoxs,VolSlider,SpinBoxs,outputDevs
    a_shared.AllDevS = {}
    # 輸入裝置
    p = pyaudio.PyAudio()
    if a_shared.isloopback: #設定輸入裝置
        print(f'[INFO] 輸入為Loopback裝置')
        inputDev = p.get_default_wasapi_loopback()
        inputDevID = inputDev['name'] = inputDev['name'].replace(" [Loopback]","")
    else:
        print(f'[INFO] 輸入為麥克風裝置')
        inputDev = p.get_default_wasapi_device()
        inputDevID = inputDev['name'] + '🎙️'
    # 更新參數
    inputDev.update({
        'switch': True,'IP': None,'chList':a_volume.DevS[inputDevID]['chList'],
        'volume':a_volume.DevS[inputDevID]['volume'],'maxVol':100
    })
    a_shared.AllDevS[inputDevID]=inputDev
    # 本機輸出裝置
    outputDevs = {}
    for device in p.get_device_info_generator_by_host_api(host_api_index=2):
        if (device['maxOutputChannels'] > 0) and (device['name'] != inputDevID):
            DevName = device['name']
            device.update({
                'switch': False,'IP': None,'chList':a_volume.DevS[DevName]['chList'],
                'volume': a_volume.DevS[DevName]['volume'],'maxVol':100
            })
            outputDevs[device['name']] = device
    p.terminate()
    # 網路輸出裝置
    for client_IP in a_shared.clients:
        dev = a_shared.clients.get(client_IP)
        MAC = dev['MAC']
        netdevice = {
            'maxOutputChannels': 2,'switch': False ,'name':dev['name'],
            'IP':client_IP,'MAC':MAC,'defaultSampleRate':inputDev['defaultSampleRate'],
            'volume':dev['volume'],'maxVol':dev['maxVol'],'chList':['FL','FR']
        }
        outputDevs[MAC] = netdevice
    # 依照名稱排序輸出裝置
    outputDevs = {k: outputDevs[k] for k in sorted(outputDevs)}
    # 完成AllDevS
    a_shared.AllDevS.update(outputDevs)
    for devName in a_shared.AllDevS:
        for key in list(a_shared.AllDevS[devName].keys()):
            if 'Latency' in key:
                a_shared.AllDevS[devName].pop(key)
    # 建立裝置UI
    clear_layout(Grid)
    clear_layout(cbox)
    CheckBoxs = {}
    VolSlider = {}
    SpinBoxs = {}
    clear_layout(cbox)
    for i,devName in enumerate(a_shared.AllDevS):
        name = a_shared.AllDevS[devName]['name']
        match = re.search(r'\((.*)\)',name )
        if loaded_config.get('shortName',False) and match:
            name = match.group(1)  # 提取最外層括號內的內容
        if devName == inputDevID: # 輸入裝置UI
            a_shared.AllDevS[devName]['name'] = f'{name} | {inputDev["defaultSampleRate"]/1000}KHz'
            # 開關
            CheckBoxs[devName] = QtWidgets.QCheckBox()
            CheckBoxs[devName].setStyleSheet('color:rgb(0,230,0)')
            CheckBoxs[devName].setText(a_shared.AllDevS[devName]['name'])
            CheckBoxs[devName].setChecked(True)
            CheckBoxs[devName].clicked.connect(partial(GetCheckBoxs,devName))
            cbox.addWidget(CheckBoxs[devName])
        else: # 輸出裝置UI
            a_shared.AllDevS[devName]['name'] = f'{i}. {name} | {a_shared.AllDevS[devName]["defaultSampleRate"]/1000}KHz'
            # 開關
            CheckBoxs[devName] = QtWidgets.QCheckBox()
            CheckBoxs[devName].setText(a_shared.AllDevS[devName]['name'])
            CheckBoxs[devName].clicked.connect(partial(GetCheckBoxs,devName))
            # 延遲
            SpinBoxs[devName] = QtWidgets.QSpinBox()
            SpinBoxs[devName].setFixedWidth(55)
            SpinBoxs[devName].setRange(0,1000)
            SpinBoxs[devName].setSingleStep(10)
            SpinBoxs[devName].setValue(0)
            SpinBoxs[devName].valueChanged.connect(partial(GetSpinBox,devName))
            # 建立水平佈局管理器
            hbox3 = QtWidgets.QHBoxLayout()
            hbox3.setContentsMargins(0, 0, 0, 0)
            hbox3.addWidget(CheckBoxs[devName])
            hbox3.addWidget(SpinBoxs[devName])
            cbox.addLayout(hbox3)
        # 建立音量條
        vol = a_shared.AllDevS[devName]['volume']
        maxVol = a_shared.AllDevS[devName]['maxVol']
        VolSlider[devName] = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        VolSlider[devName].setRange(0,maxVol)
        VolSlider[devName].setValue(round(vol*maxVol))
        VolSlider[devName].valueChanged.connect(partial(GetVolSlider,devName))
        cbox.addWidget(VolSlider[devName])
    # 自動勾選裝置
    if 'devList' in a_shared.Config:
        for devName in a_shared.Config['devList']:
            if devName in CheckBoxs:
                CheckBoxs[devName].setChecked(True)
                a_shared.AllDevS[devName]['switch'] = True
    GetCheckBoxs(None) # 更新devList

def LayoutClicked():
    """布局"""
    global table,list_Row,ChSlider
    list_Row = ['i\o']
    # outputSets,list_Row
    table = [] # [device,channel]
    for i,devName in enumerate(outputDevs):
        chNum = outputDevs[devName]['maxOutputChannels']
        # 建立 a_shared.Config
        a_shared.Config.setdefault(devName,{'delay':0})
        a_shared.Config[devName].setdefault('channels',[0 for _ in range(chNum)])
        if outputDevs[devName]['switch'] == True:
            for c in range(chNum): #c=channel num
                list_Row.append(f'dev{i+1}: {a_shared.AllDevS[devName]["chList"][c]}')
                table.append([devName,c])
    # 建立聲道滑條
    clear_layout(Grid)
    ChSlider = {}
    for inch in range(inputDev['maxInputChannels']+1):
        for outch in range(len(list_Row)):
            if inch == 0 : #output label
                outLabel = QtWidgets.QLabel(list_Row[outch])
                outLabel.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
                Grid.addWidget(outLabel, inch, outch)
            elif outch == 0 and inch > 0: #input label
                
                inLabel = QtWidgets.QLabel(inputDev['chList'][inch-1])
                Grid.addWidget(inLabel, inch, outch)
            else:
                devName,c = table[outch-1]
                slider = QtWidgets.QSlider()
                slider.setOrientation(QtCore.Qt.Orientation.Horizontal)
                slider.setRange(0,100)
                slider.setValue(0)
                slider.valueChanged.connect(partial(GetChSlider, devName, inch-1, c))
                Grid.addWidget(slider, inch, outch)
                # 初始化ChSlider[devName]
                ChSlider.setdefault(devName,[])
                # 確保輸入聲道 inch 有對應的列表
                while len(ChSlider[devName]) <= c:
                    ChSlider[devName].append([])  
                ChSlider[devName][c].append(slider)

def Auto_Apply():
    '自動套用'
    def Apply(devName,devSetting):
        SpinBoxs[devName].setValue(devSetting['delay'])
        for idx,outchs in enumerate(ChSlider[devName]):
            chVal = devSetting['channels'][idx] if idx < len(devSetting['channels']) else 0
            if int(chVal) < len(outchs):
                outchs[int(chVal)].setValue(int((chVal % 1)*1000))

    # 更新配置
    if coName in loaded_config:
        print(f'[INFO] Apply loaded config: {coName} {loaded_config[coName]}')
        for devName in loaded_config[coName]:
            if devName!=inputDevID:
                Apply(devName,loaded_config[coName][devName])
    elif 'devList' in a_shared.Config:
        for devName in a_shared.Config['devList']:
            if devName!=inputDevID:
                print(f'[INFO] Apply curent config: {devName} {a_shared.Config[devName]}')
                Apply(devName,a_shared.Config[devName])

def SetVolSlider(devName,vol):
    '設定音量滑條'
    maxVol = a_shared.AllDevS[devName]['maxVol']
    VolSlider[devName].blockSignals(True)
    VolSlider[devName].setValue(round(vol*maxVol))
    VolSlider[devName].blockSignals(False)

def GetVolSlider(devName):
    '音量滑條變動'
    maxVol = a_shared.AllDevS[devName]['maxVol']
    vol = VolSlider[devName].value()/maxVol
    a_volume.setDevVol(devName,vol)
    a_shared.VolChanger = devName

def GetCheckBoxs(_): #devName   
    'CheckBox變動'
    global coName
    coName=''
    devList= []
    for devName in CheckBoxs:
        switch = CheckBoxs[devName].isChecked()
        a_shared.AllDevS[devName]['switch'] = switch
        if switch and devName!=inputDevID:
            coName+=devName
            devList.append(devName)
    a_shared.Config['devList']=devList
    #print(f'[INFO] 裝置變化\n{a_shared.Config}')

def GetSpinBox(devName):
    '延遲SpinBox變動'
    a_shared.Config[devName]['delay'] = SpinBoxs[devName].value()
    #print(f'{a_shared.Config}')

def GetChSlider(devName, inch, c):
    '聲道滑條變動'
    for ch,inSlider in enumerate(ChSlider[devName][c]):
        if ch == inch:
            a_shared.Config[devName]['channels'][c]=(ch + inSlider.value()/1000)
        else: # 將其它滑條設為0
            inSlider.blockSignals(True)
            inSlider.setValue(0)
            inSlider.blockSignals(False)
    #print(f'{a_shared.Config}')

def MappingClicked():
    '開始/停止按鈕'
    if a_mapping.isRunning: # 如果正在運作就停止
        a_mapping.Start = False
        return
    ScanClicked(True)
    
def config_file(save_config=None):
    """
    用於讀寫位於"%APPDATA%\AudioMapping\config.json"的設定檔。
    若 save_config 為 None 代表要讀取設定；
    否則寫入save_config 到檔案中。
    """
    def Save(data):
        with open(filePath, 'w') as json_file:
            json.dump(data, json_file, indent=4)
    # # # # # # # # # # # # # # # # # # #
    appdataDir = os.environ.get("APPDATA")
    folderPath = os.path.join(appdataDir, appName)
    filePath = os.path.join(folderPath, "config.json")
    os.makedirs(folderPath, exist_ok=True)
    with open(filePath, 'a') as json_file:
        pass
    if save_config is None:
        try:
            with open(filePath, 'r') as json_file:
                save_config = json.load(json_file)
        except json.decoder.JSONDecodeError:
            save_config = {}
            ShortMesg.put(app.translate("", "Config created"))
            Save(save_config)
        return save_config
    else:
        Save(save_config)

def SaveClicked():
    """儲存按鈕"""
    loaded_config = config_file()
    loaded_config.setdefault(coName,{})
    coDict = {}
    for devName in a_shared.Config['devList']:
        coDict[devName] = a_shared.Config[devName]
    loaded_config[coName] = coDict
    config_file(loaded_config)
    ShortMesg.put(app.translate("", "Saved"))

def DelClicked():
    """刪除按鈕"""
    loaded_config = config_file()
    if coName in loaded_config:
        loaded_config.pop(coName,None)
        config_file(loaded_config)
    for devName in a_shared.Config['devList']:
        a_shared.Config[devName]['delay'] = 0
        a_shared.Config[devName]['channels'] = [0 for _ in a_shared.Config[devName]['channels']]
    ShortMesg.put(app.translate("", "Deleted"))

def clear_layout(layout):
    """清除layout"""
    #徹底清空一個佈局，移除並刪除所有項目，包括嵌套佈局和空間項。
    while layout.count():
        item = layout.takeAt(0)  # 從佈局中移除項目
        widget = item.widget()  # 檢查是否是 Widget
        child_layout = item.layout()  # 檢查是否是子佈局
        # 如果是 Widget，刪除
        if widget is not None:
            widget.deleteLater()
        # 如果是子佈局，遞歸清空
        elif child_layout is not None:  
            clear_layout(child_layout)
        # 如果是空間項，直接刪除
        else:
            del item

# 處理回傳訊息(接收)
class HandleReturnMessages(QtCore.QThread):
    Rescan = QtCore.pyqtSignal()
    StartStop = QtCore.pyqtSignal()
    def run(self):
        while True:
            state,parameter, = a_shared.to_GUI.get()  # 等待狀態更新
            match state:
                case 0:  # 持續狀態
                    status_label.setText(parameter)
                case 1:  # 開始按鈕
                    if parameter:
                        button_mapping.setText('⏹️')#Text['Stop'])
                    else:
                        button_mapping.setText('▶️')#Text['Start'])
                case 2:  # 短暫通知
                    ShortMesg.put(parameter)
                case 3:  # 重新掃描
                    self.Rescan.emit()
                case 4:  # 同步音量條
                    SetVolSlider(*parameter)
                case 5:  # 顯示延遲
                    devName,txt = parameter
                    if CheckBoxs[devName]:
                        CheckBoxs[devName].setText(f'{a_shared.AllDevS[devName]["name"]} | {txt}')
                case 6: # 媒體鍵
                    media_key(parameter)
                case 7: # 播放/暫停
                    a_shared.Config['devList'].append(parameter)
                    self.StartStop.emit()

def start_HandleReturnMessages():
    global worker
    worker = HandleReturnMessages()
    worker.Rescan.connect(ScanClicked)
    worker.StartStop.connect(MappingClicked)
    worker.start()
# 顯示短消息
ShortMesg = queue.Queue()
def printShortMesg():
    while True:
        txt = ShortMesg.get()
        print('[ONUI]',txt)
        mesg_label.setText(txt)
        timer = 2/(ShortMesg.qsize()+2)
        time.sleep(timer)
        mesg_label.setText('')

def check_for_updates(failMesg = True):
    """檢查更新"""
    update_url = "https://api.github.com/repos/XPRAMT/audio-channel-mapping/releases/latest"
    loaded_config = config_file()
    ignore_version = loaded_config.get('ignore_version', '0.0')
    try:
        response = requests.get(update_url)
        if response.status_code == 200:
            latest_release = response.json()
            latest_version = latest_release["name"]
            if latest_version > curVersion and latest_version != ignore_version:
                reply = QtWidgets.QMessageBox.question(
                    None, 
                    "Update Available",
                    f"A new version {latest_version} is available.\nDo you want to download or ignore this version?",
                    QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.Ignore | QtWidgets.QMessageBox.StandardButton.Cancel
                )
                if reply == QtWidgets.QMessageBox.StandardButton.Yes:
                    QtGui.QDesktopServices.openUrl(QtCore.QUrl(latest_release["html_url"]))
                elif reply == QtWidgets.QMessageBox.StandardButton.Ignore:
                    loaded_config['ignore_version'] = latest_version
                    config_file(loaded_config)
            elif failMesg:
                QtWidgets.QMessageBox.information(
                    None, 
                    "No Updates", 
                    "You are using the latest version."
                )
        elif failMesg:
            QtWidgets.QMessageBox.warning(
                None, 
                "Update Check Failed", 
                f"Failed to check for updates (HTTP {response.status_code})."
            )
    except Exception as e:
        if failMesg:
            QtWidgets.QMessageBox.critical(
                None, 
                "Error", 
                f"An error occurred while checking for updates:\n{e}"
            )
# 媒體按鍵
def media_key(key_value):
    keyboard.send(key_value)

def get_theme():
    "預設值為 1 (淺色模式)，若返回 0 則表示深色模式"
    if sys.platform == 'win32':
        # 在 Windows 上讀取登錄檔
        settings = QtCore.QSettings(r"HKEY_CURRENT_USER\Software\Microsoft\Windows\CurrentVersion\Themes\Personalize", QtCore.QSettings.Format.NativeFormat)
        # 預設值為 1 (淺色模式)，若返回 0 則表示深色模式
        value = settings.value("AppsUseLightTheme", 1, type=int)
        return value
##########初始化##########
app = QtWidgets.QApplication(sys.argv)
app.setStyle('Fusion')
# 設定字體
default_font = QtGui.QFont('Microsoft JhengHei',12)
app.setFont(default_font)
# 建立主頁面與設定頁面堆疊
class main_window(QtWidgets.QStackedWidget):
    def __init__(self):
        super().__init__()
        self.init_ui()

    def init_ui(self):
        '初始化'
        self.apply_palette()

    def changeEvent(self, event: QtCore.QEvent):
        '偵測系統主題更改事件'
        if event.type() == QtCore.QEvent.Type.PaletteChange:
            print("[INFO] 系統主題已更改")
            self.apply_palette()
        super().changeEvent(event)

    def apply_palette(self):
        '套用調色盤'
        dark_palette = QtGui.QPalette()
        dark_palette.setColor(QtGui.QPalette.ColorRole.Window, QtGui.QColor(0, 0, 0))
        dark_palette.setColor(QtGui.QPalette.ColorRole.Button, QtGui.QColor(20, 20, 20))
        light_palette = QtGui.QPalette()

        if get_theme():
            QtWidgets.QApplication.instance().setPalette(light_palette)
        else:
            QtWidgets.QApplication.instance().setPalette(dark_palette)
MainWindow = main_window()
main_page = QtWidgets.QWidget()
settings_page = QtWidgets.QWidget()
# loaded config
loaded_config = config_file()
# 翻譯
def translate():
    global Text, translator
    # 獲取系統語言
    def get_display_language():
        try:
            # 註冊表鍵
            sub_key = r"Control Panel\International\User Profile"
            value_name = "Languages"
            # 打開註冊表鍵
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, sub_key) as registry_key:
                # 讀取多重字符串（MULTI_SZ）類型的值
                value, _ = winreg.QueryValueEx(registry_key, value_name)
            # 返回多重字符串中的第一個語言
            if value:
                return value[0]  # 返回第一個語言
        except WindowsError:
            return "Error" 
    
    # 檢測系統語言
    system_locale = get_display_language()
    print(f"[INFO] locale: {system_locale}")
    # 創建翻譯器
    translator = QtCore.QTranslator()
    if translator.load(f"language/{system_locale}.qm"):
        app.installTranslator(translator)
    # 建立翻譯字典
    Text={}
    Text["Start"] = app.translate('', "Start")
    Text["Stop"] = app.translate('', "Stop")
translate()
# MainUI
def BuildMainPage():
    global button_mapping,button_scan,button_switch,media_keys
    global status_label,mesg_label,Grid,vbox,cbox

    # 建立一個垂直佈局管理器
    vbox = QtWidgets.QVBoxLayout()
    vbox.setContentsMargins(5, 5, 5, 5)
    vbox.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop)
    # 建立一個CheckBox佈局管理器
    cbox = QtWidgets.QVBoxLayout()
    cbox.setContentsMargins(0, 0, 0, 0)
    vbox.addLayout(cbox)
     # 建立一個網格佈局管理器
    Grid_btn = QtWidgets.QGridLayout()
    Grid_btn.setContentsMargins(0, 0, 0, 0)
    #Grid_btn.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
    vbox.addLayout(Grid_btn)
    # 建立儲存按鈕
    button_Save = QtWidgets.QPushButton('💾')#app.translate('', "Save"))
    button_Save.clicked.connect(SaveClicked)
    Grid_btn.addWidget(button_Save,0,0)
    # 建立刪除按鈕
    button_del = QtWidgets.QPushButton('🗑️')#app.translate('', "Delete"))
    button_del.clicked.connect(DelClicked)
    Grid_btn.addWidget(button_del,0,1)
    # 建立輸入裝置切換按鈕
    button_switch = QtWidgets.QPushButton('🎧➞🎙️')#app.translate('', "Switch"))
    button_switch.clicked.connect(switch_inputDev)
    Grid_btn.addWidget(button_switch,0,2)
    # 建立設定按鈕
    button_setting = QtWidgets.QPushButton('⚙️')#app.translate('', "Setting"))
    button_setting.clicked.connect(lambda: MainWindow.setCurrentWidget(settings_page))
    Grid_btn.addWidget(button_setting,1,0)
    # 建立Refresh按鈕
    button_scan = QtWidgets.QPushButton('🔄')#app.translate('', "Refresh"))
    button_scan.clicked.connect(ScanClicked)
    Grid_btn.addWidget(button_scan,1,1)
    # 建立映射按鈕
    button_mapping = QtWidgets.QPushButton('▶️')#app.translate('', "Start"))
    button_mapping.clicked.connect(MappingClicked)
    Grid_btn.addWidget(button_mapping,1,2)
    # 建立媒體控制按鈕
    button_Previous = QtWidgets.QPushButton("⏮")
    button_Previous.clicked.connect(lambda: media_key("previous track"))
    Grid_btn.addWidget(button_Previous,2,0)

    button_PlayPause = QtWidgets.QPushButton("⏸️")
    button_PlayPause.clicked.connect(lambda: media_key("play/pause"))
    Grid_btn.addWidget(button_PlayPause,2,1)

    button_Next = QtWidgets.QPushButton("⏭")
    button_Next.clicked.connect(lambda: media_key("next track"))
    Grid_btn.addWidget(button_Next,2,2)
    media_keys=[button_Previous,button_PlayPause,button_Next]
    for btn in media_keys:
        btn.setVisible(loaded_config.get('mediaKey',False))
    # 建立一個網格佈局管理器
    Grid = QtWidgets.QGridLayout()
    Grid.setContentsMargins(0, 0, 0, 0)
    Grid.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
    vbox.addLayout(Grid)
    # 建立水平佈局管理器3
    hbox3 = QtWidgets.QHBoxLayout()
    hbox3.setContentsMargins(0, 0, 0, 0)
    vbox.addLayout(hbox3)
    # 建立狀態顯示區
    status_label = QtWidgets.QLabel()
    hbox3.addWidget(status_label)
    mesg_label = QtWidgets.QLabel()
    mesg_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight)
    hbox3.addWidget(mesg_label)

    main_page.setLayout(vbox)
BuildMainPage()
# SettingUI
def get_registry_value():
        """讀取登錄檔中開機自啟動的值，若不存在則回傳 None"""
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                r"Software\Microsoft\Windows\CurrentVersion\Run",
                                0, winreg.KEY_READ)
            winreg.QueryValueEx(key, appName)
            winreg.CloseKey(key)
            return True
        except Exception as e:
            return False
def BuildSettingsPage():
    global MediaKeyBox
    # 初始化
    settings_layout = QtWidgets.QVBoxLayout()
    settings_layout.setContentsMargins(5, 5, 5, 5)
    settings_layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop)
    # 開發者
    settings_label = QtWidgets.QLabel("Developed by XPRAMT")
    settings_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
    settings_layout.addWidget(settings_label)
    # 首頁連結
    github_button = QtWidgets.QPushButton("Homepage")
    github_button.setStyleSheet("color: lightblue; background: transparent; border: none;")
    github_button.clicked.connect(lambda: QtGui.QDesktopServices.openUrl(QtCore.QUrl("https://github.com/XPRAMT/audio-channel-mapping")))
    settings_layout.addWidget(github_button)
    # 短名稱
    shortNameBox = QtWidgets.QCheckBox()
    shortNameBox.setText(app.translate('', "Use short name"))
    if loaded_config.get('shortName',False):
        shortNameBox.setChecked(True)
    def toggleShortName():
        loaded_config['shortName'] = shortNameBox.isChecked()
        config_file(loaded_config)
        ScanClicked()
    shortNameBox.clicked.connect(toggleShortName)
    settings_layout.addWidget(shortNameBox)
    # media key
    MediaKeyBox = QtWidgets.QCheckBox()
    MediaKeyBox.setText(app.translate('', "Use media key"))
    if loaded_config.get('mediaKey',False):
        MediaKeyBox.setChecked(True)
    def toggleMediaKey():
        btn_switch = MediaKeyBox.isChecked()
        loaded_config['mediaKey'] = btn_switch
        config_file(loaded_config)
        for btn in media_keys:
            btn.setVisible(btn_switch)
    MediaKeyBox.clicked.connect(toggleMediaKey)
    settings_layout.addWidget(MediaKeyBox)
    # 開機自啟動
    StartLoginBox = QtWidgets.QCheckBox()
    StartLoginBox.setText(app.translate('', "Start at Login"))
    # 取得目前程式的完整路徑
    app_path = os.path.realpath(sys.argv[0])
    StartLoginBox.setChecked(get_registry_value())
    def toggleStartAtLogin():
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                 r"Software\Microsoft\Windows\CurrentVersion\Run",
                                 0, winreg.KEY_ALL_ACCESS)
            if StartLoginBox.isChecked():# 將程式加入開機自啟動
                winreg.SetValueEx(key, appName, 0, winreg.REG_SZ, app_path)
                print('設定開機自啟動')
            else:
                try:# 從開機自啟動中移除程式
                    winreg.DeleteValue(key, appName)
                    print('刪除開機自啟動')
                except Exception as e:
                    print("登錄中無此項目")
            winreg.CloseKey(key)
        except Exception as e:
            print("設定開機自啟動失敗：", e)
    StartLoginBox.clicked.connect(toggleStartAtLogin)
    settings_layout.addWidget(StartLoginBox)
    # 啟動時最小化
    MinimizeAtStartBox = QtWidgets.QCheckBox()
    MinimizeAtStartBox.setText(app.translate('', "Minimize at start"))
    if loaded_config.get('minimizeAtStart',False):
        MinimizeAtStartBox.setChecked(True)
    def toggleminimizeAtStart():
        loaded_config['minimizeAtStart'] = MinimizeAtStartBox.isChecked()
        config_file(loaded_config)
    MinimizeAtStartBox.clicked.connect(toggleminimizeAtStart)
    settings_layout.addWidget(MinimizeAtStartBox)
    # Minimize to system tray on close
    KeepTrayBox = QtWidgets.QCheckBox()
    KeepTrayBox.setText(app.translate('', "Minimize to system tray on close"))
    if loaded_config.get('keepTray',False):
        KeepTrayBox.setChecked(True)
    def toggleKeepTray():
        loaded_config['keepTray'] = KeepTrayBox.isChecked()
        config_file(loaded_config)
    KeepTrayBox.clicked.connect(toggleKeepTray)
    settings_layout.addWidget(KeepTrayBox)
    # 檢查更新
    update_button = QtWidgets.QPushButton(app.translate('', "Check for Updates"))
    update_button.clicked.connect(lambda: check_for_updates())
    settings_layout.addWidget(update_button)
    # 返回
    back_button = QtWidgets.QPushButton(app.translate('', "Back"))
    back_button.clicked.connect(lambda: MainWindow.setCurrentWidget(main_page))
    settings_layout.addWidget(back_button)

    settings_page.setLayout(settings_layout)
BuildSettingsPage()

# 啟動線程
threading.Thread(target=a_volume.volSyncMain,daemon = True).start()  #音量同步
threading.Thread(target=a_server.start_server,daemon = True).start() #server
threading.Thread(target=a_mapping.StartStream,daemon = True).start() #Mapping
threading.Thread(target=printShortMesg,daemon = True).start()        #ShortMesg
start_HandleReturnMessages() #處理回傳訊息
# 掃描置裝
ScanClicked()
#設定系統匣
def showMainWindow():
    """顯示主視窗並恢復應用程式"""
    MainWindow.showNormal()  # 還原視窗
    MainWindow.activateWindow()  # 讓視窗獲得焦點
exit_action = QtGui.QAction("Exit", MainWindow) # 退出鍵
exit_action.triggered.connect(lambda: sys.exit()) 
tray_menu = QtWidgets.QMenu() #menu
tray_menu.addAction(exit_action) 
tray_icon = QtWidgets.QSystemTrayIcon(QtGui.QIcon('C:/APP/@develop/audio-channel-mapping/icon.ico'))
tray_icon.setContextMenu(tray_menu)
tray_icon.activated.connect(lambda reason: showMainWindow() if reason == QtWidgets.QSystemTrayIcon.ActivationReason.Trigger else None)
tray_icon.show()
# 連結關閉事件
def close_Event(event):
    """攔截關閉事件，最小化到托盤"""
    if loaded_config.get('keepTray',False):
        event.ignore()
        MainWindow.hide()
MainWindow.closeEvent = close_Event
# 設置堆疊佈局
MainWindow.addWidget(main_page)
MainWindow.addWidget(settings_page)
MainWindow.setCurrentWidget(main_page)
MainWindow.setWindowTitle(app.translate('', "Audio Mapping") + ' v' + curVersion)
MainWindow.setWindowIcon(QtGui.QIcon('C:/APP/@develop/audio-channel-mapping/icon.ico'))
def center(self):
    """視窗置中"""
    # 取得螢幕的幾何訊息
    screenGeometry = QtWidgets.QApplication.primaryScreen().geometry()
    # 計算視窗左上角的座標，使其位於螢幕中心
    x = (screenGeometry.width() - self.width()) // 2
    y = (screenGeometry.height() - self.height()) // 2
    # 設定視窗的位置
    self.setGeometry(x, y, self.width(), self.height())
# 啟動時是否顯示窗口
if not loaded_config.get('minimizeAtStart',False):
    MainWindow.show()
    center(MainWindow)

# 檢查更新
#check_for_updates(False)
sys.exit(app.exec())
