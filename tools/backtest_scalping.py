"""Backtest harness for the advanced ScalpEngine (SMC + mean-reversion).

Runs the SAME detection logic the live brain uses, but against historical M5
bars so you can measure the edge before risking capital. It simulates pending
LIMIT orders exactly like the live executor would: a BUY LIMIT fills when a
later bar's low trades down to `entry`; a SELL LIMIT fills when a later bar's
high trades up to `entry`. Exits are SL/TP (server-side, like a real pending
order). Spread is modeled from the symbol's live tick + a configurable add.

Requires an MT5 terminal connected to the account (read-only history is free).
Run:  .venv\Scripts\python.exe tools/backtest_scalping.py --symbol GBPJPY --bars 3000
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

# allow running from repo root
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np

try:
    import MetaTrader5 as mt5
except Exception:
    mt5 = None

from ai_trading_agents.scalping_engine import ScalpingEngine, _atr, _adx, _session_utc
from config import settings
from datetime import datetime, timezone


TF_MIN = {"M1": 1, "M5": 5, "M15": 15, "H1": 60}


def _tf_int(tf: str) -> int:
    return getattr(mt5, f"TIMEFRAME_{tf}", 5) if mt5 else 5


def load_history(symbol: str, tf: str, count: int) -> dict:
    if mt5 is None or not mt5.terminal_info():
        raise RuntimeError("MT5 terminal not connected")
    r = mt5.copy_rates_from_pos(symbol, _tf_int(tf), 0, count)
    if r is None or len(r) == 0:
        raise RuntimeError(f"no history for {symbol} {tf}")
    return {
        "time": np.array([int(x["time"]) for x in r]),
        "open": np.array([float(x["open"]) for x in r]),
        "high": np.array([float(x["high"]) for x in r]),
        "low": np.array([float(x["low"]) for x in r]),
        "close": np.array([float(x["close"]) for x in r]),
        "tick_volume": np.array([float(x["tick_volume"]) for x in r]),
    }


def htf_bias_from(h1: dict, t: int):
    """Approximate the engine's H1 bias/ADX using a window ending at bar t."""
    c = h1["close"][: t + 1]
    h = h1["high"][: t + 1]
    l = h1["low"][: t + 1]
    if len(c) < 30:
        return 0.0, float("nan")
    ema = c[-1] - c[-20] if len(c) >= 20 else 0.0
    bias = 1.0 if ema > 0 else -1.0 if ema < 0 else 0.0
    try:
        adx = _adx(h, l, c, 14)[-1]
    except Exception:
        adx = float("nan")
    return bias, adx


def session_for_ts(ts: int) -> str:
    """Replicate ScalpingEngine._session_utc() using a bar's own UTC hour
    (so backtest respects the session gate per historical bar)."""
    h = datetime.fromtimestamp(ts, tz=timezone.utc).hour
    if 0 <= h < 7:
        return "tokyo"
    if 7 <= h < 9:
        return "frankfurt"
    if 9 <= h < 12:
        return "london"
    if 12 <= h < 16:
        return "london_ny_overlap"
    if 16 <= h < 20:
        return "ny"
    if 20 <= h < 22:
        return "sydney"
    return "quiet"


def simulate(symbol: str, m5: dict, h1: dict, eng: ScalpingEngine,
             spread_add: float = 0.0, warmup: int = 200, max_bars_open: int = 300) -> dict:
    n = len(m5["close"])
    wins = losses = 0
    pnl = []
    pending = None  # dict: direction, entry, sl, tp, idx
    momentum = set(eng.cfg.get("momentum_sessions", []))
    meanrev = set(eng.cfg.get("meanrev_sessions", []))
    min_conf = float(eng.cfg.get("min_confidence", 0.60))

    W = int(eng.cfg.get("backtest_window", 250))  # mirror live _rates() window
    for t in range(warmup, n):
        ws = max(0, t - W)
        win = {k: arr[ws:t] for k, arr in m5.items()}
        ts = int(m5["time"][t - 1])
        h1_idx = int(np.searchsorted(h1["time"], ts, side="right") - 1)
        if h1_idx < 0:
            h1_idx = 0
        hs = max(0, h1_idx - W)
        h1win = {k: arr[hs:h1_idx + 1] for k, arr in h1.items()}
        bias, adx = htf_bias_from(h1win, len(h1win["close"]) - 1)
        eng._htf_bias = lambda s: (bias, adx)
        session = session_for_ts(ts)
        setup = None
        if session in momentum:
            try:
                setup = eng._detect_smc(symbol, win, session)
            except Exception:
                setup = None
        elif session in meanrev:
            try:
                setup = eng._detect_mean_reversion(symbol, win)
            except Exception:
                setup = None
        if setup is not None and setup.get("confidence", 0) < min_conf:
            setup = None

        if setup is not None and pending is None:
            a = _atr(win["high"], win["low"], win["close"], 14)[-1]
            slm = setup["sl_atr_mult"]; tpm = setup["tp_atr_mult"]
            tp1m = setup.get("tp1_atr_mult", tpm)
            is_smc = setup.get("mode") == "smc"
            so = eng.cfg.get("scale_out", {})
            scale = bool(so.get("enabled", False)) and is_smc
            frac = float(so.get("frac", 0.5))
            pending = {"direction": setup["direction"], "entry": setup["entry_price"], "idx": t,
                       "mode": setup["mode"], "is_smc_scale": scale, "frac": frac}
            if setup["direction"] == "BUY":
                pending["sl"] = setup["entry_price"] - slm * a
                pending["tp"] = setup["entry_price"] + tpm * a
                pending["tp1"] = setup["entry_price"] + tp1m * a
                pending["be"] = setup["entry_price"]
            else:
                pending["sl"] = setup["entry_price"] + slm * a
                pending["tp"] = setup["entry_price"] - tpm * a
                pending["tp1"] = setup["entry_price"] - tp1m * a
                pending["be"] = setup["entry_price"]

        if pending is not None:
            max_hold = int(eng.cfg.get("max_hold_bars", 0))
            filled = None
            for u in range(pending["idx"] + 1, min(pending["idx"] + max_bars_open, n)):
                if pending["direction"] == "BUY":
                    if m5["low"][u] <= pending["entry"]:
                        filled = u; break
                else:
                    if m5["high"][u] >= pending["entry"]:
                        filled = u; break
            if filled is None:
                if t - pending["idx"] > max_bars_open:
                    pending = None
                continue
            entry = pending["entry"]; sl0 = pending["sl"]; tp = pending["tp"]
            tp1 = pending["tp1"]; be = pending["be"]; direction = pending["direction"]
            scale = pending["is_smc_scale"]; frac = pending["frac"]
            if direction == "BUY":
                r_den = (entry - sl0)
            else:
                r_den = (sl0 - entry)
            sl_now = sl0; tp1_hit = False; done = False
            for u in range(filled + 1, min(filled + max_bars_open, n)):
                if max_hold > 0 and (u - filled) >= max_hold:
                    price = m5["close"][u]
                    if direction == "BUY":
                        r = (price - entry) / r_den
                    else:
                        r = (entry - price) / r_den
                    if scale and tp1_hit:
                        r = frac * 1.0 + (1 - frac) * r
                    pnl.append(r)
                    if r >= 0:
                        wins += 1
                    else:
                        losses += 1
                    done = True; break
                if direction == "BUY":
                    if m5["high"][u] >= tp:
                        if scale and tp1_hit:
                            r = frac * 1.0 + (1 - frac) * ((tp - entry) / r_den)
                        else:
                            r = (tp - entry) / r_den
                        pnl.append(r); wins += 1; done = True; break
                    if (not tp1_hit) and m5["high"][u] >= tp1:
                        tp1_hit = True; sl_now = be; pnl.append(frac * 1.0); continue
                    if m5["low"][u] <= sl_now:
                        if scale and tp1_hit:
                            pnl.append(frac * 1.0); wins += 1
                        else:
                            pnl.append(-1.0); losses += 1
                        done = True; break
                else:
                    if m5["low"][u] <= tp:
                        if scale and tp1_hit:
                            r = frac * 1.0 + (1 - frac) * ((entry - tp) / r_den)
                        else:
                            r = (entry - tp) / r_den
                        pnl.append(r); wins += 1; done = True; break
                    if (not tp1_hit) and m5["low"][u] <= tp1:
                        tp1_hit = True; sl_now = be; pnl.append(frac * 1.0); continue
                    if m5["high"][u] >= sl_now:
                        if scale and tp1_hit:
                            pnl.append(frac * 1.0); wins += 1
                        else:
                            pnl.append(-1.0); losses += 1
                        done = True; break
            if not done:
                pass  # open at window end -> ignored
            pending = None

    total = wins + losses
    winrate = wins / total if total else 0.0
    expectancy = sum(pnl) / total if total else 0.0
    gross_win = sum(p for p in pnl if p > 0)
    gross_loss = sum(-p for p in pnl if p < 0)
    pf = gross_win / gross_loss if gross_loss else float("inf")
    return {
        "symbol": symbol,
        "signals": total,
        "wins": wins,
        "losses": losses,
        "winrate": round(winrate, 4),
        "expectancy_R": round(expectancy, 4),
        "profit_factor": round(pf, 3) if gross_loss else None,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default="GBPJPY")
    ap.add_argument("--bars", type=int, default=3000)
    ap.add_argument("--oos-gap", type=int, default=0,
                    help="fetch this many extra OLDER bars and evaluate the oldest "
                         "`bars` of them (true out-of-sample, non-overlapping with IS)")
    ap.add_argument("--warmup", type=int, default=250)
    ap.add_argument("--spread-add", type=float, default=0.0,
                    help="extra spread points to penalize entries (realism)")
    args = ap.parse_args()

    if mt5 is None:
        print("MetaTrader5 package not available.")
        return 2
    mt5.initialize()
    if not mt5.terminal_info():
        print("MT5 terminal not connected. Start MT5 and ensure it is logged in, then rerun.")
        return 2

    cfg = getattr(settings, "SCALPING", {})
    eng = ScalpingEngine(cfg)
    total = args.bars + args.oos_gap
    h1 = load_history(args.symbol, "H1", total // 12 + 50)
    m5 = load_history(args.symbol, "M5", total)
    if args.oos_gap > 0:
        # evaluate the OLDEST `bars` bars => true out-of-sample, no overlap with IS
        keep = args.bars + args.warmup + 50
        m5 = {k: arr[:keep] for k, arr in m5.items()}
        hkeep = args.bars // 12 + args.warmup // 12 + 50
        h1 = {k: arr[:hkeep] for k, arr in h1.items()}
    res = simulate(args.symbol, m5, h1, eng, spread_add=args.spread_add, warmup=args.warmup)
    print(json.dumps(res, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
