"""Unit tests for ai_trading_agents/process_lock.py."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from ai_trading_agents.process_lock import SingleInstanceLock, _pid_alive


# ─── _pid_alive ────────────────────────────────────────────────────────────
def test_pid_alive_zero_returns_false():
    assert _pid_alive(0) is False


def test_pid_alive_negative_returns_false():
    assert _pid_alive(-1) is False


def test_pid_alive_self_returns_true():
    assert _pid_alive(os.getpid()) is True


def test_pid_alive_clearly_dead_pid_returns_false():
    # PID 999_999_999 is astronomically unlikely to exist on either OS.
    assert _pid_alive(999_999_999) is False


# ─── SingleInstanceLock — basic acquire/release ───────────────────────────
def test_lock_can_be_acquired(tmp_path: Path):
    with SingleInstanceLock("test_acq", lock_dir=tmp_path) as lock:
        assert lock.acquired is True
        assert lock.lock_path.exists()


def test_lock_releases_file_on_exit(tmp_path: Path):
    with SingleInstanceLock("test_rel", lock_dir=tmp_path) as lock:
        lock_path = lock.lock_path
        assert lock_path.exists()
    # After exit the file should be gone (we held it, so we own cleanup).
    assert not lock_path.exists()


def test_lock_writes_current_pid_into_file(tmp_path: Path):
    """The lock file holds our PID. On Windows the byte is OS-locked while
    the context manager is active AND the file is opened write-only, so we
    can't peek mid-context. Instead patch the unlink step on exit so the
    file survives, then read it once the lock is released."""
    captured = {}

    class _NoUnlinkLock(SingleInstanceLock):
        def __exit__(self, *a):
            # Flush whatever was written so we can read it after release.
            try:
                self._fh.flush()
            except Exception:
                pass
            # Snapshot the file contents while the handle is still open
            # by re-reading the buffered bytes via low-level os.read isn't
            # reliable — instead snapshot the path's bytes after closing
            # but before the parent unlink.
            try:
                self._platform_unlock(self._fh)
            except Exception:
                pass
            try:
                self._fh.close()
            except Exception:
                pass
            captured["text"] = self.lock_path.read_text(encoding="ascii").strip()
            # Now do the normal cleanup.
            try:
                if self.lock_path.exists():
                    self.lock_path.unlink()
            except OSError:
                pass

    with _NoUnlinkLock("test_pid", lock_dir=tmp_path) as lock:
        assert lock.acquired

    assert int(captured["text"]) == os.getpid()


# ─── stale-PID stealing ────────────────────────────────────────────────────
def test_stale_pid_lock_is_stolen(tmp_path: Path):
    # Pre-write a lock file with a clearly-dead PID.
    stale_lock = tmp_path / "stale.lock"
    stale_lock.write_text("999999999", encoding="ascii")

    # If the stale-steal logic worked, acquired must be True (a live PID
    # would have set it to False instead). We don't need to read the file
    # contents to prove it — the acquired flag is the contract.
    with SingleInstanceLock("stale", lock_dir=tmp_path) as lock:
        assert lock.acquired is True
        assert lock.holder_pid is None  # we stole it, no foreign holder


# ─── second acquisition refused while first held (Windows) ────────────────
@pytest.mark.skipif(sys.platform != "win32",
                    reason="msvcrt-based exclusive lock is Windows-only; "
                           "POSIX flock between two FDs of the same process "
                           "behaves differently and isn't part of this test.")
def test_second_acquisition_refused_while_first_held(tmp_path: Path):
    first = SingleInstanceLock("dup", lock_dir=tmp_path)
    first.__enter__()
    try:
        assert first.acquired is True
        # Manually pre-seed a different PID into the file so the PID-alive
        # branch refuses the second attempt (we can't truly fork in pytest).
        # Use our own PID + 1 if alive, else fall back to OS-level lock test.
        # Easier: directly assert the OS-level lock prevents a second fh.
        second_fh = open(first.lock_path, "w", encoding="ascii")
        try:
            import msvcrt
            with pytest.raises(OSError):
                msvcrt.locking(second_fh.fileno(), msvcrt.LK_NBLCK, 1)
        finally:
            second_fh.close()
    finally:
        first.__exit__(None, None, None)


def test_second_acquisition_refused_when_holder_pid_is_alive(tmp_path: Path):
    """The PID-alive branch: if the lock file contains a live foreign PID,
    a fresh SingleInstanceLock must report acquired=False."""
    # Use a PID that we know is alive but is NOT our own — the parent shell.
    # On Windows os.getppid() works; on POSIX too. If parent==self for some
    # reason, fall back to spawning won't work in-test, so just simulate by
    # writing our own pid and forcing the "prior != os.getpid()" branch via
    # a small monkey: write a different live pid (parent).
    foreign_pid = os.getppid()
    if foreign_pid == os.getpid() or foreign_pid <= 0 or not _pid_alive(foreign_pid):
        pytest.skip("no suitable foreign live PID available in this environment")

    lock_path = tmp_path / "guard.lock"
    lock_path.write_text(str(foreign_pid), encoding="ascii")

    with SingleInstanceLock("guard", lock_dir=tmp_path) as lock:
        assert lock.acquired is False
        assert lock.holder_pid == foreign_pid
