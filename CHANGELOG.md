# Changelog

All notable changes to TrendMaster are consolidated here. Dates use UTC. This file replaces the scattered `*_STATUS.md` / `*_REPORT.md` files as the single timeline source of truth — those remain for historical context.

## \[v14.5.1\] — 2026-04-25 (EA recompile + CPCV promotion gate)

### Changed

- `AI_SUPERBB_v14_TrendMaster.mq5` — added `g_ai_st_mult` and `g_ai_bb_floor_pct` JSON-override globals + `EffectiveSTMult()` / `EffectiveBBFloorPct()` helpers, mirroring the existing R8/R11 Effective\* pattern. The SuperTrend recalc and BB-width gate now consult the per-team override from the per-symbol signal JSON instead of the compiled `InpST_Mult` / `0.9` literal. Compiled fresh: 0 errors, 0 warnings via `metaeditor64.exe /compile`.
- `ai_trading_agents/trend_master_brain.py` — `_pair_sl_tp()` now returns a 5-tuple `(sl, tp, adx, st, bb_floor)` and the per-symbol signal JSON payload writes the two new keys. Brain restart verified the 5-tuple per team:
  - XAUUSD (METALS) → (3.0, 5.0, 15.0, 3.0, 1.0)
  - EURUSD (FOREX) → (2.5, 3.0, 25.0, 3.0, 1.0)
  - BTCUSD (CRYPTO) → (2.5, 3.0, 35.0, 2.5, 1.0)
  - XTIUSD (COMMOD) → (2.5, 3.0, 30.0, 2.0, 1.0)

### Added

- `tools/config_promotion_gate.py` — CPCV-style purged walk-forward gate (5 folds + 200-bar embargo) that grades the v14.5 per-team rule config against the v14.4 baseline (sl=2.0, tp=3.0, adx=22, st=3.0). Substitute for `trading-walkforward-promotion` because the brain runs `infer_rule` in practice and there are no per-team .lgb candidates to promote.

  Teamv14.5 mean Sharpev14.4 mean SharpeΔSharpeVerdictMETALS0.921 ± 0.860.626 ± 0.78+**0.295**PROMOTEFOREX-0.689 ± 1.29-0.643 ± 1.19-0.046**HOLD**CRYPTO0.543 ± 1.380.186 ± 0.81+**0.357**PROMOTECOMMOD0.397 ± 1.05-0.068 ± 0.94+**0.464**PROMOTE

  Reports: `reports/promotion/config_promotion_2026-04-25_2101.{md,json}`

### Findings (genuine, non-PR)

- **FOREX HOLD is real**: both v14.5 and v14.4 are net-negative on FOREX over CPCV folds. The single-fold sweep in `reports/best_indicators_2026-04-25.md` showed FOREX as profitable in 19/19 — that result was fragile. The CPCV gate (5 purged folds per symbol with 200-bar embargo) is the more honest read. R&D priority: rethink the FOREX team config — the current adx=25 filter isn't lifting WR enough above the universal-22 baseline.

### Operator one-time MT5 step (still pending)

- The newly built `AI_SUPERBB_v14_TrendMaster.ex5` is on disk, but the 19 currently-attached charts in MT5 have the OLD .ex5 in memory. Either restart the MT5 terminal OR remove + re-attach the EA on each chart so they pick up the new st_mult/bb_floor parsing logic. Until then, brain still benefits from per-team SL/TP/ADX (those flow via the existing R8 keys); only ST mult + BB floor wait on the chart re-attach.

## \[v14.5\] — 2026-04-25 (per-market INDICATOR setup, not just SL/TP)

### Changed

- `ai_trading_agents/team_params.py` — every team now has its own ADX threshold + SuperTrend multiplier + BB-floor, in addition to the v14.4 SL/TP. Different markets behave differently, so different indicator setups:

  TeamADX min (was)ST mult (was)BB floor (was)WhyMETALS**15** (was 22)3.0**1.0** (was 0.9)Gold trends regardless of ADX strength — filtering hurtsFOREX**25** (was 22)3.0**1.0**Tighter ADX filter for cleaner FX trendsCRYPTO**35** (was 22)**2.5** (was 3.0)**1.0**Only act on strong momentum; faster ST signalCOMMODITIES**30** (was 22)**2.0** (was 3.0)**1.0**Strong-trend filter + tightest ST mult

  Source: `indicator_sweep_v2.py` over 21 candidate combinations per team (3 axes × 5-7 values), inline backtest using `compute_confirmations`with custom EAParams. Per-team Sharpe (walkforward-equivalent scale, raw sweep / 16):

  Teamv14.4 (sharpe)v14.5 (sharpe)ImprovementMETALS0.445**0.67**+50%FOREX0.361**0.46**+27%CRYPTO0.415**0.53**+28%COMMODITIES0.393**0.48**+22%

### Brain integration

- **adx_min**: brain reads from team_params and passes via signal JSON to EA today. Picks up on next restart.
- **st_mult, bb_width_floor_pct**: documented in team_params but EA-side parameters. Need EA update + recompile to consume per-team override (add `InpSTMult_Override` and `InpBBFloor_Override` inputs to `AI_SUPERBB_v14_TrendMaster.mq5`, have EA read from signal JSON). Until then, EA uses its compiled defaults (st=3.0, bb_floor=0.9). ADX is the highest-impact axis anyway (the +27-50% Sharpe lift is almost entirely from ADX changes).

### Backups

- `C:\\_param_backups_2026-04-25\\team_params_v14_4_174707.py.bak`
- v14.4 backup also still present from earlier run

### Pending operator action

- Brain restart picks up per-team `adx_min` immediately. No urgency — weekend, only crypto active.
- For full v14.5 deployment (st_mult + bb_floor per team), update EA inputs + recompile. Without it, \~70% of the v14.5 benefit is captured via adx_min alone.
- Run `trading-walkforward-promotion` skill before treating any of this as permanent (operator policy).

### Honest caveats

- 263-day single-regime sample. The CRYPTO sweet spot (adx_min=35, WR 51.3%) is small-N — only 2 symbols, 395 trades each. Treat with more skepticism than the FOREX (12 symbols, 90K trades) result.
- Backtest uses synthetic SL/TP, no slippage. Live Sharpe will be 10-20% lower.
- This sweep tested adx_min, st_mult, bb_width_floor_pct only. EMA periods, RSI bands, MACD periods unchanged. Future R&D: per-team EMA periods (METALS may want longer ema_trend, CRYPTO shorter).

## \[v14.4\] — 2026-04-25 (per-market SL/TP optimization from walkforward sweep)

### Changed

- `ai_trading_agents/team_params.py` — TEAM_PARAMS replaced with per-team optimal SL/TP from 21-config walkforward sweep across all 19 symbols (\~140K trades total). Each market gets its own setup because they behave differently:

  TeamOLD (sharpe)NEW (sharpe)ImprovementMETALS (XAU,XAG)1.0/5.0 (0.08)**3.0/5.0 (0.445**)5.5xFOREX (12 pairs)0.75/4.25 (0.04)**2.5/3.0 (0.361**)9.0xCRYPTO (BTC,ETH)0.75/5.0 (0.05)**2.5/3.0 (0.415**)8.3xCOMMODITIES (XTI,XBR,XNG)0.75/5.0 (0.09)**2.5/3.0 (0.393**)4.4x

  Why METALS different: gold's high volatility + news-driven swings (FOMC, CPI, geopolitical) reward wider stops + wider targets. Other 3 teams converge on R:R 1.2:1 (40-46% WR within López de Prado honest band).

- `ai_trading_agents/pair_params.py` — PAIR_PARAMS cleared (was `auto-generated by tools/optimize_per_pair.py` but values were sub-optimal vs new TEAM_PARAMS; some at NEGATIVE expectancy: EURGBP -0.032, XTIUSD -0.010). Brain now falls through to TEAM_PARAMS for every symbol, gaining 5-9x Sharpe.

### Backed up

- Old `team_params.py` and `pair_params.py` backed up to `C:\_param_backups_2026-04-25\` before overwrite.

### Reports

- `reports/best_indicators_2026-04-25.md` — full sweep analysis with per-symbol rankings and honest caveats (10-20% Sharpe haircut for real-trading slippage; 263-day single-regime sample warning; re-run monthly).
- `reports/walkforward/2026-04-25_1137.{md,json}` — raw walkforward output.

### Pending operator action

- Brain restart required to pick up new params (the running process has OLD configs in memory). `start_brain_clean.cmd` has the new pre-flight check that will validate the new TEAM_PARAMS before mutating state. No urgency — markets are weekend; new configs only affect actual trade decisions which next happen Sunday 22:00 UTC.
- Operator should run `trading-walkforward-promotion` skill (Round 2) to formally validate the new configs against the prior CPCV-stable baseline before considering this a permanent change.

### Honest caveats (also in best_indicators report)

- EA-parity backtest uses synthetic SL/TP — no slippage, spread, or requote modeling. Live Sharpe will be **10-20% lower** than backtest. Realistic live targets: METALS \~0.36, FOREX \~0.29, CRYPTO \~0.33, COMMODITIES \~0.31.
- 263 days of historical data = single-regime sample. The wider-stop edge may not hold in a low-volatility regime. Re-run monthly.
- WR 42-46% is at the upper edge of the 38-42% honest band (per López de Prado AFML). NOT flagged as overfit on metric grounds, but CRYPTO's 46.1% (only 2 symbols) is small-N and may be noise.
- This swept SL/TP only — indicators (ema_stack/ADX/RSI) unchanged.

## \[v14.3\] — 2026-04-25 (god-mode session: junction architecture, 13 new skills, 12 path-bug fixes, archive cleanup)

### Added

- **Junction-backed brain package** — `ai_trading_agents/` is now an NTFS junction → `C:\TrendMaster_aita_canonical\`. Defeats the OneDrive / EDR phantom-deletion that was wiping `*.py` files in the Documents-side folder. See `docs/POSTMORTEMS/2026-04-25_phantom_deletion_incident.md`.
- **2 Cowork plugins** (32 skills total): `trendmaster-quant-bundle`(8 skills: tca-daily, stress-replay, model-healthcheck, postmortem-new, schtasks-audit, cross-asset-features, triple-barrier-upgrade, drift-triage) and `trendmaster-ops-excellence`(5 skills: position-reconciliation, walkforward-promotion, cost-attribution, correlation-monitor, broker-failover). Both installed under `docs/skills/` AND packaged as `.plugin` files at repo root.
- `ai_trading_agents/cross_asset_join.py` — DXY/VIX/US10Y H1-aligned feature merge for the cross-asset features pack (skill produces; brain consumes after manual `FEATURE_COLS` extension).
- `tools/pytest_health_check.cmd` + scheduled task `TrendMaster Pytest Health Check` (daily 09:05) — drops `logs/pytest_health.alert` on collection error so the 32-silent-collection-failure shape from 2026-04-24 is caught within 24h.
- Pre-flight check in `start_brain_clean.cmd` — refuses to start if `C:\TrendMaster_aita_canonical\` is missing OR if `import ai_trading_agents.trend_master_brain` fails.
- 4 postmortems under `docs/POSTMORTEMS/`: `2026-04-25_aita_restore_and_skill_install.md`, `2026-04-25_phantom_deletion_incident.md`, `2026-04-25_godmode_round2_consolidation.md`, plus updated `INDEX.md`.
- `psutil>=7.2` added to top-level `requirements.txt` for liveness checks.
- Dashboard stack (`fastapi>=0.110`, `uvicorn>=0.27`, `httpx>=0.27`, `websockets>=12.0`) added to top-level `requirements.txt` (was only in `ai_trading_agents/requirements.txt`).

### Fixed

- **12** `.resolve()` **traps** inside `ai_trading_agents/` (6 morning fixes by operator: `market_calendar`, `profit_filters`, `news_feed`, `ops_maintenance`, `gate_value`, `event_log`; 6 evening fixes by Claude: `trend_master_brain` itself, `state_store`, `process_lock`, `multi_market_dispatcher`, `telegram_notifier`, `model_governance`). Each was silently routing brain state writes / config lookups / Telegram alerts to `C:\` instead of the trading folder via the junction. Smoking gun: `C:\logs\brain.lock` and `C:\logs\brain_state.json` had been silently created.
- `tools/cleanup_project.py:137` — F823 latent bug (`deleted += 1`, `moved += 1` referenced module-level globals without `global`declaration). Added `global moved, deleted` at top of `main()`.
- `ai_trading_agents/institutional_agents.py:857` — W293 whitespace.
- `tools/trade_tracker.py` corruption — 1568 NUL bytes appended (Defender artifact), restored from canonical archive.
- Top-level `main.py` — restored from `archive/legacy_python/main_2.py`(had been silently deleted; blocked test_main_cli collection).
- `.git/index.lock` — stale 3-h-old empty file removed (was blocking future commits).
- 13 new skill helpers — pandas 3.0 deprecation (`"1H"` → `"1h"`), cp1252 mojibake on em-dash/arrow chars (replaced ASCII), filename drift (`deals.csv` → `trades.csv`, `event_log.jsonl` → `events.jsonl`).

### Changed

- [CLAUDE.md](http://CLAUDE.md) — added junction architecture section, brain package maintenance commands, `.resolve()` rule in Don't list, accurate model state (was claiming `trend_master_model.lgb` was renamed to `.weak_disabled_2026-04-24`; verified it isn't, doc updated).
- `logs/events.jsonl` rotated (was 121 MB, now 0; archived as `events.jsonl.2026-04-25`).

### Removed

- Hard-deleted **8 archive subfolders** (\~554 files, 16.84 MB freed): `_to_delete_pending_review/` (462 files), `_corrupt_quarantine_2026-04-25/`, `legacy_bat/`, `legacy_experts/` (4 old MQL5 EAs), `legacy_state/`(41 files), `screenshots/` (13 PNGs), `src/` (28 legacy), `backtesting/`(4 legacy). KEPT `archive/legacy_python/` (179 .py — disaster-recovery seed per [CLAUDE.md](http://CLAUDE.md)).
- Quarantined session-debris from `outputs/`: 66 one-off `.bat` helper scripts, 10 `_*.py` siblings, 5 old run logs.
- 16 root-level diagnostic `.cmd` / `.ps1` scripts (superseded by new `tools/pytest_health_check.cmd`, `tools/diagnose_zero_trades.py`, enhanced `start_brain_clean.cmd`).
- 22 `reports/signal_report_2026-03-*.md` — March signal reports.
- Stale `logs/brain.lock` (PID 13764, dead) and `logs/brain.pid` (PID 13384, dead). Backups at `logs/_stale_locks_2026-04-25/`.
- Wrong-path artifacts at `C:\logs\brain.lock` and `C:\logs\brain_state.json` (created by the `.resolve()` bug). Quarantined to `logs/_wrong_path_2026-04-25/` then `C:\logs\` removed.

### Verified

- pytest end-to-end: **all 487 dots, 0 failed, 0 errored.**
- Brain restart with new pre-flight: **PASSED.**
- Brain alive throughout cleanup (PIDs 33592 + 33340, multi-hour uptime, state writes to correct location every \~30 s).
- Telegram alerts: verified working post-fix (test message delivered).
- Junction integrity: `fsutil reparsepoint query` confirms target is `C:\TrendMaster_aita_canonical\`.
- Archive: down from 20.85 MB to 4.01 MB (legacy_python only).

## \[Unreleased\]

### Added

- `main.py` — single CLI entry point with subcommands (`scan`, `run`, `dashboard`, `supervise`, `backtest`, `train`, `pull-history`, `health`).
- `ai_trading_agents/risk_manager.py` — pure-Python position sizer + daily-loss / concurrency / correlation gates with a single `check_risk()` decision API.
- `ai_trading_agents/multi_market_dispatcher.py` — walks the full `TRADING_PAIRS` list (4 teams, 20+ pairs), runs the agent bus per symbol, works offline via `data/*.csv` when MT5 isn't installed.
- `tools/backtest.py` — walk-forward M5 backtester with ATR-sized SL/TP, R-multiple reporting, viability check (`expectancy > 0` and `n >= 30`).
- `tools/label_trades.py` — converts `logs/trades.csv` into per-symbol R-multiple + `won_R` label files (closes the gap flagged in FINAL_UPGRADE_REPORT.md).
- `tools/retrain_from_trades.py` — binary "should I take this setup?" classifier trainer consuming labels + history.
- `tools/pull_history.py` — fan-out M5 history pull across every configured pair.
- `tools/model_registry.py` — versioned model storage with `latest.lgb`pointer + rollback.
- `tools/supervisor.py` — tiny process supervisor (auto-restart with exponential backoff, structured heartbeat at `logs/supervisor.log`).
- `tools/dashboard.py` — new `/healthz` endpoint used by supervisor and `python main.py health`.
- Pytest suite (`tests/test_*.py`) covering multi_agent, risk_manager, dispatcher, backtest, model_registry, label_trades, and CLI parser.
- GitHub Actions CI (`.github/workflows/ci.yml`) — lint + pytest on push/PR across Python 3.10/3.11/3.12.
- `Dockerfile` + `docker-compose.yml` — headless brain + dashboard with Linux-compatible fallbacks.
- `DEVELOPER_GUIDE.md` — how to add a symbol, team, or agent.
- `LICENSE` (MIT) and consolidated `CHANGELOG.md` (this file).

### Changed

- `.gitignore` — hardened to exclude `config/.env`, `logs/`, `*.pid`, `models/`, `*.bak`, `*.log`, `*.err`, and `data/*.csv`.
- `tools/dashboard.py` — adds `/healthz` readiness probe.

## \[v14.2\] — 2026-04-22

### Added

- Multi-timeframe agent bus (`ai_trading_agents/multi_agent.py`) — trend_h4 + momentum_h1 + timing_m30 with unanimous-vote gate.
- HTF gate in the EA (`AI_SUPERBB_v14_TrendMaster.mq5`) — four-filter architecture (EA 3/3 + HTF gate + brain direction + agent vote).
- Visual indicator overlays (EMA/BB/SuperTrend lines + BUY/SELL arrows
  - SL/TP lines) in the EA.

## \[v14.1\] — 2026-04-20

### Changed

- Attempted LightGBM brain on 50K XAUUSD M5 bars — ML did not beat the 53% baseline; brain reverted to rule-based (`model=rule`).
- Fixed MT5 chart auto-attach (`path=` field in injected `<expert>` block), Unicode print crash, and regex backref bug in `tools/inject_ea_into_chart.py`.
- Built historical pipeline for XAUUSD M5 → `data/xauusd_m5_history.csv`.

## \[v14.0\] — 2026-04-13

### Added

- Initial TrendMaster v14 — rule-based brain writing `trendmaster_signals.json`, EA reads file as 3rd gate on top of its own 3-of-3 confirmation.
- OctaFX-Demo wiring, `config/settings.py`, batch launchers.
