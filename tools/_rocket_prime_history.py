"""Show Rocket Prime signal history per hour."""
import json
from collections import Counter
from datetime import datetime
from pathlib import Path

p = Path("logs/tv_signals.jsonl")
if not p.exists():
    print("no tv_signals.jsonl"); raise SystemExit(0)

rocket = []
for line in p.open(encoding="utf-8"):
    try:
        o = json.loads(line)
        s = str(o.get("tv_strategy", ""))
        if "rocket_prime" in s:
            rocket.append(o)
    except Exception:
        pass

print(f"Total Rocket Prime signals all-time: {len(rocket)}")
print()
print(f"Per-hour breakdown (last 24h with activity):")
by_hour = Counter()
for o in rocket:
    ts = o.get("ts", 0)
    hour = datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:00")
    by_hour[hour] += 1
for hour, count in sorted(by_hour.items())[-24:]:
    bar = "#" * count
    print(f"  {hour} | {count:>2} {bar}")

print()
print(f"Last 10 Rocket Prime signals received:")
print(f"{'Time':<20} {'Symbol':<10} {'Dir':<5} {'Strategy':<25} TF")
for o in rocket[-10:]:
    ts = o.get("ts", 0)
    t = datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
    sym = o.get("symbol", "?") or "?"
    d = o.get("direction", "?") or "?"
    strat = o.get("tv_strategy", "-") or "-"
    tf = o.get("tv_timeframe", "-") or "-"
    print(f"  {t:<20} {sym:<10} {d:<5} {strat:<25} {tf}")
