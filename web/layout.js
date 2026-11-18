/* One layout coordinate system. OS resolution is separate from browser CSS pixels. */
(function (root) {
  function settings(display = {}) {
    const n = (v, fallback, low, high) => Number.isFinite(+v) && +v >= low && +v <= high ? +v : fallback;
    const width = n(display.width, 960, 320, 7680);
    const height = n(display.height, 640, 240, 4320);
    return { width, height, fit: display.fit === 'auto' ? 'auto' : 'contain',
      textScale: n(display.text_scale, 1, .8, 1.4) };
  }
  function calculate(viewWidth, viewHeight, display = {}) {
    const d = settings(display), vw = Math.max(1, viewWidth), vh = Math.max(1, viewHeight);
    const aspect = d.fit === 'auto' ? Math.max(1.25, Math.min(2.4, vw / vh)) : d.width / d.height;
    const height = 640 / d.textScale, width = height * aspect;
    const scale = Math.min(vw / width, vh / height);
    return { width, height, scale, aspect, textScale: d.textScale, contentWidth: width * scale, contentHeight: height * scale };
  }
  function panelDisplays(displays) {
    return displays.filter(d => !d.error && !d.primary && d.current && d.modes?.some(m => m.w === 960 && m.h === 640));
  }

  // ---------- widget grid: where each card sits (display.layout in config) ----------
  const COLS = 6, ROWS = 8;
  const WIDGETS = ['bambu', 'media', 'tokens', 'companion', 'system', 'clock', 'weather'];
  const DEFAULT_ITEMS = [
    { id: 'bambu', x: 0, y: 0, w: 3, h: 5 }, { id: 'media', x: 3, y: 0, w: 3, h: 5 },
    { id: 'tokens', x: 0, y: 5, w: 3, h: 3 }, { id: 'companion', x: 3, y: 5, w: 3, h: 3 },
  ];

  // Card sizes are rules in grid cells, never pixels (docs/LAYOUT.md). To compare width and height, one row is
  // 1 unit tall and one column is COL_UNITS wide; another screen may have another grid and another COL_UNITS.
  const COL_UNITS = 2;
  const MIN = { bambu: [2, 2], media: [2, 2], tokens: [2, 2], system: [1, 2], weather: [1, 2], companion: [1, 2], clock: [1, 1] };  // [columns, rows]
  // level from the short side, direction from the ratio: {size: xs|s|m|l, orient: wide|square|tall}
  function cardSize(w, h, colUnits = COL_UNITS) {
    const uw = w * colUnits, short = Math.min(uw, h), ratio = uw / h;
    return { size: short <= 2 ? 'xs' : short <= 3 ? 's' : short <= 4 ? 'm' : 'l', orient: ratio >= 1.5 ? 'wide' : ratio < .67 ? 'tall' : 'square' };
  }
  const minSize = id => MIN[id] || [1, 1];

  const overlaps = (a, b) => a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h;
  const fits = (r, items) => r.x >= 0 && r.y >= 0 && r.x + r.w <= COLS && r.y + r.h <= ROWS && !items.some(i => i !== r && overlaps(i, r));

  // saved layout -> clean list: known widgets, inside the grid, no overlaps (later ones lose)
  function normalizeItems(items) {
    const out = [];
    for (const raw of Array.isArray(items) ? items : DEFAULT_ITEMS) {
      if (!WIDGETS.includes(raw?.id) || out.some(i => i.id === raw.id)) continue;
      const [mw, mh] = minSize(raw.id);  // a card is never smaller than its smallest readable size
      const w = Math.max(mw, Math.min(COLS, Math.round(+raw.w || 1))), h = Math.max(mh, Math.min(ROWS, Math.round(+raw.h || 1)));
      const r = { id: raw.id, w, h, x: Math.max(0, Math.min(COLS - w, Math.round(+raw.x || 0))), y: Math.max(0, Math.min(ROWS - h, Math.round(+raw.y || 0))) };
      if (fits(r, out)) out.push(r);
    }
    return out;
  }

  function freeSpot(items, sizes) {
    for (const [w, h] of sizes)
      for (let y = 0; y + h <= ROWS; y++)
        for (let x = 0; x + w <= COLS; x++) { const r = { x, y, w, h }; if (fits(r, items)) return r; }
    return null;
  }

  // Room for a card that was moved or resized onto others. It behaves like pushing through a crowd:
  //  1. the cards in the way slide in the direction of the drag, each pushing the next one along;
  //  2. if a wall stops that, they slip back past the dragged card into the place it came from (a swap);
  //  3. if there is no room for that either, they are squeezed against the wall, never below their smallest size;
  //  4. only as a last resort a card jumps to the nearest free place.
  // `from` is where the card was before the drag (it tells the direction). Returns the new list in the same
  // order, or null when the cards cannot all fit.
  function makeRoom(items, moved, from) {
    if (moved.x < 0 || moved.y < 0 || moved.x + moved.w > COLS || moved.y + moved.h > ROWS) return null;
    from = from || items.find(i => i.id === moved.id) || moved;
    if (!items.some(i => i.id !== moved.id && overlaps(i, moved))) return items.map(i => i.id === moved.id ? { ...moved } : { ...i });
    // direction of the drag: the centre moved, or the side that grew
    const dx = (moved.x + moved.w / 2) - (from.x + from.w / 2), dy = (moved.y + moved.h / 2) - (from.y + from.h / 2);
    const main = Math.abs(dx) * COL_UNITS >= Math.abs(dy) ? [Math.sign(dx) || 1, 0] : [0, Math.sign(dy) || 1];
    const side = main[0] ? (dy ? [0, Math.sign(dy)] : null) : (dx ? [Math.sign(dx), 0] : null);
    const back = [-main[0], -main[1]];
    const across = main[0] ? [[0, 1], [0, -1]] : [[1, 0], [-1, 0]];
    const dirs = [main, side, back, ...across].filter(Boolean).filter((d, i, all) => all.findIndex(o => o[0] === d[0] && o[1] === d[1]) === i);
    for (const squeeze of [false, true])
      for (const dir of dirs) { const got = pushAll(items, moved, dir, squeeze); if (got) return got; }
    return nearestRoom(items, moved);
  }

  // every card touched moves just past the one that pushed it, in one direction; with `squeeze` a card that
  // reaches the wall gets shorter instead of failing
  function pushAll(items, moved, [dx, dy], squeeze) {
    const out = items.map(i => i.id === moved.id ? { ...moved } : { ...i });
    const queue = [out.find(i => i.id === moved.id)];
    for (let guard = 0; queue.length; guard++) {
      if (guard > 60) return null;
      const a = queue.shift();
      for (const c of out) {
        if (c === a || c.id === moved.id || !overlaps(a, c)) continue;
        if (dx > 0) c.x = a.x + a.w; else if (dx < 0) c.x = a.x - c.w; else if (dy > 0) c.y = a.y + a.h; else c.y = a.y - c.h;
        const [mw, mh] = minSize(c.id);
        if (c.x < 0) { if (!squeeze) return null; c.w += c.x; c.x = 0; }
        if (c.y < 0) { if (!squeeze) return null; c.h += c.y; c.y = 0; }
        if (c.x + c.w > COLS) { if (!squeeze) return null; c.w = COLS - c.x; }
        if (c.y + c.h > ROWS) { if (!squeeze) return null; c.h = ROWS - c.y; }
        if (c.w < mw || c.h < mh) return null;
        queue.push(c);
      }
    }
    return out.every((p, i) => out.every((q, j) => i >= j || !overlaps(p, q))) ? out : null;
  }

  // last resort: each covered card goes to the nearest free place, shrinking only if it must
  function nearestRoom(items, moved) {
    const out = items.map(i => i.id === moved.id ? { ...moved } : { ...i });
    const placed = out.filter(i => i.id === moved.id || !overlaps(i, moved));
    const pushed = out.filter(i => i.id !== moved.id && overlaps(i, moved)).sort((a, b) => b.w * b.h - a.w * a.h);
    for (const card of pushed) {
      const [mw, mh] = minSize(card.id);
      let best = null;
      for (let w = card.w; w >= Math.min(mw, card.w); w--)
        for (let h = card.h; h >= Math.min(mh, card.h); h--)
          for (let y = 0; y + h <= ROWS; y++)
            for (let x = 0; x + w <= COLS; x++) {
              const r = { id: card.id, x, y, w, h };
              if (placed.some(o => overlaps(o, r))) continue;
              const cost = (card.w * card.h - w * h) * 100 + Math.abs(x - card.x) + Math.abs(y - card.y) * 1.01 - (y > card.y ? .5 : 0);
              if (!best || cost < best[0]) best = [cost, r];
            }
      if (!best) return null;
      Object.assign(card, best[1]);
      placed.push(card);
    }
    return out;
  }

  // a card dropped at cell (x, y): the biggest of `sizes` that fits with that cell inside it,
  // preferring the position centred on the drop point
  function spotAt(items, x, y, sizes = [[3, 3], [3, 2], [2, 3], [2, 2], [2, 1], [1, 2], [1, 1]]) {
    for (const [w, h] of sizes) {
      const options = [];
      for (let oy = y - h + 1; oy <= y; oy++)
        for (let ox = x - w + 1; ox <= x; ox++) {
          const r = { x: ox, y: oy, w, h };
          if (fits(r, items)) options.push([Math.abs(ox + (w - 1) / 2 - x) + Math.abs(oy + (h - 1) / 2 - y), r]);
        }
      if (options.length) return options.sort((p, q) => p[0] - q[0])[0][1];
    }
    return null;
  }

  // widgets put away in the drawer (display.layout.hidden): enabled or not, they get no card
  const hiddenIds = layout => (Array.isArray(layout?.hidden) ? layout.hidden : []).filter(id => WIDGETS.includes(id));

  // Which widgets are shown and where. `present` = widgets that have an enabled module.
  // Missing widgets get a free spot (or half of the biggest card); then cards grow into
  // holes left by switched-off widgets, so the screen never has empty gaps.
  function place(layout, present, fill = true) {
    const hidden = hiddenIds(layout);
    present = present.filter(id => !hidden.includes(id));
    const items = normalizeItems(layout?.items).filter(i => present.includes(i.id));
    for (const id of WIDGETS.filter(w => present.includes(w) && !items.some(i => i.id === w))) {
      let spot = freeSpot(items, [[3, 3], [2, 3], [3, 2], [2, 2], [1, 2], [2, 1], [1, 1]]);
      if (!spot) {
        const big = [...items].filter(i => i.w > 1 || i.h > 1).sort((a, b) => b.w * b.h - a.w * a.h)[0];
        if (!big) continue;
        if (big.w >= big.h || big.h === 1) { const w = Math.floor(big.w / 2); spot = { x: big.x + big.w - w, y: big.y, w, h: big.h }; big.w -= w; }
        else { const h = Math.floor(big.h / 2); spot = { x: big.x, y: big.y + big.h - h, w: big.w, h }; big.h -= h; }
      }
      items.push({ id, ...spot });
    }
    // grow sideways first (a row keeps its height), then downwards / upwards
    if (fill) for (const steps of [[[0, 0, 1, 0], [-1, 0, 1, 0]], [[0, 0, 0, 1], [0, -1, 0, 1]]]) {
      for (let grew = true; grew;) {
        grew = false;
        for (const i of items) {
          for (const [dx, dy, dw, dh] of steps) {
            const r = { id: i.id, x: i.x + dx, y: i.y + dy, w: i.w + dw, h: i.h + dh };
            if (fits(r, items.filter(o => o !== i))) { Object.assign(i, r); grew = true; }
          }
        }
      }
    }
    return items;
  }

  // ---------- context modes: one tap swaps the whole panel for what you're doing ----------
  // Built-in layouts; editing the panel while a mode is on stores your own version of it in
  // display.modes[<mode>]. "" = the user's own layout (display.layout).
  const MODES = {
    focus: { label: '專注', hint: '時鐘、計時與 AI 用量', items: [
      { id: 'clock', x: 0, y: 0, w: 4, h: 4 }, { id: 'weather', x: 4, y: 0, w: 2, h: 4 },
      { id: 'tokens', x: 0, y: 4, w: 4, h: 4 }, { id: 'companion', x: 4, y: 4, w: 2, h: 4 }] },
    print: { label: '列印', hint: '列印機放大，角色報告進度', items: [
      { id: 'bambu', x: 0, y: 0, w: 4, h: 8 }, { id: 'companion', x: 4, y: 0, w: 2, h: 4 },
      { id: 'tokens', x: 4, y: 4, w: 2, h: 4 }] },
    rest: { label: '休息', hint: '音樂、天氣與音量', items: [
      { id: 'media', x: 0, y: 0, w: 4, h: 6 }, { id: 'system', x: 0, y: 6, w: 4, h: 2 },
      { id: 'clock', x: 4, y: 0, w: 2, h: 3 }, { id: 'weather', x: 4, y: 3, w: 2, h: 3 },
      { id: 'companion', x: 4, y: 6, w: 2, h: 2 }] },
  };
  const MODE_ORDER = ['', 'focus', 'print', 'rest'];
  const withHidden = items => ({ items, hidden: WIDGETS.filter(w => !items.some(i => i.id === w)) });
  const modeName = mode => (MODES[mode] ? mode : '');

  // The mode in effect: the chosen one, except that with "auto" a running print brings up the
  // print layout. `override` is a manual pick made while auto was in charge (kept until the
  // printer starts or stops again).
  function effectiveMode(display = {}, printing = false, override) {
    if (override != null) return modeName(override);
    if (display.auto_mode && printing) return 'print';
    return modeName(display.mode);
  }
  // {items, hidden} to draw for a mode: the user's edited version, else the built-in one
  function layoutFor(display = {}, mode = '') {
    mode = modeName(mode);
    if (!mode) return display.layout;
    const own = display.modes?.[mode];
    return own && Array.isArray(own.items) ? own : withHidden(MODES[mode].items);
  }

  // ---------- layout packs: a shareable file with layouts, modes and colours (never modules,
  // so it can't carry an access code or an API key) ----------
  const PACK_FORMAT = 'deskmon-layout/1';
  const cleanLayout = l => l && Array.isArray(l.items)
    ? { items: normalizeItems(l.items), hidden: hiddenIds(l).filter(id => !normalizeItems(l.items).some(i => i.id === id)) } : null;
  const HEX = /^#[0-9a-f]{6}$/i;
  // ---------------------------------------------------------------- theme
  // Every colour the panel uses comes from here (and the matching defaults in style.css :root).
  // Theme = background + card shape. One theme colour for everything; a card may carry its own.
  //   {background: name | "#hex", shape, accent: "#hex",
  //    cards: {bambu|media|weather|companion: "#hex", codex|claude: ["#left", "#right"]},
  //    modes: {focus|print|rest: "#hex"}        theme colour while that mode is on
  //    night: {on, from, to, background}        another background between two hours
  //    cover: "" | "card" | "theme"}            take the colour from the album cover
  // Older configs have no `accent` and store per-card colours as printer / music / codex / claude:
  // those are read as "every card has its own colour", so nothing changes until a theme colour is chosen.
  const BACKGROUNDS = {
    graphite: { label: '石墨', bg: '#0b0c0e', card: '#141519', line: '#23252b' },
    oled: { label: '純黑 OLED', bg: '#000000', card: '#0c0c0e', line: '#1a1a1e' },
    navy: { label: '深海藍', bg: '#070b14', card: '#0f1626', line: '#1c2740' },
    warm: { label: '暖木', bg: '#100d0b', card: '#1a1613', line: '#2b241f' },
    paper: { label: '紙白', bg: '#eceae4', card: '#faf9f6', line: '#d7d3c9' },
    mist: { label: '霧藍', bg: '#e4e9f0', card: '#f6f8fb', line: '#cfd6e0' },
  };
  // text and state colours for dark and for light backgrounds
  const INK = {
    dark: { text: '#ecebe6', soft: '#b4b8c2', dim: '#8a8b90', faint: '#4a4c53', on: '#ffffff', ok: '#6fdc8c', idle: '#6b6d74', err: '#ff6b6b', warn: '#ffd27a' },
    light: { text: '#1c1d21', soft: '#44464e', dim: '#62646c', faint: '#a6a8af', on: '#000000', ok: '#1c8f4e', idle: '#8b8d94', err: '#d0342c', warn: '#9a6a00' },
  };
  const WHITE = '#ffffff', BLACK = '#000000';
  const SHAPES = ['round', 'soft', 'cut'];
  const CARD_COLORS = { bambu: 1, media: 1, weather: 1, companion: 1, codex: 2, claude: 2 };  // colours each card takes
  const CLASSIC = { bambu: '#f2a541', media: '#7ee0b5', weather: '#7cc4ff', codex: ['#4f7dff', '#c46bff'], claude: ['#ff9a3c', '#e8662a'] };
  const ACCENTS = { '#f2a541': '橘色', '#7ee0b5': '薄荷綠', '#7cc4ff': '天藍', '#b49bff': '紫色', '#ff8fa3': '粉紅', '#d8d8d8': '灰白' };
  // ready-made sets of card colours (every card gets its own colour)
  const PALETTES = {
    '經典多色': CLASSIC,
    '霓虹': { bambu: '#ffd23f', media: '#3cf0c8', weather: '#7cc4ff', codex: ['#00c6ff', '#a64dff'], claude: ['#ff4d8d', '#ff9e3d'] },
    '柔和': { bambu: '#e9b872', media: '#9fd8b8', weather: '#a9cfee', codex: ['#8aa6ff', '#b9a2ff'], claude: ['#f2a37d', '#e98b6b'] },
  };
  const COVER = ['', 'card', 'theme'];
  const MOTIONS = ['bouncy', 'calm', 'off'];   // Q 彈, plain, none
  const STYLES = { flat: '預設', glass: '毛玻璃', material: 'Material' };   // how surfaces are drawn
  const isColor = (v, n) => n === 1 ? HEX.test(v) : Array.isArray(v) && v.length === 2 && v.every(c => HEX.test(c));
  function cleanCards(c) {
    const out = {};
    for (const [k, n] of Object.entries(CARD_COLORS)) if (c && isColor(c[k], n)) out[k] = n === 1 ? c[k] : [...c[k]];
    return out;
  }
  const rgb = h => [1, 3, 5].map(i => parseInt(h.slice(i, i + 2), 16));
  const hex = c => '#' + c.map(v => Math.max(0, Math.min(255, Math.round(v))).toString(16).padStart(2, '0')).join('');
  const mix = (a, b, t) => { const x = rgb(a), y = rgb(b); return hex(x.map((v, i) => v + (y[i] - v) * t)); };
  const luminance = h => { const [r, g, b] = rgb(h).map(v => { v /= 255; return v <= .03928 ? v / 12.92 : ((v + .055) / 1.055) ** 2.4; }); return .2126 * r + .7152 * g + .0722 * b; };
  // the surfaces for a background: a built-in name, or any colour (card and line are worked out from it)
  function surface(background) {
    const named = BACKGROUNDS[background];
    const bg = named ? named.bg : HEX.test(background) ? background.toLowerCase() : BACKGROUNDS.graphite.bg;
    const light = luminance(bg) > .4;
    const base = named || (HEX.test(background) ? { bg, card: mix(bg, WHITE, light ? .6 : .055), line: mix(bg, light ? BLACK : WHITE, light ? .13 : .11) } : BACKGROUNDS.graphite);
    return { bg: base.bg, card: base.card, line: base.line, light, ...INK[light ? 'light' : 'dark'] };
  }
  const hsl = h => { const [r, g, b] = rgb(h).map(v => v / 255), mx = Math.max(r, g, b), mn = Math.min(r, g, b), l = (mx + mn) / 2, d = mx - mn;
    if (!d) return [0, 0, l];
    const s = d / (1 - Math.abs(2 * l - 1)), hh = mx === r ? ((g - b) / d) % 6 : mx === g ? (b - r) / d + 2 : (r - g) / d + 4;
    return [(hh * 60 + 360) % 360, s, l]; };
  const fromHsl = (h, s, l) => { const c = (1 - Math.abs(2 * l - 1)) * s, x = c * (1 - Math.abs((h / 60) % 2 - 1)), m = l - c / 2;
    const [r, g, b] = h < 60 ? [c, x, 0] : h < 120 ? [x, c, 0] : h < 180 ? [0, c, x] : h < 240 ? [0, x, c] : h < 300 ? [x, 0, c] : [c, 0, x];
    return hex([r, g, b].map(v => (v + m) * 255)); };
  // same hue, pushed to a lightness that reads on the background
  function readable(color, light) {
    const [h, s, l] = hsl(color);
    return fromHsl(h, Math.min(.85, s), light ? Math.min(.42, Math.max(.3, l)) : Math.min(.78, Math.max(.62, l)));
  }
  // on a light background a pale colour can't be read: darken it, keep its hue
  const onLight = c => { const [h, sat, l] = hsl(c); return l > .45 ? fromHsl(h, Math.min(sat, .62), .45) : c; };
  // the colour of a picture, from RGBA pixels: the average of its colourful pixels (grey ones barely count)
  function pictureColor(pixels) {
    let r = 0, g = 0, b = 0, n = 0;
    for (let i = 0; i + 3 < pixels.length; i += 4) {
      if (pixels[i + 3] < 128) continue;
      const mx = Math.max(pixels[i], pixels[i + 1], pixels[i + 2]), mn = Math.min(pixels[i], pixels[i + 1], pixels[i + 2]);
      const w = ((mx - mn) / 255) ** 2 + .003;
      r += pixels[i] * w; g += pixels[i + 1] * w; b += pixels[i + 2] * w; n += w;
    }
    return n ? hex([r / n, g / n, b / n]) : null;
  }
  const hourIn = (h, from, to) => from === to ? false : from < to ? h >= from && h < to : h >= from || h < to;
  const cleanHour = (v, d) => Number.isFinite(+v) && v !== '' && v != null ? Math.max(0, Math.min(23, Math.floor(+v))) : d;
  const cleanBackground = v => BACKGROUNDS[v] ? v : HEX.test(v) ? v.toLowerCase() : null;
  function cleanNight(n) {
    if (!n || typeof n !== 'object') return null;
    return { on: !!n.on, from: cleanHour(n.from, 22), to: cleanHour(n.to, 7), background: cleanBackground(n.background) || 'oled' };
  }
  function cleanModes(m) {
    const out = {};
    for (const k of Object.keys(MODES)) if (m && HEX.test(m[k])) out[k] = m[k].toLowerCase();
    return out;
  }
  // a picture behind the cards: {v: version of the uploaded file, dim: 0-90 % of page colour over it, blur: 0-40 px}
  function cleanImage(i) {
    if (!i || typeof i !== 'object' || !/^[0-9a-z]{1,24}$/i.test(String(i.v || ''))) return null;
    const n = (v, d, max) => Number.isFinite(+v) && v !== '' && v != null ? Math.max(0, Math.min(max, Math.round(+v))) : d;
    return { v: String(i.v), dim: n(i.dim, 35, 90), blur: n(i.blur, 0, 40) };
  }
  // What the panel paints at a moment: now = {mode, hour, cover}
  //   {background, shape, accent, legacy, cards (own colours as stored), shown (own colours right now),
  //    colors (every card), surface, modes, night, cover, base (the stored theme colour)}
  function resolveTheme(t, now = {}) {
    t = t && typeof t === 'object' ? t : {};
    const legacy = !HEX.test(t.accent);
    const old = cleanCards({ bambu: t.printer, media: t.music, codex: t.codex, claude: t.claude });
    const cards = { ...(legacy ? { ...CLASSIC, ...old } : {}), ...cleanCards(t.cards) };
    const modes = cleanModes(t.modes), night = cleanNight(t.night), cover = COVER.includes(t.cover) ? t.cover : '';
    const background = cleanBackground(t.background) || 'graphite';
    const atNight = !!(night?.on && Number.isFinite(now.hour) && hourIn(now.hour, night.from, night.to));
    const surf = surface(atNight ? night.background : background);
    const picture = HEX.test(now.cover) && cover ? readable(now.cover, surf.light) : null;
    const fit = c => !surf.light ? c : Array.isArray(c) ? c.map(onLight) : onLight(c);
    const shown = {};
    for (const k of Object.keys(cards)) shown[k] = fit(cards[k]);
    if (picture && cover === 'card') shown.media = picture;
    const base = legacy ? cards.bambu : t.accent.toLowerCase();
    const accent = fit((picture && cover === 'theme' ? picture : modes[now.mode]) || base);
    const colors = {};
    for (const [k, n] of Object.entries(CARD_COLORS)) colors[k] = shown[k] || (n === 1 ? accent : [accent, mix(accent, surf.light ? BLACK : WHITE, .45)]);
    const motion = MOTIONS.includes(t.motion) ? t.motion : 'bouncy', style = STYLES[t.style] ? t.style : 'flat', image = cleanImage(t.image);
    return { background, shape: SHAPES.includes(t.shape) ? t.shape : 'round', motion, style, image, accent, legacy, cards, shown, colors, surface: surf, modes, night, cover, base };
  }
  // the theme as it is stored (what settings saves): no leftovers from older formats
  function storedTheme(t) {
    const r = resolveTheme(t), out = { background: r.background, shape: r.shape, style: r.style, motion: r.motion, accent: r.base, cards: JSON.parse(JSON.stringify(r.cards)) };
    if (Object.keys(r.modes).length) out.modes = r.modes;
    if (r.night) out.night = r.night;
    if (r.cover) out.cover = r.cover;
    if (r.image) out.image = r.image;
    return out;
  }
  function cleanTheme(t) {
    if (!t || typeof t !== 'object') return null;
    const out = {};
    if (cleanBackground(t.background)) out.background = cleanBackground(t.background);
    if (SHAPES.includes(t.shape)) out.shape = t.shape;
    if (MOTIONS.includes(t.motion)) out.motion = t.motion;
    if (STYLES[t.style]) out.style = t.style;
    if (HEX.test(t.accent)) out.accent = t.accent;
    if (Object.keys(cleanCards(t.cards)).length) out.cards = cleanCards(t.cards);
    if (Object.keys(cleanModes(t.modes)).length) out.modes = cleanModes(t.modes);
    if (cleanNight(t.night)) out.night = cleanNight(t.night);
    if (COVER.includes(t.cover) && t.cover) out.cover = t.cover;
    for (const k of ['printer', 'music']) if (HEX.test(t[k])) out[k] = t[k];
    for (const k of ['codex', 'claude']) if (Array.isArray(t[k]) && t[k].length === 2 && t[k].every(c => HEX.test(c))) out[k] = [...t[k]];
    return Object.keys(out).length ? out : null;
  }
  function exportPack(config = {}, name = '我的版面') {
    const d = config.display || {}, pack = { format: PACK_FORMAT, name: String(name).slice(0, 40) };
    if (cleanLayout(d.layout)) pack.layout = cleanLayout(d.layout);
    const modes = {};
    for (const m of Object.keys(MODES)) if (cleanLayout(d.modes?.[m])) modes[m] = cleanLayout(d.modes[m]);
    if (Object.keys(modes).length) pack.modes = modes;
    if (cleanTheme(config.theme)) pack.theme = cleanTheme(config.theme);
    if (Number.isFinite(+d.text_scale)) pack.text_scale = Math.max(.8, Math.min(1.4, +d.text_scale));
    return pack;
  }
  // Checks a pack and returns only what it may change: {name, display: {...}, theme}. Throws
  // with a readable reason. Unknown keys (modules, credentials, anything else) are ignored.
  function importPack(pack) {
    if (!pack || typeof pack !== 'object' || Array.isArray(pack)) throw new Error('不是版面包（需要 JSON 物件）');
    if (pack.format !== PACK_FORMAT) throw new Error(`不支援的格式：${String(pack.format).slice(0, 30)}（需要 ${PACK_FORMAT}）`);
    const display = {};
    const layout = cleanLayout(pack.layout);
    if (pack.layout && !layout?.items.length) throw new Error('版面裡沒有可用的小工具');
    if (layout) display.layout = layout;
    const modes = {};
    for (const m of Object.keys(MODES)) { const l = cleanLayout(pack.modes?.[m]); if (l?.items.length) modes[m] = l; }
    if (Object.keys(modes).length) display.modes = modes;
    if (Number.isFinite(+pack.text_scale)) display.text_scale = Math.max(.8, Math.min(1.4, +pack.text_scale));
    const theme = cleanTheme(pack.theme);
    if (!Object.keys(display).length && !theme) throw new Error('版面包是空的');
    return { name: String(pack.name || '版面包').slice(0, 40), display, theme };
  }

  root.DeskMonLayout = { settings, calculate, panelDisplays, COLS, ROWS, WIDGETS, DEFAULT_ITEMS, normalizeItems, place, overlaps, fits, freeSpot, spotAt, hiddenIds,
    MODES, MODE_ORDER, effectiveMode, layoutFor, withHidden, PACK_FORMAT, exportPack, importPack,
    COL_UNITS, MIN, minSize, cardSize, makeRoom, MOTIONS, STYLES, cleanImage, SHAPES, CARD_COLORS, CLASSIC, ACCENTS, PALETTES, BACKGROUNDS, INK, resolveTheme, storedTheme, cleanTheme, surface, readable, pictureColor };
})(globalThis);
