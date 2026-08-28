"""Definitive "why are we not trading" diagnostic.

Use when the brain is running but `tick_all summary` shows NONE=N for
every symbol and no deals are happening. Reads live state + config, does
NOT touch MT5 or the brain process.

Outputs a verdict, one of:

  OK                   - thresholds look sane and confidences regularly
                          clear MIN_CONF; zero trades is market-driven
  HALTED               - a halt / kill switch / drawdown lockout is on
  MODEL_UNIFORM        - model predictions are clustered near 1/K
                          (K = number of classes); looks broken, not quiet
  CONF_BELOW_THRESHOLD - model produces real variance but never clears
                          MIN_CONF; gate is calibrated too high
  INSUFFICIENT_STATE   - state file too empty or brain not running long
                          enough to diagnose

Usage
-----
    python tools/diagnose_zero_trades.py

Safe to run at any time. Read-only.
"""

from __future__ import annotations

import json
import statistics
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
STATE_PATH = REPO_ROOT / "logs" / "brain_state.json"
BRAIN_LOG = REPO_ROOT / "logs" / "trend_master_brain.out"
BRAIN_ERR = REPO_ROOT / "logs" / "trend_master_brain.err"
MODEL_PATH = REPO_ROOT / "ai_trading_agents" / "trend_master_model.lgb"

# Heuristics.
UNIFORM_TOLERANCE = 0.05  # confidence std < this AND mean near 1/K -> uniform-ish
UNIFORM_DISTANCE_1_3 = 0.05  # all confidences within +/- this of 1/3 -> K=3 uniform
MIN_CONF_DEFAULT = 0.58  # from trend_master_brain.py:250
# Max age of brain_state.json before it indicates state-write drift. The brain
# saves every PERSIST_EVERY_N ticks (~3-15s). 120s is a generous ceiling — see
# docs/POSTMORTEMS/2026-04-30_junction_trap_silent_state_drift.md.
STATE_STALE_AFTER_SECONDS = 120


def load_state() -> Dict[str, Any]:
    if not STATE_PATH.exists():
        return {}
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        return {"_error": f"cannot parse state: {e}"}


def load_min_conf_from_config() -> float:
    """Best-effort: read MIN_CONF value via the same path trend_master_brain uses."""
    try:
        from config import settings  # type: ignore

        cfg = (
            getattr(settings, "TRENDMASTER_V14", None)
            or getattr(settings, "CONFIG", None)
            or getattr(settings, "TRADING_CONFIG", None)
            or {}
        )
        if isinstance(cfg, dict) and "min_ml_confidence" in cfg:
            return float(cfg["min_ml_confidence"])
    except Exception:
        pass
    return MIN_CONF_DEFAULT


def latest_tick_line(log_path: Path) -> Optional[str]:
    if not log_path.exists():
        return None
    try:
        text = log_path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return None
    # Last line that contains "tick_all summary". Strip non-ASCII for cp1252
    # console safety (Windows default codepage can't emit U+FFFD).
    for line in reversed(text.splitlines()):
        if "tick_all summary" in line:
            return line.encode("ascii", errors="replace").decode("ascii")
    return None


STALE_SIGNAL_HOURS = 6  # signal ts older than this is dropped from stats


def format_signals(
    signals: Dict[str, Dict[str, Any]], now_ts: Optional[float] = None
) -> Tuple[List[float], List[str], Dict[str, List[float]], int]:
    """Returns (all_confidences, all_directions, per_direction_confidences, n_stale_dropped).

    Signals with a ts older than STALE_SIGNAL_HOURS are filtered out - they
    often hold default values (e.g. 0.5) that mask the true confidence
    distribution of the currently-scanned symbols.
    """
    confs: List[float] = []
    dirs: List[str] = []
    by_dir: Dict[str, List[float]] = {}
    stale = 0
    cutoff = (now_ts or datetime.now(timezone.utc).timestamp()) - STALE_SIGNAL_HOURS * 3600
    for _sym, s in signals.items():
        try:
            c = float(s.get("confidence", 0.0))
        except (TypeError, ValueError):
            continue
        ts = s.get("ts") or 0
        try:
            if float(ts) < cutoff:
                stale += 1
                continue
        except (TypeError, ValueError):
            pass
        d = str(s.get("direction", "NONE")).upper()
        confs.append(c)
        dirs.append(d)
        by_dir.setdefault(d, []).append(c)
    return confs, dirs, by_dir, stale


def _fmt_ts(val: Any) -> str:
    try:
        t = int(val)
        if t == 0:
            return "never"
        return datetime.fromtimestamp(t, tz=timezone.utc).isoformat()
    except Exception:
        return str(val)


def diagnose() -> int:
    print("=" * 64)
    print("TrendMaster v14 - zero-trades diagnostic")
    print(f"Generated: {datetime.now(timezone.utc).isoformat()}")
    print("=" * 64)

    # 1. State snapshot --------------------------------------------------
    state = load_state()
    if not state:
        print("\n[VERDICT] INSUFFICIENT_STATE - brain_state.json missing or empty.")
        return 2

    if "_error" in state:
        print(f"\n[VERDICT] INSUFFICIENT_STATE - {state['_error']}")
        return 2

    # 1b. State freshness check -----------------------------------------
    # Catches the 2026-04-30 junction-trap pattern: brain alive, log fresh,
    # but state writes silently going to a different (wrong) path.
    try:
        mtime = STATE_PATH.stat().st_mtime
        age = time.time() - mtime
        last_saved_at = float(state.get("last_saved_at") or 0)
        save_age = time.time() - last_saved_at if last_saved_at else float("inf")
        if age > STATE_STALE_AFTER_SECONDS or save_age > STATE_STALE_AFTER_SECONDS:
            print(f"\n[VERDICT] STATE_DRIFT - brain_state.json is {age:.0f}s old on disk")
            print(f"          (last_saved_at field reports {save_age:.0f}s ago).")
            print("          The brain log may look healthy, but state writes are")
            print("          NOT landing here. Check for the junction-trap pattern:")
            print("          state/events/lock written to C:\\logs\\ instead of project root.")
            print("          See docs/POSTMORTEMS/2026-04-30_junction_trap_silent_state_drift.md")
            print("\nRemediation:")
            print("  1. Check C:\\logs\\brain_state.json — if it exists and is fresh, the")
            print("     brain is in the junction-trap pattern. Restart via start_brain_clean.cmd.")
            print("  2. If brain is stopped: relaunch via start_brain_clean.cmd.")
            return 1
    except OSError as e:
        print(f"\n[VERDICT] STATE_DRIFT - cannot stat brain_state.json: {e}")
        return 1

    # 2. Halt / kill-switch check ---------------------------------------
    halt_keys = ("halted", "trading_paused", "panic", "disabled")
    active_halts = {k: state.get(k) for k in halt_keys if state.get(k)}
    if active_halts:
        print("\n[VERDICT] HALTED")
        for k, v in active_halts.items():
            print(f"    {k} = {v}")
        if state.get("trading_paused"):
            print(f"    paused_at  = {_fmt_ts(state.get('trading_paused_at'))}")
            print(f"    resumed_at = {_fmt_ts(state.get('trading_resumed_at'))}")
        print("\nRemediation: send Telegram `/resume` OR inspect reason and clear manually.")
        return 1

    lockout = state.get("drawdown_lockout_until") or 0
    if lockout and int(lockout) > int(datetime.now(timezone.utc).timestamp()):
        print(f"\n[VERDICT] HALTED - drawdown_lockout_until = {_fmt_ts(lockout)}")
        print("Remediation: wait for lockout or clear if justified; check recent PnL.")
        return 1

    # 3. Signal confidence distribution ---------------------------------
    signals = state.get("last_signal_per_symbol") or {}
    if not signals:
        print("\n[VERDICT] INSUFFICIENT_STATE - last_signal_per_symbol is empty.")
        return 2

    confs, dirs, by_dir, n_stale = format_signals(signals)
    if not confs:
        print(f"\n[VERDICT] INSUFFICIENT_STATE - no fresh confidences (dropped {n_stale} stale)")
        return 2
    if n_stale:
        print(f"(filtered out {n_stale} stale signals older than {STALE_SIGNAL_HOURS}h)")

    c_mean = statistics.mean(confs)
    c_min = min(confs)
    c_max = max(confs)
    c_std = statistics.pstdev(confs) if len(confs) > 1 else 0.0
    none_frac = dirs.count("NONE") / len(dirs)

    print(f"\nSignals tracked : {len(confs)}")
    print(f"  direction mix : {', '.join(f'{d}={dirs.count(d)}' for d in set(dirs))}")
    print(f"  confidence    : mean={c_mean:.3f}  std={c_std:.3f}  min={c_min:.3f}  max={c_max:.3f}")
    print(f"  NONE fraction : {none_frac * 100:.1f}%")

    min_conf = load_min_conf_from_config()
    print(f"\nGate          : MIN_CONF = {min_conf:.2f} (hard peak-hour floor 0.50)")
    print(f"Latest tick   : {latest_tick_line(BRAIN_LOG) or '(no tick line found)'}")
    print(f"Model file    : {MODEL_PATH}")
    if MODEL_PATH.exists():
        mtime = datetime.fromtimestamp(MODEL_PATH.stat().st_mtime, tz=timezone.utc)
        age_d = (datetime.now(timezone.utc) - mtime).days
        print(f"              : mtime={mtime.isoformat()}  (age {age_d}d)")

    # 4. Pathology detection --------------------------------------------
    # 4a. Near-uniform around 1/3 -> K=3 classifier returning uniform probs
    near_third = all(abs(c - (1.0 / 3.0)) < UNIFORM_DISTANCE_1_3 for c in confs)
    near_half = all(abs(c - 0.5) < UNIFORM_DISTANCE_1_3 for c in confs)
    if near_third and c_std < UNIFORM_TOLERANCE and none_frac > 0.9:
        # [Phase B3 2026-04-26] Before crying MODEL_UNIFORM, check whether the
        # loaded model is a V2 model (>25 features) that requires smart-money
        # columns not available in the diagnostic's static feature build.
        # When smartmoney_features_enabled=True and the model has >25 features,
        # the uniform output is expected here — the brain will build V2 features
        # correctly at runtime. This is NOT a model pathology.
        _v2_model = False
        _v2_err = None
        try:
            import lightgbm as _lgb  # noqa: PLC0415

            _m = _lgb.Booster(model_file=str(MODEL_PATH))
            _v2_model = len(_m.feature_name()) > 25
        except Exception as _e:
            _v2_err = str(_e)
        if _v2_model:
            _sm_on = False
            try:
                import sys as _sys2  # noqa: PLC0415

                _rr = str(REPO_ROOT)  # project root (tools/../)
                if _rr not in _sys2.path:
                    _sys2.path.insert(0, _rr)
                from config import settings as _s  # noqa: PLC0415

                _sm_on = getattr(_s, "TRENDMASTER_V14", {}).get("smartmoney_features_enabled", False)
            except Exception:
                _sm_on = False
            if _sm_on:
                print("\n[VERDICT] MODEL_OK (V2) - model expects smart-money features (>25 cols).")
                print("          Uniform output in this diagnostic is expected: the static")
                print("          feature build here omits COT/EIA cols that the brain provides")
                print("          at runtime via build_features_v2().")
                print("          smartmoney_features_enabled=True is set in config.")
                print("\nNext step: restart the brain with start_brain_clean.cmd.")
                print("  After restart, re-run this diagnostic to confirm MODEL_OK.")
                return 0
        print("\n[VERDICT] MODEL_UNIFORM - confidences clustered near 1/3 with very low")
        print("          variance AND NONE dominates direction. Signature of a 3-class")
        print("          classifier returning near-uniform probabilities for every input")
        print("          - i.e., feature scaling / name-order mismatch OR a broken /")
        print("          untrained model. Not a market-quiet artefact: 19 different")
        print("          markets do not all produce exactly 1/3 by chance.")
        print("\nRemediation - in order:")
        print("  1. Verify features being fed to inference match training column order")
        print("     (log one row of features at tick time, compare to training CSV).")
        print("  2. Retrain the top-level model (trend_master_model.lgb). The per-team")
        print("     lgbm_*.pkl registry still works but this is the primary classifier.")
        print("  3. As a temporary sanity check, route to a simpler agent-only decision")
        print("     (skip ML layer) and verify the brain can produce non-NONE at all.")
        return 1
    if near_half and c_std < UNIFORM_TOLERANCE and none_frac > 0.9:
        print("\n[VERDICT] MODEL_UNIFORM - binary classifier returning ~0.5 everywhere.")
        print("Remediation: retrain trend_master_model.lgb.")
        return 1

    # 4b. Real variance but never clears the gate
    if c_max < min_conf and none_frac > 0.9:
        gap = min_conf - c_max
        print(f"\n[VERDICT] CONF_BELOW_THRESHOLD - best confidence {c_max:.3f} is")
        print(f"          {gap:.3f} below MIN_CONF {min_conf:.2f}. Model has variance but")
        print("          the gate is too strict for the current regime.")
        print("\nRemediation:")
        print(f"  - Lower config/settings.py :: min_ml_confidence toward {c_max - 0.02:.2f}")
        print("    AND restart the brain (see docs/skills/trading-brain-restart).")
        print("  - Or add/raise session_boost peak_boost so effective floor drops to 0.50.")
        print("  - If you don't trust lowering the gate, retrain with balanced labels.")
        return 1

    # 4c. Confidences clear the gate sometimes - gate isn't the bottleneck
    clears = sum(1 for c in confs if c >= min_conf)
    if clears > 0:
        print(f"\n[VERDICT] OK - {clears}/{len(confs)} symbols cleared MIN_CONF. Zero")
        print("          trades likely caused by the post-confidence gate stack")
        print("          (agent vote, mtf agreement, profit filters, EA quorum, reentry")
        print("          permits). Dig into profit_filters or multi_agent vote_all -")
        print("          those are next on the funnel.")
        return 0

    # Fallback
    print("\n[VERDICT] UNCLEAR - confidence pattern didn't match known pathologies.")
    print("          Paste the numbers above to the operator.")
    return 1


if __name__ == "__main__":
    raise SystemExit(diagnose())
