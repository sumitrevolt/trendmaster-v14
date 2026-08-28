"""
Junction guard for TrendMaster v14.

Verifies ai_trading_agents/ is a valid junction → C:\\TrendMaster_aita_canonical\\
and the canonical folder has all expected modules. Pages Telegram on regression.

Pure-Python; subprocess + stdlib + ai_trading_agents.telegram_notifier.
"""

from __future__ import annotations
import sys as _sys
try:
    _sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import argparse
import random
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(r"C:\Users\Ratanshila\Documents\autmated trading")
JUNCTION = REPO / "ai_trading_agents"
CANONICAL = Path(r"C:\TrendMaster_aita_canonical")
LAST_ALERT = REPO / "logs" / "junction_guard_last_alert.txt"
EXPECTED_TARGET = "C:\\TrendMaster_aita_canonical"

EXPECTED_MODULES = [
    "ab_test", "advanced_features", "agent_training", "daily_digest", "drift_detector",
    "ea_confirmations", "event_log", "gate_value", "geopolitical_agent", "institutional_agents",
    "kelly_sizer", "market_calendar", "meta_labeler", "metrics", "ml_align", "model_governance",
    "multi_agent", "multi_market_dispatcher", "news_feed", "online_learner", "ops_maintenance",
    "pair_params", "panic", "performance", "portfolio_risk", "process_lock", "profit_filters",
    "reentry_tracker", "regime_hmm", "risk_manager", "rolling_corr", "state_store",
    "structured_log", "team_params", "telegram_commands", "telegram_notifier", "trade_tracker",
    "trend_master_brain", "__init__",
]


def check_junction_exists() -> tuple[bool, str]:
    if JUNCTION.exists():
        return True, "OK"
    return False, "FAIL — ai_trading_agents/ does NOT exist"


def check_is_reparse() -> tuple[bool, str]:
    try:
        out = subprocess.run(
            ["fsutil", "reparsepoint", "query", str(JUNCTION)],
            capture_output=True, text=True, timeout=10,
        )
        if out.returncode != 0:
            return False, f"FAIL — fsutil failed: {out.stderr.strip()[:80]}"
        if "Mount Point" in out.stdout:
            return True, "OK (Mount Point)"
        return False, "FAIL — reparse type is not Mount Point"
    except Exception as e:
        return False, f"FAIL — {type(e).__name__}: {e}"


def check_target() -> tuple[bool, str]:
    try:
        out = subprocess.run(
            ["fsutil", "reparsepoint", "query", str(JUNCTION)],
            capture_output=True, text=True, timeout=10,
        )
        if EXPECTED_TARGET.lower() in out.stdout.lower():
            return True, f"OK ({EXPECTED_TARGET})"
        return False, f"FAIL — target is not {EXPECTED_TARGET}"
    except Exception as e:
        return False, f"FAIL — {type(e).__name__}: {e}"


def check_canonical_exists() -> tuple[bool, str]:
    if CANONICAL.exists() and CANONICAL.is_dir():
        return True, "OK"
    return False, "FAIL — canonical folder missing"


def check_module_count() -> tuple[bool, str]:
    if not CANONICAL.exists():
        return False, "SKIP (canonical missing)"
    present = {p.stem for p in CANONICAL.glob("*.py")}
    expected = set(EXPECTED_MODULES)
    missing = expected - present
    if missing:
        return False, f"FAIL — missing {len(missing)} modules: {sorted(missing)[:5]}..."
    return True, f"OK ({len(present)}/{len(expected)})"


def check_no_nul_corruption(sample_size: int = 5) -> tuple[bool, str]:
    if not CANONICAL.exists():
        return False, "SKIP (canonical missing)"
    py_files = [p for p in CANONICAL.glob("*.py") if p.stem in EXPECTED_MODULES]
    if not py_files:
        return False, "SKIP (no .py files)"
    sample = random.sample(py_files, min(sample_size, len(py_files)))
    for f in sample:
        try:
            data = f.read_bytes()
            if b"\x00" in data:
                return False, f"FAIL — {f.name} contains NUL bytes"
        except Exception as e:
            return False, f"FAIL — {f.name} read error: {e}"
    return True, f"OK (sampled {len(sample)} modules)"


def check_brain_import() -> tuple[bool, str]:
    # If brain just restarted (<60s), skip — startup race
    pid_file = REPO / "logs" / "brain.pid"
    if pid_file.exists():
        age = (datetime.now() - datetime.fromtimestamp(pid_file.stat().st_mtime)).total_seconds()
        if age < 60:
            return True, "SKIP (brain just restarted, age < 60s)"
    try:
        out = subprocess.run(
            [str(REPO / ".venv" / "Scripts" / "python.exe"),
             "-c", "import ai_trading_agents.trend_master_brain"],
            cwd=str(REPO),
            capture_output=True, text=True, timeout=15,
        )
        if out.returncode == 0:
            return True, "OK"
        return False, f"FAIL — import error: {(out.stderr or '')[:120]}"
    except Exception as e:
        return False, f"FAIL — {type(e).__name__}: {e}"


def should_send_telegram() -> bool:
    if not LAST_ALERT.exists():
        return True
    try:
        last = datetime.fromisoformat(LAST_ALERT.read_text().strip())
        return (datetime.now() - last) > timedelta(minutes=60)
    except Exception:
        return True


def record_telegram_sent() -> None:
    LAST_ALERT.parent.mkdir(parents=True, exist_ok=True)
    LAST_ALERT.write_text(datetime.now().isoformat())


def send_telegram(msg: str) -> bool:
    try:
        sys.path.insert(0, str(REPO))
        from ai_trading_agents.telegram_notifier import get_notifier
        n = get_notifier()
        return bool(n.send(msg))
    except Exception:
        return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quiet-on-healthy", action="store_true")
    ap.add_argument("--no-telegram", action="store_true")
    args = ap.parse_args()

    checks = [
        ("Check 1 - ai_trading_agents/ exists", check_junction_exists),
        ("Check 2 - Is junction (reparse point)", check_is_reparse),
        ("Check 3 - Junction target correct", check_target),
        ("Check 4 - Canonical folder exists", check_canonical_exists),
        ("Check 5 - Module count vs expected", check_module_count),
        ("Check 6 - Random NUL-byte sample (5)", check_no_nul_corruption),
        ("Check 7 - Brain top-level import", check_brain_import),
    ]
    results = [(label, *fn()) for label, fn in checks]
    all_ok = all(ok for _, ok, _ in results)

    if all_ok and args.quiet_on_healthy:
        return 0

    print("Junction Guard - " + datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"))
    print("=" * 44)
    for label, ok, msg in results:
        print(f"{label:46s} {msg}")
    print()
    print(f"VERDICT: {'HEALTHY' if all_ok else 'REGRESSED'}")

    if not all_ok and not args.no_telegram and should_send_telegram():
        failed = [(label, msg) for label, ok, msg in results if not ok]
        msg = f"[TrendMaster ALERT] Junction guard failed at {datetime.now(timezone.utc).strftime('%H:%M UTC')}.\n"
        for label, m in failed[:3]:
            msg += f"- {label.split(' - ')[1]}: {m}\n"
        msg += "Restore via: rd /s /q ai_trading_agents && mklink /J ai_trading_agents C:\\TrendMaster_aita_canonical"
        if send_telegram(msg):
            print("Telegram alert sent.")
            record_telegram_sent()

    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
