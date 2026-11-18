let printingBusy=false;
// Renderers keyed by module type. A new backend module only needs an entry here.
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const num = n => n == null ? "—" : n >= 1e9 ? (n / 1e9).toFixed(2) + "B" : n >= 1e6 ? (n / 1e6).toFixed(1) + "M" : n >= 1e3 ? (n / 1e3).toFixed(1) + "K" : String(n);
const mmss = s => !s || s < 0 ? "0:00" : `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`;
const hm = ts => new Date(ts * 1000).toLocaleTimeString("zh-TW", { hour: "2-digit", minute: "2-digit", hour12: false });
const dur = m => m == null ? "—" : m >= 60 ? `${Math.floor(m / 60)}h ${m % 60}m` : `${m}m`;
const until = ts => { const m = Math.max(0, Math.round((ts * 1000 - Date.now()) / 60000)); return m >= 1440 ? `${Math.floor(m / 1440)}d ${Math.floor(m % 1440 / 60)}h` : dur(m); };
// title row; the small gear right after the title opens only this card's settings (hidden until touched)
const CARD_SETTINGS = ["bambu", "media", "tokens", "weather"];
const cardGear = m => CARD_SETTINGS.includes(m.type)
  ? `<a class="card-cfg" href="/settings.html?w=${m.type}" aria-label="設定">${document.getElementById("gear")?.innerHTML || ""}</a>` : "";
// the music / video card is titled by where it is playing from (Apple Music, YouTube, Bilibili…): no separate source tag
const SOURCE_NAME = { Browser: "影片", Chrome: "Chrome", "msedge.exe": "Edge" };
const head = (m, tag) => `<div class="head"><span class="dot ${m.status}"></span><b>${esc(m.type === 'media' && tag ? SOURCE_NAME[tag] || tag : m.title)}</b>${cardGear(m)}</div>`;
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

ICON.spark = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8z"/><path d="M19 15l.8 2.2L22 18l-2.2.8L19 21l-.8-2.2L16 18l2.2-.8z"/></svg>';
ICON.warn = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3 2 20h20z"/><path d="M12 10v4M12 17h.01"/></svg>';
ICON.gear = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/><path d="M12 2v3M12 19v3M4.2 4.2l2.1 2.1M17.7 17.7l2.1 2.1M2 12h3M19 12h3M4.2 19.8l2.1-2.1M17.7 6.3l2.1-2.1"/></svg>';

// ---------- empty states: what's going on + what to do, readable on a 7cm screen ----------
const CARD_ICON = { bambu: "printer", media: "note", tokens: "spark", weather: "cloud" };
ICON.cloud = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M7 18h10a4 4 0 0 0 .6-7.96A6 6 0 0 0 6 11a3.5 3.5 0 0 0 1 7z"/></svg>';
function emptyInfo(m) {
  const msg = m.data?.message || "", title = m.title || "";
  if (m.status === "starting") return { tone: "loading", title: "讀取中…" };
  if (m.status === "error") return { tone: "error", icon: "warn", title: "讀取失敗",
    hint: (m.error || "").replace(/^\w+Error:\s*/, "").slice(0, 60) };
  if (m.type === "bambu") {
    if (/尚未填入/.test(msg)) return { tone: "setup", icon: "gear", title: "尚未設定印表機", hint: "點右上角的齒輪填入印表機資料" };
    if (/連線中/.test(msg)) return { tone: "loading", title: "正在連線印表機…" };
    if (/拒絕登入/.test(msg)) return { tone: "error", icon: "warn", title: "印表機拒絕連線", hint: "請確認 LAN 存取碼" };
    if (/無法連到/.test(msg)) return { tone: "error", title: "找不到印表機", hint: "請確認 IP、電源和網路" };
    if (/未收到狀態/.test(msg)) return { tone: "error", title: "已連線但沒有資料", hint: "請確認序號是否正確" };
    return { tone: "error", title: "印表機未連線", hint: msg };
  }
  if (m.type === "media") {
    if (/Apple Music/.test(msg)) return { tone: "setup", title: "Apple Music 未連線", hint: "在 Chrome 開啟 Apple Music 並播放" };
    if (/沒有播放/.test(msg) || !msg) return { tone: "idle", title: "目前沒有播放", hint: "播放音樂後會自動顯示" };
    return { tone: "setup", icon: "gear", title: "缺少播放器工具", hint: msg };
  }
  if (m.type === "tokens") return { tone: "idle", title: "還沒有用量紀錄", hint: `使用 ${title} 後會自動顯示` };
  if (m.type === "weather") return /尚未設定/.test(msg) ? { tone: "setup", icon: "gear", title: "尚未設定地點", hint: "點右上角的齒輪選擇城市" }
    : { tone: "error", title: "讀不到天氣", hint: "請確認網路，稍後會自動重試" };
  return { tone: "idle", title: msg || "沒有資料" };
}
function emptyCard(m) {
  const e = emptyInfo(m);
  const icon = e.tone === "loading" ? '<span class="spinner"></span>' : ICON[e.icon || CARD_ICON[m.type]] || "";
  if (e.tone === "setup")   // not set up yet: the whole card is the way into its settings, with a lit gear
    return `${head(m)}<a class="empty setup" href="/settings.html?w=${m.type}" aria-label="${esc(e.title)}，前往設定"><div class="empty-ic">${ICON.gear}</div>
      <div class="empty-txt"><div class="empty-t">${esc(e.title)}</div><div class="empty-h">點這裡設定</div></div></a>`;
  return `${head(m)}<div class="empty ${e.tone}"><div class="empty-ic">${icon}</div>
    <div class="empty-txt"><div class="empty-t">${esc(e.title)}</div>${e.hint ? `<div class="empty-h">${esc(e.hint)}</div>` : ""}</div></div>`;
}

const R = {
  bambu(m) {
    if (!m.data?.stage) return emptyCard(m);
    const d=m.data, pct=Math.max(0,Math.min(100,Number(d.progress)||0));
    const active=d.control_enabled === true && !printingBusy && ["RUNNING","PREPARE","PAUSE"].includes(d.stage);
    const allow=a=>active && (d.control_actions||[]).includes(a);
    return `${head(m)}<button class="printer-preview" data-camera="${esc(m.id)}" aria-label="開啟機艙直播">
      ${d.preview?`<img src="/api/asset/${esc(m.id)}/preview?v=${esc(d.preview_version)}" alt="目前列印模型">`:`<div class="printer-mark">${ICON.printer}</div>`}
      <span class="printer-caption">${esc(d.file || d.message || "X2D")}${d.preview && d.preview_pending ? ' · 更新預覽中' : ''}</span>
    </button>
    <div class="printer-bottom"><div class="printer-progress"><div class="printer-progress-label"><b>${d.progress==null?"—":pct}%</b><span>${esc(d.stage_label || "未連線")}</span></div><div class="printer-track"><div style="width:${pct}%"></div></div></div>
    <div class="printer-controls" data-printer="${esc(m.id)}">
    <button data-camera="${esc(m.id)}" aria-label="機艙直播" title="機艙直播">${PRINT_ICON.live}</button>
    <button data-studio aria-label="開啟 Bambu Studio" title="開啟 Bambu Studio">${PRINT_ICON.studio}</button></div></div>`;
  },

  media(m) {
    const d = m.data;
    if (!d.title) return emptyCard(m);
    // extrapolate position client-side between polls
    const pos = d.playing ? d.position + (Date.now() / 1000 - d.sampled) : d.position;
    const p = d.duration > 0 ? Math.max(0, Math.min(100, pos / d.duration * 100)) : 0;
    return `${head(m, d.source)}
      <div class="m-top" role="button" tabindex="0" aria-label="${d.video ? '在面板全螢幕顯示影片' : '開啟歌詞'}">
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
        ${d.video && d.browser_bridge ? `<button data-act="side_screen" class="side" aria-label="在副螢幕全螢幕播放" title="在副螢幕全螢幕播放"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5"/></svg></button>` : ""}
      </div>`;
  },

  tokens(m) {
    const d = m.data;
    const refresh = (d.provider || m.id) === 'claude' ? `<div class="usage-refresh-row"><button type="button" data-usage-refresh="${esc(m.id)}" aria-label="${usageRefresh.has(m.id) ? '查詢中' : '重新查詢 Claude 用量'}" title="重新查詢" ${usageRefresh.has(m.id) ? 'disabled aria-busy="true"' : ''}><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M20 7v5h-5M20 12a8 8 0 1 0-2.3 5.7"/></svg></button><span role="status">${esc(usageRefreshMessage.get(m.id) || '')}</span></div>` : '';
    // no data yet, or no usage logged at all in the last 7 days
    if (!d.today || (!d.week?.calls && !d.windows?.length)) return emptyCard(m) + refresh;
    const today = d.today.input + d.today.output;
    let wins = d.windows;
    if (!wins?.length && (d.budget_5h || d.budget_week)) {
      wins = [["5h", d.window5h, d.budget_5h], ["7d", d.week, d.budget_week]].filter(x => x[2])
        .map(([label, t, b]) => ({ label, used_percent: Math.min(100, (t.input + t.output) / b * 100), estimate: true }));
    }
    const tight = Math.max(-1, ...(wins || []).map(w => w.used_percent));
    let limits = (wins || []).map(w => `
      <div class="lim${w.used_percent === tight ? " tight" : ""}"><div class="lim-row"><span>${esc(w.label)}${w.resets_at ? ` <em>${until(w.resets_at)}</em>` : ""}</span><b>${Math.round(w.used_percent)}%</b></div>
      <div class="lim-bar ${w.used_percent > 85 ? "hot" : ""}"><div style="width:${w.used_percent}%"></div></div></div>`).join("");
    if (!limits && d.usage_error) {
      // the account's real % couldn't be read: say why instead of showing empty 0% bars
      limits = `<div class="lim usage-error" role="status">${esc(d.usage_error)}</div>`;
    } else if (!limits) {
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
      <div class="t-lims">${limits}</div></div>${refresh}`;
  },
};

// weather card (modules/weather.py)
const WX = (() => {
  const s = body => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">${body}</svg>`;
  const cloud = '<path d="M7 19h10a4 4 0 0 0 .6-7.96A6 6 0 0 0 6 12a3.5 3.5 0 0 0 1 7z"/>';
  const small = '<path d="M9 19h8.5a3.5 3.5 0 0 0 .5-6.96A5 5 0 0 0 8.3 13 3 3 0 0 0 9 19z"/>';
  return {
    sun: s('<circle cx="12" cy="12" r="4.2"/><path d="M12 2.5v2.2M12 19.3v2.2M2.5 12h2.2M19.3 12h2.2M5.3 5.3l1.5 1.5M17.2 17.2l1.5 1.5M5.3 18.7l1.5-1.5M17.2 6.8l1.5-1.5"/>'),
    moon: s('<path d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5z"/>'),
    partly: s('<circle cx="8" cy="8" r="3"/><path d="M8 2.2v1.4M2.2 8h1.4M3.9 3.9l1 1M12.1 3.9l-1 1"/>' + small),
    "partly-night": s('<path d="M11.5 7.5A4.5 4.5 0 0 1 6 3a4.5 4.5 0 1 0 5.5 4.5z"/>' + small),
    cloud: s(cloud),
    rain: s('<path d="M7 15h10a4 4 0 0 0 .6-7.96A6 6 0 0 0 6 8a3.5 3.5 0 0 0 1 7z"/><path d="M8 18l-1 3M12 18l-1 3M16 18l-1 3"/>'),
    snow: s('<path d="M7 15h10a4 4 0 0 0 .6-7.96A6 6 0 0 0 6 8a3.5 3.5 0 0 0 1 7z"/><path d="M8 19h.01M12 20.5h.01M16 19h.01M10 22h.01M14 22h.01"/>'),
    storm: s('<path d="M7 15h10a4 4 0 0 0 .6-7.96A6 6 0 0 0 6 8a3.5 3.5 0 0 0 1 7z"/><path d="M12.5 15l-2.5 4h3l-1.5 3"/>'),
    fog: s('<path d="M7 13h10a4 4 0 0 0 .6-7.96A6 6 0 0 0 6 6a3.5 3.5 0 0 0 1 7z"/><path d="M5 17h14M7 20.5h10"/>'),
  };
})();
const deg = v => v == null ? "—" : `${v}°`;
R.weather = m => {
  const d = m.data || {};
  if (d.temp == null) return emptyCard(m);
  const soon = d.rain_soon;
  const hours = (d.hours || []).slice(0, 6).map(h => `<div class="wx-h${h.pop >= 60 || h.mm >= 0.3 ? " wet" : ""}"><small>${h.hour}時</small>${WX[h.icon] || WX.cloud}<b>${deg(h.temp)}</b><em>${h.pop != null ? h.pop + "%" : h.mm >= 0.1 ? h.mm.toFixed(1) + "mm" : ""}</em></div>`).join("");
  return `${head(m)}<div class="wx">
    <div class="wx-now"><div class="wx-ic">${WX[d.icon] || WX.cloud}</div>
      <div class="wx-main"><div class="wx-temp">${deg(d.temp)}</div>
        <div class="wx-label">${esc(d.label || "")}${d.place ? ` · ${esc(d.place)}` : ""}</div></div></div>
    <div class="wx-meta"><span>高 ${deg(d.high)}　低 ${deg(d.low)}</span>${d.rain_today == null ? "" : `<span>降雨 ${d.rain_today}%</span>`}${d.stale ? "<span class=\"wx-old\">資料較舊</span>" : ""}</div>
    ${soon ? `<div class="wx-alert">${soon.in_hours <= 1 ? "一小時內" : `約 ${soon.in_hours} 小時後`}可能下雨${soon.probability != null ? `（${soon.probability}%）` : ""}</div>` : ""}
    <div class="wx-hours">${hours}</div></div>`;
};

// volume + brightness card (modules/system.py); the panel's own dim works on every screen
const SYS_ICON = {
  vol: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M4 9h4l5-4v14l-5-4H4z"/><path d="M16.5 8.5a5 5 0 0 1 0 7M19 6a8.5 8.5 0 0 1 0 12"/></svg>',
  mute: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M4 9h4l5-4v14l-5-4H4z"/><path d="M17 9l5 6M22 9l-5 6"/></svg>',
  sun: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M2 12h2M20 12h2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>',
};
let panelBright = 100;
try { panelBright = Math.max(25, Math.min(100, +localStorage.getItem("deskmon-panel-brightness") || 100)); } catch {}
R.system = m => {
  const d = m.data || {};
  // one fat bar per control: filled from the left, icon at the start, number at the end; the real range
  // input lies invisible on top. The volume icon is a button (mute); the others are only pictures.
  const row = (icon, label, attrs, value) => `<div class="sys-row${attrs.muted ? " muted" : ""}" style="--v:${Math.round(value)}">
    <div class="sys-pill"><i class="sys-fill"></i>
      <input type="range" min="${attrs.min ?? 0}" max="100" step="1" value="${value}" ${attrs.data} aria-label="${label}">
      ${attrs.mute ? `<button type="button" class="sys-knob sys-mute" data-sys-mute aria-label="${attrs.muted ? "取消靜音" : "靜音"}">${icon}</button>` : `<span class="sys-knob">${icon}</span>`}
      <span class="sys-name">${esc(label)}</span><b>${Math.round(value)}</b></div></div>`;
  const rows = [];
  if (d.volume != null) rows.push(row(d.muted ? SYS_ICON.mute : SYS_ICON.vol, d.muted ? "已靜音" : "音量", { data: `data-sys="volume"`, muted: d.muted, mute: true }, d.volume));
  // Brightness here is the panel dimming itself (a dark layer over the page): it works on every screen and
  // never touches the real monitor settings.
  rows.push(row(SYS_ICON.sun, "亮度", { min: 25, data: `data-sys="panel"` }, panelBright));
  return `${head(m)}<div class="sys" data-system="${esc(m.id)}">${rows.join("")}</div>${d.audio_error ? `<small class="sys-err">${esc(d.audio_error)}</small>` : ""}`;
};
function applyPanelBright() {
  let dim = document.getElementById("dim");
  if (!dim) { dim = document.createElement("div"); dim.id = "dim"; document.body.appendChild(dim); }
  dim.style.opacity = String((100 - panelBright) / 100 * 0.9);
}
applyPanelBright();
const sysSend = {};
function systemAction(module, action, extra) {
  return fetch("/api/action", { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ module, action, ...extra }) }).then(r => r.json()).catch(() => ({}));
}
document.getElementById("grid").addEventListener("pointerdown", e => {
  const pill = e.target.closest(".sys-pill");
  if (!pill || e.target.closest("button") || e.button) return;
  const input = pill.querySelector("input"), card = pill.closest(".card");
  // a tall card stands its bars upright (filled from the bottom, dragged up and down)
  const upright = card.dataset.orient === "tall", box = pill.getBoundingClientRect();
  const along = ev => upright ? -ev.clientY : ev.clientX, length = (upright ? box.height : box.width) || 1;
  const min = +input.min || 0, max = +input.max || 100, start = +input.value, x0 = along(e);
  e.preventDefault();
  try { pill.setPointerCapture(e.pointerId); } catch {}
  card._dragging = true; clearTimeout(card._dragEnd);
  let moved = false;
  const set = v => {
    v = Math.round(Math.max(min, Math.min(max, v)));
    if (v === +input.value) return;
    input.value = v; input.dispatchEvent(new Event("input", { bubbles: true }));
  };
  const move = ev => { if (Math.abs(along(ev) - x0) > 3) moved = true; if (moved) set(start + (along(ev) - x0) / length * (max - min)); };
  const up = ev => {
    pill.removeEventListener("pointermove", move); pill.removeEventListener("pointerup", up); pill.removeEventListener("pointercancel", up);
    if (!moved && ev.type === "pointerup") {   // a tap: go to where it was tapped
      const r = pill.getBoundingClientRect();
      set(min + (upright ? (r.bottom - ev.clientY) / (r.height || 1) : (ev.clientX - r.left) / (r.width || 1)) * (max - min));
    }
    input.dispatchEvent(new Event("change", { bubbles: true }));
    card._dragEnd = setTimeout(() => { card._dragging = false; }, 1500);
  };
  pill.addEventListener("pointermove", move); pill.addEventListener("pointerup", up); pill.addEventListener("pointercancel", up);
});
document.getElementById("grid").addEventListener("input", e => {
  const input = e.target.closest("[data-sys]");
  if (!input) return;
  const card = input.closest(".card"), module = input.closest("[data-system]").dataset.system, v = +input.value;
  card._dragging = true; clearTimeout(card._dragEnd);
  card._dragEnd = setTimeout(() => { card._dragging = false; }, 1500);
  input.closest(".sys-row").querySelector("b").textContent = v;
  input.closest(".sys-row").style.setProperty("--v", v);   // the pill fills as it is dragged
  if (input.dataset.sys === "panel") {
    panelBright = v; applyPanelBright();
    try { localStorage.setItem("deskmon-panel-brightness", v); } catch {}
  } else if (input.dataset.sys === "volume") {  // volume follows the finger (at most ~7 calls/s)
    clearTimeout(sysSend.vol);
    sysSend.vol = setTimeout(() => systemAction(module, "set_volume", { value: v }), 140);
  }
});
document.getElementById("grid").addEventListener("change", e => {
  const input = e.target.closest('[data-sys="brightness"]');  // DDC/CI is slow: send once on release
  if (input) systemAction(input.closest("[data-system]").dataset.system, "set_brightness", { value: +input.value, index: +input.dataset.index });
});
document.getElementById("grid").addEventListener("click", async e => {
  const b = e.target.closest("[data-sys-mute]");
  if (!b) return;
  await systemAction(b.closest("[data-system]").dataset.system, "toggle_mute", {});
  await poll();
});

const COLORS = { codex: "var(--codex)", claude: "var(--claude)" };
const cards = {};
const usageRefresh = new Set(), usageRefreshMessage = new Map();
const grid = document.getElementById("grid");
let state = null;

function render() {
  if (!state) return;
  // Widgets that can hold several cards (AI subscriptions, printers) live in one "viewer" in the layout:
  // a wide one shows two side by side, a narrow one swipes (or mouse wheel) between them.
  const views = {};
  for (const type of MULTI) views[type] = viewer(type);
  for (const m of state.modules) {
    let el = cards[m.id];
    if (!el) {
      el = cards[m.id] = document.createElement("section");
      el.dataset.id = m.id;
      el.className = `card ${m.type}`;
      (MULTI.includes(m.type) ? views[m.type].firstChild : grid).appendChild(el);
    }
    if (m.type === "companion") {
      DeskMonCompanion.update(el, m, { onWait: companionWait });
      continue;
    }
    if (m.type === "clock") { DeskMonClock.update(el, m); continue; }
    if (m.type === "system" && el._dragging) continue;  // don't replace a slider under the finger
    if (m.type === "tokens") {
      const p = m.data.provider || m.id;  // before the first data arrives, fall back to the card id
      el.style.setProperty("--c", COLORS[p] || "var(--accent)");
      if (COLORS[p]) el.classList.add(p);
    }
    if (m.type === 'media') {
      const stable = JSON.stringify({...m, updated: 0, data: {...m.data, sampled: 0, position: 0, progress: 0}});
      if (el._mediaStable === stable) {updateMediaProgress(el, m.data); continue;}
      el._mediaStable = stable;
    }
    if (m.type === 'bambu' && !m.data?.stage && el.querySelector('.printer-preview img')) {
      const label = el.querySelector('.printer-progress-label span');
      if (label) label.textContent = '暫時未連線，保留預覽';
      el._html = null;
      continue;
    }
    const html = (R[m.type] || offline)(m);
    if (el._html !== html) {
      if (m.type === 'bambu') DeskMonPrinterRender.replace(el, html);
      else el.innerHTML = html;
      el._html = html;
    }
  }
  // modules switched off in settings disappear instead of leaving a stale card
  for (const id of Object.keys(cards)) {
    if (!state.modules.some(m => m.id === id)) { cards[id]._companion?.destroy(); cards[id].remove(); delete cards[id]; }
  }
  layoutGrid(views);
}

const MULTI = ["tokens", "bambu"];
function viewer(type) {
  let v = grid.querySelector(`.viewer[data-type="${type}"]`);
  if (v) return v;
  v = document.createElement("div"); v.className = "viewer"; v.dataset.type = type;
  v.innerHTML = '<div class="slot"></div><div class="tv-dots" aria-hidden="true"></div>';
  grid.appendChild(v);
  const slot = v.firstChild;
  slot.addEventListener("wheel", e => {
    if (slot.scrollWidth <= slot.clientWidth + 2 || Math.abs(e.deltaX) > Math.abs(e.deltaY)) return;
    e.preventDefault();
    slot.scrollBy({ left: Math.sign(e.deltaY) * slot.clientWidth, behavior: "smooth" });
  }, { passive: false });
  slot.addEventListener("scroll", () => tokenDots(v), { passive: true });
  return v;
}

function tokenDots(viewer) {
  const slot = viewer.firstChild, dots = viewer.lastChild;
  const pages = Math.max(1, Math.ceil(slot.scrollWidth / Math.max(1, slot.clientWidth) - 0.05));
  const page = Math.round(slot.scrollLeft / Math.max(1, slot.clientWidth));
  const html = pages > 1 ? Array.from({ length: pages }, (_, i) => `<i class="${i === page ? "on" : ""}"></i>`).join("") : "";
  if (dots.innerHTML !== html) dots.innerHTML = html;
}

// after a tap on the face: poll quickly until the companion has answered (max 30 s)
async function companionWait(done) {
  const until = Date.now() + 30000;
  while (Date.now() < until) {
    await new Promise(r => setTimeout(r, 600));
    await poll();
    if (done()) return;
  }
}

function updateMediaProgress(el, data) {
  if (!data.title) return;
  const position = Math.max(0, Math.min(data.duration || Infinity, data.position + (data.playing ? Date.now() / 1000 - data.sampled : 0)));
  const bar = el.querySelector('.m-bar > div');
  if (bar) bar.style.width = (data.duration ? Math.min(100, position / data.duration * 100) : 0) + '%';
  const elapsed = el.querySelector('.m-time > span');
  if (elapsed) elapsed.textContent = mmss(position);
  const remaining = el.querySelector('.m-pct');
  if (remaining) remaining.textContent = '-' + mmss(Math.max(0, data.duration - position));
}

// Fill the screen with whatever cards are enabled, so no empty holes are left.
function layoutGrid(views) {
  const L = DeskMonLayout, types = new Set(state.modules.map(m => m.type));
  const present = L.WIDGETS.filter(w => types.has(w));
  const mode = currentMode();
  drawModeChip(mode);
  // while the pencil editor is open the panel shows the layout being edited (holes stay empty)
  const items = window.DeskMonPanelEdit?.items() || L.place(L.layoutFor(state.display, mode), present, false);  // gaps stay gaps
  const placed = new Set(items.map(i => i.id));
  const key = JSON.stringify(items);
  // the layout changed (mode switch, editor, a card switched on): cards spring from where they were
  const moving = key !== layoutGrid.key && layoutGrid.key && document.documentElement.dataset.motion !== "off"
    ? [...grid.querySelectorAll(":scope > .card, :scope > .viewer")].filter(el => el.offsetParent).map(el => [el, el.getBoundingClientRect()]) : [];
  // what a card shows depends on its real shape: a column is wider on a wide screen and narrower on a 4:3 one
  // (fit "auto"), and a larger text size leaves fewer text lines per row. Measured in rows of text ("u").
  const shape = L.calculate(innerWidth, innerHeight, layoutDisplay);
  const colUnits = shape.aspect * L.ROWS / L.COLS, ts = shape.textScale;
  const sizeOf = (w, h) => L.cardSize(w / ts, h / ts, colUnits);
  grid.style.gridTemplateColumns = `repeat(${L.COLS}, minmax(0, 1fr))`;
  grid.style.gridTemplateRows = `repeat(${L.ROWS}, minmax(0, 1fr))`;
  grid.style.gridTemplateAreas = "none";
  for (const it of items) {
    const els = views[it.id] ? [views[it.id]] : state.modules.filter(m => m.type === it.id).map(m => cards[m.id]).filter(Boolean);
    for (const el of els) {
      el.style.gridColumn = `${it.x + 1} / span ${it.w}`;
      el.style.gridRow = `${it.y + 1} / span ${it.h}`;
      el.dataset.w = it.w; el.dataset.h = it.h;
      const sz = sizeOf(it.w, it.h);          // docs/LAYOUT.md: what a card shows follows its level and direction
      el.dataset.size = sz.size; el.dataset.orient = sz.orient;
    }
  }
  cardButtons(items);
  for (const [el, a] of moving) {
    const b = el.getBoundingClientRect();
    if (!b.width || (Math.abs(a.left - b.left) < 1 && Math.abs(a.top - b.top) < 1 && Math.abs(a.width - b.width) < 1 && Math.abs(a.height - b.height) < 1)) continue;
    el.animate([{ transform: `translate(${a.left - b.left}px, ${a.top - b.top}px) scale(${a.width / b.width}, ${a.height / b.height})`, transformOrigin: "0 0" },
      { transform: "none", transformOrigin: "0 0" }], { duration: 460, easing: getComputedStyle(document.documentElement).getPropertyValue("--spring").trim() || "ease-out" });
  }
  // a clock card on the panel replaces the small time and date in the header
  document.body.classList.toggle("has-clock", placed.has("clock"));
  // widgets put away in the drawer keep running but get no card
  for (const m of state.modules) if (!views[m.type] && cards[m.id]) cards[m.id].style.display = placed.has(m.type) ? "" : "none";
  for (const [type, v] of Object.entries(views)) {
    const mine = state.modules.filter(m => m.type === type && cards[m.id]);
    v.hidden = !mine.length || !placed.has(type);
    // a wide viewer shows two cards side by side, a narrow one shows one card per page; each card is sized by its share
    const it = items.find(i => i.id === type);
    const per = Math.min(mine.length || 1, it && it.w >= 4 ? 2 : 1);
    v.firstChild.style.setProperty("--per", per);
    if (it) for (const m of mine) { const sz = sizeOf(it.w / per, it.h); cards[m.id].dataset.size = sz.size; cards[m.id].dataset.orient = sz.orient; }
  }
  // one row, times the text size setting: that setting makes the canvas smaller (so everything on it is drawn
  // larger), which also makes a row smaller; without this the card type, sized from the row, would not change
  grid.style.setProperty("--u", (grid.clientHeight + (parseFloat(getComputedStyle(grid).rowGap) || 0)) / L.ROWS * ts + "px");
  companionPop();
  if (key !== layoutGrid.key) { layoutGrid.key = key; for (const v of Object.values(views)) v.firstChild.scrollLeft = 0; }
  for (const v of Object.values(views)) tokenDots(v);
  grid.dataset.cards = present.join(" ");
  const empty = !items.length && !document.body.classList.contains("editing");
  if (empty && !grid.querySelector(".all-off")) {
    grid.insertAdjacentHTML("beforeend", `<div class="all-off">${ICON.gear}<b>畫面上沒有小工具</b><span>點左上角的鉛筆，從小工具抽屜拖出來</span></div>`);
  } else if (!empty) grid.querySelector(".all-off")?.remove();
}

// A small Agent card shows only the face; what it says pops up beside the card while it is said and a few
// seconds after, then goes away. Touching anything else closes it at once (companion.js dismiss()).
const POP_AFTER_MS = 6000;
function companionPop() {
  const m = state.modules.find(x => x.type === "companion"), el = m && cards[m.id], cp = el?._companion;
  let pop = document.getElementById("cp-pop");
  const small = el && el.style.display !== "none" && (el.dataset.size === "xs" || (el.dataset.size === "s" && el.dataset.orient !== "wide"));
  // The pop-up over the other cards is only for what was asked for (a tap) or really matters (a print done
  // or failed, the timer); smaller remarks stay inside the card. Never in the settings page's preview.
  const loud = ["tap", "print_finished", "print_failed", "timer_done"].includes(m?.data?.event) && !window.frameElement;
  if (cp?.speaking && loud) el._popUntil = Date.now() + POP_AFTER_MS;
  if (!loud && el) el._popUntil = 0;
  const bubble = small && Date.now() < (el._popUntil || 0) ? el.querySelector(".cp-bubble:not(.idle) .cp-line") : null;
  const text = bubble ? bubble.textContent.trim() : "";
  if (!text || document.body.classList.contains("editing")) { pop?.remove(); return; }
  const host = el.offsetParent || grid;
  if (!pop) { pop = document.createElement("div"); pop.id = "cp-pop"; pop.setAttribute("aria-hidden", "true"); }  // the card's live region reads it
  if (pop.parentElement !== host) host.appendChild(pop);
  if (pop.textContent !== text) pop.textContent = text;
  const below = el.offsetTop < host.clientHeight / 2, w = pop.offsetWidth, h = pop.offsetHeight;
  pop.dataset.at = below ? "below" : "above";
  pop.style.left = Math.max(8, Math.min(host.clientWidth - w - 8, el.offsetLeft + el.offsetWidth / 2 - w / 2)) + "px";
  pop.style.top = (below ? el.offsetTop + el.offsetHeight + 8 : el.offsetTop - h - 8) + "px";
}
addEventListener("pointerdown", () => document.getElementById("cp-pop")?.remove(), true);

// ---------- context modes (專注 / 列印 / 休息): the chip in the header swaps the whole layout ----------
const PRINTING = ["RUNNING", "PREPARE", "PAUSE"];
let modeOverride = null, modePrinting = null;
function currentMode() {
  const printing = state.modules.some(m => m.type === "bambu" && PRINTING.includes(m.data?.stage));
  if (printing !== modePrinting) { modePrinting = printing; modeOverride = null; }  // a manual pick lasts until the printer starts/stops
  return DeskMonLayout.effectiveMode(state.display, printing, modeOverride);
}
function drawModeChip(mode) {
  const chip = document.getElementById("mode");
  if (!chip) return;
  const label = DeskMonLayout.MODES[mode]?.label || "自訂";
  const auto = state.display?.auto_mode && modePrinting && modeOverride == null;
  const text = auto ? `${label} · 自動` : label;
  if (chip.textContent !== text) chip.textContent = text;
  chip.classList.toggle("on", !!mode);
  chip.title = "切換情境模式：自訂 → 專注 → 列印 → 休息";
}
document.getElementById("mode")?.addEventListener("click", async () => {
  if (!state || document.body.classList.contains("editing")) return;
  const order = DeskMonLayout.MODE_ORDER, next = order[(order.indexOf(currentMode()) + 1) % order.length];
  if (state.display?.auto_mode && modePrinting) { modeOverride = next; applyLook(); render(); return; }  // auto is in charge: override for now
  state.display = { ...state.display, mode: next };
  applyLook(); render();
  try {
    await fetch("/api/display", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ mode: next }) });
  } catch { /* the next poll shows what the server kept */ }
});

// ---------- event toasts: what the event centre recorded and the Companion didn't say ----------
const EVENT_TEXT = {
  print_finished: d => `${d.file ? d.file + " " : ""}印好了`,
  print_failed: d => d.reason === "stopped" ? "列印停止了" : "列印出問題了，去看一下",
  quota_high: d => `${d.title || "AI"} ${({ "5h": "5 小時", "7d": "7 天" })[d.window] || ""}額度 ${d.used_percent ?? "偏高"}%`,
  long_work: d => `已經連續工作 ${d.minutes ?? "很久"} 分鐘，休息一下`,
  timer_done: () => "計時結束，時間到了",
  rain_soon: d => `${d.in_hours <= 1 ? "一小時內" : `約 ${d.in_hours ?? "幾"} 小時後`}可能下雨`,
};
let eventSeen = null;
const eventShown = new Set();
function eventToasts() {
  const events = state.events || [];
  const newest = events.reduce((n, e) => Math.max(n, e.id), 0);
  if (eventSeen == null) { eventSeen = newest; return; }  // what happened before this page opened isn't news
  if (state.display?.toasts === false) { eventSeen = newest; return; }
  const companionShown = !!cards[state.modules.find(m => m.type === "companion")?.id]?.offsetParent;
  for (const e of events) {
    if (e.id <= eventSeen || eventShown.has(e.id) || !EVENT_TEXT[e.name]) continue;
    if (Date.now() / 1000 - e.ts < 1.5) continue;  // give the Companion a moment to take it
    eventShown.add(e.id);
    if (companionShown && ["queued", "spoken"].includes(e.outcome)) continue;  // the character says it
    if (Date.now() / 1000 - e.ts > 60) continue;
    showEventToast(e);
  }
  if (events.length && events.every(e => e.id <= eventSeen || eventShown.has(e.id) || !EVENT_TEXT[e.name])) eventSeen = newest;
}
function showEventToast(e) {
  const box = document.getElementById("toasts");
  const t = document.createElement("div");
  t.className = `ev-toast ev-${e.name}`; t.setAttribute("role", "status");
  t.innerHTML = `<b>${esc(e.label)}${e.simulated ? " · 測試" : ""}</b><span>${esc(EVENT_TEXT[e.name](e.detail || {}))}</span>`;
  t.addEventListener("click", () => t.remove());
  box.appendChild(t);
  while (box.children.length > 3) box.firstChild.remove();
  setTimeout(() => t.remove(), 9000);
}

// cards without a title row (Agent, clock) get their settings button over the card's corner
function cardButtons(items) {
  const want = items.filter(i => i.id === "companion" || i.id === "clock");
  for (const b of grid.querySelectorAll(":scope > .card-cfg")) if (!want.some(i => i.id === b.dataset.w)) b.remove();
  for (const it of want) {
    let b = grid.querySelector(`:scope > .card-cfg[data-w="${it.id}"]`);
    if (!b) {
      b = document.createElement("a");
      b.className = "card-cfg"; b.dataset.w = it.id; b.href = `/settings.html?w=${it.id}`;
      b.setAttribute("aria-label", "設定"); b.innerHTML = document.getElementById("gear").innerHTML;
      grid.appendChild(b);
    }
    b.style.gridColumn = `${it.x + 1} / span ${it.w}`;
    b.style.gridRow = `${it.y + 1} / span ${it.h}`;
  }
}

async function poll() {
  try {
    state = await (await fetch("/api/state", { cache: "no-store" })).json();
    // Mondesk was updated/restarted with new files: reload so this page isn't outdated
    poll.build ??= state.build;
    if (state.build && state.build !== poll.build && !window.frameElement) { location.reload(); return; }
    if (previewCfg) Object.assign(state, previewCfg);  // settings page: show unsaved edits
    document.body.classList.toggle("demo", !!state.demo);
    applyLook();
    render();
    if (!window.frameElement) eventToasts();
  } catch { /* server restarting; keep last frame */ }
}

// layout + theme from state (or from the settings page's live preview)
function applyLook() {
  const display = state.display || {};
  const requested = +new URLSearchParams(location.search).get("panel");
  layoutDisplay = requested > 0 ? {...display, width: 640 * requested, height: 640, fit: "contain"} : display;
  const key = JSON.stringify(layoutDisplay);
  if (key !== applyLook.lastLayout) { applyLook.lastLayout = key; fit(); }
  watchCover();
  const now = { mode: currentMode(), hour: new Date().getHours(), cover: coverColor };
  const tk = JSON.stringify([state.theme || {}, now]);
  if (tk !== applyTheme.last) { applyTheme.last = tk; applyTheme(state.theme, now); }
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


// Paints the theme. Every colour on the panel is a CSS variable set here from DeskMonLayout.resolveTheme():
// one theme colour, cards with their own colour get --c-<type> (see the :root block in style.css).
function applyTheme(t = {}, now = {}) {
  const root = document.documentElement, r = root.style, th = DeskMonLayout.resolveTheme(t, now), s = th.surface;
  for (const k of ["bg", "card", "line", "text", "soft", "dim", "faint", "on", "ok", "idle", "err", "warn"]) r.setProperty(`--${k}`, s[k]);
  root.dataset.shape = th.shape;
  root.dataset.motion = th.motion;
  root.dataset.style = th.style;
  let wall = document.getElementById("wall");
  if (th.image) {
    if (!wall) { wall = document.createElement("div"); wall.id = "wall"; document.body.prepend(wall); }
    r.setProperty("--wall-url", `url("/api/background?v=${th.image.v}")`);
    r.setProperty("--wall-dim", th.image.dim / 100);
    r.setProperty("--wall-blur", th.image.blur + "px");
  } else wall?.remove();
  root.dataset.wall = th.image ? "1" : "";
  root.dataset.light = s.light ? "1" : "";
  r.setProperty("--theme", th.accent);
  for (const [k, n] of Object.entries(DeskMonLayout.CARD_COLORS)) {
    if (n !== 1) continue;
    th.shown[k] ? r.setProperty(`--c-${k}`, th.shown[k]) : r.removeProperty(`--c-${k}`);
  }
  r.setProperty("--music", th.colors.media);
  for (const k of ["codex", "claude"]) { r.setProperty(`--${k}`, th.colors[k][0]); r.setProperty(`--${k}-2`, th.colors[k][1]); }
}

// colour of the album cover (for themes that follow it): read once per cover, null when it can't be read
let coverColor = null, coverUrl = "";
function watchCover() {
  const m = state.modules.find(x => x.type === "media");
  const url = m && state.theme?.cover ? (m.data?.art_url || (m.data?.art ? `/api/asset/${m.id}/art?v=${m.data.art}` : "")) : "";
  if (url === coverUrl) return;
  coverUrl = url; coverColor = null;
  if (!url) return;
  const img = new Image();
  img.crossOrigin = "anonymous";
  img.onload = () => {
    if (url !== coverUrl) return;
    try {
      const c = document.createElement("canvas"); c.width = c.height = 24;
      const g = c.getContext("2d", { willReadFrequently: true });
      g.drawImage(img, 0, 0, 24, 24);
      coverColor = DeskMonLayout.pictureColor(g.getImageData(0, 0, 24, 24).data);
      applyLook();
    } catch { /* a cover from another site without permission to read it: keep the theme colour */ }
  };
  img.src = url;
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
  const refresh = e.target.closest('[data-usage-refresh]');
  if (refresh) {
    const module = refresh.dataset.usageRefresh;
    if (usageRefresh.has(module)) return;
    usageRefresh.add(module); usageRefreshMessage.delete(module); render();
    try {
      const response = await fetch('/api/action', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({module, action:'refresh'})});
      const result = await response.json();
      if (!response.ok || !result.ok) throw Error(result.error || '查詢失敗');
      usageRefreshMessage.set(module, '已更新');
    } catch (error) {usageRefreshMessage.set(module, error.message.replace(/^RuntimeError: /, ''));}
    finally {usageRefresh.delete(module); await poll(); render();}
    return;
  }
  const btn = e.target.closest("[data-act]");
  if (!btn) {
    const card = e.target.closest(".card.media");
    if (card) await openMedia(card.dataset.id);
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
    const response = await fetch("/api/action", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ module, action: btn.dataset.act, track: mod?.data.track }) });
    const result = await response.json();
    if (!response.ok || !result.ok) throw Error(result.error || '播放器未接受操作');
  } catch (error) {
    const notice = document.createElement('div'); notice.className = 'printer-notice'; notice.setAttribute('role', 'alert'); notice.textContent = error.message;
    document.body.append(notice); setTimeout(() => notice.remove(), 6000);
  } finally { setTimeout(poll, 400); }
});

async function openMedia(id) {
  const media = state?.modules.find(m => m.id === id);
  const route = DeskMonMediaRoute.resolve(media?.data);
  if (route.kind === 'lyrics') {openLyrics(id); return;}
  if (route.kind === 'unavailable') {
    openLyrics(id); return;
  }
  openVideo(id);
}
grid.addEventListener('keydown', e => {
  if ((e.key === 'Enter' || e.key === ' ') && e.target.matches('.m-top')) {e.preventDefault(); void openMedia(e.target.closest('.card.media').dataset.id);}
});

addEventListener("resize", fit);
// Full-screen button (top right), shown only while the page is not full screen and is not the settings preview.
// In the Mondesk application the window itself goes full screen (and remembers it); in a browser, the page does.
const FS = document.getElementById("fs");
let shell = null;   // /api/desktop: { app, window, fullscreen, ... } when running inside the application
const inApp = () => !!(shell?.app && shell.window);
function isFullScreen() {
  if (inApp()) return !!shell.fullscreen;
  return !!document.fullscreenElement || matchMedia("(display-mode: fullscreen)").matches
    || (innerWidth >= screen.width - 2 && innerHeight >= screen.height - 2);   // F11 / kiosk
}
function showFullScreenButton() { FS.hidden = !!window.frameElement || (!inApp() && !document.documentElement.requestFullscreen) || isFullScreen(); }
async function setFullScreen(on) {
  if (!inApp()) return on ? document.documentElement.requestFullscreen({ navigationUI: "hide" }).catch(() => {}) : document.exitFullscreen?.().catch(() => {});
  try {
    shell = await (await fetch("/api/desktop", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ fullscreen: on }) })).json();
  } catch { /* the application is closing */ }
  showFullScreenButton();
}
FS.addEventListener("click", () => setFullScreen(true));
// Esc leaves full screen in the application (a browser does that by itself), unless a page on top wants the key
document.addEventListener("keydown", e => {
  if (e.key === "Escape" && inApp() && shell.fullscreen && LY.hidden && !document.getElementById("ckfull")) setFullScreen(false);
});
addEventListener("resize", showFullScreenButton);
document.addEventListener("fullscreenchange", showFullScreenButton);
showFullScreenButton();
fetch("/api/desktop").then(r => r.json()).then(d => { shell = d; showFullScreenButton(); }).catch(() => {});
fit(); tick(); poll();
setInterval(tick, 1000);
setInterval(poll, 2000);

// ---------- fullscreen lyrics (tap the music card) ----------
const LY = document.getElementById("lyrics");
// ---------- fullscreen video: mirrors the playing tab (same page and logic as lyrics) ----------
// The browser tab keeps playing with its sound; the extension sends frames only while this
// view is open, and Mondesk relays them as an MJPEG stream (like the printer camera).
const VIDEO = LY.querySelector('.ly-video'), VIDEO_MSG = LY.querySelector('.ly-video-msg');
// YouTube and Bilibili: the panel plays the same video muted and follows the tab's position, so it
// keeps working while the tab's window is covered/minimised (Chrome stops drawing hidden windows,
// which rules out copying frames there). Sites the panel has no player for, or videos that refuse
// embedding, fall back to the frame mirror (needs the tab's window to be visible).
const SYNC_HOST = Object.assign(document.createElement('div'), {className: 'ly-yt', hidden: true});
LY.insertBefore(SYNC_HOST, VIDEO);
const synced = new DeskMonVideoSync.AnyVideo(SYNC_HOST);
const MIRROR_MSG = {
  hidden: 'Chrome 看不到影片分頁（分頁在背景、視窗縮小，或整個被其他視窗蓋住），畫面暫停。讓影片視窗露出來就會恢復。',
  blocked: '這個網站不允許擷取影片畫面（例如有版權保護的影片）。',
  waiting: '正在等待影片畫面…',
};
// The video page has only our own controls: play / pause, the progress bar and the volume of that video.
// YouTube's own overlays (title link, "more videos", the next-video card) appear whenever its player is
// paused; they can't be clicked here and aren't wanted, so while the video is not playing the embedded
// player is covered by the video's still picture.
const CTL = LY.querySelector('.ly-ctl'), PLAY = CTL.querySelector('.ly-play'), VOL = CTL.querySelector('.ly-vol input');
const PLAY_ICON = { play: '<svg viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg>', pause: '<svg viewBox="0 0 24 24"><path d="M7 5h4v14H7zM13 5h4v14h-4z"/></svg>' };
function mediaAction(action, extra = {}) {
  const m = state?.modules.find(x => x.id === ly.id);
  if (!m) return Promise.resolve({ ok: false });
  return fetch('/api/action', { method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ module: m.id, action, track: m.data.track, ...extra }) }).then(r => r.json()).catch(() => ({ ok: false }));
}
// Play / pause is shown the moment it is pressed. The tab itself stops at once too, but Chrome lets a
// background tab report late (seconds), so until its report agrees (or 10 s pass) the panel goes by what
// was pressed: picture, button and clock stop or start immediately.
PLAY.addEventListener('click', e => {
  e.stopPropagation();
  const m = state?.modules.find(x => x.id === ly.id);
  if (!m) return;
  const now = expected(m.data);
  ly.expect = { track: m.data.track, playing: !now.playing, position: now.position, at: Date.now() };
  tickVideo();
  mediaAction('toggle').then(r => { if (!r.ok) { ly.expect = null; tickVideo(); } });
});
// the media state as the panel should show it right now
function expected(d) {
  const position = d.playing ? d.position + (Date.now() / 1000 - d.sampled) : d.position;
  const x = ly.expect;
  if (!x) return { ...d, position };
  if (x.track !== d.track || Date.now() - x.at > 10000 || (d.playing === x.playing && Date.now() - x.at > 600)) { ly.expect = null; return { ...d, position }; }
  return { ...d, playing: x.playing, position: x.playing ? x.position + (Date.now() - x.at) / 1000 : x.position };
}
// The controls go away after a few seconds without a touch and come back on any touch or mouse move;
// they stay while the video is paused or a bar is being dragged.
const CTL_IDLE_MS = 3500;
let ctlSeen = Date.now();
function wakeControls() { ctlSeen = Date.now(); LY.classList.remove('ctl-idle'); }
for (const ev of ['pointermove', 'pointerdown', 'keydown']) LY.addEventListener(ev, wakeControls, { passive: true });
let volTimer, volHold = 0;
VOL.addEventListener('input', e => {
  e.stopPropagation();
  volHold = Date.now() + 2500;               // what the tab reports is ignored while the bar is being moved
  VOL.closest('.ly-vol').style.setProperty('--v', VOL.value);
  clearTimeout(volTimer);
  volTimer = setTimeout(() => mediaAction('volume', { value: +VOL.value }), 120);
});
CTL.addEventListener('click', e => e.stopPropagation());
function drawVideoControls(d, pos) {
  CTL.hidden = false;
  const icon = d.playing ? 'pause' : 'play';
  if (PLAY.dataset.icon !== icon) { PLAY.dataset.icon = icon; PLAY.innerHTML = PLAY_ICON[icon]; PLAY.setAttribute('aria-label', d.playing ? '暫停' : '播放'); }
  PLAY.disabled = !d.browser_bridge;
  LY.classList.toggle('ctl-idle', d.playing && !d.ad && ly.preview == null && Date.now() > volHold && Date.now() - ctlSeen > CTL_IDLE_MS);
  CTL.querySelector('.ly-time').textContent = d.duration > 0 ? `${mmss(pos)} / ${mmss(d.duration)}` : '';
  const has = typeof d.volume === 'number';   // older extension builds don't report it: no bar until it is reloaded
  CTL.querySelector('.ly-vol').hidden = !has;
  if (has && Date.now() > volHold) { VOL.value = d.volume; VOL.closest('.ly-vol').style.setProperty('--v', d.volume); }
  CTL.querySelector('.ly-vol').classList.toggle('muted', has && +VOL.value === 0);
  // not playing: cover the embedded player with the still picture so none of YouTube's overlays show
  // ...and keep it covered until its picture is really the tab's picture again. After a short pause the
  // embedded player was left running (see tickVideo), so that is at once; after a long one it was truly
  // paused, and YouTube keeps its cards up for about three seconds after playback resumes.
  const stepping = d.playing && !d.ad && synced.inStep(pos);
  if (stepping) drawVideoControls.since ??= Date.now(); else drawVideoControls.since = null;
  const wait = synced.pausedAt && Date.now() - synced.pausedAt < 15000 ? 3600 : 250;
  const held = !d.playing || !!d.ad || (!!synced.id && !(drawVideoControls.since && Date.now() - drawVideoControls.since > wait));
  SYNC_HOST.classList.toggle('held', held);
  SYNC_HOST.classList.toggle('paused', !d.playing && !d.ad);
  SYNC_HOST.style.setProperty('--poster', d.art_url ? `url("${String(d.art_url).replace(/["\\)]/g, '')}")` : 'none');
}
function openVideo(id) {
  ly.id = id; ly.track = null; ly.request++; ly.expect = null; wakeControls();
  LY.classList.add('video-mode'); LY.hidden = false;
  tickVideo();
}
function stopMirror() {
  VIDEO.removeAttribute('src'); VIDEO.hidden = true; VIDEO.dataset.track = '';
}
function stopVideo() {
  LY.classList.remove('video-mode');
  CTL.hidden = true;
  stopMirror(); synced.close();
  VIDEO_MSG.hidden = true;
}
const GONE_CLOSE_MS = 20000;  // a video page whose source vanished closes itself after this long
function tickVideo() {
  const m = state?.modules.find(x => x.id === ly.id);
  if (!state) return;
  if (!m?.data.title) {
    // tab closed / extension gone: stop the embedded player and the frame stream right away
    // (they would keep playing and capturing for nobody), then close the page
    synced.close(); stopMirror();
    ly.goneAt ??= Date.now();
    VIDEO_MSG.textContent = '播放來源中斷了（分頁關閉或擴充功能斷線），稍後自動關閉。'; VIDEO_MSG.hidden = false;
    if (Date.now() - ly.goneAt > GONE_CLOSE_MS) void closeMediaPage();
    return;
  }
  ly.goneAt = null;
  const d = expected(m.data);   // what was just pressed counts before the tab reports it
  // the source switched back to music (e.g. Apple Music): show lyrics like a normal tap
  if (DeskMonMediaRoute.follow('video', d) === 'lyrics') { stopVideo(); openLyrics(ly.id); return; }
  if (ly.track !== d.track) {
    ly.track = d.track;
    LY.querySelector('.ly-title').textContent = d.title || '';
    LY.querySelector('.ly-artist').textContent = d.artist || d.source || '';
  }
  const pos = ly.preview != null ? ly.preview : d.position;
  LY.querySelector('.ly-bar div').style.width = d.duration > 0 ? Math.max(0, Math.min(100, pos / d.duration * 100)) + '%' : '0';
  updateSeekSlider(d, pos, d.ad);
  drawVideoControls(d, pos);
  showExtensionNotice(d);
  let message;
  if (DeskMonMediaRoute.videoPath(d, synced.failed) === 'sync') {
    stopMirror();  // no frame capture needed: the extension stops copying frames
    synced.show(d.track, pos);
    // a pause shorter than a minute leaves the embedded player running under the cover (clean, instant resume)
    if (d.playing) tickVideo.pausedSince = null; else tickVideo.pausedSince ??= Date.now();
    synced.sync(pos, d.playing, d.ad, !d.playing && !d.ad && Date.now() - tickVideo.pausedSince < 60000);
    message = d.ad ? '原分頁正在播廣告，廣告結束後會繼續同步。' : synced.ready ? '' : '正在載入影片…';
  } else {
    synced.close();
    if (VIDEO.dataset.track !== d.track) {
      // (re)connect the frame stream; the server keeps only frames of the current track
      VIDEO.dataset.track = d.track; VIDEO.hidden = true;
      VIDEO.src = `/api/stream/${encodeURIComponent(ly.id)}?t=${Date.now()}`;
    }
    message = d.mirror ? MIRROR_MSG[d.mirror] : VIDEO.naturalWidth ? '' : MIRROR_MSG.waiting;
    VIDEO.classList.toggle('stale', d.mirror === 'hidden');
  }
  VIDEO_MSG.textContent = message; VIDEO_MSG.hidden = !message;
}
VIDEO.addEventListener('load', () => { VIDEO.hidden = false; });  // first MJPEG part arrived

async function closeMediaPage() {
  ly.preview = null; ly.scrubTrack = null; ly.goneAt = null;
  LY.hidden = true; ly.id = null; ly.request++;
  stopVideo();  // dropping the stream stops the extension from sending frames
}
document.addEventListener('keydown', event => {
  if (!LY.hidden && (event.key === 'Escape' || ['Enter', ' '].includes(event.key) && event.target.matches('.ly-close'))) {event.preventDefault(); void closeMediaPage();}
});
const ly = { id: null, track: null, lines: null, plain: null, state: null, active: -1, seeking: false, revision: null, request: 0 };
const lyricSlider = LY.querySelector('.ly-seek');
lyricSlider.addEventListener('input', () => {
  if (ly.seeking) return;
  ly.scrubTrack = ly.track;
  ly.preview = Number(lyricSlider.value);
  ly.active = -2;
  tickLyrics();
});
lyricSlider.addEventListener('pointercancel', () => {ly.preview = null; ly.scrubTrack = null; ly.active = -2; tickLyrics();});
lyricSlider.addEventListener('change', async () => {
  if (ly.preview == null || ly.seeking) return;
  const position = ly.preview, track = ly.scrubTrack, id = ly.id;
  ly.seeking = true; lyricSlider.disabled = true;
  try {
    const response = await fetch('/api/action', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({module:id, action:'seek_time', track, position})});
    const result = await response.json();
    if (!response.ok || !result.ok) throw Error(result.error || '跳轉失敗');
    if (ly.id === id && ly.track === track) {
      const m = state.modules.find(x => x.id === id); if (m) m.data = result.result;
    }
  } catch (error) {
    if (ly.id === id && !LY.hidden) {
      const notice = document.createElement('div'); notice.className = 'ly-error'; notice.setAttribute('role', 'status'); notice.textContent = error.message;
      LY.appendChild(notice); setTimeout(() => notice.remove(), 5000);
    }
  } finally {ly.seeking = false; ly.preview = null; ly.scrubTrack = null; ly.active = -2; await poll(); tickLyrics();}
});

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
  if(e.target.closest(".ly-close")){await closeMediaPage();}
});

// The progress bar works for every browser source (Apple Music, YouTube, other video tabs):
// the extension moves the real player, the panel then follows the reported position.
function updateSeekSlider(d, pos, blocked = false) {
  const slider = LY.querySelector('.ly-seek');
  if (ly.scrubTrack && ly.scrubTrack !== d.track) {ly.preview = null; ly.scrubTrack = null;}
  slider.disabled = !d.browser_bridge || !(d.duration > 0) || ly.seeking || blocked;
  slider.max = d.duration || 1;
  if (ly.preview == null) slider.value = Math.min(d.duration || 0, pos);
  slider.setAttribute('aria-valuetext', `${mmss(Number(slider.value))} / ${mmss(d.duration)}`);
}
// Chrome keeps running the copy of the extension it loaded; after a Mondesk update it has to
// be reloaded once on chrome://extensions, or new features (seeking videos…) silently fail.
function showExtensionNotice(d) {
  let note = LY.querySelector('.ly-ext');
  if (!d.ext_outdated) { if (note) note.hidden = true; return; }
  if (!note) {
    note = Object.assign(document.createElement('div'), {className: 'ly-ext', role: 'status'});
    LY.appendChild(note);
  }
  note.textContent = `Chrome 裡的 Mondesk 擴充功能是舊版（${d.ext || '未知'}，最新 ${d.ext_expected}）：到 chrome://extensions 按 Mondesk 的「重新載入」，再重新整理影片／Apple Music 分頁。`;
  note.hidden = false;
}

function nowPos() {
  if (ly.preview != null) return ly.preview;
  const d = state.modules.find(x => x.id === ly.id)?.data || {};
  return d.playing ? d.position + (Date.now() / 1000 - d.sampled) : d.position;
}

async function loadLyrics(m) {
  const request = ++ly.request, moduleID = ly.id;
  if(ly.track!==m.data.track)resetLyricScroll();
  ly.track = m.data.track; ly.lines = ly.plain = null; ly.active = -1; ly.state = m.data.lyrics;
  ly.revision = m.data.lyrics_revision;
  updateLyricMetadata(m);
  const box = LY.querySelector(".ly-lines");
  ly.bridge = !!m.data.browser_bridge;
  if (m.data.lyrics !== "ok") {
    // never a blank page: say why there are no lyrics and what to do about it
    const why = !m.data.browser_bridge ? "擴充功能沒有連上，所以讀不到歌詞。到 chrome://extensions 重新載入 Mondesk 之後，要再重新整理 Apple Music 分頁。"
      : m.data.lyrics === "native_missing" ? "還沒讀到歌詞：在 Apple Music 開啟歌詞面板，或換一首歌。" : "這首歌沒有歌詞。";
    box.classList.add("plain");
    box.innerHTML = `<p class="ly-msg">${esc(why)}</p>`;
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
}

function updateLyricMetadata(m) {
  const art = m.data.art_url || (m.data.art ? `/api/asset/${m.id}/art?v=${m.data.art}` : "");
  const signature = JSON.stringify([m.id, m.data.track, m.data.title, m.data.artist, art, m.data.playing, m.data.source]);
  if (ly.metadata === signature) return;
  ly.metadata = signature;
  const image = LY.querySelector('.ly-art');
  if (image.getAttribute('src') !== art) image.src = art;
  image.hidden = !art;
  LY.querySelector('.ly-bg').style.backgroundImage = art ? `url(${JSON.stringify(art)})` : 'none';
  LY.querySelector('.ly-title').textContent = m.data.title || '';
  LY.querySelector('.ly-artist').textContent = [m.data.artist, m.data.source, m.data.playing ? '播放中' : '已暫停'].filter(Boolean).join(' · ');
}

function tickLyrics() {
  if (LY.hidden || !state || LY.classList.contains('video-mode')) return;
  const m = state.modules.find(x => x.id === ly.id);
  if (!m?.data.title) return;
  // a video started while lyrics are up (e.g. YouTube on the main screen): show the video here
  if (DeskMonMediaRoute.follow('lyrics', m.data) === 'video') { ly.preview = null; ly.scrubTrack = null; openVideo(ly.id); return; }
  updateLyricMetadata(m);
  if (m.data.track !== ly.track || m.data.lyrics_revision !== ly.revision || (ly.state !== "ok" && (m.data.lyrics !== ly.state || !!m.data.browser_bridge !== ly.bridge))) loadLyrics(m);
  const d = m.data;
  const pos = nowPos();
  updateSeekSlider(d, pos);
  showExtensionNotice(d);
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
  if(lyricManual && ly.preview == null)return;
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
setInterval(() => (LY.classList.contains('video-mode') ? tickVideo() : tickLyrics()), 200);

// Going to settings: a circle of the page colour grows from the gear that was pressed until it covers the
// screen, then the settings page opens. (Coming back, the settings page does the same from its link.)
addEventListener("click", e => {
  const a = e.target instanceof Element && e.target.closest('a[href^="/settings.html"]');
  if (!a || e.defaultPrevented || e.button || e.metaKey || e.ctrlKey || document.documentElement.dataset.motion === "off") return;
  e.preventDefault();
  const r = a.getBoundingClientRect(), x = r.left + r.width / 2, y = r.top + r.height / 2;
  softWipe(x, y, () => { location.href = a.href; });
});
// a disc of the page colour grows from (x, y) until it covers the screen; soft edge, eased in, no flash
function softWipe(x, y, done) {
  const far = Math.hypot(Math.max(x, innerWidth - x), Math.max(y, innerHeight - y)) + 80;
  const w = document.createElement("div");
  w.className = "wipe";
  w.style.cssText = `left:${x - far}px;top:${y - far}px;width:${far * 2}px;height:${far * 2}px`;
  document.body.appendChild(w);
  const go = () => { if (!go.done) { go.done = true; done(); } };
  w.animate([{ scale: 0, opacity: 0 }, { opacity: 1, offset: .35 }, { scale: 1, opacity: 1 }],
    { duration: 560, easing: "cubic-bezier(.4, 0, .2, 1)", fill: "both" }).finished.then(go);
  setTimeout(go, 900);   // a hidden window never finishes the animation: go anyway
}
addEventListener("pageshow", () => document.querySelectorAll(".wipe").forEach(w => w.remove()));

// Press feedback: whatever is pressed squishes at once and springs back with a few rebounds ("duang") when
// it is let go, even after the quickest tap. Material style adds a ripple from the finger.
const PRESSABLE = ".sys-knob, .m-ctl button, .printer-controls button, .tm-btns button, .usage-refresh-row button, .card-cfg, .sys-ic, #mode, #gear, #pencil, .ev-toast, .cp-face, .card";
function ripple(el) {   // always from the middle of what was pressed (style.css centres it)
  const d = Math.hypot(el.offsetWidth, el.offsetHeight) * 1.05;
  const s = document.createElement("span");
  s.className = "ripple";
  s.style.cssText = `width:${d}px;height:${d}px`;
  el.appendChild(s);
  s.addEventListener("animationend", () => s.remove());
}
addEventListener("pointerdown", e => {
  const root = document.documentElement, motion = root.dataset.motion || "bouncy";
  if (motion === "off" || document.body.classList.contains("editing") || !(e.target instanceof Element)) return;
  if (e.target.closest("input, select, textarea, dialog, #lyrics, .tm-col, .pe-layer, .pe-drawer, .sys-pill input")) return;
  const el = e.target.closest(PRESSABLE);
  if (!el) return;
  const card = el.matches(".card"), material = root.dataset.style === "material";
  const deep = motion === "calm" ? (card ? .99 : .96) : card ? .975 : .92;   // a real surface gives only a little
  if (material) ripple(el);
  el._press?.cancel();
  el.style.transformOrigin = "50% 50%";   // squish and rebound around the middle
  const down = el._press = el.animate([{ scale: 1 }, { scale: deep }], { duration: 90, easing: "ease-out", fill: "forwards" });
  const up = () => {
    removeEventListener("pointerup", up, true); removeEventListener("pointercancel", up, true);
    if (el._press !== down) return;
    down.cancel();
    el._press = el.animate([{ scale: deep }, { scale: 1 }], { duration: motion === "calm" ? 200 : 480,
      easing: getComputedStyle(root).getPropertyValue("--duang").trim() || "ease-out" });
  };
  addEventListener("pointerup", up, true); addEventListener("pointercancel", up, true);
}, true);

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
 const whole=!e.target.closest('button, a, input, dialog')&&e.target.closest('.card.bambu');
 const preview=e.target.closest('[data-camera]')||(whole&&!whole.querySelector('.empty')?whole:null);
 if(preview){cameraId=preview.dataset.camera||preview.dataset.id;printerView.querySelector('p').textContent='正在連接攝影機…';printerView.showModal();refreshCamera()}
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
 if(confirm)confirm.onclick=()=>{const objects=[...skipDialog.querySelectorAll('input:checked:not(:disabled)')].map(c=>+c.value);if(!objects.length)return;skipDialog.close();sendPrinter(id,'skip_objects',{objects,job:d.job_version || d.preview_version})};
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
