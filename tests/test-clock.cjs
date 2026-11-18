// Clock card: time words, options and the timer state machine (no DOM needed for these parts).
const assert = require('node:assert/strict');
const store = {};
globalThis.window = globalThis;
globalThis.localStorage = { getItem: k => store[k] ?? null, setItem: (k, v) => { store[k] = String(v); } };
require('../web/clock-widget.js');
const C = globalThis.DeskMonClock;

// looks + options
assert.deepEqual(C.STYLES, ['digital', 'analog', 'flip', 'ring', 'words']);
assert.equal(C.options({ data: { style: 'nope' } }).style, 'digital');
assert.equal(C.options({ data: {} }).seconds, true);
assert.equal(C.options({ data: { timer: true } }).timer, true);

// digital + words
const at = (h, m) => new Date(2026, 10, 8, h, m, 5);
let p = C.parts(at(14, 5), { hour12: false });
assert.equal(`${p.hh}:${p.mm}:${p.ss}`, '14:05:05');
assert.equal(p.date, '11月8日 週日');
p = C.parts(at(14, 5), { hour12: true });
assert.equal(p.hh + p.ap, '2下午');
assert.equal(p.wordsHour + p.wordsMin, '兩點零五分');
assert.equal(p.period, '下午');
p = C.parts(at(0, 30), { hour12: false });
assert.equal(p.hh, '00');
assert.equal(p.wordsHour + p.wordsMin + p.period, '十二點半凌晨');
p = C.parts(at(21, 0), {});
assert.equal(p.wordsHour + p.wordsMin, '九點整');
assert.equal(C.parts(at(11, 47), {}).wordsMin, '四十七分');

// formatting: countdowns round up, the stopwatch rounds down
assert.equal(C.fmt(60000), '01:00');
assert.equal(C.fmt(59001), '01:00');
assert.equal(C.fmt(59001, true), '00:59');
assert.equal(C.fmt(3723000), '1:02:03');

// timer: set, run, pause, resume, add while running, stopwatch, reset
C.timerAct('reset');
C.timerAct('5'); C.timerAct('1');
assert.equal(C.timer.mode, 'idle'); assert.equal(C.timer.left, 360000);
C.timerAct('go');
assert.equal(C.timer.mode, 'down'); assert.ok(Math.abs(C.timer.end - Date.now() - 360000) < 50);
C.timerAct('1');
assert.ok(Math.abs(C.timer.end - Date.now() - 420000) < 50);
C.timerAct('go');
assert.equal(C.timer.mode, 'paused'); assert.ok(C.timer.left > 419000);
C.timerAct('go');
assert.equal(C.timer.mode, 'down');
C.timerAct('reset');
assert.deepEqual([C.timer.mode, C.timer.left], ['idle', 0]);
C.timerAct('go');  // nothing set: nothing to count down (the stopwatch is its own page now)
assert.equal(C.timer.mode, 'idle');
C.timerAct('5');
assert.deepEqual([C.timer.mode, C.timer.left], ['idle', 300000]);
assert.equal(JSON.parse(store['deskmon-timer']).left, 300000);  // survives a reload

// stopwatch: its own state, beside the timer
assert.equal(C.stopwatch.mode, 'idle');
C.stopwatchAct('go');
assert.equal(C.stopwatch.mode, 'run'); assert.ok(Math.abs(C.stopwatch.start - Date.now()) < 50);
C.stopwatchAct('go');
assert.equal(C.stopwatch.mode, 'paused'); assert.ok(C.stopwatch.acc >= 0);
C.stopwatchAct('go');
assert.equal(C.stopwatch.mode, 'run');
assert.equal(C.timer.left, 300000);          // the timer is untouched
C.stopwatchAct('reset');
assert.deepEqual([C.stopwatch.mode, C.stopwatch.acc], ['idle', 0]);
assert.equal(JSON.parse(store['deskmon-stopwatch']).mode, 'idle');
console.log('Clock: 5 looks, Chinese time words, countdown / pause / stopwatch timer.');
