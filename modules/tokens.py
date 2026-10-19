"""AI token usage from local CLI logs. One module instance per provider.

Providers are tiny parser classes registered in PROVIDERS; add another CLI by
writing a class with `default_glob` and `parse(record) -> Event | None`.
"""
import glob
import json
import os
import time
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
                out["windows"].append({
                    "label": f"{mins // 60}h" if mins < 1440 else f"{mins // 1440}d",
                    "used_percent": w.get("used_percent"), "resets_at": w.get("resets_at")})
        return out


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
            out["windows"] = win
        return out

    # The usage endpoint rate-limits (HTTP 429) if asked too often, so: ask every 5 min,
    # back off 15 min after a 429/error, keep showing the last good value, and save it to disk
    # so restarting DeskMon doesn't trigger an immediate re-query.
    CACHE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".claude-usage.json")
    EVERY, BACKOFF, KEEP = 300, 900, 6 * 3600

    def _official(self):
        """Real % from the account if the Claude Code CLI login file exists."""
        if not hasattr(self, "_last"):
            try:
                with open(self.CACHE, encoding="utf-8") as f:
                    saved = json.load(f)
                self._last, self._next = saved, saved["at"] + self.EVERY
            except Exception:
                self._last, self._next = None, 0
        now = time.time()
        if now >= self._next:
            win = self._query()
            if win:
                self._last, self._next = {"at": now, "windows": win}, now + self.EVERY
                try:
                    with open(self.CACHE, "w", encoding="utf-8") as f:
                        json.dump(self._last, f)
                except OSError:
                    pass
            else:
                self._next = now + self.BACKOFF
        last = self._last
        return last["windows"] if last and now - last["at"] < self.KEEP else None

    def _query(self):
        cred = os.path.join(HOME, ".claude", ".credentials.json")
        try:
            import urllib.request
            with open(cred, encoding="utf-8") as f:
                tok = json.load(f)["claudeAiOauth"]["accessToken"]
            req = urllib.request.Request("https://api.anthropic.com/api/oauth/usage", headers={
                "Authorization": f"Bearer {tok}", "anthropic-beta": "oauth-2025-04-20", "User-Agent": "deskmon"})
            data = json.load(urllib.request.urlopen(req, timeout=8))
        except Exception:
            return None
        win = []
        for key, label in (("five_hour", "5h"), ("seven_day", "7d")):
            w = data.get(key)
            if w:
                win.append({"label": label, "used_percent": w.get("utilization") or 0,
                            "resets_at": _ts(w["resets_at"]) if w.get("resets_at") else None})
        return win or None


PROVIDERS = {"codex": Codex, "claude": Claude}


class Module(BaseModule):
    type = "tokens"
    default_interval = 15

    def start(self):
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

    def poll(self):
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
