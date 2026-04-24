# tests-dict

## Overview

Community of 17 nodes

- **Size**: 17 nodes
- **Cohesion**: 0.4818
- **Dominant Language**: python

## Members

| Name | Kind | File | Lines |
|------|------|------|-------|
| KellyConfig | Class | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\kelly_sizer.py | 58-65 |
| KellyDecision | Class | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\kelly_sizer.py | 69-88 |
| as_dict | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\kelly_sizer.py | 79-88 |
| _extract_pnl | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\kelly_sizer.py | 91-109 |
| compute_multiplier | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\kelly_sizer.py | 112-194 |
| apply | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\kelly_sizer.py | 197-210 |
| test_insufficient_samples_returns_identity | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_kelly_sizer.py | 14-19 |
| test_all_wins_returns_identity | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_kelly_sizer.py | 22-26 |
| test_all_losses_returns_identity | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_kelly_sizer.py | 29-33 |
| test_balanced_mix_scales_above_one | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_kelly_sizer.py | 36-46 |
| test_multiplier_is_clamped_to_max | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_kelly_sizer.py | 49-55 |
| test_dict_shape_via_trade_tracker | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_kelly_sizer.py | 58-70 |
| test_shadow_mode_does_not_apply | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_kelly_sizer.py | 73-80 |
| test_live_mode_scales_base | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_kelly_sizer.py | 83-89 |
| test_break_even_not_counted | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_kelly_sizer.py | 92-97 |
| test_floor_caps_downside | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_kelly_sizer.py | 100-109 |
| test_decision_as_dict_roundtrip | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_kelly_sizer.py | 112-120 |

## Execution Flows

No execution flows pass through this community.

## Dependencies

### Outgoing

- `len` (7 edge(s))
- `round` (5 edge(s))
- `float` (5 edge(s))
- `sum` (4 edge(s))
- `isinstance` (3 edge(s))
- `approx` (3 edge(s))
- `max` (2 edge(s))
- `get` (1 edge(s))
- `info` (1 edge(s))
- `list` (1 edge(s))
- `isfinite` (1 edge(s))
- `abs` (1 edge(s))
- `min` (1 edge(s))
- `as_dict` (1 edge(s))

### Incoming

- `C:\Users\Ratanshila\Documents\autmated trading\tests\test_kelly_sizer.py` (11 edge(s))
- `C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\kelly_sizer.py` (5 edge(s))
- `approx` (3 edge(s))
- `as_dict` (1 edge(s))
- `isinstance` (1 edge(s))
