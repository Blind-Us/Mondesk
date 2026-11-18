"""Companion triggers: turn changes in Mondesk's live data into events.

Everything here is plain logic with no I/O (except reading the OS idle time), so it can be
unit-tested by feeding it module snapshots. The first snapshot of every source only sets a
baseline: starting Mondesk (or saving settings, which restarts the modules) never makes the
companion announce a print that finished an hour ago.
"""
import sys
import time
from dataclasses import dataclass, field

ACTIVE_STAGES = ("RUNNING", "PREPARE", "PAUSE")

# Which events exist, their labels on screen, and which one wins when several are waiting.
EVENTS = {
    "tap":            {"label": "點一下臉", "priority": 6},
    "print_failed":   {"label": "列印失敗", "priority": 5},
    "print_finished": {"label": "列印完成", "priority": 4},
    "timer_done":     {"label": "計時結束", "priority": 4},
    "quota_high":     {"label": "AI 額度偏高", "priority": 3},
    "rain_soon":      {"label": "快下雨了", "priority": 3},
    "long_work":      {"label": "連續工作過久", "priority": 2},
    "song_change":    {"label": "換歌", "priority": 1},
}

# Seconds before the same event may speak again (each can be changed in config "cooldowns").
DEFAULT_COOLDOWNS = {
    "tap": 6,
    "print_failed": 120,
    "print_finished": 60,
    "quota_high": 1800,
    "long_work": 3600,
    "song_change": 1800,   # tools/companion_eval.py: 15 min meant ~3 song remarks an hour, all day
    "timer_done": 5,
    "rain_soon": 3 * 3600,
}

# "Small" events are frequent and low-stakes: they may use the cheaper model.
SMALL_EVENTS = ("song_change", "tap")


@dataclass
class Event:
    name: str
    detail: dict = field(default_factory=dict)
    simulated: bool = False
    at: float = field(default_factory=time.time)
    entry_id: int = None   # its record in the event centre, when it came from there

    @property
    def label(self):
        return EVENTS.get(self.name, {}).get("label", self.name)

    @property
    def priority(self):
        return EVENTS.get(self.name, {}).get("priority", 0)


def quota_windows(data):
    """[(label, used_percent, resets_at)] for one tokens module, same rules as the card:
    the official windows when present, otherwise the user's token budgets."""
    wins = data.get("windows") or []
    if wins:
        return [(w.get("label"), float(w.get("used_percent") or 0), w.get("resets_at")) for w in wins]
    out = []
    for label, key, budget in (("5h", "window5h", data.get("budget_5h")), ("7d", "week", data.get("budget_week"))):
        used = data.get(key) or {}
        if budget:
            out.append((label, min(100.0, (used.get("input", 0) + used.get("output", 0)) / budget * 100), None))
    return out


class EventDetector:
    """Compares each new snapshot of the modules with the previous one."""

    def __init__(self, quota_threshold=80):
        self.quota_threshold = quota_threshold
        self.stages = {}           # printer id -> (last known stage, error code); kept while a printer is offline
        self.track = None          # (title, artist) of the last seen track
        self.quota_over = set()    # (provider, label) currently at/above the threshold
        self.quota_primed = False
        self.quota_said = set()    # (provider, label, reset time) already mentioned
        self.rain = None           # was rain expected within the next hours at the last look

    def feed(self, modules):
        events = []
        printers = [m for m in modules if m.get("type") == "bambu" and (m.get("data") or {}).get("stage")]
        for printer in printers:   # every printer separately; with more than one the event says which
            events += self._printer(printer["data"], printer.get("id", "printer"),
                                    printer.get("title") if len([m for m in modules if m.get("type") == "bambu"]) > 1 else "")
        media = next((m for m in modules if m.get("type") == "media" and (m.get("data") or {}).get("title")), None)
        if media:
            events += self._music(media["data"])
        tokens = [m for m in modules if m.get("type") == "tokens" and (m.get("data") or {}).get("today")]
        if tokens:
            events += self._quota(tokens)
        weather = next((m for m in modules if m.get("type") == "weather" and (m.get("data") or {}).get("temp") is not None), None)
        if weather:
            events += self._weather(weather["data"])
        return events

    def _weather(self, d):
        soon = d.get("rain_soon") or None
        prev, self.rain = self.rain, bool(soon)
        if prev is None or prev or not soon:   # first look is a baseline; speak when rain appears
            return []
        return [Event("rain_soon", {"place": d.get("place") or "", "in_hours": soon.get("in_hours"),
                                    "probability": soon.get("probability")})]

    @property
    def stage(self):   # the first printer's stage (older callers and tests)
        return next(iter(self.stages.values()), (None, 0))[0]

    def _printer(self, d, pid="printer", name=""):
        prev, prev_err = self.stages.get(pid, (None, 0))
        cur, err = d.get("stage"), d.get("print_error") or 0
        self.stages[pid] = (cur, err)
        if prev is None or prev == cur and not (err and not prev_err and cur in ACTIVE_STAGES):
            return []
        detail = {"file": d.get("file") or "", "from": prev, "to": cur, "progress": d.get("progress"), "printer": name or ""}
        if prev in ACTIVE_STAGES and cur == "FINISH":
            return [Event("print_finished", detail)]
        if prev in ACTIVE_STAGES and cur == "FAILED":
            return [Event("print_failed", {**detail, "reason": "failed", "error_code": err})]
        if prev in ACTIVE_STAGES and cur == "IDLE":
            return [Event("print_failed", {**detail, "reason": "stopped"})]
        if cur == "PAUSE" and err and not prev_err:
            return [Event("print_failed", {**detail, "reason": "paused_by_error", "error_code": err})]
        return []

    def _music(self, d):
        key = (d.get("title"), d.get("artist") or "")
        prev, self.track = self.track, key
        if prev is None or prev == key or not d.get("playing"):
            return []
        return [Event("song_change", {"title": key[0], "artist": key[1], "previous": prev[0]})]

    def _quota(self, tokens):
        events, primed = [], self.quota_primed
        self.quota_primed = True
        for m in tokens:
            provider = m["data"].get("provider") or m.get("id")
            for label, pct, resets_at in quota_windows(m["data"]):
                key = (provider, label)
                # Said once for each quota period. There is nothing the user can do about a used-up quota,
                # so it is not repeated when the number wobbles or a reading drops out and comes back;
                # the next mention is after the quota has reset (a new reset time) and filled up again.
                period = (*key, round(resets_at / 900) if isinstance(resets_at, (int, float)) else None)
                if pct >= self.quota_threshold and key not in self.quota_over:
                    self.quota_over.add(key)
                    if primed and period not in self.quota_said:
                        events.append(Event("quota_high", {"provider": provider, "title": m.get("title") or provider,
                                                           "window": label, "used_percent": round(pct),
                                                           "resets_at": resets_at}))
                    self.quota_said.add(period)
                elif pct < self.quota_threshold - 5:   # a little hysteresis so 79/80/79/80 doesn't nag
                    self.quota_over.discard(key)
                    if resets_at is None:              # no reset time known: falling back under the line starts a new period
                        self.quota_said.discard(period)
        return events


def idle_seconds():
    """Seconds since the last keyboard/mouse input, or None where the OS can't tell us."""
    if sys.platform != "win32":
        return None
    try:
        import ctypes

        class LASTINPUTINFO(ctypes.Structure):
            _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]

        info = LASTINPUTINFO()
        info.cbSize = ctypes.sizeof(info)
        if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info)):
            return None
        ctypes.windll.kernel32.GetTickCount.restype = ctypes.c_uint
        return ((ctypes.windll.kernel32.GetTickCount() - info.dwTime) & 0xFFFFFFFF) / 1000
    except Exception:
        return None


class WorkTracker:
    """How long the user has been working without a real break.

    "Working" = keyboard/mouse input within the last 2 minutes (Windows), or Codex/Claude
    activity within the last 5 minutes where the OS idle time isn't available. A gap longer
    than `break_minutes` starts a new session."""

    def __init__(self, break_minutes=10, idle_fn=idle_seconds):
        self.break_s = break_minutes * 60
        self.idle_fn = idle_fn
        self.start = None
        self.last_active = None

    def update(self, now, ai_last_activity=None):
        idle = self.idle_fn()
        if idle is not None:
            active_at = now - idle if idle < 120 else None
        else:
            active_at = ai_last_activity if ai_last_activity and now - ai_last_activity < 300 else None
        if active_at is not None:
            if self.last_active is None or active_at - self.last_active > self.break_s:
                self.start = active_at
            self.last_active = max(active_at, self.last_active or 0)
        if self.start is None or now - self.last_active > self.break_s:
            return 0
        return int((now - self.start) // 60)


class Limiter:
    """Per-event cooldowns plus one hourly cap on model calls (the API bill)."""

    def __init__(self, cooldowns=None, max_per_hour=20, clock=time.time):
        self.cooldowns = {**DEFAULT_COOLDOWNS, **(cooldowns or {})}
        self.max_per_hour = max_per_hour
        self.clock = clock
        self.last = {}
        self.calls = []

    def ready(self, name):
        return self.clock() - self.last.get(name, -1e12) >= self.cooldowns.get(name, 60)

    def mark(self, name):
        self.last[name] = self.clock()

    def calls_last_hour(self):
        now = self.clock()
        self.calls = [t for t in self.calls if now - t < 3600]
        return len(self.calls)

    def can_call(self):
        return self.calls_last_hour() < self.max_per_hour

    def record_call(self, at=None):
        self.calls.append(self.clock() if at is None else at)
