---
name: trading-events-rotator
description: Automatically rotate logs/events.jsonl when it exceeds 50MB; archive rotated copies and prune older than 30 days. Wires the previously-dead ai_trading_agents/ops_maintenance.vacuum_events function into a scheduled task. Use when the user asks "rotate events", "events.jsonl too big", "log rotation", "wire vacuum_events", or as a daily scheduled task.
---

# Trading Events Rotator

Closes the action item from the 2026-04-25 godmode-r2 postmortem: `ops_maintenance.vacuum_events` was defined but never called, so `events.jsonl` grew to 121 MB before manual intervention. This skill wires it to a scheduled task with sane defaults.

## When to invoke

- Scheduled task: daily at 03:30 local (during quiet market window).
- Operator manual: "rotate events.jsonl now".
- Before any backtest that reads events.jsonl (faster reads on small files).

## Behavior

| Condition | Action |
|---|---|
| `logs/events.jsonl` ≤ 50 MB | No-op; log "no rotation needed" |
| `logs/events.jsonl` > 50 MB | Rotate to `logs/events.jsonl.YYYY-MM-DD[.N]`; create empty new |
| Rotated archives older than 30 days | Optional: compress to `.gz`. Then prune > 90 days. |
| Brain currently has events.jsonl open | Use atomic-rename strategy: brain's open handle keeps writing to the renamed file until next reopen, new events.jsonl gets next batch. (Linux semantics; on Windows we may need to wait for next brain restart for the new file to be picked up — log a NOTE in that case.) |

## Output

```
Events Rotator — 2026-04-25 03:30 local
========================================
events.jsonl current size: 67.2 MB
Threshold: 50 MB → ROTATE

Rotated: logs/events.jsonl (67.2 MB) → logs/events.jsonl.2026-04-25
New empty events.jsonl created.

Archive housekeeping:
  events.jsonl.2026-03-25 (38d old, 41 MB) — compressed to .gz (saved 32 MB)
  events.jsonl.2026-01-15 (101d old) — pruned

Final state:
  events.jsonl: 0 bytes (empty, ready for new writes)
  events.jsonl.2026-04-25: 67.2 MB (rotated from today)
  events.jsonl.2026-03-25.gz: 9 MB (compressed)

NOTE: brain process is currently running (PID 33340). On Windows, the
brain may continue writing to the renamed events.jsonl until next
restart. Operator: restart brain at next opportunity to pick up new
empty file.
```

## How to call

```cmd
cd C:\Users\Ratanshila\Documents\autmated trading
.venv\Scripts\python.exe ${CLAUDE_PLUGIN_ROOT}\skills\trading-events-rotator\rotator.py
```

Pass `--threshold-mb N` to override the rotation threshold (default 50). Pass `--prune-days N` to override prune age (default 90). Pass `--compress-days N` to override compress age (default 30). Pass `--force` to rotate regardless of size.

## Schtask installation

```cmd
schtasks /create /sc DAILY /st 03:30 /rl LIMITED /f /tn "TrendMaster Events Rotator" ^
    /tr "cmd /c cd /d \"C:\Users\Ratanshila\Documents\autmated trading\" && .venv\Scripts\python.exe docs\skills\trading-events-rotator\rotator.py >> logs\events_rotator.log 2>&1"
```

## Critical guardrails

- **Never delete unrotated events.jsonl.** Always rename, then create empty new.
- **Atomic rename** — use `os.rename` (atomic on same volume).
- **Detect Windows brain-handle conflict** — on Windows, if the brain is running and has events.jsonl open, the rename will succeed BUT the brain keeps writing to the (now-renamed) old inode. New events.jsonl will be empty until brain restarts. Log this as a NOTE so operator knows to restart at next opportunity.
- **Never compress today's rotation** — leave .jsonl uncompressed for 30 days for easy `tail` / `grep` operator workflows.

## Helper script

`rotator.py` next to this SKILL.md.
