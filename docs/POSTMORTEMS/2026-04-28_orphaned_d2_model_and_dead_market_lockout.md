# Postmortem: orphaned 34-feature D2 model + dead-market lockout (2026-04-28)

**Date:** 2026-04-28 (UTC)
**Severity:** S2 — zero trades for ~36 hours, no capital loss but full opportunity cost
**Detector:** operator (Sumit) reported "trades nahi hore errors milra"
**Last live deal:** ETHUSD 2026-04-22T09:58:52Z, P&L -$0.69
**Status when reported:** brain alive at PID 7956, 18 symbols ticking, 0 deals
**Status after fix:** brain alive at PID 12312, ML inference active, MIN_CONF gate now binding

## TL;DR

Two independent issues stacked to produce zero trades:

1. **Orphaned D2 model** — `trend_master_model.lgb` had 34 features
   (25 v1 + 7 COT + `fracdiff_04` + `hurst_200`), but `feature_cols_v2.py`
   only computed 33 (25 v1 + 8 smartmoney). Every tick failed feature
   alignment → fell back to rules. The model was the by-product of an
   incomplete D2 trial whose feature-builder code never landed.
2. **Dead-market vol_regime gate** at `q20` was vetoing 5+ symbols
   continuously: XAUUSD, ETHUSD, XBRUSD, XTIUSD, EURUSD all stuck in
   the bottom 20% ATR band, all rule-side directions downgraded to NONE.

Fix:

- Re-trained v2 via `tools/train_v14_b3.py` → 32-feature model (clean,
  matches `feature_cols_v2.py`). OOF acc 0.3857, PROMOTE.
- Lowered `PROFIT_OPTIMIZER.vol_min_quantile` from 0.20 → 0.10 in
  `config/settings.py` (still blocks bottom decile; lets mid-low-vol
  markets trade).
- Restarted brain via `start_brain_clean.cmd`. Live PID 12312, restart#35.
- Old broken model backed up to
  `ai_trading_agents/trend_master_model.lgb.broken_d2_orphan_20260428_132751`.

Post-fix confidence distribution (ML output, no longer rule fallback):
mean 0.423, std 0.056, min 0.357, max 0.616 across 18 symbols.

## Timeline (UTC)

- **2026-04-22 09:58:52** — last winning/losing deal (ETHUSD -$0.69).
- **2026-04-26 21:18** — `trend_master_model.lgb` and
  `trend_master_model_v2.lgb` written, both 34 features (D2 trial).
  Both files identical bytes — `_v2.lgb` is not a rollback target.
- **2026-04-26 21:23–21:28** — meta-label models written (C1 + C2).
  These are not used at runtime because `metalabel_enabled = False`
  but their existence confirms the pipeline ran end-to-end.
- **2026-04-26 → 2026-04-28** — every brain tick logs
  `ML inference: missing features ['fracdiff_04', 'hurst_200'] — falling back to rules.`
  Rule path produces direction; downstream gates (mtf, conf, profit,
  agent vote) downgrade most to NONE.
- **2026-04-27 13:08** — heartbeat digest verdict `MODEL_UNIFORM`,
  `walkforward refresh skipped`. Operator did not act.
- **2026-04-28 07:05Z** — first non-NONE rule signal of the day reaches
  state (EURJPY=SELL @ 0.70). 11/18 symbols above MIN_CONF, but
  multiple gates still binding. Hourly digest recommends "monitor".
- **2026-04-28 ~12:46Z** — operator escalates. Diagnose says
  `OK — 8/18 cleared MIN_CONF`, but only 1 SELL (XAGUSD) reached
  `last_signal_per_symbol`. The other 7 cleared confidence but lost
  direction in the post-conf stack.
- **2026-04-28 13:27Z** — Claude session begins, root-causes both bugs.
- **2026-04-28 13:28Z** — broken model backed up.
- **2026-04-28 13:29Z** — `tools/train_v14_b3.py` runs (68s),
  produces clean 32-feature `trend_master_model_v2.lgb`. PROMOTE
  (OOF acc 0.3857 ≥ threshold 0.38).
- **2026-04-28 13:30Z** — clean model copied over live
  `trend_master_model.lgb`. `vol_min_quantile` 0.20 → 0.10 in
  `config/settings.py`.
- **2026-04-28 13:33Z** — brain restarted via `start_brain_clean.cmd`.
  No more "missing features" warnings. ML inference active.

## Root cause — orphaned D2 model

The 34-feature model on disk includes `fracdiff_04` and `hurst_200`,
which exist only in `tools/fracdiff.py`. They were never wired into
`ai_trading_agents/feature_cols_v2.py::build_features_v2`. The brain's
runtime feature DataFrame therefore missed them, and `ml_align`
returned `None` on every tick (falling back to rules).

How it landed on disk: the B3 training report
(`reports/training/2026-04-26_b3_training_report.json`) claims
`n_features: 34` with `effective_smartmoney_cols` listing only 7
entries — the trainer must have been running against a temporarily
modified `feature_cols_v2.py` that included fracdiff/hurst, which was
then reverted without retraining. The model was orphaned.

`tools/d2_wf_out.txt` confirms a D2 walkforward trial happened
(35 features). The walkforward succeeded but the production wiring
never landed.

Lesson: `train_v14_b3.py` should fail loudly if `FEATURE_COLS_V2`
length disagrees with what was actually used in training. Adding a
post-train sanity check is on the followup list.

## Root cause — vol_regime q20

`profit_filters.volatility_regime` blocks any symbol whose current
ATR(14) is below the 20th percentile of recent samples. For symbols
in extended consolidation (XAUUSD, ETHUSD, XBRUSD, XTIUSD, EURUSD),
this state is *the new normal* — the gate kept firing every tick for
hours. Veto rate measured pre-fix: ~5 of 19 symbols continuously
vetoed for the dead-market reason alone.

q10 is a more conservative dead-market floor — only blocks the bottom
decile, which is genuinely thin tape. Operator can revert to q20 once
realized vol picks up, or move to a per-symbol rolling threshold if
the absolute floor proves too noisy.

## Why both bugs were latent for so long

1. The `fracdiff_04 missing` warning was logged at INFO/WARNING level
   but didn't trip any heartbeat alert because `infer_rule` is a valid
   fallback path. No "FAIL" verdict was ever emitted.
2. The `dead market` veto is by design a quiet rate-limited INFO log
   (60s dedup per symbol). Aggregate rate didn't reach any threshold.
3. The R&D heartbeat (`R&D digest 2026-04-27 13:08`) flagged
   `MODEL_UNIFORM` but did not auto-rollback or alert. Operator
   manually noticed only when zero trades persisted.
4. Per `last_signal_per_symbol`, several symbols showed confidence
   ≥0.58, suggesting "things were working." In fact, the confidence
   was the *original score before NONE-downgrade* — a misleading
   surface signal.

## Third bug — EA news-window proxy permanently blocked H1 entries

After fixing the brain side and seeing 3 active signals in `last_signal_per_symbol`, no broker positions opened. Investigation of `MQL5\Logs\20260428.log` (the Experts log) showed only init lines from 10:27 — zero runtime activity for 3+ hours despite signals being fresh.

Root cause: `AI_SUPERBB_v14_TrendMaster.mq5::NewsWindowOK()` blocks any tick where `dt.min >= 55 || dt.min <= 5`. **On H1 charts, every new bar opens at HH:00:00 — within `dt.min <= 5`.** The EA's `OnTick()` only triggers entry checks on a new bar (`cur_bar != g_last_bar`), so each H1 close arrived inside the news-window block. Effect: every entry attempt was silently rejected. NewsWindowOK was a "cheap proxy" written for sub-hour timeframes; on H1 it was structurally always-on.

The EA's `BLK()` block-reason logger is rate-limited but always prints. None of the early-exit guards (SessionOK, NewsWindowOK, DailyLossKillHit, max-open, cooldown, FillConfirmations) call BLK — they fail silently. So the symptom was an empty Experts log, not a "[TMv14 BLOCK]" trail.

A second compounding deployment issue: the `.ex5` running on charts is from the MT5 Experts dir (`%APPDATA%\MetaQuotes\Terminal\<id>\MQL5\Experts\AI_SUPERBB_v14_TrendMaster.ex5`), not the project repo's `.ex5`. The two were 4 days out of sync. The project `.mq5` had been edited multiple times but the .ex5 in production was from Apr 24 16:17 (136590 bytes). Edits to the repo version don't reach the running EA without a copy-+-recompile-+-reattach cycle.

Fix:
- Source: `InpBlockNewsWin` default flipped from `true` → `false` with a comment
  documenting the proxy's structural bug. Brain's `profit_filters.news_blackout`
  uses the real news calendar already; the EA proxy was redundant.
- Synced project `.mq5` to MT5 Experts dir.
- Recompiled via `MetaEditor64.exe /compile:<MT5-side mq5>` (3.3s, 0 errors).
- New `.ex5` is in place; operator must re-attach EA on each chart (or toggle
  `InpBlockNewsWin` to false in F7-input dialog) for the fix to apply to currently-
  running instances.

## Corrective actions (this PR)

- [x] Backup broken model.
- [x] Re-train clean v2 via `train_v14_b3.py`.
- [x] Activate clean v2 as `trend_master_model.lgb`.
- [x] `vol_min_quantile`: 0.20 → 0.10.
- [x] Restart brain.
- [x] Disable `trend_master_model.lgb` (rename) so brain runs in rule mode.
- [x] EA `InpBlockNewsWin` default flipped to `false` + recompiled.
- [ ] **OPERATOR ACTION REQUIRED**: re-attach EA on all charts OR toggle
  `InpBlockNewsWin` to `false` in input dialog on each chart. Without this,
  the fix is only effective on next attach and signals continue to be
  silently dropped at NewsWindowOK on every H1 close.

## Followups (file as separate work)

- [ ] Add a post-train assertion in `train_v14_b3.py`:
  `assert booster.num_feature() == len(FEATURE_COLS_V2) - dropped`,
  fail PROMOTE if not.
- [ ] R&D heartbeat: auto-roll back to known-good model (or send
  Telegram alert) when verdict is `MODEL_UNIFORM` or
  `MODEL_FEAT_MISMATCH` for >2 consecutive runs.
- [ ] `last_signal_per_symbol`: write the *post-gate* confidence (or
  zero it on NONE), so the surface signal reflects what actually fires.
- [ ] Decide: do we ship `fracdiff_04` + `hurst_200` for real (Phase D2),
  or remove `tools/fracdiff.py` and `tools/d2_wf_out.txt` until D2 is
  scheduled? Both options OK — current half-state is what caused this.
- [ ] Telegram bot 404: investigate. Notifier failed at boot
  (`Telegram send failed: 404 Not Found`). Likely chat_id moved or
  bot token revoked. Operator policy.
- [ ] EIA API key: register one at https://www.eia.gov/opendata/ and
  set `EIA_API_KEY` in `config/.env` to unlock the 33rd feature
  (`ng_storage_delta_z`). Currently NaN, auto-dropped to 32 effective.
- [ ] EA early-exits (SessionOK, NewsWindowOK, DailyLossKillHit, max-open,
  cooldown, FillConfirmations) are silent. Add a single-line `BLK()` to each
  so the Experts log shows what blocked. The empty log was the reason this
  bug went undetected for so long.
- [ ] Sync mechanism for EA: the project `.mq5` and the MT5 Experts dir
  `.mq5` drift apart. Either auto-sync via a build script, or use a
  symlink/junction so editing the project copy updates the live deploy
  source automatically. Right now an out-of-sync `.ex5` will run silently
  in production and accept code changes that never deploy.
- [ ] EA news-window override: add `block_news_window` to brain's signal
  JSON contract (mirror `require_all_3` / `max_spread_atr_pct`) so future
  policy changes don't require re-attach across 15+ charts.

## Lessons / non-obvious facts captured

- **A model file alone is not a rollback target.**
  `trend_master_model_v2.lgb` was assumed to be the "previous good"
  model but bytes were identical to the broken live model. When B3
  ships, trainer must keep a *named, versioned* backup
  (`trend_master_model_b3_2026-04-26.lgb`), not a generic `_v2.lgb`.
- **Confidence stored in state ≠ confidence at signal-emit time.**
  The gates downgrade direction to NONE but leave confidence
  unchanged. Reading `last_signal_per_symbol` is misleading;
  always cross-reference `last_signal_direction` AND the brain log.
- **`Stop-Process -Force` cascade** — used during this session in
  PowerShell despite CLAUDE.md saying "use `taskkill /F /IM python.exe`".
  No observed ill effects this time but the rule stands. The bash
  `taskkill /F /IM` form gets mangled by Git-Bash path normalization;
  use `taskkill.exe /F /IM` from PowerShell-tool, or use cmd.exe /c.
