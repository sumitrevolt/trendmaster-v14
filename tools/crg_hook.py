"""Cross-platform wrapper for the code-review-graph update hook.

Used by pre-commit and Claude Code's PostToolUse hook. Always exits 0
— a broken graph update must NEVER block a commit or a tool call.

Behavior:
  - If the project has no .git directory, skip silently (the `update`
    subcommand requires git for diffing).
  - If the `code-review-graph` CLI isn't on PATH, skip silently.
  - Otherwise run `code-review-graph update --skip-flows` and swallow
    its exit code / output.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    if not (ROOT / ".git").exists():
        return 0  # no git → nothing to diff
    cli = shutil.which("code-review-graph")
    if cli is None:
        return 0  # CLI not installed → skip quietly
    try:
        subprocess.run(
            [cli, "update", "--skip-flows"],
            cwd=str(ROOT),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=30,
            check=False,
        )
    except (subprocess.TimeoutExpired, OSError):
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
