import unittest

from modules.companion_brain import RuleBrain
from tools import companion_eval


class CompanionEvalTests(unittest.TestCase):
    def test_rule_brain_is_correct_on_the_fixed_event_set(self):
        """No key, no network: the free brain must get every fixed case right."""
        rows, score = companion_eval.evaluate(RuleBrain())
        self.assertEqual([(r["case"], r["problems"]) for r in rows if not r["ok"]], [])
        self.assertEqual(score, 1.0)
        self.assertGreaterEqual(len(rows), 12)

    def test_a_made_up_number_or_a_wrong_face_fails_the_case(self):
        class Liar:
            def respond(self, event, world):
                from modules.companion_brain import Reply
                return Reply("貓咪手機架印好了，花了 999 分鐘。", "sleepy", via="liar")
        row = companion_eval.run_case(Liar(), companion_eval.CASES[0])
        self.assertFalse(row["ok"])
        self.assertTrue(any("999" in p for p in row["problems"]))
        self.assertTrue(any("表情" in p for p in row["problems"]))

    def test_a_working_day_is_not_noisy(self):
        day = companion_eval.simulate_day()
        self.assertLessEqual(day["max_per_hour"], 5, day)
        self.assertLessEqual(day["by_event"].get("song_change", 0), 16, day)   # at most two an hour
        self.assertEqual(day["by_event"].get("quota_high"), 1, day)            # wobbling at the threshold: said once
        for must in ("print_finished", "print_failed", "rain_soon", "timer_done", "long_work"):
            self.assertGreaterEqual(day["by_event"].get(must, 0), 1, must)     # the important ones still get through
        self.assertEqual(day, companion_eval.simulate_day())                   # same script, same result


if __name__ == "__main__":
    unittest.main()
