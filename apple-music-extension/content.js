if (!globalThis.__deskmonBridgeContent) {
globalThis.__deskmonBridgeContent = true;
let busy = false, stopped = false, retryAt = 0;
window.addEventListener('message', async event => {
  if (event.source !== window || event.origin !== location.origin || event.data?.type !== 'deskmon-apple-state' || busy || stopped || Date.now() < retryAt) return;
  busy = true;
  try {
    // stamp the running extension version (page.js lives in the page and can't read it), so
    // Mondesk can tell when Chrome is still running an old copy of the extension
    const payload = event.data.payload?.state
      ? {...event.data.payload, state: {...event.data.payload.state, ext: chrome.runtime.getManifest().version}} : event.data.payload;
    const result = await chrome.runtime.sendMessage({type: 'deskmon-state', payload});
    if (result?.connected === false) retryAt = Date.now() + 10000;
    // `mirror` tells video.js whether a Mondesk panel is showing the video right now
    if (result?.commands?.length || result?.acked?.length || result?.lyrics_revision != null || typeof result?.mirror === 'boolean')
      window.postMessage({type: 'deskmon-apple-commands', commands: result?.commands || [], acked: result?.acked || [], lyrics_revision: result?.lyrics_revision, lyrics_track: event.data.payload?.state?.track, mirror: result?.mirror}, location.origin);
  } catch (error) {
    if (!chrome.runtime?.id || /context invalidated/i.test(String(error))) {
      stopped = true;
      window.dispatchEvent(new Event('deskmon-bridge-stop'));
    } else retryAt = Date.now() + 10000;
  }
  finally { busy = false; }
});
}
