---
name: trading-brain-liveness
description: Detect a dead TrendMaster v14 brain within 5 minutes via PID + heartbeat + brain.err checks; page Telegram immediately. Designed for the 2026-04-25 silent-death pattern (brain stopped writing logs at 12:24, nobody noticed for 3+ hours). Use when the user asks "is brain alive", "brain liveness", "watchdog", "brain crash detection", "page me when brain dies", or as a scheduled task on a 5-min cadence.
---

# Trading Brain Liveness Watchdog

Detect a silently-dead brain within 5 minutes and page Telegram. The 2026-04-25 incident showed a brain can die without any traceback in `brain.err` (Defender / OneDrive may kill it cleanly). The only reliable signal is "no fresh log writes."

## When to invoke

- Scheduled task: every 5 minutes (`schtasks /create /sc MINUTE /mo 5 /tn "TrendMaster Brain Liveness"`).
- Operator manual check: "is brain alive right now?".
- Right after a brain restart (verifies the restart actually took).

## Liveness signals (in order of reliability)

| Check | Signal | Threshold |
|---|---|---|
| 1. brain.pid exists | PID file present | Required |
| 2. PID is alive | `psutil.pid_exists(pid)` | Required (uses psutil — installed 2026-04-25) |
| 3. PID is python.exe | Process name match | Required |
| 4. brain.log fresh | last write < 90 seconds ago | Required (warns at 90s, alerts at 180s) |
| 5. brain_state.json fresh | last write < 120 seconds | Required (warns at 120s, alerts at 240s) |
| 6. brain.err size | NOT growing | Warns if delta > 1 KB since last check |

If checks 1-5 all pass, brain is alive. If any of 1-3 fails OR (4 AND 5) fail with stale-by-180s, brain is DEAD — page immediately.

## Output

```
Brain Liveness Check — 2026-04-25 16:32 UTC
============================================
brain.pid file:           PRESENT  (33340)
PID alive:                YES       python.exe, uptime 2847s
brain.log freshness:      28s ago   (under 90s threshold) OK
brain_state.json freshness: 11s ago (under 120s threshold) OK
brain.err size delta:     0 bytes   no growth OK

VERDICT: ALIVE

(no Telegram page sent — only paged on DEAD verdict)
```

For DEAD verdict:

```
Brain Liveness Check — 2026-04-25 16:32 UTC
============================================
brain.pid file:           PRESENT  (33340)
PID alive:                NO        process not found
brain.log freshness:      4023s ago (>>180s threshold) STALE
brain_state.json freshness: 4031s ago STALE

VERDICT: DEAD

Telegram message sent:
"[TrendMaster ALERT] Brain DEAD as of 2026-04-25 16:32 UTC.
 Last log write 67 minutes ago. PID 33340 is gone.
 Restart via start_brain_clean.cmd (pre-flight will catch any
 import-time issues before mutating state)."
```

## How to call

```cmd
cd C:\Users\Ratanshila\Documents\autmated trading
.venv\Scripts\python.exe ${CLAUDE_PLUGIN_ROOT}\skills\trading-brain-liveness\liveness.py
```

Pass `--quiet-on-alive` to suppress the OK message (use this for the schtask). Pass `--no-telegram` to disable paging (test mode).

## Schtask installation (one-time setup)

```cmd
schtasks /create /sc MINUTE /mo 5 /rl LIMITED /f /tn "TrendMaster Brain Liveness" ^
    /tr "cmd /c cd /d \"C:\Users\Ratanshila\Documents\autmated trading\" && .venv\Scripts\python.exe docs\skills\trading-brain-liveness\liveness.py --quiet-on-alive >> logs\brain_liveness.log 2>&1"
```

Operator runs this once. Watchdog then runs every 5 min forever.

## Critical guardrails

- **Never auto-restart the brain.** Operator decides whether to run `start_brain_clean.cmd`. The skill pages, the operator acts.
- **De-duplicate alerts.** If brain has been DEAD for 30+ minutes and we've already paged, don't re-page every 5 min. Use `logs/brain_liveness_last_alert.txt` to track last-alert-ts.
- **Honor `state.trading_paused`** — if the operator deliberately paused the brain, don't page (different state.json field, but if pause + dead, treat dead as expected).

## Helper script

`liveness.py` next to this SKILL.md.
