"""Check recent BTCUSD trades in MT5."""
import MetaTrader5 as mt5
import time
from datetime import datetime
from pathlib import Path

OUT = Path(r"C:\Users\Ratanshila\Documents\autmated trading\outputs\btc_trade_check.txt")

with open(OUT, "w", encoding="utf-8") as f:
    if not mt5.initialize():
        f.write(f"MT5 init failed: {mt5.last_error()}\n")
        raise SystemExit(1)

    f.write(f"=== BTC trade check — {datetime.now()} ===\n\n")
    ai = mt5.account_info()
    f.write(f"Account {ai.login} balance=${ai.balance:.2f} equity=${ai.equity:.2f}\n\n")

    # Recent deals last 2 hours
    from_dt = int(time.time() - 7200)
    deals = mt5.history_deals_get(datetime.fromtimestamp(from_dt), datetime.now()) or []
    f.write(f"Deals last 2h ({len(deals)} total):\n")
    for d in deals[-15:]:
        action = "BUY" if d.type == 0 else "SELL" if d.type == 1 else "?"
        dt_str = datetime.fromtimestamp(d.time).strftime("%H:%M:%S")
        f.write(f"  {dt_str} | {d.symbol:<10} {action} | vol={d.volume} price={d.price:.5f} | "
                f"profit=${d.profit:+.2f} | comment='{d.comment}' | entry={d.entry}\n")

    # Open positions
    f.write(f"\nOpen positions:\n")
    pos = mt5.positions_get() or []
    for p in pos:
        d = "BUY" if p.type == 0 else "SELL"
        opened = datetime.fromtimestamp(p.time).strftime("%H:%M:%S")
        f.write(f"  {p.symbol:<10} {d} {p.volume} @ {p.price_open:.5f} (opened {opened}) | PnL: ${p.profit:+.2f}\n")

    mt5.shutdown()
