"""
Brain liveness watchdog for TrendMaster v14.

Detects a dead brain within 5 minutes via PID + log freshness checks.
Pages Telegram on DEAD verdict (de-duplicated to once per 30 min).

Pure-Python; uses psutil + stdlib + ai_trading_agents.telegram_notifier.
"""

from __future__ import annotations
import sys as _sys
try:
    _sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(r"C:\Users\Ratanshila\Documents\autmated trading")
LOGS = REPO_ROOT / "logs"
LAST_ALERT = LOGS / "brain_liveness_last_alert.txt"
DEDUP_MINUTES = 30  # don't re-page within this window

# Thresholds (seconds)
LOG_FRESH_OK = 90
LOG_FRESH_DEAD = 180
STATE_FRESH_OK = 120
STATE_FRESH_DEAD = 240


def check_pid_file() -> tuple[int | None, str]:
    p = LOGS / "brain.pid"
    if not p.exists():
        return None, "brain.pid MISSING"
    try:
        text = p.read_text(encoding="ascii", errors="ignore").strip()
        # brain.pid can have multiple PIDs (one per line)
        for line in text.splitlines():
            line = line.strip()
            if line.isdigit():
                return int(line), f"brain.pid PRESENT ({line})"
        return None, f"brain.pid contains non-PID: {text!r}"
    except Exception as e:
        return None, f"brain.pid read error: {e}"


def check_pid_alive(pid: int) -> tuple[bool, str]:
    try:
        import psutil
    except ImportError:
        return False, "psutil not installed (skill needs it)"
    if not psutil.pid_exists(pid):
        return False, f"PID {pid} not found"
    try:
        proc = psutil.Process(pid)
        name = proc.name().lower()
        if "python" not in name:
            return False, f"PID {pid} is {proc.name()}, not python"
        uptime = (datetime.now() - datetime.fromtimestamp(proc.create_time())).total_seconds()
        return True, f"YES python.exe, uptime {int(uptime)}s"
    except psutil.NoSuchProcess:
        return False, f"PID {pid} died between checks"
    except Exception as e:
        return False, f"PID {pid} check error: {e}"


def check_file_freshness(name: str, max_ok: int, max_dead: int) -> tuple[str, str]:
    p = LOGS / name
    if not p.exists():
        return "DEAD", f"{name} does NOT exist"
    age = (datetime.now() - datetime.fromtimestamp(p.stat().st_mtime)).total_seconds()
    if age < max_ok:
        return "OK", f"{int(age)}s ago (under {max_ok}s threshold) OK"
    if age < max_dead:
        return "WARN", f"{int(age)}s ago (between {max_ok}-{max_dead}s) WARN"
    return "DEAD", f"{int(age)}s ago (>>{max_dead}s threshold) STALE"


def check_brain_err_growth() -> tuple[str, str]:
    p = LOGS / "trend_master_brain.err"
    if not p.exists():
        return "OK", "brain.err does not exist (good)"
    sz = p.stat().st_size
    if sz == 0:
        return "OK", "0 bytes (good)"
    return "WARN", f"{sz} bytes — investigate"


def should_send_telegram() -> bool:
    if not LAST_ALERT.exists():
        return True
    try:
        last = datetime.fromisoformat(LAST_ALERT.read_text().strip())
        return (datetime.now() - last) > timedelta(minutes=DEDUP_MINUTES)
    except Exception:
        return True


def record_telegram_sent() -> None:
    LAST_ALERT.write_text(datetime.now().isoformat())


def send_telegram(msg: str) -> bool:
    try:
        import sys
        sys.path.insert(0, str(REPO_ROOT))
        from ai_trading_agents.telegram_notifier import get_notifier
        n = get_notifier()
        return bool(n.send(msg))
    except Exception as e:
        print(f"  Telegram send failed: {e}")
        return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quiet-on-alive", action="store_true",
                    help="Suppress output if brain is alive (good for schtasks)")
    ap.add_argument("--no-telegram", action="store_true",
                    help="Disable Telegram paging (test mode)")
    args = ap.parse_args()

    pid, pid_msg = check_pid_file()
    log_status, log_msg = check_file_freshness("trend_master_brain.log", LOG_FRESH_OK, LOG_FRESH_DEAD)
    state_status, state_msg = check_file_freshness("brain_state.json", STATE_FRESH_OK, STATE_FRESH_DEAD)
    err_status, err_msg = check_brain_err_growth()

    if pid is None:
        pid_alive_ok, pid_alive_msg = False, "skipped (no PID file)"
    else:
        pid_alive_ok, pid_alive_msg = check_pid_alive(pid)

    # Verdict
    if not pid_alive_ok:
        verdict = "DEAD"
    elif log_status == "DEAD" and state_status == "DEAD":
        verdict = "DEAD"
    elif log_status == "DEAD" or state_status == "DEAD":
        verdict = "WARN_STALE"
    else:
        verdict = "ALIVE"

    if verdict == "ALIVE" and args.quiet_on_alive:
        return 0

    print("Brain Liveness Check - " + datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"))
    print("=" * 44)
    print(f"brain.pid:                   {pid_msg}")
    print(f"PID alive:                   {pid_alive_msg}")
    print(f"brain.log freshness:         {log_msg}")
    print(f"brain_state.json freshness:  {state_msg}")
    print(f"brain.err size:              {err_msg}")
    print()
    print(f"VERDICT: {verdict}")

    if verdict == "DEAD" and not args.no_telegram:
        if should_send_telegram():
            msg = (f"[TrendMaster ALERT] Brain DEAD as of "
                   f"{datetime.now(timezone.utc).strftime('%H:%M UTC')}. "
                   f"Last log write {log_msg.split(' ')[0]} ago. "
                   f"Restart via start_brain_clean.cmd (pre-flight will catch issues).")
            ok = send_telegram(msg)
            if ok:
                print()
                print("Telegram alert sent.")
                record_telegram_sent()
            else:
                print()
                print("Telegram send FAILED — operator must check Telegram bot config.")
        else:
            print()
            print(f"(skipping Telegram — already paged within last {DEDUP_MINUTES}m)")

    return 0 if verdict == "ALIVE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
