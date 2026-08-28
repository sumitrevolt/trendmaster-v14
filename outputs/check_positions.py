import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv("config/.env")
import MetaTrader5 as mt5

mt5.initialize(
    login=int(os.getenv("MT5_LOGIN")),
    password=os.getenv("MT5_PASSWORD"),
    server=os.getenv("MT5_SERVER"),
)
pos = mt5.positions_get() or []
print(f"open positions: {len(pos)}")
for p in pos:
    side = "BUY" if p.type == 0 else "SELL"
    print(
        f"  {p.symbol} {side} lots={p.volume} entry={p.price_open:.5f} "
        f"now={p.price_current:.5f} profit=${p.profit:.2f} "
        f"sl={p.sl:.5f} tp={p.tp:.5f} magic={p.magic} comment={p.comment}"
    )
ai = mt5.account_info()
print(f"equity=${ai.equity:.2f} balance=${ai.balance:.2f}")
mt5.shutdown()
