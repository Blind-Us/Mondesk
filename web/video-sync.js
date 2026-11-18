/* Shows a YouTube or Bilibili video on the panel by playing it muted and keeping it in step with the
   browser tab. The tab stays the real player (its sound, its controls); the panel only
   follows its position, so it keeps working when the tab's window is covered, minimised or
   in the background — unlike copying frames, which Chrome stops for hidden windows. */
(() => {
  const DRIFT = 1.0;        // seconds apart before re-aligning
  const SEEK_GRACE = 3000;  // ms to let a seek settle (buffering) before checking again
  const UNEMBEDDABLE = new Set([2, 5, 100, 101, 150]);  // YouTube player error codes
  const biliID = track => {
    const m = /^bilibili:(BV[0-9A-Za-z]{10})(?::(\d+))?$/.exec(track || '');
    return m ? {bvid: m[1], part: +(m[2] || 1), key: m[1] + (m[2] ? ':' + m[2] : '')} : null;
  };
  /** What the panel can play by itself: the id used for it (also the key in `failed`), or null. */
  const syncKey = track => videoID(track) || biliID(track)?.key || null;
  const BILI = 'https://player.bilibili.com';
  const CLOCK_DRIFT = 1.5;   // without the helper the position is only an estimate: allow more
  const START_LAG = 1500;    // ms from the embedded page having loaded to its picture moving
  const RELOAD_GRACE = 5000; // ms between two reloads
  const videoID = track => /^youtube:([A-Za-z0-9_-]{11})$/.exec(track || '')?.[1] || null;

  let apiPromise;
  function loadAPI() {
    if (window.YT?.Player) return Promise.resolve(window.YT);
    if (apiPromise) return apiPromise;
    apiPromise = new Promise((resolve, reject) => {
      const previous = window.onYouTubeIframeAPIReady;
      const timer = setTimeout(() => {apiPromise = null; reject(Error('timeout'));}, 20000);
      window.onYouTubeIframeAPIReady = () => {clearTimeout(timer); try {previous?.();} finally {resolve(window.YT);}};
      const script = document.createElement('script');
      script.src = 'https://www.youtube.com/iframe_api';
      script.onerror = () => {clearTimeout(timer); apiPromise = null; reject(Error('load failed'));};
      document.head.append(script);
    });
    return apiPromise;
  }

  class SyncedVideo {
    constructor(host) {
      this.host = host;          // element the player fills
      this.id = null; this.player = null; this.ready = false;
      this.lastSeek = 0;
      this.failed = new Set();   // videos that refuse embedding -> caller falls back to frame mirror
    }
    canPlay(track) { const id = videoID(track); return !!id && !this.failed.has(id); }
    /** Make sure the player shows this video, starting near `position` seconds. */
    show(track, position) {
      const id = videoID(track);
      if (!id || id === this.id) return;
      this.close();
      this.id = id; this.ready = false;
      this.pausedAt = Date.now();   // a freshly loaded player also shows YouTube's title and cards for a few seconds
      const slot = document.createElement('div');
      this.host.replaceChildren(slot);
      this.host.hidden = false;
      loadAPI().then(YT => {
        if (this.id !== id) return;  // closed or switched while loading
        this.player = new YT.Player(slot, {
          videoId: id, host: 'https://www.youtube-nocookie.com',
          playerVars: {autoplay: 1, mute: 1, controls: 0, disablekb: 1, fs: 0, rel: 0, playsinline: 1,
            iv_load_policy: 3, modestbranding: 1, start: Math.floor(position || 0)},
          events: {
            onReady: e => { if (this.id !== id) return; e.target.mute(); this.ready = true; },
            onError: e => { if (UNEMBEDDABLE.has(e.data)) { this.failed.add(id); this.close(); } },
          },
        });
      }).catch(() => { this.failed.add(id); this.close(); });
    }
    /** Follow the tab: same play/pause state, re-align when more than DRIFT seconds apart. */
    /** `keepRunning`: the tab is paused only briefly. The embedded player is then left running (the page
        covers it), because pausing it makes YouTube put up its title link and "more videos" cards, and
        those stay for seconds after it plays again. `pausedAt` tells when it was last really paused. */
    sync(position, playing, ad, keepRunning = false) {
      const p = this.player;
      if (!this.ready || !p) return;
      const state = p.getPlayerState?.();
      if (ad || !playing) {
        if (!keepRunning && state === 1) { p.pauseVideo(); this.pausedAt = Date.now(); }  // 1 = playing
        return;
      }
      if (state !== 1 && state !== 3) p.playVideo();                    // 3 = buffering
      const now = Date.now();
      if (now - this.lastSeek > SEEK_GRACE && Math.abs((p.getCurrentTime?.() || 0) - position) > DRIFT) {
        p.seekTo(position, true);
        this.lastSeek = now;
      }
    }
    /** Is the picture what the tab shows right now? (playing, and within DRIFT of its position) */
    inStep(position) {
      const p = this.player;
      return !!(this.ready && p && p.getPlayerState?.() === 1 && Math.abs((p.getCurrentTime?.() || 0) - position) <= DRIFT);
    }
    close() {
      try { this.player?.destroy?.(); } catch (_) { /* already gone */ }
      this.player = null; this.id = null; this.ready = false;
      this.host.replaceChildren(); this.host.hidden = true;
    }
  }

  /* Bilibili has no player API for other sites, so its embedded player is followed in one of two ways:
     - helper: the Mondesk extension is installed in the browser that shows the panel. Its embed.js runs
       inside the embedded player, hides everything but the picture, and seeks / pauses it exactly.
     - clock: no extension there. The player is started at the tab's position and trusted to run in real
       time; a seek or drift reloads it at the new position, a long pause takes it away. */
  class EmbeddedVideo {
    constructor(host) {
      this.host = host;
      this.id = null; this.frame = null; this.ready = false; this.pausedAt = 0;
      this.failed = new Set();
      this.now = () => Date.now();
      this.lead = 3;   // seconds a load takes until the picture moves; measured after every load
      this.onMessage = e => {
        if (!this.frame || e.origin !== BILI || e.source !== this.frame.contentWindow) return;
        if (e.data?.type === 'deskmon-embed-hello') this.helper ??= {};
        else if (e.data?.type === 'deskmon-embed-state') {
          if (!this.helper?.at) { this.pausedAt = 0; this.host.classList?.remove('crop'); }   // the helper hid the player's own controls
          this.helper = {time: +e.data.time || 0, playing: !!e.data.playing, ready: !!e.data.ready, at: this.now()};
          if (e.data.ready) this.helperReady = true;
          // the embedded player never got a picture (the video can't be embedded): give up on it
          else if (!this.helperReady && this.now() - this.lastLoad > 20000) { this.failed.add(this.id); this.close(); }
        }
      };
    }
    canPlay(track) { const b = biliID(track); return !!b && !this.failed.has(b.key); }
    show(track, position) {
      const b = biliID(track);
      if (!b || b.key === this.id) return;
      this.close();
      this.id = b.key; this.info = b;
      this.host.hidden = false;
      globalThis.addEventListener?.('message', this.onMessage);
      this.load(position, false);
    }
    /** `ahead`: the tab keeps playing while this loads, so start that much further on */
    load(position, ahead = true) {
      const frame = document.createElement('iframe'), start = Math.max(0, Math.floor((position || 0) + (ahead ? this.lead : 0)));
      this.host.classList?.add('crop');   // until the helper answers, the player's own bars are pushed out of sight
      frame.allow = 'autoplay; encrypted-media';
      frame.src = `${BILI}/player.html?bvid=${this.info.bvid}&p=${this.info.part}&autoplay=1&muted=1&danmaku=0&high_quality=1&t=${start}`;
      this.frame = frame; this.ready = false; this.helper = null; this.helperReady = false;
      this.startPos = start; this.loadedAt = 0; this.lastLoad = this.now();
      this.pausedAt = this.now();   // a freshly loaded player shows its own controls for a moment
      frame.onload = () => {
        if (this.frame !== frame) return;
        this.ready = true; this.loadedAt = this.now();
        this.lead = Math.min(10, (this.loadedAt - this.lastLoad + START_LAG) / 1000);
      };
      this.host.replaceChildren(frame);
    }
    /** clock mode: where the embedded player should be by now */
    estimate() { return this.loadedAt ? this.startPos + Math.max(0, this.now() - this.loadedAt - START_LAG) / 1000 : null; }
    sync(position, playing, ad, keepRunning = false) {
      if (!this.id) return;
      const on = playing && !ad;
      if (!this.frame) { if (on) this.load(position); return; }   // taken away during a long pause
      if (this.helper) {
        this.frame.contentWindow?.postMessage({type: 'deskmon-embed', position, playing: on}, BILI);
        return;
      }
      if (!on) {
        // it can't be paused from here: a short pause leaves it running under the cover, a long one takes it away
        if (!keepRunning) { this.frame = null; this.host.replaceChildren(); this.ready = true; this.pausedAt = this.now(); }
        return;
      }
      if (this.ready && this.now() - this.lastLoad > RELOAD_GRACE && Math.abs(this.estimate() - position) > CLOCK_DRIFT) this.load(position);
    }
    inStep(position) {
      if (!this.frame) return false;
      if (this.helper?.at) return this.helper.playing && Math.abs(this.helper.time + (this.now() - this.helper.at) / 1000 - position) <= DRIFT;
      return !!this.loadedAt && this.now() - this.loadedAt > START_LAG && Math.abs(this.estimate() - position) <= CLOCK_DRIFT;
    }
    close() {
      globalThis.removeEventListener?.('message', this.onMessage);
      this.frame = null; this.id = null; this.ready = false; this.helper = null;
      this.host.classList?.remove('crop');
      this.host.replaceChildren(); this.host.hidden = true;
    }
  }

  /** One player for every source the panel can play by itself; the page talks only to this. */
  class AnyVideo {
    constructor(host) {
      this.failed = new Set();
      this.parts = [new SyncedVideo(host), new EmbeddedVideo(host)];
      for (const p of this.parts) p.failed = this.failed;
      this.active = null;
    }
    get id() { return this.active?.id || null; }
    get ready() { return !!this.active?.ready; }
    get pausedAt() { return this.active?.pausedAt || 0; }
    canPlay(track) { return this.parts.some(p => p.canPlay(track)); }
    show(track, position) {
      const part = this.parts.find(p => p.canPlay(track));
      if (!part) return;
      if (this.active && this.active !== part) this.active.close();
      this.active = part;
      part.show(track, position);
    }
    sync(...args) { this.active?.sync(...args); }
    inStep(position) { return !!this.active?.inStep(position); }
    close() { this.active?.close(); this.active = null; }
  }

  if (typeof module !== 'undefined' && module.exports) module.exports = {SyncedVideo, EmbeddedVideo, AnyVideo, videoID, biliID, syncKey};
  else window.DeskMonVideoSync = {SyncedVideo, EmbeddedVideo, AnyVideo, videoID, biliID, syncKey};
})();
