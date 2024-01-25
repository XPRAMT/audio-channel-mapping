import pyaudiowpatch as pyaudio
import numpy as np
import queue
import time
#######################
CHUNK = 240         # 每幀長度
AllowDelay = 6      # 過低會破音，根據電腦性能調整
#######################
isStart = False
def Stop():
    global isStop
    isStop = True

def StartStream(devices_list,input_device,output_sets,state_queue,):
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
                        if CHUNK/CHUNKFix == 1:
                            outdata[:,j] = indata[:,ch]
                        elif CHUNK/CHUNKFix == 2:
                            outdata[:,j] = indata[0:CHUNK:2,ch]
                        else:
                            outdata[:,j] = indata[0:CHUNKFix,ch]
                        
            return (outdata, pyaudio.paContinue)
        return callback_B
    
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
        SameRate = True
        SameError = False
        for i,channel_sets in enumerate(output_sets):
            total_sum = sum(sum(sublist) for sublist in channel_sets if sublist)
            if total_sum > 0:
                write_queues = queue.Queue()
                Outputchannel = devices_list[i]['maxOutputChannels']
                OutputRate = int(devices_list[i]['defaultSampleRate'])
                RateScale = OutputRate/InputRate
                if not (RateScale > 1):
                    CHUNKFix = int(CHUNK*RateScale)
                    if RateScale not in {1,0.5}:
                        SameRate = False
                    stream = p.open(format=pyaudio.paInt32,
                                    channels=Outputchannel,
                                    rate=OutputRate,
                                    output=True,
                                    output_device_index=devices_list[i]['index'],
                                    frames_per_buffer=CHUNKFix,
                                    stream_callback=callback_output(write_queues,Outputchannel,channel_sets,CHUNKFix))
                    stream_output.append(stream)
                    fix_output_sets.append(channel_sets)
                    data_write_queues.append(write_queues)
                else:
                    SameError = True
        # 初始化輸入流
        if not SameError:
            stream_input=p.open(format=pyaudio.paInt32,
                                channels=InputChannel,
                                rate=InputRate,
                                input=True,
                                input_device_index=input_device['index'],
                                frames_per_buffer=CHUNK,
                                stream_callback=callback_input(data_write_queues,InputChannel))
            
            print(fix_output_sets)
            AD = int(AllowDelay*(len(data_write_queues)+2)/3)
            if SameRate:
                state_queue.put([0,f'映射中,幀長度:{CHUNK}Hz,允許延遲:{AD}幀'])
            else:
                state_queue.put([0,f'裝置採樣率不一致,聲音異常!'])

            # 持續
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
        if SameError:
            state_queue.put([0,'錯誤:輸出採樣率大於輸入'])
        else:
            state_queue.put([0,'已停止'])
        
         
    