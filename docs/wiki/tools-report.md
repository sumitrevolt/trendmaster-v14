# tools-report

## Overview

Community of 24 nodes

- **Size**: 24 nodes
- **Cohesion**: 0.3226
- **Dominant Language**: python

## Members

| Name | Kind | File | Lines |
|------|------|------|-------|
| test_flash_crash_detects_harm | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_stress_test.py | 22-26 |
| test_order_shuffle_reports_worst_dd | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_stress_test.py | 29-32 |
| test_spread_spike_reduces_pnl | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_stress_test.py | 35-37 |
| test_mt5_outage_drops_trades | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_stress_test.py | 40-43 |
| test_gap_risk_injects_losses | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_stress_test.py | 46-48 |
| test_black_monday_is_destructive | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_stress_test.py | 51-53 |
| test_run_all_produces_report | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_stress_test.py | 56-62 |
| test_report_as_dict_serializable | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_stress_test.py | 65-70 |
| ScenarioResult | Class | C:\Users\Ratanshila\Documents\autmated trading\tools\stress_test.py | 55-71 |
| as_dict | Function | C:\Users\Ratanshila\Documents\autmated trading\tools\stress_test.py | 63-71 |
| StressReport | Class | C:\Users\Ratanshila\Documents\autmated trading\tools\stress_test.py | 75-92 |
| as_dict | Function | C:\Users\Ratanshila\Documents\autmated trading\tools\stress_test.py | 79-83 |
| human | Function | C:\Users\Ratanshila\Documents\autmated trading\tools\stress_test.py | 85-92 |
| _drawdown | Function | C:\Users\Ratanshila\Documents\autmated trading\tools\stress_test.py | 98-102 |
| _base_metrics | Function | C:\Users\Ratanshila\Documents\autmated trading\tools\stress_test.py | 105-107 |
| flash_crash | Function | C:\Users\Ratanshila\Documents\autmated trading\tools\stress_test.py | 110-124 |
| order_shuffle | Function | C:\Users\Ratanshila\Documents\autmated trading\tools\stress_test.py | 127-147 |
| spread_spike | Function | C:\Users\Ratanshila\Documents\autmated trading\tools\stress_test.py | 150-165 |
| mt5_outage | Function | C:\Users\Ratanshila\Documents\autmated trading\tools\stress_test.py | 168-181 |
| gap_risk | Function | C:\Users\Ratanshila\Documents\autmated trading\tools\stress_test.py | 184-198 |
| black_monday | Function | C:\Users\Ratanshila\Documents\autmated trading\tools\stress_test.py | 201-214 |
| run_all | Function | C:\Users\Ratanshila\Documents\autmated trading\tools\stress_test.py | 220-238 |
| _load_pnls_from_brain_memory | Function | C:\Users\Ratanshila\Documents\autmated trading\tools\stress_test.py | 241-259 |
| main | Function | C:\Users\Ratanshila\Documents\autmated trading\tools\stress_test.py | 262-276 |

## Execution Flows

- **main** (criticality: 0.38, depth: 3)
- **as_dict** (criticality: 0.32, depth: 1)

## Dependencies

### Outgoing

- `max` (12 edge(s))
- `min` (8 edge(s))
- `len` (6 edge(s))
- `round` (4 edge(s))
- `list` (4 edge(s))
- `print` (4 edge(s))
- `float` (3 edge(s))
- `sum` (3 edge(s))
- `int` (3 edge(s))
- `abs` (3 edge(s))
- `range` (3 edge(s))
- `dumps` (2 edge(s))
- `isinstance` (2 edge(s))
- `append` (2 edge(s))
- `array` (2 edge(s))

### Incoming

- `C:\Users\Ratanshila\Documents\autmated trading\tools\stress_test.py` (13 edge(s))
- `C:\Users\Ratanshila\Documents\autmated trading\tests\test_stress_test.py` (8 edge(s))
- `as_dict` (1 edge(s))
- `loads` (1 edge(s))
- `dumps` (1 edge(s))
- `isinstance` (1 edge(s))
- `len` (1 edge(s))
- `human` (1 edge(s))
