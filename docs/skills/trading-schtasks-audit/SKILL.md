---
name: trading-schtasks-audit
description: Audit the three TrendMaster v14 Windows scheduled tasks (zero-trades watchdog, EA parity nightly, brain heartbeat) against the seven reliability flags — runs whether logged on, runs with highest privileges, runs on AC and battery, wakes the computer, restarts on failure, has a runtime cap, and produces a heartbeat file. Use when the user asks "audit my scheduled tasks", "schtasks healthcheck", "are the watchdogs running properly", "did Windows kill my brain again", or after laptop sleep / Defender quarantine incidents.
---

# Trading Schtasks Audit

Confirm the seven Windows reliability flags on the three TrendMaster scheduled tasks. Catches the laptop-asleep / Defender-quarantine / battery-only-failed-to-run class of incidents that produce silent gaps in the trading day.

## When to invoke

- Operator asks "audit scheduled tasks", "schtasks healthcheck".
- After laptop sleep, hibernate, or unplugged-then-plugged.
- After Defender quarantine event (you had 34 files quarantined recently).
- Weekly preventative — Sunday before market open is the canonical slot.
- After any Windows update or major .venv change.

## The seven reliability flags (per task)

| # | Flag | Why |
|---|---|---|
| 1 | `RunLevel = HighestAvailable` | Required for full file/network access on a scheduled run. |
| 2 | `LogonType = InteractiveOrPassword` AND configured to "Run whether user is logged on or not" | Survives the user logging out / locking the screen. |
| 3 | `Conditions/RunOnlyIfIdle = false` | Trading tasks must run even when the screen is active. |
| 4 | `Conditions/StartOnlyIfACPowerSource = false` | Laptops must run on battery during the trading day. |
| 5 | `Conditions/WakeToRun = true` AND Power Options → "Allow wake timers" enabled | Survives system sleep without missing the run. |
| 6 | `Settings/RestartOnFailure` set to "every 1 minute, 3 attempts" | Recovers from one-off transient failures. |
| 7 | `Settings/ExecutionTimeLimit ≤ PT1H` | Caps runaway runs that would block the next slot. |

Plus a deployment check: each task's executable path is on the Defender exclusion list (`C:\Users\…\autmated trading\` and `.venv\`).

## The three tasks audited

| Task name | Schedule | Runs |
|---|---|---|
| `TrendMaster Zero Trades Watchdog` | Daily 09:00 local | `tools/zero_trades_watchdog.py` |
| `TrendMaster EA Parity Nightly` | Mon-Fri 02:30 local | `tools/ea_parity_nightly.py` |
| `TrendMaster Heartbeat` | Every 5 min | touches `logs/heartbeat.txt` (paged at >10min stale) |

If `TrendMaster Heartbeat` doesn't exist, the audit recommends creating it — it catches scheduler-itself failures that the other two tasks can't.

## Output

```
Schtasks Audit — 2026-04-25 09:14 local
=======================================

TrendMaster Zero Trades Watchdog
  [PASS] RunLevel = HighestAvailable
  [PASS] Run whether user is logged on or not
  [PASS] RunOnlyIfIdle = false
  [FAIL] StartOnlyIfACPowerSource = true   <-- WILL NOT RUN ON BATTERY
  [PASS] WakeToRun = true
  [PASS] RestartOnFailure: 1min × 3 attempts
  [PASS] ExecutionTimeLimit = PT30M
  Recommendation:
    schtasks /Change /TN "TrendMaster Zero Trades Watchdog" /DISABLE
    schtasks /Change /TN "TrendMaster Zero Trades Watchdog" /RU SYSTEM /RP ""
    (then re-export XML, set <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>,
     re-import via /XML)

TrendMaster EA Parity Nightly
  All 7 flags PASS
  Last run: 2026-04-25 02:30:14 (success)

TrendMaster Heartbeat
  [MISSING] Task does not exist
  Recommendation: Create with:
    schtasks /Create /TN "TrendMaster Heartbeat" /TR "cmd /c echo. > C:\Users\...\heartbeat.txt"
                    /SC MINUTE /MO 5 /RL HIGHEST /F

Defender exclusions:
  [PASS] C:\Users\Ratanshila\Documents\autmated trading\ excluded
  [PASS] C:\Users\Ratanshila\Documents\autmated trading\.venv\ excluded
  [WARN] No exclusion for ai_trading_agents\ml_models\*.lgb (Defender flagged
         these as suspicious last quarter — confirm policy is permanent).

Summary: 2/3 tasks healthy; 1 has battery-policy issue; Heartbeat missing.
```

## How to call

```cmd
.venv\Scripts\python.exe ${CLAUDE_PLUGIN_ROOT}\skills\trading-schtasks-audit\audit.py
```

Pass `--task <name>` to focus on one. Pass `--fix` to print the exact `schtasks` commands needed to fix any FAIL findings (does NOT execute them — operator must run).

## Critical guardrails

- **Never auto-modify scheduled tasks.** Print the recommended commands; operator runs them. A scheduled-task delete by accident at 02:00 is exactly the kind of incident this skill exists to prevent.
- **Don't suggest disabling RestartOnFailure** even if a task is currently failing — diagnose root cause first.
- **Never recommend hibernate-friendly settings.** Use sleep S3 only; hibernate causes the "Resuming Windows" hang that's bitten the operator before.

## Helper script

`audit.py` next to this SKILL.md. Uses `schtasks /query /xml` and parses output; does not require admin elevation to read.

## References

- Microsoft Learn Q&A 1621913 (wake from sleep).
- Eleven Forum thread 27341 (Task Scheduler troubleshooting).
- TrendMaster `start_brain_clean.cmd` for parallel restart conventions.
