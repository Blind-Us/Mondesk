const assert = require('node:assert/strict');
require('../web/layout.js');
const {calculate,panelDisplays}=globalThis.DeskMonLayout;
for(const [w,h] of [[960,640],[480,320],[1920,1080],[640,426],[758,645]]){
 const d=calculate(w,h,{width:960,height:640});
 assert.ok(d.contentWidth<=w+1e-6 && d.contentHeight<=h+1e-6);
 assert.ok(Math.abs(d.contentWidth/d.contentHeight-1.5)<1e-8);
}
assert.equal(calculate(960,640,{width:960,height:640}).scale,1);
assert.equal(calculate(1920,1080,{width:960,height:640}).contentWidth,1620);
assert.equal(calculate(960,640,{width:960,height:480}).contentHeight,480);
assert.notEqual(calculate(960,640,{fit:'auto'}).aspect,calculate(1920,1080,{fit:'auto'}).aspect);
assert.deepEqual(panelDisplays([{name:'DISPLAY1',primary:true,current:{},modes:[{w:960,h:640}]},{name:'DISPLAY2',primary:false,current:{},modes:[{w:960,h:640}]}]).map(x=>x.name),['DISPLAY2']);
console.log('Layout: 5 viewport sizes preserve 3:2; preset changes apply; primary screen excluded.');

// widget grid
const {place, normalizeItems, DEFAULT_ITEMS, COLS, ROWS} = globalThis.DeskMonLayout;
const all = ['bambu', 'media', 'tokens', 'companion'];
const cells = items => items.reduce((n, i) => n + i.w * i.h, 0);
const noOverlap = items => items.every((a, i) => items.every((b, j) => i === j || a.x >= b.x + b.w || b.x >= a.x + a.w || a.y >= b.y + b.h || b.y >= a.y + a.h));
assert.deepEqual(place(null, all), DEFAULT_ITEMS);                         // printer | music / tokens | agent
const noAgent = place(null, ['bambu', 'media', 'tokens']);                 // agent off: tokens take the whole row
assert.deepEqual(noAgent.find(i => i.id === 'tokens'), {id: 'tokens', x: 0, y: 5, w: 6, h: 3});
const withSystem = place(null, [...all, 'system']);                        // a new widget takes half of the biggest card
assert.ok(withSystem.some(i => i.id === 'system') && noOverlap(withSystem) && cells(withSystem) === COLS * ROWS);
const custom = place({items: [{id: 'media', x: 0, y: 0, w: 6, h: 6}, {id: 'companion', x: 0, y: 6, w: 6, h: 2}]}, ['media', 'companion']);
assert.deepEqual(custom, [{id: 'media', x: 0, y: 0, w: 6, h: 6}, {id: 'companion', x: 0, y: 6, w: 6, h: 2}]);
assert.equal(normalizeItems([{id: 'media', x: 0, y: 0, w: 4, h: 4}, {id: 'bambu', x: 2, y: 2, w: 2, h: 2}, {id: 'nope', x: 5, y: 5, w: 1, h: 1}]).length, 1);  // overlap and unknown dropped
assert.ok(noOverlap(place({items: [{id: 'bambu', x: 9, y: 9, w: 9, h: 9}]}, all)));  // out-of-range input is clamped
console.log('Widget grid: default, holes filled, new widgets placed, custom layouts kept, bad input rejected.');
assert.equal(place({items: [{id: 'media', x: 0, y: 0, w: 2, h: 2}]}, ['media'], false)[0].w, 2);  // editor: no filling
console.log('Editor mode keeps holes.');

// widget drawer: hidden widgets get no card even when their module runs; drops land where they fit
const {spotAt} = globalThis.DeskMonLayout;
const drawerLayout = {items: DEFAULT_ITEMS, hidden: ['companion']};
const shown = place(drawerLayout, all);
assert.ok(!shown.some(i => i.id === 'companion'));
assert.deepEqual(shown.find(i => i.id === 'tokens'), {id: 'tokens', x: 0, y: 5, w: 6, h: 3});  // the hole is filled
const three = DEFAULT_ITEMS.filter(i => i.id !== 'companion');
assert.deepEqual(spotAt(three, 4, 6), {x: 3, y: 5, w: 3, h: 3});      // slides to fit the free corner
assert.equal(spotAt(DEFAULT_ITEMS, 1, 1), null);                     // a full screen has no room
console.log('Drawer: hidden widgets stay off the panel; drops snap into free space.');
const noSystem = DEFAULT_ITEMS.map(i => i.id === 'bambu' ? {...i, h: 3} : i);  // rows 3-4 free on the left
assert.deepEqual(spotAt(noSystem, 1, 3), {x: 0, y: 3, w: 3, h: 2});  // slides left to use the whole gap
