"""Hourly account snapshot to Telegram (light)."""
from __future__ import annotations

import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import MetaTrader5 as mt5
from ai_trading_agents.telegram_notifier import get_notifier


def main():
    if not mt5.initialize():
        return 1
    ai = mt5.account_info()
    pos = mt5.positions_get() or []
    floating = sum(p.profit for p in pos)

    # Skip if nothing meaningful (no positions and no recent change)
    if not pos:
        msg = (
            f"<b>⏱ Hourly snapshot</b>\n"
            f"Balance: ${ai.balance:.2f}  Equity: ${ai.equity:.2f}\n"
            f"No open positions.  Waiting for TrendMaster brain signal."
        )
    else:
        lines = [f"<b>⏱ Hourly snapshot</b>",
                 f"Balance: ${ai.balance:.2f}  Equity: ${ai.equity:.2f}",
                 f"Positions: {len(pos)}  Floating: {floating:+.2f}", ""]
        for p in sorted(pos, key=lambda x: x.symbol):
            d = "📈" if p.type == 0 else "📉"
            mark = "🟢" if p.profit >= 0 else "🔴"
            lines.append(f"  {mark} {p.symbol} {d} {p.profit:+.2f}")
        msg = "\n".join(lines)

    tg = get_notifier()
    if tg:
        tg.send(msg)
    mt5.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
