"""
tools/retrain_from_trades.py — binary "should I take this setup?" trainer.

Consumes:
    data/labels_{symbol}.csv       (from tools/label_trades.py)
    data/{symbol}_m5_history.csv   (from tools/pull_history.py)

Produces:
    models/{symbol}_setup_clf.lgb  + metadata via tools/model_registry.py

Why binary
----------
The goal isn't to predict direction — the agent bus already does that.
The goal is to filter the setups the bus emits: "of the BUYs and SELLs
we'd take, which 30% actually paid ≥ 1R?" That's a well-posed binary
problem with real labels — unlike the forward-return ML that the final
upgrade report found useless.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

logger = logging.getLogger("retrain")

try:
    import lightgbm as lgb  # type: ignore

    _HAS_LGB = True
except ImportError:
    _HAS_LGB = False


FEATURE_COLS = [
    "ret_5",
    "ret_20",
    "vol_20",
    "close_ema_20",
    "close_ema_50",
    "rsi_14",
    "atr_14",
    "adx_14",
    "bb_z",
    "bb_width",
]


def _build_features(hist: pd.DataFrame) -> pd.DataFrame:
    x = hist.copy()
    if "time" in x.columns:
        x["time"] = pd.to_datetime(x["time"], utc=True)
        x = x.set_index("time")
    c = x["close"]
    for w in (5, 20, 50):
        x[f"ret_{w}"] = c.pct_change(w)
        x[f"vol_{w}"] = c.pct_change().rolling(w).std()
        x[f"close_ema_{w}"] = (c - c.ewm(span=w, adjust=False).mean()) / c
    d = c.diff()
    up = d.clip(lower=0).rolling(14).mean()
    dn = (-d.clip(upper=0)).rolling(14).mean()
    x["rsi_14"] = 100 - 100 / (1 + up / dn.replace(0, np.nan))
    h, l = x["high"], x["low"]
    tr = pd.concat([(h - l), (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    x["atr_14"] = tr.rolling(14).mean()
    up_m = h.diff()
    dn_m = -l.diff()
    plus = np.where((up_m > dn_m) & (up_m > 0), up_m, 0.0)
    minus = np.where((dn_m > up_m) & (dn_m > 0), dn_m, 0.0)
    atr_r = tr.rolling(14).mean().replace(0, np.nan)
    pdi = 100 * pd.Series(plus, index=x.index).rolling(14).mean() / atr_r
    ndi = 100 * pd.Series(minus, index=x.index).rolling(14).mean() / atr_r
    dx = 100 * (pdi - ndi).abs() / (pdi + ndi).replace(0, np.nan)
    x["adx_14"] = dx.rolling(14).mean()
    sma20 = c.rolling(20).mean()
    std20 = c.rolling(20).std()
    x["bb_z"] = (c - sma20) / std20.replace(0, np.nan)
    x["bb_width"] = (4 * std20) / sma20.replace(0, np.nan)
    return x


def retrain(symbol: str, trades_csv: Optional[str] = None, history_csv: Optional[str] = None) -> int:
    """Train a binary classifier. Returns 0 on success, non-zero otherwise."""
    symbol = symbol.upper()
    labels_path = Path(trades_csv) if trades_csv else _ROOT / "data" / f"labels_{symbol.lower()}.csv"
    hist_path = Path(history_csv) if history_csv else _ROOT / "data" / f"{symbol.lower()}_m5_history.csv"
    for p in (labels_path, hist_path):
        if not p.exists():
            logger.error("missing input: %s", p)
            return 2

    labels = pd.read_csv(labels_path, parse_dates=["time"])
    hist = pd.read_csv(hist_path)

    feats = _build_features(hist)
    # Merge asof on timestamp: each trade grabs the feature row at its open time.
    labels = labels.sort_values("time")
    feats_reset = feats.reset_index().rename(columns={"time": "time"})
    df = pd.merge_asof(labels, feats_reset.sort_values("time"), on="time", direction="backward")
    df = df.dropna(subset=FEATURE_COLS + ["won_R"])
    if len(df) < 30:
        logger.error("not enough labelled samples: %d (need ≥ 30)", len(df))
        return 3

    split = int(len(df) * 0.8)
    tr = df.iloc[:split]
    va = df.iloc[split:]
    logger.info("train=%d  val=%d  base-rate=%.2f%%", len(tr), len(va), df["won_R"].mean() * 100)

    if not _HAS_LGB:
        logger.error("lightgbm not installed — cannot train. pip install lightgbm")
        return 4

    import lightgbm as lgb  # type: ignore

    params = dict(
        objective="binary",
        metric="binary_logloss",
        learning_rate=0.05,
        num_leaves=31,
        min_data_in_leaf=20,
        verbosity=-1,
    )
    dtr = lgb.Dataset(tr[FEATURE_COLS], label=tr["won_R"])
    dva = lgb.Dataset(va[FEATURE_COLS], label=va["won_R"])
    booster = lgb.train(params, dtr, num_boost_round=200, valid_sets=[dva], callbacks=[lgb.early_stopping(20)])

    # Holdout precision at conf ≥ 0.60
    pred = booster.predict(va[FEATURE_COLS])
    take = pred >= 0.60
    if take.any():
        prec = va.loc[take, "won_R"].mean()
        logger.info("holdout precision @ p≥0.60: %.2f%%  (n=%d)", prec * 100, int(take.sum()))
    else:
        logger.warning("no holdout rows at p≥0.60")

    # Register
    from tools.model_registry import register_model

    meta = {
        "symbol": symbol,
        "trained_on": str(labels_path.name),
        "history": str(hist_path.name),
        "n_train": int(len(tr)),
        "n_val": int(len(va)),
        "features": FEATURE_COLS,
        "base_rate": float(df["won_R"].mean()),
        "best_iter": int(booster.best_iteration or 0),
    }
    out = register_model(symbol, booster, meta)
    logger.info("registered model at %s", out)
    return 0


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    p = argparse.ArgumentParser()
    p.add_argument("symbol")
    p.add_argument("--trades", default=None)
    p.add_argument("--history", default=None)
    return retrain(p.parse_args().symbol, p.parse_args().trades, p.parse_args().history)


if __name__ == "__main__":
    raise SystemExit(main())
