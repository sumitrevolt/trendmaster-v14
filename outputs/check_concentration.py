"""Quick concentration & position diagnostic."""
import os
import sys
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv("config/.env")
import MetaTrader5 as mt5

if not mt5.initialize(
    login=int(os.getenv("MT5_LOGIN")),
    password=os.getenv("MT5_PASSWORD"),
    server=os.getenv("MT5_SERVER"),
):
    print(f"  MT5 init failed: {mt5.last_error()}")
    sys.exit(1)

ai = mt5.account_info()
print(f"  Account: balance=${ai.balance:.2f} equity=${ai.equity:.2f}")

pos = mt5.positions_get() or []
print(f"  Open positions: {len(pos)}")

LONG_USD_RULES = {
    ("USDJPY", 0): True,
    ("EURUSD", 1): True,
    ("GBPUSD", 1): True,
    ("AUDUSD", 1): True,
    ("NZDUSD", 1): True,
    ("XAUUSD", 1): True,
    ("XAGUSD", 1): True,
    ("XTIUSD", 1): True,
}
SHORT_USD_RULES = {
    ("USDJPY", 1): True,
    ("EURUSD", 0): True,
    ("GBPUSD", 0): True,
    ("AUDUSD", 0): True,
    ("NZDUSD", 0): True,
    ("XAUUSD", 0): True,
    ("XAGUSD", 0): True,
    ("XTIUSD", 0): True,
}

long_usd = 0
short_usd = 0
for p in pos:
    side = "BUY" if p.type == 0 else "SELL"
    age_min = (datetime.now(timezone.utc).timestamp() - p.time) / 60
    print(
        f"  {p.symbol:8s} {side:4s} vol={p.volume:.2f} P/L=${p.profit:7.2f} "
        f"ticket={p.ticket} age={age_min:.0f}min"
    )
    if LONG_USD_RULES.get((p.symbol, p.type)):
        long_usd += 1
    if SHORT_USD_RULES.get((p.symbol, p.type)):
        short_usd += 1

print()
print(f"  long-USD count:  {long_usd} / cap=3  {'BLOCKED' if long_usd >= 3 else 'OK'}")
print(f"  short-USD count: {short_usd} / cap=3  {'BLOCKED' if short_usd >= 3 else 'OK'}")

mt5.shutdown()
