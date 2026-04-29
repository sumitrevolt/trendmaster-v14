# Postmortem: recurring 109 KB uniform-output model overwriting live (2026-04-29)

**Date:** 2026-04-29 → 2026-04-30 IST (live debug session)
**Severity:** S2 — zero trades since 2026-04-22 (7+ days), brain looked alive but produced NONE for every symbol
**Detector:** operator (Sumit) asked "sab proper work karra kya"; `tools/diagnose_zero_trades.py` returned `MODEL_UNIFORM`
**Status when reported:** brain alive at PID 26444, 18 symbols ticking, conf mean=0.342 std=0.007, all NONE
**Status after fix:** brain alive at PID 2960 (restart#45) in `model=rule` mode; `diagnose_zero_trades` verdict OK with 4 BUY + 2 SELL signals at conf mean 0.78

## TL;DR

A single-symbol legacy V1 trainer (`tools/train_v14_better.py`) keeps overwriting the live `trend_master_model.lgb` with a 109076-byte XAUUSD-only LightGBM booster whose calibrated probabilities cluster around 1/3 across all 18 markets — the textbook MODEL_UNIFORM signature. Every overwrite silences trading until the file is renamed.

Recurrence pattern observed in `C:\TrendMaster_aita_canonical\`:

| mtime | size | archived as |
|---|---|---|
| 2026-04-27 09:05 | 109,076 | `trend_master_model.lgb.weak_v1_backup_2026-04-28` |
| 2026-04-29 09:05 | 109,076 | `trend_master_model.lgb.broken_uniform_20260429` |
| 2026-04-29 19:05 | 109,076 | `trend_master_model.lgb.broken_uniform_again_2026-04-29_223343` |

All three are the same byte-count, all written at `:05` of the hour, suggesting either a scheduled invocation or a habitual operator command at morning + evening.

## Root cause

`tools/train_v14_better.py` (legacy V1 trainer) saved its output directly to the live model path:

```python
OUT = ROOT / "ai_trading_agents" / "trend_master_model.lgb"
...
model.save_model(str(OUT))
```

The trainer:

- Loads only `data/xauusd_m5_history.csv` (single-symbol)
- Uses 25-feature v1 `FEATURE_COLS` (no smartmoney/COT — incompatible with the v2-era 32-feature ecosystem)
- Produces calibrated probabilities so tightly clustered that pre-gate confidence is ~0.34 (1/3) across every symbol
- Hard-codes a write to the live path with no candidate / promotion gate

After the Phase B3 work landed (2026-04-26), the live model was supposed to be the 20 MB triple-barrier multi-symbol model. Whenever `train_v14_better.py` ran, it silently downgraded the live brain back to the 109 KB single-symbol V1 model, which fed misaligned features (25 vs 32) into a model that by design can't differentiate the inputs — every market collapsed to the prior.

We could not identify the actual trigger. The Pytest Health Check task fires at 09:05 daily, but `tests/conftest.py` and the test files do not save_model. No scheduled task or cron job calls `train_v14_better.py`. Most likely Sumit was running it manually on a morning/evening retrain habit, possibly via `outputs/retrain_run.bat` which still exists in the worktree. Either way, the file structure permitted accidental overwrite of live.

## Compounding factor

`tools/diagnose_zero_trades.py` correctly detected MODEL_UNIFORM each time but had no auto-remediation. `tools/zero_trades_watchdog.py` logged `[MODEL_STUCK]` to its log but the alert pipeline (Telegram) is intentionally disabled per operator policy, so the alert reached only `logs/`. Watch-pets did not surface MODEL_UNIFORM as a check because that's a brain-internal signal, not an OS/disk/PID signal.

## Detection

```cmd
.venv\Scripts\python.exe tools\diagnose_zero_trades.py
```

Verdict line `MODEL_UNIFORM` with `conf std<0.05` is the diagnostic. Compare to the operator invariant in CLAUDE.md: "Brain must produce real (non-uniform) confidence distribution. If std<0.05 across 18 markets, the model is broken."

## Fix

1. Renamed the live broken model to `trend_master_model.lgb.broken_uniform_again_2026-04-29_223343` so the brain boots in rule-only mode (`model=rule`).
2. `taskkill /F /IM python.exe` (old PID 26444 had the broken booster loaded in memory; rename alone isn't enough).
3. `start_brain_clean.cmd` → restart#45, PID 2960, `infer_rule` active.
4. Verified with `diagnose_zero_trades.py` → verdict OK, 4 BUY (GBPJPY, USDCHF, USDJPY, CADJPY) + 2 SELL (EURUSD, XNGUSD) within seconds, conf mean 0.78 std 0.085.
5. **Hardened `tools/train_v14_better.py`** so it can no longer overwrite live. Output path changed from `trend_master_model.lgb` to `trend_master_model_v14_better_candidate.lgb`; the script prints an explicit promotion-required notice referencing this postmortem.
6. **Three scheduled tasks reconfigured** (separate but found in the same audit pass):
   - `TrendMaster Code Graph Rebuild` — Daily → repeat every 30 min (matches expected interval in `tools/schtasks_audit.py`).
   - `TrendMaster Events Rotator` — Daily → repeat every 60 min.
   - `tools/hidden_brain_liveness.vbs` — removed `--quiet-on-alive` flag so the heartbeat log mtime refreshes every tick (watch-pets reads mtime as freshness signal, was perpetually flagging "stale 4527s" while the task was actually running fine).

## Prevention

- `train_v14_better.py` now writes to a candidate path. Even if it fires accidentally, live model is untouched.
- All future model promotions must go through `tools/enable_phase_b3_ml.py` (which backs up the current live model and prints diagnose verdict before/after).
- This postmortem is referenced from a comment block in `train_v14_better.py` so any future engineer who tries to "just point this at live again" sees the history.
- Consider adding a CI check / pre-commit hook that fails if any `tools/train_*.py` saves to `trend_master_model.lgb` without going through the promotion harness — not done in this fix to keep the change scope tight.

## Timeline (IST)

- 2026-04-22 09:58 — last live deal (ETHUSD -$0.69). Trading silently stops shortly after due to recurring overwrites.
- 2026-04-26 — Phase B3 landed (32-feature triple-barrier model). Live model becomes the proper 20 MB B3 model.
- 2026-04-27 09:05 — first observed V1 overwrite.
- 2026-04-28 13:30 — operator manually disabled the V1 model (renamed to `*.weak_v1_backup_2026-04-28`) and promoted B3 → live.
- 2026-04-28 ~14:00 — B3 itself disabled (max calibrated prob too tight for `min_ml_confidence: 0.70`); brain switches to rule-only mode.
- 2026-04-29 09:05 — V1 trainer fires again; live `.lgb` is back to 109 KB uniform.
- 2026-04-29 19:05 — V1 trainer fires again; same broken file restored to live.
- 2026-04-29 22:33 IST — operator notices zero trades, this debug session begins.
- 2026-04-29 22:33 — broken model archived; brain killed.
- 2026-04-29 22:53 — fresh brain online (restart#45, model=rule), real signals firing within seconds.
- 2026-04-30 01:08 — `train_v14_better.py` patched to candidate path. Postmortem written.

## Related

- `docs/POSTMORTEMS/2026-04-24_zero_trades.md` — original 47-day silent failure (feature-order mismatch, fixed by `ml_align.py`)
- `docs/POSTMORTEMS/2026-04-28_orphaned_d2_model_and_dead_market_lockout.md` — the orphaned 34-feature trial that preceded this incident
- `docs/POSTMORTEMS/2026-04-29_brain_silent_termination.md` — sibling incident from same day
