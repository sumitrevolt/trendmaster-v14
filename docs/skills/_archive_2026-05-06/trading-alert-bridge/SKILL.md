---
name: trading-alert-bridge
description: File-watcher that converts logs/*.alert files (pytest_health.alert, zero_trades.alert) and new logs/drift_alerts.jsonl entries into Telegram messages. Replaces silent file drops with actual pages. Use when the user asks "alert bridge", "alerts to telegram", "why didn't I get paged", "wire up alerts", or as a 1-min scheduled task.
---

# Trading Alert Bridge

Existing watchdogs (`pytest_health_check.cmd`, `zero_trades_watchdog.py`) and the drift detector all write to local files when they detect issues. **None of them currently page Telegram.** This skill is the bridge.

## When to invoke

- Scheduled task: every 1 minute (`schtasks /sc MINUTE /mo 1`).
- Operator manual: "send any pending alerts I missed".
- After clearing an alert: re-run to confirm queue is empty.

## Sources monitored

| Source | Format | Trigger |
|---|---|---|
| `logs/pytest_health.alert` | text file | Created by `pytest_health_check.cmd` on collection error |
| `logs/zero_trades.alert` | text file | Created by `zero_trades_watchdog.py` on N>thresholds |
| `logs/drift_alerts.jsonl` | JSON-per-line | Appended by `drift_detector.ADWINDriftDetector` |
| `logs/brain.crash` | text file | Created by `start_brain_clean.cmd` pre-flight failure (future) |

For each source, the bridge tracks last-processed offset/timestamp in `logs/alert_bridge_state.json`, so each entry is paged exactly once.

## Output

```
Alert Bridge — 2026-04-25 16:45 UTC
====================================

pytest_health.alert:    not present (no current alert)
zero_trades.alert:      not present (no current alert)
drift_alerts.jsonl:     0 new entries since last check
brain.crash:            not present

VERDICT: NO PENDING ALERTS

(no Telegram messages sent)
```

For active alerts:

```
Alert Bridge — 2026-04-25 16:45 UTC
====================================

pytest_health.alert:    PRESENT (created 5m ago, content: "Collection errors at 16:40")
zero_trades.alert:      not present
drift_alerts.jsonl:     2 new entries since last check
brain.crash:            not present

VERDICT: 3 ALERTS QUEUED FOR DISPATCH

Telegram messages sent:
  [1] [TrendMaster ALERT] pytest collection error at 16:40 — see logs/pytest_health.alert
  [2] [TrendMaster ALERT] Drift detected on CRYPTO/ema_stack — adwin fired 16:42
  [3] [TrendMaster ALERT] Drift detected on FOREX/rsi — adwin fired 16:43

State file updated; same alerts will not re-page on next run.
```

## How to call

```cmd
cd C:\Users\Ratanshila\Documents\autmated trading
.venv\Scripts\python.exe ${CLAUDE_PLUGIN_ROOT}\skills\trading-alert-bridge\bridge.py
```

Pass `--quiet` to suppress all output if no alerts (good for schtask). Pass `--reset-state` to mark all current entries as seen (use after operator manually clears alerts).

## Schtask installation

```cmd
schtasks /create /sc MINUTE /mo 1 /rl LIMITED /f /tn "TrendMaster Alert Bridge" ^
    /tr "cmd /c cd /d \"C:\Users\Ratanshila\Documents\autmated trading\" && .venv\Scripts\python.exe docs\skills\trading-alert-bridge\bridge.py --quiet >> logs\alert_bridge.log 2>&1"
```

## Critical guardrails

- **Idempotent.** Same alert MUST NOT page twice. State tracking via `alert_bridge_state.json`.
- **Rate limit.** Max 10 Telegram messages per minute (avoid bot rate limiting).
- **No auto-clear.** The bridge READS alert files but does NOT delete them. Operator decides when to clear (alert files act as audit log too).
- **Telegram failure is logged, not raised.** If Telegram is down, alerts queue in `logs/alert_bridge_failures.log` for retry on next cycle.

## Helper script

`bridge.py` next to this SKILL.md.
