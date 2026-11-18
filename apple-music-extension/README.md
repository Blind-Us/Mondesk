# Mondesk Now Playing（Windows／Linux）

支援 Apple Music 原生歌詞、YouTube、YouTube Music，以及手動連接的一般 HTML5 影片分頁。

點 Mondesk 的音樂卡片：
- **Apple Music 歌曲** → 全螢幕同步歌詞。
- **YouTube、Bilibili** → 面板自己靜音播同一支影片並跟著原分頁的進度，不擷取畫面，原分頁可以蓋住或縮小。
- **其他影片網站** → 全螢幕顯示影片畫面（鏡像）。原分頁照常播放、聲音也從原分頁出來，不會暫停或跳轉；
  擴充功能只在全螢幕頁面打開時擷取畫面（最高約 30 張／秒、最寬 960px），關閉後約 2 秒內停止。
  按右上角 ✕ 或 Esc 關閉，邏輯和歌詞頁相同。

## 送到副螢幕全螢幕（最順）

在影片分頁按 **Alt+Shift+D**（或點擴充功能圖示 →「送到副螢幕全螢幕」，或 Mondesk 音樂卡上的 ⤢ 按鈕），
整個分頁會搬到副螢幕、全螢幕，只顯示影片。因為是瀏覽器自己在播，畫面和主螢幕一樣順，聲音照舊，
B 站、Netflix 這類網站也可以。再按一次 Alt+Shift+D、按 Esc，或點副螢幕左上角的「↩ 回主螢幕」就會搬回原本的視窗。
快捷鍵可以在 `chrome://extensions/shortcuts` 修改。

影片畫面的限制：
- 影片分頁必須在前景（可以放在主螢幕的另一個視窗）。分頁在背景時 Chrome 會停止繪製影片，面板會顯示提示而不是凍結的畫面。
- 有版權保護（DRM）或跨來源的影片，瀏覽器不允許擷取畫面，面板會顯示「不允許擷取」的提示。

歌詞讀取與查詢留在 Apple Music 頁面；登入憑證不會傳到 Mondesk。影片畫面只送到本機的 Mondesk（127.0.0.1），並以配對金鑰驗證。

## 首次設定

1. desktop 會從使用者設定產生配對資料夾；使用伺服器版可執行 `python -m modules.apple_bridge`。
2. Windows 資料夾為 `%LOCALAPPDATA%/DeskMon/browser-extension`；Linux 為 `~/.config/DeskMon/browser-extension`（遵循 XDG_CONFIG_HOME）。
3. Chrome 開啟 `chrome://extensions/`，開啟「開發人員模式」，點「載入未封裝項目」，選擇上面的使用者資料夾。通用 desktop 包只有模板，不包含任何人的設定或配對碼。
4. 重新整理已登入的 `https://music.apple.com/`，播放歌曲並開啟 Apple Music 的歌詞面板。擴充功能需要重新整理後才會開始觀察歌詞回應；必要時關閉再開啟歌詞面板，或換歌。
5. Mondesk 點開音樂卡片，可用滾輪捲動；點擊帶原生時間的歌詞會要求 Apple Music 跳轉並播放。

YouTube／YouTube Music 自動辨識；其他影片網站請先選取該分頁，再點擴充功能的「連接目前影片分頁」。這只授權目前分頁，不要求所有網站的存取權限。跨來源 iframe 中的影片及特殊 DRM 播放器可能不支援。

Linux 使用同一份擴充功能；伺服器與 Chrome 必須在同一台機器。正式設定唯一來源是 user config，必要的擴充功能配對副本只產生在同一使用者目錄。

使用者設定與產生的 `browser-extension/config.js` 請勿分享或提交版本控制。

## 目前限制

- Apple Music 頁面必須暴露 MusicKit 播放器，並透過歌曲的 lyrics／syllable-lyrics 回應提供 TTML；Apple 修改內部網頁格式時可能需要調整。
- 未攔截到原生歌詞時會提示開啟歌詞面板，不會假裝已同步。Apple 本身沒有提供同步時間的歌曲仍無法點擊跳轉。
- 優先顯示正在播放的分頁；兩個分頁同時播放時維持先取得控制的來源，暫停後可由另一個播放來源接替。
- 擴充功能僅將歌名、歌手、播放狀態及歌詞傳到本機；不傳遞 Apple 帳號、Cookie 或權杖。
