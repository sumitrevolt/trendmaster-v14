# tests-ea

## Overview

Community of 43 nodes

- **Size**: 43 nodes
- **Cohesion**: 0.2299
- **Dominant Language**: python

## Members

| Name | Kind | File | Lines |
|------|------|------|-------|
| EAParams | Class | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\ea_confirmations.py | 58-73 |
| _ema | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\ea_confirmations.py | 77-78 |
| _atr_wilder | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\ea_confirmations.py | 81-92 |
| _adx_wilder | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\ea_confirmations.py | 95-108 |
| _macd | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\ea_confirmations.py | 111-117 |
| _bbands | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\ea_confirmations.py | 120-125 |
| _supertrend | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\ea_confirmations.py | 128-190 |
| compute_confirmations | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\ea_confirmations.py | 194-272 |
| ea_would_enter | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\ea_confirmations.py | 275-289 |
| make_bullish_ohlcv | Function | C:\Users\Ratanshila\Documents\autmated trading\outputs\check_ea_parity_backtest.py | 23-41 |
| main | Function | C:\Users\Ratanshila\Documents\autmated trading\outputs\check_ea_parity_backtest.py | 44-64 |
| test_backtest_runs_and_reports | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_backtest.py | 32-40 |
| test_backtest_missing_csv_raises | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_backtest.py | 43-45 |
| _make_ohlcv | Function | C:\Users\Ratanshila\Documents\autmated trading\tests\test_ea_confirmations.py | 32-46 |
| bull_df | Function | C:\Users\Ratanshila\Documents\autmated trading\tests\test_ea_confirmations.py | 50-52 |
| bear_df | Function | C:\Users\Ratanshila\Documents\autmated trading\tests\test_ea_confirmations.py | 56-57 |
| chop_df | Function | C:\Users\Ratanshila\Documents\autmated trading\tests\test_ea_confirmations.py | 61-63 |
| test_compute_confirmations_returns_all_expected_columns | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_ea_confirmations.py | 67-69 |
| test_compute_confirmations_has_exactly_twenty_columns | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_ea_confirmations.py | 72-74 |
| test_compute_confirmations_row_aligned_with_input | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_ea_confirmations.py | 77-80 |
| test_bull_regime_produces_some_three_of_three_long_bars | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_ea_confirmations.py | 85-88 |
| test_bull_regime_has_more_long_than_short_trend_bars | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_ea_confirmations.py | 92-96 |
| test_bear_regime_produces_some_short_trend_bars | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_ea_confirmations.py | 101-103 |
| test_bear_regime_has_more_short_than_long_trend_bars | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_ea_confirmations.py | 107-111 |
| test_chop_regime_has_fewer_three_of_three_bars_than_bull | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_ea_confirmations.py | 116-122 |
| test_ea_would_enter_returns_long_in_bull_regime | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_ea_confirmations.py | 127-134 |
| test_ea_would_enter_returns_short_in_bear_regime | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_ea_confirmations.py | 138-144 |
| test_ea_would_enter_returns_zero_for_too_short_input | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_ea_confirmations.py | 147-149 |
| test_ea_would_enter_returns_int_type | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_ea_confirmations.py | 152-155 |
| test_ea_params_defaults_match_ea_inputs | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_ea_confirmations.py | 159-168 |
| test_ea_params_is_frozen | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_ea_confirmations.py | 171-174 |
| test_compute_confirmations_accepts_custom_params | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_ea_confirmations.py | 177-181 |
| _atr | Function | C:\Users\Ratanshila\Documents\autmated trading\tools\backtest.py | 51-56 |
| _resample | Function | C:\Users\Ratanshila\Documents\autmated trading\tools\backtest.py | 59-63 |
| Trade | Class | C:\Users\Ratanshila\Documents\autmated trading\tools\backtest.py | 67-75 |
| BacktestReport | Class | C:\Users\Ratanshila\Documents\autmated trading\tools\backtest.py | 79-126 |
| compute | Function | C:\Users\Ratanshila\Documents\autmated trading\tools\backtest.py | 94-107 |
| is_viable | Function | C:\Users\Ratanshila\Documents\autmated trading\tools\backtest.py | 109-110 |
| format | Function | C:\Users\Ratanshila\Documents\autmated trading\tools\backtest.py | 112-126 |
| run_backtest | Function | C:\Users\Ratanshila\Documents\autmated trading\tools\backtest.py | 129-208 |
| run_ea_parity_backtest | Function | C:\Users\Ratanshila\Documents\autmated trading\tools\backtest.py | 211-355 |
| _load_ohlcv_csv | Function | C:\Users\Ratanshila\Documents\autmated trading\tools\backtest.py | 358-364 |
| main | Function | C:\Users\Ratanshila\Documents\autmated trading\tools\backtest.py | 367-398 |

## Execution Flows

- **main** (criticality: 0.54, depth: 4)
- **main** (criticality: 0.53, depth: 3)

## Dependencies

### Outgoing

- `float` (16 edge(s))
- `len` (15 edge(s))
- `sum` (14 edge(s))
- `print` (11 edge(s))
- `Series` (9 edge(s))
- `mean` (8 edge(s))
- `abs` (6 edge(s))
- `mask` (6 edge(s))
- `add_argument` (6 edge(s))
- `ewm` (5 edge(s))
- `range` (5 edge(s))
- `int` (5 edge(s))
- `shift` (4 edge(s))
- `max` (4 edge(s))
- `rolling` (4 edge(s))

### Incoming

- `C:\Users\Ratanshila\Documents\autmated trading\tests\test_ea_confirmations.py` (19 edge(s))
- `C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\ea_confirmations.py` (9 edge(s))
- `sum` (9 edge(s))
- `C:\Users\Ratanshila\Documents\autmated trading\tools\backtest.py` (8 edge(s))
- `len` (4 edge(s))
- `C:\Users\Ratanshila\Documents\autmated trading\outputs\check_ea_parity_backtest.py` (2 edge(s))
- `C:\Users\Ratanshila\Documents\autmated trading\tests\test_backtest.py` (2 edge(s))
- `raises` (2 edge(s))
- `isinstance` (2 edge(s))
- `range` (2 edge(s))
- `str` (1 edge(s))
- `compute` (1 edge(s))
- `issubset` (1 edge(s))
- `set` (1 edge(s))
- `all` (1 edge(s))
