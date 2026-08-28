"""Daily P/L summary to Telegram (run via schtask at 23:00 IST)."""
from __future__ import annotations

import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
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
        print(f"mt5.initialize failed: {mt5.last_error()}")
        return 1

    ai = mt5.account_info()
    pos = mt5.positions_get() or []

    # Last 24h closed deals
    since = datetime.now() - timedelta(hours=24)
    deals = mt5.history_deals_get(since, datetime.now()) or []
    closed = [d for d in deals if d.entry == mt5.DEAL_ENTRY_OUT]
    wins = [d for d in closed if d.profit > 0]
    losses = [d for d in closed if d.profit < 0]
    total_realized = sum(d.profit for d in closed)
    floating = sum(p.profit for p in pos)
    wr = (len(wins) / len(closed) * 100) if closed else 0
    avg_win = (sum(d.profit for d in wins) / len(wins)) if wins else 0
    avg_loss = (sum(d.profit for d in losses) / len(losses)) if losses else 0

    # Per-symbol breakdown
    by_sym = defaultdict(lambda: {"wins": 0, "losses": 0, "pnl": 0.0})
    for d in closed:
        s = by_sym[d.symbol]
        if d.profit > 0:
            s["wins"] += 1
        elif d.profit < 0:
            s["losses"] += 1
        s["pnl"] += d.profit

    msg_lines = [
        "<b>📊 DAILY SUMMARY (last 24h)</b>",
        "",
        f"<b>Account:</b>",
        f"  Balance: <code>${ai.balance:.2f}</code>",
        f"  Equity:  <code>${ai.equity:.2f}</code>",
        f"  Open positions: <b>{len(pos)}</b>",
        f"  Floating P/L: <b>{floating:+.2f}</b>",
        "",
        f"<b>Trades closed today: {len(closed)}</b>",
        f"  Wins: <b>{len(wins)}</b>  Losses: <b>{len(losses)}</b>  WR: <b>{wr:.0f}%</b>",
        f"  Realized P/L: <b>{total_realized:+.2f}</b>",
    ]
    if wins:
        msg_lines.append(f"  Avg win: +{avg_win:.2f}")
    if losses:
        msg_lines.append(f"  Avg loss: {avg_loss:.2f}")
    if by_sym:
        msg_lines.append("")
        msg_lines.append("<b>Per pair:</b>")
        for sym in sorted(by_sym.keys()):
            s = by_sym[sym]
            sign = "+" if s["pnl"] >= 0 else ""
            msg_lines.append(f"  {sym}: {s['wins']}W/{s['losses']}L  {sign}{s['pnl']:.2f}")

    if pos:
        msg_lines.append("")
        msg_lines.append("<b>Currently open:</b>")
        for p in sorted(pos, key=lambda x: x.symbol):
            d = "BUY" if p.type == 0 else "SELL"
            msg_lines.append(f"  {p.symbol} {d} @{p.price_open:.5f} → P/L {p.profit:+.2f}")

    msg = "\n".join(msg_lines)
    tg = get_notifier()
    ok = tg.send(msg) if tg else False
    print(f"Daily summary sent: {ok}")
    mt5.shutdown()
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
