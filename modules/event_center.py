"""Event centre: "something changed" is recorded once; how to remind is decided by whoever
listens (the Companion speaks, the panel shows a toast, the settings page lists the history).

The hub owns one EventCenter and a watcher that turns module data into events every second
(companion_events.EventDetector + WorkTracker), so events exist even when no Companion card
is on the panel. Events are kept in memory and appended to events.jsonl in the user folder.

Not a module type: the hub creates it directly.
"""
import json
import threading
import time
from pathlib import Path

from .companion_events import EVENTS, Event, EventDetector, WorkTracker

KEEP = 200                 # events kept in memory / returned at most
MAX_FILE = 512 * 1024      # events.jsonl is cut back to its newest half past this size
# Events a page may report itself (the countdown runs in the browser, not in a module)
CLIENT_EVENTS = ("timer_done",)
# What became of an event: detected -> queued -> spoken, or why nobody said it
OUTCOMES = ("detected", "queued", "spoken", "off", "cooldown", "skipped", "stale")


class EventCenter:
    def __init__(self, path=None, clock=time.time):
        self.path = Path(path) if path else None
        self.clock = clock
        self.lock = threading.Lock()
        self.entries = []
        self.listeners = []
        self.seq = 0
        self.work_minutes = 0
        self._load()

    # ------------------------------------------------------------ recording
    def record(self, event, source="detector", notify=True):
        """Store one event and tell the listeners. Returns its history entry."""
        with self.lock:
            self.seq += 1
            entry = {"id": self.seq, "ts": round(event.at, 3), "name": event.name, "label": event.label,
                     "detail": dict(event.detail), "simulated": bool(event.simulated), "source": source,
                     "outcome": "detected", "line": None, "emotion": None}
            self.entries = (self.entries + [entry])[-KEEP:]
            listeners = list(self.listeners) if notify else []
        event.entry_id = entry["id"]
        self._append(entry)
        for fn in listeners:
            try:
                fn(event)
            except Exception:
                pass  # one broken listener must not hide the event from the others
        return entry

    def update(self, entry_id, **fields):
        """A listener reports what it did with the event (queued, spoken + the line, cooldown…)."""
        if entry_id is None:
            return
        with self.lock:
            entry = next((e for e in self.entries if e["id"] == entry_id), None)
            if not entry:
                return
            entry.update({k: v for k, v in fields.items() if k in ("outcome", "line", "emotion", "via")})
            snapshot = dict(entry)
        if fields.get("outcome") == "spoken":
            self._append({**snapshot, "update": True})

    def subscribe(self, fn):
        with self.lock:
            self.listeners.append(fn)

    def unsubscribe(self, fn):
        with self.lock:
            self.listeners = [f for f in self.listeners if f != fn]

    def recent(self, limit=30):
        with self.lock:
            return [dict(e) for e in self.entries[-limit:]]

    # ------------------------------------------------------------ file
    def _append(self, entry):
        if not self.path:
            return
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            if self.path.exists() and self.path.stat().st_size > MAX_FILE:
                lines = self.path.read_text(encoding="utf-8", errors="ignore").splitlines()
                self.path.write_text("\n".join(lines[len(lines) // 2:]) + "\n", encoding="utf-8")
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except OSError:
            pass

    def _load(self):
        """Show the last day's events again after a restart (ids continue from the file)."""
        if not self.path:
            return
        try:
            with open(self.path, "rb") as f:
                f.seek(0, 2)
                start = max(0, f.tell() - 131072)
                f.seek(start)
                tail = f.read().decode("utf-8", "ignore").splitlines()[1 if start else 0:]
        except OSError:
            return
        by_id, now = {}, self.clock()
        for raw in tail:
            try:
                entry = json.loads(raw)
            except ValueError:
                continue
            if not isinstance(entry, dict) or not isinstance(entry.get("id"), int):
                continue
            entry.pop("update", None)
            by_id[entry["id"]] = entry  # a later "spoken" line replaces the first record
        self.seq = max(by_id, default=0)
        self.entries = [e for e in by_id.values() if now - e.get("ts", 0) < 86400][-KEEP:]


class EventWatcher:
    """Runs the detector on the hub's module states once a second and records what it finds."""

    def __init__(self, hub, center, quota_threshold=80, work_minutes=120, break_minutes=10, interval=1.0):
        self.hub, self.center, self.interval = hub, center, interval
        self.detector = EventDetector(quota_threshold)
        self.tracker = WorkTracker(break_minutes)
        self.work_limit = work_minutes
        self.long_work_at = None   # work minutes at which long_work was last reported
        self.running = False

    def start(self):
        self.running = True
        threading.Thread(target=self._loop, daemon=True, name="event-watcher").start()

    def stop(self):
        self.running = False

    def _loop(self):
        while self.running and getattr(self.hub, "running", True):
            try:
                self.step()
            except Exception:
                pass  # a module with odd data must not stop event detection
            time.sleep(self.interval)

    def step(self, now=None):
        now = now or time.time()
        others = [m for m in self.hub.module_states() if m.get("type") != "companion"]
        events = self.detector.feed(others)
        ai_last = max((((m.get("data") or {}).get("last_activity") or 0) for m in others
                       if m.get("type") == "tokens"), default=0) or None
        work = self.center.work_minutes = self.tracker.update(now, ai_last)
        if work < self.work_limit:
            self.long_work_at = None
        elif self.long_work_at is None or work - self.long_work_at >= 60:   # once, then hourly
            self.long_work_at = work
            events.append(Event("long_work", {"minutes": work}))
        for ev in events:
            self.center.record(ev)
        return events


def client_event(center, name, detail=None):
    """An event reported by Mondesk's own page (POST /api/event)."""
    if name not in CLIENT_EVENTS or name not in EVENTS:
        raise ValueError(f"未知的事件：{name}")
    clean = {k: v for k, v in (detail or {}).items()
             if isinstance(k, str) and len(k) <= 20 and isinstance(v, (int, float, str)) and len(str(v)) <= 60}
    return center.record(Event(name, clean), source="panel")
