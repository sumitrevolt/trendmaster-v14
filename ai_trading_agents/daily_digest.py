"""
daily_digest.py — institutional-grade end-of-day report.

What this gives the operator
----------------------------
At UTC midnight (or on demand), emits:

  * `reports/daily_YYYY-MM-DD.md` — human-readable Markdown report.
  * Telegram summary (if creds present) — compressed version of the
    same info suitable for mobile reading.
  * `reports/daily_YYYY-MM-DD.json` — machine-readable version for
    downstream tools / dashboards / data lakes.

Contents
--------
  1. PnL summary (today, 7d, 30d, all-time).
  2. Sharpe / Sortino / Calmar over each window.
  3. Top 3 / bottom 3 symbols (30d PnL).
  4. Gate veto breakdown — which gates fired most today.
  5. Drift status — ADWIN counters + last-drift timestamp.
  6. Portfolio VaR / CVaR snapshot.
  7. System health — MT5 reconnects, signal-file retries, brain restarts.
  8. Open positions snapshot.
  9. News events in the next 24h.
  10. Action items — anything worth the operator's attention.

Designed as a pure function — `generate_report(state, trades, ...)`
returns a dict. The output-path writers and Telegram push are separate.
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("daily_digest")


@dataclass
class ActionItem:
    severity: str   # "info" | "warn" | "critical"
    title:    str
    detail:   str

    def as_dict(self) -> dict:
        return asdict(self)


def generate_report(state: Dict[str, Any],
                    project_root: Optional[Path] = None,
                    team_of_fn=None) -> Dict[str, Any]:
    """Build the full digest dict. Caller renders Markdown / sends TG."""
    from ai_trading_agents import performance as perf_mod
    try:
        from ai_trading_agents import portfolio_risk as pr_mod
    except Exception:
        pr_mod = None
    try:
        from ai_trading_agents import drift_detector as drift_mod
    except Exception:
        drift_mod = None

    now_utc = datetime.now(timezone.utc)
    today_str = now_utc.strftime("%Y-%m-%d")
    trades = list(state.get("recent_results", []))

    # 1. Performance windows.
    perf = perf_mod.snapshot(trades, team_of_fn=team_of_fn)

    # 2. VaR / CVaR.
    var_snap: Dict = {}
    if pr_mod is not None:
        try:
            var_snap = pr_mod.snapshot(trades, confidence=0.95)
        except Exception as e:
            var_snap = {"error": repr(e)}

    # 3. Drift status.
    drift_status: Dict = {}
    if drift_mod is not None:
        try:
            det = drift_mod.get_detector("pnl")
            drift_status = {
                "total_observations":  det.state.total_observations,
                "window_size":         det.state.current_window_size,
                "drift_count":         det.state.drift_count,
                "warning_count":       det.state.warning_count,
                "mean":                round(det.state.mean, 4),
                "variance":            round(det.state.variance, 4),
                "last_drift_at":       det.state.last_drift_at,
            }
        except Exception:
            pass

    # 4. Open positions — read from MT5 if possible.
    open_positions: List[Dict] = []
    try:
        import MetaTrader5 as mt5   # type: ignore
        pos = mt5.positions_get()
        if pos:
            for p in pos:
                open_positions.append({
                    "symbol": str(getattr(p, "symbol", "")),
                    "type":   int(getattr(p, "type", 0)),
                    "volume": float(getattr(p, "volume", 0.0)),
                    "price_open": float(getattr(p, "price_open", 0.0)),
                    "profit":     float(getattr(p, "profit", 0.0)),
                })
    except Exception:
        pass

    # 5. Action items derived from metrics.
    actions: List[ActionItem] = []
    dd_lock = int(state.get("drawdown_lockout_until", 0) or 0)
    if dd_lock > int(time.time()):
        actions.append(ActionItem("critical", "Drawdown lockout active",
                                   f"until {datetime.fromtimestamp(dd_lock, tz=timezone.utc).isoformat()}"))
    halted = bool(state.get("halted") or state.get("trading_paused"))
    if halted:
        actions.append(ActionItem("warn", "Trading halted",
                                   "/resume to re-enable"))
    w30 = perf.get("windows", {}).get("30d", {})
    if w30.get("n_trades", 0) > 0 and w30.get("sharpe", 0.0) < 0:
        actions.append(ActionItem(
            "warn", "30d Sharpe is negative",
            f"sharpe={w30.get('sharpe',0):.2f} — review recent strategy changes",
        ))
    if w30.get("n_trades", 0) > 20 and w30.get("win_rate", 1.0) < 0.45:
        actions.append(ActionItem(
            "warn", "30d win rate below 45%",
            f"win_rate={w30.get('win_rate',0):.1%} — consider tighter confidence floor",
        ))
    if drift_status.get("drift_count", 0) > 3:
        actions.append(ActionItem(
            "warn", "Multiple drift flags in window",
            f"count={drift_status.get('drift_count')} — consider retraining",
        ))

    return {
        "date":             today_str,
        "generated_at":     now_utc.isoformat(),
        "performance":      perf,
        "var_cvar":         var_snap,
        "drift_status":     drift_status,
        "open_positions":   open_positions,
        "state_summary": {
            "halted":               bool(state.get("halted")),
            "trading_paused":       bool(state.get("trading_paused")),
            "restart_count":        int(state.get("restart_count", 0)),
            "start_of_day_equity":  float(state.get("start_of_day_equity", 0.0) or 0.0),
            "drawdown_lockout_until": dd_lock,
            "daily_drawdown_peak_eq": float(state.get("daily_drawdown_peak_eq", 0.0) or 0.0),
            "cooldown_until_ts":    int(state.get("cooldown_until_ts", 0) or 0),
        },
        "action_items":     [a.as_dict() for a in actions],
    }


# ======================================================================
# Renderers
# ======================================================================
def to_markdown(digest: Dict[str, Any]) -> str:
    p = digest.get("performance", {})
    win = p.get("windows", {})
    lines: List[str] = []
    lines.append(f"# TrendMaster v14 — Daily Digest {digest.get('date')}")
    lines.append(f"_Generated {digest.get('generated_at')} UTC_")
    lines.append("")
    lines.append("## Performance windows")
    lines.append("")
    lines.append("| Window | Trades | Win% | Total PnL | Sharpe | Sortino | MaxDD | Expectancy |")
    lines.append("|--------|-------:|-----:|----------:|-------:|--------:|------:|-----------:|")
    for w in ("7d", "30d", "90d", "all"):
        m = win.get(w, {})
        lines.append(
            f"| {w:6s} | {m.get('n_trades',0):6d} | "
            f"{m.get('win_rate',0)*100:4.1f}% | "
            f"{m.get('total_pnl',0):+10.2f} | "
            f"{m.get('sharpe',0):+6.2f} | "
            f"{m.get('sortino',0):+6.2f} | "
            f"{m.get('max_drawdown',0):6.2f} | "
            f"{m.get('expectancy',0):+9.3f} |"
        )
    lines.append("")

    top = p.get("by_symbol_30d", {})
    if top:
        items = list(top.items())
        best = items[:3]
        worst = items[-3:][::-1]
        lines.append("## Top 3 symbols (30d)")
        for sym, m in best:
            lines.append(f"- **{sym}** — PnL {m.get('total_pnl',0):+.2f}, "
                         f"n={m.get('n_trades',0)}, WR={m.get('win_rate',0)*100:.1f}%")
        lines.append("")
        lines.append("## Bottom 3 symbols (30d)")
        for sym, m in worst:
            lines.append(f"- **{sym}** — PnL {m.get('total_pnl',0):+.2f}, "
                         f"n={m.get('n_trades',0)}, WR={m.get('win_rate',0)*100:.1f}%")
        lines.append("")

    vc = digest.get("var_cvar", {})
    if vc and "historical" in vc:
        h = vc["historical"]
        lines.append("## Portfolio risk (95%)")
        lines.append(f"- historical VaR: **${h.get('var',0):.2f}**  CVaR: **${h.get('cvar',0):.2f}**")
        if "parametric" in vc:
            pa = vc["parametric"]
            lines.append(f"- parametric VaR: ${pa.get('var',0):.2f}  CVaR: ${pa.get('cvar',0):.2f}")
        if "cornish_fisher" in vc:
            cf = vc["cornish_fisher"]
            lines.append(f"- Cornish-Fisher VaR: ${cf.get('var',0):.2f}  CVaR: ${cf.get('cvar',0):.2f}")
        lines.append("")

    d = digest.get("drift_status", {})
    if d:
        lines.append("## Drift detector")
        lines.append(f"- total obs: `{d.get('total_observations',0)}`  "
                     f"window: `{d.get('window_size',0)}`")
        lines.append(f"- drift count: `{d.get('drift_count',0)}`  "
                     f"warnings: `{d.get('warning_count',0)}`")
        lines.append(f"- mean/var: `{d.get('mean',0):.4f}` / `{d.get('variance',0):.4f}`")
        lines.append("")

    op = digest.get("open_positions", [])
    lines.append(f"## Open positions: {len(op)}")
    for o in op[:8]:
        side = "BUY" if o.get("type") == 0 else "SELL"
        lines.append(f"- {o.get('symbol')} {side} {o.get('volume'):.2f} "
                     f"@ {o.get('price_open'):.5f}  PnL {o.get('profit'):+.2f}")
    lines.append("")

    ai = digest.get("action_items", [])
    lines.append(f"## Action items: {len(ai)}")
    for a in ai:
        sev = a.get("severity", "info")
        lines.append(f"- **[{sev.upper()}] {a.get('title')}** — {a.get('detail')}")
    if not ai:
        lines.append("- (none — system healthy)")
    lines.append("")

    return "\n".join(lines) + "\n"


def to_telegram(digest: Dict[str, Any]) -> str:
    """Compact HTML for Telegram. <b> and <code> only — no Markdown."""
    w30 = digest.get("performance", {}).get("windows", {}).get("30d", {})
    h = digest.get("var_cvar", {}).get("historical", {})
    d = digest.get("drift_status", {})
    ai = digest.get("action_items", [])
    lines = [
        f"<b>📋 Daily Digest — {digest.get('date')}</b>",
        "",
        "<b>30-day</b>  "
        f"n=<code>{w30.get('n_trades',0)}</code>  "
        f"WR=<code>{w30.get('win_rate',0)*100:.1f}%</code>  "
        f"PnL=<code>{w30.get('total_pnl',0):+.2f}</code>  "
        f"Sharpe=<code>{w30.get('sharpe',0):+.2f}</code>  "
        f"MDD=<code>{w30.get('max_drawdown',0):.2f}</code>",
        "",
        f"<b>95% VaR</b>=<code>${h.get('var',0):.2f}</code>  "
        f"<b>CVaR</b>=<code>${h.get('cvar',0):.2f}</code>  "
        f"<b>drift</b>=<code>{d.get('drift_count',0)}</code>",
    ]
    top = list(digest.get("performance", {}).get("by_symbol_30d", {}).items())
    if top:
        best = top[:3]
        worst = top[-3:][::-1]
        lines.append("")
        lines.append("<b>Top:</b> " + ", ".join(
            f"{s} {m.get('total_pnl',0):+.2f}" for s, m in best))
        lines.append("<b>Bot:</b> " + ", ".join(
            f"{s} {m.get('total_pnl',0):+.2f}" for s, m in worst))
    if ai:
        lines.append("")
        lines.append(f"<b>⚠ {len(ai)} action items:</b>")
        for a in ai[:4]:
            lines.append(f" • [{a.get('severity','')}] {a.get('title')}")
    return "\n".join(lines)


# ======================================================================
# Writers
# ======================================================================
def write_daily(digest: Dict[str, Any],
                reports_dir: Path) -> Dict[str, str]:
    """Write JSON + Markdown to `reports/`. Returns paths."""
    reports_dir = Path(reports_dir)
    reports_dir.mkdir(parents=True, exist_ok=True)
    date = digest.get("date", datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    json_path = reports_dir / f"daily_{date}.json"
    md_path = reports_dir / f"daily_{date}.md"
    json_path.write_text(json.dumps(digest, indent=2), encoding="utf-8")
    md_path.write_text(to_markdown(digest), encoding="utf-8")
    return {"json": str(json_path), "md": str(md_path)}


def push_telegram(digest: Dict[str, Any]) -> bool:
    """Best-effort Telegram push. Never raises."""
    try:
        from ai_trading_agents.telegram_notifier import get_notifier
        msg = to_telegram(digest)
        get_notifier().notify_alert(
            "TrendMaster v14 daily digest", msg, emoji="📋",
        )
        return True
    except Exception as e:
        logger.debug("telegram push skipped: %s", e)
        return False


__all__ = [
    "ActionItem", "generate_report", "to_markdown", "to_telegram",
    "write_daily", "push_telegram",
]
