import pyaudiowpatch as pyaudio
import numpy as np
import queue
import time
#######################
isStart = False
def Stop():
    global isStop
    isStop = True

def StartStream(output_devices,input_device,output_sets,state_queue,AllowDelay):
    global isStart,isStop
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
    def callback_output(write_queues,channel_num,channel_sets,CHUNKFix):
        def callback_B(in_data, frame_count, time_info, status):
            # 分離聲道
            outdata = np.zeros((CHUNKFix,channel_num),dtype=np.int32)
            if not isStop:
                indata = write_queues.get()
                for j,channel in enumerate(channel_sets): #  channel
                    if channel and indata.size > 0:
                        ch = channel[0] - 1
                        if CHUNK/CHUNKFix == 1:     #原始
                            outdata[:,j] = indata[:,ch]
                        elif CHUNK/CHUNKFix == 2: #1/2倍採樣
                            outdata[:,j] = indata[0:CHUNK:2,ch]
                        elif CHUNK/CHUNKFix == 1/2: #2倍採樣
                            outdata[:,j] = np.repeat(indata[:,ch],2)
                        else:                       # 其他
                            indices = np.linspace(0, CHUNK, CHUNKFix+1)
                            outdata[:,j] = np.interp(indices[:-1], np.arange(CHUNK),indata[:,ch])
                        
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
        state_queue.put([1,False]) #更改按鈕文字為停止
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
        CHUNK = round(InputRate/300) #300可以整除96/48/44.1KHz,每幀延遲10/3ms
        AD_Frame = round(AllowDelay*3/10-1)
        for i,CH_sets in enumerate(output_sets):
            total_sum = sum(sum(sublist) for sublist in CH_sets if sublist)
            if total_sum > 0:
                write_queues = queue.Queue()
                OutputCH = output_devices[i]['maxOutputChannels']
                OutputRate = int(output_devices[i]['defaultSampleRate'])
                RateScale = OutputRate/InputRate
                CHUNKFix = round(CHUNK*RateScale)
                if RateScale not in {1,2}:
                    Resample = True
                po = pyaudio.PyAudio()
                stream = po.open(format=pyaudio.paInt32,
                                channels=OutputCH,
                                rate=OutputRate,
                                output=True,
                                output_device_index=output_devices[i]['index'],
                                frames_per_buffer=CHUNKFix,
                                stream_callback=callback_output(write_queues,OutputCH,CH_sets,CHUNKFix))
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
                state_queue.put([0,f'幀長度:{CHUNK}Hz,允許延遲:{AD_Frame}幀({round(AD_Frame*10/3)}ms){Resample_msg}'])
                
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
        state_queue.put([1,True]) #更改按鈕文字為開始
        state_queue.put([2,'停止映射'])
