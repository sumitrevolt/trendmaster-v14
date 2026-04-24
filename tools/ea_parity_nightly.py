"""
Nightly ea_parity runner with Telegram alert on divergence.

What it does
------------
For each symbol in SYMBOLS_FOR_PARITY it loads the historical OHLCV CSV in
`data/`, runs `tools.backtest.run_ea_parity_backtest`, and accumulates the
per-symbol metrics. Then it diffs the current run against the baseline at
`reports/ea_parity_baseline.json`:

    - If the baseline does NOT exist, the current run becomes the baseline
      (first-run seeding) and the script exits 0.
    - If the baseline exists, the script computes per-metric deltas and
      flags symbols whose divergence exceeds the thresholds below.
    - If any symbol diverges, a Telegram alert is posted via the project's
      existing notifier. If the baseline was intentional (e.g., rule
      change committed), delete the baseline file and re-run to reseed.

Every run is also appended to `reports/ea_parity_history/YYYY-MM-DD.json`
for a historical record.

Thresholds
----------
    bars_scanned: > 1% relative diff
    trades:       > 5% relative diff
    win_rate:     > 5 pp absolute diff
    expectancy_R: > 0.15 absolute diff

These mirror the table in the `trading-ea-parity` skill.

Installed via
-------------
    install_ea_parity_nightly.bat  (schtasks, runs 02:30 local Mon-Fri)

Safe to run anytime - read-only against historical CSVs, no MT5 touch.
"""

from __future__ import annotations

import json
import os
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

# Per-symbol CSV filename convention: data/<symbol lower>_m5_history.csv
SYMBOLS_FOR_PARITY: List[str] = [
    "XAUUSD",
    "EURUSD",
    "GBPUSD",
    "BTCUSD",
]

BASELINE_PATH = REPO_ROOT / "reports" / "ea_parity_baseline.json"
HISTORY_DIR = REPO_ROOT / "reports" / "ea_parity_history"

# Divergence thresholds.
THR_BARS_REL = 0.01
THR_TRADES_REL = 0.05
THR_WIN_RATE_PP = 0.05  # 5 percentage points
THR_EXPECTANCY_ABS = 0.15

# Baseline staleness warning threshold (days). If the baseline is older
# than this, nightly runs will include a "stale baseline" alert so the
# operator can decide whether to reseed after intentional rule changes.
STALE_BASELINE_DAYS = 14


def _csv_for(symbol: str) -> Path:
    return REPO_ROOT / "data" / f"{symbol.lower()}_m5_history.csv"


def run_one(symbol: str) -> Dict[str, Any]:
    """Run ea_parity for a single symbol. Returns dict with metrics or error."""
    csv = _csv_for(symbol)
    if not csv.exists():
        return {"symbol": symbol, "error": f"CSV missing: {csv}"}

    try:
        from tools.backtest import run_ea_parity_backtest  # type: ignore
    except Exception as e:  # pragma: no cover - defensive
        return {"symbol": symbol, "error": f"import run_ea_parity_backtest failed: {e}"}

    try:
        df = pd.read_csv(csv)
        # best-effort time column normalisation
        for col in ("time", "datetime", "date"):
            if col in df.columns:
                df[col] = pd.to_datetime(df[col], errors="coerce", utc=True)
                break
        result = run_ea_parity_backtest(df, sl_atr_mult=1.5, tp_atr_mult=3.0)
    except Exception as e:
        return {"symbol": symbol, "error": f"backtest failure: {e}", "traceback": traceback.format_exc()}

    out: Dict[str, Any] = {"symbol": symbol, "csv": str(csv.name)}
    out.update(result)
    return out


def load_baseline() -> Optional[Dict[str, Any]]:
    if not BASELINE_PATH.exists():
        return None
    try:
        return json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return None


def _baseline_age_days(baseline: Optional[Dict[str, Any]]) -> Optional[int]:
    """Return age (in days) of baseline['generated_at'], or None if absent/bad."""
    if not baseline or not isinstance(baseline, dict):
        return None
    ts = baseline.get("generated_at")
    if not ts or not isinstance(ts, str):
        return None
    try:
        gen = datetime.fromisoformat(ts)
        if gen.tzinfo is None:
            gen = gen.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None
    delta = datetime.now(timezone.utc) - gen
    return max(delta.days, 0)


def save_baseline(payload: Dict[str, Any]) -> None:
    BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
    BASELINE_PATH.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")


def _rel_diff(cur: Optional[float], base: Optional[float]) -> Optional[float]:
    if cur is None or base is None or base == 0:
        return None
    return (cur - base) / abs(base)


def _abs_diff(cur: Optional[float], base: Optional[float]) -> Optional[float]:
    if cur is None or base is None:
        return None
    return cur - base


def diff_symbol(cur: Dict[str, Any], base: Dict[str, Any]) -> Tuple[bool, List[str]]:
    flags: List[str] = []
    if "error" in cur:
        return True, [f"current run errored: {cur['error']}"]
    if "error" in base:
        return False, [f"baseline had error for this symbol, seeding with current"]

    bars_rd = _rel_diff(cur.get("bars_scanned"), base.get("bars_scanned"))
    if bars_rd is not None and abs(bars_rd) > THR_BARS_REL:
        flags.append(f"bars_scanned diverged {bars_rd * 100:+.1f}%")

    tr_rd = _rel_diff(cur.get("trades"), base.get("trades"))
    if tr_rd is not None and abs(tr_rd) > THR_TRADES_REL:
        flags.append(f"trades diverged {tr_rd * 100:+.1f}%")

    wr_ad = _abs_diff(cur.get("win_rate"), base.get("win_rate"))
    if wr_ad is not None and abs(wr_ad) > THR_WIN_RATE_PP:
        flags.append(f"win_rate diverged {wr_ad * 100:+.1f} pp")

    ex_ad = _abs_diff(cur.get("expectancy_R"), base.get("expectancy_R"))
    if ex_ad is not None and abs(ex_ad) > THR_EXPECTANCY_ABS:
        flags.append(f"expectancy_R diverged {ex_ad:+.3f}")

    return bool(flags), flags


def send_telegram(title: str, message: str) -> bool:
    """Post via the project's existing notifier. Returns True on success."""
    try:
        from ai_trading_agents.telegram_notifier import get_notifier  # type: ignore
    except Exception as e:
        print(f"[telegram] import failed: {e}")
        return False
    try:
        get_notifier().notify_alert(title, message, emoji="🟡")
        return True
    except Exception as e:
        print(f"[telegram] notify_alert failed: {e}")
        return False


def write_history(payload: Dict[str, Any]) -> Path:
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M")
    p = HISTORY_DIR / f"{stamp}.json"
    p.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    return p


def format_alert(results: List[Dict[str, Any]], baseline: Dict[str, Any]) -> Tuple[bool, str]:
    lines: List[str] = []
    any_flag = False
    base_by_sym = {r["symbol"]: r for r in baseline.get("per_symbol", [])}
    for cur in results:
        sym = cur["symbol"]
        base = base_by_sym.get(sym, {})
        flagged, flags = diff_symbol(cur, base)
        if flagged:
            any_flag = True
            lines.append(f"❗ {sym}")
            for f in flags:
                lines.append(f"   - {f}")
        else:
            lines.append(
                f"✅ {sym}  (trades={cur.get('trades', '-')}  "
                f"wr={_fmt_pct(cur.get('win_rate'))}  "
                f"exp={_fmt_num(cur.get('expectancy_R'))})"
            )
    return any_flag, "\n".join(lines)


def _fmt_pct(x: Any) -> str:
    try:
        return f"{float(x) * 100:.1f}%"
    except Exception:
        return "-"


def _fmt_num(x: Any) -> str:
    try:
        return f"{float(x):.3f}"
    except Exception:
        return "-"


def main() -> int:
    results = [run_one(sym) for sym in SYMBOLS_FOR_PARITY]
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "symbols": SYMBOLS_FOR_PARITY,
        "per_symbol": results,
    }
    hist_path = write_history(payload)
    print(f"[info] wrote {hist_path}")

    baseline = load_baseline()
    if baseline is None:
        save_baseline(payload)
        print(f"[info] seeded baseline at {BASELINE_PATH}")
        send_telegram(
            "ea_parity baseline seeded",
            f"First nightly run. Baseline written for {len(results)} symbols.\nFuture divergence will trigger alerts.",
        )
        return 0

    # Baseline staleness check: warn (but don't block) if the baseline has
    # been frozen for too long. Common cause: gate tweaks made without
    # reseeding, so divergence never exceeds threshold because gradual
    # drift got baked into the baseline's own seeding.
    age = _baseline_age_days(baseline)
    if age is not None and age > STALE_BASELINE_DAYS:
        stale_msg = (
            f"Baseline is {age} days old (threshold {STALE_BASELINE_DAYS}). "
            f"If recent gate/EA changes are the new normal, reseed with "
            f"`del reports\\ea_parity_baseline.json` + re-run. Otherwise "
            f"consider whether slow drift is being masked."
        )
        print(f"[warn] {stale_msg}")
        send_telegram("ea_parity baseline stale", stale_msg)

    flagged, summary = format_alert(results, baseline)
    print(summary)
    if flagged:
        send_telegram("ea_parity nightly: divergence", summary)
        return 1

    # All within tolerance - post a quiet OK (useful to confirm scheduler is alive).
    if os.getenv("EA_PARITY_QUIET_OK", "").lower() not in ("1", "true", "yes"):
        send_telegram("ea_parity nightly: OK", summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
