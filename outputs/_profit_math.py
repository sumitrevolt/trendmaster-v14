"""Honest profit projection math from deployed config."""
import json
import sys
from pathlib import Path

root = Path(r"C:\Users\Ratanshila\Documents\autmated trading")
sys.path.insert(0, str(root))

from ai_trading_agents.pair_params import PAIR_PARAMS

ACCOUNT = 546.55
RISK_PCT = 0.005  # 0.5% per trade (current)
RISK_PER_TRADE = ACCOUNT * RISK_PCT   # ~$2.73

BARS_PER_SYMBOL = 50_000
BARS_PER_DAY = 288   # M5 bars in 24h
DAYS_PER_SYMBOL = BARS_PER_SYMBOL / BARS_PER_DAY   # ~174 days

print("="*75)
print(f"  PROFIT PROJECTION — Account ${ACCOUNT:.2f}, risk {RISK_PCT*100}%/trade")
print("="*75)
print()
print(f"{'Symbol':8s}  {'n':>5s} {'exp(R)':>7s} {'gross R':>8s} "
      f"{'$/sym/yr':>9s} {'$/sym/day':>10s}")
print("-"*75)

total_r = 0
total_dollars = 0
for sym, p in sorted(PAIR_PARAMS.items(), key=lambda kv: -kv[1]["gross_r"]):
    n = p["trades_bt"]
    gross = p["gross_r"]
    exp = p["expected_exp"]
    total_r += gross
    # Over 50K bars ≈ 174 days. Project to 365 calendar days.
    dollars_per_sym_year = gross * RISK_PER_TRADE * (365 / DAYS_PER_SYMBOL)
    dollars_per_sym_day = dollars_per_sym_year / 365
    total_dollars += dollars_per_sym_year
    print(f"{sym:8s}  {n:>5d} {exp:+7.3f} {gross:+8.2f} "
          f"${dollars_per_sym_year:>8.0f} ${dollars_per_sym_day:>9.2f}")

print()
print(f"TOTAL across all deployed pairs:")
print(f"  Gross R per year (all 18 syms parallel): +{total_r * (365/DAYS_PER_SYMBOL):.0f}R")
print(f"  Dollar profit per year (backtest raw):   +${total_dollars:,.0f}")
print()
# Live adjustments
live_adj = 0.55   # 0.85 WR × 0.90 slippage × 0.70 realistic = ~0.55
live_dollars = total_dollars * live_adj
live_per_day = live_dollars / 365
live_per_pair_per_day = live_per_day / len(PAIR_PARAMS)
print(f"Live-adjusted (×0.55 realism):")
print(f"  Projected profit/year:         ${live_dollars:,.0f}  "
      f"({live_dollars/ACCOUNT*100:+.1f}% on $546)")
print(f"  Projected profit/day (total):  ${live_per_day:.2f}  "
      f"({live_per_day/ACCOUNT*100:+.2f}% daily)")
print(f"  Per pair per day:              ${live_per_pair_per_day:.2f}  "
      f"({live_per_pair_per_day/ACCOUNT*100:+.3f}% per pair/day)")
print()
print("="*75)
print("  WHAT 1%/pair/day WOULD REQUIRE")
print("="*75)
target_per_pair_per_day = ACCOUNT * 0.01
total_per_day = target_per_pair_per_day * len(PAIR_PARAMS)
print(f"  Target: 1% of ${ACCOUNT} = ${target_per_pair_per_day:.2f}/pair/day")
print(f"  × {len(PAIR_PARAMS)} pairs = ${total_per_day:.2f}/day total")
print(f"  × 365 days = ${total_per_day*365:,.0f}/year")
print(f"  = {total_per_day*365/ACCOUNT*100:,.0f}% annual return (impossible)")
print()
print(f"  To chase it, would need {target_per_pair_per_day / live_per_pair_per_day:.1f}x "
      f"more aggressive risk sizing.")
