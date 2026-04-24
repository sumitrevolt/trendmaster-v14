# tests-corr

## Overview

Community of 17 nodes

- **Size**: 17 nodes
- **Cohesion**: 0.2687
- **Dominant Language**: python

## Members

| Name | Kind | File | Lines |
|------|------|------|-------|
| CorrViolation | Class | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\rolling_corr.py | 56-68 |
| as_dict | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\rolling_corr.py | 62-68 |
| RollingCorrMatrix | Class | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\rolling_corr.py | 72-168 |
| update_bar | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\rolling_corr.py | 80-93 |
| corr | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\rolling_corr.py | 96-113 |
| check | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\rolling_corr.py | 116-163 |
| coverage | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\rolling_corr.py | 166-168 |
| _synthetic_walk | Function | C:\Users\Ratanshila\Documents\autmated trading\tests\test_rolling_corr.py | 13-16 |
| test_corr_returns_none_when_window_not_full | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_rolling_corr.py | 19-23 |
| test_corr_near_plus_one_for_copy | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_rolling_corr.py | 26-34 |
| test_corr_near_minus_one_for_mirror | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_rolling_corr.py | 37-45 |
| test_check_blocks_same_direction_high_corr | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_rolling_corr.py | 48-57 |
| test_check_blocks_anti_corr_with_opposite_side | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_rolling_corr.py | 60-69 |
| test_check_allows_independent_pair | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_rolling_corr.py | 72-80 |
| test_dict_positions_supported | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_rolling_corr.py | 83-90 |
| test_coverage_reports_per_symbol_bars | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_rolling_corr.py | 93-99 |
| test_invalid_price_ignored | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_rolling_corr.py | 102-106 |

## Execution Flows

- **check** (criticality: 0.36, depth: 1)

## Dependencies

### Outgoing

- `update_bar` (10 edge(s))
- `get` (4 edge(s))
- `float` (4 edge(s))
- `check` (4 edge(s))
- `list` (3 edge(s))
- `corr` (3 edge(s))
- `getattr` (2 edge(s))
- `isinstance` (2 edge(s))
- `len` (2 edge(s))
- `diff` (2 edge(s))
- `log` (2 edge(s))
- `clip` (2 edge(s))
- `asarray` (2 edge(s))
- `range` (2 edge(s))
- `type` (2 edge(s))

### Incoming

- `C:\Users\Ratanshila\Documents\autmated trading\tests\test_rolling_corr.py` (10 edge(s))
- `update_bar` (10 edge(s))
- `check` (4 edge(s))
- `corr` (3 edge(s))
- `C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\rolling_corr.py` (2 edge(s))
- `range` (2 edge(s))
- `type` (2 edge(s))
- `Random` (1 edge(s))
- `gauss` (1 edge(s))
- `coverage` (1 edge(s))
