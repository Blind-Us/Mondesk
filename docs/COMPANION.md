# Mondesk Companion

一個住在小螢幕上、有臉的 AI 夥伴。它會看 Mondesk 的即時資料（列印機、正在播放、AI 用量、時間），在發生事件時用一兩句繁體中文提醒你，並切換表情。

## 運作方式

```
Mondesk 各模組的資料 ──► companion_events（每秒比對前後兩次快照）
                              │ 事件：列印完成／失敗、額度偏高、換歌、工作過久、點臉
                              ▼
                      冷卻時間、換歌機率、每小時上限
                              │
                              ▼
            companion_brain：大腦用 Tool Use 查資料，回傳固定格式
            get_printer_status / get_now_playing / get_ai_quota
            → {"line": "印好了！記得等熱床降溫再拿。", "emotion": "happy"}
                              │
                              ▼
            web/companion.js：先換表情 → 打字機顯示台詞，同時交替張嘴／閉嘴 → 停在該表情
```

- **大腦**（設定頁可切換）
  - Claude（Anthropic Messages API）：預設 `claude-opus-5-5`，effort `low`；換歌、點臉這類頻繁小事件可另選 `claude-haiku-5-5`。
    結構化輸出（`output_config.format` JSON Schema）把回應固定成 `{line, emotion}`；Tool Use 迴圈最多 5 輪。
    Opus 5.5 開啟伺服器端 refusal fallback（`fallbacks: "default"`），被安全分類器拒絕時 API 會在同一次呼叫內改用備援模型。
  - Ollama：本機模型（預設 `qwen3:8b`），用同一組工具與 JSON Schema，方便比較。
  - 規則式：固定句型填入工具查到的資料，不呼叫 AI、不花錢。API 失敗、被拒絕或超過每小時上限時也由它接手，角色不會沉默；氣泡下方會標示原因。
- **只根據資料發言**：系統提示要求只說工具查得到的事；工具回傳的是 Mondesk 已經有的資料，沒有就明說沒有。
- **表情**：模型只能在 `neutral、happy、thinking、worried、surprised、sleepy` 六種裡選一個。`talk_open／talk_closed` 兩張是說話動畫用的嘴型，由面板自動切換，不讓模型選。

## 觸發事件

| 事件 | 條件 | 冷卻 | 常見表情 |
|---|---|---|---|
| 列印完成 | 列印中／準備中／暫停 → 已完成 | 1 分鐘 | happy |
| 列印失敗或停止 | 列印中 → 失敗或待機（被停止），或因錯誤暫停 | 2 分鐘 | worried |
| AI 額度偏高 | 任一 5 小時／7 天額度 ≥ 門檻（預設 80%）；降到門檻 −5% 以下才會再提醒 | 30 分鐘 | worried |
| 換歌 | 播放中換了曲目；只有一部分歌會聊（預設機率 40%） | 30 分鐘 | happy／neutral |
| 計時結束 | 時鐘卡片的倒數計時歸零（由面板回報） | 5 秒 | surprised |
| 快下雨了 | 天氣預報接下來 3 小時內降雨機率 ≥ 60%（從「不會下」變成「會下」時） | 3 小時 | worried |
| 連續工作過久 | 鍵盤滑鼠持續有輸入（Windows）或 Codex／Claude 持續有活動，超過設定分鐘數；中斷 10 分鐘以上算休息 | 60 分鐘 | sleepy |
| 點一下臉 | 使用者點擊 | 6 秒 | 視狀況 |

- 啟動 Mondesk（或在設定頁按「套用」，模組會重新啟動）時，第一次看到的狀態只當作基準，不會補報一小時前就印好的東西。
- 同時有多個事件時，依「點臉 > 列印失敗 > 列印完成 > 額度 > 工作過久 > 換歌」挑一個說；排隊超過 3 分鐘的事件會丟掉。
- 冷卻時間可以在 config.json 的 `cooldowns` 覆寫（單位：秒），例如 `"cooldowns": {"song_change": 600}`。

## 花費控制

1. 每個事件的冷卻時間，換歌另有機率。
2. 每小時最多呼叫 AI 幾次（預設 20）。超過時由規則式台詞代替。這個計數記在紀錄檔裡，按「套用」重啟模組也不會歸零。
3. 每個事件最多 5 輪工具呼叫。
4. 小事件可以用便宜的模型（Haiku 5.5 的單價約為 Opus 5.5 的 1/40）。
5. 設定頁的「測試事件」按鈕一樣算在每小時上限內。

## 角色（臉）

角色可以換，格式見 [CHARACTER-FORMAT.md](CHARACTER-FORMAT.md)。內建兩個：

- **Emoji**（預設）：超大表情符號，不需要任何圖片，說話時彈跳。
- **耳機小子**：8 張 SVG 圖，含張嘴／閉嘴兩張；由 `tools/make_kid_faces.py` 產生（所有表情共用同一顆頭，只換五官）。做自己的圖片角色時可以「匯出目前角色」當範本。
- **Codex 寵物**：裝在 `~/.codex/pets` 的寵物會自動出現；也可以匯入寵物的 zip。表情會對應到寵物的動畫列（見 CHARACTER-FORMAT.md）。

自己生成的表情圖：照 CHARACTER-FORMAT.md 放成一個資料夾（或壓成 zip 從設定頁匯入）。面板約 5 秒內會換上新圖，不用重開。

### 生成流程（對應專案規格第四節）

1. **基準圖**：用文字提示決定髮型、配色、畫風，挑一張當角色定稿，記下種子與所有參數。
   ```
   chibi cartoon character, head and shoulders, front view, centered, looking at viewer,
   short dark navy hair, wearing over-ear headphones, big round eyes, soft blush,
   flat colors, clean thick outlines, sticker style, plain light gray background, no text
   ```
   負向提示（Stable Diffusion）：`photo, realistic, 3d, multiple characters, hands, text, watermark, cropped head, side view`
2. **其他表情**：固定種子，把基準圖當參考（img2img 去噪強度約 0.35–0.5，或 IP-Adapter 權重約 0.6–0.8），只改表情描述：

   | 檔名 | 加在提示詞後面 |
   |---|---|
   | neutral | calm relaxed expression, small closed-mouth smile |
   | happy | very happy, big open smile, eyes closed in joy |
   | thinking | thinking, eyes looking up to the side, one eyebrow raised, mouth pursed |
   | worried | worried, eyebrows raised in the middle, small frown, sweat drop |
   | surprised | surprised, wide open eyes, small round open mouth |
   | sleepy | sleepy, half-closed eyes, small yawn |

3. **說話兩張**：不要整張重生。用 `neutral` 做 **inpainting，只遮住嘴巴**，生成張嘴版（`talk_open`）與閉嘴版（`talk_closed`）。這樣兩張除了嘴巴完全一樣，交替播放時臉才不會抖動。
4. **一致性不夠時**：用基準圖的多張變化（不同表情、輕微角度）訓練小型 LoRA，再重跑第 2 步。
5. **後製**：去背、置中、裁成正方形、縮到 512×512，存成 PNG，再寫一個 `character.json` 打包成角色包。

### 一致性評估紀錄（範本）

每種作法各生成一批，人工判斷「是不是同一個角色」（髮型、配色、臉型、畫風都要對）：

| 作法 | 生成張數 | 判定為同一角色 | 成功率 | 主要問題 |
|---|---|---|---|---|
| 只固定種子 |  |  |  |  |
| 固定種子＋參考圖（img2img／IP-Adapter） |  |  |  |  |
| LoRA |  |  |  |  |

## 模型比較（速度、台詞品質、花費）

兩種資料來源：

- **控制實驗**：所有大腦看到完全相同的假資料（和「測試事件」按鈕同一組）。
  ```bash
  python tools/companion_bench.py --brains claude-opus-5-5,claude-haiku-5-5,ollama:qwen3:8b,rule --runs 3
  ```
  會呼叫 API、會花錢。結果寫入 `companion-bench.csv`，最後三欄（台詞品質 1–5、表情是否合適、是否像同一個角色的語氣）留給你評分。
- **實際使用紀錄**：每句台詞都記在 `companion-log.jsonl`（使用者設定資料夾），包含事件、大腦、延遲、tokens、用了哪些工具、是否改用規則式。
  ```bash
  python tools/companion_report.py --days 7 --real --csv lines.csv
  ```
  費用依 `tools/companion_report.py` 裡的 `PRICES` 估算（思考 tokens 算在輸出 tokens 裡）。

## 程式位置

| 檔案 | 內容 |
|---|---|
| `modules/companion.py` | 模組本體：每秒輪詢、事件排隊、背景執行緒、表情圖、紀錄檔 |
| `modules/companion_events.py` | 事件偵測、連續工作時間、冷卻與每小時上限 |
| `modules/companion_brain.py` | 系統提示、工具、Claude／Ollama／規則式三種大腦、測試用假資料 |
| `modules/companion_characters.py` | 角色包：讀取、驗證、匯入、匯出、刪除 |
| `web/companion.js` | 卡片：表情切換、打字機、嘴型動畫或彈跳、點臉 |
| `web/companion/<id>/` | 內建角色包（emoji、kid） |
| `tools/companion_bench.py`、`tools/companion_report.py` | 模型比較與紀錄統計 |
| `tests/test_companion.py`、`tests/test_companion_characters.py`、`tests/test-companion.cjs` | 測試 |
