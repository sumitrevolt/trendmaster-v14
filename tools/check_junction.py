"""Pre-commit + post-commit guard: verify the ai_trading_agents/ NTFS junction.

Purpose
-------
Pre-commit's ``git stash`` / ``git stash pop`` cycle on Windows can
replace the ``ai_trading_agents/`` junction with a real directory (or
remove it) when an auto-fix hook reformats files inside the junction
target. See ``docs/POSTMORTEMS/2026-04-26_pre_commit_junction_breakage.md``
and ``docs/POSTMORTEMS/2026-04-30_junction_trap_silent_state_drift.md``.

Modes
-----
- **Default (pre-commit)**: check-only. Print a loud error and exit
  non-zero if the junction is missing/wrong, aborting the commit.
- **--heal (post-commit / post-checkout / post-merge)**: also auto-run
  ``tools/restore_junction.cmd`` when the check fails. This covers the
  case observed 2026-04-30: the pre-commit ``check-junction`` hook
  passes (junction OK at hook-run time) but the *subsequent*
  ``[INFO] Restored changes from ...`` stash-pop step replaces the
  junction with a real folder. A post-commit invocation with --heal
  re-restores it before the operator's next command runs.

Design rules
------------
- **Standard library only.** No new pip dependencies; this runs from
  the project's existing ``language: system`` pre-commit shell.
- **Cross-platform safe.** On non-Windows the junction concept does
  not exist; the script exits 0 silently so CI on Linux stays green.
- **No hard-coded drive letters in the comparison.** We resolve the
  expected target via ``os.path.realpath`` and compare normalized
  paths so the check still works if the canonical source is ever
  relocated (just update ``EXPECTED_TARGET`` here).
- **No false positives on a clean repo.** A healthy junction whose
  ``realpath`` resolves to the canonical folder must produce exit 0.

Exit codes
----------
0 - junction healthy, or non-Windows (skipped), or broken+healed (with --heal)
1 - junction missing, replaced with a real folder, or pointing
    somewhere unexpected (and either --heal not set, or heal failed)
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

# The junction path (worktree-relative) and its expected NTFS target.
# Both are resolved/normalized before comparison.
JUNCTION_RELATIVE = "ai_trading_agents"
EXPECTED_TARGET = r"C:\TrendMaster_aita_canonical"


def _norm(p: str | Path) -> str:
    """Normalize a path for case-insensitive comparison on Windows."""
    return os.path.normcase(os.path.normpath(str(p)))


def _check(project_root: Path) -> tuple[bool, str]:
    """Return (ok, reason). reason is the human-readable failure cause."""
    junction = project_root / JUNCTION_RELATIVE
    if not junction.exists():
        return False, f"ai_trading_agents/ is MISSING at {junction}"
    actual_target = _norm(os.path.realpath(junction))
    expected_target = _norm(EXPECTED_TARGET)
    if actual_target != expected_target:
        return False, (
            f"ai_trading_agents/ does NOT resolve to {EXPECTED_TARGET}\n"
            f"  realpath -> {actual_target}\n"
            f"  expected -> {expected_target}"
        )
    brain_entry = junction / "trend_master_brain.py"
    if not brain_entry.exists():
        return False, (f"ai_trading_agents/ resolves correctly but trend_master_brain.py is missing at {brain_entry}")
    return True, ""


def _heal(project_root: Path) -> bool:
    """Run tools/restore_junction.cmd. Return True on success."""
    cmd = project_root / "tools" / "restore_junction.cmd"
    if not cmd.exists():
        print(f"[heal] cannot heal: {cmd} missing", file=sys.stderr)
        return False
    try:
        result = subprocess.run(
            ["cmd.exe", "/c", str(cmd)],
            cwd=str(project_root),
            capture_output=True,
            text=True,
            timeout=30,
        )
    except subprocess.SubprocessError as e:
        print(f"[heal] restore_junction.cmd failed to launch: {e}", file=sys.stderr)
        return False
    sys.stderr.write(result.stdout)
    sys.stderr.write(result.stderr)
    return result.returncode == 0


def main() -> int:
    if sys.platform != "win32":
        # The junction is a Windows-NTFS construct; on Linux/macOS
        # CI runners the path is just a checked-out directory tree
        # and there is nothing to verify. Skip silently.
        return 0

    heal_mode = "--heal" in sys.argv[1:]

    # Resolve the project root from this file's location. tools/ is
    # OUTSIDE the junction, so realpath here is safe and points at the
    # real worktree root (no junction traversal).
    project_root = Path(__file__).resolve().parent.parent

    ok, reason = _check(project_root)
    if ok:
        return 0

    if heal_mode:
        # Quiet, single-line auto-heal — this runs as a post-commit
        # hook after every commit, so verbose noise on healthy commits
        # is undesirable.
        print(
            f"[junction-guard] junction broken — {reason.splitlines()[0]}",
            file=sys.stderr,
        )
        print("[junction-guard] running tools/restore_junction.cmd ...", file=sys.stderr)
        if _heal(project_root):
            ok2, _ = _check(project_root)
            if ok2:
                print("[junction-guard] junction healed.", file=sys.stderr)
                return 0
            print(
                "[junction-guard] heal ran but check still fails. Investigate.",
                file=sys.stderr,
            )
        # Fall through to loud error if heal failed.

    _print_error(
        *reason.splitlines(),
        "The junction was probably replaced with a real folder by",
        "pre-commit's stash/restore cycle.",
    )
    return 1


def _print_error(*lines: str) -> None:
    """Print a loud, copy-paste-able error block to stderr."""
    bar = "=" * 72
    print(bar, file=sys.stderr)
    print("PRE-COMMIT JUNCTION GUARD: FAIL", file=sys.stderr)
    print(bar, file=sys.stderr)
    for line in lines:
        print(line, file=sys.stderr)
    print("", file=sys.stderr)
    print("Recovery:", file=sys.stderr)
    print(r"    tools\restore_junction.cmd", file=sys.stderr)
    print("", file=sys.stderr)
    print(
        "See docs/POSTMORTEMS/2026-04-26_pre_commit_junction_breakage.md",
        file=sys.stderr,
    )
    print(bar, file=sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main())
