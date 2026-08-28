"""Send a status snapshot to Telegram."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from ai_trading_agents.telegram_notifier import get_notifier
import MetaTrader5 as mt5

mt5.initialize()
ai = mt5.account_info()
pos = mt5.positions_get() or []
fp = sum(p.profit for p in pos)
mt5.shutdown()

tg = get_notifier()
msg = (
    "<b>TrendMaster Pipeline ALIVE</b>\n"
    "Telegram notifications now wired:\n"
    "• On every order open\n"
    "• On every order close (with P/L)\n"
    "• Source: Rocket Prime indicator only\n\n"
    "<b>Account snapshot:</b>\n"
    f"Balance: ${ai.balance:.2f}  Equity: ${ai.equity:.2f}\n"
    f"Open positions: {len(pos)}  Floating P/L: {fp:+.2f}\n"
    "SL widened to 2.5x ATR(H1) on all pairs.\n\n"
    "<i>Next signal from Rocket Prime triggers next trade.</i>"
)
ok = tg.send(msg)
print(f"Telegram sent: {ok}")
print(f"Notifier enabled: {tg.enabled}")
