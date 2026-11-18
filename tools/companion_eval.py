"""Fixed evaluation set for the Companion: is what it says correct, and how often does it talk?

    python tools/companion_eval.py                      # rule-based brain: offline, free
    python tools/companion_eval.py --brains rule,claude-haiku-5-5,ollama:qwen3:8b

Part 1, correctness. Each case is a pair of Mondesk snapshots (before / after). The real
detector must find the expected event, then the brain answers from the real tools. A line
passes when it
  * names the facts the case requires (file name, percentage, song title…),
  * contains no number that isn't in the data it could look up (nothing made up),
  * uses one of the expressions that fit, and stays within the length limit.
Part 2, interruptions. A scripted 8-hour day (two prints, a song every 4 minutes, a quota that
hovers around the threshold, rain, a timer, a long work session) goes through the real
cooldowns and the song chance; the report shows how many lines per hour would be spoken.

Model brains cost money (1-3 requests per case) and need the same key as the Companion.
The rule brain needs nothing, so this also runs in CI: tests/test_companion_eval.py.
"""
import argparse
import csv
import random
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from modules.companion import Module as Companion
from modules.companion_brain import MAX_LINE, BrainError, RuleBrain, World
from modules.companion_events import Event, EventDetector, Limiter

NOW = 1_800_000_000.0


def printer(stage, file="貓咪手機架", progress=64, **extra):
    return {"id": "printer", "type": "bambu", "title": "X2D",
            "data": {"stage": stage, "stage_label": stage, "file": file, "progress": progress, "remaining_min": 38,
                     "eta": NOW + 38 * 60, "nozzle": 220, "bed": 60, "print_error": 0, **extra}}


def music(title, artist="示範樂團", playing=True):
    return {"id": "music", "type": "media", "title": "Now Playing",
            "data": {"title": title, "artist": artist, "album": "示範專輯", "source": "Apple Music", "playing": playing,
                     "position": 5, "duration": 240, "sampled": NOW}}


def quota(pct, provider="claude", title="Claude"):
    return {"id": provider, "type": "tokens", "title": title,
            "data": {"provider": provider, "today": {"input": 1000, "output": 500},
                     "windows": [{"label": "5h", "used_percent": pct, "resets_at": NOW + 72 * 60},
                                 {"label": "7d", "used_percent": 41, "resets_at": NOW + 3 * 86400}]}}


def weather(soon=None, temp=24):
    return {"id": "weather", "type": "weather", "title": "天氣",
            "data": {"place": "台北", "temp": temp, "feels": temp + 2, "label": "多雲", "high": 27, "low": 21,
                     "rain_today": 80 if soon else 20, "rain_soon": soon}}


# name, before, after, expected event, expressions that fit, facts the line must contain
CASES = [
    ("列印完成", [printer("RUNNING", progress=99)], [printer("FINISH", progress=100)],
     "print_finished", ("happy",), ["貓咪手機架"]),
    ("列印失敗", [printer("RUNNING", file="齒輪盒蓋", progress=37)], [printer("FAILED", file="齒輪盒蓋", progress=37, print_error=50348044)],
     "print_failed", ("worried",), ["37"]),
    ("列印被停止", [printer("RUNNING")], [printer("IDLE", progress=None)],
     "print_failed", ("worried",), ["停"]),
    ("因錯誤暫停", [printer("RUNNING", progress=52)], [printer("PAUSE", progress=52, print_error=123)],
     "print_failed", ("worried",), ["52"]),
    ("額度偏高", [quota(72)], [quota(86)],
     "quota_high", ("worried",), ["Claude", "86"]),
    ("換歌", [music("第一首")], [music("第二首")],
     "song_change", ("happy", "neutral"), ["第二首"]),
    ("快下雨", [weather()], [weather({"in_hours": 2, "probability": 70})],
     "rain_soon", ("worried", "neutral"), ["雨"]),
    ("計時結束", [], [], "timer_done", ("surprised", "happy", "neutral"), ["時"]),
    ("連續工作", [], [], "long_work", ("sleepy", "worried"), ["休息", "動"]),   # either word
    ("點臉：列印中", [], [printer("RUNNING", progress=64), quota(23, "codex", "Codex")],
     "tap", ("neutral", "happy", "thinking"), ["64"]),
    ("點臉：額度快滿", [], [quota(91)], "tap", ("worried",), ["91"]),
    ("點臉：沒事", [], [], "tap", ("neutral", "happy", "sleepy"), []),
]
MANUAL = {"timer_done": {}, "long_work": {"minutes": 135}, "tap": {}}  # not found by diffing snapshots
ANY_OF = {"連續工作"}  # cases where one of the facts is enough


def numbers(text):
    return set(re.findall(r"\d+", str(text)))


def allowed_numbers(world, event):
    """Every number the brain could legitimately have read: all tools, the event, the work time."""
    seen = numbers(event.detail) | numbers(world.work_minutes)
    for tool in ("get_printer_status", "get_now_playing", "get_ai_quota", "get_weather"):
        seen |= numbers(World(world.modules, world.work_minutes, world.now).call(tool))
    hours, minutes = divmod(int(world.work_minutes), 60)
    return seen | {str(hours), str(minutes)}


def run_case(brain, case):
    name, before, after, expected, emotions, facts = case
    if expected in MANUAL:
        event = Event(expected, dict(MANUAL[expected]))
    else:
        detector = EventDetector(80)
        detector.feed(before)
        found = detector.feed(after)
        if [e.name for e in found] != [expected]:
            return {"case": name, "event": expected, "ok": False, "line": "", "emotion": "", "latency": 0,
                    "problems": [f"偵測到 {[e.name for e in found]}，應該是 {expected}"]}
        event = found[0]
    world = World(after, work_minutes=135 if expected == "long_work" else 20, now=NOW)
    started = time.time()
    try:
        reply = brain.respond(event, world)
    except BrainError as e:
        return {"case": name, "event": expected, "ok": False, "line": "", "emotion": "", "latency": round(time.time() - started, 2),
                "problems": [f"沒有回應：{e}"]}
    problems = []
    hit = [f for f in facts if f in reply.line]
    if facts and (not hit if name in ANY_OF else len(hit) != len(facts)):
        problems.append("缺少：" + "、".join(f for f in facts if f not in reply.line))
    made_up = numbers(reply.line) - allowed_numbers(world, event)
    if made_up:
        problems.append("資料裡沒有的數字：" + "、".join(sorted(made_up)))
    if reply.emotion not in emotions:
        problems.append(f"表情 {reply.emotion} 不合適（可以是 {'／'.join(emotions)}）")
    if len(reply.line) > MAX_LINE:
        problems.append(f"太長（{len(reply.line)} 字）")
    return {"case": name, "event": expected, "ok": not problems, "line": reply.line, "emotion": reply.emotion,
            "latency": round(time.time() - started, 2), "problems": problems, "long": len(reply.line) > 40}


# ---------------------------------------------------------------- part 2: a scripted day
def day_states(t):
    """Module snapshots at second t of an 8-hour working day."""
    hour = t / 3600
    if hour < 1.5:
        p = printer("RUNNING", progress=int(hour / 1.5 * 100))
    elif hour < 3:
        p = printer("FINISH", progress=100)
    elif hour < 5:
        p = printer("RUNNING", file="齒輪盒蓋", progress=int((hour - 3) / 2 * 37))
    elif hour < 5.2:
        p = printer("FAILED", file="齒輪盒蓋", progress=37, print_error=1)
    else:
        p = printer("IDLE", progress=None)
    # the quota climbs and then wobbles around the threshold: must not nag on every wobble
    pct = min(78 + hour * 2, 84) + (2 if int(t / 60) % 2 else -2) if hour > 1 else 40 + hour * 30
    playing = not 4 <= hour < 4.5                       # a lunch break without music
    rain = {"in_hours": 2, "probability": 70} if 6 <= hour < 7.5 else None
    return [p, quota(pct), music(f"第 {int(t // 240) + 1} 首", playing=playing), weather(rain)]


def simulate_day(hours=8, song_chance=0.4, cooldowns=None, seed=7):
    """How many lines the Companion would speak in each hour of the scripted day."""
    clock = {"t": NOW}
    companion = Companion({"id": "companion", "type": "companion", "provider": "rule", "song_chance": song_chance,
                           "triggers_v": 2, "log_path": str(Path(__import__("tempfile").mkdtemp()) / "log.jsonl")})
    companion.limiter = Limiter(cooldowns, companion.limiter.max_per_hour, clock=lambda: clock["t"])
    companion.random = random.Random(seed).random
    detector, spoken, detected = EventDetector(80), [], {}
    work_started = None
    for t in range(0, hours * 3600, 5):
        clock["t"] = NOW + t
        events = detector.feed(day_states(t))
        hour = t / 3600
        if 4 <= hour < 4.5:
            work_started = None                           # the lunch break ends the work session
        else:
            work_started = t if work_started is None else work_started
            if (t - work_started) // 60 >= 120:
                events.append(Event("long_work", {"minutes": (t - work_started) // 60}))
        if t == int(2.25 * 3600):
            events.append(Event("timer_done"))
        for ev in events:
            detected[ev.name] = detected.get(ev.name, 0) + (ev.name != "long_work")
            queued, _ = companion.offer(ev)
            if queued:
                spoken.append((t, ev.name))
                with companion.lock:
                    companion.pending.clear()
    per_hour = [sum(1 for t, _ in spoken if h * 3600 <= t < (h + 1) * 3600) for h in range(hours)]
    kinds = {}
    for _, name in spoken:
        kinds[name] = kinds.get(name, 0) + 1
    return {"per_hour": per_hour, "total": len(spoken), "max_per_hour": max(per_hour), "by_event": kinds,
            "detected": detected}


def evaluate(brain):
    rows = [run_case(brain, c) for c in CASES]
    return rows, sum(r["ok"] for r in rows) / len(rows)


def main():
    from tools.companion_bench import make_brain
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--brains", default="rule", help="comma-separated: rule, an Anthropic model id, or ollama:<model>")
    ap.add_argument("--effort", default="low", choices=["low", "medium", "high"])
    ap.add_argument("--out", default="", help="CSV file (default: companion-eval.csv in the Mondesk user folder)")
    args = ap.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    all_rows = []
    for spec in [b.strip() for b in args.brains.split(",") if b.strip()]:
        brain = RuleBrain() if spec == "rule" else make_brain(spec, args.effort)
        rows, score = evaluate(brain)
        print(f"\n== {spec}：{sum(r['ok'] for r in rows)}/{len(rows)} 個案例正確（{score:.0%}），"
              f"平均延遲 {sum(r['latency'] for r in rows) / len(rows):.2f} 秒 ==")
        for r in rows:
            print(f"  [{'通過' if r['ok'] else '失敗'}] {r['case']}：{r['line'] or '—'}  ({r['emotion'] or '—'})"
                  + ("".join(f"\n         ↳ {p}" for p in r["problems"])) + ("  ※超過 40 字" if r.get("long") else ""))
        all_rows += [{**r, "brain": spec} for r in rows]
    day = simulate_day()
    print(f"\n== 打擾程度：模擬 8 小時工作日（預設冷卻時間、換歌機率 40%）==")
    print(f"  每小時說話次數：{day['per_hour']}（最多 {day['max_per_hour']}，共 {day['total']} 句）")
    print(f"  各事件說了幾次：{day['by_event']}")
    print(f"  偵測到但沒說的：換歌 {day['detected'].get('song_change', 0) - day['by_event'].get('song_change', 0)} 次")
    if args.out:
        out = Path(args.out)
    else:
        from user_paths import user_data_dir
        out = user_data_dir() / "companion-eval.csv"
    with open(out, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["brain", "case", "event", "passed", "line", "emotion", "latency", "problems"])
        for r in all_rows:
            w.writerow([r["brain"], r["case"], r["event"], "y" if r["ok"] else "n", r["line"], r["emotion"], r["latency"],
                        "；".join(r["problems"])])
    print(f"\n已寫入 {out}")
    return 0 if all(r["ok"] for r in all_rows if r["brain"] == "rule") else 1


if __name__ == "__main__":
    sys.exit(main())
