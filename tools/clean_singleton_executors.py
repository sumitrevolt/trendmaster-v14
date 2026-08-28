"""URGENT: kill all duplicate executor + trailing instances → leave ONE of each.

Multiple watchdogs spawned 26 copies of python_signal_executor and 26 of
trailing_stop_manager. This risks duplicate MT5 orders. Reduce to a single
oldest instance of each (kill newer ones to preserve cooldown state).
"""
from __future__ import annotations
import sys
import time
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import psutil


TARGETS = {
    "python_signal_executor": "python_signal_executor",
    "trailing_stop_manager":  "trailing_stop_manager",
}


def find(needle: str):
    rows = []
    for p in psutil.process_iter(["pid", "name", "cmdline", "create_time"]):
        try:
            cmd = " ".join(p.info.get("cmdline") or [])
            if needle in cmd:
                rows.append((p.info["pid"], p.info["create_time"], cmd[:120]))
        except Exception:
            pass
    return rows


def main():
    summary = {}
    for label, needle in TARGETS.items():
        procs = find(needle)
        procs.sort(key=lambda r: r[1])  # oldest first
        if not procs:
            print(f"  {label}: none running", flush=True)
            summary[label] = (0, 0)
            continue
        keeper = procs[0]
        killers = procs[1:]
        print(f"\n{label}: {len(procs)} found", flush=True)
        print(f"  KEEP   pid={keeper[0]} (oldest)", flush=True)
        n = 0
        for pid, _, _ in killers:
            try:
                psutil.Process(pid).kill()
                n += 1
            except Exception as e:
                print(f"    [WARN] could not kill {pid}: {e}", flush=True)
        print(f"  KILLED {n}/{len(killers)} duplicates", flush=True)
        summary[label] = (len(procs), n)

    time.sleep(2)
    print("\n=== Post-cleanup tally ===", flush=True)
    for label, needle in TARGETS.items():
        n_now = len(find(needle))
        before, killed = summary[label]
        print(f"  {label:28} before={before:3}  killed={killed:3}  now={n_now}", flush=True)


if __name__ == "__main__":
    sys.exit(main() or 0)
