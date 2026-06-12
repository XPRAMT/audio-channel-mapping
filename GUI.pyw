import time,json,queue,threading,sys,os,re,ctypes,copy,requests,winreg
import packaging.version
from PyQt6 import QtWidgets,QtCore,QtGui
from qasync import QEventLoop
#import qfluentwidgets
#import qdarktheme
from functools import partial
import pyaudiowpatch as pyaudio
import a_shared
import a_mapping
import a_volume
import a_server
#import a_openrgb
import a_smtc

ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('xpramt.audio.channel.mapping')
##########FUN##########
def asset_path(relative_path):
    "回傳資產路徑，支援開發/PyInstaller 打包模式"
    if getattr(sys, 'frozen', False):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), relative_path)

##########參數##########
curVersion = "26.05.14"
appName = "AudioMapping"
coName = ''
QUICK_MAPPING_CONFIG_KEY = 'quickMappingSlots'
QUICK_MAPPING_INDEX_KEY = 'quickMappingSlotIndex'
quickMappingSlotIndex = 0
CheckBoxs = {}
VolSlider = {}
list_Row = []
ShortMesg = queue.Queue()
##########FUN##########
def ScanClicked(tmpMapRunning=False):
    "掃描 (是否運作)"
    global timerIsReset,loaded_config
    button_scan.setEnabled(False)
    if not tmpMapRunning:
        tmpMapRunning = Mapping.isRunning
    # 讀取配置
    loaded_config = config_file()
    # 重置狀態
    Mapping.Start = False
    a_volume.Stop = True
    a_volume.initiDev = True
    # 等待重置
    def isReset():
        if not (Mapping.isRunning or a_volume.initiDev):
            '如果已停止'
            timerIsReset.stop()
            
            list_audio_devices()
            ShortMesg.put(app.translate("", "Scan successful"))
            LayoutClicked()
            Auto_Apply()
            if tmpMapRunning and len(list_Row)>0: # 以裝置數量判斷是否啟動
                Mapping.outputDevs = copy.deepcopy(outputDevs)
                Mapping.inputDev = inputDev
                threading.Thread(target=Mapping.run,daemon = True).start() 
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
                slider.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding,
                                      QtWidgets.QSizePolicy.Policy.Expanding)
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
        SetChannelSliders(devName, devSetting.get('channels', []))

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

def current_mapping_snapshot():
    '取得目前聲道映射快照'
    snapshot = {'devList': list(a_shared.Config.get('devList', [])), 'maps': {}}
    for devName in snapshot['devList']:
        devSetting = a_shared.Config.get(devName, {})
        snapshot['maps'][devName] = {
            'delay': devSetting.get('delay', 0),
            'channels': list(devSetting.get('channels', []))
        }
    return snapshot

def SetChannelSliders(devName, channels):
    '設定聲道映射滑條'
    if devName not in ChSlider:
        return
    a_shared.Config[devName]['channels'] = [0 for _ in ChSlider[devName]]
    for c,outchs in enumerate(ChSlider[devName]):
        chVal = channels[c] if c < len(channels) else 0
        try:
            chVal = float(chVal)
        except (TypeError, ValueError):
            chVal = 0
        inch = int(chVal)
        sliderValue = max(0, min(100, int(round((chVal % 1) * 1000))))
        for inSlider in outchs:
            inSlider.blockSignals(True)
            inSlider.setValue(0)
            inSlider.blockSignals(False)
        if inch < len(outchs):
            outchs[inch].blockSignals(True)
            outchs[inch].setValue(sliderValue)
            outchs[inch].blockSignals(False)
            a_shared.Config[devName]['channels'][c] = inch + sliderValue/1000

def ApplyMappingSnapshot(snapshot):
    '套用聲道映射快照'
    maps = snapshot.get('maps', {})
    for devName,devSetting in maps.items():
        if devName not in a_shared.Config:
            continue
        delay = devSetting.get('delay', 0)
        if devName in SpinBoxs:
            SpinBoxs[devName].setValue(delay)
        else:
            a_shared.Config[devName]['delay'] = delay
        SetChannelSliders(devName, devSetting.get('channels', []))

def SaveQuickMappingClicked():
    '保存快速聲道映射'
    global loaded_config,quickMappingSlotIndex
    snapshot = current_mapping_snapshot()
    if len(snapshot['maps']) == 0:
        ShortMesg.put(app.translate('', 'No mapping to save'))
        return
    loaded_config = config_file()
    slots = loaded_config.setdefault(QUICK_MAPPING_CONFIG_KEY, [])
    if len(slots) < 2:
        slots.append(snapshot)
        quickMappingSlotIndex = len(slots) - 1
    else:
        quickMappingSlotIndex = int(loaded_config.get(QUICK_MAPPING_INDEX_KEY, quickMappingSlotIndex)) % 2
        slots[quickMappingSlotIndex] = snapshot
    loaded_config[QUICK_MAPPING_INDEX_KEY] = quickMappingSlotIndex
    config_file(loaded_config)
    ShortMesg.put(f'{app.translate("", "Saved")} {quickMappingSlotIndex + 1}/2')

def SwitchQuickMappingClicked():
    '切換快速聲道映射'
    global loaded_config,quickMappingSlotIndex
    loaded_config = config_file()
    slots = loaded_config.get(QUICK_MAPPING_CONFIG_KEY, [])[:2]
    if len(slots) < 2:
        ShortMesg.put(app.translate('', 'Save two mappings first'))
        return
    quickMappingSlotIndex = (int(loaded_config.get(QUICK_MAPPING_INDEX_KEY, quickMappingSlotIndex)) + 1) % 2
    ApplyMappingSnapshot(slots[quickMappingSlotIndex])
    loaded_config[QUICK_MAPPING_INDEX_KEY] = quickMappingSlotIndex
    config_file(loaded_config)
    ShortMesg.put(f'{app.translate("", "Switch")} {quickMappingSlotIndex + 1}/2')

def MappingClicked():
    '開始/停止按鈕'
    if Mapping.isRunning: # 如果正在運作就停止
        Mapping.Start = False
        return
    ScanClicked(True)
    
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

def printShortMesg():
    '顯示短消息'
    while True:
        txt = ShortMesg.get()
        print('[ONUI]',txt)
        mesg_label.setText(txt)
        timer = 2/(ShortMesg.qsize()+2)
        time.sleep(timer)
        mesg_label.setText('')

def config_file(save_config=None):
    """
    用於讀寫位於"%APPDATA%\AudioMapping\config.json"的設定檔。\n
    若 save_config 為 None 代表要讀取設定；\n
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
        if 'port' not in save_config:
            save_config['port'] = 25505
            Save(save_config)
        return save_config
    else:
        Save(save_config)
        return save_config
def get_display_language():
    "從 Windows 註冊表讀取系統顯示語言"
    try:
        sub_key = r"Control Panel\International\User Profile"
        value_name = "Languages"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, sub_key) as registry_key:
            value, _ = winreg.QueryValueEx(registry_key, value_name)
        if value:
            return value[0]
    except WindowsError:
        return "en"
    return "en"

# 語言代碼 → 顯示名稱
LANG_NAMES = {
    "zh-Hans-CN": "简体中文", "zh-Hant-TW": "繁體中文",
    "hi": "हिन्दी", "es": "Español", "fr": "Français",
    "ar": "العربية", "bn": "বাংলা", "pt": "Português",
    "ru": "Русский", "ja": "日本語", "ko": "한국어",
    "en": "English",
}

def scan_language_qm():
    "掃描 language/ 目錄下所有 .qm 檔案，回傳 [(代碼, 顯示名稱), ...]"
    lang_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "language")
    if not os.path.isdir(lang_dir):
        return []
    result = []
    for f in sorted(os.listdir(lang_dir)):
        if f.endswith('.qm') and f != 'translations.qm':
            code = f[:-3]  # 去掉 .qm 副檔名
            name = LANG_NAMES.get(code, code)
            result.append((code, name))
    return result

def translate():
    system_locale = get_display_language()
    print(f"[INFO] system locale: {system_locale}")

    # config 手動選擇優先，否則用系統語言
    loaded_config = config_file()
    chosen = loaded_config.get('language', '')
    locale = chosen if chosen else system_locale
    print(f"[INFO] using locale: {locale}")

    Translator = QtCore.QTranslator()
    if locale != 'en' and Translator.load(f"language/{locale}.qm"):
        app.installTranslator(Translator)
    Text={}
    Text["Start"] = app.translate('', "Start")
    Text["Stop"] = app.translate('', "Stop")
    return Translator

def check_for_updates(failMesg = True):
    "檢查更新(是否開啟彈窗)"
    update_url = "https://api.github.com/repos/XPRAMT/audio-channel-mapping/releases/latest"
    loaded_config = config_file()
    ignore_version = loaded_config.get('ignore_version', '0.0')
    try:
        response = requests.get(update_url)
        if response.status_code == 200:
            latest_release = response.json()
            latest_version = latest_release["tag_name"]
            print(f'[UPDATE] current:{curVersion} | github:{latest_version}')
            if packaging.version.parse(latest_version) > packaging.version.parse(curVersion) and latest_version != ignore_version:
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

class HandleReturnMessages(QtCore.QThread):
    '處理回傳訊息'
    ReturnMeg = QtCore.pyqtSignal(object,object)
    def run(self):
        while True:
            # 等待狀態更新
            state,parameter = a_shared.to_GUI.get()
            self.ReturnMeg.emit(state,parameter)

##########初始化##########
app = QtWidgets.QApplication(sys.argv)
colors={"[dark]": {"primary": "#D0BCFF","background":"#000000"}}
#qdarktheme.setup_theme("auto",custom_colors = colors)
app.setStyle('Fusion')
# 設定字體 
app.setFont(QtGui.QFont('Microsoft JhengHei',12))   
# 載入設定
loaded_config = config_file()
a_shared.Config['port'] = loaded_config.get('port', 25505)
# 建立翻譯器
translator = translate()
# 映射
Mapping = a_mapping.Mapping()

# 建立主頁面
class main_window(QtWidgets.QWidget):

    def __init__(self):
        super().__init__()
        self.setWindowTitle(app.translate('', "Audio Mapping") + ' v' + curVersion)
        self.setWindowIcon(QtGui.QIcon(asset_path('icon/icon.ico')))
        self.init_ui()
        self.init_SystemTray()
        # 啟動狀態更新worker
        self.worker = HandleReturnMessages()
        self.worker.ReturnMeg.connect(self.update)
        self.worker.start()
        # 啟動線程
        threading.Thread(target=a_volume.volSyncMain,daemon = True).start()  #音量同步
        threading.Thread(target=a_server.start_server,daemon = True).start() #server
        #threading.Thread(target=a_openrgb.OpenRGB,daemon=True).start()      #OpenRGB
        threading.Thread(target=printShortMesg,daemon = True).start()        #ShortMesg
        # 掃描裝置
        ScanClicked()
        # 啟動時是否顯示窗口
        if not loaded_config.get('minimizeAtStart',False):
            self.show()
            self.center()
        # 檢查更新
        if loaded_config.get('checkUpdataBox',False):
            print('[INFO] 檢查更新')
            check_for_updates(False)

    def init_ui(self):
        '初始化'
        self.MainLayout = QtWidgets.QHBoxLayout(self)
        self.MainLayout.setContentsMargins(5, 5, 5, 5)
        # 堆疊佈局
        self.leftStacked = QtWidgets.QStackedWidget()
        # 建立主要頁面
        self.main_page = QtWidgets.QWidget()
        self.init_MainPage()
        self.leftStacked.addWidget(self.main_page)
        # 建立設定頁面
        self.settings_page = QtWidgets.QWidget()
        self.init_SettingsPage()
        self.leftStacked.addWidget(self.settings_page)
        # # #
        self.leftStacked.setCurrentWidget(self.main_page)
        self.MainLayout.addWidget(self.leftStacked)
        # 建立SMTC控制器
        self.SMTC = a_smtc.MediaControlWidget()
        self.MainLayout.addWidget(self.SMTC)
        self.SMTC.setVisible(loaded_config.get('mediaKey',False))

        self.apply_palette()

    def init_MainPage(self):
        'Main UI'
        global button_mapping,button_scan,button_switch
        global status_label,mesg_label,Grid,vbox,cbox

        # 建立一個垂直佈局管理器
        vbox = QtWidgets.QVBoxLayout(self.main_page)
        vbox.setContentsMargins(0, 0, 0, 0)
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
        button_setting.clicked.connect(lambda: MainWindow.leftStacked.setCurrentWidget(self.settings_page))
        Grid_btn.addWidget(button_setting,1,0)
        # 建立Refresh按鈕
        button_scan = QtWidgets.QPushButton('🔄')#app.translate('', "Refresh"))
        button_scan.clicked.connect(ScanClicked)
        Grid_btn.addWidget(button_scan,1,1)
        # 建立映射按鈕
        button_mapping = QtWidgets.QPushButton('▶️')#app.translate('', "Start"))
        button_mapping.clicked.connect(MappingClicked)
        Grid_btn.addWidget(button_mapping,1,2)
        # 建立一個網格佈局管理器
        Grid = QtWidgets.QGridLayout()
        Grid.setContentsMargins(0, 0, 0, 0)
        Grid.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        vbox.addLayout(Grid)
        # 建立快速聲道映射按鈕
        quick_map_box = QtWidgets.QHBoxLayout()
        quick_map_box.setContentsMargins(0, 0, 0, 0)
        vbox.addLayout(quick_map_box)
        button_quick_save = QtWidgets.QPushButton('保存')
        button_quick_save.clicked.connect(SaveQuickMappingClicked)
        quick_map_box.addWidget(button_quick_save)
        button_quick_switch = QtWidgets.QPushButton('切換')
        button_quick_switch.clicked.connect(SwitchQuickMappingClicked)
        quick_map_box.addWidget(button_quick_switch)
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

    def init_SettingsPage(self):
        'Setting UI'
        # 初始化
        settings_layout = QtWidgets.QVBoxLayout(self.settings_page)
        settings_layout.setContentsMargins(0, 0, 0, 0)
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
        MediaKeyBox.setText(app.translate('', "Use media controler"))
        if loaded_config.get('mediaKey',False):
            MediaKeyBox.setChecked(True)
        def toggleMediaKey():
            btn_switch = MediaKeyBox.isChecked()
            loaded_config['mediaKey'] = btn_switch
            config_file(loaded_config)
            MainWindow.SMTC.setVisible(btn_switch)
        MediaKeyBox.clicked.connect(toggleMediaKey)
        settings_layout.addWidget(MediaKeyBox)

        

        # 開機自啟動
        StartLoginBox = QtWidgets.QCheckBox()
        StartLoginBox.setText(app.translate('', "Start at Login"))
        # 取得目前程式的完整路徑
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
        # 啟動時檢查更新
        CheckUpdateBox = QtWidgets.QCheckBox()
        CheckUpdateBox.setText(app.translate('', "Check update at start"))
        if loaded_config.get('checkUpdataBox',False):
            CheckUpdateBox.setChecked(True)
        def toggleminimizeAtStart():
            loaded_config['checkUpdataBox'] = CheckUpdateBox.isChecked()
            config_file(loaded_config)
        CheckUpdateBox.clicked.connect(toggleminimizeAtStart)
        settings_layout.addWidget(CheckUpdateBox)
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
        #OpenRGB
        OpenRGBBox = QtWidgets.QCheckBox()
        OpenRGBBox.setText(app.translate('', "Use OpenRGB"))
        if loaded_config.get('OpenRGB', False):
            OpenRGBBox.setChecked(True)
            #a_openrgb.Start = True
        def toggleOpenRGB():
            #loaded_config['OpenRGB'] = a_openrgb.Start = OpenRGBBox.isChecked()
            config_file(loaded_config)
        OpenRGBBox.clicked.connect(toggleOpenRGB)
        #settings_layout.addWidget(OpenRGBBox)

        # 語言選擇
        lang_layout = QtWidgets.QHBoxLayout()
        lang_label = QtWidgets.QLabel(app.translate('', "Language"))
        lang_combo = QtWidgets.QComboBox()
        available_langs = scan_language_qm()
        system_locale = get_display_language()
        sys_name = LANG_NAMES.get(system_locale, system_locale)
        # 第一項：系統預設
        lang_combo.addItem(f'{app.translate("", "System Default")}', '')
        # 第二項：English（原始語言，不載入 .qm）
        lang_combo.addItem('English  (en)', 'en')
        current_lang = loaded_config.get('language', '')
        selected_idx = 0
        if current_lang == 'en':
            selected_idx = 1
        for i, (code, name) in enumerate(available_langs):
            lang_combo.addItem(f'{name}  ({code})', code)
            if code == current_lang:
                selected_idx = i + 2  # +2 因為前面有系統預設和 English
        def changeLanguage():
            code = lang_combo.currentData()
            loaded_config['language'] = code
            config_file(loaded_config)
            ShortMesg.put(app.translate('', "Language saved, restart app to apply"))
        lang_combo.currentIndexChanged.connect(changeLanguage)
        lang_combo.blockSignals(True)
        lang_combo.setCurrentIndex(selected_idx)
        lang_combo.blockSignals(False)
        lang_layout.addWidget(lang_label)
        lang_layout.addWidget(lang_combo)
        settings_layout.addLayout(lang_layout)
        

        # 網路 Port 設定
        port_layout = QtWidgets.QHBoxLayout()
        port_label = QtWidgets.QLabel(app.translate('', "Network port"))
        port_spin = QtWidgets.QSpinBox()
        port_spin.setRange(1024, 65535)
        port_spin.setValue(loaded_config.get('port', 25505))
        def changePort():
            loaded_config['port'] = port_spin.value()
            config_file(loaded_config)
            a_shared.Config['port'] = loaded_config['port']
            ShortMesg.put(app.translate('', "Port saved, restart app to apply"))
        port_spin.valueChanged.connect(changePort)
        port_layout.addWidget(port_label)
        port_layout.addWidget(port_spin)
        settings_layout.addLayout(port_layout)

        
        # 檢查更新
        update_button = QtWidgets.QPushButton(app.translate('', "Check for Updates"))
        update_button.clicked.connect(lambda: check_for_updates())
        settings_layout.addWidget(update_button)
        # 返回
        back_button = QtWidgets.QPushButton(app.translate('', "Back"))
        back_button.clicked.connect(lambda: MainWindow.leftStacked.setCurrentWidget(self.main_page))
        settings_layout.addWidget(back_button)

    def init_SystemTray(self):
        '建立系統匣'
        def showMainWindow():
            '顯示主視窗'
            self.showNormal()  # 還原視窗
            self.activateWindow()  # 讓視窗獲得焦點
        exit_action = QtGui.QAction("Exit", self) # 退出鍵
        exit_action.triggered.connect(lambda: sys.exit()) 
        tray_menu = QtWidgets.QMenu()
        tray_menu.addAction(exit_action) 
        self.tray_icon = QtWidgets.QSystemTrayIcon(QtGui.QIcon(asset_path('icon/icon.ico')))
        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.activated.connect(lambda reason: showMainWindow() if reason == QtWidgets.QSystemTrayIcon.ActivationReason.Trigger else None)
        self.tray_icon.show()

    def center(self):
        '視窗置中'
        # 取得螢幕的幾何訊息
        screenGeometry = QtWidgets.QApplication.primaryScreen().geometry()
        # 計算視窗左上角的座標，使其位於螢幕中心
        x = (screenGeometry.width() - self.width()) // 2
        y = (screenGeometry.height() - self.height()) // 2
        # 設定視窗的位置
        self.setGeometry(x, y, self.width(), self.height())

    def update(self,state,parameter):
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
                ScanClicked()
            case 4:  # 同步音量條
                SetVolSlider(*parameter)
            case 5:  # 顯示延遲
                devName,txt = parameter
                if CheckBoxs[devName]:
                    CheckBoxs[devName].setText(f'{a_shared.AllDevS[devName]["name"]} | {txt}')
            case 6: # 媒體鍵
                self.SMTC.control(parameter)
            case 7: # 播放/暫停
                MappingClicked()

    def changeEvent(self, event: QtCore.QEvent):
        '偵測系統主題更改事件'
        if event.type() == QtCore.QEvent.Type.PaletteChange:
            print("[INFO] 系統主題已更改")
            self.apply_palette()
        super().changeEvent(event)

    def closeEvent(self, a0):
        '攔截關閉事件，最小化到托盤'
        if loaded_config.get('keepTray',False):
            a0.ignore()
            self.hide()
        else:
            super().closeEvent(a0)

    def apply_palette(self):
        '套用調色盤'
        dark_palette = QtGui.QPalette()
        dark_palette.setColor(QtGui.QPalette.ColorRole.Window, QtGui.QColor(0, 0, 0))
        dark_palette.setColor(QtGui.QPalette.ColorRole.Button, QtGui.QColor(20, 20, 20))
        light_palette = QtGui.QPalette()

        def get_theme():
            "預設值為 1 (淺色模式)，若返回 0 則表示深色模式"
            if sys.platform == 'win32':
                # 在 Windows 上讀取登錄檔
                settings = QtCore.QSettings(r"HKEY_CURRENT_USER\Software\Microsoft\Windows\CurrentVersion\Themes\Personalize", QtCore.QSettings.Format.NativeFormat)
                # 預設值為 1 (淺色模式)，若返回 0 則表示深色模式
                value = settings.value("AppsUseLightTheme", 1, type=int)
                return value

        if get_theme():
            QtWidgets.QApplication.instance().setPalette(light_palette)
        else:
            QtWidgets.QApplication.instance().setPalette(dark_palette)
MainWindow = main_window() 

#sys.exit(app.exec())

loop = QEventLoop(app)
with loop:
    loop.run_forever()