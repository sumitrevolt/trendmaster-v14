"""
Better trainer for TrendMaster v14:
  - Looser label threshold (0.5 ATR) to balance classes
  - Longer horizon (12 bars = 1h on M5) so trends have room
  - Class weights to penalize NONE-only collapse
  - Walk-forward holdout with precision/recall per direction
"""

from __future__ import annotations
import sys, os, json
from pathlib import Path
import numpy as np
import pandas as pd
import lightgbm as lgb

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from ai_trading_agents.trend_master_brain import build_features, FEATURE_COLS

CSV = ROOT / "data" / "xauusd_m5_history.csv"
# Write to a CANDIDATE path, never the live model. Promotion to
# trend_master_model.lgb must go through tools/enable_phase_b3_ml.py
# (which backs up the current live model and runs diagnose post-swap).
# This trainer is single-symbol XAUUSD-only and historically produced
# the 109 KB uniform-output model that silently zero-trades when copied
# live. See docs/POSTMORTEMS/2026-04-29_uniform_model_recurrence.md.
OUT = ROOT / "ai_trading_agents" / "trend_master_model_v14_better_candidate.lgb"

HORIZON = 12  # 12 bars on M5 = 1 hour ahead
THR_ATR = 0.5  # 0.5 * ATR move = "directional" event
CONF_DEPLOY = 0.45  # threshold the brain will use at runtime

print(f"loading {CSV}")
df = pd.read_csv(CSV, parse_dates=True, index_col=0)
df = df.rename(columns=str.lower)
print(f"raw rows: {len(df)}")

x = build_features(df).dropna().copy()
print(f"feature rows: {len(x)}")

atr = x["atr_14"]
fwd = x["close"].shift(-HORIZON) - x["close"]
lbl = np.where(fwd > THR_ATR * atr, 2, np.where(fwd < -THR_ATR * atr, 0, 1)).astype(int)
x["label"] = lbl
x = x.dropna().iloc[:-HORIZON]

print("label distribution:")
print(pd.Series(x["label"]).value_counts().sort_index())

cut = int(len(x) * 0.8)
X_tr, y_tr = x.iloc[:cut][FEATURE_COLS].values, x.iloc[:cut]["label"].values
X_va, y_va = x.iloc[cut:][FEATURE_COLS].values, x.iloc[cut:]["label"].values

# class weights to keep model from collapsing to majority
classes, counts = np.unique(y_tr, return_counts=True)
weights = {int(c): float(len(y_tr) / (3 * cnt)) for c, cnt in zip(classes, counts)}
w_tr = np.array([weights[int(y)] for y in y_tr])
print("class weights:", weights)

# Pass feature_name explicitly so Booster.feature_name() returns the
# real training-time column list at inference time instead of the
# default 'Column_0, Column_1, ...' placeholders. Without this, the
# brain's feature-alignment guard cannot match columns and routes all
# inference to rule fallback. See docs/POSTMORTEMS/2026-04-24_zero_trades.md.
d_tr = lgb.Dataset(X_tr, y_tr, weight=w_tr, feature_name=list(FEATURE_COLS))
d_va = lgb.Dataset(X_va, y_va, reference=d_tr, feature_name=list(FEATURE_COLS))

params = dict(
    objective="multiclass",
    num_class=3,
    metric="multi_logloss",
    learning_rate=0.04,
    num_leaves=63,
    min_data_in_leaf=80,
    feature_fraction=0.85,
    bagging_fraction=0.85,
    bagging_freq=5,
    lambda_l2=0.5,
    verbosity=-1,
)
model = lgb.train(params, d_tr, num_boost_round=1500, valid_sets=[d_va], callbacks=[lgb.early_stopping(50)])

# === holdout report ===
probs = model.predict(X_va)
pred = probs.argmax(axis=1)
maxp = probs.max(axis=1)
acc = (pred == y_va).mean()
print(f"\nholdout overall accuracy: {acc:.4f}  (random=0.333, majority={(y_va == 1).mean():.3f})")

print("\nholdout predicted class distribution:")
print(pd.Series(pred).value_counts().sort_index())

for thr in (0.38, 0.42, 0.45, 0.50, 0.55):
    mb = (pred == 2) & (maxp >= thr)
    ms = (pred == 0) & (maxp >= thr)
    pb = (y_va[mb] == 2).sum() / max(mb.sum(), 1)
    ps = (y_va[ms] == 0).sum() / max(ms.sum(), 1)
    print(f"  thr={thr:.2f}  BUY n={mb.sum():4d} prec={pb:.3f}  | SELL n={ms.sum():4d} prec={ps:.3f}")

model.save_model(str(OUT))
print(f"\nsaved CANDIDATE -> {OUT}")
print("This file is a CANDIDATE only. To promote to live, validate via")
print("  .venv\\Scripts\\python.exe tools\\diagnose_zero_trades.py")
print("then explicitly copy:")
print(f"  copy /Y {OUT} ai_trading_agents\\trend_master_model.lgb")
print("Direct overwrites of the live model are blocked by policy")
print("(see docs/POSTMORTEMS/2026-04-29_uniform_model_recurrence.md).")
