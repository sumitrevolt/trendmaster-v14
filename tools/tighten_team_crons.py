"""
tighten_team_crons.py — reduce the cron cadence so the team doesn't
exhaust GitHub Copilot Enterprise's 5-hour session quota.

Original cadences (too noisy):
  trader heartbeat:   every 30 min  → 48/day
  reviewer:           every 6 hours → 4/day
  debugger:           every 1 hour  → 24/day (mostly no-op)
  morning brief:      daily         → 1/day
  writer digest:      daily         → 1/day
  architect:          weekly        → 0.14/day
  researcher:         weekly        → 0.14/day
                                     ──── 78 calls/day worst case

Tightened cadences (sustainable):
  trader heartbeat:   every 60 min  → 24/day
  reviewer:           every 12 hours → 2/day
  debugger:           every 6 hours  → 4/day (still mostly no-op)
  morning brief:      daily          → 1/day
  writer digest:      daily          → 1/day
  architect:          weekly         → 0.14/day
  researcher:         weekly         → 0.14/day
                                      ──── 32 calls/day, ~58 % less

Run:
    .venv\\Scripts\\python.exe tools\\tighten_team_crons.py
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

JOBS_PATH = Path(os.environ.get("USERPROFILE", "")) / ".openclaw" / "cron" / "jobs.json"

NEW_INTERVALS_MS = {
    # name → new everyMs (only for kind="every"; cron-expr jobs untouched)
    "trendmaster-health-check":    60 * 60 * 1000,        # 60 min  (was 30)
    "trendmaster-debugger-hourly": 6 * 60 * 60 * 1000,    # 6 hours (was 1)
    "trendmaster-reviewer-6h":     12 * 60 * 60 * 1000,   # 12 hours (was 6)
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
        if name not in NEW_INTERVALS_MS:
            continue
        sched = job.get("schedule", {})
        if sched.get("kind") != "every":
            continue
        old = sched.get("everyMs", 0)
        new = NEW_INTERVALS_MS[name]
        if old == new:
            continue
        sched["everyMs"] = new
        sched["anchorMs"] = now_ms
        # also push next run out so it doesn't fire instantly
        job["state"]["nextRunAtMs"] = now_ms + min(new, 600_000)
        job["state"]["consecutiveErrors"] = 0
        changed.append(f"{name}: {old/60000:.0f}min → {new/60000:.0f}min")

    JOBS_PATH.write_text(json.dumps(j, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[tighten] updated {len(changed)} jobs")
    for c in changed:
        print(f"  • {c}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
