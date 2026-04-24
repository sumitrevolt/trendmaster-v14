# tools-read

## Overview

Community of 6 nodes

- **Size**: 6 nodes
- **Cohesion**: 0.0862
- **Dominant Language**: python

## Members

| Name | Kind | File | Lines |
|------|------|------|-------|
| _read_signal | Function | C:\Users\Ratanshila\Documents\autmated trading\tools\dashboard.py | 182-190 |
| _read_brain_tail | Function | C:\Users\Ratanshila\Documents\autmated trading\tools\dashboard.py | 204-211 |
| _read_mt5_log_tail | Function | C:\Users\Ratanshila\Documents\autmated trading\tools\dashboard.py | 214-227 |
| _mt5_state | Function | C:\Users\Ratanshila\Documents\autmated trading\tools\dashboard.py | 247-287 |
| api_state | Function | C:\Users\Ratanshila\Documents\autmated trading\tools\dashboard.py | 387-394 |
| healthz | Function | C:\Users\Ratanshila\Documents\autmated trading\tools\dashboard.py | 451-466 |

## Execution Flows

- **healthz** (criticality: 0.48, depth: 1)
- **api_state** (criticality: 0.41, depth: 1)

## Dependencies

### Outgoing

- `getattr` (10 edge(s))
- `read_text` (5 edge(s))
- `exists` (3 edge(s))
- `now` (3 edge(s))
- `splitlines` (2 edge(s))
- `stat` (2 edge(s))
- `round` (2 edge(s))
- `JSONResponse` (2 edge(s))
- `get` (2 edge(s))
- `initialize` (1 edge(s))
- `last_error` (1 edge(s))
- `account_info` (1 edge(s))
- `terminal_info` (1 edge(s))
- `positions_get` (1 edge(s))
- `symbol_info_tick` (1 edge(s))

### Incoming

- `C:\Users\Ratanshila\Documents\autmated trading\tools\dashboard.py` (6 edge(s))
