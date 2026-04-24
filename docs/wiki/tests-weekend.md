# tests-weekend

## Overview

Community of 17 nodes

- **Size**: 17 nodes
- **Cohesion**: 0.5895
- **Dominant Language**: python

## Members

| Name | Kind | File | Lines |
|------|------|------|-------|
| _market | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\market_calendar.py | 52-57 |
| is_weekend_closed | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\market_calendar.py | 65-80 |
| _load_holidays | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\market_calendar.py | 90-123 |
| _sym_markets | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\market_calendar.py | 126-147 |
| is_holiday | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\market_calendar.py | 150-159 |
| is_market_open | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\market_calendar.py | 162-175 |
| _dt | Function | C:\Users\Ratanshila\Documents\autmated trading\tests\test_market_calendar.py | 13-14 |
| test_crypto_always_open | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_market_calendar.py | 17-25 |
| test_forex_closed_weekend | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_market_calendar.py | 28-33 |
| test_forex_closed_friday_late | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_market_calendar.py | 36-40 |
| test_forex_open_weekday | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_market_calendar.py | 43-46 |
| test_christmas_closes_all | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_market_calendar.py | 49-53 |
| test_new_years_closes_all | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_market_calendar.py | 56-59 |
| test_us_holiday_closes_usd_but_not_jpy_pairs | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_market_calendar.py | 62-70 |
| test_is_weekend_closed_explicit | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_market_calendar.py | 73-78 |
| test_is_holiday_returns_false_on_normal_day | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_market_calendar.py | 81-84 |
| test_unknown_symbol_still_gated_by_weekend | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_market_calendar.py | 87-90 |

## Execution Flows

No execution flows pass through this community.

## Dependencies

### Outgoing

- `add` (3 edge(s))
- `get` (3 edge(s))
- `lower` (2 edge(s))
- `time` (1 edge(s))
- `resolve` (1 edge(s))
- `Path` (1 edge(s))
- `exists` (1 edge(s))
- `open` (1 edge(s))
- `load` (1 edge(s))
- `debug` (1 edge(s))
- `strftime` (1 edge(s))
- `set` (1 edge(s))
- `now` (1 edge(s))
- `weekday` (1 edge(s))
- `datetime` (1 edge(s))

### Incoming

- `C:\Users\Ratanshila\Documents\autmated trading\tests\test_market_calendar.py` (11 edge(s))
- `C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\market_calendar.py` (6 edge(s))
- `lower` (2 edge(s))
