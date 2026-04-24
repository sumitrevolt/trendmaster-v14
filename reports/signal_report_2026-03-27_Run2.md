# Trading Signal Report
**Date:** 2026-03-27 | **Run:** 2

---

## Market Conditions (Based on Last Signals — Mar 16-17)

**Overall Bias:** Mixed — Metals/Crypto showing divergence, Forex weak signals

⚠️ **Data is 10 days stale** — bot has not generated new signals since March 17.

### Current Signal Snapshot

| Symbol | Direction | Confidence | Assessment |
|--------|-----------|------------|------------|
| BTCUSD | SELL | 39% | Strongest signal but below threshold |
| XAUUSD | BUY | 34% | Contradicts 14 open SELL positions |
| ETHUSD | BUY | 34% | Moderate crypto bullishness |
| XAGUSD | BUY | 28% | Metals bullish alignment with Gold |
| USDJPY | SELL | 26% | Weak |
| EURUSD | SELL | 24% | Very weak |
| GBPUSD | SELL | 21% | Extremely weak |

---

## Top 3 Strongest Signals

### 1. BTCUSD — SELL @ $74,232
- **Confidence:** 39% (highest available)
- **Training data support:** BUY signal in training (conflicting)
- **Prediction accuracy:** 36.2% (poor)
- **Verdict:** ❌ NOT ACTIONABLE — low confidence + poor track record

### 2. XAUUSD — BUY @ $5,013.79
- **Confidence:** 34%
- **Prediction accuracy:** 53.4% (best of all symbols)
- **Concern:** 14 open SELL positions conflict with BUY signal
- **Verdict:** ⚠️ INTERESTING but sub-threshold. The BUY signal suggests the 14 open SELLs may be underwater.

### 3. ETHUSD — BUY @ $2,330.95
- **Confidence:** 34%
- **Prediction accuracy:** 42.6% (moderate)
- **Verdict:** ❌ NOT ACTIONABLE — below threshold

---

## Active Positions & Estimated P&L

14 XAUUSD SELL positions (all opened Feb 12-13):
- **Average entry price:** ~$4,977
- **Last known XAUUSD price:** $5,013.79 (from agent memory, Mar 17)
- **Estimated unrealized loss:** Positions are likely underwater as XAUUSD moved higher from entry
- **Position size:** 0.01-0.02 lots each (small)

---

## Bot Health Score: 2/10

| Category | Score | Reason |
|----------|-------|--------|
| Bot Activity | 0/2 | Not running for 43+ days |
| Signal Quality | 0/2 | All signals below confidence gate |
| Trade Management | 0/2 | 14 orphaned open positions |
| Prediction Accuracy | 1/2 | XAUUSD decent at 53.4%, others poor |
| Risk Management | 1/2 | Position sizes small, but high concentration |

---

*Signal Report — AI Trading Bot Monitor*
