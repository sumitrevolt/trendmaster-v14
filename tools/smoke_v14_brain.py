"""
Smoke test for the TrendMaster v14 brain.
Runs entirely offline — no MT5 connection needed.
"""
from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd

from ai_trading_agents.trend_master_brain import (
    TrendMasterBrain, build_features, FEATURE_COLS,
    SYMBOL, TF, INFER_MS, MIN_CONF, SIG_FILE,
)


def _synth_bars(n: int = 300, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    # Trend + noise to give features real structure
    drift = np.linspace(0, 0.02, n)
    noise = rng.normal(0, 0.002, n).cumsum()
    close = 2000 * (1 + drift + noise)
    high = close * (1 + rng.uniform(0.0001, 0.0015, n))
    low  = close * (1 - rng.uniform(0.0001, 0.0015, n))
    op   = np.r_[close[0], close[:-1]]
    vol  = rng.integers(800, 1800, n)
    idx  = pd.date_range("2026-04-01", periods=n, freq="5min", tz="UTC")
    return pd.DataFrame(
        {"open": op, "high": high, "low": low, "close": close, "volume": vol},
        index=idx,
    )


def main() -> int:
    print("=" * 60)
    print("TrendMaster v14 — brain smoke test")
    print("=" * 60)
    print(f"symbol={SYMBOL}  tf={TF}  infer_ms={INFER_MS}  min_conf={MIN_CONF}")
    print(f"signal_file={SIG_FILE}")

    df = _synth_bars(300)
    print(f"\nsynthetic bars: rows={len(df)}  cols={list(df.columns)}")

    feats = build_features(df).dropna()
    print(f"features after dropna: rows={len(feats)}  total_cols={len(feats.columns)}")
    missing = [c for c in FEATURE_COLS if c not in feats.columns]
    print(f"missing_feature_cols: {missing}")
    assert not missing, "feature engineering broken"

    brain = TrendMasterBrain()
    print(f"\nbrain state_dir: {brain.state_dir}")
    print(f"brain model_path: {brain.model_path}")
    print(f"LightGBM model loaded: {brain.state.model is not None}")

    # Rule-based inference (always works)
    direction, conf = brain.infer_rule(feats)
    print(f"\ninfer_rule -> direction={direction}  conf={conf:.3f}")

    # ML inference (falls back to rule if no trained model)
    direction2, conf2 = brain.infer_ml(feats)
    print(f"infer_ml  -> direction={direction2}  conf={conf2:.3f}")

    # Write a signal payload (to state_dir when MT5 isn't available)
    try:
        brain.write_signal("BUY", 0.73)
        print("\nwrite_signal OK")
        print(f"last_signal -> {brain.state.last_signal}")
    except Exception as e:
        print(f"write_signal FAILED: {e}")
        return 1

    print("\n" + "=" * 60)
    print("PASS — brain is wired correctly")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
