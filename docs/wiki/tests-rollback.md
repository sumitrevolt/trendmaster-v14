# tests-rollback

## Overview

Community of 6 nodes

- **Size**: 6 nodes
- **Cohesion**: 0.1852
- **Dominant Language**: python

## Members

| Name | Kind | File | Lines |
|------|------|------|-------|
| _FakeBooster | Class | C:\Users\Ratanshila\Documents\autmated trading\tests\test_model_registry.py | 12-18 |
| __init__ | Function | C:\Users\Ratanshila\Documents\autmated trading\tests\test_model_registry.py | 14-15 |
| save_model | Function | C:\Users\Ratanshila\Documents\autmated trading\tests\test_model_registry.py | 17-18 |
| test_register_and_list | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_model_registry.py | 27-37 |
| test_rollback | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_model_registry.py | 40-50 |
| test_rollback_missing_version_fails | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_model_registry.py | 53-55 |

## Execution Flows

No execution flows pass through this community.

## Dependencies

### Outgoing

- `register_model` (4 edge(s))
- `read_text` (4 edge(s))
- `latest_model_path` (3 edge(s))
- `list_versions` (2 edge(s))
- `latest_metadata` (2 edge(s))
- `rollback_to` (2 edge(s))
- `write_text` (1 edge(s))
- `Path` (1 edge(s))
- `exists` (1 edge(s))
- `len` (1 edge(s))

### Incoming

- `C:\Users\Ratanshila\Documents\autmated trading\tests\test_model_registry.py` (4 edge(s))
- `register_model` (4 edge(s))
- `read_text` (4 edge(s))
- `latest_model_path` (3 edge(s))
- `list_versions` (2 edge(s))
- `latest_metadata` (2 edge(s))
- `rollback_to` (2 edge(s))
- `exists` (1 edge(s))
- `len` (1 edge(s))
