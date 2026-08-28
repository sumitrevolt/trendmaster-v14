"""Clean state.json after demo top-up:
- Remove the BALANCE-credit pseudo-trade ($464 on deal_id 731555171, type=2)
- Reset phase1_baseline.json starting_equity to current balance ($1010.55)
"""
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent.parent
STATE = ROOT / "logs" / "brain_state.json"
BASELINE = ROOT / "logs" / "phase1_baseline.json"

# Backup first
ts = datetime.now().strftime("%Y%m%d_%H%M%S")
shutil.copy(STATE, STATE.with_suffix(f".bak.{ts}"))
shutil.copy(BASELINE, BASELINE.with_suffix(f".bak.{ts}"))
print(f"backups written with suffix .bak.{ts}")

# 1. Clean state.json — drop BALANCE deal from recent_results
state = json.loads(STATE.read_text(encoding="utf-8"))
before = list(state.get("recent_results", []))
# Filter: keep only entries with non-empty symbol AND deal_id that's not the topup
DEAL_BLACKLIST = {731555171}
state["recent_results"] = [
    r for r in before
    if r.get("symbol") and r.get("deal_id") not in DEAL_BLACKLIST
]
# Also reset start_of_day_equity to current MT5 balance
state["start_of_day_equity"] = 1010.55
state["start_of_day_date"] = datetime.now(timezone.utc).strftime("%Y-%m-%d")
state["daily_drawdown_peak_eq"] = 1010.55
state["daily_pnl_close"] = 0.0
state["session_high_equity"] = 1010.55
state["session_low_equity"] = 1010.55
# Mark this so the brain knows we manually reset
state["_phase1_topup_reset_at"] = datetime.now(timezone.utc).isoformat()

# Atomic write (temp + rename)
tmp = STATE.with_suffix(".tmp")
tmp.write_text(json.dumps(state, indent=0, separators=(",", ":")), encoding="utf-8")
tmp.replace(STATE)
print(f"state.json cleaned: recent_results {len(before)} -> {len(state['recent_results'])}")
print(f"  starting_equity reset to ${state['start_of_day_equity']:.2f}")
print(f"  daily_pnl_close reset to ${state['daily_pnl_close']:.2f}")

# 2. Update Phase 1 baseline
baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
baseline["starting_equity_usd"] = 1010.55
baseline["topup_applied_at"] = datetime.now(timezone.utc).isoformat()
baseline["topup_amount_usd"] = 464.00
baseline["pre_topup_equity_usd"] = 546.55
# Update expected band given $1000 capital (was already calc'd for $1000)
baseline["expected_band_30d"] = [80.0, 250.0]
baseline["expected_p50_30d_pnl"] = 180.0
baseline["note"] = "Baseline rebased after demo top-up at 14:15 IST. starting_equity_usd reflects post-topup balance. Expected bands match the original $1000 plan."

BASELINE.write_text(json.dumps(baseline, indent=2), encoding="utf-8")
print(f"phase1_baseline.json updated: starting_equity_usd = ${baseline['starting_equity_usd']:.2f}")
print()
print("DONE. Brain will pick up cleaned state on next tick (state_store reloads on each save).")
