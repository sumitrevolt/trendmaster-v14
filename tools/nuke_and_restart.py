"""Kill ALL dashboards/executors/trailings, delete stale lock files, then run master_autostart."""
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
PY = ROOT / ".venv/Scripts/python.exe"
LOGS = ROOT / "logs"

KILL = ["dashboard_server", "python_signal_executor", "trailing_stop_manager"]


def kill_all(needle: str) -> int:
    n = 0
    for p in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            cmd = " ".join(p.info.get("cmdline") or [])
            if needle in cmd:
                p.kill()
                n += 1
        except Exception:
            pass
    return n


def main():
    print("=== Kill all watched processes ===", flush=True)
    for k in KILL:
        n = kill_all(k)
        print(f"  killed {n} {k}", flush=True)
    print("Sleep 3s for handles to release…", flush=True)
    time.sleep(3)

    print("\n=== Delete stale lock files ===", flush=True)
    for fname in ("dashboard_server.lock", "python_signal_executor.lock", "trailing_stop_manager.lock"):
        f = LOGS / fname
        if f.exists():
            try: f.unlink(); print(f"  removed {fname}")
            except Exception as e: print(f"  could not remove {fname}: {e}")

    print("\n=== Running master_autostart.py ===", flush=True)
    r = subprocess.run([str(PY), str(ROOT / "tools/master_autostart.py")],
                        capture_output=True, text=True, timeout=120,
                        creationflags=0x08000000)
    print(r.stdout)
    if r.stderr:
        print("STDERR:", r.stderr)
    return r.returncode


if __name__ == "__main__":
    sys.exit(main())
