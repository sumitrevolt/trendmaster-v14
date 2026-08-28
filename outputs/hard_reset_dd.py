"""Hard reset: clear lockout + sync SoD equity to current + nuke today's recent_results.

After this, brain has no DD history to act on, so the lockout setter cannot fire.
"""
import json
import shutil
import os
import sys
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv
load_dotenv(r"C:\Users\Ratanshila\Documents\autmated trading\config\.env")

ROOT = Path(r"C:\Users\Ratanshila\Documents\autmated trading")
STATE = ROOT / "logs" / "brain_state.json"

# Backup
ts = datetime.now().strftime("%Y%m%d_%H%M%S")
backup = STATE.with_name(f"brain_state.bak.hard_reset_{ts}")
shutil.copy2(STATE, backup)
print(f"  Backup: {backup.name}")

# Live equity
import MetaTrader5 as mt5
mt5.initialize(login=int(os.getenv("MT5_LOGIN")),
               password=os.getenv("MT5_PASSWORD"),
               server=os.getenv("MT5_SERVER"))
ai = mt5.account_info()
equity = float(ai.equity)
print(f"  Live equity: ${equity:.2f}")
mt5.shutdown()

state = json.loads(STATE.read_text())
print(f"\n=== BEFORE ===")
print(f"  drawdown_lockout_until: {state.get('drawdown_lockout_until')}")
print(f"  start_of_day_equity:    {state.get('start_of_day_equity')}")
print(f"  daily_drawdown_peak_eq: {state.get('daily_drawdown_peak_eq')}")
print(f"  recent_results count:   {len(state.get('recent_results', []))}")

# HARD RESET fields
state["drawdown_lockout_until"] = 0
state["cooldown_until_ts"] = 0
state["trading_paused"] = False
state["trading_paused_at"] = 0
# Sync SoD to current equity so DD% = 0 going forward
state["start_of_day_equity"] = equity
state["start_of_day_date"] = datetime.utcnow().strftime("%Y-%m-%d")
state["daily_drawdown_peak_eq"] = equity
state["daily_pnl_close"] = 0.0
# Trim recent_results — keep only entries older than today (preserves long-term learning,
# kills today's losses that triggered the lockout)
import time
today_start_ts = int(datetime.combine(datetime.utcnow().date(), datetime.min.time()).timestamp())
old_recent = state.get("recent_results", [])
state["recent_results"] = [r for r in old_recent if r.get("ts", 0) < today_start_ts]
print(f"\n=== TRIMMED ===")
print(f"  recent_results: {len(old_recent)} -> {len(state['recent_results'])} (kept pre-today only)")

STATE.write_text(json.dumps(state, indent=2))

# Verify
state2 = json.loads(STATE.read_text())
print(f"\n=== AFTER ===")
print(f"  drawdown_lockout_until: {state2.get('drawdown_lockout_until')}")
print(f"  start_of_day_equity:    {state2.get('start_of_day_equity')}")
print(f"  start_of_day_date:      {state2.get('start_of_day_date')}")
print(f"  daily_drawdown_peak_eq: {state2.get('daily_drawdown_peak_eq')}")
print(f"  recent_results count:   {len(state2.get('recent_results', []))}")
print(f"\n[OK] Hard reset done. Now restart brain so it loads cleared state.")
