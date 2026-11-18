// Reads the existing player (never creates a second one). While a Mondesk panel shows the
// video, it mirrors the playing <video> as JPEG frames; the tab keeps playing with its sound.
(() => {
  if (globalThis.__deskmonVideoConnected) return;
  globalThis.__deskmonVideoConnected = true;
  let acks = [], busy = false;
  // ---- mirror: copy frames only while Mondesk says a panel is watching ----
  const FPS = 30, MAX_WIDTH = 960;  // one frame in flight at a time, so a slow PC simply gets fewer
  let mirror = false, mirrorTimer = null, mirrorBusy = false, mirrorState = '', lastSent = -1;
  const canvas = document.createElement('canvas');
  const ctx = canvas.getContext('2d', {alpha: false});
  function setMirror(on) {
    if (on === mirror) return;
    mirror = on;
    clearInterval(mirrorTimer);
    mirrorTimer = on ? setInterval(sendFrame, 1000 / FPS) : null;
    if (!on) {mirrorState = ''; lastSent = -1;}
  }
  async function sendFrame() {
    if (!mirror || mirrorBusy) return;  // include encoding in the one-frame limit
    const video = current(), state = snapshot();
    if (!video || !state) return;
    // Chrome stops drawing video in hidden tabs, so frames would freeze: say so instead
    if (document.hidden) {mirrorState = 'hidden'; return;}
    if (!video.videoWidth) {mirrorState = 'waiting'; return;}
    if (video.currentTime === lastSent) return;  // paused, or no new video frame since the last one
    const width = Math.min(MAX_WIDTH, video.videoWidth);
    const height = Math.round(width * video.videoHeight / video.videoWidth);
    if (canvas.width !== width || canvas.height !== height) {canvas.width = width; canvas.height = height;}
    const frameTime = video.currentTime;
    mirrorBusy = true;
    let blob;
    try {
      ctx.drawImage(video, 0, 0, width, height);
      blob = await new Promise((resolve, reject) => canvas.toBlob(b => b ? resolve(b) : reject(Error('no frame')), 'image/jpeg', 0.72));
    } catch (_) {
      mirrorBusy = false;
      setMirror(false);
      mirrorState = 'blocked';
      return;
    }
    mirrorState = '';
    lastSent = frameTime;
    try {
      if (!mirror || snapshot()?.track !== state.track) return;
      const data = await new Promise(resolve => {const r = new FileReader(); r.onload = () => resolve(r.result); r.readAsDataURL(blob);});
      const reply = await chrome.runtime.sendMessage({type: 'deskmon-frame', track: state.track, data});
      if (reply?.mirror === false) setMirror(false);
    } catch (_) {
      setMirror(false);  // extension reloaded or Mondesk gone
    } finally {mirrorBusy = false;}
  }
  // read once: after the extension is reloaded, chrome.runtime throws in the copy of this script left in open tabs
  let EXT = '';
  try { EXT = chrome.runtime?.getManifest?.().version || ''; } catch (_) { /* that left-over copy */ }
  const apple = location.hostname === 'music.apple.com';
  let appleState = null;
  let cachedVideo = null;
  const current = () => {
    if (cachedVideo && cachedVideo.isConnected !== false && !cachedVideo.ended && !cachedVideo.paused) return cachedVideo;
    const videos = [...document.querySelectorAll('video')];
    cachedVideo = videos.find(v => !v.paused && v.readyState > 0) || videos.find(v => v.readyState > 0);
    return cachedVideo;
  };
  function snapshot() {
    if (apple) return appleState;
    const video = current();
    if (!video) return null;
    const metadata = navigator.mediaSession?.metadata;
    const youtube = ['www.youtube.com', 'music.youtube.com'].includes(location.hostname);
    // Bilibili: the video's BV id (and part number), so the panel can play the same video itself
    const bv = location.hostname === 'www.bilibili.com' ? location.pathname.match(/^\/video\/(BV[0-9A-Za-z]{10})/)?.[1] : null;
    const part = bv ? Math.max(1, parseInt(new URL(location.href).searchParams.get('p'), 10) || 1) : 1;
    const id = youtube ? new URL(location.href).searchParams.get('v') || location.pathname.match(/\/shorts\/([^/?]+)/)?.[1]
      : bv ? bv + (part > 1 ? ':' + part : '') : (metadata?.title || document.title) + ':' + video.duration;
    if (!id) return null;
    let cover = '';
    if (!youtube) {
      try {
        const raw = document.querySelector('meta[property="og:image"], meta[name="og:image"], meta[name="twitter:image"]')?.content || video.poster || '';
        // Bilibili adds a size suffix (@100w_100h…) that makes it tiny: ask for the full picture
        if (raw) cover = new URL(bv ? raw.replace(/@.*$/, '') : raw, location.href).href.replace(/^http:/, 'https:');
      } catch (_) { /* not a usable address */ }
    }
    return {track: (youtube ? 'youtube:' : bv ? 'bilibili:' : 'web:') + id, source: location.hostname === 'music.youtube.com' ? 'YouTube Music' : youtube ? 'YouTube' : bv ? 'Bilibili' : 'Browser',
      title: (metadata?.title || document.title).replace(/ - YouTube(?: Music)?$/, '').replace(/_哔哩哔哩_bilibili$/, ''), artist: metadata?.artist || '', album: metadata?.album || '',
      art_url: metadata?.artwork?.at(-1)?.src || (youtube ? `https://i.ytimg.com/vi/${encodeURIComponent(id)}/hqdefault.jpg` : cover || ''),
      playing: !video.paused && !video.ended, position: Math.max(0, video.currentTime || 0), duration: Number.isFinite(video.duration) ? video.duration : 0,
      // during a YouTube ad the <video> plays the ad: its time isn't the video's time
      ad: youtube && !!document.querySelector('#movie_player.ad-showing, .html5-video-player.ad-showing'),
      volume: video.muted ? 0 : Math.round((video.volume ?? 1) * 100),  // this video's own volume, not the computer's
      video: true, mirror: mirrorState, ext: EXT, lines: [], plain: [], lyrics_revision: 0};
  }
  window.addEventListener('message', async e => {
    if (e.source === window && e.origin === location.origin && e.data?.type === 'deskmon-apple-state' && apple) {appleState = e.data.payload?.state; return;}
    if (apple) return;
    if (e.source !== window || e.origin !== location.origin || e.data?.type !== 'deskmon-apple-commands') return;
    if (typeof e.data.mirror === 'boolean') setMirror(e.data.mirror);
    if (busy) return;
    acks = acks.filter(a => !(e.data.acked || []).includes(a.id));
    busy = true;
    try {
      for (const command of e.data.commands || []) {
        try {
          const video = current();
          if (snapshot()?.track !== command.track || !video) throw Error('影片已變更');
          if (command.action === 'fullscreen-result') {acks.push({id: command.id, ok: command.ok, error: command.error}); continue;}
          if (command.action === 'toggle') await (video.paused ? video.play() : video.pause());
          else if (command.action === 'seek_time') {
            // the progress bar on Mondesk: jump the real <video>; YouTube's own UI follows it
            const target = Number(command.position);
            if (!Number.isFinite(target) || target < 0 || (Number.isFinite(video.duration) && target > video.duration)) throw Error('無效的播放時間');
            if (snapshot()?.ad) throw Error('廣告播放中，結束後再跳轉');
            video.currentTime = target;
            lastSent = -1;
          }
          else if (command.action === 'volume') {
            // the volume bar on Mondesk: this video only (the tab's player), never the system volume
            const value = Number(command.value);
            if (!Number.isFinite(value) || value < 0 || value > 100) throw Error('無效的音量');
            video.muted = value === 0;
            video.volume = value / 100;
            lastSent = -1;
          }
          else if (command.action === 'next' || command.action === 'prev') {
            const button = document.querySelector(command.action === 'next' ? '.ytp-next-button' : '.ytp-prev-button');
            if (!button || button.getAttribute('aria-disabled') === 'true') throw Error('播放器不提供這個操作');
            button.click();
          } else throw Error('不支援的影片操作');
          acks.push({id: command.id, ok: true});
        } catch (error) {acks.push({id: command.id, ok: false, error: error.message});}
      }
    } finally {busy = false;}
  });
  const heartbeat = setInterval(() => {
    if (apple) return;
    const state = snapshot();
    if (state) window.postMessage({type: 'deskmon-apple-state', payload: {state, acks, diagnostic: '已讀取原分頁播放資訊'}}, location.origin);
  }, 2000);
  window.addEventListener('deskmon-bridge-stop', () => {clearInterval(heartbeat); setMirror(false);}, {once: true});
})();
