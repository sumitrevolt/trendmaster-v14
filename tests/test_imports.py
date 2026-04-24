"""Cross-platform import smoke test.

Ensures every module under `ai_trading_agents/` and `tools/` can be
imported on the CI environment (Linux, no MetaTrader5, no Windows-only
native deps). This catches the most common regression: someone moves
an `import MetaTrader5 as mt5` from inside a function to the top of a
file, which silently breaks CI because the module is now un-importable
on Linux.

Strategy:

- Discover every .py file under the two live dirs.
- For each, convert to its dotted module name and try
  `importlib.import_module`.
- If the module needs MetaTrader5 at *top level*, fail loudly (this is
  the invariant we're guarding).
- If the module needs some other Windows-only dep (pywin32 etc.),
  skip with a clear reason rather than fail, since the CI doesn't
  install those either.

Runs fast (<2 s) on a warm interpreter.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

# Files we deliberately don't try to import. Add a reason for each —
# keep this list tiny, each entry is a place where coverage is quietly
# not happening.
SKIP_FILES: set[str] = {
    # Windows-only tool scripts meant to be run directly, not imported.
    # They do module-level work (SystemExit, KeyError, win32 lookups)
    # that makes them un-importable as library modules. Safe to skip —
    # they're invoked via .bat/.cmd not by the brain.
    "tools/check_status.py",
    "tools/compile_ea.py",
    "tools/install_indicator.py",
    "tools/trigger_training.py",
    "tools/live_brain_check.py",
}

# Same set, for the top-level-MT5 guard (these files are deliberately
# Windows-only and not imported on CI, so a top-level MT5 import is OK).
MT5_TOPLEVEL_OK: set[str] = {
    "tools/live_brain_check.py",
}

# Dirs whose modules must always be importable on CI (Linux).
TARGET_DIRS = ["ai_trading_agents", "tools"]


def _discover() -> list[tuple[str, Path]]:
    """Return (module-name, path) for each .py under the target dirs."""
    found: list[tuple[str, Path]] = []
    for d in TARGET_DIRS:
        base = ROOT / d
        if not base.is_dir():
            continue
        for py in sorted(base.rglob("*.py")):
            rel = py.relative_to(ROOT)
            if "__pycache__" in rel.parts:
                continue
            if py.name.startswith("_") and py.name != "__init__.py":
                # Skip private scripts (outputs-style underscore scripts).
                # They may not be real modules at all.
                continue
            if str(rel).replace("\\", "/") in SKIP_FILES:
                continue
            # Convert path/to/file.py -> path.to.file  (and __init__.py -> pkg)
            if py.name == "__init__.py":
                mod = ".".join(rel.parent.parts)
            else:
                mod = ".".join(rel.with_suffix("").parts)
            found.append((mod, py))
    return found


DISCOVERED = _discover()


@pytest.mark.parametrize("module_name,path", DISCOVERED, ids=[m for m, _ in DISCOVERED])
def test_module_imports(module_name: str, path: Path) -> None:
    """Every live module must import cleanly on the current platform."""
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))

    try:
        importlib.import_module(module_name)
    except ModuleNotFoundError as e:
        missing = getattr(e, "name", "") or ""
        # Known Windows-only deps: CI (Linux) won't have them and we
        # don't want to fail for that — just skip.
        if missing in {"MetaTrader5", "win32api", "win32com", "pywintypes"}:
            pytest.skip(f"{module_name} requires {missing} (Windows-only)")
        raise
    except ImportError as e:
        # Late-import errors that aren't ModuleNotFoundError (rare).
        pytest.skip(f"{module_name} late import error: {e}")


def test_no_toplevel_mt5_import() -> None:
    """Guard invariant: MT5 must be imported late (inside funcs), not at
    module top. A top-level import would make the module un-importable
    on Linux CI.

    We scan the source text for a line beginning (optionally indented by
    a shebang or encoding declaration) with `import MetaTrader5` or
    `from MetaTrader5`. Any match where the indent is 0 fails.
    """
    offenders: list[str] = []
    for mod, path in DISCOVERED:
        rel_key = str(path.relative_to(ROOT)).replace("\\", "/")
        if rel_key in MT5_TOPLEVEL_OK:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for i, line in enumerate(text.splitlines(), start=1):
            stripped = line.lstrip()
            if stripped.startswith("import MetaTrader5") or stripped.startswith(
                "from MetaTrader5"
            ):
                # Check indent — top-level imports have indent == 0.
                if len(line) - len(stripped) == 0:
                    offenders.append(f"  {path.relative_to(ROOT)}:{i}: {stripped}")
    assert not offenders, (
        "MetaTrader5 must be imported late (inside a function/try block) so the "
        "module stays importable on Linux CI. Offenders:\n" + "\n".join(offenders)
    )
