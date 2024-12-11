import pyaudiowpatch as pyaudio
import numpy as np
import queue
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
    #輸出處理(重採樣,分配聲道)
    def OutputProcesse(devName,indata,CHUNKFix,CH_num):
        outdata = np.zeros((CHUNKFix,CH_num),dtype=np_type)
        channelSet = a_shared.Config[devName]['channels']
        for outCh,inCh_Vol in enumerate(channelSet): 
            if indata.size > 0:
                inCh = int(inCh_Vol)
                vol = (inCh_Vol % 1)*10
                vol = 1 if vol > 0.99 else vol
                if CHUNK/CHUNKFix == 1:     #原始
                    outdata[:,outCh] = indata[:,inCh]*vol
                elif CHUNK/CHUNKFix == 2:   #1/2倍採樣
                    outdata[:,outCh] = indata[::2,inCh]*vol
                elif CHUNK/CHUNKFix == 1/2: #2倍採樣
                    outdata[:,outCh] = np.repeat(indata[:,inCh],2)*vol
                else:                       # 其他
                    indices = np.linspace(0, CHUNK, CHUNKFix+1)
                    outdata[:,outCh] = np.interp(indices[:-1], np.arange(CHUNK),indata[:,inCh])*vol
        return outdata
    # 輸入處理
    def callback_input(inCh):
        def callback_A(in_data, frame_count, time_info, status):
            indata = np.frombuffer(in_data, dtype=np_type).reshape(-1, inCh)
            for devName in outputDevs:
                if outputDevs[devName]['switch']:
                    IP = outputDevs[devName]['IP']
                    Queue = outputDevs[devName]['queue']
                    Qsize = Queue.qsize()
                    delay = a_shared.Config[devName]['delay']/Frametime
                    if IP: # 網路輸出裝置
                        CH_num = outputDevs[devName]['maxOutputChannels']
                        if Qsize > delay+1:
                            Queue.get()
                            outdata = Queue.get()
                            outdata_bytes = OutputProcesse(devName,outdata,CHUNK,CH_num).tobytes()
                            a_shared.to_server.put([IP,False,outdata_bytes])
                        elif Qsize < delay:
                            Queue.put(indata)
                        else:
                            Queue.put(indata)
                            outdata = Queue.get()
                            outdata_bytes = OutputProcesse(devName,outdata,CHUNK,CH_num).tobytes()
                            a_shared.to_server.put([IP,False,outdata_bytes])
                    else: # 本機輸出裝置
                        Queue.put(indata)
                        
            return (in_data, pyaudio.paContinue)
        return callback_A
    # 本機輸出裝置
    def callback_output(outdevName,Queue,CH_num,CHUNKFix):
        def callback_B(in_data, frame_count, time_info, status):
            Qsize = Queue.qsize()
            delay = a_shared.Config[outdevName]['delay']/Frametime
            if Qsize == 0:
                a_shared.AllDevS[outdevName]['wait']=True

            if a_shared.AllDevS[outdevName]['wait']:
                outdata = np.zeros((CHUNKFix,CH_num),dtype=np_type)
                if Qsize > delay:
                    a_shared.AllDevS[outdevName]['wait']=False
            else:
                indata = Queue.get()
                outdata = OutputProcesse(outdevName,indata,CHUNKFix,CH_num)
                if Qsize > delay + 6:
                    Queue.get()

            return (outdata, pyaudio.paContinue)
        return callback_B
    # 顯示延遲
    def queueDelay():
        for devName in outputDevs:
            if outputDevs[devName]['switch']:
                frameNum = outputDevs[devName]['queue'].qsize()
                a_shared.to_GUI.put([5,[devName,f'{frameNum * Frametime:.1f}ms']])
                if frameNum > 400:
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
            pyaudios = []
            stream_output = []
            Resample = False
            Framerate = 300 #300可以整除96/48/44.1KHz,每幀延遲10/3ms
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
                        pyaudios.append(po)
                        stream_output.append(stream)
                    except Exception as error:
                        print(f'start {devName} error:{error}')
                outputDevs[devName]['queue']=writeQueue
            # 初始化輸入流
            pi = pyaudio.PyAudio()
            try:
                stream_input=pi.open(
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
                if timer > 2:
                    timer = 0
                    queueDelay()
                time.sleep(0.1)
                timer +=0.1
            # 結束處理
            for stream in stream_output:
                stream.stop_stream()
                stream.close()
            for po in pyaudios:
                po.terminate()
            stream_input.stop_stream()
            stream_input.close()
            pi.terminate()
            isRunning = False
            a_shared.to_GUI.put([0,''])    # 清空文字 
            a_shared.to_GUI.put([1,isRunning]) # 運作狀態
            a_shared.to_GUI.put([2,'Stop mapping'])
        time.sleep(0.1)
