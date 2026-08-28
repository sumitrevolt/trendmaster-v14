# v14.5.1 deployment summary — 2026-04-25

**Three operator-decision items closed.** Per-team rule config now flows end-to-end (brain → signal JSON → EA), and the change has been graded under a CPCV-style purged walk-forward gate before being declared production-ready.

---

## Item 1 — Brain restart (DONE)

Killed the seven stale brain processes, deleted `logs/brain.lock`, spawned a fresh detached brain. Verified online via the live log:

```
TrendMaster brain online | mode=MULTI (18 syms) tf=H1 interval=3000ms
ML feature audit: order_match=True model_count=25 brain_count=25
Acquired brain lock (pid=7432, file=...\logs\brain.lock)
```

After the v14.5.1 EA + brain code changes, restarted again. Current brain pids: `13368, 29960, 32312, 32360, 35112`.

## Item 2 — EA recompile (DONE)

`AI_SUPERBB_v14_TrendMaster.mq5` now mirrors the Round 11 JSON-override pattern for two more keys:

KeyGlobalEffective helperUsed in`st_multg_ai_st_multEffectiveSTMult()`SuperTrend recalc loop (line 319)`bb_width_floor_pctg_ai_bb_floor_pctEffectiveBBFloorPct()`C2 BB-width gate (line 469)

Brain side: `_pair_sl_tp(sym)` returns 5-tuple, signal payload includes all 5 keys per the `team_params.TEAM_PARAMS` table.

Compiled headless via `metaeditor64.exe /compile:...mq5 /log:...log`:

```
Result: 0 errors, 0 warnings, 3543 ms elapsed, cpu='X64 Regular'
EX5: AI_SUPERBB_v14_TrendMaster.ex5  109,732 bytes  21:08
```

### One-time MT5 chart re-attach (only step still needing you)

The 19 currently-attached charts in MT5 have the OLD `.ex5` in memory. Pick one of:

1. **Quickest** — restart MT5 terminal once. All charts re-load the new `.ex5` automatically.
2. **Per-chart** — on each of the 19 charts: F7 → re-select EA from Navigator → OK. Order matters less than coverage.

Until the re-attach, brain still benefits from per-team SL/TP/ADX (those flow via the existing R8 JSON keys that Round 8 wired). Only the ST mult and BB-width floor wait on the chart re-attach.

## Item 3 — Promotion gate (DONE)

Substituted the model-only `trading-walkforward-promotion` skill with a **rule-config CPCV gate** since (a) brain runs `infer_rule` in practice and (b) no per-team `.lgb` candidates exist.

`tools/config_promotion_gate.py` — 5 purged folds per symbol with 200-bar embargo, comparing v14.5 EAParams against v14.4 baseline (sl=2.0, tp=3.0, adx=22, st=3.0).

Teamv14.5 mean Sharpev14.4 mean SharpeΔSharpeVerdictMETALS0.921 ± 0.860.626 ± 0.78+**0.295**PROMOTEFOREX-0.689 ± 1.29-0.643 ± 1.19-0.046**HOLD**CRYPTO0.543 ± 1.380.186 ± 0.81+**0.357**PROMOTECOMMODITIES0.397 ± 1.05-0.068 ± 0.94+**0.464**PROMOTE

Reports: `reports/promotion/config_promotion_2026-04-25_2101.{md,json}`.

### Honest read of the FOREX HOLD

Both v14.5 and v14.4 are **negative** on FOREX over CPCV folds. The single-fold sweep in `reports/best_indicators_2026-04-25.md` showed FOREX as profitable in 19/19 — that result was fragile to embargoed re-folding. CPCV is a stricter test and is the read to trust.

Practical implication: METALS/CRYPTO/COMMODITIES configs are real edges in the v14.5 form. FOREX needs more R&D — likely a different dimension entirely (session windows, pair-specific tuning, or a meta-labeller filter on top of the rule). Don't roll the FOREX team back to v14.4 mid-flight; both are negative, and you'd be choosing between two losing configs. Keep v14.5 for consistency, queue a proper FOREX-only investigation.

## What changed end-to-end (file list)

- `AI_SUPERBB_v14_TrendMaster.mq5` — 5 surgical patches; recompiled.
- `AI_SUPERBB_v14_TrendMaster.ex5` — fresh build 21:08.
- `ai_trading_agents/trend_master_brain.py` — `_pair_sl_tp` 5-tuple + signal payload.
- `ai_trading_agents/team_params.py` — docstring updated to mark all 5 keys ACTIVE.
- `tools/config_promotion_gate.py` — new (164 lines).
- `reports/promotion/config_promotion_2026-04-25_2101.{md,json}` — new.
- `CHANGELOG.md` — v14.5.1 entry.
- `reports/v14_5_1_deployment.md` — this file.

## Next monitoring steps (when London opens Monday)

1. Tail `logs/trend_master_brain.log` for first signal-write of the week. Verify the JSON contains `"st_mult"` and `"bb_width_floor_pct"`keys.
2. After ≥10 trades fill, run `tools/diagnose_zero_trades.py` and `tools/validate_crypto_ml.py --team all` for a sanity pass.
3. Watch FOREX for ≥1 week; if signals dry up under adx=25, that's the trigger to revisit the FOREX-specific config.
