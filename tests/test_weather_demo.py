import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from modules import demo, weather
from modules.companion_brain import RuleBrain, World
from modules.companion_events import Event, EventDetector


def forecast(now, pops, code=2):
    """An Open-Meteo style answer whose hourly rows start at the current local hour."""
    hours = [time.strftime("%Y-%m-%dT%H:00", time.gmtime(now - now % 3600 + i * 3600)) for i in range(len(pops))]
    return {"utc_offset_seconds": 0,
            "current": {"temperature_2m": 23.6, "apparent_temperature": 25.2, "weather_code": code, "is_day": 1, "precipitation": 0},
            "hourly": {"time": hours, "temperature_2m": [24 - i for i in range(len(pops))],
                       "precipitation_probability": pops, "weather_code": [61 if p >= 60 else 2 for p in pops]},
            "daily": {"temperature_2m_max": [27.4], "temperature_2m_min": [20.6], "precipitation_probability_max": [max(pops)]}}


class WeatherTests(unittest.TestCase):
    NOW = 1_800_000_000 + 600  # ten minutes past an hour

    def test_parse_rounds_and_finds_rain_in_the_next_hours(self):
        d = weather.parse(forecast(self.NOW, [10, 20, 70, 80, 10, 10, 10, 10, 10]), "台北", self.NOW)
        self.assertEqual((d["temp"], d["feels"], d["label"], d["icon"], d["high"], d["low"], d["rain_today"]),
                         (24, 25, "多雲", "partly", 27, 21, 80))
        self.assertEqual(len(d["hours"]), 6)
        self.assertEqual(d["rain_soon"], {"in_hours": 2, "probability": 70})  # the 70 % hour starts in under 2 h
        dry = weather.parse(forecast(self.NOW, [10, 20, 30, 40, 90, 90]), "台北", self.NOW)
        self.assertIsNone(dry["rain_soon"])  # rain five hours away is not "soon"

    def test_night_icons_and_unknown_codes(self):
        self.assertEqual(weather.describe(0, is_day=False), ("晴", "moon"))
        self.assertEqual(weather.describe(1234), ("—", "cloud"))
        self.assertEqual(weather.describe(None)[1], "cloud")

    def test_module_needs_a_place_and_keeps_the_last_forecast_when_offline(self):
        m = weather.Module({"id": "weather", "type": "weather"})
        m.start()
        self.assertEqual(m.poll()["message"], "尚未設定地點")
        m = weather.Module({"id": "weather", "type": "weather", "place": "台北", "latitude": 25.04, "longitude": 121.56})
        m.start()
        with patch.object(m, "fetch", return_value=forecast(time.time(), [10, 10, 10, 10, 10, 10])):
            self.assertEqual(m.poll()["temp"], 24)
        m.next = 0
        with patch.object(m, "fetch", side_effect=OSError("offline")), patch.object(m, "fetch_metno", side_effect=OSError("offline")):
            again = m.poll()
        self.assertEqual((again["temp"], again["_status"]), (24, "ok"))  # still shown
        self.assertIn("offline", again["error_detail"])
        fresh = weather.Module({"id": "w", "type": "weather", "latitude": 1, "longitude": 1})
        fresh.start()
        with patch.object(fresh, "fetch", side_effect=OSError("offline")), \
                patch.object(fresh, "fetch_metno", side_effect=OSError("offline")):
            self.assertEqual(fresh.poll()["_status"], "offline")

    def test_second_source_takes_over_when_the_first_is_unreachable(self):
        now = time.time()
        stamp = lambda i: time.strftime("%Y-%m-%dT%H:00:00Z", time.gmtime(now - now % 3600 + i * 3600))
        entry = lambda i, temp, symbol, mm: {"time": stamp(i), "data": {
            "instant": {"details": {"air_temperature": temp, "apparent_air_temperature": temp - 1}},
            "next_1_hours": {"summary": {"symbol_code": symbol}, "details": {"precipitation_amount": mm}}}}
        metno = {"properties": {"timeseries": [entry(0, 21.4, "partlycloudy_night", 0.0), entry(1, 22.0, "cloudy", 0.0),
                                               entry(2, 22.6, "lightrain", 0.8), entry(3, 23.0, "rain", 1.5)]}}
        d = weather.parse_metno(metno, "台北", now)
        self.assertEqual((d["temp"], d["feels"], d["label"], d["icon"]), (21, 20, "多雲", "partly-night"))
        self.assertEqual(d["rain_soon"], {"in_hours": 2, "probability": None})  # rain by amount: no percentage here
        self.assertIsNone(d["rain_today"])
        self.assertEqual(weather.describe_symbol("heavyrainshowersandthunder_day"), ("雷雨", "storm"))
        m = weather.Module({"id": "w", "type": "weather", "place": "台北", "latitude": 25.04, "longitude": 121.56})
        m.start()
        with patch.object(m, "fetch", side_effect=OSError("handshake timed out")) as first, \
                patch.object(m, "fetch_metno", return_value=metno):
            got = m.poll()
            self.assertEqual((got["provider"], got["temp"], got["_status"]), ("MET Norway", 21, "ok"))
            m.next = 0
            m.poll()
            self.assertEqual(first.call_count, 1)  # the dead host isn't asked again for an hour
        line = RuleBrain().respond(Event("rain_soon"), World([{"id": "w", "type": "weather", "data": got}])).line
        self.assertIn("2 小時", line)
        self.assertNotIn("%", line)

    def test_rain_event_fires_when_rain_appears_and_the_rule_brain_says_it(self):
        det = EventDetector()
        w = lambda soon: [{"id": "weather", "type": "weather", "data": {"temp": 24, "label": "多雲", "place": "台北", "rain_soon": soon}}]
        soon = {"in_hours": 2, "probability": 70}
        names = [[e.name for e in det.feed(w(s))] for s in (None, soon, soon, None, soon)]
        self.assertEqual(names, [[], ["rain_soon"], [], [], ["rain_soon"]])
        reply = RuleBrain().respond(Event("rain_soon"), World(w(soon)))
        self.assertEqual(reply.emotion, "worried")
        self.assertIn("2 小時", reply.line)
        self.assertIn("70%", reply.line)
        self.assertEqual(RuleBrain().respond(Event("timer_done"), World([])).emotion, "surprised")


class DemoTests(unittest.TestCase):
    def test_demo_printer_and_song_have_pictures(self):
        printer = demo.Module({"id": "printer", "type": "bambu"}, time.time())
        music = demo.Module({"id": "music", "type": "media"}, time.time())
        self.assertTrue(printer.poll()["preview"])
        self.assertEqual(music.poll()["art_url"], "/api/asset/music/cover?v=1")
        for module, name in ((printer, "preview"), (music, "cover")):
            body, mime = module.asset(name)
            self.assertEqual(mime, "image/svg+xml")
            self.assertTrue(body.lstrip().startswith(b"<svg"))

    def test_the_script_produces_the_same_events_every_loop(self):
        """Offline, repeatable acceptance data: one loop of the demo fed to the real detector."""
        det, names = EventDetector(80), []
        for t in range(0, int(demo.PERIOD) * 2, 1):
            t %= demo.PERIOD
            states = [{"id": "printer", "type": "bambu", "title": "示範", "data": demo.printer_at(t)},
                      {"id": "codex", "type": "tokens", "title": "Codex", "data": demo.quota_at("codex", t)},
                      {"id": "weather", "type": "weather", "data": demo.weather_at(t)}]
            names += [e.name for e in det.feed(states)]
        loop = ["rain_soon", "print_finished", "quota_high", "print_failed"]
        # the second loop runs in the same quota period (same reset time): the quota is not mentioned again
        self.assertEqual(names, loop + [n for n in loop if n != "quota_high"])

    def test_demo_app_runs_without_touching_user_settings_or_the_program_folder(self):
        import server
        root = Path(server.ROOT)
        before = {p.name for p in root.iterdir()}
        user = Path(tempfile.mkdtemp())
        with patch.dict(os.environ, {"LOCALAPPDATA": str(user), "XDG_CONFIG_HOME": str(user)}):
            app = server.App(demo=5)
            try:
                types = {m.type for m in app.hub.modules}
                self.assertLessEqual({"bambu", "media", "tokens", "weather", "companion", "clock"}, types)
                music = next(m for m in app.hub.modules if m.type == "media")
                data = music.poll()
                self.assertTrue(data["browser_bridge"] and data["lyrics"] == "ok")
                lines = json.loads(music.asset("lyrics")[0])["synced"]
                self.assertEqual(len(lines), len(demo.LINES))
                self.assertAlmostEqual(music.action("seek_time", position=20, track=data["track"])["position"], 20, delta=1.5)
                self.assertEqual(music.action("toggle", track=data["track"]), "toggle")
                self.assertFalse(music.poll()["playing"])
                with self.assertRaises(RuntimeError):
                    music.action("toggle", track="demo:99")
                app.save({**app.hub.config, "theme": {"background": "oled"}})  # editing the demo is allowed…
                self.assertEqual(app.hub.config["theme"], {"background": "oled"})
                self.assertTrue(server.diagnostics(app)["app"]["demo"])
            finally:
                app.hub.stop()
        self.assertEqual(list(user.rglob("*")), [])                       # …but nothing is saved for the user
        self.assertEqual({p.name for p in root.iterdir()} - before - {"__pycache__"}, set())  # nor next to the program

    def test_background_picture_is_checked_and_kept_in_the_user_folder(self):
        import server
        user = Path(tempfile.mkdtemp())
        png = b"\x89PNG\r\n\x1a\n" + b"0" * 64
        with patch.dict(os.environ, {"LOCALAPPDATA": str(user), "XDG_CONFIG_HOME": str(user)}):
            real, demo_app = type("A", (), {"demo": None})(), type("A", (), {"demo": 1})()
            self.assertEqual(server.background_type(png), "image/png")
            self.assertEqual(server.background_type(b"RIFF0000WEBPVP8 "), "image/webp")
            self.assertIsNone(server.background_type(b"RIFF0000WAVEfmt "))            # RIFF but not a picture
            self.assertIsNone(server.background_type(b"<svg onload=alert(1)>"))
            self.assertFalse(server.save_background(demo_app, png)["ok"])               # the demo never writes
            self.assertFalse(server.background_path().exists())
            self.assertFalse(server.save_background(real, b"<html>")["ok"])
            self.assertFalse(server.save_background(real, b"")["ok"])
            self.assertFalse(server.save_background(real, png + b"0" * server.MAX_BACKGROUND)["ok"])
            got = server.save_background(real, png)
            self.assertTrue(got["ok"] and got["v"].isalnum())
            path = server.background_path()
            self.assertEqual(path.read_bytes(), png)
            self.assertIn(user, path.parents)
            self.assertNotIn(Path(server.ROOT), path.parents)
            server.delete_background(demo_app)
            self.assertTrue(path.exists())                                              # the demo deletes nothing either
            server.delete_background(real)
            self.assertFalse(path.exists())

    def test_runtime_files_live_in_the_user_folder(self):
        import server
        from modules import companion, companion_characters, tokens
        from user_paths import user_data_dir
        user = Path(tempfile.mkdtemp())
        with patch.dict(os.environ, {"LOCALAPPDATA": str(user), "XDG_CONFIG_HOME": str(user)}):
            home = user_data_dir()
            self.assertEqual(home, user / "DeskMon")
            root = Path(server.ROOT)
            paths = [Path(tokens.Claude()._cache_path()), companion.user_folder() / "companion-log.jsonl",
                     companion_characters.user_dir()]
            for p in paths:
                self.assertIn(home, p.parents, p)
                self.assertNotIn(root, p.parents, p)


if __name__ == "__main__":
    unittest.main()
