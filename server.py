"""DeskMon - modular desk monitor (Windows / Linux / macOS).

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


SECRET_KEYS = ("access_code", "pair_key", "token", "password", "secret")
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

    def __init__(self, config):
        self.config = config
        self.modules = []
        self.state = {}
        self.lock = threading.Lock()
        self.running = True
        for spec in config.get("modules", []):
            if not spec.get("enabled", True):
                continue
            mod = importlib.import_module(f"modules.{spec['type']}")
            inst = mod.Module(spec)
            self.modules.append(inst)
            self.state[inst.id] = {"id": inst.id, "type": inst.type, "title": inst.title,
                                   "status": "starting", "data": {}}

    def start(self):
        for m in self.modules:
            m.start()
            threading.Thread(target=self._loop, args=(m,), daemon=True).start()

    def stop(self):
        self.running = False
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
        if name == "seek":
            data = m.action(name, **params)
            entry = {"status":data.pop("_status","ok"),"data":data,"error":None,"id":m.id,"type":m.type,"title":m.title,"updated":time.time()}
            with self.lock: self.state[m.id]=entry
            return data
        return m.action(name, **params)

    def snapshot(self):
        with self.lock:
            return {"time": time.time(), "display": self.config.get("display", {}),
                    "theme": self.config.get("theme", {}),
                    "modules": [self.state[m.id] for m in self.modules]}


class App:
    """Owns the config file and the running Hub; saving settings swaps in a new Hub."""

    def __init__(self, path):
        self.path = path
        self.hub = None
        self.reload(json.loads(path.read_text(encoding="utf-8")))

    def reload(self, config):
        old, self.hub = self.hub, Hub(config)
        if old:
            old.stop()
        self.hub.start()

    def save(self, config):
        if self.path.name == "config.example.json":
            self.path = ROOT / "config.json"
        self.path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
        self.reload(config)


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

        # ---- security: only DeskMon's own pages may use the API ----
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

        def _deny(self):
            self._json({"ok": False, "error": "已拒絕：只接受 DeskMon 自己頁面的請求"}, 403)

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
            if self.path.startswith("/api/displays"):
                from displays import list_displays  # read-only
                return self._json(list_displays())
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
                    while app.hub is hub:
                        sampled, frame = m.stream_frame()
                        if frame and sampled != last:
                            last = sampled
                            self.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: "
                                             + str(len(frame)).encode() + b"\r\n\r\n" + frame + b"\r\n")
                            self.wfile.flush()
                        time.sleep(0.05)
                except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
                    pass  # viewer closed the live view
                return
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

        def do_POST(self):
            try:
                if self.path == '/api/apple-music':
                    from modules.apple_bridge import bridge, paired
                    media = next((m for m in app.hub.config.get("modules", []) if m.get("type") == "media"), {})
                    if not paired(self.headers, self.client_address[0], media.get("pair_key")):
                        return self._json({'error': '擴充功能尚未配對'}, 403)
                    size = int(self.headers.get('Content-Length', 0))
                    if not 0 < size <= 512000:
                        return self._json({'error': '資料大小無效'}, 413)
                    payload = json.loads(self.rfile.read(size))
                    commands = bridge.exchange(payload)
                    return self._json({'commands': commands, 'acked': [ack.get('id') for ack in payload.get('acks', [])]})
                if not self._allowed(write=True):
                    return self._deny()
                size = int(self.headers.get("Content-Length", 0))
                if size > 1_000_000:
                    return self._json({"ok": False, "error": "資料太大"}, 413)
                req = json.loads(self.rfile.read(size) or b"{}")
                if self.path == "/api/action":
                    # {"module": "music", "action": "toggle"}
                    return self._json({"ok": True, "result": app.hub.action(req["module"], req["action"], **({"position":req.get("position"),"track":req.get("track")} if req["action"]=="seek" else {"objects":req.get("objects"),"job":req.get("job")} if req["action"]=="skip_objects" else {}))})
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
    ap.add_argument("--config", default=str(ROOT / "config.json"))
    ap.add_argument("--host", default=None)
    ap.add_argument("--port", type=int, default=None)
    args = ap.parse_args()
    cfg_path = Path(args.config)
    if not cfg_path.exists():
        cfg_path = ROOT / "config.example.json"
    app = App(cfg_path)
    host = args.host or app.hub.config.get("host", "127.0.0.1")
    port = args.port or app.hub.config.get("port", 9361)
    print(f"DeskMon on http://{host}:{port}  ({len(app.hub.modules)} modules, config: {cfg_path.name})")
    print(f"Settings:  http://{host}:{port}/settings.html")
    if __import__("sys").platform == "win32":
        ThreadingHTTPServer.allow_reuse_address = False
    ThreadingHTTPServer((host, port), make_handler(app)).serve_forever()


if __name__ == "__main__":
    main()
