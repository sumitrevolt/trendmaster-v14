# ai-trading-agents-variant

## Overview

Community of 14 nodes

- **Size**: 14 nodes
- **Cohesion**: 0.2530
- **Dominant Language**: python

## Members

| Name | Kind | File | Lines |
|------|------|------|-------|
| Variant | Class | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\ab_test.py | 57-67 |
| apply | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\ab_test.py | 61-67 |
| ShadowRecord | Class | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\ab_test.py | 71-82 |
| as_dict | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\ab_test.py | 81-82 |
| ABTester | Class | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\ab_test.py | 86-149 |
| register | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\ab_test.py | 93-94 |
| load_from_settings | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\ab_test.py | 96-107 |
| tick | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\ab_test.py | 109-134 |
| summary | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\ab_test.py | 136-149 |
| test_register_and_tick_records_divergence | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_ab_test.py | 23-30 |
| test_no_divergence_when_variant_returns_same | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_ab_test.py | 33-40 |
| test_variant_failure_is_caught | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_ab_test.py | 43-51 |
| test_multiple_variants_independent | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_ab_test.py | 54-61 |
| test_shadow_record_as_dict | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_ab_test.py | 87-93 |

## Execution Flows

- **load_from_settings** (criticality: 0.37, depth: 2)
- **tick** (criticality: 0.36, depth: 1)

## Dependencies

### Outgoing

- `register` (5 edge(s))
- `tick` (4 edge(s))
- `summary` (4 edge(s))
- `get` (3 edge(s))
- `len` (3 edge(s))
- `warning` (2 edge(s))
- `append` (2 edge(s))
- `float` (2 edge(s))
- `strip` (1 edge(s))
- `str` (1 edge(s))
- `split` (1 edge(s))
- `import_module` (1 edge(s))
- `getattr` (1 edge(s))
- `list` (1 edge(s))
- `abs` (1 edge(s))

### Incoming

- `C:\Users\Ratanshila\Documents\autmated trading\tests\test_ab_test.py` (5 edge(s))
- `register` (5 edge(s))
- `tick` (4 edge(s))
- `summary` (4 edge(s))
- `C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\ab_test.py` (3 edge(s))
- `as_dict` (1 edge(s))
