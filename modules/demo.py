"""Demo mode: every data source is replaced by a scripted one, so the whole flow can be shown
and re-tested with no printer, no browser extension, no account and no API key.

    python server.py --demo            (or run-demo.bat / run-demo.sh)

The script loops every PERIOD seconds and is a pure function of the elapsed time, so a run is
repeatable: the print finishes, a second print fails, the Codex quota crosses 80 %, songs
change (with synced lines) and rain shows up in the forecast. The real event centre and the
real Companion (rule-based brain, no cost) react to it exactly as they would to live data.
Nothing is written to the user's settings: the demo keeps its files in a temp folder.

Not listed in config.json: the hub swaps these in for the real modules while in demo mode.
"""
import json
import time

from . import BaseModule

PERIOD = 240.0
STAGE_LABELS = {"IDLE": "待機", "PREPARE": "準備中", "RUNNING": "列印中", "PAUSE": "已暫停",
                "FINISH": "已完成", "FAILED": "失敗"}

# (title, artist, album, seconds). Made-up songs with made-up lines: no real lyrics are shipped.
SONGS = [("示範曲一：晨間作業", "Mondesk 樂團", "示範專輯", 50),
         ("示範曲二：列印進行中", "Mondesk 樂團", "示範專輯", 45),
         ("示範曲三：收工", "Mondesk 樂團", "示範專輯", 55)]
LINES = ["這是示範歌詞的第一句", "歌詞會跟著播放進度往上捲", "點任何一句可以跳到那個時間",
         "下方的進度條也可以直接拖曳", "這些句子只是示範用的文字", "實際使用時會顯示 Apple Music 的歌詞",
         "換歌的時候角色偶爾會說一句", "列印完成時它會提醒你", "額度快滿的時候它也會說", "示範歌詞到這裡結束"]


def printer_at(t):
    """Printer data at second t of the loop."""
    if t < 70:
        return _printer("RUNNING", "貓咪手機架", 80 + t / 70 * 20, remain=(70 - t) / 60 * 3, layer=(int(160 + t), 240))
    if t < 100:
        return _printer("FINISH", "貓咪手機架", 100, remain=0, layer=(240, 240), nozzle=96, bed=58)
    if t < 110:
        return _printer("IDLE", "", None, nozzle=45, bed=38)
    if t < 125:
        return _printer("PREPARE", "齒輪盒蓋", 0, remain=64, nozzle=150, bed=52)
    if t < 190:
        return _printer("RUNNING", "齒輪盒蓋", (t - 125) / 65 * 37, remain=64 - (t - 125) / 65 * 24, layer=(int((t - 125) * 0.8), 180))
    if t < 215:
        return _printer("FAILED", "齒輪盒蓋", 37, layer=(52, 180), error=50348044)
    return _printer("IDLE", "", None, nozzle=60, bed=40)


def _printer(stage, file, progress, remain=None, layer=None, nozzle=220, bed=60, error=0):
    remain = None if remain is None else int(round(remain))
    return {
        "stage": stage, "stage_label": STAGE_LABELS[stage], "file": file,
        "progress": None if progress is None else int(progress), "remaining_min": remain,
        "eta": time.time() + remain * 60 if remain else None,
        "layer": layer[0] if layer else None, "total_layers": layer[1] if layer else None,
        "nozzle": nozzle, "nozzle_target": 220 if stage in ("RUNNING", "PREPARE") else 0,
        "bed": bed, "bed_target": 60 if stage in ("RUNNING", "PREPARE") else 0, "chamber": 34,
        "print_error": error, "hms": [], "ams": [], "objects": [], "skip_enabled": False, "stale": False,
        "preview": False, "preview_version": 0, "preview_pending": False, "model": "示範機",
        "control_enabled": False, "control_actions": [],
        "_status": "ok" if stage in ("RUNNING", "PREPARE") else "idle",
    }


def quota_at(provider, t):
    """Codex climbs through the 80 % threshold once per loop; Claude stays calm."""
    now = time.time()
    if provider == "codex":
        five, week, plan, today = 62 + t / PERIOD * 30, 34, "plus", 310_000 + int(t * 900)
    else:
        five, week, plan, today = 41 + t / PERIOD * 4, 27, "max", 520_000 + int(t * 600)
    hourly = [int(20_000 + 18_000 * ((i * 7 + 3) % 5)) if 8 <= i else 0 for i in range(24)]
    usage = lambda n: {"input": int(n * 0.7), "output": int(n * 0.3), "cached": n * 20, "calls": n // 3000}
    return {"provider": provider, "plan": plan, "today": usage(today), "window5h": usage(today // 2),
            "week": usage(today * 5), "hourly": hourly, "last_activity": now, "budget_5h": None, "budget_week": None,
            "windows": [{"label": "5h", "used_percent": round(five, 1), "resets_at": now + 2.4 * 3600},
                        {"label": "7d", "used_percent": week, "resets_at": now + 3.2 * 86400}],
            "_status": "ok"}


def weather_at(t):
    rain = 30 <= t < 150
    hour = time.localtime().tm_hour
    hours = [{"hour": (hour + i) % 24, "temp": 24 - i // 2, "pop": [20, 35, 70, 80, 60, 30][i] if rain else [10, 10, 15, 20, 20, 15][i],
              "icon": "rain" if rain and i >= 2 else "partly", "ahead": i + 1} for i in range(6)]
    return {"place": "示範市", "temp": 24, "feels": 26, "code": 2, "label": "多雲", "icon": "partly", "is_day": True,
            "raining": False, "high": 27, "low": 21, "rain_today": 80 if rain else 20, "hours": hours,
            "rain_soon": {"in_hours": 3, "probability": 70} if rain else None, "fetched": time.time(),
            "stale": False, "error_detail": "", "_status": "ok"}


class Module(BaseModule):
    """Scripted stand-in for one real module (bambu / media / tokens / weather / system)."""
    default_interval = 1

    def __init__(self, spec, started=None, speed=1.0):
        super().__init__(spec)
        self.type = spec["type"]
        self.started = started or time.time()
        self.speed = speed
        # media: position inside the playlist is "seconds played", so pause and seek are real
        self.playing, self.played, self.at = True, 0.0, time.time()
        self.volume, self.muted = 40, False

    def clock(self):
        return ((time.time() - self.started) * self.speed) % PERIOD

    def poll(self):
        t = self.clock()
        if self.type == "bambu":
            return printer_at(t)
        if self.type == "tokens":
            return quota_at(self.spec.get("provider") or self.id, t)
        if self.type == "weather":
            return weather_at(t)
        if self.type == "system":
            return {"volume": self.volume, "muted": self.muted, "monitors": [], "_status": "ok"}
        if self.type == "media":
            return self._media()
        return {"_status": "idle", "message": "示範模式沒有這個資料來源"}

    # ------------------------------------------------------------ media
    def _advance(self):
        now = time.time()
        if self.playing:
            self.played += (now - self.at) * self.speed
        self.at = now

    def _song(self):
        self._advance()
        total = sum(s[3] for s in SONGS)
        pos, index = self.played % total, 0
        while pos >= SONGS[index][3]:
            pos -= SONGS[index][3]
            index += 1
        return index, pos

    def _lines(self, index):
        length = SONGS[index][3]
        step = (length - 6) / len(LINES)
        return [[round(3 + i * step, 2), text, ""] for i, text in enumerate(LINES)]

    def _media(self):
        index, pos = self._song()
        title, artist, album, length = SONGS[index]
        return {"title": title, "artist": artist, "album": album, "source": "Apple Music", "playing": self.playing,
                "position": pos, "duration": float(length), "sampled": time.time(), "track": f"demo:{index}",
                "browser_bridge": True, "video": False, "lyrics": "ok", "lyrics_revision": index, "art_url": "",
                "progress": round(pos / length * 100), "ext": "demo", "ext_expected": "demo", "ext_outdated": False,
                "mirror": "", "demo": True, "_status": "ok" if self.playing else "idle"}

    def asset(self, name):
        if self.type == "media" and name == "lyrics":
            index, _ = self._song()
            body = {"source": "示範", "synced": self._lines(index)}
            return json.dumps(body, ensure_ascii=False).encode(), "application/json; charset=utf-8"
        return None

    def _jump(self, index, pos=0.0):
        self.played = sum(s[3] for s in SONGS[:index % len(SONGS)]) + max(0.0, pos)
        self.at = time.time()

    # ------------------------------------------------------------ actions
    def action(self, name, **params):
        if self.type == "system":
            if name == "set_volume":
                self.volume, self.muted = max(0, min(100, int(params.get("value") or 0))), False
            elif name == "toggle_mute":
                self.muted = not self.muted
            elif name != "set_brightness":
                raise ValueError("不支援的操作")
            return self.poll()
        if self.type == "tokens" and name == "refresh":
            return self.poll()
        if self.type == "bambu":
            if name == "camera":
                return {"ready": False, "message": "示範模式沒有攝影機畫面"}
            raise RuntimeError("示範模式不會控制列印機")
        if self.type != "media":
            raise ValueError("不支援的操作")
        index, pos = self._song()
        if params.get("track") not in (None, f"demo:{index}"):
            raise RuntimeError("歌曲已變更，請重新操作")
        if name == "toggle":
            self.playing = not self.playing
        elif name in ("next", "prev"):
            self._jump(index + (1 if name == "next" else -1))
        elif name in ("seek", "seek_time"):
            target = float(params.get("position") or 0)
            if not 0 <= target <= SONGS[index][3]:
                raise ValueError("無效的播放時間")
            self._jump(index, target)
            return self.poll()
        elif name == "side_screen":
            raise RuntimeError("示範模式沒有影片分頁")
        else:
            raise ValueError(name)
        return name


DEMO_TYPES = ("bambu", "media", "tokens", "weather", "system")


def demo_config(folder):
    """The in-memory config of a demo session (never saved to the user's settings)."""
    return {
        "host": "127.0.0.1", "port": 9361, "demo": True,
        "display": {"text_scale": 1, "mode": "", "auto_mode": False, "layout": {"items": [
            {"id": "bambu", "x": 0, "y": 0, "w": 2, "h": 5}, {"id": "media", "x": 2, "y": 0, "w": 2, "h": 5},
            {"id": "companion", "x": 4, "y": 0, "w": 2, "h": 5}, {"id": "tokens", "x": 0, "y": 5, "w": 2, "h": 3},
            {"id": "weather", "x": 2, "y": 5, "w": 2, "h": 3}, {"id": "clock", "x": 4, "y": 5, "w": 2, "h": 3}],
            "hidden": ["system"]}},
        "modules": [
            {"id": "printer", "type": "bambu", "title": "示範列印機"},
            {"id": "music", "type": "media", "title": "Now Playing"},
            {"id": "codex", "type": "tokens", "provider": "codex", "title": "Codex"},
            {"id": "claude", "type": "tokens", "provider": "claude", "title": "Claude"},
            {"id": "weather", "type": "weather", "title": "天氣", "place": "示範市"},
            {"id": "system", "type": "system", "title": "系統"},
            {"id": "clock", "type": "clock", "title": "時鐘", "style": "digital", "seconds": True, "date": True, "timer": True},
            # the real Companion with the free rule-based brain; short cooldowns so the loop is lively
            {"id": "companion", "type": "companion", "title": "Companion", "provider": "rule", "character": "kid",
             "song_chance": 1, "triggers_v": 2, "log_path": str(folder / "companion-log.jsonl"),
             "triggers": ["print_finished", "print_failed", "quota_high", "song_change", "long_work", "timer_done", "rain_soon"],
             "cooldowns": {"print_finished": 20, "print_failed": 20, "quota_high": 60, "song_change": 90,
                           "rain_soon": 60, "timer_done": 3}},
        ],
    }
