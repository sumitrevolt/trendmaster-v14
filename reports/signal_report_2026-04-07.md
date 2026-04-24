# Signal Report — 2026-04-07 (Run 16)

## Market Overview
Bot is **OFFLINE** since Feb 12 (~54 days). No live execution. 3 JSON files still corrupted (agent_learnings, agent_internet_research, prediction_memory). 82/84 Python files pass syntax.

## Active Positions
14 orphaned XAUUSD SELL positions (54+ days old, entries $4,923–$5,063) — **CLOSE IMMEDIATELY**

## Top 3 Signals

### 1. GBPJPY — BUY
- Prediction Accuracy: 97.0% (459/473)
- Last Confidence: 70%
- Signal Time: 2026-04-07 17:50 UTC
- Gate: 60 — **PASSES**
- Status: ⭐ ELITE — RE-ENABLED in bot settings

### 2. USDCAD — SELL
- Prediction Accuracy: 87.0% (47/54)
- Last Confidence: 70%
- Signal Time: 2026-04-06 22:29 UTC
- Gate: 65 — **PASSES**
- Status: ⭐ STRONG — gate recently lowered

### 3. BTCUSD — SELL
- Prediction Accuracy: 70.2% (351/500)
- Last Confidence: 39%
- Signal Time: 2026-03-16 23:44 UTC
- Gate: 95 — **FAILS** (recommend lower to 75)
- Status: Good accuracy, needs gate adjustment

## Symbols to Watch
- **ETHUSD**: 64.9% accuracy, BUY signal — decent but low confidence (34%)
- **XAGUSD**: 54.8% accuracy — marginal, monitor for improvement

## Symbols to Avoid
- **XAUUSD**: 30.8% accuracy — worst enabled pair, add to weak pairs with gate 85
- **USDCHF**: 12.5% — blacklist
- **GBPUSD**: 9.7% — blacklist
- **USDJPY**: 2.5% — blacklist

## Bot Health Score: 2/10

| Component | Score | Notes |
|-----------|-------|-------|
| Code Integrity | 8/10 | 82/84 Python pass, 3 JSON corrupted |
| Data Integrity | 3/10 | Training data has only 1 sample, 3 corrupted JSON |
| Bot Uptime | 0/10 | Offline 54+ days |
| Trade Execution | 0/10 | 0 closed trades |
| ML Model | 1/10 | 91.8% train vs 30.8% live = 60% overfitting |
| Risk Management | 1/10 | 14 orphaned positions |
| **Overall** | **1/10** | **CRITICAL** |

## Priority Actions
1. Close 14 orphaned XAUUSD positions in MT5
2. Restart bot: `.venv\Scripts\python.exe safe_start.py`
3. Retrain ML with multi_agent_trainer.py
4. Lower BTCUSD gate from 95 to 75
5. Disable GBPUSD (gate → 100)

*Updated 2026-04-07 — Run 16 (Scheduled Monitor)*
