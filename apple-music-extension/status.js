async function update() {
  try {
    const status = await chrome.runtime.sendMessage({type: 'deskmon-status'});
    const stale = status?.updated && Date.now() - status.updated > 5000;
    document.getElementById('status').textContent = (stale ? '頁面訊息已中斷。上次狀態：' : '') + (status?.message || '尚未收到頁面訊息，請重新整理 Apple Music。');
  } catch (error) { document.getElementById('status').textContent = '背景服務無法啟動：' + error.message; }
}
update();
setInterval(update, 1000);
