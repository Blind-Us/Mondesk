import json
import threading
import unittest
import urllib.request
from http.server import ThreadingHTTPServer

import server


class FakeHub:
    def __init__(self):
        self.calls = []
        self.config = {}

    def action(self, module, name, **params):
        self.calls.append((module, name, params))
        return {}


class ActionRouteTests(unittest.TestCase):
    def test_seek_time_forwards_position_and_track(self):
        # the lyrics progress slider sends seek_time; without the position the seek always failed
        app = type("App", (), {})()
        app.hub = FakeHub()
        http = ThreadingHTTPServer(("127.0.0.1", 0), server.make_handler(app))
        threading.Thread(target=http.serve_forever, daemon=True).start()
        try:
            for action in ("seek_time", "seek"):
                req = urllib.request.Request(
                    f"http://127.0.0.1:{http.server_port}/api/action",
                    data=json.dumps({"module": "music", "action": action, "track": "t1", "position": 42.5}).encode(),
                    headers={"Content-Type": "application/json", "X-DeskMon": "1"})
                self.assertTrue(json.load(urllib.request.urlopen(req))["ok"])
        finally:
            http.shutdown()
            http.server_close()
        self.assertEqual(app.hub.calls, [("music", "seek_time", {"position": 42.5, "track": "t1"}),
                                         ("music", "seek", {"position": 42.5, "track": "t1"})])


if __name__ == "__main__":
    unittest.main()


class SideScreenTests(unittest.TestCase):
    def test_side_screen_goes_to_the_extension_with_the_track(self):
        from unittest.mock import patch
        from modules.media import Module
        m = Module({"id": "music", "type": "media"})
        m.last_media = {"browser_bridge": False, "track": "x"}
        with self.assertRaisesRegex(RuntimeError, r"Alt\+Shift\+D"):  # no extension tab: say how instead
            m.action("side_screen")
        m.last_media = {"browser_bridge": True, "track": "web:abc"}
        with patch("modules.apple_bridge.bridge.action") as act:
            self.assertEqual(m.action("side_screen", track="web:abc"), "side_screen")
        act.assert_called_once_with("side-screen", "web:abc")
