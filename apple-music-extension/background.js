importScripts('config.js', 'side-screen.js');
let owner = null, lastSeen = 0, ownerPlaying = false, lyricAck = null;
const connectedTabs = new Map();
const supported = (url, tabID) => {try {const parsed = new URL(url); return ['music.apple.com', 'www.youtube.com', 'music.youtube.com', 'www.bilibili.com'].includes(parsed.hostname) || connectedTabs.get(tabID) === parsed.origin;} catch (_) {return false;}};
let status = {message: '尚未收到頁面訊息。請重新整理 Apple Music 分頁並播放歌曲。', updated: 0};
function show(message, badge) {
  if (status.message === message) {status.updated = Date.now(); return;}
  status = {message, updated: Date.now()};
  chrome.action.setBadgeText({text: badge});
  chrome.action.setTitle({title: message});
}
// Alt+Shift+D on a video tab: send it to the side screen fullscreen (again: bring it back)
chrome.commands.onCommand.addListener((command, tab) => {
  if (command === 'side-screen' && tab?.id != null) toggleSideScreen(tab.id).catch(error => show('副螢幕：' + error.message, '!'));
});
chrome.runtime.onMessage.addListener((message, sender, reply) => {
  if (message.type === 'deskmon-side-back' && sender.tab?.id != null) {
    sideBack(sender.tab.id).then(where => reply({ok: true, where}), error => reply({ok: false, error: error.message}));
    return true;
  }
  if (message.type === 'deskmon-side-toggle' && sender.id === chrome.runtime.id && !sender.tab) {
    (async () => {
      const [tab] = await chrome.tabs.query({active: true, lastFocusedWindow: true});
      if (!tab?.id || !/^https?:\/\//.test(tab.url || '')) throw Error('請先選擇影片分頁');
      return toggleSideScreen(tab.id);
    })().then(where => reply({ok: true, where}), error => reply({ok: false, error: error.message}));
    return true;
  }
  if (message.type === 'deskmon-connect-tab' && sender.id === chrome.runtime.id && !sender.tab) {
    (async () => {
      const [tab] = await chrome.tabs.query({active: true, currentWindow: true});
      if (!tab?.id || !/^https?:\/\//.test(tab.url || '') || /^(localhost|127\.0\.0\.1)$/.test(new URL(tab.url).hostname)) throw Error('請先選擇要連接的影片分頁');
      connectedTabs.set(tab.id, new URL(tab.url).origin);
      await chrome.scripting.executeScript({target: {tabId: tab.id}, files: ['content.js', 'video.js']});
      reply({ok: true});
    })().catch(error => reply({ok: false, error: error.message}));
    return true;
  }
  if (message.type === 'deskmon-status' && sender.id === chrome.runtime.id && !sender.tab) {
    reply(status); return;
  }
  if (sender.tab?.id == null || !supported(sender.url, sender.tab.id)) return;
  if (message.type === 'deskmon-frame') {
    // a mirrored video frame: only from the tab Mondesk currently follows
    if (sender.tab.id !== owner || typeof message.data !== 'string' || !message.data.startsWith('data:image/jpeg;base64,')) {
      reply({mirror: false}); return;
    }
    fetch(message.data).then(r => r.blob()).then(jpeg => fetch(DESKMON.url + '/frame', {
      method: 'POST', body: jpeg, signal: AbortSignal.timeout(2500),
      headers: {'Content-Type': 'image/jpeg', 'X-DeskMon-Key': DESKMON.key, 'X-DeskMon-Track': encodeURIComponent(message.track || '')}
    })).then(r => r.ok ? r.json() : {mirror: false}).then(result => reply({mirror: result.mirror !== false}))
      .catch(() => reply({mirror: false}));
    return true;
  }
  if (message.type !== 'deskmon-state') return;
  const playing = !!message.payload?.state?.playing;
  // A paused background tab must not steal a paused video's resume button.
  const ownerTTL = ownerPlaying ? 12000 : 60000;
  if (owner !== null && owner !== sender.tab.id && Date.now() - lastSeen < ownerTTL && (ownerPlaying || !playing)) {
    reply({commands: []}); return;
  }
  if (owner !== sender.tab.id) lyricAck = null;
  owner = sender.tab.id; lastSeen = Date.now(); ownerPlaying = playing;
  if (!message.payload?.state) {
    show(message.payload?.diagnostic || '尚未讀到 Apple Music 播放資料', '?');
    reply({commands: []}); return;
  }
  const payload = {...message.payload, state: {...message.payload.state}};
  const signature = payload.state.track + ':' + payload.state.lyrics_revision;
  if (signature === lyricAck) {delete payload.state.lines; delete payload.state.plain;}
  fetch(DESKMON.url, {
    method: 'POST', headers: {'Content-Type': 'application/json', 'X-DeskMon-Key': DESKMON.key},
    body: JSON.stringify(payload), signal: AbortSignal.timeout(2500)
  }).then(async r => {
    if (!r.ok) throw new Error(r.status === 403 ? '配對失敗（403），請重新產生配對檔並重新載入擴充功能' : 'Mondesk 拒絕資料（HTTP ' + r.status + '）');
    const result = await r.json();
    lyricAck = result.lyrics_revision == null ? null : payload.state.track + ':' + result.lyrics_revision;
    const commands = [];
    for (const command of result.commands || []) {
      if (command.action === 'side-screen') {  // Mondesk's panel asked for this tab on the side screen
        try { await toggleSideScreen(sender.tab.id); commands.push({...command, action: 'fullscreen-result', ok: true}); }
        catch (error) { commands.push({...command, action: 'fullscreen-result', ok: false, error: '副螢幕：' + error.message}); }
        continue;
      }
      if (command.action !== 'fullscreen') {commands.push(command); continue;}
      commands.push({...command, action: 'fullscreen-result', ok: false, error: '已改為面板內影片，請重新整理 Mondesk'});
    }
    show('已連線：' + (payload.state.source || 'Apple Music') + '。' + (message.payload.diagnostic || ''), 'ON');
    status.nowPlaying = {title: payload.state.title || '', artist: payload.state.artist || '', source: payload.state.source || '', playing: !!payload.state.playing};
    reply({...result, commands});
  }).catch(error => {
    show('連線失敗：' + error.message + '。請確認 Mondesk 正在這台電腦執行。', '!');
    reply({commands: [], connected: false});
  });
  return true;
});
