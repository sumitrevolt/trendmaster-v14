# tests-label

## Overview

Community of 5 nodes

- **Size**: 5 nodes
- **Cohesion**: 0.1167
- **Dominant Language**: python

## Members

| Name | Kind | File | Lines |
|------|------|------|-------|
| _write_trades | Function | C:\Users\Ratanshila\Documents\autmated trading\tests\test_label_trades.py | 12-27 |
| test_label_produces_per_symbol_files | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_label_trades.py | 30-45 |
| test_label_missing_columns_raises | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_label_trades.py | 48-52 |
| label | Function | C:\Users\Ratanshila\Documents\autmated trading\tools\label_trades.py | 42-78 |
| main | Function | C:\Users\Ratanshila\Documents\autmated trading\tools\label_trades.py | 81-88 |

## Execution Flows

- **main** (criticality: 0.36, depth: 1)

## Dependencies

### Outgoing

- `to_csv` (3 edge(s))
- `add_argument` (3 edge(s))
- `DataFrame` (2 edge(s))
- `str` (2 edge(s))
- `set` (2 edge(s))
- `read_csv` (2 edge(s))
- `Path` (2 edge(s))
- `where` (2 edge(s))
- `raises` (1 edge(s))
- `exists` (1 edge(s))
- `FileNotFoundError` (1 edge(s))
- `ValueError` (1 edge(s))
- `to_datetime` (1 edge(s))
- `copy` (1 edge(s))
- `dropna` (1 edge(s))

### Incoming

- `C:\Users\Ratanshila\Documents\autmated trading\tests\test_label_trades.py` (3 edge(s))
- `str` (2 edge(s))
- `set` (2 edge(s))
- `C:\Users\Ratanshila\Documents\autmated trading\tools\label_trades.py` (2 edge(s))
- `to_csv` (1 edge(s))
- `DataFrame` (1 edge(s))
- `raises` (1 edge(s))
- `read_csv` (1 edge(s))
