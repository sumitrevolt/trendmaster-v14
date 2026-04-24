---
name: trading-strategies
description: "Named strategy recipes for algorithmic trading bots. Use when picking, combining, or tuning a trading strategy — this skill lists canonical entry/exit patterns (Trend+Pullback, Breakout+Retest, Opening-Range, Mean-Reversion, Ichimoku Trend, SuperTrend, Triple-Screen, MACD-Cross, Grid/Martingale danger-zones) with pseudocode, suitable timeframes, known failure modes, and GitHub references from freqtrade-strategies and EA31337-Libre. Useful for deciding WHICH strategy to encode, not HOW to code generic EA scaffolding."
---

# trading-strategies

A catalogue of named strategy recipes, distilled from `freqtrade/freqtrade-strategies` (Strategy 001-005 + hyperopt patterns), `EA31337/EA31337-Libre` (35+ MT5 strategies), and classic technical-analysis literature. Pick one, encode it cleanly, and backtest to the rules in `trading-backtest`.

**Core principle:** A strategy is not a set of indicators — it's a rule set that says *when to enter*, *when to exit*, *how to size*, and *when not to trade at all*. This skill focuses on the first two; sizing belongs in `trading-risk-ops`.

## When to use

- Picking a starting strategy for a new symbol or timeframe.
- Porting a crypto (freqtrade) strategy to forex (MT5).
- Combining two strategies into a voting ensemble (the 3-agent bus in this project is a special case).
- Debugging why a "working" strategy loses money — match against the failure-mode list.

## Strategy taxonomy

Strategies fall into four buckets. Mixing buckets inside one EA usually loses — pick one dominant regime and one confirmation regime at most.

| Bucket | Edge | Works in | Breaks in |
|---|---|---|---|
| **Trend following** | Ride the move, cut losers fast | Directional markets (ADX>20) | Sideways chop |
| **Mean reversion** | Fade extremes back to fair | Range-bound, high ADX<15 | Strong trends |
| **Breakout** | Catch regime change early | Consolidation → expansion | False breakouts |
| **Scalping/microstructure** | Exploit spread/queue | Liquid, low-spread hours | News, low liquidity |

## 1. Trend + Pullback

**Regime:** Trend-following. The classic "buy the dip in an uptrend."

**Entry (long):**
- H4 / daily: `EMA20 > EMA50 > EMA200` (trend fan clean)
- H4 ADX ≥ 20 (trending, not ranging)
- H1 pullback: price touches or crosses below EMA20 then closes back above
- RSI(14) on H1 between 40-60 on the pullback (oversold within a trend)

**Exit:**
- TP: previous swing high, or `2 × ATR(14)` above entry
- SL: `1 × ATR(14)` below entry, or below the pullback low + buffer
- Trail: move SL to break-even at `+1 ATR`, then trail by `1 ATR`

**Suitable TFs:** H1 entry, H4 trend filter, D1 bias. Works well on major forex, XAUUSD, index CFDs.

**Failure modes:**
- Fakeout pullbacks that break the structure → require RSI to confirm.
- News spikes that invalidate the trend in one candle → pair with news filter.
- Very tight TP / wide SL → profit factor sinks. Keep R:R ≥ 1.5.

**This project implements exactly this pattern.** See `multi_agent.py`:
- `trend_agent_h4` = EMA fan + ADX
- `momentum_agent_h1` = MACD histogram rising
- `timing_agent_m30` = RSI 45-70 in an uptrend

## 2. Breakout + Retest

**Regime:** Breakout. Enter after consolidation resolves.

**Entry (long):**
- Price consolidating in a range for ≥ N bars (e.g. 20 H1 bars)
- Donchian(N) upper channel breaks on strong volume / ATR expansion
- **Wait for retest** — price returns to the broken level and holds
- Enter on the first close back above the level

**Exit:**
- TP: 1.5× the range height projected from the breakout
- SL: mid-range or below the retest low
- Do NOT chase the initial break without retest — false-breakout rate is high.

**Suitable TFs:** H1-H4 for forex/indices, M15-H1 for crypto.

**Failure modes:**
- Entering on the first break without retest → 50%+ failure rate on minor breakouts.
- Range was never clean to begin with → add a "range quality" filter (low ADX, tight Bollinger bandwidth).
- Retest invalidated by news → block around high-impact releases.

**MQL5 tip:** use `iHighest` / `iLowest` with a shift of 1 to exclude the current bar from the channel calc, preventing repaint.

## 3. Opening Range Breakout (ORB)

**Regime:** Breakout, session-timed. The London or New York open sets the range; breaks of that range often run.

**Entry:**
- Build opening range = high/low of first N minutes after a session open (e.g. first 30 min of London)
- Long on close above range high; short on close below range low
- Trade only **one direction per day** — the first valid break

**Exit:**
- TP: 1× range width extended from break
- SL: opposite side of the opening range
- Time-exit at session close if not filled.

**Suitable TFs:** M5-M15 execution, with a daily bias filter.

**Failure modes:**
- "Inside day" — no break happens → no trade, skip, don't force it.
- Holiday / thin-liquidity days → the opening range is noise.
- Bad for XAUUSD on Sunday open and Monday pre-London — add session guards.

**Reference:** EA31337 strategies library ships an ORB module; patterns in freqtrade-strategies are also mostly session-agnostic crypto variants.

## 4. Mean Reversion at Bollinger Bands

**Regime:** Range. Fade the extremes.

**Entry (long):**
- Daily / H4 ADX < 15 (confirmed range, not a hidden trend)
- Price touches or pierces lower Bollinger(20, 2σ)
- RSI(14) < 30
- Candle closes back inside the band (rejection confirmation)

**Exit:**
- TP: middle band (MA20) or upper band
- SL: `1 × ATR` below the low of the entry candle
- Time-exit after N bars if price stalls at mid-band.

**Suitable TFs:** M30-H1 on ranging symbols (EURCHF, GBPAUD on certain weeks, XAUUSD consolidation phases).

**Failure modes:**
- ADX check missed → trade the strongest trend in reverse, classic account-killer.
- Catching a falling knife on news → no fade in the hour around red-folder news.
- Works in backtest, fails live because ADX lags → add a second range filter like Keltner vs Bollinger (Bollinger-inside-Keltner = genuine squeeze/range).

## 5. Ichimoku Kinko Hyo Trend

**Regime:** Trend following, visual. Popular in JP and crypto communities.

**Entry (long):**
- Price above Kumo (cloud)
- Tenkan-sen crosses above Kijun-sen (TK cross) above the cloud
- Chikou span free of price (no obstruction 26 bars back)
- Cloud ahead is green (bullish)

**Exit:**
- TP: next resistance or `2 × ATR`
- SL: below Kijun-sen or below the cloud
- Flip / close on TK bear cross below the cloud

**Suitable TFs:** H4-D1 — Ichimoku is noisy on sub-H1.

**Failure modes:**
- Using default 9/26/52 on non-daily TFs without thinking → params should scale with TF.
- Cloud twists constantly on choppy markets → filter with weekly trend.

**Reference:** multiple Ichimoku EAs on MQL5 code base; parameters worth tuning differ between forex (keep defaults) and crypto (shorter, e.g. 7/22/44).

## 6. SuperTrend + Confirmation

**Regime:** Trend, simple. Low-noise, rules-light.

**Entry (long):**
- SuperTrend(ATR=10, multiplier=3) flips to green
- Confirmation: MACD histogram > 0 **or** price closes above EMA50
- Optional: VWAP above

**Exit:**
- Exit when SuperTrend flips back
- Or trail by `2 × ATR` — whichever is tighter

**Suitable TFs:** M15-H1 on actively trading sessions.

**Failure modes:**
- Whipsaws in low-ATR conditions → require ATR / close > 0.2%.
- Flipping in and out rapidly → add a minimum hold of 3 bars unless SL hit.

**This project's EA** uses SuperTrend as one of its 3 local confirmations — see `FillConfirmations` in the MQL5 file.

## 7. Triple-Screen (Elder)

**Regime:** Meta-strategy. Combine three timeframes, all must agree.

**Entry (long):**
- Screen 1 (higher TF trend): weekly MACD histogram rising OR EMA slope up
- Screen 2 (trading TF pullback): daily stochastic oversold
- Screen 3 (execution trigger): intraday break of prior bar high

**Exit:**
- Trail via screen-2 stochastic: exit on overbought + bearish divergence.

**Suitable TFs:** any, as long as the three are well-separated (W/D/H1 or D/H4/H1).

**Failure modes:**
- Using three adjacent TFs (H1/H4/D) — too correlated, not independent. Space by at least 4×.
- Weekly filter almost always bullish → becomes a long-only system during equity bull markets.

**This project's multi-agent bus is a 3-TF triple-screen variant** — H4 trend screen, H1 momentum screen, M30 timing trigger.

## 8. MACD Zero-Line Cross with Trend Filter

**Regime:** Momentum / trend.

**Entry (long):**
- MACD line crosses above zero (momentum turning bull)
- H4 EMA200 slope > 0 (trend filter)
- Price above EMA50 on entry TF

**Exit:**
- Exit on MACD line crossing back below signal line
- SL below recent swing low

**Failure modes:**
- Without the trend filter, counter-trend MACD crosses are the majority of losers.
- Very slow: often misses the first third of a move. Accept that or combine with a momentum agent.

## 9. Grid / Martingale — DANGER ZONE

**Pattern:** Open buy at P, another buy at P-X, another at P-2X, averaging down. Close the basket when total PnL > 0.

**Why this appears in so many freqtrade strategies and EA31337 variants:** because backtests look *amazing*. Win rate approaches 100%.

**Why it blows accounts:**
- Exponential drawdown when the move doesn't revert.
- Tail-risk events (CHF flash crash, COVID open, LUNA) hit grid systems first and hardest.
- A 15-trade grid with 1% margin each = 15% margin-used; one 5% move against you can liquidate the whole stack.

**Rules if you insist:**
- Hard max-basket cap (e.g. 3 levels, never 10).
- Hard total-exposure cap as % of equity.
- A "circuit breaker" that closes the whole basket at -N% equity — no exceptions.
- Never use on news days. Never use without a VIX / realized-vol filter.

**Recommendation:** don't. Use Trend+Pullback or Mean-Reversion with proper SL instead. You keep the edge without the tail.

## 10. Ensemble voting (multi-strategy)

When no single strategy is reliable, combine several and require agreement. This is exactly what `multi_agent.py` in this project does.

**Rules:**
- Each strategy votes independently: +1 long, -1 short, 0 pass.
- Require **unanimous** non-zero agreement (2/3 is a trap — see `trading-python-brain`).
- Each strategy should target a different regime (one trend-follower, one breakout, one mean-reverter) or a different TF — otherwise the votes are correlated and you've just added complexity.
- Log every vote with reason. Unexplained refusals are the #1 source of post-hoc "should have traded that" regret.

## Picking a strategy — decision tree

```
Is ADX(14) on H4 >= 20 most days?
├─ YES → market is trending
│   ├─ Want higher win-rate, lower R:R? → Trend+Pullback
│   ├─ Want fewer trades, bigger winners? → SuperTrend or Ichimoku
│   └─ Want to catch regime change? → Breakout+Retest
│
└─ NO → market is ranging
    ├─ Clean range (Bollinger inside Keltner)? → Mean-Reversion at Bands
    ├─ Session-timed tradition (London/NY)?   → Opening Range Breakout
    └─ Unclear regime                          → Ensemble vote (wait for unanimous)
```

## GitHub references

- `freqtrade/freqtrade-strategies` — 5 hyperopt-tuned named strategies (Strategy 001-005); read to understand *buy_signal* / *sell_signal* structure, not as ready-to-ship code.
- `paulcpk/freqtrade-strategies-that-work` — community-maintained "what actually held up in 2023-24" filter on the above.
- `EA31337/EA31337-Libre` — 35+ MT5 strategies in one framework; useful to cross-reference parameter defaults for forex.
- `virtualpeer/freqtrade-strategies-1` / `tikkeninc/freqtrade-strategies` — additional community variants, worth skimming for novel buy filters.
- MQL5 code base (`mql5.com/en/code`) — search "SuperTrend EA", "ORB EA", "Ichimoku EA" for MT5-native reference implementations.

## Extension workflow

Encoding a new strategy:

1. Write the entry rules as a single `bool is_entry_long()` / `is_entry_short()` function — one per side, easy to test.
2. Write the exit rules as `void manage_trade(position)` — called every tick or bar close.
3. Add a regime filter (ADX, volatility, session). Without it, most strategies fail out-of-regime.
4. Backtest with walk-forward (see `trading-backtest`). If OOS Sharpe < 0.5, reject.
5. Add to the ensemble as an agent or keep standalone. If standalone, give it its own `InpUseX` toggle.

Red flags to reject before coding:

- Backtest uses look-ahead (uses `iHigh(0)` or `close[-1]` in Python without shift).
- No defined SL — "we'll figure it out" = you'll figure it out at -20%.
- Backtest has < 30 trades over several years — not enough signal, probably curve-fit.
- Strategy "only works" on one symbol and one TF — acceptable, but flag it as narrow.

## Disclaimer

Every repo cited above carries the same warning as this skill: **these are educational recipes**. Backtest in dry-run for weeks before live. Size small when going live. Accept that every strategy has a regime where it's garbage and plan for that regime to arrive eventually.
