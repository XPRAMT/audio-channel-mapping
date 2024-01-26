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
run.bat<br>

注意事項:<br>
如果遇到聲音卡頓問題在config.json嘗試調整幀長度和允許延遲<br>
允許延遲過低會破音(因為不斷清空處理隊列，根據電腦性能調整)<br>
```
[["CHUNK"], [320]]      # 每幀長度(Hz)
[["AllowDelay"], [6]]   # 允許延遲(幀)
```
