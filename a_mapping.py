import pyaudiowpatch as pyaudio
import numpy as np
import queue
import threading
import a_shared
import time
#######################
isRunning = False
Start = False
outputDevs=None # 輸出固定參數
inputDev=None   # 輸入固定參數
np_type = np.float32
pya_type = pyaudio.paFloat32
#######################
def StartStream():
    global isRunning,Start,inputDev,outputDevs,CHUNK
    def getTime():
        curTime = time.time()
        ms = int((curTime % 1) * 1000)
        localTime = time.localtime(curTime)
        return f'{time.strftime("%H:%M:%S", localTime)}.{ms:03d}'
    #輸出處理(重採樣,分配聲道)
    def OutputProcesse(devName,indata,CHUNKFix,CH_num):
        outdata = np.zeros((CHUNKFix,CH_num),dtype=np_type)
        channelSet = a_shared.Config[devName]['channels']
        for outCh,inCh_Vol in enumerate(channelSet): 
            if indata.size > 0:
                inCh = int(inCh_Vol)
                vol = (inCh_Vol % 1)*10
                vol = 1 if vol > 0.99 else vol
                if CHUNKFix/CHUNK == 1:     # 原始
                    outdata[:,outCh] = indata[:,inCh]*vol
                elif CHUNKFix/CHUNK == 1/2: # 1/2倍採樣
                    outdata[:,outCh] = indata[::2,inCh]*vol
                elif CHUNKFix/CHUNK == 2:   # 2倍採樣
                    outdata[:,outCh] = np.repeat(indata[:,inCh],2)*vol
                else:                       # 其他
                    indices = np.linspace(0, CHUNK, CHUNKFix+1)
                    outdata[:,outCh] = np.interp(indices[:-1], np.arange(CHUNK),indata[:,inCh])*vol
        return outdata
    # 輸入處理
    def callback_input(inCh):
        def callback_A(in_data, frame_count, time_info, status):
            indata = np.frombuffer(in_data, dtype=np_type).reshape(-1, inCh)
            for devName,Dev in outputDevs.items():
                if Dev['switch']:
                    IP = Dev['IP']
                    Queue = Dev['queue']
                    Queue.put(indata)
                    if IP: # 網路輸出裝置
                        CH_num = Dev['maxOutputChannels']
                        delay = round(a_shared.Config[devName]['delay']/Frametime)
                        Qsize = Queue.qsize()
                        if Qsize <= delay:
                            #print(f'[Time] {getTime()} Qsize:{Qsize} wait')
                            pass
                        else:
                            if Qsize > delay+1:
                                #print(f'[Time] {getTime()} Qsize:{Qsize} 降低延遲')
                                while Queue.qsize() > delay+1:
                                    Queue.get_nowait()

                            outdata_bytes = OutputProcesse(devName,Queue.get(),CHUNK,CH_num).tobytes()
                            a_shared.to_server.put([IP,False,outdata_bytes])
                        
            return (in_data, pyaudio.paContinue)
        return callback_A
    # 本機輸出裝置
    def callback_output(outdevName,Queue,CH_num,CHUNKFix):
        def callback_B(in_data, frame_count, time_info, status):
            Qsize = Queue.qsize()
            delay = int(a_shared.Config[outdevName]['delay']/Frametime)

            if Qsize < delay:
                #print(f'[Time] {getTime()} Qsize:{Qsize} wait')
                outdata = np.zeros((CHUNKFix,CH_num),dtype=np_type)
            else:
                if Qsize > delay + 2:
                    #print(f'[Time] {getTime()} Qsize:{Qsize} 降低延遲')
                    while Queue.qsize() > delay + 2:
                        Queue.get_nowait()
                    
                indata = Queue.get()
                outdata = OutputProcesse(outdevName,indata,CHUNKFix,CH_num)

            return (outdata, pyaudio.paContinue)
        return callback_B
    # 顯示延遲
    def queueDelay():
        for devName,Dev in outputDevs.items():
            if Dev['switch']:
                Qsize = Dev['queue'].qsize()
                a_shared.to_GUI.put([5,[devName,f'{Qsize * Frametime:.1f}ms']])
                if Qsize > 200: # 延遲太多重新掃描
                    a_shared.to_GUI.put([3,None])
                
        # 開始
    while True:
        if Start:
            isRunning = True
            a_shared.to_GUI.put([1,isRunning]) #運作狀態
            a_shared.to_GUI.put([2,'Start mapping'])
            # 輸入聲道,samplerate
            InputChannel = inputDev['maxInputChannels']
            InputRate = int(inputDev['defaultSampleRate'])
            # 初始化輸出流
            Resample = False
            Framerate = 100 #可以整除96/48/44.1KHz
            Frametime = 1000/Framerate #ms
            CHUNK = round(InputRate/Framerate)
            for devName in a_shared.Config['devList']:
                writeQueue = queue.Queue()
                chNum = outputDevs[devName]['maxOutputChannels']
                OutputRate = int(outputDevs[devName]['defaultSampleRate'])
                RateScale = OutputRate/InputRate
                CHUNKFix = round(CHUNK*RateScale)
                if RateScale not in {1,2}:
                    Resample = True
                if not outputDevs[devName]['IP']: #本機裝置
                    try:
                        po = pyaudio.PyAudio()
                        stream = po.open(
                            format=pya_type,
                            channels=chNum,
                            rate=OutputRate,
                            output=True,
                            output_device_index=outputDevs[devName]['index'],
                            frames_per_buffer=CHUNKFix,
                            stream_callback=callback_output(devName,writeQueue,chNum,CHUNKFix))
                        outputDevs[devName]['pyaudio']=po
                        outputDevs[devName]['stream']=stream
                    except Exception as error:
                        print(f'start {devName} error:{error}')
                outputDevs[devName]['queue']=writeQueue
            # 初始化輸入流
            pIn = pyaudio.PyAudio()
            try:
                sIn=pIn.open(
                    format=pya_type,
                    channels=InputChannel,
                    rate=InputRate,
                    input=True,
                    input_device_index=inputDev['index'],
                    frames_per_buffer=CHUNK,
                    stream_callback=callback_input(InputChannel))
            except Exception as error:
                        print(f'start {a_shared.inputDevName} error:{error}')
            a_shared.Header.sample_rate = InputRate
            a_shared.Header.channels = InputChannel
            a_shared.Header.block_size = CHUNK
            a_shared.header_bytes = a_shared.Header.serialize()
            Resample_msg = ''
            if Resample:
                #Resample_msg = f' 重採樣,音質受損!'
                Resample_msg = f',Resampling!'
            # 等待停止&清空隊列
            print("[INFO] 啟動映射")
            a_shared.to_GUI.put([0,f'幀長度:{CHUNK}Hz({Frametime:.1f}ms){Resample_msg}'])
            timer = 0
            while Start:
                if timer > 2: # 秒
                    timer = 0
                    threading.Thread(target=queueDelay,daemon = True).start() 
                    #queueDelay()
                time.sleep(0.1)
                timer +=0.1
            # 結束處理
            for devName,Dev in outputDevs.items():
                if Dev['switch']:
                    Dev['queue'].put(np.zeros((CHUNK,InputChannel),dtype=np_type))
                    if not Dev['IP']: #本機裝置
                        Dev['stream'].stop_stream()
                        Dev['stream'].close()
                        Dev['pyaudio'].terminate()
            sIn.stop_stream()
            sIn.close()
            pIn.terminate()
            isRunning = False
            a_shared.to_GUI.put([0,''])    # 清空文字 
            a_shared.to_GUI.put([1,isRunning]) # 運作狀態
            a_shared.to_GUI.put([2,'Stop mapping'])
        time.sleep(0.1)
