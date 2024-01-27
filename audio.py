import pyaudiowpatch as pyaudio
import numpy as np
import queue
import time
#######################
isStart = False
def Stop():
    global isStop
    isStop = True

def StartStream(output_devices,input_device,output_sets,state_queue,CHUNK,AllowDelay):
    global isStart,isStop
    # 輸入處理
    def callback_input(data_write_queues,InputChannels):
        def callback_A(in_data, frame_count, time_info, status):
            # bytes>np.array
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
            outdata = np.zeros((CHUNKFix,channel_num),dtype=np.uint32)
            if not write_queues.empty(): #不為空
                indata = write_queues.get()
                for j,channel in enumerate(channel_sets): # channel
                    if channel:
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
    # 清除隊列
    def Clear_Queen(data_write_queues,AD):
        Clear = False
        for write_queues in data_write_queues:
            if write_queues.qsize() > AD:
                write_queues.queue.clear()
                Clear = True
        return Clear

    if not isStart:
        isStart = True
        state_queue.put([1,'停止'])
        p = pyaudio.PyAudio()

        # 輸入聲道,samplerate
        InputChannel = input_device['maxInputChannels']
        InputRate = int(input_device['defaultSampleRate'])
        # 初始化輸出流
        stream_output = []
        fix_output_sets = []
        data_write_queues = []
        Resample = False
        AD = AllowDelay
        for i,CH_sets in enumerate(output_sets):
            total_sum = sum(sum(sublist) for sublist in CH_sets if sublist)
            if total_sum > 0:
                write_queues = queue.Queue()
                OutputCH = output_devices[i]['maxOutputChannels']
                OutputRate = int(output_devices[i]['defaultSampleRate'])
                RateScale = OutputRate/InputRate
                CHUNKFix = int(CHUNK*RateScale)
                if RateScale not in {1,2}:
                    Resample = True
                stream = p.open(format=pyaudio.paInt32,
                                channels=OutputCH,
                                rate=OutputRate,
                                output=True,
                                output_device_index=output_devices[i]['index'],
                                frames_per_buffer=CHUNKFix,
                                stream_callback=callback_output(write_queues,OutputCH,CH_sets,CHUNKFix))
                stream_output.append(stream)
                fix_output_sets.append(CH_sets)
                data_write_queues.append(write_queues)
                
        print(fix_output_sets)
        # 初始化輸入流
        stream_input=p.open(format=pyaudio.paInt32,
                            channels=InputChannel,
                            rate=InputRate,
                            input=True,
                            input_device_index=input_device['index'],
                            frames_per_buffer=CHUNK,
                            stream_callback=callback_input(data_write_queues,InputChannel))
        if Resample or (len(stream_output)>1):
            AD = AllowDelay*2
        Resample_msg = ''
        if Resample:
            Resample_msg = f' |重採樣,音質受損!'
        delay_ms = int(CHUNK*AD*1000/InputRate)
        state_queue.put([0,f'幀長度:{CHUNK}Hz |允許延遲:{AD}幀({delay_ms}ms){Resample_msg}'])
        # 等待停止&清空隊列
        isStop = False
        while not isStop:
            if Clear_Queen(data_write_queues,AD):
                state_queue.put([2,f'已降低延遲'])
            time.sleep(0.2)
        # 結束處理
        stream_input.stop_stream()
        stream_input.close()
        for stream in stream_output:
            stream.stop_stream()
            stream.close()
        p.terminate()
        isStart = False
        state_queue.put([1,'開始'])
        state_queue.put([0,'已停止'])
        
         
    