# 🎯 BILLIONAIRE SNIPER TRADING BOT - AI Agent Rules

> **THINK LIKE A BILLIONAIRE. ACT LIKE A BILLIONAIRE. WORK LIKE A BILLIONAIRE.**

## 💰 NON-NEGOTIABLE PROFIT RULES

| Metric | FIXED Value | NEVER Deviate |
|--------|-------------|---------------|
| **Risk:Reward Ratio** | **1:2 MINIMUM** | TP = 2× SL distance ALWAYS |
| **Win Rate Target** | **80-85%** | Quality > Quantity |
| **Max Risk Per Trade** | **1.5%** | Protect capital at all costs |
| **Min Confluences** | **5+** | NO trade without 5 confirmations |
| **Trades Per Day** | **5-6** | Scan ALL timeframes (M5→Daily) |

### ⚠️ CRITICAL: FIXED PROFIT ONLY
- **NEVER** lower the 1:2 RR ratio to get more trades
- **NEVER** widen stop loss without widening TP proportionally
- **NEVER** take Grade B/C setups - wait for A+ only
- **Trade AFTER the trap, not INTO the trap**

---

## 🏗 Architecture

| Component | File | Purpose |
|-----------|------|---------|
| Entry Point | `main.py` | Live/demo trading loop |
| Backtest | `run_backtest.py` | Historical simulation |
| Strategy | `src/strategy.py` | **5+ Confluence enforcement (SOLE decision maker)** |
| Indicators | `src/indicators.py` | AMD phases, EMA, RSI, Volume |
| Execution | `src/order_executor.py` | Trade placement (1:2 RR) |
| Risk | `src/risk_manager.py` | Position sizing (1.5% max) |
| Trade Recorder | `src/brain.py` | **Statistics ONLY - NO decision power** |
| Config | `config/settings.py` | Pairs, timeframes, parameters |

---

## 📊 MULTI-TIMEFRAME SCANNING (5-6 Trades/Day)

To achieve 5-6 quality trades daily, scan ALL timeframes simultaneously:

| Timeframe | Purpose | Scan Frequency |
|-----------|---------|----------------|
| **Daily** | Macro bias, liquidity zones | Once at session open |
| **H4** | Order blocks, structure | Every 4 hours |
| **H1** | Entry preparation, CHoCH/BOS | Every hour |
| **M15** | Sniper entries | Every 15 min |
| **M5** | Micro confirmation | Real-time |

### Trade Distribution Strategy
- Scan **12+ pairs** across all timeframes
- Each pair × 5 timeframes = 60+ opportunities/day
- Filter to **5-6 A+ setups** that meet ALL confluences

---

## ✅ MANDATORY ENTRY CHECKLIST (ALL 7 REQUIRED)

Before ANY signal generation, verify:
1. **Daily Liquidity Zone** - Price at major supply/demand
2. **H4 Order Block** - Near valid OB from structure
3. **Liquidity Sweep** - Stop hunt completed (wick beyond level)
4. **Structure Shift** - CHoCH or BOS on H1/M15
5. **Imbalance/FVG** - Strong displacement candle
6. **EMA Alignment** - 20 EMA crossed 50 EMA in trade direction
7. **Session Timing** - London or NY session only

**If < 5 conditions met → NO TRADE. Period.**

---

## 🛡️ Coding Rules

### PURE STRATEGY - NO SENTIMENT
- **ALL trade decisions come from technical strategy ONLY**
- `src/brain.py` is **record-only** - it tracks stats but NEVER gates/blocks trades
- NO sentiment analysis, NO news feeds, NO adaptive AI overrides
- Strategy confluences are the SOLE entry criteria
- Risk parameters are FIXED in config - never dynamically adjusted

### Strategy Modifications
- Read `BILLIONAIRE_AGENT_INSTRUCTIONS.md` before ANY strategy change
- `AMDStrategy.check_signals()` MUST enforce `min_confluences >= 5`
- TP calculation: `tp_price = entry + (2 * sl_distance)` - FIXED

### MT5 Interactions
```python
# Always convert MT5 data to lowercase DataFrame
df.columns = ['open', 'high', 'low', 'close', 'tick_volume', 'spread', 'real_volume']
df['time'] = pd.to_datetime(df['time'], unit='s')
```
- Call `mt5.initialize()` before API calls
- Call `mt5.shutdown()` in `finally` blocks

---

## 🚀 Commands

```bash
python main.py          # Live/Demo trading
python main.py --scan   # One-off market scan
python run_backtest.py  # Test strategy (expect 80%+ WR)
```

---

## 📂 Key Files
- `BILLIONAIRE_AGENT_INSTRUCTIONS.md` - **THE BIBLE** (read first)
- `src/strategy.py` - Decision engine (confluence checks)
- `config/settings.py` - Risk & pair settings

---
