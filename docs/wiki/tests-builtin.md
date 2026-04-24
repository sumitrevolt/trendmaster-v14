# tests-builtin

## Overview

Community of 28 nodes

- **Size**: 28 nodes
- **Cohesion**: 0.2637
- **Dominant Language**: python

## Members

| Name | Kind | File | Lines |
|------|------|------|-------|
| TelegramCommandListener | Class | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\telegram_commands.py | 83-293 |
| __init__ | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\telegram_commands.py | 93-119 |
| register_command | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\telegram_commands.py | 122-132 |
| start | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\telegram_commands.py | 134-147 |
| stop | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\telegram_commands.py | 149-150 |
| _builtin_ping | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\telegram_commands.py | 153-157 |
| _builtin_help | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\telegram_commands.py | 159-164 |
| _send | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\telegram_commands.py | 167-180 |
| _poll_loop | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\telegram_commands.py | 183-204 |
| _fetch_latest_offset | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\telegram_commands.py | 206-219 |
| _get_updates | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\telegram_commands.py | 221-231 |
| _handle_update | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\telegram_commands.py | 233-293 |
| get_listener | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\telegram_commands.py | 301-306 |
| _offline_listener | Function | C:\Users\Ratanshila\Documents\autmated trading\tests\test_telegram_commands.py | 45-47 |
| test_register_command_accepts_known_name | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_telegram_commands.py | 51-54 |
| test_register_command_strips_leading_slash | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_telegram_commands.py | 57-60 |
| test_register_command_rejects_unknown_name | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_telegram_commands.py | 63-66 |
| test_register_command_is_case_insensitive | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_telegram_commands.py | 69-72 |
| test_builtin_ping_starts_with_pong | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_telegram_commands.py | 76-79 |
| test_builtin_ping_includes_uptime_format | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_telegram_commands.py | 82-87 |
| test_builtin_help_lists_all_known_commands | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_telegram_commands.py | 91-95 |
| test_builtin_help_marks_wired_commands_with_check | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_telegram_commands.py | 98-108 |
| test_builtin_help_has_header | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_telegram_commands.py | 111-114 |
| test_listener_disabled_when_no_credentials | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_telegram_commands.py | 118-120 |
| test_listener_start_is_noop_when_disabled | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_telegram_commands.py | 123-126 |
| test_send_is_safe_when_disabled | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_telegram_commands.py | 130-141 |
| _Boom | Class | C:\Users\Ratanshila\Documents\autmated trading\tests\test_telegram_commands.py | 135-137 |
| post | Function | C:\Users\Ratanshila\Documents\autmated trading\tests\test_telegram_commands.py | 136-137 |

## Execution Flows

- **_poll_loop** (criticality: 0.37, depth: 2)
- **get_listener** (criticality: 0.16, depth: 1)

## Dependencies

### Outgoing

- `get` (12 edge(s))
- `strip` (6 edge(s))
- `int` (4 edge(s))
- `append` (4 edge(s))
- `startswith` (4 edge(s))
- `fn` (4 edge(s))
- `register_command` (4 edge(s))
- `join` (3 edge(s))
- `format` (3 edge(s))
- `warning` (3 edge(s))
- `debug` (3 edge(s))
- `_builtin_help` (3 edge(s))
- `getenv` (2 edge(s))
- `time` (2 edge(s))
- `info` (2 edge(s))

### Incoming

- `C:\Users\Ratanshila\Documents\autmated trading\tests\test_telegram_commands.py` (14 edge(s))
- `register_command` (4 edge(s))
- `_builtin_help` (3 edge(s))
- `startswith` (3 edge(s))
- `C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\telegram_commands.py` (2 edge(s))
- `next` (2 edge(s))
- `strip` (2 edge(s))
- `_builtin_ping` (2 edge(s))
- `splitlines` (1 edge(s))
- `start` (1 edge(s))
- `setattr` (1 edge(s))
- `_send` (1 edge(s))
