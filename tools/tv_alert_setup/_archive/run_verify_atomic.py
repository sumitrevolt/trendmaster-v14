"""Kill dashboard → run verify_frequency → restart dashboard (atomic)."""
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
SCRIPT = HERE / "verify_frequency.py"
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


def kill_chromium(profile_dir: Path) -> int:
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
    print("Step 1: kill dashboard")
    for pid in find_dashboard_pids():
        try:
            psutil.Process(pid).kill()
            print(f"  killed {pid}")
        except Exception as e:
            print(f"  could not kill {pid}: {e}")
    profile = HERE / "_browser_profile"
    n = kill_chromium(profile)
    print(f"  killed {n} chromium")
    time.sleep(4)
    for fn in ("SingletonLock", "SingletonCookie", "SingletonSocket"):
        f = profile / fn
        if f.exists():
            try: f.unlink(); print(f"  removed {fn}")
            except Exception: pass

    print("Step 2: verify_frequency")
    print("=" * 70)
    p = subprocess.Popen(
        [str(PY), str(SCRIPT)],
        cwd=str(ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        creationflags=0x08000000,
    )
    out, _ = p.communicate(timeout=120)
    text = out.decode("utf-8", errors="replace")
    print(text)
    print("=" * 70)
    print(f"  verify exit code: {p.returncode}")

    print("Step 3: restart dashboard")
    DETACHED_PROCESS = 0x00000008
    CREATE_NEW_PROCESS_GROUP = 0x00000200
    CREATE_NO_WINDOW = 0x08000000
    flags = DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW
    log_dir = ROOT / "logs"
    log_dir.mkdir(exist_ok=True)
    out_log = open(log_dir / "dashboard.out", "ab")
    err_log = open(log_dir / "dashboard.err", "ab")
    pp = subprocess.Popen(
        [str(PYW), str(DASH)],
        cwd=str(ROOT),
        stdout=out_log,
        stderr=err_log,
        stdin=subprocess.DEVNULL,
        creationflags=flags,
        close_fds=True,
    )
    print(f"  dashboard pid={pp.pid}")
    return p.returncode


if __name__ == "__main__":
    sys.exit(main() or 0)
