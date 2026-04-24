# tests-merge

## Overview

Community of 14 nodes

- **Size**: 14 nodes
- **Cohesion**: 0.2258
- **Dominant Language**: python

## Members

| Name | Kind | File | Lines |
|------|------|------|-------|
| FetchResult | Class | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\news_feed.py | 88-106 |
| as_dict | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\news_feed.py | 97-106 |
| fetch_weekly_high_impact | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\news_feed.py | 109-152 |
| _ff_json_to_event | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\news_feed.py | 155-176 |
| merge_events | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\news_feed.py | 182-228 |
| fetch_and_merge | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\news_feed.py | 231-263 |
| test_ff_json_to_event_parses_happy | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_news_feed.py | 19-31 |
| test_ff_json_to_event_maps_colours | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_news_feed.py | 34-42 |
| test_ff_json_to_event_handles_missing_fields | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_news_feed.py | 45-48 |
| test_merge_creates_file_when_missing | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_news_feed.py | 51-60 |
| test_merge_is_idempotent | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_news_feed.py | 63-71 |
| test_merge_preserves_header_row | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_news_feed.py | 74-89 |
| test_merge_sorts_by_ts | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_news_feed.py | 92-102 |
| test_fetch_result_as_dict_shape | Test | C:\Users\Ratanshila\Documents\autmated trading\tests\test_news_feed.py | 105-110 |

## Execution Flows

- **fetch_and_merge** (criticality: 0.37, depth: 2)

## Dependencies

### Outgoing

- `get` (12 edge(s))
- `str` (8 edge(s))
- `open` (5 edge(s))
- `strip` (4 edge(s))
- `replace` (3 edge(s))
- `exists` (3 edge(s))
- `load` (3 edge(s))
- `lower` (2 edge(s))
- `with_suffix` (2 edge(s))
- `time` (2 edge(s))
- `len` (2 edge(s))
- `add` (2 edge(s))
- `isinstance` (2 edge(s))
- `append` (2 edge(s))
- `dump` (2 edge(s))

### Incoming

- `C:\Users\Ratanshila\Documents\autmated trading\tests\test_news_feed.py` (8 edge(s))
- `C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\news_feed.py` (5 edge(s))
- `open` (3 edge(s))
- `load` (2 edge(s))
- `as_dict` (1 edge(s))
- `exists` (1 edge(s))
- `dump` (1 edge(s))
- `len` (1 edge(s))
- `get` (1 edge(s))
- `sorted` (1 edge(s))
