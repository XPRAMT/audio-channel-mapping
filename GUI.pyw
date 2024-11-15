from PyQt6 import QtWidgets,QtCore,QtGui
from functools import partial
import pyaudiowpatch as pyaudio
import json
import threading
import a_mapping
import a_volume
import queue
import time
import sys
import ctypes
import winreg
ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('xpramt.audio.channel.mapping')
##########參數##########
Config = [[],[]]
file_name = 'config.json'
AllowDelay = 20 
MesgPrintTime = 1000
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
def ScanClicked():
    global Mapping_State
    a_mapping.Stop()
    for _ in range(50):
        if not Mapping_State:
            break
        time.sleep(0.1)
    list_audio_devices()
    clear_layout(Grid)
    state_queue.put([2,app.translate("", "Scan successful")])
    mesg_timer.start(MesgPrintTime)
    
# 切換輸入來源
input_class_loopback = True
def switch_input_device():
    global input_class_loopback
    input_class_loopback = not input_class_loopback
    ScanClicked()

# 列出音訊裝置
def list_audio_devices():
    global input_device,devices_list,CheckBoxs,VolSlider,All_Devices,Vol_settings
    # 獲取裝置
    p = pyaudio.PyAudio()
    if input_class_loopback:
        input_device = p.get_default_wasapi_loopback()
        input_device_name = input_device['name'].replace(" [Loopback]","")
    else:
        input_device = p.get_default_wasapi_device()
        input_device_name = input_device['name']

    devices_list = []
    All_Devices = []
    for device in p.get_device_info_generator_by_host_api(host_api_index=2):
        All_Devices.append(device)
        if (device['maxOutputChannels'] > 0) and (device['name'] != input_device_name):
            device['switch'] = 0
            devices_list.append(device)
    p.terminate()
    devices_list = sorted(devices_list, key=lambda x: x['name'])
    input_label.setText(f'{input_device_name} | {input_device["defaultSampleRate"]/1000}KHz')
    # 建立CheckBoxs
    clear_layout(cbox)
    CheckBoxs = {}
    VolSlider={}
    Vol_settings=[]
    for i,device in enumerate(devices_list):
        CheckBoxs[i] = QtWidgets.QCheckBox()
        CheckBoxs[i].setText(f'{i+1}.{device["name"]} | {device["defaultSampleRate"]/1000}KHz')
        CheckBoxs[i].clicked.connect(SetVolume)
        cbox.addWidget(CheckBoxs[i])
        # 音量條
        VolSlider[i] = QtWidgets.QSlider()
        VolSlider[i].setOrientation(QtCore.Qt.Orientation.Horizontal)
        VolSlider[i].setRange(0,100)
        VolSlider[i].setValue(100)
        VolSlider[i].valueChanged.connect(SetVolume)
        cbox.addWidget(VolSlider[i])
        Vol_settings.append([device["name"],VolSlider[i].value()/100,False])
    # 音量同步線程
    a_volume.Stop()
    vol_thread = threading.Thread(target=a_volume.VolumeSync)
    vol_thread.daemon = True 
    vol_thread.start()
    
# 布局
def OkClicked():
    global table,output_sets,buttons,devices_list,list_Col,list_Row
    clear_layout(Grid)
    list_Row = ['i\o']
    list_Col = ['']
    Config[0] = [] 
    for i in range(len(devices_list)):
        if CheckBoxs[i].isChecked():
            devices_list[i]['switch'] = 1
            Config[0].append(devices_list[i]['name'])
        else:
            devices_list[i]['switch'] = 0
            
    table = [] # j對應device,channel
    output_sets = []
    for i in range(len(devices_list)):
        channel = [[] for _ in range(devices_list[i]['maxOutputChannels'])]
        output_sets.append(channel) 
        if devices_list[i]['switch'] == 1:
            for c in range(devices_list[i]['maxOutputChannels']): #c=channel num
                list_Row.append(f'dev{i+1}: {list_input[c]}')
                table.append([i,c])

    # 生成list_Col
    for i in range(input_device['maxInputChannels']):
        list_Col.append(list_input[i])
    # 生成按鈕
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

# 操作config.json
def config_file(save_config=None):
    global state_queue
    with open(file_name, 'a') as json_file:
        pass
    if save_config==None:
        try:
            with open(file_name, 'r') as json_file:
                load_config = json.load(json_file)
        except json.decoder.JSONDecodeError:
            load_config = [[["Settings"],[AllowDelay]]]
            state_queue.put([2,app.translate("", "Config created")])
            mesg_timer.start(MesgPrintTime)
    else:
        load_config = save_config
    # 將更新後的配置寫回 JSON 文件
    with open(file_name, 'w') as json_file:
        json.dump(load_config, json_file)
    return load_config

# 自動套用
def Auto_Apply():
    global Config,buttons,state_queue,AllowDelay
    loaded_config = config_file()
    # 更新配置
    A = None # 檢查是否有已儲存的配置
    for i,C in enumerate(loaded_config):
        if set(C[0]) == set(Config[0]):
            A=i
        if C[0][0] == 'Settings':
            AllowDelay = C [1][0]
    if A != None:
        for j,i in enumerate(loaded_config[A][1]):
            if (i*j > 0) and (i < len(list_Col)) and (j < len(list_Row)):
                buttons[i][j].setValue(100)
        state_queue.put([2,app.translate("", "Applied config")])
        mesg_timer.start(MesgPrintTime)

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
    global output_sets,output_vol,buttons
    for i,row_btns in enumerate(buttons):
                for j,button in enumerate(row_btns):
                    if button:
                        if button.value() >= 0:
                            #[device][out channel].append(in channel)
                            output_sets[table[j-1][0]][table[j-1][1]]=[i,button.value()/100] 
    a_mapping.Receive(output_sets)

# 開始按鈕
def StarClicked():
    global table,devices_list,Grid,All_Devices

    def Check_Devices():
        p2 = pyaudio.PyAudio()
        for i,device in enumerate(p2.get_device_info_generator_by_host_api(host_api_index=2)):
            A = (device['name'] != All_Devices[i]['name'])
            B = (device['maxOutputChannels'] != All_Devices[i]['maxOutputChannels'])
            C = (device['maxInputChannels'] != All_Devices[i]['maxInputChannels'])
            D = (device['defaultSampleRate'] != All_Devices[i]['defaultSampleRate'])
            if A or B or C or D:
                p2.terminate()
                return True
        p2.terminate()
        return False

    if (Grid.count() == 0):
        state_queue.put([2,app.translate("", "Please layout first")])
        mesg_timer.start(MesgPrintTime)
    elif Check_Devices():
        state_queue.put([2,app.translate("", "Device change, rescan")])
        mesg_timer.start(MesgPrintTime)
        rescan_timer.start(500)
    else:
        a_mapping.Stop()
        SentUpdate()
        t_args = (devices_list,input_device,state_queue,AllowDelay)
        t = threading.Thread(target=a_mapping.StartStream,args=t_args)
        t.daemon = True 
        t.start()
        mesg_timer.start(MesgPrintTime)

# 儲存按鈕
def SaveClicked():
    global Config,buttons,state_queue
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
        state_queue.put([2,app.translate("", "Saved")])
        mesg_timer.start(MesgPrintTime)
    else:
        state_queue.put([2,app.translate("", "Please layout first")])
        mesg_timer.start(MesgPrintTime)

# 刪除按鈕
def DelClicked():
    global Config,state_queue
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
    state_queue.put([2,app.translate("", "Deleted")])
    mesg_timer.start(MesgPrintTime)

# 清除layout
def clear_layout(layout):
        # 移除 layout 中的所有子項目
        for i in reversed(range(layout.count())):
            item = layout.itemAt(i)
            layout.removeItem(item)
            if item.widget():
                item.widget().deleteLater()

# 設定裝置音量
def SetVolume():
    global Vol_settings
    for i in VolSlider:
        Vol_settings[i][1] = VolSlider[i].value()/100
        Vol_settings[i][2] = CheckBoxs[i].isChecked()
        a_volume.VolumeSettings(Vol_settings)

# 更新狀態(接收)
Mapping_State = False
def updateChanged(state_queue):
    global status_label,button_start,Mapping_State
    while (True):
        parameter = state_queue.get() # 等待狀態更新
        match parameter[0]:
            case 0: # 持續狀態
                status_label.setText(parameter[1])
            case 1: # 開始按鈕
                Mapping_State = parameter[1]
                if Mapping_State:
                    button_start.setText(app.translate("", "Stop"))
                else:
                    button_start.setText(app.translate("", "Start"))
            case 2: # 短暫通知
                mesg_label.setText(parameter[1])
                '''
            case 3: # vol
                Vol_labelA.setText(parameter[1])
            case 4: # vol
                Vol_labelB.setText(parameter[1])
            '''
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
app = QtWidgets.QApplication(sys.argv)
app.setStyle('Fusion')
# 檢測系統語言
system_locale = get_display_language()
print(system_locale)
# 創建翻譯器
translator = QtCore.QTranslator()
if translator.load(f"{system_locale}.qm"):
    app.installTranslator(translator)
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
button_Save = QtWidgets.QPushButton(app.translate("", "Save"))
button_Save.clicked.connect(SaveClicked)
hbox.addWidget(button_Save)
# 建立刪除按鈕
button_del = QtWidgets.QPushButton(app.translate("", "Delete"))
button_del.clicked.connect(DelClicked)
hbox.addWidget(button_del)
# 建立輸入裝置切換按鈕
button_switch = QtWidgets.QPushButton(app.translate("", "Switch"))
button_switch.clicked.connect(switch_input_device)
hbox.addWidget(button_switch)
# 建立scan按鈕
button_scan = QtWidgets.QPushButton(app.translate("", "Scan"))
button_scan.clicked.connect(ScanClicked)
hbox2.addWidget(button_scan)
# 建立ok按鈕
button_ok = QtWidgets.QPushButton(app.translate("", "Layout"))
button_ok.clicked.connect(OkClicked)
hbox2.addWidget(button_ok)
# 建立映射按鈕
button_start = QtWidgets.QPushButton(app.translate("", "Start"))
button_start.clicked.connect(StarClicked)
hbox2.addWidget(button_start)
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
'''
Vol_labelA = QtWidgets.QLabel()
vbox.addWidget(Vol_labelA)
Vol_labelB = QtWidgets.QLabel()
vbox.addWidget(Vol_labelB)'''
# 更新狀態線程
state_queue = queue.Queue()
t2 = threading.Thread(target=updateChanged,args=(state_queue,))
t2.daemon = True
t2.start()
# 計時器
mesg_timer= QtCore.QTimer()
def reset_mesg():
    mesg_label.setText('')
mesg_timer.timeout.connect(reset_mesg)
rescan_timer = QtCore.QTimer()
def rescan():
    rescan_timer.stop()
    ScanClicked() 
rescan_timer.timeout.connect(rescan)
# 添加置裝
list_audio_devices()
# 建立視窗
main_window = QtWidgets.QWidget()
main_window.setLayout(vbox)
main_window.setWindowTitle(app.translate("", "Audio Mapping")+' v2.1')
main_window.setWindowIcon(QtGui.QIcon('C:/APP/@develop/audio-channel-mapping/icon.ico')) 
main_window.show()
center(main_window)
sys.exit(app.exec())