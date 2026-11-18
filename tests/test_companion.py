from unittest.mock import patch
import os
import json
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace

from modules import companion_brain as brain
from modules.companion import Module
from modules.companion_brain import AnthropicBrain, BrainError, OllamaBrain, RuleBrain, World, parse_reply
from modules.companion_events import Event, EventDetector, Limiter, WorkTracker


def printer(stage, **extra):
    return {"id": "printer", "type": "bambu", "title": "X2D", "data": {"stage": stage, "file": "box", **extra}}


def music(title, playing=True):
    return {"id": "music", "type": "media", "data": {"title": title, "artist": "A", "playing": playing}}


def quota(pct, provider="claude"):
    return {"id": provider, "type": "tokens", "title": provider.title(),
            "data": {"provider": provider, "today": {"input": 1, "output": 1},
                     "windows": [{"label": "5h", "used_percent": pct, "resets_at": None}]}}


class DetectorTests(unittest.TestCase):
    def names(self, det, *snapshots):
        return [[e.name for e in det.feed(s)] for s in snapshots]

    def test_each_printer_has_its_own_events_and_is_named(self):
        det = EventDetector()
        two = lambda a, b: [{**printer(a), "title": "左邊"}, {**printer(b), "id": "printer2", "title": "右邊", "data": {"stage": b, "file": "gear"}}]
        got = [det.feed(s) for s in (two("RUNNING", "RUNNING"), two("FINISH", "RUNNING"), two("FINISH", "FAILED"))]
        self.assertEqual([[e.name for e in g] for g in got], [[], ["print_finished"], ["print_failed"]])
        self.assertEqual((got[1][0].detail["printer"], got[2][0].detail["printer"], got[2][0].detail["file"]), ("左邊", "右邊", "gear"))
        line = RuleBrain().respond(got[2][0], World(two("FINISH", "FAILED"))).line
        self.assertIn("右邊", line)
        one = EventDetector()
        one.feed([printer("RUNNING")])
        self.assertEqual(one.feed([printer("FINISH")])[0].detail["printer"], "")   # one printer: no name needed

    def test_first_snapshot_is_only_a_baseline(self):
        det = EventDetector()
        self.assertEqual(self.names(det, [printer("FINISH"), music("x"), quota(95)]), [[]])

    def test_print_transitions(self):
        self.assertEqual(self.names(EventDetector(), [printer("RUNNING")], [printer("FINISH")]), [[], ["print_finished"]])
        self.assertEqual(self.names(EventDetector(), [printer("RUNNING")], [printer("FAILED")]), [[], ["print_failed"]])
        det = EventDetector()
        det.feed([printer("PREPARE")])
        stopped = det.feed([printer("IDLE")])
        self.assertEqual(stopped[0].detail["reason"], "stopped")
        self.assertEqual(self.names(EventDetector(), [printer("IDLE")], [printer("FINISH")]), [[], []])

    def test_pause_is_only_a_failure_with_an_error(self):
        self.assertEqual(self.names(EventDetector(), [printer("RUNNING")], [printer("PAUSE")]), [[], []])
        det = EventDetector()
        got = self.names(det, [printer("RUNNING")], [printer("PAUSE", print_error=123)], [printer("PAUSE", print_error=123)])
        self.assertEqual(got, [[], ["print_failed"], []])

    def test_printer_going_offline_keeps_the_last_stage(self):
        det = EventDetector()
        offline = {"id": "printer", "type": "bambu", "data": {"message": "連線中…"}}
        self.assertEqual(self.names(det, [printer("RUNNING")], [offline], [printer("FINISH")]), [[], [], ["print_finished"]])

    def test_song_change_only_while_playing(self):
        det = EventDetector()
        got = self.names(det, [music("a")], [music("b")], [music("c", playing=False)], [music("c")])
        self.assertEqual(got, [[], ["song_change"], [], []])

    def test_quota_fires_once_per_crossing_with_hysteresis(self):
        det = EventDetector(80)
        got = self.names(det, [quota(50)], [quota(82)], [quota(90)], [quota(78)], [quota(81)], [quota(70)], [quota(85)])
        self.assertEqual(got, [[], ["quota_high"], [], [], [], [], ["quota_high"]])

    def test_quota_is_said_once_per_period_even_when_the_reading_drops_out(self):
        def q(pct, resets_at):
            m = quota(pct)
            m["data"]["windows"][0]["resets_at"] = resets_at
            return m
        det = EventDetector(80)
        got = self.names(det, [q(50, 1000000)], [q(95, 1000000)], [q(0, 1000000)], [q(95, 1000000)], [q(96, 1000030)],
                         [q(10, 1600000)], [q(90, 1600000)])
        #                 first    over: said        reading lost      back: not again   same period        reset       full again: said
        self.assertEqual(got, [[], ["quota_high"], [], [], [], [], ["quota_high"]])

    def test_quota_uses_budgets_when_there_are_no_official_windows(self):
        det = EventDetector(80)
        m = {"id": "claude", "type": "tokens", "data": {"provider": "claude", "today": {"input": 1, "output": 1},
                                                       "budget_5h": 100, "window5h": {"input": 10, "output": 0}}}
        det.feed([m])
        m["data"]["window5h"] = {"input": 85, "output": 0}
        self.assertEqual([e.detail["used_percent"] for e in det.feed([m])], [85])


class WorkAndLimitTests(unittest.TestCase):
    def test_work_session_resets_after_a_break(self):
        idle = {"s": 0}
        t = WorkTracker(break_minutes=10, idle_fn=lambda: idle["s"])
        now = 1_000_000
        for minute in range(181):                         # sampled every minute while typing
            got = t.update(now + minute * 60)
        self.assertEqual(got, 180)
        idle["s"] = 15 * 60                               # then away for 15 minutes
        self.assertEqual(t.update(now + 195 * 60), 0)
        idle["s"] = 0
        self.assertEqual(t.update(now + 196 * 60), 0)    # back: a new session starts
        self.assertEqual(t.update(now + 206 * 60), 10)

    def test_work_falls_back_to_ai_activity(self):
        t = WorkTracker(idle_fn=lambda: None)          # no OS idle time (Linux): use Codex/Claude activity
        for minute in range(51):
            got = t.update(5000 + minute * 60, ai_last_activity=5000 + minute * 60 - 30)
        self.assertEqual(got, 50)
        self.assertEqual(t.update(5000 + 80 * 60, ai_last_activity=5000 + 50 * 60), 0)  # quiet for 30 min

    def test_cooldowns_and_hourly_cap(self):
        clock = {"t": 0}
        lim = Limiter({"tap": 10}, max_per_hour=2, clock=lambda: clock["t"])
        self.assertTrue(lim.ready("tap"))
        lim.mark("tap")
        self.assertFalse(lim.ready("tap"))
        clock["t"] = 11
        self.assertTrue(lim.ready("tap"))
        lim.record_call(); lim.record_call()
        self.assertFalse(lim.can_call())
        clock["t"] = 3700
        self.assertTrue(lim.can_call())


# ---------------------------------------------------------------- fake Anthropic client
def block(type, **kw):
    return SimpleNamespace(type=type, **kw)


def resp(stop, *content, model="claude-opus-5-5"):
    return SimpleNamespace(stop_reason=stop, content=list(content), model=model,
                           usage=SimpleNamespace(input_tokens=100, output_tokens=20,
                                                 cache_creation_input_tokens=0, cache_read_input_tokens=0))


class FakeClient:
    def __init__(self, *responses):
        self.responses, self.calls = list(responses), []
        self.messages = SimpleNamespace(create=self._create("messages"))
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create("beta")))

    def _create(self, kind):
        def create(**kw):
            self.calls.append((kind, {**kw, "messages": list(kw["messages"])}))
            return self.responses.pop(0)
        return create


def world():
    return World([printer("FINISH", progress=100, bed=58, bed_target=0), music("晴天"), quota(40)], work_minutes=30)


class AnthropicBrainTests(unittest.TestCase):
    def test_tool_loop_then_structured_reply(self):
        client = FakeClient(
            resp("tool_use", block("thinking", thinking=""), block("tool_use", id="t1", name="get_printer_status", input={})),
            resp("end_turn", block("text", text=json.dumps({"line": "印好了！記得等熱床降溫再拿。", "emotion": "happy"}))))
        reply = AnthropicBrain("claude-opus-5-5", client=client).respond(Event("print_finished", {"file": "box"}), world())
        self.assertEqual((reply.line, reply.emotion, reply.tools), ("印好了！記得等熱床降溫再拿。", "happy", ["get_printer_status"]))
        self.assertEqual(reply.usage["requests"], 2)
        kind, first = client.calls[0]
        self.assertEqual(kind, "beta")  # Opus 5.5: server-side refusal fallback
        self.assertEqual(first["fallbacks"], "default")
        self.assertEqual(first["output_config"]["effort"], "low")
        self.assertEqual(first["output_config"]["format"]["schema"]["properties"]["emotion"]["enum"], list(brain.EMOTIONS))
        self.assertEqual([t["name"] for t in first["tools"]], ["get_printer_status", "get_now_playing", "get_ai_quota", "get_weather"])
        self.assertNotIn("thinking", first)  # Opus 5.5 thinking can't be configured off; effort controls it
        _, second = client.calls[1]
        result = second["messages"][-1]["content"][0]
        self.assertEqual((result["type"], result["tool_use_id"]), ("tool_result", "t1"))
        self.assertEqual(json.loads(result["content"])["stage"], "FINISH")
        self.assertEqual(second["messages"][1]["content"][0].type, "thinking")  # assistant turn passed back unchanged

    def test_haiku_uses_plain_messages_endpoint(self):
        client = FakeClient(resp("end_turn", block("text", text='{"line": "好聽", "emotion": "happy"}'), model="claude-haiku-5-5"))
        reply = AnthropicBrain("claude-haiku-5-5", client=client).respond(Event("song_change"), world())
        self.assertEqual(client.calls[0][0], "messages")
        self.assertNotIn("fallbacks", client.calls[0][1])
        self.assertEqual(reply.served_by, "claude-haiku-5-5")

    def test_refusal_and_runaway_tool_loops_raise(self):
        with self.assertRaisesRegex(BrainError, "拒絕"):
            AnthropicBrain(client=FakeClient(resp("refusal"))).respond(Event("tap"), world())
        loop = [resp("tool_use", block("tool_use", id=f"t{i}", name="get_ai_quota", input={})) for i in range(5)]
        with self.assertRaisesRegex(BrainError, "過多"):
            AnthropicBrain(client=FakeClient(*loop)).respond(Event("tap"), world())

    def test_reply_validation(self):
        self.assertEqual(parse_reply('{"line": "  嗨 ", "emotion": "angry"}'), ("嗨", "neutral"))
        line, _ = parse_reply(json.dumps({"line": "很長的句子。" * 20, "emotion": "happy"}))
        self.assertLessEqual(len(line), brain.MAX_LINE)
        for bad in ("not json", "[]", '{"line": "", "emotion": "happy"}'):
            with self.assertRaises(BrainError):
                parse_reply(bad)


class OtherBrainTests(unittest.TestCase):
    def test_ollama_tool_call_then_json(self):
        replies = [{"message": {"role": "assistant", "content": "", "tool_calls": [{"function": {"name": "get_now_playing", "arguments": {}}}]}},
                   {"message": {"role": "assistant", "content": '{"line": "晴天耶", "emotion": "happy"}'}, "eval_count": 9}]
        sent = []
        ob = OllamaBrain("qwen3:8b", post=lambda body: (sent.append(body), replies.pop(0))[1])
        reply = ob.respond(Event("song_change"), world())
        self.assertEqual((reply.line, reply.via, reply.tools), ("晴天耶", "ollama:qwen3:8b", ["get_now_playing"]))
        self.assertEqual(sent[1]["messages"][-1]["role"], "tool")

    def test_rule_brain_only_states_known_facts(self):
        self.assertIn("box", RuleBrain().respond(Event("print_finished"), world()).line)
        empty = World([])
        self.assertEqual(RuleBrain().respond(Event("tap"), empty).line, "目前一切平靜，沒什麼特別的事。")
        scen = World([], scenario=brain.SCENARIOS["quota_high"])
        self.assertIn("86%", RuleBrain().respond(Event("quota_high"), scen).line)


# ---------------------------------------------------------------- the module
class FailingBrain:
    name = "claude-opus-5-5"

    def respond(self, event, world):
        raise BrainError("API 金鑰無效或未設定")


class ModuleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.states = [printer("RUNNING")]

    def module(self, **spec):
        m = Module({"id": "companion", "type": "companion", "log_path": str(self.tmp / "log.jsonl"),
                    **spec})
        m.hub = SimpleNamespace(module_states=lambda: [*self.states, {"id": "companion", "type": "companion", "data": {}}])
        return m

    def wait_line(self, m, seq=0):
        for _ in range(100):
            data = m.poll()
            if data["seq"] > seq and not data["busy"]:
                return data
            time.sleep(0.02)
        self.fail("companion never answered")

    def test_poll_turns_printer_changes_into_speech(self):
        m = self.module(provider="rule")
        m.start()
        try:
            m.poll()
            self.states = [printer("FINISH")]
            data = self.wait_line(m)
            self.assertEqual((data["event"], data["emotion"], data["via"]), ("print_finished", "happy", "rule"))
            self.assertIn("box", data["line"])
        finally:
            m.stop()

    def test_offer_respects_switches_cooldowns_and_song_chance(self):
        m = self.module(triggers=["song_change"], provider="rule")
        self.assertEqual(m.offer(Event("print_finished")), (False, "off"))
        m.random = lambda: 0.99
        self.assertEqual(m.offer(Event("song_change")), (False, "skipped"))
        m.random = lambda: 0.0
        self.assertEqual(m.offer(Event("song_change")), (True, "queued"))
        self.assertEqual(m.offer(Event("song_change")), (False, "cooldown"))
        self.assertEqual(m.offer(Event("print_finished"), manual=True), (True, "queued"))  # test buttons
        self.assertEqual(m._next().name, "print_finished")  # higher priority first

    def test_api_failure_falls_back_to_rule_line_and_counts_against_cap(self):
        m = self.module(provider="anthropic", api_key="sk-test", max_calls_per_hour=1)
        m.brains["claude-opus-5-5"] = FailingBrain()
        m.start()
        try:
            m.action("trigger", event="quota_high", simulate=True)
            first = self.wait_line(m)
            self.assertEqual((first["via"], first["fallback_reason"]), ("rule", "API 金鑰無效或未設定"))
            self.assertIn("86%", first["line"])
            m.action("trigger", event="tap", simulate=True)
            second = self.wait_line(m, first["seq"])
            self.assertIn("上限", second["fallback_reason"])
        finally:
            m.stop()
        # the cap and the last line survive a restart (saving settings recreates the module)
        again = self.module(provider="anthropic", api_key="sk-test", max_calls_per_hour=1)
        again._load_log()
        self.assertFalse(again.limiter.can_call())
        self.assertEqual(again._state()["line"], second["line"])
        log = [json.loads(x) for x in (self.tmp / "log.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual([e["billed"] for e in log], [True, False])

    def test_small_events_use_the_small_model(self):
        m = self.module(model="claude-opus-5-5", small_model="claude-haiku-5-5", api_key="sk-test")
        self.assertEqual(m._brain_for(Event("song_change")).model, "claude-haiku-5-5")
        self.assertEqual(m._brain_for(Event("print_failed")).model, "claude-opus-5-5")
        rule_only = self.module(provider="rule")
        self.assertIs(rule_only._brain_for(Event("tap")), rule_only.rule)
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": ""}):
            no_key = self.module(provider="anthropic")  # no key anywhere: no call that can only fail
            self.assertIs(no_key._brain_for(Event("print_failed")), no_key.rule)

    def test_state_carries_the_selected_character(self):
        data = self.module(character="kid")._state()
        self.assertEqual(data["character"]["id"], "kid")
        self.assertIn("v", data["character"]["faces"]["talk_open"])
        self.assertEqual(self.module(character="missing")._state()["character"]["id"], "emoji")  # falls back

    def test_unknown_manual_event_is_rejected(self):
        with self.assertRaises(ValueError):
            self.module().action("trigger", event="explode")


class ReportTests(unittest.TestCase):
    def test_cost_estimate(self):
        from tools.companion_report import cost, summarise
        usage = {"input_tokens": 1_000_000, "output_tokens": 100_000}
        self.assertAlmostEqual(cost("claude-opus-5-5", usage), 6.0)
        self.assertAlmostEqual(cost("claude-haiku-5-5", usage), 0.15)
        self.assertEqual(cost("rule", usage), 0)
        rows = [{"brain": "claude-opus-5-5", "latency": 2.0, "usage": usage}, {"brain": "claude-opus-5-5", "latency": 4.0,
                 "usage": {}, "error": "API 錯誤 500"}]
        s = summarise(rows)[0]
        self.assertEqual((s["lines"], s["fallbacks"], s["latency_avg"], s["cost_usd"]), (2, 1, 2.0, 6.0))


class ServerTests(unittest.TestCase):
    def test_api_key_never_reaches_the_settings_page(self):
        import server
        cfg = {"modules": [{"id": "companion", "type": "companion", "api_key": "sk-ant-secret"}]}
        masked = server.mask_secrets(cfg)
        self.assertEqual(masked["modules"][0]["api_key"], server.MASK)
        self.assertEqual(server.restore_secrets(masked, cfg)["modules"][0]["api_key"], "sk-ant-secret")

    def test_hub_gives_modules_access_to_each_other(self):
        import server
        hub = server.Hub({"modules": [{"id": "companion", "type": "companion", "provider": "rule",
                                       "log_path": str(Path(tempfile.mkdtemp()) / "log.jsonl")}]})
        self.assertIs(hub.modules[0].hub, hub)
        self.assertEqual(hub.module_states()[0]["status"], "starting")


if __name__ == "__main__":
    unittest.main()
