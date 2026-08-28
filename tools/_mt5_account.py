"""Check MT5 account state after top-up."""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

# Load env
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / "config" / ".env")
except ImportError:
    pass

import MetaTrader5 as mt5

login = int(os.getenv("MT5_LOGIN", 0))
password = os.getenv("MT5_PASSWORD", "")
server = os.getenv("MT5_SERVER", "OctaFX-Demo")

ok = mt5.initialize(login=login, password=password, server=server)
print(f"mt5.initialize(): {ok}")
if not ok:
    print(f"  last_error: {mt5.last_error()}")
    sys.exit(1)

ai = mt5.account_info()
if ai is None:
    print(f"  account_info FAILED: {mt5.last_error()}")
    sys.exit(2)

print()
print("=== Account ===")
print(f"  login:        {ai.login}")
print(f"  server:       {ai.server}")
print(f"  currency:     {ai.currency}")
print(f"  leverage:     1:{ai.leverage}")
print(f"  balance:      ${ai.balance:.2f}")
print(f"  equity:       ${ai.equity:.2f}")
print(f"  margin:       ${ai.margin:.2f}")
print(f"  margin_free:  ${ai.margin_free:.2f}")
print(f"  margin_level: {ai.margin_level:.1f}%" if ai.margin_level else "  margin_level: n/a")
print()

# Open positions
pos = mt5.positions_get()
print(f"=== Open positions ({len(pos) if pos else 0}) ===")
for p in (pos or []):
    side = "BUY" if p.type == 0 else "SELL"
    print(f"  {p.symbol:<8} {side:<5} {p.volume:>5.2f}lot  open=${p.price_open:.4f}  current=${p.price_current:.4f}  pnl=${p.profit:+.2f}  sl=${p.sl}  tp=${p.tp}")

# Pending orders
ord = mt5.orders_get()
print(f"=== Pending orders ({len(ord) if ord else 0}) ===")
for o in (ord or []):
    print(f"  {o.symbol} {o.type} {o.volume_current}lot @ ${o.price_open}")

# Recent deal history (last 6 hours)
import time
from datetime import datetime, timezone, timedelta
t_to = datetime.now(timezone.utc)
t_from = t_to - timedelta(hours=6)
deals = mt5.history_deals_get(t_from, t_to)
print(f"=== Deals last 6h ({len(deals) if deals else 0}) ===")
for d in (deals or [])[-10:]:
    dt = datetime.fromtimestamp(d.time, tz=timezone.utc)
    side = "BUY" if d.type == 0 else "SELL" if d.type == 1 else f"type={d.type}"
    print(f"  {dt.isoformat()[:19]}  deal={d.ticket}  {d.symbol:<8} {side:<5} {d.volume:>5.2f}lot  pnl=${d.profit:+.2f}  comment={d.comment}")

mt5.shutdown()
