"""
Morning routine composite for TrendMaster v14.

Runs 5 diagnostic skills in sequence, captures output, builds Telegram digest.

Pure-Python; subprocess + stdlib + ai_trading_agents.telegram_notifier.
"""

from __future__ import annotations
import sys as _sys
try:
    _sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import argparse
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

REPO = Path(r"C:\Users\Ratanshila\Documents\autmated trading")
SKILLS = REPO / "docs" / "skills"
PYTHON = REPO / ".venv" / "Scripts" / "python.exe"
LOG_DIR = REPO / "logs"

SUB_SKILLS = [
    ("model-healthcheck", SKILLS / "trading-model-healthcheck" / "health_metrics.py", ["--team", "all"]),
    ("correlation-monitor", SKILLS / "trading-correlation-monitor" / "corr.py", []),
    ("drift-triage-crypto", SKILLS / "trading-drift-triage" / "triage.py", ["--team", "crypto"]),
    ("position-reconciliation", SKILLS / "trading-position-reconciliation" / "reconcile.py", ["--no-mt5"]),
    ("tca-daily", SKILLS / "trading-tca-daily" / "tca_helpers.py", ["--window", "24h"]),
]


def run_one(name: str, helper: Path, args: list[str], timeout: int = 60) -> dict:
    if not helper.exists():
        return {"name": name, "status": "MISSING", "verdict": "skipped", "stdout": "", "duration": 0.0}
    t0 = datetime.now()
    try:
        out = subprocess.run(
            [str(PYTHON), str(helper)] + args,
            cwd=str(REPO),
            capture_output=True, text=True, timeout=timeout, encoding="utf-8", errors="replace",
        )
        return {
            "name": name,
            "status": "OK" if out.returncode == 0 else f"EXIT_{out.returncode}",
            "verdict": _extract_verdict(name, out.stdout or ""),
            "stdout": out.stdout or "",
            "stderr": out.stderr or "",
            "duration": (datetime.now() - t0).total_seconds(),
        }
    except subprocess.TimeoutExpired:
        return {"name": name, "status": "TIMEOUT", "verdict": "timed-out", "stdout": "", "duration": timeout}
    except Exception as e:
        return {"name": name, "status": "ERROR", "verdict": str(e)[:100], "stdout": "", "duration": 0.0}


def _extract_verdict(name: str, output: str) -> str:
    """Pluck the headline verdict from each skill's output."""
    if "model-healthcheck" in name:
        # Look for "Verdict: HEALTHY" lines per team
        verdicts = re.findall(r"Verdict:\s*(\S+)", output)
        return " . ".join(verdicts) if verdicts else "no verdict found"
    if "correlation-monitor" in name:
        # Skip team-vs-baseline lines, look for known-relationship verdicts
        m = re.search(r"BTCUSD/ETHUSD\s+30d=([\d.+-]+)\s+180d baseline=([\d.+-]+)", output)
        if m:
            return f"BTC/ETH 30d={m.group(1)} vs baseline={m.group(2)}"
        # Fallback: look for "WEAKENED" / "STRENGTHENED" / "DECOUPLED"
        if "DECOUPLED" in output:
            return "DECOUPLED — investigate"
        if "WEAKENED" in output or "STRENGTHENED" in output:
            return "regime shift detected"
        return "normal"
    if "drift-triage" in name:
        m = re.search(r"RECOMMENDATION:\s*TIER\s+(\S+)", output)
        return m.group(1) if m else "no recommendation"
    if "position-reconciliation" in name:
        if "DRIFT DETECTED: none" in output:
            return "all sources agree"
        if "DRIFT DETECTED" in output:
            return "DRIFT — see log"
        return "no positions"
    if "tca-daily" in name:
        m = re.search(r"Deals last 24h:\s*(\d+)", output)
        if m:
            return f"{m.group(1)} deals"
        if "no fresh deals" in output.lower() or "No trades" in output:
            return "no deals"
        return "ran"
    return "ran"


def build_digest(results: list[dict], date_str: str) -> str:
    lines = [f"TrendMaster v14 morning brief - {date_str}"]
    for r in results:
        if r["status"] == "OK":
            lines.append(f"- {r['name']}: {r['verdict']}")
        else:
            lines.append(f"- {r['name']}: [{r['status']}] {r['verdict']}")
    return "\n".join(lines)


def send_telegram(msg: str) -> bool:
    try:
        sys.path.insert(0, str(REPO))
        from ai_trading_agents.telegram_notifier import get_notifier
        n = get_notifier()
        return bool(n.send(msg))
    except Exception as e:
        print(f"  Telegram send failed: {e}")
        return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-telegram", action="store_true")
    ap.add_argument("--quiet", action="store_true", help="Only print final summary line")
    ap.add_argument("--skill", default=None, help="Run only one sub-skill by name")
    args = ap.parse_args()

    date_str = datetime.now().strftime("%Y-%m-%d")
    if not args.quiet:
        print(f"=== TrendMaster v14 morning routine - {date_str} ===")
        print()

    results = []
    skills = SUB_SKILLS if not args.skill else [s for s in SUB_SKILLS if args.skill in s[0]]
    for i, (name, helper, helper_args) in enumerate(skills, 1):
        if not args.quiet:
            print(f"[{i}/{len(skills)}] {name}")
        r = run_one(name, helper, helper_args)
        results.append(r)
        if not args.quiet:
            print(f"  status: {r['status']}  verdict: {r['verdict']}  ({r['duration']:.1f}s)")
            print()

    digest = build_digest(results, date_str)
    if not args.quiet:
        print("=== DIGEST ===")
    print(digest)

    # Persist full transcript
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    transcript_path = LOG_DIR / f"morning_routine_{date_str}.log"
    with transcript_path.open("a", encoding="utf-8") as f:
        f.write(f"\n=== run @ {datetime.now().isoformat()} ===\n")
        for r in results:
            f.write(f"\n--- {r['name']} ---\n")
            f.write(r.get("stdout", "") + "\n")
        f.write("\n=== digest ===\n")
        f.write(digest + "\n")

    if not args.no_telegram:
        if send_telegram(digest):
            if not args.quiet:
                print("\nTelegram digest sent.")


if __name__ == "__main__":
    main()
