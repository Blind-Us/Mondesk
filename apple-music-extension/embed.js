// Runs inside Bilibili's embedded player (player.bilibili.com in an <iframe>). It does nothing until the
// page that embeds it is a Mondesk panel and says so; then it turns that player into a silent picture
// that follows the real tab: no controls, no cards, muted, same position and play / pause state.
(() => {
  if (window.top === window || globalThis.__deskmonEmbed) return;
  globalThis.__deskmonEmbed = true;
  const DRIFT = 0.6;     // seconds apart before re-aligning
  const GRACE = 2500;    // ms to let a seek settle (buffering) before checking again
  // a Mondesk panel is served by the user's own PC: this machine or an address on the home network
  const local = origin => {
    try {
      const u = new URL(origin);
      return u.protocol === 'http:' && /^(localhost|127\.0\.0\.1|\[::1\]|10\.\d+\.\d+\.\d+|192\.168\.\d+\.\d+|172\.(1[6-9]|2\d|3[01])\.\d+\.\d+|[\w-]+\.local)$/.test(u.hostname);
    } catch (_) { return false; }
  };
  let panel = null, lastSeek = 0;
  const video = () => document.querySelector('video');
  function takeOver() {
    // only the picture is left: it fills the frame, above everything the player draws, and nothing reacts to a touch
    const style = document.createElement('style');
    style.textContent = 'video{position:fixed!important;inset:0!important;width:100vw!important;height:100vh!important;' +
      'z-index:2147483647!important;object-fit:contain!important;background:#000!important}html{pointer-events:none!important}';
    document.documentElement.append(style);
  }
  function follow(command) {
    const v = video(), position = Number(command.position);
    if (!v || !Number.isFinite(position) || position < 0) return;
    v.muted = true;   // the sound is the real tab's
    if (!command.playing) {
      if (!v.paused) v.pause();
      if (Math.abs(v.currentTime - position) > DRIFT) v.currentTime = position;
      return;
    }
    if (v.paused) v.play().catch(() => {});
    if (Date.now() - lastSeek > GRACE && Math.abs(v.currentTime - position) > DRIFT) { v.currentTime = position; lastSeek = Date.now(); }
  }
  window.addEventListener('message', e => {
    if (e.source !== window.parent || e.data?.type !== 'deskmon-embed' || !local(e.origin)) return;
    if (!panel) { panel = e.origin; takeOver(); }
    follow(e.data);
  });
  const timer = setInterval(() => {
    try {
      if (!panel) { window.parent.postMessage({type: 'deskmon-embed-hello'}, '*'); return; }   // says nothing but "I am here"
      const v = video();
      window.parent.postMessage({type: 'deskmon-embed-state', ready: !!v && v.readyState >= 2, time: v?.currentTime || 0,
        playing: !!v && !v.paused && !v.ended && v.readyState > 2}, panel);
    } catch (_) { clearInterval(timer); }
  }, 500);
})();
