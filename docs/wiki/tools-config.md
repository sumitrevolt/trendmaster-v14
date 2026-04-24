# tools-config

## Overview

Community of 21 nodes

- **Size**: 21 nodes
- **Cohesion**: 0.1702
- **Dominant Language**: python

## Members

| Name | Kind | File | Lines |
|------|------|------|-------|
| _atr | Function | C:\Users\Ratanshila\Documents\autmated trading\tools\backtest_filtered.py | 32-37 |
| _ema | Function | C:\Users\Ratanshila\Documents\autmated trading\tools\backtest_filtered.py | 40-41 |
| _adx | Function | C:\Users\Ratanshila\Documents\autmated trading\tools\backtest_filtered.py | 44-56 |
| _bollinger | Function | C:\Users\Ratanshila\Documents\autmated trading\tools\backtest_filtered.py | 59-62 |
| _macd_hist | Function | C:\Users\Ratanshila\Documents\autmated trading\tools\backtest_filtered.py | 65-67 |
| _super_trend | Function | C:\Users\Ratanshila\Documents\autmated trading\tools\backtest_filtered.py | 70-84 |
| FilterConfig | Class | C:\Users\Ratanshila\Documents\autmated trading\tools\backtest_filtered.py | 88-97 |
| BacktestResult | Class | C:\Users\Ratanshila\Documents\autmated trading\tools\backtest_filtered.py | 101-114 |
| as_dict | Function | C:\Users\Ratanshila\Documents\autmated trading\tools\backtest_filtered.py | 113-114 |
| backtest_1to3 | Function | C:\Users\Ratanshila\Documents\autmated trading\tools\backtest_filtered.py | 117-257 |
| grid_search | Function | C:\Users\Ratanshila\Documents\autmated trading\tools\backtest_filtered.py | 260-312 |
| main | Function | C:\Users\Ratanshila\Documents\autmated trading\tools\backtest_filtered.py | 315-348 |
| ProConfig | Class | C:\Users\Ratanshila\Documents\autmated trading\tools\backtest_pro.py | 49-72 |
| ProResult | Class | C:\Users\Ratanshila\Documents\autmated trading\tools\backtest_pro.py | 76-93 |
| as_dict | Function | C:\Users\Ratanshila\Documents\autmated trading\tools\backtest_pro.py | 92-93 |
| backtest_pro | Function | C:\Users\Ratanshila\Documents\autmated trading\tools\backtest_pro.py | 96-300 |
| main | Function | C:\Users\Ratanshila\Documents\autmated trading\tools\backtest_pro.py | 303-360 |
| main | Function | C:\Users\Ratanshila\Documents\autmated trading\tools\backtest_rr_sweep.py | 19-65 |
| score_config | Function | C:\Users\Ratanshila\Documents\autmated trading\tools\optimize_per_pair.py | 61-67 |
| optimize_symbol | Function | C:\Users\Ratanshila\Documents\autmated trading\tools\optimize_per_pair.py | 70-121 |
| main | Function | C:\Users\Ratanshila\Documents\autmated trading\tools\optimize_per_pair.py | 124-233 |

## Execution Flows

- **main** (criticality: 0.46, depth: 3)
- **main** (criticality: 0.45, depth: 2)
- **main** (criticality: 0.45, depth: 2)
- **main** (criticality: 0.38, depth: 3)

## Dependencies

### Outgoing

- `print` (34 edge(s))
- `append` (23 edge(s))
- `len` (19 edge(s))
- `mean` (10 edge(s))
- `max` (8 edge(s))
- `float` (8 edge(s))
- `get` (8 edge(s))
- `rolling` (6 edge(s))
- `round` (6 edge(s))
- `abs` (5 edge(s))
- `ewm` (5 edge(s))
- `shift` (4 edge(s))
- `sum` (4 edge(s))
- `isfinite` (4 edge(s))
- `min` (4 edge(s))

### Incoming

- `C:\Users\Ratanshila\Documents\autmated trading\tools\backtest_filtered.py` (11 edge(s))
- `C:\Users\Ratanshila\Documents\autmated trading\tools\backtest_pro.py` (4 edge(s))
- `C:\Users\Ratanshila\Documents\autmated trading\tools\optimize_per_pair.py` (3 edge(s))
- `C:\Users\Ratanshila\Documents\autmated trading\tools\backtest_rr_sweep.py` (1 edge(s))
