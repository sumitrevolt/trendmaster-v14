# Phase D2 — ML edge improvement (parallel R&D track)

_Queued 2026-05-01 alongside the Concentrated live config switch._

## Why this exists

The rule-based brain has a real but capped edge — walkforward on 50K M5 bars
shows aggregate WR 33.0%, expR +0.302R across 19 symbols (141K trades). That's
inside the literature ceiling of 38-42% for 3-class direction prediction, and
matches a 2:1 RR strategy almost exactly at breakeven.

**Risk-side levers (more risk per trade, more concentration) amplify dollar
returns proportionally but DON'T improve Sharpe.** The only lever that
genuinely lifts the edge curve is better features and better labels. That's
what D2 delivers.

This plan is a parallel R&D track — it does NOT touch live trading. The brain
keeps running on rules. D2 trains a CHALLENGER model in shadow mode; only
when it beats the production rules on out-of-sample data does it get promoted.

## What Phase D2 ships (in order)

### D2.1 — Fractional differentiation features (week 1-2)

**The problem:** Current `ret_*` features use integer differencing (close - close.shift(N)).
This destroys ~99% of the long-memory information in the price series and
produces stationary-but-uninformative features. López de Prado AFML chapter 5
shows `frac_diff(d≈0.4)` keeps long memory while making the series stationary
enough for ML.

**What to build:**
- `ai_trading_agents/feature_frac_diff.py` — implement `frac_diff_FFD(series, d, thresh=1e-4)` using fixed-window FFD.
- Add 4 new features per symbol: `frac_diff_close_d04`, `frac_diff_close_d06`,
  `frac_diff_high_d04`, `frac_diff_low_d04`.
- Wire into `FEATURE_COLS_V3` (V2 + frac_diff features = 36 cols).

**Test:** ADF stationarity on each frac-diff series across all 19 symbols.
Reject if p-value > 0.05 (means the d value is too low — bump it).

### D2.2 — Hurst exponent (week 2)

**The problem:** Single global threshold for "trending vs reverting" misses
regime change at the symbol level. Hurst H exposes this directly per symbol per
window.

**What to build:**
- `ai_trading_agents/feature_hurst.py` — rolling Hurst exponent over 200-bar
  window using R/S analysis.
- Add 1 feature: `hurst_200`.
- Optional: `regime_label` ∈ {trending, mean_reverting, random_walk} from H>0.55, H<0.45, else.

**Test:** correlation of `hurst_200` with subsequent `expR` from triple-barrier
labels. Should be positive (H>0.5 → trend strategy outperforms).

### D2.3 — Triple-barrier retrain on V3 features (week 3-4)

**Now we have V3 = V2 (33) + frac_diff (4) + hurst (1) = 38 features.**

- Retrain `tools/train_v14_b3_v3.py` (clone of `train_v14_b3.py`).
- Use existing triple-barrier setup (TP=2×ATR, SL=1×ATR, hold=12 H1).
- Sample-weight by avg_uniqueness (D1 already shipped).
- Purged 5-fold walk-forward; promote threshold = OOF acc ≥ 0.40 (vs current
  V2 OOF acc 0.393).
- If OOF AUC > 0.55, also retrain meta-labeler (C1 + C2 cascade).

**Promote criteria:**
- V3 OOF acc ≥ 0.40 (3pp above V2)
- V3 expR (out-of-sample, 5-fold) ≥ +0.32R (5% above V2)
- No team regresses by more than 5pp expR vs V2

If promoted: copy `trend_master_model_v3.lgb` over `trend_master_model.lgb`,
flip `smartmoney_features_enabled` already True, restart brain. **No code
change to brain — it just picks up the new model on restart.**

### D2.4 — Live shadow validation (week 5-6)

Run V3 in shadow alongside production rules for 2 weeks. Compare:

- V3 signal direction vs rule signal direction (agreement rate).
- V3 confidence calibration: when V3 says >0.55, does live PnL match?
- Per-team signal volume: does V3 fire more or less than rules?

If shadow validates, FLIP gate `infer_ml_enabled = True` in
`config/settings.py`. Brain switches from `infer_rule` to `infer_ml` on next
restart. Keep `ml_align` guard active — if V3 ever produces uniform output
(std < 0.05), brain falls back to rules silently.

## What this is NOT

- **Not a return amplifier.** It improves the per-trade edge by maybe 20-40%
  (taking expR from 0.30 to 0.36-0.42). The only way to scale beyond that is
  more risk per trade or a fundamentally new strategy class (HMM-experts,
  PPO/SAC RL, foundation models like Kronos — Round 3 R&D).
- **Not a replacement for the rules.** Rules stay as fallback in `ml_align`
  guard. If the model ever drifts to MODEL_UNIFORM (std < 0.05), brain auto-
  reverts. We don't trust ML-only — we trust ML-with-rule-floor.
- **Not blocking the live config.** Concentrated mode (top-8, 0.5% risk) is
  active TODAY. D2 is a 4-6 week parallel investment. Live trading proceeds.

## Out-of-scope (deliberate)

- DXY/VIX/US10Y macro features (Phase D3). Need a free macro feed wired in.
- HMM-gated experts (Phase E1). Only after D2 retrain shows real edge lift.
- PPO/SAC RL. Too many degrees of freedom for live retail; deferred indefinitely.
- Foundation models (Kronos). Watching the literature.

## Tracking

- New issue: open one in `gh issue` repo `sumitrevolt/trendmaster-v14`
  with label `agent-task:researcher`. Researcher agent (Gemini) handles
  feature implementation; QA reviewer audits before any model promote.
- Weekly progress write-up: `docs/team/researcher/weekly_<date>.md`.
- Promote/reject decision: documented in `docs/POSTMORTEMS/` regardless
  of outcome (rejection learnings are also valuable).
