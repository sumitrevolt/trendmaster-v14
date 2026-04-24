# ai-trading-agents-handle

## Overview

Community of 73 nodes

- **Size**: 73 nodes
- **Cohesion**: 0.1187
- **Dominant Language**: python

## Members

| Name | Kind | File | Lines |
|------|------|------|-------|
| StateStore | Class | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\state_store.py | 71-166 |
| __init__ | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\state_store.py | 78-81 |
| load | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\state_store.py | 83-99 |
| save | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\state_store.py | 101-150 |
| append_result | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\state_store.py | 153-156 |
| update_signal | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\state_store.py | 158-166 |
| pnl_of | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\trade_tracker.py | 67-95 |
| TradeTracker | Class | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\trade_tracker.py | 99-210 |
| poll | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\trade_tracker.py | 110-196 |
| _worst_loss_for | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\trade_tracker.py | 199-210 |
| _pair_sl_tp | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\trend_master_brain.py | 191-218 |
| _effective_min_conf | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\trend_master_brain.py | 254-268 |
| _build_risk_config | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\trend_master_brain.py | 283-318 |
| _tf_for | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\trend_master_brain.py | 332-333 |
| _log_dedup | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\trend_master_brain.py | 343-351 |
| _tf_to_mt5 | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\trend_master_brain.py | 354-365 |
| _mt5_initialize_with_retry | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\trend_master_brain.py | 377-394 |
| _mt5_copy_rates_safe | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\trend_master_brain.py | 397-417 |
| _ema | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\trend_master_brain.py | 423-424 |
| _rsi | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\trend_master_brain.py | 427-432 |
| _atr | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\trend_master_brain.py | 435-440 |
| _adx | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\trend_master_brain.py | 443-456 |
| build_features | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\trend_master_brain.py | 459-500 |
| BrainState | Class | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\trend_master_brain.py | 519-529 |
| TrendMasterBrain | Class | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\trend_master_brain.py | 532-2009 |
| __init__ | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\trend_master_brain.py | 537-586 |
| _load_model | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\trend_master_brain.py | 589-601 |
| pull_bars | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\trend_master_brain.py | 604-616 |
| infer_ml | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\trend_master_brain.py | 619-641 |
| infer_rule | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\trend_master_brain.py | 643-665 |
| mtf_agree | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\trend_master_brain.py | 668-686 |
| agent_vote | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\trend_master_brain.py | 689-709 |
| _resolve_signal_path | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\trend_master_brain.py | 712-724 |
| _signal_filename_for | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\trend_master_brain.py | 726-736 |
| write_signal | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\trend_master_brain.py | 738-826 |
| tick_once | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\trend_master_brain.py | 829-1342 |
| _build_status_message | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\trend_master_brain.py | 1345-1391 |
| _build_pnl_message | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\trend_master_brain.py | 1393-1434 |
| _is_today | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\trend_master_brain.py | 1412-1422 |
| _handle_perf | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\trend_master_brain.py | 1437-1467 |
| _handle_digest | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\trend_master_brain.py | 1469-1478 |
| _handle_gates | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\trend_master_brain.py | 1480-1498 |
| _handle_var | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\trend_master_brain.py | 1500-1525 |
| _handle_drift | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\trend_master_brain.py | 1527-1553 |
| _handle_halt | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\trend_master_brain.py | 1555-1565 |
| _handle_halt_close | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\trend_master_brain.py | 1567-1601 |
| _handle_halt_plain | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\trend_master_brain.py | 1604-1642 |
| _handle_resume | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\trend_master_brain.py | 1644-1668 |
| _handle_why | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\trend_master_brain.py | 1670-1727 |
| _build_symbols_message | Function | C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\trend_master_brain.py | 1729-1741 |

*... and 23 more members.*

## Execution Flows

- **main** (criticality: 0.72, depth: 5)
- **__init__** (criticality: 0.58, depth: 1)
- **_handle_why** (criticality: 0.53, depth: 1)
- **scan_for_sl_hits** (criticality: 0.45, depth: 2)
- **main** (criticality: 0.45, depth: 2)
- **main** (criticality: 0.45, depth: 2)
- **_build_status_message** (criticality: 0.43, depth: 1)
- **poll** (criticality: 0.37, depth: 2)
- **_handle_halt** (criticality: 0.36, depth: 1)

## Dependencies

### Outgoing

- `get` (136 edge(s))
- `float` (76 edge(s))
- `int` (44 edge(s))
- `print` (35 edge(s))
- `getattr` (29 edge(s))
- `len` (25 edge(s))
- `debug` (25 edge(s))
- `append` (23 edge(s))
- `time` (19 edge(s))
- `list` (18 edge(s))
- `load` (16 edge(s))
- `save` (14 edge(s))
- `join` (14 edge(s))
- `warning` (12 edge(s))
- `max` (12 edge(s))

### Incoming

- `C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\trend_master_brain.py` (18 edge(s))
- `C:\Users\Ratanshila\Documents\autmated trading\tests\test_state_store.py` (14 edge(s))
- `load` (13 edge(s))
- `update_signal` (5 edge(s))
- `save` (4 edge(s))
- `append_result` (3 edge(s))
- `list` (3 edge(s))
- `range` (3 edge(s))
- `len` (3 edge(s))
- `write_text` (3 edge(s))
- `C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\trade_tracker.py` (2 edge(s))
- `dumps` (2 edge(s))
- `dict` (2 edge(s))
- `C:\Users\Ratanshila\Documents\autmated trading\tools\smoke_v14_brain.py` (2 edge(s))
- `C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\state_store.py` (1 edge(s))
