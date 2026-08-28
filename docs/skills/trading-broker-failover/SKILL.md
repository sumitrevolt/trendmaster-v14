---
name: trading-broker-failover
description: Detect when MT5 broker connection has failed (or is degrading) and produce the exact close-only / pause / failover commands the operator should run. Never auto-executes any P&L action — prints the playbook only. Use when the user asks "MT5 disconnected", "broker is down", "failover", "what do I do when OctaFX dies", "my brain can't reach the broker", or after `terminal_info().connected == False` for >5 minutes.
---

# Trading Broker Failover

A live trading bot has exactly two safe states when the broker is unreachable: **flat** or **frozen**. Anywhere in between is a leak. This skill produces the playbook to reach one of those two states deterministically, without auto-executing the P&L-affecting parts.

## When to invoke

- `MetaTrader5.terminal_info().connected == False` for more than 3 consecutive 5-second polls.
- `OrderSend` retcodes 10004 (requote storm), 10006 (timeout), 10009 (invalid stops) clustering.
- `state.last_tick_ts` stale > 180 seconds.
- Operator notices Telegram alerts mentioning "MT5 connection lost".
- Quarterly drill (the runbook needs to be muscle memory).

## The three failover modes

| Mode | When to choose | What changes |
|---|---|---|
| **A. Pause-in-place** | Disconnect <2 minutes, no urgent positions. | `state.trading_paused = True`. Don't touch positions. Resume when reconnected. |
| **B. Close-out-only** | Disconnect 2-15 minutes OR positions exist with no SL OR a critical news event is live. | Pause new entries; for each open position, close at market via the broker's web/mobile interface (NOT via brain). Once flat, set trading_paused=True. |
| **C. Hard halt + investigate** | Disconnect >15 minutes OR repeated retcode 10006 OR margin level approaching threshold. | Close all positions via broker UI. Stop the brain process via `start_brain_clean.cmd --stop`. File postmortem. Do not restart until root cause known. |

The skill diagnoses which mode applies and prints the matching playbook.

## Output

```
Broker Failover Triage — 2026-04-25 14:32 UTC
=============================================

Connection status:
  MT5 terminal connected:    NO  (last successful poll 7m12s ago)
  Last successful tick:      2026-04-25 14:25:18 UTC
  Recent OrderSend retcodes: 10006 x3, 10006 x1 (timeouts clustering)

Open positions snapshot (from brain_memory.json — may be stale):
  XAUUSD long  0.10 lots  SL 2335.20  current PnL est: +$12
  EURUSD long  0.20 lots  SL 1.0651   current PnL est: +$3
  BTCUSD long  0.05 lots  SL 66200    current PnL est: -$8

Drawdown lockout active: NO
News blackout window: NO

==> RECOMMENDED MODE: B. CLOSE-OUT-ONLY
    Reason: 7m disconnect + open positions exist; not yet a hard halt
            but past the pause-in-place window.

PLAYBOOK (execute manually in this order):

1. Pause new entries via Telegram:
   /halt-team all

2. Verify pause took effect (file log):
   .venv\Scripts\python.exe tools\diagnose_zero_trades.py

3. Open OctaFX-Demo web/mobile interface (NOT MT5 desktop — it's the
   thing that's stuck) and close each open position at market:
       https://my.octafx.com  → Trading → Positions
   Do this for: XAUUSD, EURUSD, BTCUSD (3 positions).

4. Once flat, persist the new state:
   .venv\Scripts\python.exe -c "from ai_trading_agents.state_store import StateStore; s=StateStore(); st=s.load(); st['open_positions']=[]; st['trading_paused']=True; s.save(st)"

5. Wait for MT5 desktop to reconnect (visible in terminal: green status).
   When connected, run trading-position-reconciliation to confirm broker
   reports zero open positions.

6. If reconnect doesn't happen within 15 more minutes, escalate to MODE C:
   stop the brain via start_brain_clean.cmd --stop and file postmortem
   via trading-postmortem-new.

DO NOT:
  - Restart the brain blindly. ml_align would catch most issues but a
    restart at 10006-cluster time often makes things worse.
  - Use taskkill /F to kill MT5 desktop. Use the in-app File → Quit.
  - Try to close positions via OrderSend from the brain — that's the
    very thing currently failing.
  - Lower MIN_CONF or re-enable spread_guard "to make trades again". Operator policy.

After resolution, file postmortem:
  .venv\Scripts\python.exe docs\skills\trading-postmortem-new\scaffold.py ^
    --slug octafx_disconnect_2026-04-25 ^
    --detection 2026-04-25T14:25:18Z ^
    --summary "OctaFX-Demo MT5 disconnect ~7m; 3 positions closed via web UI."
```

## How to call

```cmd
cd C:\Users\Ratanshila\Documents\autmated trading
.venv\Scripts\python.exe ${CLAUDE_PLUGIN_ROOT}\skills\trading-broker-failover\failover.py
```

Pass `--mode B` to force a specific mode (useful for drills). Pass `--dry-run` to print the playbook without checking live MT5.

## Critical guardrails

- **NEVER auto-close positions.** Operator clicks the broker UI; that's the only safe place a P&L-affecting action can originate during a broker incident.
- **NEVER auto-restart the brain.** A restart while the broker is partially-responsive is exactly how you turn a 5-minute incident into a 50-minute one.
- **The web/mobile broker interface and the MT5 desktop are different code paths.** When MT5 desktop is stuck, the web interface usually still works. Trust the web/mobile path.
- **Honor existing `state.drawdown_lockout_until`** — if a drawdown lockout is already active, don't recommend additional pauses.
- **Quarterly drill is required.** Run `--mode B --dry-run` once a quarter so the playbook stays in muscle memory.

## Helper script

`failover.py` next to this SKILL.md.

## References

- TrendMaster `ai_trading_agents/state_store.py::StateStore.save()` — atomic write with `trading_paused`.
- MetaTrader5 `terminal_info()` API.
- MQL5 forum 2024-2026 on retcode 10006 / disconnection patterns.
- TrendMaster postmortem template via `trading-postmortem-new`.
