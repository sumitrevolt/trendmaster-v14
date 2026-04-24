# ai-trading-agents-meta

## Overview

Community of 13 nodes

- **Size**: 13 nodes
- **Cohesion**: 0.1746
- **Dominant Language**: python

## Members

| Name | Kind | File | Lines |
|------|------|------|-------|
| MetaConfig | Class | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\meta_labeler.py | 70-76 |
| MetaPrediction | Class | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\meta_labeler.py | 80-92 |
| as_dict | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\meta_labeler.py | 86-92 |
| MetaLabeler | Class | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\meta_labeler.py | 96-272 |
| predict | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\meta_labeler.py | 112-153 |
| _row_from_dict | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\meta_labeler.py | 155-163 |
| train | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\meta_labeler.py | 169-240 |
| save | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\meta_labeler.py | 245-254 |
| load | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\meta_labeler.py | 257-272 |
| _oof_metrics | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\meta_labeler.py | 275-302 |
| test_null_labeler_passes_through | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_meta_labeler.py | 17-22 |
| test_predict_rejects_non_buy_sell | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_meta_labeler.py | 25-32 |
| test_threshold_gates_acting | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_meta_labeler.py | 88-100 |

## Execution Flows

- **predict** (criticality: 0.36, depth: 1)
- **train** (criticality: 0.36, depth: 1)

## Dependencies

### Outgoing

- `float` (10 edge(s))
- `list` (5 edge(s))
- `get` (5 edge(s))
- `asarray` (5 edge(s))
- `cls` (4 edge(s))
- `predict_proba` (3 edge(s))
- `model_factory` (3 edge(s))
- `fit` (3 edge(s))
- `astype` (3 edge(s))
- `extend` (3 edge(s))
- `tolist` (3 edge(s))
- `predict` (3 edge(s))
- `Path` (2 edge(s))
- `open` (2 edge(s))
- `reshape` (2 edge(s))

### Incoming

- `C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\meta_labeler.py` (4 edge(s))
- `C:\Users\Ratanshila\Documents\autmated trading\tests\test_meta_labeler.py` (3 edge(s))
- `predict` (3 edge(s))
- `list` (2 edge(s))
- `default_rng` (1 edge(s))
- `normal` (1 edge(s))
- `choice` (1 edge(s))
- `astype` (1 edge(s))
- `random` (1 edge(s))
- `train` (1 edge(s))
