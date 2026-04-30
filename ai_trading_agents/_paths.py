"""
_paths.py — single source of truth for the project root inside the
``ai_trading_agents/`` junction.

Why
---
``ai_trading_agents/`` is a Windows NTFS junction to
``C:\\TrendMaster_aita_canonical\\``. CLAUDE.md's rule
``Path(__file__).parent.parent`` (NEVER ``.resolve()``) is necessary but not
sufficient: even without an explicit ``.resolve()`` call, Python on Windows
can return ``__file__`` through the canonical target depending on how the path
was cached at import time. When that happens, ``parent.parent`` lands on
``C:\\`` instead of the project root and every config-file/state-file lookup
silently writes to ``C:\\logs\\``.

Observed in production 2026-04-30: ``state_store.py``, ``event_log.py``, and
``process_lock.py`` all wrote to ``C:\\logs\\`` for ~90 minutes despite
correct cwd, despite no ``.resolve()`` calls. See
``docs/POSTMORTEMS/2026-04-30_junction_trap_silent_state_drift.md``.

Usage
-----
    from ai_trading_agents._paths import project_root
    ROOT = project_root()
    state_path = ROOT / "logs" / "brain_state.json"

The helper validates by checking for ``config/settings.py`` (a known project
invariant). If absent, falls back to ``Path.cwd()`` — the brain launcher
(``start_brain_clean.cmd``) always sets cwd to the project root via ``cd /d``,
so cwd is the safe fallback.
"""

from __future__ import annotations

from pathlib import Path

_HERE = Path(__file__).parent
_INVARIANT = ("config", "settings.py")


def project_root() -> Path:
    """Return the project root, resilient to the junction trap.

    Validates the candidate by looking for ``config/settings.py``; if the
    invariant is missing under the candidate, falls back to ``Path.cwd()``.
    """
    candidate = _HERE.parent
    if (candidate / _INVARIANT[0] / _INVARIANT[1]).exists():
        return candidate
    return Path.cwd()


__all__ = ["project_root"]
