"""AI token usage from local CLI logs. One module instance per provider.

Providers are tiny parser classes registered in PROVIDERS; add another CLI by
writing a class with `default_glob` and `parse(record) -> Event | None`.
"""
import glob
import json
import os
import time
import threading
from datetime import datetime

from . import BaseModule

HOME = os.path.expanduser("~")


def _ts(s):
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
    except Exception:
        return None


class Codex:
    default_glob = os.path.join(HOME, ".codex", "sessions", "**", "*.jsonl")

    def __init__(self):
        self.limits = None
        self.limits_ts = 0
        self.plan = None

    def parse(self, rec, file_state):
        p = rec.get("payload") or {}
        if rec.get("type") != "event_msg" or p.get("type") != "token_count":
            return None
        ts = _ts(rec.get("timestamp", ""))
        rl = p.get("rate_limits")
        if rl and ts and ts >= self.limits_ts:
            self.limits, self.limits_ts, self.plan = rl, ts, rl.get("plan_type")
        info = p.get("info") or {}
        last = info.get("last_token_usage")
        if not last or not ts:
            return None
        # total_token_usage is cumulative per session; skip duplicate emits
        tot = (info.get("total_token_usage") or {}).get("total_tokens")
        if tot is not None and tot == file_state.get("last_total"):
            return None
        file_state["last_total"] = tot
        return ts, last.get("input_tokens", 0) - last.get("cached_input_tokens", 0), \
            last.get("output_tokens", 0), last.get("cached_input_tokens", 0)

    def extra(self):
        if not self.limits:
            return {}
        out = {"plan": self.plan, "windows": []}
        for key in ("primary", "secondary"):
            w = self.limits.get(key)
            if w:
                mins = w.get("window_minutes", 0)
                out["windows"].append(_fresh({
                    "label": f"{mins // 60}h" if mins < 1440 else f"{mins // 1440}d",
                    "used_percent": w.get("used_percent"), "resets_at": w.get("resets_at")}))
        return out


def _fresh(w, now=None):
    """Codex only logs its limits when it makes a request, so after a window resets the last
    logged % would stay on screen until the next request: a window whose reset time has
    passed is back at 0%."""
    reset = w.get("resets_at")
    if reset and reset <= (now or time.time()):
        return {**w, "used_percent": 0, "resets_at": None, "reset": True}
    return w


class Claude:
    default_glob = os.path.join(HOME, ".claude", "projects", "**", "*.jsonl")

    def __init__(self):
        self.seen = set()
        self.model = None

    def parse(self, rec, _fs):
        msg = rec.get("message") or {}
        u = msg.get("usage")
        if rec.get("type") != "assistant" or not u:
            return None
        key = (msg.get("id"), rec.get("requestId"))  # streamed chunks repeat usage
        if key in self.seen:
            return None
        self.seen.add(key)
        ts = _ts(rec.get("timestamp", ""))
        if not ts:
            return None
        self.model = msg.get("model") or self.model
        return ts, u.get("input_tokens", 0) + u.get("cache_creation_input_tokens", 0), \
            u.get("output_tokens", 0), u.get("cache_read_input_tokens", 0)

    def extra(self):
        out = {"model": self.model}
        # opt-in: only read the local Claude Code login when the user enabled it in settings
        win = self._official() if getattr(self, "official", False) else None
        if win:
            out["windows"] = [_fresh(w) for w in win]
        if getattr(self, "official", False) and self.error:
            out["usage_error"] = self.error
        return out

    # The usage endpoint rate-limits (HTTP 429) if asked too often, so: ask every 5 min,
    # back off 15 min after a 429/error, keep showing the last good value, and save it to disk
    # so restarting Mondesk doesn't trigger an immediate re-query.
    CACHE = None   # default: <user folder>/claude-usage.json (tests point this at a temp file)
    LEGACY_CACHE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".claude-usage.json")

    def _cache_path(self):
        if self.CACHE:
            return self.CACHE
        from user_paths import user_data_dir
        return os.path.join(str(user_data_dir()), "claude-usage.json")
    EVERY, BACKOFF, KEEP = 300, 900, 6 * 3600

    def _official(self, force=False):
        """Real % from the account if the Claude Code CLI login file exists."""
        if not hasattr(self, "_last"):
            self._last, self._next = None, 0
            # older versions kept the cache next to the program: still read it once
            for path in (self._cache_path(), *(() if self.CACHE else (self.LEGACY_CACHE,))):
                try:
                    with open(path, encoding="utf-8") as f:
                        saved = json.load(f)
                    self._last, self._next = saved, saved["at"] + self.EVERY
                    break
                except Exception:
                    continue
        now = time.time()
        if force or now >= self._next:
            win = self._query()
            if win:
                self._last, self._next = {"at": now, "windows": win}, now + self.EVERY
                try:
                    with open(self._cache_path(), "w", encoding="utf-8") as f:
                        json.dump(self._last, f)
                except OSError:
                    pass
            else:
                self._next = now + self.BACKOFF
                if force:
                    raise RuntimeError((self.error or 'Claude 用量查詢失敗，請稍後重試') + '；保留上次資料')
        last = self._last
        return last["windows"] if last and now - last["at"] < self.KEEP else None

    # Claude Code's login (~/.claude/.credentials.json). Its access token lasts a few hours and
    # only the CLI refreshes it, so when Claude Code is used from the desktop app the file goes
    # stale and every query got 401 -> the card showed 0% / 0% forever. Like other usage
    # monitors, refresh it with the refresh token and write the new pair back, so the CLI keeps
    # working with the same login.
    CRED = os.path.join(HOME, ".claude", ".credentials.json")
    USAGE_URL = "https://api.anthropic.com/api/oauth/usage"
    TOKEN_URLS = ("https://platform.claude.com/v1/oauth/token", "https://console.anthropic.com/v1/oauth/token")
    CLIENT_ID = "9d1c250a-e61b-44d9-88ed-5944d1962f5e"   # Claude Code's public OAuth client
    error = ""

    def _query(self):
        import urllib.error
        try:
            with open(self.CRED, encoding="utf-8") as f:
                oauth = json.load(f)["claudeAiOauth"]
        except (OSError, ValueError, KeyError):
            self.error = "找不到 Claude Code 的登入資料（先在終端機執行一次 claude 並登入）"
            return None
        try:
            if (oauth.get("expiresAt") or 0) / 1000 < time.time() + 60:
                oauth = self._refresh(oauth)
            try:
                data = self._get_usage(oauth["accessToken"])
            except urllib.error.HTTPError as e:
                if e.code != 401:
                    raise
                data = self._get_usage(self._refresh(oauth)["accessToken"])  # revoked early: refresh once
        except urllib.error.HTTPError as e:
            self.error = "查詢太頻繁，稍後會自動再試" if e.code == 429 else f"用量查詢失敗（HTTP {e.code}）"
            return None
        except RuntimeError as e:
            self.error = str(e)
            return None
        except Exception:
            self.error = "連不上 Claude，稍後會自動再試"
            return None
        self.error = ""
        win = []
        for key, label in (("five_hour", "5h"), ("seven_day", "7d")):
            w = data.get(key)
            if w:
                win.append({"label": label, "used_percent": w.get("utilization") or 0,
                            "resets_at": _ts(w["resets_at"]) if w.get("resets_at") else None})
        return win or None

    def _get_usage(self, token):
        import urllib.request
        req = urllib.request.Request(self.USAGE_URL, headers={
            "Authorization": f"Bearer {token}", "anthropic-beta": "oauth-2025-04-20", "User-Agent": "deskmon"})
        with urllib.request.urlopen(req, timeout=8) as r:
            return json.load(r)

    def _refresh(self, oauth):
        """New access token from the refresh token; saved back into the credentials file."""
        import urllib.error
        import urllib.request
        if not oauth.get("refreshToken") or (oauth.get("refreshTokenExpiresAt") or 1e15) / 1000 < time.time():
            raise RuntimeError("Claude 登入已過期：在終端機執行 claude，輸入 /login 重新登入")
        body = json.dumps({"grant_type": "refresh_token", "refresh_token": oauth["refreshToken"],
                           "client_id": self.CLIENT_ID}).encode()
        last = None
        for url in self.TOKEN_URLS:
            req = urllib.request.Request(url, data=body, method="POST", headers={
                "Content-Type": "application/json", "User-Agent": "deskmon"})
            try:
                with urllib.request.urlopen(req, timeout=10) as r:
                    got = json.load(r)
                break
            except urllib.error.HTTPError as e:
                last = e
                if e.code in (400, 401, 403):   # the token itself was refused: another host won't help
                    raise RuntimeError("Claude 登入已過期：在終端機執行 claude，輸入 /login 重新登入") from e
                if e.code == 429:
                    raise
        else:
            raise last or RuntimeError("連不上 Claude 登入伺服器")
        now_ms = int(time.time() * 1000)
        oauth = {**oauth, "accessToken": got["access_token"],
                 "expiresAt": now_ms + int(got.get("expires_in", 3600)) * 1000}
        if got.get("refresh_token"):
            oauth["refreshToken"] = got["refresh_token"]
        if got.get("refresh_token_expires_in"):
            oauth["refreshTokenExpiresAt"] = now_ms + int(got["refresh_token_expires_in"]) * 1000
        self._save(oauth)
        return oauth

    def _save(self, oauth):
        """Write the new tokens back, keeping everything else in the file (atomic replace)."""
        try:
            with open(self.CRED, encoding="utf-8") as f:
                whole = json.load(f)
        except (OSError, ValueError):
            whole = {}
        whole["claudeAiOauth"] = {**whole.get("claudeAiOauth", {}), **oauth}
        tmp = self.CRED + ".deskmon-tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(whole, f)
        os.replace(tmp, self.CRED)


PROVIDERS = {"codex": Codex, "claude": Claude}


class Module(BaseModule):
    type = "tokens"
    default_interval = 15

    def start(self):
        self._poll_lock = threading.RLock()
        self._manual_at = 0
        self.provider = PROVIDERS[self.spec["provider"]]()
        self.provider.official = bool(self.spec.get("official_usage", False))
        self.pattern = os.path.expanduser(self.spec.get("glob") or self.provider.default_glob)
        self.files = {}   # path -> {"offset": int, ...}
        self.events = []  # (ts, input, output, cached)

    def _scan(self):
        horizon = time.time() - 8 * 86400
        for path in glob.glob(self.pattern, recursive=True):
            try:
                st = os.stat(path)
            except OSError:
                continue
            if st.st_mtime < horizon:
                continue
            fs = self.files.setdefault(path, {"offset": 0})
            if st.st_size <= fs["offset"]:
                continue
            with open(path, "rb") as f:
                f.seek(fs["offset"])
                chunk = f.read()
            end = chunk.rfind(b"\n") + 1  # leave a half-written last line for next time
            fs["offset"] += end
            for line in chunk[:end].splitlines():
                try:
                    ev = self.provider.parse(json.loads(line), fs)
                except Exception:
                    continue
                if ev and ev[0] > horizon:
                    self.events.append(ev)
        self.events = [e for e in self.events if e[0] > horizon]

    def action(self, name):
        if name != 'refresh' or self.spec.get('provider') != 'claude':
            raise ValueError('不支援的操作')
        with self._poll_lock:
            if time.time() - self._manual_at < 15:
                raise RuntimeError('剛剛已查詢，請稍候再試')
            self._manual_at = time.time()
            if self.provider.official:
                self.provider._official(force=True)
            return self._poll()

    def poll(self):
        with self._poll_lock:
            return self._poll()

    def _poll(self):
        self._scan()
        now = time.time()
        midnight = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).timestamp()

        def total(since):
            sel = [e for e in self.events if e[0] >= since]
            return {"input": sum(e[1] for e in sel), "output": sum(e[2] for e in sel),
                    "cached": sum(e[3] for e in sel), "calls": len(sel)}

        # 24 hourly buckets of (input+output) for the sparkline
        hourly = [0] * 24
        for ts, i, o, _c in self.events:
            h = int((now - ts) // 3600)
            if 0 <= h < 24:
                hourly[23 - h] += i + o
        last = max((e[0] for e in self.events), default=None)
        data = {
            "provider": self.spec["provider"],
            "today": total(midnight), "window5h": total(now - 5 * 3600), "week": total(now - 7 * 86400),
            "hourly": hourly, "last_activity": last,
            "budget_5h": self.spec.get("budget_5h"), "budget_week": self.spec.get("budget_week"),
            **self.provider.extra(),
        }
        data["_status"] = "ok" if last and now - last < 600 else "idle"
        return data
