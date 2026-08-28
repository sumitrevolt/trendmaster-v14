# v14.5 Per-Team Config Promotion Gate -- 2026-04-25_2101

CPCV-style purged walk-forward gate comparing v14.5 per-team configs
(SL/TP + per-team ADX/ST) against the v14.4 universal baseline
(sl=2.0, tp=3.0, adx=22, st=3.0).

Folds per symbol: **5** | Embargo: **200 bars** (~17h on M5)

| Team | v14.5 Sharpe (mean ± std) | v14.4 Sharpe (mean ± std) | Δ Sharpe | v14.5 trades | Verdict |
|---|---|---|---|---|---|
| METALS | 0.921 ± 0.863 | 0.626 ± 0.778 | +0.295 | 16890 | **PROMOTE** |
| FOREX | -0.689 ± 1.285 | -0.643 ± 1.189 | -0.046 | 65451 | **HOLD** |
| CRYPTO | 0.543 ± 1.377 | 0.186 ± 0.807 | +0.357 | 6026 | **PROMOTE** |
| COMMODITIES | 0.397 ± 1.052 | -0.068 ± 0.941 | +0.464 | 11651 | **PROMOTE** |

## Per-team detail

### METALS

**Config v14.5**: {'sl_atr_mult': 3.0, 'tp_atr_mult': 5.0, 'adx_min': 15, 'st_mult': 3.0, 'bb_width_floor_pct': 1.0, 'expected_wr': 0.478, 'expected_exp': 1.971, 'trades_bt': 14512, 'sharpe': 0.67}

**Verdict**: PROMOTE

- v14.5: trades=16890 WR=0.421 exp_R=0.074
- v14.4: trades=13784 WR=0.421 exp_R=0.048

### FOREX

**Config v14.5**: {'sl_atr_mult': 2.5, 'tp_atr_mult': 3.0, 'adx_min': 25, 'st_mult': 3.0, 'bb_width_floor_pct': 1.0, 'expected_wr': 0.477, 'expected_exp': 0.918, 'trades_bt': 90034, 'sharpe': 0.46}

**Verdict**: HOLD

- v14.5: trades=65451 WR=0.438 exp_R=-0.041
- v14.4: trades=84827 WR=0.387 exp_R=-0.044

### CRYPTO

**Config v14.5**: {'sl_atr_mult': 2.5, 'tp_atr_mult': 3.0, 'adx_min': 35, 'st_mult': 2.5, 'bb_width_floor_pct': 1.0, 'expected_wr': 0.513, 'expected_exp': 1.057, 'trades_bt': 15511, 'sharpe': 0.53}

**Verdict**: PROMOTE

- v14.5: trades=6026 WR=0.474 exp_R=0.038
- v14.4: trades=14568 WR=0.410 exp_R=0.017

### COMMODITIES

**Config v14.5**: {'sl_atr_mult': 2.5, 'tp_atr_mult': 3.0, 'adx_min': 30, 'st_mult': 2.0, 'bb_width_floor_pct': 1.0, 'expected_wr': 0.483, 'expected_exp': 0.945, 'trades_bt': 22154, 'sharpe': 0.48}

**Verdict**: PROMOTE

- v14.5: trades=11651 WR=0.469 exp_R=0.028
- v14.4: trades=21172 WR=0.401 exp_R=-0.003

## Summary

- **PROMOTE**: METALS, CRYPTO, COMMODITIES
- **HOLD**: FOREX
