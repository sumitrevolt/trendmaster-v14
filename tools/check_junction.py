"""Pre-commit guard: verify the ai_trading_agents/ NTFS junction is intact.

Purpose
-------
Pre-commit's ``git stash`` / ``git stash pop`` cycle on Windows can
replace the ``ai_trading_agents/`` junction with a real directory (or
remove it) when an auto-fix hook reformats files inside the junction
target. See ``docs/POSTMORTEMS/2026-04-26_pre_commit_junction_breakage.md``
for the failure mode in full.

This hook runs after the auto-fix stage on every commit. If the
junction is broken it prints a loud error and exits non-zero, which
aborts the commit before the operator pushes a corrupted worktree.

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
0 - junction healthy, or non-Windows (skipped)
1 - junction missing, replaced with a real folder, or pointing
    somewhere unexpected
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# The junction path (worktree-relative) and its expected NTFS target.
# Both are resolved/normalized before comparison.
JUNCTION_RELATIVE = "ai_trading_agents"
EXPECTED_TARGET = r"C:\TrendMaster_aita_canonical"


def _norm(p: str | Path) -> str:
    """Normalize a path for case-insensitive comparison on Windows."""
    return os.path.normcase(os.path.normpath(str(p)))


def main() -> int:
    if sys.platform != "win32":
        # The junction is a Windows-NTFS construct; on Linux/macOS
        # CI runners the path is just a checked-out directory tree
        # and there is nothing to verify. Skip silently.
        return 0

    # Resolve the project root from this file's location. tools/ is
    # OUTSIDE the junction, so realpath here is safe and points at the
    # real worktree root (no junction traversal).
    project_root = Path(__file__).resolve().parent.parent
    junction = project_root / JUNCTION_RELATIVE

    if not junction.exists():
        _print_error(
            f"ai_trading_agents/ is MISSING at {junction}",
            "The junction was deleted (likely by pre-commit's stash/restore).",
        )
        return 1

    # The junction must resolve to the canonical target. realpath on
    # Windows follows reparse points, so a real (non-junction) folder
    # at this path will resolve to itself, NOT to the canonical target,
    # and the comparison below will fail loudly.
    actual_target = _norm(os.path.realpath(junction))
    expected_target = _norm(EXPECTED_TARGET)

    if actual_target != expected_target:
        _print_error(
            f"ai_trading_agents/ does NOT resolve to {EXPECTED_TARGET}",
            f"  realpath -> {actual_target}",
            f"  expected -> {expected_target}",
            "The junction was probably replaced with a real folder by",
            "pre-commit's stash/restore cycle.",
        )
        return 1

    # Sanity: the canonical target should contain the brain entrypoint.
    # This catches the rare case where the canonical folder has been
    # emptied out from under us.
    brain_entry = junction / "trend_master_brain.py"
    if not brain_entry.exists():
        _print_error(
            "ai_trading_agents/ resolves correctly but trend_master_brain.py",
            f"is missing at {brain_entry}",
            "The canonical folder may have been wiped.",
        )
        return 1

    return 0


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
