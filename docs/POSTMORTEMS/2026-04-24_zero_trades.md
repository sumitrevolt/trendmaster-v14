# Postmortem: 47-day zero-trades incident

_Date of incident: approximately 2026-03-09 onward_
_Date of detection & fix: 2026-04-24_
_Severity: HIGH (full revenue loss over 47 days, no capital risk)_
_Author: diagnosed and remediated jointly by operator (Sumit) and assistant_

## Summary

From approximately 2026-03-09 the TrendMaster v14 Python brain continued
running and scanning all 18 configured symbols every 3 seconds but
produced zero live trades. The only exception was a single ETHUSD
deal on 2026-04-17 (-$0.69). The silent-failure was missed because
(a) all operator attention was on memory-tracked improvements to the
gates, the ML pipeline, and new modules; (b) `trade_history` in
`logs/brain_memory.json` looked healthy but was a frozen snapshot of
a 2026-03-08 backtest; (c) no alerting existed for the "running but
not trading" state.

## Impact

- 47 days of zero live trades. Opportunity cost: unknown, non-zero.
- All ML-related work (`lgbm_CRYPTO.pkl` flagged as 99.2% WR,
  Round 2/3/5 additions, validator build, class-imbalance checks) was
  done against the 2026-03-08 backtest snapshot, not live data.
- Operator confidence in the system was eroded - multiple memory
  entries claimed "zero-trades fix applied" during this window when
  the root cause was elsewhere.

## Timeline (UTC)

| When                 | What                                                                                                |
|----------------------|-----------------------------------------------------------------------------------------------------|
| 2026-03-08 20:56-21:04 | Backtest session produces 500 "trades" in 8 minutes (259 ETHUSD + 241 XAUUSD); these become `trade_history` and the training set for the top-level LGBM model. |
| ~2026-03-09 onward    | Brain goes live. Every tick returns NONE for every symbol. No live trades executed.                 |
| 2026-04-17            | A single ETHUSD deal closes at -$0.69 (recorded in `state.recent_results`). Origin of this trade is unclear - may predate a brain restart. |
| 2026-04-23            | Per-team ML pipeline runs; `lgbm_CRYPTO.pkl` flagged as likely overfit. Operator notes land in memory. This masks the deeper issue: the top-level model is what actually drives `infer_ml`, not the per-team one. |
| 2026-04-24 11:08      | `trend_master_model.lgb` retrained. Output confidence collapses to ~0.344 +/- 0.005 across all 18 symbols. Almost certainly a feature-order mismatch introduced by the retrain. |
| 2026-04-24 18:53      | Brain restart #26 picks up the new model. `tick_all summary: NONE=18` becomes the only log line produced.      |
| 2026-04-24 16:40-17:10 | Assistant diagnostic pass: state inspection reveals confidence cluster near 1/3, std=0.005 across 18 different markets. Root cause identified as feature misalignment at inference. |
| 2026-04-24 commit c08cae1 | Fix lands: `ai_trading_agents/ml_align.py` + `infer_ml` patched to use `model.feature_name()` for column order; `_load_model` now logs an audit line at boot. |

## Root cause

`trend_master_brain.py::infer_ml` used the module-level `FEATURE_COLS`
list to index the features DataFrame and then called
`lgb.Booster.predict(numpy_array)`. Because numpy arrays carry no
column names, the Booster had no way to detect that the caller was
feeding it columns in the wrong order. When the 2026-04-24 retrain
produced a model with a slightly different feature order, inference
silently mixed up the columns. A LightGBM multi-class Booster fed
shuffled features collapses to a near-uniform distribution over the
classes - exactly the 0.344 +/- 0.005 we saw on every market.

The `FEATURE_COLS` list and the trained feature list may or may not
be identical - but even when they are, the code had no defense
against future drift.

## Why detection took 47 days

1. **No "not trading" alert.** The stack had alerts for errors,
   drawdown, halts, and news events, but no alert for the condition
   "brain is healthy and scanning but has not placed a deal in N
   hours." A trading system that does not trade is indistinguishable
   from one that is waiting for the right setup - unless we check.
2. **`trade_history` was a red herring.** 500 rows looked like a rich
   live dataset. They were a frozen snapshot from one backtest window.
   Any aggregation metric (WR, PnL, Sharpe) looked fine against them.
3. **Recent "fix" memory entries.** Memory contained several entries
   claiming zero-trades was fixed (Round 11 and others). Operators
   trusted those entries and did not re-verify with a full diagnostic.
4. **The daily digest does not distinguish new deals from old.** The
   Telegram `/pnl` and daily digest aggregate `trade_history` and
   `recent_results` without emphasising time-since-last-deal.

## Fix (commit c08cae1)

Three parts:

1. **`ai_trading_agents/ml_align.py`** - new helper `align_feature_row()`
   that calls `model.feature_name()` (LightGBM API) to pick features
   in training-time order, not brain's FEATURE_COLS order.
2. **`trend_master_brain.py::infer_ml`** - uses the helper. If any
   trained feature is missing from the DataFrame, route to rule
   fallback (no silent zero-fill).
3. **`trend_master_brain.py::_load_model`** - on boot, logs an audit
   line: `ML feature audit: order_match=...  model_count=...
   brain_count=...`. Any future retrain drift is visible in
   `logs/trend_master_brain.out` immediately after restart.

Unit-tested in `tests/test_ml_align.py` (8 tests including the shuffled
order regression).

## Prevention (added 2026-04-24)

- **`tools/diagnose_zero_trades.py`** - standalone diagnostic.
  Classifies brain state into OK / HALTED / MODEL_UNIFORM /
  CONF_BELOW_THRESHOLD / INSUFFICIENT_STATE with remediation text.
  Runs in seconds, read-only.
- **`tools/zero_trades_watchdog.py` + `install_zero_trades_watchdog.bat`**
  (new) - scheduled task runs daily 09:00 local. If no closed deal
  in N hours AND brain is not explicitly halted, post Telegram alert.
  This is what would have caught the incident 46 days earlier.
- **`docs/skills/trading-zero-trades/SKILL.md`** - skill wrapper so
  the diagnostic is discoverable from the skill picker.

## Lessons

1. **A trading system that cannot detect "not trading" is a broken
   trading system.** This is the single most load-bearing correction
   from this incident. Going forward: any execution system we ship
   must have a watchdog that alerts on extended silence.
2. **Do not trust `trade_history` as proof of life.** Always check
   `max(ts)` and compare to "now" before treating the dataset as
   current.
3. **Booster.predict on numpy arrays is unsafe by default.** When
   the downstream library drops column names, the caller owns the
   column-order contract. Always round-trip through the model's own
   `feature_name()` when the API supports it.
4. **"Almost certainly X" memory entries need a verification step.**
   The zero-trades memory entries from earlier rounds described
   symptoms that matched this incident, but no one ran a full
   diagnostic afterwards.
5. **Per-team metrics can mask top-level failures.** We spent hours
   on `lgbm_CRYPTO.pkl` overfit analysis while the primary classifier
   (`trend_master_model.lgb`) was the actual problem. Inspect the
   first link in the chain before drilling into sub-components.

## Follow-ups tracked

- [ ] Operator to execute brain restart per
      `docs/skills/trading-brain-restart/SKILL.md` to activate the fix.
- [ ] After restart: run `python tools/diagnose_zero_trades.py` and
      confirm std(confidence) > 0.05 and at least one symbol clears
      MIN_CONF=0.58.
- [ ] Operator to install the zero-trades watchdog with
      `install_zero_trades_watchdog.bat` (admin).
- [ ] Within 7 days: retrain `trend_master_model.lgb` with explicit
      feature-name recording so `feature_name()` returns the same
      order as `FEATURE_COLS` by convention, not by alignment guard.
- [ ] Add a Grafana panel (Round 2 stack) for `last_signal_per_symbol`
      confidence mean and std so that next time a uniform-1/3
      collapse is a 5-second visual check, not a 30-minute diagnostic.
