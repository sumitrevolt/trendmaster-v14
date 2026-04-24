"""
process_lock.py — single-instance guard for the brain.

Why
---
START_TRENDMASTER_v14.bat clicked twice ⇒ two brains writing the same
trendmaster_signals.json ⇒ EA reads torn writes ⇒ duplicate orders.
This module gives us a hard "only one of me may run" lock that works on
both Windows (msvcrt.locking) and POSIX (fcntl.flock), with an automatic
PID staleness check (if the holding PID is gone, we steal the lock).

Usage
-----
    from ai_trading_agents.process_lock import SingleInstanceLock

    with SingleInstanceLock("brain") as lock:
        if not lock.acquired:
            # another instance is alive — bail out cleanly
            return
        run_forever()
"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Optional

logger = logging.getLogger("process_lock")

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent
_LOCK_DIR = _ROOT / "logs"


def _pid_alive(pid: int) -> bool:
    """Return True if the given PID is currently running (cross-platform)."""
    if pid <= 0:
        return False
    if os.name == "nt":
        try:
            import ctypes
            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            STILL_ACTIVE = 259
            h = ctypes.windll.kernel32.OpenProcess(
                PROCESS_QUERY_LIMITED_INFORMATION, 0, pid)
            if not h:
                return False
            try:
                exit_code = ctypes.c_ulong()
                ok = ctypes.windll.kernel32.GetExitCodeProcess(
                    h, ctypes.byref(exit_code))
                if not ok:
                    return False
                return exit_code.value == STILL_ACTIVE
            finally:
                ctypes.windll.kernel32.CloseHandle(h)
        except Exception:
            return False
    # POSIX
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError):
        return False


class SingleInstanceLock:
    """
    File-based single-instance lock.

    On enter:
        * Reads existing logs/<name>.lock; if PID inside is alive, sets
          self.acquired=False and returns (caller must check + bail).
        * Otherwise writes our PID + flocks the file. self.acquired=True.

    On exit:
        * Releases the flock, deletes the file.
    """

    def __init__(self, name: str = "brain", lock_dir: Optional[Path] = None):
        self.name = name
        self.lock_dir = lock_dir or _LOCK_DIR
        self.lock_dir.mkdir(parents=True, exist_ok=True)
        self.lock_path = self.lock_dir / f"{name}.lock"
        self._fh = None
        self.acquired: bool = False
        self.holder_pid: Optional[int] = None

    def __enter__(self) -> "SingleInstanceLock":
        # Read any prior holder PID. If alive, refuse to start.
        if self.lock_path.exists():
            try:
                prior = int(self.lock_path.read_text(encoding="ascii").strip() or "0")
            except (ValueError, OSError):
                prior = 0
            if prior and _pid_alive(prior) and prior != os.getpid():
                self.holder_pid = prior
                self.acquired = False
                logger.error(
                    "Another %s instance is already running (PID=%d). "
                    "Lock file: %s. Refusing to start a second brain.",
                    self.name, prior, self.lock_path,
                )
                return self
            # Stale — steal it.
            try:
                self.lock_path.unlink()
            except OSError:
                pass

        # Open + lock.
        self._fh = open(self.lock_path, "w", encoding="ascii")
        if not self._platform_lock(self._fh):
            self.acquired = False
            self._fh.close()
            self._fh = None
            logger.error("Could not acquire OS lock on %s. Another instance "
                         "may be racing us. Refusing to start.", self.lock_path)
            return self

        self._fh.write(str(os.getpid()))
        self._fh.flush()
        try:
            os.fsync(self._fh.fileno())
        except OSError:
            pass
        self.acquired = True
        logger.info("Acquired %s lock (pid=%d, file=%s)",
                    self.name, os.getpid(), self.lock_path)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if self._fh is not None:
            try:
                self._platform_unlock(self._fh)
            except Exception:
                pass
            try:
                self._fh.close()
            except Exception:
                pass
            self._fh = None
        try:
            if self.lock_path.exists():
                # Only unlink if the file still has our PID (don't nuke
                # a successor's lock that happened to claim it during a race).
                try:
                    inside = int(self.lock_path.read_text(encoding="ascii").strip() or "0")
                except (ValueError, OSError):
                    inside = 0
                if inside == os.getpid() or not inside:
                    self.lock_path.unlink()
        except OSError:
            pass

    # ─── platform helpers ────────────────────────────────────────────────
    def _platform_lock(self, fh) -> bool:
        if os.name == "nt":
            try:
                import msvcrt
                # LK_NBLCK = non-blocking exclusive lock on first byte.
                msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
                return True
            except OSError:
                return False
        try:
            import fcntl
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except (OSError, ImportError):
            return False

    def _platform_unlock(self, fh) -> None:
        if os.name == "nt":
            try:
                import msvcrt
                msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
            except OSError:
                pass
            return
        try:
            import fcntl
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        except (OSError, ImportError):
            pass


__all__ = ["SingleInstanceLock"]
