"""Start ONE python_signal_executor and ONE trailing_stop_manager (singleton).

Use after clean_singleton_executors.py kills duplicates. Sets a PID file
so future watchdogs can check before spawning.
"""
from __future__ import annotations
import os
import subprocess
import sys
import time
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import psutil

ROOT = Path("C:/Users/Ratanshila/Documents/autmated trading")
PYW = ROOT / ".venv/Scripts/pythonw.exe"
EXEC_SCRIPT = ROOT / "tools/python_signal_executor.py"
TRAIL_SCRIPT = ROOT / "tools/trailing_stop_manager.py"
LOGS = ROOT / "logs"
LOGS.mkdir(exist_ok=True)

DETACHED_PROCESS = 0x00000008
CREATE_NEW_PROCESS_GROUP = 0x00000200
CREATE_NO_WINDOW = 0x08000000
HIDDEN_FLAGS = DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW


def find(needle: str):
    pids = []
    for p in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            cmd = " ".join(p.info.get("cmdline") or [])
            if needle in cmd:
                pids.append(p.info["pid"])
        except Exception:
            pass
    return pids


def start_one(script: Path, label: str, pidfile: Path):
    existing = find(script.stem)
    if existing:
        print(f"  {label}: already running pids={existing} — skip", flush=True)
        return existing[0]
    log_out = LOGS / f"{label}.out"
    log_err = LOGS / f"{label}.err"
    fout = open(log_out, "ab")
    ferr = open(log_err, "ab")
    p = subprocess.Popen(
        [str(PYW), str(script)],
        cwd=str(ROOT),
        stdout=fout, stderr=ferr, stdin=subprocess.DEVNULL,
        creationflags=HIDDEN_FLAGS, close_fds=True,
    )
    pidfile.write_text(str(p.pid))
    print(f"  {label}: started pid={p.pid}", flush=True)
    return p.pid


def main():
    pid_executor = start_one(EXEC_SCRIPT, "python_signal_executor", LOGS / "python_signal_executor.pid")
    pid_trail = start_one(TRAIL_SCRIPT, "trailing_stop_manager", LOGS / "trailing_stop_manager.pid")
    time.sleep(3)
    # Verify
    print("\nVerification:", flush=True)
    for label, needle in (("executor", "python_signal_executor"),
                          ("trailing", "trailing_stop_manager")):
        ps = find(needle)
        if not ps:
            print(f"  [DOWN] {label}", flush=True)
        elif len(ps) == 1:
            print(f"  [OK]   {label} pid={ps[0]} (singleton)", flush=True)
        else:
            print(f"  [WARN] {label} has {len(ps)} instances: {ps}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
