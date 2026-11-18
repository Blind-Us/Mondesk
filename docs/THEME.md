# 主題

面板上所有顏色都來自主題，樣式檔裡沒有寫死的顏色（`tests/test-modes-packs.cjs` 有一項測試在守這件事）。定義在 `web/layout.js` 的「theme」區塊，設定存在 `config.json` 的 `theme`。

```json
"theme": {
  "background": "graphite",
  "shape": "round",
  "accent": "#f2a541",
  "cards": { "media": "#7ee0b5", "codex": ["#4f7dff", "#c46bff"] },
  "modes": { "focus": "#7cc4ff" },
  "night": { "on": true, "from": 22, "to": 7, "background": "oled" },
  "cover": "card",
  "style": "glass",
  "motion": "bouncy"
}
```

| 欄位 | 意義 |
|---|---|
| `background` | 內建名稱（`graphite` 石墨、`oled` 純黑、`navy` 深海藍、`warm` 暖木、`paper` 紙白、`mist` 霧藍）或任何 `#rrggbb`。自訂顏色時卡片底色和線條自動算出；背景夠亮就自動改用深色文字 |
| `shape` | 卡片外型：`round` 圓角、`soft` 方角、`cut` 切角 |
| `accent` | 主題色，套用到所有卡片 |
| `cards` | 有自己顏色的卡片。`bambu`、`media`、`weather`、`companion` 一個顏色；`codex`、`claude` 兩個顏色，是漸層的左端和右端。沒列出的卡片跟主題色。在每張卡片自己的設定頁調整 |
| `modes` | 情境模式（`focus`、`print`、`rest`）開著時改用的主題色 |
| `night` | `from` 點到 `to` 點之間換成另一個背景 |
| `cover` | 跟著專輯封面：`""` 不跟、`card` 只有「正在播放」卡片、`theme` 整個主題色 |
| `style` | 風格：`flat` 預設、`glass` 毛玻璃（iOS 風：半透明卡片，模糊後面的彩色光暈）、`material` Material（Android 風：實色色調表面、沒有外框、大圓角、按下有水波） |
| `image` | 背景圖片：`{"v": 版本, "dim": 0–90, "blur": 0–40}`。圖片在設定頁上傳（PNG、JPEG、WebP、GIF，最大 8 MB），存在使用者資料夾的 `background.img`，不在程式資料夾，也不會放進版面包。`dim` 是蓋在圖上的背景色濃度（%），`blur` 是模糊（px），用來讓卡片上的字看得清楚。毛玻璃風格的卡片會模糊這張圖 |
| `motion` | 動畫：`bouncy` Q 彈（預設，按下微微下沉、放開回彈一次就停；曲線是照阻尼彈簧的物理算出來的，約 10% 過衝）、`calm` 平順不回彈、`off` 關閉。系統設定「減少動態效果」時一律關閉 |

## 怎麼決定畫面上的顏色

`DeskMonLayout.resolveTheme(theme, {mode, hour, cover})` 是唯一的入口，面板和設定頁都用它：

1. 背景：夜間時段用 `night.background`，否則用 `background`。由背景得到文字、線條、狀態色（深色和淺色各一組）。
2. 主題色：封面顏色（`cover: "theme"`）優先，其次是目前情境模式的顏色，最後是 `accent`。
3. 每張卡片：有自己的顏色就用自己的，否則用主題色。漸層卡片跟主題色時，右端是主題色的淺一階。
4. 淺色背景上太淡的顏色會保留色相、自動加深，存檔的值不變。
5. 封面顏色取圖片中有彩度的像素平均，再調到讀得清楚的明度。圖片來自不允許讀取的網站時維持主題色。

紅色的錯誤、綠色的正常、警示色屬於狀態色，不跟主題色走。歌詞／影片頁永遠是深色（底下是調暗的封面或影片）。

## 舊設定檔

沒有 `accent` 的舊設定（`printer`、`music`、`codex`、`claude`）會被讀成「每張卡片都有自己的顏色」，畫面顏色不變。在設定頁按「全部跟隨主題色」才會變成單色；儲存後改寫成新格式。

## 加新顏色

不要在 CSS 或 JavaScript 寫色碼。需要新顏色時：能從現有變數混出來就用 `color-mix()`（例如 `color-mix(in srgb, var(--on) 8%, transparent)`）；真的是新的語意，就在 `layout.js` 的 `INK` 深淺兩組各加一個值，並在 `style.css` 第一個 `:root` 加同名的預設值、`app.js` 的 `applyTheme()` 加進清單。

| 變數 | 用途 |
|---|---|
| `--bg` `--card` `--line` | 背景、卡片、線條 |
| `--text` `--soft` `--dim` `--faint` | 文字四階 |
| `--on` | 疊加層和細線的基色：深色主題是白、淺色主題是黑 |
| `--theme` | 主題色；卡片內用 `--c`（自己的顏色或主題色） |
| `--ok` `--idle` `--err` `--warn` | 狀態色 |
| `--fill` `--fill-2` `--ink` | 軌道與按鈕底色、主題色塊上的文字 |
| `--black` `--white` `--stage*` | 陰影與遮罩、影片底色、歌詞頁 |
