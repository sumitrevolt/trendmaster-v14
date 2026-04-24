# tests-action

## Overview

Community of 16 nodes

- **Size**: 16 nodes
- **Cohesion**: 0.1673
- **Dominant Language**: python

## Members

| Name | Kind | File | Lines |
|------|------|------|-------|
| ActionItem | Class | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\daily_digest.py | 44-50 |
| as_dict | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\daily_digest.py | 49-50 |
| generate_report | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\daily_digest.py | 53-160 |
| to_markdown | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\daily_digest.py | 166-246 |
| to_telegram | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\daily_digest.py | 249-283 |
| write_daily | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\daily_digest.py | 289-299 |
| push_telegram | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\daily_digest.py | 302-313 |
| _fake_state | Function | C:\Users\Ratanshila\Documents\autmated trading\tests\test_daily_digest.py | 15-33 |
| test_generate_report_has_keys | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_daily_digest.py | 36-40 |
| test_generate_report_handles_empty_state | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_daily_digest.py | 43-46 |
| test_markdown_renders | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_daily_digest.py | 49-54 |
| test_telegram_renders | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_daily_digest.py | 57-61 |
| test_write_daily | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_daily_digest.py | 64-71 |
| test_action_items_flag_halted | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_daily_digest.py | 74-79 |
| test_action_items_flag_drawdown_lockout | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_daily_digest.py | 82-87 |
| test_action_item_as_dict | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_daily_digest.py | 90-92 |

## Execution Flows

- **push_telegram** (criticality: 0.36, depth: 1)

## Dependencies

### Outgoing

- `get` (68 edge(s))
- `append` (44 edge(s))
- `int` (7 edge(s))
- `getattr` (5 edge(s))
- `float` (5 edge(s))
- `join` (4 edge(s))
- `Path` (4 edge(s))
- `list` (3 edge(s))
- `time` (3 edge(s))
- `bool` (3 edge(s))
- `len` (3 edge(s))
- `now` (2 edge(s))
- `strftime` (2 edge(s))
- `snapshot` (2 edge(s))
- `round` (2 edge(s))

### Incoming

- `C:\Users\Ratanshila\Documents\autmated trading\tests\test_daily_digest.py` (9 edge(s))
- `C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\daily_digest.py` (6 edge(s))
- `Path` (3 edge(s))
- `any` (2 edge(s))
- `lower` (2 edge(s))
- `exists` (2 edge(s))
- `as_dict` (1 edge(s))
- `int` (1 edge(s))
- `time` (1 edge(s))
- `loads` (1 edge(s))
- `read_text` (1 edge(s))
