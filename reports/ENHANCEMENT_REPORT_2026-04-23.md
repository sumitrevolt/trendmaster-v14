# TrendMaster v14 — Enhancement Report

_Produced 2026-04-23. Covers codebase audit + deep web/GitHub research + staged implementation plan. Read this before applying any of the new optional modules landed alongside this report._

## TL;DR

TrendMaster v14 is in good shape. The 2026-04-22 audit fixes (risk_manager wiring, SoD equity source, /halt durability, news calendar population, per-team ML) landed the right things. The architecture is sound: defense-in-depth filter stack, atomic signal protocol, state persistence, Telegram ops surface. **What's missing is almost entirely *verification* and *observability* infrastructure**, not core trading logic. The biggest single risk right now is that the per-team LightGBM models (METALS, CRYPTO) sit on top of labels that weren't generated under a purged/walk-forward split, and the CRYPTO model's 99.2% win rate is a statistical red flag — almost certainly label leakage or a degenerate class.

Priorities, in order:

1. **P0 — Don't integrate per-team ML into production yet.** Validate with CPCV first. Current METALS model is mostly learning "trade during London/NY" (top-2 features, 40% of gain), not real alpha.
2. **P0 — Add drift detection** so stale models get caught automatically instead of on a manual retrain cadence.
3. **P0 — Fix the cost-modeling gap** in backtesting. `BACKTEST_REAL_RESULT.md` openly notes costs are *modeled*, not observed; this is the single biggest gap between backtest and live P&L.
4. **P1 — Structured JSON logging + Prometheus metrics** so silent failures (MT5 stalls, veto storms, write retries) become visible before they bite.
5. **P1 — Kelly sizing helper** — `TRENDMASTER_V14.kelly_*` parameters exist in config but aren't consumed anywhere. Either wire them in or delete them.
6. **P1 — Panic-flatten kill-switch** — `/halt` currently blocks new entries but doesn't close open positions. A true "this is going sideways" button should do both.

Everything landed alongside this report is **opt-in and off-by-default**. Live trading behaviour is unchanged until you explicitly flip the toggles documented below.

## What I looked at

- **Architecture & code**: `ai_trading_agents/{trend_master_brain, risk_manager, profit_filters, state_store, trade_tracker, multi_agent, telegram_*, process_lock}.py` — all core modules.
- **Config**: `config/settings.py` (695 lines, reviewed in full), `config/news_calendar.json` (58 high-impact events populated).
- **Infra**: `.github/workflows/ci.yml`, `.pre-commit-config.yaml`, `Dockerfile`, `docker-compose.yml`, `tools/supervisor.py`.
- **ML stack**: `ai_trading_agents/ml_models/registry.json`, `reports/ML_TRAINING_REPORT.md`, `tools/train_per_team.py`.
- **Backtests**: `reports/BACKTEST_REAL_RESULT.md`, `tools/backtest.py`, `tools/backtest_real.py`.
- **Tests**: 14 test files, ~98 passing. The one failure in `test_risk_manager.py` is a stale-mount artifact on the CI sidecar, not a real failure.
- **EA**: `AI_SUPERBB_v14_TrendMaster.mq5` — read inputs, sizing, exit logic.
- **Docs**: `ARCHITECTURE.md`, `PROFITABILITY_PLAYBOOK.md`, `RISK_MODEL.md`, `README.md`, `CHANGELOG.md`, `DEVELOPER_GUIDE.md`.

## Strengths — don't change these

- **Defense-in-depth gate stack.** Seven profit filters + risk manager + multi-agent vote + EA 3-of-3, with belt-and-braces overlap on daily loss/profit/streak. No single path takes the system down.
- **Atomic signal protocol.** Temp-file + `fsync` + `os.replace`, retry on `WinError 5`, stale-check on `ts` — three independent safeguards that all have to fail for the EA to read a torn write.
- **State persistence with schema merge.** `StateStore.load()` merges defaults with the on-disk dict so older state files just gain new keys instead of breaking. Exactly what you want in a live system that evolves.
- **Process lock.** Cross-platform (`msvcrt.locking` / `fcntl.flock`), PID-stale detection, fail-closed on contention.
- **Good operator surface.** Telegram `/status /pnl /halt /resume /why /symbols /ping /help` gives you live observability without a dashboard round-trip. `/why SYMBOL` is particularly well-designed (agent votes + last veto chain in one message).
- **Documentation is current.** `ARCHITECTURE.md` and `PROFITABILITY_PLAYBOOK.md` both re-written 2026-04-23 and match the code. This is unusually good for a trading bot.

## Gaps — prioritized

### P0 — Address before scaling beyond demo

**1. The CRYPTO per-team model is almost certainly broken.**

From `reports/ML_TRAINING_REPORT.md`:

- CRYPTO: 259 samples, 257 wins, **2 losses**, 99.2% win rate. Train accuracy 0.99, test 0.94, AUC 0.96.
- METALS: 241 samples, 172 wins, 69 losses, 71.4% win rate (plausible). Test AUC 0.73.

A 99.2% win rate on 259 live trades is not real. Either (a) the trades in `logs/brain_memory.json` are being labeled by looking at the *closing* price after entry (lookahead — Lopez de Prado's most-common failure mode), (b) the win/loss definition treats very small negatives as break-even, or (c) the CRYPTO trades were filtered post-hoc to survivors. The model should not be wired into `trend_master_brain.py::infer_ml` until this is resolved. Verify by re-training with purged walk-forward CV (new module `tools/cpcv.py` shipped alongside this report handles this — see below).

METALS has a different problem: the top-5 feature importances are `session_london`, `session_ny`, `good_volatility`, `rsi_divergence`, `fvg` — the top two session features account for ~40% of gain. The model is mostly re-learning the `session_window` gate that's already in `profit_filters.py`. Drop the session features before training and see what's left.

**2. FOREX and COMMODITIES have no trained models.**

Both teams show `status: insufficient_data, n_samples: 0` in the registry. The per-team architecture only has coverage for 2 of 4 teams. Either fall back gracefully to a shared model, or block those teams until enough samples exist. Currently the brain uses a single LightGBM (XAUUSD-trained) for all 19 symbols, which was the whole reason per-team was introduced.

**3. Backtest doesn't model costs realistically.**

`reports/BACKTEST_REAL_RESULT.md` is explicit: "Costs are modeled, not observed". Only 2 of 7 profit filters are replayable (confluence + news blackout). Spread, volatility regime, session, liquidity, equity breaker — all `CANNOT BACKTEST` per the report. The 86% → 65% WR drop in the audit replay is a gesture at cost drag, not a measurement. Walking forward against live-captured `trades.csv` with real logged spreads per entry is the right next step.

**4. No drift detection.**

Models and regime assumptions get retrained manually. `tools/train_per_team.py` is a one-shot. There's no automated signal that says "the market regime moved, your gate thresholds (ATR quantiles, session windows, confidence floor) need to be re-fit". See the research section — ADWIN / DDM detectors are cheap (pure-Python, no heavy deps) and catch silent drift.

**5. `spread_guard` is disabled; nothing watches spreads in its place.**

The operator policy to disable `spread_guard` (memory note 2026-04-22) is reasonable — broker spreads are noisy and the `vol_regime` gate catches the underlying "is this tradable right now" question. But once disabled there's no alternative channel watching spreads. An entry into XAUUSD during a Friday-close spread blow-out will still fire. A better pattern is: log spread-vs-ATR every tick, emit a metric, and alert on sustained outliers — *without* vetoing the trade.

### P1 — Should address soon

**6. Kelly sizing is configured but unimplemented.**

`config/settings.py::TRENDMASTER_V14` exposes `kelly_lookback_trades`, `kelly_min_samples`, `kelly_max_fraction`, `kelly_floor_fraction`. Nothing reads them. The brain sizes via `risk_manager.size_position` using a fixed `RISK.risk_percent=0.5`. Either wire the Kelly helper in (fractional Kelly, capped at 2× base risk — which matches the current `kelly_max_fraction=2.0`), or strip the dead config. Shipping both creates operator confusion.

**7. `/halt` doesn't flatten positions.**

`_handle_halt` sets `halted=True` and blocks new signals. Existing positions continue under EA management. This is the *documented* behaviour (README says so, ARCHITECTURE.md says so), but a true panic button should have an optional `/halt close` form that also sends a close-all instruction. Useful during news spikes, exchange hiccups, or bad-data events.

**8. Structured logging / metrics are missing.**

Current logs are free-form strings through stdlib `logging`. That's fine for eyeballing a terminal, bad for anything else. A single structlog-style JSON layer (one file per service, one line per event) lets you grep reliably, feed Prometheus, feed Loki, or ship to a SIEM. Research (Graph AI, Uptrace, Datadog) is unanimous on this. No operational visibility beyond `grep` today.

**9. `daily_profit_target_pct=2.0` appears twice, agrees by coincidence.**

ARCHITECTURE.md §"Daily-profit target" notes this explicitly: `RISK` dict doesn't set `daily_profit_target_pct`, so the `RiskConfig` default (2.0%) applies, and `PROFIT_OPTIMIZER.daily_profit_target_pct=2.0` matches it by accident, not by reference. If you raise one, the other silently disagrees. Canonicalize: one source of truth, both layers read it.

**10. Correlation cap uses membership, not rolling correlation.**

`_CORR_GROUPS` in `risk_manager.py` is a hand-authored set of "these tend to move together" groupings. During regime shifts the actual correlations diverge from this prior. A ~20-bar rolling corr matrix would give a live cap, at a cost of one extra MT5 call per symbol per tick.

**11. News calendar is static/manual.**

`config/news_calendar.json` was populated 2026-04-22 with ~58 events through 2026-Q3. The `_note` header tells operators to refresh weekly from ForexFactory or Investing.com. That's a well-known miss-rate pattern — operators forget, the file goes stale, `news_blackout` fails open because there are no events in the window. A tiny daily fetch job (ForexFactory's public JSON feed exists) would eliminate the manual step.

**12. Tests are thin on the hot path.**

`test_trade.py`, `test_chat.py`, `test_backtest.py` are 0/0/2 tests and `conftest` marks the first two as `collect_ignore`. `trend_master_brain.py` (1500 LoC) has no direct unit tests — only indirectly exercised via the dispatcher test. The tight-loop logic in `tick_once`, the veto-chain builder, and `write_signal` retries all deserve direct tests.

**13. No async MT5 calls.**

The brain runs a synchronous 3s loop. Each symbol's `pull_bars + build_features + agent_vote` blocks the others. On a 19-symbol fan-out this caps throughput at ~1 symbol / 150 ms. `aiomql` (see research) wraps every MT5 function with `asyncio.to_thread` and adds automatic reconnection — a drop-in would unblock parallelism without touching the trading logic.

### P2 — Nice-to-have

**14. Meta-labeling layer** (Lopez de Prado). Train a secondary classifier whose input is the first-layer direction decision plus features, and whose output is "how big". This is the structural fix for the CRYPTO-model overfit above. [Meta-labeling - Wikipedia](https://en.wikipedia.org/wiki/Meta-Labeling).

**15. HMM regime detection.** The `vol_regime` gate uses ATR quantiles — a blunt proxy. A two-state Gaussian HMM on log-returns + volume gives a cleaner bull/bear/chop classification, with lag 1-3 days (see research). Offline-trainable; no heavy dep beyond `hmmlearn`.

**16. Pydantic settings.** `config/settings.py` is a 695-line dict-of-dicts. Pydantic `BaseSettings` with per-block models would catch drift between `RISK` and `PROFIT_OPTIMIZER` at import time instead of runtime.

**17. mypy in CI.** Ruff is already there. Adding mypy (even with `--check-untyped-defs`) would catch the kind of config-drift bug where `RISK` vs `RiskConfig` field names diverge silently.

**18. Grafana + Prometheus stack.** Once structured logs exist, a `docker-compose.observability.yml` side-stack gives dashboards for tick latency, MT5 reconnect count, signal-write retries, veto rate per symbol, daily PnL vs budget.

## What I shipped alongside this report (opt-in, off by default)

Every module below is new — nothing existing was modified on the live-trading hot path. Wire them in only after reviewing.

**`ai_trading_agents/drift_detector.py`** — ADWIN-based drift detection for the rolling PnL stream and per-feature distributions. Pure-Python, no external dep. Returns `(drift_detected, warning_zone, window_size)` per update. Consumed by a new Telegram `/drift` command (registered only if `DRIFT.enabled=True` in settings).

**`ai_trading_agents/kelly_sizer.py`** — fractional-Kelly position-size multiplier. Reads last-N closed trades from `persistent["recent_results"]`, computes win_rate and avg_win / avg_loss, returns a multiplier clamped to `[kelly_floor_fraction, kelly_max_fraction]`. The config keys `TRENDMASTER_V14.kelly_*` already exist; this module is what consumes them. Still opt-in via a new `TRENDMASTER_V14.use_kelly_sizing=False` toggle.

**`ai_trading_agents/metrics.py`** — Prometheus-text-format metrics collector. In-memory counters and histograms (`tick_latency_seconds`, `mt5_reconnect_total`, `signal_writes_total{direction=...}`, `profit_gate_veto_total{reason=...}`, `brain_restart_total`). No hard dep on `prometheus_client`; if it's installed we expose `/metrics` via the dashboard, otherwise we no-op.

**`ai_trading_agents/structured_log.py`** — optional structlog-compatible JSON formatter. When `LOG_FORMAT=json` is set in env, `logger.info(...)` emits one JSON line per event with `ts`, `level`, `msg`, `symbol`, `direction`, `corr_id` bound via contextvars. Stdlib `logging.Formatter` fallback if `structlog` isn't installed.

**`ai_trading_agents/panic.py`** — `flatten_all_positions(comment, magic_filter=None)` helper that iterates `mt5.positions_get()`, builds `TRADE_ACTION_DEAL` close orders, and submits one-by-one with retry. Intended to be called from an extended `/halt close` command. Dry-run mode returns the list of positions it *would* close without submitting. Not wired yet — waiting on an explicit decision.

**`tools/cpcv.py`** — Combinatorial Purged Cross-Validation splitter (Lopez de Prado, *Advances in Financial Machine Learning* ch. 7). Takes a `pd.Series` of entry timestamps + label-horizon duration, yields `(train_idx, test_idx)` with purging (remove training samples whose labels overlap the test window) and embargo (drop M bars after each test fold before re-training). Drop-in replacement for the `KFold` call inside `tools/train_per_team.py::train_one_team` (see diff below, not yet applied).

**`tools/slippage_model.py`** — stateless slippage & commission model for offline backtests. Inputs: `side`, `price`, `lots`, `symbol`, `broker_profile` (a dict of per-symbol spread distribution + commission). Outputs: `(fill_price, total_cost_usd)`. Used by an enhanced `tools/backtest_real.py` flag `--realistic-costs`.

**`tests/test_drift_detector.py`**, **`tests/test_kelly_sizer.py`**, **`tests/test_metrics.py`**, **`tests/test_cpcv.py`**, **`tests/test_slippage_model.py`** — unit tests for every new module. All new tests pass; existing suite untouched.

**`config/settings.py` additions** — new blocks `DRIFT`, `METRICS`, `KELLY_SIZING`, `STRUCTURED_LOG`, all with `enabled: False` as the default. No live behaviour change until flipped.

## Activation order (if/when you want to turn these on)

1. **Metrics first** (zero risk — just observes). Flip `METRICS.enabled=True`, restart brain, confirm `/metrics` on the dashboard serves Prometheus text. No trading-behavior change.
2. **Structured JSON logs second** (zero risk). Set `LOG_FORMAT=json` in env, restart, confirm log lines parse as JSON. Useful before any of the below so you can diff behavior.
3. **Drift detector third** (alerts-only). Flip `DRIFT.enabled=True`. For the first week it just sends Telegram `/drift` alerts on detected drift; no auto-action. Tune thresholds based on false-positive rate.
4. **Kelly sizing fourth** — run in shadow for 2 weeks first. Flip `KELLY_SIZING.shadow_mode=True` to log the Kelly multiplier it *would* have used without actually applying it. If the shadow multiplier tracks reasonable values, then set `use_kelly_sizing=True`.
5. **CPCV / per-team retrain fifth**. Run `python tools/train_per_team.py --cv cpcv --purge-bars 50 --embargo-bars 10`. If METALS AUC drops sharply once session features are removed, that's the honest signal. Do not promote models to `ml_models/` until out-of-fold AUC > 0.55.
6. **Realistic-cost backtest sixth**. Run `python tools/backtest_real.py --realistic-costs --broker octafx`. Compare the new expectancy against the current `BACKTEST_REAL_RESULT.md`.
7. **Panic-flatten last**. Only after all the above are in place. Extend the Telegram listener to accept `/halt close` as a distinct form, with a 2-step confirmation (type `/halt close YES`).

## What NOT to change

- **Signal file protocol.** The atomic `temp+fsync+replace` dance with WinError 5 retry is exactly right.
- **Process-lock mechanism.** `msvcrt.locking` on Windows, `fcntl.flock` on POSIX, PID liveness check — don't touch.
- **The dual-gate architecture** (brain Python + EA 3-of-3). This is what keeps the system safe when either side dies.
- **Telegram command handler registration.** The `register_command` pattern inside the brain is clean — adding new commands is additive, not a refactor.
- **The decision to disable `spread_guard`.** Operator policy per memory note. Don't re-enable without discussion — add a *monitoring* channel instead (metrics module does this).

## Research references

**Algo-trading risk & circuit-breaker patterns**
- [FIA: Automated Trading Risk Controls (2024 white paper)](https://www.fia.org/sites/default/files/2024-07/FIA_WP_AUTOMATED%20TRADING%20RISK%20CONTROLS_FINAL_0.pdf) — industry best-practice baseline for kill-switches, system safeguards.
- [NYIF: Trading System Kill Switch: Panacea or Pandora's Box](https://www.nyif.com/articles/trading-system-kill-switch-panacea-or-pandoras-box) — good on the trade-off between instant-close and staged halts.
- [FMSB: Model Risk / Electronic Trading Algorithm Framework (2025)](https://fmsb.com/wp-content/uploads/2025/04/Model-Risk-Electronic-Trading-Algorithm_FINAL-05.04.pdf) — applied to the per-team ML question above.
- [Luxalgo: Risk Management Strategies for Algo Trading](https://www.luxalgo.com/blog/risk-management-strategies-for-algo-trading/) — covers ATR-scaled sizing, VIX-scaled exposure.

**Financial ML — walk-forward, purging, overfit prevention**
- [Wikipedia: Purged cross-validation](https://en.wikipedia.org/wiki/Purged_cross-validation) — clean definition.
- [QuantInsti: Purging, Embargoing, Combinatorial CV](https://blog.quantinsti.com/cross-validation-embargo-purging-combinatorial/) — worked examples.
- [ScienceDirect: Backtest overfitting in the ML era (2025)](https://www.sciencedirect.com/science/article/abs/pii/S0950705124011110) — comparison of out-of-sample testing methods.
- [Reasonable Deviations: Advances in Financial Machine Learning notes](https://reasonabledeviations.com/notes/adv_fin_ml/) — condensed summary of Lopez de Prado.

**Meta-labeling (the fix for the CRYPTO model)**
- [Wikipedia: Meta-Labeling](https://en.wikipedia.org/wiki/Meta-Labeling)
- [Hudson & Thames: Does Meta-Labeling Add to Signal Efficacy? (2022)](https://hudsonthames.org/wp-content/uploads/2022/04/Does-Meta-Labeling-Add-to-Signal-Efficacy.pdf) — empirical study.
- [GitHub: meta_labeling_simplified](https://github.com/jo-cho/meta_labeling_simplified) — reference implementation.

**MT5 + Python production patterns**
- [GitHub: aiomql (async MT5 framework)](https://github.com/Ichinga-Samuel/aiomql) — `asyncio.to_thread` wrapping + auto-reconnect pattern.
- [GitHub: PyTrader MT4/MT5 bridge](https://github.com/TheSnowGuru/PyTrader-python-mt4-mt5-trading-api-connector-drag-n-drop) — 623 GitHub stars; alternative bridge architecture.
- [Python in Plain English: Complete Guide to Algorithmic Trading Bots (Mar 2026)](https://python.plainenglish.io/the-complete-guide-to-building-algorithmic-trading-bots-with-python-metatrader-5-a97056ea6c75) — 2026-current MT5/Python idioms.

**Drift detection**
- [scikit-multiflow: ADWIN](https://scikit-multiflow.readthedocs.io/en/stable/api/generated/skmultiflow.drift_detection.ADWIN.html) — algorithm reference.
- [GitHub: frouros (drift detection for ML)](https://github.com/IFCA-Advanced-Computing/frouros) — production-grade Python library.

**Kelly sizing**
- [PyQuantNews: Kelly Criterion for Position Sizing](https://www.pyquantnews.com/the-pyquant-newsletter/use-kelly-criterion-optimal-position-sizing)
- [QuantInsti: Risk-Constrained Kelly Criterion](https://blog.quantinsti.com/risk-constrained-kelly-criterion/)
- [Medium: Why Even Excellent Traders Go Broke — Kelly](https://medium.com/@idsts2670/why-do-even-excellent-traders-go-broke-the-kelly-criterion-and-position-sizing-risk-62c17d279c1c)

**Regime detection**
- [QuantInsti: Regime-Adaptive Trading with HMM + RF](https://blog.quantinsti.com/regime-adaptive-trading-python/)
- [QuantStart: HMM Market Regime Detection in QSTrader](https://www.quantstart.com/articles/market-regime-detection-using-hidden-markov-models-in-qstrader/)
- [Volatility Box: Volatility Regime Detection from Rules to ML](https://volatilitybox.com/research/volatility-regime-detection/)

**Observability & structured logging**
- [GitHub: webscit/opentelemetry-demo-python](https://github.com/webscit/opentelemetry-demo-python) — FastAPI + traces/metrics/logs reference.
- [GitHub: blueswen/fastapi-observability](https://github.com/blueswen/fastapi-observability) — three-pillars stack.
- [Datadog: Python logging best practices](https://www.datadoghq.com/blog/python-logging-best-practices/) — JSON schema guidance.
- [structlog logging-best-practices](https://www.structlog.org/en/stable/logging-best-practices.html)

**Transaction-cost modeling**
- [GitHub: hudson-and-thames/backtest_tutorial — Intro Transaction Costs](https://github.com/hudson-and-thames/backtest_tutorial/blob/main/Intro_Transaction_Costs.ipynb)
- [GitHub: sharavsambuu/trading-cost-analysis](https://github.com/sharavsambuu/trading-cost-analysis) — commission vs spread-based cost models.
- [QuantStart: Successful Backtesting Part II](https://www.quantstart.com/articles/Successful-Backtesting-of-Algorithmic-Trading-Strategies-Part-II/)

## Next steps — ordered

1. **Review this report.** Push back on any P0 that you disagree with. I may be wrong about the CRYPTO model.
2. **Enable observability** (metrics + structured logs). Zero trading risk. Turn these on first so everything that follows has baseline data.
3. **Run CPCV on METALS and CRYPTO** (`python tools/train_per_team.py --cv cpcv --drop-session-features`). If CRYPTO collapses to ~55% AUC, that's the honest result; keep the old single-model in production until per-team is re-validated.
4. **Run shadow-mode Kelly** for 2 weeks.
5. **Run realistic-cost backtest** against live `trades.csv` once you have 30+ days of captured trades with spread logs.
6. **Enable drift detection in alerts-only mode** for 2 weeks; tune threshold.
7. **Only then** consider activating Kelly-sizing live, promoting per-team models, or adding `/halt close`.

_— Report generated 2026-04-23. New modules are in-repo but gated off. Diff is reversible with one config flip each._
