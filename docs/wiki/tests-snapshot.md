# tests-snapshot

## Overview

Community of 16 nodes

- **Size**: 16 nodes
- **Cohesion**: 0.1212
- **Dominant Language**: python

## Members

| Name | Kind | File | Lines |
|------|------|------|-------|
| MaintenanceReport | Class | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\ops_maintenance.py | 46-54 |
| as_dict | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\ops_maintenance.py | 53-54 |
| rotate_logs | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\ops_maintenance.py | 60-121 |
| snapshot_state | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\ops_maintenance.py | 127-153 |
| snapshot_models | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\ops_maintenance.py | 156-183 |
| vacuum_events | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\ops_maintenance.py | 189-228 |
| run_all | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\ops_maintenance.py | 234-260 |
| test_rotate_small_file_does_nothing | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_ops_maintenance.py | 18-24 |
| test_rotate_large_file_truncates | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_ops_maintenance.py | 27-40 |
| test_rotate_uncompressed | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_ops_maintenance.py | 43-47 |
| test_snapshot_state_copies_file | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_ops_maintenance.py | 50-57 |
| test_snapshot_state_missing_source | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_ops_maintenance.py | 60-62 |
| test_snapshot_models_copies_pkls | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_ops_maintenance.py | 65-72 |
| test_vacuum_events_prunes_old | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_ops_maintenance.py | 75-85 |
| test_vacuum_nonexistent_ok | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_ops_maintenance.py | 88-89 |
| test_run_all_returns_report | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_ops_maintenance.py | 92-101 |

## Execution Flows

No execution flows pass through this community.

## Dependencies

### Outgoing

- `Path` (10 edge(s))
- `exists` (8 edge(s))
- `append` (8 edge(s))
- `len` (8 edge(s))
- `write_text` (7 edge(s))
- `mkdir` (6 edge(s))
- `int` (5 edge(s))
- `open` (5 edge(s))
- `warning` (5 edge(s))
- `str` (4 edge(s))
- `time` (4 edge(s))
- `stat` (3 edge(s))
- `strftime` (3 edge(s))
- `now` (3 edge(s))
- `read_text` (3 edge(s))

### Incoming

- `C:\Users\Ratanshila\Documents\autmated trading\tests\test_ops_maintenance.py` (9 edge(s))
- `write_text` (7 edge(s))
- `C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\ops_maintenance.py` (6 edge(s))
- `len` (5 edge(s))
- `exists` (4 edge(s))
- `Path` (3 edge(s))
- `read_text` (3 edge(s))
- `mkdir` (3 edge(s))
- `isinstance` (3 edge(s))
- `dumps` (2 edge(s))
- `range` (2 edge(s))
- `stat` (1 edge(s))
- `open` (1 edge(s))
- `read` (1 edge(s))
- `write_bytes` (1 edge(s))
