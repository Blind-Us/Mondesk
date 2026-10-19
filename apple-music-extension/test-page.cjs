const {test} = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
function run(musicKit) {
  const messages = [];
  let tick;
  function XHR() {}
  XHR.prototype.open = function () {};
  XHR.prototype.send = function () {};
  const context = {MusicKit: musicKit, location: {origin: 'https://music.apple.com'},
    XMLHttpRequest: XHR, fetch: () => Promise.resolve(),
    setInterval: callback => {tick = callback;}, addEventListener() {},
    postMessage: message => messages.push(message)};
  context.window = context;
  vm.runInNewContext(fs.readFileSync(__dirname + '/page.js', 'utf8'), context);
  tick();
  return messages[0].payload;
}
const player = () => ({nowPlayingItem: {id: '123', attributes: {name: 'Song', artistName: 'Artist', durationInMillis: 200000}},
  currentPlaybackTime: 10, currentPlaybackDuration: 200, isPlaying: true});
test('modern root playback takes precedence over unrelated .player object', () => {
  const result = run({getInstance: () => ({...player(), player: {}})});
  assert.equal(result.state.track, 'apple:123');
  assert.equal(result.state.position, 10);
});
test('older .player playback is supported', () => {
  assert.equal(run({getInstance: () => ({player: player()})}).state.track, 'apple:123');
});
test('native artwork uses a concrete Apple image URL', () => {
  const p = player();
  p.nowPlayingItem.attributes.artwork = {url: 'https://is1-ssl.mzstatic.com/image/{w}x{h}bb.{f}'};
  assert.equal(run({getInstance: () => p}).state.art_url, 'https://is1-ssl.mzstatic.com/image/600x600bb.jpg');
});
test('missing MusicKit emits a diagnostic instead of going silent', () => {
  const result = run(undefined);
  assert.equal(result.state, null);
  assert.match(result.diagnostic, /未提供 MusicKit/);
});
test('player exceptions are reported without fabricated playback', () => {
  const result = run({getInstance: () => {throw Error('not ready');}});
  assert.equal(result.state, null);
  assert.match(result.diagnostic, /not ready/);
});
test('queries native lyrics using the current Apple storefront and session', async () => {
  const requests = [];
  const p = player();
  p.storefrontId = 'tw';
  p.api = {music: async path => {requests.push(path); return {data: {data: []}};}};
  const result = run({getInstance: () => p});
  await new Promise(resolve => setImmediate(resolve));
  assert.deepEqual(requests, ['/v1/catalog/tw/songs/123/syllable-lyrics', '/v1/catalog/tw/songs/123/lyrics']);
  assert.deepEqual(Array.from(result.state.lines), []);
});
