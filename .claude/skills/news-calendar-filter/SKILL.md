---
name: news-calendar-filter
description: Block or downscale trading around high-impact economic events (NFP, FOMC, CPI, ECB, BOE, RBA) for the AMD bot. Use when a user reports the bot got slaughtered during news, when adding a calendar gate to the EA or brain, or when scheduling backtests that need to exclude news bars. Cheap, one-time install with permanent payoff — the most common cause of single-day catastrophic losses on retail FX is news spikes.
---

# News Calendar Filter

Forex bots without news filters routinely give back a week of profits in
the 90 seconds around NFP. Spreads blow out 20x, slippage is brutal, and
the AMD pattern is meaningless — there's no "smart money accumulation",
just whip from algos reacting to a single number.

A news filter is the cheapest, highest-floor improvement you can ship.

## What to filter

| Event impact | Window before | Window after | Action |
|--------------|---------------|--------------|--------|
| **High** (NFP, FOMC, CPI, GDP) | 30 min | 60 min | No new entries; close near-stops |
| **Medium** (PMI, retail sales, jobless claims) | 15 min | 30 min | Reduce risk to 0.5x |
| **Low** | 0 | 0 | Ignore |

The bot's *open* positions are a separate decision — most users prefer
"close all" before NFP rather than let trailing stops take wide hits.

## Data sources

| Source | Cost | Notes |
|--------|------|-------|
| **ForexFactory XML feed** (`forexfactory.com/calendar`) | Free | De facto standard; weekly XML, parse with `requests` + `xml.etree` |
| **Investing.com calendar** | Free w/ scrape | More events, harder to parse |
| **TradingEconomics API** | Paid (~$50/mo) | Cleanest data, JSON, historical lookup |
| **MT5 economic calendar** (`mt5.calendar_event_get`) | Free | Already available! Built into MetaTrader5 Python lib |

**Recommended: use the built-in MT5 calendar.** No extra dependency, no
HTTP, no parsing — and it's already on the machine.

## Implementation

### Step 1: Calendar fetcher

```python
# tools/news_calendar.py
from datetime import datetime, timedelta
from typing import List, Tuple
import MetaTrader5 as mt5

HIGH_IMPACT_KEYWORDS = (
    "Nonfarm", "NFP", "FOMC", "Federal Funds", "CPI",
    "GDP", "Unemployment Rate", "ECB Interest", "BOE Interest",
)

def upcoming_high_impact(symbol: str, hours_ahead: int = 6) -> List[Tuple[datetime, str]]:
    """Returns [(event_time_utc, event_name), ...] for currencies in `symbol`."""
    if not mt5.initialize():
        return []
    currencies = _currencies_in_symbol(symbol)  # EURUSD -> ("EUR", "USD")
    now = datetime.utcnow()
    end = now + timedelta(hours=hours_ahead)
    events = mt5.calendar_event_get(now, end) or []
    results = []
    for ev in events:
        if ev.importance < 3:           # 3 = high
            continue
        if ev.currency not in currencies:
            continue
        results.append((datetime.fromtimestamp(ev.time), ev.name))
    return results

def in_news_window(symbol: str, now=None) -> bool:
    now = now or datetime.utcnow()
    for event_time, _ in upcoming_high_impact(symbol, hours_ahead=2):
        if event_time - timedelta(minutes=30) <= now <= event_time + timedelta(minutes=60):
            return True
    return False
```

### Step 2: Wire into the brain

In `ai_trading_agents/trend_master_brain.py` inference loop:

```python
from tools.news_calendar import in_news_window

if in_news_window(symbol):
    write_signal(direction="NONE", confidence=0.0, reason="news_window")
    log.info(f"[{symbol}] suppressed: high-impact news within 30/60 min")
    return
```

### Step 3: Wire into the EA (independent safety net)

The brain might crash; the EA should also check. Add to OnTick:

```mql5
// AI_SUPERBB_v14_TrendMaster.mq5
if (IsHighImpactNewsWindow(_Symbol)) {
    if (InpCloseBeforeNews && PositionsTotal() > 0) {
        ClosePositionsForSymbol(_Symbol);
    }
    return;  // no new entries
}
```

`IsHighImpactNewsWindow` reads MQL5's built-in `CalendarValueHistory()`
or a JSON dropped by the Python helper — pick one path and stick with it.

## Backtest implications

If you add a news filter to live but your historical backtests *don't*
filter news bars, your backtest is now an unrealistic upper bound.
Re-run WFO with the filter enabled and compare:

- Trade count drop: typically 5-15% (news windows are short)
- Win rate change: typically +3-8 pp
- Max drawdown: typically -20-40% (this is the big win)
- Sharpe: typically +0.2 to +0.5

If your numbers don't move, either the filter isn't catching the right
events, or your backtest data already excluded the worst spikes.

## Edge cases

- **Cross-currency events.** EURUSD has both EUR and USD events. Both must
  be checked.
- **Metals.** XAUUSD reacts to USD events + Fed speak + geopolitics.
  Treat it as USD-only for the simple filter; add geopolitical alerts
  separately if needed.
- **DST shifts.** Calendar times are usually UTC; broker server may be
  UTC+2 or UTC+3. Always compare in UTC.
- **Holiday liquidity.** Christmas week, Thanksgiving Friday, etc. —
  not "news" but spreads behave the same. Add a hardcoded exclusion list.
- **Surprise events.** Central-bank emergency cuts, geopolitical shocks.
  Calendar can't predict these. The position-size limits and regime
  filter are the backstop.

## Validation

Pull `logs/trades_*.log` for the past 60 days. Match each trade's entry
timestamp against `mt5.calendar_event_get` for the same window. For
trades that fired within ±30 min of a high-impact event:

- What % were losers?
- What % of total drawdown came from this slice?

If 8% of trades cause 35% of drawdown and live in news windows, the
filter is going to materially improve your equity curve. Ship it.

## Related skills

- `amd-trading-bot-ops` — for the brain↔EA contract you'll extend
- `regime-detection` — sister skill; news filter is just a calendar-driven
  regime override
- `risk-metrics-calculation` — for measuring drawdown reduction
