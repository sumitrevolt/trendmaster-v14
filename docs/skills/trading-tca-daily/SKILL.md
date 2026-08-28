---
name: trading-tca-daily
description: Run a daily Transaction-Cost-Analysis scorecard for TrendMaster v14 — markout-30s, slip-bps per symbol/session, and adverse-selection flags from logs/deals or MT5 history. Use when the user asks for "TCA", "fill quality", "slippage report", "markout", "is the bot getting toxic fills", "post-trade analysis", or wants to compare today's execution quality against the trailing 30-day distribution.
---

# Trading TCA Daily

Generate a one-page Transaction-Cost-Analysis scorecard for TrendMaster v14. Surface what the cost-model in `tools/slippage_model.py` cannot: actual realized slip, markouts at +5s / +30s / +5min, and per-(symbol, session) percentile drift.

## When to invoke

- Operator asks for "TCA", "fill quality", "slippage", "markout", "post-trade".
- After any change to `OrderSend` parameters (deviation, filling mode).
- Weekly review — append the run to `logs/tca_history.parquet` and flag >2σ deterioration vs trailing 30-day.

## Inputs

The skill expects either:

1. `logs/trades.csv` — exported from MT5 via `HistoryDealsTotal()` loop, schema: `deal_id, time, symbol, type, price, volume, profit`.
2. `brain_memory.json::trade_history[]` — fallback if the deals export is missing. Note: this is also used for ML training, so cross-check `max(ts)` against now.
3. `logs/signal_history.jsonl` — for `intent_ts` and `intent_px`. Required to compute slip.

If no fresh deals (last 24h) exist, report that and exit cleanly. Do not fabricate.

## Output

Print to stdout AND append a row to `logs/tca_daily_history.parquet`:

```
TCA Daily — 2026-04-25
======================
Deals last 24h: 7
Filled symbols: XAUUSD x3, EURUSD x2, GBPUSD x1, BTCUSD x1

Slip (bps, mean / p50 / p95):
  XAUUSD  Tokyo    -0.4 / -0.2 / -2.1   [normal]
  XAUUSD  London   +0.3 / +0.1 / +1.4   [normal]
  EURUSD  London   -0.1 / 0.0  / -0.6   [normal]
  BTCUSD  NY       -3.8 / -2.9 / -9.4   [WIDE — investigate]

Markout-30s (bps, mean — negative = adverse selection):
  XAUUSD  -1.2   [normal]
  EURUSD  +0.4   [normal — paying spread but not adversely picked]
  BTCUSD  -6.7   [TOXIC — informed flow on the other side]

Trailing-30d drift:
  BTCUSD slip-p95 deteriorated 2.4σ vs 30d baseline.
  Recommend: tag last 24h BTCUSD entries for review; consider
  conf-floor bump to 0.65 on this symbol pending investigation.

Action items (auto):
  [ ] Inspect BTCUSD deals 4527-4533 in tools/diagnose_zero_trades.py
  [ ] Compare to days where BTCUSD markout-30s was healthy
  [ ] If pattern persists 3 days, file postmortem template
```

## How to call

```cmd
cd C:\Users\Ratanshila\Documents\autmated trading
.venv\Scripts\python.exe ${CLAUDE_PLUGIN_ROOT}\skills\trading-tca-daily\tca_helpers.py --window 24h --baseline 30d
```

Pass `--symbol XAUUSD` to focus on one pair, `--session London` to focus on one session, `--verbose` to dump per-deal rows.

## Critical guardrails

- **Demo broker caveat**: OctaFX-Demo fills are synthetic and understate live slippage by 30-60%. Report relative regime ranking, never absolute slip thresholds. State this explicitly in the output if `BROKER` env var contains "demo".
- **Sample-size guard**: Never flag a (symbol, session) bucket as "WIDE" or "TOXIC" with fewer than 5 deals in the bucket.
- **Don't suggest re-enabling spread_guard.** The operator policy `feedback_no_spread_gate` is non-negotiable; if the report would naturally lead there, suggest a per-symbol confidence-floor bump instead.

## Helper script

See `tca_helpers.py` next to this SKILL.md. The helper is import-safe — Claude can invoke it with `python -c` for ad-hoc queries.

## References

- Markout methodology: LSEG TCA framework, kdb+ TCA paper, BIS FX execution algos report.
- Schema: `references/tca-schema.md`.
