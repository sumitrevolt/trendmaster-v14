import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
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
    print(f"MT5 init failed: {mt5.last_error()}")
    sys.exit(1)

ai = mt5.account_info()
s = json.loads(open("logs/brain_state.json", encoding="utf-8").read())
sod = float(s.get("start_of_day_equity", 0))
eq = float(ai.equity)
dd = (sod - eq) / sod * 100 if sod > 0 else 0
from config.settings import PROFIT_OPTIMIZER as P
cap = float(P.get("daily_max_loss_pct", 5.0))

print(f"  equity = ${eq:.2f}")
print(f"  balance= ${ai.balance:.2f}")
print(f"  sod    = ${sod:.2f}")
print(f"  dd     = {dd:.2f}%")
print(f"  cap    = {cap:.2f}%")
print(f"  GATE   = {'BLOCKED' if dd >= cap else 'OPEN'}")
print(f"  lockout= {s.get('drawdown_lockout_until', 0)}")
print(f"  paused = {s.get('trading_paused')}")
print(f"  positions_open = {mt5.positions_total()}")
mt5.shutdown()
