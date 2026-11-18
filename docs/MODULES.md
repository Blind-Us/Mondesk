# 模組契約

一個資料來源就是 `modules/` 裡的一個檔案。新增來源不需要改核心：照這份契約寫，面板、事件中心、診斷頁、示範模式都會自動接上。`modules/weather.py` 是最小的完整範例。

## 後端

```python
from . import BaseModule

class Module(BaseModule):
    type = "weather"          # 和檔名相同；config.json 用 "type": "weather" 載入
    default_interval = 30     # 幾秒呼叫一次 poll()

    def start(self): ...      # 啟動一次：建立連線、初始化狀態（不要在 __init__ 連線）
    def poll(self): ...       # 回傳可轉成 JSON 的 dict
    def stop(self): ...       # 儲存設定時模組會被換掉：釋放連線、執行緒
    def action(self, name, **params): ...   # 選用：面板的按鈕
    def asset(self, name): ...              # 選用：(bytes, mime)，例如封面
    def stream_frame(self): ...             # 選用：(時間, JPEG) 給 /api/stream/<id>
```

`poll()` 的規則：

| 欄位 | 意義 |
|---|---|
| `_status` | `ok`（運作中）、`idle`（正常但沒事）、`offline`（連不上／還沒設定）。丟出例外會變成 `error`，模組不會死，下一輪再試 |
| `message` | `offline` 時給人看的一句話（繁體中文），面板的空狀態和診斷頁都會顯示 |
| 其他欄位 | 這張卡要畫的資料。欄位名稱一旦發佈就不要改意義，要改就加新欄位 |

- `self.spec` 是 config.json 裡這個模組的設定；`self.hub.module_states()` 可以讀其他模組的最新資料。
- 執行時要寫的檔案一律放 `user_paths.user_data_dir()`，不要寫在程式資料夾。
- 欄位名稱含 `access_code`、`pair_key`、`token`、`password`、`secret`、`api_key` 的設定會被當成機密：設定頁只看得到 `••••••`。
- 網路失敗時保留上一次的好資料並標示 `stale`，不要把卡片清空。

## 前端

1. `web/app.js`：在 `R` 加一個 `R.<type> = m => html`；沒資料時回傳 `emptyCard(m)`，並在 `emptyInfo()` 加上這個來源的說明。
2. `web/layout.js`：把 type 加進 `WIDGETS`。
3. `web/panel-edit.js`：在 `NAMES`、`ICONS`、`DEFAULTS` 各加一筆（從抽屜拖出來時用的預設設定）。
4. 需要設定頁：在 `web/settings.html` 加一個 `<section data-widget="<type>">`，欄位用 `data-k="<模組 id>.<欄位>"`；並把 type 加進 `app.js` 的 `CARD_SETTINGS`。

## 尺寸

新卡片要照 [LAYOUT.md](LAYOUT.md) 的規定：在 `web/layout.js` 的 `MIN` 加最小格數，並在 `web/style.css` 的「Card sizes」區塊用 `data-size`（xs／s／m／l）和 `data-orient`（wide／square／tall）寫出每一級顯示什麼。不要用像素門檻，尺寸用 `--u`，字級用 `--f1`、`--f2`、`--f3`，顏色用主題變數（[THEME.md](THEME.md)）。

## 事件

事件由 `modules/companion_events.py` 的 `EventDetector` 比對前後兩次資料產生，交給事件中心（`modules/event_center.py`）。要讓新來源產生事件：

1. 在 `EVENTS` 加名稱、標籤、優先順序，在 `DEFAULT_COOLDOWNS` 加冷卻秒數。
2. 在 `EventDetector.feed()` 加一段偵測。第一次看到的資料只當基準，不產生事件。
3. 在 `companion_brain.py`：`EVENT_HINTS` 加一句給模型的說明、`RuleBrain` 加 `_<事件名>` 固定句型；模型需要查資料時在 `TOOLS` 和 `World` 加一個工具。
4. `web/app.js` 的 `EVENT_TEXT` 加面板提示的文字；`companion.py` 的 `ADDED_TRIGGERS` 和 `web/settings.js` 的同名表各加一筆，舊設定檔才會預設開啟。
5. `tools/companion_eval.py` 的 `CASES` 加一個案例。

面板自己才知道的事（例如倒數計時）用 `POST /api/event`，名稱要先列在 `event_center.CLIENT_EVENTS`。

## 示範模式與測試

- `modules/demo.py`：在 `DEMO_TYPES` 和 `Module.poll()` 加這個來源的腳本資料，示範和 `check` 才看得到它。
- 解析邏輯寫成不碰網路的純函式（像 `weather.parse()`），用固定資料測試。
- `python tools/check.py` 要全部通過。
