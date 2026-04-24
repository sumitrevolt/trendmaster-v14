---
name: trading-zero-trades
description: "Diagnose why the TrendMaster brain is running but placing zero trades. Classifies the state into OK / HALTED / MODEL_UNIFORM / CONF_BELOW_THRESHOLD / INSUFFICIENT_STATE with remediation steps. Use whenever `tick_all summary: NONE=N` dominates the log, Telegram /pnl shows flat, or the zero-trades watchdog alert fires."
---

# trading-zero-trades

The definitive "why are we not trading" diagnostic. Reads
`logs/brain_state.json` and the latest brain log; no MT5 touch, no
process interference, safe to run at any time.

## When to use

- Telegram `/pnl` shows zero activity for a day or more
- Brain log shows `tick_all summary: NONE=N` for every tick
- The zero-trades watchdog just posted a STALE or MODEL_STUCK alert
- Right after any brain restart, to confirm the new state is healthy
- Before escalating to "restart the brain" - this usually tells you
  whether a restart will help

## Run

From repo root:

```
python tools\diagnose_zero_trades.py
```

Output has a single verdict plus remediation bullets. The tool is
self-contained and prints one of these:

| Verdict              | Meaning                                                                 |
|----------------------|-------------------------------------------------------------------------|
| OK                   | Confidence clears MIN_CONF for some symbols; zero trades is market-driven. |
| HALTED               | `halted` or `trading_paused` flag is on. Telegram `/resume` or clear manually. |
| MODEL_UNIFORM        | Confidences clustered near 1/K with near-zero std across diverse markets - feature alignment / broken model. |
| CONF_BELOW_THRESHOLD | Model has variance but never clears MIN_CONF - gate too strict for current regime. |
| INSUFFICIENT_STATE   | State file empty or brain not running long enough to diagnose.          |

## Interpreting MODEL_UNIFORM specifically

This was the root cause of the 2026-04-24 incident. Signature:

- 18+ symbols from totally different markets (metals, forex, crypto, commodities)
- confidence `std < 0.05`
- mean in `[0.28, 0.40]` (near 1/3, signature of a 3-class classifier
  returning uniform probability)

If you see this, the fix is:

1. Check the boot-time audit line in `logs/trend_master_brain.out`:
   `ML feature audit: order_match=True/False ...`.
2. If `order_match=False`, the `ai_trading_agents.ml_align`
   reindexing should still be working, but something is broken
   further downstream. Follow the full postmortem recovery path.
3. If `order_match=True`, the issue is data-quality (NaN features,
   stale bars). Dig into `pull_bars` output.

## Pairs well with

- `trading-brain-restart` - if the diagnostic says the fix needs a
  restart, that skill has the safe restart sequence.
- `trading-why-inspector` - once the model is healthy, drill into
  which specific gate is vetoing individual symbols.

## Preventative automation

The `zero-trades watchdog` (`tools/zero_trades_watchdog.py`, installed
via `install_zero_trades_watchdog.bat`) runs daily at 09:00 local and
posts a Telegram alert if the symptom returns. Keeps the
47-day-silent-failure from repeating.

## Full postmortem

See `docs/POSTMORTEMS/2026-04-24_zero_trades.md` for the 2026-04-24
incident - timeline, root cause, fix, and lessons.
