# tests-cost

## Overview

Community of 15 nodes

- **Size**: 15 nodes
- **Cohesion**: 0.2371
- **Dominant Language**: python

## Members

| Name | Kind | File | Lines |
|------|------|------|-------|
| test_buy_pays_above_mid | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_slippage_model.py | 9-13 |
| test_sell_hits_below_mid | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_slippage_model.py | 16-19 |
| test_flat_style_uses_fixed_cost | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_slippage_model.py | 22-25 |
| test_p95_spread_is_larger_than_median | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_slippage_model.py | 28-32 |
| test_commission_applied_per_lot | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_slippage_model.py | 35-41 |
| test_sqrt_impact_scales_with_lots | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_slippage_model.py | 44-49 |
| test_fill_as_dict_has_expected_keys | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_slippage_model.py | 52-59 |
| test_unknown_symbol_falls_back_to_defaults | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_slippage_model.py | 62-67 |
| _pip_size | Function | C:\Users\Ratanshila\Documents\autmated trading\tools\slippage_model.py | 95-100 |
| _pip_value_usd_per_lot | Function | C:\Users\Ratanshila\Documents\autmated trading\tools\slippage_model.py | 103-114 |
| Fill | Class | C:\Users\Ratanshila\Documents\autmated trading\tools\slippage_model.py | 118-141 |
| total_cost_usd | Function | C:\Users\Ratanshila\Documents\autmated trading\tools\slippage_model.py | 128-129 |
| as_dict | Function | C:\Users\Ratanshila\Documents\autmated trading\tools\slippage_model.py | 131-141 |
| CostModel | Class | C:\Users\Ratanshila\Documents\autmated trading\tools\slippage_model.py | 145-197 |
| fill | Function | C:\Users\Ratanshila\Documents\autmated trading\tools\slippage_model.py | 153-197 |

## Execution Flows

- **fill** (criticality: 0.36, depth: 1)

## Dependencies

### Outgoing

- `float` (14 edge(s))
- `fill` (10 edge(s))
- `get` (4 edge(s))
- `round` (4 edge(s))
- `approx` (3 edge(s))
- `dict` (2 edge(s))
- `endswith` (2 edge(s))
- `startswith` (2 edge(s))
- `as_dict` (1 edge(s))
- `lower` (1 edge(s))
- `sqrt` (1 edge(s))
- `max` (1 edge(s))
- `abs` (1 edge(s))

### Incoming

- `fill` (10 edge(s))
- `C:\Users\Ratanshila\Documents\autmated trading\tests\test_slippage_model.py` (8 edge(s))
- `C:\Users\Ratanshila\Documents\autmated trading\tools\slippage_model.py` (4 edge(s))
- `approx` (3 edge(s))
- `dict` (2 edge(s))
- `as_dict` (1 edge(s))
