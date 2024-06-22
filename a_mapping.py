import pyaudiowpatch as pyaudio
import numpy as np
import queue
import time
#######################
isStart = False
def Stop():
    global isStop
    isStop = True

def Receive(output_sets_in):
    global output_sets
    output_sets = output_sets_in

def StartStream(output_devices,input_device,state_queue,AllowDelay):
    global isStart,isStop,output_sets
    # 輸入處理
    def callback_input(data_write_queues,InputChannels):
        def callback_A(in_data, frame_count, time_info, status):
            indata = np.frombuffer(in_data, dtype=np.int32)
            indata = np.reshape(indata, (CHUNK, InputChannels))
            for write_queues in data_write_queues:
                write_queues.put(indata)
            return (in_data, pyaudio.paContinue)
        return callback_A
    # 輸出處理
    def callback_output(i,write_queues,CH_num,CHUNKFix):
        def callback_B(in_data, frame_count, time_info, status):
            # 分離聲道
            outdata = np.zeros((CHUNKFix,CH_num),dtype=np.int32)
            if not isStop:
                indata = write_queues.get()
                for j,channel in enumerate(output_sets[i]): #  channel
                    if channel and indata.size > 0: # inputCH/vol
                        ch = channel[0] - 1 
                        if CHUNK/CHUNKFix == 1:     #原始
                            outdata[:,j] = indata[:,ch]*channel[1]
                        elif CHUNK/CHUNKFix == 2: #1/2倍採樣
                            outdata[:,j] = indata[0:CHUNK:2,ch]*channel[1]
                        elif CHUNK/CHUNKFix == 1/2: #2倍採樣
                            outdata[:,j] = np.repeat(indata[:,ch],2)*channel[1]
                        else:                       # 其他
                            indices = np.linspace(0, CHUNK, CHUNKFix+1)
                            outdata[:,j] = np.interp(indices[:-1], np.arange(CHUNK),indata[:,ch])*channel[1]
                '''
                def get_vol_level(AA):
                    log_value = np.mean((abs(AA)/2**24))
                    return '·' * int(log_value)
                if i==1:
                    state_queue.put([3,get_vol_level(outdata)])
                elif i==2:
                    state_queue.put([4,get_vol_level(outdata)])
                '''
            return (outdata, pyaudio.paContinue)
        return callback_B
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

    if not isStart:
        isStart = True
        state_queue.put([1,True]) #運作狀態
        state_queue.put([2,'啟動映射'])
        # 輸入聲道,samplerate
        InputChannel = input_device['maxInputChannels']
        InputRate = int(input_device['defaultSampleRate'])
        # 初始化輸出流
        pyaudios = []
        stream_output = []
        fix_output_sets = []
        data_write_queues = []
        Resample = False
        Framerate = 300 #300可以整除96/48/44.1KHz,每幀延遲10/3ms
        Frametime = 1000/Framerate #ms
        CHUNK = round(InputRate/Framerate) 
        AD_Frame = max(round(AllowDelay/Frametime)-1,1)
        for i,CH_sets in enumerate(output_sets):
            if output_devices[i]['switch']:
                write_queues = queue.Queue()
                CH_num = output_devices[i]['maxOutputChannels']
                OutputRate = int(output_devices[i]['defaultSampleRate'])
                RateScale = OutputRate/InputRate
                CHUNKFix = round(CHUNK*RateScale)
                if RateScale not in {1,2}:
                    Resample = True
                po = pyaudio.PyAudio()
                stream = po.open(format=pyaudio.paInt32,
                                channels=CH_num,
                                rate=OutputRate,
                                output=True,
                                output_device_index=output_devices[i]['index'],
                                frames_per_buffer=CHUNKFix,
                                stream_callback=callback_output(i,write_queues,CH_num,CHUNKFix))
                pyaudios.append(po)
                stream_output.append(stream)
                fix_output_sets.append(CH_sets)
                data_write_queues.append(write_queues)
                
        print(fix_output_sets)
        # 初始化輸入流
        pi = pyaudio.PyAudio()
        stream_input=pi.open(format=pyaudio.paInt32,
                            channels=InputChannel,
                            rate=InputRate,
                            input=True,
                            input_device_index=input_device['index'],
                            frames_per_buffer=CHUNK,
                            stream_callback=callback_input(data_write_queues,InputChannel))
        Resample_msg = ''
        if Resample:
            Resample_msg = f' 重採樣,音質受損!'
        # 等待停止&清空隊列
        isStop = False
        while not isStop:
            for _ in range(10):
                time.sleep(0.1)
                if isStop:
                    break
            else:
                if Clear_Queen(data_write_queues,AD_Frame):
                    AD_Frame+=1
                    state_queue.put([2,f'已降低延遲'])
                state_queue.put([0,f'幀長度:{CHUNK}Hz,允許延遲:{AD_Frame}幀({round(AD_Frame*Frametime)}ms){Resample_msg}'])
                
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
        isStart = False
        state_queue.put([0,''])
        state_queue.put([1,False]) #運作狀態
        state_queue.put([2,'停止映射'])
