# ai-trading-agents-predict

## Overview

Community of 15 nodes

- **Size**: 15 nodes
- **Cohesion**: 0.2475
- **Dominant Language**: python

## Members

| Name | Kind | File | Lines |
|------|------|------|-------|
| _ManualSGDLogReg | Class | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\online_learner.py | 53-80 |
| _z | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\online_learner.py | 61-62 |
| predict_proba | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\online_learner.py | 64-70 |
| learn_one | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\online_learner.py | 72-80 |
| OnlineLearner | Class | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\online_learner.py | 87-162 |
| __post_init__ | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\online_learner.py | 94-108 |
| learn_one | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\online_learner.py | 111-118 |
| predict_proba | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\online_learner.py | 121-129 |
| predict_is_win | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\online_learner.py | 131-134 |
| save | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\online_learner.py | 137-146 |
| load | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\online_learner.py | 149-162 |
| test_fresh_learner_predicts_midpoint | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_online_learner.py | 9-13 |
| test_learns_simple_pattern | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_online_learner.py | 16-30 |
| test_predict_is_win_respects_threshold | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_online_learner.py | 33-37 |
| test_save_load_roundtrip | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_online_learner.py | 40-52 |

## Execution Flows

- **learn_one** (criticality: 0.38, depth: 3)
- **predict_proba** (criticality: 0.37, depth: 2)
- **predict_is_win** (criticality: 0.37, depth: 2)
- **__post_init__** (criticality: 0.28, depth: 1)

## Dependencies

### Outgoing

- `get` (5 edge(s))
- `predict_proba` (5 edge(s))
- `cls` (3 edge(s))
- `str` (3 edge(s))
- `float` (3 edge(s))
- `int` (2 edge(s))
- `debug` (2 edge(s))
- `Path` (2 edge(s))
- `open` (2 edge(s))
- `items` (2 edge(s))
- `exp` (2 edge(s))
- `range` (2 edge(s))
- `learn_one` (2 edge(s))
- `Pipeline` (1 edge(s))
- `StandardScaler` (1 edge(s))

### Incoming

- `predict_proba` (5 edge(s))
- `C:\Users\Ratanshila\Documents\autmated trading\tests\test_online_learner.py` (4 edge(s))
- `C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\online_learner.py` (2 edge(s))
- `range` (2 edge(s))
- `learn_one` (2 edge(s))
- `str` (2 edge(s))
- `Random` (1 edge(s))
- `uniform` (1 edge(s))
- `predict_is_win` (1 edge(s))
- `float` (1 edge(s))
- `save` (1 edge(s))
- `load` (1 edge(s))
- `abs` (1 edge(s))
