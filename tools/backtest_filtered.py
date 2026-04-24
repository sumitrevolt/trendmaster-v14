"""
tools/backtest_filtered.py — 1:3 RR @ high WR explorer.

Goal
----
Starting from the EA's C1/C2/C3 3-of-3 logic, layer additional quality
filters (ADX threshold, session window, volatility band, confluence
count) and backtest with SL=1*ATR / TP=3*ATR (1:3 RR). Grid-search
filter combinations to find the one that produces >= 80% WR while
still producing enough trades (>= 30) to be statistically meaningful.

Reference: Lopez de Prado meta-labeling paper — filtering primary
signals by a secondary quality layer can push WR from 55% to 83%.
Here we use a rule-based quality layer instead of ML.

Usage
-----
    python tools/backtest_filtered.py data/xauusd_m5_history.csv
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd


def _atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    h, l, c = df["high"], df["low"], df["close"]
    tr = pd.concat([(h - l),
                    (h - c.shift()).abs(),
                    (l - c.shift()).abs()], axis=1).max(axis=1)
    return tr.rolling(n).mean()


def _ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()


def _adx(df: pd.DataFrame, n: int = 14) -> pd.Series:
    up = df["high"].diff()
    dn = -df["low"].diff()
    plus = np.where((up > dn) & (up > 0), up, 0.0)
    minus = np.where((dn > up) & (dn > 0), dn, 0.0)
    tr = pd.concat([df["high"] - df["low"],
                    (df["high"] - df["close"].shift()).abs(),
                    (df["low"] - df["close"].shift()).abs()], axis=1).max(axis=1)
    atr = tr.ewm(span=n, adjust=False).mean()
    pdi = 100 * pd.Series(plus, index=df.index).ewm(span=n, adjust=False).mean() / atr
    mdi = 100 * pd.Series(minus, index=df.index).ewm(span=n, adjust=False).mean() / atr
    dx = 100 * (pdi - mdi).abs() / (pdi + mdi).replace(0, np.nan)
    return dx.ewm(span=n, adjust=False).mean()


def _bollinger(s: pd.Series, n: int = 20, k: float = 2.0):
    mid = s.rolling(n).mean()
    std = s.rolling(n).std()
    return mid + k * std, mid, mid - k * std


def _macd_hist(s: pd.Series, fast: int = 12, slow: int = 26, sig: int = 9) -> pd.Series:
    line = _ema(s, fast) - _ema(s, slow)
    return line - _ema(line, sig)


def _super_trend(df: pd.DataFrame, period: int = 10, mult: float = 3.0) -> pd.Series:
    atr = _atr(df, period)
    hl2 = (df["high"] + df["low"]) / 2.0
    upper = hl2 + mult * atr
    lower = hl2 - mult * atr
    direction = pd.Series(index=df.index, dtype=float)
    direction.iloc[0] = 1
    for i in range(1, len(df)):
        if df["close"].iloc[i] > upper.iloc[i - 1]:
            direction.iloc[i] = 1
        elif df["close"].iloc[i] < lower.iloc[i - 1]:
            direction.iloc[i] = -1
        else:
            direction.iloc[i] = direction.iloc[i - 1]
    return direction


@dataclass
class FilterConfig:
    adx_min:         float = 22.0   # base EA threshold
    require_peak_session: bool = False    # 12-16 UTC overlap only
    vol_min_pct:     float = 0.0    # ATR >= this quantile
    vol_max_pct:     float = 1.0    # ATR <= this quantile
    require_mtf:     bool = False    # H1 EMA fan aligned with H4
    min_confluences: int = 3         # C1 + C2 + C3 all aligned
    sl_atr:          float = 1.0
    tp_atr:          float = 3.0
    hold_bars:       int = 36        # timeout after N M5 bars (3h)


@dataclass
class BacktestResult:
    name:       str
    trades:     int = 0
    wins:       int = 0
    losses:     int = 0
    timeouts:   int = 0
    gross_r:    float = 0.0
    win_rate:   float = 0.0
    expectancy: float = 0.0
    sharpe:     float = 0.0
    passed:     bool = False

    def as_dict(self) -> dict:
        return self.__dict__


def backtest_1to3(df: pd.DataFrame, cfg: FilterConfig,
                  name: str = "cfg") -> BacktestResult:
    """Walk bar-by-bar, apply filters, simulate 1:3 RR trades."""
    # Compute indicators once on the full series.
    ema20 = _ema(df["close"], 20)
    ema50 = _ema(df["close"], 50)
    ema200 = _ema(df["close"], 200)
    adx = _adx(df)
    atr = _atr(df, 14)
    bb_up, bb_mid, bb_lo = _bollinger(df["close"], 20, 2.0)
    macd_h = _macd_hist(df["close"])
    st = _super_trend(df, 10, 3.0)

    atr_quantiles = atr.rolling(500, min_periods=100).quantile
    # Cached: we compute ATR percentile vs a rolling 500-bar window.
    # For speed: use expanding quantile up to current bar.
    atr_rank = atr.rolling(200, min_periods=50).apply(
        lambda x: (x[-1] <= np.sort(x)).sum() / len(x) if len(x) else 0.5,
        raw=True,
    )

    closes = df["close"].values
    highs = df["high"].values
    lows = df["low"].values
    times = df.index

    st_vals = st.values
    ema20_v = ema20.values; ema50_v = ema50.values; ema200_v = ema200.values
    adx_v = adx.values; atr_v = atr.values
    bb_mid_v = bb_mid.values; bb_up_v = bb_up.values; bb_lo_v = bb_lo.values
    macd_v = macd_h.values
    atr_rank_v = atr_rank.values

    result = BacktestResult(name=name)
    r_results: List[float] = []

    i = 200       # warm-up
    n = len(df)
    last_trade_bar = -100
    while i < n - cfg.hold_bars:
        # Filter 1: no overlapping trades (cooldown)
        if i - last_trade_bar < 20:
            i += 1; continue

        # Filter 2: ADX threshold
        if not (adx_v[i] >= cfg.adx_min):
            i += 1; continue

        # Filter 3: session window
        if cfg.require_peak_session:
            hour = times[i].hour
            if hour < 12 or hour >= 16:
                i += 1; continue

        # Filter 4: volatility band
        rank = atr_rank_v[i]
        if not (cfg.vol_min_pct <= rank <= cfg.vol_max_pct):
            i += 1; continue

        # EA confluence — C1 (ST + EMA fan + ADX), C2 (BB mid crossed + width), C3 (MACD hist)
        direction = 0
        # Bullish?
        if (st_vals[i] > 0
                and ema20_v[i] > ema50_v[i] > ema200_v[i]
                and closes[i] > ema50_v[i]
                and adx_v[i] >= cfg.adx_min
                and closes[i] > bb_mid_v[i]
                and (bb_up_v[i] - bb_lo_v[i]) > np.nanmedian(
                    bb_up_v[max(0, i-50):i] - bb_lo_v[max(0, i-50):i]
                )
                and macd_v[i] > macd_v[i-1]
                and macd_v[i] > 0):
            direction = 1
        # Bearish?
        elif (st_vals[i] < 0
                and ema20_v[i] < ema50_v[i] < ema200_v[i]
                and closes[i] < ema50_v[i]
                and adx_v[i] >= cfg.adx_min
                and closes[i] < bb_mid_v[i]
                and (bb_up_v[i] - bb_lo_v[i]) > np.nanmedian(
                    bb_up_v[max(0, i-50):i] - bb_lo_v[max(0, i-50):i]
                )
                and macd_v[i] < macd_v[i-1]
                and macd_v[i] < 0):
            direction = -1

        if direction == 0:
            i += 1; continue

        # Simulate 1:3 RR trade.
        entry = closes[i]
        sl_dist = cfg.sl_atr * atr_v[i]
        if not np.isfinite(sl_dist) or sl_dist <= 0:
            i += 1; continue
        tp_dist = cfg.tp_atr * atr_v[i]
        sl = entry - direction * sl_dist
        tp = entry + direction * tp_dist
        outcome = None
        j_end = min(n, i + cfg.hold_bars)
        for j in range(i + 1, j_end):
            hi = highs[j]; lo = lows[j]
            hit_sl = (lo <= sl) if direction == 1 else (hi >= sl)
            hit_tp = (hi >= tp) if direction == 1 else (lo <= tp)
            if hit_sl and hit_tp:
                outcome = -1.0
                result.losses += 1
                break
            if hit_sl:
                outcome = -1.0
                result.losses += 1
                break
            if hit_tp:
                outcome = cfg.tp_atr / cfg.sl_atr   # in R units (3.0 here)
                result.wins += 1
                break
        if outcome is None:
            # Mark-to-market timeout.
            last_close = closes[j_end - 1]
            mtm = (last_close - entry) / sl_dist
            if direction == -1:
                mtm = -mtm
            outcome = mtm
            result.timeouts += 1
            if outcome > 0:
                result.wins += 1
            else:
                result.losses += 1
        r_results.append(outcome)
        last_trade_bar = i
        i += cfg.hold_bars   # skip ahead after any trade

    result.trades = len(r_results)
    if result.trades:
        arr = np.asarray(r_results)
        result.gross_r = float(arr.sum())
        result.expectancy = float(arr.mean())
        std = float(arr.std(ddof=0))
        result.sharpe = float(result.expectancy / std) if std > 0 else 0.0
        result.win_rate = result.wins / result.trades
    result.passed = (result.trades >= 30 and result.win_rate >= 0.80)
    return result


def grid_search(df: pd.DataFrame) -> List[BacktestResult]:
    """Try multiple filter combos; return all results sorted by WR desc."""
    configs: List[Tuple[str, FilterConfig]] = []

    # Baseline.
    configs.append(("baseline_1:3", FilterConfig(adx_min=22, sl_atr=1.0, tp_atr=3.0)))

    # ADX tightening.
    for adx in (25, 30, 35, 40):
        configs.append((f"adx{adx}", FilterConfig(adx_min=adx, sl_atr=1.0, tp_atr=3.0)))

    # ADX + peak session.
    for adx in (25, 30, 35):
        configs.append(
            (f"adx{adx}+peak", FilterConfig(adx_min=adx, require_peak_session=True,
                                             sl_atr=1.0, tp_atr=3.0)),
        )

    # ADX + volatility mid-band.
    for adx in (25, 30):
        configs.append(
            (f"adx{adx}+vol45-85", FilterConfig(adx_min=adx, vol_min_pct=0.45,
                                                 vol_max_pct=0.85,
                                                 sl_atr=1.0, tp_atr=3.0)),
        )

    # Ultimate stack: ADX + peak + vol-band.
    for adx in (25, 30, 35):
        configs.append(
            (f"adx{adx}+peak+vol", FilterConfig(adx_min=adx,
                                                  require_peak_session=True,
                                                  vol_min_pct=0.45,
                                                  vol_max_pct=0.85,
                                                  sl_atr=1.0, tp_atr=3.0)),
        )

    # Hold-bar variation on the best-looking stack.
    for hold in (24, 48, 72):
        configs.append(
            (f"adx30+peak+vol+hold{hold}", FilterConfig(adx_min=30,
                                                         require_peak_session=True,
                                                         vol_min_pct=0.45,
                                                         vol_max_pct=0.85,
                                                         hold_bars=hold,
                                                         sl_atr=1.0, tp_atr=3.0)),
        )

    results: List[BacktestResult] = []
    for name, cfg in configs:
        r = backtest_1to3(df, cfg, name=name)
        results.append(r)
    results.sort(key=lambda x: (x.passed, x.win_rate, x.trades), reverse=True)
    return results


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python tools/backtest_filtered.py <ohlcv_csv>")
        return 2
    csv_path = sys.argv[1]
    df = pd.read_csv(csv_path)
    if "time" in df.columns:
        df["time"] = pd.to_datetime(df["time"], utc=True)
        df = df.set_index("time")
    df = df[["open", "high", "low", "close", "volume"]].sort_index()
    print(f"Loaded {len(df)} bars")

    results = grid_search(df)
    print()
    print(f"{'config':28s} {'trades':>6s} {'WR':>6s} {'exp(R)':>7s} "
          f"{'grossR':>8s} {'Sharpe':>7s}  {'pass':>5s}")
    print("-" * 80)
    for r in results:
        mark = "PASS" if r.passed else ("near" if r.win_rate >= 0.75 else "")
        print(f"{r.name:28s} {r.trades:6d} {r.win_rate*100:5.1f}% "
              f"{r.expectancy:+7.3f} {r.gross_r:+8.2f} "
              f"{r.sharpe:+7.3f}  {mark:>5s}")

    winners = [r for r in results if r.passed]
    print()
    if winners:
        print(f"[PASS] {len(winners)} config(s) achieved >= 80% WR at 1:3 RR "
              f"with >= 30 trades.")
        print("   Top winner:", winners[0].name)
    else:
        best = max(results, key=lambda r: r.win_rate)
        print(f"[FAIL] No config achieved 80% WR at 1:3 RR. Best: "
              f"{best.name} - {best.win_rate*100:.1f}% WR, {best.trades} trades.")
    return 0 if winners else 1


if __name__ == "__main__":
    raise SystemExit(main())
