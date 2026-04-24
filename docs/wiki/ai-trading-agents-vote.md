# ai-trading-agents-vote

## Overview

Community of 26 nodes

- **Size**: 26 nodes
- **Cohesion**: 0.2874
- **Dominant Language**: python

## Members

| Name | Kind | File | Lines |
|------|------|------|-------|
| _ema | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\multi_agent.py | 37-38 |
| _rsi | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\multi_agent.py | 41-46 |
| _macd_hist | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\multi_agent.py | 49-52 |
| _adx | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\multi_agent.py | 55-69 |
| AgentVote | Class | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\multi_agent.py | 74-80 |
| as_dict | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\multi_agent.py | 79-80 |
| trend_agent_h4 | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\multi_agent.py | 84-100 |
| momentum_agent_h1 | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\multi_agent.py | 103-116 |
| timing_agent_m30 | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\multi_agent.py | 119-136 |
| vote_all | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\multi_agent.py | 140-157 |
| test_agent_vote_serializes | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_multi_agent.py | 11-14 |
| test_insufficient_bars_yield_zero_vote | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_multi_agent.py | 17-25 |
| test_bullish_frames_vote_buy_or_abstain | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_multi_agent.py | 28-33 |
| test_sideways_frames_dont_force_trade | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_multi_agent.py | 36-39 |
| test_vote_all_requires_unanimity | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_multi_agent.py | 42-64 |
| _stub_bull | Function | C:\Users\Ratanshila\Documents\autmated trading\tests\test_multi_agent.py | 46-47 |
| _stub_none | Function | C:\Users\Ratanshila\Documents\autmated trading\tests\test_multi_agent.py | 49-50 |
| make_series | Function | C:\Users\Ratanshila\Documents\autmated trading\tools\backtest_profit_filters.py | 43-72 |
| resample | Function | C:\Users\Ratanshila\Documents\autmated trading\tools\backtest_profit_filters.py | 75-79 |
| atr14 | Function | C:\Users\Ratanshila\Documents\autmated trading\tools\backtest_profit_filters.py | 82-87 |
| trade_result | Function | C:\Users\Ratanshila\Documents\autmated trading\tools\backtest_profit_filters.py | 97-124 |
| run_strategy | Function | C:\Users\Ratanshila\Documents\autmated trading\tools\backtest_profit_filters.py | 130-226 |
| fmt_row | Function | C:\Users\Ratanshila\Documents\autmated trading\tools\backtest_profit_filters.py | 229-234 |
| main | Function | C:\Users\Ratanshila\Documents\autmated trading\tools\backtest_profit_filters.py | 237-296 |
| avg | Function | C:\Users\Ratanshila\Documents\autmated trading\tools\backtest_profit_filters.py | 252-254 |
| agg | Function | C:\Users\Ratanshila\Documents\autmated trading\tools\backtest_profit_filters.py | 256-268 |

## Execution Flows

- **main** (criticality: 0.72, depth: 5)
- **scan_once** (criticality: 0.61, depth: 3)
- **main** (criticality: 0.55, depth: 4)
- **main** (criticality: 0.54, depth: 4)

## Dependencies

### Outgoing

- `print` (19 edge(s))
- `round` (10 edge(s))
- `DataFrame` (9 edge(s))
- `mean` (8 edge(s))
- `sum` (8 edge(s))
- `max` (7 edge(s))
- `len` (7 edge(s))
- `ewm` (5 edge(s))
- `isfinite` (5 edge(s))
- `get` (5 edge(s))
- `abs` (4 edge(s))
- `int` (4 edge(s))
- `diff` (3 edge(s))
- `shift` (3 edge(s))
- `rolling` (3 edge(s))

### Incoming

- `C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\multi_agent.py` (9 edge(s))
- `C:\Users\Ratanshila\Documents\autmated trading\tools\backtest_profit_filters.py` (9 edge(s))
- `C:\Users\Ratanshila\Documents\autmated trading\tests\test_multi_agent.py` (7 edge(s))
- `DataFrame` (5 edge(s))
- `C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\multi_market_dispatcher.py::scan_once` (1 edge(s))
- `C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\trend_master_brain.py::TrendMasterBrain.agent_vote` (1 edge(s))
- `C:\Users\Ratanshila\Documents\autmated trading\tools\backtest.py::run_backtest` (1 edge(s))
- `as_dict` (1 edge(s))
- `sum` (1 edge(s))
- `len` (1 edge(s))
