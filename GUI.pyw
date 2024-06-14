from PyQt6.QtCore import Qt,QTimer
from PyQt6.QtGui import QPalette,QColor,QFont,QIcon
from PyQt6.QtWidgets import QApplication,QWidget,QVBoxLayout,QHBoxLayout,QGridLayout,QPushButton,QCheckBox,QLabel
from functools import partial
import pyaudiowpatch as pyaudio
import json
import threading
import audio
import queue
import time
import sys
import os
import ctypes
import subprocess
import atexit
ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('xpramt.audio.channel.mapping')
##########參數##########
Config = [[],[]]
file_name = 'config.json'
AllowDelay = 20 
vol_sync_init = 1
MesgPrintTime = 1000
list_input = ['FL','FR','CNT','SW','SL','SR','SBL','SBR']
##########FUN##########
#視窗置中
def center(self):
    # 取得螢幕的幾何訊息
    screenGeometry = QApplication.primaryScreen().geometry()
    # 計算視窗左上角的座標，使其位於螢幕中心
    x = (screenGeometry.width() - self.width()) // 2
    y = (screenGeometry.height() - self.height()) // 2
    # 設定視窗的位置
    self.setGeometry(x, y, self.width(), self.height())
    
# 列出音訊裝置
def list_audio_devices():
    global input_loopback,devices_list,CheckBoxs,All_Devices
    p = pyaudio.PyAudio()
    input_loopback = p.get_default_wasapi_loopback()
    input_device = p.get_default_wasapi_device(d_out = True)
    devices_list = []
    All_Devices = []
    for device in p.get_device_info_generator_by_host_api(host_api_index=2):
        All_Devices.append(device)
        if (device['maxOutputChannels'] > 0) and (device['index'] != input_device['index']):
            device['switch'] = 0
            devices_list.append(device)
    p.terminate()
    devices_list = sorted(devices_list, key=lambda x: x['name'])
    input_label.setText(f'{input_device["name"]} | {input_device["defaultSampleRate"]/1000}KHz')
    # 建立CheckBoxs
    clear_layout(cbox)
    CheckBoxs = {}
    for i,device in enumerate(devices_list):
        CheckBoxs[i] = QCheckBox()
        CheckBoxs[i].setText(f'{i+1}.{device["name"]} | {device["defaultSampleRate"]/1000}KHz')
        cbox.addWidget(CheckBoxs[i])
    
# 掃描
def ScanClicked():
    audio.Stop()
    time.sleep(0.1)
    list_audio_devices()
    clear_layout(Grid)
    state_queue.put([2,'掃描成功'])
    mesg_timer.start(MesgPrintTime)
        
# 布局
def OkClicked():
    global table,buttons,devices_list,list_Col,list_Row
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
            
    table = [] #j對應device,channel
    for i in range(len(devices_list)):
        if devices_list[i]['switch'] == 1:
            for channel in range(devices_list[i]['maxOutputChannels']):
                list_Row.append(f'dev{i+1}:{list_input[channel]}')
                table.append([i,channel])
    # 生成list_Col
    for i in range(input_loopback['maxInputChannels']):
        list_Col.append(list_input[i])
    # 生成按鈕
    Devices_Label = {}
    buttons = []
    for i in range(len(list_Col)):
        buttons.append([])
        for j in range(len(list_Row)):
            if i == 0 :
                Devices_Label[i,j] = QLabel(list_Row[j])
                Grid.addWidget(Devices_Label[i, j], i, j)
            elif j == 0:
                Devices_Label[i,j] = QLabel(list_Col[i])
                Grid.addWidget(Devices_Label[i, j], i, j)
                buttons[i].append(None)
            else:
                button = QPushButton(f'off')
                button.clicked.connect(partial(buttons_clicked, i, j))
                button.setStyleSheet('color: red')
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
            load_config = [[["Settings"], [AllowDelay],[vol_sync_init]]]
            state_queue.put([2,'已建立配置檔'])
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
            buttons_clicked(i,j)
        state_queue.put([2,'已套用配置'])
        mesg_timer.start(MesgPrintTime)

# 接線按鈕
def buttons_clicked(i,j):
    global buttons,list_Col,list_Row
    if (i*j > 0) and (i <= len(list_Col)) and (j <= len(list_Row)):
        if buttons[i][j].text() == 'off':
            for k in range(1,len(list_Col)):
                buttons[k][j].setText('off')
                buttons[k][j].setStyleSheet('color: red')
            buttons[i][j].setText('on')
            buttons[i][j].setStyleSheet('color: white')
        else:
            buttons[i][j].setText('off')
            buttons[i][j].setStyleSheet('color: red')

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
        state_queue.put([2,'請先佈局'])
        mesg_timer.start(MesgPrintTime)
    elif Check_Devices():
        state_queue.put([2,'裝置變化,重新掃描'])
        mesg_timer.start(MesgPrintTime)
        rescan_timer.start(500)
    else:
        audio.Stop()
        output_sets = []
        for i in range(len(devices_list)):
            channel = [[] for _ in range(devices_list[i]['maxOutputChannels'])]
            output_sets.append(channel)

        for i,row_btns in enumerate(buttons):
            for j,button in enumerate(row_btns):
                if button:
                    if button.text() == 'on':
                        output_sets[table[j-1][0]][table[j-1][1]].append(i) #[device][out channel].append(in channel)

        t_args = (devices_list,input_loopback,output_sets,state_queue,AllowDelay)
        t = threading.Thread(target=audio.StartStream,args=t_args)
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
                    if button.text() == 'on':
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
            loaded_config[i][1] = Config[1]
        # 將更新後的配置寫回 JSON 文件
        config_file(loaded_config)
        state_queue.put([2,'已儲存'])
        mesg_timer.start(MesgPrintTime)
    else:
        state_queue.put([2,'請先佈局'])
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
    state_queue.put([2,'已刪除'])
    mesg_timer.start(MesgPrintTime)

# 音量同步按鈕
def VolSync():
    global VolSync_state,vol_sync
    def cleanup():
        vol_sync.terminate()  # 嘗試終止子進程
        vol_sync.wait()       # 等待子進程真正終止
    atexit.register(cleanup)

    if VolSync_state==False:
        info = subprocess.STARTUPINFO()
        info.dwFlags = subprocess.STARTF_USESHOWWINDOW
        info.wShowWindow = 0 #隱藏 0,最小化 6
        vol_sync = subprocess.Popen(["C:\\APP\\@develop\\Device-Volume-Sync\\vol_sync.exe"], startupinfo=info)
        VolSync_state=True
        button_volsync.setStyleSheet('color: white')
        state_queue.put([2,'啟動音量同步'])
        mesg_timer.start(MesgPrintTime)
    else:
        cleanup()
        VolSync_state=False
        button_volsync.setStyleSheet('color: red')
        state_queue.put([2,'停止音量同步'])
        mesg_timer.start(MesgPrintTime)

# 清除layout
def clear_layout(layout):
        # 移除 layout 中的所有子項目
        for i in reversed(range(layout.count())):
            item = layout.itemAt(i)
            layout.removeItem(item)
            if item.widget():
                item.widget().deleteLater()

# 更新狀態
def updateChanged(state_queue):
    global status_label,button_start
    while (True):
        parameter = state_queue.get() # 等待狀態更新
        match parameter[0]:
            case 0: # 持續狀態
                status_label.setText(parameter[1])
            case 1: # 開始按鈕
                if parameter[1]:
                    button_start.setStyleSheet('color: red')
                else:
                    button_start.setStyleSheet('color: white')
            case 2: # 短暫通知
                mesg_label.setText(parameter[1])

##########初始化##########
app = QApplication(sys.argv)
app.setStyle('Fusion')
# 設定深色主題
dark_palette = QPalette()
dark_palette.setColor(QPalette.ColorRole.Window, QColor(0, 0, 0))
dark_palette.setColor(QPalette.ColorRole.Button, QColor(20, 20, 20))
app.setPalette(dark_palette)
# 設定字體
default_font = QFont('Microsoft JhengHei',12)
app.setFont(default_font)
# 建立一個垂直佈局管理器
vbox = QVBoxLayout()
vbox.setContentsMargins(5, 5, 5, 5)
vbox.setAlignment(Qt.AlignmentFlag.AlignTop)
# 輸入裝置
input_label = QLabel()
input_label.setStyleSheet('color:rgb(0, 255, 0)')
vbox.addWidget(input_label)
# 建立一個CheckBox佈局管理器
cbox = QVBoxLayout()
cbox.setContentsMargins(0, 0, 0, 0)
cbox_container = QWidget()
cbox_container.setLayout(cbox)
vbox.addWidget(cbox_container)
# 建立水平佈局管理器1
hbox = QHBoxLayout()
hbox.setContentsMargins(0, 0, 0, 0)
hbox_container = QWidget()
hbox_container.setLayout(hbox)
vbox.addWidget(hbox_container)
# 建立scan按鈕
button_scan = QPushButton('掃描')
button_scan.clicked.connect(ScanClicked)
hbox.addWidget(button_scan)
# 建立ok按鈕
button_ok = QPushButton('布局')
button_ok.clicked.connect(OkClicked)
hbox.addWidget(button_ok)
# 建立映射按鈕
button_start = QPushButton('映射')
button_start.clicked.connect(StarClicked)
button_start.setStyleSheet('color: red')
hbox.addWidget(button_start)
# 建立水平佈局管理器2
hbox2 = QHBoxLayout()
hbox2.setContentsMargins(0, 0, 0, 0)
hbox2_container = QWidget()
hbox2_container.setLayout(hbox2)
vbox.addWidget(hbox2_container)
# 建立儲存按鈕
button_Save = QPushButton('儲存配置')
button_Save.clicked.connect(SaveClicked)
hbox2.addWidget(button_Save)
# 建立刪除按鈕
button_del = QPushButton('刪除配置')
button_del.clicked.connect(DelClicked)
hbox2.addWidget(button_del)
# 建立音量同步按鈕
button_volsync = QPushButton('音量同步')
button_volsync.clicked.connect(VolSync)
button_volsync.setStyleSheet('color: red')
hbox2.addWidget(button_volsync)
VolSync_state=False
# 建立一個網格佈局管理器
Grid = QGridLayout()
Grid.setContentsMargins(0, 0, 0, 0)
Grid.setAlignment(Qt.AlignmentFlag.AlignCenter)
Grid_container = QWidget()
Grid_container.setLayout(Grid)
vbox.addWidget(Grid_container)
# 建立水平佈局管理器3
hbox3 = QHBoxLayout()
hbox3.setContentsMargins(0, 0, 0, 0)
hbox3_container = QWidget()
hbox3_container.setLayout(hbox3)
vbox.addWidget(hbox3_container)
# 建立狀態顯示區
status_label = QLabel()
hbox3.addWidget(status_label)
mesg_label = QLabel()
mesg_label.setAlignment(Qt.AlignmentFlag.AlignRight)
hbox3.addWidget(mesg_label)
# 計時器
mesg_timer= QTimer()
def reset_mesg():
    mesg_label.setText('')
mesg_timer.timeout.connect(reset_mesg)
rescan_timer = QTimer()
def rescan():
    rescan_timer.stop()
    ScanClicked() 
rescan_timer.timeout.connect(rescan)
# 更新狀態線程
state_queue = queue.Queue()
t2 = threading.Thread(target=updateChanged,args=(state_queue,))
t2.daemon = True
t2.start()
# 添加置裝
list_audio_devices()
# 啟動音量同步程式
loaded_config = config_file()
if loaded_config[0][0][0] == 'Settings':
    if loaded_config [0][2][0] == 1:
        VolSync()
# 建立視窗
main_window = QWidget()
main_window.setLayout(vbox)
main_window.setWindowTitle('聲道映射 v1.8')
main_window.setWindowIcon(QIcon('C:/APP/@develop/audio-channel-mapping/icon.ico'))
main_window.show()
center(main_window)
sys.exit(app.exec())
