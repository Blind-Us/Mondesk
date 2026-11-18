let connectionError = '', connecting = false;
async function update() {
  try {
    const status = await chrome.runtime.sendMessage({type: 'deskmon-status'});
    const stale = !status?.updated || Date.now() - status.updated > 12000;
    const media = !stale && !/^連線失敗/.test(status?.message || '') ? status?.nowPlaying : null;
    document.getElementById('title').textContent = media?.title || '等待播放';
    document.getElementById('artist').textContent = media?.artist || (media ? '目前分頁' : '開啟音樂或影片後自動同步');
    document.getElementById('source').textContent = media ? `${media.source} · ${media.playing ? '播放中' : '已暫停'}` : '等待連線';
    document.getElementById('status').textContent = connectionError || (stale ? '頁面訊息已中斷。上次狀態：' : '') + (status?.message || '尚未收到頁面訊息，請重新整理播放分頁。');
  } catch (error) { document.getElementById('status').textContent = '背景服務無法啟動：' + error.message; }
}
document.getElementById('version').textContent = 'v' + chrome.runtime.getManifest().version;
update();
setInterval(() => {if (!connecting) update();}, 2000);
document.getElementById('side').onclick = async () => {
  const result = await chrome.runtime.sendMessage({type: 'deskmon-side-toggle'}).catch(error => ({ok: false, error: error.message}));
  if (result?.ok) window.close();
  else document.getElementById('status').textContent = result?.error || '無法送到副螢幕';
};
document.getElementById('connect').onclick = async () => {
  const button = document.getElementById('connect'); connecting = true; connectionError = ''; button.disabled = true; button.textContent = '正在連接…';
  try {
    const result = await chrome.runtime.sendMessage({type: 'deskmon-connect-tab'});
    if (!result?.ok) throw Error(result?.error || '無法連接');
    button.textContent = '已連接目前分頁';
  } catch (error) {connectionError = error.message; document.getElementById('status').textContent = connectionError; button.textContent = '重試連接目前分頁';}
  finally {connecting = false; button.disabled = false;}
};
