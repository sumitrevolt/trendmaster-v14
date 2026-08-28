"""
Schtasks audit for TrendMaster v14.

Queries the three TrendMaster scheduled tasks via `schtasks /query /xml /v`,
parses the XML, and asserts the seven reliability flags.

Pure stdlib; uses subprocess + xml.etree + argparse + pathlib + sys.
Does not require admin elevation for read-only query.
"""

from __future__ import annotations

import sys as _sys
try:
    _sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import argparse
import subprocess
import sys
from pathlib import Path
from xml.etree import ElementTree as ET

REPO_ROOT = Path(r"C:\Users\Ratanshila\Documents\autmated trading")
HEARTBEAT_FILE = REPO_ROOT / "logs" / "heartbeat.txt"

TASKS = [
    "TrendMaster Zero Trades Watchdog",
    "TrendMaster EA Parity Nightly",
    "TrendMaster Heartbeat",
]

NS = "{http://schemas.microsoft.com/windows/2004/02/mit/task}"


def query_xml(task_name: str) -> ET.Element | None:
    try:
        out = subprocess.run(
            ["schtasks", "/query", "/tn", task_name, "/xml"],
            capture_output=True, text=True, timeout=20,
        )
    except FileNotFoundError:
        print("schtasks not on PATH - are you running on Windows?")
        sys.exit(2)
    except subprocess.TimeoutExpired:
        return None
    if out.returncode != 0:
        return None
    # schtasks emits BOM-prefixed UTF-16 - try a few decode strategies
    text = out.stdout
    if text.startswith("﻿"):
        text = text.lstrip("﻿")
    try:
        return ET.fromstring(text)
    except ET.ParseError:
        return None


def get(elem: ET.Element, path: str) -> str | None:
    """Find element under namespaced path; return text or None."""
    parts = path.split("/")
    e: ET.Element | None = elem
    for p in parts:
        if e is None:
            return None
        e = e.find(NS + p)
    return e.text.strip() if (e is not None and e.text) else None


def check_task(name: str, root: ET.Element) -> list[tuple[str, str, str]]:
    """Return list of (label, status, detail). status ∈ {PASS, FAIL, INFO}."""
    if root is None:
        return [("task_exists", "FAIL", "Task does not exist")]
    rows = []
    # Flag 1: RunLevel
    rl = get(root, "Principals/Principal/RunLevel")
    rows.append((
        "RunLevel = HighestAvailable",
        "PASS" if rl == "HighestAvailable" else "FAIL",
        f"actual={rl}",
    ))
    # Flag 2: LogonType / Run whether logged on
    lt = get(root, "Principals/Principal/LogonType")
    rows.append((
        "Run whether user is logged on or not",
        "PASS" if lt in ("Password", "InteractiveOrPassword", "S4U") else "FAIL",
        f"LogonType={lt}",
    ))
    # Flag 3: RunOnlyIfIdle
    idle = get(root, "Settings/RunOnlyIfIdle")
    rows.append((
        "RunOnlyIfIdle = false",
        "PASS" if (idle is None or idle.lower() == "false") else "FAIL",
        f"actual={idle}",
    ))
    # Flag 4: StartOnlyIfACPowerSource (StopIfGoingOnBatteries / DisallowStartIfOnBatteries)
    on_batt = get(root, "Settings/DisallowStartIfOnBatteries")
    stop_batt = get(root, "Settings/StopIfGoingOnBatteries")
    will_run_on_battery = (on_batt or "").lower() == "false" and (stop_batt or "").lower() == "false"
    rows.append((
        "Runs on battery",
        "PASS" if will_run_on_battery else "FAIL",
        f"DisallowStartIfOnBatteries={on_batt}, StopIfGoingOnBatteries={stop_batt}",
    ))
    # Flag 5: WakeToRun
    wake = get(root, "Settings/WakeToRun")
    rows.append((
        "WakeToRun = true",
        "PASS" if (wake or "").lower() == "true" else "FAIL",
        f"actual={wake}",
    ))
    # Flag 6: RestartOnFailure
    rof_count = get(root, "Settings/RestartOnFailure/Count")
    rof_interval = get(root, "Settings/RestartOnFailure/Interval")
    has_retry = rof_count and rof_interval
    rows.append((
        "RestartOnFailure configured",
        "PASS" if has_retry else "FAIL",
        f"count={rof_count}, interval={rof_interval}",
    ))
    # Flag 7: ExecutionTimeLimit
    etl = get(root, "Settings/ExecutionTimeLimit")
    rows.append((
        "ExecutionTimeLimit <= PT1H",
        "PASS" if etl in ("PT0S", "PT5M", "PT10M", "PT30M", "PT1H") else "INFO",
        f"actual={etl}",
    ))
    return rows


def heartbeat_check() -> tuple[str, str, str]:
    if not HEARTBEAT_FILE.exists():
        return ("Heartbeat file present", "FAIL", "logs/heartbeat.txt does not exist")
    age_min = (Path(HEARTBEAT_FILE).stat().st_mtime - 0)  # mtime
    import time as _t
    age = (_t.time() - HEARTBEAT_FILE.stat().st_mtime) / 60.0
    if age < 10:
        return ("Heartbeat fresh (<10m)", "PASS", f"age={age:.1f}m")
    return ("Heartbeat fresh (<10m)", "FAIL", f"age={age:.1f}m - heartbeat task may be dead")


def render(results: dict[str, list[tuple[str, str, str]]], hb: tuple[str, str, str], fix: bool) -> str:
    out = ["Schtasks Audit - TrendMaster v14"]
    out.append("=" * 40)
    for name, rows in results.items():
        out.append("")
        out.append(name)
        for label, status, detail in rows:
            out.append(f"  [{status}] {label}  ({detail})")
        if fix:
            for label, status, detail in rows:
                if status != "FAIL":
                    continue
                if "battery" in label.lower():
                    out.append(f"    FIX (battery): export task XML, set <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>, re-import via schtasks /Create /XML")
                if "logon" in label.lower():
                    out.append(f"    FIX (logon): schtasks /Change /TN \"{name}\" /RU SYSTEM /RP \"\"")
                if "WakeToRun" in label:
                    out.append(f"    FIX (wake): export XML, set <WakeToRun>true</WakeToRun>, re-import")
    out.append("")
    out.append("Heartbeat")
    out.append(f"  [{hb[1]}] {hb[0]}  ({hb[2]})")
    fail_total = sum(1 for rows in results.values() for _, s, _ in rows if s == "FAIL")
    fail_total += 1 if hb[1] == "FAIL" else 0
    out.append("")
    out.append(f"Summary: {fail_total} flags failed across {len(results)} tasks.")
    out.append("")
    out.append("This skill never modifies scheduled tasks. Run any FIX commands manually after review.")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--task", default=None)
    ap.add_argument("--fix", action="store_true", help="Print fix commands for FAIL findings (does not execute)")
    args = ap.parse_args()

    tasks = [args.task] if args.task else TASKS
    results = {}
    for t in tasks:
        root = query_xml(t)
        results[t] = check_task(t, root)

    hb = heartbeat_check()
    print(render(results, hb, args.fix))


if __name__ == "__main__":
    main()
