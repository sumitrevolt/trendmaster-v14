<!--
  TrendMaster v14 collaboration brief.
  This file is loaded into every Claude session for this project.
  Keep it dense, factual, and current. Avoid prose.
-->

# TrendMaster v14 — Claude collaboration brief

## What this project is

Live MT5 algorithmic trading bot. Python brain in `ai_trading_agents/`
talks to an MQL5 EA (`AI_SUPERBB_v14_TrendMaster.mq5`) via a JSON
signal file. Brain scans 19 symbols every ~3 s on H1 timeframe across
4 teams: METALS, FOREX, CRYPTO, COMMODITIES. Single operator (Sumit),
running on Windows + OctaFX-Demo broker.

## Current state (snapshot — verify against logs/, don't trust this past 24h)

- Brain is running on **rule-based inference** (`infer_rule`). Top-level
  ML model `trend_master_model.lgb` is renamed to
  `.weak_disabled_2026-04-24` because it had no predictive edge
  (holdout acc 0.344 vs random 0.333).
- Feature-alignment guard (`ai_trading_agents/ml_align.py`) is wired
  into `infer_ml`; if a model is loaded with mismatching feature names,
  inference safely routes to `infer_rule` instead of feeding misaligned
  columns.
- Per-team ML models in `ai_trading_agents/ml_models/` are trained
  separately and used by the meta-labeler / drift / Kelly stack but not
  by `infer_ml`. CRYPTO model flagged INSUFFICIENT_DATA (only 2 losses
  in 259 trades — see `tools/validate_crypto_ml.py`).
- Live trade history is sparse: 1 deal in last 6 weeks (ETHUSD
  2026-04-17, -$0.69). All other "trades" in `brain_memory.json` are
  from a 2026-03-08 backtest snapshot.
- See `docs/POSTMORTEMS/2026-04-24_zero_trades.md` for the 47-day
  silent-failure incident and root cause (feature-order mismatch
  after a retrain). The fix is in commit `c08cae1`.

## Tools you must use BEFORE Grep/Read for code exploration

The project has a knowledge graph. Use it first:

- `semantic_search_nodes` for finding functions/classes by keyword
- `query_graph` for callers / callees / imports / tests-for
- `get_architecture_overview` and `list_communities` for high-level structure
- `detect_changes` and `get_review_context` when reviewing changes
- `get_impact_radius` and `get_affected_flows` to understand blast radius
- Fall back to Grep/Glob/Read only when the graph doesn't cover what you need

The graph auto-updates on every file change via the PostToolUse hook
in `tools/crg_hook.cmd`.

## Key files (memorize these paths)

| What | Path | Notes |
|---|---|---|
| Brain main loop | `ai_trading_agents/trend_master_brain.py` | ~2000 lines; tick loop, gates, infer_ml/rule |
| Feature builder | `ai_trading_agents/trend_master_brain.py::build_features` | line ~459, returns DataFrame with FEATURE_COLS |
| Feature list | `ai_trading_agents/trend_master_brain.py::FEATURE_COLS` | line ~499; canonical 25 names |
| ML alignment guard | `ai_trading_agents/ml_align.py` | uses model.feature_name() to reorder columns |
| Profit filter gates | `ai_trading_agents/profit_filters.py::evaluate_all` | 6 gates; spread_guard is OFF by policy |
| Rule-based inference | `ai_trading_agents/trend_master_brain.py::infer_rule` | uses ema_stack/adx/rsi/bb_z; score >=0.35 fires |
| State store | `ai_trading_agents/state_store.py` | reads/writes `logs/brain_state.json` |
| EA reproduction | `ai_trading_agents/ea_confirmations.py` | reproduces EA's 3-of-3 quorum bar-by-bar |
| Backtest | `tools/backtest.py::run_backtest`, `run_ea_parity_backtest` | both walk-forward |
| Walk-forward lab | `tools/walkforward_lab.py` | per-symbol R&D harness across all 19 CSVs |
| ML overfit validator | `tools/validate_crypto_ml.py` | per-team CV with class-imbalance gate |
| Zero-trades watchdog | `tools/zero_trades_watchdog.py` + scheduled task | daily 09:00 local |
| EA parity nightly | `tools/ea_parity_nightly.py` + scheduled task | weekdays 02:30 local |
| Diagnostic | `tools/diagnose_zero_trades.py` | OK / HALTED / MODEL_UNIFORM / CONF_BELOW_THRESHOLD |
| Skills | `docs/skills/trading-*` | brain-restart, daily-pnl, ea-parity, why-inspector, zero-trades |
| Postmortems | `docs/POSTMORTEMS/` | one file per incident |
| Round 5 deploy | `docs/DEPLOY_ROUND5_RUNBOOK.md` | per-team cap, session boost, reentry, pyramid, TP-ladder |

## Data

- 19 historical CSVs in `data/<symbol_lower>_m5_history.csv`. Schema:
  `time,open,high,low,close,volume`. Each ~50,000 M5 bars,
  2025-08-07 → 2026-04-23 (~263 days).
- `logs/brain_state.json` is the single source of truth for live state:
  `last_signal_per_symbol`, `recent_results`, `trading_paused`,
  `drawdown_lockout_until`, `start_of_day_equity`, etc.
- `logs/brain_memory.json` `trade_history[]` is **NOT live trade
  history** — it's training data for the per-team ML models. Always
  cross-check `max(ts)` against now before treating it as recent.

## Gates (in order brain applies them)

1. kill_switch — `state.halted` or `state.trading_paused` → NONE
2. mtf_agree — fast/mid/slow timeframes must agree
3. confidence gate — `conf >= MIN_CONF` (default 0.58, peak floor 0.50)
4. profit_filters.evaluate_all — 6 sub-gates (vol_regime, profit_lock,
   loss_streak_cooldown, daily_loss_limit, session_window,
   news_blackout). spread_guard is intentionally **disabled**.
5. multi_agent.vote_all — 3 agents (trend/momentum/timing) must agree
6. risk_manager — max_open, max_open_per_team (=2), per-symbol cap
7. EA quorum — `require_all_3` confirmations (loosenable via signal JSON)
8. reentry_tracker — permits, cooldown, size_mult, max_age

## Honest performance ceiling (from research, not aspiration)

- 3-class direction prediction (your problem): realistic accuracy is
  **38–42%** vs 33.3% random; anything > 45% is suspect for overfit.
- 2-class binary direction (typical literature): realistic ceiling is
  **53–56%**; 80%+ AUC papers are mostly compromised by lookahead.
- Profitability comes from R:R + position sizing, NOT from raw
  accuracy — published walk-forwards with WR 38% can be profitable
  with right TP/SL geometry.

## Where the alpha actually lives (use this for feature R&D)

Synthesis from quant literature (López de Prado AFML, Hudson & Thames,
Quantpedia, MQL5 forum 2024-2026):

1. **Triple-barrier labels** beat fixed-time forward returns; barriers
   = (TP=k1·ATR, SL=k2·ATR, time=N bars), label = whichever hits first.
2. **Fractional differentiation (d≈0.4)** of log-price keeps long
   memory while making the series stationary. Integer differencing
   (your `ret_*`) destroys ~99% of price information.
3. **Hurst exponent** (rolling 200-bar) gates trend-vs-revert regime
   directly. H>0.5 trending, H<0.5 mean-reverting.
4. **Cross-asset features** are first-order for FX. Add DXY, US10Y,
   VIX, gold/oil ratios H1-aligned. Single-pair models leave 30-40%
   of variance on the table.
5. **Sample-weight by uniqueness** is mandatory for overlapping
   labels (your 12-bar horizon overlaps 11/12 with neighbours →
   labels are NOT iid; LightGBM bagging memorizes).
6. **Meta-labeling** beats raw classifier improvements: keep the
   primary side-classifier, add a secondary binary "act/skip" model
   trained on triple-barrier outcomes; trade only when P_act > 0.55.

## How to be a great collaborator on this codebase

**Do:**
- Verify against the live brain log (`logs/trend_master_brain.out`)
  before claiming a fix worked. Restart-to-test is cheap.
- Save institutional knowledge in `docs/POSTMORTEMS/` after any
  non-trivial debug session.
- Treat any change to `infer_ml` / `infer_rule` / gate logic as a
  production change. Run `tools/diagnose_zero_trades.py` before and
  after. Compare confidence distributions.
- Use the existing walk-forward harness (`tools/walkforward_lab.py`)
  to measure edge before adding indicators or changing gates. Numbers,
  not opinions.
- When proposing a new ML model, prove its OOF metrics with
  `tools/validate_crypto_ml.py` (CPCV + walk-forward + class-imbalance
  guard) before any deployment.
- Commit early and often; pre-commit (ruff, end-of-file-fixer,
  code-review-graph hook) is fast.
- Wrap operational helpers as Claude skills under `docs/skills/`
  so they're discoverable from the picker.

**Don't:**
- Don't restart the brain on a hunch. Use `start_brain_clean.cmd`
  only after `diagnose_zero_trades` says you have a real problem to
  solve.
- Don't lower MIN_CONF below 0.50 to force trades — that trades on
  noise.
- Don't re-enable spread_guard without asking. Memory entry
  `feedback_no_spread_gate` records the operator policy.
- Don't trust `feature_name()` returning generic `Column_0..` — the
  alignment guard will catch it but a CI check should also fail.
- Don't use `Stop-Process -Force` in PowerShell — cascades to parent
  terminal on Win11 24H2. Use `taskkill /F /IM python.exe`.
- Don't introduce new dependencies casually. The repo runs on a live
  trading machine; npm/Bun/Rust toolchains add Defender attack surface.
  We just had 34 files quarantined by Defender mid-session.

## Operator's invariants (never break these)

- Spread guard stays disabled.
- Per-team max-open stays at 2.
- Trades on rules > trades on broken ML > no trades.
- Brain must produce real (non-uniform) confidence distribution. If
  std<0.05 across 18 markets, the model is broken — fall back to rules
  via `align_feature_row` returning None.
- All commits go through pre-commit; no `--no-verify`.

## Useful one-liners

```cmd
:: Live state inspection
.venv\Scripts\python.exe tools\diagnose_zero_trades.py

:: Why isn't symbol X firing?
.venv\Scripts\python.exe -c "import json; from pathlib import Path; print(json.dumps(json.loads(Path('logs/brain_state.json').read_text())['last_signal_per_symbol']['XAUUSD'], indent=2))"

:: Run all four ML team validators
.venv\Scripts\python.exe tools\validate_crypto_ml.py --team all

:: Per-symbol walk-forward
.venv\Scripts\python.exe tools\walkforward_lab.py --symbol all

:: Brain restart with safety
start_brain_clean.cmd

:: Check schtasks installed
schtasks /query /tn "TrendMaster Zero Trades Watchdog" /fo LIST
schtasks /query /tn "TrendMaster EA Parity Nightly" /fo LIST
```

## Open R&D priorities (in order)

1. **Triple-barrier labelling** — replace fixed-horizon return labels
   in `tools/train_v14_better.py` with TP/SL/time triple-barrier;
   target acc on purged CV ≥ 0.40.
2. **Fractional-diff & Hurst features** — added to `build_features` in
   commit shipped with this CLAUDE.md upgrade. Retrain after 1-2 weeks
   of live data accumulation under the new labels.
3. **Cross-asset features** — pull DXY/VIX/US10Y H1-aligned into
   `build_features`. Requires either MT5 symbols if the broker offers
   them or a free macro-data feed.
4. **Meta-labelling head** — keep current 3-class as side-classifier,
   add binary act/skip classifier on triple-barrier outcomes.
5. **Sequential-bootstrap LightGBM** — replace stock bagging to fix
   overlapping-label correlation.
6. **HMM-gated experts** — only after 1-4 deliver a deployable Sharpe.

## Pre-commit hook gotchas (saw these mid-session)

- `ruff format` reformats files at commit time → first attempt fails,
  re-stage and re-commit. This is normal.
- `end-of-file-fixer` modifies trailing newlines → same pattern.
- Long commit messages with `&&` need `-m "..."` per line.
- `code-review-graph incremental update` runs on every commit (~2s).

## Memory and identity

User auto-memory lives in
`C:\Users\Ratanshila\AppData\Roaming\Claude\local-agent-mode-sessions\.../memory/`.
Read MEMORY.md at session start; it has 16+ entries covering v14
phases, gate policy, schedule of incidents, and known gotchas. When
saving project memory, add a one-line entry to MEMORY.md and a typed
detail file under the same directory.
