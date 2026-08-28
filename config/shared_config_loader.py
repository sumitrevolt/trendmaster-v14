"""
shared_config_loader.py
=======================
Loads config/trading_config.yaml and exposes the dotted-namespace dicts
used by the brain (settings.py imports from here).

Rationale: keep YAML as the single source of truth so EA and Python
brain never drift again (see docs/ARCHITECTURE.md "Planned, not live"
section -> "Shared config file read by both Python and MQL5").

Usage in settings.py:

    from config.shared_config_loader import load_shared_config
    SHARED = load_shared_config()
    RISK_PERCENT = SHARED["risk"]["risk_percent"]

Falls back gracefully if the YAML is missing OR PyYAML isn't installed —
returns an empty dict, settings.py keeps its hard-coded defaults. This
makes adoption non-breaking: old code paths still work, new code paths
read from SHARED.
"""

from __future__ import annotations
from pathlib import Path
from typing import Any
import os

_CACHE: dict | None = None


def _yaml_path() -> Path:
    """Resolve YAML path - works from both Documents path AND junction target."""
    # NOTE: per CLAUDE.md, files inside ai_trading_agents/ must NOT use
    # .resolve() (it follows the junction). config/ lives outside the
    # junction, so .resolve() is fine here.
    here = Path(__file__).resolve().parent
    return here / "trading_config.yaml"


def load_shared_config(refresh: bool = False) -> dict[str, Any]:
    """Return the parsed shared YAML, or an empty dict if unavailable.

    Cached for the lifetime of the process unless refresh=True.
    """
    global _CACHE
    if _CACHE is not None and not refresh:
        return _CACHE

    path = _yaml_path()
    if not path.exists():
        _CACHE = {}
        return _CACHE

    try:
        import yaml  # type: ignore
    except ImportError:
        # Don't crash the brain just because pyyaml isn't installed.
        # Operator can `pip install pyyaml` to enable shared-config mode.
        _CACHE = {}
        return _CACHE

    try:
        with path.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
    except (OSError, yaml.YAMLError) as exc:  # pragma: no cover
        # Log to stderr but don't crash
        import sys
        print(f"[shared_config_loader] WARN: {exc}", file=sys.stderr)
        data = {}

    _CACHE = data
    return _CACHE


def get(path: str, default: Any = None) -> Any:
    """Dotted-path getter: get('risk.risk_percent', 0.5)"""
    cfg = load_shared_config()
    cur: Any = cfg
    for key in path.split("."):
        if isinstance(cur, dict) and key in cur:
            cur = cur[key]
        else:
            return default
    return cur


def env_or_shared(env_key: str, shared_path: str, default: Any,
                  cast: type = float) -> Any:
    """ENV variable overrides YAML; YAML overrides hard-coded default.

    This is the ergonomic way to migrate settings.py:

        RISK = {
            "risk_percent": env_or_shared(
                "RISK_PERCENT", "risk.risk_percent", 0.5
            ),
            ...
        }
    """
    env_val = os.getenv(env_key)
    if env_val is not None:
        try:
            return cast(env_val)
        except (TypeError, ValueError):
            pass
    yaml_val = get(shared_path, default)
    try:
        return cast(yaml_val) if yaml_val is not None else default
    except (TypeError, ValueError):
        return default


__all__ = ["load_shared_config", "get", "env_or_shared"]
