import pyaudiowpatch as pyaudio
import numpy as np
import queue
import threading
from . import a_shared
import time
#from scipy.signal import butter, sosfilt
#from . import a_openrgb
#######################
class Mapping():
    def __init__(self):
        self.isRunning = False
        self.Start = False
        self.outputDevs = None # 輸出固定參數
        self.inputDev = None   # 輸入固定參數
        self.np_type = np.float32
        self.pya_type = pyaudio.paFloat32
        #self.sos = self.design_lowpass_transition_sos()

    def getTime(self):
        'h:m:s.ms'
        curTime = time.time()
        ms = int((curTime % 1) * 1000)
        localTime = time.localtime(curTime)
        return f'{time.strftime("%H:%M:%S", localTime)}.{ms:03d}'

    def OutputProcesse(self,devName,indata,CHUNKFix,CH_num):
        '輸出處理(重採樣,分配聲道)'
        outdata = np.zeros((CHUNKFix,CH_num),dtype=self.np_type)
        channelSet = a_shared.Config[devName]['channels']
        for outCh,inCh_Vol in enumerate(channelSet): 
            if indata.size > 0:
                inCh = int(inCh_Vol)
                vol = (inCh_Vol % 1)*10
                vol = 1 if vol > 0.99 else vol
                if CHUNKFix/self.CHUNK == 1:     # 原始
                    outdata[:,outCh] = indata[:,inCh]*vol
                elif CHUNKFix/self.CHUNK == 1/2: # 1/2倍採樣
                    outdata[:,outCh] = indata[::2,inCh]*vol
                elif CHUNKFix/self.CHUNK == 2:   # 2倍採樣
                    outdata[:,outCh] = np.repeat(indata[:,inCh],2)*vol
                else:                       # 其他
                    indices = np.linspace(0, self.CHUNK, CHUNKFix+1)
                    outdata[:,outCh] = np.interp(indices[:-1], np.arange(self.CHUNK),indata[:,inCh])*vol
        return outdata
    
    """
    def design_lowpass_transition_sos(self,fs=48000, low=190, high=230, order=6):
        sos = butter(order, low / (0.5 * fs), btype='low', output='sos')
        return sos
    
    def EQ(self,indata: np.ndarray) -> np.ndarray:
        #fs : int
        #    取樣頻率 (Sampling Rate)，單位 Hz
        if indata.ndim == 1:
            # 單聲道
            y = sosfilt(self.sos, indata)
        else:
            # 多聲道處理
            y = np.stack([sosfilt(self.sos, indata[:, ch]) for ch in range(indata.shape[1])], axis=1)

        return y.astype(self.np_type)*5
        """

    def callback_input(self,inCh):
        '輸入處理'
        def callback_A(in_data, frame_count, time_info, status):
            indata = np.frombuffer(in_data, dtype=self.np_type).reshape(-1, inCh)
            for devName,Dev in self.outputDevs.items():
                if Dev['switch']:
                    IP = Dev['IP']
                    Queue = Dev['queue']
                    Queue.put(indata)
                    if IP: # 網路輸出裝置
                        CH_num = Dev['maxOutputChannels']
                        delay = round(a_shared.Config[devName]['delay']/self.Frametime)
                        Qsize = Queue.qsize()
                        Dev['qsize'] = Qsize
                        if Qsize <= delay:
                            #print(f'[Time] {getTime()} Qsize:{Qsize} wait')
                            pass
                        else:
                            if Qsize > delay+1:
                                #print(f'[Time] {getTime()} Qsize:{Qsize} 降低延遲')
                                while Queue.qsize() > delay+1:
                                    Queue.get_nowait()

                            outdata_bytes = self.OutputProcesse(devName,Queue.get(),self.CHUNK,CH_num).tobytes()
                            a_shared.to_server.put([IP,False,outdata_bytes])
            #if a_openrgb.Start:
            #    a_openrgb.RGBQueue.put(indata)
                        
            return (in_data, pyaudio.paContinue)
        return callback_A

    def callback_output(self,outdevName,Queue,CH_num,CHUNKFix):
        '本機輸出裝置'
        def callback_B(in_data, frame_count, time_info, status):
            Qsize = Queue.qsize()
            self.outputDevs[outdevName]['qsize'] = Qsize
            delay = int(a_shared.Config[outdevName]['delay']/self.Frametime)

            if Qsize < delay:
                #print(f'[Time] {getTime()} Qsize:{Qsize} wait')
                outdata = np.zeros((CHUNKFix,CH_num),dtype=self.np_type)
            else:
                if Qsize > delay + 1:
                    print(f'[Time] {self.getTime()} Qsize:{Qsize} delay:{delay} 降低延遲')
                    while Queue.qsize() > delay + 1:
                        Queue.get_nowait()
                    
                indata = Queue.get()
                outdata = self.OutputProcesse(outdevName,indata,CHUNKFix,CH_num)
                #if "DualSense" in outdevName:
                #    outdata = self.EQ(outdata)

            return (outdata, pyaudio.paContinue)
        return callback_B

    def queueDelay(self):
        '顯示延遲'
        for devName,Dev in self.outputDevs.items():
            if Dev['switch']:
                Qsize = Dev.get('qsize',0)
                a_shared.to_GUI.put([5,[devName,f'{Qsize* self.Frametime:02.0f}ms']])
                if Qsize > 200: # 延遲太多重新掃描
                    a_shared.to_GUI.put([3,None])
                
    def sendState(self):
        '對所有已連線裝置發送狀態'
        for devName in self.outputDevs:
            IP = self.outputDevs[devName].get('IP',False)
            if IP:
                a_shared.to_server.put([IP,'state',None])

    def run(self):
        '啟動'
        self.isRunning = True
        a_shared.to_GUI.put([1,self.isRunning]) #運作狀態
        a_shared.to_GUI.put([2,'Start mapping'])
        # 輸入聲道,samplerate
        InputChannel = self.inputDev['maxInputChannels']
        InputRate = int(self.inputDev['defaultSampleRate'])
        # 初始化輸出流
        Resample = False
        Framerate = 100 #可以整除96/48/44.1KHz
        self.Frametime = 1000/Framerate #ms
        self.CHUNK = round(InputRate/Framerate)
        for devName in a_shared.Config['devList']:
            writeQueue = queue.Queue()
            chNum = self.outputDevs[devName]['maxOutputChannels']
            OutputRate = int(self.outputDevs[devName]['defaultSampleRate'])
            RateScale = OutputRate/InputRate
            CHUNKFix = round(self.CHUNK*RateScale)
            if RateScale not in {1,2}:
                Resample = True
            if not self.outputDevs[devName]['IP']: #本機裝置
                try:
                    po = pyaudio.PyAudio()
                    stream = po.open(
                        format=self.pya_type,
                        channels=chNum,
                        rate=OutputRate,
                        output=True,
                        output_device_index=self.outputDevs[devName]['index'],
                        frames_per_buffer=CHUNKFix,
                        stream_callback=self.callback_output(devName,writeQueue,chNum,CHUNKFix))
                    self.outputDevs[devName]['pyaudio']=po
                    self.outputDevs[devName]['stream']=stream
                except Exception as error:
                    print(f'start {devName} error:{error}')
            self.outputDevs[devName]['queue']=writeQueue
        # 初始化輸入流
        pIn = pyaudio.PyAudio()
        try:
            sIn=pIn.open(
                format=self.pya_type,
                channels=InputChannel,
                rate=InputRate,
                input=True,
                input_device_index=self.inputDev['index'],
                frames_per_buffer=self.CHUNK,
                stream_callback=self.callback_input(InputChannel))
        except Exception as error:
                    print(f'start error:{error}')
        a_shared.Header.sampleRate = InputRate
        a_shared.Header.channels = InputChannel
        a_shared.Header.blockSize = self.CHUNK
        a_shared.Header.startStop = True
        #a_openrgb.RGBQueue.empty()
        self.sendState()
        Resample_msg = ''
        if Resample:
            #Resample_msg = f' 重採樣,音質受損!'
            Resample_msg = f',Resampling!'
        # 等待停止&清空隊列
        print("[INFO] 啟動映射")
        a_shared.to_GUI.put([0,f'幀長度:{self.CHUNK}Hz({self.Frametime:.0f}ms){Resample_msg}'])
        timer = 0
        self.Start = True
        while self.Start:
            if timer > 0.5: # 秒
                timer = 0
                #threading.Thread(target=self.queueDelay,daemon = True).start() 
                self.queueDelay()
            time.sleep(0.1)
            timer +=0.1
        # 結束處理
        for devName,Dev in self.outputDevs.items():
            if Dev['switch']:
                Dev['queue'].put(np.zeros((self.CHUNK,InputChannel),dtype=self.np_type))
                if not Dev['IP']: #本機裝置
                    Dev['stream'].stop_stream()
                    Dev['stream'].close()
                    Dev['pyaudio'].terminate()
        sIn.stop_stream()
        sIn.close()
        pIn.terminate()
        self.isRunning = False
        a_shared.to_GUI.put([0,''])    # 清空文字 
        a_shared.to_GUI.put([1,self.isRunning]) # 運作狀態
        a_shared.to_GUI.put([2,'Stop mapping'])
        a_shared.Header.startStop = False
        self.sendState()