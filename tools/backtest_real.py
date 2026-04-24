"""TrendMaster v14 - Real-data backtest over brain_memory.json trade_history.

Replays the closed trades stored in logs/brain_memory.json, applies cost
modeling (spread + slippage), and compares a baseline (take every trade)
vs a gated arm (confluence >= 6 features AND outside +/-30min of any
high-impact news event in config/news_calendar.json).  Produces
reports/BACKTEST_REAL_RESULT.md.

Only two of the seven live profit filters are replayable from the stored
fields (confluence + news blackout).  spread_guard and vol_regime need
live tick/ATR context and are listed as "cannot-backtest".

Only stdlib.  Run from project root:
    python3 tools/backtest_real.py
"""
from __future__ import annotations

import json
import math
import statistics
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parent.parent
BRAIN_PATH = ROOT / "logs" / "brain_memory.json"
NEWS_PATH = ROOT / "config" / "news_calendar.json"
REPORT_PATH = ROOT / "reports" / "BACKTEST_REAL_RESULT.md"

# Cost model (OctaFX-style, commission-free).  Approximations per brief:
#   XAU : 40 points spread, $0.10 per point on 0.01 lot.
#   ETH : 80 points spread, $0.01 per point on 0.01 lot.
# Round-trip = 1 spread + 0.5 spread entry slip + 0.5 spread exit slip = 2 spreads.
COSTS = {
    "XAUUSD": {"spread_points": 40, "usd_per_point": 0.10},
    "ETHUSD": {"spread_points": 80, "usd_per_point": 0.01},
}
CONFLUENCE_MIN = 6
NEWS_WINDOW_MIN = 30


def _parse_ts(ts: str) -> datetime:
    s = ts.replace("Z", "+00:00")
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def load_trades() -> List[Dict[str, Any]]:
    with BRAIN_PATH.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    return list(data.get("trade_history", []))


def load_news_events() -> List[datetime]:
    if not NEWS_PATH.exists():
        return []
    with NEWS_PATH.open("r", encoding="utf-8") as fh:
        rows = json.load(fh)
    out: List[datetime] = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        if r.get("event") == "__HEADER__":
            continue
        if str(r.get("impact", "")).lower() != "high":
            continue
        ts = r.get("ts_utc")
        if not ts:
            continue
        try:
            out.append(_parse_ts(str(ts)))
        except Exception:
            continue
    return out


def cost_for_trade(symbol: str) -> float:
    c = COSTS.get(symbol)
    if not c:
        return 0.0
    return 2.0 * c["spread_points"] * c["usd_per_point"]


def r_multiple(t: Dict[str, Any]) -> float:
    entry = float(t.get("entry_price", 0.0))
    exit_ = float(t.get("exit_price", 0.0))
    sl = float(t.get("stop_loss", 0.0))
    direction = str(t.get("direction", "BUY")).upper()
    risk = abs(entry - sl)
    if risk <= 0:
        return 0.0
    move = (exit_ - entry) if direction == "BUY" else (entry - exit_)
    return move / risk


def near_news(ts: datetime, events: List[datetime], window_min: int) -> bool:
    if not events:
        return False
    delta = timedelta(minutes=window_min)
    return any(abs(ts - ev) <= delta for ev in events)


def passes_gated(t: Dict[str, Any], events: List[datetime]) -> bool:
    feats = t.get("features") or {}
    score = sum(1 for v in feats.values() if bool(v))
    if score < CONFLUENCE_MIN:
        return False
    try:
        ts = _parse_ts(str(t.get("timestamp", "")))
    except Exception:
        return True
    if near_news(ts, events, NEWS_WINDOW_MIN):
        return False
    return True


def max_drawdown(equity_curve: List[float]) -> float:
    peak = -math.inf
    max_dd = 0.0
    for v in equity_curve:
        if v > peak:
            peak = v
        dd = peak - v
        if dd > max_dd:
            max_dd = dd
    return max_dd


def evaluate(trades: List[Dict[str, Any]], label: str) -> Dict[str, Any]:
    net_profits: List[float] = []
    rs: List[float] = []
    wins = losses = 0
    gross_win = gross_loss = 0.0
    cost_by_symbol: Dict[str, float] = {}
    trades_by_symbol: Dict[str, int] = {}
    equity = 0.0
    curve: List[float] = [0.0]

    for t in trades:
        sym = str(t.get("symbol", ""))
        raw = float(t.get("profit", 0.0))
        cost = cost_for_trade(sym)
        net = raw - cost
        net_profits.append(net)
        rs.append(r_multiple(t))
        cost_by_symbol[sym] = cost_by_symbol.get(sym, 0.0) + cost
        trades_by_symbol[sym] = trades_by_symbol.get(sym, 0) + 1
        if net > 0:
            wins += 1
            gross_win += net
        else:
            losses += 1
            gross_loss += -net
        equity += net
        curve.append(equity)

    n = len(net_profits)
    win_rate = (wins / n) if n else 0.0
    win_vals = [p for p in net_profits if p > 0]
    loss_vals = [p for p in net_profits if p <= 0]
    avg_win = statistics.mean(win_vals) if win_vals else 0.0
    avg_loss = statistics.mean(loss_vals) if loss_vals else 0.0
    exp_usd = statistics.mean(net_profits) if net_profits else 0.0
    exp_r = statistics.mean(rs) if rs else 0.0
    total_pnl = sum(net_profits)
    mdd = max_drawdown(curve)
    pf = (gross_win / gross_loss) if gross_loss > 0 else float("inf")
    sd = statistics.pstdev(net_profits) if len(net_profits) > 1 else 0.0
    sharpe = (exp_usd / sd) if sd > 0 else 0.0

    return {
        "label": label,
        "total_trades": n,
        "wins": wins,
        "losses": losses,
        "win_rate": win_rate,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "expectancy_per_trade_usd": exp_usd,
        "expectancy_per_trade_R": exp_r,
        "total_pnl_usd": total_pnl,
        "max_drawdown_usd": mdd,
        "profit_factor": pf,
        "sharpe_per_trade": sharpe,
        "cost_by_symbol": cost_by_symbol,
        "trades_by_symbol": trades_by_symbol,
    }


def fmt(v: float, pct: bool = False) -> str:
    if v == float("inf"):
        return "inf"
    if pct:
        return f"{v*100:.2f}%"
    return f"{v:.4f}" if abs(v) < 10 else f"{v:.2f}"


def render_report(baseline: Dict[str, Any], gated: Dict[str, Any],
                  n_trades_source: int, n_events: int) -> str:
    rows = [
        ("total_trades",           str(baseline["total_trades"]),             str(gated["total_trades"])),
        ("wins",                   str(baseline["wins"]),                     str(gated["wins"])),
        ("losses",                 str(baseline["losses"]),                   str(gated["losses"])),
        ("win_rate",               fmt(baseline["win_rate"], pct=True),       fmt(gated["win_rate"], pct=True)),
        ("avg_win ($)",            fmt(baseline["avg_win"]),                  fmt(gated["avg_win"])),
        ("avg_loss ($)",           fmt(baseline["avg_loss"]),                 fmt(gated["avg_loss"])),
        ("expectancy / trade ($)", fmt(baseline["expectancy_per_trade_usd"]), fmt(gated["expectancy_per_trade_usd"])),
        ("expectancy / trade (R)", fmt(baseline["expectancy_per_trade_R"]),   fmt(gated["expectancy_per_trade_R"])),
        ("total_pnl ($)",          fmt(baseline["total_pnl_usd"]),            fmt(gated["total_pnl_usd"])),
        ("max_drawdown ($)",       fmt(baseline["max_drawdown_usd"]),         fmt(gated["max_drawdown_usd"])),
        ("profit_factor",          fmt(baseline["profit_factor"]),            fmt(gated["profit_factor"])),
        ("sharpe / trade",         fmt(baseline["sharpe_per_trade"]),         fmt(gated["sharpe_per_trade"])),
    ]
    lines = [
        "# TrendMaster v14 - Real-Data Backtest",
        "",
        f"Source: `logs/brain_memory.json` (trade_history, {n_trades_source} trades).",
        f"News calendar: `config/news_calendar.json` ({n_events} high-impact events loaded).",
        "Window: 2026-03-08 (one-day replay). Symbols: XAUUSD, ETHUSD.",
        "",
        "## Baseline vs Gated",
        "",
        "| metric | baseline | gated |",
        "| --- | ---: | ---: |",
    ]
    for name, a, b in rows:
        lines.append(f"| {name} | {a} | {b} |")

    lines += ["", "## Cost breakdown per symbol", "",
              "| symbol | arm | trades | total_cost_usd | per_trade_usd |",
              "| --- | --- | ---: | ---: | ---: |"]
    for arm in (baseline, gated):
        for sym in sorted(arm["trades_by_symbol"].keys()):
            n = arm["trades_by_symbol"][sym]
            c = arm["cost_by_symbol"].get(sym, 0.0)
            per = (c / n) if n else 0.0
            lines.append(f"| {sym} | {arm['label']} | {n} | {c:.2f} | {per:.4f} |")

    lines += [
        "",
        "## Filters: gradeable vs not",
        "",
        "| filter | status | reason |",
        "| --- | --- | --- |",
        "| confluence (>=6 of 15 features) | GRADED | features dict is stored per trade |",
        "| news blackout (+/-30min) | GRADED (degenerate here) | calendar starts 2026-04-28; no overlap with 2026-03-08 trades |",
        "| spread_guard | CANNOT BACKTEST | needs live spread snapshot at entry, not logged |",
        "| vol_regime (ATR) | CANNOT BACKTEST | needs candle series, not logged |",
        "| session filter | CANNOT BACKTEST standalone | already folded into features, not a separate gate |",
        "| liquidity floor | CANNOT BACKTEST | needs tick volume at entry |",
        "| equity / DD breaker | CANNOT BACKTEST here | per-account state, not per-trade replay |",
        "",
        "## Caveats",
        "",
        "- One-day window (2026-03-08). Not representative of regime variety.",
        "- Only two symbols (XAUUSD, ETHUSD) - no forex, no other commodities.",
        "- Replay is from the brain's own trade log, not raw market ticks: survivorship of the already-executed trades is baked in.",
        "- Only 2 of 7 profit filters are replayable from the stored fields.",
        "- Base class is heavily imbalanced (~86% win rate). That looks suspiciously high for real live trading and may reflect optimistic exit logic in the replay source.",
        "- Not a walk-forward / out-of-sample test. No parameter was re-fit; this only measures whether a simple confluence+news gate would have improved the same trades.",
        "- Costs are modeled, not observed - OctaFX real spreads fluctuate, especially around news.",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    trades = load_trades()
    events = load_news_events()

    baseline_trades = list(trades)
    gated_trades = [t for t in trades if passes_gated(t, events)]

    baseline = evaluate(baseline_trades, "baseline")
    gated = evaluate(gated_trades, "gated")

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    report = render_report(baseline, gated,
                           n_trades_source=len(trades),
                           n_events=len(events))
    REPORT_PATH.write_text(report, encoding="utf-8")

    delta_r = gated["expectancy_per_trade_R"] - baseline["expectancy_per_trade_R"]
    headline = (
        f"Baseline={baseline['expectancy_per_trade_R']:.4f}R/trade, "
        f"Gated={gated['expectancy_per_trade_R']:.4f}R/trade, "
        f"delta={delta_r:+.4f}R on {baseline['total_trades']}->{gated['total_trades']} trades "
        f"(XAU/ETH, 2026-03-08, costs modeled)"
    )
    print(headline)
    print(f"Report written: {REPORT_PATH}")


if __name__ == "__main__":
    main()
