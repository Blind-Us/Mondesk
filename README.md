<p align="center"><img src="assets/mondesk.png" width="128" alt="Mondesk"></p>

# Mondesk

**中文** ｜ [English](README.en.md)

每個禮拜一坐回桌前，旁邊那塊小螢幕幫你盯著其他事。

## 下載

到 [Releases](../../releases) 下載，解壓縮後點兩下就能用，不用安裝 Python，也不用打任何指令。

| 系統 | 檔案 | 開啟 |
|---|---|---|
| Windows 10／11 | `Mondesk-windows.zip` | `Mondesk.exe`。想先看看長什麼樣子，點 `Mondesk 示範模式.bat` |
| Linux | `Mondesk-linux.tar.gz` | `./Mondesk`（面板開在瀏覽器裡）。示範：`./mondesk-demo.sh` |

- 示範模式全部是腳本產生的資料，不需要列印機、帳號或金鑰，也不會存檔。
- 開機自動啟動、全螢幕：設定頁的「應用程式」。視窗會開在上次關閉時的螢幕、位置和大小。
- 再點一次 `Mondesk.exe` 不會開第二個，只會把原本的視窗叫到前面。
- Apple Music 歌詞、YouTube／B 站影片同步需要瀏覽器擴充功能。擴充功能已經包在裡面，設定頁「正在播放」有一步一步的安裝說明（Chrome 不允許程式自動安裝，要手動載入一次）。
- Windows 第一次開啟可能顯示「Windows 已保護您的電腦」：這個程式沒有購買簽章，按「其他資訊」→「仍要執行」。開著「智慧型應用程式控制」的電腦不允許任何沒有簽章的程式，請改用下面的原始碼版（`Mondesk.bat`）。
- Linux 版的系統音量卡片和「系統正在播放」需要 Windows；其他功能相同。

## 這是什麼

放在桌上小螢幕的監看面板：3D 列印機、正在播放的音樂（含同步歌詞）、Codex／Claude 用量，以及一個會看這些資料、主動跟你說話的 Companion 角色。
Windows 與 Linux 都可使用，所有設定都在本機網頁完成。

| 卡片 | 內容 |
|---|---|
| 3D 列印機（Bambu Lab） | 進度、剩餘時間、溫度、模型預覽、機艙直播、一鍵開啟 Bambu Studio |
| 正在播放 | 封面、剩餘時間、播放控制；點卡片：Apple Music 顯示全螢幕同步歌詞，YouTube、B 站的影片由面板自己靜音同步播放（原分頁照常播放、可以蓋住），其他網站才擷取分頁畫面 |
| AI 用量 | 今日 tokens、5 小時／7 天額度 % |
| Companion | 有臉的 AI 夥伴：列印完成／失敗、額度偏高、換歌、工作太久時用一兩句話提醒你並切換表情；點臉回報目前狀況。角色可換、可匯入別人做的角色包（見 [docs/COMPANION.md](docs/COMPANION.md)、[docs/CHARACTER-FORMAT.md](docs/CHARACTER-FORMAT.md)） |
| 系統控制 | 音量（含靜音）、支援 DDC/CI 的螢幕亮度，以及小螢幕本身的「面板」調暗 |
| 天氣 | 氣溫、天氣狀況、今天高低溫與降雨機率、接下來幾小時；快下雨時會提醒（資料來自 Open-Meteo，不用帳號） |
| 時鐘 | 數字、指針、翻頁、圓環、文字五種樣式，任何大小都看得清楚；點卡片開全螢幕，裡面有計時器和碼錶兩頁，用滾輪設定倒數、開始和重設，時間到螢幕四邊會發光。放上時鐘後，右上角的小時間會隱藏 |

版面可以自己調：碰一下螢幕，點左上角的鉛筆，就能直接拖曳卡片、拖右下角改大小（6×8 格）；按 ✕ 收進「小工具」抽屜，用不到的就不用放。每張卡右上角的小齒輪只開那張卡的設定，左上角齒輪只有螢幕和顏色。預設是左上列印機、右上正在播放、左下 AI 用量（多個訂閱可左右滑動或滾輪切換）、右下 Companion。

**情境模式**：碰一下螢幕，左上角的模式按鈕可在「自訂／專注／列印／休息」之間切換整個版面；也可以設定開始列印時自動切到「列印」。模式開著時按鉛筆，改的是那個模式自己的版面。版面可以匯出成「版面包」分享（只含版面、模式與顏色，不含任何帳號或金鑰），設定頁內建專注、媒體、列印三個範本。

**事件**：列印完成／失敗、額度偏高、快下雨、計時結束、工作太久都只記錄一次。Companion 在畫面上時由角色說；沒有角色時面板下方會跳出提示；設定頁的「事件紀錄」看得到全部。

## 先試試看（不用任何帳號或設備）

```bash
run-demo.bat        # Windows；Linux 用 ./run-demo.sh
```

示範模式用腳本產生列印機、音樂（含歌詞）、AI 額度和天氣的資料，大約四分鐘一輪：列印完成、第二次列印失敗、額度超過 80%、換歌、快下雨。角色、事件紀錄、情境模式、版面編輯都是真的在運作。不會讀寫你的設定。

## 檢查這份程式是否正常

```bash
check.bat           # Windows；Linux 用 ./check.sh
```

會檢查套件、跑完 Python 與 JavaScript 測試（沒裝 Node.js 會略過 JavaScript），再啟動一次示範伺服器確認頁面和 API。不需要帳號、列印機或金鑰。

## 安裝與啟動

需要 Python 3.10 以上。

```bash
# Windows
run.bat

# Linux
./run.sh
```

第一次啟動會建立虛擬環境、安裝套件，並以 `config.example.json` 建立使用者設定；程式目錄不保存正式使用者設定。

獨立視窗（不是瀏覽器分頁）：Windows 點 `Mondesk.bat`，Linux 用 `./run-desktop.sh`。Windows 使用 `%LOCALAPPDATA%/DeskMon/config.json`，Linux 使用 `$XDG_CONFIG_HOME/DeskMon/config.json`（未設定時為 `~/.config/DeskMon/config.json`）。伺服器與 desktop 共用此設定路徑；開發可用 `--config` 明確指定其他檔案。

下載用的應用程式由 `python tools/build_app.py` 產生（需要 `pip install -r requirements-desktop.txt -r requirements-build.txt`），它只能做出執行它的那個系統的版本；推一個 `v` 開頭的標籤，[.github/workflows/release.yml](.github/workflows/release.yml) 會在 GitHub 上把 Windows 和 Linux 兩個版本都做出來並掛到 Releases。圖示由 `python tools/make_icons.py` 畫出。應用程式在使用者設定旁產生 `browser-extension/`，配對網址使用實際桌面服務連接埠。Chrome 從這個資料夾載入「Mondesk — Now Playing」。

- 面板：<http://127.0.0.1:9361>
- 設定：<http://127.0.0.1:9361/settings.html>（或點面板左上角的齒輪）

Linux 額外需要：`playerctl`（正在播放）、`xrandr`（解析度清單）。

## 設定與帳號

**所有憑證由你在設定頁輸入，設定來源只有本機 user config**。瀏覽器連接器的必要配對資料由該設定產生在同一個使用者目錄，不會放進發佈包。
設定頁讀取設定時，存取碼等機密欄位只會顯示 `••••••`，原值不會離開伺服器。

| 功能 | 需要什麼 | 預設 |
|---|---|---|
| Bambu 列印機 | 印表機 IP、序號、LAN 存取碼（印表機螢幕上可查） | 關閉 |
| Claude 官方 % | 在這台電腦用 `claude` 指令登入過 Claude Code | 關閉，需自行開啟 |
| Companion（Claude） | Anthropic API 金鑰（設定頁輸入，或環境變數 `ANTHROPIC_API_KEY`）；也可改用本機 Ollama 或不花錢的規則式台詞 | 關閉 |
| Apple Music 同步歌詞 | 執行 `python -m modules.apple_bridge` 配對，並在 Chrome 載入 `apple-music-extension`（歌詞只來自 Apple Music） | 關閉 |

## 會連到哪些外部服務

Mondesk 只綁定 `127.0.0.1`。以下是它會主動連線的地方，非預設的都要在設定頁自行開啟：

| 服務 | 用途 | 送出的資料 | 預設 |
|---|---|---|---|
| 你的印表機（區網） | 讀取狀態、預覽圖、直播 | 無（只接收） | 設定後啟用 |
| iTunes Search API | 封面、歌曲長度 | 歌名、歌手 | 開啟 |
| Anthropic | Claude 官方用量 % | 你的 Claude Code 登入權杖 | 關閉 |
| Anthropic Messages API | Companion 產生台詞（選 Claude 大腦時） | 事件名稱、時間、連續工作時間，以及模型查詢的列印狀態、歌名、AI 用量 | 關閉 |
| Ollama（本機） | Companion 本機模型（選 Ollama 大腦時） | 同上，只送到你的電腦 | 關閉 |
| Open-Meteo；連不上時改用挪威氣象局（api.met.no） | 天氣預報、設定頁的地名搜尋 | 你選的地點的經緯度；搜尋時送出你輸入的地名 | 關閉（放上天氣卡並選地點後啟用） |

注意：Claude 官方用量、Apple Music 擴充功能、Bambu Studio 直播工具都**不是官方公開的介面**，對方改版時可能失效，使用前請自行確認是否符合各服務條款。

## 安全性

- 伺服器只接受來自本機（`127.0.0.1`／`localhost`）且來自 Mondesk 自己頁面的請求；
  所有寫入類 API 需要 `X-DeskMon` 標頭，其他網站無法替你送出設定或操作。
- 「開啟 Bambu Studio」只會啟動名為 `bambu-studio` 的程式。
- 列印機預設**只監看**。Bambu 新版韌體在雲端模式會拒絕非官方軟體的控制指令（錯誤 84033543），請用 Bambu Studio／Handy 操作。

## 機艙直播

優先使用 Bambu Studio 的攝影機直播工具（`bambu_source`，雲端模式可用，不需要 LAN Only Liveview）；
沒有在執行時，改用印表機的 LAN 直播（需在印表機開啟 LAN Only Liveview）。

## 開發

```bash
python tools/check.py                        # 套件、全部測試、示範伺服器（同 check.bat）
python -m unittest discover -s tests -t .    # 只跑 Python 測試
node --test tests/*.cjs                      # 只跑 JavaScript 測試（需要 Node.js 18 以上）
python tools/companion_eval.py               # Companion 固定事件集與一天的說話次數
```

- 新增資料來源：照 [docs/MODULES.md](docs/MODULES.md) 的契約，`modules/weather.py` 是範例。
- 影片顯示的三條路徑與釋放時機：[docs/VIDEO.md](docs/VIDEO.md)。
- 卡片在不同大小顯示什麼、最小幾格：[docs/LAYOUT.md](docs/LAYOUT.md)。
- 主題（背景、外型、主題色、卡片各自的顏色、情境與夜間、跟著封面）：[docs/THEME.md](docs/THEME.md)。
- 實機驗收步驟：[docs/ACCEPTANCE.md](docs/ACCEPTANCE.md)；現況與待辦：[docs/ROADMAP.md](docs/ROADMAP.md)。

## 授權

[MIT](LICENSE)
