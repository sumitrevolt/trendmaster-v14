"""Find when brain last pushed a non-NONE signal + what EA saw."""
import os, sys, json, time, re
from pathlib import Path
from datetime import datetime, timezone

os.chdir(r"C:\Users\Ratanshila\Documents\autmated trading")

print("=" * 72)
print("  LAST BUY/SELL TRACE")
print("=" * 72)

# 1. Search brain log for last BUY/SELL signals
print("\n[1] Last BUY/SELL entries in brain log")
log_path = Path("logs/trend_master_brain.log")
if log_path.exists():
    try:
        content = log_path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        print(f"  read failed: {e}")
        content = ""
    # Match BUY or SELL in any brain log line.
    lines = content.splitlines()
    # Direction change lines — formatted like "[SYM] direction BUY 0.72"
    # tick_all summary lines with BUY= or SELL= counts
    hits = []
    for l in lines:
        if "BUY=" in l and "BUY=0" not in l:
            hits.append(l)
        elif "SELL=" in l and "SELL=0" not in l:
            hits.append(l)
        elif " BUY " in l or " SELL " in l:
            hits.append(l)
    print(f"  found {len(hits)} lines with BUY/SELL references")
    for l in hits[-15:]:
        # Strip any non-ASCII chars that break Windows console.
        safe = "".join(c if ord(c) < 128 else "?" for c in l)
        print(f"    {safe[:200]}")

# 2. Events log — find signal events with non-NONE direction
print("\n[2] Non-NONE signal events in events.jsonl")
ev_path = Path("logs/events.jsonl")
if ev_path.exists():
    signals = []
    try:
        for line in ev_path.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                obj = json.loads(line)
            except Exception:
                continue
            if obj.get("k") != "signal":
                continue
            p = obj.get("p") or {}
            if p.get("direction") not in ("BUY", "SELL"):
                continue
            signals.append(obj)
    except Exception as e:
        print(f"  read failed: {e}")
    print(f"  found {len(signals)} non-NONE signal events")
    for s in signals[-15:]:
        ts = int(s.get("ts", 0))
        ago = int(time.time() - ts) if ts else -1
        when = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S") if ts else "?"
        p = s.get("p", {})
        print(f"    {when}  ({ago}s ago)  {s.get('s'):8s} "
              f"{p.get('direction'):4s}  conf={p.get('confidence'):.2f}")
    if signals:
        last = signals[-1]
        last_ts = int(last.get("ts", 0))
        last_ago_min = int((time.time() - last_ts) / 60) if last_ts else -1
        print(f"\n  LAST BUY/SELL signal was {last_ago_min} MINUTES ago")

# 3. Read the telegram notifier's dedup state — shows what was last pushed
print("\n[3] TelegramNotifier dedup — what was last pushed per symbol")
try:
    # Check the state file — dedup is in-memory but brain_state has last_signal_per_symbol
    state = json.loads(Path("logs/brain_state.json").read_text(encoding="utf-8"))
    last_sig = state.get("last_signal_per_symbol", {}) or {}
    now = int(time.time())
    for sym in sorted(last_sig):
        info = last_sig[sym]
        d = info.get("direction", "?")
        c = info.get("confidence", 0.0)
        ts = int(info.get("ts", 0))
        ago = now - ts if ts else -1
        mark = "[LIVE]" if d in ("BUY", "SELL") else "[    ]"
        print(f"    {mark} {sym:8s} {d:5s} conf={c:.2f} ago={ago}s")
except Exception as e:
    print(f"  state read failed: {e}")

print("\n" + "=" * 72)
