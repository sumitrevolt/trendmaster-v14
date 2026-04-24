"""
tools/backtest.py — walk-forward backtester for TrendMaster v14.

What it does
------------
1. Loads an OHLCV CSV (default: data/{symbol}_m5_history.csv).
2. Walks bar-by-bar; for each bar, resamples to M30/H1/H4 using only
   data up to that bar (no lookahead) and calls the agent bus.
3. When the bus returns BUY/SELL, simulates a trade with fixed R:R
   (SL = 1 ATR, TP = 2 * SL). Tracks hit/miss/timeout on the next N bars.
4. Reports win rate, average R, expectancy, max consecutive losses,
   and whether the strategy is "viable" (expectancy > 0 and sample size
   ≥ MIN_TRADES).

This is the backtest harness the final-upgrade report called for:
it lets you measure if the rule-based agent bus actually has edge on
arbitrary instruments before you switch them live.

Design choices
--------------
* No stateful order-book simulation. Simple MAE/MFE on close prices
  from the signal bar. That's the right fidelity for swing / M5-gated
  entries — not for HFT.
* Python-only, no backtesting.py or vectorbt dep. Keeps CI lean.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

import numpy as np
import pandas as pd

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from ai_trading_agents.multi_agent import vote_all  # noqa: E402
from ai_trading_agents.ea_confirmations import compute_confirmations  # noqa: E402


MIN_TRADES_VIABLE = 30
DEFAULT_HOLD_BARS = 12      # M5 bars = 1 hour hold
SL_ATR_MULT       = 1.0
RR                = 2.0


def _atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    h, l, c = df["high"], df["low"], df["close"]
    tr = pd.concat([(h - l),
                    (h - c.shift()).abs(),
                    (l - c.shift()).abs()], axis=1).max(axis=1)
    return tr.rolling(n).mean()


def _resample(df: pd.DataFrame, minutes: int) -> pd.DataFrame:
    return df.resample(f"{minutes}min").agg({
        "open": "first", "high": "max", "low": "min",
        "close": "last", "volume": "sum",
    }).dropna()


@dataclass
class Trade:
    time: pd.Timestamp
    direction: str
    entry: float
    sl: float
    tp: float
    exit_price: float = np.nan
    outcome: str = "open"      # "win" | "loss" | "timeout"
    r_multiple: float = 0.0


@dataclass
class BacktestReport:
    symbol: str
    trades: List[Trade] = field(default_factory=list)
    bars_scanned: int   = 0

    # Derived
    n:           int   = 0
    wins:        int   = 0
    losses:      int   = 0
    timeouts:    int   = 0
    win_rate:    float = 0.0
    avg_r:       float = 0.0
    expectancy:  float = 0.0
    max_consec_loss: int = 0

    def compute(self) -> None:
        self.n = len(self.trades)
        self.wins      = sum(1 for t in self.trades if t.outcome == "win")
        self.losses    = sum(1 for t in self.trades if t.outcome == "loss")
        self.timeouts  = sum(1 for t in self.trades if t.outcome == "timeout")
        self.win_rate  = (self.wins / self.n) if self.n else 0.0
        self.avg_r     = (sum(t.r_multiple for t in self.trades) / self.n) if self.n else 0.0
        self.expectancy = self.avg_r
        # Max consecutive losses
        run = best = 0
        for t in self.trades:
            run = run + 1 if t.outcome == "loss" else 0
            best = max(best, run)
        self.max_consec_loss = best

    def is_viable(self) -> bool:
        return self.n >= MIN_TRADES_VIABLE and self.expectancy > 0

    def format(self) -> str:
        self.compute()
        lines = [
            f"Backtest report — {self.symbol}",
            "-" * 40,
            f"Bars scanned       : {self.bars_scanned}",
            f"Trades             : {self.n}",
            f"Wins / Losses / TO : {self.wins} / {self.losses} / {self.timeouts}",
            f"Win rate           : {self.win_rate*100:.1f}%",
            f"Average R          : {self.avg_r:+.3f}",
            f"Expectancy         : {self.expectancy:+.3f} R / trade",
            f"Max consec losses  : {self.max_consec_loss}",
            f"Viable             : {self.is_viable()}",
        ]
        return "\n".join(lines)


def run_backtest(symbol: str,
                 csv_path: Optional[str] = None,
                 min_votes: int = 3,
                 warmup_bars: int = 600,
                 stride: int = 12,
                 hold_bars: int = DEFAULT_HOLD_BARS) -> BacktestReport:
    """
    Walk-forward backtest. Evaluates the bus only every `stride` M5 bars
    (so one decision per hour by default) — matches how the live brain
    actually fires.
    """
    path = Path(csv_path) if csv_path else _ROOT / "data" / f"{symbol.lower()}_m5_history.csv"
    if not path.exists():
        raise FileNotFoundError(f"No history csv at {path}")
    df = pd.read_csv(path)
    if "time" in df.columns:
        df["time"] = pd.to_datetime(df["time"], utc=True)
        df = df.set_index("time")
    df = df[["open", "high", "low", "close", "volume"]].sort_index()

    report = BacktestReport(symbol=symbol)
    atr = _atr(df, 14)

    if len(df) < warmup_bars + hold_bars + 50:
        report.bars_scanned = len(df)
        return report

    for i in range(warmup_bars, len(df) - hold_bars, stride):
        window = df.iloc[: i + 1]
        frames = {
            "M30": _resample(window, 30),
            "H1":  _resample(window, 60),
            "H4":  _resample(window, 240),
        }
        direction, _ = vote_all(frames, min_votes=min_votes)
        if direction == 0:
            report.bars_scanned += 1
            continue

        entry_ts = df.index[i]
        entry_px = float(df["close"].iloc[i])
        atr_now  = float(atr.iloc[i])
        if not np.isfinite(atr_now) or atr_now <= 0:
            continue
        sl_dist = SL_ATR_MULT * atr_now
        if direction == +1:
            sl, tp = entry_px - sl_dist, entry_px + RR * sl_dist
            d = "BUY"
        else:
            sl, tp = entry_px + sl_dist, entry_px - RR * sl_dist
            d = "SELL"

        tr = Trade(entry_ts, d, entry_px, sl, tp)
        forward = df.iloc[i + 1 : i + 1 + hold_bars]
        for _, row in forward.iterrows():
            hi, lo = float(row["high"]), float(row["low"])
            if direction == +1:
                if lo <= sl:
                    tr.outcome, tr.exit_price, tr.r_multiple = "loss", sl, -1.0
                    break
                if hi >= tp:
                    tr.outcome, tr.exit_price, tr.r_multiple = "win", tp, RR
                    break
            else:
                if hi >= sl:
                    tr.outcome, tr.exit_price, tr.r_multiple = "loss", sl, -1.0
                    break
                if lo <= tp:
                    tr.outcome, tr.exit_price, tr.r_multiple = "win", tp, RR
                    break
        if tr.outcome == "open":
            exit_px = float(forward["close"].iloc[-1])
            tr.exit_price = exit_px
            r = (exit_px - entry_px) / sl_dist * (1 if direction == +1 else -1)
            tr.r_multiple = round(r, 3)
            tr.outcome = "timeout"
        report.trades.append(tr)
        report.bars_scanned += 1
    report.compute()
    return report


def run_ea_parity_backtest(df: pd.DataFrame,
                           sl_atr_mult: float = 1.5,
                           tp_atr_mult: float = 2.5) -> dict:
    """
    EA-parity backtest: reproduces the MT5 EA's accept/reject logic
    bar-for-bar by delegating to ``ea_confirmations.compute_confirmations``.

    Synthetic SL/TP rule
    --------------------
    For every bar where ``agreed == 3 and trend_dir != 0`` we open a
    synthetic trade at the **next bar's open** (no lookahead — we only
    use information closed by the signal bar). Stops are anchored to the
    Wilder ATR computed by ``compute_confirmations`` at the signal bar:

        long  : SL = entry - sl_atr_mult * atr,  TP = entry + tp_atr_mult * atr
        short : SL = entry + sl_atr_mult * atr,  TP = entry - tp_atr_mult * atr

    Walk-forward fill
    -----------------
    From the entry bar onward we step bar-by-bar:
      * if the bar's high crosses TP first  -> win  (+tp_atr_mult R)
      * if the bar's low  crosses SL first  -> loss (-1 R)
      * if neither hits within ``MAX_HOLD_BARS = 96`` bars, mark-to-market
        on the last close (in R units relative to the SL distance).

    Why 96 bars? The live EA caps trade lifetime at roughly an 8-hour
    swing window; on M5 that's ``8 * 60 / 5 = 96`` bars. Matching that
    cap keeps backtested expectancy comparable to live PnL.

    Edge cases
    ----------
    * ATR is NaN during the warmup window — those signal rows are skipped.
    * If an entry bar is the last bar in the frame, the trade is dropped
      (no next-bar open available).
    * If both SL and TP fall inside the same bar's high/low range we
      conservatively treat the **SL** as hit first (worst-case fill).
    * Empty trade list returns a zero-filled dict so callers don't crash.

    Returns
    -------
    dict with keys: trades, wins, losses, expectancy_R, win_rate,
    gross_R, sharpe_proxy.
    """
    MAX_HOLD_BARS = 96

    if df is None or len(df) < 50:
        return {"trades": 0, "wins": 0, "losses": 0,
                "expectancy_R": 0.0, "win_rate": 0.0,
                "gross_R": 0.0, "sharpe_proxy": 0.0}

    conf = compute_confirmations(df)
    # Bars where the EA's three-of-three gate fires.
    fire_mask = (conf["agreed"] == 3) & (conf["trend_dir"] != 0)
    fire_idx  = np.where(fire_mask.values)[0]

    opens  = df["open"].values
    highs  = df["high"].values
    lows   = df["low"].values
    closes = df["close"].values
    atrs   = conf["atr"].values
    dirs   = conf["trend_dir"].values

    n = len(df)
    r_results: list[float] = []
    wins = losses = 0

    for i in fire_idx:
        # Need a next bar to fill on, plus a finite ATR for sizing.
        if i + 1 >= n:
            continue
        atr_now = atrs[i]
        if not np.isfinite(atr_now) or atr_now <= 0:
            continue

        direction = int(dirs[i])
        entry = float(opens[i + 1])
        sl_dist = sl_atr_mult * float(atr_now)
        tp_dist = tp_atr_mult * float(atr_now)

        if direction == 1:
            sl = entry - sl_dist
            tp = entry + tp_dist
        else:
            sl = entry + sl_dist
            tp = entry - tp_dist

        end = min(i + 1 + MAX_HOLD_BARS, n)
        outcome_r: Optional[float] = None
        for j in range(i + 1, end):
            hi = float(highs[j]); lo = float(lows[j])
            if direction == 1:
                hit_sl = lo <= sl
                hit_tp = hi >= tp
            else:
                hit_sl = hi >= sl
                hit_tp = lo <= tp
            # Worst-case: if both touched in the same bar, count as SL loss.
            if hit_sl and hit_tp:
                outcome_r = -1.0
                losses += 1
                break
            if hit_sl:
                outcome_r = -1.0
                losses += 1
                break
            if hit_tp:
                outcome_r = float(tp_atr_mult)
                wins += 1
                break

        if outcome_r is None:
            # Mark-to-market timeout in R units relative to SL distance.
            last_close = float(closes[end - 1])
            mtm = (last_close - entry) / sl_dist
            if direction == -1:
                mtm = -mtm
            outcome_r = float(mtm)
            if outcome_r >= 0:
                wins += 1
            else:
                losses += 1

        r_results.append(outcome_r)

    n_tr = len(r_results)
    if n_tr == 0:
        return {"trades": 0, "wins": 0, "losses": 0,
                "expectancy_R": 0.0, "win_rate": 0.0,
                "gross_R": 0.0, "sharpe_proxy": 0.0}

    arr = np.asarray(r_results, dtype=float)
    gross = float(arr.sum())
    expectancy = float(arr.mean())
    std = float(arr.std(ddof=0))
    sharpe = float(expectancy / std) if std > 0 else 0.0

    return {
        "trades": n_tr,
        "wins": int(wins),
        "losses": int(losses),
        "expectancy_R": expectancy,
        "win_rate": float(wins) / n_tr,
        "gross_R": gross,
        "sharpe_proxy": sharpe,
    }


def _load_ohlcv_csv(path: str) -> pd.DataFrame:
    """Helper: load an OHLCV CSV with optional ``time`` index column."""
    df = pd.read_csv(path)
    if "time" in df.columns:
        df["time"] = pd.to_datetime(df["time"], utc=True)
        df = df.set_index("time")
    return df[["open", "high", "low", "close", "volume"]].sort_index()


def main() -> int:
    import argparse

    # Subcommand-aware dispatch: legacy form ``backtest.py SYMBOL ...``
    # still works, but ``backtest.py ea_parity bars.csv`` is new.
    if len(sys.argv) >= 2 and sys.argv[1] == "ea_parity":
        ep = argparse.ArgumentParser(prog="backtest.py ea_parity")
        ep.add_argument("csv")
        ep.add_argument("--sl-atr-mult", type=float, default=1.5)
        ep.add_argument("--tp-atr-mult", type=float, default=2.5)
        args = ep.parse_args(sys.argv[2:])
        df = _load_ohlcv_csv(args.csv)
        result = run_ea_parity_backtest(df,
                                        sl_atr_mult=args.sl_atr_mult,
                                        tp_atr_mult=args.tp_atr_mult)
        print("EA-parity backtest")
        print("-" * 40)
        for k, v in result.items():
            if isinstance(v, float):
                print(f"{k:<14}: {v:+.4f}")
            else:
                print(f"{k:<14}: {v}")
        return 0 if result["trades"] > 0 and result["expectancy_R"] > 0 else 2

    p = argparse.ArgumentParser()
    p.add_argument("symbol")
    p.add_argument("--csv", default=None)
    p.add_argument("--min-votes", type=int, default=3)
    args = p.parse_args()
    rep = run_backtest(args.symbol, args.csv, args.min_votes)
    print(rep.format())
    return 0 if rep.is_viable() else 2


if __name__ == "__main__":
    raise SystemExit(main())
