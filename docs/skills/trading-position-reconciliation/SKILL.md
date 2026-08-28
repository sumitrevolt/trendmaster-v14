---
name: trading-position-reconciliation
description: Three-way reconcile TrendMaster v14's three sources of truth — live MT5 broker positions, brain_memory.json::open_positions, and logs/brain_state.json::open_positions. Flags any drift between the three (extra position, missing position, mismatched lot size, stale SL/TP). Use when the user asks "reconcile positions", "are my positions in sync", "MT5 vs brain mismatch", "position drift", "did the brain forget a trade", or as part of the daily morning routine.
---

# Trading Position Reconciliation

The brain has three places where "open positions" lives. They should always agree. When they disagree, you're one bad restart away from a double-fill or a forgotten stop-loss.

## The three sources of truth

| Source | What it stores | Updated by |
|---|---|---|
| **MT5 broker** | Authoritative open positions (the actual money at risk) | The exchange / broker |
| **`brain_memory.json::open_positions`** | What the brain *thinks* it opened | Brain on every tick that completes an order |
| **`logs/brain_state.json::open_positions`** | What the watchdog/dashboard reads | StateStore.save() at end of every tick |

Drift between any two is a precondition for one of three failure modes:

- **MT5 has, brain doesn't** — operator opened a manual trade, OR brain restarted before persisting after fill. Brain may try to re-enter the same position.
- **Brain has, MT5 doesn't** — broker rejected/closed (SL hit, margin call, manual close) and brain didn't observe. Brain treats the symbol as "blocked by max_open" forever.
- **state_store ≠ brain_memory** — atomic-write race; one was persisted before the other. Watchdog readouts will lie.

## When to invoke

- Operator asks "reconcile positions", "are positions in sync".
- Daily morning routine, before market open in operator timezone.
- Immediately after any unplanned brain restart.
- After any MT5 disconnect-reconnect cycle.

## Output

```
Position Reconciliation — 2026-04-25 09:14 local
================================================

MT5 broker (authoritative)         3 positions:
  XAUUSD long  0.10 lots @ 2342.50  SL 2335.20  ticket 4527181
  EURUSD long  0.20 lots @ 1.0682   SL 1.0651   ticket 4527205
  BTCUSD long  0.05 lots @ 67400    SL 66200    ticket 4527239

brain_memory.json::open_positions  4 positions:
  XAUUSD long  0.10 lots @ 2342.50  SL 2335.20
  EURUSD long  0.20 lots @ 1.0682   SL 1.0651
  BTCUSD long  0.05 lots @ 67400    SL 66200
  GBPUSD short 0.15 lots @ 1.2421   SL 1.2462   <-- NOT IN MT5

state_store.json::open_positions   3 positions:
  XAUUSD long  0.10 lots @ 2342.50
  EURUSD long  0.20 lots @ 1.0682
  BTCUSD long  0.05 lots @ 67400

DRIFT DETECTED:
  MT5 vs brain_memory:    GBPUSD short in brain_memory but NOT in MT5
                          (likely SL hit and brain didn't observe close)
  brain_memory vs state:  GBPUSD short in brain_memory but NOT in state
                          (atomic-write race; brain_memory was persisted later)

RECOMMENDED ACTIONS (run manually after confirming):
  1. Inspect MT5 history for GBPUSD ticket(s) closed in last 24h:
     .venv\Scripts\python.exe tools\diagnose_zero_trades.py --symbol GBPUSD --window 24h

  2. If close was legitimate (SL hit), prune from brain_memory:
     # in Python REPL:
     mem = json.loads(Path("brain_memory.json").read_text())
     mem["open_positions"] = [p for p in mem["open_positions"] if p["symbol"] != "GBPUSD"]
     Path("brain_memory.json").write_text(json.dumps(mem, indent=2))
     # then restart brain via start_brain_clean.cmd (NOT a force-kill)

  3. If close was unexpected (broker rejection, margin event), file postmortem:
     /skills trading-postmortem-new --slug gbpusd_unexpected_close ...

DO NOT use taskkill /F to "force-sync" — restart with the existing safe flow.
```

## How to call

```cmd
cd C:\Users\Ratanshila\Documents\autmated trading
.venv\Scripts\python.exe ${CLAUDE_PLUGIN_ROOT}\skills\trading-position-reconciliation\reconcile.py
```

Pass `--no-mt5` to skip the live broker query (useful when MT5 is disconnected — falls back to comparing the two file-based sources).

## Critical guardrails

- **Read-only.** This skill never modifies positions. It prints recommended commands the operator runs manually.
- **MT5 is authoritative.** When in doubt, MT5 wins; never overwrite MT5 state from a file.
- **Detect the atomic-write race specifically** — if `brain_memory.json::ts_persisted` differs from `state_store.json::ts_persisted` by <500ms and one has a position the other doesn't, log it as `RACE_SUSPECTED` rather than `STATE_DRIFT`.
- **Honor `state.trading_paused`** — if the brain is paused, drift is expected (no new entries to reconcile).

## Helper script

`reconcile.py` next to this SKILL.md. Uses MetaTrader5 Python module if available; degrades to file-only mode if not.

## References

- TrendMaster `ai_trading_agents/state_store.py::StateStore` — atomic-write semantics.
- MetaTrader5 `positions_get()` API.
- TrendMaster CLAUDE.md "logs/brain_memory.json trade_history[] is NOT live trade history" caveat.
