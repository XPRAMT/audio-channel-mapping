from PyQt6 import QtWidgets, QtCore, QtGui
from winsdk.windows.media.control import GlobalSystemMediaTransportControlsSessionManager as MediaManager
from winsdk.windows.storage.streams import DataReader, Buffer, InputStreamOptions
from qasync import asyncSlot
import time

def TimeSpan(seconds):
    return int(seconds * 10**7)

def format_time(seconds):
    """將秒數格式化為 mm:ss 或超過1小時則格式化為 hh:mm:ss"""
    seconds = int(seconds)
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    else:
        return f"{minutes:02d}:{secs:02d}"

def getSystemRatio():
    '取得系統縮放比例'
    screen = QtGui.QGuiApplication.primaryScreen()
    return screen.devicePixelRatio()

async def read_stream_into_buffer(stream_ref):
    """
    讀取縮圖串流並返回包含圖片資料的 buffer
    """
    readable_stream = await stream_ref.open_read_async()
    thumb_read_buffer = Buffer(readable_stream.size)
    await readable_stream.read_async(thumb_read_buffer, thumb_read_buffer.capacity, InputStreamOptions.READ_AHEAD)
    
    buffer_reader = DataReader.from_buffer(thumb_read_buffer)
    byte_buffer = bytearray(thumb_read_buffer.length)
    buffer_reader.read_bytes(byte_buffer)
    
    return byte_buffer

class controlBtn(QtWidgets.QPushButton):
    '覆寫按鈕class實現長按'
    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self.pressed_timestamp = None

    def mousePressEvent(self, event):
        self.pressed_timestamp = time.time()  # 記錄按下時的 UNIX 時間戳（秒）
        super().mousePressEvent(event)  # 記得呼叫父類別，否則 clicked 等事件不會觸發

    def mouseReleaseEvent(self, event):
        if self.pressed_timestamp:
            if time.time() - self.pressed_timestamp > 0.3:
                self.blockSignals(True)
                super().mouseReleaseEvent(event)
                self.blockSignals(False)
            else:
                super().mouseReleaseEvent(event)
                
class MediaControlWidget(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.uiTimeOverride = None  # 用來記錄 UI 操作產生的播放時間
        self.currentInfo = None
        self.Pixmap = None
        self.changeSizeEvent = False
        self.session = None
        self.init_ui()

        # 每秒更新一次狀態
        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self.update_status)
        self.timer.start(500)

    def init_ui(self):
        # 把 MainLayout 綁定到 self
        MainLayout = QtWidgets.QVBoxLayout(self)
        MainLayout.setContentsMargins(0, 0, 0, 0)
        # 封面
        self.albumDefault = QtGui.QPixmap("icon/album_default.jpg")
        self.coverLabel = QtWidgets.QLabel()
        self.coverLabel.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.coverLabel.setMinimumSize(200,200)
        self.coverLabel.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding,
                                      QtWidgets.QSizePolicy.Policy.Expanding)
        MainLayout.addWidget(self.coverLabel)
        # 資訊
        self.infoLabel = QtWidgets.QLabel()
        self.infoLabel.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.infoLabel.setWordWrap(True)
        self.infoLabel.setVisible(False)
        MainLayout.addWidget(self.infoLabel)
        # 進度條
        self.slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.slider.valueChanged.connect(self.on_slider_changed)
        MainLayout.addWidget(self.slider)
        # 顯示播放位置/總長度的標籤
        # 先在 init_ui 裏面加上：
        timeLayout = QtWidgets.QHBoxLayout()
        # 左邊顯示「當前時間」
        self.currentTimeLabel = QtWidgets.QLabel("00:00")
        timeLayout.addWidget(self.currentTimeLabel)
        # 用一個彈性空間撐開
        timeLayout.addStretch()
        # 右邊顯示「總時長」
        self.totalTimeLabel = QtWidgets.QLabel("00:00")
        timeLayout.addWidget(self.totalTimeLabel)
        # 最後將 timeLayout 加到你的主佈局中
        MainLayout.addLayout(timeLayout)
        # 控制按鈕
        #⏮⏪▶️⏩⏭
        self.btnPlayIcon = QtGui.QIcon(QtGui.QPixmap("C:\APP\@develop/audio-channel-mapping\icon\widget_play_normal.png"))
        self.btnPauseIcon = QtGui.QIcon(QtGui.QPixmap("C:\APP\@develop/audio-channel-mapping\icon\widget_pause_normal.png"))
        btnLayout = QtWidgets.QHBoxLayout()
        self.btnPrev = controlBtn('')
        self.btnRew = QtWidgets.QPushButton('')
        self.btnPlayPause = QtWidgets.QPushButton('')
        self.btnFwd = QtWidgets.QPushButton('')
        self.btnNext = controlBtn('')
        self.btnPrev.setIcon(QtGui.QIcon("C:\APP\@develop/audio-channel-mapping\icon\widget_previous_normal.png"))
        self.btnPrev.setIconSize(QtCore.QSize(50, 50))
        self.btnPlayPause.setIcon(self.btnPlayIcon)
        self.btnPlayPause.setIconSize(QtCore.QSize(50, 50))
        self.btnNext.setIcon(QtGui.QIcon("C:\APP\@develop/audio-channel-mapping\icon/widget_next_normal.png"))
        self.btnNext.setIconSize(QtCore.QSize(50, 50))

        self.btnPrev.clicked.connect(lambda: self.control('previous track'))
        self.btnPlayPause.clicked.connect(lambda: self.control('play/pause'))
        self.btnNext.clicked.connect(lambda: self.control('next track'))

        for btn in [self.btnPrev, self.btnPlayPause, self.btnNext]:
            btn.setStyleSheet("""
                QPushButton {
                    background-color: transparent;
                    border: none;
                }
                QPushButton:hover { /* 滑鼠懸停時 */
                    background-color: rgb(30, 30, 30);
                    border: none;
                }
                QPushButton:pressed {/* 按下時 */
                    background-color: rgb(50, 50, 50);
                    border: none;
                }
            """)
            btnLayout.addWidget(btn)
        MainLayout.addLayout(btnLayout)

    async def get_session(self):
        try:
            manager = await MediaManager.request_async()
            session = manager.get_current_session()
            if session is None:
                return None
            await session.try_get_media_properties_async()
            return session
        except Exception as e:
            print(f'[ERRO] get_session\n{e}')
    
    def resizeEvent(self, event: QtGui.QResizeEvent):
        super().resizeEvent(event)
        self.setCover()
        
    def setCover(self):
        '設定圖片'
        #print('更新封面')
        if self.Pixmap is None:
            scale = self.albumDefault
        else:
            scale = self.Pixmap
        # 取得圖片比例
        Ratio = scale.height()/scale.width()
        # 計算長寬
        Width = self.slider.width()
        Height = Width * Ratio
        if Height > self.coverLabel.height():
            Height = self.coverLabel.height()
            Width = Height/Ratio
        SystemRatio = getSystemRatio()
        Width = int(Width * SystemRatio)
        Height = int(Height * SystemRatio)
        Size = QtCore.QSize(Width, Height)
        scale.setDevicePixelRatio(SystemRatio)
        scaled = scale.scaled(
                    Size,
                    QtCore.Qt.AspectRatioMode.KeepAspectRatio,
                    QtCore.Qt.TransformationMode.SmoothTransformation
                )
        self.coverLabel.setPixmap(scaled)

    def setLabel(self,info):
        parts = []
        if info.title:
            parts.append(info.title)
        if info.artist:
            parts.append(info.artist)
        if info.album_title:
            parts.append(info.album_title)
        elif info.album_artist:
            parts.append(info.album_artist)

        text_to_show = "\n".join(parts)  # 以換行分割

        if text_to_show != '':
            self.infoLabel.setVisible(True)
            self.infoLabel.setText(text_to_show)
        else:
            self.infoLabel.setVisible(False)

    @asyncSlot()
    async def update_status(self):
        '更新狀態'
        self.session = await self.get_session()
        if self.session is None:
            self.infoLabel.setVisible(False)
            self.currentTimeLabel.setText("00:00")
            self.totalTimeLabel.setText("00:00")
            self.slider.setValue(0)
            self.Pixmap = None
        else:
            info = await self.session.try_get_media_properties_async()
            playback = self.session.get_playback_info()
            timeline = self.session.get_timeline_properties()

            def printInfo():
                print("----- dir() 列出屬性與其值 -----")
                for name in dir(info):
                    # 過濾掉私有屬性 (底線開頭)
                    if not name.startswith("_"):
                        attr_value = getattr(info, name)
                        print(f"{name} = {attr_value}")

            # 若有標題則顯示標題，否則顯示 ""
            if info.title != self.currentInfo:
                #printInfo()
                self.currentInfo = info.title
                self.setLabel(info)
                self.changeSizeEvent = True
                # 取得封面
                if hasattr(info, 'thumbnail') and info.thumbnail:
                    try:
                        byte_buffer = await read_stream_into_buffer(info.thumbnail)
                        self.Pixmap = QtGui.QPixmap()
                        self.Pixmap.loadFromData(byte_buffer)
                    except Exception as e:
                        self.Pixmap = None
                else:
                    self.Pixmap = None
                
            # 更新進度條與時間顯示
            if self.uiTimeOverride is None: # 沒有UI操作
                if self.slider.isSliderDown(): 
                    current_display = self.slider.value()
                else:
                    current_display = int(timeline.position.seconds)
                    self.slider.blockSignals(True)
                    self.slider.setValue(int(current_display))
                    self.slider.blockSignals(False)
            else:
                current_display = self.uiTimeOverride
                self.session.try_change_playback_position_async(TimeSpan(self.uiTimeOverride))
                self.slider.blockSignals(True)
                self.slider.setValue(int(current_display))
                self.slider.blockSignals(False)
                self.uiTimeOverride = None
            
            max_sec = timeline.end_time.total_seconds()
            if max_sec > 0:
                self.slider.setMaximum(int(max_sec))
                self.currentTimeLabel.setText(f"{format_time(current_display)}")
                self.totalTimeLabel.setText(f"{format_time(max_sec)}")
            else:
                self.currentTimeLabel.setText("00:00")
                self.totalTimeLabel.setText("00:00")

            # 根據播放狀態更新按鈕文字
            self.btnPlayPause.setIcon(self.btnPauseIcon if playback.playback_status.name == "PLAYING" else self.btnPlayIcon)

            currentTime = time.time()
            if self.btnNext.isDown() and currentTime - self.btnNext.pressed_timestamp > 0.3:
                self.control('fwd')
            elif self.btnPrev.isDown() and currentTime - self.btnPrev.pressed_timestamp > 0.3:
                self.control('rew')

        # 更新封面
        if self.changeSizeEvent:
            self.changeSizeEvent = False
            self.setCover()

    def control(self, action):
        '發送控制指令'
        if not self.session:
            print('[Erro] 找不到媒體會話，無法執行控制指令')
            return

        if action == 'play/pause':
            status = self.session.get_playback_info().playback_status.name
            if status == "PLAYING":
                self.session.try_pause_async()
            else:
                self.session.try_play_async()
        elif action == 'next track':
            self.session.try_skip_next_async()
        elif action == 'previous track':
            self.session.try_skip_previous_async()
        elif action == 'fwd':
            t = self.session.get_timeline_properties()
            new_pos = t.position.total_seconds() + 5
            self.session.try_change_playback_position_async(TimeSpan(new_pos))
            self.uiTimeOverride = int(new_pos)
        elif action == 'rew':
            t = self.session.get_timeline_properties()
            new_pos = max(t.position.total_seconds() - 5, 0)
            self.session.try_change_playback_position_async(TimeSpan(new_pos))
            self.uiTimeOverride = int(new_pos)

    def on_slider_changed(self):
        '放開滑條'
        if not self.session:
            return
        self.uiTimeOverride = self.slider.value()
