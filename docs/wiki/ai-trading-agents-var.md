# ai-trading-agents-var

## Overview

Community of 16 nodes

- **Size**: 16 nodes
- **Cohesion**: 0.2847
- **Dominant Language**: python

## Members

| Name | Kind | File | Lines |
|------|------|------|-------|
| VaRResult | Class | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\portfolio_risk.py | 40-64 |
| as_dict | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\portfolio_risk.py | 52-64 |
| _extract_pnl | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\portfolio_risk.py | 67-81 |
| _moments | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\portfolio_risk.py | 84-96 |
| historical_var | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\portfolio_risk.py | 99-114 |
| parametric_var | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\portfolio_risk.py | 117-134 |
| cornish_fisher_var | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\portfolio_risk.py | 137-163 |
| snapshot | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\portfolio_risk.py | 166-172 |
| test_insufficient_samples_returns_zeros | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_portfolio_risk.py | 16-19 |
| test_historical_var_positive_for_losses | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_portfolio_risk.py | 22-28 |
| test_parametric_var_normal_formula | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_portfolio_risk.py | 31-36 |
| test_cornish_fisher_handles_fat_tails_safely | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_portfolio_risk.py | 39-53 |
| test_snapshot_has_all_three_methods | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_portfolio_risk.py | 56-63 |
| test_handles_dict_shaped_entries | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_portfolio_risk.py | 66-70 |
| test_confidence_level_affects_var | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_portfolio_risk.py | 73-78 |
| test_as_dict_roundtrip | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_portfolio_risk.py | 81-86 |

## Execution Flows

No execution flows pass through this community.

## Dependencies

### Outgoing

- `float` (9 edge(s))
- `round` (8 edge(s))
- `max` (6 edge(s))
- `len` (5 edge(s))
- `mean` (4 edge(s))
- `isfinite` (4 edge(s))
- `get` (3 edge(s))
- `array` (3 edge(s))
- `default_rng` (3 edge(s))
- `normal` (3 edge(s))
- `tolist` (3 edge(s))
- `isinstance` (2 edge(s))
- `exp` (2 edge(s))
- `sqrt` (2 edge(s))
- `quantile` (2 edge(s))

### Incoming

- `C:\Users\Ratanshila\Documents\autmated trading\tests\test_portfolio_risk.py` (8 edge(s))
- `C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\portfolio_risk.py` (7 edge(s))
- `default_rng` (3 edge(s))
- `normal` (3 edge(s))
- `tolist` (3 edge(s))
- `as_dict` (1 edge(s))
- `list` (1 edge(s))
- `range` (1 edge(s))
- `standard_t` (1 edge(s))
- `concatenate` (1 edge(s))
- `enumerate` (1 edge(s))
- `abs` (1 edge(s))
