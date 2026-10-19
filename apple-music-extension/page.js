// Observe only lyric responses already requested by Apple Music. Never forward tokens.
(() => {
  const lyrics = new Map();
  const lyricRequests = new Map();
  let lyricDiagnostic = '';
  let acks = [], running = false;
  const kit = () => {
    const k = window.MusicKit?.getInstance();
    // Modern MusicKit exposes playback directly; older builds use .player.
    return [k, k?.player].find(p => p?.nowPlayingItem && Number.isFinite(Number(p.currentPlaybackTime))) || k?.player || k;
  };
  const itemID = item => String(item?.attributes?.playParams?.catalogId || item?.attributes?.playParams?.id || item?.id || '');
  function seconds(value) {
    if (!value) return null;
    value = value.trim();
    if (/^\d+(\.\d+)?(ms|s)$/.test(value)) return parseFloat(value) / (value.endsWith('ms') ? 1000 : 1);
    // Apple writes "12.345" (bare seconds) under a minute and "1:02.345" after.
    if (/^\d+(\.\d+)?$/.test(value)) return parseFloat(value);
    if (!/^\d+(?::\d+(?:\.\d+)?){1,2}$/.test(value)) return null;
    return value.split(':').reduce((n, part) => n * 60 + Number(part), 0);
  }
  // Syllable lyrics may time the words instead of the line: fall back to the first timed child.
  const lineStart = p => seconds(p.getAttribute('begin'))
    ?? [...p.getElementsByTagNameNS('*', 'span')].map(s => seconds(s.getAttribute('begin'))).find(t => t !== null) ?? null;
  function parse(text) {
    const doc = new DOMParser().parseFromString(text, 'application/xml');
    if (doc.querySelector('parsererror')) return {lines: [], plain: []};
    const lines = [], plain = [];
    for (const p of doc.getElementsByTagNameNS('*', 'p')) {
      const words = p.textContent.replace(/\s+/g, ' ').trim();
      if (!words) continue;
      plain.push(words);
      const start = lineStart(p);
      if (start !== null && Number.isFinite(start)) lines.push([start, words]);
    }
    const timing = doc.documentElement.getAttribute('itunes:timing') || '未標示';
    const timed = timing !== 'None' && lines.length === plain.length && new Set(lines.map(l => l[0])).size > 1;
    const sample = doc.getElementsByTagNameNS('*', 'p')[0];
    const why = timing === 'None' ? 'Apple Music 這首歌只有靜態歌詞（沒有同步時間）'
      : `時間格式無法解析（timing=${timing}，${lines.length}/${plain.length} 行有時間，範例 begin="${sample?.getAttribute('begin') ?? ''}"）`;
    return {lines: timed ? lines.sort((a, b) => a[0] - b[0]) : [], plain, why: timed ? '' : why};
  }
  function capture(url, body) {
    const match = String(url).match(/\/songs\/([^/?]+)(?:[/?]|$)/);
    if (!match) return;
    try {
      let text = body;
      if (!String(body).trim().startsWith('<')) {
        const json = typeof body === 'string' ? JSON.parse(body) : body;
        const findTTML = value => {
          if (!value || typeof value !== 'object') return null;
          if (typeof value.attributes?.ttml === 'string') return value.attributes.ttml;
          for (const child of Object.values(value)) {
            const found = findTTML(child);
            if (found) return found;
          }
          return null;
        };
        const resources = Array.isArray(json?.data) ? json.data : [];
        // Expanded song responses can carry lyrics under relationships.
        const song = resources.find(row => row.type === 'songs' && String(row.id) === decodeURIComponent(match[1]));
        text = song ? findTTML(song) : /\/(?:syllable-lyrics|lyrics)(?:[/?]|$)/.test(String(url)) ? findTTML(json) : null;
      }
      if (typeof text !== 'string' || !text.includes('<tt')) return;
      lyrics.set(decodeURIComponent(match[1]), parse(text));
      if (lyrics.size > 12) lyrics.delete(lyrics.keys().next().value);
    } catch (_) { /* An unsupported response is never assigned fabricated timing. */ }
  }
  const originalFetch = window.fetch;
  window.fetch = function (...args) {
    const result = originalFetch.apply(this, args);
    const url = args[0]?.url || String(args[0]);
    if (/\/songs\/[^/?]+(?:[/?]|$)/.test(url)) {
      result.then(r => r.clone().text()).then(body => capture(url, body)).catch(() => {});
    }
    return result;
  };
  const open = XMLHttpRequest.prototype.open, send = XMLHttpRequest.prototype.send;
  const urls = new WeakMap();
  XMLHttpRequest.prototype.open = function (method, url, ...rest) { urls.set(this, String(url)); return open.call(this, method, url, ...rest); };
  XMLHttpRequest.prototype.send = function (...args) {
    const url = urls.get(this) || '';
    if (/\/songs\/[^/?]+(?:[/?]|$)/.test(url)) this.addEventListener('load', () => {
      try { capture(url, this.responseType === 'json' ? this.response : this.responseText); } catch (_) {}
    }, {once: true});
    return send.apply(this, args);
  };
  function snapshot() {
    const player = kit(), item = player?.nowPlayingItem, id = itemID(item);
    if (!id) return null;
    const attr = item.attributes || item;
    const artwork = attr.artwork?.url || item.artwork?.url || '';
    const artURL = artwork.replaceAll('{w}', '600').replaceAll('{h}', '600').replaceAll('{f}', 'jpg').replaceAll('{c}', 'bb');
    const position = Number(player.currentPlaybackTime), duration = Number(player.currentPlaybackDuration || attr.durationInMillis / 1000);
    if (!Number.isFinite(position) || !Number.isFinite(duration)) return null;
    return {track: 'apple:' + id, title: attr.name || item.title || '', artist: attr.artistName || '', album: attr.albumName || '', art_url: artURL,
      position: Math.max(0, position), duration: Math.max(0, duration), playing: !!player.isPlaying,
      ...(lyrics.get(id) || {lines: [], plain: []})};
  }
  async function requestLyrics(state) {
    const id = state.track.slice(6);
    if (lyrics.has(id) || Date.now() - (lyricRequests.get(id) || 0) < 20000) return;
    lyricRequests.set(id, Date.now());
    try {
      const instance = window.MusicKit?.getInstance();
      if (typeof instance?.api?.music !== 'function') {
        lyricDiagnostic = '此頁面未提供歌詞查詢介面，等待網頁原生歌詞回應';
        return;
      }
      const region = [instance.storefrontId, location.pathname?.split('/')[1]].find(value => typeof value === 'string' && /^[a-z]{2}$/i.test(value));
      if (!region) { lyricDiagnostic = '尚未讀到 Apple Music 商店地區'; return; }
      // Requests stay inside the signed-in Apple page via its own API client.
      // No credentials are copied or sent to DeskMon.
      for (const kind of ['syllable-lyrics', 'lyrics']) {
        const path = `/v1/catalog/${region.toLowerCase()}/songs/${encodeURIComponent(id)}/${kind}`;
        try {
          const response = await instance.api.music(path);
          capture(path, response);
          if (lyrics.has(id)) { lyricDiagnostic = ''; return; }
          lyricDiagnostic = 'Apple Music 回應尚未包含可辨識的 TTML 歌詞';
        } catch (error) {
          const code = Number(error?.status || error?.response?.status || error?.errors?.[0]?.status);
          lyricDiagnostic = Number.isFinite(code) && code > 0 ? `Apple Music 歌詞查詢回覆 HTTP ${code}` : 'Apple Music 歌詞查詢未成功';
        }
      }
    } catch (_) { lyricDiagnostic = 'Apple Music 歌詞介面暫時無法讀取'; }
  }
  window.addEventListener('message', async event => {
    if (event.source !== window || event.origin !== location.origin || event.data?.type !== 'deskmon-apple-commands' || running) return;
    const acknowledged = new Set(event.data.acked || []);
    acks = acks.filter(ack => !acknowledged.has(ack.id));
    running = true;
    try {
      for (const command of event.data.commands || []) {
        if (!['seek', 'toggle', 'next', 'prev'].includes(command.action)) continue;
        try {
          const state = snapshot(), player = kit();
          if (!state || state.track !== command.track) throw new Error('歌曲已變更');
          if (command.action === 'seek') {
            if (!Number.isFinite(command.position) || !state.lines.some(row => Math.abs(row[0] - command.position) < .01)) throw new Error('缺少原生歌詞時間');
            await player.seekToTime(command.position);
            await player.play();
          } else if (command.action === 'toggle') await (player.isPlaying ? player.pause() : player.play());
          else if (command.action === 'next') await player.skipToNextItem();
          else await player.skipToPreviousItem();
          acks.push({id: command.id, ok: true});
        } catch (error) { acks.push({id: command.id, ok: false, error: error.message}); }
      }
    } finally { running = false; }
  });
  setInterval(() => {
    try {
      const state = snapshot();
      if (state) void requestLyrics(state);
      const found = state && lyrics.get(state.track.slice(6));
      const diagnostic = '[v0.1.4] ' + (!window.MusicKit ? '頁面未提供 MusicKit 播放器' : !state ? '已找到 MusicKit，尚未讀到歌曲或有效播放時間'
        : state.lines.length ? '已讀到 Apple Music 同步歌詞' : found?.why || lyricDiagnostic || '已讀到播放資料，等待原生歌詞；請開啟歌詞面板');
      window.postMessage({type: 'deskmon-apple-state', payload: {state, acks, diagnostic}}, location.origin);
    } catch (error) {
      window.postMessage({type: 'deskmon-apple-state', payload: {state: null, acks, diagnostic: '讀取播放器失敗：' + error.message}}, location.origin);
    }
  }, 500);
})();
