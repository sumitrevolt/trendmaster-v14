"""Quick Phase 1 zero-trade diagnostic — why no entry yet?"""
import io
import json
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Force utf-8 output to handle non-cp1252 chars in brain log
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

ROOT = Path(__file__).parent.parent
state = json.loads((ROOT / "logs" / "brain_state.json").read_text(encoding="utf-8"))

print("=" * 60)
print("  PHASE 1 ZERO-TRADE DIAGNOSTIC")
print("=" * 60)
print()

# Active symbols only (Concentrated 8)
ACTIVE = {"XAUUSD","XAGUSD","USDCHF","AUDJPY","BTCUSD","ETHUSD","XTIUSD","XNGUSD"}
sigs = state.get("last_signal_per_symbol", {})

print(f"{'symbol':<8} {'dir':<6} {'conf':>6} {'age_s':>7}")
print("-" * 35)
now = datetime.now(timezone.utc).timestamp()
for sym in sorted(ACTIVE):
    s = sigs.get(sym, {})
    if not s:
        print(f"{sym:<8} {'(no data)':<14}")
        continue
    age = int(now - s.get("ts", 0))
    print(f"{sym:<8} {s.get('direction','?'):<6} {s.get('confidence', 0):>6.3f} {age:>7}")

print()
print(f"Brain state:")
print(f"  trading_paused: {state.get('trading_paused')}")
print(f"  drawdown_lockout_until: {state.get('drawdown_lockout_until')}")
print(f"  start_of_day_equity: ${state.get('start_of_day_equity')}")
print(f"  daily_drawdown_peak_eq: ${state.get('daily_drawdown_peak_eq')}")
print(f"  daily_pnl_close: ${state.get('daily_pnl_close')}")

# Read last 200 lines of brain log to find vetoes
log_path = ROOT / "logs" / "trend_master_brain.out"
if log_path.exists():
    txt = log_path.read_text(encoding="utf-8", errors="replace")
    lines = txt.splitlines()[-3000:]

    # Veto pattern counter
    veto_counts = {}
    for line in lines:
        if "profit_gate veto:" in line:
            # Extract gate name
            after = line.split("profit_gate veto:")[1].strip()
            gate = after.split(":")[0].strip()
            veto_counts[gate] = veto_counts.get(gate, 0) + 1
        elif "rejected by mtf" in line.lower() or "mtf_agree" in line.lower():
            veto_counts['mtf_agree'] = veto_counts.get('mtf_agree', 0) + 1
        elif "conf below" in line or "below threshold" in line:
            veto_counts['conf_threshold'] = veto_counts.get('conf_threshold', 0) + 1
        elif "agents disagree" in line.lower() or "vote_all" in line.lower():
            veto_counts['multi_agent'] = veto_counts.get('multi_agent', 0) + 1

    print()
    print("=== Veto reasons (last ~3000 log lines) ===")
    if veto_counts:
        for gate, n in sorted(veto_counts.items(), key=lambda x: -x[1]):
            print(f"  {gate:<20} {n:>4}x")
    else:
        print("  (no vetoes seen in last 3000 lines — log mostly feature-build noise)")

    # Last tick_all summary
    print()
    print("=== Last 3 tick_all summaries ===")
    summaries = [l for l in lines if "tick_all summary" in l]
    for s in summaries[-3:]:
        print(f"  {s.strip()[:140]}")

    # Any high-confidence signals?
    print()
    print("=== High-conf events (conf > 0.50) ===")
    hi = [l for l in lines if "conf=" in l.lower()]
    for l in hi[-5:]:
        print(f"  {l.strip()[:140]}")
