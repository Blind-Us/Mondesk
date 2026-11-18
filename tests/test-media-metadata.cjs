const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

test('late title and artwork refresh without changing the track or reassigning unchanged images', () => {
  const source = fs.readFileSync(__dirname + '/../web/app.js', 'utf8');
  const fn = source.slice(source.indexOf('function updateLyricMetadata('), source.indexOf('function tickLyrics('));
  let writes = 0, src = '';
  const image = {getAttribute: () => src, set src(value) {src = value; writes++;}};
  const nodes = {'.ly-art': image, '.ly-bg': {style: {}}, '.ly-title': {}, '.ly-artist': {}};
  const context = {ly: {}, LY: {querySelector: selector => nodes[selector]}};
  vm.createContext(context);
  vm.runInContext(fn, context);
  const m = {id: 'music', data: {track: 'apple:123', title: 'Loading', artist: 'Singer'}};
  context.updateLyricMetadata(m);
  m.data.title = 'Actual title'; m.data.art_url = 'https://example.com/new.jpg';
  context.updateLyricMetadata(m);
  assert.equal(nodes['.ly-title'].textContent, 'Actual title');
  assert.equal(src, m.data.art_url);
  const count = writes;
  context.updateLyricMetadata(m);
  assert.equal(writes, count);
});
