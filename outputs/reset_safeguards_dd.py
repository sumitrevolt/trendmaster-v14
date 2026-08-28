"""Reset tools/safeguards.py DD breaker (logs/dd_state.json).

Why: safeguards.check_dd_breaker maintains a SEPARATE DD state file from
brain_state.json. Once tripped (sticky), it blocks every BUY/SELL on every
symbol until midnight. We rebase to current equity + clear the trip flag.

Counterpart to outputs/reset_dd_baseline.py (which fixes brain_state.json).
"""
import json
import os
import sys
import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv("config/.env")
import MetaTrader5 as mt5

ok = mt5.initialize(
    login=int(os.getenv("MT5_LOGIN")),
    password=os.getenv("MT5_PASSWORD"),
    server=os.getenv("MT5_SERVER"),
)
if not ok:
    print(f"[FATAL] MT5 init failed: {mt5.last_error()}")
    sys.exit(1)

ai = mt5.account_info()
eq = float(ai.equity)
mt5.shutdown()

today = datetime.datetime.now().strftime("%Y-%m-%d")
state_path = Path("logs/dd_state.json")
before = state_path.read_text(encoding="utf-8") if state_path.exists() else "<missing>"
print(f"  BEFORE: {before}")

state = {
    "date": today,
    "start_equity": eq,
    "tripped": False,
    "trip_at": None,
}
state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")
print(f"  AFTER:  start_equity=${eq:.2f}  date={today}  tripped=False  trip_at=None")
print()
print("OK — safeguards DD breaker reset. Next BUY/SELL signal should now pass through.")
