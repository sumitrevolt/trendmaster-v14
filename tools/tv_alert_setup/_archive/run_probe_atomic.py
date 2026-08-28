"""Kill dashboard → run probe → restart dashboard."""
from __future__ import annotations
import subprocess, sys, time
from pathlib import Path
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
import psutil
ROOT = Path("C:/Users/Ratanshila/Documents/autmated trading")
HERE = Path(__file__).resolve().parent
PYW = ROOT / ".venv/Scripts/pythonw.exe"
PY = ROOT / ".venv/Scripts/python.exe"


def find(needle):
    pids = []
    for p in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            cmd = " ".join(p.info.get("cmdline") or [])
            if needle in cmd:
                pids.append(p.info["pid"])
        except Exception:
            pass
    return pids


def main():
    print("Kill dashboard…", flush=True)
    for pid in find("dashboard_server"):
        try: psutil.Process(pid).kill()
        except Exception: pass
    time.sleep(3)
    profile = HERE / "_browser_profile"
    for fn in ("SingletonLock", "SingletonCookie", "SingletonSocket"):
        f = profile / fn
        if f.exists():
            try: f.unlink()
            except Exception: pass

    print("Run probe…", flush=True)
    print("=" * 70, flush=True)
    p = subprocess.Popen([str(PY), str(HERE / "probe_freq_values.py")],
                         cwd=str(ROOT),
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                         creationflags=0x08000000)
    out, _ = p.communicate(timeout=180)
    print(out.decode("utf-8", errors="replace"), flush=True)
    print("=" * 70, flush=True)

    print("Restart dashboard via master_autostart…", flush=True)
    subprocess.Popen([str(PY), str(ROOT / "tools/master_autostart.py")],
                     cwd=str(ROOT),
                     stdout=open(ROOT / "logs/master_after_probe.out", "ab"),
                     stderr=subprocess.STDOUT,
                     creationflags=0x08000000)
    return p.returncode


if __name__ == "__main__":
    sys.exit(main() or 0)
