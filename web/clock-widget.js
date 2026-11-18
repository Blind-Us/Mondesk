/* Custom clock card (modules/clock.py). Five looks: digital, analog, flip, ring, words.
   The card itself is only a clock (plus one small line while a timer or the stopwatch runs): it is too
   small for controls. Tapping it opens the clock full screen with three pages: clock, countdown timer
   (set by turning wheels: hours / minutes / seconds) and stopwatch. Pages change with the tabs or the
   mouse wheel, sliding up or down; never by swiping (a sideways drag selects text).
   The card is built once per look/option set and then only its numbers move, once a second.
   Sizing is all CSS container queries (style.css "clock"), so any card size works. */
(() => {
  const STYLES = ["digital", "analog", "flip", "ring", "words"];
  const WEEK = "日一二三四五六";
  const CN = "零一二三四五六七八九十";
  const pad = n => String(n).padStart(2, "0");
  const cn = n => n <= 10 ? CN[n] : n < 20 ? "十" + (n % 10 ? CN[n % 10] : "") : CN[Math.floor(n / 10)] + "十" + (n % 10 ? CN[n % 10] : "");

  function options(m) {
    const d = m.data || {};
    return { style: STYLES.includes(d.style) ? d.style : "digital", hour12: !!d.hour12,
      seconds: d.seconds !== false, date: d.date !== false, color: d.color || "", timer: !!d.timer };
  }

  function parts(now, o) {
    const h = now.getHours(), m = now.getMinutes(), s = now.getSeconds();
    const h12 = h % 12 || 12;
    return {
      h, m, s, ms: now.getMilliseconds(),
      hh: o.hour12 ? String(h12) : pad(h), mm: pad(m), ss: pad(s),
      ap: h < 12 ? "上午" : "下午",
      date: `${now.getMonth() + 1}月${now.getDate()}日 週${WEEK[now.getDay()]}`,
      dshort: `${now.getMonth() + 1}/${now.getDate()} 週${WEEK[now.getDay()]}`,
      period: h < 5 ? "凌晨" : h < 11 ? "早上" : h < 13 ? "中午" : h < 18 ? "下午" : "晚上",
      wordsHour: (h12 === 2 ? "兩" : cn(h12)) + "點",
      wordsMin: m === 0 ? "整" : m === 30 ? "半" : (m < 10 ? "零" : "") + cn(m) + "分",
    };
  }

  // ---------- the looks ----------
  const ticks = (r1, rMajor, rMinor) => Array.from({ length: 60 }, (_, i) => {
    const major = i % 5 === 0, a = i * Math.PI / 30, r2 = major ? rMajor : rMinor;
    const x = r => (100 + r * Math.sin(a)).toFixed(2), y = r => (100 - r * Math.cos(a)).toFixed(2);
    return `<line class="${major ? "maj" : "min"}" x1="${x(r1)}" y1="${y(r1)}" x2="${x(r2)}" y2="${y(r2)}"/>`;
  }).join("");

  // digital time + date beside (wide card) or under (tall card) a round face
  const info = o => `<div class="ck-info"><div class="ck-itime"><span data-k="hh"></span>:<span data-k="mm"></span>${o.hour12 ? '<em data-k="ap"></em>' : ""}</div>${o.date ? '<div class="ck-idate" data-k="date"></div>' : ""}</div>`;
  const date = o => o.date ? '<div class="ck-date" data-k="date"></div>' : "";

  const BUILD = {
    digital: o => `<div class="ck-main">
        <div class="ck-time">${o.hour12 ? '<em class="ck-ap" data-k="ap"></em>' : ""}<span data-k="hh"></span><i class="ck-colon">:</i><span data-k="mm"></span>${o.seconds ? '<small class="ck-s" data-k="ss"></small>' : ""}</div>${date(o)}</div>`,

    analog: o => `<div class="ck-face"><svg viewBox="0 0 200 200" aria-hidden="true">
        <circle class="ck-dial" cx="100" cy="100" r="97"/>${ticks(91, 77, 85)}
        <line class="ck-hand hr" data-k="hr" x1="100" y1="112" x2="100" y2="54"/>
        <line class="ck-hand mn" data-k="mn" x1="100" y1="116" x2="100" y2="26"/>
        ${o.seconds ? '<line class="ck-hand sc" data-k="sc" x1="100" y1="124" x2="100" y2="20"/>' : ""}
        <circle class="ck-pin" cx="100" cy="100" r="5"/></svg></div>${info(o)}`,

    flip: o => `<div class="ck-main">
        <div class="ck-tiles">${o.hour12 ? '<em class="ck-ap" data-k="ap"></em>' : ""}<b class="ck-tile" data-k="hh"></b><b class="ck-tile" data-k="mm"></b>${o.seconds ? '<b class="ck-tile sec" data-k="ss"></b>' : ""}</div>${date(o)}</div>`,

    ring: o => `<div class="ck-face"><svg viewBox="0 0 200 200" aria-hidden="true">
        ${[["hr", 90], ["mn", 72], ...(o.seconds ? [["sc", 54]] : [])].map(([k, r]) =>
          `<circle class="ck-track" cx="100" cy="100" r="${r}"/><circle class="ck-arc ${k}" data-k="${k}" cx="100" cy="100" r="${r}" pathLength="100" stroke-dasharray="0 100" transform="rotate(-90 100 100)"/>`).join("")}
        <text class="ck-rtime" x="100" y="${o.date ? 106 : 112}" text-anchor="middle"><tspan data-k="hh"></tspan>:<tspan data-k="mm"></tspan></text>
        ${o.date ? '<text class="ck-rdate" x="100" y="128" text-anchor="middle" data-k="dshort"></text>' : ""}</svg></div>${info(o)}`,

    words: o => `<div class="ck-main">
        <div class="ck-period" data-k="period"></div>
        <div class="ck-phrase"><span data-k="wh"></span><span data-k="wm"></span></div>${date(o)}</div>`,
  };

  // ---------- timer page ----------
  const TM_ICON = {
    go: '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z"/></svg>',
    pause: '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M7 5h4v14H7zM13 5h4v14h-4z"/></svg>',
    reset: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 12a8 8 0 1 0 2.4-5.7M4 4v5h5"/></svg>',
  };
  const WHEELS = [["h", 24, "時"], ["m", 60, "分"], ["s", 60, "秒"]];
  const WHEEL_HTML = `<div class="tm-wheels">${WHEELS.map(([k, n, unit]) =>
    `<div class="tm-wheel"><div class="tm-col" data-w="${k}" tabindex="0" aria-label="${unit}">${Array.from({ length: n }, (_, i) => `<b>${pad(i)}</b>`).join("")}</div><span>${unit}</span></div>`).join("")}</div>`;
  const buttons = kind => `<div class="tm-btns"><button type="button" data-${kind}="go" class="main" data-t="go" aria-label="開始／暫停"></button>
        <button type="button" data-${kind}="reset" aria-label="重設">${TM_ICON.reset}</button></div>`;
  // on the card: the time only. Full screen: wheels and buttons.
  const timerPage = full => `<div class="ck tm tm-timer${full ? " tm-full" : ""}">
      <div class="tm-main"><div class="tm-label" data-t="label"></div>${full ? WHEEL_HTML : ""}<div class="tm-time" data-t="time"></div></div>${full ? buttons("tm") : ""}</div>`;
  const stopwatchPage = full => `<div class="ck tm tm-sw">
      <div class="tm-main"><div class="tm-label" data-t="label"></div><div class="tm-time" data-t="time"></div></div>${full ? buttons("sw") : ""}</div>`;
  const PAGE_NAMES = ["時鐘", "計時", "碼錶"];

  // one timer and one stopwatch for the whole panel; kept in the browser so a reload doesn't lose a running one
  // timer: idle (left = set time) · down (running until `end`) · paused (left) · done
  // stopwatch: idle · run (since `start`) · paused (acc)
  let TM = { mode: "idle", left: 0, end: 0 };
  let SW = { mode: "idle", start: 0, acc: 0 };
  try { Object.assign(TM, JSON.parse(localStorage.getItem("deskmon-timer")) || {}); } catch {}
  try { Object.assign(SW, JSON.parse(localStorage.getItem("deskmon-stopwatch")) || {}); } catch {}
  if (TM.mode === "up" || TM.mode === "uppaused") {   // saved by an older version, where the timer doubled as the stopwatch
    SW = { mode: TM.mode === "up" ? "run" : "paused", start: TM.start || 0, acc: TM.acc || 0 };
    TM = { mode: "idle", left: 0, end: 0 };
  }
  const saveTM = () => { try { localStorage.setItem("deskmon-timer", JSON.stringify(TM)); } catch {} };
  const saveSW = () => { try { localStorage.setItem("deskmon-stopwatch", JSON.stringify(SW)); } catch {} };

  function timerAct(act) {
    const now = Date.now();
    if (act === "1" || act === "5") {
      const add = +act * 60000;
      if (TM.mode === "down") TM.end += add;
      else if (TM.mode === "idle" || TM.mode === "paused") TM.left = Math.min(TM.left + add, 100 * 3600000 - 1000);
      else TM = { mode: "idle", left: add, end: 0 };  // done: start a new countdown
    } else if (act === "go") {
      if (TM.mode === "idle") { if (TM.left > 0) Object.assign(TM, { mode: "down", end: now + TM.left }); }
      else if (TM.mode === "paused") Object.assign(TM, { mode: "down", end: now + TM.left });
      else if (TM.mode === "down") Object.assign(TM, { mode: "paused", left: Math.max(0, TM.end - now) });
      else TM = { mode: "idle", left: 0, end: 0 };
    } else if (act === "reset") TM = { mode: "idle", left: 0, end: 0 };
    if (TM.mode !== "done") stopAlarm();
    saveTM();
  }
  function stopwatchAct(act) {
    const now = Date.now();
    if (act === "reset") SW = { mode: "idle", start: 0, acc: 0 };
    else if (SW.mode === "run") Object.assign(SW, { mode: "paused", acc: now - SW.start });
    else Object.assign(SW, { mode: "run", start: now - (SW.mode === "paused" ? SW.acc : 0) });
    saveSW();
  }

  // countdowns round up (01:00 until a full second has gone), the stopwatch rounds down
  const fmt = (ms, up) => {
    const t = Math.max(0, Math[up ? "floor" : "ceil"](ms / 1000 - 1e-6)), h = Math.floor(t / 3600), m = Math.floor(t % 3600 / 60), s = t % 60;
    return h ? `${h}:${pad(m)}:${pad(s)}` : `${pad(m)}:${pad(s)}`;
  };

  // beeps: the AudioContext is created on a button press (browsers only allow sound after a touch)
  let audio = null, alarmTimer = null;
  const ensureAudio = () => { try { audio ??= new AudioContext(); audio.resume(); } catch {} };
  function beep() {
    if (!audio) return;
    const t = audio.currentTime;
    for (let i = 0; i < 3; i++) {
      const osc = audio.createOscillator(), g = audio.createGain();
      osc.frequency.value = 880; osc.connect(g); g.connect(audio.destination);
      g.gain.setValueAtTime(0.0001, t + i * .25); g.gain.exponentialRampToValueAtTime(.3, t + i * .25 + .02);
      g.gain.exponentialRampToValueAtTime(.0001, t + i * .25 + .18);
      osc.start(t + i * .25); osc.stop(t + i * .25 + .2);
    }
  }
  function startAlarm() {
    let n = 0; beep(); clearInterval(alarmTimer);
    alarmTimer = setInterval(() => (++n >= 15 ? clearInterval(alarmTimer) : beep()), 2000);  // about 30 s at most
  }
  function stopAlarm() { clearInterval(alarmTimer); alarmTimer = null; }

  // ---------- wheels (full screen): each column is a list; the number in the middle counts ----------
  // The list is lined up by this code, not by CSS scroll snapping: the rows are a fraction of a pixel tall
  // (they scale with the screen), and the browser's snapping then jumps back to another row by itself.
  const rowHeight = col => (col.scrollHeight - col.clientHeight) / Math.max(1, col.children.length - 1) || 1;   // exact, with fractions
  const wheelValue = col => Math.max(0, Math.min(col.children.length - 1, Math.round(col.scrollTop / rowHeight(col))));
  const turnTo = (col, i) => { col.scrollTop = Math.max(0, Math.min(col.children.length - 1, i)) * rowHeight(col); };
  function readWheels(el) {
    const v = {};
    for (const col of el.querySelectorAll(".tm-col")) {
      const i = v[col.dataset.w] = wheelValue(col);
      for (let k = 0; k < col.children.length; k++) col.children[k].classList.toggle("on", k === i);
    }
    return ((v.h || 0) * 3600 + (v.m || 0) * 60 + (v.s || 0)) * 1000;
  }
  function setWheels(el, ms) {
    const t = Math.round(ms / 1000), v = { h: Math.min(23, Math.floor(t / 3600)), m: Math.floor(t % 3600 / 60), s: t % 60 };
    for (const col of el.querySelectorAll(".tm-col")) if (col.clientHeight && wheelValue(col) !== v[col.dataset.w]) turnTo(col, v[col.dataset.w]);
    readWheels(el);
  }
  // what the wheels show becomes the timer's time. Called right where a wheel is turned, not only from the
  // scroll event: that event can come late, and the once-a-second tick must not undo the turn meanwhile.
  function commitWheels(el) {
    const left = readWheels(el);
    if (TM.mode !== "idle") return;
    if (left !== TM.left) { TM.left = left; saveTM(); }
    el._tmSeen = TM.left;
  }
  function wireWheel(el, col) {
    let dragging = false, rest = 0;
    const turn = i => { turnTo(col, i); commitWheels(el); };
    col.addEventListener("scroll", () => {
      commitWheels(el);
      // once it stops moving (a finger's flick has run out), line the nearest number up in the middle
      clearTimeout(rest);
      rest = setTimeout(() => { if (!dragging) turn(wheelValue(col)); }, 160);
    }, { passive: true });
    // a finger scrolls the list by itself; a mouse has to drag it
    col.addEventListener("pointerdown", e => {
      if (e.pointerType !== "mouse" || e.button) return;
      const y0 = e.clientY, top0 = col.scrollTop;
      dragging = true;
      try { col.setPointerCapture(e.pointerId); } catch {}
      const move = ev => { col.scrollTop = top0 - (ev.clientY - y0); };
      const up = () => {
        col.removeEventListener("pointermove", move); col.removeEventListener("pointerup", up); col.removeEventListener("pointercancel", up);
        dragging = false;
        turn(wheelValue(col));
      };
      col.addEventListener("pointermove", move); col.addEventListener("pointerup", up); col.addEventListener("pointercancel", up);
    });
    // one notch of the mouse wheel turns the wheel by exactly one number (the browser's own scrolling jumps two or three)
    let turned = 0;
    col.addEventListener("wheel", e => {
      e.preventDefault(); e.stopPropagation();
      turned += e.deltaMode === 1 ? e.deltaY * 40 : e.deltaY;
      if (Math.abs(turned) < 40) return;     // a touchpad sends many small moves: wait until they add up to a notch
      const step = Math.sign(turned); turned = 0;
      turn(wheelValue(col) + step);
    }, { passive: false });
    col.addEventListener("keydown", e => {
      const step = { ArrowUp: -1, ArrowDown: 1 }[e.key];
      if (!step) return;
      e.preventDefault();
      turn(wheelValue(col) + step);
    });
  }

  // time's up: a soft light breathes in from all four edges of the screen (a card's own border is too thin to notice)
  function glow(on) {
    let g = document.getElementById("tm-glow");
    if (!on) { g?.remove(); return; }
    if (g) return;
    g = document.createElement("div"); g.id = "tm-glow";
    (document.getElementById("lyrics")?.parentNode || document.body).append(g);
  }

  function goPage(el, i, slide = true) {
    const pages = el.querySelector(".ck-pages");
    if (!pages) return;
    i = Math.max(0, Math.min(pages.children.length - 1, i));
    const from = el._page || 0;
    el._page = i;
    pages.scrollTo({ left: i * pages.clientWidth, behavior: "instant" });
    el.querySelectorAll("[data-pg]").forEach((d, k) => d.classList.toggle("on", k === i));
    // The new page slides in from below (next) or above (previous). The page is already in place before the
    // slide starts and the slide is cancelled by a timer, so a window that never advances animations (an
    // unfocused one on a second screen) simply shows the page.
    const page = pages.children[i]?.firstElementChild;
    if (!slide || i === from || !page?.animate || document.documentElement.dataset.motion === "off") return;
    const anim = page.animate([{ transform: `translateY(${i > from ? 28 : -28}%)`, opacity: 0 }, { transform: "none", opacity: 1 }],
      { duration: 260, easing: "cubic-bezier(.2, .7, .2, 1)" });
    setTimeout(() => anim.cancel(), 320);
  }

  // once a second, whether or not a timer page is on screen: has the countdown run out?
  function checkTimer() {
    const now = Date.now();
    if (TM.mode === "down" && TM.end <= now) {
      TM.mode = "done"; saveTM(); startAlarm();
      // tell the event centre once (the Companion says it; without one the panel shows a toast)
      if (now - TM.end < 15000) fetch("/api/event", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: "timer_done" }) }).catch(() => {});
    }
    glow(TM.mode === "done");
  }
  const timerLeft = now => ({ idle: TM.left, paused: TM.left, down: TM.end - now, done: 0 }[TM.mode] ?? 0);
  const stopwatchTime = now => SW.mode === "run" ? now - SW.start : SW.mode === "paused" ? SW.acc : 0;

  function tickTimer(el) {
    const set = (box, k, v, html) => { const n = box.querySelector(`[data-t="${k}"]`); if (n && n[html ? "innerHTML" : "textContent"] !== v) n[html ? "innerHTML" : "textContent"] = v; };
    const now = Date.now();
    // the card: one small line under the clock while something is running
    const run = el.querySelector(".ck-run");
    if (run) {
      const text = TM.mode === "done" ? "時間到！" : TM.mode === "down" ? `計時 ${fmt(timerLeft(now))}` : TM.mode === "paused" ? `計時暫停 ${fmt(TM.left)}`
        : SW.mode === "run" ? `碼錶 ${fmt(stopwatchTime(now), true)}` : SW.mode === "paused" ? `碼錶暫停 ${fmt(SW.acc, true)}` : "";
      if (run.textContent !== text) run.textContent = text;
      run.hidden = !text;
      run.classList.toggle("done", TM.mode === "done");
    }
    const sw = el.querySelector(".tm-sw");
    if (sw) {
      const ms = stopwatchTime(now);
      set(sw, "time", fmt(ms, true));
      set(sw, "label", SW.mode === "paused" ? "碼錶 · 已暫停" : "碼錶");
      set(sw, "go", SW.mode === "run" ? TM_ICON.pause : TM_ICON.go, true);
      sw.dataset.mode = SW.mode;
      sw.classList.toggle("long", ms >= 3600000);
    }
    const box = el.querySelector(".tm-timer");
    if (!box) return;
    // time's up: bring the timer page into view once
    if (TM.mode !== "done") el._doneShown = false;
    else if (!el._doneShown && el.querySelector(".ck-pages")?.clientWidth) { el._doneShown = true; goPage(el, 1); }
    const ms = timerLeft(now);
    // the wheels are set from the timer only when the timer was changed elsewhere (reset, time's up), never
    // just because they differ: that would undo a wheel that is being turned
    if (TM.mode !== "idle") el._tmSeen = null;
    else if (el._tmSeen !== TM.left && box.querySelector(".tm-col")?.clientHeight) { setWheels(el, TM.left); el._tmSeen = TM.left; }
    set(box, "time", fmt(ms));
    set(box, "label", { idle: "計時器", paused: "計時器 · 已暫停", down: "倒數中", done: "時間到！" }[TM.mode]);
    set(box, "go", TM.mode === "down" ? TM_ICON.pause : TM_ICON.go, true);
    box.dataset.mode = TM.mode;
    box.classList.toggle("long", ms >= 3600000);
  }

  // ---------- card ----------
  function build(el, o) {
    el.dataset.style = o.style;
    el.classList.toggle("ck-has-s", o.seconds);
    el.classList.toggle("ck-12", o.hour12);
    el.style.setProperty("--ck", o.color || "var(--text)");
    el.style.setProperty("--ck2", o.color || "var(--accent)");
    // full screen: clock, timer, stopwatch, with named tabs. The card: the clock, and a line for what is running.
    const extra = o.full ? [timerPage(true), stopwatchPage(true)] : [];
    const nav = o.full
      ? `<div class="ck-tabs">${PAGE_NAMES.map((n, i) => `<button type="button" data-pg="${i}"${i ? "" : ' class="on"'}>${n}</button>`).join("")}</div>`
      : '<div class="ck-run" hidden></div>';
    el.innerHTML = `<div class="ck-pages"><div class="ck-page"><div class="ck ck-${o.style}">${BUILD[o.style](o)}</div></div>${
      extra.map(page => `<div class="ck-page">${page}</div>`).join("")}</div>${nav}`;
    el._ck = { o, nodes: [...el.querySelectorAll(".ck-page:first-child [data-k]")], last: {} };
    el._page = 0;
    const pages = el.querySelector(".ck-pages");
    let wheelAt = 0;
    pages.addEventListener("wheel", e => {
      if (!o.full || Math.abs(e.deltaX) > Math.abs(e.deltaY) || e.target.closest(".tm-col")) return;   // over a wheel, the mouse wheel turns that wheel
      e.preventDefault();
      if (Date.now() - wheelAt < 350) return;   // one notch, one page
      wheelAt = Date.now();
      goPage(el, (el._page || 0) + Math.sign(e.deltaY));
    }, { passive: false });
    if (o.full) for (const col of el.querySelectorAll(".tm-col")) wireWheel(el, col);
    if (!el._ckBound) {
      el._ckBound = true;
      el.addEventListener("click", e => {
        const full = el._ck?.o.full;
        if (e.target.closest(".ck-tabs [data-pg]")) return goPage(el, +e.target.closest("[data-pg]").dataset.pg);
        const b = e.target.closest("[data-tm], [data-sw]");
        if (b) {
          ensureAudio();
          if (b.dataset.tm) timerAct(b.dataset.tm); else stopwatchAct(b.dataset.sw);
          for (const card of live) tickTimer(card);
          return;
        }
        if (TM.mode === "done") { timerAct("reset"); for (const card of live) tickTimer(card); return; }   // any tap answers the alarm
        // a tap on the card opens the clock full screen on the same page (not while the layout is being edited)
        // ...on the page of whatever is running
        if (!full && !e.target.closest(".card-cfg, a, button") && !document.body.classList.contains("editing"))
          openFull(el, TM.mode !== "idle" ? 1 : SW.mode !== "idle" ? 2 : 0);
      });
    }
  }

  function tick(el, now = new Date()) {
    const st = el._ck;
    if (!st) return;
    const p = parts(now, st.o), last = st.last;
    const text = { hh: p.hh, mm: p.mm, ss: p.ss, ap: p.ap, date: p.date, dshort: p.dshort, period: p.period, wh: p.wordsHour, wm: p.wordsMin };
    const angle = { hr: (p.h % 12 + p.m / 60) * 30, mn: (p.m + p.s / 60) * 6, sc: p.s * 6 };
    const ring = { hr: (p.h % 12 + p.m / 60) / 12 * 100, mn: (p.m + p.s / 60) / 60 * 100, sc: p.s / 60 * 100 };
    for (const n of st.nodes) {
      const k = n.dataset.k;
      if (n.classList.contains("ck-hand")) n.setAttribute("transform", `rotate(${angle[k].toFixed(2)} 100 100)`);
      else if (n.classList.contains("ck-arc")) n.setAttribute("stroke-dasharray", `${ring[k].toFixed(2)} 100`);
      else if (n.textContent !== text[k]) {
        n.textContent = text[k];
        // flip tiles fold down when their number changes (not on first paint)
        if (n.classList.contains("ck-tile") && last[k] != null) { n.classList.remove("flip"); void n.offsetWidth; n.classList.add("flip"); }
      }
      last[k] = text[k];
    }
    if (st.o.style === "words") {  // phrase length drives its font size
      el.style.setProperty("--wl", p.wordsHour.length + p.wordsMin.length);
      el.style.setProperty("--wl2", Math.max(p.wordsHour.length, p.wordsMin.length, 2));
    }
    tickTimer(el);
  }

  const live = new Set();
  let timer = null;
  function loop() {
    checkTimer();
    for (const el of live) if (!el.isConnected) live.delete(el); else tick(el);
    timer = live.size ? setTimeout(loop, 1000 - Date.now() % 1000 + 5) : null;  // land just after each new second
  }

  function update(el, m) {
    const o = options(m), key = JSON.stringify(o);
    if (el._ckKey !== key) { el._ckKey = key; build(el, o); tick(el); }
    live.add(el);
    if (!timer) loop();
  }

  // ---------- full screen ----------
  let fullPage = null;
  function openFull(card, page = 0) {
    const o = card._ck?.o;
    if (fullPage || !o) return;
    fullPage = document.createElement("div");
    fullPage.id = "ckfull";
    fullPage.innerHTML = '<div class="card clock ckf"></div><button type="button" class="ckf-close" aria-label="關閉全螢幕時鐘">✕</button>';
    (document.getElementById("lyrics")?.parentNode || document.body).append(fullPage);
    const inner = fullPage.firstElementChild;
    build(inner, { ...o, full: true });
    tick(inner);
    goPage(inner, page, false);
    live.add(inner);
    if (!timer) loop();
    fullPage.querySelector(".ckf-close").addEventListener("click", closeFull);
  }
  function closeFull() { fullPage?.remove(); fullPage = null; }
  globalThis.addEventListener?.("keydown", e => { if (e.key === "Escape" && fullPage) closeFull(); });

  window.DeskMonClock = { update, openFull, closeFull, parts, options, timerAct, stopwatchAct, fmt, STYLES, get timer() { return { ...TM }; }, get stopwatch() { return { ...SW }; } };
})();
