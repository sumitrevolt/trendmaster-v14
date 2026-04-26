# Phase B2-research — Walkforward v1 vs v2 (LIVE DATA)

**Verdict (overall): RESEARCH MORE**

**Date:** 2026-04-26
**Author:** Claude (research subagent, 2nd run)
**Run mode:** Live CFTC data via the Phase B1.5 fetcher; no EIA NG data (EIA_API_KEY env var unset on this host — `ng_storage_delta_z` is all-NaN and dropped from training in the v2 run, see Caveat #1).
**Inputs:** `data/<symbol>_m5_history.csv` (19 symbols, ~50k bars each, 2025-08-07 → 2026-04-23) → resampled to H1.
**Feature sets:** v1 = 25 cols (current FEATURE_COLS) | v2 = 32 cols active (25 + 7 CFTC COT spec_delta_z; ng_storage_delta_z column listed in FEATURE_COLS_V2 but excluded as all-NaN at run time)
**Walk-forward:** 5 purged folds, 12-bar purge gap, triple-barrier labels (TP=2R, SL=1R, hold=12 H1 bars), seed=42, deterministic LightGBM.

---

## 1. Headline

| Metric | v1 | v2 | Delta (v2 minus v1) |
|---|---:|---:|---:|
| Symbols ok | 19 | 19 | 0 |
| Mean expectancy_R | +0.319 | +0.308 | **-0.011** |
| Mean OOS purged-CV acc | 0.420 | 0.420 | -0.001 |
| Symbols where v2 >= v1 expR | -- | -- | **11/19 (58%)** |
| Strongest gain | -- | -- | **ETHUSD +0.065** |
| Largest regression | -- | -- | **AUDUSD -0.092** |

**Overall verdict thresholds:** PROMOTE iff mean dexpR >= +0.05 AND >=60% improved AND mean dacc >= +0.005. None of the three pass: mean dexpR = -0.011, 58% improved, mean dacc = -0.001. Verdict: **RESEARCH MORE.**

---

## 2. Per-symbol comparison

| Symbol | Team | v1 expR | v2 expR | dexpR | v1 OOS acc | v2 OOS acc | dacc | v1 WR | v2 WR | Notes |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| XAUUSD | METALS | +0.467 | +0.399 | **-0.068** | 0.420 | 0.411 | -0.009 | 35.3% | 33.2% | regression |
| XAGUSD | METALS | +0.263 | +0.265 | +0.002 | 0.407 | 0.406 | -0.001 | 29.8% | 29.6% | flat |
| EURUSD | FOREX | +0.285 | +0.237 | -0.048 | 0.446 | 0.436 | -0.009 | 27.9% | 25.9% | regression |
| GBPUSD | FOREX | +0.220 | +0.159 | -0.061 | 0.454 | 0.430 | -0.024 | 26.4% | 24.3% | regression |
| AUDUSD | FOREX | +0.304 | +0.212 | **-0.092** | 0.411 | 0.386 | -0.025 | 28.8% | 25.3% | worst |
| NZDUSD | FOREX | +0.187 | +0.111 | -0.076 | 0.402 | 0.382 | -0.019 | 25.1% | 22.7% | regression |
| USDJPY | FOREX | +0.380 | +0.394 | +0.014 | 0.420 | 0.416 | -0.004 | 32.7% | 32.8% | small gain |
| USDCAD | FOREX | +0.276 | +0.340 | +0.064 | 0.471 | 0.475 | +0.004 | 28.3% | 30.5% | gain |
| USDCHF | FOREX | +0.309 | +0.337 | +0.028 | 0.454 | 0.472 | +0.017 | 29.0% | 30.6% | gain |
| EURJPY | FOREX | +0.366 | +0.304 | -0.062 | 0.411 | 0.407 | -0.004 | 32.4% | 30.5% | regression |
| GBPJPY | FOREX | +0.334 | +0.347 | +0.013 | 0.422 | 0.422 | -0.000 | 30.3% | 30.7% | small gain |
| AUDJPY | FOREX | +0.442 | +0.446 | +0.004 | 0.413 | 0.416 | +0.003 | 35.5% | 35.9% | flat |
| CADJPY | FOREX | +0.274 | +0.287 | +0.013 | 0.384 | 0.392 | +0.009 | 27.3% | 27.9% | small gain |
| EURGBP | FOREX | +0.424 | +0.479 | +0.056 | 0.506 | 0.512 | +0.005 | 34.8% | 36.7% | gain |
| BTCUSD | CRYPTO | +0.316 | +0.316 | -0.000 | 0.414 | 0.419 | +0.005 | 28.9% | 28.8% | flat |
| ETHUSD | CRYPTO | +0.247 | +0.312 | **+0.065** | 0.386 | 0.405 | +0.019 | 27.1% | 29.3% | best |
| XTIUSD | COMMODITIES | +0.285 | +0.211 | -0.074 | 0.424 | 0.418 | -0.006 | 29.3% | 26.9% | regression |
| XBRUSD | COMMODITIES | +0.314 | +0.326 | +0.013 | 0.422 | 0.430 | +0.008 | 31.8% | 32.6% | small gain |
| XNGUSD | COMMODITIES | +0.326 | +0.328 | +0.001 | 0.344 | 0.356 | +0.012 | 30.8% | 31.4% | flat (no NG data) |

---

## 3. Per-team verdicts

| Team | n | mean dexpR | mean dacc | pct improved | Verdict |
|---|---:|---:|---:|---:|---|
| FOREX | 12 | -0.012 | -0.004 | 58.3% (7/12) | **RESEARCH MORE** |
| METALS | 2 | -0.033 | -0.005 | 50% (1/2) | **DROP** (XAUUSD regressed -0.068, XAGUSD flat) |
| CRYPTO | 2 | +0.033 | +0.012 | 50% (1/2) | **RESEARCH MORE** (ETHUSD strong gain, BTCUSD flat) |
| COMMODITIES | 3 | -0.020 | +0.005 | 67% (2/3) | **RESEARCH MORE** (XTIUSD regression dominates the mean) |

(Per-team thresholds reuse the global rule: PROMOTE if mean dexpR >= +0.05 AND >=60% improved AND mean dacc >= +0.005; DROP if mean dexpR <= -0.02; otherwise RESEARCH MORE.)

---

## 4. Did the verdict change vs the prior synthetic-data run?

**Yes, in detail; same RESEARCH MORE headline.**

The prior synthetic-data run (cleared from `2026-04-26_v1_all.json` / `_v2_all.json` by this run) returned mean dexpR ~ 0 with no per-symbol pattern, because synthetic random feature columns have zero correlation with H1 returns by construction. The prior team verdicts therefore had no statistical content. With LIVE CFTC data:

- COT-relevant symbols where Phase A2 found EDGE-class signals: **GC -> XAUUSD regressed**, BTC -> BTCUSD flat, **6E -> EURUSD regressed**, **6J -> USDJPY +0.014 (small gain)**, 6C -> USDCAD +0.064 (gain), CL -> XTIUSD regressed -0.074. Phase A2's EDGE prior holds for USDCAD and USDJPY but does not hold for the strongest A2 signals (XAUUSD, EURUSD, BTCUSD).
- Symbols where Phase A2 had NO COT prior: ETHUSD's +0.065 gain is the strongest in the run. This is unexpected -- ETH is not a COT contract; the model is borrowing the BTC_spec_delta_z column. Treat as suggestive but not validated.
- METALS team verdict went from "no signal" (synthetic) to "actively worse" (real data). The XAUUSD regression is the single most important number to explain before any v2 wire-in.

---

## 5. Lessons from Phase B1.5

The Phase B1 -> B1.5 column-name bug is the structural reason the prior synthetic-data run produced flat-line results: the CFTC fetcher requested `m_money_positions_long_all` from the LEGACY endpoint, where that column doesn't exist. Phase B1's response was an empty record set; the production code path swallowed this silently because of the Socrata-default `$limit=5000` (which itself only reaches back ~36 weeks across the full 140-market dataset, before any column issue), and the walkforward then trained on z-scored zeros -- i.e. noise.

Phase B1.5 fixes three things in `cross_asset_join.py`:

1. **Column rename**: `m_money_*` -> `noncomm_*` to match the LEGACY endpoint's actual schema. Phase A2's correlation study used these exact columns to find the EDGE-class signals (see `reports/influencer_correlation_phaseA2_2026-04-26.md` section 2.1).
2. **Per-contract pagination via SoQL `$where`**: the fetcher now issues one query per contract code with `$where=upper(contract_market_name) like '%PATTERN%'` and `$limit=50000`. This matches Phase A2's working approach and reliably returns ~16 years (851 weekly rows) per flagship contract.
3. **CL contract pattern tightened**: dropped the bare `wti` substring (which matched `WTI-PHYSICAL - NEW YORK MERCANTILE EXCHANGE`, only 220 weekly rows from 2022) in favour of the canonical `crude oil, light sweet` pattern (which gives 16y of `CRUDE OIL, LIGHT SWEET - NEW YORK MERCANTILE EXCHANGE` history).

Live smoke after the fix:
- `fetch_cot_weekly(force_refresh=True)` returns shape (851, 7), index 2010-01-05 -> 2026-04-21, with finite z-score values from week 52 onward; BTC has more NaN warmup because the CME futures only launched in 2018.
- Cache parquet at `data/external/cot_weekly_cache.parquet` (~61 KB).
- EIA fetcher unchanged behaviour: with `EIA_API_KEY` not set, it raises `CrossAssetConfigError` per design. The walkforward handles this by adding `ng_storage_delta_z` as an all-NaN column and dropping it from training; reported in result notes.

---

## 6. Caveats for interpreting the verdict

1. **EIA NG storage_delta_z was unavailable for this run.** v2 effectively had +7 COT columns (not +8). XNGUSD's tiny dexpR (+0.001) is therefore a v1-vs-v1-with-COT-only result, not the full v2 hypothesis. The v2 verdict for COMMODITIES will need a re-run with `EIA_API_KEY` set to be conclusive on XNGUSD.
2. **History mismatch: COT covers 2010-2026; M5 CSVs only cover 2025-08-07 -> 2026-04-23.** The walkforward's `_resample_h1_for_ml` only sees ~263 days of price history; meanwhile the COT spec_delta_z has 16y of conditioning history but only ~38 weekly observations overlap with the price window. After H1 forward-fill that becomes ~6,400 H1 timestamps with non-NaN COT values, of which only ~4,100 survive feature/label dropna. The COT signal is being asked to explain the model's decisions on a much shorter window than the signal's natural cycle. This is plausibly why Phase A2's strongest priors (XAUUSD, EURUSD, BTCUSD) don't translate into v2 walkforward gains.
3. **Triple-barrier expectancy is in R-units; +0.30 to +0.45 R per trade is what you'd expect from a 27-35% WR with TP=2R/SL=1R geometry.** The absolute numbers are noisy in this regime; the RIGHT comparison is the v1-vs-v2 delta, not the levels.
4. **No Stage-2 sample-uniqueness weighting, no fractional differentiation, no Hurst regime gate.** Per CLAUDE.md "Where the alpha actually lives" sections 1-5, those upgrades likely matter more than COT features in isolation. v2's job here is just to tell us whether COT features add anything to the existing FEATURE_COLS contract; the answer is "marginally for some symbols, marginally negative for others."
5. **No statistical significance test applied.** The 11/19 improvement count is a coin-flip-with-edge, not a t-test. With 19 symbols x 5 folds and per-symbol expR noise of ~0.05R, dexpR < +/-0.05 is well within fold-to-fold sampling noise.
6. **A `feature_name` warning fires from sklearn during fold prediction.** This is the same class of warning as the production `ml_align` guard -- it indicates LightGBM was fitted with feature names but predict was called on a numpy array. Not load-bearing for the comparison but worth noting that `ml_align` would handle this in production.

---

## 7. Recommendation

- **Do NOT promote v2 to FEATURE_COLS in trend_master_brain.py** at this stage. The mean dexpR is mildly negative and the symbol where Phase A2 had the strongest prior (XAUUSD) regressed by the largest single-symbol margin (-0.068).
- **Do keep the `cross_asset_join.py` plumbing.** It now actually works, the cache is populated, and Phase B1.5's hotfix unblocks all subsequent feature R&D that wants COT data.
- **Re-run with `EIA_API_KEY` set** before drawing any conclusion about the NG signal in particular. That single re-run is the cheapest path to a final verdict on the COMMODITIES team.
- **Consider an A/B isolation step:** run v2 with ONLY the COT columns where Phase A2's correlation was strongest (BTC/GC/6J), and see whether the noise from the weaker columns (6C, 6E, CL) is what drags the team mean down. The current v2 fires all 7 columns at every model.
- **Park the Phase B2-deploy commit** until at least (a) `EIA_API_KEY` is set on the research host, (b) a +EDGE COT-only sub-experiment lands dexpR >= +0.05 on at least 2 of {METALS, FOREX, COMMODITIES}.

---

## 8. Artifacts produced by this run

- `reports/walkforward/2026-04-26_v1_all.json` -- 19-symbol v1 results (real data; runtime 70s)
- `reports/walkforward/2026-04-26_v2_all.json` -- 19-symbol v2 results (real data; runtime 70s)
- `reports/walkforward/2026-04-26_v1_all.md` and `2026-04-26_v2_all.md` -- per-feature-set tables
- `reports/walkforward/2026-04-26_v1_<SYMBOL>.json` x 19 and `_v2_<SYMBOL>.json` x 19 -- per-symbol detail
- `data/external/cot_weekly_cache.parquet` -- fresh COT cache populated by the live smoke test (851 weekly rows, 7 contracts, 2010-2026)

The synthetic-data run from earlier today is overwritten by these files.
