---
name: amd-trading-bot-ops
description: Operate, debug, and extend the AMD Smart Money Forex Trading Bot in this repo — the MT5 Expert Advisor (AI_SUPERBB_v14_TrendMaster.mq5), the Python AI brain (ai_trading_agents/trend_master_brain.py), the multi-agent voting layer (multi_agent.py), and the brain↔EA JSON handshake. Use when the user asks to start/stop the bot, retrain the brain, debug a missed/bad trade, tune confluence thresholds, work with brain_memory.json or agent_learnings_*.json, compile or inject the EA, or change the M5/M15/H1 multi-timeframe logic.
---

# AMD Smart Money Forex Bot — Operations Skill

This skill captures everything specific to **this repo's** automated forex
trading system so Claude can act like a teammate who already knows it.

## Architecture in 30 seconds

```
   MetaTrader 5 (terminal)
   └─ AI_SUPERBB_v14_TrendMaster.mq5  ← Expert Advisor
          │   reads:  data/ai_signal_<SYMBOL>.json
          │   writes: trade events → logs/
          ▼
   Python AI Brain (ai_trading_agents/trend_master_brain.py)
   ├─ Multi-Timeframe features (M5 / M15 / H1)
   ├─ LightGBM / XGBoost classifier
   ├─ Multi-Agent voting (multi_agent.py — H4/H1/M30 unanimous)
   └─ Self-Learning Brain (trend_master_brain.py)
        ├─ logs/brain_memory.json          ← feature weights, win/loss
        └─ ai_trading_agents/agent_learnings_{forex,crypto,metals}.json
```

Trade fires only when **EA 3-of-3 confluence** AND **brain.confidence >= 0.58**
AND (when enabled) **multi-agent unanimous vote**.

## Key files

| File | Purpose |
|------|---------|
| `AI_SUPERBB_v14_TrendMaster.mq5` | MQL5 EA — execution, risk, trailing |
| `ai_trading_agents/trend_master_brain.py` | Python brain — features + ML + JSON write |
| `ai_trading_agents/multi_agent.py` | Rule-based H4/H1/M30 agents (audit layer) |
| `config/settings.py` | All tunable thresholds (risk %, confluence, conf min) |
| `tools/compile_ea.py` | MetaEditor headless compile |
| `tools/inject_ea_into_chart.py` | Push fresh EA to running MT5 chart |
| `tools/train_v14_better.py` | Retrain LightGBM brain from collected trades |
| `tools/live_brain_check.py` | Verify brain JSON output is fresh & valid |
| `START_TRENDMASTER_v14.bat` / `STOP_..._v14.bat` | Convenience launchers |
| `logs/brain_memory.json` | Persisted feature weights (do **not** delete blindly) |

## Common workflows

### 1. "The bot isn't trading"

Check in this order — most failures come from item 1 or 2:

1. **Brain JSON is stale.** `python tools/live_brain_check.py` — confirms
   `data/ai_signal_<SYMBOL>.json` `ts` is within ~30 s. If stale, the brain
   loop crashed; check `logs/brain_*.log`.
2. **MT5 → Python connection.** Brain needs MT5 terminal *running and
   logged in* on the same machine; `MetaTrader5.initialize()` returns False
   if the terminal isn't open.
3. **Confluence too tight.** In `config/settings.py`, `MIN_CONFIDENCE`
   (default 0.58) and `REQUIRED_CONFLUENCES` (default 3) suppress signals.
   Lower temporarily to 0.50 / 2 to confirm signal flow before tuning.
4. **Symbol disabled.** `SYMBOLS_ENABLED` list in `settings.py`.
5. **Spread filter.** EA's `InpMaxSpread` rejects if broker spread > X
   points — common on OctaFX-Demo overnight.

### 2. "Retrain the brain"

```bash
# 1. Collect more data first by letting the bot run on demo
# 2. Retrain (writes new model to logs/brain_v14.pkl, backs up old)
python tools/train_v14_better.py --symbols EURUSD,XAUUSD --min-trades 200

# 3. Smoke test
python tools/smoke_v14_brain.py

# 4. Restart brain only (EA can keep running)
python ai_trading_agents/trend_master_brain.py
```

Always **back up `logs/brain_memory.json`** before retraining — feature
weights are accumulated from live trade outcomes and represent real-money
learning that retraining can clobber.

Before any retrain promotion to live, run walk-forward validation
(see `walk-forward-optimization` skill) to confirm the new model isn't
overfit to the recent training window.

### 3. "Push a new EA build to MT5"

```bash
python tools/compile_ea.py            # headless MetaEditor compile -> .ex5
python tools/inject_ea_into_chart.py  # reattaches to live chart, no restart
```

If `compile_ea.py` fails with "MetaEditor not found", run
`tools/find_mt5.py` to discover the install path and update
`config/settings.py:METAEDITOR_PATH`.

### 4. "Investigate a bad trade"

The audit trail lives in three places:

- `logs/trades_<date>.log` — EA's view (entry, SL/TP, exit reason)
- `logs/brain_<date>.log` — brain's confidence at signal time
- `ai_trading_agents/prediction_memory.json` — last N predictions w/ features

Cross-reference timestamps. If brain confidence was high but trade lost,
the feature weights in `brain_memory.json` will auto-decrement on the
losing feature next cycle (this is the self-learning loop).

Also check: was the trade in a chop regime (`regime-detection` skill),
near a high-impact news release (`news-calendar-filter` skill), or
correlated with other open positions (`correlation-risk-controls` skill)?
Bad trades are usually one of those three patterns.

## Things to NOT do

- **Don't edit `*.json.bak` files** — those are atomic-write fallbacks.
- **Don't delete `brain_memory.json`** without backing it up — you lose
  every weight the bot has learned from real trades.
- **Don't change M5 timeframe** in EA without also updating
  `trend_master_brain.py:MTF_FRAMES` — they must match or the JSON
  handshake desyncs.
- **Don't put live credentials in committed code.** `config/.env` is
  gitignored; `config/.env.example` is the template.
- **Don't run two brain processes** against the same symbol — they'll
  race-write the JSON and the EA may read torn data (atomic write helps
  but isn't infinite).

## Tuning cheatsheet (config/settings.py)

| Knob | Default | Effect of raising |
|------|---------|--------------------|
| `MIN_CONFIDENCE` | 0.58 | Fewer trades, higher win rate |
| `REQUIRED_CONFLUENCES` | 3 | Fewer trades, higher conviction |
| `RISK_PERCENT` | 0.5 | Bigger positions, bigger drawdowns |
| `MAX_DAILY_TRADES` | 8 | More trades / day |
| `TRAIL_ATR_MULT` | 1.5 | Wider trailing stop, holds winners longer |
| `BRAIN_LEARN_RATE` | 0.05 | Weights move faster per trade outcome |

## Related skills in this repo

- `mql-developer` — full MQL5 reference for EA edits
- `backtesting-frameworks` — for validating strategy changes before live
- `risk-metrics-calculation` — Sharpe / Calmar / MaxDD on logged trades
- `walk-forward-optimization` — overfitting defense; run BEFORE every
  brain retrain or live promotion of new params
- `regime-detection` — sit-out logic for ranging/dead/news-spike markets
- `news-calendar-filter` — pause around NFP/FOMC/CPI using MT5's built-in calendar
- `correlation-risk-controls` — currency-bucket exposure caps when
  trading multiple symbols

### Routing cheatsheet

When the user asks…

- MQL5 syntax / CTrade / indicator buffers → `mql-developer`
- "Did this beat the benchmark?" / Sharpe / drawdown → `risk-metrics-calculation`
- "Brain works in backtest, fails live" → `walk-forward-optimization`
- "Why does it lose every trade in chop?" → `regime-detection`
- "It got crushed during NFP" → `news-calendar-filter`
- "Three trades all lost together" → `correlation-risk-controls`
- Anything brain↔EA glue (JSON contract, settings, retrain, compile) →
  this skill (`amd-trading-bot-ops`)

This skill owns the **glue** between EA and Python brain. The other
skills own the *trading craft* — they should be invoked alongside this
one whenever a change touches both glue and craft (which is most changes).
