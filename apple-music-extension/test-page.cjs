const {test} = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
function run(musicKit, change) {
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
  if (change) {change(); tick();}
  return messages.at(-1).payload;
}
const player = () => ({nowPlayingItem: {id: '123', attributes: {name: 'Song', artistName: 'Artist', durationInMillis: 200000}},
  currentPlaybackTime: 10, currentPlaybackDuration: 200, isPlaying: true});

test('album queue advance refreshes title and artwork despite stale nowPlayingItem', () => {
  const p = player();
  const next = {id: '456', attributes: {name: 'Next song', albumName: 'Album two', artwork: {url: 'https://is1-ssl.mzstatic.com/next/{w}.jpg'}}};
  p.queue = {position: 0, items: [p.nowPlayingItem, next]};
  const result = run({getInstance: () => p}, () => {p.queue.position = 1;});
  assert.equal(result.state.track, 'apple:456');
  assert.equal(result.state.title, 'Next song');
  assert.equal(result.state.album, 'Album two');
  assert.equal(result.state.art_url, 'https://is1-ssl.mzstatic.com/next/600.jpg');
});

test('playlist queue item supports flattened MusicKit metadata', () => {
  const p = player();
  p.queue = {position: 1, item: i => i === 1 ? {id: 'library:next', playParams: {catalogId: '789'}, title: 'Playlist next', artistName: 'Next artist', artwork: {url: 'https://is1-ssl.mzstatic.com/789.jpg'}} : null};
  const result = run({getInstance: () => p});
  assert.equal(result.state.track, 'apple:789');
  assert.equal(result.state.title, 'Playlist next');
  assert.equal(result.state.artist, 'Next artist');
});
test('modern root playback takes precedence over unrelated .player object', () => {
  const result = run({getInstance: () => ({...player(), player: {}})});
  assert.equal(result.state.track, 'apple:123');
  assert.equal(result.state.position, 10);
});

test('replacing a queue cannot blank the current song', () => {
  const p = player(); p.queue = {position: 0, item() {throw Error('replacing');}};
  assert.equal(run({getInstance: () => p}).state.track, 'apple:123');
});

test('queue stubs cannot hide refreshed metadata for the same song', () => {
  const p = player(); p.queue = {position: 0, items: [{id: '123'}]};
  assert.equal(run({getInstance: () => p}).state.title, 'Song');
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
