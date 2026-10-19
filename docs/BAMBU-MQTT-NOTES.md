# Bambu Studio 指令與 MQTT 錯誤排查

核對版本：使用者提供的 Bambu Studio 02.08.02.61。未執行安裝檔，也未在實機重送控制指令。

## 官方原始碼確認

[DeviceManager.cpp（此版本）](https://github.com/bambulab/BambuStudio/blob/v02.08.02.61/src/slic3r/GUI/DeviceManager.cpp)

| 操作 | print.command | 其他欄位 | 定義 |
| --- | --- | --- | --- |
| 暫停 | pause | param 為空字串、sequence_id | command_task_pause |
| 繼續 | resume | param 為空字串、sequence_id；先檢查恢復條件 | command_task_resume |
| 終止 | stop | param 為空字串、sequence_id | command_task_abort |
| 跳過物件 | skip_objects | obj_list、sequence_id | command_task_partskip |

這些指令交給 publish_json，依 LAN／雲端路徑呼叫 NetworkAgent。公開原始碼不是完整的私有網路外掛實作，不能把上表當作通過韌體授權檢查的保證。

Studio 回覆解析還會讀取 command 的 err_code，以及狀態中的 print_error、mc_print_error_code 和 HMS。MQTT 訊息送達不等於印表機接受或執行。

## 本機證據與限制

- Studio 本機官方 HMS 字典確認照片中的 0500050000010007 是「MQTT 命令校驗失敗」，建議更新 Studio（含網路外掛）或 Handy。
- 現有 Studio／網路日誌為 enc 加密格式，未解密，無法證明當次是哪個指令、哪個 sequence_id 造成錯誤。
- 84033543 等驗證回報碼的對照來自 [Open Bamboo Networking 的封包研究](https://github.com/ClusterM/open-bamboo-networking/blob/master/research/10.04-mqtt-signing.md)，尚未從此台印表機擷取到；程式會保留實際原始 err_code 供判讀。
- 目前 config.json 的印表機模組為 enabled=false；本次維持停用，不自動重新接上實機。

## 本次修正

- 預設只訂閱 report，不在連線／重連時送 pushall。
- 預設停用 pause／resume／stop／skip_objects，前後端皆檢查。
- 對齊三個基本控制指令的空白 param 欄位，但保留停用狀態。
- 解析 err_code，不再只看 result；驗證錯誤後鎖住後續控制。
- 支援印表機以 sequence_id=0 回覆目前指令的拒絕；不將其他指令當作目前操作的成功回覆。
- 命令回覆不覆蓋狀態；保留最近 30 筆錯誤摘要與 HMS／列印錯誤欄位，不保存帳號或存取碼。
- 沒有實作發起新列印，也不送清除警告、忽略 HMS、加熱或重新啟動指令。

## 驗證與後續

新增 7 項離線測試，包含連線零 publish、控制停用、只有 err_code 的拒絕、拒絕優先於狀態成功、異常 sequence_id、錯誤紀錄上限。連同既有歌詞測試共 19 項通過。

尚未驗證實機恢復正常列印，也未完成相容的授權控制通道。不能因為 JSON 欄位已補齊，就重新開啟控制按鈕。後續應先在維持被動監看的條件下觀察錯誤回報，再依印表機型號、韌體、LAN／雲端模式核對官方網路外掛支援。
