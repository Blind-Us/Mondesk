const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

function harness({displays, tabWindowExists = true} = {}) {
  const calls = [], store = {};
  const chrome = {
    system: {display: {getInfo: async () => displays || [
      {isPrimary: true, bounds: {left: 0, top: 0, width: 2560, height: 1440}, workArea: {left: 0, top: 0, width: 2560, height: 1400}},
      {isPrimary: false, bounds: {left: 2560, top: 0, width: 1920, height: 1080}},
      {isPrimary: false, bounds: {left: -960, top: 200, width: 960, height: 640}},
    ]}},
    windows: {
      create: async opts => { calls.push(['create', opts]); return {id: 77}; },
      update: async (id, opts) => calls.push(['update', id, opts]),
      get: async id => { if (!tabWindowExists) throw Error('gone'); return {id}; },
      onRemoved: {addListener() {}},
    },
    tabs: {
      get: async id => ({id, windowId: 5, index: 3}),
      move: async (id, opts) => calls.push(['move', id, opts]),
      update: async (id, opts) => calls.push(['tab', id, opts]),
      onRemoved: {addListener() {}},
    },
    scripting: {executeScript: async ({args}) => { calls.push(['fill', args[0]]); return [{result: true}]; }},
    storage: {session: {get: async () => ({...store}), set: async v => Object.assign(store, v)}},
  };
  const context = {chrome};
  vm.runInNewContext(fs.readFileSync(__dirname + '/side-screen.js', 'utf8'), context);
  return {context, calls, store, plain: () => JSON.parse(JSON.stringify(calls))};
}

test('the video tab goes fullscreen on the smallest extra screen, then back to its old spot', async () => {
  const {context, calls, plain} = harness();
  assert.equal(await context.toggleSideScreen(9), 'side');
  assert.deepEqual(plain()[0], ['create', {tabId: 9, left: -960, top: 200, width: 960, height: 640, focused: true}]);
  assert.deepEqual(plain()[1], ['update', 77, {state: 'fullscreen'}]);
  assert.deepEqual(plain()[2], ['fill', true]);
  calls.length = 0;
  assert.equal(await context.toggleSideScreen(9), 'main');
  assert.deepEqual(plain()[0], ['fill', false]);
  assert.deepEqual(plain()[1], ['move', 9, {windowId: 5, index: 3}]);
});

test('no extra screen: a clear error and nothing moves', async () => {
  const {context, calls} = harness({displays: [{isPrimary: true, bounds: {left: 0, top: 0, width: 1920, height: 1080}}]});
  await assert.rejects(context.toggleSideScreen(9), /找不到副螢幕/);
  assert.equal(calls.length, 0);
});

test('its old window is gone: it comes back in a new window on the main screen', async () => {
  const {context, calls} = harness({tabWindowExists: false});
  await context.toggleSideScreen(9);
  calls.length = 0;
  await context.sideBack(9);
  assert.equal(calls[1][0], 'create');
  assert.equal(calls[1][1].left, 40);
});
