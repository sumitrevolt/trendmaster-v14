"""Kill dashboard → recreate top5 instant alerts → restart dashboard."""
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
SCRIPT = HERE / "recreate_top5_instant.py"
PYW = ROOT / ".venv" / "Scripts" / "pythonw.exe"
PY = ROOT / ".venv" / "Scripts" / "python.exe"


def find_dash():
    pids = []
    for p in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            cmd = " ".join(p.info.get("cmdline") or [])
            if "dashboard_server" in cmd:
                pids.append(p.info["pid"])
        except Exception:
            pass
    return pids


def main():
    print("Killing dashboard…", flush=True)
    for pid in find_dash():
        try: psutil.Process(pid).kill(); print(f"  killed {pid}", flush=True)
        except Exception: pass
    time.sleep(3)
    profile = HERE / "_browser_profile"
    for fn in ("SingletonLock", "SingletonCookie", "SingletonSocket"):
        f = profile / fn
        if f.exists():
            try: f.unlink()
            except Exception: pass

    print("Running recreate_top5_instant.py…", flush=True)
    print("=" * 70, flush=True)
    p = subprocess.Popen(
        [str(PY), str(SCRIPT)],
        cwd=str(ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        creationflags=0x08000000,
    )
    out, _ = p.communicate(timeout=300)
    text = out.decode("utf-8", errors="replace")
    print(text, flush=True)
    print("=" * 70, flush=True)
    print(f"recreate exit code: {p.returncode}", flush=True)

    print("Restart dashboard…", flush=True)
    flags = 0x00000008 | 0x00000200 | 0x08000000
    log_dir = ROOT / "logs"
    log_dir.mkdir(exist_ok=True)
    out_log = open(log_dir / "dashboard.out", "ab")
    err_log = open(log_dir / "dashboard.err", "ab")
    pp = subprocess.Popen([str(PYW), str(DASH)], cwd=str(ROOT),
                          stdout=out_log, stderr=err_log,
                          stdin=subprocess.DEVNULL,
                          creationflags=flags, close_fds=True)
    print(f"  dash pid {pp.pid}", flush=True)
    return p.returncode


if __name__ == "__main__":
    sys.exit(main() or 0)
