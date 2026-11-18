"""Model comparison for the Companion: same events, same fake data, different brains.

    python tools/companion_bench.py --brains claude-opus-5-5,claude-haiku-5-5,rule
    python tools/companion_bench.py --brains claude-opus-5-5,ollama:qwen3:8b --runs 3 --out bench.csv

Every event uses the test-button scenario data (print finished, quota 86%, ...), so all
brains see exactly the same world. Brains: an Anthropic model id, "ollama:<model>", or "rule".

Costs money: each Claude run is 1-3 API requests. The API key comes from the
ANTHROPIC_API_KEY environment variable, else from the Companion settings (config.json),
else the SDK's own login. Results go to a CSV with empty columns for your quality rating.
"""
import argparse
import csv
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from modules.companion_brain import (SCENARIOS, SIMULATED_DETAIL, AnthropicBrain, OllamaBrain, RuleBrain, World,
                                     BrainError)
from modules.companion_events import Event
from tools.companion_report import cost, print_table, summarise


def saved_api_key():
    try:
        from user_paths import user_config_path
        cfg = json.loads(user_config_path().read_text(encoding="utf-8"))
        return next((m.get("api_key") for m in cfg.get("modules", []) if m.get("type") == "companion"), None)
    except Exception:
        return None


def make_brain(spec, effort):
    if spec == "rule":
        return RuleBrain()
    if spec.startswith("ollama:"):
        return OllamaBrain(spec[7:])
    import os
    return AnthropicBrain(spec, effort=effort, api_key=os.environ.get("ANTHROPIC_API_KEY") or saved_api_key())


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--brains", required=True, help="comma-separated, e.g. claude-opus-5-5,claude-haiku-5-5,rule")
    ap.add_argument("--events", default=",".join(SCENARIOS), help="comma-separated (default: all six)")
    ap.add_argument("--runs", type=int, default=1, help="repeats per brain and event")
    ap.add_argument("--effort", default="low", choices=["low", "medium", "high"])
    ap.add_argument("--out", default="companion-bench.csv")
    args = ap.parse_args()
    events = [e for e in args.events.split(",") if e]
    unknown = [e for e in events if e not in SCENARIOS]
    if unknown:
        sys.exit(f"未知的事件：{', '.join(unknown)}（可用：{', '.join(SCENARIOS)}）")
    rows = []
    for spec in [b.strip() for b in args.brains.split(",") if b.strip()]:
        brain = make_brain(spec, args.effort)
        for name in events:
            for run in range(1, args.runs + 1):
                world = World([], work_minutes=SCENARIOS[name].get("work_minutes", 0), scenario=SCENARIOS[name])
                started = time.time()
                try:
                    reply, error = brain.respond(Event(name, dict(SIMULATED_DETAIL.get(name, {})), simulated=True), world), None
                except BrainError as e:
                    reply, error = None, str(e)
                row = {"ts": time.time(), "brain": spec, "event": name, "run": run,
                       "latency": round(time.time() - started, 2), "line": reply.line if reply else "",
                       "emotion": reply.emotion if reply else "", "tools": reply.tools if reply else [],
                       "usage": reply.usage if reply else {}, "served_by": reply.served_by if reply else None,
                       "error": error}
                rows.append(row)
                print(f"[{spec}] {name} #{run}: {row['line'] or '錯誤：' + error}  ({row['emotion']}, {row['latency']} 秒)")
    print()
    print_table(summarise(rows, key=lambda e: e["brain"]))
    with open(args.out, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["brain", "event", "run", "latency", "line", "emotion", "tools", "input_tokens", "output_tokens",
                    "cost_usd", "error", "quality_1to5", "emotion_fits_y_n", "same_character_voice_y_n"])
        for r in rows:
            u = r["usage"]
            w.writerow([r["brain"], r["event"], r["run"], r["latency"], r["line"], r["emotion"], " ".join(r["tools"]),
                        u.get("input_tokens", 0), u.get("output_tokens", 0), round(cost(r["brain"], u), 5), r["error"],
                        "", "", ""])
    print(f"\n已寫入 {args.out}（最後三欄留給你評分）")


if __name__ == "__main__":
    main()
