# ai-trading-agents-event

## Overview

Community of 16 nodes

- **Size**: 16 nodes
- **Cohesion**: 0.2276
- **Dominant Language**: python

## Members

| Name | Kind | File | Lines |
|------|------|------|-------|
| Event | Class | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\event_log.py | 54-73 |
| as_line | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\event_log.py | 61-73 |
| EventLog | Class | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\event_log.py | 77-161 |
| __post_init__ | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\event_log.py | 85-90 |
| append | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\event_log.py | 92-108 |
| _flush_locked | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\event_log.py | 110-132 |
| flush | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\event_log.py | 134-136 |
| read_since | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\event_log.py | 138-161 |
| get_log | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\event_log.py | 171-179 |
| test_append_and_read_roundtrip | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_event_log.py | 11-22 |
| test_kind_filter_applies | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_event_log.py | 25-33 |
| test_since_ts_filter | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_event_log.py | 36-41 |
| test_buffered_writes_eventually_flush | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_event_log.py | 44-51 |
| test_event_line_is_valid_json | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_event_log.py | 54-61 |
| test_corr_id_default_populates | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_event_log.py | 64-70 |
| test_read_missing_file_returns_empty | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_event_log.py | 73-79 |

## Execution Flows

- **read_since** (criticality: 0.38, depth: 3)
- **get_log** (criticality: 0.24, depth: 1)

## Dependencies

### Outgoing

- `append` (8 edge(s))
- `time` (6 edge(s))
- `len` (6 edge(s))
- `read_since` (6 edge(s))
- `flush` (5 edge(s))
- `int` (3 edge(s))
- `Path` (2 edge(s))
- `open` (2 edge(s))
- `loads` (2 edge(s))
- `get` (2 edge(s))
- `dumps` (1 edge(s))
- `mkdir` (1 edge(s))
- `exists` (1 edge(s))
- `touch` (1 edge(s))
- `write` (1 edge(s))

### Incoming

- `append` (8 edge(s))
- `C:\Users\Ratanshila\Documents\autmated trading\tests\test_event_log.py` (7 edge(s))
- `read_since` (6 edge(s))
- `flush` (5 edge(s))
- `C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\event_log.py` (3 edge(s))
- `len` (3 edge(s))
- `range` (1 edge(s))
- `as_line` (1 edge(s))
- `loads` (1 edge(s))
- `all` (1 edge(s))
- `unlink` (1 edge(s))
