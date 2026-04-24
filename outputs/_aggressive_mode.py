"""Show projection at different risk levels."""
import json, sys
from pathlib import Path
root = Path(r"C:\Users\Ratanshila\Documents\autmated trading")
sys.path.insert(0, str(root))
from ai_trading_agents.pair_params import PAIR_PARAMS

ACCOUNT = 546.55
BARS_PER_SYM = 50000
BARS_PER_DAY = 288
DAYS_PER_SYM = BARS_PER_SYM / BARS_PER_DAY
LIVE_ADJ = 0.55
TOTAL_R = sum(p["gross_r"] for p in PAIR_PARAMS.values())

print("="*75)
print(f"  RISK-SCALING MODES — Account ${ACCOUNT:.2f}, {len(PAIR_PARAMS)} deployed pairs")
print("="*75)
print(f"{'Mode':24s}  {'Risk/trade':>10s} {'Max DD est':>11s}  "
      f"{'$/day':>8s} {'%/day':>7s} {'%/year':>8s}")
print("-"*75)

for label, risk_pct, dd_est in [
    ("CURRENT (safe)",       0.005, "8%"),
    ("BALANCED",              0.010, "15%"),
    ("AGGRESSIVE",            0.015, "22%"),
    ("VERY AGGRESSIVE",       0.025, "35%"),
    ("MAX KELLY (risky)",     0.040, "55%"),
    ("SUICIDE (don't)",       0.080, ">80%"),
]:
    risk_per_trade = ACCOUNT * risk_pct
    live_dollars_year = TOTAL_R * risk_per_trade * (365 / DAYS_PER_SYM) * LIVE_ADJ
    per_day = live_dollars_year / 365
    pct_year = live_dollars_year / ACCOUNT * 100
    pct_day = per_day / ACCOUNT * 100
    print(f"{label:24s}  {risk_pct*100:>9.1f}% {dd_est:>11s}  "
          f"${per_day:>7.2f} {pct_day:>6.2f}% {pct_year:>7.0f}%")
print()
print("NOTES:")
print("  - 0.5%/trade (CURRENT) is industry-conservative, survives all scenarios.")
print("  - 1.0-1.5% is typical retail max — pushes returns 2-3x with manageable DD.")
print("  - 2.5%+ hits Kelly-fraction territory, DD can exceed 30% on losing streaks.")
print("  - 4%+ is pure gambling — one bad streak = account death.")
print()
print("SAFE-AGGRESSIVE recommendation: 1.0% risk/trade")
print("  → ~3.8%/day, ~1,400%/year projected (backtest × 0.55 realism)")
print("  → Max drawdown estimate: 15% ($82 on $546)")
