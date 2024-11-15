### 功能
可以將輸入的任何聲道映射到輸出裝置的任何聲道<br>
簡單的說就是可以用多個藍牙音響組家庭劇院<br>
![img](https://i.imgur.com/SwIU751.jpeg)
<br>
### 安裝
[Download](https://github.com/XPRAMT/audio-channel-mapping/releases)<br>
or<br>
```
git clone https://github.com/XPRAMT/audio-channel-mapping.git
```
```
pip install -r requirements.txt
```
python>=3.10

### 使用:
GUI.pyw<br>

### 提示:
可以在config.json調整允許延遲(ms),系統會從設定值開始嘗試,直到不會卡頓<br>
```
[["Settings"], [20], [1]]   # [允許延遲20ms],[自啟動音量同步 0 or 1]
```
