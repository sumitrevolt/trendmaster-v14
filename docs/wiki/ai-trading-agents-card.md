# ai-trading-agents-card

## Overview

Community of 24 nodes

- **Size**: 24 nodes
- **Cohesion**: 0.3054
- **Dominant Language**: python

## Members

| Name | Kind | File | Lines |
|------|------|------|-------|
| ModelCard | Class | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\model_governance.py | 45-61 |
| as_dict | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\model_governance.py | 60-61 |
| DeploymentEntry | Class | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\model_governance.py | 65-75 |
| as_dict | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\model_governance.py | 74-75 |
| Governance | Class | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\model_governance.py | 78-197 |
| __init__ | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\model_governance.py | 81-88 |
| _load | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\model_governance.py | 91-98 |
| _save | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\model_governance.py | 100-104 |
| register_card | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\model_governance.py | 107-110 |
| list_cards | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\model_governance.py | 112-121 |
| get_deployment | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\model_governance.py | 124-129 |
| set_champion | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\model_governance.py | 131-140 |
| set_challenger | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\model_governance.py | 142-154 |
| should_promote | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\model_governance.py | 156-161 |
| promote_challenger | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\model_governance.py | 163-178 |
| rollback | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\model_governance.py | 180-192 |
| deployments | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\model_governance.py | 194-197 |
| test_register_card_writes_json | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_model_governance.py | 14-28 |
| test_list_cards_filters_by_team | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_model_governance.py | 31-40 |
| test_set_and_rollback_champion | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_model_governance.py | 43-52 |
| test_challenger_flow | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_model_governance.py | 55-64 |
| test_should_promote_margin | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_model_governance.py | 67-70 |
| test_rollback_without_previous_returns_none | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_model_governance.py | 73-76 |
| test_deployments_returns_dict | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_model_governance.py | 79-86 |

## Execution Flows

- **get_deployment** (criticality: 0.36, depth: 1)
- **set_champion** (criticality: 0.36, depth: 1)
- **set_challenger** (criticality: 0.36, depth: 1)
- **promote_challenger** (criticality: 0.36, depth: 1)
- **rollback** (criticality: 0.36, depth: 1)
- **deployments** (criticality: 0.36, depth: 1)
- **register_card** (criticality: 0.32, depth: 1)

## Dependencies

### Outgoing

- `get` (9 edge(s))
- `Path` (5 edge(s))
- `isoformat` (5 edge(s))
- `now` (5 edge(s))
- `set_champion` (5 edge(s))
- `items` (4 edge(s))
- `setdefault` (4 edge(s))
- `loads` (3 edge(s))
- `read_text` (3 edge(s))
- `register_card` (3 edge(s))
- `asdict` (2 edge(s))
- `mkdir` (2 edge(s))
- `exists` (2 edge(s))
- `write_text` (2 edge(s))
- `dumps` (2 edge(s))

### Incoming

- `C:\Users\Ratanshila\Documents\autmated trading\tests\test_model_governance.py` (7 edge(s))
- `set_champion` (5 edge(s))
- `C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\model_governance.py` (3 edge(s))
- `register_card` (3 edge(s))
- `Path` (3 edge(s))
- `get_deployment` (2 edge(s))
- `list_cards` (2 edge(s))
- `len` (2 edge(s))
- `rollback` (2 edge(s))
- `should_promote` (2 edge(s))
- `set_challenger` (1 edge(s))
- `promote_challenger` (1 edge(s))
- `deployments` (1 edge(s))
- `isinstance` (1 edge(s))
- `exists` (1 edge(s))
