# Changelog

All notable changes to TrendMaster are consolidated here. Dates use UTC.
This file replaces the scattered `*_STATUS.md` / `*_REPORT.md` files as the
single timeline source of truth — those remain for historical context.

## [Unreleased]

### Added
- `main.py` — single CLI entry point with subcommands (`scan`, `run`,
  `dashboard`, `supervise`, `backtest`, `train`, `pull-history`, `health`).
- `ai_trading_agents/risk_manager.py` — pure-Python position sizer +
  daily-loss / concurrency / correlation gates with a single
  `check_risk()` decision API.
- `ai_trading_agents/multi_market_dispatcher.py` — walks the full
  `TRADING_PAIRS` list (4 teams, 20+ pairs), runs the agent bus per
  symbol, works offline via `data/*.csv` when MT5 isn't installed.
- `tools/backtest.py` — walk-forward M5 backtester with ATR-sized
  SL/TP, R-multiple reporting, viability check (`expectancy > 0` and
  `n >= 30`).
- `tools/label_trades.py` — converts `logs/trades.csv` into per-symbol
  R-multiple + `won_R` label files (closes the gap flagged in
  FINAL_UPGRADE_REPORT.md).
- `tools/retrain_from_trades.py` — binary "should I take this setup?"
  classifier trainer consuming labels + history.
- `tools/pull_history.py` — fan-out M5 history pull across every
  configured pair.
- `tools/model_registry.py` — versioned model storage with `latest.lgb`
  pointer + rollback.
- `tools/supervisor.py` — tiny process supervisor (auto-restart with
  exponential backoff, structured heartbeat at `logs/supervisor.log`).
- `tools/dashboard.py` — new `/healthz` endpoint used by supervisor
  and `python main.py health`.
- Pytest suite (`tests/test_*.py`) covering multi_agent, risk_manager,
  dispatcher, backtest, model_registry, label_trades, and CLI parser.
- GitHub Actions CI (`.github/workflows/ci.yml`) — lint + pytest on
  push/PR across Python 3.10/3.11/3.12.
- `Dockerfile` + `docker-compose.yml` — headless brain + dashboard with
  Linux-compatible fallbacks.
- `DEVELOPER_GUIDE.md` — how to add a symbol, team, or agent.
- `LICENSE` (MIT) and consolidated `CHANGELOG.md` (this file).

### Changed
- `.gitignore` — hardened to exclude `config/.env`, `logs/`, `*.pid`,
  `models/`, `*.bak`, `*.log`, `*.err`, and `data/*.csv`.
- `tools/dashboard.py` — adds `/healthz` readiness probe.

## [v14.2] — 2026-04-22
### Added
- Multi-timeframe agent bus (`ai_trading_agents/multi_agent.py`) —
  trend_h4 + momentum_h1 + timing_m30 with unanimous-vote gate.
- HTF gate in the EA (`AI_SUPERBB_v14_TrendMaster.mq5`) — four-filter
  architecture (EA 3/3 + HTF gate + brain direction + agent vote).
- Visual indicator overlays (EMA/BB/SuperTrend lines + BUY/SELL arrows
  + SL/TP lines) in the EA.

## [v14.1] — 2026-04-20
### Changed
- Attempted LightGBM brain on 50K XAUUSD M5 bars — ML did not beat the
  53% baseline; brain reverted to rule-based (`model=rule`).
- Fixed MT5 chart auto-attach (`path=` field in injected
  `<expert>` block), Unicode print crash, and regex backref bug in
  `tools/inject_ea_into_chart.py`.
- Built historical pipeline for XAUUSD M5 → `data/xauusd_m5_history.csv`.

## [v14.0] — 2026-04-13
### Added
- Initial TrendMaster v14 — rule-based brain writing
  `trendmaster_signals.json`, EA reads file as 3rd gate on top of its
  own 3-of-3 confirmation.
- OctaFX-Demo wiring, `config/settings.py`, batch launchers.
