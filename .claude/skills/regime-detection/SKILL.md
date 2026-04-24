---
name: regime-detection
description: Classify the current market state (trending, ranging, high-volatility, low-volatility) and tell the AMD bot when to sit out. Use when adding a regime filter to the brain or EA, when investigating losing streaks during chop, when the user asks "why did the bot lose every trade today", or when designing a strategy that should only fire in specific regimes. The biggest single live-PnL improvement for an AMD strategy is refusing to trade in the wrong regime.
---

# Regime Detection

The AMD (Accumulation–Manipulation–Distribution) Smart Money pattern
exists clearly in trending and post-consolidation markets. In tight chop
or ultra-low-volatility "dead" markets, every "manipulation" is just
noise — the bot will see fake signals, take losses, and the brain will
poison its own weights learning from garbage.

A regime filter that says "do not trade right now" is often worth more
than any signal improvement.

## The four regimes that matter for this bot

| Regime | Detect with | AMD strategy fit |
|--------|-------------|------------------|
| **Trending** | ADX(14) > 25, EMA(50) slope persistent | Best fit — let it run |
| **Ranging** | ADX(14) < 20, BB width < median | Poor — sit out or scalp tight |
| **High-vol** | ATR(14) > 2x 30-day median | Risky — reduce size or sit out |
| **Low-vol** | ATR(14) < 0.5x 30-day median | No move to ride — sit out |

Compute these on H1 (the macro frame your `multi_agent.py` already uses).
The brain should have read-only access to the regime label as an extra
feature; the EA should respect a hard sit-out flag from the brain.

## Implementation pattern

```python
# regime_classifier.py — drop into ai_trading_agents/
import pandas as pd
import numpy as np
from ta.trend import ADXIndicator
from ta.volatility import AverageTrueRange, BollingerBands

REGIMES = ("trending", "ranging", "high_vol", "low_vol")

def classify_regime(h1_df: pd.DataFrame) -> str:
    """Returns one of REGIMES based on last 200 H1 bars."""
    adx = ADXIndicator(h1_df.high, h1_df.low, h1_df.close, window=14).adx().iloc[-1]
    atr = AverageTrueRange(h1_df.high, h1_df.low, h1_df.close, window=14).average_true_range()
    bb = BollingerBands(h1_df.close, window=20, window_dev=2)
    bb_width = (bb.bollinger_hband() - bb.bollinger_lband()) / h1_df.close

    atr_ratio = atr.iloc[-1] / atr.tail(200).median()
    bb_w_now = bb_width.iloc[-1]
    bb_w_med = bb_width.tail(200).median()

    if atr_ratio > 2.0:
        return "high_vol"
    if atr_ratio < 0.5:
        return "low_vol"
    if adx > 25:
        return "trending"
    if adx < 20 and bb_w_now < bb_w_med:
        return "ranging"
    return "trending"  # default — neutral case lean

# In trend_master_brain.py inference loop:
regime = classify_regime(h1_bars)
if regime in ("ranging", "low_vol"):
    write_signal(direction="NONE", confidence=0.0, regime=regime)
    return
if regime == "high_vol":
    confidence_min = 0.70  # demand much higher conviction
else:
    confidence_min = 0.58
```

## Wiring into the EA

The brain JSON gains a `regime` field; the EA reads it and:

```mql5
// in OnTick(), after reading ai_signal_<symbol>.json
if (signal.regime == "ranging" || signal.regime == "low_vol") {
    // skip — log only, no order
    return;
}
if (signal.regime == "high_vol") {
    risk_pct = InpRiskPercent * 0.5;  // half-size in chaos
}
```

## Validation: did the filter actually help?

Before promoting, replay the last 90 days of `logs/trades_*.log` and
re-classify each trade's regime at entry. Then ask:

| Regime | Win rate | Avg R | Decision |
|--------|----------|-------|----------|
| trending | (compute) | (compute) | Keep |
| ranging | usually <40% | usually <0.3 | **Filter out** |
| high_vol | mixed | high variance | Reduce size |
| low_vol | usually <30% | tiny | **Filter out** |

If filtering ranging+low_vol drops total trade count by 40% and lifts
overall expectancy by >25%, ship it. If trade count drops 70% and
expectancy improves only 5%, you've over-filtered — relax thresholds.

## Things to watch

- **Regime labels are lagging**, especially ADX. By the time you classify
  "ranging", you may be at the end of the range. Use forward-looking
  validation, not just point-in-time agreement.
- **Markov / HMM regime models** sound clever but rarely outperform the
  simple ADX/ATR rules above for short-horizon FX. Don't add complexity
  unless WFO proves it.
- **Different symbols want different thresholds.** XAUUSD's "high vol"
  is different from EURUSD's. Calibrate per-symbol if the bot trades >2.

## Related skills

- `amd-trading-bot-ops` — for the brain↔EA JSON contract you'll extend
- `walk-forward-optimization` — to validate the filter doesn't overfit
- `backtesting-frameworks` — for replay validation methodology
