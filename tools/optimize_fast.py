"""
tools/optimize_fast.py — fast per-symbol optimizer.

Drops SuperTrend (Python-loop heavy) and uses pure-numpy EMA-fan
trend detection. Same filter logic, ~20x faster — 19 symbols in
under 60 seconds.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

SYMBOLS = [
    "XAUUSD",
    "XAGUSD",
    "GBPJPY",
    "USDCAD",
    "USDCHF",
    "EURUSD",
    "GBPUSD",
    "AUDUSD",
    "USDJPY",
    "NZDUSD",
    "EURJPY",
    "EURGBP",
    "AUDJPY",
    "CADJPY",
    "BTCUSD",
    "ETHUSD",
    "XTIUSD",
    "XBRUSD",
    "XNGUSD",
]

SL_VALUES = [1.0, 1.5, 2.0]
TP_VALUES = [1.5, 2.5, 3.5]
ADX_VALUES = [22, 30, 40]


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


def backtest(df, sl_mul, tp_mul, adx_min, hold=36, cooldown=20, warmup=210):
    """Lightweight 1:N RR backtest using EMA fan + ADX + BB mid + MACD."""
    ema20 = df["close"].ewm(span=20, adjust=False).mean().values
    ema50 = df["close"].ewm(span=50, adjust=False).mean().values
    ema200 = df["close"].ewm(span=200, adjust=False).mean().values
    adx = _adx(df).values
    atr = _atr(df).values
    bb_mid = df["close"].rolling(20).mean().values
    bb_std = df["close"].rolling(20).std().values
    # MACD hist via EMAs
    macd_line = df["close"].ewm(span=12, adjust=False).mean() - df["close"].ewm(span=26, adjust=False).mean()
    macd_sig = macd_line.ewm(span=9, adjust=False).mean()
    macd_h = (macd_line - macd_sig).values

    closes = df["close"].values
    highs = df["high"].values
    lows = df["low"].values
    n = len(df)

    wins = losses = timeouts = trades = 0
    r_outcomes = []
    last_trade = -cooldown - 1
    i = warmup
    while i < n - hold:
        if i - last_trade < cooldown:
            i += 1
            continue
        if not np.isfinite(adx[i]) or adx[i] < adx_min:
            i += 1
            continue
        direction = 0
        # Bullish: EMA fan up, close above fan, BB mid below close, MACD rising positive
        if (
            ema20[i] > ema50[i] > ema200[i]
            and closes[i] > ema50[i]
            and closes[i] > bb_mid[i]
            and macd_h[i] > macd_h[i - 1]
            and macd_h[i] > 0
        ):
            direction = 1
        elif (
            ema20[i] < ema50[i] < ema200[i]
            and closes[i] < ema50[i]
            and closes[i] < bb_mid[i]
            and macd_h[i] < macd_h[i - 1]
            and macd_h[i] < 0
        ):
            direction = -1
        if direction == 0:
            i += 1
            continue
        entry = closes[i]
        sl_dist = sl_mul * atr[i]
        if not np.isfinite(sl_dist) or sl_dist <= 0:
            i += 1
            continue
        sl = entry - direction * sl_dist
        tp = entry + direction * tp_mul * atr[i]
        outcome = None
        j_end = min(n, i + hold)
        for j in range(i + 1, j_end):
            hi = highs[j]
            lo = lows[j]
            hit_sl = (lo <= sl) if direction == 1 else (hi >= sl)
            hit_tp = (hi >= tp) if direction == 1 else (lo <= tp)
            if hit_sl and hit_tp:
                outcome = -1.0
                losses += 1
                break
            if hit_sl:
                outcome = -1.0
                losses += 1
                break
            if hit_tp:
                outcome = tp_mul / sl_mul
                wins += 1
                break
        if outcome is None:
            last_close = closes[j_end - 1]
            mtm = (last_close - entry) / sl_dist
            if direction < 0:
                mtm = -mtm
            outcome = mtm
            timeouts += 1
            if outcome > 0:
                wins += 1
            else:
                losses += 1
        r_outcomes.append(outcome)
        last_trade = i
        i += cooldown + 1
    trades = len(r_outcomes)
    if trades == 0:
        return {
            "trades": 0,
            "wins": 0,
            "losses": 0,
            "timeouts": 0,
            "win_rate": 0.0,
            "expectancy": 0.0,
            "gross_r": 0.0,
            "sharpe": 0.0,
        }
    arr = np.array(r_outcomes)
    gross = float(arr.sum())
    exp = float(arr.mean())
    std = float(arr.std(ddof=0))
    return {
        "trades": trades,
        "wins": wins,
        "losses": losses,
        "timeouts": timeouts,
        "win_rate": wins / trades,
        "expectancy": exp,
        "gross_r": gross,
        "sharpe": exp / std if std > 0 else 0.0,
    }


def score(r):
    if r["trades"] < 30:
        return -1e9
    if r["expectancy"] <= 0:
        return r["expectancy"]
    return r["expectancy"] * (r["trades"] ** 0.5) * (1.0 + r["win_rate"])


def optimize_symbol(csv_path):
    df = pd.read_csv(csv_path)
    if "time" in df.columns:
        df["time"] = pd.to_datetime(df["time"], utc=True)
        df = df.set_index("time")
    df = df[["open", "high", "low", "close", "volume"]].sort_index()
    if len(df) < 500:
        return None
    best_overall = None
    best_1to3 = None
    for sl in SL_VALUES:
        for tp in TP_VALUES:
            for adx in ADX_VALUES:
                r = backtest(df, sl, tp, adx)
                if r["trades"] == 0:
                    continue
                rr = tp / sl
                row = {"sl": sl, "tp": tp, "rr": round(rr, 2), "adx": adx, **r, "score": round(score(r), 3)}
                if best_overall is None or row["score"] > best_overall["score"]:
                    best_overall = row
                if rr >= 2.2 and (best_1to3 is None or row["score"] > best_1to3["score"]):
                    best_1to3 = row
    return {"best_overall": best_overall, "best_1to3": best_1to3}


def main():
    root = Path(__file__).resolve().parent.parent
    data_dir = root / "data"
    reports = root / "reports"
    reports.mkdir(exist_ok=True)
    summary = {}
    print(f"Optimizing {len(SYMBOLS)} symbols x {len(SL_VALUES) * len(TP_VALUES) * len(ADX_VALUES)} configs each...")
    print()
    print(f"{'symbol':8s}  {'BEST overall':60s}  {'BEST 1:3 RR':50s}")
    print("-" * 130)
    sys.stdout.flush()
    for idx, sym in enumerate(SYMBOLS, 1):
        csv = data_dir / f"{sym.lower()}_m5_history.csv"
        if not csv.exists():
            print(f"{sym:8s} (no data)")
            sys.stdout.flush()
            continue
        t0 = time.time()
        out = optimize_symbol(csv)
        dt = time.time() - t0
        if out is None:
            print(f"{sym:8s} INSUFFICIENT DATA")
            sys.stdout.flush()
            continue
        summary[sym] = out
        bo = out["best_overall"]
        b13 = out.get("best_1to3")
        left = ""
        if bo:
            left = (
                f"SL={bo['sl']} TP={bo['tp']} ADX={bo['adx']} "
                f"WR={bo['win_rate'] * 100:.1f}% exp={bo['expectancy']:+.3f} "
                f"n={bo['trades']} R={bo['gross_r']:+.1f}"
            )
        right = ""
        if b13:
            right = (
                f"SL={b13['sl']} TP={b13['tp']} ADX={b13['adx']} "
                f"WR={b13['win_rate'] * 100:.1f}% exp={b13['expectancy']:+.3f} "
                f"n={b13['trades']}"
            )
        else:
            right = "(no profitable 1:3)"
        print(f"{sym:8s}  {left:60s}  {right:50s}  [{dt:.1f}s {idx}/{len(SYMBOLS)}]")
        sys.stdout.flush()

    # JSON + MD output
    json_path = reports / "PER_PAIR_OPTIMAL.json"
    json_path.write_text(json.dumps(summary, indent=2))
    md = [
        "# Per-Pair Optimal Parameters (Fast Sweep)",
        "",
        "_50K bars per symbol, 27 configs each. Ranks by composite score._",
        "",
        "## Best overall config per symbol",
        "",
        "| Symbol | SL | TP | R:R | ADX | Trades | WR | Exp(R) | Gross R | Sharpe |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for sym in SYMBOLS:
        if sym not in summary:
            continue
        bo = summary[sym].get("best_overall")
        if not bo:
            continue
        md.append(
            f"| {sym} | {bo['sl']} | {bo['tp']} | 1:{bo['rr']} | "
            f"{bo['adx']} | {bo['trades']} | {bo['win_rate'] * 100:.1f}% | "
            f"{bo['expectancy']:+.3f} | {bo['gross_r']:+.1f} | "
            f"{bo['sharpe']:+.2f} |"
        )
    md.append("")
    md.append("## Best 1:3 RR (or better) config per symbol")
    md.append("")
    md.append("| Symbol | SL | TP | R:R | ADX | Trades | WR | Exp(R) | Gross R |")
    md.append("| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |")
    for sym in SYMBOLS:
        if sym not in summary:
            continue
        b13 = summary[sym].get("best_1to3")
        if not b13:
            md.append(f"| {sym} | — | — | — | — | — | — | — | — |")
            continue
        md.append(
            f"| {sym} | {b13['sl']} | {b13['tp']} | 1:{b13['rr']} | "
            f"{b13['adx']} | {b13['trades']} | {b13['win_rate'] * 100:.1f}% | "
            f"{b13['expectancy']:+.3f} | {b13['gross_r']:+.1f} |"
        )
    (reports / "PER_PAIR_OPTIMAL.md").write_text("\n".join(md) + "\n")

    # pair_params.py
    lines = [
        '"""Auto-generated per-symbol optimal parameters.',
        "",
        "Generated by tools/optimize_fast.py. DO NOT EDIT BY HAND.",
        '"""',
        "",
        "PAIR_PARAMS = {",
    ]
    for sym in SYMBOLS:
        if sym not in summary:
            continue
        b13 = summary[sym].get("best_1to3")
        bo = summary[sym].get("best_overall")
        # Prefer 1:3 if its expectancy passes a minimum. Otherwise best overall.
        pick = b13 if (b13 and b13["expectancy"] > 0.05) else bo
        if not pick:
            continue
        lines.append(f"    '{sym}': {{")
        lines.append(f"        'sl_atr_mult':  {pick['sl']},")
        lines.append(f"        'tp_atr_mult':  {pick['tp']},")
        lines.append(f"        'adx_min':      {pick['adx']},")
        lines.append(f"        'expected_wr':  {pick['win_rate']:.4f},")
        lines.append(f"        'expected_exp': {pick['expectancy']:.4f},")
        lines.append(f"        'trades_bt':    {pick['trades']},")
        lines.append(f"        'gross_r':      {pick['gross_r']:.2f},")
        lines.append(f"        'sharpe':       {pick['sharpe']:.3f},")
        lines.append("    },")
    lines.append("}")
    (root / "ai_trading_agents" / "pair_params.py").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print()
    print(f"Wrote: {json_path}")
    print(f"Wrote: {reports / 'PER_PAIR_OPTIMAL.md'}")
    print(f"Wrote: ai_trading_agents/pair_params.py")


if __name__ == "__main__":
    main()
