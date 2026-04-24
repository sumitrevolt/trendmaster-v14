# tests-pid

## Overview

Community of 19 nodes

- **Size**: 19 nodes
- **Cohesion**: 0.2519
- **Dominant Language**: python

## Members

| Name | Kind | File | Lines |
|------|------|------|-------|
| _pid_alive | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\process_lock.py | 37-66 |
| SingleInstanceLock | Class | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\process_lock.py | 69-187 |
| __init__ | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\process_lock.py | 82-89 |
| __enter__ | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\process_lock.py | 91-132 |
| __exit__ | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\process_lock.py | 134-156 |
| _platform_lock | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\process_lock.py | 159-173 |
| _platform_unlock | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\process_lock.py | 175-187 |
| test_pid_alive_zero_returns_false | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_process_lock.py | 14-15 |
| test_pid_alive_negative_returns_false | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_process_lock.py | 18-19 |
| test_pid_alive_self_returns_true | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_process_lock.py | 22-23 |
| test_pid_alive_clearly_dead_pid_returns_false | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_process_lock.py | 26-28 |
| test_lock_can_be_acquired | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_process_lock.py | 32-35 |
| test_lock_releases_file_on_exit | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_process_lock.py | 38-43 |
| test_lock_writes_current_pid_into_file | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_process_lock.py | 46-83 |
| _NoUnlinkLock | Class | C:\Users\Ratanshila\Documents\autmated trading\tests\test_process_lock.py | 53-78 |
| __exit__ | Function | C:\Users\Ratanshila\Documents\autmated trading\tests\test_process_lock.py | 54-78 |
| test_stale_pid_lock_is_stolen | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_process_lock.py | 87-97 |
| test_second_acquisition_refused_while_first_held | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_process_lock.py | 105-122 |
| test_second_acquisition_refused_when_holder_pid_is_alive | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_process_lock.py | 125-142 |

## Execution Flows

- **main** (criticality: 0.72, depth: 5)
- **__enter__** (criticality: 0.36, depth: 1)
- **__exit__** (criticality: 0.36, depth: 1)

## Dependencies

### Outgoing

- `getpid` (7 edge(s))
- `exists` (6 edge(s))
- `fileno` (6 edge(s))
- `close` (4 edge(s))
- `int` (3 edge(s))
- `strip` (3 edge(s))
- `read_text` (3 edge(s))
- `unlink` (3 edge(s))
- `locking` (3 edge(s))
- `error` (2 edge(s))
- `open` (2 edge(s))
- `str` (2 edge(s))
- `flush` (2 edge(s))
- `flock` (2 edge(s))
- `write_text` (2 edge(s))

### Incoming

- `C:\Users\Ratanshila\Documents\autmated trading\tests\test_process_lock.py` (11 edge(s))
- `exists` (3 edge(s))
- `getpid` (3 edge(s))
- `C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\process_lock.py` (2 edge(s))
- `write_text` (2 edge(s))
- `C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\trend_master_brain.py::TrendMasterBrain.run_forever` (1 edge(s))
- `int` (1 edge(s))
- `getppid` (1 edge(s))
- `skip` (1 edge(s))
- `str` (1 edge(s))
- `__enter__` (1 edge(s))
- `open` (1 edge(s))
- `raises` (1 edge(s))
- `locking` (1 edge(s))
- `fileno` (1 edge(s))
