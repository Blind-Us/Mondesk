const {test} = require('node:test');
const assert = require('node:assert/strict');
const {replace} = require('../web/printer-render.js');
function setup() {
  const requests = [];
  const image = {url: 'one', isConnected: true, getAttribute() {return this.url;}, setAttribute(k, value) {this.url = value;}};
  const card = {querySelector: () => image, replaceChildren() {}};
  global.document = {createElement() {let url; return {
    set innerHTML(value) {url = value;}, content: {querySelector: selector => selector.endsWith(' img') ? {getAttribute: () => url, replaceWith() {}} : null}
  };}};
  global.Image = class {set src(value) {this.url = value; requests.push(this);}};
  return {card, image, requests};
}
test('progress rerenders preserve the image without issuing a preload', () => {
  const h = setup();
  replace(h.card, 'one'); replace(h.card, 'one');
  assert.equal(h.requests.length, 0);
  assert.equal(h.image.url, 'one');
});
test('new preview loads once and old bitmap stays visible until loaded', () => {
  const h = setup();
  replace(h.card, 'two'); replace(h.card, 'two');
  assert.equal(h.requests.length, 1);
  assert.equal(h.image.url, 'one');
  h.requests[0].onload();
  assert.equal(h.image.url, 'two');
});
test('a superseded preload cannot replace the current preview', () => {
  const h = setup();
  replace(h.card, 'two'); replace(h.card, 'one');
  h.requests[0].onload();
  assert.equal(h.image.url, 'one');
});
test('failed image keeps previous preview and does not repeatedly request it', () => {
  const h = setup();
  replace(h.card, 'two'); h.requests[0].onerror(); replace(h.card, 'two');
  assert.equal(h.requests.length, 1);
  assert.equal(h.image.url, 'one');
});
