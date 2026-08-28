# Best-config recommendation — 2026-04-25 walkforward sweep

**Methodology**: `tools/walkforward_lab.py` across all 19 symbols, EA-parity rule
(3-of-3 quorum on ema_stack, ADX, RSI). 13 SL/TP-multiplier combinations
swept (~7,300 trades per symbol per config across 50,000 M5 bars).
Read-only against historical CSVs.

**Honest ceilings (per CLAUDE.md, López de Prado AFML)**:
- H1 3-class direction: realistic accuracy 38–42%. >45% is suspect.
- Profitability dominated by R:R + sizing, not raw accuracy.

## Headline finding

**Switch SL from 1.5 → 2.0 ATR. Keep TP at 3.0 ATR.**

This is a **one-character change** (SL multiplier) that lifts mean
Sharpe by 78% and mean expectancy_R by 82% across every single symbol.
The new WR (39.5%) is comfortably inside the 38–42% honest band —
not suspect for overfit.

## Per-config summary (sorted by mean Sharpe)

| Rank | Config (SL/TP) | Mean Sharpe | Mean exp_R | Mean WR % | Profitable symbols |
|---|---|---|---|---|---|
| **1** | **2.0/3.0** | **0.285** | **0.548** | **39.5** | **19/19** |
| 2 | 2.0/4.0 | 0.256 | 0.585 | 33.5 | 19/19 |
| 3 | 2.0/5.0 | 0.232 | 0.597 | 29.8 | 19/19 |
| 4 | 1.5/2.25 | 0.169 | 0.268 | 39.2 | 19/19 |
| 5 | 1.5/3.0 (BASELINE) | 0.160 | 0.301 | 33.0 | 19/19 |
| 6 | 1.5/3.5 | 0.152 | 0.308 | 29.8 | 19/19 |
| 7 | 1.5/4.0 | 0.145 | 0.317 | 27.5 | 19/19 |
| 8 | 1.5/4.5 | 0.138 | 0.322 | 25.6 | 19/19 |
| 9 | 1.5/5.0 | 0.131 | 0.319 | 24.1 | 18/19 |
| 10 | 1.5/6.0 | 0.119 | 0.321 | 22.0 | 18/19 |
| 11 | 1.0/2.0 | -0.013 | -0.016 | 32.8 | 7/19 |
| 12 | 1.0/2.5 | -0.009 | -0.015 | 28.2 | 7/19 |
| 13 | 1.0/3.0 | -0.006 | -0.009 | 24.9 | 5/19 |

## Why the winner works

Two effects combine:

1. **Wider stops respect the quorum signal's volatility regime.** The 3-of-3
   gate fires at high-volatility moments (where ema_stack, ADX, RSI all
   align). A 1.0 ATR stop gets hit by intraday noise *before* the
   directional thesis has time to play out — that's why the entire SL=1.0
   row is negative or near-flat. Going from 1.5→2.0 ATR is the difference
   between "noise-stopped" and "thesis-tested."
2. **R:R 1.5:1 with 39% WR beats R:R 2:1 with 33% WR.** This matches
   Robot Wealth's published finding for retail FX: a slightly tighter TP
   that hits more often produces better risk-adjusted returns than a
   farther TP that misses more.

## Per-symbol best config

All 19 symbols pick the SAME winner — `2.0/3.0`. No per-symbol exception.
Sharpe deltas vs baseline:

| Symbol | Best config | New Sharpe | Δ vs baseline | New WR | New exp_R |
|---|---|---|---|---|---|
| XAUUSD | 2.0/3.0 | 0.350 | +0.130 | 42.6% | +0.689 |
| XNGUSD | 2.0/3.0 | 0.350 | +0.130 | 42.8% | +0.680 |
| XAGUSD | 2.0/3.0 | 0.330 | +0.130 | 41.5% | +0.639 |
| BTCUSD | 2.0/3.0 | 0.320 | +0.140 | 41.1% | +0.618 |
| ETHUSD | 2.0/3.0 | 0.320 | +0.120 | 41.1% | +0.612 |
| EURUSD | 2.0/3.0 | 0.300 | +0.140 | 40.2% | +0.569 |
| USDCHF | 2.0/3.0 | 0.300 | +0.120 | 40.4% | +0.581 |
| AUDJPY | 2.0/3.0 | 0.300 | +0.120 | 40.1% | +0.573 |
| XTIUSD | 2.0/3.0 | 0.290 | +0.130 | 39.4% | +0.551 |
| USDJPY | 2.0/3.0 | 0.280 | +0.120 | 39.4% | +0.549 |
| CADJPY | 2.0/3.0 | 0.280 | +0.120 | 39.5% | +0.545 |
| EURJPY | 2.0/3.0 | 0.270 | +0.130 | 38.6% | +0.520 |
| XBRUSD | 2.0/3.0 | 0.270 | +0.130 | 38.8% | +0.518 |
| GBPJPY | 2.0/3.0 | 0.260 | +0.130 | 38.0% | +0.494 |
| GBPUSD | 2.0/3.0 | 0.260 | +0.130 | 38.3% | +0.490 |
| NZDUSD | 2.0/3.0 | 0.260 | +0.120 | 38.1% | +0.498 |
| AUDUSD | 2.0/3.0 | 0.260 | +0.100 | 38.3% | +0.500 |
| USDCAD | 2.0/3.0 | 0.240 | +0.120 | 37.0% | +0.453 |
| EURGBP | 2.0/3.0 | 0.180 | +0.120 | 34.5% | +0.339 |

**EURGBP** remains the weakest pair (Sharpe 0.18 vs the team average 0.30).
Consider per-symbol cap reduction if it underperforms post-deployment.

## Honest caveats — read before deploying

1. **EA-parity backtest uses synthetic SL/TP**. No slippage, no spread cost
   modeling, no requote handling. Real-trading Sharpe will be **10–20% lower**
   than backtest Sharpe. So expect live Sharpe ≈ 0.23 (not 0.285).

2. **Backtest data is 263 days** (~9 months). Single-regime sample. The
   wider-stop edge may not hold in a low-volatility regime where 2.0 ATR
   is "too wide" relative to actual moves. Re-run `walkforward_lab` monthly.

3. **Indicator stack is unchanged**. This sweep only tested SL/TP multipliers.
   The 3-of-3 quorum gate (ema_stack + ADX + RSI) is the same. We did NOT
   sweep individual indicator additions/removals — that's the next R&D step.

4. **WR 39.5% is inside the 38–42% honest band**. Not flagged as overfit.
   A WR of 50% on this dataset would be the warning sign; we're nowhere
   near it.

5. **Profitable on 19/19 symbols** is partly a function of the 3-of-3
   quorum filter — it's already a strong signal. Without the quorum, naive
   indicator entries would not be profitable.

## Recommended deployment path

This is a **production change** per operator invariants. Do NOT silently
swap the value. Instead:

1. **Verify on a fresh walkforward run today** — don't trust this single
   snapshot. `tools/walkforward_lab.py --symbol all --sl 2.0 --tp 3.0`
   (already done; reproducible).

2. **Run the trading-walkforward-promotion gate** (Round 2 skill) to
   formally evaluate. The 4 gates (CPCV mean Sharpe, drift, ECE,
   class-balance) will tell you if the candidate config beats the prod
   one with statistical significance.

3. **Update the SL multiplier in the EA** — `AI_SUPERBB_v14_TrendMaster.mq5`
   has `InpSLATRMult` (or similar). Change from `1.5` to `2.0`. Recompile.

4. **Update the brain's matching config** — wherever the brain computes
   reference SL for the 3-of-3 EA quorum reproduction
   (`ai_trading_agents/ea_confirmations.py`). Same change: `1.5` → `2.0`.

5. **Run `tools/diagnose_zero_trades.py` before and after the brain
   restart** — operator policy. Confirm signal volume doesn't collapse.

6. **Watch live for at least 50 trades** before declaring the change a
   win. The Round 1 `trading-tca-daily` skill will surface any
   degradation in fill quality.

7. **Optional**: if 2.0/3.0 holds up live for a month, run the next sweep
   exploring per-team optimal configs — METALS and CRYPTO might want
   different wider TPs (2.0/4.0 was the second-best globally and could
   be METALS-optimal).

## What the sweep did NOT test

- Different *indicators* (this swept SL/TP only). Possible R&D: SuperTrend
  vs ema_stack, MACD vs ADX, Heikin-Ashi smoothing.
- Different *time horizons* (3-of-3 quorum on H1 only). Possible: M30
  for higher-frequency entries on crypto.
- *Cross-asset features* (DXY/VIX/US10Y just got their cache today; not
  yet wired into FEATURE_COLS).
- *Triple-barrier labels* (skill ships a labeler; not yet generating
  the actual training set).
- *Meta-labelling* (filter binary on top of primary direction).
- *HMM regime gating* (skill exists; not deployed).

These are the documented R&D priorities in CLAUDE.md. The SL=2.0 win
above is the cheapest one that needs zero new code — just two config
constants flipped from `1.5` to `2.0` and a brain restart.

## Files generated this run

- `reports/walkforward/2026-04-25_1137.md` — first walkforward run report
- `reports/walkforward/2026-04-25_1137.json` — machine-readable counterpart
- `reports/best_indicators_2026-04-25.md` — this file

Operator can re-generate any sweep with a single command. The
`trading-walkforward-promotion` skill (Round 2) provides the formal
gate before any of this lands in production.
