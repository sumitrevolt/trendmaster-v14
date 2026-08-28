"""Check what closed since this session started."""
import MetaTrader5 as mt5
from datetime import datetime, timedelta

mt5.initialize()
since = datetime(2026, 5, 5, 21, 0)
deals = mt5.history_deals_get(since, datetime.now()) or []
print(f"=== Deals since {since} ===")
print(f"Total: {len(deals)}")
print()
print(f"{'Sym':<10} {'Type':<8} {'Vol':<6} {'Price':<12} {'Profit':>8} {'Time':<20} Comment")
print("-" * 90)
for d in sorted(deals, key=lambda x: x.time):
    typ = "BUY" if d.type == 0 else ("SELL" if d.type == 1 else f"T{d.type}")
    when = datetime.fromtimestamp(d.time).strftime("%H:%M:%S")
    print(f"{d.symbol:<10} {typ:<8} {d.volume:<6.2f} {d.price:<12.5f} {d.profit:>+8.2f} {when:<20} {d.comment}")

print()
pos = mt5.positions_get() or []
print(f"=== Open positions: {len(pos)} ===")
for p in sorted(pos, key=lambda x: x.symbol):
    typ = "BUY" if p.type == 0 else "SELL"
    print(f"  {p.symbol:<10} {typ:<5} {p.volume:<6.2f} open={p.price_open:<12.5f} now={p.price_current:<12.5f} P/L={p.profit:>+.2f}")
mt5.shutdown()
