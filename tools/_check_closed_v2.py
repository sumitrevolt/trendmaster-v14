"""Check ALL deal types since today 09:00 (UTC)."""
import MetaTrader5 as mt5
from datetime import datetime, timedelta, timezone

mt5.initialize()

# Try with UTC and a wide range
since = datetime(2026, 5, 5, 0, 0, tzinfo=timezone.utc)
to = datetime.now(timezone.utc) + timedelta(hours=1)

deals = mt5.history_deals_get(since, to)
if deals is None:
    print(f"history_deals_get returned None, last_error: {mt5.last_error()}")
    deals = []
print(f"=== ALL deals from {since} to {to}: {len(deals)} ===")
print(f"{'Time':<20} {'Sym':<10} {'Type':<6} {'Entry':<8} {'Vol':<6} {'Price':<12} {'Profit':>8} Comment")
print("-" * 110)

DEAL_TYPES = {0: "BUY", 1: "SELL", 2: "BAL", 3: "CRD", 4: "CHG", 5: "CMS",
              6: "CDF", 7: "TAX", 8: "BNS", 9: "INT", 10: "STO", 11: "CRG",
              12: "DEP", 13: "WTH", 14: "RBT", 15: "RFD"}
DEAL_ENTRY = {0: "IN", 1: "OUT", 2: "INOUT", 3: "OUT_BY"}

for d in sorted(deals, key=lambda x: x.time):
    t = datetime.fromtimestamp(d.time).strftime("%Y-%m-%d %H:%M:%S")
    typ = DEAL_TYPES.get(d.type, f"T{d.type}")
    ent = DEAL_ENTRY.get(d.entry, f"E{d.entry}")
    print(f"{t:<20} {d.symbol:<10} {typ:<6} {ent:<8} {d.volume:<6.2f} {d.price:<12.5f} {d.profit:>+8.2f} {d.comment}")

print()
print("=== Position changes summary ===")
in_count = sum(1 for d in deals if d.entry == 0)
out_count = sum(1 for d in deals if d.entry == 1)
print(f"  Position OPENED (entry=IN):  {in_count}")
print(f"  Position CLOSED (entry=OUT): {out_count}")
total_profit_closed = sum(d.profit for d in deals if d.entry == 1)
print(f"  Total realized P/L on closes: {total_profit_closed:+.2f}")

mt5.shutdown()
