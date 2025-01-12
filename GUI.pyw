from PyQt6 import QtWidgets,QtCore,QtGui
from functools import partial
import pyaudiowpatch as pyaudio
import re
import time
import json
import queue
import threading
import a_shared
import a_mapping
import a_volume
import a_server
import sys
import copy
import ctypes
import winreg
import requests
import keyboard
ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('xpramt.audio.channel.mapping')
##########參數##########
file_name = 'config.json'
curVersion = "3.2"
coName = ''
CheckBoxs = {}
VolSlider = {}
list_Row = []
##########FUN##########
#視窗置中
def center(self):
    # 取得螢幕的幾何訊息
    screenGeometry = QtWidgets.QApplication.primaryScreen().geometry()
    # 計算視窗左上角的座標，使其位於螢幕中心
    x = (screenGeometry.width() - self.width()) // 2
    y = (screenGeometry.height() - self.height()) // 2
    # 設定視窗的位置
    self.setGeometry(x, y, self.width(), self.height())

# 掃描
def ScanClicked(tmpMapRunning=False):
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

# 切換輸入類型
def switch_inputDev():
    a_shared.input_class_loopback = not a_shared.input_class_loopback
    if a_shared.input_class_loopback:
        button_switch.setText('🎧➞🎙️')
    else:
        button_switch.setText('🎙️➞🎧')
    ScanClicked()

# 列出音訊裝置
def list_audio_devices():
    global inputDev,CheckBoxs,VolSlider,SpinBoxs,outputDevs
    a_shared.AllDevS = {}
    # 輸入裝置
    p = pyaudio.PyAudio()
    if a_shared.input_class_loopback: #設定輸入裝置
        print(f'[INFO] 輸入為Loopback裝置')
        inputDev = p.get_default_wasapi_loopback()
        a_shared.inputDevName = inputDev['name'].replace(" [Loopback]","")
    else:
        print(f'[INFO] 輸入為麥克風裝置')
        inputDev = p.get_default_wasapi_device()
        inDevName = inputDev['name']
    inDevName = a_shared.inputDevName
    inputDev.update({
        'switch': True,'IP': None,'chList':a_volume.DevS[inDevName]['chList'],
        'volume':a_volume.DevS[inDevName]['volume'],'maxVol':100
    })
    a_shared.AllDevS[inDevName]=inputDev
    a_shared.inputDevName = inDevName
    # 本機輸出裝置
    outputDevs = {}
    for device in p.get_device_info_generator_by_host_api(host_api_index=2):
        if (device['maxOutputChannels'] > 0) and (device['name'] != inDevName):
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
        if devName == a_shared.inputDevName: # 輸入裝置UI
            a_shared.AllDevS[devName]['name'] = f'{name} | {inputDev["defaultSampleRate"]/1000}KHz'
            # 開關
            CheckBoxs[devName] = QtWidgets.QCheckBox()
            CheckBoxs[devName].setStyleSheet('color:rgb(0, 255, 0)')
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
        VolSlider[devName] = QtWidgets.QSlider()
        VolSlider[devName].setOrientation(QtCore.Qt.Orientation.Horizontal)
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

# 布局
def LayoutClicked():
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
                slider.valueChanged.connect(partial(ChSlider_clicked, devName, inch-1, c))
                Grid.addWidget(slider, inch, outch)
                # 初始化ChSlider[devName]
                ChSlider.setdefault(devName,[])
                # 確保輸入聲道 inch 有對應的列表
                while len(ChSlider[devName]) <= c:
                    ChSlider[devName].append([])  
                ChSlider[devName][c].append(slider)

# 自動套用
def Auto_Apply():
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
            if devName!=a_shared.inputDevName:
                Apply(devName,loaded_config[coName][devName])
    elif 'devList' in a_shared.Config:
        for devName in a_shared.Config['devList']:
            if devName!=a_shared.inputDevName:
                print(f'[INFO] Apply curent config: {devName} {a_shared.Config[devName]}')
                Apply(devName,a_shared.Config[devName])

# 設定音量滑條
def SetVolSlider(devName,vol):
    maxVol = a_shared.AllDevS[devName]['maxVol']
    VolSlider[devName].blockSignals(True)
    VolSlider[devName].setValue(round(vol*maxVol))
    VolSlider[devName].blockSignals(False)
# 音量滑條變動
def GetVolSlider(devName):
    maxVol = a_shared.AllDevS[devName]['maxVol']
    vol = VolSlider[devName].value()/maxVol
    a_volume.setDevVol(devName,vol)
    a_shared.VolChanger = devName
# CheckBox變動
def GetCheckBoxs(_): #devName   
    global coName
    coName=''
    devList= []
    for devName in CheckBoxs:
        switch = CheckBoxs[devName].isChecked()
        a_shared.AllDevS[devName]['switch'] = switch
        if switch and devName!=a_shared.inputDevName:
            coName+=devName
            devList.append(devName)
    a_shared.Config['devList']=devList
    print(f'[INFO] 裝置變化\n{a_shared.Config}')
# 延遲SpinBox變動
def GetSpinBox(devName):
    a_shared.Config[devName]['delay'] = SpinBoxs[devName].value()
    #print(f'{a_shared.Config}')
# 聲道滑條變動
def ChSlider_clicked(devName, inch, c):
    for ch,inSlider in enumerate(ChSlider[devName][c]):
        if ch == inch:
            a_shared.Config[devName]['channels'][c]=(ch + inSlider.value()/1000)
        else: # 將其它滑條設為0
            inSlider.blockSignals(True)
            inSlider.setValue(0)
            inSlider.blockSignals(False)
    #print(f'{a_shared.Config}')

# 開始/停止按鈕
def MappingClicked():
    if a_mapping.isRunning: # 如果正在運作就停止
        a_mapping.Start = False
        return
    ScanClicked(True)
    
# 操作config.json
def config_file(save_config=None):
    def Save(data):
        with open(file_name, 'w') as json_file:
            json.dump(data, json_file)
    # # # # ＃ # # # # ＃ # # # # ＃ # # # #
    with open(file_name, 'a') as json_file:
        pass
    if save_config==None:
        try:
            with open(file_name, 'r') as json_file:
                save_config = json.load(json_file)
        except json.decoder.JSONDecodeError:
            save_config = {}
            ShortMesg.put(app.translate("", "Config created"))
            Save(save_config)
        return save_config
    else:
        Save(save_config)

# 儲存按鈕
def SaveClicked():
    loaded_config = config_file()
    loaded_config.setdefault(coName,{})
    coDict = {}
    for devName in a_shared.Config['devList']:
        coDict[devName] = a_shared.Config[devName]
    loaded_config[coName] = coDict
    config_file(loaded_config)
    ShortMesg.put(app.translate("", "Saved"))

# 刪除按鈕
def DelClicked():
    loaded_config = config_file()
    if coName in loaded_config:
        loaded_config.pop(coName,None)
        config_file(loaded_config)
    for devName in a_shared.Config['devList']:
        a_shared.Config[devName]['delay'] = 0
        a_shared.Config[devName]['channels'] = [0 for _ in a_shared.Config[devName]['channels']]
    ShortMesg.put(app.translate("", "Deleted"))

# 清除layout
def clear_layout(layout):
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

def start_HandleReturnMessages():
    global worker
    worker = HandleReturnMessages()
    worker.Rescan.connect(ScanClicked)
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
# 檢查更新
def check_for_updates(failMesg = True):
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

##########初始化##########
app = QtWidgets.QApplication(sys.argv)
app.setStyle('Fusion')
# 設定深色主題
dark_palette = QtGui.QPalette()
dark_palette.setColor(QtGui.QPalette.ColorRole.Window, QtGui.QColor(0, 0, 0))
dark_palette.setColor(QtGui.QPalette.ColorRole.Button, QtGui.QColor(20, 20, 20))
app.setPalette(dark_palette)
# 設定字體
default_font = QtGui.QFont('Microsoft JhengHei',12)
app.setFont(default_font)
# 建立主頁面與設定頁面堆疊
stacked_widget = QtWidgets.QStackedWidget()
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
    if translator.load(f"{system_locale}.qm"):
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
    button_setting.clicked.connect(lambda: stacked_widget.setCurrentWidget(settings_page))
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
        btn.setVisible(loaded_config['mediaKey'])
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
    def switchShortName():
        loaded_config['shortName'] = shortNameBox.isChecked()
        config_file(loaded_config)
        ScanClicked()
    shortNameBox.clicked.connect(switchShortName)
    settings_layout.addWidget(shortNameBox)
    # media key
    MediaKeyBox = QtWidgets.QCheckBox()
    MediaKeyBox.setText(app.translate('', "Use media key"))
    if loaded_config.get('mediaKey',False):
        MediaKeyBox.setChecked(True)
    def switchMediaKey():
        btn_switch = MediaKeyBox.isChecked()
        loaded_config['mediaKey'] = btn_switch
        config_file(loaded_config)
        for btn in media_keys:
            btn.setVisible(btn_switch)
    MediaKeyBox.clicked.connect(switchMediaKey)
    settings_layout.addWidget(MediaKeyBox)
    # 檢查更新
    update_button = QtWidgets.QPushButton(app.translate('', "Check for Updates"))
    update_button.clicked.connect(lambda: check_for_updates())
    settings_layout.addWidget(update_button)
    # 返回
    back_button = QtWidgets.QPushButton(app.translate('', "Back"))
    back_button.clicked.connect(lambda: stacked_widget.setCurrentWidget(main_page))
    settings_layout.addWidget(back_button)

    settings_page.setLayout(settings_layout)
BuildSettingsPage()

# 設置堆疊佈局
stacked_widget.addWidget(main_page)
stacked_widget.addWidget(settings_page)
stacked_widget.setCurrentWidget(main_page)
stacked_widget.setWindowTitle(app.translate('', "Audio Mapping") + ' v' + curVersion)
stacked_widget.setWindowIcon(QtGui.QIcon('C:/APP/@develop/audio-channel-mapping/icon.ico')) 
stacked_widget.show()
center(stacked_widget)

# 各種線程
threading.Thread(target=a_volume.volSyncMain,daemon = True).start()      #音量同步
threading.Thread(target=a_server.start_server,daemon = True).start() #server
threading.Thread(target=a_mapping.StartStream,daemon = True).start() #Mapping
threading.Thread(target=printShortMesg,daemon = True).start()        #ShortMesg
start_HandleReturnMessages() #處理回傳訊息
# 添加置裝(程式入口)
ScanClicked()
# 檢查更新
check_for_updates(False)

sys.exit(app.exec())
