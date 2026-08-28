"""Clear stale drawdown_lockout_until in brain_state.json.

USER OPERATION: This unblocks EA from trading. Sumit must run.

Logic:
  1. Backup brain_state.json -> brain_state.bak.<timestamp>
  2. Read state, log current lockout value + DD%
  3. If account is currently HEALTHY (no real DD), set lockout=0 + cooldown=0
  4. Verify + print new state
"""
import json
import shutil
import sys
import os
from pathlib import Path
from datetime import datetime

ROOT = Path(r"C:\Users\Ratanshila\Documents\autmated trading")
STATE = ROOT / "logs" / "brain_state.json"

if not STATE.exists():
    print(f"FATAL: {STATE} missing"); sys.exit(1)

# 1. Backup
ts = datetime.now().strftime("%Y%m%d_%H%M%S")
backup = STATE.with_name(f"brain_state.bak.before_lockout_clear_{ts}")
shutil.copy2(STATE, backup)
print(f"  Backed up to: {backup.name}")

state = json.loads(STATE.read_text())
print(f"\n=== BEFORE ===")
print(f"  drawdown_lockout_until: {state.get('drawdown_lockout_until')}")
print(f"  trading_paused:         {state.get('trading_paused')}")
print(f"  cooldown_until_ts:      {state.get('cooldown_until_ts')}")
print(f"  start_of_day_equity:    {state.get('start_of_day_equity')}")
print(f"  daily_drawdown_peak_eq: {state.get('daily_drawdown_peak_eq')}")

# 2. Live equity check (sanity)
from dotenv import load_dotenv
load_dotenv(ROOT / "config" / ".env")
import MetaTrader5 as mt5
mt5.initialize(login=int(os.getenv("MT5_LOGIN")),
               password=os.getenv("MT5_PASSWORD"),
               server=os.getenv("MT5_SERVER"))
ai = mt5.account_info()
sod = float(state.get("start_of_day_equity", 0) or 0)
equity = float(ai.equity)
dd_pct = ((sod - equity) / sod * 100) if sod > 0 else 0
print(f"\n  Live equity:            ${equity:.2f}")
print(f"  Live DD vs SoD:         {dd_pct:+.2f}%")
mt5.shutdown()

if dd_pct >= 1.0:
    print(f"\n[ABORT] Real DD detected ({dd_pct:.2f}%). NOT clearing lockout.")
    print(f"        Manually investigate before clearing.")
    sys.exit(2)

# 3. Clear lockout fields
print(f"\n=== CLEARING ===")
state["drawdown_lockout_until"] = 0
state["cooldown_until_ts"] = 0
# Reset trading_paused to False just in case
state["trading_paused"] = False
state["trading_paused_at"] = 0
state["trading_resumed_at"] = int(datetime.now().timestamp())

STATE.write_text(json.dumps(state, indent=2))
print(f"  Wrote cleared state")

# 4. Verify
state2 = json.loads(STATE.read_text())
print(f"\n=== AFTER ===")
print(f"  drawdown_lockout_until: {state2.get('drawdown_lockout_until')}")
print(f"  trading_paused:         {state2.get('trading_paused')}")
print(f"  cooldown_until_ts:      {state2.get('cooldown_until_ts')}")

print(f"\n[OK] Lockout cleared. EA should now process the next Rocket Prime signal.")
print(f"     Test by waiting for next TV alert fire OR forcing one via 'Test alert' on TV.")
print(f"     Restore from {backup.name} if anything misbehaves.")
