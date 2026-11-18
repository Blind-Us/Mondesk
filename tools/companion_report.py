"""Summarise the Companion's log: speed, tokens and estimated cost per brain.

    python tools/companion_report.py                 # last 7 days, real + test events
    python tools/companion_report.py --days 1 --real # only events that really happened
    python tools/companion_report.py --csv lines.csv # every line, with an empty column to rate quality

Reads companion-log.jsonl from the Mondesk user folder (or --log PATH).
"""
import argparse
import csv
import json
import statistics
import sys
import time
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# USD per million tokens: input, output, cache write, cache read. Estimates only; check
# https://claude.com/pricing before quoting numbers. Thinking tokens are billed as output.
PRICES = {
    "claude-opus-5-5": (4.00, 20.00, 5.00, 0.20),
    "claude-sonnet-5-5": (2.00, 10.00, 2.50, 0.20),
    "claude-haiku-5-5": (0.10, 0.50, 0.125, 0.01),
}


def cost(brain, usage):
    p = PRICES.get(brain)
    if not p or not usage:
        return 0.0
    return (usage.get("input_tokens", 0) * p[0] + usage.get("output_tokens", 0) * p[1]
            + usage.get("cache_creation_input_tokens", 0) * p[2] + usage.get("cache_read_input_tokens", 0) * p[3]) / 1e6


def load(path, days, real_only):
    since = time.time() - days * 86400
    rows = []
    for raw in Path(path).read_text(encoding="utf-8").splitlines():
        try:
            e = json.loads(raw)
        except ValueError:
            continue
        if e.get("ts", 0) >= since and not (real_only and e.get("simulated")):
            rows.append(e)
    return rows


def summarise(rows, key=lambda e: e.get("brain") or e.get("via")):
    groups = defaultdict(list)
    for e in rows:
        groups[key(e)].append(e)
    out = []
    for brain, items in sorted(groups.items()):
        ok = [e for e in items if not e.get("error")]
        lat = sorted(e["latency"] for e in ok if e.get("latency") is not None)
        tokens_in = sum((e.get("usage") or {}).get("input_tokens", 0) for e in items)
        tokens_out = sum((e.get("usage") or {}).get("output_tokens", 0) for e in items)
        total = sum(cost(brain, e.get("usage")) for e in items)
        out.append({
            "brain": brain, "lines": len(items), "fallbacks": len(items) - len(ok),
            "latency_avg": round(statistics.mean(lat), 2) if lat else None,
            "latency_p90": lat[min(len(lat) - 1, int(len(lat) * 0.9))] if lat else None,
            "tokens_in": tokens_in, "tokens_out": tokens_out,
            "cost_usd": round(total, 4), "cost_per_line": round(total / len(items), 5) if items else 0,
        })
    return out


def print_table(summary):
    cols = ["brain", "lines", "fallbacks", "latency_avg", "latency_p90", "tokens_in", "tokens_out", "cost_usd", "cost_per_line"]
    widths = {c: max(len(c), *(len(str(r[c])) for r in summary)) for c in cols} if summary else {}
    print("  ".join(c.ljust(widths[c]) for c in cols))
    for r in summary:
        print("  ".join(str(r[c] if r[c] is not None else "-").ljust(widths[c]) for c in cols))


def main():
    from modules.companion import user_folder
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--log", default=str(user_folder() / "companion-log.jsonl"))
    ap.add_argument("--days", type=float, default=7)
    ap.add_argument("--real", action="store_true", help="skip test-button (simulated) events")
    ap.add_argument("--csv", help="also write every line to this CSV for manual quality rating")
    args = ap.parse_args()
    if not Path(args.log).is_file():
        sys.exit(f"找不到紀錄檔：{args.log}")
    rows = load(args.log, args.days, args.real)
    if not rows:
        sys.exit("這段期間沒有紀錄")
    print_table(summarise(rows))
    print("\n費用為估計值（依 PRICES 表），不含規則式與本機模型。")
    if args.csv:
        with open(args.csv, "w", newline="", encoding="utf-8-sig") as f:  # BOM: Excel opens Chinese correctly
            w = csv.writer(f)
            w.writerow(["time", "event", "simulated", "brain", "served_by", "latency", "line", "emotion", "tools",
                        "error", "cost_usd", "quality_1to5", "emotion_fits_y_n"])
            for e in rows:
                w.writerow([time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(e["ts"])), e.get("event"),
                            e.get("simulated"), e.get("brain"), e.get("served_by"), e.get("latency"), e.get("line"),
                            e.get("emotion"), " ".join(e.get("tools") or []), e.get("error"),
                            round(cost(e.get("brain"), e.get("usage")), 5), "", ""])
        print(f"已寫入 {args.csv}（最後兩欄留給你評分）")


if __name__ == "__main__":
    main()
