# DeskMon

放在桌上小螢幕的監看面板：3D 列印機、正在播放的音樂（含同步歌詞）、Codex／Claude 用量。
Windows 與 Linux 都可使用，所有設定都在本機網頁完成。

| 卡片 | 內容 |
|---|---|
| 3D 列印機（Bambu Lab） | 進度、剩餘時間、溫度、模型預覽、機艙直播、一鍵開啟 Bambu Studio |
| 正在播放 | 封面、剩餘時間、播放控制、全螢幕同步歌詞 |
| AI 用量 | 今日 tokens、5 小時／7 天額度 % |

## 安裝與啟動

需要 Python 3.10 以上。

```bash
# Windows
run.bat

# Linux
./run.sh
```

第一次啟動會建立虛擬環境、安裝套件，並從 `config.example.json` 複製出 `config.json`。

- 面板：<http://127.0.0.1:9361>
- 設定：<http://127.0.0.1:9361/settings.html>（或點面板左上角的齒輪）

Linux 額外需要：`playerctl`（正在播放）、`xrandr`（解析度清單）。

## 設定與帳號

**所有憑證都由你自己在設定頁輸入，只存在本機的 `config.json`**（已列入 `.gitignore`，不會被提交）。
設定頁讀取設定時，存取碼等機密欄位只會顯示 `••••••`，原值不會離開伺服器。

| 功能 | 需要什麼 | 預設 |
|---|---|---|
| Bambu 列印機 | 印表機 IP、序號、LAN 存取碼（印表機螢幕上可查） | 關閉 |
| Claude 官方 % | 在這台電腦用 `claude` 指令登入過 Claude Code | 關閉，需自行開啟 |
| Apple Music 原生歌詞 | 執行 `python -m modules.apple_bridge` 配對，並在 Chrome 載入 `apple-music-extension` | 關閉 |

## 會連到哪些外部服務

DeskMon 只綁定 `127.0.0.1`。以下是它會主動連線的地方，非預設的都要在設定頁自行開啟：

| 服務 | 用途 | 送出的資料 | 預設 |
|---|---|---|---|
| 你的印表機（區網） | 讀取狀態、預覽圖、直播 | 無（只接收） | 設定後啟用 |
| LRCLIB | 同步歌詞 | 歌名、歌手 | 開啟 |
| iTunes Search API | 封面、歌曲長度 | 歌名、歌手 | 開啟 |
| 酷狗、網易雲 | 中文歌詞 | 歌名、歌手 | 關閉（非官方介面） |
| Anthropic | Claude 官方用量 % | 你的 Claude Code 登入權杖 | 關閉 |

注意：酷狗、網易雲、Claude 官方用量、Apple Music 擴充功能、Bambu Studio 直播工具都**不是官方公開的介面**，對方改版時可能失效，使用前請自行確認是否符合各服務條款。

## 安全性

- 伺服器只接受來自本機（`127.0.0.1`／`localhost`）且來自 DeskMon 自己頁面的請求；
  所有寫入類 API 需要 `X-DeskMon` 標頭，其他網站無法替你送出設定或操作。
- 「開啟 Bambu Studio」只會啟動名為 `bambu-studio` 的程式。
- 列印機預設**只監看**。Bambu 新版韌體在雲端模式會拒絕非官方軟體的控制指令（錯誤 84033543），請用 Bambu Studio／Handy 操作。

## 機艙直播

優先使用 Bambu Studio 的攝影機直播工具（`bambu_source`，雲端模式可用，不需要 LAN Only Liveview）；
沒有在執行時，改用印表機的 LAN 直播（需在印表機開啟 LAN Only Liveview）。

## 開發

```bash
python -m unittest discover -s tests -t .   # Python 測試
node tests/test-layout.cjs                  # 版面計算測試（需要 Node.js）
```

模組放在 `modules/`，每個模組實作 `start()`、`poll()`，可選 `action()`、`asset()`；
在 `config.json` 的 `modules` 加一筆 `"type": "<檔名>"` 就會載入。

## 授權

[MIT](LICENSE)
