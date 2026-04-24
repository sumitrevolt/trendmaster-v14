---
name: trading-daily-pnl
description: "Generate today's PnL snapshot for TrendMaster v14 with per-team breakdown, open positions, drift status, and gate veto summary. Use for end-of-day review, investigating a bad day, or preparing a weekly digest. Reads logs/brain_state.json via daily_digest.generate_report — does not touch MT5 directly, safe to run while brain is live."
---

# trading-daily-pnl

Fast snapshot of where the book stands and what the brain actually did today. Single source of truth: `logs/brain_state.json` via `ai_trading_agents.daily_digest.generate_report()`.

## When to use

- End-of-trading-day review
- After a notable event (big win, big loss, halt trigger, news spike)
- Preparing a weekly or monthly digest for the record
- Before a brain restart — capture pre-restart state so you can diff afterwards

## Generate

From Python (matches what Telegram `/pnl` does):

```python
from pathlib import Path
from ai_trading_agents.daily_digest import generate_report
from ai_trading_agents.state_store import StateStore

state = StateStore(Path("logs/brain_state.json")).load()
report = generate_report(state, project_root=Path("."))
```

Or the one-shot CLI:

```
python main.py daily-report --telegram
```

The `--telegram` flag posts the markdown summary to the configured chat (creds in `config/.env`: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`).

## What's in the report

- `pnl.today`, `pnl.7d`, `pnl.30d`, `pnl.all_time` — realized PnL in account currency + R-multiples
- `per_team` — METALS, FOREX, CRYPTO, COMMODITIES: trades, wins, losses, net_R, hit_rate
- `open_positions` — symbol, direction, entry, current, unreal_pnl, bars_open
- `metrics` — rolling 30-day Sharpe, Sortino, Calmar
- `drift` — latest DriftMonitor state: `ACTIVE` / `WARN` / `HALT` and the feature drivers
- `gate_vetoes` — last 20 veto reasons, grouped by gate name
- `written_to` — `reports/daily_YYYY-MM-DD.md` and `.json`

## What to check first (in order)

1. **Open positions with deep unrealized loss**: any `unreal_pnl` more negative than `config.RISK.daily_max_drawdown_floor / open_positions_count` deserves a look before close.
2. **`drift.state == "HALT"`**: the brain self-halted. Do not override without reading the drivers. See `trading-debug` skill for recovery flow.
3. **Gate veto spikes**: if one gate name dominates `gate_vetoes` (e.g., `profit_optimizer` at 80%+ of all vetoes), a threshold is miscalibrated — pair with `trading-why-inspector` to dig in.
4. **Per-team skew**: if CRYPTO win rate is dramatically above the others (e.g., > 90% with low sample size), flag for the overfit check — see `tools/validate_crypto_ml.py`.

## Common follow-ups

- "Why didn't XAUUSD fire today?" → `trading-why-inspector` skill
- "Why did we enter at a bad price?" → inspect `logs/trades_executed.jsonl` + the signal JSON written at entry time
- "Was there a news event we missed?" → check `data/news_calendar.json` windows vs trade timestamps
