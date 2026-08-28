---
name: trading-triple-barrier-upgrade
description: Replace fixed-horizon return labels in TrendMaster v14 training with asymmetric volatility-scaled triple-barrier labels (TP=k1·ATR, SL=k2·ATR, time=N bars), per López de Prado AFML ch.3. Generates the relabeled CSV plus a label-quality report (path-dependence, overlap fraction, class balance). Use when the user asks "triple-barrier", "vol-scaled labels", "improve labels", "label quality", "AFML labels", or wants to upgrade from fixed-horizon labels.
---

# Trading Triple-Barrier Label Upgrade

Generate vol-scaled asymmetric triple-barrier labels for TrendMaster's training pipeline. Extends the partial implementation already in `ai_trading_agents/advanced_features.py`. Single highest-ROI change to the training data per the 2026 ML research brief.

## When to invoke

- Operator asks "triple-barrier labels", "improve labels", "AFML ch.3 labels".
- Before any retrain that goes into production.
- After the cross-asset features land — the two changes compound.

## What the labels look like

For each bar `t` in the training set:

```
TP_px = entry_px + k1 * ATR(t)        # k1 default 2.0
SL_px = entry_px - k2 * ATR(t)        # k2 default 1.5  (asymmetric — TP wider than SL)
time_horizon = N bars                  # default 24 H1 bars = 1 day

label[t] = +1 if TP_px hit first within N bars
        =  0 if time_horizon expires before either barrier
        = -1 if SL_px hit first within N bars
```

Asymmetry encodes the actual trade R:R. For mean-reversion strategies flip the asymmetry (k1<k2). The defaults `k1=2.0, k2=1.5` map to R:R 1.33:1 — Robot Wealth's reproducibly-profitable retail FX baseline.

## Inputs

- `data/<symbol>_m5_history.csv` — H1 resampled inside the script.
- `--k1`, `--k2`, `--horizon`, `--atr-window` — overridable on CLI.
- `--side` — `long`, `short`, or `both` (default both produces `meta_label` for meta-labeling head).

## Outputs

1. **Relabeled CSV** at `data/labels/<symbol>_tb_h<H>_k<K1>_<K2>.parquet` with columns:
   `ts, entry_px, atr, tp_px, sl_px, label, hit_ts, hit_px, holding_bars, vol_at_entry`.
2. **Label-quality report** printed to stdout AND saved to `logs/label_quality/<run_ts>.json`:

```
Label quality — XAUUSD H1 — k1=2.0 k2=1.5 horizon=24
====================================================

Bars labeled: 7,341
Class balance:
  +1 (TP hit):  29.4%
   0 (timeout): 41.2%
  -1 (SL hit):  29.4%

Time-to-resolution distribution:
  median: 7 bars
  p25 / p75: 3 / 14 bars
  p95: 23 bars (close to horizon — consider widening N)

Path-dependence (mean uniqueness):
  0.42  — labels are NOT iid (40-60% overlap with neighbors expected)
  Use sample_weight = uniqueness when training; consider sequential bootstrap.

vol_at_entry vs label:
  Higher-vol entries hit TP/SL faster; class balance stable across vol terciles.

Recommendations:
  - Class balance is healthy; LightGBM bagging will memorize without
    sample_weight by uniqueness.
  - p95=23 means 5% of labels barely resolved within horizon. Consider N=32.
  - Ready to feed into training pipeline.
```

## Integration

After the CSV is written, the training script (`tools/train_v14_better.py`) needs to load `data/labels/...` instead of computing fixed-horizon labels in-place. Skill prints the exact diff:

```python
# Replace in tools/train_v14_better.py:
- df["label"] = compute_fwd_return_label(df["close"], horizon=12, threshold=...)
+ labels = pd.read_parquet(f"data/labels/{symbol}_tb_h24_k2.0_1.5.parquet")
+ df = df.merge(labels[["ts", "label"]], on="ts").dropna(subset=["label"])
```

The skill does NOT auto-edit the training script — operator runs the diff.

## How to call

```cmd
cd C:\Users\Ratanshila\Documents\autmated trading
.venv\Scripts\python.exe ${CLAUDE_PLUGIN_ROOT}\skills\trading-triple-barrier-upgrade\tb_labeler.py ^
  --symbol XAUUSD --k1 2.0 --k2 1.5 --horizon 24
```

Pass `--symbol all` to label every symbol in `data/`. Pass `--side long` to skip the short half if a particular team only trades long.

## Critical guardrails

- **No leakage.** `ATR(t)` MUST use only bars `[t-window, t-1]`. Never include `t` itself.
- **Sample-weight by uniqueness is mandatory** when training on these labels — overlapping windows make labels non-iid; LightGBM stock bagging will memorize. Skill prints a snippet showing how to compute weights via `getAvgUniqueness` from the relabeled CSV.
- **Class-balance gate**: if any class drops below 15% of total, refuse to write the file and recommend re-tuning `k1/k2/horizon`. A degenerate label distribution is the root cause of `INSUFFICIENT_DATA` model promotions.
- **Don't replace existing labels in-place.** Always write to `data/labels/` so the operator can A/B against the old labels.

## Helper script

`tb_labeler.py` next to this SKILL.md.

## References

- López de Prado, *Advances in Financial Machine Learning* ch.3 + ch.4.
- Hudson & Thames `mlfinlab` triple-barrier reference impl.
- Robot Wealth blog series on labeling for retail FX (2023-2025).
- TrendMaster `ai_trading_agents/advanced_features.py` — partial impl this skill extends.
