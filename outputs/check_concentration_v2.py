"""Show open positions classified by USD direction concentration."""
import MetaTrader5 as mt5
from datetime import datetime
from pathlib import Path

OUT = Path(r"C:\Users\Ratanshila\Documents\autmated trading\outputs\concentration_check.txt")

if not mt5.initialize():
    OUT.write_text(f"MT5 init failed: {mt5.last_error()}", encoding="utf-8")
    raise SystemExit(1)

def classify(sym, side):
    s = sym.upper()
    if s.startswith("USD"):
        return "LONG-USD" if side == "BUY" else "SHORT-USD"
    if s.endswith("USD"):
        return "LONG-USD" if side == "SELL" else "SHORT-USD"
    return "neutral"

pos = mt5.positions_get() or []
ai = mt5.account_info()

lines = [
    f"=== Concentration check — {datetime.now()} ===",
    f"Account {ai.login} balance=${ai.balance:.2f} equity=${ai.equity:.2f}",
    f"Open positions: {len(pos)}",
    "",
]

long_usd, short_usd, neutral = [], [], []
for p in pos:
    side = "BUY" if p.type == mt5.ORDER_TYPE_BUY else "SELL"
    cls = classify(p.symbol, side)
    opened = datetime.fromtimestamp(p.time).strftime("%H:%M:%S")
    row = f"  {p.symbol:<8} {side:<4} {p.volume:.2f} @ {p.price_open:.5f}  opened {opened}  PnL ${p.profit:+.2f}  [{cls}]"
    if cls == "LONG-USD": long_usd.append(row)
    elif cls == "SHORT-USD": short_usd.append(row)
    else: neutral.append(row)

lines.append(f"LONG-USD positions ({len(long_usd)}/3):")
lines.extend(long_usd or ["  (none)"])
lines.append("")
lines.append(f"SHORT-USD positions ({len(short_usd)}/3):")
lines.extend(short_usd or ["  (none)"])
lines.append("")
lines.append(f"Neutral cross-pairs ({len(neutral)}):")
lines.extend(neutral or ["  (none)"])
lines.append("")
lines.append("Safeguard cap: 3 long-USD AND 3 short-USD")
if len(long_usd) >= 3:
    lines.append("→ ETHUSD SELL (long-USD) is BLOCKED until one of the 3 above closes.")
else:
    lines.append("→ ETHUSD SELL would have capacity to fire if it came now.")

OUT.write_text("\n".join(lines), encoding="utf-8")
mt5.shutdown()
