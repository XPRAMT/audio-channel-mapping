# Audio Controller 通訊協議規範 (v2.0)

本文件定義了 Android 客戶端與 PC 伺服器端之間的通訊協議及其交互邏輯。

## 架構概述

| 通道 | 協議 | 方向 | 用途 |
| :--- | :--- | :--- | :--- |
| 控制通道 | TCP | 雙向 | JSON 指令與狀態同步 |
| 音頻通道 | UDP | Server → Client | PCM 音頻串流 |

- **TCP 端口**：可設定（預設 `25505`）
- **UDP 端口**：TCP 端口 + 1（預設 `25506`）

---

## 1. TCP 控制通道

### 1.1 封包格式
所有 TCP 訊息均採用 **長度前綴 + JSON** 格式：
- **Length** (2 bytes, Big Endian): JSON 字串的 UTF-8 位元組長度
- **Payload** (N bytes): UTF-8 編碼的 JSON 字串

> 與 Android `writeUTF` 的格式相容。

---

### 1.2 Server → Client 狀態推送

當伺服端狀態改變時（音量、播放/暫停、串流啟停），**主動推送** JSON：

```json
{
  "type": "state",
  "sampleRate": 48000,
  "blockSize": 480,
  "channels": 2,
  "volume": 0.5,
  "startStop": true,
  "isPlaying": true
}
```

| 欄位 | 類型 | 說明 |
| :--- | :--- | :--- |
| type | string | 固定為 `"state"` |
| sampleRate | int | 音訊採樣率 (Hz) |
| blockSize | int | 每個音訊塊的幀數 |
| channels | int | 輸入聲道數 |
| volume | float | 目前伺服器音量 (0.0 ~ 1.0) |
| startStop | bool | 串流狀態 (true: 運行, false: 停止) |
| isPlaying | bool | 媒體播放狀態 (true: 播放中, false: 暫停) |

> 當僅音量變更時，`type` 可為 `"volume"`，僅含 `volume` 欄位以減少傳輸量。

---

### 1.3 Client → Server 指令

所有指令均為 UTF-8 編碼的 JSON 字串（透過 `writeUTF` 發送）。

#### 1.3.1 初始交握 (Handshake)
連線建立後，Client **必須**立即發送：

```json
{
  "maxVol": 150,
  "volume": 0.5,
  "name": "Phone Model",
  "udpPort": 25506
}
```

| 欄位 | 類型 | 說明 |
| :--- | :--- | :--- |
| maxVol | int | 手機最大音量階數 |
| volume | float | 目前音量 (0.0 ~ 1.0) |
| name | string | 裝置顯示名稱 |
| udpPort | int | Client 的 UDP 接收端口 |

#### 1.3.2 音量同步
`{"volume": 0.5}`

#### 1.3.3 串流控制
`{"startStop": " "}`

#### 1.3.4 媒體鍵
- 上一曲：`{"mediaKey": "previous track"}`
- 播放/暫停：`{"mediaKey": "play/pause"}`
- 下一曲：`{"mediaKey": "next track"}`

---

## 2. UDP 音頻通道

### 2.1 端口規則
- Server **發送**端口：TCP 端口 + 1
- Client **接收**端口：由交握中的 `udpPort` 指定

### 2.2 UDP 封包格式

| 偏移量 | 欄位 | 類型 | 說明 |
| :--- | :--- | :--- | :--- |
| 0 | Sequence | uint32 BE | 封包序號，從 0 開始遞增，溢位歸零 |
| 4 | Timestamp | uint32 BE | 串流開始後的毫秒數 |
| 8 | Audio Data | float32[] | PCM 音頻數據 (interleaved) |

> 每個 UDP 封包對應一個音訊幀區塊（blockSize 幀 × channels 聲道）。

---

## 3. 交互邏輯

### 3.1 連線流程
1. Client 透過 mDNS 發現 Server
2. Client 建立 TCP 連線到 Server
3. Client 發送交握 JSON（含 `udpPort`）
4. Server 記錄 Client 資訊，開始監聽狀態變化
5. 音頻數據透過 UDP 發送到 `Client_IP:udpPort`

### 3.2 串流控制
1. Client 發送 `{"startStop": " "}`
2. Server 切換音訊擷取開關
3. Server 推送狀態 JSON（`startStop` 更新）
4. 若開始串流，Server 開始發送 UDP 音頻封包

### 3.3 媒體控制
1. Client 發送 `{"mediaKey": "..."}`
2. Server 調用系統 API 模擬按鍵
3. Server 偵測播放狀態變化後，推送狀態 JSON（`isPlaying` 更新）

---

v2.0 更新摘要：
- 音頻傳輸從 TCP 改為 UDP（端口 = TCP 端口 + 1）
- TCP 通道僅用於雙向 JSON 控制通訊
- 移除二進制 Header 結構，統一使用 JSON
- 交握新增 `udpPort` 欄位
