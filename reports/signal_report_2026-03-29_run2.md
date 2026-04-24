# Trading Signal Report — 2026-03-29

## Current Market Conditions (Based on Last Signals)

| Symbol | Last Signal | Price | Confidence | Timestamp |
|--------|-------------|-------|------------|-----------|
| XAUUSD | BUY | 5,013.79 | 34% | 2026-03-17 01:36 |
| XAGUSD | BUY | 80.90 | 28% | 2026-03-17 01:56 |
| BTCUSD | SELL | 74,232.00 | 39% | 2026-03-16 23:44 |
| ETHUSD | BUY | 2,330.95 | 34% | 2026-03-17 01:56 |
| EURUSD | SELL | 1.15065 | 24% | 2026-03-17 01:48 |
| GBPUSD | SELL | 1.33014 | 21% | 2026-03-16 23:29 |
| USDJPY | SELL | 159.193 | 26% | 2026-03-16 23:37 |

**Note:** All signals are stale — last update was 12+ days ago (March 16-17). Bot has not generated new signals since then.

## Active Positions & P&L

14 XAUUSD SELL positions open from Feb 12-13 (all OPEN, no exits recorded):

| # | Entry Time | Entry Price | Volume | SL | TP |
|---|------------|-------------|--------|------|------|
| 1 | Feb 12 20:07 | 5,062.94 | 0.01 | 5,072.22 | 5,052.60 |
| 2 | Feb 12 20:16 | 5,060.08 | 0.01 | 5,068.31 | 5,047.69 |
| 3 | Feb 12 22:52 | 4,961.35 | 0.01 | 4,983.46 | 4,931.55 |
| 4-14 | Feb 12-13 | 4,923–4,970 | 0.01-0.02 | Various | Various |

**WARNING:** These 14 positions have been open for 44+ days with no status updates. If XAUUSD has moved significantly, these could represent large unrealized losses or gains. Manual verification on MT5 is critical.

## Top 3 Strongest Current Signals

1. **BTCUSD SELL** — Confidence 39% (highest among current signals), Agent accuracy 70%
2. **ETHUSD BUY** — Confidence 34%, Agent accuracy 65%
3. **XAUUSD BUY** — Confidence 34%, Agent accuracy 51%

*Note: None of these meet the 65% minimum confidence gate currently set in main.py. No actionable signals.*

## Prediction Accuracy Leaderboard

| Symbol | Accuracy | Status |
|--------|----------|--------|
| AUDUSD | 64.7% | ⭐ STRONG — Consider increased sizing |
| XAUUSD | 54.0% | Good |
| NZDUSD | 52.0% | Acceptable |
| XAGUSD | 48.8% | Borderline |
| ETHUSD | 42.6% | Below target |
| EURUSD | 37.0% | Weak |
| BTCUSD | 36.2% | Weak |
| USDJPY | 29.3% | ⚠️ BELOW 30% — Flag for blacklist |
| GBPUSD | 22.8% | ⚠️ BELOW 30% — Flag for blacklist |

## Bot Health Score: 3/10

**Reasons:**
- Bot INACTIVE since Feb 12 (last scan 45 days ago, only 18 scans total)
- 14 stale OPEN trades with no exit management
- prediction_memory.json was CORRUPTED (restored from backup)
- Only 1 training data sample — ML model essentially untrained
- No signals generated in 12+ days
- Brain memory shows 1,979 wins / 310 losses (86.5% WR) but this appears to be from backtesting/simulation, not live trades
