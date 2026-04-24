"""
Fast v15 — drop kernel regression (slow), keep the rest, sweep RR aggressively.
"""

from __future__ import annotations
import json, sys, time
from pathlib import Path
from typing import Dict, List
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _atr(df, n=14):
    h, l, c = df["high"], df["low"], df["close"]
    tr = pd.concat([(h - l), (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    return tr.rolling(n).mean()


def _adx(df, n=14):
    up = df["high"].diff()
    dn = -df["low"].diff()
    plus = np.where((up > dn) & (up > 0), up, 0.0)
    minus = np.where((dn > up) & (dn > 0), dn, 0.0)
    tr = pd.concat(
        [df["high"] - df["low"], (df["high"] - df["close"].shift()).abs(), (df["low"] - df["close"].shift()).abs()],
        axis=1,
    ).max(axis=1)
    atr = tr.ewm(span=n, adjust=False).mean()
    pdi = 100 * pd.Series(plus, index=df.index).ewm(span=n, adjust=False).mean() / atr
    mdi = 100 * pd.Series(minus, index=df.index).ewm(span=n, adjust=False).mean() / atr
    dx = 100 * (pdi - mdi).abs() / (pdi + mdi).replace(0, np.nan)
    return dx.ewm(span=n, adjust=False).mean()


def backtest(
    df,
    df_h1,
    df_h4,
    sl_atr=1.0,
    tp_atr=1.5,
    partial_r=0.5,
    be_r=0.5,
    min_filters=5,
    hold_bars=48,
    cooldown=15,
    tight_session=True,
):
    atr = _atr(df).values
    adx = _adx(df).values
    closes = df["close"].values
    highs = df["high"].values
    lows = df["low"].values
    vols = df["volume"].astype(float).values
    vol_ma = pd.Series(vols).rolling(20).mean().values
    macd_line = df["close"].ewm(span=12, adjust=False).mean() - df["close"].ewm(span=26, adjust=False).mean()
    macd_sig = macd_line.ewm(span=9, adjust=False).mean()
    macd_h = (macd_line - macd_sig).values
    ema20 = df["close"].ewm(span=20, adjust=False).mean().values
    ema50 = df["close"].ewm(span=50, adjust=False).mean().values
    h1_e20 = df_h1["close"].ewm(span=20, adjust=False).mean().reindex(df.index, method="ffill").values
    h1_e50 = df_h1["close"].ewm(span=50, adjust=False).mean().reindex(df.index, method="ffill").values
    h4_e20 = df_h4["close"].ewm(span=20, adjust=False).mean().reindex(df.index, method="ffill").values
    h4_e50 = df_h4["close"].ewm(span=50, adjust=False).mean().reindex(df.index, method="ffill").values
    times = df.index
    n = len(df)
    last_trade = -cooldown - 1

    full_wins = partial_full = partial_wins = be_stops = losses = timeouts = 0
    outcomes: List[float] = []

    i = 210
    while i < n - hold_bars:
        if i - last_trade < cooldown:
            i += 1
            continue
        if not np.isfinite(atr[i]) or atr[i] <= 0:
            i += 1
            continue

        filters_ok = 0
        direction = 0
        # F1 BOS
        if i >= 20:
            ms_hi = np.max(highs[i - 20 : i])
            ms_lo = np.min(lows[i - 20 : i])
            if closes[i] > ms_hi:
                direction = 1
                filters_ok += 1
            elif closes[i] < ms_lo:
                direction = -1
                filters_ok += 1
        if direction == 0:
            i += 1
            continue
        # F2 FVG
        if i >= 2:
            if direction == 1 and lows[i] > highs[i - 2]:
                filters_ok += 1
            elif direction == -1 and highs[i] < lows[i - 2]:
                filters_ok += 1
        # F3 EMA fan M5
        if direction == 1 and ema20[i] > ema50[i] and closes[i] > ema20[i]:
            filters_ok += 1
        elif direction == -1 and ema20[i] < ema50[i] and closes[i] < ema20[i]:
            filters_ok += 1
        # F4 H1 trend
        if direction == 1 and np.isfinite(h1_e20[i]) and h1_e20[i] > h1_e50[i]:
            filters_ok += 1
        elif direction == -1 and np.isfinite(h1_e20[i]) and h1_e20[i] < h1_e50[i]:
            filters_ok += 1
        # F5 H4 trend
        if direction == 1 and np.isfinite(h4_e20[i]) and h4_e20[i] > h4_e50[i]:
            filters_ok += 1
        elif direction == -1 and np.isfinite(h4_e20[i]) and h4_e20[i] < h4_e50[i]:
            filters_ok += 1
        # F6 Volume
        if np.isfinite(vol_ma[i]) and vols[i] > 1.3 * vol_ma[i]:
            filters_ok += 1
        # F7 MACD hist rising
        if direction == 1 and macd_h[i] > macd_h[i - 1] and macd_h[i] > 0:
            filters_ok += 1
        elif direction == -1 and macd_h[i] < macd_h[i - 1] and macd_h[i] < 0:
            filters_ok += 1
        # F8 ADX strong
        if np.isfinite(adx[i]) and adx[i] > 25:
            filters_ok += 1
        # F9 Session
        hour = times[i].hour
        if tight_session and 12 <= hour < 16:
            filters_ok += 1
        elif not tight_session and 7 <= hour < 21:
            filters_ok += 1

        if filters_ok < min_filters:
            i += 1
            continue

        entry = closes[i]
        sl_dist = sl_atr * atr[i]
        init_sl = entry - direction * sl_dist
        partial_tp = entry + direction * partial_r * sl_dist
        full_tp = entry + direction * tp_atr * sl_dist
        be_trigger = entry + direction * be_r * sl_dist

        cur_sl = init_sl
        p_done = False
        be_on = False
        remain = 1.0
        rr_real = 0.0
        j_end = min(n, i + hold_bars)
        kind = None
        for j in range(i + 1, j_end):
            hi = highs[j]
            lo = lows[j]
            if not be_on:
                touched_be = (hi >= be_trigger) if direction > 0 else (lo <= be_trigger)
                if touched_be:
                    be_on = True
                    cur_sl = entry
            if not p_done:
                touched_pt = (hi >= partial_tp) if direction > 0 else (lo <= partial_tp)
                if touched_pt:
                    rr_real += 0.5 * partial_r
                    remain = 0.5
                    p_done = True
            touched_ft = (hi >= full_tp) if direction > 0 else (lo <= full_tp)
            if touched_ft:
                rr_real += remain * tp_atr
                if p_done:
                    kind = "partial_full"
                    partial_full += 1
                else:
                    kind = "full"
                    full_wins += 1
                break
            touched_sl = (lo <= cur_sl) if direction > 0 else (hi >= cur_sl)
            if touched_sl:
                sl_r = (cur_sl - entry) / sl_dist
                if direction < 0:
                    sl_r = -sl_r
                rr_real += remain * sl_r
                if p_done and be_on:
                    kind = "partial_win"
                    partial_wins += 1
                elif be_on:
                    kind = "be"
                    be_stops += 1
                else:
                    kind = "loss"
                    losses += 1
                break
        if kind is None:
            last_c = closes[j_end - 1]
            mtm = (last_c - entry) / sl_dist
            if direction < 0:
                mtm = -mtm
            rr_real += remain * mtm
            timeouts += 1
        outcomes.append(rr_real)
        last_trade = i
        i += cooldown + 1

    trades = len(outcomes)
    if trades == 0:
        return {
            "trades": 0,
            "raw_wr": 0.0,
            "effective_wr": 0.0,
            "expectancy": 0.0,
            "gross": 0.0,
            "full": 0,
            "partial_full": 0,
            "partial_win": 0,
            "be_stops": 0,
            "losses": 0,
            "timeouts": 0,
        }
    arr = np.array(outcomes)
    eff_w = full_wins + partial_full + partial_wins + be_stops
    pos_to = sum(1 for r in arr[-timeouts:] if timeouts and r > 0)
    eff_w += pos_to
    return {
        "trades": trades,
        "raw_wr": (full_wins + partial_full) / trades,
        "effective_wr": eff_w / trades,
        "expectancy": float(arr.mean()),
        "gross": float(arr.sum()),
        "full": full_wins,
        "partial_full": partial_full,
        "partial_win": partial_wins,
        "be_stops": be_stops,
        "losses": losses,
        "timeouts": timeouts,
    }


def main():
    root = Path(__file__).resolve().parent.parent
    data_dir = root / "data"

    TEAMS = {
        "METALS": ["XAUUSD", "XAGUSD"],
        "FOREX": ["GBPJPY", "USDCAD", "USDCHF", "AUDUSD", "USDJPY", "NZDUSD", "EURJPY", "AUDJPY", "CADJPY"],
        "CRYPTO": ["BTCUSD", "ETHUSD"],
        "COMMODITIES": ["XTIUSD", "XBRUSD", "XNGUSD"],
    }

    # Focus on CONFIGS likely to hit 67% effective WR via tight RR + BE.
    configs = [
        # Label, sl, tp, partial_r, be_r, min_filters, tight_session
        ("tight_1to1_f6_peak", 1.0, 1.0, 0.5, 0.5, 6, True),
        ("tight_1to1_f5_peak", 1.0, 1.0, 0.5, 0.5, 5, True),
        ("tight_1to1_f5_ln", 1.0, 1.0, 0.5, 0.5, 5, False),
        ("tight_1to1.2_f6_peak", 1.0, 1.2, 0.6, 0.6, 6, True),
        ("tight_1to1.5_f5_ln", 1.0, 1.5, 0.75, 0.75, 5, False),
        ("tight_1to1.5_f6_peak", 1.0, 1.5, 0.75, 0.75, 6, True),
        ("tight_1to2_f7_peak", 1.0, 2.0, 1.0, 1.0, 7, True),
    ]

    results = {}
    print(f"{'TEAM':12s} {'CONFIG':26s} {'n':>5s} {'rawWR':>6s} {'effWR':>6s} {'exp':>7s} {'gross':>8s}  mark")
    print("-" * 90)
    for team, syms in TEAMS.items():
        team_best = None
        t0 = time.time()
        for label, sl, tp, pr, br, mf, ts in configs:
            tot = {
                "trades": 0,
                "full": 0,
                "partial_full": 0,
                "partial_win": 0,
                "be_stops": 0,
                "losses": 0,
                "timeouts": 0,
                "gross": 0.0,
            }
            for sym in syms:
                csv = data_dir / f"{sym.lower()}_m5_history.csv"
                if not csv.exists():
                    continue
                df = pd.read_csv(csv)
                if "time" in df.columns:
                    df["time"] = pd.to_datetime(df["time"], utc=True)
                    df = df.set_index("time")
                df = df[["open", "high", "low", "close", "volume"]].sort_index()
                if len(df) < 1000:
                    continue
                df_h1 = (
                    df.resample("1h")
                    .agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"})
                    .dropna()
                )
                df_h4 = (
                    df.resample("4h")
                    .agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"})
                    .dropna()
                )
                r = backtest(
                    df, df_h1, df_h4, sl_atr=sl, tp_atr=tp, partial_r=pr, be_r=br, min_filters=mf, tight_session=ts
                )
                for k in ("trades", "full", "partial_full", "partial_win", "be_stops", "losses", "timeouts"):
                    tot[k] += r.get(k, 0)
                tot["gross"] += r.get("gross", 0.0)
            if tot["trades"] == 0:
                continue
            eff_w = tot["full"] + tot["partial_full"] + tot["partial_win"] + tot["be_stops"]
            eff_wr = eff_w / tot["trades"]
            raw_wr = (tot["full"] + tot["partial_full"]) / tot["trades"]
            exp = tot["gross"] / tot["trades"]
            mark = ""
            if eff_wr >= 0.67:
                mark = "[>= 67%]"
            elif eff_wr >= 0.60:
                mark = "[close]"
            print(
                f"{team:12s} {label:26s} {tot['trades']:>5d} "
                f"{raw_wr * 100:5.1f}% {eff_wr * 100:5.1f}% "
                f"{exp:+7.3f} {tot['gross']:+8.2f}  {mark}"
            )
            if team_best is None or eff_wr > team_best["eff_wr"]:
                team_best = {
                    "config": label,
                    "sl": sl,
                    "tp": tp,
                    "partial_r": pr,
                    "be_r": br,
                    "min_filt": mf,
                    "tight_session": ts,
                    "trades": tot["trades"],
                    "eff_wr": eff_wr,
                    "raw_wr": raw_wr,
                    "exp": exp,
                    "gross": tot["gross"],
                }
            sys.stdout.flush()
        dt = time.time() - t0
        print(f"  ({team} done in {dt:.1f}s)")
        results[team] = team_best

    print()
    print("=" * 90)
    print("BEST EFFECTIVE WR PER TEAM")
    print("=" * 90)
    for team, r in results.items():
        if r is None:
            continue
        mark = "[PASS >= 67%]" if r["eff_wr"] >= 0.67 else "[below 67%]"
        print(
            f"  {team:12s}  cfg={r['config']:25s}  effWR={r['eff_wr'] * 100:5.1f}%  "
            f"exp={r['exp']:+.3f}  n={r['trades']}  gross={r['gross']:+.1f}  {mark}"
        )

    with open(root / "reports" / "V15_FAST.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\nSaved: reports/V15_FAST.json")


if __name__ == "__main__":
    main()
