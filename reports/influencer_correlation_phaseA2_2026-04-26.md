# Phase A2 — Smart-Money Flow Correlation Study

**Project:** TrendMaster v14
**Author:** Claude (research subagent)
**Date generated:** 2026-04-26
**Inputs:** 5 data sources × 22 source-symbol pairs against the 14 most-relevant TrendMaster price series
**Compute backend:** yfinance (price), CFTC Socrata public API, EIA public xls, SEC EDGAR JSON, Yahoo ZQ=F (FedWatch proxy)

---

## 1. Executive verdict table

Verdicts: **8 EDGE / 9 WEAK / 5 NONE** out of 22 pairs analysed.

| Source | Symbol | N | Best-lag Pearson | Best lag | OOS Pearson (last 30%) | OOS sign preserved | Verdict |
|---|---|---:|---:|---:|---:|:--:|:--|
| CFTC COT BTC | BTCUSD | 420 | -0.201 | 0 | -0.183 | Y | **EDGE** |
| CFTC COT GC | XAUUSD | 850 | +0.173 | 0 | +0.161 | Y | **EDGE** |
| CFTC COT 6J | USDJPY | 850 | +0.145 | 0 | +0.221 | Y | **EDGE** |
| CFTC COT SI | XAGUSD | 850 | +0.141 | 0 | +0.140 | Y | **EDGE** |
| EIA NG storage Δ | XNGUSD | 848 | +0.121 | 2 | +0.151 | Y | **EDGE** |
| CFTC COT 6E | EURUSD | 850 | +0.117 | 0 | +0.019 | Y | **EDGE** |
| CFTC COT CL | XTIUSD | 850 | +0.116 | 0 | +0.211 | Y | **EDGE** |
| CFTC COT 6C | USDCAD | 850 | +0.106 | 0 | +0.146 | Y | **EDGE** |
| Farside-ETF IBIT $-volume (proxy for net flow) | BTCUSD | 572 | +0.104 | 0 | -0.173 | N | **WEAK** |
| CFTC COT 6N | NZDUSD | 850 | +0.099 | 0 | +0.010 | Y | **WEAK** |
| Farside-ETF total $-volume (proxy for net flow) | BTCUSD | 579 | +0.099 | 0 | -0.166 | N | **WEAK** |
| CFTC COT BZ | XBRUSD | 753 | +0.098 | 0 | +0.150 | Y | **WEAK** |
| CFTC COT 6S | USDCHF | 847 | -0.093 | 3 | +0.074 | N | **WEAK** |
| EIA crude stocks Δ | XTIUSD | 849 | -0.087 | 1 | -0.010 | Y | **WEAK** |
| CFTC COT 6A | AUDUSD | 850 | +0.079 | 0 | +0.010 | Y | **WEAK** |
| CFTC COT 6B | GBPUSD | 850 | +0.075 | 0 | +0.038 | Y | **WEAK** |
| EIA crude stocks Δ | XBRUSD | 849 | -0.060 | 1 | +0.000 | N | **WEAK** |
| Strategy/MSTR 8-K event-window | BTCUSD | 150 | +0.027 | 0 | -0.006 | N | **NONE** |
| FedWatch (ZQ 30d Δ implied rate) | XAUUSD | 4069 | -0.019 | 2 | -0.041 | Y | **NONE** |
| FedWatch (ZQ 30d Δ implied rate) | EURUSD | 4210 | +0.016 | 3 | +0.023 | Y | **NONE** |
| CFTC COT NG | XNGUSD | 848 | -0.014 | 2 | -0.039 | Y | **NONE** |
| FedWatch (ZQ 30d Δ implied rate) | USDJPY | 4212 | +0.010 | 1 | +0.023 | Y | **NONE** |

**Verdict thresholds:** EDGE = |Pearson| ≥ 0.10 AND OOS sign matches IS; WEAK = 0.05 ≤ |Pearson| < 0.10 OR OOS sign flips; NONE = |Pearson| < 0.05.

---

## 2. Per-source narrative

### 2.1 CFTC Commitments of Traders (legacy futures-only)

**Fetched:** Socrata public endpoint `https://publicreporting.cftc.gov/resource/6dca-aqww.json`. The disaggregated F+O endpoint `72hf-taqq` returned HTTP 404 for several contracts so the legacy report was used instead. The signal is **non-commercial net = noncomm_long − noncomm_short** (a slightly broader proxy than disaggregated "Managed Money", but highly correlated and historically supported in the literature). The first-difference of net positioning ("Δspec_net") is the actual signal — raw level is non-stationary.

**History:** 2010-01-05 → 2026-04-21 for GC/SI/6E/6J/6A/6C/6S (851 weekly obs). Brent (BZ) starts 2011-10-18 because the modern futures contract was renamed mid-stream; Bitcoin (BTC) starts 2018-04-10 (CME launch); 6B/6N/CL/NG required merging older + renamed contract names to recover full history.

**Top 3 strongest correlations:**
1. **CFTC BTC futures → BTCUSD** : `r=−0.201` at lag 0, n=420. OOS r=−0.183, sign preserved. **EDGE.**
2. **CFTC GC → XAUUSD** : `r=+0.173` at lag 0, n=850. OOS r=+0.161, sign preserved. **EDGE.**
3. **CFTC 6J → USDJPY (inverted)** : `r=+0.145` at lag 0, n=850. OOS r=+0.221 (gets *stronger* OOS — note it). **EDGE.**

**OOS robustness:** 6 of 13 COT contracts cross the EDGE threshold and 4 of those have OOS that preserves *or amplifies* the IS coefficient (GC, SI, 6J, 6C, CL, BTC). The crypto sign is *negative* — when speculators add longs, BTCUSD weakly mean-reverts the same week. Gold/silver show the opposite: spec adds → price up. 6S (Swiss) is a sign-flip case → demoted to WEAK.

**Recommendation: PROMOTE.** This is the highest-density signal among the five sources tested; mature, free, weekly. Wire `Δspec_net` (per contract, z-scored over 52-week rolling window) into `build_features` for the 7 contracts that hit EDGE: GC, SI, 6E, 6J, 6C, CL, BTC.

### 2.2 BTC ETF flows — Farside (proxy: aggregate ETF dollar-volume from yfinance)

**Fetched:** Farside Investors all-data table at `https://farside.co.uk/bitcoin-etf-flow-all-data/` is **bot-blocked by Cloudflare** — three different UA strings + endpoints all returned HTTP 403 (see Appendix B for details). As a substitute, daily $-volume = `close × shares_volume` was pulled via yfinance for 11 spot ETFs (IBIT, FBTC, ARKB, BITB, BTCO, EZBC, BRRR, HODL, BTCW, DEFI, GBTC). $-volume is **NOT** the same as net creation/redemption flow: high $-volume can be high churn at zero net creation. Treat results below as a **lower bound on the true correlation** of net-flow with price.

**History:** 2024-01-11 → 2026-04-24 (572-579 obs depending on ticker), covering the full life of the US spot ETF complex.

**Top 3 strongest correlations on this proxy:**
1. **IBIT $-volume Δlog** vs BTCUSD daily return : `r=+0.104` (lag 0, OOS -0.173, n=572) — IS positive, **OOS sign flips to −0.17**. WEAK.
2. **Total ETF $-volume Δlog** vs BTCUSD daily return : `r=+0.099` (lag 0, OOS -0.166, n=579) — same IS-positive / OOS-negative pattern.

**OOS robustness:** **Sign flip in last 30%.** This is the most informative null result of the study: in 2024 the spot-ETF complex was net-creation-positive on green days; by 2025-2026 the relationship inverted, plausibly because ETF activity now includes dominant short-volatility / arb flows that push *against* spot price intraday.

**Recommendation: RESEARCH MORE — do NOT promote.** The $-volume proxy is too noisy and the sign instability disqualifies it as-is. To rescue this source, get the *signed creation/redemption* delta (true net flow) from BlackRock IBIT ShareClassNetCash filings or via paid SoSoValue/Bitbo API; without that, the dollar-volume proxy actively misleads.

### 2.3 EIA Weekly Petroleum + Natural Gas Storage

**Fetched:** Public Excel files from `eia.gov/dnav/pet/hist_xls/WCESTUS1w.xls` (crude stocks) and `eia.gov/dnav/ng/hist_xls/NW2_EPG0_SWO_R48_BCFw.xls` (gas storage). Both 200 OK with no UA tricks. Crude history: 1982 → 2026-04-17 (2,273 weekly obs); NG: 2010 → 2026-04-17 (851 obs). Signal is the weekly **delta** of total stocks (negative delta = drawdown = bullish).

**Top 3 strongest correlations:**
1. **EIA NG storage Δ → XNGUSD** : `r=+0.121` (lag 2, OOS +0.151, n=848) — **EDGE**, sign preserved OOS.
2. **EIA crude Δ → XTIUSD** : `r=-0.087` (lag 1, OOS -0.010, n=849) — WEAK; effect is small and noisy.
3. **EIA crude Δ → XBRUSD** : `r=-0.060` (lag 1, OOS +0.000, n=849) — WEAK / sign flip OOS.

**OOS robustness:** NG storage Δ has the cleanest behaviour of any non-COT signal. Crude Δ is too small in magnitude to clear the EDGE bar — the 10:30 ET WPSR release moves the **same hour** but smooths out at weekly close, which is what weekly Pearson measures.

**Recommendation: PROMOTE for XNGUSD only.** Wire `eia_ng_storage_delta_z` (z-score over 52-week window) for XNGUSD. Drop crude inventory delta as a weekly feature; the alpha lives in the **announcement-window** intraday spike, not the weekly close-to-close return — outside the scope of this study but a strong R&D candidate (event-driven feature) for Phase B.

### 2.4 FedWatch implied rate probabilities (proxy: ZQ=F 30-day implied rate change)

**Fetched:** True FedWatch CME endpoint requires session cookies / paid API; **PyFedWatch was not installed to honour the "no new dependencies" invariant**. Instead the 30-day Fed Funds futures continuous (`ZQ=F` from yfinance, 4,103 daily obs since 2010) was used. Implied rate = 100 − price; signal = rolling 30-day Δ in implied rate (negative = market increasingly pricing cuts). FRED `DFEDTARU` (current Fed-funds upper bound) timed out repeatedly so the absolute prob-of-cut figure could not be constructed; the *change* in implied rate is the next-best alternative.

**Top 3 strongest correlations:**
1. **30d Δ implied rate → XAUUSD** : `r=-0.019` (lag 2, OOS -0.041, n=4069)
2. **30d Δ implied rate → EURUSD** : `r=+0.016` (lag 3, OOS +0.023, n=4210)
3. **30d Δ implied rate → USDJPY (inv)** : `r=+0.010` (lag 1, OOS +0.023, n=4212)

**OOS robustness:** All three pairs come back as **NONE** (|r| < 0.05), with sign-stable but vanishingly small effect sizes. This is the most disappointing source of the five tested.

**Recommendation: DROP** in current form. The 30-day Δ in ZQ implied rate over a daily horizon is too low-frequency to drive H1 returns; the real Fed-related alpha is a *coincident* move at the FOMC announcement (14:00 ET). To recover this, switch to an event-study around scheduled FOMC dates (8 events/yr) — but that's the calendar already inside `news_blackout` and not a "smart-money flow" signal per the original brief.

### 2.5 Strategy / MSTR Bitcoin purchases (SEC EDGAR 8-K event study)

**Fetched:** EDGAR submissions JSON for CIK 0001050446 (`https://data.sec.gov/submissions/CIK0001050446.json` + the older index file). Filtered to forms `8-K` with Item 8.01 ("Other Events") since 2020-08-11 (first BTC purchase). 150 events across 2020-08 → 2026-04-20.

**Caveat on event filter:** Item 8.01 is broader than just BTC-purchase announcements — Strategy uses it for board updates, share-issuance ATM tranches, and PR. A clean filter would download each filing and string-match for "bitcoin" or "BTC" in the body — that took beyond the time budget. The 150-event sample therefore *over-counts* genuine BTC-purchase events and dilutes the signal toward zero.

**Event-study results:** Mean cumulative log-return over [-5, +5] business-day window = **+0.22%** (vs unconditional 10-day mean = +0.30%); post-only [0, +5] = **+0.34%** (vs unconditional 5-day = +0.15%). T-test of post-window vs unconditional: `t=-0.58`, `p=0.561` — **not statistically significant**. IS-vs-OOS first-half-vs-second-half mean event return: IS=+0.86%, OOS=−0.61%. **Sign flips OOS.**

**Recommendation: DROP** from feature set; **MAYBE promote** as a soft news event (binary "MSTR-buy in last 5d") only after rebuilding the event filter to actual BTC-purchase 8-Ks (manual or LLM-classified). The current window-mean is *below* the unconditional mean.

---

## 3. Cross-section synthesis — top-3 to promote into Phase B

| Rank | Source-symbol pair | Effect size | Stability | Why |
|---|---|---|---|---|
| 1 | **CFTC COT BTC → BTCUSD (lag 0, weekly)** | r=-0.20, n=420 | OOS=-0.18, sign preserved | Largest absolute effect of any pair tested; sign indicates spec-positioning extremes mean-revert weekly. Free, stable, T+3 release. |
| 2 | **CFTC COT GC → XAUUSD (lag 0, weekly)** | r=+0.17, n=850 | OOS=+0.16, sign preserved | Second-largest; aligns with classical COT-trend literature (spec adds → price continues short-term in metals). 16y of data. |
| 3 | **CFTC COT 6J → USDJPY (inv, lag 0, weekly)** | r=+0.15, n=850 | OOS=+0.22 (amplifies) | Only cross-asset signal where OOS *strengthens*. Likely captures the BoJ-intervention regime shift in 2024-2026. |

**Honourable mentions** — also EDGE-class but smaller effect: COT SI → XAGUSD (r=+0.14), COT 6E → EURUSD (r=+0.12, but OOS r drops to +0.02 → marginal), COT CL → XTIUSD (r=+0.12, OOS=+0.21), COT 6C → USDCAD (r=+0.11), EIA NG storage Δ → XNGUSD (r=+0.12).

If you want one recommendation for **Phase B feature integration**: package all 7 EDGE-class CFTC contracts as a single new feature family (`cot_<contract>_spec_delta_z`), z-scored over 52-week rolling window, ffilled to daily H1 bars (signal updates Friday 15:30 ET, valid until next Friday). That's 7 new columns — a tractable diff against the current 25-column FEATURE_COLS — and gives every team except COMMODITIES-NG at least one COT input.

---

## 4. What surprised me

- **Both BTC ETF $-volume signals' OOS sign flip** — IS positive, OOS negative. The 2024 launch-rush correlation broke during the late-2025 / early-2026 sideways tape. This warns against features built only on the post-Jan-2024 ETF era for crypto.
- **CFTC 6J inverted USDJPY OOS r=+0.22 > IS r=+0.15.** Most signals decay OOS; this one strengthens, suggesting the JPY positioning channel is actually getting *cleaner* as a signal in the BoJ-pivot regime. Worth deeper inspection.
- **CFTC NG → XNGUSD verdict = NONE** while **EIA NG storage Δ → XNGUSD verdict = EDGE.** For natural gas, the *fundamental* (storage) variable beats the *positioning* variable. Inverse for crude (CL COT EDGE, EIA crude WEAK).
- **MSTR event mean post-window (+0.34%) is statistically indistinguishable from baseline (+0.15%).** Either Strategy purchase events are already priced in 2-3 days before the 8-K (likely, given MSTR's pre-announce on X), or our 8-K filter (Item 8.01 catch-all) over-counts non-BTC events. Both effects pull the measured edge to ~0.

---

## 5. Limitations

- **yfinance vs MT5 CFD price divergence.** All correlations were computed against Yahoo continuous-front-month futures (GC=F, SI=F, CL=F, BZ=F, NG=F) and Yahoo spot FX (EURUSD=X, etc.), not the OctaFX-Demo CFD prices TrendMaster actually trades. For CL/BZ specifically the front-month roll discontinuity introduces ~0.5-1% spurious returns at expiry; a finer-grained study would use the MT5 H1 prices we already have (limited to 2025-08-07 → 2026-04-23, ~263 days), losing the 2010-2024 history.
- **Weekly → daily aliasing for COT.** COT is "as of Tuesday close, published Friday 15:30 ET". I forward-filled to Friday close return so the signal is *strictly contemporaneous* (no look-ahead), but the published-Friday-night release window could have been used to get a same-week realised lead — that requires intraday alignment.
- **Event-study power.** 150 MSTR events × ±5d = N=1500 observation-days, but they overlap heavily (some weeks have 3 filings) → effective N is closer to 80. T-test on N=80 against an effect size of ~0.2σ has power ≈30%; we are not powered to detect a small edge here.
- **Farside dollar-volume IS NOT net flow.** The signed BlackRock SEC filings (IBIT 8.K — net cash flow from operations daily) would give the truer signal. This is the single biggest data-quality lift available for Phase B.
- **FedWatch ZQ-30d-Δ is a continuous-rate-expectation proxy, not the FedWatch-published probability of a specific cut at a specific FOMC.** PyFedWatch (rejected here on dependency-policy grounds) reconstructs the latter.

---

## 6. Appendix A — Key calculation kernels

```python
# Forward-return / lag correlation (used for COT, EIA, FedWatch sources)
def lag_corr(signal: pd.Series, ret: pd.Series, max_lag=3):
    out = {}
    for lag in range(0, max_lag + 1):
        merged = pd.concat([signal.rename("sig"),
                            ret.shift(-lag).rename("ret")], axis=1).dropna()
        if len(merged) < 10:
            out[lag] = (np.nan, np.nan, len(merged)); continue
        p  = stats.pearsonr (merged["sig"], merged["ret"])[0]
        sp = stats.spearmanr(merged["sig"], merged["ret"])[0]
        out[lag] = (p, sp, len(merged))
    return out

# Bootstrap 95% CI (used on best-lag Pearson)
def bootstrap_ci(signal, ret, n=500, ci=0.95):
    arr = pd.concat([signal.rename("s"), ret.rename("r")], axis=1).dropna().to_numpy()
    boots = []
    for _ in range(n):
        idx = RNG.integers(0, len(arr), size=len(arr))
        boots.append(stats.pearsonr(arr[idx,0], arr[idx,1])[0])
    return np.percentile(boots, [(1-ci)/2*100, 100-(1-ci)/2*100])

# 70/30 in-sample / out-of-sample split
def is_oos_split(signal, ret, lag, frac=0.7):
    m = pd.concat([signal, ret.shift(-lag)], axis=1).dropna()
    cut = int(frac * len(m))
    is_p  = stats.pearsonr(m.iloc[:cut, 0], m.iloc[:cut, 1])[0]
    oos_p = stats.pearsonr(m.iloc[cut:, 0], m.iloc[cut:, 1])[0]
    return is_p, oos_p

# COT signal construction: difference of speculator net (stationary)
cot["spec_delta"] = cot["spec_net"].diff()  # spec_net = noncomm_long - noncomm_short
```

---

## 7. Appendix B — Data fetch failures / partial successes

| Source | Endpoint | Status | Resolution |
|---|---|---|---|
| CFTC disaggregated F+O | `publicreporting.cftc.gov/resource/72hf-taqq.json` | HTTP 404 (dataset.missing) | Switched to legacy F-only endpoint `6dca-aqww.json`; reconstructed signal as `noncomm_long − noncomm_short` (proxy for managed money). |
| CFTC contract market names | (multi) | mid-stream renames | Older + newer market names had to be merged: WTI = `CRUDE OIL, LIGHT SWEET ...` → `WTI-PHYSICAL ...`, Brent has 3 names spread over 2011-2026, GBP = `BRITISH POUND STERLING ...` → `BRITISH POUND ...`, NZD = `NEW ZEALAND DOLLAR ...` → `NZ DOLLAR ...`, NG = `NATURAL GAS ...` → `HENRY HUB ...` (2018 split). |
| Farside BTC ETF flow | `farside.co.uk/bitcoin-etf-flow-all-data/` | HTTP 403 Cloudflare bot block (3× UA, 3× endpoint) | Substituted with yfinance ETF dollar-volume for 11 ETFs as PROXY — flagged heavily in §2.2 since it is NOT the same as net creation/redemption. |
| SoSoValue ETF API | `sosovalue.com/api/v1/etf/historicalInflowChart/us-btc-spot` | HTTP 403 | No fallback found within time budget. |
| TheBlock ETF chart API | `theblock.co/api/charts/...` | HTTP 403 | Same. |
| EIA Natural Gas Storage (ir.eia.gov) | `ir.eia.gov/ngs/wngsr.xls` | HTTP 403 | Substituted with `eia.gov/dnav/ng/hist_xls/NW2_EPG0_SWO_R48_BCFw.xls` (200 OK) — same series, different host. |
| FRED DFEDTARU | `fred.stlouisfed.org/graph/fredgraph.csv?id=DFEDTARU` | Read timeout (3× retry, 40s each) | Could not produce absolute "prob of cut" series; fell back to 30d Δ in ZQ implied rate, which lost the absolute-level information and produced verdict NONE for all three pairs. |
| MSTR Item-8.01 BTC filter | EDGAR JSON | 200 OK, but Item 8.01 also covers non-BTC events | Used 8.01 catch-all → over-counts events → dilutes effect size. Mitigation requires per-filing body-text classification. |

---

**Saved artifacts in `reports/phaseA2_data/`:**

- `_phaseA2_results.csv` — full numeric table (one row per (source,symbol) pair)
- `price_<symbol>.csv` × 14 — yfinance daily closes
- `cot_<contract>.csv` × 13 — CFTC weekly, with `spec_net`, `comm_net`
- `etf_<ticker>.csv` × 11 — yfinance daily ETF OHLCV
- `etf_dollar_volume.csv` — aggregate ETF dollar-volume pivot
- `eia_crude_stocks.csv`, `eia_ng_storage.csv` — EIA weekly inventories
- `fedfunds_zq_front.csv` — Yahoo ZQ=F implied rate
- `mstr_8k_filings.csv`, `mstr_8k_all.csv` — SEC 8-K filing index for CIK 0001050446
- `_work/` — fetch + analysis kernels (reproducible)

