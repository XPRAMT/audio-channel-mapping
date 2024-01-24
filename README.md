可以將輸入的任何聲道映射到輸出裝置的任何聲道<br>
簡單的說就是可以用多個藍牙音響組家庭劇院<br>
![img](https://i.imgur.com/mKcvyig.jpg)
<br><br>
安裝:<br>
python>=3.10
```
pip install -r requirements.txt
```

使用:<br>
run.bat<br>
<br>
如果遇到聲音卡頓問題嘗試調整緩衝(CHUNK)大小<br>
SAMPLERATE 需要與裝置實際的採樣率一致
```
CHUNK = 16
SAMPLERATE = 96000
```
