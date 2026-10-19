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
