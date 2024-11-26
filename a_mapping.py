import pyaudiowpatch as pyaudio
import numpy as np
import queue
import a_shared
import time
import threading
#######################
isRunning = False
Start = False
outputSets=[]
outputDevList=None
input_device=None
AllowDelay=10
np_type = np.float32
pya_type = pyaudio.paFloat32
#######################
def Receive(outputSetsIn):
    global outputSets
    if len(outputSetsIn)==len(outputSets) or isRunning == False:
        outputSets = outputSetsIn
        print(f"\033[K[INFO] {outputSets}",end='\r')

def StartStream():
    global isRunning,Start,input_device,outputDevList,outputSets,CHUNK
    #輸出處理(重採樣,分配聲道)
    def OutputProcesse(indata,CHUNKFix,output_set,CH_num):
        outdata = np.zeros((CHUNKFix,CH_num),dtype=np_type)
        for j,channel in enumerate(output_set): 
            if channel and indata.size > 0: # [[inputCH,vol][inputCH,vol]]
                ch = channel[0] - 1 
                vol = channel[1]
                if CHUNK/CHUNKFix == 1:     #原始
                    outdata[:,j] = indata[:,ch]*vol
                elif CHUNK/CHUNKFix == 2:   #1/2倍採樣
                    outdata[:,j] = indata[::2,ch]*vol
                elif CHUNK/CHUNKFix == 1/2: #2倍採樣
                    outdata[:,j] = np.repeat(indata[:,ch],2)*vol
                else:                       # 其他
                    indices = np.linspace(0, CHUNK, CHUNKFix+1)
                    outdata[:,j] = np.interp(indices[:-1], np.arange(CHUNK),indata[:,ch])*vol
        return outdata
    # 輸入處理
    def callback_input(data_write_queues,InputChannels):
        def callback_A(in_data, frame_count, time_info, status):
            indata = np.frombuffer(in_data, dtype=np_type).reshape(-1, InputChannels)
            for write_queues in data_write_queues:
                write_queues.put(indata)
            return (in_data, pyaudio.paContinue)
        return callback_A
    # 輸出處理(本機裝置)
    def callback_output(i,write_queue,CH_num,CHUNKFix):
        def callback_B(in_data, frame_count, time_info, status):
            if Start:
                indata = write_queue.get()
                outdata = OutputProcesse(indata,CHUNKFix,outputSets[i],CH_num)
            else:
                outdata = np.zeros((CHUNKFix,CH_num),dtype=np_type)
            return (outdata, pyaudio.paContinue)
        return callback_B
    # 輸出處理(網路裝置)
    def netDev_output(i,write_queue,CH_num,IP):
        while Start:
            indata = write_queue.get()
            outdata_bytes = OutputProcesse(indata,CHUNK,outputSets[i],CH_num).tobytes()
            a_shared.to_server.put([IP,False,outdata_bytes])
    # 清除隊列/增加延遲
    def Clear_Queen(data_write_queues,AD_Frame):
        Clear = False
        for write_queues in data_write_queues:
            if write_queues.qsize() > AD_Frame:
                Clear = True
        if Clear:
            for write_queues in data_write_queues:
                write_queues.queue.clear()
        return Clear
    # 開始
    while True:
        if Start:
            isRunning = True
            a_shared.to_GUI.put([1,isRunning]) #運作狀態
            a_shared.to_GUI.put([2,'Start mapping'])
            # 輸入聲道,samplerate
            InputChannel = input_device['maxInputChannels']
            InputRate = int(input_device['defaultSampleRate'])
            # 初始化輸出流
            pyaudios = []
            stream_output = []
            data_write_queues = []
            Resample = False
            Framerate = 300 #300可以整除96/48/44.1KHz,每幀延遲10/3ms
            Frametime = 1000/Framerate #ms
            CHUNK = round(InputRate/Framerate)
            AD_Frame = max(round(AllowDelay/Frametime)-1,1)
            for i in range(len(outputDevList)):
                if outputDevList[i]['switch']:
                    write_queue = queue.Queue()
                    CH_num = outputDevList[i]['maxOutputChannels']
                    OutputRate = int(outputDevList[i]['defaultSampleRate'])
                    RateScale = OutputRate/InputRate
                    CHUNKFix = round(CHUNK*RateScale)
                    if RateScale not in {1,2}:
                        Resample = True
                    if outputDevList[i]['IP']: #網路裝置
                        IP = outputDevList[i]['IP']
                        threading.Thread( # 為每個連線啟動一個線程
                            target=netDev_output,
                            args=(i,write_queue,CH_num,IP),
                            daemon=True).start()
                    else: #本機裝置
                        try:
                            po = pyaudio.PyAudio()
                            stream = po.open(
                                format=pya_type,
                                channels=CH_num,
                                rate=OutputRate,
                                output=True,
                                output_device_index=outputDevList[i]['index'],
                                frames_per_buffer=CHUNKFix,
                                stream_callback=callback_output(i,write_queue,CH_num,CHUNKFix))
                            pyaudios.append(po)
                            stream_output.append(stream)
                        except Exception as error:
                            print(f'start {outputDevList[i]["name"]} error:\n{error}')
                    data_write_queues.append(write_queue)
            # 初始化輸入流
            pi = pyaudio.PyAudio()
            try:
                stream_input=pi.open(
                    format=pya_type,
                    channels=InputChannel,
                    rate=InputRate,
                    input=True,
                    input_device_index=input_device['index'],
                    frames_per_buffer=CHUNK,
                    stream_callback=callback_input(data_write_queues,InputChannel))
            except Exception as error:
                        print(f'start {input_device["name"]} error:\n{error}')
            a_shared.Header.sample_rate = InputRate
            a_shared.Header.channels = InputChannel
            a_shared.Header.block_size = CHUNK
            a_shared.header_bytes = a_shared.Header.serialize()
            Resample_msg = ''
            if Resample:
                #Resample_msg = f' 重採樣,音質受損!'
                Resample_msg = f',Resampling!'
            # 等待停止&清空隊列
            print("\n[INFO] 啟動映射",end='\r')
            while Start:
                for _ in range(10):
                    time.sleep(0.1)
                    a_shared.ScanColDown = False
                    if not Start:
                        break
                else:
                    totalDelay = round(AD_Frame*Frametime)
                    if Clear_Queen(data_write_queues,AD_Frame):
                        AD_Frame+=1
                        a_shared.to_GUI.put([2,f'Latency reduced'])
                    if totalDelay > 50: #延遲>50ms
                        a_shared.to_GUI.put([3,None])
                    a_shared.to_GUI.put([0,f'幀長度:{CHUNK}Hz,允許延遲:{AD_Frame}幀({totalDelay})ms){Resample_msg}'])
                    #a_shared.to_GUI.put([0,f'Allow delay:{round(AD_Frame*Frametime)}ms{Resample_msg}'])

            # 結束處理
            stream_input.stop_stream()
            stream_input.close()
            pi.terminate()
            for write_queues in data_write_queues:
                    write_queues.put(np.array([]))
            for stream in stream_output:
                stream.stop_stream()
                stream.close()
            for po in pyaudios:
                po.terminate()
            isRunning = False
            a_shared.to_GUI.put([0,''])    # 清空文字 
            a_shared.to_GUI.put([1,isRunning]) # 運作狀態
            a_shared.to_GUI.put([2,'Stop mapping'])
            print("\n[INFO] 停止映射",end='\r')
        time.sleep(0.1)
