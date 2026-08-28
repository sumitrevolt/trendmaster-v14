"""
stagger_team_crons.py — space out next-run times for the team cron jobs
so they don't all hit Copilot's API at the same moment after a gateway
restart. Resets consecutiveErrors=0 in the process.

Stagger plan (relative to now):
  trendmaster-health-check       +60s   trader heartbeat (cheap)
  trendmaster-debugger-hourly    +180s  3 min — only fires if brain.err > 0
  trendmaster-reviewer-6h        +300s  5 min — git log scan
  trendmaster-writer-daily       (kept on cron schedule 23:00 IST)
  trendmaster-architect-weekly   (kept on cron Sun 09:00 IST)
  trendmaster-researcher-weekly  (kept on cron Sat 10:00 IST)
  trendmaster-morning-brief      (kept on cron 08:30 IST)

Run:
    .venv\\Scripts\\python.exe tools\\stagger_team_crons.py
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

JOBS_PATH = Path(os.environ.get("USERPROFILE", "")) / ".openclaw" / "cron" / "jobs.json"

# Map job-name → seconds-from-now to fire next. None means leave the existing schedule alone.
STAGGER_OFFSETS_S = {
    "trendmaster-health-check":     60,
    "trendmaster-debugger-hourly":  180,
    "trendmaster-reviewer-6h":      300,
    # The other 4 (writer-daily, architect-weekly, researcher-weekly, morning-brief)
    # are time-of-day cron schedules; don't override.
    "trendmaster-writer-daily":     None,
    "trendmaster-architect-weekly": None,
    "trendmaster-researcher-weekly": None,
    "trendmaster-morning-brief":    None,
}


def main() -> int:
    if not JOBS_PATH.exists():
        print(f"ERR: {JOBS_PATH} not found")
        return 1

    j = json.loads(JOBS_PATH.read_text(encoding="utf-8"))
    now_ms = int(time.time() * 1000)
    changed: list[str] = []

    for job in j.get("jobs", []):
        name = job.get("name")
        offset = STAGGER_OFFSETS_S.get(name)
        # Always reset error count, even on time-of-day jobs
        if job["state"].get("consecutiveErrors", 0) > 0:
            job["state"]["consecutiveErrors"] = 0
        if offset is None:
            continue
        job["state"]["nextRunAtMs"] = now_ms + offset * 1000
        changed.append(f"{name} (+{offset}s)")

    JOBS_PATH.write_text(json.dumps(j, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[stagger] re-scheduled: {changed}")
    print()
    print("[stagger] full state:")
    for job in j.get("jobs", []):
        nxt = job["state"]["nextRunAtMs"]
        delta = (nxt - now_ms) / 1000 if nxt else None
        delta_str = f"+{delta:.0f}s" if delta and delta > 0 else (f"{delta:.0f}s ago" if delta else "n/a")
        print(
            f"  {job['name']:<35} agent={job['agentId']:<11} "
            f"errors={job['state'].get('consecutiveErrors', 0)} "
            f"nextRun={delta_str}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
