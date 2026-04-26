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

- **`ai_trading_agents/` is a Windows NTFS junction** (`mklink /J`)
  pointing to `C:\TrendMaster_aita_canonical\`. This is permanent
  infrastructure, not a temporary fix — see
  `docs/POSTMORTEMS/2026-04-25_phantom_deletion_incident.md` for why
  (OneDrive/EDR was silently deleting `*.py` files in the original
  Documents-side folder; the junction with the curated source outside
  Documents stopped that). **Do NOT delete the junction or move modules
  back into the original folder.**
- **`.resolve()` trap inside the brain package**: any module living
  inside `ai_trading_agents/` that needs the project root must use
  `Path(__file__).parent.parent` — NEVER `Path(__file__).resolve().parent.parent`,
  because `.resolve()` follows the junction to `C:\` and breaks every
  config-file lookup. This rule is project-specific, only applies to
  files inside the junction (i.e. `ai_trading_agents/`); files in
  `tools/`, `tests/`, `docs/skills/` can use `.resolve()` normally
  because they live outside the junction. Audit was clean as of
  2026-04-25 evening — zero `.resolve()` callsites remain inside the
  package. (12 total were affected: 6 found in the first pass + 6
  more found later by re-grepping the canonical source directly via
  Windows. The Linux mount under-reported the brain-side files because
  it follows the junction differently from `Path.resolve()`. Always
  re-grep `C:\TrendMaster_aita_canonical\` directly when auditing
  `.resolve()` regressions.)
- The `archive/legacy_python/` folder still holds byte-perfect
  canonical copies of every brain module (used as the seed for
  `C:\TrendMaster_aita_canonical\`). Treat it as the disaster-recovery
  source-of-truth.
- Brain is running on **rule-based inference** (`infer_rule`) in
  practice. Top-level ML model `trend_master_model.lgb` IS still on
  disk and IS still being loaded by `_load_model()` at brain startup
  — but it has no predictive edge (holdout acc 0.344 vs random 0.333,
  diagnose verdict MODEL_UNIFORM). The `ml_align` guard catches
  feature-name mismatch and routes inference back to `infer_rule`
  whenever the model would otherwise produce uniform 1/3 outputs.
  (CLAUDE.md previously claimed the file was renamed to
  `.weak_disabled_2026-04-24`. Verified 2026-04-25: no such rename
  exists. To actually disable, run:
  `move ai_trading_agents\trend_master_model.lgb ai_trading_agents\trend_master_model.lgb.weak_disabled_2026-04-24`
  — operator decision because the rename forces the brain into the
  per-team-model path which has its own MODEL_UNIFORM finding on
  CRYPTO.)
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
- **Phase A1 / A2 / B1 / B2 landed 2026-04-26.** A1+A2 surveyed
  influencer / smart-money tracking as an alpha source — see
  `reports/influencer_tracking_feasibility_2026-04-26.md` and
  `reports/influencer_correlation_phaseA2_2026-04-26.md`. B1 shipped
  the cross-asset / smart-money join harness in
  `ai_trading_agents/cross_asset_join.py` (COT + EIA fetchers,
  H1-aligned); commit `862077b`. **B2 (commit `5b85a21`) wired features
  in**: `ai_trading_agents/feature_cols_v2.py` now exports `FEATURE_COLS_V2`
  (33 cols = 25 v1 + 7 COT spec_delta_z + ng_storage_delta_z),
  `SYMBOL_COT_MAP` (19 symbols → COT contract), and `build_features_v2`
  (fill_na_smartmoney for live inference). `tick_once` in brain has CFG
  gate `smartmoney_features_enabled` (now **True** as of B3). Walkforward
  comparison 2026-04-26: V1 acc=0.422 expR=0.317 vs V2 acc=0.421 expR=0.306
  across 19 symbols — no regression; CRYPTO improves (+3 pp expR, +1 pp acc);
  EIA absent (no `EIA_API_KEY` set, ng_storage_delta_z = all-NaN, auto-
  dropped to 32 effective features — set key in `config/.env` to unlock).
  **Phase B3 shipped (commit follows B2 on 2026-04-26).** Triple-barrier
  retrain on all 19 symbols, FEATURE_COLS_V2 (32 eff. features); purged 5-fold
  walk-forward OOF acc=0.393 (threshold 0.38 → PROMOTE). Model saved to
  `ai_trading_agents/trend_master_model_v2.lgb` and copied over live
  `trend_master_model.lgb`. `smartmoney_features_enabled=True` set in
  `config/settings.py`. Restart brain with `start_brain_clean.cmd` to
  activate; run `diagnose_zero_trades.py` after restart to confirm MODEL_OK.
  See `docs/POSTMORTEMS/2026-04-26_pre_commit_junction_breakage.md` for
  the junction-related drama during the B1/B2 commit cycles.

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
| Smart-money join | `ai_trading_agents/cross_asset_join.py` | Phase B1, COT+EIA fetchers + H1 align (Phase B2 wires features into FEATURE_COLS) |
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
| Skills | `docs/skills/trading-*` | 32 skills: 14 original (mql5-ea, python-brain, risk-ops, backtest, bridge, strategies, indicators, ml-features, optimization, news-events, order-execution, portfolio, deploy-monitor, debug) + 5 ops (brain-restart, daily-pnl, ea-parity, why-inspector, zero-trades) + 8 from `trendmaster-quant-bundle` (tca-daily, stress-replay, model-healthcheck, postmortem-new, schtasks-audit, cross-asset-features, triple-barrier-upgrade, drift-triage) + 5 from `trendmaster-ops-excellence` (position-reconciliation, walkforward-promotion, cost-attribution, correlation-monitor, broker-failover) |
| Plugins | `*.plugin` (workspace root) | `trendmaster-quant-bundle.plugin`, `trendmaster-ops-excellence.plugin` — installable Cowork plugins mirroring the new skill folders |
| Postmortems | `docs/POSTMORTEMS/` (with `INDEX.md`) | one file per incident; index updated by `trading-postmortem-new` skill |
| Round 5 deploy | `docs/DEPLOY_ROUND5_RUNBOOK.md` | per-team cap, session boost, reentry, pyramid, TP-ladder |

## Brain package maintenance (junction architecture)

`ai_trading_agents/` is a Windows NTFS junction at
`C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents`
pointing to the canonical source folder
`C:\TrendMaster_aita_canonical\`.

To **edit a brain module** (e.g., `state_store.py`): edit it directly
through the `ai_trading_agents/` path; the write goes through to the
canonical folder transparently. No special handling required.

To **add a new brain module**: drop the .py file at
`ai_trading_agents/<name>.py` (or equivalently at
`C:\TrendMaster_aita_canonical\<name>.py`). Both views show it.

To **rebuild the junction from scratch** (e.g., if it ever gets removed):

```cmd
cd /d "C:\Users\Ratanshila\Documents\autmated trading"
rd /s /q ai_trading_agents
mklink /J ai_trading_agents C:\TrendMaster_aita_canonical
```

To **rebuild `C:\TrendMaster_aita_canonical\` from `archive/legacy_python/`**
(disaster recovery):

```cmd
cd /d "C:\Users\Ratanshila\Documents\autmated trading"
mkdir C:\TrendMaster_aita_canonical 2>nul
for %%m in (ab_test advanced_features daily_digest drift_detector ea_confirmations event_log gate_value kelly_sizer market_calendar meta_labeler metrics ml_align model_governance multi_agent multi_market_dispatcher news_feed online_learner ops_maintenance pair_params panic performance portfolio_risk process_lock profit_filters reentry_tracker regime_hmm risk_manager rolling_corr state_store structured_log team_params telegram_commands telegram_notifier trade_tracker) do copy /Y "archive\legacy_python\%%m.py" "C:\TrendMaster_aita_canonical\%%m.py"
```

Plus `trend_master_brain.py`, `__init__.py`, `cross_asset_join.py`, the
`ml_models/` folder, and `trend_master_model.lgb`. The brain restart
script (`start_brain_clean.cmd`) should ideally pre-flight check that
the junction resolves; if `C:\TrendMaster_aita_canonical\` is missing,
the brain will fail at import and the script should refuse to start.

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
- **Don't call `Path(__file__).resolve()` in any module inside
  `ai_trading_agents/`.** The package is a junction; `.resolve()`
  follows it and `parent.parent` lands on `C:\` instead of the project
  root, silently breaking every config-file load. Use plain
  `Path(__file__).parent.parent`. Files in `tools/`, `tests/`,
  `docs/skills/` are outside the junction and CAN use `.resolve()`
  normally.
- **Don't delete or recreate the `ai_trading_agents/` junction unless
  `C:\TrendMaster_aita_canonical\` exists**, otherwise the brain dies
  at next import. See "Brain package maintenance" above.
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
- **Don't run pre-commit without a junction guard.** Pre-commit's `git stash`/restore cycle can replace the `ai_trading_agents/` junction with a real folder (or remove it entirely) when reformatting hooks touch files inside it. The repo now ships `tools/restore_junction.cmd` and a `tools/check_junction.py` pre-commit hook. If you ever see "no module named ai_trading_agents.X" after a commit, run `tools\restore_junction.cmd`. See `docs/POSTMORTEMS/2026-04-26_pre_commit_junction_breakage.md`.

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

1. **✅ DONE — Triple-barrier labelling + V2 retrain (Phase B3)** — shipped
   2026-04-26. `tools/train_v14_b3.py`: 19-symbol pool, TP=2×ATR/SL=1×ATR/
   hold=12H1, purged 5-fold WF OOF acc=0.393. Model live as
   `trend_master_model.lgb`. Restart brain to activate. Set `EIA_API_KEY`
   to unlock 33rd feature (ng_storage_delta_z; currently 32 eff. features).
1b. **✅ DONE — Meta-labelling head (Phase C1)** — shipped 2026-04-26.
    `tools/train_v14_c1_metalabel.py`: 35 meta-features (3 B3 probs + 32 V2),
    binary act/skip on triple-barrier outcomes; purged 5-fold WF OOF AUC=0.906
    (PROMOTE). Model saved to `ai_trading_agents/meta_label_model.lgb`.
    Brain wired (`infer_ml` gate, `_load_meta_model`). Gate is OFF by default.
    To activate:
      1. In `config/settings.py` set `metalabel_enabled = True`
         (also `metalabel_act_threshold = 0.55`)
      2. `start_brain_clean.cmd`
      3. `.venv\Scripts\python.exe tools\diagnose_zero_trades.py`
         --> expect MODEL_OK, non-NONE directions with P_act filter active
2. **Fractional-diff & Hurst features** — retrain after 1-2 weeks of live
   data accumulation under the triple-barrier labels.
3. **Cross-asset features (done: COT+EIA via B1/B2)** — COT 7 contracts
   + EIA NG storage now live in `FEATURE_COLS_V2`. Next: add DXY/VIX/
   US10Y H1-aligned (requires MT5 symbols or free macro feed).
4. **Per-team meta-label models (Phase C2)** — train separate act/skip heads
   per team (METALS/FOREX/CRYPTO/COMMODITIES); team-specific TP_rate varies
   80-88%, per-team models will capture that variance.
5. **Sequential-bootstrap LightGBM** — replace stock bagging to fix
   overlapping-label correlation.
6. **HMM-gated experts** — only after 1-5 deliver a deployable Sharpe.

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
