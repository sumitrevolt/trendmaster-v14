# COMPOUND GROWTH PLAN: $200 -> $500,000

**Generated:** 2026-08-25
**Strategy:** Multi-pair M5 scalping with 8-layer confluence scoring
**Validation:** Grid search (192 configs × 7 pairs) + Monte Carlo (500 sims)

---

## STRATEGY SUMMARY

| Parameter | Value | Notes |
|-----------|-------|-------|
| Starting Capital | $200 | Seed capital |
| Target | $500,000 | 2,500x return |
| Risk Per Trade | 3.0% | Phase 1 (scales down as account grows) |
| SL/TP | 0.8 / 2.0 ATR | Grid-search optimal for USDJPY |
| Leverage | 1:500 | Maximizes position sizing on small account |
| Compound | YES | All profits reinvested |
| Pairs | 7 | USDJPY, XAGUSD, EURUSD, AUDUSD, USDCHF, GBPUSD, NZDUSD |
| Trades/Day | 5 per pair = 35 total | High-frequency scalping |

---

## PAIR RANKINGS (by expectancy)

| Rank | Pair | WR% | Profit Factor | Avg R | Grid Config |
|------|------|-----|---------------|-------|-------------|
| 1 | **USDJPY** | 34.7% | 1.32 | +$1.00 | SL=0.8 TP=2.0 MinSc=5.0 |
| 2 | XAGUSD | 34.6% | 1.05 | +$0.25 | SL=1.2 TP=2.5 MinSc=5.0 |
| 3 | EURUSD | 35.8% | 1.32 | +$0.01 | SL=1.2 TP=3.0 MinSc=5.0 |
| 4 | AUDUSD | 37.3% | 1.35 | +$0.01 | SL=1.2 TP=2.5 MinSc=5.0 |
| 5 | USDCHF | 31.5% | 1.37 | +$0.01 | SL=1.2 TP=3.0 MinSc=5.0 |
| 6 | GBPUSD | 31.0% | 1.25 | +$0.01 | SL=0.8 TP=2.0 MinSc=5.0 |
| 7 | NZDUSD | 30.7% | 1.02 | +$0.00 | SL=1.2 TP=2.5 MinSc=5.0 |

---

## MONTE CARLO PROJECTION (500 simulations)

### Phase 1: SEED ($200 -> $2,000)
- Risk: 3.0% per trade
- Blow-up rate: **0.0%** (0/500 sims)
- Median end equity: **$2,110**
- 10th percentile: $2,019 | 90th percentile: $2,324
- Median days: **83 days** (2.8 months)
- Average max drawdown: 44.0%

### Phase 2: GROW ($2,000 -> $20,000)
- Risk: 2.5% per trade
- Blow-up rate: **0.0%** (0/500 sims)
- Median end equity: **$20,876**
- 10th percentile: $20,183 | 90th percentile: $22,697
- Median days: **97 days** (3.2 months)
- Average max drawdown: 40.1%

### Phase 3: SCALE ($20,000 -> $200,000)
- Risk: 2.0% per trade
- Blow-up rate: **0.0%** (0/500 sims)
- Median end equity: **$206,921**
- 10th percentile: $201,165 | 90th percentile: $220,358
- Median days: **146 days** (4.9 months)
- Average max drawdown: 35.2%

### Phase 4: HARVEST ($200,000 -> $500,000)
- Risk: 1.5% per trade
- Blow-up rate: **0.0%** (0/500 sims)
- Median end equity: **$511,472**
- 10th percentile: $501,432 | 90th percentile: $530,344
- Median days: **98 days** (3.3 months)
- Average max drawdown: 22.8%

### TOTAL
- **Median time to $500K: ~14 months**
- **Total blow-up rate: 0.0%**
- **Median final equity: $511,472**

---

## MONTHLY MILESTONES

| Month | Balance | Milestone |
|-------|---------|-----------|
| 1 | $517 | 1st double |
| 2 | $1,088 | 1K club |
| 4 | $3,204 | 2.5K |
| 5 | $10,148 | **10K!** |
| 8 | $42,634 | 25K |
| 10 | $57,380 | 50K |
| 14 | $107,433 | **100K! Six figures!** |
| 19 | $306,646 | 200K |
| 21 | $623,194 | **500K TARGET!** |

---

## SETTINGS APPLIED

### config/settings.py
- `INITIAL_BALANCE_USD = 200` (was $300)
- `LEVERAGE = 500` (was 200)
- `COMPOUND_GROWTH_MODE = True`
- `RISK.risk_percent = 3.0` (was 0.5)
- `RISK.compound_profits = True` (was False)
- `RISK.max_lot_size = 0.50` (was 0.03)
- `RISK.default_sl_atr_multiple = 0.8` (was 1.2)
- `RISK.default_tp_atr_multiple = 2.0` (was 2.5)
- `RISK.max_trades_per_day = 35` (was 20)
- `RISK.max_trades_per_symbol_per_day = 5` (was 2)
- `RISK.equity_drawdown_halt_pct = 8.0` (was 5.0)

### config/.env
- `RISK_PERCENT=3.0` (was 0.5)

### config/trading_config.yaml
- `risk_percent: 3.0` (was 0.5)

---

## 8-LAYER CONFLUENCE SCORING

| Layer | Weight | What it checks |
|-------|--------|----------------|
| 1. TREND | 2.0 | ADX>28 + EMA8/20/50 stack alignment |
| 2. MOMENTUM | 1.5 | RSI 40-65 sweet spot + MACD rising |
| 3. VOLATILITY | 1.5 | BB squeeze + ATR expansion |
| 4. SESSION | 1.0 | Peak hours (London-NY overlap) |
| 5. MTF + STOCH | 1.5 | EMA20>EMA50>EMA200 + Stochastic alignment |
| 6. PRICE ACTION | 1.3 | Strong body candle / pin bar |
| 7. VOLUME | 0.7 | Above-average volume confirmation |

**Minimum score to trade:** 5.0 (out of ~10.0 max)

---

## DAILY PROTOCOL

1. **Pre-market (6:30 UTC):** Check news calendar for high-impact events
2. **London open (7:00 UTC):** Start monitoring for setups
3. **Peak session (12:00-15:00 UTC):** Maximum trading activity
4. **NY close (20:00 UTC):** Close any remaining positions
5. **Post-market:** Log trades, update state, check equity curve

### Risk Controls
- **Daily loss limit:** -8% equity = stop trading for the day
- **Consecutive losses:** 4 losses = 2-hour cooldown
- **Max per symbol:** 5 trades per day per pair
- **Max open:** 8 simultaneous positions

---

## CRITICAL SUCCESS FACTORS

1. **COMPOUND REINVEST** — Never withdraw profits until $10K milestone
2. **DISCIPLINE** — Follow the scoring system, no manual overrides
3. **PATIENCE** — Phase 1-2 is slow; exponential growth comes in Phase 3-4
4. **ADAPTIVE RISK** — Reduce risk % as account grows (3% → 2.5% → 2% → 1.5%)
5. **MULTI-PAIR** — Trade all 7 pairs simultaneously for diversification
6. **SESSION FOCUS** — London-NY overlap (12-15 UTC) produces highest quality signals

---

## RISK WARNINGS

- Past performance does not guarantee future results
- Monte Carlo projections are theoretical — real markets have gaps, slippage, and black swans
- Maximum historical drawdown: 44% — this is normal for aggressive compounding
- If account drops below $100, STOP and reassess strategy
- Re-evaluate strategy every 3 months or after 30% drawdown
- Consider taking 10% profits at $10K, $50K, and $100K milestones

---

*Generated by Compound Growth Engine v2.0*
*Backtest data: 50K M5 bars per pair (7 pairs = 350K bars total)*
*Validation: 500 Monte Carlo simulations per growth phase*
