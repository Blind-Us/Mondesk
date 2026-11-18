const SHAPE_NAMES = { round: "圓角", soft: "方角", cut: "切角" };
const CARD_NAMES = { bambu: "列印機", media: "正在播放", weather: "天氣", companion: "Agent", codex: "Codex", claude: "Claude" };
const PRESETS = DeskMonLayout.PALETTES;   // every colour and palette comes from the theme in layout.js
let cfg, saved;
const WIDGET = new URLSearchParams(location.search).get("w");
const PAGE_TITLES = { bambu: "列印機", media: "正在播放", tokens: "AI 用量", companion: "Agent", clock: "時鐘", weather: "天氣" };
(() => {
  const own = WIDGET && document.querySelector(`[data-widget="${CSS.escape(WIDGET)}"]`);
  for (const el of document.querySelectorAll("[data-widget]")) el.hidden = el !== own;
  for (const el of document.querySelectorAll("[data-global]")) el.hidden = !!own;
  document.body.classList.toggle("widget-page", !!own);
  document.getElementById("pageTitle").textContent = own ? PAGE_TITLES[WIDGET] + "設定" : "設定";
  document.title = own ? `${PAGE_TITLES[WIDGET]}設定 · Mondesk` : "Mondesk 設定";
})();
const $ = s => document.querySelector(s);
const mod = id => cfg.modules.find(m => m.id === id);
// the theme as it is stored: {background, shape, accent, cards}. Older configs (no accent) come out as
// "every card has its own colour", which is how they looked.
const theme = () => DeskMonLayout.storedTheme(cfg.theme);

// data-k paths: "<moduleId>.<field>", "display.<field>", "theme.<field>[.<index>]"
function get(path) {
  const [root, key, idx] = path.split(".");
  if (root === "display") return cfg.display?.[key] ?? ({ text_scale: 1, toasts: true, auto_mode: false }[key] ?? "");
  if (root === "theme") { const v = theme()[key]; return idx != null ? v[idx] : v; }
  const m = mod(root);
  if (!m) return "";
  // "<module>.<list>.<item>" = is <item> in that list
  if (idx != null) return (m[key] ?? LIST_DEFAULTS[key] ?? []).includes(idx);
  return key === "enabled" ? m.enabled !== false : m[key] ?? "";
}
const LIST_DEFAULTS = { triggers: ["print_finished", "print_failed", "quota_high", "song_change", "long_work", "timer_done", "rain_soon"] };
const TRIGGERS_V = 2, ADDED_TRIGGERS = { 2: ["timer_done", "rain_soon"] };  // same table as modules/companion.py
const WEATHER_DEFAULT = { id: "weather", type: "weather", title: "天氣", enabled: false, place: "", latitude: null, longitude: null };
const COMPANION_DEFAULT = { id: "companion", type: "companion", title: "Companion", enabled: false,
  provider: "rule", model: "claude-opus-5-5", small_model: "", effort: "low", api_key: "", fallbacks: true,
  ollama_url: "http://127.0.0.1:11434", ollama_model: "qwen3:8b", triggers: [...LIST_DEFAULTS.triggers],
  quota_threshold: 80, work_minutes: 120, break_minutes: 10, song_chance: 0.4, max_calls_per_hour: 20, character: "emoji" };

const CLOCK_DEFAULT = { id: "clock", type: "clock", title: "時鐘", enabled: false, style: "digital",
  hour12: false, seconds: true, date: true, color: "", timer: false };
const CLOCK_STYLES = [["digital", "數字", "12:34"], ["analog", "指針", "🕒"], ["flip", "翻頁", "12▕34"],
  ["ring", "圓環", "◔"], ["words", "文字", "三點半"]];
function drawClockStyles() {
  const cur = mod("clock")?.style || "digital";
  $("#clockStyles").innerHTML = CLOCK_STYLES.map(([k, name, look]) =>
    `<button type="button" class="char ${k === cur ? "on" : ""}" data-clock-style="${k}"><div class="face ck-look">${look}</div>${name}</button>`).join("");
}
document.addEventListener("click", e => {
  const b = e.target.closest("[data-clock-style]");
  if (!b || !mod("clock")) return;
  mod("clock").style = b.dataset.clockStyle;
  drawClockStyles(); dirty();
});

function set(path, el) {
  const [root, key, idx] = path.split(".");
  const v = el.type === "checkbox" ? el.checked : el.value;
  if (root === "display") {
    cfg.display ??= {};
    if (key === "text_scale") cfg.display.text_scale = +v;
    else if (key === "mode") cfg.display.mode = ["focus", "print", "rest"].includes(v) ? v : "";
    else if (key === "auto_mode" || key === "toasts") cfg.display[key] = !!v;
  } else if (root === "theme") {
    cfg.theme = theme();
    if (idx != null) { cfg.theme[key] = [...cfg.theme[key]]; cfg.theme[key][idx] = v; }
    else cfg.theme[key] = v;
  } else {
    const m = mod(root);
    if (!m) return;
    if (idx != null) {
      const list = new Set(m[key] ?? LIST_DEFAULTS[key] ?? []);
      v ? list.add(idx) : list.delete(idx);
      m[key] = [...list];
    } else m[key] = el.type === "number" || el.type === "range" ? (v === "" ? null : +v) : v;
  }
  paint();
  dirty();
}

// printers: one block per Bambu module, the first is "printer"; more can be added and removed
const PRINTER_FIELDS = `
  <div class="row"><label>名稱<input type="text" data-k="ID.title" placeholder="Bambu Lab"></label>
    <label>型號<input type="text" data-k="ID.model" placeholder="X2D"></label></div>
  <div class="row three"><label>IP 位址<input type="text" data-k="ID.ip" placeholder="192.168.1.100" inputmode="decimal"></label>
    <label>序號<input type="text" data-k="ID.serial" placeholder="印表機上的序號"></label>
    <label>LAN 存取碼<span class="pw"><input type="password" data-k="ID.access_code" placeholder="8 碼" autocomplete="off"><button type="button" data-reveal>顯示</button></span></label></div>`;
function drawPrinters() {
  const list = cfg.modules.filter(m => m.type === "bambu");
  $("#printers").innerHTML = list.map((m, i) => `<div class="printer-block" data-printer-id="${esc(m.id)}">
    ${list.length > 1 ? `<div class="printer-block-head"><b>第 ${i + 1} 台</b>${i ? `<button type="button" data-remove-printer="${esc(m.id)}">移除</button>` : ""}</div>` : ""}
    ${PRINTER_FIELDS.replaceAll("ID.", m.id + ".")}</div>`).join("") || `<p class="hint">還沒有列印機，按下面的按鈕新增。</p>`;
}
document.addEventListener("click", e => {
  if (e.target.closest("#addPrinter")) {
    const ids = new Set(cfg.modules.map(m => m.id));
    let n = cfg.modules.filter(m => m.type === "bambu").length + 1, id = n === 1 ? "printer" : `printer${n}`;
    while (ids.has(id)) id = `printer${++n}`;
    cfg.modules.push({ id, type: "bambu", title: n === 1 ? "Bambu Lab" : `列印機 ${n}`, ip: "", serial: "", access_code: "", model: "" });
    fill(); dirty();
    document.querySelector(`[data-printer-id="${id}"] input`)?.focus();
  }
  const rm = e.target.closest("[data-remove-printer]");
  if (rm) {
    const m = mod(rm.dataset.removePrinter);
    if (m && confirm(`移除「${m.title || m.id}」？按「套用」後才會生效。`)) {
      cfg.modules = cfg.modules.filter(x => x !== m); fill(); dirty();
    }
  }
});

function fill() {
  drawPrinters();
  document.querySelectorAll("[data-k]").forEach(el => {
    const v = get(el.dataset.k);
    if (el.type === "checkbox") el.checked = !!v; else el.value = v;
  });
  const d = DeskMonLayout.settings(cfg.display);
  const chosen = d.fit === "auto" ? "auto" : `${d.width},${d.height}`;
  $("#layoutSize").value = [...$("#layoutSize").options].some(o => o.value === chosen) ? chosen : "960,640";
  drawCardColors();
  drawClockColors();
  paint();
}

// mode colours and the night background (drawn once per change so a colour picker stays open while dragging)
function drawThemeExtras(t) {
  const key = JSON.stringify([t.modes, t.night, t.accent]);
  if (key === drawThemeExtras.last) return;
  drawThemeExtras.last = key;
  const M = DeskMonLayout.MODES;
  $("#modeColors").innerHTML = Object.keys(M).map(k => {
    const own = !!t.modes?.[k];
    return `<div class="card-color"><span>${M[k].label}</span><input type="color" data-mode-color="${k}" value="${t.modes?.[k] || t.accent}" aria-label="${M[k].label}主題色" ${own ? "" : "disabled"}>
      <label class="toggle small"><input type="checkbox" data-mode-own="${k}" ${own ? "checked" : ""}><span>自訂</span></label></div>`;
  }).join("");
  const n = t.night || { on: false, from: 22, to: 7, background: "oled" };
  $("#nightBg").innerHTML = Object.entries(DeskMonLayout.BACKGROUNDS).map(([k, v]) => `<option value="${k}">${v.label}</option>`).join("");
  document.querySelectorAll("[data-night]").forEach(el => { el.type === "checkbox" ? el.checked = !!n.on : el.value = n[el.dataset.night]; });
  $("#nightRow").hidden = !n.on;
}
document.addEventListener("input", e => {
  const el = e.target, t = theme();
  if (el.id === "bgColor") cfg.theme = { ...t, background: el.value };
  else if (el.dataset.modeOwn) { const m = { ...t.modes }; el.checked ? m[el.dataset.modeOwn] = t.accent : delete m[el.dataset.modeOwn]; cfg.theme = { ...t, modes: m }; }
  else if (el.dataset.modeColor) cfg.theme = { ...t, modes: { ...t.modes, [el.dataset.modeColor]: el.value } };
  else if (el.dataset.night) {
    const n = { on: false, from: 22, to: 7, background: "oled", ...t.night }, k = el.dataset.night;
    n[k] = k === "on" ? el.checked : k === "background" ? el.value : el.value === "" ? n[k] : +el.value;
    cfg.theme = { ...t, night: n };
  } else return;
  if (el.dataset.modeColor) drawThemeExtras.last = JSON.stringify([cfg.theme.modes, cfg.theme.night, cfg.theme.accent]);  // keep the open picker
  paint(); dirty();
});

// each card's own settings carry its colour: follow the theme colour, or its own colour(s)
function drawCardColors() {
  const t = theme(), colors = DeskMonLayout.resolveTheme(t).colors;
  const row = k => {
    const n = DeskMonLayout.CARD_COLORS[k], own = k in t.cards, list = n === 1 ? [colors[k]] : colors[k];
    const pick = (c, i) => `<input type="color" data-card="${k}" data-i="${i}" value="${c}" aria-label="${CARD_NAMES[k]}${n > 1 ? (i ? "右端" : "左端") : ""}顏色" ${own ? "" : "disabled"}>`;
    // two colours = one gradient bar with a picker at each end
    const body = n === 1 ? pick(list[0], 0)
      : `<div class="grad-bar ${own ? "" : "off"}" data-grad="${k}" style="background:linear-gradient(90deg, ${list[0]}, ${list[1]})">${pick(list[0], 0)}${pick(list[1], 1)}</div>`;
    return `<div class="card-color"><span>${n > 1 ? CARD_NAMES[k] + " " : ""}顏色</span>${body}
      <label class="toggle small"><input type="checkbox" data-card-own="${k}" ${own ? "checked" : ""}><span>自訂</span></label></div>`;
  };
  document.querySelectorAll("[data-cards]").forEach(el => {
    el.innerHTML = el.dataset.cards.split(",").map(row).join("");
  });
  const own = Object.keys(t.cards).map(k => CARD_NAMES[k]);
  $("#cardSummary").textContent = (own.length ? `自訂顏色：${own.join("、")}。` : "全部跟隨主題色。") + "在各卡片的設定裡調整。";
}
document.addEventListener("input", e => {
  const el = e.target, t = theme();
  if (el.dataset.cardOwn) {
    const k = el.dataset.cardOwn;
    if (el.checked) t.cards[k] = DeskMonLayout.resolveTheme(t).colors[k]; else delete t.cards[k];
    cfg.theme = t; drawCardColors(); paint(); dirty();
  } else if (el.dataset.card) {
    const k = el.dataset.card;
    if (Array.isArray(t.cards[k])) t.cards[k][+el.dataset.i] = el.value; else t.cards[k] = el.value;
    const bar = el.closest("[data-grad]");
    if (bar) bar.style.background = `linear-gradient(90deg, ${t.cards[k][0]}, ${t.cards[k][1]})`;
    cfg.theme = t; paint(); dirty();
  } else if (el.dataset.k === "theme.accent") drawCardColors();  // cards that follow show the new colour
});

function paint() {
  const t = theme();
  const B = DeskMonLayout.BACKGROUNDS, surf = DeskMonLayout.surface(t.background);
  $("#bgs").innerHTML = Object.entries(B).map(([k, v]) =>
    `<div class="swatch ${t.background === k ? "on" : ""}" data-bg="${k}" style="--b:${v.bg};--k:${v.card};--t:${DeskMonLayout.surface(k).soft}"><div></div>${v.label}</div>`).join("");
  $("#bgColor").value = surf.bg;
  $("#bgColor").closest("label").classList.toggle("on", !B[t.background]);
  const img = t.image;   // background picture controls
  $("#wallRemove").hidden = $("#wallOpts").hidden = !img;
  if (img) {
    for (const el of document.querySelectorAll("[data-wall]")) if (document.activeElement !== el) el.value = img[el.dataset.wall];
    $("#wallDimVal").textContent = img.dim + "%"; $("#wallBlurVal").textContent = img.blur + "px";
  }
  $("#styles").innerHTML = Object.entries(DeskMonLayout.STYLES).map(([k, name]) =>
    `<button type="button" data-style="${k}" aria-pressed="${t.style === k}">${name}</button>`).join("");
  $("#shapes").innerHTML = Object.entries(SHAPE_NAMES).map(([k, name]) =>
    `<button type="button" data-shape="${k}" aria-pressed="${t.shape === k}"><i class="shape-${k}"></i>${name}</button>`).join("");
  const seen = DeskMonLayout.resolveTheme(t), colors = seen.colors;
  const r = document.documentElement.style;
  // the settings page wears the theme too
  for (const [k, v] of Object.entries({ bg: surf.bg, card: surf.card, line: surf.line, text: surf.text, dim: surf.soft, faint: surf.dim,
    on: surf.on, ok: surf.ok, err: surf.err, warn: surf.warn, accent: seen.accent })) r.setProperty(`--${k}`, v);
  r.setProperty("--printer", colors.bambu);
  r.setProperty("--music", colors.media);
  r.setProperty("--codex", colors.codex[0]);
  drawThemeExtras(t);
  const scale = Math.round((cfg.display?.text_scale ?? 1) * 100) + "%";
  const d = DeskMonLayout.settings(cfg.display);
  $("#scaleVal").textContent = scale;
  const cp = mod("companion");
  if (cp) {
    document.querySelectorAll("[data-cp-for]").forEach(el => { el.hidden = el.dataset.cpFor !== (cp.provider || "anthropic"); });
    $("#songChanceVal").textContent = Math.round((cp.song_chance ?? 0.4) * 100) + "%";
  }
  scalePreview();
}

function pushPreview() {
  // preview frame mimics the panel: always apply the chosen ratio there
  const display = { ...cfg.display };
  $("#pv").contentWindow?.postMessage({ type: "deskmon-preview", theme: theme(), display }, location.origin);
}

function dirty() {
  pushPreview();
  const st = $("#status");
  st.className = "";
  st.textContent = JSON.stringify(cfg) !== saved ? "有未儲存的變更" : "尚未修改";
}

function scalePreview() {
  const d = DeskMonLayout.settings(cfg?.display);
  const f = $("#frame"), pa = d.fit === "auto" ? 1.5 : d.width / d.height;
  f.style.aspectRatio = pa;
  const iw = Math.round(640 * pa), pv = $("#pv");
  pv.width = iw;
  pv.height = 640;
  pv.style.transform = `scale(${f.clientWidth / iw}, ${f.clientHeight / 640})`;
}

document.addEventListener("input", e => { if (e.target.dataset.k) set(e.target.dataset.k, e.target); });
document.addEventListener("click", e => {
  const sw = e.target.closest("[data-bg]");
  if (sw) { cfg.theme = { ...theme(), background: sw.dataset.bg }; paint(); dirty(); }
  const pr = e.target.closest("[data-preset]");
  if (pr) { cfg.theme = { ...theme(), cards: pr.dataset.preset ? structuredClone(PRESETS[pr.dataset.preset]) : {} }; fill(); dirty(); }
  const st = e.target.closest("#styles [data-style]");
  if (st) { cfg.theme = { ...theme(), style: st.dataset.style }; paint(); dirty(); }
  const sh = e.target.closest("[data-shape]");
  if (sh) { cfg.theme = { ...theme(), shape: sh.dataset.shape }; paint(); dirty(); }
  const ac = e.target.closest("[data-accent]");
  if (ac) { cfg.theme = { ...theme(), accent: ac.dataset.accent }; fill(); dirty(); }
  const rv = e.target.closest("[data-reveal]");
  if (rv) {
    const i = rv.previousElementSibling;
    i.type = i.type === "password" ? "text" : "password";
    rv.textContent = i.type === "password" ? "顯示" : "隱藏";
  }
});

$("#presets").innerHTML = `<button type="button" data-preset="">全部跟隨主題色</button>` + Object.entries(PRESETS).map(([k, p]) =>
  `<button type="button" data-preset="${k}"><i style="background:linear-gradient(135deg, ${p.codex[0]}, ${p.claude[0]})"></i>${k}</button>`).join("");
$("#accents").innerHTML = Object.entries(DeskMonLayout.ACCENTS).map(([c, name]) => `<button type="button" data-accent="${c}" aria-label="主題色：${name}" title="${name}"><i style="background:${c}"></i></button>`).join("");
function drawClockColors() {
  const cur = mod("clock")?.color || "", known = DeskMonLayout.ACCENTS;
  $("#clockColor").innerHTML = `<option value="">白色</option>` + Object.entries(known).map(([c, name]) => `<option value="${c}">${name}</option>`).join("")
    + (cur && !known[cur] ? `<option value="${cur}">自訂（${cur}）</option>` : "");
  $("#clockColor").value = cur;
}

$("#save").onclick = async () => {
  const st = $("#status"), button = $("#save");
  st.hidden = true;
  button.disabled = true;
  button.textContent = "套用中…";
  try {
    const response = await fetch("/api/config", {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(cfg)});
    const result = await response.json();
    if (!response.ok || !result.ok) throw new Error(result.error || "請再試一次");
    location.assign("/");
  } catch (err) {
    st.hidden = false;
    st.className = "err";
    st.textContent = "套用失敗：" + err.message;
    button.disabled = false;
    button.textContent = "套用";
  }
};

addEventListener("resize", () => cfg && paint());

const ratio = (w, h) => {
  const g = (a, b) => b ? g(b, a % b) : a, d = g(w, h);
  const r = `${w / d}:${h / d}`;
  return { "8:5": "16:10", "683:384": "16:9", "85:48": "16:9", "4:3": "4:3", "16:9": "16:9", "3:2": "3:2", "5:4": "5:4" }[r] || (w / h).toFixed(2);
};

let displays = [];

async function loadDisplays() {
  const box = $("#displays");
  try {
    const found = await (await fetch("/api/displays", { cache: "no-store" })).json();
    displays = DeskMonLayout.panelDisplays(found);
    if (!displays.length) { box.textContent = "未偵測到小螢幕"; return; }
    box.innerHTML = displays.map(d => d.error ? `<div class="disp">${d.error}</div>` : `
      <div class="disp">
        <div class="disp-head"><b>小螢幕 · ${d.name}</b>${d.primary ? "<em>主螢幕</em>" : ""}
          <span>目前 ${d.current ? `${d.current.w}×${d.current.h} · ${ratio(d.current.w, d.current.h)} · ${d.current.hz}Hz` : "—"}</span></div>
        <div class="modes">${d.modes.map(m => {
          const on = d.current && m.w === d.current.w && m.h === d.current.h;
          return `<button type="button" class="${on ? "on" : ""}" data-disp="${d.name}" data-w="${m.w}" data-h="${m.h}">${m.w}×${m.h}<i>${ratio(m.w, m.h)}</i></button>`;
        }).join("")}</div>
      </div>`).join("");
  } catch { box.textContent = "讀取失敗"; }
}

const modeApi = body => fetch("/api/displays", { method: "POST", headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body) }).then(r => r.json()).catch(() => ({ok:false, message:"無法連線到服務，請確認 Mondesk 正在執行。"}));

function modal(title, text, yes, no) {
  $("#mTitle").textContent = title; $("#mText").textContent = text;
  $("#mYes").textContent = yes; $("#mNo").textContent = no;
  $("#modal").hidden = false;
  return new Promise(res => { $("#mYes").onclick = () => res(true); $("#mNo").onclick = () => res(false); });
}

async function pickMode(name, w, h) {
  const disp = displays.find(d => d.name === name);
  if (!disp || disp.primary) return;
  const label = `${w}×${h}（${ratio(w, h)}）`;
  if (!await modal(`把 ${name} 改成 ${label}？`, `${disp?.primary ? "這是主螢幕。" : ""}套用後如果畫面不對，15 秒後會自動還原。`, "套用", "取消")) {
    $("#modal").hidden = true; return;
  }
  const test = await modeApi({ name, w, h, step: "test" });
  if (!test.ok) { await modal("無法套用", test.message || test.error, "好", "關閉"); $("#modal").hidden = true; return; }
  const tried = await modeApi({ name, w, h, step: "try" });
  if (!tried.ok) { await modal("無法套用", tried.message || tried.error, "好", "關閉"); $("#modal").hidden = true; return; }
  let left = 15;
  const tick = setInterval(() => { left--; $("#mText").textContent = `要保留這個解析度嗎？${left} 秒後自動還原。`; if (left <= 0) $("#mNo").click(); }, 1000);
  const keep = await modal(`已切換到 ${label}`, `要保留這個解析度嗎？${left} 秒後自動還原。`, "保留", "還原");
  clearInterval(tick);
  const result = await modeApi({ name, w, h, step: keep ? "keep" : "revert", change_id: tried.change_id });
  if (!result.ok) { await modal("解析度未保留", result.message || result.error || "請重新試用", "好", "關閉"); }

  $("#modal").hidden = true;
  setTimeout(loadDisplays, 800);
}

document.addEventListener("click", e => {
  const b = e.target.closest("[data-disp]");
  if (b && !b.classList.contains("on")) pickMode(b.dataset.disp, +b.dataset.w, +b.dataset.h);
});

(async () => {
  loadDisplays();
  cfg = await (await fetch("/api/config", { cache: "no-store" })).json();
  // older configs have no companion entry yet: show its (disabled) defaults
  if (!cfg.modules.some(m => m.type === "companion")) cfg.modules.push(structuredClone(COMPANION_DEFAULT));
  // triggers added since this config was written start switched on (once), like the server treats them
  for (const m of cfg.modules.filter(m => m.type === "companion")) {
    for (const [v, names] of Object.entries(ADDED_TRIGGERS))
      if ((m.triggers_v || 1) < +v && Array.isArray(m.triggers)) m.triggers = [...new Set([...m.triggers, ...names])];
    m.triggers_v = TRIGGERS_V;
  }
  if (WIDGET === "weather" && !cfg.modules.some(m => m.id === "weather")) cfg.modules.push(structuredClone(WEATHER_DEFAULT));
  const clock = cfg.modules.find(m => m.id === "clock");
  if (clock) for (const [k, v] of Object.entries(CLOCK_DEFAULT)) if (k !== "enabled") clock[k] ??= v;  // a missing "enabled" means on
  else if (WIDGET === "clock") cfg.modules.push(structuredClone(CLOCK_DEFAULT));
  const normalized = DeskMonLayout.settings(cfg.display);
  cfg.display = {...cfg.display, width:normalized.width, height:normalized.height, fit:normalized.fit, text_scale:normalized.textScale};
  delete cfg.display.panel_aspect;
  delete cfg.display.signal_aspect;
  saved = JSON.stringify(cfg);
  fill();
  drawClockStyles();
  drawWeatherPlace();
  $("#pv").addEventListener("load", () => setTimeout(pushPreview, 300));
})();

$("#layoutSize").onchange = e => {
  cfg.display ??= {};
  if (e.target.value === "auto") cfg.display.fit = "auto";
  else { const [w,h] = e.target.value.split(",").map(Number); Object.assign(cfg.display, {width:w,height:h,fit:"contain"}); }
  delete cfg.display.panel_aspect; delete cfg.display.signal_aspect;
  paint(); dirty();
};

// Companion test buttons: fire one event with made-up data (needs the saved, running module)
document.addEventListener("click", async e => {
  const b = e.target.closest("[data-cp-test]");
  if (!b) return;
  const st = $("#cpTestStatus");
  if (JSON.stringify(cfg) !== saved) { st.textContent = "請先按「套用」儲存設定，再測試。"; return; }
  if (mod("companion")?.enabled === false) { st.textContent = "先把 Agent 放到畫面上。"; return; }
  const event = b.dataset.cpTest;
  st.textContent = `已送出「${b.textContent}」，看右邊預覽…`;
  try {
    const r = await fetch("/api/action", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ module: "companion", action: "trigger", event, simulate: event !== "tap" }) });
    const result = await r.json();
    if (!r.ok || !result.ok) throw Error(result.error || "沒有回應");
  } catch (err) { st.textContent = "測試失敗：" + err.message.replace(/^KeyError: .*/, "Agent 不在畫面上"); }
});



// ---------- character packs ----------
let charList = [];
async function loadCharacters() {
  const box = $("#characters");
  try {
    charList = (await (await fetch("/api/companion/characters", { cache: "no-store" })).json()).characters;
  } catch { box.textContent = "讀取角色失敗"; return; }
  drawCharacters();
}
function drawCharacters() {
  const cur = mod("companion")?.character || "emoji";
  const face = c => {
    const f = c.faces?.happy || c.faces?.neutral, name = c.faces?.happy ? "happy" : "neutral";
    if (!f) return "";
    if (f.sprite) {  // sprite sheet (Codex pet): the first cell of that row, sized like a face
      const s = f.sprite, url = `/api/companion/character/${encodeURIComponent(c.id)}/sheet?v=${s.v}`;
      return `<span class="sprite" data-sheet="${esc(url)}" data-row="${s.row}" data-cols="${s.columns}" data-cell="${s.cell.join("x")}" style="background-image:url(&quot;${esc(url)}&quot;);aspect-ratio:${s.cell[0]}/${s.cell[1]}"></span>`;
    }
    return f.text != null ? esc(f.text) : `<img src="/api/companion/character/${encodeURIComponent(c.id)}/${name}?v=${f.v}" alt="">`;
  };
  $("#characters").innerHTML = charList.map(c => c.error
    ? `<div class="char broken" title="${esc(c.error)}"><div class="face">⚠️</div>${esc(c.name)}<small>${esc(c.error)}</small></div>`
    : `<button type="button" class="char ${c.id === cur ? "on" : ""}" data-char="${esc(c.id)}"><div class="face">${face(c)}</div>${esc(c.name)}<small>${c.builtin ? "內建" : c.source === "codex" ? "Codex 寵物" : esc(c.author || "匯入")}</small></button>`).join("");
  // size each sprite preview once its sheet has loaded (rows come from the image height)
  document.querySelectorAll("#characters .sprite").forEach(el => {
    const img = new Image(), [cw, ch] = el.dataset.cell.split("x").map(Number), cols = +el.dataset.cols;
    img.onload = () => {
      const rows = Math.max(1, Math.round(img.naturalHeight / (img.naturalWidth / cols * ch / cw))), row = Math.min(+el.dataset.row, rows - 1);
      el.style.backgroundSize = `${cols * 100}% ${rows * 100}%`;
      el.style.backgroundPosition = `0% ${rows > 1 ? row / (rows - 1) * 100 : 0}%`;
    };
    img.src = el.dataset.sheet;
  });
  const sel = charList.find(c => c.id === cur);
  $("#charDelete").disabled = !sel || sel.builtin || sel.source === "codex";
}
const esc = v => String(v ?? "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
document.addEventListener("click", e => {
  const b = e.target.closest("[data-char]");
  if (!b) return;
  mod("companion").character = b.dataset.char;
  drawCharacters(); dirty();
});
$("#charImport").onclick = () => $("#charFile").click();
$("#charFile").onchange = async () => {
  const file = $("#charFile").files[0], msg = $("#charMsg");
  if (!file) return;
  msg.textContent = "匯入中…";
  try {
    const r = await fetch("/api/companion/import", { method: "POST", headers: { "Content-Type": "application/octet-stream" }, body: file });
    const res = await r.json();
    if (!r.ok || !res.ok) throw Error(res.error || "匯入失敗");
    mod("companion").character = res.character.id;
    msg.textContent = `已匯入「${res.character.name}」，按「套用」使用這個角色。`;
    await loadCharacters(); dirty();
  } catch (err) { msg.textContent = "匯入失敗：" + err.message; }
  $("#charFile").value = "";
};
$("#charExport").onclick = () => { location.href = `/api/companion/export/${encodeURIComponent(mod("companion")?.character || "emoji")}`; };
$("#charDelete").onclick = async () => {
  const id = mod("companion")?.character, c = charList.find(x => x.id === id);
  if (!c || c.builtin) return;
  const yes = await modal(`刪除「${c.name}」？`, "會刪除這個匯入的角色包，無法復原。", "刪除", "取消");
  $("#modal").hidden = true;
  if (!yes) return;
  const r = await (await fetch("/api/companion/delete", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ id }) })).json();
  $("#charMsg").textContent = r.ok ? `已刪除「${c.name}」。` : "刪除失敗：" + r.error;
  mod("companion").character = "emoji";
  await loadCharacters(); dirty();
};
loadCharacters();


// ---------- weather: find a place by name ----------
function drawWeatherPlace() {
  const w = mod("weather"), el = $("#wxNow");
  if (!el) return;
  el.textContent = w && w.latitude != null && w.longitude != null
    ? `目前地點：${w.place || "（未命名）"}（${(+w.latitude).toFixed(2)}, ${(+w.longitude).toFixed(2)}）` : "還沒選地點：輸入城市名稱後按「搜尋」。";
}
async function searchPlace() {
  const q = $("#wxQuery").value.trim(), box = $("#wxResults"), msg = $("#wxNow");
  if (!q) return;
  box.innerHTML = ""; msg.textContent = "搜尋中…";
  try {
    const r = await (await fetch("/api/weather/search?q=" + encodeURIComponent(q), { cache: "no-store" })).json();
    if (!r.ok) throw Error(r.error);
    if (!r.places.length) { msg.textContent = "找不到這個地名。試試加上「市／區」或改用英文，例如「台北市」「Taipei」。"; return; }
    box.innerHTML = r.places.map((p, i) => `<button type="button" data-place="${i}">${esc(p.name)}<small style="color:var(--dim)">${esc(p.region)}</small></button>`).join("");
    box._places = r.places;
    msg.textContent = "選一個地點：";
  } catch (err) { msg.textContent = "搜尋失敗：" + (err.message || "請確認網路"); }
}
$("#wxSearch").onclick = searchPlace;
$("#wxQuery").addEventListener("keydown", e => { if (e.key === "Enter") { e.preventDefault(); searchPlace(); } });
document.addEventListener("click", e => {
  const b = e.target.closest("[data-place]");
  if (!b) return;
  const p = $("#wxResults")._places[+b.dataset.place], w = mod("weather");
  if (!w) return;
  Object.assign(w, { place: p.name, latitude: p.latitude, longitude: p.longitude });
  $("#wxResults").innerHTML = "";
  drawWeatherPlace(); dirty();
});

// ---------- layout templates and layout packs (layouts, modes, colours: never modules) ----------
function applyPack(pack, onlyLayout) {
  const got = DeskMonLayout.importPack(pack);
  cfg.display ??= {};
  if (got.display.layout) cfg.display.layout = got.display.layout;
  if (!onlyLayout) {
    if (got.display.modes) cfg.display.modes = { ...cfg.display.modes, ...got.display.modes };
    if (got.display.text_scale) cfg.display.text_scale = got.display.text_scale;
    if (got.theme) {  // a pack changes only what it carries; packs from before the theme colour bring card colours
      const now = theme(), g = got.theme, inc = DeskMonLayout.resolveTheme(g);
      const colours = g.accent || g.cards || ["printer", "music", "codex", "claude"].some(k => k in g);
      cfg.theme = { ...now, background: g.background ? inc.background : now.background, shape: g.shape ? inc.shape : now.shape,
        accent: g.accent || now.accent, cards: colours ? inc.cards : now.cards };
    }
  }
  if (got.display.layout) cfg.display.mode = "";  // show the layout that was just applied
  fill(); dirty();
  return got;
}
document.addEventListener("click", async e => {
  const b = e.target.closest("[data-pack]");
  if (!b) return;
  const msg = $("#packMsg");
  try {
    const got = applyPack(await (await fetch(`layouts/${b.dataset.pack}.json`, { cache: "no-store" })).json(), true);
    msg.textContent = `已套用「${got.name}」版面，看右邊預覽；按「套用」儲存。沒啟用的小工具不會顯示，可用面板的鉛筆拖出來。`;
  } catch (err) { msg.textContent = "套用失敗：" + err.message; }
});
$("#packImport").onclick = () => $("#packFile").click();
$("#packFile").onchange = async () => {
  const file = $("#packFile").files[0], msg = $("#packMsg");
  if (!file) return;
  try {
    if (file.size > 200000) throw Error("檔案太大，不像版面包");
    const got = applyPack(JSON.parse(await file.text()));
    msg.textContent = `已匯入「${got.name}」，按「套用」儲存。`;
  } catch (err) { msg.textContent = "匯入失敗：" + (err instanceof SyntaxError ? "不是有效的 JSON" : err.message); }
  $("#packFile").value = "";
};
$("#packExport").onclick = () => {
  const pack = DeskMonLayout.exportPack({ display: cfg.display, theme: cfg.theme && theme() });
  const a = Object.assign(document.createElement("a"), {
    href: URL.createObjectURL(new Blob([JSON.stringify(pack, null, 2)], { type: "application/json" })), download: "deskmon-layout.json" });
  a.click(); setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  $("#packMsg").textContent = "已匯出 deskmon-layout.json（只有版面、模式與顏色）。";
};

// ---------- diagnostics + event history ----------
const ago = s => s == null ? "—" : s < 2 ? "剛剛" : s < 90 ? `${Math.round(s)} 秒前` : s < 5400 ? `${Math.round(s / 60)} 分鐘前` : `${Math.round(s / 3600)} 小時前`;
const drow = (label, value, tone = "") => `<div class="diag-row ${tone}"><span>${esc(label)}</span><b>${value}</b></div>`;
const STATUS = { ok: ["正常", "good"], idle: ["待機", ""], offline: ["未連線", "bad"], error: ["錯誤", "bad"], starting: ["啟動中", "warn"] };
const OUTCOME = { detected: "只記錄", queued: "等角色說", spoken: "角色說了", off: "此提醒已關閉", cooldown: "冷卻中，沒說", skipped: "這次略過", stale: "太久沒說，丟棄" };
function mediaDiag(m) {
  if (!m) return drow("正在播放", "沒有啟用這個小工具");
  const rows = [];
  rows.push(drow("目前來源", m.title ? `${esc(m.source || "系統播放資訊")} · ${m.playing ? "播放中" : "已暫停"}` : esc(m.message || "目前沒有播放")));
  rows.push(drow("瀏覽器擴充功能", m.bridge ? "已連線" : "沒有收到資料（只有系統播放資訊）", m.bridge ? "good" : "warn"));
  if (m.bridge || m.ext) rows.push(drow("擴充功能版本", m.ext_outdated
    ? `${esc(m.ext || "未知")}（最新 ${esc(m.ext_expected)}）：到 chrome://extensions 按「重新載入」，再重新整理分頁`
    : `${esc(m.ext || "—")}（最新）`, m.ext_outdated ? "bad" : "good"));
  if (m.os_reader === "powershell") rows.push(drow("系統播放資訊", "用 PowerShell 讀取（較慢）：winrt 套件無法載入，常見原因是 Windows 的應用程式控制原則封鎖。不影響擴充功能的歌詞與影片。", "warn"));
  if ("last_report" in m) rows.push(drow("最後回報", ago(m.last_report), m.last_report != null && m.last_report > 15 && m.playing ? "warn" : ""));
  if ("paired" in m) rows.push(drow("配對金鑰", m.paired ? "已產生" : "還沒有：執行 python -m modules.apple_bridge", m.paired ? "" : "warn"));
  if (m.title) {
    const lyric = m.video ? "（影片）" : m.lyrics === "ok" ? (m.lines ? `同步歌詞 ${m.lines} 句（可點擊跳轉）` : m.plain ? `靜態歌詞 ${m.plain} 句（不會跟唱）` : "有歌詞")
      : m.lyrics === "native_missing" ? "還沒讀到：在 Apple Music 開啟歌詞面板，或換一首歌" : "這個來源沒有歌詞";
    rows.push(drow("歌詞", lyric, m.lyrics === "native_missing" ? "warn" : ""));
    if (m.video) rows.push(drow("影片顯示方式", /^(youtube|bilibili)/i.test(m.source || "") ? "面板自己播同一支影片並同步進度（不擷取畫面）"
      : `擷取分頁畫面${m.mirror ? "：" + ({ hidden: "分頁被蓋住，畫面暫停", blocked: "網站不允許擷取", waiting: "等待畫面" }[m.mirror] || m.mirror) : ""}`, m.mirror ? "warn" : ""));
    if (m.watching) rows.push(drow("畫面擷取", "面板正在觀看，擴充功能傳送畫面中"));
    if (m.timeline_estimated) rows.push(drow("播放進度", "估算值（播放器回報的是整個清單的時間）", "warn"));
  }
  if (m.native) rows.push(drow("頁面訊息", esc(m.native)));
  return rows.join("");
}
function drawDiagnostics(d) {
  const media = mediaDiag(d.media);
  document.querySelectorAll('[data-diag="media"]').forEach(el => { el.innerHTML = media; });
  const guide = $("#extGuide");  // the install steps open by themselves until the extension has reported once
  if (guide && !guide.dataset.touched) guide.open = !!d.media && !d.media.bridge && !d.media.ext;
  const all = document.querySelector('[data-diag="all"]');
  if (all && !all.closest("[hidden]")) {
    const mods = d.modules.map(m => { const [text, tone] = STATUS[m.status] || [m.status, ""];
      return drow(`${m.title}`, `${text} · ${ago(m.age)}更新${m.error ? ` · ${esc(m.error)}` : m.message && m.status !== "ok" ? ` · ${esc(m.message)}` : ""}`, tone); }).join("");
    const tokens = d.tokens.map(t => drow(t.title, `${esc(t.source)}${t.windows.length ? "：" + t.windows.map(w => `${esc(w.label)} ${Math.round(w.used_percent)}%`).join("、") : ""}${t.error ? ` · ${esc(t.error)}` : ""}`, t.error ? "bad" : "")).join("");
    const cp = d.companion ? drow("Agent", `${({ rule: "固定句子", anthropic: "Claude", ollama: "本機 AI" })[d.companion.provider] || esc(d.companion.provider)}`
      + ` · 這小時已呼叫 ${d.companion.calls_last_hour}/${d.companion.max_calls_per_hour} 次`
      + (d.companion.setup ? ` · ${esc(d.companion.setup)}` : "") + (d.companion.fallback_reason ? ` · 上一句改用固定句子：${esc(d.companion.fallback_reason)}` : ""),
      d.companion.setup || d.companion.fallback_reason ? "warn" : "") : "";
    all.innerHTML = (d.app.demo ? drow("模式", "示範模式：所有資料都是腳本產生的，設定不會存檔", "warn") : "")
      + `<h4>小工具</h4>${mods}${cp}<h4>正在播放</h4>${media}${tokens ? `<h4>AI 用量的資料來源</h4>${tokens}` : ""}`
      + `<h4>程式</h4>${drow("連續工作", `${d.work_minutes} 分鐘`)}${drow("設定檔", `<code>${esc(d.app.config)}</code>`)}`
      + drow("資料夾（快取、紀錄、角色）", `<code>${esc(d.app.data_dir)}</code>`) + drow("程式位置（只讀取）", `<code>${esc(d.app.program_dir)}</code>`)
      + drow("環境", `Python ${esc(d.app.python)} · ${esc(d.app.platform)} · build ${esc(d.app.build)}`);
  }
  const log = $("#events");
  if (log && !log.closest("[hidden]")) {
    log.innerHTML = d.events.length ? [...d.events].reverse().map(e =>
      `<div class="ev ${e.outcome}"><time>${new Date(e.ts * 1000).toLocaleTimeString("zh-TW", { hour12: false })}</time><b>${esc(e.label)}${e.simulated ? "<em>測試</em>" : ""}</b><span>${e.line ? esc(e.line) : esc(OUTCOME[e.outcome] || e.outcome)}${e.line ? `<em>${esc(OUTCOME[e.outcome] || "")}</em>` : ""}</span></div>`).join("")
      : '<p class="hint">還沒有事件。列印完成、額度偏高、計時結束時會出現在這裡。</p>';
  }
}
async function loadDiagnostics() {
  if (document.hidden) return;
  try { drawDiagnostics(await (await fetch("/api/diagnostics", { cache: "no-store" })).json()); }
  catch { document.querySelectorAll("[data-diag]").forEach(el => { el.textContent = "讀不到診斷資料：Mondesk 是否還在執行？"; }); }
}
loadDiagnostics();
setInterval(loadDiagnostics, 3000);

// Apple Music / YouTube: the extension install guide in the media settings
document.addEventListener("click", async e => {
  const cp = e.target.closest("[data-copy]");
  if (cp) {
    try { await navigator.clipboard.writeText(cp.dataset.copy); cp.textContent = "已複製"; }
    catch { cp.textContent = "請手動複製"; }
    setTimeout(() => { cp.textContent = "複製"; }, 2000);
    return;
  }
  const b = e.target.closest("[data-ext]");
  if (!b) return;
  const msg = $("#extMsg");
  b.disabled = true;
  try {
    const r = await (await fetch("/api/extension", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ step: b.dataset.ext }) })).json();
    if (!r.ok) throw Error(r.error || "沒有回應");
    if (r.folder) { $("#extPath").hidden = false; $("#extPath").textContent = r.folder; }
    msg.textContent = b.dataset.ext === "prepare" ? "資料夾準備好了，接著做第 2 步。" : "已在檔案總管開啟。";
    msg.className = "hint ok";
  } catch (err) { msg.textContent = err.message; msg.className = "hint bad"; }
  finally { b.disabled = false; }
});
document.getElementById("extGuide")?.querySelector("summary").addEventListener("click", e => { e.currentTarget.parentElement.dataset.touched = "1"; });

// leaving for the panel: the same circular wipe the panel uses to come here
document.addEventListener("click", e => {
  const a = e.target.closest('a[href="/"]');
  if (!a || e.defaultPrevented || e.button || e.metaKey || e.ctrlKey || matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  e.preventDefault();
  const r = a.getBoundingClientRect(), x = r.left + r.width / 2, y = r.top + r.height / 2;
  const far = Math.hypot(Math.max(x, innerWidth - x), Math.max(y, innerHeight - y)) + 80;
  const w = document.createElement("div");
  w.className = "wipe";
  w.style.cssText = `left:${x - far}px;top:${y - far}px;width:${far * 2}px;height:${far * 2}px`;
  document.body.appendChild(w);
  const go = () => { location.href = a.href; };
  w.animate([{ scale: 0, opacity: 0 }, { opacity: 1, offset: .35 }, { scale: 1, opacity: 1 }],
    { duration: 560, easing: "cubic-bezier(.4, 0, .2, 1)", fill: "both" }).finished.then(go);
  setTimeout(go, 900);   // a hidden window never finishes the animation: go anyway
});
addEventListener("pageshow", () => document.querySelectorAll(".wipe").forEach(w => w.remove()));

// background picture: uploaded right away (it is a file, not a setting); which picture and how dark is part of the theme
$("#wallPick").onclick = () => $("#wallFile").click();
$("#wallFile").onchange = async e => {
  const file = e.target.files[0], msg = $("#wallMsg");
  e.target.value = "";
  if (!file) return;
  if (file.size > 8 * 1024 * 1024) { msg.textContent = "圖片超過 8 MB"; msg.className = "hint bad"; return; }
  msg.textContent = "上傳中…"; msg.className = "hint";
  try {
    const r = await (await fetch("/api/background", { method: "POST", headers: { "Content-Type": "application/octet-stream" }, body: file })).json();
    if (!r.ok) throw Error(r.error || "上傳失敗");
    const old = theme().image;
    cfg.theme = { ...theme(), image: { v: r.v, dim: old?.dim ?? 35, blur: old?.blur ?? 0 } };
    msg.textContent = "按「套用」後生效"; msg.className = "hint ok";
    paint(); dirty();
  } catch (err) { msg.textContent = err.message; msg.className = "hint bad"; }
};
$("#wallRemove").onclick = async () => {
  const t = theme(); delete t.image; cfg.theme = t;
  $("#wallMsg").textContent = "按「套用」後生效"; $("#wallMsg").className = "hint";
  try { await fetch("/api/background/delete", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" }); } catch { /* the file is only unused */ }
  paint(); dirty();
};
document.addEventListener("input", e => {
  const el = e.target;
  if (!el.dataset.wall) return;
  const t = theme();
  if (!t.image) return;
  cfg.theme = { ...t, image: { ...t.image, [el.dataset.wall]: +el.value } };
  paint(); dirty();
});


// ---------- the application (desktop.py): shown only when the page runs inside it ----------
(async () => {
  const box = document.getElementById("appBox"), auto = document.getElementById("appAutostart"), full = document.getElementById("appFullscreen");
  const post = body => fetch("/api/desktop", { method: "POST", headers: { "Content-Type": "application/json", "X-DeskMon": "1" }, body: JSON.stringify(body) }).then(r => r.json());
  const show = d => {
    box.hidden = !d.app;
    auto.checked = !!d.autostart; auto.closest("label").hidden = !d.autostart_supported;
    full.checked = !!d.fullscreen; full.closest("label").hidden = !d.window;
  };
  try { show(await (await fetch("/api/desktop")).json()); } catch { return; }
  auto.addEventListener("change", async () => { try { show(await post({ autostart: auto.checked })); } catch { auto.checked = !auto.checked; } });
  full.addEventListener("change", async () => { try { show(await post({ fullscreen: full.checked })); } catch { full.checked = !full.checked; } });
})();
