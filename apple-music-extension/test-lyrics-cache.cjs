const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(__dirname + '/page.js', 'utf8');
function harness() {
  const lyrics = new Map(), lyricText = new Map();
  const context = {lyrics, lyricText, parse: text => ({lines:text.includes('timed') ? [[1,'line'],[2,'next']] : [], plain:['line','next']})};
  vm.createContext(context);
  vm.runInContext('let lyricRevision = 0;' + source.slice(source.indexOf('  function capture('), source.indexOf('  const originalFetch')), context);
  return {lyrics, capture: text => context.capture('/v1/catalog/tw/songs/123/lyrics', text)};
}
test('late static lyrics cannot replace native timed lyrics', () => {
  const h = harness(); h.capture('<tt>timed</tt>'); h.capture('<tt>static</tt>');
  assert.equal(h.lyrics.get('123').lines.length, 2);
  assert.equal(h.lyrics.get('123').lyrics_revision, 1);
});
test('native timed response upgrades a cached static response', () => {
  const h = harness(); h.capture('<tt>static</tt>'); h.capture('<tt>timed</tt>');
  assert.equal(h.lyrics.get('123').lines.length, 2);
  assert.equal(h.lyrics.get('123').lyrics_revision, 2);
});
test('static lyrics do not prevent querying both native timing endpoints', async () => {
  const requests = [], lyrics = new Map([['123',{lines:[],plain:['line']}] ]);
  const context = {lyrics, lyricRequests:new Map(), Date, location:{pathname:'/tw/'}, window:{MusicKit:{getInstance:()=>({storefrontId:'tw',api:{music:async path=>{requests.push(path); return {};}}})}}, capture() {}};
  vm.createContext(context);
  vm.runInContext("let lyricDiagnostic = '';" + source.slice(source.indexOf('  async function requestLyrics('), source.indexOf("  window.addEventListener('message'")), context);
  await context.requestLyrics({track:'apple:123'});
  assert.equal(requests.length, 2);
  await context.requestLyrics({track:'apple:123'});
  assert.equal(requests.length, 2, 'retry is rate limited');
});
