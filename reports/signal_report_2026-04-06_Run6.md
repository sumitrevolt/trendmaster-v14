# Signal Report — 2026-04-06

## Current Market Conditions
**UNKNOWN** — Bot is offline. No market data being collected.

## Active Positions
14 orphaned XAUUSD SELL positions (Feb 12-13, 2026)
- Entry range: $4,923 - $5,063
- Status: Unmanaged for 53+ days
- Action: CLOSE IMMEDIATELY

## Top 3 Strongest Signals
**NONE** — No signals being generated.

## Bot Health Score: 1/10

| Category | Score | Notes |
|----------|-------|-------|
| Uptime | 0/3 | Offline 53+ days |
| Position Management | 0/2 | 14 orphaned trades |
| Trade Execution | 0/2 | 0 closed trades ever |
| ML Model | 0.5/1.5 | Severe overfitting (90.5% vs 20.5% real) |
| Data Integrity | 0.5/1.5 | Windows CR corruption in 3 files |
| **TOTAL** | **1/10** | **CRITICAL** |

## Recommendations
1. Close orphaned positions before any restart
2. Focus bot on XAUUSD only (82.4% training accuracy)
3. Fix ML overfitting before trusting model predictions
4. Implement proper holdout testing
