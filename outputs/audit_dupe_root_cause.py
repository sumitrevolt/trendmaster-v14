"""Audit Windows scheduled tasks + find which launchers are creating
duplicate executor/trailing-stop processes. Read-only; outputs report."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

INTERESTING_KEYWORDS = [
    "python_signal_executor",
    "trailing_stop_manager",
    "hidden_python_executor",
    "hidden_trailing",
    "health_watchdog",
    "trendmaster",
    "TrendMaster",
    "brain",
    "watchdog",
    "tv_webhook",
    "ngrok",
]


def run_cmd(args: list[str]) -> tuple[int, str]:
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=30)
        return r.returncode, r.stdout + r.stderr
    except Exception as e:
        return -1, str(e)


def parse_schtasks_csv(csv_text: str) -> list[dict]:
    """Parse schtasks /query /fo CSV output."""
    import csv
    import io
    rows = []
    reader = csv.DictReader(io.StringIO(csv_text))
    for r in reader:
        # CSV has repeating headers per task — skip those
        if r.get("TaskName") == "TaskName":
            continue
        rows.append(r)
    return rows


def main() -> int:
    print("=== schtasks audit + duplicate-launcher root cause ===")
    print()

    # 1. Get all scheduled tasks (CSV format with verbose)
    rc, out = run_cmd(["schtasks", "/query", "/fo", "CSV", "/v"])
    if rc != 0:
        print(f"schtasks failed: rc={rc}")
        print(out)
        return 1

    tasks = parse_schtasks_csv(out)
    print(f"Total scheduled tasks: {len(tasks)}")
    print()

    # 2. Filter to TrendMaster-related
    tm_tasks = []
    for t in tasks:
        name = t.get("TaskName", "")
        action = t.get("Task To Run", "") or ""
        combined = (name + " " + action).lower()
        if any(k.lower() in combined for k in INTERESTING_KEYWORDS):
            tm_tasks.append(t)

    print(f"TrendMaster-related tasks: {len(tm_tasks)}")
    print()
    print(f"{'STATUS':<10} {'NAME':<55} {'TASK TO RUN':<80}")
    print("-" * 145)
    for t in sorted(tm_tasks, key=lambda x: x.get("TaskName", "")):
        name = t.get("TaskName", "")[:55]
        action = (t.get("Task To Run", "") or "")[:78]
        status = (t.get("Status", "") or "")[:10]
        print(f"{status:<10} {name:<55} {action:<80}")

    # 3. Group by what they launch (script name)
    print()
    print("=== grouped by target script ===")
    by_target: dict[str, list[dict]] = {}
    for t in tm_tasks:
        action = (t.get("Task To Run", "") or "").lower()
        target = "?"
        for keyword in [
            "python_signal_executor", "trailing_stop_manager",
            "hidden_python_executor", "hidden_trailing",
            "health_watchdog", "trend_master_brain", "tv_webhook",
            "ngrok", "master_autostart"
        ]:
            if keyword in action:
                target = keyword
                break
        by_target.setdefault(target, []).append(t)

    for target, tlist in sorted(by_target.items()):
        marker = "  WARN" if len(tlist) > 1 else "  OK  "
        print(f"{marker} {target}: {len(tlist)} task(s)")
        for t in tlist:
            print(f"    - {t.get('TaskName', '')}")
            print(f"      author={t.get('Author', '')}  status={t.get('Status', '')}")
            print(f"      run as={t.get('Run As User', '')}")
            print(f"      action={t.get('Task To Run', '')}")
            print()

    # 4. Suggest disable list
    print()
    print("=== suggested disable list ===")
    for target, tlist in sorted(by_target.items()):
        if len(tlist) <= 1:
            continue
        # Sort by status (Ready first, Disabled last) and prefer venv-using
        ready = [t for t in tlist if (t.get("Status", "") or "").lower() in ("ready", "running")]
        if len(ready) <= 1:
            continue
        # Keep one (prefer venv pythonw), disable rest
        venv_ones = [t for t in ready if ".venv" in (t.get("Task To Run", "") or "").lower()]
        keep = venv_ones[0] if venv_ones else ready[0]
        for t in ready:
            if t["TaskName"] == keep["TaskName"]:
                print(f"KEEP   {target}: {t['TaskName']}")
            else:
                print(f"DISABLE {target}: {t['TaskName']}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
