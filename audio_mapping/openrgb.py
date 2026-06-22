import time
from openrgb import OpenRGBClient
from openrgb.utils import RGBColor
import numpy as np
import queue
from scipy.signal import butter, filtfilt
#######################
Start = False
RGBQueue = queue.Queue()
#######################

def generate_V(data):
    L = len(data)
    norm_data = (data - min(data))
    # 計算平均振幅與理想峰值位置（可以是小數）
    mean_amp = np.mean(norm_data)
    Max_L = max(round(mean_amp)*80,30) # 最大亮度
    peak_pos = min(round(mean_amp * (L - 1)),L-1)
    V = np.zeros(L)
    # 左側
    V[:peak_pos+1] = np.linspace(0, Max_L, peak_pos+1)
    # 右側
    # np.linspace(Max_L*0.1, Max_L*0.1, L - peak_pos)
    V[peak_pos:] = Max_L * 0.1 
    #V[peak_pos-1: peak_pos+2] = round(mean_amp)
    return V

def audio2RGB(audio,fs=96000):
    '''
    將音訊資料轉換為 HSV 色彩數據，並適用於多顆 LED 燈條。
    
    參數:
        audio: (2, N) 的 numpy 陣列，左右聲道
        num_leds: LED 燈條上的 LED 數量
        fs: 原始採樣頻率（Hz）
        
    回傳:
        H, S, V 三個 numpy 陣列
        H: 0-360, S: 0-100, V: 0-100
    '''
    # 合併左右聲道
    data = (audio[:,0] + audio[:,1]) / 2.0
    # 降採樣：降低採樣率為原來的1/4
    data_down = data[::32]
    
    new_fs = fs / 32  # 降採樣後的採樣率
    # 振幅處理 正規化到 [0, 1]
    Min = min(data_down)
    norm_data = (data_down - Min) / (np.max(data_down) - Min + 1e-6)

    # 2. 利用差分取得律動強度，並用低通濾波器平滑
    diff = np.abs(np.diff(data_down, prepend=data_down[0]))

    def lowpass_filter(data, cutoff=0.1, fs=1.0, order=4):
        if len(data) < 15:  # scipy 的 filtfilt 預設 padlen 為 3 * order = 12
            return data  # 直接返回原始數據，避免錯誤
        b, a = butter(order, cutoff, btype='low', fs=fs)
        return filtfilt(b, a, data)
    smooth_diff = lowpass_filter(diff, cutoff=0.05, fs=1.0)

    # 將律動數值正規化
    norm_diff = smooth_diff / (np.max(smooth_diff) + 1e-6)

    # 3. 加入 FFT 頻譜分析：計算短時傅立葉轉換中的頻譜質心
    # 參數設定
    window_size = 32  # 可依需求調整
    hop_size = window_size // 2  # 重疊50%
    centroids = []
    # 依據 Hann 窗計算 STFT
    for start in range(0, len(data_down) - window_size, hop_size):
        window = data_down[start: start + window_size] * \
            np.hanning(window_size)
        fft_vals = np.abs(np.fft.rfft(window))
        freqs = np.fft.rfftfreq(window_size, d=1/new_fs)
        # 計算頻譜質心：加權平均頻率
        if np.sum(fft_vals) > 0:
            centroid = np.sum(freqs * fft_vals) / np.sum(fft_vals)
        else:
            centroid = 0
        centroids.append(centroid)
    centroids = np.array(centroids)
    # 插值使其與 data_down 長度相符
    if len(centroids) == 0:
        centroids = np.zeros(1)  # 以 0 取代，避免內插時出錯
    interp_centroids = np.interp(np.arange(len(data_down)),
                                 np.linspace(0, len(data_down),
                                             len(centroids)),
                                 centroids)
    # 由於 new_fs 的 Nyquist 為 new_fs/2，因此將質心正規化到 [0,1]
    norm_centroids = np.clip(interp_centroids / (new_fs/2 + 1e-6), 0, 1)

    # 4. 計算 H (色相)：結合律動與頻譜質心
    # 可調參數：律動佔70%，頻譜質心佔30%
    H = ((norm_diff * 360 * 0.7) + (norm_centroids * 360 * 0.3)) % 360
    # 加入細微波動，增添動態效果
    H += np.sin(np.linspace(0, 2*np.pi, len(H))) * 20
    H = np.clip(H, 0, 360)

    # 計算 S (飽和度)：
    S = np.full_like(norm_data, 100)
    # 計算 V (亮度)：
    V = generate_V(data_down)

    return [H, S, V]

def OpenRGB():
    global Start,RGBQueue

    client = None

    while True:
        if Start:
            if client:
                if RGBQueue.qsize() > 0:
                    # 取得音訊
                    audio = np.vstack([RGBQueue.get() for _ in range(4)])
                    hsv_data = audio2RGB(audio)
                    for device in client.devices:
                        leds = len(device.leds)
                        # 目標的 x 軸座標
                        x_new = np.linspace(0, 1, num=leds)
                        # 使用 np.interp 進行線性插值
                        H_old = np.linspace(0, 1, num=len(hsv_data[0]))
                        S_old = np.linspace(0, 1, num=len(hsv_data[1]))
                        V_old = np.linspace(0, 1, num=len(hsv_data[2]))
                        H = np.interp(x_new, H_old, hsv_data[0])
                        S = np.interp(x_new, S_old, hsv_data[1])
                        V = np.interp(x_new, V_old, hsv_data[2])
                        colors = [RGBColor.fromHSV(int(H[i]), int(S[i]),
                                        int(V[i])) for i in range(leds)]
                        device.set_colors(colors,fast=True)

                else:
                    time.sleep(0.001)
            else:
                try:
                    client = OpenRGBClient()
                    print('[INFO] 與OpenRGB連線成功')
                except:
                    print('[ERRO] 無法與OpenRGB連線')
                    time.sleep(10)
                    
        else:
            if client:
                print('[INFO] 關閉OpenRGB')
                client.clear()
                client = None
            RGBQueue.empty()
            time.sleep(1)

