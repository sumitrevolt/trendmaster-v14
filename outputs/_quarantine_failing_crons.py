"""Disable OpenClaw cron jobs that have consecutiveErrors >= 5.

Idempotent. Writes backup is the caller's job.
The job stays in jobs.json with `enabled=false` so the user can re-enable
after fixing the underlying API timeout.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

JOBS = Path(r"C:\Users\Ratanshila\.openclaw\cron\jobs.json")


def main() -> int:
    if not JOBS.exists():
        print(f"  [SKIP] {JOBS} not found")
        return 0
    try:
        data = json.loads(JOBS.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"  [X] cannot parse {JOBS}: {e}")
        return 2

    jobs = data.get("jobs", [])
    disabled, kept_enabled = [], []
    for job in jobs:
        state = job.get("state") or {}
        ce = state.get("consecutiveErrors", 0)
        if job.get("enabled") and ce >= 5:
            job["enabled"] = False
            job["_disabled_by"] = "harden_all_2026-05-08"
            job["_disabled_reason"] = f"consecutiveErrors={ce}"
            disabled.append(job.get("name", job.get("id", "?")))
        elif job.get("enabled"):
            kept_enabled.append(job.get("name", job.get("id", "?")))

    if not disabled:
        print("  [OK] no failing cron jobs found (all healthy or already disabled)")
        return 0

    JOBS.write_text(json.dumps(data, indent=2), encoding="utf-8")
    print(f"  [OK] disabled {len(disabled)} failing job(s):")
    for n in disabled:
        print(f"        - {n}")
    if kept_enabled:
        print(f"  [INFO] {len(kept_enabled)} job(s) still enabled:")
        for n in kept_enabled:
            print(f"        - {n}")
    print("  [HINT] re-enable: set enabled=true + reset state.consecutiveErrors=0")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
