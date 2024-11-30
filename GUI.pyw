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
import copy
import ctypes
import winreg
ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('xpramt.audio.channel.mapping')
##########參數##########
file_name = 'config.json'
coName = ''
CheckBoxs = {}
VolSlider = {}
list_Row = []
list_Col = []
list_input = ['FL','FR','CNT','SW','SL','SR','SBL','SBR']
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
    global timerIsMapping,timerCoDn
    def isMapping():
        if not a_mapping.isRunning:
            timerIsMapping.stop()
            list_audio_devices()
            ShortMesg.put(app.translate("", "Scan successful"))   
            LayoutClicked()
            if tmpMapRunning and len(list_Row)>1:
                a_mapping.outputDevs = copy.deepcopy(outputDevs)
                a_mapping.inputDev = inputDev
                SentUpdate()
                a_mapping.Start = True
            timerCoDn.start(1000)
        else:
            print('a_mapping is Running')
    timerIsMapping = QtCore.QTimer()
    timerIsMapping.timeout.connect(isMapping)
    # # # # # # # # # # # # # # # # # # # 
    def timeOut():
        timerCoDn.stop()
        a_shared.initVol = False
        button_scan.setEnabled(True)
    timerCoDn = QtCore.QTimer()
    timerCoDn.timeout.connect(timeOut)
    # # # # # # # # # # # # # # # # # # # 
    button_scan.setEnabled(False)
    a_shared.initVol = True
    if not tmpMapRunning:
        tmpMapRunning = a_mapping.isRunning
    a_mapping.Start = False
    timerIsMapping.start(100)

# 切換輸入類型
def switch_inputDev():
    a_shared.switchInDev = True
    a_shared.input_class_loopback = not a_shared.input_class_loopback
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
        a_shared.inputDevName = inputDev['name']
    inputDev.update({
        'name': a_shared.inputDevName,'switch': True,
        'IP': None,'volume': 0.0,'maxVol':100
    })
    a_shared.AllDevS[a_shared.inputDevName]=inputDev
    # 本機輸出裝置
    outputDevs = {}
    for device in p.get_device_info_generator_by_host_api(host_api_index=2):
        if (device['maxOutputChannels'] > 0) and (device['name'] != a_shared.inputDevName):
            device.update({
                'switch': False,'IP': None,'volume': 0.0,'maxVol':100,'delay':0,'wait':True
            })
            outputDevs[device['name']] = device
    p.terminate()
    # 網路輸出裝置
    for client_IP in a_server.connected_clients:
        header = a_server.connected_clients.get(client_IP)['header']
        netdevice = {
            'maxOutputChannels': header.channels,'switch': False ,'name':f"IP:{client_IP}",
            'IP':client_IP,'defaultSampleRate':inputDev['defaultSampleRate'],
            'volume':header.volume,'maxVol':header.maxVol,'delay':0,'wait':True
        }
        outputDevs[client_IP] = netdevice
    # 依照名稱排序輸出裝置
    outputDevs = {k: outputDevs[k] for k in sorted(outputDevs)}
    a_shared.AllDevS.update(outputDevs)
    for devName in a_shared.AllDevS:
        for key in list(a_shared.AllDevS[devName].keys()):
            if 'Latency' in key:
                a_shared.AllDevS[devName].pop(key)
    # 重置音量同步
    a_volume.Stop = True
    # 建立裝置UI
    clear_layout(Grid)
    clear_layout(cbox)
    tmpCkBoxs = CheckBoxs
    tmpSlider = VolSlider
    CheckBoxs = {}
    VolSlider = {}
    SpinBoxs = {}
    def buildVolSlider(name):
        vol = a_shared.AllDevS[name]['volume']
        maxVol = a_shared.AllDevS[name]['maxVol']
        VolSlider[name] = QtWidgets.QSlider()
        VolSlider[name].setOrientation(QtCore.Qt.Orientation.Horizontal)
        VolSlider[name].setRange(0,maxVol)
        VolSlider[name].setValue(round(vol*maxVol))
        VolSlider[name].valueChanged.connect(partial(GetVolSlider,name))
        cbox.addWidget(VolSlider[name])
    for i,devName in enumerate(a_shared.AllDevS):
        if devName == a_shared.inputDevName: # 輸入裝置UI
            a_shared.AllDevS[devName]["name"] = f'{devName} | {inputDev["defaultSampleRate"]/1000}KHz'
            input_label.setText(a_shared.AllDevS[devName]["name"])
            CheckBoxs[a_shared.inputDevName] = QtWidgets.QCheckBox()
        else: # 輸出裝置UI
            a_shared.AllDevS[devName]["name"] = f'{i}.{devName} | {a_shared.AllDevS[devName]["defaultSampleRate"]/1000}KHz'
            CheckBoxs[devName] = QtWidgets.QCheckBox()
            CheckBoxs[devName].setText(a_shared.AllDevS[devName]["name"])
            CheckBoxs[devName].clicked.connect(partial(GetCheckBoxs,devName))
            SpinBoxs[devName] = QtWidgets.QSpinBox()
            SpinBoxs[devName].setFixedWidth(55)
            SpinBoxs[devName].setRange(0,1000)
            SpinBoxs[devName].setValue(0)
            SpinBoxs[devName].valueChanged.connect(partial(GetSpinBox,devName))
            # 建立水平佈局管理器
            hbox3 = QtWidgets.QHBoxLayout()
            hbox3.setContentsMargins(0, 0, 0, 0)
            hbox3Container = QtWidgets.QWidget()
            hbox3Container.setLayout(hbox3)
            hbox3.addWidget(CheckBoxs[devName])
            hbox3.addWidget(SpinBoxs[devName])
            cbox.addWidget(hbox3Container)
        # 音量條
        buildVolSlider(devName)
    
    # 套用上次狀態
    for i,SliderName in enumerate(tmpSlider):
        if (i!=0) and (SliderName in VolSlider):
            VolSlider[SliderName].setValue(tmpSlider[SliderName].value())
    for i,CkBoxName in enumerate(tmpCkBoxs):
        if tmpCkBoxs[CkBoxName].isChecked() and (i!=0) and (CkBoxName in CheckBoxs):
            CheckBoxs[CkBoxName].setChecked(True)
            a_shared.AllDevS[CkBoxName]['switch'] = True
# 布局
def LayoutClicked(keep=False):
    global table,outputSets,list_Col,list_Row,buttons,coName
    list_Row = ['i\o']
    list_Col = ['']
    coName=''
    devList= []
    for devName, device in a_shared.AllDevS.items():
        if device['switch'] and device['maxOutputChannels'] > 0:
            coName+=devName
            devList.append(devName)
    a_shared.Config['devList'] = devList
    #print(a_shared.Config)
    table = [] # j對應device,channel
    outputSets = []
    for i,devName in enumerate(outputDevs):
        channel = [[] for _ in range(outputDevs[devName]['maxOutputChannels'])]
        outputSets.append(channel) 
        if outputDevs[devName]['switch'] == 1:
            for c in range(outputDevs[devName]['maxOutputChannels']): #c=channel num
                list_Row.append(f'dev{i+1}: {list_input[c]}')
                table.append([i,c])
    # 生成list_Col
    for i in range(inputDev['maxInputChannels']):
        list_Col.append(list_input[i])
    if not keep:
        clear_layout(Grid)
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

# 自動套用
def Auto_Apply():
    global buttons
    loaded_config = config_file()
    # 更新配置
    if coName in loaded_config:
        print(f'[INFO] Apply config: {coName} {loaded_config[coName]}')

        if 'channels' in loaded_config[coName]:
            for j,i in enumerate(loaded_config[coName]['channels']):
                if (i*j > 0) and (i < len(list_Col)) and (j < len(list_Row)):
                    buttons[i][j].setValue(100)
            ShortMesg.put(app.translate("", "Applied config"))

        if 'delay' in loaded_config[coName]:
            for i,devName in enumerate(a_shared.Config['devList']):
                SpinBoxs[devName].setValue(loaded_config[coName]['delay'][i])
                
# 設定音量滑條
def SetVolSlider(devName,vol):
    a_shared.SliderOn = False
    maxVol = a_shared.AllDevS[devName]['maxVol']
    VolSlider[devName].setValue(round(vol*maxVol))
# 取得音量滑條
def GetVolSlider(devName):
    if a_shared.SliderOn and not a_shared.initVol:
        maxVol = a_shared.AllDevS[devName]['maxVol']
        vol = VolSlider[devName].value()/maxVol
        a_volume.setDevVol(devName,vol)
        a_shared.VolChanger = devName
    a_shared.SliderOn = True
# 取得CheckBox
def GetCheckBoxs(devName):
    a_shared.AllDevS[devName]['switch'] = CheckBoxs[devName].isChecked()
    LayoutClicked(True)
# 取得SpinBox
def GetSpinBox(devName):
    a_shared.AllDevS[devName]['delay'] = SpinBoxs[devName].value()
    a_shared.AllDevS[devName]['wait'] = True

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
    global Grid,inputDev,outputDevList
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
    global buttons
    loaded_config = config_file()
    loaded_config.setdefault(coName,{})
    
    if (Grid.count() == len(list_Col)*len(list_Row)):
        a_shared.Config['channels'] = [0] * len(buttons[1])
        for i,row_btns in enumerate(buttons):
            for j,button in enumerate(row_btns):
                if button:
                    if button.value() >0:
                        a_shared.Config['channels'][j] = i
        loaded_config[coName]['channels']=a_shared.Config['channels']

    a_shared.Config['delay'] = []
    for devName in SpinBoxs:
        if a_shared.AllDevS[devName]['switch']:
            a_shared.Config['delay'].append(SpinBoxs[devName].value())
    loaded_config[coName]['delay'] = a_shared.Config['delay']

    config_file(loaded_config)
    ShortMesg.put(app.translate("", "Saved"))

# 刪除按鈕
def DelClicked():
    loaded_config = config_file()
    if coName in loaded_config:
        loaded_config.pop(coName,None)
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
                    SetVolSlider(*parameter)
                case 5:  # 顯示延遲
                    devName,txt = parameter
                    if CheckBoxs[devName]:
                        CheckBoxs[devName].setText(f'{a_shared.AllDevS[devName]["name"]} | {txt}')
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
    global app,button_mapping,button_scan,Text, translator
    global status_label,mesg_label,Grid,vbox,cbox,input_label
    app = QtWidgets.QApplication(sys.argv)
    app.setStyle('Fusion')
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
    button_Save = QtWidgets.QPushButton(app.translate('', "Save"))
    button_Save.clicked.connect(SaveClicked)
    hbox.addWidget(button_Save)
    # 建立刪除按鈕
    button_del = QtWidgets.QPushButton(app.translate('', "Delete"))
    button_del.clicked.connect(DelClicked)
    hbox.addWidget(button_del)
    # 建立輸入裝置切換按鈕
    button_switch = QtWidgets.QPushButton(app.translate('', "Switch"))
    button_switch.clicked.connect(switch_inputDev)
    hbox.addWidget(button_switch)
    # 建立Refresh按鈕
    button_scan = QtWidgets.QPushButton(app.translate('', "Refresh"))
    button_scan.clicked.connect(ScanClicked)
    hbox2.addWidget(button_scan)
    # 建立映射按鈕
    button_mapping = QtWidgets.QPushButton(app.translate('', "Start"))
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
threading.Thread(target=a_volume.volSync,daemon = True).start()      #音量同步
threading.Thread(target=a_server.start_server,daemon = True).start() #server
threading.Thread(target=a_mapping.StartStream,daemon = True).start() #Mapping
threading.Thread(target=printShortMesg,daemon = True).start()        #ShortMesg
start_HandleReturnMessages() #處理回傳訊息
# 添加置裝(程式入口)
ScanClicked()
# 建立視窗
main_window = QtWidgets.QWidget()
main_window.setLayout(vbox)
main_window.setWindowTitle(app.translate('', "Audio Mapping") + ' v3.0')
main_window.setWindowIcon(QtGui.QIcon('C:/APP/@develop/audio-channel-mapping/icon.ico')) 
main_window.show()
center(main_window)

sys.exit(app.exec())
