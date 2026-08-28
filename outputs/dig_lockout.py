"""Find who set the drawdown_lockout_until and why."""
import json
from datetime import datetime
from pathlib import Path

# Decode the timestamp
lockout_ts = 1778112000
print(f"=== Lockout interpretation ===")
print(f"  drawdown_lockout_until: {lockout_ts}")
print(f"  As UTC : {datetime.utcfromtimestamp(lockout_ts).isoformat()}")
print(f"  As local: {datetime.fromtimestamp(lockout_ts).isoformat()}")
print(f"  Hours from now: {(lockout_ts - datetime.now().timestamp())/3600:.1f}")

# Full brain_state inspection
print(f"\n=== brain_state.json full ===")
state = json.loads(Path("logs/brain_state.json").read_text())
for k, v in state.items():
    if isinstance(v, list) and len(v) > 3:
        print(f"  {k}: list[{len(v)}]  first 3: {v[:3]}")
    elif isinstance(v, dict) and len(v) > 5:
        print(f"  {k}: dict[{len(v)} keys]  sample: {dict(list(v.items())[:3])}")
    else:
        print(f"  {k}: {v}")

# Check brain log for "lockout" / "drawdown" keywords
print(f"\n=== Brain log mentions of drawdown/lockout (last 30) ===")
log_path = Path("logs/trend_master_brain.out")
if log_path.exists():
    lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    matching = [l for l in lines if any(k in l.lower() for k in ["lockout", "drawdown", "dd_breach", "trading_paused", "max_dd"])]
    for l in matching[-30:]:
        print(f"  {l[:200]}")
    if not matching:
        print(f"  (no lockout/drawdown mentions in {len(lines)} log lines)")

# Check dd_state.json if exists
dd_path = Path("logs/dd_state.json")
print(f"\n=== logs/dd_state.json ===")
if dd_path.exists():
    print(f"  {dd_path.read_text()[:500]}")
else:
    print(f"  not found")
