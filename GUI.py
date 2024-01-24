from PyQt6.QtCore import *
from PyQt6.QtGui import *
from PyQt6.QtWidgets import *
from functools import partial
import threading
import pyaudiowpatch as pyaudio
import audio
import queue
import sys
##########FUN##########
isStar = False
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
    global input_device,devices_list,isStar
    audio.Stop()
    p = pyaudio.PyAudio()
    input_device = p.get_default_wasapi_loopback()
    default_device = p.get_default_wasapi_device(d_out = True)
    devices_list = []
    for _ , device in enumerate(p.get_device_info_generator_by_host_api(host_api_index=2)):
        if (device['maxOutputChannels'] > 0) and (device['index'] != default_device['index']):
            device['switch'] = 0
            devices_list.append(device)
    p.terminate()
    AddCheckBox()# 添加裝置
# 建立勾選按鈕
def AddCheckBox(): 
    global CheckBoxs,devices_list
    CheckBoxs = {}
    clear_layout(cbox)
    clear_layout(Grid)
    for i,device in enumerate(devices_list):
        name = device['name']
        CheckBoxs[i] = QCheckBox()
        CheckBoxs[i].setText(f'{i+1}.{name}')
        cbox.addWidget(CheckBoxs[i])
    
def OkClicked():
    global table,buttons,devices_list,list_Col
    clear_layout(Grid)
    buttons = {}
    list_Row = ['i\o']
    list_Col = ['']
    for i in range(len(devices_list)):
        if CheckBoxs[i].isChecked():
            devices_list[i]['switch'] = 1
        else:
            devices_list[i]['switch'] = 0

    table = [] #j對應device,channel
    for i in range(len(devices_list)):
        if devices_list[i]['switch'] == 1:
            for channel in range(devices_list[i]['maxOutputChannels']):
                list_Row.append(f'dev{i+1}:{list_input[channel]}')
                table.append([i,channel])
    # 生成list_Col
    for i in range(input_device['maxInputChannels']):
        list_Col.append(list_input[i])
    # 生成按鈕
    Devices_Label = {}
    for i in range(len(list_Col)):
        for j in range(len(list_Row)):
            if i == 0 :
                Devices_Label[i,j] = QLabel(list_Row[j])
                Grid.addWidget(Devices_Label[i, j], i, j)
            elif j == 0:
                Devices_Label[i,j] = QLabel(list_Col[i])
                Grid.addWidget(Devices_Label[i, j], i, j)
            else:
                buttons[i,j] = QPushButton(f'off')
                buttons[i,j].clicked.connect(partial(buttons_clicked, i, j))
                buttons[i,j].setStyleSheet('color: red')
                Grid.addWidget(buttons[i,j], i, j)

def buttons_clicked(i,j):
    global buttons,list_Col
    if buttons[i,j].text() == 'off':
        for k in range(1,len(list_Col)):
            buttons[k,j].setText('off')
            buttons[k,j].setStyleSheet('color: red')
        buttons[i,j].setText('on')
        buttons[i,j].setStyleSheet('color: white')
    else:
        buttons[i,j].setText('off')
        buttons[i,j].setStyleSheet('color: red')

def StarClicked():
    global table,devices_list,isStar,button_star,Grid
    if Grid.count() != 0:
        audio.Stop()
        output_sets = []
        for i in range(len(devices_list)):
            channel = [[] for _ in range(devices_list[i]['maxOutputChannels'])]
            output_sets.append(channel)
                
        for index in buttons:
            if buttons[index].text() == 'on':
                output_sets[table[index[1]-1][0]][table[index[1]-1][1]].append(index[0]) #[device][out channel].append(in channel)

        t = threading.Thread(target=audio.StarStream,args=(devices_list,input_device,output_sets,state_queue,))
        t.daemon = True 
        t.start()

def clear_layout(layout):
        # 移除 layout 中的所有子項目
        for i in reversed(range(layout.count())):
            item = layout.itemAt(i)
            layout.removeItem(item)
            if item.widget():
                item.widget().deleteLater()

def updateChanged(state_queue):
    global status_label,button_star
    while (True):
        parameter = state_queue.get() # 等待狀態更新
        match parameter[0]:
            case 0:
                status_label.setText(parameter[1])
            case 1:
                button_star.setText(parameter[1])
##########參數##########
# 通道列表
list_input = ['FL','FR','CNT','SW','SL','SR','SBL','SBR']
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
# 建立一個CheckBox佈局管理器
cbox = QVBoxLayout()
cbox.setContentsMargins(0, 0, 0, 0)
cbox_container = QWidget()
cbox_container.setLayout(cbox)
vbox.addWidget(cbox_container)
# 建立一個水平佈局管理器
hbox = QHBoxLayout()
hbox.setContentsMargins(0, 0, 0, 0)
hbox_container = QWidget()
hbox_container.setLayout(hbox)
vbox.addWidget(hbox_container)
# 建立scan按鈕
button_scan = QPushButton('掃描')
button_scan.clicked.connect(list_audio_devices)
hbox.addWidget(button_scan)
# 建立ok按鈕
button_ok = QPushButton('布局')
button_ok.clicked.connect(OkClicked)
hbox.addWidget(button_ok)
# 建立開始停止按鈕
button_star = QPushButton('開始')
button_star.clicked.connect(StarClicked)
hbox.addWidget(button_star)
# 建立一個網格佈局管理器
Grid = QGridLayout()
Grid.setContentsMargins(0, 0, 0, 0)
Grid.setAlignment(Qt.AlignmentFlag.AlignCenter)
Grid_container = QWidget()
Grid_container.setLayout(Grid)
vbox.addWidget(Grid_container)
# 建立狀態顯示區
status_label = QLabel()
vbox.addWidget(status_label)
# 更新狀態線程
state_queue = queue.Queue()
t2 = threading.Thread(target=updateChanged,args=(state_queue,))
t2.daemon = True
t2.start()
# 添加置裝
list_audio_devices()
# 建立視窗
main_window = QWidget()
main_window.setLayout(vbox)
main_window.setGeometry(0, 0, 500, 100)
main_window.setWindowTitle('聲道映射')
center(main_window)
main_window.show()
sys.exit(app.exec())