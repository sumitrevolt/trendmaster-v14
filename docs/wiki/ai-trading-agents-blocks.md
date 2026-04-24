# ai-trading-agents-blocks

## Overview

Community of 29 nodes

- **Size**: 29 nodes
- **Cohesion**: 0.5735
- **Dominant Language**: python

## Members

| Name | Kind | File | Lines |
|------|------|------|-------|
| _csv_path | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\multi_market_dispatcher.py | 39-40 |
| _resample_m5_to | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\multi_market_dispatcher.py | 43-52 |
| load_frames | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\multi_market_dispatcher.py | 55-87 |
| _profit_filter_cfg | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\multi_market_dispatcher.py | 90-91 |
| _last_atr | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\multi_market_dispatcher.py | 94-102 |
| scan_once | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\multi_market_dispatcher.py | 105-177 |
| team_of | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\risk_manager.py | 34-39 |
| Position | Class | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\risk_manager.py | 54-60 |
| RiskConfig | Class | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\risk_manager.py | 64-74 |
| RiskDecision | Class | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\risk_manager.py | 78-84 |
| as_dict | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\risk_manager.py | 83-84 |
| RiskState | Class | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\risk_manager.py | 88-93 |
| size_position | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\risk_manager.py | 96-107 |
| _corr_conflict | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\risk_manager.py | 110-121 |
| _loss_streak | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\risk_manager.py | 124-133 |
| check_risk | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\risk_manager.py | 136-185 |
| test_team_of_known_symbols | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_risk_manager.py | 11-16 |
| test_size_position_scales_with_equity | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_risk_manager.py | 19-26 |
| test_size_position_caps_at_max_lot | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_risk_manager.py | 29-33 |
| test_size_position_bad_inputs_zero | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_risk_manager.py | 36-39 |
| test_daily_loss_stop_blocks_trade | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_risk_manager.py | 42-47 |
| test_global_concurrency_blocks_trade | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_risk_manager.py | 50-57 |
| test_team_cap_blocks | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_risk_manager.py | 60-68 |
| test_correlation_cap_blocks_stacked_longs | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_risk_manager.py | 71-79 |
| test_happy_path_allows_trade | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_risk_manager.py | 82-86 |
| test_daily_profit_lock_blocks_after_target | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_risk_manager.py | 90-95 |
| test_daily_profit_lock_allows_below_target | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_risk_manager.py | 98-102 |
| test_loss_streak_blocks_after_n_losses | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_risk_manager.py | 105-113 |
| test_cooldown_active_blocks | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_risk_manager.py | 116-121 |

## Execution Flows

- **scan_once** (criticality: 0.61, depth: 3)

## Dependencies

### Outgoing

- `len` (8 edge(s))
- `getattr` (4 edge(s))
- `max` (3 edge(s))
- `get` (3 edge(s))
- `min` (3 edge(s))
- `as_dict` (3 edge(s))
- `dropna` (2 edge(s))
- `float` (2 edge(s))
- `to_datetime` (2 edge(s))
- `set_index` (2 edge(s))
- `round` (2 edge(s))
- `lower` (1 edge(s))
- `Series` (1 edge(s))
- `concat` (1 edge(s))
- `abs` (1 edge(s))

### Incoming

- `C:\Users\Ratanshila\Documents\autmated trading\tests\test_risk_manager.py` (13 edge(s))
- `C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\risk_manager.py` (9 edge(s))
- `C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\multi_market_dispatcher.py` (6 edge(s))
