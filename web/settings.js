const DEFAULT_THEME = { background: "graphite", printer: "#f2a541", music: "#7ee0b5",
  codex: ["#4f7dff", "#c46bff"], claude: ["#ff9a3c", "#e8662a"] };
const BGS = { graphite: ["石墨", "#0b0c0e", "#141519"], oled: ["純黑 OLED", "#000", "#0c0c0e"],
  navy: ["深海藍", "#070b14", "#0f1626"], warm: ["暖木", "#100d0b", "#1a1613"] };
const PRESETS = {
  "預設": DEFAULT_THEME,
  "霓虹": { printer: "#ffd23f", music: "#3cf0c8", codex: ["#00c6ff", "#a64dff"], claude: ["#ff4d8d", "#ff9e3d"] },
  "柔和": { printer: "#e9b872", music: "#9fd8b8", codex: ["#8aa6ff", "#b9a2ff"], claude: ["#f2a37d", "#e98b6b"] },
  "單色": { printer: "#d8d8d8", music: "#d8d8d8", codex: ["#bfc4ff", "#ffffff"], claude: ["#ffd2b0", "#ffffff"] },
};
let cfg, saved;
const $ = s => document.querySelector(s);
const mod = id => cfg.modules.find(m => m.id === id);
const theme = () => ({ ...DEFAULT_THEME, ...cfg.theme });

// data-k paths: "<moduleId>.<field>", "display.<field>", "theme.<field>[.<index>]"
function get(path) {
  const [root, key, idx] = path.split(".");
  if (root === "display") return cfg.display?.[key] ?? (key === "text_scale" ? 1 : "");
  if (root === "theme") { const v = theme()[key]; return idx != null ? v[idx] : v; }
  const m = mod(root);
  if (!m) return "";
  // "music.lyrics_sources.kugou" = is "kugou" in the list
  if (idx != null) return (m[key] ?? LIST_DEFAULTS[key] ?? []).includes(idx);
  return key === "enabled" ? m.enabled !== false : m[key] ?? "";
}
const LIST_DEFAULTS = { lyrics_sources: ["lrclib"] };

function set(path, el) {
  const [root, key, idx] = path.split(".");
  const v = el.type === "checkbox" ? el.checked : el.value;
  if (root === "display") {
    cfg.display ??= {};
    if (key === "text_scale") cfg.display.text_scale = +v;
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
    } else m[key] = el.type === "number" ? (v === "" ? null : +v) : v;
  }
  paint();
  dirty();
}

function fill() {
  document.querySelectorAll("[data-k]").forEach(el => {
    const v = get(el.dataset.k);
    if (el.type === "checkbox") el.checked = !!v; else el.value = v;
  });
  const d = DeskMonLayout.settings(cfg.display);
  const chosen = d.fit === "auto" ? "auto" : `${d.width},${d.height}`;
  $("#layoutSize").value = [...$("#layoutSize").options].some(o => o.value === chosen) ? chosen : "960,640";
  paint();
}

function paint() {
  const t = theme();
  $("#bgs").innerHTML = Object.entries(BGS).map(([k, [name, b, c]]) =>
    `<div class="swatch ${t.background === k ? "on" : ""}" data-bg="${k}" style="--b:${b};--k:${c}"><div></div>${name}</div>`).join("");
  $("#gCodex").style.background = `linear-gradient(90deg, ${t.codex[0]}, ${t.codex[1]})`;
  $("#gClaude").style.background = `linear-gradient(90deg, ${t.claude[0]}, ${t.claude[1]})`;
  const r = document.documentElement.style;
  r.setProperty("--printer", t.printer);
  r.setProperty("--music", t.music);
  r.setProperty("--codex", t.codex[0]);
  const scale = Math.round((cfg.display?.text_scale ?? 1) * 100) + "%";
  const d = DeskMonLayout.settings(cfg.display);
  $("#scaleVal").textContent = scale;
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
  if (pr) { cfg.theme = { ...theme(), ...PRESETS[pr.dataset.preset] }; fill(); dirty(); }
  const rv = e.target.closest("[data-reveal]");
  if (rv) {
    const i = rv.previousElementSibling;
    i.type = i.type === "password" ? "text" : "password";
    rv.textContent = i.type === "password" ? "顯示" : "隱藏";
  }
});

$("#presets").innerHTML = Object.entries(PRESETS).map(([k, p]) =>
  `<button type="button" data-preset="${k}"><i style="background:linear-gradient(135deg, ${p.codex[0]}, ${p.claude[0]})"></i>${k}</button>`).join("");

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
  body: JSON.stringify(body) }).then(r => r.json()).catch(() => ({ok:false, message:"無法連線到服務，請確認 DeskMon 正在執行。"}));

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
  const normalized = DeskMonLayout.settings(cfg.display);
  cfg.display = {...cfg.display, width:normalized.width, height:normalized.height, fit:normalized.fit, text_scale:normalized.textScale};
  delete cfg.display.panel_aspect;
  delete cfg.display.signal_aspect;
  saved = JSON.stringify(cfg);
  fill();
  $("#pv").addEventListener("load", () => setTimeout(pushPreview, 300));
})();

$("#layoutSize").onchange = e => {
  cfg.display ??= {};
  if (e.target.value === "auto") cfg.display.fit = "auto";
  else { const [w,h] = e.target.value.split(",").map(Number); Object.assign(cfg.display, {width:w,height:h,fit:"contain"}); }
  delete cfg.display.panel_aspect; delete cfg.display.signal_aspect;
  paint(); dirty();
};
