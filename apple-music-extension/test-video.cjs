const {test} = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');

// Runs video.js in a fake YouTube page: one <video>, a fake canvas and chrome.runtime.
function harness({hidden = false, tainted = false, reply = {mirror: true}, ad = false, deferEncode = false} = {}) {
  const events = {}, messages = [], created = [], frames = [], timers = new Map();
  let nextTimer = 1;
  const video = {paused: false, ended: false, readyState: 4, currentTime: 12, duration: 200,
    videoWidth: 1920, videoHeight: 1080, closest: () => null};
  video.pause = () => {video.paused = true;};
  video.play = async () => {video.paused = false;};
  const canvas = {width: 0, height: 0,
    getContext: () => ({drawImage: () => { if (tainted) throw new Error('SecurityError: tainted'); }}),
    toBlob: (cb, type) => {if (deferEncode) canvas.finish = () => cb({type}); else cb({type});}};
  const context = {URL, location: {href: 'https://www.youtube.com/watch?v=test123', origin: 'https://www.youtube.com', hostname: 'www.youtube.com', pathname: '/watch'},
    navigator: {mediaSession: {metadata: {title: 'Test video', artist: 'Channel'}}},
    document: {title: 'Test video - YouTube', hidden, querySelectorAll: () => [video], querySelector: sel => ad && sel.includes('ad-showing') ? {} : null,
      createElement: tag => {created.push(tag); return canvas;}},
    FileReader: class { readAsDataURL() { this.result = 'data:image/jpeg;base64,AAAA'; this.onload(); } },
    chrome: {runtime: {sendMessage: async msg => {frames.push(msg); return reply;}}},
    setInterval: (fn, ms) => {const id = nextTimer++; timers.set(id, {fn, ms}); return id;},
    clearInterval: id => timers.delete(id),
    addEventListener: (name, fn) => events[name] = fn, postMessage: m => messages.push(m)};
  context.window = context;
  vm.runInNewContext(fs.readFileSync(__dirname + '/video.js', 'utf8'), context);
  const source = vm.runInContext('window', context);
  const heartbeat = () => [...timers.values()].find(t => t.ms === 2000).fn();
  const mirrorTimer = () => [...timers.values()].find(t => t.ms < 2000);
  return {video, canvas, created, frames, timers, stop: () => events['deskmon-bridge-stop'](),
    snapshot: () => {heartbeat(); return messages.at(-1).payload.state;},
    mirror: on => events.message({source, origin: context.location.origin, data: {type: 'deskmon-apple-commands', commands: [], acked: [], mirror: on}}),
    frame: async () => {const t = mirrorTimer(); if (t) { await t.fn(); await new Promise(r => setImmediate(r)); }},
    mirrorTimer,
    command: async (action, track = 'youtube:test123') => {
      await events.message({source, origin: context.location.origin, data: {type: 'deskmon-apple-commands', commands: [{id: 'c', action, track}], acked: []}});
      heartbeat(); return messages.at(-1).payload.acks.at(-1);
    }};
}

test('reports the existing YouTube video without creating a player', () => {
  const h = harness();
  const s = h.snapshot();
  assert.equal(s.source, 'YouTube');
  assert.equal(s.track, 'youtube:test123');
  assert.equal(s.video, true);
  assert.deepEqual(h.created.filter(tag => tag !== 'canvas'), []);  // no <video>/<iframe> ever
});

test('captures nothing until a Mondesk panel watches', async () => {
  const h = harness();
  assert.equal(h.mirrorTimer(), undefined);
  await h.mirror(true);
  await h.frame();
  assert.equal(h.frames.length, 1);
  assert.equal(h.frames[0].type, 'deskmon-frame');
  assert.equal(h.frames[0].track, 'youtube:test123');
  assert.match(h.frames[0].data, /^data:image\/jpeg;base64,/);
  await h.mirror(false);
  assert.equal(h.mirrorTimer(), undefined);  // panel closed: capture loop stopped
});

test('stops by itself when Mondesk says nobody watches any more', async () => {
  const h = harness({reply: {mirror: false}});
  await h.mirror(true);
  await h.frame();
  assert.equal(h.mirrorTimer(), undefined);
});

test('frames are scaled down to at most 960px wide', async () => {
  const h = harness();
  await h.mirror(true);
  await h.frame();
  assert.equal(h.canvas.width, 960);   // 1920x1080 source
  assert.equal(h.canvas.height, 540);
});

test('a background tab reports "hidden" instead of sending frozen frames', async () => {
  const h = harness({hidden: true});
  await h.mirror(true);
  await h.frame();
  assert.equal(h.frames.length, 0);
  assert.equal(h.snapshot().mirror, 'hidden');
});

test('a site that blocks frame copying reports "blocked"', async () => {
  const h = harness({tainted: true});
  await h.mirror(true);
  await h.frame();
  assert.equal(h.frames.length, 0);
  assert.equal(h.snapshot().mirror, 'blocked');
});

test('a paused video is not re-sent every tick', async () => {
  const h = harness();
  h.video.paused = true;
  await h.mirror(true);
  await h.frame();
  await h.frame();
  assert.equal(h.frames.length, 1);
});

test('play/pause still controls the original tab', async () => {
  const h = harness();
  assert.equal((await h.command('toggle')).ok, true);
  assert.equal(h.video.paused, true);
});

test('reports when the tab is playing a YouTube ad', () => {
  assert.equal(harness().snapshot().ad, false);
  assert.equal(harness({ad: true}).snapshot().ad, true);
});

test('slow encoding never starts overlapping frame encodes', async () => {
  const h = harness({deferEncode: true});
  await h.mirror(true);
  const pending = h.frame();
  const first = h.canvas.finish;
  h.video.currentTime++;
  await h.frame();
  assert.equal(h.canvas.finish, first);
  first(); await pending;
  assert.equal(h.frames.length, 1);
});

test('disconnect during encoding stops timers and drops the unfinished frame', async () => {
  const h = harness({deferEncode: true});
  await h.mirror(true);
  const pending = h.frame();
  h.stop(); h.canvas.finish(); await pending;
  assert.equal(h.timers.size, 0);
  assert.equal(h.frames.length, 0);
});
