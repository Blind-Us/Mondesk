import json
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace

from modules.companion import Module as Companion
from modules.companion_events import Event
from modules.event_center import EventCenter, EventWatcher, client_event


def printer(stage):
    return {"id": "printer", "type": "bambu", "title": "X2D", "data": {"stage": stage, "file": "box"}}


class EventCenterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def test_record_notifies_listeners_and_keeps_the_outcome(self):
        center, heard = EventCenter(), []
        center.subscribe(heard.append)
        entry = center.record(Event("print_finished", {"file": "box"}))
        self.assertEqual((entry["name"], entry["label"], entry["outcome"]), ("print_finished", "列印完成", "detected"))
        self.assertEqual(heard[0].entry_id, entry["id"])
        center.update(entry["id"], outcome="spoken", line="印好了", emotion="happy", secret="x")
        got = center.recent()[0]
        self.assertEqual((got["outcome"], got["line"]), ("spoken", "印好了"))
        self.assertNotIn("secret", got)
        center.record(Event("quota_high"), notify=False)  # test buttons: history only
        self.assertEqual(len(heard), 1)

    def test_a_broken_listener_does_not_hide_the_event(self):
        center, heard = EventCenter(), []
        center.subscribe(lambda ev: 1 / 0)
        center.subscribe(heard.append)
        center.record(Event("timer_done"))
        self.assertEqual(len(heard), 1)

    def test_history_survives_a_restart(self):
        path = self.tmp / "events.jsonl"
        first = EventCenter(path)
        entry = first.record(Event("print_failed", {"reason": "stopped"}))
        first.update(entry["id"], outcome="spoken", line="列印停止了")
        again = EventCenter(path)
        self.assertEqual([(e["name"], e["outcome"], e["line"]) for e in again.recent()], [("print_failed", "spoken", "列印停止了")])
        self.assertEqual(again.record(Event("timer_done"))["id"], entry["id"] + 1)  # ids continue
        path.write_text("not json\n", encoding="utf-8")
        self.assertEqual(EventCenter(path).recent(), [])  # a damaged file is ignored, not fatal

    def test_only_the_panels_own_events_can_be_posted(self):
        center = EventCenter()
        self.assertEqual(client_event(center, "timer_done", {"minutes": 5, "bad": {"x": 1}})["detail"], {"minutes": 5})
        for name in ("print_finished", "quota_high", "nope", None):
            with self.assertRaises(ValueError):
                client_event(center, name)

    def test_watcher_detects_without_any_companion(self):
        states = [printer("RUNNING")]
        hub = SimpleNamespace(module_states=lambda: states, running=True)
        center = EventCenter()
        watcher = EventWatcher(hub, center)
        watcher.tracker.idle_fn = lambda: 9999  # nobody at the keyboard
        self.assertEqual(watcher.step(), [])    # the first look is only a baseline
        states[0] = printer("FINISH")
        self.assertEqual([e.name for e in watcher.step()], ["print_finished"])
        self.assertEqual(center.recent()[0]["detail"]["file"], "box")

    def test_long_work_is_reported_once_then_hourly(self):
        hub = SimpleNamespace(module_states=lambda: [], running=True)
        center = EventCenter()
        watcher = EventWatcher(hub, center, work_minutes=120)
        watcher.tracker.idle_fn = lambda: 0
        now, names = 1_000_000, []
        for minute in range(0, 200):
            names += [e.name for e in watcher.step(now + minute * 60)]
        self.assertEqual(names, ["long_work", "long_work"])  # at 120 and again at 180 minutes
        self.assertEqual(center.work_minutes, 199)

    def test_companion_listens_to_the_centre_and_reports_back(self):
        center = EventCenter()
        hub = SimpleNamespace(module_states=lambda: [printer("FINISH")], events=center)
        m = Companion({"id": "companion", "type": "companion", "provider": "rule", "log_path": str(self.tmp / "log.jsonl"),
                       "triggers": ["print_finished"], "triggers_v": 2})
        m.hub = hub
        m.start()
        try:
            spoken = center.record(Event("print_finished", {"file": "box"}))
            muted = center.record(Event("quota_high", {"title": "Claude"}))
            again = center.record(Event("print_finished", {"file": "box"}))
            for _ in range(100):
                if center.recent()[0]["outcome"] == "spoken":
                    break
                time.sleep(0.02)
            by_id = {e["id"]: e for e in center.recent()}
            self.assertEqual(by_id[spoken["id"]]["outcome"], "spoken")
            self.assertIn("box", by_id[spoken["id"]]["line"])
            self.assertEqual(by_id[muted["id"]]["outcome"], "off")        # that reminder is switched off
            self.assertEqual(by_id[again["id"]]["outcome"], "cooldown")   # said a moment ago
            self.assertEqual(m.poll()["event"], "print_finished")
        finally:
            m.stop()
        self.assertEqual(center.listeners, [])

    def test_new_triggers_are_on_for_configs_written_before_them(self):
        old = Companion({"id": "c", "type": "companion", "triggers": ["print_finished"], "log_path": str(self.tmp / "a")})
        self.assertLessEqual({"timer_done", "rain_soon"}, old.triggers)
        saved = Companion({"id": "c", "type": "companion", "triggers": ["print_finished"], "triggers_v": 2,
                           "log_path": str(self.tmp / "b")})
        self.assertEqual(saved.triggers, {"print_finished"})  # the user unticked them: stays off


class HubTests(unittest.TestCase):
    def test_state_and_diagnostics_carry_the_events(self):
        import server
        tmp = Path(tempfile.mkdtemp())
        cfg = tmp / "config.json"
        cfg.write_text(json.dumps({"modules": [{"id": "clock", "type": "clock"}]}), encoding="utf-8")
        app = server.App(cfg)
        try:
            self.assertEqual(app.data_dir, tmp)  # a config given by path keeps its files next to it
            client_event(app.hub.events, "timer_done")
            self.assertEqual([e["name"] for e in app.hub.snapshot()["events"]], ["timer_done"])
            d = server.diagnostics(app)
            self.assertEqual((d["app"]["demo"], d["modules"][0]["id"], d["events"][0]["label"]), (False, "clock", "計時結束"))
            self.assertTrue((tmp / "events.jsonl").exists())
            # switching the context mode is saved without restarting the modules
            hub = app.hub
            self.assertEqual(app.patch_display({"mode": "focus", "layout": "ignored"})["mode"], "focus")
            self.assertIs(app.hub, hub)
            self.assertEqual(json.loads(cfg.read_text(encoding="utf-8"))["display"], {"mode": "focus"})
            with self.assertRaises(ValueError):
                app.patch_display({"mode": "party"})
        finally:
            app.hub.stop()


if __name__ == "__main__":
    unittest.main()
