### feature
You can map any input channel to any output device channel.<br>
In simple terms, this means you can use multiple Bluetooth speakers to create a home theater.<br>
![img](https://i.imgur.com/SwIU751.jpeg)
<br>
### Install
[Download](https://github.com/XPRAMT/audio-channel-mapping/releases)<br>
or<br>
```
git clone https://github.com/XPRAMT/audio-channel-mapping.git
```
```
pip install -r requirements.txt
```
python>=3.10

### Usage:
GUI.pyw<br>

### Tips:
You can adjust the allowed delay (ms) in `config.json`. The system will start trying from the set value until it stops stuttering.
```
[["Settings"], [20], [1]]   # [Allow delay  20ms],[Auto-enable volume sync 0 or 1]
```
