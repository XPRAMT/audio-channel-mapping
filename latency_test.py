import sounddevice as sd
import numpy as np
import time

# 設定參數
SAMPLE_RATE = 96000  # 96kHz
DURATION = 0.001  # 1ms
FREQ = 24000  # 測試信號頻率 1000Hz
TIMEOUT = 2  # 超時時間 (秒)

# 產生 1ms 的正弦波音訊信號
t = np.linspace(0, DURATION, int(SAMPLE_RATE * DURATION), endpoint=False)
signal = 0.5 * np.sin(2 * np.pi * FREQ * t)

# 初始化變數
start_time = None
received = False
delays = []
success_count = 0  # 成功接收到信號的次數

def callback(indata, frames, time_info, status):
    """回調函數，用於檢測麥克風接收信號"""
    global start_time, received, delays, success_count
    if status:
        print(f"Warning: {status}")

    # 檢查信號是否出現在麥克風數據中
    if np.any(indata[:, 0] > 0.01):  # 判斷是否有超過閾值的信號
        received = True
        end_time = time.time()  # 使用 time.time() 取得實際時間戳
        delay = end_time - start_time
        delays.append(delay)
        print(f"{success_count + 1:02d}|latency: {delay * 1000:.3f} ms")
        success_count += 1

# 測試 n 次
print('開始測試...')
while success_count < 12:
    try:
        # 設定麥克風錄音
        with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, callback=callback):
            # 記錄發送開始時間
            start_time = time.time()
            received = False

            # 發送音訊信號
            sd.play(signal, samplerate=SAMPLE_RATE)

            # 等待信號接收或超時
            timeout_time = start_time + TIMEOUT
            while not received and time.time() < timeout_time:
                time.sleep(0.001)

            if not received:
                print('.')

    except KeyboardInterrupt:
        print("程序中止。")
        break

# 計算平均延遲
if delays:
    avg_delay = sum(delays) / len(delays)
    print(f"平均延遲時間: {avg_delay * 1000:.3f} ms")
    max_values = sorted(delays, reverse=True)[:2]  # 找到最大的兩個值
    min_values = sorted(delays)[:2]  # 找到最小的兩個值
    # 去除最高兩個和最低兩個值
    trimmed_delays = [d for d in delays if d not in max_values and d not in min_values]
    avg_delay = sum(trimmed_delays) / len(trimmed_delays)  # 計算平均值
    print(f"去除最高最低: {avg_delay * 1000:.3f} ms")
else:
    print("未能成功測量延遲時間。")
