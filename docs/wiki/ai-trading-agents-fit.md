# ai-trading-agents-fit

## Overview

Community of 23 nodes

- **Size**: 23 nodes
- **Cohesion**: 0.2857
- **Dominant Language**: python

## Members

| Name | Kind | File | Lines |
|------|------|------|-------|
| HMMConfig | Class | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\regime_hmm.py | 65-72 |
| RegimeObs | Class | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\regime_hmm.py | 76-80 |
| RegimeHMM | Class | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\regime_hmm.py | 84-352 |
| _features | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\regime_hmm.py | 97-104 |
| fit | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\regime_hmm.py | 109-124 |
| _fit_via_lib | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\regime_hmm.py | 126-140 |
| _fit_manual | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\regime_hmm.py | 142-208 |
| _log_gaussian | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\regime_hmm.py | 210-222 |
| _forward | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\regime_hmm.py | 224-237 |
| _backward | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\regime_hmm.py | 239-250 |
| _logsumexp | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\regime_hmm.py | 253-255 |
| _assign_labels | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\regime_hmm.py | 260-281 |
| classify | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\regime_hmm.py | 286-313 |
| save | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\regime_hmm.py | 318-331 |
| load | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\regime_hmm.py | 334-352 |
| _make_closes | Function | C:\Users\Ratanshila\Documents\autmated trading\tests\test_regime_hmm.py | 10-13 |
| test_insufficient_history_raises | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_regime_hmm.py | 16-20 |
| test_fit_runs_on_synthetic_stream | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_regime_hmm.py | 23-30 |
| test_classify_returns_valid_state | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_regime_hmm.py | 33-40 |
| test_untrained_classify_returns_unknown | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_regime_hmm.py | 43-47 |
| test_chop_vs_trend_distinguishable | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_regime_hmm.py | 50-66 |
| test_save_load_roundtrip | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_regime_hmm.py | 69-80 |
| test_three_state_labels | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_regime_hmm.py | 83-89 |

## Execution Flows

- **classify** (criticality: 0.37, depth: 2)

## Dependencies

### Outgoing

- `range` (11 edge(s))
- `sum` (11 edge(s))
- `log` (9 edge(s))
- `float` (8 edge(s))
- `len` (7 edge(s))
- `exp` (7 edge(s))
- `get` (7 edge(s))
- `clip` (6 edge(s))
- `reshape` (6 edge(s))
- `fit` (6 edge(s))
- `classify` (6 edge(s))
- `zeros` (5 edge(s))
- `asarray` (5 edge(s))
- `abs` (4 edge(s))
- `max` (4 edge(s))

### Incoming

- `C:\Users\Ratanshila\Documents\autmated trading\tests\test_regime_hmm.py` (8 edge(s))
- `fit` (6 edge(s))
- `classify` (6 edge(s))
- `C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\regime_hmm.py` (3 edge(s))
- `str` (2 edge(s))
- `concatenate` (1 edge(s))
- `abs` (1 edge(s))
- `sum` (1 edge(s))
- `raises` (1 edge(s))
- `save` (1 edge(s))
- `load` (1 edge(s))
- `len` (1 edge(s))
- `any` (1 edge(s))
