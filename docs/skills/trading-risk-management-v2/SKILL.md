# Trading Risk Management v2 — Web-Research-Driven Rules

**Built 2026-05-13** after deep research into retail FX/multi-asset risk frameworks.

**Updated 2026-05-13 PM** with Layer 9 (Brain Veto) + cap=10 override.

## When to Use This Skill

- Operator asks about safeguard caps, concentration, drawdown, exposure
- Reviewing a new safeguard rule before deploying
- Debugging "SAFEGUARD BLOCK" log lines
- Tuning rules for a different account size

## The 8-Layer Risk Framework

Each trade signal passes through 8 sequential checks. First to refuse blocks the trade.

### Layer 1 — Drawdown Breaker (existing)
- **Daily DD ≤ 5%** (matches FTMO standard)
- **Intraday DD peak vs current ≤ 3%** (catches sudden adverse moves)
- File: `tools/safeguards.py::drawdown_breaker_tripped`

### Layer 2 — News Blackout (existing, asymmetric)
- **-60 min before** high-impact news
- **+30 min after** (asymmetric — pre-news positioning is the risky window)
- Source: `config/news_calendar.json`

### Layer 3 — Time-of-Day Blackout (NEW v2)
Avoid known thin-liquidity / gap windows:
- **Sunday 00:00-04:00 IST** — pre-Tokyo dead zone
- **Sunday 04:00-04:30 IST** — FX open spread spike
- **Friday 21:00-23:59 IST** — weekend gap risk
- **Daily 13:00-13:15 IST** — London open spread spike
- **Daily 18:30-18:45 IST** — NY open spread spike

Research basis: ActivTrades + AlphaExCapital 2026 guides — session-overlap windows have 2-3x normal spread.

### Layer 4 — Per-Symbol Daily Loss Cap (NEW v2)
If a single symbol loses **>1% of equity in one day**, block trading that symbol for the rest of the day. Prevents revenge trading + concentration in losing pair.

Research basis: FTMO drawdown framework + Tradetron risk-management techniques.

### Layer 5 — Equity-Tier Scaling (NEW v2)
Max total open positions scales with account size:

| Equity (USD) | Max Open | Rationale |
|---|---|---|
| ≤ $500 | 5 | Micro: tight but allows diversification |
| > $500 | **10** | **Operator override** — flat cap for current account size |

(Was multi-tier 2/5/8/12 — operator chose flat 10 for current setup. At 0.5% risk × 10 = 5% max simultaneous risk, matching daily DD breaker.)

Research basis: Quantpedia Kelly + fixed-fractional position sizing — smaller accounts need tighter concentration to survive losing streaks.

### Layer 6 — USD-Side Correlation (existing v1)
- **Max 3 long-USD positions** (USDxxx BUY or xxxUSD SELL → all increase $-strength bet)
- **Max 3 short-USD positions**
- Symbol classifier in `_usd_side(symbol, is_buy)`

Research basis: industry standard sector exposure cap (~25% — at 0.5% risk × 3 = 1.5% sector risk, comfortably under).

### Layer 7 — Correlation Cluster (NEW v2)
Within highly-correlated symbol clusters, **max 2 same-direction positions**:

```python
CORRELATION_CLUSTERS = {
    "USD_MAJORS":    {EURUSD, GBPUSD},          # ~0.85 corr
    "USD_COMMODITY": {AUDUSD, NZDUSD},          # ~0.88 corr
    "PRECIOUS":      {XAUUSD, XAGUSD},          # ~0.80 corr
    "OIL":           {XTIUSD, XBRUSD},          # ~0.95 corr
    "CRYPTO":        {BTCUSD, ETHUSD},          # ~0.70 corr
    "JPY_RISK":      {USDJPY, EURJPY, GBPJPY, AUDJPY, CADJPY},  # carry-trade complex
}
```

Why: USD-side cap counts global $-direction but misses cluster bets. Example — long XAUUSD + long XAGUSD = same gold/silver trade twice. Without cluster cap, both would pass USD-side check (each only counts as 1 long-USD).

Research basis: Hudson & Thames + ActivTrades correlation papers — uncontrolled cluster exposure is the #1 silent drawdown source for retail traders.

### Layer 9 — Brain Veto (NEW 2026-05-13 PM — operator-requested)

If brain process is running with confident contradictory view, block the trade.

Rules:
- Brain confidence ≥ 0.65 AND direction differs from RP → BLOCK
- Brain confidence < 0.65 → defer to RP (allow)
- Brain view stale (>1 hr old) → defer to RP (allow)
- Brain agrees → allow
- Brain not running → allow

Disable via `BRAIN_VETO_ENABLED=0` env or `BRAIN_VETO_ENABLED = False` constant.

Tuning knobs:
```python
BRAIN_VETO_ENABLED = True
BRAIN_VETO_MIN_CONFIDENCE = 0.65   # below this, brain doesn't veto
BRAIN_VIEW_STALENESS_SEC = 3600    # >1 hr = ignore brain view
```

Brain inference comes from `logs/brain_state.json`:
- Primary: `last_signal_per_symbol[SYM]` (post-gates current view)
- Fallback: `last_signal_direction[SYM]` (pre-gates last directional view)

Operator policy: "brain decide karega kya signal pe trade karna hai ya nahi". Brain doesn't approve positively — RP does that. Brain has VETO power when it strongly disagrees.

### Layer 8 — Spread Guard (DISABLED per operator policy)
Operator's standing decision (memory `feedback_no_spread_gate`). Vol regime check covers liquidity proxy. Don't re-enable without asking.

## Configuration Knobs

Edit `tools/safeguards.py` constants:

```python
MAX_SAME_SIDE_USD_POSITIONS = 3        # Layer 6
MAX_PER_CLUSTER_SAME_DIR = 2           # Layer 7
PER_SYMBOL_DAILY_LOSS_PCT = 1.0        # Layer 4
EQUITY_TIERS = [...]                   # Layer 5
TOD_BLACKOUTS = [...]                  # Layer 3
TOD_DAILY = [...]                      # Layer 3
```

## Calibration Guide

**For < $500 account:** tighten everything
```python
MAX_SAME_SIDE_USD_POSITIONS = 2
MAX_PER_CLUSTER_SAME_DIR = 1
PER_SYMBOL_DAILY_LOSS_PCT = 0.5
```

**For > $5000 account:** relax for diversification
```python
MAX_SAME_SIDE_USD_POSITIONS = 4
MAX_PER_CLUSTER_SAME_DIR = 3
PER_SYMBOL_DAILY_LOSS_PCT = 1.5
```

**Never:** remove drawdown breaker. Removing the 5% daily DD cap is the fastest way to wipe an account.

## Common "SAFEGUARD BLOCK" Reasons + Operator Action

| Log message | What it means | Operator action |
|---|---|---|
| `already 3 long-USD positions (cap 3)` | USD-side cap | Wait for one to close, OR raise cap in safeguards.py |
| `cluster CRYPTO already has 2 same-direction positions (cap 2)` | Cluster cap | This is the new rule. Wait for BTC/ETH to close. |
| `equity-tier 'small' (eq=$800) cap=5 reached` | Total position cap | Close some positions or wait |
| `symbol XAUUSD day-PnL -$12 (-1.10%) ≤ -1.0% cap` | Symbol daily loss | XAU blocked rest of day — fresh start tomorrow |
| `time-of-day FRIDAY_LATE` | Weekend gap window | Wait until Sunday 04:30 IST |
| `daily DD breached: -5.2%` | Account DD cap | Day done. Wait for tomorrow. |
| `news blackout: NFP in 45 min` | High-impact news | Wait until release + 30 min |

## How to Test the Stack

```cmd
.venv\Scripts\python.exe -c "from tools.safeguards import check_all; print(check_all('BTCUSD', 'BUY'))"
```

Returns `(allowed, reason)`. Logs to `logs/safeguards.log` on each call.

## Memory Cross-Refs

- `feedback_no_spread_gate` — spread guard stays OFF
- `project_2026-05-06_safeguards_concentration_caps` — original v1 cap docs
- `project_2026-05-09_dupe_executor_root_cause` — why dupes amplified USD-side breach
- `project_2026-05-13_inferred_failed_again` — INFERRED banned (separate from safeguards)

## Research Sources

- [Modern Forex Risk Management Beyond Stop Losses (PFH Markets 2026)](https://blog.pfhmarkets.com/forex/modern-forex-risk-management-beyond-stop-losses-2026/)
- [Currency Correlation & Portfolio Risk Guide (ActivTrades)](https://www.activtrades.com/en/news/forex-correlation-pairs-how-they-influence-multi-asset-portfolio-risk)
- [Top Portfolio Risks in 2026: Concentration, Correlation, Drift (Guardfolio)](https://www.guardfolio.ai/blog/portfolio-risks-2026)
- [Risk Before Returns: Position Sizing Frameworks (Ildi Veliu, Medium)](https://medium.com/@ildiveliu/risk-before-returns-position-sizing-frameworks-fixed-fractional-atr-based-kelly-lite-4513f770a82a)
- [FTMO Maximum Daily Loss](https://academy.ftmo.com/lesson/maximum-daily-loss/)
- [ATR Based Stop Loss (AlphaExCapital 2026)](https://www.alphaexcapital.com/stocks/technical-analysis-for-stock-trading/trading-strategies-using-technical-analysis/atr-based-stop-loss)
- [Reducing Drawdown: 7 Risk-Management Techniques (Tradetron)](https://tradetron.tech/blog/reducing-drawdown-7-risk-management-techniques-for-algo-traders)
