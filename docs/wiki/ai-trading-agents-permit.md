# ai-trading-agents-permit

## Overview

Community of 29 nodes

- **Size**: 29 nodes
- **Cohesion**: 0.3614
- **Dominant Language**: python

## Members

| Name | Kind | File | Lines |
|------|------|------|-------|
| ReentryPermit | Class | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\reentry_tracker.py | 58-81 |
| to_dict | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\reentry_tracker.py | 68-69 |
| from_dict | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\reentry_tracker.py | 72-81 |
| ReentryTracker | Class | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\reentry_tracker.py | 85-294 |
| _cooldown_s | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\reentry_tracker.py | 93-94 |
| _max_age_s | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\reentry_tracker.py | 96-97 |
| _size_mult | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\reentry_tracker.py | 99-100 |
| _max_reentries | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\reentry_tracker.py | 102-103 |
| _require_same_direction | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\reentry_tracker.py | 105-106 |
| _load_permits | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\reentry_tracker.py | 111-124 |
| _save_permits | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\reentry_tracker.py | 126-127 |
| _hydrate_seen | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\reentry_tracker.py | 129-134 |
| scan_for_sl_hits | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\reentry_tracker.py | 139-215 |
| _count_used_today | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\reentry_tracker.py | 220-231 |
| available_permit | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\reentry_tracker.py | 233-279 |
| consume | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\reentry_tracker.py | 281-294 |
| _base_cfg | Function | C:\Users\Ratanshila\Documents\autmated trading\tests\test_reentry_tracker.py | 25-34 |
| _make_sl_result | Function | C:\Users\Ratanshila\Documents\autmated trading\tests\test_reentry_tracker.py | 37-47 |
| test_scan_mints_one_permit_per_new_loss | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_reentry_tracker.py | 64-78 |
| test_scan_skips_scratch_losses | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_reentry_tracker.py | 81-92 |
| test_scan_skips_wins | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_reentry_tracker.py | 95-103 |
| test_scan_idempotent | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_reentry_tracker.py | 106-118 |
| test_scan_survives_restart | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_reentry_tracker.py | 121-135 |
| test_available_permit_respects_cooldown | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_reentry_tracker.py | 141-153 |
| test_available_permit_respects_max_age | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_reentry_tracker.py | 156-169 |
| test_available_permit_respects_max_reentries | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_reentry_tracker.py | 172-191 |
| test_available_permit_require_same_direction | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_reentry_tracker.py | 194-206 |
| test_available_permit_wrong_symbol | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_reentry_tracker.py | 209-217 |
| test_consume_marks_used_and_blocks_reuse | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_reentry_tracker.py | 223-241 |

## Execution Flows

- **__init__** (criticality: 0.58, depth: 1)
- **scan_for_sl_hits** (criticality: 0.45, depth: 2)
- **available_permit** (criticality: 0.37, depth: 2)
- **consume** (criticality: 0.37, depth: 2)

## Dependencies

### Outgoing

- `get` (20 edge(s))
- `int` (19 edge(s))
- `scan_for_sl_hits` (13 edge(s))
- `available_permit` (11 edge(s))
- `len` (10 edge(s))
- `time` (9 edge(s))
- `float` (5 edge(s))
- `add` (4 edge(s))
- `append` (4 edge(s))
- `str` (3 edge(s))
- `isinstance` (3 edge(s))
- `bool` (2 edge(s))
- `strftime` (2 edge(s))
- `fromtimestamp` (2 edge(s))
- `consume` (2 edge(s))

### Incoming

- `C:\Users\Ratanshila\Documents\autmated trading\tests\test_reentry_tracker.py` (13 edge(s))
- `scan_for_sl_hits` (13 edge(s))
- `available_permit` (11 edge(s))
- `len` (10 edge(s))
- `int` (6 edge(s))
- `time` (6 edge(s))
- `C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\reentry_tracker.py` (2 edge(s))
- `consume` (2 edge(s))
- `C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\trend_master_brain.py::TrendMasterBrain.__init__` (1 edge(s))
- `all` (1 edge(s))
