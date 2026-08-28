"""
schtasks_audit.py - meta-watchdog for Windows scheduled tasks.

Runs every 30 min via Scheduled Task "TrendMaster Schtasks Audit".
Reads each TrendMaster + OpenClaw scheduled task, checks LastRunTime
+ LastTaskResult vs expected cadence. Emits logs/schtasks_audit.alert
when any task drifted (which watch_pets then surfaces).

Why: 14 tasks watch the brain + ops. If one of THOSE tasks dies
(e.g., disabled by Windows update, missed run, persistent failure),
the visible watcher silently goes blind. This catches that.

Output:
  - logs/schtasks_audit.json   - full state per task (always written)
  - logs/schtasks_audit.alert  - present only when issues found

Exit codes:
  0 - all tasks healthy
  1 - one or more tasks unhealthy (alert file written)
  2 - audit itself errored

Pure stdlib + subprocess. No new dependencies.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
LOGS = PROJECT_ROOT / "logs"
LOGS.mkdir(exist_ok=True)

STATE_FILE = LOGS / "schtasks_audit.json"
ALERT_FILE = LOGS / "schtasks_audit.alert"

# Expected cadence for known tasks (in minutes). Audit warns if last run
# is older than 2x this (covers: missed run, paused task, taskhost down).
# Source: existing ScheduledTasks visible via Get-ScheduledTask 2026-04-28.
EXPECTED_INTERVAL_MIN = {
    "TrendMaster Watch-Pets":        5,
    "TrendMaster Brain Liveness":    5,
    "TrendMaster Junction Guard":    15,
    "TrendMaster Alert Bridge":      5,
    "TrendMaster Events Rotator":    60,
    "TrendMaster Code Graph Rebuild": 30,
    "TrendMaster Pytest Health Check": 240,
    "TrendMaster Walkforward Lab":   1440,    # daily
    "TrendMaster Morning Routine":   1440,    # daily
    "TrendMaster Zero Trades Watchdog": 1440, # daily
    "TrendMaster EA Parity Nightly": 1440 * 7 / 5,  # weekdays
    "TrendMaster Schtasks Audit":    30,      # this script's own task
    "TrendMaster Daily Summary":     1440,    # daily
    "OpenClaw Gateway":              0,       # always-on, not interval-based
    "OpenClaw Watchdog":             0,       # always-on
}

# Known good LastTaskResult codes:
#  0      - completed normally
#  267009 - "currently running" (always-on tasks)
#  267011 - "task has not yet run" (just-registered, fine)
#  1      - our scripts return 1 when severity>=ERROR (still ran ok)
GOOD_RESULT_CODES = {0, 1, 267009, 267011}


def _now_utc() -> datetime:
    return datetime.now(tz=timezone.utc)


def _powershell(cmd: str) -> str:
    """Run a PowerShell one-liner and return stdout text. Empty on failure."""
    try:
        r = subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command", cmd],
            capture_output=True, text=True, timeout=20, check=False,
        )
        return r.stdout or ""
    except Exception:
        return ""


def list_scheduled_tasks() -> list[dict]:
    """Return list of dicts for matching tasks."""
    cmd = (
        "Get-ScheduledTask | Where-Object { "
        "$_.TaskName -match '^TrendMaster|^OpenClaw' "
        "} | ForEach-Object { "
        "$info = $_ | Get-ScheduledTaskInfo; "
        "[PSCustomObject]@{"
        "TaskName=$_.TaskName; State=[string]$_.State; "
        "LastRunTime=if($info.LastRunTime){$info.LastRunTime.ToString('o')}else{$null}; "
        "LastTaskResult=$info.LastTaskResult; "
        "NextRunTime=if($info.NextRunTime){$info.NextRunTime.ToString('o')}else{$null}; "
        "NumberOfMissedRuns=$info.NumberOfMissedRuns "
        "} } | ConvertTo-Json -Depth 5 -Compress"
    )
    out = _powershell(cmd)
    if not out.strip():
        return []
    try:
        data = json.loads(out)
    except Exception:
        return []
    if isinstance(data, dict):
        data = [data]
    return data


def _parse_iso(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        # PowerShell .ToString('o') gives full ISO 8601
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


def audit_task(t: dict) -> dict:
    name = t.get("TaskName", "?")
    state = t.get("State")
    last_run = _parse_iso(t.get("LastRunTime"))
    last_result = t.get("LastTaskResult")
    missed = t.get("NumberOfMissedRuns") or 0

    interval = EXPECTED_INTERVAL_MIN.get(name, None)
    issues: list[str] = []

    # State must be Ready (between runs) or Running (always-on tasks)
    if state and state not in ("Ready", "Running"):
        issues.append(f"state={state}")

    # LastTaskResult should be in known-good set
    if last_result is not None and last_result not in GOOD_RESULT_CODES:
        issues.append(f"LastTaskResult={last_result}")

    # Cadence check (skip always-on tasks where interval=0)
    if interval and last_run:
        age_min = (_now_utc() - last_run).total_seconds() / 60
        if age_min > interval * 2:
            issues.append(
                f"last run {age_min:.0f}min ago, expected interval {interval}min"
            )

    # Missed runs > 2 means task was suspended or PC was off long enough
    if missed and missed > 2:
        issues.append(f"missed_runs={missed}")

    return {
        "name": name,
        "state": state,
        "last_run": last_run.isoformat() if last_run else None,
        "last_result": last_result,
        "missed_runs": missed,
        "expected_interval_min": interval,
        "issues": issues,
        "ok": not issues,
    }


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except Exception:
        pass

    try:
        tasks = list_scheduled_tasks()
    except Exception as e:
        print(f"audit fatal: {e}", file=sys.stderr)
        return 2

    if not tasks:
        print("No matching scheduled tasks found.")
        ALERT_FILE.write_text(
            f"[{_now_utc().isoformat()}] No TrendMaster/OpenClaw tasks visible. "
            "Check that schtasks/Get-ScheduledTask works in this user context.\n",
            encoding="utf-8",
        )
        return 1

    audits = [audit_task(t) for t in tasks]
    summary = {
        "ts": _now_utc().isoformat(),
        "task_count": len(audits),
        "issue_count": sum(1 for a in audits if not a["ok"]),
        "audits": audits,
    }

    try:
        STATE_FILE.write_text(
            json.dumps(summary, indent=2, default=str), encoding="utf-8"
        )
    except Exception:
        pass

    if summary["issue_count"] == 0:
        # all healthy — remove any stale alert file so watch_pets clears
        if ALERT_FILE.exists():
            try:
                ALERT_FILE.unlink()
            except Exception:
                pass
        print(
            f"OK - all {summary['task_count']} TrendMaster/OpenClaw tasks healthy"
        )
        return 0

    # write alert file with details
    bad = [a for a in audits if not a["ok"]]
    lines = [
        f"[{summary['ts']}] {len(bad)} of {summary['task_count']} tasks have issues:"
    ]
    for a in bad:
        lines.append(
            f"  - {a['name']:<35} {', '.join(a['issues'])}"
        )
    text = "\n".join(lines) + "\n"
    try:
        ALERT_FILE.write_text(text, encoding="utf-8")
    except Exception:
        pass
    print(text)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
