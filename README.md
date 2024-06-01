可以將輸入的任何聲道映射到輸出裝置的任何聲道<br>
簡單的說就是可以用多個藍牙音響組家庭劇院<br>
![img](https://i.imgur.com/mKcvyig.jpg)
<br><br>
安裝:<br>
python>=3.10
```
git clone https://github.com/XPRAMT/audio-channel-mapping.git
```
```
pip install -r requirements.txt
```

使用:<br>
GUI.pyw<br>

提示:<br>
可以在config.json調整允許延遲(ms),系統會從設定值開始嘗試,直到不會卡頓<br>
```
[["AllowDelay"], [20]]   # 允許延遲,預設20ms
```
如果需要在多個裝置間同步音量請參考:<br>
https://github.com/XPRAMT/Device-Volume-Sync<br>
1.7版可以自動啟動vol_sync.exe了，將它與主程式放在同目錄即可