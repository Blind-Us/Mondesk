"""Volume and monitor brightness.

Windows: volume through Core Audio (pycaw); brightness through DDC/CI (monitorcontrol) for
         monitors that support it. Many small USB/HDMI panels don't: the panel page then
         offers a software dim instead (handled in the browser, always works).
Linux:   `pactl` for volume, `brightnessctl` for a laptop backlight.
"""
import subprocess
import sys
import threading
import time
import warnings

from . import BaseModule

BRIGHTNESS_EVERY = 30  # seconds; DDC/CI reads are slow (tens to hundreds of ms per monitor)


def _run(cmd):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=3).stdout.strip()
    except Exception:
        return ""


class WindowsAudio:
    def _endpoint(self):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", FutureWarning)
            import comtypes
        comtypes.CoInitialize()  # each hub / HTTP thread needs its own COM apartment
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", FutureWarning)
            from pycaw.pycaw import AudioUtilities
        return AudioUtilities.GetSpeakers().EndpointVolume

    def get(self):
        ev = self._endpoint()
        return round(ev.GetMasterVolumeLevelScalar() * 100), bool(ev.GetMute())

    def set(self, value):
        self._endpoint().SetMasterVolumeLevelScalar(max(0.0, min(1.0, value / 100)), None)

    def mute(self, on):
        self._endpoint().SetMute(1 if on else 0, None)


class PulseAudio:
    def get(self):
        vol = _run(["pactl", "get-sink-volume", "@DEFAULT_SINK@"])
        pct = next((int(p.rstrip("%")) for p in vol.split() if p.endswith("%")), None)
        if pct is None:
            raise RuntimeError("找不到 pactl")
        return pct, "yes" in _run(["pactl", "get-sink-mute", "@DEFAULT_SINK@"])

    def set(self, value):
        _run(["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{int(value)}%"])

    def mute(self, on):
        _run(["pactl", "set-sink-mute", "@DEFAULT_SINK@", "1" if on else "0"])


class DDCBrightness:
    """Monitors that answer DDC/CI. Index = order Windows lists them."""

    def read(self):
        from monitorcontrol import get_monitors
        out = []
        for i, m in enumerate(get_monitors()):
            try:
                with m:
                    out.append({"index": i, "name": f"螢幕 {i + 1}", "value": int(m.get_luminance())})
            except Exception:
                continue  # this monitor doesn't support DDC/CI
        return out

    def set(self, index, value):
        from monitorcontrol import get_monitors
        monitors = list(get_monitors())
        with monitors[index] as m:
            m.set_luminance(int(max(0, min(100, value))))


class BacklightBrightness:
    def read(self):
        cur, top = _run(["brightnessctl", "get"]), _run(["brightnessctl", "max"])
        if not (cur.isdigit() and top.isdigit() and int(top)):
            return []
        return [{"index": 0, "name": "螢幕", "value": round(int(cur) / int(top) * 100)}]

    def set(self, index, value):
        _run(["brightnessctl", "set", f"{int(value)}%"])


class Module(BaseModule):
    type = "system"
    default_interval = 2

    def __init__(self, spec):
        super().__init__(spec)
        win = sys.platform == "win32"
        self.audio = WindowsAudio() if win else PulseAudio()
        self.bright = DDCBrightness() if win else BacklightBrightness()
        self.monitors, self.bright_at, self.bright_err = [], 0, None
        self.lock = threading.Lock()

    def _brightness(self, force=False):
        if force or time.time() - self.bright_at > BRIGHTNESS_EVERY:
            self.bright_at = time.time()
            try:
                self.monitors = self.bright.read()
                self.bright_err = None
            except Exception as e:  # e.g. monitorcontrol missing
                self.monitors, self.bright_err = [], f"{type(e).__name__}"
        return self.monitors

    def poll(self):
        with self.lock:
            try:
                volume, muted = self.audio.get()
                audio_err = None
            except Exception as e:
                volume, muted, audio_err = None, None, f"無法讀取音量（{type(e).__name__}）"
            return {"_status": "ok" if volume is not None else "offline", "volume": volume, "muted": muted,
                    "audio_error": audio_err, "monitors": self._brightness()}

    def action(self, name, value=None, index=None):
        with self.lock:
            if name == "set_volume":
                self.audio.set(float(value))
                if float(value) > 0:
                    self.audio.mute(False)
            elif name == "toggle_mute":
                self.audio.mute(not self.audio.get()[1])
            elif name == "set_brightness":
                self.bright.set(int(index or 0), float(value))
                for m in self.monitors:
                    if m["index"] == int(index or 0):
                        m["value"] = int(float(value))
            else:
                raise ValueError("不支援的操作")
        return self.poll()
