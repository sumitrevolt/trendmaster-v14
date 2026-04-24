# tests-split

## Overview

Community of 14 nodes

- **Size**: 14 nodes
- **Cohesion**: 0.2101
- **Dominant Language**: python

## Members

| Name | Kind | File | Lines |
|------|------|------|-------|
| test_split_yields_expected_fold_count | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_cpcv.py | 10-16 |
| test_no_overlap_between_train_and_test | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_cpcv.py | 19-23 |
| test_embargo_removes_post_test_samples | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_cpcv.py | 26-36 |
| test_purge_by_label_times_removes_overlapping_train | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_cpcv.py | 39-48 |
| test_invalid_n_test_raises | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_cpcv.py | 51-55 |
| test_small_n_groups_raises | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_cpcv.py | 58-60 |
| test_empty_folds_are_skipped | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_cpcv.py | 72-77 |
| CPCVSplit | Class | C:\Users\Ratanshila\Documents\autmated trading\tools\cpcv.py | 57-169 |
| __post_init__ | Function | C:\Users\Ratanshila\Documents\autmated trading\tools\cpcv.py | 87-91 |
| _group_indices | Function | C:\Users\Ratanshila\Documents\autmated trading\tools\cpcv.py | 94-97 |
| _apply_embargo | Function | C:\Users\Ratanshila\Documents\autmated trading\tools\cpcv.py | 99-110 |
| _apply_purge | Function | C:\Users\Ratanshila\Documents\autmated trading\tools\cpcv.py | 112-137 |
| split | Function | C:\Users\Ratanshila\Documents\autmated trading\tools\cpcv.py | 140-164 |
| get_n_splits | Function | C:\Users\Ratanshila\Documents\autmated trading\tools\cpcv.py | 166-169 |

## Execution Flows

- **split** (criticality: 0.36, depth: 1)

## Dependencies

### Outgoing

- `arange` (8 edge(s))
- `len` (8 edge(s))
- `split` (5 edge(s))
- `range` (5 edge(s))
- `int` (4 edge(s))
- `float` (4 edge(s))
- `raises` (3 edge(s))
- `array` (3 edge(s))
- `list` (2 edge(s))
- `ValueError` (2 edge(s))
- `concatenate` (2 edge(s))
- `sort` (2 edge(s))
- `max` (1 edge(s))
- `min` (1 edge(s))
- `intersect1d` (1 edge(s))

### Incoming

- `C:\Users\Ratanshila\Documents\autmated trading\tests\test_cpcv.py` (7 edge(s))
- `arange` (7 edge(s))
- `split` (5 edge(s))
- `len` (4 edge(s))
- `raises` (3 edge(s))
- `int` (1 edge(s))
- `max` (1 edge(s))
- `range` (1 edge(s))
- `min` (1 edge(s))
- `intersect1d` (1 edge(s))
- `float` (1 edge(s))
- `list` (1 edge(s))
- `get_n_splits` (1 edge(s))
- `C:\Users\Ratanshila\Documents\autmated trading\tools\cpcv.py` (1 edge(s))
