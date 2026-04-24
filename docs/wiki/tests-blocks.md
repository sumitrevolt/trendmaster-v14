# tests-blocks

## Overview

Community of 31 nodes

- **Size**: 31 nodes
- **Cohesion**: 0.3453
- **Dominant Language**: python

## Members

| Name | Kind | File | Lines |
|------|------|------|-------|
| FilterDecision | Class | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\profit_filters.py | 36-46 |
| as_dict | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\profit_filters.py | 41-46 |
| spread_guard | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\profit_filters.py | 52-78 |
| volatility_regime | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\profit_filters.py | 84-115 |
| daily_profit_lock | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\profit_filters.py | 121-139 |
| loss_streak_cooldown | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\profit_filters.py | 145-196 |
| _pnl_of | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\profit_filters.py | 166-178 |
| daily_loss_limit | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\profit_filters.py | 202-255 |
| _load_news_calendar | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\profit_filters.py | 284-314 |
| news_blackout | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\profit_filters.py | 317-344 |
| session_window | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\profit_filters.py | 350-364 |
| CombinedDecision | Class | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\profit_filters.py | 371-381 |
| as_dict | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\profit_filters.py | 377-381 |
| evaluate_all | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\profit_filters.py | 384-451 |
| test_spread_guard_allows_tight_spread | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_profit_filters.py | 17-20 |
| test_spread_guard_blocks_wide_spread | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_profit_filters.py | 22-25 |
| test_spread_guard_zero_atr_blocks | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_profit_filters.py | 27-29 |
| _atr_sample | Function | C:\Users\Ratanshila\Documents\autmated trading\tests\test_profit_filters.py | 33-35 |
| test_vol_regime_dead_market_blocks | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_profit_filters.py | 37-42 |
| test_vol_regime_spike_blocks | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_profit_filters.py | 44-49 |
| test_vol_regime_normal_allows | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_profit_filters.py | 51-54 |
| test_vol_regime_insufficient_samples_passes | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_profit_filters.py | 56-59 |
| test_profit_lock_blocks_after_target | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_profit_filters.py | 63-66 |
| test_profit_lock_allows_below_target | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_profit_filters.py | 68-70 |
| test_loss_streak_blocks_after_three_losses | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_profit_filters.py | 74-76 |
| test_loss_streak_allows_when_short | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_profit_filters.py | 78-80 |
| test_loss_streak_cooldown_flag_overrides | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_profit_filters.py | 82-84 |
| test_session_window_inside_best_hours | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_profit_filters.py | 88-92 |
| test_session_window_blocks_off_hours | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_profit_filters.py | 94-97 |
| test_evaluate_all_happy_path | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_profit_filters.py | 101-112 |
| test_evaluate_all_any_veto_blocks | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_profit_filters.py | 114-124 |

## Execution Flows

- **main** (criticality: 0.72, depth: 5)
- **scan_once** (criticality: 0.61, depth: 3)
- **main** (criticality: 0.55, depth: 4)

## Dependencies

### Outgoing

- `get` (20 edge(s))
- `float` (15 edge(s))
- `abs` (6 edge(s))
- `int` (5 edge(s))
- `Series` (5 edge(s))
- `quantile` (4 edge(s))
- `datetime` (4 edge(s))
- `isinstance` (3 edge(s))
- `range` (3 edge(s))
- `list` (3 edge(s))
- `round` (2 edge(s))
- `replace` (2 edge(s))
- `lower` (2 edge(s))
- `values` (2 edge(s))
- `items` (2 edge(s))

### Incoming

- `C:\Users\Ratanshila\Documents\autmated trading\tests\test_profit_filters.py` (17 edge(s))
- `C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\profit_filters.py` (12 edge(s))
- `datetime` (4 edge(s))
- `Series` (3 edge(s))
- `concat` (2 edge(s))
- `C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\multi_market_dispatcher.py::scan_once` (1 edge(s))
- `C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\trend_master_brain.py::TrendMasterBrain.tick_once` (1 edge(s))
- `C:\Users\Ratanshila\Documents\autmated trading\tools\backtest_profit_filters.py::run_strategy` (1 edge(s))
- `any` (1 edge(s))
- `rand` (1 edge(s))
- `max` (1 edge(s))
