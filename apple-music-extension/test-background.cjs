const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
function harness(commands = []) {
  let listener, revision = null, now = 100000;
  const payloads = [], windows = [], tabs = [], frames = [];
  const chrome = {runtime: {id: 'test', onMessage: {addListener: fn => listener = fn}}, commands: {onCommand: {addListener() {}}},
    action: {setBadgeText() {}, setTitle() {}},
    windows: {get: async () => ({state: 'normal'}), update: async (id, state) => {windows.push(state);}},
    tabs: {update: async id => tabs.push(id), sendMessage: async () => ({ok: true})}};
  const context = {chrome, URL, AbortSignal, Date: {now: () => now}, importScripts() {}, DESKMON: {url: 'http://127.0.0.1:9361/api/apple-music', key: 'test'},
    fetch: async (url, options) => {
      if (url.startsWith('data:')) return {blob: async () => ({jpeg: url})};  // dataURL -> Blob
      if (url.endsWith('/frame')) { frames.push({body: options.body, headers: options.headers}); return {ok: true, json: async () => ({mirror: true})}; }
      const body = JSON.parse(options.body); payloads.push(body);
      if ('lines' in body.state) revision = body.state.lyrics_revision;
      return {ok: true, json: async () => ({commands: commands.splice(0), lyrics_revision: revision, acked: []})};
    }};
  vm.runInNewContext(fs.readFileSync(__dirname + '/background.js', 'utf8'), context);
  return {payloads, windows, tabs, frames, advance: ms => now += ms,
    frame: (data, id = 1, track = 'youtube:123') => new Promise(resolve => {
      listener({type: 'deskmon-frame', track, data}, {tab: {id, windowId: 5}, url: 'https://www.youtube.com/watch?v=123'}, resolve);
    }),
    send: (state, id = 1, host = 'music.apple.com') => new Promise(resolve => {
    listener({type: 'deskmon-state', payload: {state, acks: []}}, {tab: {id, windowId: 5}, url: `https://${host}/watch?v=123`}, resolve);
  })};
}
const state = playing => ({track: 'apple:123', playing, lines: [[1, 'x']], plain: ['x'], lyrics_revision: 2});
test('playing YouTube replaces a paused Apple tab', async () => {
  const h = harness();
  await h.send(state(false));
  await h.send({...state(true), track: 'youtube:123'}, 2, 'www.youtube.com');
  await h.send(state(false));
  assert.equal(h.payloads.length, 2);
  assert.equal(h.payloads[1].state.track, 'youtube:123');
});

test('paused Apple tab cannot steal a paused YouTube resume target', async () => {
  const h = harness();
  await h.send({...state(false), track: 'youtube:123'}, 2, 'www.youtube.com');
  h.advance(10000);
  await h.send(state(false));
  assert.equal(h.payloads.length, 1);
  assert.equal(h.payloads[0].state.track, 'youtube:123');
});
test('unchanged lyrics are sent once, not on every heartbeat', async () => {
  const h = harness();
  await h.send(state(true));
  await h.send(state(true));
  assert.ok('lines' in h.payloads[0].state);
  assert.ok(!('lines' in h.payloads[1].state));
});
test('legacy fullscreen never focuses or changes the main-screen window', async () => {
  const h = harness([{id: 'command', track: 'youtube:123', action: 'fullscreen'}]);
  const result = await h.send({...state(true), track: 'youtube:123', video: true}, 2, 'www.youtube.com');
  assert.deepEqual(h.tabs, []);
  assert.equal(h.windows.length, 0);
  assert.equal(result.commands[0].action, 'fullscreen-result');
  assert.equal(result.commands[0].ok, false);
});
test('old track fullscreen command never focuses a different video', async () => {
  const h = harness([{id: 'command', track: 'youtube:old', action: 'fullscreen'}]);
  const result = await h.send({...state(true), track: 'youtube:123', video: true}, 2, 'www.youtube.com');
  assert.equal(h.tabs.length, 0);
  assert.equal(result.commands[0].ok, false);
});

// ---- video mirror frames ----
const JPEG = 'data:image/jpeg;base64,/9j/AAAA';
test('frames from the followed tab are forwarded with key and encoded track', async () => {
  const h = harness();
  await h.send({...state(true), track: 'youtube:123'}, 2, 'www.youtube.com');
  const reply = await h.frame(JPEG, 2, 'web:中文標題:212');
  assert.equal(reply.mirror, true);
  assert.equal(h.frames.length, 1);
  assert.equal(h.frames[0].headers['X-DeskMon-Key'], 'test');
  assert.equal(h.frames[0].headers['X-DeskMon-Track'], encodeURIComponent('web:中文標題:212'));
});
test('frames from another tab are refused', async () => {
  const h = harness();
  await h.send({...state(true), track: 'youtube:123'}, 2, 'www.youtube.com');
  assert.equal((await h.frame(JPEG, 7)).mirror, false);
  assert.equal(h.frames.length, 0);
});
test('anything that is not a JPEG data URL is refused', async () => {
  const h = harness();
  await h.send({...state(true), track: 'youtube:123'}, 2, 'www.youtube.com');
  assert.equal((await h.frame('data:text/html;base64,PHNjcmlwdD4=', 2)).mirror, false);
  assert.equal((await h.frame('https://evil.example/x.jpg', 2)).mirror, false);
  assert.equal(h.frames.length, 0);
});
