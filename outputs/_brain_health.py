"""Check the actual running brain's health."""
import os, sys, json, time, subprocess
os.chdir(r"C:\Users\Ratanshila\Documents\autmated trading")

print("=" * 70)
print("  BRAIN HEALTH CHECK")
print("=" * 70)

# 1. signal files — most important live indicator
from pathlib import Path
root = Path(".")
sig_files = list(root.glob("trendmaster_signals*.json"))
print(f"\n[signals] {len(sig_files)} signal file(s)")
for f in sig_files:
    age = int(time.time() - f.stat().st_mtime)
    try:
        sig = json.loads(f.read_text())
        dir_ = sig.get("direction")
        conf = sig.get("confidence")
        print(f"  {f.name:45s} age={age:4d}s dir={dir_} conf={conf}")
    except Exception as e:
        print(f"  {f.name:45s} unreadable: {e}")

# 2. Brain state file
state_path = root / "logs" / "brain_state.json"
if state_path.exists():
    state = json.loads(state_path.read_text())
    print(f"\n[brain_state.json]")
    for k in ("restart_count", "last_started_at", "last_saved_at",
              "halted", "trading_paused", "start_of_day_equity",
              "daily_drawdown_peak_eq", "drawdown_lockout_until"):
        v = state.get(k)
        if k.endswith("_at"):
            if isinstance(v, int) and v > 0:
                v = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime(v))
        print(f"  {k:30s} = {v}")
    print(f"  recent_results len = {len(state.get('recent_results', []))}")
    print(f"  last_signal_per_symbol keys = {len(state.get('last_signal_per_symbol', {}))}")

# 3. brain log tail
err_log = root / "logs" / "trend_master_brain.err"
out_log = root / "logs" / "trend_master_brain.out"
trading_log = root / "logs" / "trading.log"
log_log = root / "logs" / "trend_master_brain.log"
for p in (err_log, out_log, trading_log, log_log):
    if p.exists():
        size = p.stat().st_size
        age = int(time.time() - p.stat().st_mtime)
        print(f"\n[{p}] {size} bytes, last-modified {age}s ago")
        if size > 0:
            try:
                content = p.read_text(encoding="utf-8", errors="replace")
                lines = content.splitlines()
                print(f"  ... last 10 lines ...")
                for l in lines[-10:]:
                    print(f"  {l}")
            except Exception as e:
                print(f"  read failed: {e}")

# 4. Event log check
evt_log = root / "logs" / "events.jsonl"
if evt_log.exists():
    try:
        lines = evt_log.read_text(encoding="utf-8", errors="replace").splitlines()
        print(f"\n[events.jsonl] {len(lines)} events")
        for l in lines[-3:]:
            print(f"  {l}")
    except Exception as e:
        print(f"  read failed: {e}")
else:
    print(f"\n[events.jsonl] not yet created")

print("\n" + "=" * 70)
print("  HEALTH CHECK COMPLETE")
print("=" * 70)
