# Apple Music 原生歌詞連接（Windows／Linux）

此擴充功能讀取 Apple Music 網頁的原生 TTML 歌詞；若尚未取得，會透過已登入頁面的 MusicKit API 查詢同一首歌的原生歌詞，並使用網頁播放器控制播放。Apple 沒有同步時間的歌曲，DeskMon 會改查外部同步歌詞（LRCLIB／酷狗／網易雲），並用 Apple Music 的實際播放進度對時。登入憑證留在 Apple 頁面，不會傳到 DeskMon。

## 首次設定

1. 在 DeskMon 專案資料夾執行 `python -m modules.apple_bridge`，產生本機配對檔。此命令不會連線 Apple，也不會讀取登入憑證。
2. 在 `config.json` 的 media 模組加入 `"apple_music_native": true`，然後重新啟動 DeskMon。
3. Chrome 開啟 `chrome://extensions/`，開啟「開發人員模式」，點「載入未封裝項目」，選擇此資料夾。
4. 重新整理已登入的 `https://music.apple.com/`，播放歌曲並開啟 Apple Music 的歌詞面板。擴充功能需要重新整理後才會開始觀察歌詞回應；必要時關閉再開啟歌詞面板，或換歌。
5. DeskMon 點開音樂卡片，可用滾輪捲動；點擊帶原生時間的歌詞會要求 Apple Music 跳轉並播放。

Linux 使用同一份擴充功能。請在 Linux 那台機器重做第 1 步配對；伺服器與 Chrome 必須在同一台機器。預設連接埠是 9361，若修改過，請調整產生的 `config.js` 中的 url。

配對檔 `.apple-music-key` 和 `config.js` 請勿分享或提交版本控制。

## 目前限制

- 這是本專案的初版連接器，尚待使用者已登入的 Chrome 實機驗證。
- Apple Music 頁面必須暴露 MusicKit 播放器，並透過歌曲的 lyrics／syllable-lyrics 回應提供 TTML；Apple 修改內部網頁格式時可能需要調整。
- 未攔截到原生歌詞時會提示開啟歌詞面板，不會假裝已同步。Apple 本身沒有提供同步時間的歌曲仍無法點擊跳轉。
- 一次連接一個 Apple Music 分頁；關閉其他播放分頁可避免選錯來源。
- 擴充功能僅將歌名、歌手、播放狀態及歌詞傳到本機；不傳遞 Apple 帳號、Cookie 或權杖。
