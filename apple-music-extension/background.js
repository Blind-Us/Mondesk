importScripts('config.js');
let owner = null, lastSeen = 0;
let status = {message: '尚未收到頁面訊息。請重新整理 Apple Music 分頁並播放歌曲。', updated: 0};
function show(message, badge) {
  status = {message, updated: Date.now()};
  chrome.action.setBadgeText({text: badge});
  chrome.action.setTitle({title: message});
}
chrome.runtime.onMessage.addListener((message, sender, reply) => {
  if (message.type === 'deskmon-status' && sender.id === chrome.runtime.id && !sender.tab) {
    reply(status); return;
  }
  if (sender.tab?.id == null || !sender.url?.startsWith('https://music.apple.com/') || message.type !== 'deskmon-state') return;
  if (owner !== null && owner !== sender.tab.id && Date.now() - lastSeen < 4000) {
    reply({commands: []}); return;
  }
  owner = sender.tab.id; lastSeen = Date.now();
  if (!message.payload?.state) {
    show(message.payload?.diagnostic || '尚未讀到 Apple Music 播放資料', '?');
    reply({commands: []}); return;
  }
  fetch(DESKMON.url, {
    method: 'POST', headers: {'Content-Type': 'application/json', 'X-DeskMon-Key': DESKMON.key},
    body: JSON.stringify(message.payload), signal: AbortSignal.timeout(2500)
  }).then(async r => {
    if (!r.ok) throw new Error(r.status === 403 ? '配對失敗（403），請重新產生配對檔並重新載入擴充功能' : 'DeskMon 拒絕資料（HTTP ' + r.status + '）');
    const result = await r.json();
    show('DeskMon 已連線。' + (message.payload.diagnostic || ''), message.payload.state.lines?.length ? 'OK' : '歌詞');
    reply(result);
  }).catch(error => {
    show('連線失敗：' + error.message + '。請確認 DeskMon 正在這台電腦執行。', '!');
    reply({commands: [], connected: false});
  });
  return true;
});
