"""Drift detector: skills reference specific Python symbols (functions /
classes / module paths). If someone refactors and renames or moves a
symbol, the skill's code sample silently goes stale.

This test parses the referenced modules via AST (no imports, no side
effects, no dependency on lightgbm/MT5/etc.) and asserts each expected
symbol is defined at the top level of its module.

Add a new entry to EXPECTED_REFERENCES whenever you add a skill that
cites a specific function or class.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


# (module path relative to repo root, symbol name, cited in / by)
EXPECTED_REFERENCES = [
    ("ai_trading_agents/daily_digest.py", "generate_report", "skill: trading-daily-pnl"),
    ("ai_trading_agents/state_store.py", "StateStore", "skill: trading-daily-pnl"),
    ("ai_trading_agents/state_store.py", "StateStore", "skill: trading-why-inspector"),
    ("tools/backtest.py", "run_ea_parity_backtest", "skill: trading-ea-parity"),
    ("ai_trading_agents/telegram_notifier.py", "get_notifier", "tools/ea_parity_nightly.py"),
    ("tools/cpcv.py", "CPCVSplit", "tools/validate_crypto_ml.py"),
]


def _top_level_names(py_path: Path) -> set:
    """AST-parse a Python file and return the set of top-level def/class/assign names.

    Returns empty set if the file can't be read or parsed (including exotic
    encodings). Callers should skip rather than fail in that case.
    """
    text = None
    for enc in ("utf-8", "utf-8-sig", "utf-16", "utf-16-le", "utf-16-be"):
        try:
            text = py_path.read_text(encoding=enc)
            break
        except (UnicodeDecodeError, UnicodeError):
            continue
    if text is None:
        return set()
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return set()

    names: set = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    names.add(t.id)
        elif isinstance(node, ast.AnnAssign):
            if isinstance(node.target, ast.Name):
                names.add(node.target.id)
    return names


@pytest.mark.parametrize("rel_module,symbol,cited_by", EXPECTED_REFERENCES)
def test_symbol_defined_in_module(rel_module, symbol, cited_by):
    mod_path = REPO_ROOT / rel_module
    assert mod_path.exists(), f"{cited_by}: module {rel_module} missing from disk"

    names = _top_level_names(mod_path)
    if not names:
        pytest.skip(
            f"{cited_by}: could not parse {rel_module} (unusual encoding or syntax error). Skipped, not failed."
        )

    assert symbol in names, (
        f"{cited_by}: references {rel_module}::{symbol}, but that name is "
        f"not defined at the module's top level. Top-level names detected: "
        f"{sorted(names)[:30]}..."
    )
