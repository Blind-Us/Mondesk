import unittest

from modules.clock import Module


class ClockTests(unittest.TestCase):
    def test_defaults(self):
        data = Module({"id": "clock", "type": "clock"}).poll()
        self.assertEqual(data, {"style": "digital", "hour12": False, "seconds": True,
                                "date": True, "color": "", "timer": False})

    def test_options_pass_through_and_bad_style_falls_back(self):
        data = Module({"type": "clock", "style": "flip", "hour12": True, "timer": True, "color": "#7cc4ff"}).poll()
        self.assertEqual((data["style"], data["hour12"], data["timer"], data["color"]), ("flip", True, True, "#7cc4ff"))
        self.assertEqual(Module({"type": "clock", "style": "huge"}).poll()["style"], "digital")


if __name__ == "__main__":
    unittest.main()
