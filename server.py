"""Mondesk - modular desk monitor (Windows / Linux / macOS).

python server.py [--port 9361] [--config config.json]
Dashboard: http://127.0.0.1:9361/   Settings: http://127.0.0.1:9361/settings.html
"""
import argparse
import importlib
import json
import threading
import time
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

ROOT = Path(__file__).resolve().parent
WEB = ROOT / "web"
DEMO_TYPES = ("bambu", "media", "tokens", "weather", "system")  # scripted in --demo (modules/demo.py)


# Changes whenever the web files or the server code change; open pages compare it and reload
# themselves, so an always-on desk screen never keeps running an outdated page.
BUILD = str(int(max(p.stat().st_mtime for p in [*WEB.glob("*"), Path(__file__)] if p.is_file())))

SECRET_KEYS = ("access_code", "pair_key", "token", "password", "secret", "api_key")
MASK = "••••••"


def _is_secret(key):
    return any(s in key.lower() for s in SECRET_KEYS)


def mask_secrets(value):
    """Copy of the config with every secret replaced by a mask (sent to the settings page)."""
    if isinstance(value, dict):
        return {k: (MASK if v and _is_secret(k) and isinstance(v, str) else mask_secrets(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [mask_secrets(v) for v in value]
    return value


def restore_secrets(new, old):
    """Settings page sends the mask back for untouched secrets: keep the stored value."""
    if isinstance(new, dict):
        old = old if isinstance(old, dict) else {}
        return {k: (old.get(k) if v == MASK and _is_secret(k) else restore_secrets(v, old.get(k)))
                for k, v in new.items()}
    if isinstance(new, list):
        old = old if isinstance(old, list) else []
        # modules are matched by id so reordering doesn't mix up their secrets
        by_id = {o.get("id"): o for o in old if isinstance(o, dict)}
        return [restore_secrets(v, by_id.get(v.get("id")) if isinstance(v, dict) else None) for v in new]
    return new


class Hub:
    """Loads modules from config, polls each in its own thread, keeps latest state."""

    def __init__(self, config, demo=None, data_dir=None):
        from modules.event_center import EventCenter, EventWatcher
        self.config = config
        self.modules = []
        self.state = {}
        self.lock = threading.Lock()
        self.running = True
        self.demo = demo  # {"started": ts, "speed": 1.0} while every source is scripted (--demo)
        # one event history for the Companion, the panel's toasts and the settings page
        self.events = EventCenter(Path(data_dir) / "events.jsonl" if data_dir else None)
        companion = next((s for s in config.get("modules", []) if s.get("type") == "companion"), {})
        self.watcher = EventWatcher(self, self.events, float(companion.get("quota_threshold") or 80),
                                    int(companion.get("work_minutes") or 120), int(companion.get("break_minutes") or 10))
        for spec in config.get("modules", []):
            if not spec.get("enabled", True):
                continue
            if demo and spec["type"] in DEMO_TYPES:
                from modules import demo as demo_module
                inst = demo_module.Module(spec, demo["started"], demo.get("speed", 1.0))
            else:
                inst = importlib.import_module(f"modules.{spec['type']}").Module(spec)
            inst.hub = self  # lets a module read the others (the companion watches them all)
            self.modules.append(inst)
            self.state[inst.id] = {"id": inst.id, "type": inst.type, "title": inst.title,
                                   "status": "starting", "data": {}}

    def start(self):
        for m in self.modules:
            m.start()
            threading.Thread(target=self._loop, args=(m,), daemon=True).start()
        self.watcher.start()

    def stop(self):
        self.running = False
        self.watcher.stop()
        for m in self.modules:
            try:
                m.stop()
            except Exception:
                pass

    def _loop(self, m):
        while self.running:
            try:
                data = m.poll()
                entry = {"status": data.pop("_status", "ok"), "data": data, "error": None}
            except Exception as e:  # keep the module alive; surface the error to the UI
                entry = {"status": "error", "data": {}, "error": f"{type(e).__name__}: {e}"}
            entry.update(id=m.id, type=m.type, title=m.title, updated=time.time())
            with self.lock:
                self.state[m.id] = entry
            time.sleep(m.interval)

    def action(self, module_id, name, **params):
        m = next((m for m in self.modules if m.id == module_id), None)
        if not m or not hasattr(m, "action"):
            raise KeyError(module_id)
        if name in ("seek", "seek_time") or name == 'refresh' and m.type == 'tokens' or m.type == 'system':
            data = m.action(name, **params)
            entry = {"status":data.pop("_status","ok"),"data":data,"error":None,"id":m.id,"type":m.type,"title":m.title,"updated":time.time()}
            with self.lock: self.state[m.id]=entry
            return data
        return m.action(name, **params)

    def module_states(self):
        """Latest entry of every module. Entries are replaced, never mutated, so shallow
        copies are safe to read from another thread."""
        with self.lock:
            return [dict(self.state[m.id]) for m in self.modules]

    def snapshot(self):
        with self.lock:
            return {"time": time.time(), "build": BUILD, "display": self.config.get("display", {}),
                    "theme": self.config.get("theme", {}), "demo": bool(self.demo),
                    "events": self.events.recent(12),
                    "modules": [self.state[m.id] for m in self.modules]}


class App:
    """Owns the config file and the running Hub; saving settings swaps in a new Hub.

    Demo mode (`demo` = speed): the config is built in memory, every data source is scripted
    and nothing is ever written to the user's settings."""

    def __init__(self, path=None, demo=None):
        self.path = path
        self.hub = None
        self.demo = None
        if demo:
            import tempfile
            from modules.demo import demo_config
            self.data_dir = Path(tempfile.mkdtemp(prefix="deskmon-demo-"))
            self.demo = {"started": time.time(), "speed": float(demo)}
            self.reload(demo_config(self.data_dir))
            return
        try:
            from user_paths import user_data_dir
            # a config given on the command line keeps its own files next to it (tests, portable use)
            self.data_dir = user_data_dir() if path.parent == ROOT else path.parent
        except OSError:
            self.data_dir = None
        self.reload(json.loads(path.read_text(encoding="utf-8")))

    def reload(self, config):
        old, self.hub = self.hub, Hub(config, self.demo, self.data_dir)
        if old:
            old.stop()
        self.hub.start()

    def save(self, config):
        if self.demo:  # the demo may be rearranged, but only for this session
            self.reload({**config, "demo": True})
            return
        if self.path.name == "config.example.json":
            from user_paths import ensure_user_config
            self.path = ensure_user_config(ROOT / 'config.example.json')
        self.path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
        self.reload(config)

    def patch_display(self, changes):
        """Small display changes (the context mode) without restarting every module."""
        allowed = {k: v for k, v in changes.items() if k in ("mode", "auto_mode")}
        if "mode" in allowed and allowed["mode"] not in ("", "focus", "print", "rest"):
            raise ValueError("未知的情境模式")
        if "auto_mode" in allowed:
            allowed["auto_mode"] = bool(allowed["auto_mode"])
        display = {**self.hub.config.get("display", {}), **allowed}
        self.hub.config["display"] = display
        if not self.demo and self.path.name != "config.example.json":
            stored = json.loads(self.path.read_text(encoding="utf-8"))
            stored["display"] = {**stored.get("display", {}), **allowed}
            self.path.write_text(json.dumps(stored, ensure_ascii=False, indent=2), encoding="utf-8")
        return display


MAX_BACKGROUND = 8 * 1024 * 1024
BACKGROUND_TYPES = {"image/png": b"\x89PNG\r\n\x1a\n", "image/jpeg": b"\xff\xd8\xff", "image/webp": b"RIFF", "image/gif": b"GIF8"}


def background_path():
    """The uploaded background picture lives with the user's settings, never in the program folder."""
    from user_paths import user_data_dir
    return user_data_dir() / "background.img"


def background_type(data):
    """Mime type of a picture by its first bytes, or None when it is not a picture we show."""
    for mime, magic in BACKGROUND_TYPES.items():
        if data[:len(magic)] == magic and (mime != "image/webp" or data[8:12] == b"WEBP"):
            return mime
    return None


def save_background(app, data):
    """Store an uploaded picture; returns {"ok", "v"} where v changes with every upload (cache key)."""
    if app.demo:
        return {"ok": False, "error": "示範模式不會儲存檔案；請用一般模式開啟 Mondesk"}
    if not data or len(data) > MAX_BACKGROUND:
        return {"ok": False, "error": "圖片是空的或超過 8 MB"}
    if not background_type(data):
        return {"ok": False, "error": "只接受 PNG、JPEG、WebP 或 GIF 圖片"}
    path = background_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return {"ok": True, "v": format(int(time.time()), "x")}


def delete_background(app):
    if not app.demo:
        background_path().unlink(missing_ok=True)
    return {"ok": True}


def extension_folder(app):
    return Path(app.path).parent / "browser-extension" if app.path else None


def extension_step(app, step, port):
    """The browser extension for Apple Music / YouTube: make the folder Chrome loads, or open it."""
    if app.demo:
        return {"ok": False, "error": "示範模式不會寫入設定；請用一般模式開啟 Mondesk 再設定擴充功能"}
    if not app.path or Path(app.path).name == "config.example.json":
        return {"ok": False, "error": "請先在設定頁按一次「套用」，建立你自己的設定檔"}
    folder = extension_folder(app)
    if step == "prepare":
        from modules.apple_bridge import prepare_extension
        folder = prepare_extension(app.path, port=port)
        key = next((m.get("pair_key") for m in json.loads(Path(app.path).read_text(encoding="utf-8")).get("modules", [])
                    if m.get("type") == "media"), None)
        for m in app.hub.config.get("modules", []):   # the running hub accepts the extension right away
            if m.get("type") == "media" and key:
                m["pair_key"] = key
        return {"ok": True, "folder": str(folder)}
    if step == "open":
        if not folder.is_dir():
            return {"ok": False, "error": "資料夾還沒建立，請先按「準備擴充功能」"}
        import subprocess, sys
        if sys.platform == "win32":
            __import__("os").startfile(folder)
        else:
            try:
                subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", str(folder)])
            except OSError:   # no file manager opener on this system (minimal desktops): show the path instead
                return {"ok": False, "folder": str(folder), "error": f"無法自動開啟資料夾，請手動開啟：{folder}"}
        return {"ok": True, "folder": str(folder)}
    return {"ok": False, "error": "不明的步驟"}


def diagnostics(app):
    """Everything needed to see why something isn't updating, for the settings page."""
    import platform
    import sys
    hub, now = app.hub, time.time()
    states = hub.module_states()
    out = {
        "app": {"build": BUILD, "demo": bool(app.demo), "python": platform.python_version(),
                "platform": f"{platform.system()} {platform.release()}",
                "config": "（示範模式：不讀寫設定檔）" if app.demo else str(app.path),
                "data_dir": str(app.data_dir) if app.data_dir else "", "program_dir": str(ROOT),
                "frozen": bool(getattr(sys, "frozen", False))},
        "modules": [{"id": s["id"], "type": s["type"], "title": s["title"], "status": s["status"],
                     "error": s.get("error"), "message": (s.get("data") or {}).get("message"),
                     "age": round(now - s["updated"], 1) if s.get("updated") else None} for s in states],
        "events": hub.events.recent(40),
        "work_minutes": hub.events.work_minutes,
    }
    media = next((s for s in states if s["type"] == "media"), None)
    if media:
        d = media.get("data") or {}
        info = {"title": d.get("title"), "source": d.get("source"), "playing": d.get("playing"),
                "bridge": bool(d.get("browser_bridge")), "ext": d.get("ext") or "", "ext_expected": d.get("ext_expected") or "",
                "ext_outdated": bool(d.get("ext_outdated")), "video": bool(d.get("video")), "mirror": d.get("mirror") or "",
                "lyrics": d.get("lyrics"), "timeline_estimated": bool(d.get("timeline_estimated")), "message": d.get("message")}
        if not app.demo:
            from modules.apple_bridge import bridge
            with bridge.lock:
                st = bridge.state or {}
                info.update(last_report=round(time.monotonic() - bridge.updated, 1) if bridge.updated else None,
                            lines=len(st.get("lines") or []), plain=len(st.get("plain") or []),
                            watching=time.monotonic() - bridge.viewer_at < 1.5,
                            pending_commands=len(bridge.commands), native=st.get("native_diagnostic") or "",
                            paired=any(m.get("pair_key") for m in hub.config.get("modules", []) if m.get("type") == "media"))
            module = next((m for m in hub.modules if m.id == media["id"]), None)
            if __import__("sys").platform == "win32" and module is not None:
                from modules import media as media_module
                # the fast reader needs a DLL that Windows' app control policy sometimes blocks
                info["os_reader"] = "powershell" if getattr(module, "win", None) is media_module._windows_ps else "winrt"
        out["media"] = info
    out["tokens"] = []
    for s in states:
        if s["type"] != "tokens":
            continue
        d = s.get("data") or {}
        spec = next((m for m in hub.config.get("modules", []) if m.get("id") == s["id"]), {})
        provider = d.get("provider") or s["id"]
        source = ("示範資料" if app.demo else "Codex 本機紀錄裡的額度" if provider == "codex" and d.get("windows")
                  else "Claude 官方用量" if d.get("windows") else "依自訂上限估算" if d.get("budget_5h") or d.get("budget_week")
                  else "只有本機 token 紀錄（沒有百分比）")
        out["tokens"].append({"id": s["id"], "title": s["title"], "source": source, "windows": d.get("windows") or [],
                              "error": d.get("usage_error") or "", "official": bool(spec.get("official_usage")),
                              "last_activity": d.get("last_activity")})
    companion = next((s for s in states if s["type"] == "companion"), None)
    if companion:
        d = companion.get("data") or {}
        out["companion"] = {k: d.get(k) for k in ("provider", "model", "setup", "calls_last_hour", "max_calls_per_hour",
                                                  "fallback_reason", "line", "event_label", "said_at", "via")}
    return out


def make_handler(app):
    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *a, **kw):
            super().__init__(*a, directory=str(WEB), **kw)

        def log_message(self, *a):
            pass

        def end_headers(self):
            if not self.path.startswith("/api/"):
                self.send_header("Cache-Control", "no-cache")  # always pick up UI updates
            super().end_headers()

        # ---- security: only Mondesk's own pages may use the API ----
        # Other websites open in the same browser can send requests to 127.0.0.1. We reject:
        #  * a Host that isn't this machine (DNS-rebinding attacks),
        #  * an Origin / Sec-Fetch-Site that says the request came from another site,
        #  * writes without the X-DeskMon header (a cross-site page can't add it without a
        #    CORS preflight, which this server never approves).
        def _allowed(self, write):
            host = (self.headers.get("Host") or "").rsplit(":", 1)[0].strip("[]").lower()
            port = str(self.server.server_address[1])
            if host not in ("127.0.0.1", "localhost", "::1") and host != app.hub.config.get("host"):
                return False
            origin = self.headers.get("Origin")
            if origin and origin not in {f"http://{h}:{port}" for h in ("127.0.0.1", "localhost", "[::1]")}:
                return False
            if self.headers.get("Sec-Fetch-Site") == "cross-site":
                return False
            return not write or self.headers.get("X-DeskMon") == "1"

        def _client_gone(self):
            """True once the viewer closed the connection. A stream that has no new frame to
            write would otherwise never notice, keep counting as 'watched' and keep the
            camera / browser video capture running for nobody."""
            import select, socket
            try:
                readable, _, _ = select.select([self.connection], [], [], 0)
                return bool(readable) and self.connection.recv(1, socket.MSG_PEEK) == b""
            except OSError:
                return True

        def _deny(self):
            self._json({"ok": False, "error": "已拒絕：只接受 Mondesk 自己頁面的請求"}, 403)

        def _json(self, obj, code=200):
            body = json.dumps(obj, ensure_ascii=False).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            hub = app.hub
            if self.path.startswith("/api/") and not self._allowed(write=False):
                return self._deny()
            if self.path.startswith("/api/state"):
                return self._json(hub.snapshot())
            if self.path.startswith("/api/config"):
                return self._json(mask_secrets(hub.config))  # secrets never leave the server
            if self.path.startswith("/api/desktop"):
                # the application around the pages (desktop.py); a plain server in a browser says app: false
                shell = getattr(app, "desktop", None)
                return self._json(shell.state() if shell else {"app": False})
            if self.path.startswith("/api/displays"):
                from displays import list_displays  # read-only
                return self._json(list_displays())
            if self.path.startswith("/api/diagnostics"):
                return self._json(diagnostics(app))
            if self.path.startswith("/api/background"):
                path = background_path()
                data = path.read_bytes() if path.is_file() else b""
                mime = background_type(data)
                if not mime:
                    return self.send_error(404)
                return self._send(data, mime, [("Cache-Control", "private, max-age=31536000, immutable")])  # ?v= changes per upload
            if self.path.startswith("/api/events"):
                return self._json({"events": hub.events.recent(200)})
            if self.path.startswith("/api/weather/search"):
                from urllib.parse import parse_qs, urlsplit
                from modules import weather
                try:
                    query = (parse_qs(urlsplit(self.path).query).get("q") or [""])[0]
                    return self._json({"ok": True, "places": weather.search(query)})
                except Exception as e:
                    return self._json({"ok": False, "error": "找不到地點，請確認網路後再試", "detail": str(e)[:120]}, 502)
            if self.path.startswith("/api/stream/"):
                # /api/stream/<module>  MJPEG (multipart) live stream, e.g. the printer camera
                mid = self.path[12:].split("?")[0].split("/")[0]
                m = next((m for m in hub.modules if m.id == mid and hasattr(m, "stream_frame")), None)
                if not m:
                    self.send_error(404)
                    return
                self.send_response(200)
                self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                last = None
                try:
                    while app.hub is hub and not self._client_gone():
                        sampled, frame = m.stream_frame()
                        if frame and sampled != last:
                            last = sampled
                            self.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: "
                                             + str(len(frame)).encode() + b"\r\n\r\n" + frame + b"\r\n")
                            self.wfile.flush()
                        time.sleep(0.01)  # new frames go out within ~10 ms (up to ~30 fps sources)
                except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
                    pass  # viewer closed the live view
                return
            if self.path.startswith("/api/companion/"):
                return self._companion_get(self.path.split("?")[0][15:])
            if self.path.startswith("/api/asset/"):
                # /api/asset/<module>/<name>?v=..  binary assets such as album art
                mid, _, name = self.path[11:].split("?")[0].partition("/")
                m = next((m for m in hub.modules if m.id == mid and hasattr(m, "asset")), None)
                got = m.asset(name) if m else None
                if not got:
                    self.send_error(404)
                    return
                body, mime = got
                self.send_response(200)
                self.send_header("Content-Type", mime)
                self.send_header("Cache-Control", "no-store" if name == "camera" else "max-age=3600")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            super().do_GET()

        def _send(self, body, mime, extra=()):
            self.send_response(200)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(body)))
            for k, v in extra:
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)

        def _companion_get(self, rest):
            """Character packs: list, face images (any pack, for previews) and .zip export."""
            from modules import companion_characters as chars
            parts = rest.split("/")
            if parts == ["characters"]:
                return self._json({"characters": chars.list_characters(), "folder": str(chars.user_dir())})
            if len(parts) == 3 and parts[0] == "character":
                got = chars.face_file(parts[1], parts[2])
                if not got:
                    return self.send_error(404)
                # imported SVGs could carry scripts: never let them run on Mondesk's origin
                return self._send(got[0], got[1], [("Cache-Control", "max-age=3600"), ("X-Content-Type-Options", "nosniff"),
                                                   ("Content-Security-Policy", "default-src 'none'; style-src 'unsafe-inline'; sandbox")])
            if len(parts) == 2 and parts[0] == "export":
                try:
                    body, name = chars.export_package(parts[1])
                except chars.PackError as e:
                    return self._json({"ok": False, "error": str(e)}, 404)
                return self._send(body, "application/zip", [("Content-Disposition", f'attachment; filename="{name}"'),
                                                            ("Cache-Control", "no-store")])
            self.send_error(404)

        def do_POST(self):
            try:
                if self.path in ('/api/apple-music', '/api/apple-music/frame'):
                    from modules.apple_bridge import bridge, paired, MAX_FRAME
                    media = next((m for m in app.hub.config.get("modules", []) if m.get("type") == "media"), {})
                    if not paired(self.headers, self.client_address[0], media.get("pair_key")):
                        return self._json({'error': '擴充功能尚未配對'}, 403)
                    size = int(self.headers.get('Content-Length', 0))
                    if self.path == '/api/apple-music/frame':
                        # one JPEG frame of the playing video (sent only while a panel watches)
                        if not 0 < size <= MAX_FRAME:
                            return self._json({'error': '畫面大小無效'}, 413)
                        from urllib.parse import unquote
                        bridge.put_frame(unquote(self.headers.get('X-DeskMon-Track', '')), self.rfile.read(size))
                        return self._json({'mirror': bridge.want_frames()})
                    if not 0 < size <= 512000:
                        return self._json({'error': '資料大小無效'}, 413)
                    payload = json.loads(self.rfile.read(size))
                    commands = bridge.exchange(payload)
                    return self._json({'commands': commands, 'acked': [ack.get('id') for ack in payload.get('acks', [])],
                                       'lyrics_revision': (bridge.snapshot() or {}).get('lyrics_revision'),
                                       'mirror': bridge.want_frames()})
                if not self._allowed(write=True):
                    return self._deny()
                if self.path == "/api/background":
                    # body = the picture itself
                    size = int(self.headers.get("Content-Length", 0))
                    if not 0 < size <= MAX_BACKGROUND:
                        return self._json({"ok": False, "error": "圖片是空的或超過 8 MB"}, 413)
                    got = save_background(app, self.rfile.read(size))
                    return self._json(got, 200 if got["ok"] else 400)
                if self.path == "/api/companion/import":
                    # body = the .zip pack or character.json itself
                    from modules import companion_characters as chars
                    size = int(self.headers.get("Content-Length", 0))
                    if not 0 < size <= chars.MAX_PACKAGE:
                        return self._json({"ok": False, "error": "檔案是空的或超過 10 MB"}, 413)
                    try:
                        return self._json({"ok": True, "character": chars.import_package(self.rfile.read(size))})
                    except chars.PackError as e:
                        return self._json({"ok": False, "error": str(e)}, 400)
                size = int(self.headers.get("Content-Length", 0))
                if size > 1_000_000:
                    return self._json({"ok": False, "error": "資料太大"}, 413)
                req = json.loads(self.rfile.read(size) or b"{}")
                if self.path == "/api/action" and req.get("action") in ("set_volume", "toggle_mute", "set_brightness"):
                    # system card: {"module": "system", "action": "set_volume", "value": 40}
                    params = {k: req.get(k) for k in ("value", "index") if req.get(k) is not None}
                    return self._json({"ok": True, "result": app.hub.action(req["module"], req["action"], **params)})
                if self.path == "/api/action" and req.get("action") in ("tap", "trigger"):
                    # companion: {"module": "companion", "action": "trigger", "event": "print_finished", "simulate": true}
                    params = {"event": req.get("event"), "simulate": bool(req.get("simulate"))} if req["action"] == "trigger" else {}
                    return self._json({"ok": True, "result": app.hub.action(req["module"], req["action"], **params)})
                if self.path == "/api/action":
                    # {"module": "music", "action": "toggle"}
                    return self._json({"ok": True, "result": app.hub.action(req["module"], req["action"], **({"position":req.get("position"),"track":req.get("track")} if req["action"] in ('seek', 'seek_time') else {"track":req.get("track"),"value":req.get("value")} if req["action"] == 'volume' else {"track":req.get("track")} if req["action"] in ('toggle', 'prev', 'next', 'side_screen') else {"objects":req.get("objects"),"job":req.get("job")} if req["action"]=="skip_objects" else {}))})
                if self.path == "/api/event":
                    # the panel reports something only it knows, e.g. {"name": "timer_done"}
                    from modules.event_center import client_event
                    return self._json({"ok": True, "event": client_event(app.hub.events, req.get("name"), req.get("detail"))})
                if self.path == "/api/display":
                    # {"mode": "focus"}: switch the context mode without restarting the modules
                    return self._json({"ok": True, "display": app.patch_display(req)})
                if self.path == "/api/desktop":
                    # {"autostart": true} / {"fullscreen": true} / {"action": "show"}
                    shell = getattr(app, "desktop", None)
                    if not shell:
                        return self._json({"ok": False, "app": False, "error": "只有用 Mondesk 應用程式開啟時才能設定"}, 400)
                    return self._json({"ok": True, **shell.set(req)})
                if self.path == "/api/background/delete":
                    return self._json(delete_background(app))
                if self.path == "/api/extension":
                    # settings page, Apple Music guide: {"step": "prepare"} writes the paired extension folder,
                    # {"step": "open"} shows that folder in the file manager
                    return self._json(extension_step(app, req.get("step"), self.server.server_port))
                if self.path == "/api/companion/delete":
                    from modules import companion_characters as chars
                    chars.delete_package(req.get("id"))
                    return self._json({"ok": True})
                if self.path == "/api/displays":
                    # {"name": "DISPLAY2", "w": 1920, "h": 1080, "step": "test|try|keep|revert"}
                    from displays import set_mode
                    return self._json(set_mode(req["name"], req.get("w", 0), req.get("h", 0), req.get("step", "test"), change_id=req.get("change_id")))
                if self.path == "/api/config":
                    if not isinstance(req.get("modules"), list):
                        raise ValueError("config needs a modules list")
                    app.save(restore_secrets(req, app.hub.config))
                    return self._json({"ok": True})
                self.send_error(404)
            except Exception as e:
                self._json({"ok": False, "error": f"{type(e).__name__}: {e}"}, 400)

    return Handler


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=None)
    ap.add_argument("--host", default=None)
    ap.add_argument("--port", type=int, default=None)
    ap.add_argument("--demo", action="store_true", help="scripted data for every source: no printer, extension, account or key needed")
    ap.add_argument("--demo-speed", type=float, default=1.0, help="play the demo script faster (2 = twice as fast)")
    args = ap.parse_args()
    from user_paths import ensure_user_config
    if args.demo:
        cfg_path, app = None, App(demo=max(0.1, min(20.0, args.demo_speed)))
    else:
        cfg_path = Path(args.config) if args.config else ensure_user_config(ROOT / 'config.example.json')
        if not cfg_path.exists():
            cfg_path = ROOT / "config.example.json"
        app = App(cfg_path)
    host = args.host or app.hub.config.get("host", "127.0.0.1")
    port = args.port or app.hub.config.get("port", 9361)
    print(f"Mondesk on http://{host}:{port}  ({len(app.hub.modules)} modules, "
          f"{'DEMO: scripted data, settings are not saved' if args.demo else 'config: ' + cfg_path.name})", flush=True)
    print(f"Settings:  http://{host}:{port}/settings.html", flush=True)
    if __import__("sys").platform == "win32":
        ThreadingHTTPServer.allow_reuse_address = False
    http = ThreadingHTTPServer((host, port), make_handler(app))
    if not args.demo and any(m.get('pair_key') for m in app.hub.config.get('modules', []) if m.get('type') == 'media'):
        from modules.apple_bridge import prepare_extension
        prepare_extension(cfg_path, port=http.server_port)
    http.serve_forever()


if __name__ == "__main__":
    main()
