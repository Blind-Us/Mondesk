const assert = require('node:assert/strict');
require('../web/companion.js');
const C = globalThis.DeskMonCompanion;

// typing: every character appears in order, punctuation adds a pause
const line = '印好了！記得降溫再拿。';
const times = C.revealTimes(line);
assert.equal(times.length, Array.from(line).length);
assert.ok(times.every((t, i) => i === 0 || t > times[i - 1]));
assert.ok(times[4] - times[3] > times[3] - times[2], 'pause after ！');
assert.equal(C.visibleCount(times, -1), 0);
assert.equal(C.visibleCount(times, 1e9), times.length);

// mouth: flaps while typing, closed during the pause after punctuation, null when done
const frames = new Set();
for (let t = 0; t < times[3]; t += 20) frames.add(C.mouthFrame(line, times, t));
assert.deepEqual([...frames].sort(), ['talk_closed', 'talk_open']);
assert.equal(C.mouthFrame(line, times, times[3] + 30), 'talk_closed');   // just after ！
assert.equal(C.mouthFrame(line, times, times.at(-1) + 1), null);
assert.equal(C.mouthFrame('', [], 0), null);

// which face rests on the card
const now = 1_000_000;
assert.equal(C.restingFace({ busy: true, emotion: 'happy', said_at: now }, now), 'thinking');
assert.equal(C.restingFace({ emotion: 'worried', said_at: now - 10 }, now), 'worried');
assert.equal(C.restingFace({ emotion: 'worried', said_at: now - 600 }, now), 'neutral');
assert.equal(C.restingFace({ emotion: 'talk_open', said_at: now }, now), 'neutral');

// only new, fresh lines are spoken (an old line after a page reload is just shown)
assert.equal(C.shouldSpeak(undefined, { line: 'hi', said_at: now - 5 }, now), true);
assert.equal(C.shouldSpeak(now - 5, { line: 'hi', said_at: now - 5 }, now), false);
assert.equal(C.shouldSpeak(undefined, { line: 'hi', said_at: now - 300 }, now), false);
assert.equal(C.shouldSpeak(undefined, { said_at: now }, now), false);

// character packs: image faces carry a version, emoji faces carry text; missing ones use neutral
const faces = { neutral: { text: '🙂' }, happy: { v: '123' } };
assert.deepEqual(C.faceSpec(faces, 'happy'), { face: 'happy', v: '123' });
assert.deepEqual(C.faceSpec(faces, 'sleepy'), { face: 'neutral', text: '🙂' });
assert.equal(C.faceSpec({}, 'happy'), null);

// labels
assert.equal(C.modelName('claude-opus-5-5'), 'Opus 5.5');
assert.equal(C.modelName('claude-haiku-5-5'), 'Haiku 5.5');
assert.equal(C.modelName('ollama:qwen3:8b'), 'Ollama qwen3:8b');
assert.equal(C.modelName('rule'), '規則式');
assert.equal(C.metaText({ event_label: '列印完成', via: 'claude-opus-5-5', latency: 2.34 }), '列印完成 · Opus 5.5 · 2.3 秒');
assert.equal(C.metaText({ simulated: true, event_label: '換歌', via: 'rule', fallback_reason: '尚未設定 API 金鑰' }), '測試 · 換歌 · 規則式（尚未設定 API 金鑰）');

console.log('Companion: typing, mouth frames, resting face, fresh-line detection, faces and labels OK.');
