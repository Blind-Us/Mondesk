/* Companion widget: face + speech area.
   The server publishes the latest utterance ({line, emotion, said_at, character, ...}); this
   file picks the face from the selected character pack (image or giant emoji), types the line
   out and flips between the two talking frames while "speaking" (packs without talking frames
   bounce instead). Pure helpers are exported for tests (tests/test-companion.cjs). */
(function (root) {
  const EMOTIONS = ["neutral", "happy", "thinking", "worried", "surprised", "sleepy"];
  const CPS = 11;              // characters per second while typing
  const LEAD_MS = 450;         // show the expression briefly before the mouth starts moving
  const FLAP_MS = 110;         // mouth open/closed period while typing
  const FRESH_S = 30;          // a line newer than this is "spoken"; older ones just shown
  const EMOTION_HOLD_S = 90;   // then the face relaxes back to neutral
  const PAUSE = { "，": 180, "、": 180, ",": 180, "。": 340, "！": 340, "？": 340, "!": 340, "?": 340, "…": 340 };

  // ms at which each character appears (punctuation adds a short pause after it)
  function revealTimes(text) {
    const chars = Array.from(text || ""), out = [];
    let t = 0;
    for (const c of chars) { out.push(t); t += 1000 / CPS + (PAUSE[c] || 0); }
    return out;
  }
  function visibleCount(times, elapsed) {
    let n = 0;
    while (n < times.length && times[n] <= elapsed) n++;
    return n;
  }
  // talking frame for this moment, or null once the whole line is out
  function mouthFrame(text, times, elapsed) {
    const chars = Array.from(text || ""), n = visibleCount(times, elapsed);
    if (elapsed < 0 || n >= chars.length) return null;
    const last = chars[n - 1];
    if (n > 0 && PAUSE[last] && elapsed - times[n - 1] < 1000 / CPS + PAUSE[last] - 40) return "talk_closed";
    return Math.floor(elapsed / FLAP_MS) % 2 ? "talk_closed" : "talk_open";
  }
  function restingFace(data, nowS) {
    if (data.busy) return "thinking";
    const e = EMOTIONS.includes(data.emotion) ? data.emotion : "neutral";
    return data.said_at && nowS - data.said_at < EMOTION_HOLD_S ? e : "neutral";
  }
  function shouldSpeak(lastSaidAt, data, nowS) {
    return !!(data.line && data.said_at && data.said_at !== lastSaidAt && nowS - data.said_at < FRESH_S);
  }
  // a face of the pack, falling back to neutral: {face, v} for images or {face, text} for emoji
  function faceSpec(faces, name) {
    const face = faces?.[name] ? name : faces?.neutral ? "neutral" : null;
    return face ? { face, ...faces[face] } : null;
  }
  function modelName(via) {
    if (!via) return "";
    if (via === "rule") return "規則式";
    if (via.startsWith("ollama:")) return "Ollama " + via.slice(7);
    const m = /^claude-([a-z]+)-(\d+)(?:-(\d+))?/.exec(via);
    return m ? `${m[1][0].toUpperCase()}${m[1].slice(1)} ${m[2]}${m[3] ? "." + m[3] : ""}` : via;
  }
  function metaText(d) {
    const parts = [];
    if (d.simulated) parts.push("測試");
    if (d.event_label) parts.push(d.event_label);
    if (d.fallback_reason) parts.push(`規則式（${d.fallback_reason}）`);
    else if (d.via) parts.push(modelName(d.via) + (d.via !== "rule" && d.latency != null ? ` · ${d.latency.toFixed(1)} 秒` : ""));
    return parts.join(" · ");
  }

  // sprite sheets (Codex pets etc.): background-size/position of one cell of a cols x rows grid
  const SPRITE_FPS = 8;
  function spriteStyle(sprite, rows, frame) {
    const cols = sprite.columns, row = Math.min(sprite.row, rows - 1), col = frame % sprite.frames;
    const pct = (i, n) => (n > 1 ? (i / (n - 1)) * 100 : 0);
    return { size: `${cols * 100}% ${rows * 100}%`, position: `${pct(col, cols)}% ${pct(row, rows)}%` };
  }
  function sheetRows(sprite, width, height) {
    const [cw, ch] = sprite.cell, cellH = (width / sprite.columns) * (ch / cw);
    return Math.max(1, Math.round(height / cellH));
  }

  const LINGER_S = 45;  // seconds a spoken line stays on the card

  class Companion {
    constructor(card, opts = {}) {
      this.card = card; this.opts = opts; this.data = {}; this.lastSaidAt = undefined; this.preloaded = "";
      card.innerHTML = `<div class="cp-inner">
          <button class="cp-face" type="button" aria-label="點一下，讓角色回報目前狀態">
            <img class="cp-img" alt="" draggable="false" hidden><span class="cp-glyph" aria-hidden="true" hidden></span>
            <span class="cp-sprite" aria-hidden="true" hidden></span>
            <span class="cp-dots" hidden><i></i><i></i><i></i></span></button>
          <div class="cp-bubble"><p class="cp-line" aria-hidden="true"></p><div class="cp-meta"></div>
            <span class="cp-live" role="status" aria-live="polite"></span></div>
        </div>`;
      const $ = s => card.querySelector(s);
      this.img = $(".cp-img"); this.glyph = $(".cp-glyph"); this.sprite = $(".cp-sprite"); this.dots = $(".cp-dots");
      this.bubble = $(".cp-bubble"); this.lineEl = $(".cp-line"); this.metaEl = $(".cp-meta");
      $(".cp-face").addEventListener("click", () => this.tap());
      // touching anything else puts the current line away (card and pop-up), so it never sits in the way
      addEventListener("pointerdown", e => { if (!this.card.contains(e.target) && this.data?.said_at) this.dismiss(); }, true);
      this.bubble.addEventListener("click", () => { if (this.speaking) { this.started = -1e12; this.frame(); } });
    }

    get faces() { return this.data.character?.faces || {}; }
    get hasTalk() { return !!(this.faces.talk_open && this.faces.talk_closed); }
    faceUrl(name) {
      const spec = faceSpec(this.faces, name), id = this.data.character?.id;
      return spec?.v && id ? `/api/companion/character/${encodeURIComponent(id)}/${spec.face}?v=${spec.v}` : "";
    }
    sheetUrl(sprite) {
      const id = this.data.character?.id;
      return id ? `/api/companion/character/${encodeURIComponent(id)}/sheet?v=${sprite.v}` : "";
    }
    setFace(name) {
      const spec = faceSpec(this.faces, name);
      if (spec?.sprite) {
        this.showSprite(spec.sprite);
        this.img.hidden = true; this.glyph.hidden = true;
      } else {
        this.stopSprite();
        if (spec?.text != null) {
          if (this.glyph.textContent !== spec.text) this.glyph.textContent = spec.text;
          this.glyph.hidden = false; this.img.hidden = true;
        } else {
          const url = this.faceUrl(name);
          if (url && this.img.getAttribute("src") !== url) this.img.src = url;
          this.img.hidden = !url; this.glyph.hidden = true;
        }
      }
      this.card.dataset.face = name;
    }
    // play one row of the sheet in a loop; the same row keeps its frame (talk_open/closed share one)
    showSprite(sprite) {
      const url = this.sheetUrl(sprite), el = this.sprite;
      if (this.spriteUrl !== url) {
        this.spriteUrl = url; this.rows = 0;
        const img = new Image();
        img.onload = () => { if (this.spriteUrl === url) { this.rows = sheetRows(sprite, img.naturalWidth, img.naturalHeight); this.drawSprite(); } };
        img.src = url;
        el.style.backgroundImage = `url("${url}")`;
        el.style.aspectRatio = `${sprite.cell[0]} / ${sprite.cell[1]}`;
        el.style.setProperty("--ar", sprite.cell[0] / sprite.cell[1]);
      }
      if (this.spriteRow?.row !== sprite.row) { this.spriteRow = sprite; this.spriteFrame = 0; }
      el.hidden = false;
      this.drawSprite();
      if (!this.spriteTimer) this.spriteTimer = setInterval(() => { this.spriteFrame++; this.drawSprite(); }, 1000 / SPRITE_FPS);
    }
    drawSprite() {
      if (!this.rows || !this.spriteRow) return;
      const s = spriteStyle(this.spriteRow, this.rows, this.spriteFrame);
      this.sprite.style.backgroundSize = s.size; this.sprite.style.backgroundPosition = s.position;
    }
    stopSprite() {
      clearInterval(this.spriteTimer); this.spriteTimer = null; this.spriteRow = null;
      this.sprite.hidden = true;
    }
    preload() {
      const key = JSON.stringify(this.data.character || {});
      if (key === this.preloaded) return;
      this.preloaded = key;
      const urls = Object.values(this.faces).map(f => f.sprite ? this.sheetUrl(f.sprite) : "")
        .concat(Object.keys(this.faces).map(n => this.faceUrl(n)));
      this.images = [...new Set(urls.filter(Boolean))].map(src => Object.assign(new Image(), { src }));
    }

    update(m) {
      const d = this.data = m.data || {};
      const nowS = Date.now() / 1000;
      this.preload();
      if (this.lastSaidAt === undefined && !shouldSpeak(undefined, d, nowS)) this.lastSaidAt = d.said_at ?? null;
      if (shouldSpeak(this.lastSaidAt, d, nowS)) this.speak(d);
      const waiting = d.busy || (this.tapAt && Date.now() - this.tapAt < 30000 && d.said_at === this.tapSaidAt);
      this.dots.hidden = !waiting;
      if (!this.speaking) {
        // resting: the last line stays a little while, then only the face is left
        const fresh = d.line && d.said_at && nowS - d.said_at < LINGER_S && d.said_at !== this.dismissed;
        this.bubble.classList.toggle("idle", !fresh);
        this.lineEl.textContent = fresh ? d.line : "";
        this.metaEl.textContent = "";
        this.setFace(waiting ? "thinking" : restingFace(d, nowS));
      }
    }

    speak(d) {
      this.lastSaidAt = d.said_at; this.tapAt = 0; this.dismissed = null;
      this.line = d.line; this.times = revealTimes(d.line); this.started = Date.now() + LEAD_MS;
      this.speaking = true;
      this.bubble.classList.remove("idle");
      this.bubble.classList.remove("pop"); void this.bubble.offsetWidth; this.bubble.classList.add("pop");
      this.lineEl.textContent = "";
      this.metaEl.textContent = "";
      this.bubble.querySelector(".cp-live").textContent = d.line;
      this.setFace(EMOTIONS.includes(d.emotion) ? d.emotion : "neutral");
      clearInterval(this.timer);
      this.timer = setInterval(() => this.frame(), 40);
    }

    frame() {
      const elapsed = Date.now() - this.started;
      if (elapsed < 0) return;
      this.lineEl.textContent = Array.from(this.line).slice(0, visibleCount(this.times, elapsed)).join("");
      const mouth = mouthFrame(this.line, this.times, elapsed);
      if (mouth) {
        if (this.hasTalk) this.setFace(mouth);
        else this.card.classList.add("talking");  // no mouth frames in this pack: bounce instead
        return;
      }
      clearInterval(this.timer);
      this.speaking = false;
      this.card.classList.remove("talking");
      this.setFace(restingFace(this.data, Date.now() / 1000));
    }

    // the line goes away now: stop revealing it, show only the face
    dismiss() {
      if (this.dismissed === this.data.said_at) return;
      this.dismissed = this.data.said_at;
      if (this.speaking) { clearInterval(this.timer); this.speaking = false; this.card.classList.remove("talking"); }
      this.bubble.classList.add("idle");
      this.lineEl.textContent = "";
      this.setFace(restingFace(this.data, Date.now() / 1000));
    }

    async tap() {
      if (this.data.busy || this.speaking) return;
      this.tapAt = Date.now(); this.tapSaidAt = this.data.said_at;
      this.dots.hidden = false; this.setFace("thinking");
      try {
        const r = await fetch("/api/action", { method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ module: this.opts.id, action: "tap" }) });
        const result = await r.json();
        if (!r.ok || !result.ok) throw Error(result.error || "沒有回應");
        if (!result.result.queued) { this.tapAt = 0; this.card.classList.add("nudge"); setTimeout(() => this.card.classList.remove("nudge"), 500); }
        else this.opts.onWait?.(() => this.data.said_at !== this.tapSaidAt);
      } catch { this.tapAt = 0; }
    }

    destroy() { clearInterval(this.timer); clearInterval(this.spriteTimer); }
  }

  // app.js entry point: mount once per card, then feed it every state update
  function update(card, m, opts = {}) {
    if (!card._companion) card._companion = new Companion(card, { ...opts, id: m.id });
    card._companion.update(m);
  }

  root.DeskMonCompanion = { EMOTIONS, revealTimes, visibleCount, mouthFrame, restingFace, shouldSpeak, faceSpec,
    modelName, metaText, spriteStyle, sheetRows, update, Companion };
})(globalThis);
