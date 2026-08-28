"""Drop expired and empty-direction reentry permits from brain_state.json.

Brain populates these when SL hits, then re-uses them within the expiry
window. Old/expired permits accumulate as noise and can confuse manual
inspection. Brain itself eventually prunes them on the next save tick,
but this gives the operator an explicit reset.
"""
import json
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
state_path = ROOT / "logs" / "brain_state.json"
backup = state_path.with_suffix(".json.bak.prune-" + time.strftime("%Y-%m-%d-%H%M%S"))

state = json.loads(state_path.read_text(encoding="utf-8"))
old_permits = state.get("reentry_permits", [])
now = time.time()

# Keep only permits that haven't expired AND have a real direction
new_permits = [
    p for p in old_permits
    if (p.get("direction") in ("BUY", "SELL"))
    and (p.get("expires_ts", 0) > now)
    and (not p.get("used", False))
]

dropped = len(old_permits) - len(new_permits)
if dropped == 0:
    print("  no stale permits to prune.")
else:
    backup.write_text(state_path.read_text(encoding="utf-8"), encoding="utf-8")
    state["reentry_permits"] = new_permits
    tmp = state_path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, separators=(",", ":")), encoding="utf-8")
    tmp.replace(state_path)
    print(f"  pruned {dropped} stale permits. backup at {backup.name}")
    print(f"  remaining: {len(new_permits)}")

# Show what's left
for p in new_permits:
    age_min = (now - p.get("original_sl_ts", 0)) / 60
    print(f"    {p.get('symbol')} {p.get('direction')} age={age_min:.1f}min size_mult={p.get('size_mult')}")
