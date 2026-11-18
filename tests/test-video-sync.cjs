const {test} = require('node:test');
const assert = require('node:assert/strict');

// fake DOM + YouTube IFrame API
function setup() {
  const players = [];
  const el = () => ({hidden: true, children: [], replaceChildren(...c) { this.children = c; }});
  global.document = {createElement: el, head: {append() {}}};
  class Player {
    constructor(slot, options) { this.options = options; this.time = options.playerVars.start; this.state = -1; this.seeks = []; players.push(this); }
    mute() { this.muted = true; } playVideo() { this.state = 1; } pauseVideo() { this.state = 2; }
    getPlayerState() { return this.state; } getCurrentTime() { return this.time; }
    seekTo(t) { this.seeks.push(t); this.time = t; } destroy() { this.destroyed = true; }
    ready() { this.options.events.onReady({target: this}); } error(code) { this.options.events.onError({data: code}); }
  }
  global.window = {YT: {Player}};
  delete require.cache[require.resolve('../web/video-sync.js')];
  const {SyncedVideo, videoID} = require('../web/video-sync.js');
  return {video: new SyncedVideo(el()), players, videoID};
}
const flush = () => new Promise(r => setImmediate(r));
const TRACK = 'youtube:abcdefghijk';

test('only YouTube tracks with a valid id can be synced', () => {
  const {video, videoID} = setup();
  assert.equal(videoID(TRACK), 'abcdefghijk');
  assert.equal(video.canPlay('web:Some title:200'), false);
  assert.equal(video.canPlay('youtube:bad'), false);
  assert.equal(video.canPlay(TRACK), true);
});

test('plays muted, without controls, starting where the tab is', async () => {
  const {video, players} = setup();
  video.show(TRACK, 42.7); await flush();
  const p = players[0];
  assert.equal(p.options.videoId, 'abcdefghijk');
  assert.equal(p.options.playerVars.mute, 1);
  assert.equal(p.options.playerVars.controls, 0);
  assert.equal(p.options.playerVars.start, 42);
  p.ready();
  assert.equal(p.muted, true);
});

test('re-aligns when more than a second apart, then lets the seek settle', async () => {
  const {video, players} = setup();
  video.show(TRACK, 10); await flush();
  const p = players[0]; p.ready();
  video.sync(10.5, true, false);           // 0.5 s apart: leave it alone
  assert.deepEqual(p.seeks, []);
  video.sync(30, true, false);             // 20 s apart: jump
  assert.deepEqual(p.seeks, [30]);
  p.time = 31.6;                           // still buffering behind
  video.sync(33, true, false);             // within the grace period: no seek storm
  assert.deepEqual(p.seeks, [30]);
});

test('follows pause and holds during ads', async () => {
  const {video, players} = setup();
  video.show(TRACK, 10); await flush();
  const p = players[0]; p.ready();
  video.sync(10, true, false); assert.equal(p.state, 1);
  video.sync(10, false, false); assert.equal(p.state, 2);
  video.sync(10, true, false); assert.equal(p.state, 1);
  video.sync(3, true, true);               // ad in the tab: its time is the ad's, don't follow it
  assert.equal(p.state, 2);
  assert.deepEqual(p.seeks, []);
});

test('a video that refuses embedding falls back (canPlay false)', async () => {
  const {video, players} = setup();
  video.show(TRACK, 0); await flush();
  players[0].error(150);
  assert.equal(video.canPlay(TRACK), false);
  assert.equal(players[0].destroyed, true);
});

test('switching videos replaces the player; closing destroys it', async () => {
  const {video, players} = setup();
  video.show(TRACK, 0); await flush();
  video.show('youtube:zzzzzzzzzzz', 5); await flush();
  assert.equal(players[0].destroyed, true);
  assert.equal(players[1].options.videoId, 'zzzzzzzzzzz');
  video.close();
  assert.equal(players[1].destroyed, true);
  assert.equal(video.host.hidden, true);
});

test('a short pause leaves the embedded player running; a long one really pauses it', async () => {
  const {video, players} = setup();
  video.show(TRACK, 10); await flush();
  const p = players[0]; p.ready();
  video.sync(10, true, false);
  assert.equal(p.state, 1);
  assert.equal(video.inStep(10), true);
  video.sync(10, false, false, true);            // tab paused a moment ago: keep running under the cover
  assert.equal(p.state, 1);
  const loaded = video.pausedAt;                  // loading counts as "cards are up"
  assert.ok(loaded);
  p.time = 40;                                    // it ran ahead meanwhile
  assert.equal(video.inStep(10), false);          // not the tab's picture: the page keeps the cover on
  video.sync(10, true, false);                    // resume: pulled back to the tab's position
  assert.deepEqual(p.seeks, [10]);
  assert.equal(video.inStep(10), true);
  video.sync(10, false, false, false);            // paused for long: really pause, and remember when
  assert.equal(p.state, 2);
  assert.ok(video.pausedAt >= loaded && Date.now() - video.pausedAt < 1000);
  assert.equal(video.inStep(10), false);
  video.sync(10, false, true, true);              // an ad never keeps it running? it is covered either way
  assert.equal(p.state, 2);
});

// ---- Bilibili: an embedded player without an API ----
function bili() {
  const frames = [];
  const el = () => { const e = {hidden: true, children: [], posted: [], replaceChildren(...c) { this.children = c; }}; e.contentWindow = {postMessage: m => e.posted.push(m)}; frames.push(e); return e; };
  global.document = {createElement: el, head: {append() {}}};
  global.window = {};
  delete require.cache[require.resolve('../web/video-sync.js')];
  const {AnyVideo, biliID, syncKey} = require('../web/video-sync.js');
  const host = el(); frames.length = 0;
  const video = new AnyVideo(host);
  let clock = 1000000;
  const part = video.parts[1];
  part.now = () => clock;
  return {video, part, host, frames, biliID, syncKey, tick: ms => { clock += ms; }, say: data => part.onMessage({origin: 'https://player.bilibili.com', source: part.frame.contentWindow, data})};
}
const BV = 'bilibili:BV14uWC6bEz2';

test('Bilibili ids: BV number and part', () => {
  const {biliID, syncKey, video} = bili();
  assert.deepEqual(biliID(BV), {bvid: 'BV14uWC6bEz2', part: 1, key: 'BV14uWC6bEz2'});
  assert.equal(syncKey(BV + ':3'), 'BV14uWC6bEz2:3');
  assert.equal(syncKey('youtube:abcdefghijk'), 'abcdefghijk');
  assert.equal(syncKey('web:Some title:200'), null);
  assert.equal(video.canPlay(BV), true);
  assert.equal(video.canPlay('bilibili:nope'), false);
});

test('Bilibili starts muted at the tab position', () => {
  const {video, frames} = bili();
  video.show(BV + ':2', 61.9);
  assert.equal(video.id, 'BV14uWC6bEz2:2');
  assert.match(frames[0].src, /^https:\/\/player\.bilibili\.com\/player\.html\?bvid=BV14uWC6bEz2&p=2&autoplay=1&muted=1&danmaku=0&high_quality=1&t=61$/);
});

test('without the helper it runs by the clock: reloads on a seek, leaves a short pause alone, drops on a long one', () => {
  const {video, part, frames, tick, host} = bili();
  video.show(BV, 100);
  frames[0].onload(); tick(1500);
  assert.equal(video.ready, true);
  tick(4000);
  assert.equal(video.inStep(104), true);
  video.sync(104, true, false);
  assert.equal(frames.length, 1);                 // in step: left alone
  video.sync(300, true, false);                   // the tab jumped
  assert.equal(frames.length, 2);
  assert.match(frames[1].src, /&t=30[0-9]$/);     // a little ahead: loading takes time
  frames[1].onload(); tick(6000);
  video.sync(304, false, false, true);            // short pause: stays (the page covers it)
  assert.equal(part.frame, frames[1]);
  video.sync(304, false, false, false);           // long pause: taken away
  assert.equal(part.frame, null);
  assert.deepEqual(host.children, []);
  assert.equal(video.inStep(304), false);
  video.sync(304, true, false);                   // playing again: loaded again
  assert.equal(frames.length, 3);
});

test('with the helper the embedded player is told the position and never reloaded', () => {
  const {video, part, frames, tick, say} = bili();
  video.show(BV, 100);
  frames[0].onload();
  part.onMessage({origin: 'https://evil.example', source: frames[0].contentWindow, data: {type: 'deskmon-embed-hello'}});
  assert.equal(part.helper, null);                // only the embedded player itself is believed
  say({type: 'deskmon-embed-hello'});
  tick(8000);
  video.sync(300, true, false);
  assert.equal(frames.length, 1);
  assert.deepEqual(frames[0].posted.at(-1), {type: 'deskmon-embed', position: 300, playing: true});
  say({type: 'deskmon-embed-state', ready: true, time: 300.2, playing: true});
  assert.equal(video.pausedAt, 0);
  tick(500);
  assert.equal(video.inStep(300.7), true);
  assert.equal(video.inStep(320), false);
  video.sync(301, false, false);
  assert.equal(frames[0].posted.at(-1).playing, false);   // a real pause, exactly where the tab is
  assert.equal(part.frame, frames[0]);
});

test('a Bilibili video that never gets a picture falls back', () => {
  const {video, tick, say} = bili();
  video.show(BV, 0);
  say({type: 'deskmon-embed-hello'});
  tick(21000);
  say({type: 'deskmon-embed-state', ready: false, time: 0, playing: false});
  assert.equal(video.canPlay(BV), false);
  assert.equal(video.id, null);
});
