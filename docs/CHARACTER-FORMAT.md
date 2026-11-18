# Mondesk 角色包格式（deskmon-character/1）

Mondesk Companion 的臉可以換。一個角色包就是一個資料夾（分享時壓成 .zip），裡面有一個 `character.json`，表情可以用圖片，也可以直接用 emoji。

## 最簡單：只用 emoji（一個檔案就夠）

```json
{
  "format": "deskmon-character/1",
  "name": "貓貓",
  "author": "你的名字",
  "faces": {
    "neutral": "🐱",
    "happy": "😸",
    "thinking": "🤔",
    "worried": "😿",
    "surprised": "🙀",
    "sleepy": "😴"
  }
}
```

存成 `character.json`，點 Agent 卡片右上角的小齒輪 →「匯入角色…」選這個檔案就好。沒有說話嘴型時，角色說話會上下彈跳。

## 用圖片

```
sunny/
├── character.json
├── neutral.png
├── happy.png
├── thinking.png
├── worried.png
├── surprised.png
├── sleepy.png
├── talk_open.png
└── talk_closed.png
```

```json
{
  "format": "deskmon-character/1",
  "id": "sunny",
  "name": "Sunny",
  "author": "you",
  "description": "戴耳機的小太陽",
  "persona": "開朗、愛吐槽，講話很短。",
  "faces": {
    "neutral": "neutral.png",
    "happy": "happy.png",
    "thinking": "thinking.png",
    "worried": "worried.png",
    "surprised": "surprised.png",
    "sleepy": "sleepy.png",
    "talk_open": "talk_open.png",
    "talk_closed": "talk_closed.png"
  }
}
```

把整個 `sunny` 資料夾壓成 `sunny.zip` 就能分享；別人用「匯入角色…」選這個 zip 即可。圖片和 emoji 可以混用。

## 直接用 Codex 寵物（pet）

Codex 的寵物包（`pet.json` ＋ `spritesheet.webp`，8 欄 × 9 列、每格 192×208 的動畫圖）可以直接當 Agent 的臉，不用另外畫：

- **已經裝在 Codex 裡的寵物**（`~/.codex/pets/<id>/`，Windows 是 `%USERPROFILE%\.codex\pets`）會自動出現在角色清單，標示「Codex 寵物」，id 是 `codex-<id>`。Mondesk 只讀取，不會修改或刪除 Codex 的檔案。
- **別人分享的寵物**：把整個寵物資料夾（含 `pet.json` 和精靈圖）壓成 zip，用「匯入角色…」選它。

表情對應到寵物的動畫列：

| Mondesk 表情 | 寵物動畫（列） |
|---|---|
| neutral | idle（0） |
| happy | jumping（4） |
| surprised | waving（3） |
| thinking | review（8） |
| worried | failed（5） |
| sleepy | waiting（6） |
| 說話中 | running（7） |

精靈圖若列數不同（例如 11 列的新版），會依圖片高度自動算出列數。

自己的角色也能用精靈圖做動畫，在 `character.json` 加上 `sprite`（可以和 `faces` 混用，同名時以動畫為準）：

```json
"sprite": {
  "sheet": "sheet.png",
  "columns": 8,
  "cell": [192, 208],
  "faces": { "neutral": [0, 6], "happy": [4, 5], "talk_open": [7, 6], "talk_closed": [7, 6] }
}
```

`faces` 每一項是 `[列（從 0 起算）, 這一列有幾張]`，每秒播 8 張；精靈圖最大 8 MB，不能是 SVG。

## 欄位

| 欄位 | 必填 | 說明 |
|---|---|---|
| `format` | 建議 | 固定為 `deskmon-character/1` |
| `name` | 是 | 顯示名稱，1–40 字；也會出現在 AI 的系統提示（「你是『Sunny』…」） |
| `faces` | 是 | 表情對照表，至少要有 `neutral` |
| `id` | 否 | 英文小寫、數字、`-`、`_`，最多 40 字；沒有就由名稱產生。跟內建角色同名會自動加上 `-custom` |
| `author` | 否 | 作者，最多 60 字 |
| `description` | 否 | 簡介，最多 120 字 |
| `persona` | 否 | 角色個性，最多 300 字。只影響語氣和用詞；「只根據資料發言、一兩句話、繁體中文」這些規則不會被它改變 |

### 表情名稱

| 名稱 | 什麼時候用 |
|---|---|
| `neutral` | 平常（必填；缺少的表情都會用它代替） |
| `happy` | 好消息、列印完成 |
| `thinking` | 等 AI 回應、資訊不完整 |
| `worried` | 列印失敗、額度快滿 |
| `surprised` | 意外的變化 |
| `sleepy` | 工作太久、很晚了 |
| `talk_open`、`talk_closed` | 說話時交替顯示（張嘴／閉嘴）。兩張都有才會用；建議只改嘴巴，其餘完全一樣 |

### 每個表情的值

- **圖片**：同一個資料夾裡的檔名，副檔名 `.png`、`.webp`、`.gif`（可動畫）、`.jpg`、`.svg`。檔名只能用英數字和 `.-_`，不能有子資料夾。建議正方形 512×512、去背。
- **文字**：最多 12 個字元，通常是一個 emoji，會放大顯示。

## 限制與安全

- 匯入的檔案最大 10 MB；單張圖片最大 4 MB；解壓後全部最多 24 MB。
- 只會取出 `character.json` 和它用到的圖片，其他檔案、子資料夾和路徑一律忽略。
- 圖片會檢查檔頭是否真的是圖片；SVG 以沙箱方式提供，裡面的程式碼不會執行。
- 匯入的角色存放在使用者設定資料夾的 `characters/<id>/`（Windows：`%LOCALAPPDATA%\DeskMon\characters`）。也可以直接把資料夾放進去；沒有 `character.json` 但有 `neutral.png` 等圖片的資料夾也能用。
- Agent 設定裡的「匯出」會產生同樣格式的 zip，內建角色也能匯出當範本。
