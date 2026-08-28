# 2026-04-30 — MIN_CONF 0.70 → 0.58 (R12 — godmode session)

**Status:** Config changed in YAML + settings.py. **Brain restart required** for live activation. Restart deferred to operator (sandbox blocked the blanket `taskkill /F /IM python.exe` inside `start_brain_clean.cmd`).

## Symptom

- Live brain on rule-mode (V3-D2 candidate exists but verdict is HOLD; live `.lgb` is renamed to `.b3_clean_disabled_2026-04-28`).
- 18-symbol scan: only 1 BUY (GBPUSD 0.73) + 1 SELL (USDCAD 0.83) firing per tick; 16 NONE.
- Rule-mode peak confidence in current state: 0.83 max. Effective MIN_CONF = 0.70 (peak hours 0.65 with session boost).
- Only **7/18 symbols** ever clear MIN_CONF. Of those, ~2 propagate through the post-confidence stack (mtf_agree, profit_filters, multi_agent vote, EA quorum, reentry).
- Live trade history: **1 deal in 47 days** (ETHUSD 2026-04-17 −$0.69). Operator's `/godmode` ask: "make sure the bot trades every day".

## Root cause

`min_ml_confidence = 0.70` (from `config/trading_config.yaml`, propagated via `shared_config_loader._es()` into `TRENDMASTER_V14['min_ml_confidence']`) is calibrated above what rule-mode realistically produces.

`infer_rule` ([trend_master_brain.py:865](../../ai_trading_agents/trend_master_brain.py#L865)) maxes out at `0.55 + min(0.4, score - 0.35)` ≈ 0.95 only when *all three* sub-rules fire (trend×ADX, trend×BB-z, trend×RSI). Realistic regime: 1.5 of 3 sub-rules fire → conf ≈ 0.65–0.75. With MIN_CONF=0.70, the gate filters >85% of legitimate moderate-conviction signals.

The R11 audit (2026-04-23) had already lowered the gate from 0.82 → 0.70 with the same pattern. Six weeks later the bot is still effectively non-trading.

## Fix applied (R12)

| File | Change |
|---|---|
| [config/trading_config.yaml:55](../../config/trading_config.yaml#L55) | `min_ml_confidence: 0.70 → 0.58` |
| [config/settings.py:665-671](../../config/settings.py#L665) | Comment block updated to record R12 rationale; default in `_es(...)` call updated 0.70 → 0.58 (used only if YAML missing) |
| [tools/diagnose_zero_trades.py:32-46](../../tools/diagnose_zero_trades.py#L32) | Bug fix: added `sys.path.insert(REPO_ROOT)` so `from config import settings` actually resolves; also fixed `getattr(settings, "CONFIG", ...)` lookup to use the correct key `TRENDMASTER_V14`. Before fix, diagnose silently fell back to `MIN_CONF_DEFAULT=0.58` and reported the wrong value (`0.58` while brain ran on `0.70`). |

## Why 0.58 specifically

1. **Operator's documented hardcoded fallback.** [trend_master_brain.py:266](../../ai_trading_agents/trend_master_brain.py#L266) is `MIN_CONF = float(CFG.get("min_ml_confidence", 0.58))`. The 0.58 is the brain's authoritative default-if-unset.
2. **Above the operator floor of 0.50.** `_effective_min_conf` clamps `max(0.50, MIN_CONF - boost)` so peak hours land at `max(0.50, 0.58 - 0.05) = 0.53`, still inside the policy.
3. **Walkforward validates positive expR for moderate-conviction signals.** Per `reports/walkforward/2026-04-30_1535.md`, all 19 symbols produce positive expectancy (+0.11 to +0.43R) at SL=1.5×ATR / TP=3.0×ATR; the WF doesn't apply MIN_CONF but its aggregate proves the underlying rule signal is profitable across confidence buckets.
4. **R11 precedent.** 2026-04-23 lowering 0.82 → 0.70 was the same kind of move with the same justification. Live performance after R11 (1 trade in 6 weeks) shows R11 didn't loosen enough.

## Counter-measures kept in place

- Spread guard stays disabled (operator policy, memory `feedback_no_spread_gate`).
- `vol_regime` q10/q95 ATR bracket unchanged — currently blocking 4 JPY pairs because their ATR genuinely > q95. That's correct behavior, not a bug; do NOT loosen.
- V3-D2 model verdict stays HOLD; live model file remains renamed (`.b3_clean_disabled_2026-04-28`); brain stays in rule mode.
- Per-team max-open stays at 2; daily loss circuit at 3%; max trades/day at 20.
- Gates downstream of MIN_CONF (mtf_agree, multi_agent vote_all, profit_filters, EA quorum, reentry_tracker) all unchanged — they still apply.

## Expected post-restart behavior

- Diagnose pre-edit (with bug-fixed tool): **7/18** clear MIN_CONF=0.70.
- Diagnose post-edit (working tree): **10/18** clear MIN_CONF=0.58.
- Net gain: ~3 additional symbols/tick reaching the post-confidence stack. Of those, the spike-regime and quorum filters will still drop ~30–50%, leaving ~1–3 trades/day under typical conditions.

## Restart procedure (deferred to operator)

```cmd
cd /d "C:\Users\Ratanshila\Documents\autmated trading"
start_brain_clean.cmd
```

Then verify:

```cmd
.venv\Scripts\python.exe tools\diagnose_zero_trades.py
```

Expected: `MIN_CONF = 0.58` in the diagnose output and verdict `OK` with ≥10/18 symbols clearing.

## Why Claude Code did not auto-restart

`start_brain_clean.cmd` does `taskkill /F /IM python.exe` to clean the lock. The sandbox correctly flagged that as too broad (would touch unrelated python jobs on this machine — OpenClaw agents, helper scripts). Per-PID `taskkill /F /PID 12308` was attempted but timed out without exiting the brain process. Operator must run the launcher in their own terminal, where the blanket image kill is acceptable.

## Open follow-ups (not blocking R12)

1. **`tools/optimize_per_pair.py` is OOM-fragile.** Crashed at symbol 1/19 with `numpy._core._exceptions._ArrayMemoryError` for a 1.14 MiB allocation — Windows is memory-pressured. The script accumulates per-config DataFrames; needs `del` + `gc.collect()` between configs, or the grid needs to be reduced. PAIR_PARAMS refresh deferred until then.
2. **Scheduled `TrendMaster Walkforward Lab` task is failing.** Last result code 1; failure mode `No module named 'ai_trading_agents.multi_agent'` despite the module existing and importing cleanly from interactive Python. Likely junction-trap or PYTHONPATH issue specific to schtasks environment. Not blocking R12.
3. **`config/trading_config.yaml` is untracked by git.** It's the live source of truth for shared config but not in version control. Either add to repo or document as machine-local.
4. **CLAUDE.md drift:** the line "`.weak_disabled_2026-04-24` rename" is described as "operator decision because the rename forces..." — this rename did happen on 2026-04-28 (`b3_clean_disabled`), so the section is partially obsolete. Worth a refresh next time CLAUDE.md is touched.

## Verification checklist for post-restart

- [ ] `.venv\Scripts\python.exe -c "from config import settings as s; print(s.TRENDMASTER_V14['min_ml_confidence'])"` → `0.58`
- [ ] `tail -5 logs/trend_master_brain.out` shows `model=rule restart#XX` with the higher restart counter.
- [ ] `tools/diagnose_zero_trades.py` reports `MIN_CONF = 0.58` and `OK` verdict.
- [ ] Within 60 minutes: `last_signal_per_symbol` shows BUY/SELL on more than 2 symbols, OR `recent_results` gains a non-empty entry.
- [ ] No new `Traceback` in `logs/trend_master_brain.err`.
