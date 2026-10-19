let printingBusy=false;
// Renderers keyed by module type. A new backend module only needs an entry here.
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const num = n => n == null ? "—" : n >= 1e9 ? (n / 1e9).toFixed(2) + "B" : n >= 1e6 ? (n / 1e6).toFixed(1) + "M" : n >= 1e3 ? (n / 1e3).toFixed(1) + "K" : String(n);
const mmss = s => !s || s < 0 ? "0:00" : `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`;
const hm = ts => new Date(ts * 1000).toLocaleTimeString("zh-TW", { hour: "2-digit", minute: "2-digit", hour12: false });
const dur = m => m == null ? "—" : m >= 60 ? `${Math.floor(m / 60)}h ${m % 60}m` : `${m}m`;
const until = ts => { const m = Math.max(0, Math.round((ts * 1000 - Date.now()) / 60000)); return m >= 1440 ? `${Math.floor(m / 1440)}d ${Math.floor(m % 1440 / 60)}h` : dur(m); };
const head = (m, tag) => `<div class="head"><span class="dot ${m.status}"></span><b>${esc(m.title)}</b></div>`;
const offline = m => `${head(m)}<div class="msg">${m.status === "error" ? "模組錯誤" : esc(m.data.message || "沒有資料")}${m.error ? `<small>${esc(m.error)}</small>` : ""}</div>`;

const PRINT_ICON = {
 pause:'<svg viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="4" width="4" height="16" rx="1"/><rect x="14" y="4" width="4" height="16" rx="1"/></svg>',
 resume:'<svg viewBox="0 0 24 24" fill="currentColor"><path d="M7 4v16l14-8z"/></svg>',
 stop:'<svg viewBox="0 0 24 24" fill="currentColor"><rect x="4" y="4" width="16" height="16" rx="3"/></svg>',
 skip:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M5 10a7 7 0 0 1 13-3M18 3v5h-5"/><rect x="3" y="15" width="4" height="5" rx="1"/><rect x="10" y="15" width="4" height="5" rx="1"/><rect x="17" y="15" width="4" height="5" rx="1"/></svg>',
 live:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="2.5" y="6" width="13" height="12" rx="2"/><path d="M15.5 10.5 21 7.5v9l-5.5-3"/><circle cx="7" cy="10" r="1.2" fill="currentColor" stroke="none"/></svg>',
 studio:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M14 4h6v6M20 4l-9 9"/><path d="M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5"/></svg>'
};
const ICON = {
  note: '<svg viewBox="0 0 24 24"><path d="M9 18V5l12-2v13" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/><circle cx="6" cy="18" r="3" fill="none" stroke="currentColor" stroke-width="1.6"/><circle cx="18" cy="16" r="3" fill="none" stroke="currentColor" stroke-width="1.6"/></svg>',
  printer: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="3"/><path d="M3 8h18M8 8v4h8V8M10 12l2 3 2-3M6 18h12"/></svg>',
};

const R = {
  bambu(m) {
    const d=m.data, pct=Math.max(0,Math.min(100,Number(d.progress)||0));
    const active=d.control_enabled === true && !printingBusy && ["RUNNING","PREPARE","PAUSE"].includes(d.stage);
    const allow=a=>active && (d.control_actions||[]).includes(a);
    return `${head(m)}<button class="printer-preview" data-camera="${esc(m.id)}" aria-label="開啟機艙直播">
      ${d.preview?`<img src="/api/asset/${esc(m.id)}/preview?v=${esc(d.preview_version)}" alt="目前列印模型">`:`<div class="printer-mark">${ICON.printer}</div>`}
      <span class="printer-caption">${esc(d.file || d.message || "X2D")}</span>
    </button>
    <div class="printer-bottom"><div class="printer-progress"><div class="printer-progress-label"><b>${d.progress==null?"—":pct}%</b><span>${esc(d.stage_label || "未連線")}</span></div><div class="printer-track"><div style="width:${pct}%"></div></div></div>
    <div class="printer-controls" data-printer="${esc(m.id)}">
    <button data-camera="${esc(m.id)}" aria-label="機艙直播" title="機艙直播">${PRINT_ICON.live}</button>
    <button data-studio aria-label="開啟 Bambu Studio" title="開啟 Bambu Studio">${PRINT_ICON.studio}</button></div></div>`;
  },

  media(m) {
    const d = m.data;
    if (!d.title) return offline(m);
    // extrapolate position client-side between polls
    const pos = d.playing ? d.position + (Date.now() / 1000 - d.sampled) : d.position;
    const p = d.duration > 0 ? Math.max(0, Math.min(100, pos / d.duration * 100)) : 0;
    return `${head(m, d.source)}
      <div class="m-top">
        <div class="m-art">${d.art_url || d.art ? `<img src="${esc(d.art_url || `/api/asset/${m.id}/art?v=${d.art}`)}" alt="專輯封面">` : ICON.note}</div>
        <div class="m-body">
        <div class="eq ${d.playing ? "" : "paused"}"><i></i><i></i><i></i>${d.duration > 0 ? `<span class="m-pct">-${mmss(Math.max(0, d.duration - pos))}</span>` : ""}</div>
        <div class="m-title">${esc(d.title)}</div>
        <div class="m-artist">${esc(d.artist || d.album || "")}</div>
        ${d.duration > 0 ? `<div class="m-bar"><div style="width:${p}%"></div></div>
        <div class="m-time"><span>${mmss(pos)}</span><span>${mmss(d.duration)}</span></div>` : ""}
      </div></div>
      <div class="m-ctl" data-module="${esc(m.id)}">
        <button data-act="prev" aria-label="上一首"><svg viewBox="0 0 24 24"><path d="M6 5h2v14H6zM20 5v14L9 12z"/></svg></button>
        <button data-act="toggle" class="main" aria-label="播放/暫停">${d.playing
          ? '<svg viewBox="0 0 24 24"><path d="M7 5h4v14H7zM13 5h4v14h-4z"/></svg>'
          : '<svg viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg>'}</button>
        <button data-act="next" aria-label="下一首"><svg viewBox="0 0 24 24"><path d="M16 5h2v14h-2zM4 5v14l11-7z"/></svg></button>
      </div>`;
  },

  tokens(m) {
    const d = m.data;
    if (!d.today) return offline(m);
    const today = d.today.input + d.today.output;
    let wins = d.windows;
    if (!wins?.length && (d.budget_5h || d.budget_week)) {
      wins = [["5h", d.window5h, d.budget_5h], ["7d", d.week, d.budget_week]].filter(x => x[2])
        .map(([label, t, b]) => ({ label, used_percent: Math.min(100, (t.input + t.output) / b * 100), estimate: true }));
    }
    let limits = (wins || []).map(w => `
      <div class="lim"><div class="lim-row"><span>${esc(w.label)}${w.resets_at ? ` <em>${until(w.resets_at)}</em>` : ""}</span><b>${Math.round(w.used_percent)}%</b></div>
      <div class="lim-bar ${w.used_percent > 85 ? "hot" : ""}"><div style="width:${w.used_percent}%"></div></div></div>`).join("");
    if (!limits) {
      const bar = (label, used, budget) => {
        const pct = budget ? Math.min(100, used / budget * 100) : 0;
        return `<div class="lim"><div class="lim-row"><span>${label}</span><b>${budget ? Math.round(pct) + "%" : "—%"}</b></div>
          <div class="lim-bar ${pct > 85 ? "hot" : ""}"><div style="width:${pct}%"></div></div></div>`;
      };
      limits = bar("5h", d.window5h.input + d.window5h.output, d.budget_5h)
             + bar("7d", d.week.input + d.week.output, d.budget_week);
    }
    return `${head(m, d.plan || (d.model || "").replace(/^claude-/, ""))}
      <div class="t-row"><div><div class="t-big">${num(today)}</div></div>
      <div class="t-lims">${limits}</div></div>`;
  },
};

const COLORS = { codex: "var(--codex)", claude: "var(--claude)" };
const cards = {};
const grid = document.getElementById("grid");
let state = null;

function render() {
  if (!state) return;
  let tokenSlot = grid.querySelector(".slot-tokens");
  if (!tokenSlot) { tokenSlot = document.createElement("div"); tokenSlot.className = "slot-tokens"; grid.appendChild(tokenSlot); }
  for (const m of state.modules) {
    let el = cards[m.id];
    if (!el) {
      el = cards[m.id] = document.createElement("section");
      el.dataset.id = m.id;
      el.className = `card ${m.type}`;
      (m.type === "tokens" ? tokenSlot : grid).appendChild(el);
    }
    if (m.type === "tokens") { el.style.setProperty("--c", COLORS[m.data.provider] || "var(--accent)"); if (m.data.provider) el.classList.add(m.data.provider); }
    const html = (R[m.type] || offline)(m);
    if (el._html !== html) { el.innerHTML = html; el._html = html; }
  }
}

async function poll() {
  try {
    state = await (await fetch("/api/state", { cache: "no-store" })).json();
    if (previewCfg) Object.assign(state, previewCfg);  // settings page: show unsaved edits
    applyLook();
    render();
  } catch { /* server restarting; keep last frame */ }
}

// layout + theme from state (or from the settings page's live preview)
function applyLook() {
  const display = state.display || {};
  const requested = +new URLSearchParams(location.search).get("panel");
  layoutDisplay = requested > 0 ? {...display, width: 640 * requested, height: 640, fit: "contain"} : display;
  const key = JSON.stringify(layoutDisplay);
  if (key !== applyLook.lastLayout) { applyLook.lastLayout = key; fit(); }
  const tk = JSON.stringify(state.theme || {});
  if (tk !== applyTheme.last) { applyTheme.last = tk; applyTheme(state.theme); }
}

function tick() {
  const n = new Date();
  document.getElementById("clock").textContent = n.toLocaleTimeString("zh-TW", { hour12: false });
  document.getElementById("date").textContent = n.toLocaleDateString("zh-TW", { month: "long", day: "numeric", weekday: "short" });
  render(); // keeps music progress moving smoothly
}

let layoutDisplay = {};
let previewCfg = null;
// live preview: the settings page posts its unsaved theme/display into this iframe
addEventListener("message", e => {
  if (e.origin !== location.origin || e.data?.type !== "deskmon-preview") return;
  previewCfg = { theme: e.data.theme, display: e.data.display };
  if (state) { Object.assign(state, previewCfg); applyLook(); render(); }
});


const BACKGROUNDS = {
  graphite: { bg: "#0b0c0e", card: "#141519", line: "#23252b" },
  oled:     { bg: "#000000", card: "#0c0c0e", line: "#1a1a1e" },
  navy:     { bg: "#070b14", card: "#0f1626", line: "#1c2740" },
  warm:     { bg: "#100d0b", card: "#1a1613", line: "#2b241f" },
};

function applyTheme(t = {}) {
  const r = document.documentElement.style;
  const bg = BACKGROUNDS[t.background] || BACKGROUNDS.graphite;
  r.setProperty("--bg", bg.bg); r.setProperty("--card", bg.card); r.setProperty("--line", bg.line);
  if (t.printer) r.setProperty("--accent", t.printer);
  if (t.music) r.setProperty("--music", t.music);
  for (const k of ["codex", "claude"]) {
    const c = t[k];
    if (Array.isArray(c) && c.length === 2) {
      r.setProperty(`--${k}`, c[0]);
      r.setProperty(`--${k}-fluid`, `linear-gradient(100deg, ${c[0]}, ${c[1]}, ${c[0]}, ${c[1]}, ${c[0]})`);
    }
  }
}

function fit() {
  const d = DeskMonLayout.calculate(innerWidth, innerHeight, layoutDisplay);
  const root = document.documentElement.style;
  root.setProperty("--w", d.width + "px");
  root.setProperty("--h", d.height + "px");
  root.setProperty("--sx", d.scale);
  root.setProperty("--s", d.scale);
}

// play controls (event delegation: cards re-render every second)
grid.addEventListener("click", async e => {
  const btn = e.target.closest("[data-act]");
  if (!btn) {
    const card = e.target.closest(".card.media");
    if (card) openLyrics(card.dataset.id);
    return;
  }
  const module = btn.closest("[data-module]").dataset.module;
  btn.classList.add("busy");
  // optimistic flip so the button feels instant
  const mod = state?.modules.find(m => m.id === module);
  if (btn.dataset.act === "toggle" && mod?.data.title) {
    mod.data.position += mod.data.playing ? Date.now() / 1000 - mod.data.sampled : 0;
    mod.data.sampled = Date.now() / 1000;
    mod.data.playing = !mod.data.playing;
    render();
  }
  try {
    await fetch("/api/action", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ module, action: btn.dataset.act }) });
  } finally { setTimeout(poll, 400); }
});

addEventListener("resize", fit);
fit(); tick(); poll();
setInterval(tick, 1000);
setInterval(poll, 2000);

// ---------- fullscreen lyrics (tap the music card) ----------
const LY = document.getElementById("lyrics");
const ly = { id: null, track: null, lines: null, plain: null, state: null, active: -1, seeking: false, revision: null, request: 0 };

function openLyrics(id) { resetLyricScroll(); ly.id = id; ly.track = null; LY.hidden = false; tickLyrics(); }
LY.addEventListener("click", async e => {
  const p = e.target.closest(".ly-lines p[data-i]");
  if (p) {
    if (!ly.lines || ly.seeking) return;
    const position=ly.lines[+p.dataset.i]?.[0], track=ly.track, id=ly.id;
    if (!Number.isFinite(position)) return;
    ly.seeking=true;
    try {
      const response=await fetch("/api/action",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({module:id,action:"seek",position,track})});
      const result=await response.json();
      if (!response.ok || !result.ok) throw new Error(result.error || "播放器不支援跳轉");
      if (ly.track===track) {const m=state.modules.find(x=>x.id===id);if(m)m.data=result.result;ly.active=-2;tickLyrics();}
    } catch(err) {
      let message=LY.querySelector(".ly-error");if(!message){message=document.createElement("div");message.className="ly-error";message.setAttribute("role","status");LY.appendChild(message)}
      message.textContent=err.message.replace(/^RuntimeError: /,"");setTimeout(()=>message.remove(),4000);
    } finally {ly.seeking=false;await poll()}
    return;
  }
  if(e.target.closest(".ly-close")){LY.hidden = true; ly.id = null;}
});

function nowPos() {
  const d = state.modules.find(x => x.id === ly.id)?.data || {};
  return d.playing ? d.position + (Date.now() / 1000 - d.sampled) : d.position;
}

async function loadLyrics(m) {
  const request = ++ly.request, moduleID = ly.id;
  if(ly.track!==m.data.track)resetLyricScroll();
  ly.track = m.data.track; ly.lines = ly.plain = null; ly.active = -1; ly.state = m.data.lyrics;
  ly.revision = m.data.lyrics_revision;
  const box = LY.querySelector(".ly-lines");
  const art = m.data.art_url || (m.data.art ? `/api/asset/${m.id}/art?v=${m.data.art}` : "");
  LY.querySelector(".ly-art").src = art; LY.querySelector(".ly-art").hidden = !art;
  LY.querySelector(".ly-bg").style.backgroundImage = art ? `url(${JSON.stringify(art)})` : "none";
  LY.querySelector(".ly-title").textContent = m.data.title || "";
  LY.querySelector(".ly-artist").textContent = m.data.artist || "";
  if (m.data.lyrics !== "ok") {
    box.innerHTML = `<p class="ly-msg">${m.data.lyrics === "native_missing" ? esc(m.data.native_diagnostic || "請在 Apple Music 網頁開啟歌詞面板；若已開啟，這首歌可能沒有可用歌詞。") : m.data.lyrics === "loading" ? "正在找歌詞…" : "找不到這首歌的歌詞"}</p>`;
    return;
  }
  const d = await (await fetch(`/api/asset/${m.id}/lyrics?t=${m.data.track}&r=${m.data.lyrics_revision ?? ''}`, {cache: 'no-store'})).json();
  if (request !== ly.request || moduleID !== ly.id || LY.hidden) return;
  ly.lines = d.synced?.filter(l => l[1]) || null;
  ly.plain = d.plain || null;
  const rows = ly.lines ? ly.lines.map(l => [l[1], l[2]]) : (ly.plain || []).map(t => [t]);
  box.innerHTML = rows.map(([t, sub], i) =>
    `<p data-i="${i}">${esc(t) || "&nbsp;"}</p>`).join("");
  box.classList.toggle("plain", !ly.lines);
  if (!ly.lines && rows.length) box.insertAdjacentHTML('afterbegin', '<div class="ly-msg" role="status">Apple Music 未提供同步時間，僅顯示歌詞。</div>');
}

function tickLyrics() {
  if (LY.hidden || !state) return;
  const m = state.modules.find(x => x.id === ly.id);
  if (!m?.data.title) return;
  if (m.data.track !== ly.track || m.data.lyrics_revision !== ly.revision || (ly.state !== "ok" && m.data.lyrics !== ly.state)) loadLyrics(m);
  const d = m.data;
  const pos = nowPos();
  LY.querySelector(".ly-bar div").style.width = d.duration > 0 ? Math.max(0,Math.min(100, pos / d.duration * 100)) + "%" : "0";
  if (!ly.lines) return;
  let i = ly.lines.findIndex(l => l[0] > pos + 0.25) - 1;
  if (i < -1) i = ly.lines.length - 1;
  if (i === ly.active) return;
  ly.active = i;
  const box = LY.querySelector(".ly-lines");
  box.querySelectorAll("p").forEach(p => {
    const k = +p.dataset.i;
    p.className = k === i ? "now" : k < i ? "past" : "";
  });
  const cur = box.querySelector("p.now");
  const body = LY.querySelector(".ly-body");
  if(lyricManual)return;
  const y = cur ? cur.offsetTop - body.clientHeight * 0.32 + cur.offsetHeight / 2 : 0;
  scrollLyricsTo(box, -Math.max(0, y));
}

// Smooth-scroll the lyrics, but never depend on the animation: some windows (e.g. an
// unfocused one on a second screen) never advance CSS transitions, which froze the lyrics.
let lyricAnim = true;
function scrollLyricsTo(box, target) {
  box.style.transition = lyricAnim ? "" : "none";
  box.style.transform = `translateY(${target}px)`;
  if (!lyricAnim) return;
  clearTimeout(scrollLyricsTo.check);
  scrollLyricsTo.check = setTimeout(() => {
    const now = new DOMMatrixReadOnly(getComputedStyle(box).transform).m42;
    if (Math.abs(now - target) > 2) {
      lyricAnim = false;               // animation stuck here: jump and stop animating
      box.style.transition = "none";
      box.style.transform = `translateY(${target}px)`;
    }
  }, 900);
}
setInterval(tickLyrics, 200);

// show the settings gear only while someone is interacting
let sleepTimer;
function wake() {
  document.body.classList.add("awake");
  clearTimeout(sleepTimer);
  sleepTimer = setTimeout(() => document.body.classList.remove("awake"), 3000);
}
["mousemove", "touchstart", "pointerdown"].forEach(ev => addEventListener(ev, wake, { passive: true }));

const printerView=document.createElement("dialog");
printerView.className="printer-dialog";
printerView.innerHTML='<div class="camera-heading"><h2>機艙直播</h2><button data-camera-close aria-label="關閉直播">✕</button></div><div class="camera-content"><img hidden alt="機艙直播"><p role="status"></p></div>';
document.body.appendChild(printerView);
let cameraId=null,cameraBusy=false;
printerView.querySelector('[data-camera-close]').onclick=()=>printerView.close();
// small touchscreen: tapping the picture or the dimmed backdrop also closes the live view
printerView.addEventListener('click',e=>{if(e.target===printerView||e.target.closest('.camera-content'))printerView.close()});
printerView.addEventListener('close',()=>{cameraId=null;const img=printerView.querySelector('img');img.hidden=true;img.removeAttribute('src');delete img.dataset.streaming});
async function refreshCamera(){
 if(!cameraId || cameraBusy || !printerView.open)return;
 cameraBusy=true;
 const id=cameraId;
 try{
  const response=await fetch('/api/action',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({module:id,action:'camera'})});
  const data=await response.json();
  if(cameraId!==id)return;
  if(!data.ok)throw Error(data.error);
  const image=printerView.querySelector('img');
  image.hidden=!data.result.ready;
  // once frames flow, switch to the continuous MJPEG stream (one connection, ~10 fps)
  if(data.result.ready&&!image.dataset.streaming){image.dataset.streaming='1';image.src=`/api/stream/${encodeURIComponent(id)}?t=${Date.now()}`}
  printerView.querySelector('p').textContent=data.result.ready?'':data.result.message||'正在連接攝影機…';
 }catch(e){printerView.querySelector('p').textContent=e.message||'攝影機無法連線'}
 finally{cameraBusy=false}
}
setInterval(refreshCamera,1000);
const stopDialog=document.createElement('dialog');stopDialog.className='stop-dialog';
stopDialog.innerHTML='<h2>確定終止列印？</h2><p>這次列印會取消，無法直接繼續。</p><div><button data-cancel>返回</button><button data-confirm class="stop">終止列印</button></div>';
document.body.appendChild(stopDialog);
let pendingStop=null;
stopDialog.querySelector('[data-cancel]').onclick=()=>stopDialog.close();
stopDialog.addEventListener('close',()=>pendingStop=null);
stopDialog.querySelector('[data-confirm]').onclick=()=>{const id=pendingStop;stopDialog.close();if(id)sendPrinter(id,'stop')};
async function sendPrinter(id,action,extra={}){
 if(printingBusy)return;printingBusy=true;
 document.querySelectorAll("[data-print]").forEach(b=>{b.disabled=true;b.classList.add("busy")});
 try{
  const response=await fetch('/api/action',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({module:id,action,...extra})});
  const data=await response.json();if(!data.ok)throw Error(data.error);
 }catch(e){const notice=document.createElement('div');notice.className='printer-notice';notice.setAttribute('role','alert');notice.textContent=e.message||'操作未成功';document.body.appendChild(notice);setTimeout(()=>notice.remove(),6000)}
 finally{printingBusy=false;await poll()}
}
grid.addEventListener('click',e=>{
 const studio=e.target.closest('[data-studio]');
 if(studio){sendPrinter(studio.closest('[data-printer]').dataset.printer,'open_studio');return}
 const preview=e.target.closest('[data-camera]');
 if(preview){cameraId=preview.dataset.camera;printerView.querySelector('p').textContent='正在連接攝影機…';printerView.showModal();refreshCamera()}
});

const skipDialog=document.createElement('dialog');skipDialog.className='stop-dialog skip-dialog';document.body.appendChild(skipDialog);
grid.addEventListener('click',e=>{
 const button=e.target.closest('[data-skip]');if(!button)return;
 const id=button.closest('[data-printer]').dataset.printer,d=state.modules.find(m=>m.id===id)?.data;
 if(!d)return;
 const enabled=d.skip_enabled && d.objects?.length;
 skipDialog.innerHTML=`<h2>跳過物件</h2>${enabled?`<p>選擇要停止列印的物件。</p><div class="skip-objects">${d.objects.map(o=>`<label><input type="checkbox" value="${o.id}" ${o.skipped?'disabled checked':''}>${esc(o.name)} <small>#${o.id}${o.skipped?' · 已跳過':''}</small></label>`).join('')}</div>`:'<p>此切片未啟用「標記物件」，無法跳過物件。下次切片時請啟用這個選項。</p>'}<div><button data-return>返回</button>${enabled?'<button data-skip-confirm class="stop">確認跳過</button>':''}</div>`;
 skipDialog.querySelector('[data-return]').onclick=()=>skipDialog.close();
 const confirm=skipDialog.querySelector('[data-skip-confirm]');
 if(confirm)confirm.onclick=()=>{const objects=[...skipDialog.querySelectorAll('input:checked:not(:disabled)')].map(c=>+c.value);if(!objects.length)return;skipDialog.close();sendPrinter(id,'skip_objects',{objects,job:d.preview_version})};
 skipDialog.showModal();
});

let lyricManual=false,lyricScroll=0;
const lyricBody=LY.querySelector('.ly-body'),lyricBox=LY.querySelector('.ly-lines');
const lyricFollow=document.createElement('button');lyricFollow.className='ly-follow';lyricFollow.textContent='回到目前歌詞';lyricFollow.hidden=true;LY.appendChild(lyricFollow);
function resetLyricScroll(){lyricManual=false;lyricScroll=0;lyricFollow.hidden=true;ly.active=-2}
lyricFollow.onclick=e=>{e.stopPropagation();resetLyricScroll();tickLyrics()};
lyricBody.addEventListener('wheel',e=>{
 if(LY.hidden)return;e.preventDefault();
 if(!lyricManual){const matrix=new DOMMatrixReadOnly(getComputedStyle(lyricBox).transform);lyricScroll=Math.max(0,-matrix.m42)}
 lyricManual=true;lyricFollow.hidden=false;
 const delta=e.deltaY*(e.deltaMode===1?32:e.deltaMode===2?lyricBody.clientHeight:1);
 lyricScroll=Math.max(0,Math.min(Math.max(0,lyricBox.scrollHeight-lyricBody.clientHeight),lyricScroll+delta));
 lyricBox.style.transform=`translateY(${-lyricScroll}px)`;
},{passive:false});
