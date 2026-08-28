"""
enable_phase_b3_ml.py
=====================
Safely re-enable the Phase B3 LightGBM model that was disabled on
2026-04-28 because its calibrated max-prob (0.589) couldn't clear
the min_ml_confidence=0.70 floor.

Strategy:
  1. Backup current trend_master_model.lgb (the weak v1 fallback).
  2. Restore the B3 model from the .b3_clean_disabled_2026-04-28 file.
  3. Smoke-test inference on a tiny synthetic batch to confirm the
     model loads and emits sensible (non-NaN, in-range) probabilities.
  4. Print recommended next steps - the operator must decide whether to:
     (a) lower min_ml_confidence to 0.62 in trading_config.yaml AND
         settings.py, OR
     (b) recalibrate the model with isotonic regression / Platt scaling
         to widen the prob distribution.

This script is REVERSIBLE - if anything looks wrong, run with --rollback
to swap back to the weak v1.

Usage:
    python tools/enable_phase_b3_ml.py            # do the swap
    python tools/enable_phase_b3_ml.py --dry-run  # just print plan
    python tools/enable_phase_b3_ml.py --rollback # restore weak v1
    python tools/enable_phase_b3_ml.py --verify   # check current model
"""

from __future__ import annotations
import argparse
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

# ---- Paths -----------------------------------------------------------------
# CLAUDE.md rule: ai_trading_agents/ is a junction. Use parent.parent NOT
# .resolve(), but THIS script lives in tools/, OUTSIDE the junction, so
# .resolve() is fine here.
REPO = Path(__file__).resolve().parent.parent
BRAIN_DIR = REPO / "ai_trading_agents"

# Fallback: if the junction is unreadable (e.g. running under a Linux
# bind-mount that can't follow NTFS junctions), reach for the canonical
# location directly.
_CANONICAL = Path(r"C:\TrendMaster_aita_canonical")
try:
    next(BRAIN_DIR.iterdir())
    _BRAIN = BRAIN_DIR
except (OSError, StopIteration):
    if _CANONICAL.exists():
        _BRAIN = _CANONICAL
    else:
        _BRAIN = BRAIN_DIR

ACTIVE = _BRAIN / "trend_master_model.lgb"
B3_DISABLED = _BRAIN / "trend_master_model.lgb.b3_clean_disabled_2026-04-28"
WEAK_BACKUP = _BRAIN / "trend_master_model.lgb.weak_v1_backup_2026-04-28"


def _ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _bytes(p: Path) -> str:
    if not p.exists():
        return "missing"
    n = p.stat().st_size
    if n < 1024:
        return f"{n}B"
    if n < 1024 * 1024:
        return f"{n/1024:.1f}KB"
    return f"{n/1024/1024:.1f}MB"


def verify_current() -> int:
    print(f"Active model:   {ACTIVE.name}        ({_bytes(ACTIVE)})")
    print(f"B3 disabled:    {B3_DISABLED.name}  ({_bytes(B3_DISABLED)})")
    print(f"Weak v1 backup: {WEAK_BACKUP.name}  ({_bytes(WEAK_BACKUP)})")
    if ACTIVE.exists() and B3_DISABLED.exists():
        same_size = ACTIVE.stat().st_size == B3_DISABLED.stat().st_size
        if same_size:
            print("\nActive size matches B3? YES (B3 is live)")
        else:
            print("\nActive size matches B3? NO (weak v1 is live)")
    return 0


def smoke_test() -> bool:
    """Load the active model and emit one prediction on synthetic features."""
    try:
        import numpy as np  # noqa: F401
        import lightgbm as lgb  # type: ignore
    except ImportError as exc:
        print(f"[smoke-test] WARN: cannot test load - {exc}", file=sys.stderr)
        return False

    import numpy as np
    try:
        booster = lgb.Booster(model_file=str(ACTIVE))
    except Exception as exc:
        print(f"[smoke-test] FAIL: model won't load: {exc}", file=sys.stderr)
        return False

    n_features = booster.num_feature()
    print(f"[smoke-test] model expects {n_features} features")

    rng = np.random.default_rng(42)
    X = rng.standard_normal((4, n_features)).astype(np.float32)
    try:
        proba = booster.predict(X)
    except Exception as exc:
        print(f"[smoke-test] FAIL: predict raised: {exc}", file=sys.stderr)
        return False

    arr = np.asarray(proba)
    print(f"[smoke-test] output shape: {arr.shape}")
    print(f"[smoke-test] sample probs: {arr.flatten()[:8]}")
    if not np.isfinite(arr).all():
        print("[smoke-test] FAIL: NaN/Inf in predictions", file=sys.stderr)
        return False
    if arr.min() < -0.1 or arr.max() > 1.1:
        print(f"[smoke-test] WARN: probs outside [0,1]: min={arr.min()}, max={arr.max()}")
    print("[smoke-test] PASS")
    return True


def plan(rollback: bool):
    pre_swap_backup = _BRAIN / f"trend_master_model.lgb.pre_swap_{_ts()}"
    if rollback:
        if not WEAK_BACKUP.exists():
            raise SystemExit(f"[ERROR] No weak v1 backup at {WEAK_BACKUP}")
        return [
            (ACTIVE, pre_swap_backup),
            (WEAK_BACKUP, ACTIVE),
        ]
    else:
        if not B3_DISABLED.exists():
            raise SystemExit(f"[ERROR] B3 disabled file missing: {B3_DISABLED}")
        return [
            (ACTIVE, pre_swap_backup),
            (B3_DISABLED, ACTIVE),
        ]


def execute(plan_steps) -> None:
    for src, dst in plan_steps:
        if not src.exists():
            raise SystemExit(f"[ERROR] missing source: {src}")
        print(f"  copy {src.name}  ->  {dst.name}")
        shutil.copy2(src, dst)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true",
                    help="Print plan, don't change anything")
    ap.add_argument("--rollback", action="store_true",
                    help="Restore weak v1 from .weak_v1_backup")
    ap.add_argument("--verify", action="store_true",
                    help="Just print current model status")
    ap.add_argument("--no-smoke-test", action="store_true",
                    help="Skip post-swap inference smoke test")
    args = ap.parse_args()

    if args.verify:
        return verify_current()

    print("=" * 60)
    if args.rollback:
        print("ML rollback to weak v1")
    else:
        print("Phase B3 ML re-enable")
    print("=" * 60)
    print()
    verify_current()
    print()

    steps = plan(args.rollback)
    print(f"Planned steps ({len(steps)}):")
    for s, d in steps:
        print(f"  {s.name}  ->  {d.name}")
    print()

    if args.dry_run:
        print("[dry-run] no files changed.")
        return 0

    execute(steps)
    print("[OK] file ops complete.")
    print()

    if not args.no_smoke_test:
        ok = smoke_test()
        if not ok:
            print()
            print("!! Smoke test FAILED - rolling back to weak v1 is recommended:")
            print("   python tools/enable_phase_b3_ml.py --rollback")
            return 3

    print()
    print("=" * 60)
    print("Next steps (operator decision):")
    print("=" * 60)
    print("1. Lower min_ml_confidence to 0.62 (or 0.55 for more trades):")
    print("   - config/trading_config.yaml: brain.min_ml_confidence: 0.62")
    print("   - config/settings.py: TRENDMASTER_V14['min_ml_confidence']")
    print("2. Restart brain: START_TRENDMASTER_LIVE.bat (or supervisor)")
    print("3. Watch first 30 min: tail -f logs/trend_master_brain.log")
    print("4. Verify trades fire: /status, /symbols on Telegram")
    print()
    print("If calibration is still off, prefer model recalibration over")
    print("dropping the confidence floor below 0.55.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
