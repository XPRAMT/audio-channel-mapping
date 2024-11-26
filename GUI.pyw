from PyQt6 import QtWidgets,QtCore,QtGui
from functools import partial
import pyaudiowpatch as pyaudio
import time
import json
import queue
import threading
import a_shared
import a_mapping
import a_volume
import a_server
import sys
import ctypes
import winreg
ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('xpramt.audio.channel.mapping')
##########參數##########
Config = [[],[]]
file_name = 'config.json'
CheckBoxs = {}
VolSlider = {}
list_input = ['FL','FR','CNT','SW','SL','SR','SBL','SBR']
TextKeys = [
    "Save", "Delete", "Switch", "Scan", "Layout",
    "Start", "Stop","Audio Mapping"]
##########FLAG#########
input_class_loopback = True
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
def ScanClicked():
    if a_shared.ScanColDown:
        return
    else:
        a_volume.Stop = True
        if a_mapping.isRunning:
            a_mapping.Start = False
            while a_mapping.isRunning == True:
                time.sleep(0.1)
            a_shared.ScanColDown = True
            list_audio_devices()
            MappingClicked()
        else:
            list_audio_devices()
        ShortMesg.put(app.translate("", "Scan successful"))
    
# 切換輸入類型
def switch_inputDev():
    global input_class_loopback
    input_class_loopback = not input_class_loopback
    ScanClicked()
    print("\n[INFO] 已切換輸入類型",end='\r')

# 列出音訊裝置
def list_audio_devices():
    global inputDev,CheckBoxs,VolSlider,allDevList
    # 輸入裝置
    MainVol,_ = a_volume.Mainvol()
    p = pyaudio.PyAudio()
    if input_class_loopback: #設定輸入裝置
        inputDev = p.get_default_wasapi_loopback()
        a_shared.inputDevName = inputDev['name'].replace(" [Loopback]","")
    else:
        inputDev = p.get_default_wasapi_device()
        a_shared.inputDevName = inputDev['name']
    inputDev.update({
        'name': a_shared.inputDevName,'switch': True,
        'IP': None,'volume': MainVol
    })
    a_shared.AllDevS = {}
    a_shared.AllDevS[a_shared.inputDevName]=inputDev
    # 輸出裝置
    allDevList = []
    outputDev = {}
    for device in p.get_device_info_generator_by_host_api(host_api_index=2):
        allDevList.append(device)
        if (device['maxOutputChannels'] > 0) and (device['name'] != a_shared.inputDevName):
            device.update({
                'switch': False,'IP': None,'volume': 1.0
            })
            outputDev[device['name']] = device
    p.terminate()
    # 網路裝置
    for IP in a_server.connected_clients:
        netdevice = {
            'maxOutputChannels': 2,'switch': False ,'name':f"IP:{IP}",
            'IP':IP,'defaultSampleRate':inputDev['defaultSampleRate'],'volume':1.0
        }
        outputDev[IP] = netdevice
    a_shared.AllDevS.update({k: outputDev[k] for k in sorted(outputDev)})
    # 建立裝置UI
    clear_layout(Grid)
    clear_layout(cbox)
    tmpCkBoxs = CheckBoxs
    tmpSlider = VolSlider
    CheckBoxs = {}
    VolSlider = {}
    def buildVolSlider(name,vol):
        VolSlider[name] = QtWidgets.QSlider()
        VolSlider[name].setOrientation(QtCore.Qt.Orientation.Horizontal)
        VolSlider[name].setRange(0,100)
        VolSlider[name].setValue(int(vol*100))
        VolSlider[name].valueChanged.connect(partial(SetVolSlider,name))
        cbox.addWidget(VolSlider[name])
    for i,(devName, device) in enumerate(a_shared.AllDevS.items()):
        if devName == a_shared.inputDevName: # 輸入裝置UI
            input_label.setText(f'{a_shared.inputDevName} | {inputDev["defaultSampleRate"]/1000}KHz')
            CheckBoxs[a_shared.inputDevName] = QtWidgets.QCheckBox()
        else: # 輸出裝置UI
            CheckBoxs[devName] = QtWidgets.QCheckBox()
            CheckBoxs[devName].setText(f'{i}.{device["name"]} | {device["defaultSampleRate"]/1000}KHz')
            CheckBoxs[devName].clicked.connect(partial(SetCheckBoxs,devName))
            cbox.addWidget(CheckBoxs[devName])
        # 音量條
        buildVolSlider(devName,device['volume'])
    
    # 套用上次狀態
    for i,SliderName in enumerate(tmpSlider):
        if (i!=0) and (SliderName in VolSlider):
            VolSlider[SliderName].setValue(tmpSlider[SliderName].value())
    isTmp = False
    for i,CkBoxName in enumerate(tmpCkBoxs):
        if tmpCkBoxs[CkBoxName].isChecked() and (i!=0) and (CkBoxName in CheckBoxs):
            CheckBoxs[CkBoxName].setChecked(True)
            a_shared.AllDevS[CkBoxName]['switch'] = True
            isTmp = True
    if isTmp:
        LayoutClicked()
        
# 布局
def LayoutClicked():
    global table,outputSets,buttons,list_Col,list_Row,outputDevList
    clear_layout(Grid)
    list_Row = ['i\o']
    list_Col = ['']
    Config[0] = [] 
    for devName, device in a_shared.AllDevS.items():
        if device['switch'] and device['maxOutputChannels'] > 0:
            Config[0].append(devName)

    table = [] # j對應device,channel
    outputSets = []
    # 產生outputDevList
    filteredDict = {k: v for k, v in a_shared.AllDevS.items() if k != a_shared.inputDevName}
    outputDevList = list(filteredDict.values())
    for i in range(len(outputDevList)):
        channel = [[] for _ in range(outputDevList[i]['maxOutputChannels'])]
        outputSets.append(channel) 
        if outputDevList[i]['switch'] == 1:
            for c in range(outputDevList[i]['maxOutputChannels']): #c=channel num
                list_Row.append(f'dev{i+1}: {list_input[c]}')
                table.append([i,c])
    # 生成list_Col
    for i in range(inputDev['maxInputChannels']):
        list_Col.append(list_input[i])
    # 生成滑條
    Devices_Label = {}
    buttons = []
    for i in range(len(list_Col)):
        buttons.append([])
        for j in range(len(list_Row)):
            if i == 0 :
                Devices_Label[i,j] = QtWidgets.QLabel(list_Row[j])
                Devices_Label[i,j].setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
                Grid.addWidget(Devices_Label[i, j], i, j)
            elif j == 0:
                Devices_Label[i,j] = QtWidgets.QLabel(list_Col[i])
                Grid.addWidget(Devices_Label[i, j], i, j)
                buttons[i].append(None)
            else:
                button = QtWidgets.QSlider()
                button.setOrientation(QtCore.Qt.Orientation.Horizontal)
                button.setRange(-1,100)
                button.setValue(-1)
                button.valueChanged.connect(partial(buttons_clicked, i, j))
                Grid.addWidget(button, i, j)
                buttons[i].append(button)
    Auto_Apply()
    SentUpdate()
    # 恢復播放狀態
    if a_mapping.isRunning:
        a_mapping.Start = False
        while a_mapping.isRunning == True:
            time.sleep(0.1)
        MappingClicked()

# 自動套用
def Auto_Apply():
    global Config,buttons
    loaded_config = config_file()
    # 更新配置
    A = None # 檢查是否有已儲存的配置
    for i,C in enumerate(loaded_config):
        if set(C[0]) == set(Config[0]):
            A=i
        if C[0][0] == 'Settings':
            a_mapping.AllowDelay = C [1][0]
    if A != None:
        for j,i in enumerate(loaded_config[A][1]):
            if (i*j > 0) and (i < len(list_Col)) and (j < len(list_Row)):
                buttons[i][j].setValue(100)
        ShortMesg.put(app.translate("", "Applied config"))

# 設定裝置音量
def SetVolSlider(devName):
        a_shared.AllDevS[devName]['volume'] = VolSlider[devName].value()/100
def SetCheckBoxs(devName):
        a_shared.AllDevS[devName]['switch'] = CheckBoxs[devName].isChecked()
def SetGUIMainVol(vol):
    VolSlider[a_shared.inputDevName].setValue(vol)

# 接線按鈕
def buttons_clicked(i,j):
    global buttons,list_Col,list_Row
    if (i*j > 0) and (i < len(list_Col)) and (j < len(list_Row)):
        for k in range(1,len(list_Col)):
            if k!=i:
                buttons[k][j].setValue(-1)
    SentUpdate()

# 更新狀態(發送)
def SentUpdate():
    global outputSets,buttons
    for i,row_btns in enumerate(buttons):
                for j,button in enumerate(row_btns):
                    if button:
                        if button.value() >= 0:
                            #[device][out channel].append(in channel)
                            outputSets[table[j-1][0]][table[j-1][1]]=[i,button.value()/100] 
    a_mapping.Receive(outputSets)

# 開始/停止按鈕
def MappingClicked():
    global table,Grid,inputDev,allDevList,outputDevList
    if a_mapping.isRunning: # 如果正在運作就停止
        a_mapping.Start = False
        return

    def Check_Devices():
        p2 = pyaudio.PyAudio()
        for i,device in enumerate(p2.get_device_info_generator_by_host_api(host_api_index=2)):
            A = (device['name'] != allDevList[i]['name'])
            B = (device['maxOutputChannels'] != allDevList[i]['maxOutputChannels'])
            C = (device['maxInputChannels'] != allDevList[i]['maxInputChannels'])
            D = (device['defaultSampleRate'] != allDevList[i]['defaultSampleRate'])
            if A or B or C or D:
                p2.terminate()
                return True
        p2.terminate()
        return False

    if (Grid.count() == 0):
        ShortMesg.put(app.translate("", "Please layout first"))
    elif Check_Devices():
        ShortMesg.put(app.translate("", "Device change, rescan"))
        ScanClicked()
    else:
        SentUpdate()
        a_mapping.outputDevList = outputDevList
        a_mapping.input_device = inputDev
        a_mapping.Start = True

# 操作config.json
def config_file(save_config=None):
    with open(file_name, 'a') as json_file:
        pass
    if save_config==None:
        try:
            with open(file_name, 'r') as json_file:
                load_config = json.load(json_file)
        except json.decoder.JSONDecodeError:
            load_config = [[["Settings"],[10]]] # AllowDelay = 10
            ShortMesg.put(app.translate("", "Config created"))
    else:
        load_config = save_config
    # 將更新後的配置寫回 JSON 文件
    with open(file_name, 'w') as json_file:
        json.dump(load_config, json_file)
    return load_config

# 儲存按鈕
def SaveClicked():
    global Config,buttons
    if Grid.count() != 0:
        Config[1] = [0] * len(buttons[1])
        for i,row_btns in enumerate(buttons):
            for j,button in enumerate(row_btns):
                if button:
                    if button.value() >0:
                        Config[1][j] = i
       
        loaded_config = config_file()
        # 更新配置
        A = None # 檢查是否有已儲存的配置
        for i,C in enumerate(loaded_config):
            if set(C[0]) == set(Config[0]):
                A=i
        if A == None:
            loaded_config.append(Config)
        else:
            loaded_config[A][1] = Config[1]
        # 將更新後的配置寫回 JSON 文件
        config_file(loaded_config)
        ShortMesg.put(app.translate("", "Saved"))
    else:
        ShortMesg.put(app.translate("", "Please layout first"))

# 刪除按鈕
def DelClicked():
    global Config
    loaded_config = config_file()
    # 更新配置
    A = None # 檢查是否有已儲存的配置
    for i,C in enumerate(loaded_config):
        if set(C[0]) == set(Config[0]):
            A=i
    if A != None:
        del loaded_config[A]
    # 將更新後的配置寫回 JSON 文件
    config_file(loaded_config)
    ShortMesg.put(app.translate("", "Deleted"))

# 清除layout
def clear_layout(layout):
        # 移除 layout 中的所有子項目
        for i in reversed(range(layout.count())):
            item = layout.itemAt(i)
            layout.removeItem(item)
            if item.widget():
                item.widget().deleteLater()

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
                        button_mapping.setText(Text['Stop'])
                    else:
                        button_mapping.setText(Text['Start'])
                case 2:  # 短暫通知
                    ShortMesg.put(parameter)
                case 3:  # 重新掃描
                    self.Rescan.emit()
                case 4:  # 同步音量條
                    SetGUIMainVol(parameter)
def start_HandleReturnMessages():
    global worker
    worker = HandleReturnMessages()
    worker.Rescan.connect(ScanClicked)
    worker.start()
ShortMesg = queue.Queue()
def printShortMesg():
    while True:
        mesg_label.setText(ShortMesg.get())
        timer = 2/(ShortMesg.qsize()+2)
        time.sleep(timer)
        mesg_label.setText('')

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
##########初始化##########
def BuildGUI():
    global app,button_mapping,button_layout,Text
    global status_label,mesg_label,Grid,vbox,cbox,input_label
    app = QtWidgets.QApplication(sys.argv)
    app.setStyle('Fusion')
    # 檢測系統語言
    system_locale = get_display_language()
    print(f"[INFO] locale: {system_locale}",end='\r')
    # 創建翻譯器
    translator = QtCore.QTranslator()
    if translator.load(f"{system_locale}.qm"):
        app.installTranslator(translator)
    # 建立翻譯字典
    Text = {key: app.translate('', key) for key in TextKeys}
    # 設定深色主題
    dark_palette = QtGui.QPalette()
    dark_palette.setColor(QtGui.QPalette.ColorRole.Window, QtGui.QColor(0, 0, 0))
    dark_palette.setColor(QtGui.QPalette.ColorRole.Button, QtGui.QColor(20, 20, 20))
    app.setPalette(dark_palette)
    # 設定字體
    default_font = QtGui.QFont('Microsoft JhengHei',12)
    app.setFont(default_font)
    # 建立一個垂直佈局管理器
    vbox = QtWidgets.QVBoxLayout()
    vbox.setContentsMargins(5, 5, 5, 5)
    vbox.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop)
    # 輸入裝置
    input_label = QtWidgets.QLabel()
    input_label.setStyleSheet('color:rgb(0, 255, 0)')
    vbox.addWidget(input_label)
    # 建立一個CheckBox佈局管理器
    cbox = QtWidgets.QVBoxLayout()
    cbox.setContentsMargins(0, 0, 0, 0)
    cbox_container = QtWidgets.QWidget()
    cbox_container.setLayout(cbox)
    vbox.addWidget(cbox_container)
    # 建立水平佈局管理器1
    hbox = QtWidgets.QHBoxLayout()
    hbox.setContentsMargins(0, 0, 0, 0)
    hbox_container = QtWidgets.QWidget()
    hbox_container.setLayout(hbox)
    vbox.addWidget(hbox_container)
    # 建立水平佈局管理器2
    hbox2 = QtWidgets.QHBoxLayout()
    hbox2.setContentsMargins(0, 0, 0, 0)
    hbox2_container = QtWidgets.QWidget()
    hbox2_container.setLayout(hbox2)
    vbox.addWidget(hbox2_container)
    # 建立儲存按鈕
    button_Save = QtWidgets.QPushButton(Text['Save'])
    button_Save.clicked.connect(SaveClicked)
    hbox.addWidget(button_Save)
    # 建立刪除按鈕
    button_del = QtWidgets.QPushButton(Text['Delete'])
    button_del.clicked.connect(DelClicked)
    hbox.addWidget(button_del)
    # 建立輸入裝置切換按鈕
    button_switch = QtWidgets.QPushButton(Text['Switch'])
    button_switch.clicked.connect(switch_inputDev)
    hbox.addWidget(button_switch)
    # 建立scan按鈕
    button_scan = QtWidgets.QPushButton(Text['Scan'])
    button_scan.clicked.connect(ScanClicked)
    hbox2.addWidget(button_scan)
    # 建立佈局按鈕
    button_layout = QtWidgets.QPushButton(Text['Layout'])
    button_layout.clicked.connect(LayoutClicked)
    hbox2.addWidget(button_layout)
    # 建立映射按鈕
    button_mapping = QtWidgets.QPushButton(Text['Start'])
    button_mapping.clicked.connect(MappingClicked)
    hbox2.addWidget(button_mapping)
    # 建立一個網格佈局管理器
    Grid = QtWidgets.QGridLayout()
    Grid.setContentsMargins(0, 0, 0, 0)
    Grid.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
    Grid_container = QtWidgets.QWidget()
    Grid_container.setLayout(Grid)
    vbox.addWidget(Grid_container)
    # 建立水平佈局管理器3
    hbox3 = QtWidgets.QHBoxLayout()
    hbox3.setContentsMargins(0, 0, 0, 0)
    hbox3_container = QtWidgets.QWidget()
    hbox3_container.setLayout(hbox3)
    vbox.addWidget(hbox3_container)
    # 建立狀態顯示區
    status_label = QtWidgets.QLabel()
    hbox3.addWidget(status_label)
    mesg_label = QtWidgets.QLabel()
    mesg_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight)
    hbox3.addWidget(mesg_label)
#建立GUI
BuildGUI()
# 各種線程
threading.Thread(target=a_volume.VolumeSync,daemon = True).start() #音量同步
threading.Thread(target=a_server.start_server,daemon = True).start() #server
threading.Thread(target=a_mapping.StartStream,daemon = True).start() #Mapping
threading.Thread(target=printShortMesg,daemon = True).start() #ShortMesg
# 添加置裝(程式入口)
list_audio_devices()
start_HandleReturnMessages() #處理回傳訊息
# 建立視窗
main_window = QtWidgets.QWidget()
main_window.setLayout(vbox)
main_window.setWindowTitle(Text['Audio Mapping'] + ' v3.0')
main_window.setWindowIcon(QtGui.QIcon('C:/APP/@develop/audio-channel-mapping/icon.ico')) 
main_window.show()
center(main_window)

sys.exit(app.exec())
