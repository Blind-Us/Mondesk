const {test} = require('node:test');
const assert = require('node:assert/strict');
const {resolve, follow} = require('../web/media-route.js');
test('OS media never opens Apple lyrics just because video is missing', () => {
  assert.equal(resolve({source: 'Chrome', title: 'Video'}).kind, 'unavailable');
});
test('only verified Apple bridge music opens lyrics', () => {
  assert.equal(resolve({source: 'Apple Music', browser_bridge: true, video: false}).kind, 'lyrics');
  assert.equal(resolve({source: 'YouTube', browser_bridge: true, video: false}).kind, 'unavailable');
});
test('a video from the extension opens the mirrored video view', () => {
  assert.equal(resolve({source: 'YouTube', browser_bridge: true, video: true, track: 'youtube:abcdefghijk'}).kind, 'video');
  assert.equal(resolve({source: 'Browser', browser_bridge: true, video: true, track: 'web:Some title:212'}).kind, 'video');
});
test('Apple Music music videos open the video view, not lyrics', () => {
  assert.equal(resolve({source: 'Apple Music', browser_bridge: true, video: true}).kind, 'video');
});
test('open lyrics page switches to the video when one starts, and back when it ends', () => {
  const yt = {source: 'YouTube', browser_bridge: true, video: true, track: 'youtube:abcdefghijk'};
  const mv = {source: 'Apple Music', browser_bridge: true, video: true};
  const song = {source: 'Apple Music', browser_bridge: true, video: false};
  assert.equal(follow('lyrics', yt), 'video');
  assert.equal(follow('lyrics', mv), 'video');
  assert.equal(follow('lyrics', song), 'lyrics');
  assert.equal(follow('lyrics', {source: 'Chrome', video: true}), 'lyrics');  // no extension data: nothing to show
  assert.equal(follow('video', song), 'lyrics');
  assert.equal(follow('video', yt), 'video');
});
