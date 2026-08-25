"""Pipeline integrity guard tests.

[2026-05-09 GODMODE] These tests prevent the next 5-day silent failure.
Run them in CI / pre-commit so the executor's strategy whitelist and
safety gates can never silently drop a known-valid signal source again.

The original 5-day failure happened because:
  - tools/python_signal_executor.py ALLOWED_STRATEGIES did NOT contain
    "local_generator", so 76 signals/run were silently dropped.
  - There was no automated check that ALLOWED_STRATEGIES stays in sync
    with the actual strategy strings written by the receivers/generators.

Run: pytest -xvs tests/test_pipeline_integrity.py
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

# --------------------------------------------------------------------------
# Test 1: ALLOWED_STRATEGIES contains every known strategy string written
#         elsewhere in the codebase.
# --------------------------------------------------------------------------

# Every place a tv_strategy value can appear in a written signal.
# If you add a new strategy elsewhere, also add it to ALLOWED_STRATEGIES
# in tools/python_signal_executor.py — these tests will tell you if you
# forgot.
KNOWN_STRATEGIES = {
    "rocket_prime",
    "rocket_prime_text",
    "rocket_prime_inferred",
    "rocket_prime_plot0",
    "rocket_prime_plot1",
    "rocket_prime_url_direction",
    "rocket_prime_chart_ocr",  # OCR-based chart image strategy
    "telegram_manual_direction",  # Operator-tapped direction via inline keyboard
    # [2026-05-09 00:50 IST] local_generator removed per operator decision —
    # Rocket-Prime-only mode. Re-add this string if you re-enable EMA-cross
    # trades by uncommenting "local_generator" in ALLOWED_STRATEGIES.
    # "local_generator",
}


def _read_executor_source() -> str:
    return (ROOT / "tools" / "python_signal_executor.py").read_text(encoding="utf-8")


def _extract_allowed_strategies() -> set[str]:
    """Extract the ALLOWED_STRATEGIES set body and return the quoted strings,
    skipping any inside Python comments (which can contain arbitrary text).
    """
    src = _read_executor_source()
    m = re.search(r"ALLOWED_STRATEGIES\s*=\s*\{([^}]+)\}", src, re.DOTALL)
    assert m, "ALLOWED_STRATEGIES set not found in python_signal_executor.py"
    body = m.group(1)
    # Strip inline comments line-by-line (`# ...` to end-of-line)
    lines = []
    for line in body.splitlines():
        idx = line.find("#")
        if idx >= 0:
            line = line[:idx]
        lines.append(line)
    code_only = "\n".join(lines)
    return set(re.findall(r'"([^"]+)"', code_only))


def test_allowed_strategies_contains_all_known() -> None:
    """ALLOWED_STRATEGIES set in python_signal_executor.py must contain every
    strategy string ever written by a signal source. Missing entries → silent
    drop = 5-day failure.
    """
    found = _extract_allowed_strategies()
    missing = KNOWN_STRATEGIES - found
    assert not missing, (
        f"ALLOWED_STRATEGIES missing entries: {sorted(missing)}.\n"
        f"This was the 5-day silent failure root cause. Add them to the set."
    )


def test_allowed_strategies_no_extras() -> None:
    """Sanity: ALLOWED_STRATEGIES shouldn't have phantom entries that no
    source actually writes — those clutter the gate without protecting it.
    """
    found = _extract_allowed_strategies()
    extras = found - KNOWN_STRATEGIES
    assert not extras, (
        f"ALLOWED_STRATEGIES has unknown entries: {sorted(extras)}.\n"
        f"If these are new strategies, add them to KNOWN_STRATEGIES at the "
        f"top of this test. If they're stale, remove from the executor."
    )


# --------------------------------------------------------------------------
# Test 2: load_signal must log a skip reason whenever it returns None.
# --------------------------------------------------------------------------

def test_load_signal_no_silent_returns() -> None:
    """The 5-day failure root cause: `if strategy not in ALLOWED_STRATEGIES:
    return None` had NO log call, so dropped signals were invisible. Make
    sure every `return None` inside load_signal is preceded by a log call
    within ~6 lines.
    """
    src = _read_executor_source()
    # Find load_signal function body
    m = re.search(r"def load_signal\([^)]*\)[^:]*:\n((?:    .*\n|\n)+)", src)
    assert m, "load_signal function not found"
    body = m.group(1)
    lines = body.splitlines()
    for i, line in enumerate(lines):
        if "return None" in line and "#" not in line.split("return")[0]:
            # Check for a log call in the previous 6 lines
            window = "\n".join(lines[max(0, i - 6) : i + 1])
            assert re.search(r"\blog\.(info|warning|error|debug)\(", window), (
                f"load_signal line {i} returns None without a log call in "
                f"the preceding 6 lines:\n{window}\n"
                f"This is the 5-day-silent-failure pattern. Add a "
                f"log.info('skip ...: reason') before return None."
            )


# --------------------------------------------------------------------------
# Test 3: The startup banner exists and exits hard if safeguards disabled.
# --------------------------------------------------------------------------

def test_startup_banner_exists() -> None:
    src = _read_executor_source()
    assert "_print_startup_banner" in src, (
        "Startup banner removed. Re-add it — silent disabled gates were "
        "what caused the 5-day failure to be invisible."
    )


def test_safeguards_failure_is_hard_exit() -> None:
    """If safeguards_check is None at startup, the executor MUST refuse to
    trade unless TM_NO_SAFEGUARDS=1 is explicitly set. Trading without
    concentration caps + DD breaker + news blackout = blow up the account.
    """
    src = _read_executor_source()
    assert "REFUSING TO TRADE WITHOUT SAFEGUARDS" in src, (
        "Hard-fail-on-safeguards-disabled removed. Restore it — trading "
        "without gates is unrecoverable."
    )
    assert "sys.exit(2)" in src, "sys.exit(2) on safeguards failure missing"


# --------------------------------------------------------------------------
# Test 4: Skip taxonomy in heartbeat
# --------------------------------------------------------------------------

def test_heartbeat_has_skip_taxonomy() -> None:
    """Heartbeat should report `no_file=N filtered=N stale=N` not just `skipped=N`,
    so the operator can SEE which gate is dropping signals.
    """
    src = _read_executor_source()
    assert "skipped_strategy_filter" in src, (
        "Skip taxonomy missing. Without it, the next silent drop won't be "
        "visible in the heartbeat — exactly the 5-day failure pattern."
    )
    assert "no_file=" in src and "filtered=" in src and "stale=" in src, (
        "Heartbeat should print no_file=, filtered=, stale= breakdown."
    )


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-xvs"]))
