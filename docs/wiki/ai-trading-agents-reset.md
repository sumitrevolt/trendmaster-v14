# ai-trading-agents-reset

## Overview

Community of 23 nodes

- **Size**: 23 nodes
- **Cohesion**: 0.3333
- **Dominant Language**: python

## Members

| Name | Kind | File | Lines |
|------|------|------|-------|
| ADWINConfig | Class | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\drift_detector.py | 51-66 |
| ADWINState | Class | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\drift_detector.py | 70-78 |
| ADWIN | Class | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\drift_detector.py | 81-225 |
| __init__ | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\drift_detector.py | 95-99 |
| update | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\drift_detector.py | 102-147 |
| reset | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\drift_detector.py | 150-156 |
| _recalc_mean_var | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\drift_detector.py | 159-171 |
| _epsilon_cut | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\drift_detector.py | 173-182 |
| _try_split | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\drift_detector.py | 184-209 |
| _in_warning_zone | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\drift_detector.py | 211-225 |
| get_detector | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\drift_detector.py | 235-239 |
| reset_all | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\drift_detector.py | 242-246 |
| feed_recent_results | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\drift_detector.py | 249-269 |
| pnl_of | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\drift_detector.py | 262-267 |
| _clean | Function | C:\Users\Ratanshila\Documents\autmated trading\tests\test_drift_detector.py | 18-21 |
| test_short_window_never_flags | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_drift_detector.py | 24-32 |
| test_stable_stream_does_not_flag | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_drift_detector.py | 35-45 |
| test_distribution_shift_triggers_drift | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_drift_detector.py | 48-58 |
| test_reset_clears_window_not_counters | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_drift_detector.py | 61-69 |
| test_non_numeric_input_ignored | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_drift_detector.py | 72-81 |
| test_feed_recent_results_handles_float_and_dict | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_drift_detector.py | 84-91 |
| test_singleton_reuses_instance | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_drift_detector.py | 94-99 |
| test_warning_fires_before_drift_on_slow_shift | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_drift_detector.py | 102-117 |

## Execution Flows

- **__init__** (criticality: 0.24, depth: 1)

## Dependencies

### Outgoing

- `update` (10 edge(s))
- `range` (9 edge(s))
- `float` (7 edge(s))
- `len` (6 edge(s))
- `gauss` (5 edge(s))
- `max` (4 edge(s))
- `sum` (4 edge(s))
- `list` (3 edge(s))
- `log` (2 edge(s))
- `abs` (2 edge(s))
- `clear` (2 edge(s))
- `isinstance` (2 edge(s))
- `seed` (2 edge(s))
- `deque` (1 edge(s))
- `Lock` (1 edge(s))

### Incoming

- `update` (10 edge(s))
- `C:\Users\Ratanshila\Documents\autmated trading\tests\test_drift_detector.py` (9 edge(s))
- `C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\drift_detector.py` (7 edge(s))
- `range` (7 edge(s))
- `gauss` (5 edge(s))
- `seed` (2 edge(s))
- `float` (2 edge(s))
- `reset` (1 edge(s))
