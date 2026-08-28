"""Restart brain so it picks up the trading_config.yaml change
(vol_min_quantile 0.10 -> 0.05). ASCII-only, no unicode trap."""
from __future__ import annotations

import subprocess
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
START_BRAIN = ROOT / "start_brain_clean.cmd"
BRAIN_OUT = ROOT / "logs" / "trend_master_brain.out"


def find_brain_pids() -> list[int]:
    import psutil
    return [
        p.info["pid"]
        for p in psutil.process_iter(["pid", "name", "cmdline"])
        if "python" in (p.info.get("name") or "").lower()
        and "trend_master_brain" in " ".join(p.info.get("cmdline") or [])
    ]


def now() -> str:
    return datetime.now().strftime("%H:%M:%S")


def main() -> int:
    print(f"=== restart_brain_yaml_pickup ({datetime.now()}) ===")

    # Kill if alive
    pids = find_brain_pids()
    if pids:
        print(f"[{now()}] killing brain PIDs: {pids}")
        for pid in pids:
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)],
                          capture_output=True, text=True)
        deadline = time.time() + 8
        while time.time() < deadline:
            if not find_brain_pids():
                break
            time.sleep(0.5)
        print(f"[{now()}] brain dead")

    time.sleep(3)

    # Restart
    print(f"[{now()}] launching start_brain_clean.cmd")
    try:
        r = subprocess.run(["cmd.exe", "/c", str(START_BRAIN)], cwd=str(ROOT),
                          capture_output=True, text=True, timeout=60)
        print(f"[{now()}] rc={r.returncode}")
    except subprocess.TimeoutExpired:
        print(f"[{now()}] timeout (brain may have started detached)")

    # Verify
    deadline = time.time() + 30
    while time.time() < deadline:
        time.sleep(2)
        pids = find_brain_pids()
        if pids:
            print(f"[{now()}] brain alive: PIDs={pids}")
            break
    else:
        print(f"[{now()}] brain didn't appear within 30s")
        return 1

    # Wait + check first tick
    time.sleep(10)
    if BRAIN_OUT.exists():
        head = BRAIN_OUT.read_text(encoding="utf-8", errors="replace")
        if "TrendMaster brain online" in head:
            # Grep for new restart#
            import re
            m = re.search(r"restart#(\d+)", head)
            if m:
                print(f"[{now()}] brain online, restart#{m.group(1)}")
        # Check dead-market veto status
        dead_count = head.count("dead market")
        print(f"[{now()}] 'dead market' veto count in fresh log: {dead_count}")
        if dead_count == 0:
            print(f"[{now()}] OK - vol_min_quantile=0.05 likely admitting BTC now")
        else:
            print(f"[{now()}] still some dead-market vetos - check ATR vs new q5 threshold")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
