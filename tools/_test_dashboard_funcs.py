"""Test each dashboard function in isolation."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
import MetaTrader5 as mt5
mt5.initialize()

from tools.dashboard_server import (
    get_account_state, get_per_pair_pnl, get_spread_monitor,
    get_trade_duration_stats, get_brain_learning_stats,
    get_news_calendar, get_recent_signals,
)

print("=== Account ===")
a = get_account_state()
print(f"  balance={a.get('balance')} positions={a.get('n_positions')}")

print("=== Per-pair P/L (168h) ===")
p = get_per_pair_pnl(168)
print(f"  pairs returned: {len(p)}")
for r in p[:5]:
    print(f"    {r['symbol']}: closed={r['n_closed']} total_pl={r['total_pl']}")

print("=== Spread monitor ===")
s = get_spread_monitor()
print(f"  pairs: {len(s)}")
for r in s[:3]:
    print(f"    {r['symbol']}: spread={r['spread_pts']}pts ratio={r['ratio_pct']}%")

print("=== Duration ===")
d = get_trade_duration_stats(168)
print(f"  all: {d.get('all')}")
print(f"  quick: {d.get('quick')}")
print(f"  trend: {d.get('trend')}")

print("=== Brain learning ===")
bl = get_brain_learning_stats()
print(f"  total outcomes: {bl.get('total')}")
print(f"  classes: {len(bl.get('by_class', []))}")

print("=== News ===")
n = get_news_calendar()
print(f"  events upcoming: {len(n)}")
