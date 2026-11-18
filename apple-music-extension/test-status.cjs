const {test} = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
test('popup follows songs and preserves actionable connection errors across refreshes', async () => {
  const nodes = Object.fromEntries(['status','title','artist','source','version','connect','side'].map(id => [id, {}]));
  let title = 'First'; let tick;
  const context = {Date, document: {getElementById: id => nodes[id]}, setInterval: fn => tick = fn,
    chrome: {runtime: {getManifest: () => ({version:'0.3.4'}), sendMessage: async msg => msg.type === 'deskmon-connect-tab' ? {ok:false,error:'請選擇影片分頁'} : {updated:Date.now(),message:'已連線',nowPlaying:{title,artist:'Singer',source:'YouTube',playing:true}}}}};
  vm.runInNewContext(fs.readFileSync(__dirname + '/status.js', 'utf8'), context);
  await new Promise(r => setImmediate(r));
  assert.equal(nodes.title.textContent, 'First');
  title = 'Next'; await tick();
  await new Promise(r => setImmediate(r));
  assert.equal(nodes.title.textContent, 'Next');
  await nodes.connect.onclick(); await tick();
  await new Promise(r => setImmediate(r));
  assert.equal(nodes.status.textContent, '請選擇影片分頁');
  assert.equal(nodes.connect.disabled, false);
});
