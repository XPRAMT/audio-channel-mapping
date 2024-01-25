import pyaudiowpatch as pyaudio
import numpy as np
import queue
import time
#######################
CHUNK = 16         # 每幀長度
SampleRate = 96000 # 需要與裝置實際的採樣率一致
AllowDelay = 60    # 過低會破音，根據電腦性能調整
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
    def callback_output(write_queues,channel_num,channel_sets):
        def callback_B(in_data, frame_count, time_info, status):
            # 分離聲道
            outdata = np.zeros((CHUNK,channel_num),dtype=np.uint32)
            if not write_queues.empty(): #不為空
                indata = write_queues.get()
                for j,channel in enumerate(channel_sets): # channel
                    if channel:
                        ch = channel[0] - 1
                        outdata[:,j] = indata[:,ch]
            return (outdata, pyaudio.paContinue)
        return callback_B
    
    def Clear_Queen(data_write_queues):
        for write_queues in data_write_queues:
            with write_queues.mutex:
                write_queues.queue.clear()

    if not isStart:
        isStart = True
        state_queue.put([1,'停止'])
        p = pyaudio.PyAudio()
        # 初始化輸出流
        stream_output = []
        fix_output_sets = []
        data_write_queues = []
        for i,channel_sets in enumerate(output_sets):
            total_sum = sum(sum(sublist) for sublist in channel_sets if sublist)
            if total_sum > 0:
                write_queues = queue.Queue()
                channel = devices_list[i]['maxOutputChannels']
                stream = p.open(format=pyaudio.paInt32,
                                channels=channel,
                                rate=SampleRate,
                                output=True,
                                output_device_index=devices_list[i]['index'],
                                frames_per_buffer=CHUNK,
                                stream_callback=callback_output(write_queues,channel,channel_sets))
                stream_output.append(stream)
                fix_output_sets.append(channel_sets)
                data_write_queues.append(write_queues)
        # 初始化輸入流
        InputChannels = input_device['maxInputChannels']
        stream_input=p.open(format=pyaudio.paInt32,
                            channels=InputChannels,
                            rate=SampleRate,
                            input=True,
                            input_device_index=input_device['index'],
                            frames_per_buffer=CHUNK,
                            stream_callback=callback_input(data_write_queues,InputChannels))
        
        state_queue.put([0,f'聲道映射中,幀長度:{CHUNK}'])
        print(fix_output_sets)
        # 持續
        isStop = False
        while not isStop:
            if data_write_queues[0].qsize() > AllowDelay:
                Clear_Queen(data_write_queues)
                state_queue.put([2,f'已降低延遲'])
            time.sleep(0.5)
        # 結束處理
        stream_input.stop_stream()
        stream_input.close()
        for stream in stream_output:
            stream.stop_stream()
            stream.close()
        p.terminate()
        isStart = False
        state_queue.put([0,'已停止'])
        state_queue.put([1,'開始'])
    