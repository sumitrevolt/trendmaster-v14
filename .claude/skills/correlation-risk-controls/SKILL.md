---
name: correlation-risk-controls
description: Cap aggregate exposure across correlated forex symbols (USD-bucket, EUR-bucket, JPY-bucket, metals) and adjust position sizing for correlated entries. Use when adding multi-symbol risk controls, when the bot took 3 simultaneous USD-short positions and lost on all of them at once, when designing portfolio-level kill switches, or when promoting from single-pair to multi-pair trading.
---

# Correlation-Aware Risk Controls

If the AMD bot trades EURUSD long, GBPUSD long, and XAUUSD long
simultaneously, you don't have three diversified positions — you have
one big USD-short position. When the dollar rallies, all three lose
together. Per-trade risk of 0.5% suddenly behaves like 1.5%, and your
"max daily drawdown" calculation is wrong.

This skill prevents the most common form of overnight account-killer:
correlated drawdown that the per-position risk limit didn't see coming.

## Core idea: currency buckets

Every forex/metal trade is exposure to *currencies*, not symbols. Bucket
the exposure by base currency and cap the bucket — not the symbol.

| Symbol | Long means | Short means |
|--------|------------|-------------|
| EURUSD | +EUR / -USD | -EUR / +USD |
| GBPUSD | +GBP / -USD | -GBP / +USD |
| USDJPY | +USD / -JPY | -USD / +JPY |
| XAUUSD | +Gold / -USD | -Gold / +USD |
| AUDUSD | +AUD / -USD | -AUD / +USD |

Three "long" trades on EURUSD/GBPUSD/AUDUSD = -3x USD exposure. Cap it.

## Implementation

### Step 1: Bucket calculator

```python
# tools/correlation_risk.py
from dataclasses import dataclass
from typing import Dict, List
import MetaTrader5 as mt5

CURRENCY_MAP = {
    "EURUSD": ("EUR", "USD"),
    "GBPUSD": ("GBP", "USD"),
    "AUDUSD": ("AUD", "USD"),
    "USDJPY": ("USD", "JPY"),
    "USDCAD": ("USD", "CAD"),
    "XAUUSD": ("XAU", "USD"),
    "XAGUSD": ("XAG", "USD"),
}

@dataclass
class BucketExposure:
    currency: str
    risk_pct: float  # signed: + means net long, - means net short

def compute_buckets(account_equity: float) -> Dict[str, float]:
    """Returns {currency: signed_risk_pct} across all open positions."""
    positions = mt5.positions_get() or []
    buckets: Dict[str, float] = {}
    for p in positions:
        base, quote = CURRENCY_MAP.get(p.symbol, (None, None))
        if not base:
            continue
        # risk_pct = SL distance * lot * point_value / equity
        sl_dist = abs(p.price_open - p.sl) if p.sl else 0
        risk_money = sl_dist * p.volume * mt5.symbol_info(p.symbol).trade_contract_size
        risk_pct = risk_money / account_equity * 100
        sign = +1 if p.type == mt5.POSITION_TYPE_BUY else -1
        buckets[base] = buckets.get(base, 0) + sign * risk_pct
        buckets[quote] = buckets.get(quote, 0) - sign * risk_pct
    return buckets

def can_take_new_trade(symbol: str, side: str, risk_pct: float,
                       max_bucket_pct: float = 1.5) -> tuple[bool, str]:
    """Returns (allowed, reason_if_blocked)."""
    base, quote = CURRENCY_MAP.get(symbol, (None, None))
    if not base:
        return True, ""
    equity = mt5.account_info().equity
    buckets = compute_buckets(equity)
    sign = +1 if side.upper() == "BUY" else -1
    new_base = buckets.get(base, 0) + sign * risk_pct
    new_quote = buckets.get(quote, 0) - sign * risk_pct
    if abs(new_base) > max_bucket_pct:
        return False, f"{base} bucket would be {new_base:+.2f}% > cap {max_bucket_pct}%"
    if abs(new_quote) > max_bucket_pct:
        return False, f"{quote} bucket would be {new_quote:+.2f}% > cap {max_bucket_pct}%"
    return True, ""
```

### Step 2: Wire into the brain or EA

In `trend_master_brain.py` before writing a BUY/SELL signal:

```python
from tools.correlation_risk import can_take_new_trade

allowed, reason = can_take_new_trade(symbol, direction, risk_pct=0.5)
if not allowed:
    write_signal(direction="NONE", confidence=0.0, reason=f"bucket_cap:{reason}")
    return
```

Or in the EA OnTick (more authoritative):

```mql5
if (!CheckCurrencyBucketLimit(_Symbol, signal_direction, InpRiskPercent)) {
    Print("Bucket cap hit; skipping trade");
    return;
}
```

## Sane defaults

| Knob | Default | Notes |
|------|---------|-------|
| `MAX_BUCKET_PCT` | 1.5% | No more than 1.5% account risk on any single currency |
| `MAX_TOTAL_OPEN_RISK` | 3.0% | Sum of all open trade risks |
| `MAX_CONCURRENT_TRADES` | 4 | Cap by count too — defense in depth |
| `CORR_LOOKBACK_DAYS` | 60 | Window for measuring rolling correlation |

These pair naturally with the bot's existing per-trade `RISK_PERCENT`
of 0.5% in `config/settings.py`. The bucket cap is the *aggregate*
limit; the per-trade risk is the *unit*.

## Beyond buckets: rolling correlation

Currency buckets handle the obvious cases. For subtler cases (EUR and
CHF often move together; CAD and AUD when oil rallies), use rolling
realized correlation:

```python
def correlated_pairs(returns: pd.DataFrame, threshold: float = 0.7,
                     window: int = 60) -> List[tuple[str, str, float]]:
    """Returns [(sym_a, sym_b, corr), ...] for sym pairs above threshold."""
    rolling_corr = returns.rolling(window).corr().iloc[-len(returns.columns):]
    pairs = []
    syms = returns.columns
    for i, a in enumerate(syms):
        for b in syms[i+1:]:
            c = rolling_corr.loc[a, b]
            if abs(c) >= threshold:
                pairs.append((a, b, c))
    return pairs
```

When the bot wants to take a new trade, scale the size by:
`new_size = base_size / (1 + sum(|corr_with_open|))`

Two highly correlated open positions and one new aligned one → size
gets cut roughly in half.

## Account-level circuit breakers

These are sister-controls, not strictly correlation but in the same family:

| Trigger | Action |
|---------|--------|
| Daily loss > 3% of equity | Disable all entries until next session |
| Open drawdown > 6% | Force-close losing positions |
| 5 consecutive losses | Pause for 24 hours; require manual unlock |
| Equity < 80% of starting | Stop bot, require user review |

These belong in the EA (authoritative) AND optionally the brain (early
warning). The EA controls whether orders are sent — that's the only
hard guarantee.

## Validation

Replay 60 days of `logs/trades_*.log`. For each trade entry, compute
what the bucket exposure WAS at that moment (from the prior open
positions). Then ask:

- How many trades would have been blocked by a 1.5% bucket cap?
- What was the PnL of the *blocked* trades vs the *taken* trades?
- Does blocked-trade PnL skew negative (filter is helping) or positive
  (filter is overly cautious)?

If blocked-trade PnL is meaningfully negative, the cap is rescuing you.
If it's positive, you're leaving money on the table — relax the cap.

## Things to NOT do

- **Don't only cap by symbol count.** "Max 3 open trades" is naive — 3
  USD-short trades is one big position.
- **Don't use static historical correlation.** Currency correlations
  break in stress (the Swiss Franc shock, GFC, etc.). Use rolling.
- **Don't forget metals.** XAU is "USD-short with extra volatility". A
  long XAUUSD + long EURUSD is the same direction.
- **Don't set the cap so low the bot never trades.** Start at 1.5%, log
  blocked trades for a week, then tune.

## Related skills

- `risk-metrics-calculation` — for measuring portfolio-level VaR/CVaR
- `amd-trading-bot-ops` — for the brain↔EA contract
- `regime-detection` — pair with this; high-vol regime + correlation = double trouble
