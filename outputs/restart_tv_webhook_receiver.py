"""Surgically restart the TV webhook receiver to pick up code changes
in tv_webhook_receiver.py (URL plot extraction patch 2026-05-10).
"""
from __future__ import annotations
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PYTHONW = ROOT / ".venv" / "Scripts" / "pythonw.exe"


def find_webhook_pids() -> list[int]:
    import psutil
    pids = []
    for p in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            n = (p.info.get("name") or "").lower()
            if "python" not in n:
                continue
            cmd = " ".join(p.info.get("cmdline") or [])
            if "tv_webhook_receiver" in cmd:
                pids.append(p.info["pid"])
        except Exception:
            pass
    return pids


def main() -> int:
    print("=== restart_tv_webhook_receiver ===")
    pids = find_webhook_pids()
    print(f"Found {len(pids)} webhook PIDs: {pids}")

    if pids:
        for pid in pids:
            r = subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)],
                              capture_output=True, text=True, timeout=10)
            print(f"  kill PID={pid}: rc={r.returncode}")

        # Wait for PIDs to die
        deadline = time.time() + 8
        while time.time() < deadline:
            if not find_webhook_pids():
                break
            time.sleep(0.5)

    # Wait for OS to release port 5005
    time.sleep(2)

    # Spawn fresh detached webhook
    print("Spawning fresh webhook...")
    DETACHED = 0x00000008
    NOWIN = 0x08000000
    try:
        proc = subprocess.Popen(
            [str(PYTHONW), "-m", "ai_trading_agents.tv_webhook_receiver"],
            cwd=str(ROOT),
            creationflags=DETACHED | NOWIN,
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, close_fds=True,
        )
        print(f"  spawned PID={proc.pid}")
    except Exception as e:
        print(f"  spawn failed: {e}")
        return 1

    # Verify alive
    time.sleep(5)
    new_pids = find_webhook_pids()
    print(f"After restart: {len(new_pids)} webhook PID(s): {new_pids}")
    if new_pids:
        # Quick health check
        try:
            import urllib.request
            r = urllib.request.urlopen("http://127.0.0.1:5005/health", timeout=5)
            print(f"  health: HTTP {r.status} body={r.read().decode()[:100]}")
        except Exception as e:
            print(f"  health check failed: {e}")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main() or 0)
