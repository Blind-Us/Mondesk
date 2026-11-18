/* Sends a video tab to the side screen: the tab moves into its own fullscreen window on the
   small extra display and the video fills it. Chrome keeps playing it natively, so it is as
   smooth as on the main screen, keeps its sound and works on any site (even DRM ones).
   The same trigger again (Alt+Shift+D, the popup button, Mondesk's panel, Esc or the
   "回主螢幕" button on the side screen) moves the tab back where it was. */
const sideTabs = new Map();  // tabId -> {windowId, index, sideWindow}
// Chrome unloads the background between uses: keep the record in session storage
const sideReady = chrome.storage.session.get('sideTabs').then(r => {
  for (const [id, info] of r.sideTabs || []) sideTabs.set(+id, info);
}).catch(() => {});
const saveSide = () => chrome.storage.session.set({sideTabs: [...sideTabs]}).catch(() => {});

async function sideDisplay() {
  const displays = await chrome.system.display.getInfo();
  // Mondesk's panel is the extra screen; with several, take the smallest one
  return displays.filter(d => !d.isPrimary && d.isEnabled !== false)
    .sort((a, b) => a.bounds.width * a.bounds.height - b.bounds.width * b.bounds.height)[0] || null;
}

// runs inside the video page: make the site's player fill the window (or undo that).
// The whole player box is enlarged, not just the <video>, so the site's own progress bar and
// buttons keep working; the real player is picked over decorative videos other extensions add.
function deskmonFillVideo(on) {
  window.__deskmonSideOff?.();
  if (!on) return true;
  const known = document.querySelector('#movie_player video.html5-main-video, .bpx-player-video-wrap video');
  const score = v => (v.muted ? 0 : 4) + (v.paused ? 0 : 2) + (v.readyState >= 2 ? 1 : 0);
  const video = known || [...document.querySelectorAll('video')].filter(v => v.offsetWidth * v.offsetHeight > 0)
    .sort((a, b) => score(b) - score(a) || b.offsetWidth * b.offsetHeight - a.offsetWidth * a.offsetHeight)[0];
  if (!video) return false;
  // the player box: the highest ancestor that is still about the video's size
  const known_box = video.closest('#movie_player, .bpx-player-primary-area, .bpx-player-container');
  let box = known_box || video;
  if (!known_box) {
    const vr = video.getBoundingClientRect();
    for (let el = video.parentElement; el && el !== document.body; el = el.parentElement) {
      const r = el.getBoundingClientRect();
      if (r.width > vr.width * 1.1 + 24 || r.height > vr.height * 1.25 + 60) break;
      box = el;
    }
  }
  box.setAttribute('data-deskmon-fill', '');
  video.setAttribute('data-deskmon-video', '');
  // wrappers between the player and the video often have no height of their own
  const mids = [];
  for (let el = video.parentElement; el && el !== box; el = el.parentElement) { el.setAttribute('data-deskmon-mid', ''); mids.push(el); }
  const ups = [];
  for (let el = box.parentElement; el; el = el.parentElement) { el.setAttribute('data-deskmon-up', ''); ups.push(el); }
  const style = document.createElement('style');
  // ancestors lose anything that would trap a fixed element; everything beside them is hidden
  style.textContent = `
    [data-deskmon-up]{transform:none!important;filter:none!important;perspective:none!important;contain:none!important;will-change:auto!important;backdrop-filter:none!important}
    [data-deskmon-up]>*:not([data-deskmon-up]):not([data-deskmon-fill]):not(#deskmon-side-back){visibility:hidden!important}
    html,body{overflow:hidden!important;background:#000!important}
    [data-deskmon-fill]{position:fixed!important;inset:0!important;width:100vw!important;height:100vh!important;max-width:none!important;max-height:none!important;min-width:0!important;min-height:0!important;margin:0!important;transform:none!important;background:#000!important;z-index:2147483646!important;visibility:visible!important}
    [data-deskmon-mid]{position:absolute!important;inset:0!important;width:100%!important;height:100%!important;transform:none!important}
    video[data-deskmon-video]{position:absolute!important;inset:0!important;width:100%!important;height:100%!important;object-fit:contain!important;transform:none!important;visibility:visible!important;opacity:1!important}
    #deskmon-side-back{position:fixed;top:16px;left:16px;z-index:2147483647;padding:12px 20px;border:0;border-radius:999px;background:#000b;color:#fff;font:600 18px system-ui,sans-serif;cursor:pointer;opacity:0;transition:opacity .3s;visibility:visible!important}
    #deskmon-side-back.show{opacity:1}`;
  const back = document.createElement('button');
  back.id = 'deskmon-side-back'; back.textContent = '↩ 回主螢幕';
  document.documentElement.append(style, back);
  dispatchEvent(new Event('resize'));  // players re-measure themselves for the new size
  let timer;
  const wake = () => { back.classList.add('show'); clearTimeout(timer); timer = setTimeout(() => back.classList.remove('show'), 2500); };
  const goBack = () => chrome.runtime.sendMessage({type: 'deskmon-side-back'});
  const key = e => { if (e.key === 'Escape') goBack(); };
  back.addEventListener('click', goBack);
  addEventListener('pointermove', wake, true); addEventListener('pointerdown', wake, true); addEventListener('keydown', key, true);
  window.__deskmonSideOff = () => {
    style.remove(); back.remove(); clearTimeout(timer);
    removeEventListener('pointermove', wake, true); removeEventListener('pointerdown', wake, true); removeEventListener('keydown', key, true);
    box.removeAttribute('data-deskmon-fill'); video.removeAttribute('data-deskmon-video'); mids.forEach(el => el.removeAttribute('data-deskmon-mid')); ups.forEach(el => el.removeAttribute('data-deskmon-up'));
    delete window.__deskmonSideOff;
    dispatchEvent(new Event('resize'));
  };
  return true;
}

async function setFill(tabId, on) {
  const [result] = await chrome.scripting.executeScript({target: {tabId}, func: deskmonFillVideo, args: [on]});
  return result?.result;
}

async function sendToSide(tabId) {
  const display = await sideDisplay();
  if (!display) throw Error('找不到副螢幕');
  const tab = await chrome.tabs.get(tabId);
  const {left, top, width, height} = display.bounds;
  sideTabs.set(tabId, {windowId: tab.windowId, index: tab.index});
  const win = await chrome.windows.create({tabId, left, top, width, height, focused: true});
  sideTabs.get(tabId).sideWindow = win.id;
  saveSide();
  await chrome.windows.update(win.id, {state: 'fullscreen'});
  // without access to the page the whole page shows fullscreen instead of just the video
  await setFill(tabId, true).catch(() => false);
  return 'side';
}

async function backFromSide(tabId) {
  const info = sideTabs.get(tabId);
  sideTabs.delete(tabId);
  saveSide();
  await setFill(tabId, false).catch(() => {});
  try {
    await chrome.windows.get(info.windowId);
    await chrome.tabs.move(tabId, {windowId: info.windowId, index: info.index});  // the empty side window closes
    await chrome.tabs.update(tabId, {active: true});
    await chrome.windows.update(info.windowId, {focused: true});
  } catch (_) {
    // its old window is gone (it was the only tab there): open a normal window on the main screen
    const main = (await chrome.system.display.getInfo()).find(d => d.isPrimary)?.workArea;
    await chrome.windows.create({tabId, focused: true, ...(main ? {left: main.left + 40, top: main.top + 40,
      width: Math.round(main.width * .8), height: Math.round(main.height * .8)} : {})});
  }
  return 'main';
}

async function toggleSideScreen(tabId) {
  await sideReady;
  return sideTabs.has(tabId) ? backFromSide(tabId) : sendToSide(tabId);
}
async function sideBack(tabId) {
  await sideReady;
  return sideTabs.has(tabId) ? backFromSide(tabId) : 'main';
}

chrome.tabs.onRemoved.addListener(async tabId => { await sideReady; if (sideTabs.delete(tabId)) saveSide(); });
chrome.windows.onRemoved.addListener(async windowId => {
  await sideReady;
  for (const [tabId, info] of sideTabs) if (info.sideWindow === windowId) sideTabs.delete(tabId);
  saveSide();
});
