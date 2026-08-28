"""
auto_research.py - overnight walkforward + summary loop.

Runs at 03:30 IST via Scheduled Task "TrendMaster Auto Research".
Calls tools/walkforward_lab.py over a configurable symbol set,
captures the JSON results, computes a summary (top symbols by expR,
biggest drift from prior runs), writes:

  reports/auto_research/<date>.json    - raw walkforward output
  reports/auto_research/<date>.md      - human summary with deltas

The trader agent and operator both read the summary at session start.
This is an OpenClaw / cron-driven superpower: vanilla Opus chat
cannot run experiments overnight without operator presence.

Failure modes:
  - if walkforward_lab.py is missing or fails, write a minimal failure
    report so the absence is visible
  - safe to skip on weekends if data hasn't refreshed (configurable)

Pure stdlib + subprocess; reads MetaTrader5 only via the existing
walkforward_lab.py if that pulls live ticks (it doesn't by default -
it walks historical CSVs, so this is safe to run any time).
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
REPORTS_DIR = PROJECT_ROOT / "reports" / "auto_research"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

PYTHON = PROJECT_ROOT / ".venv" / "Scripts" / "python.exe"
WALKFORWARD_LAB = PROJECT_ROOT / "tools" / "walkforward_lab.py"


def _ist_today() -> datetime:
    return datetime.now(tz=timezone.utc).astimezone(timezone(timedelta(hours=5, minutes=30)))


def _safe_json(p: Path) -> dict | list | None:
    try:
        return json.loads(p.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return None


def run_walkforward(symbols: str = "all", timeout_s: int = 1800) -> dict:
    """Invoke walkforward_lab.py and capture its output.

    walkforward_lab.py is expected to print a JSON block with per-symbol
    metrics (acc, expR, win_rate, etc). If the lab supports --json output,
    use it. Otherwise capture stdout text and the operator can parse it.
    """
    if not WALKFORWARD_LAB.exists():
        return {
            "ok": False,
            "error": f"walkforward_lab.py not found at {WALKFORWARD_LAB}",
        }
    if not PYTHON.exists():
        return {"ok": False, "error": f".venv python not found at {PYTHON}"}

    try:
        r = subprocess.run(
            [str(PYTHON), str(WALKFORWARD_LAB), "--symbol", symbols, "--json"],
            capture_output=True,
            text=True,
            timeout=timeout_s,
            cwd=str(PROJECT_ROOT),
            check=False,
        )
        return {
            "ok": r.returncode == 0,
            "exit_code": r.returncode,
            "stdout": r.stdout[-50000:],  # cap at 50K
            "stderr": r.stderr[-10000:],
        }
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"timed out after {timeout_s}s"}
    except Exception as e:
        return {"ok": False, "error": f"exception: {e}"}


def parse_walkforward_json(stdout: str) -> dict | None:
    """Try to extract a JSON dict from walkforward_lab stdout.

    walkforward_lab.py may print free-form text plus a JSON line. We try
    each line, last-to-first, and return the first valid dict.
    """
    if not stdout:
        return None
    for line in reversed(stdout.splitlines()):
        line = line.strip()
        if line.startswith("{") and line.endswith("}"):
            try:
                obj = json.loads(line)
                if isinstance(obj, dict):
                    return obj
            except Exception:
                continue
    # also try to find the largest JSON-looking block
    start = stdout.find("{")
    end = stdout.rfind("}")
    if 0 <= start < end:
        try:
            obj = json.loads(stdout[start : end + 1])
            if isinstance(obj, dict):
                return obj
        except Exception:
            return None
    return None


def find_prior_report() -> dict | None:
    files = sorted(REPORTS_DIR.glob("*.json"), reverse=True)
    if not files:
        return None
    return _safe_json(files[0])


def summarize(today_metrics: dict | None, prior: dict | None) -> list[str]:
    """Produce a markdown summary list of lines."""
    out: list[str] = []
    if not today_metrics:
        out.append("- (no parseable metrics from walkforward_lab.py)")
        return out

    # Try common shapes: {"per_symbol": {SYM: {acc, expR, wr}}, "overall": ...}
    per_sym = today_metrics.get("per_symbol") or today_metrics.get("symbols") or {}
    overall = today_metrics.get("overall") or {}

    if overall:
        out.append("**Overall**")
        for k, v in overall.items():
            out.append(f"- {k}: {v}")

    if isinstance(per_sym, dict) and per_sym:
        # rank by expR desc
        rows: list[tuple[str, float, dict]] = []
        for sym, m in per_sym.items():
            if not isinstance(m, dict):
                continue
            expR = m.get("expR", m.get("expectancy", m.get("avg_r", 0)))
            try:
                expR = float(expR)
            except Exception:
                expR = 0
            rows.append((sym, expR, m))
        rows.sort(key=lambda x: x[1], reverse=True)
        out.append("")
        out.append("**Top 5 by expR**")
        out.append("")
        out.append("| symbol | expR | acc | wr | n |")
        out.append("|---|---|---|---|---|")
        for sym, expR, m in rows[:5]:
            acc = m.get("acc", m.get("accuracy", "-"))
            wr = m.get("win_rate", m.get("wr", "-"))
            n = m.get("n", m.get("count", "-"))
            out.append(f"| {sym} | {expR:.3f} | {acc} | {wr} | {n} |")

        if prior:
            prior_per = prior.get("metrics", {}).get("per_symbol") or {}
            if prior_per:
                out.append("")
                out.append("**Largest expR drift vs prior run**")
                out.append("")
                out.append("| symbol | today | prior | delta |")
                out.append("|---|---|---|---|")
                deltas = []
                for sym, expR, _ in rows:
                    if sym in prior_per and isinstance(prior_per[sym], dict):
                        try:
                            prior_r = float(prior_per[sym].get("expR", 0))
                            deltas.append((sym, expR, prior_r, expR - prior_r))
                        except Exception:
                            continue
                deltas.sort(key=lambda x: abs(x[3]), reverse=True)
                for sym, today_r, prior_r, d in deltas[:5]:
                    out.append(f"| {sym} | {today_r:.3f} | {prior_r:.3f} | {d:+.3f} |")
    else:
        out.append("- (no per_symbol metrics in output)")

    return out


def write_reports(today: datetime, raw_run: dict, metrics: dict | None, summary_lines: list[str]) -> tuple[Path, Path]:
    date_str = today.strftime("%Y-%m-%d")
    json_path = REPORTS_DIR / f"{date_str}.json"
    md_path = REPORTS_DIR / f"{date_str}.md"

    # raw JSON dump
    json_path.write_text(
        json.dumps(
            {
                "ts": today.isoformat(),
                "run": raw_run,
                "metrics": metrics,
            },
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )

    # markdown summary
    lines: list[str] = []
    lines.append(f"# Auto-research report - {date_str}")
    lines.append("")
    lines.append(f"_Generated by `tools/auto_research.py` at {today.strftime('%H:%M:%S IST')}_")
    lines.append("")
    if not raw_run.get("ok"):
        lines.append("## Run failed")
        lines.append("")
        lines.append("```")
        lines.append(raw_run.get("error", "unknown error"))
        lines.append("")
        if raw_run.get("stderr"):
            lines.append("--- stderr ---")
            lines.append(raw_run["stderr"][-2000:])
        lines.append("```")
    else:
        lines.append(f"## Run OK (exit={raw_run.get('exit_code', 0)})")
        lines.append("")
        lines.extend(summary_lines)
        lines.append("")
        lines.append("## Raw stdout (last 200 lines)")
        lines.append("")
        lines.append("```")
        for ln in raw_run.get("stdout", "").splitlines()[-200:]:
            lines.append(ln)
        lines.append("```")
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return json_path, md_path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbols", default="all", help="symbol selection passed to walkforward_lab")
    parser.add_argument("--timeout", type=int, default=1800, help="walkforward timeout seconds")
    args = parser.parse_args()

    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except Exception:
        pass

    today = _ist_today()
    print(f"[{today.strftime('%Y-%m-%d %H:%M')}] auto_research starting (symbols={args.symbols})")

    prior = find_prior_report()
    raw = run_walkforward(args.symbols, timeout_s=args.timeout)
    metrics = parse_walkforward_json(raw.get("stdout", ""))

    summary_lines = summarize(metrics, prior)
    json_path, md_path = write_reports(today, raw, metrics, summary_lines)
    print(f"raw:     {json_path}")
    print(f"summary: {md_path}")

    if not raw.get("ok"):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
