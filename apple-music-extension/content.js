let busy = false;
window.addEventListener('message', async event => {
  if (event.source !== window || event.origin !== location.origin || event.data?.type !== 'deskmon-apple-state' || busy) return;
  busy = true;
  try {
    const result = await chrome.runtime.sendMessage({type: 'deskmon-state', payload: event.data.payload});
    window.postMessage({type: 'deskmon-apple-commands', commands: result?.commands || [], acked: result?.acked || []}, location.origin);
  } catch (_) { /* Reload the Apple Music tab after reloading this extension. */ }
  finally { busy = false; }
});
