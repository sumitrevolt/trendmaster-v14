"""
write_brain_pid.py - find the running brain process and write its PID to
logs/brain.pid so watch-pets / brain-liveness can verify aliveness.

Called from start_brain_clean.cmd after the 15-second boot wait.

Strategy:
  1. Prefer logs/brain.lock content (set by SingleInstanceLock).
  2. Fall back to scanning python.exe processes for trend_master_brain.
  3. Idempotent: only writes brain.pid if a real brain is found.
"""

from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
LOGS = ROOT / "logs"
PID_FILE = LOGS / "brain.pid"
LOCK_FILE = LOGS / "brain.lock"


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        import ctypes

        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        STILL_ACTIVE = 259
        h = ctypes.windll.kernel32.OpenProcess(
            PROCESS_QUERY_LIMITED_INFORMATION, 0, pid
        )
        if not h:
            return False
        try:
            exit_code = ctypes.c_ulong()
            ok = ctypes.windll.kernel32.GetExitCodeProcess(h, ctypes.byref(exit_code))
            if not ok:
                return False
            return exit_code.value == STILL_ACTIVE
        finally:
            ctypes.windll.kernel32.CloseHandle(h)
    except Exception:
        return False


def _from_lock() -> int | None:
    if not LOCK_FILE.exists():
        return None
    try:
        pid = int(LOCK_FILE.read_text(encoding="ascii").strip() or "0")
    except (ValueError, OSError):
        return None
    return pid if _pid_alive(pid) else None


def _from_scan() -> int | None:
    try:
        import subprocess
        out = subprocess.check_output(
            [
                "powershell",
                "-NoProfile",
                "-Command",
            "Get-CimInstance Win32_Process -Filter \"name='python.exe' OR name='pythonw.exe'\" | "
            "Where-Object { $_.CommandLine -match 'trend_master_brain' } | "
                "Select-Object -First 1 -ExpandProperty ProcessId",
            ],
            text=True,
            timeout=10,
        ).strip()
        if out and out.isdigit():
            return int(out)
    except Exception:
        pass
    return None


def main() -> int:
    LOGS.mkdir(parents=True, exist_ok=True)
    pid = _from_lock()
    src = "lock" if pid else None
    if not pid:
        pid = _from_scan()
        src = "scan"
    if not pid:
        print("WARN: no brain process found; brain.pid not written", file=sys.stderr)
        return 1
    PID_FILE.write_text(str(pid), encoding="ascii")
    print(f"brain.pid set to {pid} (source: {src})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
