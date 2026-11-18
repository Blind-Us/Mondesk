const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
require('../web/layout.js');
const L = globalThis.DeskMonLayout;
const {videoPath} = require('../web/media-route.js');

const ALL = L.WIDGETS;
const noOverlap = items => items.every((a, i) => items.every((b, j) => i >= j || !L.overlaps(a, b)));

test('every built-in mode is a valid layout that fills the screen', () => {
  for (const [name, mode] of Object.entries(L.MODES)) {
    assert.deepEqual(L.normalizeItems(mode.items), mode.items, name);  // nothing clipped or dropped
    const placed = L.place(L.layoutFor({}, name), ALL);
    assert.ok(noOverlap(placed), name);
    assert.equal(placed.reduce((n, i) => n + i.w * i.h, 0), L.COLS * L.ROWS, name + ' leaves a hole');
    assert.deepEqual(placed.map(i => i.id).sort(), mode.items.map(i => i.id).sort(), name + ' shows a hidden widget');
  }
});

test('a mode only shows widgets whose module is on; without fill the gap stays empty', () => {
  const placed = L.place(L.layoutFor({}, 'print'), ['bambu', 'tokens'], false);  // no Companion configured
  assert.deepEqual(placed.map(i => i.id).sort(), ['bambu', 'tokens']);
  assert.deepEqual(placed.find(i => i.id === 'bambu'), L.MODES.print.items.find(i => i.id === 'bambu'));  // nothing grew
  assert.ok(placed.reduce((n, i) => n + i.w * i.h, 0) < L.COLS * L.ROWS);
});

test('mode in effect: chosen mode, auto print while printing, manual override wins', () => {
  assert.equal(L.effectiveMode({}), '');
  assert.equal(L.effectiveMode({mode: 'focus'}), 'focus');
  assert.equal(L.effectiveMode({mode: 'party'}), '');                       // unknown: the user's own layout
  assert.equal(L.effectiveMode({mode: 'focus', auto_mode: true}, true), 'print');
  assert.equal(L.effectiveMode({mode: 'focus', auto_mode: false}, true), 'focus');
  assert.equal(L.effectiveMode({mode: 'focus', auto_mode: true}, true, 'rest'), 'rest');
  assert.equal(L.effectiveMode({mode: 'focus', auto_mode: true}, true, ''), '');  // override back to "own layout"
});

test("an edited mode replaces the built-in one; no mode means the user's layout", () => {
  const own = {items: [{id: 'clock', x: 0, y: 0, w: 6, h: 8}], hidden: []};
  const display = {layout: {items: [{id: 'media', x: 0, y: 0, w: 6, h: 8}]}, modes: {focus: own}};
  assert.equal(L.layoutFor(display, 'focus'), own);
  assert.equal(L.layoutFor(display, ''), display.layout);
  assert.deepEqual(L.layoutFor(display, 'rest').items, L.MODES.rest.items);
});

test('an exported pack carries layouts and colours, never modules or secrets', () => {
  const config = {
    display: {layout: {items: [{id: 'media', x: 0, y: 0, w: 6, h: 8}], hidden: ['bambu']}, modes: {focus: {items: L.MODES.focus.items}},
      text_scale: 1.1, mode: 'focus', width: 960},
    theme: {background: 'navy', printer: '#ff0000', codex: ['#111111', '#222222'], evil: '<script>'},
    modules: [{id: 'printer', type: 'bambu', access_code: '12345678'}, {id: 'companion', api_key: 'sk-ant-secret'}],
  };
  const pack = L.exportPack(config, '我的版面');
  const text = JSON.stringify(pack);
  assert.equal(pack.format, 'deskmon-layout/1');
  assert.ok(!/12345678|sk-ant|access_code|api_key|modules|script/.test(text), text);
  assert.deepEqual(Object.keys(pack).sort(), ['format', 'layout', 'modes', 'name', 'text_scale', 'theme']);
  const back = L.importPack(JSON.parse(text));  // an export imports again
  assert.deepEqual(back.display.layout, pack.layout);
  assert.deepEqual(back.theme, {background: 'navy', printer: '#ff0000', codex: ['#111111', '#222222']});
});

test('importing keeps only what a pack may change and explains what is wrong', () => {
  const got = L.importPack({format: 'deskmon-layout/1', name: 'x'.repeat(99),
    layout: {items: [{id: 'media', x: 0, y: 0, w: 99, h: 99}, {id: 'nope', x: 0, y: 0, w: 1, h: 1}, {id: 'clock', x: 0, y: 0, w: 1, h: 1}]},
    modes: {focus: {items: [{id: 'clock', x: 0, y: 0, w: 2, h: 2}]}, hacked: {items: []}},
    theme: {printer: 'red; background:url(x)'}, modules: [{type: 'bambu', ip: '10.0.0.1'}], text_scale: 9});
  assert.equal(got.name.length, 40);
  assert.deepEqual(got.display.layout.items, [{id: 'media', w: 6, h: 8, x: 0, y: 0}]);  // clipped; unknown + overlapping dropped
  assert.deepEqual(Object.keys(got.display.modes), ['focus']);
  assert.equal(got.display.text_scale, 1.4);
  assert.equal(got.theme, null);
  assert.ok(!('modules' in got) && !('modules' in got.display));
  for (const [bad, reason] of [[null, /JSON/], [[], /JSON/], [{format: 'other/2'}, /不支援/], [{format: 'deskmon-layout/1'}, /空的/],
    [{format: 'deskmon-layout/1', layout: {items: [{id: 'nope'}]}}, /沒有可用/]])
    assert.throws(() => L.importPack(bad), reason);
});

test('the three shipped templates are valid packs', () => {
  const dir = path.join(__dirname, '..', 'web', 'layouts');
  const files = fs.readdirSync(dir).filter(f => f.endsWith('.json')).sort();
  assert.deepEqual(files, ['focus.json', 'media.json', 'print.json']);
  for (const f of files) {
    const raw = JSON.parse(fs.readFileSync(path.join(dir, f), 'utf8'));
    const got = L.importPack(raw);
    assert.deepEqual(got.display.layout.items, raw.layout.items, f);  // nothing had to be fixed
    assert.deepEqual(Object.keys(raw).sort(), ['format', 'layout', 'name'], f);
  }
});

test('video path: YouTube is played in step, other sites are mirrored, a gone source stops both', () => {
  const yt = {title: 'v', video: true, browser_bridge: true, track: 'youtube:abcdefghijk'};
  assert.equal(videoPath(yt), 'sync');
  assert.equal(videoPath(yt, new Set(['abcdefghijk'])), 'mirror');           // embedding refused: fall back
  assert.equal(videoPath({...yt, track: 'web:Some title:212'}), 'mirror');
  assert.equal(videoPath({...yt, track: 'youtube:short'}), 'mirror');
  assert.equal(videoPath({...yt, track: 'bilibili:BV14uWC6bEz2'}), 'sync');   // Bilibili is played by the panel too
  assert.equal(videoPath({...yt, track: 'bilibili:BV14uWC6bEz2:2'}, new Set(['BV14uWC6bEz2:2'])), 'mirror');
  assert.equal(videoPath({}), 'none');                                        // tab closed
  assert.equal(videoPath({...yt, title: ''}), 'none');
  assert.equal(videoPath({...yt, video: false}), 'none');                     // back to music
  assert.equal(videoPath({...yt, browser_bridge: false}), 'none');            // OS info only: nothing to show
});

test('theme: one colour for every card, cards may override, old configs keep their colours', () => {
  const old = L.resolveTheme({background: 'navy', printer: '#ff0000', codex: ['#111111', '#222222']});
  assert.equal(old.legacy, true);
  assert.equal(old.accent, '#ff0000');                                   // the printer colour was the accent
  assert.deepEqual(old.colors, {...L.CLASSIC, bambu: '#ff0000', codex: ['#111111', '#222222'], companion: '#ff0000'});
  assert.deepEqual(Object.keys(old.cards).sort(), Object.keys(L.CLASSIC).sort());        // the cards that had colours keep them
  const mono = L.resolveTheme({accent: '#7CC4FF', shape: 'cut', printer: '#ff0000', cards: {media: '#00ff00', codex: 'red', nope: '#000000'}});
  assert.deepEqual([mono.legacy, mono.shape, mono.background, mono.accent], [false, 'cut', 'graphite', '#7cc4ff']);
  assert.deepEqual(mono.cards, {media: '#00ff00'});                      // bad values and unknown cards dropped, old keys ignored
  assert.equal(mono.colors.bambu, '#7cc4ff');
  assert.equal(mono.colors.media, '#00ff00');
  assert.equal(mono.colors.codex[0], '#7cc4ff');
  assert.match(mono.colors.codex[1], /^#[0-9a-f]{6}$/);                  // a lighter step of the same colour
  assert.equal(L.resolveTheme({shape: 'blob'}).shape, 'round');
  assert.equal(L.resolveTheme(null).background, 'graphite');
  const pack = L.importPack(L.exportPack({theme: {accent: '#112233', shape: 'soft', cards: {weather: '#445566'}, evil: 'x'}}));
  assert.deepEqual(pack.theme, {shape: 'soft', accent: '#112233', cards: {weather: '#445566'}});
});

test('theme: light and custom backgrounds, mode colours, night background, cover colour', () => {
  assert.equal(L.surface('graphite').light, false);
  const paper = L.surface('paper');
  assert.deepEqual([paper.light, paper.on, paper.text], [true, L.INK.light.on, L.INK.light.text]);
  const own = L.surface('#F0E8D8');                                       // any colour: card and line are derived
  assert.equal(own.bg, '#f0e8d8');
  assert.ok(own.light && /^#[0-9a-f]{6}$/.test(own.card) && own.card !== own.bg && own.line !== own.bg);
  assert.equal(L.surface('nonsense').bg, L.BACKGROUNDS.graphite.bg);

  const t = {accent: '#7cc4ff', background: 'paper', modes: {focus: '#ff0000', party: '#00ff00', rest: 'red'},
    night: {on: true, from: 22, to: 7, background: 'oled'}, cover: 'card', cards: {weather: '#123456'}};
  const d = {...t, background: 'navy'};
  assert.equal(L.resolveTheme(d, {mode: 'focus', hour: 12}).accent, '#ff0000');
  assert.equal(L.resolveTheme(d, {mode: 'rest', hour: 12}).accent, '#7cc4ff');      // bad colour: the theme colour
  assert.equal(L.resolveTheme(d, {mode: 'focus', hour: 12}).colors.weather, '#123456');  // a card's own colour stays
  const day = L.resolveTheme(t, {hour: 12}), lum = h => [1, 3, 5].reduce((n, i) => n + parseInt(h.slice(i, i + 2), 16), 0) / 765;
  assert.ok(lum(day.accent) < lum('#7cc4ff'), 'a pale theme colour is darkened on a light background');
  assert.equal(day.base, '#7cc4ff');                                               // …but stored as chosen
  assert.equal(day.colors.weather, '#123456');                                     // already dark enough: untouched
  assert.deepEqual([12, 22, 23, 3, 6, 7].map(h => L.resolveTheme(t, {hour: h}).surface.light), [true, false, false, false, false, true]);
  assert.equal(L.resolveTheme({...t, night: {...t.night, on: false}}, {hour: 23}).surface.light, true);

  const card = L.resolveTheme(d, {hour: 12, cover: '#203060'});
  assert.notEqual(card.colors.media, '#7cc4ff');
  assert.equal(card.accent, '#7cc4ff');                                    // "card": only the music card follows the cover
  assert.equal(card.cards.media, undefined);                               // …and it is not stored as the card's own colour
  const whole = L.resolveTheme({...d, cover: 'theme'}, {mode: 'focus', hour: 12, cover: '#203060'});
  assert.equal(whole.accent, whole.colors.bambu);
  assert.notEqual(whole.accent, '#ff0000');                                // the cover wins over the mode colour
  assert.equal(L.resolveTheme({...d, cover: ''}, {cover: '#203060'}).colors.media, '#7cc4ff');
  assert.ok(lum(L.readable('#101830', false)) > .45, 'a dark cover is lifted on a dark background');
  assert.ok(lum(L.readable('#f4e9c0', true)) < .55, 'a pale cover is darkened on a light background');
  assert.equal(L.pictureColor([200, 30, 30, 255, 128, 128, 128, 255, 128, 128, 128, 255, 0, 0, 0, 0]), '#c71f1f');  // grey barely counts
  assert.equal(L.pictureColor([]), null);

  const stored = L.storedTheme({printer: '#ff0000', music: '#00ff00', junk: 1});   // an old config, saved again
  assert.deepEqual(Object.keys(stored).sort(), ['accent', 'background', 'cards', 'motion', 'shape', 'style']);
  assert.deepEqual(L.resolveTheme(stored).colors, L.resolveTheme({printer: '#ff0000', music: '#00ff00'}).colors);
  const pack = L.importPack(L.exportPack({theme: t}));
  assert.deepEqual(pack.theme.modes, {focus: '#ff0000'});
  assert.deepEqual(pack.theme.night, t.night);
  assert.equal(pack.theme.cover, 'card');
});

test('no colour is written outside the theme: style sheets keep literals in their first :root block only', () => {
  const colour = /#[0-9a-fA-F]{3,8}\b(?![\w-])/g;
  for (const file of ['style.css', 'settings.css']) {
    const css = fs.readFileSync(path.join(__dirname, '..', 'web', file), 'utf8');
    const rest = css.slice(css.indexOf('}', css.indexOf(':root')) + 1).replace(/\/\*[\s\S]*?\*\//g, '');
    const found = (rest.match(colour) || []).filter(c => /^#([0-9a-fA-F]{3,4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$/.test(c));
    assert.deepEqual(found, [], file);
    assert.ok(!/\brgba?\(|\bhsla?\(/.test(rest), file + ' has rgb()/hsl() colours');
  }
  for (const file of ['app.js', 'settings.js', 'panel-edit.js', 'clock-widget.js', 'companion.js', 'settings.html', 'index.html']) {
    const text = fs.readFileSync(path.join(__dirname, '..', 'web', file), 'utf8');
    assert.deepEqual(text.match(/#[0-9a-fA-F]{6}\b/g) || [], [], file);
  }
});

test('card sizes: level from the short side, direction from the ratio, in grid units', () => {
  const at = (w, h, u) => { const s = L.cardSize(w, h, u); return s.size + '/' + s.orient; };
  assert.deepEqual([[2, 4], [2, 5], [3, 4], [3, 5], [4, 8], [2, 3], [3, 3], [2, 2], [6, 2], [1, 2], [1, 4], [2, 7], [1, 1]].map(([w, h]) => at(w, h)),
    ['m/square', 'm/square', 'm/wide', 'l/square', 'l/square', 's/square', 's/wide', 'xs/wide', 'xs/wide', 'xs/square', 'xs/tall', 'm/tall', 'xs/wide']);
  assert.equal(at(4, 4, 1), 'm/square');           // another screen: square cells
  assert.equal(at(3, 4), at(6, 4, 1));             // the same shape in another grid is the same card
  // nothing may be saved, imported or built in below a card's smallest size
  assert.deepEqual(L.normalizeItems([{id: 'media', x: 0, y: 0, w: 1, h: 1}, {id: 'clock', x: 3, y: 0, w: 1, h: 1}]),
    [{id: 'media', w: 2, h: 2, x: 0, y: 0}, {id: 'clock', w: 1, h: 1, x: 3, y: 0}]);
  for (const id of L.WIDGETS) assert.ok(L.MIN[id], id + ' has no smallest size');
  for (const [name, mode] of Object.entries(L.MODES))
    for (const it of mode.items) assert.ok(it.w >= L.minSize(it.id)[0] && it.h >= L.minSize(it.id)[1], name + ' ' + it.id);
  for (const it of L.DEFAULT_ITEMS) assert.ok(it.w >= L.minSize(it.id)[0] && it.h >= L.minSize(it.id)[1], it.id);
  // the player is never small and upright: its smallest size is already wide
  assert.equal(at(...L.MIN.media), 'xs/wide');
});

test('card rules use levels and directions, not pixel thresholds', () => {
  const css = fs.readFileSync(path.join(__dirname, '..', 'web', 'style.css'), 'utf8');
  const clock = css.indexOf('custom clock card');
  assert.ok(clock > 0);
  assert.equal((css.slice(0, clock).match(/@container/g) || []).length, 0);       // only the clock fits its own page
  const rules = css.slice(css.indexOf('Card sizes (docs/LAYOUT.md)'));
  assert.ok(!/@container|@media/.test(rules));
  for (const card of ['media', 'bambu', 'tokens', 'weather', 'companion', 'system'])
    assert.ok(rules.includes('.card.' + card + '[data-size') || rules.includes('.card.' + card + '[data-orient'), card);
});

test('editor: cards in the way step aside to the nearest free place, and shrink only when they must', () => {
  const items = [{id: 'media', x: 0, y: 0, w: 3, h: 4}, {id: 'bambu', x: 3, y: 0, w: 3, h: 4},
    {id: 'tokens', x: 0, y: 4, w: 3, h: 4}];
  // media pushed down onto tokens: tokens moves into the free corner, same size
  const a = L.makeRoom(items, {id: 'media', x: 0, y: 2, w: 3, h: 4});
  assert.deepEqual(a.map(i => i.id), ['media', 'bambu', 'tokens']);
  assert.deepEqual(a.find(i => i.id === 'tokens'), {id: 'tokens', x: 3, y: 4, w: 3, h: 4});
  assert.ok(a.every((p, i) => a.every((q, j) => i >= j || !L.overlaps(p, q))));
  // a full screen: the pushed card shrinks, not below its smallest size
  const full = [...items, {id: 'companion', x: 3, y: 4, w: 3, h: 4}];
  const b = L.makeRoom(full, {id: 'media', x: 0, y: 0, w: 3, h: 6});
  const t = b.find(i => i.id === 'tokens');
  assert.ok(t.w * t.h < 12 && t.w >= L.MIN.tokens[0] && t.h >= L.MIN.tokens[1], JSON.stringify(t));
  assert.ok(b.every((p, i) => b.every((q, j) => i >= j || !L.overlaps(p, q))));
  // off the screen, or nowhere to go: no change
  assert.equal(L.makeRoom(items, {id: 'media', x: 4, y: 0, w: 3, h: 4}), null);
  assert.equal(L.makeRoom(full, {id: 'media', x: 0, y: 0, w: 6, h: 7}), null);
  assert.deepEqual(L.makeRoom(items, {id: 'media', x: 0, y: 0, w: 2, h: 4}).slice(1), items.slice(1));  // nothing hit: others stay
});

test('editor: pushing through. Cards slide the way you drag, swap when a wall stops them, then squeeze', () => {
  const row = [{id: 'bambu', x: 0, y: 0, w: 2, h: 4}, {id: 'media', x: 2, y: 0, w: 2, h: 4}, {id: 'companion', x: 4, y: 0, w: 2, h: 4}];
  const at = (list, id) => { const c = list.find(i => i.id === id); return [c.x, c.y, c.w, c.h]; };
  const clean = list => list.every((p, i) => list.every((q, j) => i >= j || !L.overlaps(p, q)));
  // room ahead: the neighbour slides along, the far one is untouched
  const open = row.slice(0, 2);
  const a = L.makeRoom(open, {...open[0], x: 1}, open[0]);
  assert.deepEqual(at(a, 'media'), [3, 0, 2, 4]);
  // a chain: both neighbours move one step each
  const chain = [{id: 'bambu', x: 0, y: 0, w: 1, h: 4}, {id: 'weather', x: 1, y: 0, w: 2, h: 4}, {id: 'clock', x: 3, y: 0, w: 2, h: 4}];
  const b = L.makeRoom(chain, {...chain[0], x: 1}, chain[0]);
  assert.deepEqual([at(b, 'weather'), at(b, 'clock')], [[2, 0, 2, 4], [4, 0, 2, 4]]);
  // the wall is in the way: the neighbour slips back into the place the dragged card left (a swap)
  const c = L.makeRoom(row, {...row[0], x: 2}, row[0]);
  assert.deepEqual([at(c, 'bambu'), at(c, 'media'), at(c, 'companion')], [[2, 0, 2, 4], [0, 0, 2, 4], [4, 0, 2, 4]]);
  // dragged down: what is below goes down, not sideways
  const col = [{id: 'media', x: 0, y: 0, w: 3, h: 3}, {id: 'tokens', x: 0, y: 3, w: 3, h: 2}, {id: 'bambu', x: 3, y: 0, w: 3, h: 8}];
  const d = L.makeRoom(col, {...col[0], y: 1}, col[0]);
  assert.deepEqual(at(d, 'tokens'), [0, 4, 3, 2]);
  // growing a card on a full screen: the one below is squeezed, and only as far as its smallest size
  const full = [{id: 'media', x: 0, y: 0, w: 3, h: 4}, {id: 'tokens', x: 0, y: 4, w: 3, h: 4}, {id: 'bambu', x: 3, y: 0, w: 3, h: 8}];
  const e = L.makeRoom(full, {...full[0], h: 6}, full[0]);
  assert.deepEqual(at(e, 'tokens'), [0, 6, 3, 2]);
  assert.equal(L.makeRoom(full, {...full[0], h: 7}, full[0]), null);          // 1 row left: below the smallest size
  for (const got of [a, b, c, d, e]) assert.ok(clean(got));
  assert.deepEqual(L.makeRoom(row, {...row[0]}, row[0]), row);                 // nothing in the way: nothing moves
});

test('theme: a background picture is a version, a dim and a blur; packs never carry it', () => {
  assert.deepEqual(L.cleanImage({v: '6a1b2c', dim: 250, blur: -3, url: 'http://evil'}), {v: '6a1b2c', dim: 90, blur: 0});
  assert.deepEqual(L.cleanImage({v: 'abc'}), {v: 'abc', dim: 35, blur: 0});
  for (const bad of [null, {}, {v: ''}, {v: '../x'}, {v: 'a b'}, 'abc']) assert.equal(L.cleanImage(bad), null);
  const t = {accent: '#112233', image: {v: 'abc', dim: 40, blur: 10}};
  assert.deepEqual(L.resolveTheme(t).image, {v: 'abc', dim: 40, blur: 10});
  assert.deepEqual(L.storedTheme(t).image, {v: 'abc', dim: 40, blur: 10});
  assert.equal(L.resolveTheme({accent: '#112233'}).image, null);
  assert.ok(!('image' in L.storedTheme({accent: '#112233'})));
  const pack = L.exportPack({theme: t});
  assert.ok(!JSON.stringify(pack).includes('image'), 'the picture stays on this computer');
});
