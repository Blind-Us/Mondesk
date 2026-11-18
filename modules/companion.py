"""Mondesk Companion: a character with a face that reads Mondesk's live data and talks.

Flow: poll() runs every second, diffs the other modules' state (companion_events) and
queues events; a worker thread takes the most important waiting event, asks the brain
(companion_brain) for {"line", "emotion"}, and publishes it in the module's data. The panel
switches the face, types the line out and animates the mouth.

Cost control: per-event cooldowns, a chance for song comments, an hourly cap on model calls
(over the cap the rule-based brain speaks instead), and a capped tool loop per event. Every
utterance is appended to companion-log.jsonl in the user folder for the model comparison
(see tools/companion_report.py).
"""
import json
import os
import random
import threading
import time
from pathlib import Path

from . import BaseModule
from . import companion_characters as characters
from .companion_brain import (SCENARIOS, SIMULATED_DETAIL, AnthropicBrain, OllamaBrain, RuleBrain, BrainError,
                              World, build_system_prompt)
from .companion_events import EVENTS, SMALL_EVENTS, Event, EventDetector, Limiter, WorkTracker

ROOT = Path(__file__).resolve().parent.parent
AUTO_TRIGGERS = ("print_finished", "print_failed", "quota_high", "song_change", "long_work", "timer_done", "rain_soon")
# Triggers added after a config was written are on until the user saves the settings page once
# (which stores "triggers_v"); from then on the list in the config is the whole truth.
TRIGGERS_V = 2
ADDED_TRIGGERS = {2: ("timer_done", "rain_soon")}
STALE_AFTER = 180  # seconds; a queued event older than this is no longer worth saying


def user_folder():
    try:
        from user_paths import user_config_path
        return user_config_path().parent
    except Exception:
        return Path.home() / ".deskmon"


class Module(BaseModule):
    type = "companion"
    default_interval = 1

    def __init__(self, spec):
        super().__init__(spec)
        self.hub = None  # the Hub sets this so the companion can read the other modules
        s = spec
        self.provider = s.get("provider", "anthropic")
        self.model = s.get("model") or "claude-opus-5-5"
        self.small_model = s.get("small_model") or ""
        self.triggers = set(s.get("triggers", AUTO_TRIGGERS))
        for version, names in ADDED_TRIGGERS.items():
            if int(s.get("triggers_v") or 1) < version:
                self.triggers.update(names)
        self.quota_threshold = float(s.get("quota_threshold") or 80)
        self.work_limit = int(s.get("work_minutes") or 120)
        self.song_chance = float(s.get("song_chance", 0.4))
        self.character_id = s.get("character") or characters.DEFAULT_ID
        self.log_path = Path(s["log_path"]) if s.get("log_path") else user_folder() / "companion-log.jsonl"
        self.random = random.random
        self.detector = EventDetector(self.quota_threshold)
        self.tracker = WorkTracker(int(s.get("break_minutes") or 10))
        self.limiter = Limiter(s.get("cooldowns"), int(s.get("max_calls_per_hour") or 20))
        self.rule = RuleBrain()
        self.brains = {}
        self.lock = threading.Lock()
        self.wake = threading.Event()
        self.pending = {}
        self.busy = None
        self.current = {}
        self.history = []
        self.seq = 0
        self.work = 0
        self.running = False
        self._character = (0, None)

    # ---------------------------------------------------------------- lifecycle
    def start(self):
        self._load_log()
        self.running = True
        center = self._center()
        if center:  # events come from the hub's event centre (shared with toasts and history)
            center.subscribe(self._from_center)
        threading.Thread(target=self._worker, daemon=True, name="companion").start()

    def stop(self):
        self.running = False
        center = self._center()
        if center:
            center.unsubscribe(self._from_center)
        self.wake.set()

    def _center(self):
        return getattr(self.hub, "events", None)

    def _from_center(self, ev):
        self.offer(ev)

    def _mark(self, ev, **fields):
        """Tell the event centre what happened to this event (queued, spoken, cooldown…)."""
        center = self._center()
        if center and getattr(ev, "entry_id", None) is not None:
            center.update(ev.entry_id, **fields)

    # ---------------------------------------------------------------- hub contract
    def poll(self):
        center = self._center()
        if center:  # the hub's watcher detects; this module only listens (see _from_center)
            self.work = center.work_minutes
            return self._state()
        # standalone (no event centre, e.g. unit tests): detect here
        now = time.time()
        others = self._others()
        events = self.detector.feed(others)
        ai_last = max((((m.get("data") or {}).get("last_activity") or 0) for m in others
                       if m.get("type") == "tokens"), default=0) or None
        self.work = self.tracker.update(now, ai_last)
        if self.work >= self.work_limit:
            events.append(Event("long_work", {"minutes": self.work}))
        for ev in events:
            self.offer(ev)
        return self._state()

    def action(self, name, event=None, simulate=False):
        if name == "tap":
            queued, reason = self.offer(Event("tap"))
            return {"queued": queued, "reason": reason}
        if name == "trigger":  # manual test buttons in the settings page
            if event not in EVENTS:
                raise ValueError(f"未知的事件：{event}")
            detail = dict(SIMULATED_DETAIL.get(event, {})) if simulate else {}
            ev = Event(event, detail, simulated=bool(simulate))
            center = self._center()
            if center and event != "tap":  # test buttons show up in the history too
                center.record(ev, source="manual", notify=False)
            queued, reason = self.offer(ev, manual=True)
            return {"queued": queued, "reason": reason}
        raise ValueError("不支援的操作")

    # ---------------------------------------------------------------- events
    def offer(self, ev, manual=False):
        """Queue an event unless it's switched off or cooling down. Returns (queued, reason)."""
        reason = "queued"
        if not manual:
            if ev.name != "tap" and ev.name not in self.triggers:
                reason = "off"
            elif not self.limiter.ready(ev.name):
                reason = "cooldown"
            elif ev.name == "song_change" and self.random() >= self.song_chance:
                reason = "skipped"  # only comment on some songs
            else:
                self.limiter.mark(ev.name)
        self._mark(ev, outcome=reason)
        if reason != "queued":
            return False, reason
        with self.lock:
            self.pending[ev.name] = ev  # one per kind: a newer song replaces the older one
        self.wake.set()
        return True, "queued"

    def _next(self):
        now = time.time()
        with self.lock:
            for name, ev in list(self.pending.items()):
                if now - ev.at > STALE_AFTER:
                    del self.pending[name]
                    self._mark(ev, outcome="stale")
            if not self.pending:
                return None
            ev = max(self.pending.values(), key=lambda e: e.priority)
            del self.pending[ev.name]
            self.busy = ev
            return ev

    def _worker(self):
        while self.running:
            ev = self._next()
            if ev is None:
                self.wake.wait(1.0)
                self.wake.clear()
                continue
            try:
                self._speak(ev)
            finally:
                with self.lock:
                    self.busy = None

    def _brain_for(self, ev):
        # no key anywhere: use the free fixed sentences instead of a call that can only fail
        if self.provider == "rule" or self._setup_message():
            return self.rule
        if self.provider == "ollama":
            if "ollama" not in self.brains:
                self.brains["ollama"] = OllamaBrain(self.spec.get("ollama_model") or "qwen3:8b",
                                                    self.spec.get("ollama_url") or "http://127.0.0.1:11434",
                                                    quota_threshold=self.quota_threshold, system=self._system())
            return self.brains["ollama"]
        model = self.small_model if ev.name in SMALL_EVENTS and self.small_model else self.model
        if model not in self.brains:
            self.brains[model] = AnthropicBrain(model, effort=self.spec.get("effort") or "low",
                                                api_key=self.spec.get("api_key"),
                                                fallbacks=self.spec.get("fallbacks", True),
                                                quota_threshold=self.quota_threshold, system=self._system())
        return self.brains[model]

    def _system(self):
        c = self.character()
        return build_system_prompt(c.name, c.persona)

    def _world(self, ev):
        return World(self._others(), work_minutes=self.work, scenario=SCENARIOS.get(ev.name) if ev.simulated else None)

    def _speak(self, ev):
        brain, reason, billed = self._brain_for(ev), None, False
        started = time.time()
        if brain is not self.rule and not self.limiter.can_call():
            brain, reason = self.rule, f"已達每小時 {self.limiter.max_per_hour} 次上限"
        if brain is not self.rule:
            self.limiter.record_call()
            billed = True
        try:
            reply = brain.respond(ev, self._world(ev))
        except Exception as e:  # never go silent: the rule brain still answers
            reason = str(e) if isinstance(e, BrainError) else f"{type(e).__name__}: {e}"
            reply = self.rule.respond(ev, self._world(ev))
        latency = round(time.time() - started, 2)
        entry = {"ts": round(time.time(), 3), "event": ev.name, "event_label": ev.label, "simulated": ev.simulated,
                 "line": reply.line, "emotion": reply.emotion, "via": reply.via,
                 "served_by": reply.served_by, "provider": self.provider, "brain": brain.name,
                 "latency": latency, "tools": reply.tools, "usage": reply.usage, "billed": billed,
                 "error": reason}
        with self.lock:
            self.seq += 1
            self.current = {**entry, "seq": self.seq}
            self.history = (self.history + [entry])[-5:]
        self._append_log(entry)
        self._mark(ev, outcome="spoken", line=reply.line, emotion=reply.emotion, via=reply.via)

    # ---------------------------------------------------------------- state for the panel
    def _others(self):
        if not self.hub:
            return []
        return [m for m in self.hub.module_states() if m.get("type") != "companion"]

    def _setup_message(self):
        if self.provider == "anthropic" and not (self.spec.get("api_key") or os.environ.get("ANTHROPIC_API_KEY")):
            return "尚未設定 Anthropic API 金鑰"
        return None

    def _state(self):
        char = self.character()
        with self.lock:
            cur, busy, history = dict(self.current), self.busy, list(self.history)
        model = {"anthropic": self.model, "ollama": f"ollama:{self.spec.get('ollama_model') or 'qwen3:8b'}",
                 "rule": "rule"}.get(self.provider, self.provider)
        return {
            "_status": "ok",
            "provider": self.provider, "model": model, "small_model": self.small_model or None,
            "setup": self._setup_message(),
            "busy": bool(busy), "busy_event": busy.label if busy else None,
            "seq": cur.get("seq", 0), "line": cur.get("line"), "emotion": cur.get("emotion") or "neutral",
            "event": cur.get("event"), "event_label": cur.get("event_label"), "said_at": cur.get("ts"),
            "via": cur.get("via"), "served_by": cur.get("served_by"), "latency": cur.get("latency"),
            "simulated": cur.get("simulated"), "fallback_reason": cur.get("error"),
            "character": {"id": char.id, "name": char.name, "faces": char.face_info()},
            "work_minutes": self.work,
            "calls_last_hour": self.limiter.calls_last_hour(), "max_calls_per_hour": self.limiter.max_per_hour,
            "history": [{k: h.get(k) for k in ("line", "emotion", "event_label", "ts", "via", "error")}
                        for h in history],
        }

    def character(self):
        """The selected pack (re-read every few seconds so edited images show up)."""
        at, cached = self._character
        if cached is None or time.time() - at > 5:
            try:
                cached = characters.find(self.character_id)
            except (characters.PackError, OSError):
                cached = cached or characters.load_folder(characters.BUILTIN_DIR / characters.DEFAULT_ID, True)
            self._character = (time.time(), cached)
        return cached

    # ---------------------------------------------------------------- log
    def _append_log(self, entry):
        try:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except OSError:
            pass

    def _load_log(self):
        """Saving settings restarts the modules: keep the hourly cap and the last line."""
        try:
            with open(self.log_path, "rb") as f:
                f.seek(0, 2)
                start = max(0, f.tell() - 65536)
                f.seek(start)
                tail = f.read().decode("utf-8", "ignore").splitlines()[1 if start else 0:]  # skip a cut line
        except OSError:
            return
        now = time.time()
        for raw in tail:
            try:
                entry = json.loads(raw)
            except ValueError:
                continue
            if entry.get("billed") and now - entry.get("ts", 0) < 3600:
                self.limiter.record_call(entry["ts"])
            if now - entry.get("ts", 0) < 1800:
                self.history = (self.history + [entry])[-5:]
        if self.history:
            self.seq = 1
            self.current = {**self.history[-1], "seq": 1}
