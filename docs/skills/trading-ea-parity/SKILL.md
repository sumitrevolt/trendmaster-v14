---
name: trading-ea-parity
description: "Run the ea_parity backtest that replays historical bars through the EA's confirmation logic and compares it against the Python brain's acceptance path. Use when gate thresholds change, EA inputs change, or for nightly drift detection. Catches silent regressions where the brain and the EA quietly diverge on the same bar."
---

# trading-ea-parity

Bar-by-bar parity check between `ea_confirmations.compute_confirmations()` (the EA's rule set, reproduced in Python) and the brain's acceptance path. If the two diverge, one of two things happened: the EA ported the wrong rule, or the brain introduced a silent regression during refactoring.

This is the load-bearing sanity check before any gate or EA-input change goes live.

## When to use

- Changed any gate in `config/settings.py` (`require_all_3`, `max_spread_atr_pct`, confidence floor, etc.)
- Changed EA input parameters (`InpPartial1Pct`, `InpPyramidR`, etc.)
- EA rejection rate spiked (EA rejecting signals the brain accepted)
- Nightly automated drift detection (see `tools/ea_parity_nightly.py`)

## Manual run

```
python tools\backtest.py ea_parity data\xauusd_m5_history.csv --sl-atr-mult 1.5 --tp-atr-mult 3.0
```

**Note:** the subcommand is `ea_parity` (underscore), not `ea-parity`.

CSV must have OHLCV columns plus a time column. Output is printed as JSON to stdout.

## Programmatic

```python
import pandas as pd
from tools.backtest import run_ea_parity_backtest

df = pd.read_csv("data/xauusd_m5_history.csv", parse_dates=["time"])
result = run_ea_parity_backtest(df, sl_atr_mult=1.5, tp_atr_mult=3.0)
# {
#   "bars_scanned": int,
#   "trades": int, "wins": int, "losses": int,
#   "win_rate": float,  "expectancy_R": float,
#   "gross_R": float,   "sharpe_proxy": float,
# }
```

## Nightly automation

`tools/ea_parity_nightly.py` runs this across all configured symbols, diffs against `reports/ea_parity_baseline.json`, and posts a Telegram alert if divergence exceeds thresholds. Install with:

```
install_ea_parity_nightly.bat
```

Runs at 02:30 local time, Mon–Fri (broker weekend). First run creates the baseline; subsequent runs diff against it.

## Interpreting divergence

| Metric              | Safe band    | Action threshold | What it means                                                 |
|---------------------|--------------|------------------|---------------------------------------------------------------|
| `bars_scanned` diff | < 0.5%       | > 1%             | Historical CSV changed — check data freshness first           |
| `trades` diff       | < 2%         | > 5%             | Gate or EA rule changed; intentional? Confirm in git log      |
| `win_rate` diff     | < 2 pp       | > 5 pp           | Meaningful behavior shift — investigate before committing     |
| `expectancy_R` diff | < 0.05       | > 0.15           | EA and brain are diverging — lock down the gate change        |

## Pairs well with

- `trading-why-inspector` — once you see divergence, drill into which signal was treated differently
- `trading-brain-restart` — after a gate change that passed parity, restart to pick up the new config

## Baseline management

- First run: `reports/ea_parity_baseline.json` is created from the current run.
- To reset the baseline (e.g., after an intentional rule change): delete the file and run the nightly once manually.
- Baselines are per-symbol; add or remove symbols by editing `SYMBOLS_FOR_PARITY` in `tools/ea_parity_nightly.py`.
