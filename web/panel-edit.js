/* Panel edit mode. The pencil in the header turns the panel itself into the layout editor:
   drag a card to move it, drag its corner to resize, × puts it away in the widget drawer,
   and widgets in the drawer can be dragged (or tapped) back onto the panel.
   "完成" saves display.layout = {items, hidden} and switches on a widget's module if needed. */
(() => {
  if (window.frameElement) return;  // the settings page's live preview never edits
  const L = DeskMonLayout;
  const NAMES = { bambu: "列印機", media: "正在播放", tokens: "AI 用量", companion: "Agent", system: "音量／亮度", clock: "時鐘", weather: "天氣" };
  const ICONS = { bambu: "🖨️", media: "🎵", tokens: "📊", companion: "🙂", system: "🔊", clock: "🕒", weather: "⛅" };
  // module added when a widget is dragged out and nothing of that type is configured yet
  const DEFAULTS = {
    bambu: { id: "printer", type: "bambu", title: "Bambu Lab" },
    media: { id: "music", type: "media", title: "Now Playing" },
    tokens: { id: "claude", type: "tokens", provider: "claude", title: "Claude" },
    companion: { id: "companion", type: "companion", title: "Companion", provider: "rule", character: "emoji" },
    system: { id: "system", type: "system", title: "系統" },
    clock: { id: "clock", type: "clock", title: "時鐘", style: "digital", hour12: false, seconds: true, date: true, color: "", timer: false },
    weather: { id: "weather", type: "weather", title: "天氣", place: "", latitude: null, longitude: null },
  };
  const PENCIL = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M4 20h4L19 9a2.8 2.8 0 0 0-4-4L4 16v4z"/><path d="M13.5 6.5l4 4"/></svg>';

  const stage = document.getElementById("stage"), header = stage.querySelector("header");
  const pencil = document.createElement("button");
  pencil.id = "pencil"; pencil.type = "button"; pencil.setAttribute("aria-label", "編輯版面"); pencil.innerHTML = PENCIL;
  document.getElementById("gear").after(pencil);

  const bar = document.createElement("div");
  bar.className = "pe-bar";
  bar.innerHTML = `<button type="button" data-pe="drawer">＋ 小工具</button><button type="button" data-pe="reset">恢復預設</button>
    <span data-pe-mode></span><button type="button" data-pe="cancel">取消</button><button type="button" data-pe="save" class="primary">完成</button>`;
  header.insertBefore(bar, document.getElementById("clock"));
  const drawer = document.createElement("div");
  drawer.className = "pe-drawer";
  stage.appendChild(drawer);

  let ed = null;  // { cfg, items, enabled:Set }
  window.DeskMonPanelEdit = { items: () => ed && ed.items.map(i => ({ ...i })) };

  function toast(text) {
    const t = document.createElement("div");
    t.className = "pe-toast"; t.textContent = text; stage.appendChild(t);
    setTimeout(() => t.remove(), 3500);
  }

  async function enter() {
    let cfg;
    try { cfg = await (await fetch("/api/config", { cache: "no-store" })).json(); }
    catch { return toast("讀不到設定，Mondesk 是否還在執行？"); }
    const enabled = new Set(cfg.modules.filter(m => m.enabled !== false).map(m => m.type));
    // start from exactly what the panel shows now; with a context mode on, that mode is what gets edited
    const mode = typeof currentMode === "function" ? currentMode() : "";
    ed = { cfg, enabled, mode, items: L.place(L.layoutFor(cfg.display, mode), L.WIDGETS.filter(w => enabled.has(w)), false) };   // exactly as saved: gaps stay gaps
    bar.querySelector("[data-pe-mode]").textContent = mode ? `正在編輯「${L.MODES[mode].label}」模式` : "";
    document.body.classList.add("editing");
    draw();
  }

  function exit() {
    ed = null;
    document.body.classList.remove("editing", "pe-open");
    grid.querySelector(".pe-layer")?.remove();
    render();
  }

  function layer() {
    let el = grid.querySelector(".pe-layer");
    if (!el) {
      el = document.createElement("div");
      el.className = "pe-layer";
      el.style.gridTemplateColumns = `repeat(${L.COLS}, minmax(0, 1fr))`;
      el.style.gridTemplateRows = `repeat(${L.ROWS}, minmax(0, 1fr))`;
      grid.appendChild(el);
      el.addEventListener("pointerdown", boxDown);
    }
    return el;
  }

  const area = (el, r) => { el.style.gridColumn = `${r.x + 1} / span ${r.w}`; el.style.gridRow = `${r.y + 1} / span ${r.h}`; };

  function draw() {
    const el = layer();
    el.innerHTML = Array.from({ length: L.COLS * L.ROWS }, (_, i) =>
      `<i class="pe-cell" style="grid-column:${i % L.COLS + 1};grid-row:${Math.floor(i / L.COLS) + 1}"></i>`).join("")
      + ed.items.map(i => `<div class="pe-box${ed.enabled.has(i.id) ? "" : " new"}" data-w="${i.id}">
          <b>${ICONS[i.id]} ${NAMES[i.id]}</b><small>${ed.enabled.has(i.id) ? `${i.w}×${i.h}` : "按完成後啟用"}</small>
          <button type="button" class="pe-x" data-remove aria-label="收進抽屜">✕</button>
          <span class="pe-grip" data-grip aria-label="調整大小"></span></div>`).join("");
    for (const it of ed.items) { const b = el.querySelector(`[data-w="${it.id}"]`); area(b, it); b.dataset.at = `${it.x + 1} / span ${it.w}|${it.y + 1} / span ${it.h}`; }
    const away = L.WIDGETS.filter(w => !ed.items.some(i => i.id === w));
    drawer.innerHTML = `<div class="pe-drawer-head">小工具</div><div class="pe-tiles">${
      away.map(w => `<div class="pe-tile" data-w="${w}"><span>${ICONS[w]}</span>${NAMES[w]}</div>`).join("")
      || '<p class="pe-empty">所有小工具都在畫面上</p>'}</div>`;
    render();  // real cards follow the edited layout underneath
  }

  // pixel -> grid cell, using the layer's real size (the stage is scaled to the screen)
  function cells() {
    const r = layer().getBoundingClientRect(), gap = parseFloat(getComputedStyle(grid).columnGap) * (r.width / layer().offsetWidth || 1);
    return { r, cw: (r.width + gap) / L.COLS, ch: (r.height + gap) / L.ROWS };
  }

  function track(e, move, up) {
    const mv = ev => move(ev), end = ev => {
      removeEventListener("pointermove", mv); removeEventListener("pointerup", end); removeEventListener("pointercancel", end);
      up(ev);
    };
    addEventListener("pointermove", mv); addEventListener("pointerup", end); addEventListener("pointercancel", end);
  }

  // move / resize / remove a card
  function boxDown(e) {
    const box = e.target.closest(".pe-box");
    if (!box) return;
    const id = box.dataset.w;
    if (e.target.closest("[data-remove]")) { ed.items = ed.items.filter(i => i.id !== id); draw(); return; }
    e.preventDefault();
    const { cw, ch } = cells(), item = ed.items.find(i => i.id === id), start = { ...item };
    const resize = !!e.target.closest("[data-grip]");
    let next = { ...start }, arranged = ed.items;
    box.classList.add("drag");
    track(e, ev => {
      const dx = Math.round((ev.clientX - e.clientX) / cw), dy = Math.round((ev.clientY - e.clientY) / ch);
      const [mw, mh] = L.minSize(id);
      next = resize ? { ...start, w: Math.max(mw, start.w + dx), h: Math.max(mh, start.h + dy) } : { ...start, x: start.x + dx, y: start.y + dy };
      // cards in the way step aside to the nearest free place (and come back if the drag moves on)
      arranged = L.makeRoom(ed.items.map(i => i.id === id ? start : i), next, start);
      area(box, { x: Math.max(0, Math.min(L.COLS - 1, next.x)), y: Math.max(0, Math.min(L.ROWS - 1, next.y)),
        w: Math.min(next.w, L.COLS), h: Math.min(next.h, L.ROWS) });
      for (const it of arranged || ed.items) if (it.id !== id) glide(layer().querySelector(`.pe-box[data-w="${it.id}"]`), it);
      // between two cells the box follows the pointer, so it feels like pushing through, not jumping
      const k = layer().offsetWidth / (layer().getBoundingClientRect().width || 1);
      box.style.translate = resize ? "" : `${((ev.clientX - e.clientX) - dx * cw) * k}px ${((ev.clientY - e.clientY) - dy * ch) * k}px`;
      box.classList.toggle("bad", !arranged);
      box.classList.toggle("min", resize && (start.w + dx < mw || start.h + dy < mh));
      box.querySelector("small").textContent = `${next.w}×${next.h}`;
    }, () => {
      if (arranged) ed.items = arranged;  // off the screen, or no room for the others: everything snaps back
      draw();
      const landed = layer().querySelector(`.pe-box[data-w="${id}"]`);   // the dropped card lands with a rebound
      landed?.animate([{ scale: 1.03 }, { scale: 1 }], { duration: 420, easing: getComputedStyle(document.documentElement).getPropertyValue("--duang").trim() || "ease-out" });
    });
  }

  // move a box to its cell with a springy slide (the box keeps its place in the DOM)
  function glide(el, r) {
    if (!el) return;
    const want = `${r.x + 1} / span ${r.w}|${r.y + 1} / span ${r.h}`;
    if (el.dataset.at === want) return;
    const before = el.getBoundingClientRect();
    el.dataset.at = want; area(el, r);
    const after = el.getBoundingClientRect();
    if (!before.width || !after.width) return;
    // it slides (and resizes) to its new place on a damped spring: one small overshoot, then rest
    const k = el.offsetWidth / (after.width || 1), mx = (before.left - after.left) * k, my = (before.top - after.top) * k;
    const spring = getComputedStyle(document.documentElement).getPropertyValue("--spring").trim() || "ease-out";
    el.animate([{ translate: `${mx}px ${my}px`, transform: `scale(${before.width / after.width}, ${before.height / after.height})`, transformOrigin: "0 0" },
      { translate: "0px 0px", transform: "none", transformOrigin: "0 0" }], { duration: 420, easing: spring });
    el.querySelector("small").textContent = `${r.w}×${r.h}`;
  }

  // drag a widget out of the drawer (or tap it to have it placed automatically)
  drawer.addEventListener("pointerdown", e => {
    const tile = e.target.closest(".pe-tile");
    if (!tile) return;
    e.preventDefault();
    const id = tile.dataset.w, ghost = tile.cloneNode(true);
    ghost.classList.add("pe-ghost");
    let dragging = false, spot = null, preview = null;
    track(e, ev => {
      if (!dragging && Math.hypot(ev.clientX - e.clientX, ev.clientY - e.clientY) < 8) return;
      if (!dragging) { dragging = true; document.body.appendChild(ghost); document.body.classList.remove("pe-open"); }
      Object.assign(ghost.style, { left: ev.clientX + "px", top: ev.clientY + "px" });
      const { r, cw, ch } = cells();
      const cx = Math.floor((ev.clientX - r.left) / cw), cy = Math.floor((ev.clientY - r.top) / ch);
      const inside = cx >= 0 && cy >= 0 && cx < L.COLS && cy < L.ROWS;
      const [mw, mh] = L.minSize(id);
      spot = inside ? L.spotAt(ed.items, cx, cy, [[3, 3], [3, 2], [2, 3], [2, 2], [2, 1], [1, 2], [1, 1]].filter(([w, h]) => w >= mw && h >= mh)) : null;
      if (!preview) { preview = document.createElement("div"); preview.className = "pe-box preview"; layer().appendChild(preview); }
      preview.hidden = !inside;
      if (inside) { area(preview, spot || { x: cx, y: cy, w: 1, h: 1 }); preview.classList.toggle("bad", !spot); }
    }, () => {
      ghost.remove(); preview?.remove();
      if (!dragging) {  // a tap: free spot, or half of the biggest card
        ed.items = L.place({ items: ed.items }, [...ed.items.map(i => i.id), id], false);
      } else if (spot) ed.items.push({ id, ...spot });
      else toast("這裡放不下，先把其他卡片縮小或移開");
      draw();
    });
  });

  async function save() {
    const cfg = ed.cfg, ids = ed.items.map(i => i.id);
    cfg.display ??= {};
    const layout = { items: ed.items.map(({ id, x, y, w, h }) => ({ id, x, y, w, h })),
      hidden: L.WIDGETS.filter(w => !ids.includes(w)) };
    if (ed.mode) cfg.display.modes = { ...cfg.display.modes, [ed.mode]: layout };  // your version of this mode
    else cfg.display.layout = layout;
    for (const id of ids) {
      const mods = cfg.modules.filter(m => m.type === id);
      if (mods.some(m => m.enabled !== false)) continue;
      let m = mods[0];
      if (!m) {
        m = { ...DEFAULTS[id] };
        while (cfg.modules.some(o => o.id === m.id)) m.id += "-2";
        cfg.modules.push(m);
      }
      m.enabled = true;
      // no API key yet: start with the free rule-based brain instead of an error bubble
      if (m.type === "companion" && (m.provider || "anthropic") === "anthropic" && !m.api_key) m.provider = "rule";
    }
    // an Agent put away stops talking (and spending API calls) instead of running unseen
    // (only for your own layout: a mode without the Agent must not switch it off everywhere)
    if (!ed.mode) for (const m of cfg.modules) if (m.type === "companion" && !ids.includes("companion")) m.enabled = false;
    try {
      const res = await (await fetch("/api/config", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(cfg) })).json();
      if (!res.ok) throw Error(res.error);
    } catch (err) { return toast("儲存失敗：" + (err.message || err)); }
    exit();
    poll();
  }

  pencil.addEventListener("click", enter);
  bar.addEventListener("click", e => {
    const act = e.target.closest("[data-pe]")?.dataset.pe;
    if (!act || !ed) return;
    if (act === "drawer") document.body.classList.toggle("pe-open");
    if (act === "cancel") exit();
    if (act === "save") save();
    if (act === "reset") {
      const base = ed.mode ? L.MODES[ed.mode].items : L.DEFAULT_ITEMS;
      ed.items = L.place({ items: base }, base.map(i => i.id), false); draw();
    }
  });
  addEventListener("keydown", e => { if (e.key === "Escape" && ed) exit(); });
})();
