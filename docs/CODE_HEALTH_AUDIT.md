# TrendMaster v14 Code Health Audit

_Generated 2026-04-24 15:15 from `.code-review-graph/graph.db` over `ai_trading_agents/**` and `tools/**`._

## Summary

- **total live functions**: 465
- **untested**: 431
- **tested coverage**: 7.3%
- **dead-code candidates**: 115

## 1. Untested live functions

Functions in live code with no `TESTED_BY` edge in the graph. 431 total — top 25 by LOC shown below (biggest first = highest-value tests to add).

| LOC | Function | File:line |
|----:|----------|-----------|
| 514 | `tick_once` | `ai_trading_agents/trend_master_brain.py`:829 |
| 205 | `backtest_pro` | `tools/backtest_pro.py`:96 |
| 204 | `backtest_v15` | `tools/backtest_v15.py`:110 |
| 182 | `train_team` | `tools/train_per_team.py`:132 |
| 171 | `run_forever` | `ai_trading_agents/trend_master_brain.py`:1839 |
| 165 | `write_report` | `tools/train_per_team.py`:341 |
| 150 | `backtest` | `tools/backtest_v15_fast.py`:34 |
| 145 | `run_ea_parity_backtest` | `tools/backtest.py`:211 |
| 141 | `backtest_1to3` | `tools/backtest_filtered.py`:117 |
| 111 | `flatten_all_positions` | `ai_trading_agents/panic.py`:114 |
| 108 | `generate_report` | `ai_trading_agents/daily_digest.py`:53 |
| 100 | `_chart_template` | `tools/setup_multi_ea.py`:66 |
| 97 | `run_strategy` | `tools/backtest_profit_filters.py`:130 |
| 90 | `backtest` | `tools/optimize_fast.py`:53 |
| 89 | `write_signal` | `ai_trading_agents/trend_master_brain.py`:738 |
| 87 | `poll` | `ai_trading_agents/trade_tracker.py`:110 |
| 83 | `compute_multiplier` | `ai_trading_agents/kelly_sizer.py`:112 |
| 81 | `to_markdown` | `ai_trading_agents/daily_digest.py`:166 |
| 80 | `run_backtest` | `tools/backtest.py`:129 |
| 79 | `compute_confirmations` | `ai_trading_agents/ea_confirmations.py`:194 |
| 77 | `scan_for_sl_hits` | `ai_trading_agents/reentry_tracker.py`:139 |
| 77 | `retrain` | `tools/retrain_from_trades.py`:85 |
| 73 | `scan_once` | `ai_trading_agents/multi_market_dispatcher.py`:105 |
| 72 | `train` | `ai_trading_agents/meta_labeler.py`:169 |
| 69 | `tick_all` | `ai_trading_agents/trend_master_brain.py`:1769 |

## 2. Dead-code candidates

Live functions with zero incoming `CALLS` edges, no tests, not on the entry-point allow-list. **Review before deleting** — some may be called dynamically (getattr, decorators, string-based dispatch, EA/MT5 callbacks) which the static parser can't see.

Total: **115** candidates. First 25 below.

| Function | File:line | LOC |
|----------|-----------|----:|
| `load_from_settings` | `ai_trading_agents/ab_test.py`:96 | 12 |
| `tick` | `ai_trading_agents/ab_test.py`:109 | 26 |
| `summary` | `ai_trading_agents/ab_test.py`:136 | 14 |
| `push_telegram` | `ai_trading_agents/daily_digest.py`:302 | 12 |
| `read_since` | `ai_trading_agents/event_log.py`:138 | 24 |
| `get_log` | `ai_trading_agents/event_log.py`:171 | 9 |
| `as_dict` | `ai_trading_agents/gate_value.py`:72 | 9 |
| `human` | `ai_trading_agents/gate_value.py`:82 | 17 |
| `_proxy_pnl` | `ai_trading_agents/gate_value.py`:120 | 11 |
| `as_dict` | `ai_trading_agents/kelly_sizer.py`:79 | 10 |
| `as_dict` | `ai_trading_agents/meta_labeler.py`:86 | 7 |
| `predict` | `ai_trading_agents/meta_labeler.py`:112 | 42 |
| `train` | `ai_trading_agents/meta_labeler.py`:169 | 72 |
| `save` | `ai_trading_agents/meta_labeler.py`:245 | 10 |
| `labels` | `ai_trading_agents/metrics.py`:90 | 5 |
| `inc` | `ai_trading_agents/metrics.py`:96 | 4 |
| `labels` | `ai_trading_agents/metrics.py`:110 | 3 |
| `set` | `ai_trading_agents/metrics.py`:114 | 4 |
| `labels` | `ai_trading_agents/metrics.py`:130 | 3 |
| `observe` | `ai_trading_agents/metrics.py`:134 | 9 |
| `counter` | `ai_trading_agents/metrics.py`:157 | 6 |
| `gauge` | `ai_trading_agents/metrics.py`:164 | 6 |
| `histogram` | `ai_trading_agents/metrics.py`:171 | 10 |
| `registry` | `ai_trading_agents/metrics.py`:252 | 2 |
| `render_text` | `ai_trading_agents/metrics.py`:256 | 3 |

## 3. Complexity hotspots (top 20 by LOC)

Largest live functions. Candidates for refactoring into smaller helpers. High LOC correlates with bugs and review friction.

| LOC | Function | File:line | Tested? | Callers |
|----:|----------|-----------|:-------:|-------:|
| 514 | `tick_once` | `ai_trading_agents/trend_master_brain.py`:829 | no | 3 |
| 205 | `backtest_pro` | `tools/backtest_pro.py`:96 | no | 1 |
| 204 | `backtest_v15` | `tools/backtest_v15.py`:110 | no | 1 |
| 182 | `train_team` | `tools/train_per_team.py`:132 | no | 1 |
| 171 | `run_forever` | `ai_trading_agents/trend_master_brain.py`:1839 | no | 1 |
| 165 | `write_report` | `tools/train_per_team.py`:341 | no | 1 |
| 153 | `main` | `tools/optimize_profit_max.py`:74 | no | 0 |
| 150 | `backtest` | `tools/backtest_v15_fast.py`:34 | no | 1 |
| 145 | `run_ea_parity_backtest` | `tools/backtest.py`:211 | no | 2 |
| 141 | `backtest_1to3` | `tools/backtest_filtered.py`:117 | no | 3 |
| 112 | `main` | `tools/backtest_v15.py`:316 | no | 0 |
| 111 | `flatten_all_positions` | `ai_trading_agents/panic.py`:114 | no | 0 |
| 110 | `main` | `tools/optimize_per_pair.py`:124 | no | 0 |
| 108 | `generate_report` | `ai_trading_agents/daily_digest.py`:53 | no | 7 |
| 104 | `main` | `tools/optimize_fast.py`:179 | no | 0 |
| 101 | `main` | `tools/optimize_per_team.py`:162 | no | 0 |
| 100 | `_chart_template` | `tools/setup_multi_ea.py`:66 | no | 1 |
| 97 | `run_strategy` | `tools/backtest_profit_filters.py`:130 | no | 2 |
| 90 | `backtest` | `tools/optimize_fast.py`:53 | no | 3 |
| 89 | `write_signal` | `ai_trading_agents/trend_master_brain.py`:738 | no | 1 |

## 4. Change-risk nodes (top 20 by fan-in)

Functions called by the most other functions. Changes here have the widest blast radius — worth extra review attention and thorough test coverage.

| Callers | Function | File:line | Tested? |
|-------:|----------|-----------|:-------:|
| 13 | `compute_confirmations` | `ai_trading_agents/ea_confirmations.py`:194 | no |
| 12 | `_fmt` | `tools/train_per_team.py`:333 | no |
| 11 | `_ema` | `tools/backtest_filtered.py`:40 | no |
| 11 | `_base_metrics` | `tools/stress_test.py`:105 | no |
| 10 | `compute_multiplier` | `ai_trading_agents/kelly_sizer.py`:112 | no |
| 10 | `is_market_open` | `ai_trading_agents/market_calendar.py`:162 | no |
| 10 | `check_risk` | `ai_trading_agents/risk_manager.py`:136 | no |
| 9 | `team_of` | `ai_trading_agents/risk_manager.py`:34 | no |
| 9 | `avg` | `tools/backtest_profit_filters.py`:252 | no |
| 9 | `fmt` | `tools/backtest_real.py`:192 | no |
| 8 | `vote_all` | `ai_trading_agents/multi_agent.py`:140 | no |
| 8 | `_fmt_num` | `tools/dashboard.py`:480 | no |
| 7 | `generate_report` | `ai_trading_agents/daily_digest.py`:53 | no |
| 7 | `pnl_of` | `ai_trading_agents/trade_tracker.py`:67 | no |
| 6 | `_ema` | `ai_trading_agents/ea_confirmations.py`:77 | no |
| 6 | `_load` | `ai_trading_agents/model_governance.py`:91 | no |
| 6 | `_ema` | `ai_trading_agents/multi_agent.py`:37 | no |
| 6 | `_ff_json_to_event` | `ai_trading_agents/news_feed.py`:155 | no |
| 6 | `merge_events` | `ai_trading_agents/news_feed.py`:182 | no |
| 6 | `_extract` | `ai_trading_agents/performance.py`:48 | no |

## Methodology notes

- Data source: `.code-review-graph/graph.db` (schema v9), built by `code-review-graph build` with Leiden communities via `python-igraph`.
- "Live" scope: files under `ai_trading_agents/` and `tools/`. `archive/`, `tests/`, `outputs/`, and `.venv/` are excluded.
- Entry-point allow-list: dunder methods, `main`, pytest/unittest hooks. Extend `ENTRY_POINT_NAMES` in `tools/code_health_audit.py` if your framework adds more externally-invoked names.
- **Static-only**: dynamic dispatch (getattr, decorators, registries, string-keyed handler maps, MT5 EA callbacks) is invisible to the parser. Use this report as a starting point for investigation, not as ground truth.
- Regenerate: `python tools/code_health_audit.py`. For a fresh graph first: `rebuild_graph.cmd` → then this script.
