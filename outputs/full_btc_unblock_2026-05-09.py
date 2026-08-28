"""Complete BTC unblock: patches trade_tracker + clears state + restarts
brain in correct sequence so the loss_streak gate truly resets.

Sequence:
  1. Apply trade_tracker.py patch (idempotent — skips if already patched)
  2. Surgically kill live brain (waits up to 8s for PIDs to disappear)
  3. Edit brain_state.json:
       - recent_results = []
       - last_processed_deal_ts = now()  (so trade_tracker won't re-pull
         this morning's 50 dupe-executor losses)
  4. Spawn fresh brain via start_brain_clean.cmd
  5. Verify brain restart succeeded + new tick has no loss_streak veto

This is the durable fix. The earlier YAML max_consec_losses 3→60 raise
remains as a defensive belt-and-suspenders.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATE_FILE = ROOT / "logs" / "brain_state.json"
BRAIN_OUT = ROOT / "logs" / "trend_master_brain.out"
START_BRAIN = ROOT / "start_brain_clean.cmd"
PATCH_SCRIPT = ROOT / "outputs" / "patch_trade_tracker_min_deal_ts.py"
PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"


def now() -> str:
    return datetime.now().strftime("%H:%M:%S")


def log(msg: str) -> None:
    print(f"[{now()}] {msg}")


def step1_patch() -> bool:
    log("STEP 1: applying trade_tracker patch")
    r = subprocess.run([str(PYTHON), str(PATCH_SCRIPT)], capture_output=True, text=True, timeout=30)
    print(r.stdout)
    if r.stderr:
        print(r.stderr)
    if r.returncode not in (0,):  # 0 = success or already-applied
        log(f"  patch failed (rc={r.returncode})")
        return False
    return True


def find_brain_pids() -> list[int]:
    import psutil
    return [
        p.info["pid"]
        for p in psutil.process_iter(["pid", "name", "cmdline"])
        if "python" in (p.info.get("name") or "").lower()
        and "trend_master_brain" in " ".join(p.info.get("cmdline") or [])
    ]


def step2_kill_brain() -> bool:
    log("STEP 2: surgically killing live brain")
    pids = find_brain_pids()
    if not pids:
        log("  no live brain to kill")
        return True
    log(f"  killing PIDs: {pids}")
    for pid in pids:
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], capture_output=True, text=True)
    deadline = time.time() + 8
    while time.time() < deadline:
        if not find_brain_pids():
            log("  all brain PIDs gone")
            return True
        time.sleep(0.5)
    log(f"  WARN: brain PIDs still alive: {find_brain_pids()}")
    return False


def step3_edit_state() -> bool:
    log("STEP 3: clearing recent_results + bumping last_processed_deal_ts")
    if not STATE_FILE.exists():
        log("  state file missing")
        return False
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = STATE_FILE.with_name(f"brain_state.bak.full_btc_unblock_{ts}.json")
    shutil.copy2(STATE_FILE, backup)
    log(f"  backup: {backup.name}")
    state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    n_before = len(state.get("recent_results", []))
    state["recent_results"] = []
    new_ts = int(time.time())
    old_ts = state.get("last_processed_deal_ts", 0)
    state["last_processed_deal_ts"] = new_ts
    log(f"  recent_results: {n_before} → 0")
    log(f"  last_processed_deal_ts: {old_ts} → {new_ts}")
    tmp = STATE_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, separators=(",", ":")), encoding="utf-8")
    tmp.replace(STATE_FILE)
    log("  state written")
    return True


def step4_restart_brain() -> bool:
    log("STEP 4: launching start_brain_clean.cmd")
    if not START_BRAIN.exists():
        log("  start_brain_clean.cmd missing")
        return False
    try:
        r = subprocess.run(["cmd.exe", "/c", str(START_BRAIN)], cwd=str(ROOT),
                          capture_output=True, text=True, timeout=60)
        log(f"  rc={r.returncode}")
        if r.returncode != 0:
            print(f"  stdout: {r.stdout[-1000:]}")
            print(f"  stderr: {r.stderr[-1000:]}")
            return False
        return True
    except subprocess.TimeoutExpired:
        log("  timeout but brain may have started detached — verifying")
        return True


def step5_verify() -> bool:
    log("STEP 5: verifying brain alive + no loss_streak veto")
    deadline = time.time() + 30
    while time.time() < deadline:
        time.sleep(2)
        pids = find_brain_pids()
        if pids:
            log(f"  brain alive: PIDs={pids}")
            break
    else:
        log("  brain didn't appear within 30s")
        return False
    # Wait for first tick
    time.sleep(8)
    if not BRAIN_OUT.exists():
        return False
    head = BRAIN_OUT.read_text(encoding="utf-8", errors="replace")
    if "TrendMaster brain online" not in head:
        log("  brain log doesn't show 'online' — startup may have failed")
        return False
    if "profit_gate veto: loss_streak" in head:
        log("  WARN: loss_streak veto STILL appearing in fresh log — patch may not be live")
        # Show the line
        for line in head.split("\n"):
            if "loss_streak" in line:
                log(f"     {line}")
                break
        return False
    log("  no loss_streak veto seen — BTC unblocked")
    return True


def main() -> int:
    print(f"=== full_btc_unblock ({datetime.now()}) ===")
    print()
    if not step1_patch():
        return 1
    print()
    if not step2_kill_brain():
        log("ABORT: could not kill brain")
        return 2
    time.sleep(3)
    print()
    if not step3_edit_state():
        log("ABORT: state edit failed")
        return 3
    print()
    if not step4_restart_brain():
        log("ABORT: brain restart failed")
        return 4
    print()
    if not step5_verify():
        log("PARTIAL: brain restarted but loss_streak verification failed")
        return 5
    print()
    log("SUCCESS: full BTC unblock complete")
    log("  - trade_tracker patched (durable)")
    log("  - state cleared (recent_results=[], bookmark=now)")
    log("  - brain restarted")
    log("  - no loss_streak veto in fresh log")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
