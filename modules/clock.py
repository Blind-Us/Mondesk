"""Custom clock widget. The time itself is drawn by the browser (web/clock-widget.js), every
second and without waiting for a poll; this module only hands the card its look:
style (digital / analog / flip / ring / words), 12- or 24-hour, seconds, date, colour and
whether a second page with a timer is added."""
from . import BaseModule

STYLES = ("digital", "analog", "flip", "ring", "words")


class Module(BaseModule):
    type = "clock"
    default_interval = 60  # nothing changes until settings are saved (which rebuilds the module)

    def poll(self):
        s = self.spec
        return {
            "style": s.get("style") if s.get("style") in STYLES else "digital",
            "hour12": bool(s.get("hour12", False)),
            "seconds": bool(s.get("seconds", True)),
            "date": bool(s.get("date", True)),
            "color": str(s.get("color") or ""),
            "timer": bool(s.get("timer", False)),  # second page: countdown timer / stopwatch
        }
