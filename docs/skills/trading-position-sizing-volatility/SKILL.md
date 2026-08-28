---
name: trading-position-sizing-volatility
description: Volatility-targeted position sizing using ATR + fractional Kelly. Use when the operator asks "how big should the next trade be?", "is 0.01 lot too small / too big for XAUUSD?", "what's my optimal risk per trade?", "calculate Kelly fraction from recent results", or when reviewing whether the static 0.5% RISK_PERCENT is right for current volatility regime.
---

# Volatility-targeted position sizing

## When to invoke

Operator wants to:
- Compute optimal position size for a specific (symbol, current ATR, account equity) tuple
- Translate a risk budget (e.g. 0.5% of equity) into actual lots given the SL distance in price
- Apply Kelly fraction (Half / Quarter Kelly) to recent (win_rate, avg_R) history
- Check if the static `RISK_PERCENT=0.5` in `config/.env` is leaving alpha on the table OR is too aggressive given recent drawdown

## Core math

### A. Risk-budget → lots (the canonical formula MT5 EA uses)

```
sl_distance_price  = entry_price - sl_price                  (for BUY)
sl_distance_pips   = sl_distance_price / pip_value
risk_dollars       = equity * (RISK_PERCENT / 100)           e.g. 1146 * 0.005 = $5.73
pip_value_per_lot  = 10 USD per pip per 1 lot (USDJPY ≈ $9.5/pip; XAUUSD = $10/pip)
lots               = risk_dollars / (sl_distance_pips * pip_value_per_lot)
```

For XAUUSD: SL at 50 pip distance, risk $5.73 → lots = 5.73 / (50 * 10 * 0.01) = 0.0114, round to 0.01.

### B. Volatility-targeted scaling

Adjust risk_pct by ratio of current ATR to the symbol's median ATR:

```
atr_ratio        = current_atr_h1 / median_atr_h1_30d
sized_risk_pct   = base_risk_pct * (1 / atr_ratio)
                   (caps: min=base*0.5, max=base*2.0)
```

Logic: when the market is 2x more volatile than usual, halve risk; when 0.5x, double risk (within caps).
Source: López de Prado AFML Ch.10, "Bet Sizing"; QuantStart equal-volatility allocation.

### C. Half-Kelly from recent stats

```
win_rate  = winners / total_trades                            (last 50-200 trades)
avg_win_R = mean(R-multiples of winners)                      e.g. +1.5R
avg_loss_R = mean(R-multiples of losers)                      e.g. -1.0R (always 1R if SL hit)
b         = avg_win_R / avg_loss_R                            "edge ratio"
k_full    = win_rate - (1 - win_rate) / b
half_kelly = k_full / 2                                       most retail uses Half Kelly
```

If half_kelly > 0.02 (2%), consider raising risk_pct toward it; if half_kelly < 0, your strategy is negative-edge and **stop trading**, don't size larger.

## Project-specific data sources

| Path | What |
|---|---|
| `logs/brain_state.json::recent_results` | Last N closed trade R-multiples |
| `logs/brain_memory.json::trade_history[]` | Longer history (incl. backtest seed) |
| `data/<symbol_lower>_m5_history.csv` | OHLCV for ATR calc |
| `config/.env::RISK_PERCENT` | Current static risk budget (default 0.5) |
| `config/settings.py::PAIR_PARAMS[<sym>]::sl_atr_mult` | Per-pair SL distance in ATR units |
| `MT5 account.equity` (live) | Current equity for lot calc |

## Quick calculator script

```python
# outputs/sizing_calc.py
import os, MetaTrader5 as mt5
from dotenv import load_dotenv; load_dotenv("config/.env")
mt5.initialize(login=int(os.getenv("MT5_LOGIN")),
               password=os.getenv("MT5_PASSWORD"),
               server=os.getenv("MT5_SERVER"))
ai = mt5.account_info()
sym = "XAUUSD"
risk_pct = float(os.getenv("RISK_PERCENT", "0.5"))
risk_usd = ai.equity * risk_pct / 100
sl_atr_mult = 1.0   # from PAIR_PARAMS
# Get current ATR from MT5 H1 bars
import MetaTrader5 as mt5
import pandas as pd
bars = pd.DataFrame(mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_H1, 0, 50))
bars['hl'] = bars['high'] - bars['low']
atr = bars['hl'].rolling(14).mean().iloc[-1]
sl_distance = atr * sl_atr_mult
si = mt5.symbol_info(sym)
pip_value = (si.trade_tick_value / si.trade_tick_size) * si.point
lots = risk_usd / (sl_distance * pip_value)
lots = round(lots / si.volume_step) * si.volume_step
print(f"{sym}: equity=${ai.equity:.2f}  risk=${risk_usd:.2f}  ATR={atr:.4f}  sl_dist={sl_distance:.4f}  lots={lots}")
mt5.shutdown()
```

## Operator policy (CLAUDE.md invariants)

- `RISK_PERCENT=0.5` is the floor — never go below 0.25%, never above 2% without explicit operator approval
- Half-Kelly is the cap — never use Full Kelly even if math suggests it (psychological + DD survival)
- After any 3% daily DD breach, halve `RISK_PERCENT` for the next 5 trading days
- After 5 consecutive winning days, may increase `RISK_PERCENT` by 25% step (max 2x base)

## When to update settings

1. Compute current half_kelly + atr-adjusted risk
2. If significantly different from `RISK_PERCENT=0.5`, propose a settings change
3. Update via `config/.env` (sync to settings.py if cached)
4. Restart brain via `RESTART_BRAIN_NOW.cmd`
5. Log decision in `docs/POSTMORTEMS/risk_changes.md`

## Related

- `trading-risk-ops` — broader risk policies
- `trading-cost-attribution` — how costs eat the risk budget
- `tools/kelly_sizer.py` — existing Kelly module in brain (currently in shadow mode)
