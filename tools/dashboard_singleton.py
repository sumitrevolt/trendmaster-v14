"""Singleton launcher for dashboard_server.py.

[2026-08-25] hidden_dashboard.vbs (TrendMaster Live Dashboard schtask, PT5M)
blind-spawned a new dashboard every 5 minutes with no aliveness check,
piling up duplicate servers. This wrapper spawns ONLY if no instance of
tools/dashboard_server.py is currently running.
"""
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "tools", "dashboard_server.py")
PYW = os.path.join(ROOT, ".venv", "Scripts", "pythonw.exe")
CREATE_NO_WINDOW = 0x08000000


def already_running() -> bool:
    import psutil

    for p in psutil.process_iter(["pid", "cmdline"]):
        try:
            if p.info["pid"] == os.getpid():
                continue
            cl = " ".join(p.info.get("cmdline") or []).replace("\\", "/").lower()
            if "dashboard_server.py" in cl and "dashboard_singleton" not in cl:
                return True
        except Exception:
            continue
    return False


def main() -> int:
    if already_running():
        return 0
    subprocess.Popen(
        [PYW, SCRIPT],
        cwd=ROOT,
        creationflags=CREATE_NO_WINDOW,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    time.sleep(1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
