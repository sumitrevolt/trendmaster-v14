"""Atomically: kill dashboard → run set_instant_frequency → restart dashboard.

The dashboard's _tv_alerts_refresh_loop holds a chromium persistent context
on the same browser profile every 5 min, blocking standalone scripts.
This wrapper takes the lock for itself, runs the freq update, then restores.
"""
from __future__ import annotations
import subprocess
import sys
import time
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import psutil

ROOT = Path(__file__).resolve().parent.parent.parent
HERE = Path(__file__).resolve().parent
DASH = ROOT / "tools" / "dashboard_server.py"
FREQ_SCRIPT = HERE / "set_instant_frequency.py"
PYW = ROOT / ".venv" / "Scripts" / "pythonw.exe"
PY = ROOT / ".venv" / "Scripts" / "python.exe"


def find_dashboard_pids() -> list[int]:
    pids: list[int] = []
    for p in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            cmd = " ".join(p.info.get("cmdline") or [])
            if "dashboard_server" in cmd and "python" in (p.info.get("name") or "").lower():
                pids.append(p.info["pid"])
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return pids


def kill_chromium_using_profile(profile_dir: Path) -> int:
    n = 0
    target = str(profile_dir).lower()
    for p in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            name = (p.info.get("name") or "").lower()
            cmd = " ".join(p.info.get("cmdline") or []).lower()
            if any(k in name for k in ("chromium", "chrome", "headless_shell", "playwright")):
                if target in cmd or "_browser_profile" in cmd:
                    p.kill()
                    n += 1
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return n


def main():
    print("Step 1: locating dashboard process(es)…")
    dash_pids = find_dashboard_pids()
    print(f"  found dashboard pids: {dash_pids}")
    for pid in dash_pids:
        try:
            proc = psutil.Process(pid)
            proc.kill()
            print(f"  killed pid {pid}")
        except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
            print(f"  could not kill {pid}: {e}")

    print("Step 2: killing residual chromium tied to _browser_profile…")
    profile = HERE / "_browser_profile"
    n = kill_chromium_using_profile(profile)
    print(f"  killed {n} chromium/playwright procs")

    print("Step 3: waiting 4s for browser-profile lock to release…")
    time.sleep(4)

    # Remove the well-known SingletonLock files chromium leaves behind
    for fn in ("SingletonLock", "SingletonCookie", "SingletonSocket"):
        f = profile / fn
        if f.exists():
            try:
                f.unlink()
                print(f"  removed stale {fn}")
            except Exception as e:
                print(f"  could not remove {fn}: {e}")

    print("Step 4: running set_instant_frequency.py")
    print("=" * 70)
    rc = subprocess.call(
        [str(PY), str(FREQ_SCRIPT)],
        cwd=str(ROOT),
        creationflags=0x08000000,  # CREATE_NO_WINDOW
    )
    print("=" * 70)
    print(f"  set_instant_frequency exit code: {rc}")

    print("Step 5: restarting dashboard server (pythonw, no console)…")
    DETACHED_PROCESS = 0x00000008
    CREATE_NEW_PROCESS_GROUP = 0x00000200
    CREATE_NO_WINDOW = 0x08000000
    flags = DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW
    log_dir = ROOT / "logs"
    log_dir.mkdir(exist_ok=True)
    out_log = open(log_dir / "dashboard.out", "ab")
    err_log = open(log_dir / "dashboard.err", "ab")
    p = subprocess.Popen(
        [str(PYW), str(DASH)],
        cwd=str(ROOT),
        stdout=out_log,
        stderr=err_log,
        stdin=subprocess.DEVNULL,
        creationflags=flags,
        close_fds=True,
    )
    print(f"  dashboard restarted, pid={p.pid}")
    return rc


if __name__ == "__main__":
    sys.exit(main() or 0)
