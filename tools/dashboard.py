r"""
TrendMaster v14 — live dashboard
Runs on http://localhost:8000/

- Reads per-symbol signal files, brain state (PnL, restart count), MT5
  account, open positions and brain log tails
- Self-refreshing single-page HTML (JS polls /api/state every 1 s, plus
  a static `<meta http-equiv="refresh" content="5">` ops view at /)
- Zero external deps beyond FastAPI + uvicorn (+ MetaTrader5 which the
  brain already needs)

Routes
------
  /                — HTML ops view (5 s auto-refresh)
  /api/state       — full JSON dump (legacy, used by inline JS poller)
  /signals         — JSON array of {symbol, direction, confidence, ts}
  /pnl             — JSON daily PnL block from brain_state.json + live equity
  /restarts        — JSON {restart_count, last_started_at, last_saved_at}
  /healthz         — supervisor probe (unchanged)

Start:  python tools\dashboard.py
"""

from __future__ import annotations
import json, os, sys, time, datetime as dt
from pathlib import Path
from typing import Any, Dict, List, Optional

# Ensure the project root is on sys.path BEFORE any project imports. When
# launched as `python tools/dashboard.py`, Python only puts `tools/` on the
# path, so `from config import settings` would silently fail and we'd lose
# the 21-symbol TRADING_PAIRS list — leaving /signals showing only XAUUSD.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
import uvicorn

try:
    import MetaTrader5 as mt5

    HAVE_MT5 = True
except Exception:
    HAVE_MT5 = False

# Project imports — pull symbol list + state schema straight from source so
# the dashboard can never drift from the brain. The sys.path nudge above
# guarantees these resolve regardless of how the script was launched.
try:
    from config import settings as _settings

    TRADING_PAIRS: List[str] = list(getattr(_settings, "TRADING_PAIRS", []) or [])
    _TM_CFG: Dict[str, Any] = dict(getattr(_settings, "TRENDMASTER_V14", {}) or {})
except Exception as _e:
    print(f"[dashboard] WARN: failed to import config.settings: {_e!r}")
    TRADING_PAIRS = []
    _TM_CFG = {}

try:
    from ai_trading_agents.state_store import StateStore

    _STATE_STORE: Optional[StateStore] = StateStore()
except Exception:
    _STATE_STORE = None

# pnl_of() normalises both legacy float entries AND new dict entries
# (added by trade_tracker.py in Phase G1). Without it, /pnl undercounts
# wins/losses to zero on any post-G1 state file.
try:
    from ai_trading_agents.trade_tracker import pnl_of as _pnl_of  # type: ignore
except Exception:

    def _pnl_of(entry):  # fallback shim — keep dashboard bootable
        if entry is None:
            return 0.0
        if isinstance(entry, (int, float)):
            return float(entry)
        if isinstance(entry, dict):
            for k in ("pnl", "r_mult", "r"):
                if k in entry and entry[k] is not None:
                    try:
                        return float(entry[k])
                    except (TypeError, ValueError):
                        pass
        return 0.0


ROOT = Path(__file__).resolve().parent.parent
BRAIN_ERR = ROOT / "logs" / "trend_master_brain.err"
BRAIN_LOG = ROOT / "logs" / "trend_master_brain.log"

TERMINAL_ID = "D0E8209F77C8CF37AD8BF550E51FF075"
PRIMARY_SYMBOL = _TM_CFG.get("primary_symbol", "XAUUSD")
SIG_FILE_NAME = _TM_CFG.get("signal_file", "trendmaster_signals.json")
USE_COMMON = bool(_TM_CFG.get("use_common_folder", False))

# Legacy single-symbol signal path (still used by /api/state + /healthz).
SIGNAL_FILE = Path(
    os.environ.get(
        "TM_SIGNAL_FILE",
        rf"C:\Users\Ratanshila\AppData\Roaming\MetaQuotes\Terminal\{TERMINAL_ID}\MQL5\Files\trendmaster_signals.json",
    )
)
MT5_LOG_DIR = Path(rf"C:\Users\Ratanshila\AppData\Roaming\MetaQuotes\Terminal\{TERMINAL_ID}\MQL5\Logs")


# Candidate base directories where per-symbol signal JSON might live.
# Mirrors `_resolve_signal_path` in trend_master_brain.py: first the live
# MT5 Files dir (queried at runtime if MT5 available), then the hard-coded
# terminal path used by SIGNAL_FILE, then the project root fallback.
def _candidate_signal_dirs() -> List[Path]:
    dirs: List[Path] = []
    if HAVE_MT5:
        try:
            if mt5.initialize():
                try:
                    info = mt5.terminal_info()
                    if info is not None:
                        if USE_COMMON:
                            dirs.append(Path(info.commondata_path) / "Files")
                        else:
                            dirs.append(Path(info.data_path) / "MQL5" / "Files")
                finally:
                    mt5.shutdown()
        except Exception:
            pass
    # Hard-coded fallback (matches SIGNAL_FILE parent).
    dirs.append(SIGNAL_FILE.parent)
    # Project root fallback.
    dirs.append(ROOT)
    # Dedup while preserving order.
    seen, out = set(), []
    for d in dirs:
        s = str(d)
        if s not in seen:
            seen.add(s)
            out.append(d)
    return out


def _signal_filename_for(symbol: str) -> str:
    """Mirror `_signal_filename_for` in the brain — primary symbol keeps the
    legacy filename, others get `<stem>_<SYMBOL><suffix>`."""
    if symbol == PRIMARY_SYMBOL:
        return SIG_FILE_NAME
    p = Path(SIG_FILE_NAME)
    return f"{p.stem}_{symbol}{p.suffix or '.json'}"


def _read_per_symbol_signal(symbol: str) -> Dict[str, Any]:
    """Walk candidate dirs looking for the per-symbol signal file. Returns
    a dict with at least {symbol, direction, confidence, ts} or sentinel."""
    name = _signal_filename_for(symbol)
    for base in _candidate_signal_dirs():
        f = base / name
        try:
            if not f.exists():
                continue
            data = json.loads(f.read_text())
            mtime = dt.datetime.fromtimestamp(f.stat().st_mtime)
            return {
                "symbol": data.get("symbol", symbol),
                "direction": data.get("direction", "NONE"),
                "confidence": data.get("confidence"),
                "ts": data.get("ts"),
                "model": data.get("model"),
                "file": str(f),
                "age_sec": round((dt.datetime.now() - mtime).total_seconds(), 1),
            }
        except Exception:
            # Try next candidate dir; missing/corrupt file is non-fatal.
            continue
    return {
        "symbol": symbol,
        "direction": "—",
        "confidence": None,
        "ts": None,
        "model": None,
        "file": None,
        "age_sec": None,
    }


app = FastAPI(title="TrendMaster v14")


def _read_signal() -> Dict[str, Any]:
    try:
        data = json.loads(SIGNAL_FILE.read_text())
        mtime = dt.datetime.fromtimestamp(SIGNAL_FILE.stat().st_mtime)
        data["_file_age_sec"] = round((dt.datetime.now() - mtime).total_seconds(), 1)
        data["_ok"] = True
    except Exception as e:
        data = {"_ok": False, "_err": str(e)}
    return data


def _read_brain_state() -> Dict[str, Any]:
    """Best-effort read of brain_state.json via the shared StateStore. On
    any failure returns an empty dict — callers must tolerate missing keys."""
    if _STATE_STORE is None:
        return {}
    try:
        return _STATE_STORE.load() or {}
    except Exception:
        return {}


def _read_brain_tail(path: Path, n: int = 25) -> list[str]:
    if not path.exists():
        return [f"(no file: {path.name})"]
    try:
        lines = path.read_text(errors="ignore").splitlines()
        return lines[-n:]
    except Exception as e:
        return [f"(read err: {e})"]


def _read_mt5_log_tail(n: int = 25) -> list[str]:
    today = dt.datetime.now().strftime("%Y%m%d")
    f = MT5_LOG_DIR / f"{today}.log"
    if not f.exists():
        return ["(no MT5 log for today yet)"]
    try:
        text = (
            f.read_text(errors="ignore", encoding="utf-16")
            if f.read_bytes()[:2] == b"\xff\xfe"
            else f.read_text(errors="ignore")
        )
    except Exception:
        text = f.read_text(errors="ignore")
    hits = [ln for ln in text.splitlines() if "TMv14" in ln or "AI_SUPERBB" in ln]
    return hits[-n:]


def _live_equity() -> Optional[float]:
    """Best-effort live equity lookup. Returns None if MT5 isn't available
    or the connection fails — caller renders '—'."""
    if not HAVE_MT5:
        return None
    try:
        if not mt5.initialize():
            return None
        try:
            acc = mt5.account_info()
            return float(getattr(acc, "equity", 0.0)) if acc else None
        finally:
            mt5.shutdown()
    except Exception:
        return None


def _mt5_state() -> Dict[str, Any]:
    if not HAVE_MT5:
        return {"_ok": False, "_err": "MetaTrader5 module not installed"}
    # Fresh connect each poll — dashboard is low-freq
    if not mt5.initialize():
        return {"_ok": False, "_err": f"initialize failed: {mt5.last_error()}"}
    try:
        acc = mt5.account_info()
        term = mt5.terminal_info()
        positions = mt5.positions_get(symbol="XAUUSD") or []
        tick = mt5.symbol_info_tick("XAUUSD")
        out = {
            "_ok": True,
            "login": getattr(acc, "login", None),
            "server": getattr(acc, "server", None),
            "balance": getattr(acc, "balance", 0.0),
            "equity": getattr(acc, "equity", 0.0),
            "profit": getattr(acc, "profit", 0.0),
            "margin_free": getattr(acc, "margin_free", 0.0),
            "trade_allowed": getattr(term, "trade_allowed", False),
            "connected": getattr(term, "connected", False),
            "symbol_bid": getattr(tick, "bid", 0.0) if tick else 0.0,
            "symbol_ask": getattr(tick, "ask", 0.0) if tick else 0.0,
            "positions": [
                {
                    "ticket": p.ticket,
                    "type": "BUY" if p.type == 0 else "SELL",
                    "volume": p.volume,
                    "price_open": p.price_open,
                    "price_current": p.price_current,
                    "sl": p.sl,
                    "tp": p.tp,
                    "profit": p.profit,
                    "magic": p.magic,
                    "comment": p.comment,
                }
                for p in positions
            ],
        }
    finally:
        mt5.shutdown()
    return out


# ─── new ops endpoints ──────────────────────────────────────────────────────
def _signals_payload() -> List[Dict[str, Any]]:
    syms = TRADING_PAIRS or [PRIMARY_SYMBOL]
    return [_read_per_symbol_signal(s) for s in syms]


def _pnl_payload() -> Dict[str, Any]:
    state = _read_brain_state()
    equity_now = _live_equity()
    equity_open = state.get("start_of_day_equity")
    try:
        equity_open_f = float(equity_open) if equity_open is not None else None
    except Exception:
        equity_open_f = None
    pnl: Optional[float] = None
    pnl_pct: Optional[float] = None
    if equity_open_f is not None and equity_now is not None and equity_open_f > 0:
        pnl = round(equity_now - equity_open_f, 2)
        pnl_pct = round((equity_now / equity_open_f - 1.0) * 100.0, 3)
    elif equity_open_f is not None:
        # No live equity — fall back to persisted realized PnL.
        try:
            pnl = float(state.get("daily_pnl_close", 0.0))
        except Exception:
            pnl = None

    recent = list(state.get("recent_results", []) or [])
    # Filter to today's UTC date (matches the brain's _build_pnl_message).
    # Only dict entries from trade_tracker carry a real `ts`. Legacy float
    # entries (pre-Phase-G1) have no timestamp, so we cannot prove they
    # belong to today — exclude them from today's tally to avoid inflating
    # the count. They still appear in the rolling window for loss-streak
    # calc but not in the "today" KPI.
    today_utc = dt.datetime.utcnow().strftime("%Y-%m-%d")

    def _is_today(r) -> bool:
        if not isinstance(r, dict):
            return False  # legacy float — unknown date, don't count as today
        try:
            ts = int(r.get("ts", 0) or 0)
        except (TypeError, ValueError):
            return False
        if ts <= 0:
            return False
        return dt.datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d") == today_utc

    todays = [r for r in recent if _is_today(r)]
    trades_today = len(todays)
    wins_today = sum(1 for r in todays if _pnl_of(r) > 0)
    losses_today = sum(1 for r in todays if _pnl_of(r) < 0)

    return {
        "date": state.get("start_of_day_date") or dt.date.today().isoformat(),
        "equity_open": equity_open_f,
        "equity_now": equity_now,
        "pnl": pnl,
        "pnl_pct": pnl_pct,
        "daily_pnl_close": state.get("daily_pnl_close", 0.0),
        "trades_today": trades_today,
        "wins_today": wins_today,
        "losses_today": losses_today,
        "restart_count": int(state.get("restart_count", 0) or 0),
    }


def _restarts_payload() -> Dict[str, Any]:
    state = _read_brain_state()
    # Phase G3/G4: surface kill-switch + drawdown-lockout so the dashboard
    # makes the brain's true execution state visible (not just signal age).
    dd_until = int(state.get("drawdown_lockout_until", 0) or 0)
    dd_active = dd_until > int(time.time())
    return {
        "restart_count": int(state.get("restart_count", 0) or 0),
        "last_started_at": int(state.get("last_started_at", 0) or 0),
        "last_saved_at": int(state.get("last_saved_at", 0) or 0),
        "trading_paused": bool(state.get("trading_paused", False)),
        "trading_paused_at": int(state.get("trading_paused_at", 0) or 0),
        "drawdown_lockout_until": dd_until,
        "drawdown_lockout_active": dd_active,
        "daily_drawdown_peak_eq": float(state.get("daily_drawdown_peak_eq", 0.0) or 0.0),
    }


@app.get("/signals")
def signals() -> JSONResponse:
    return JSONResponse(_signals_payload())


@app.get("/pnl")
def pnl() -> JSONResponse:
    return JSONResponse(_pnl_payload())


@app.get("/restarts")
def restarts() -> JSONResponse:
    return JSONResponse(_restarts_payload())


@app.get("/api/state")
def api_state() -> JSONResponse:
    return JSONResponse(
        {
            "ts": dt.datetime.now().isoformat(timespec="seconds"),
            "signal": _read_signal(),
            "mt5": _mt5_state(),
            "brain_tail": _read_brain_tail(BRAIN_ERR, 20),
            "ea_tail": _read_mt5_log_tail(20),
        }
    )


# [enhancement 2026-04-23 R4 — operator grade] /performance route —
# returns perf snapshot JSON. Lightweight; reads brain_state.json.
@app.get("/performance")
def performance_route() -> JSONResponse:
    try:
        from ai_trading_agents import performance as _p
        from ai_trading_agents.state_store import StateStore as _SS

        state = _SS().load()
        trades = state.get("recent_results", [])
        snap = _p.snapshot(trades)
        return JSONResponse(snap)
    except Exception as e:
        return JSONResponse({"error": repr(e)}, status_code=200)


# /digest — returns today's digest (also writes the file when called).
@app.get("/digest")
def digest_route() -> JSONResponse:
    try:
        from ai_trading_agents import daily_digest as _dd
        from ai_trading_agents.state_store import StateStore as _SS

        state = _SS().load()
        d = _dd.generate_report(state)
        return JSONResponse(d)
    except Exception as e:
        return JSONResponse({"error": repr(e)}, status_code=200)


# [enhancement 2026-04-23] Prometheus /metrics endpoint — gated on
# settings.METRICS.enabled so pre-config installs return a 404-ish
# short message rather than silently leaking an empty scrape.
@app.get("/metrics")
def metrics_route():
    from fastapi.responses import PlainTextResponse

    try:
        from ai_trading_agents import metrics as _tm_metrics

        _metrics_enabled = getattr(_settings, "METRICS", {}).get("enabled", False)
        if not _metrics_enabled:
            return PlainTextResponse(
                "# metrics disabled (set METRICS.enabled=True in config/settings.py)\n",
                status_code=200,
                media_type="text/plain; version=0.0.4",
            )
        return PlainTextResponse(
            _tm_metrics.render_text(),
            media_type="text/plain; version=0.0.4",
        )
    except Exception as e:
        return PlainTextResponse(
            f"# metrics collection error: {e!r}\n",
            status_code=200,
            media_type="text/plain; version=0.0.4",
        )


@app.get("/healthz")
def healthz() -> JSONResponse:
    """Liveness + readiness probe for tools/supervisor.py and `python main.py health`."""
    sig = _read_signal()
    signal_ok = bool(sig.get("_ok")) and sig.get("_file_age_sec", 999) < 60
    brain_log_age = None
    if BRAIN_ERR.exists():
        brain_log_age = round(time.time() - BRAIN_ERR.stat().st_mtime, 1)
    status = "ok" if signal_ok else "degraded"
    code = 200 if signal_ok else 503
    return JSONResponse(
        {
            "status": status,
            "signal_ok": signal_ok,
            "signal_age_sec": sig.get("_file_age_sec"),
            "brain_log_age_sec": brain_log_age,
        },
        status_code=code,
    )


# ─── HTML helpers ───────────────────────────────────────────────────────────
def _fmt_ts(epoch: Any) -> str:
    try:
        e = int(epoch)
        if e <= 0:
            return "—"
        return dt.datetime.fromtimestamp(e).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return "—"


def _fmt_num(v: Any, digits: int = 2) -> str:
    if v is None:
        return "—"
    try:
        return f"{float(v):.{digits}f}"
    except Exception:
        return str(v)


def _render_ops_html() -> str:
    sigs = _signals_payload()
    pnl_d = _pnl_payload()
    rst = _restarts_payload()

    # Signals table
    sig_rows = []
    for s in sigs:
        d = s.get("direction") or "—"
        cls = "ok" if d == "BUY" else ("bad" if d == "SELL" else "warn")
        sig_rows.append(
            f"<tr><td>{s.get('symbol', '—')}</td>"
            f"<td class='{cls}'>{d}</td>"
            f"<td>{_fmt_num(s.get('confidence'), 3)}</td>"
            f"<td>{_fmt_ts(s.get('ts'))}</td>"
            f"<td>{_fmt_num(s.get('age_sec'), 1)}</td></tr>"
        )
    sig_html = "".join(sig_rows) or "<tr><td colspan=5 class='warn'>no signal files yet</td></tr>"

    # PnL panel
    pnl_val = pnl_d.get("pnl")
    pnl_cls = (
        "ok"
        if isinstance(pnl_val, (int, float)) and pnl_val > 0
        else ("bad" if isinstance(pnl_val, (int, float)) and pnl_val < 0 else "")
    )
    pnl_html = (
        f"<tr><td class='k'>date</td><td>{pnl_d.get('date')}</td></tr>"
        f"<tr><td class='k'>equity open</td><td>{_fmt_num(pnl_d.get('equity_open'))}</td></tr>"
        f"<tr><td class='k'>equity now</td><td>{_fmt_num(pnl_d.get('equity_now'))}</td></tr>"
        f"<tr><td class='k'>P/L</td><td class='{pnl_cls}'>{_fmt_num(pnl_val)} "
        f"({_fmt_num(pnl_d.get('pnl_pct'), 3)}%)</td></tr>"
        f"<tr><td class='k'>realized close</td><td>{_fmt_num(pnl_d.get('daily_pnl_close'))}</td></tr>"
        f"<tr><td class='k'>trades / wins / losses</td>"
        f"<td>{pnl_d.get('trades_today')} / "
        f"<span class='ok'>{pnl_d.get('wins_today')}</span> / "
        f"<span class='bad'>{pnl_d.get('losses_today')}</span></td></tr>"
        f"<tr><td class='k'>restart count</td><td>{pnl_d.get('restart_count')}</td></tr>"
    )

    # Restart + kill-switch panel
    paused = bool(rst.get("trading_paused"))
    dd_active = bool(rst.get("drawdown_lockout_active"))
    halt_label = "<span class='bad'>HALTED via /halt</span>" if paused else "<span class='ok'>LIVE</span>"
    dd_label = (
        f"<span class='bad'>LOCKED until {_fmt_ts(rst.get('drawdown_lockout_until'))}</span>"
        if dd_active
        else "<span class='ok'>clear</span>"
    )
    rst_html = (
        f"<tr><td class='k'>trading state</td><td>{halt_label}</td></tr>"
        f"<tr><td class='k'>drawdown lockout</td><td>{dd_label}</td></tr>"
        f"<tr><td class='k'>peak equity (today)</td>"
        f"<td>{_fmt_num(rst.get('daily_drawdown_peak_eq'))}</td></tr>"
        f"<tr><td class='k'>restart_count</td><td>{rst.get('restart_count')}</td></tr>"
        f"<tr><td class='k'>last_started_at</td><td>{_fmt_ts(rst.get('last_started_at'))}</td></tr>"
        f"<tr><td class='k'>last_saved_at</td><td>{_fmt_ts(rst.get('last_saved_at'))}</td></tr>"
    )

    return _OPS_HTML.format(
        ts=dt.datetime.now().isoformat(timespec="seconds"),
        sig_rows=sig_html,
        pnl_rows=pnl_html,
        restart_rows=rst_html,
    )


@app.get("/", response_class=HTMLResponse)
def home() -> str:
    return _render_ops_html()


_OPS_HTML = r"""<!doctype html>
<html><head><meta charset="utf-8">
<meta http-equiv="refresh" content="5">
<title>TrendMaster v14 ops</title>
<style>
 body{{background:#0b1020;color:#d6e0ff;font:13px/1.45 ui-monospace,Consolas,monospace;margin:0;padding:16px}}
 h1{{margin:0 0 12px 0;color:#ffd84a;font:600 16px ui-monospace}}
 h2{{margin:0 0 6px 0;color:#8ab4ff;font:600 13px ui-monospace}}
 .grid{{display:grid;grid-template-columns:1fr 1fr;gap:14px}}
 .card{{background:#14193a;border:1px solid #2a3464;border-radius:8px;padding:10px 12px}}
 .ok{{color:#52e08a}}.bad{{color:#ff6b6b}}.warn{{color:#ffb347}}
 table{{border-collapse:collapse;width:100%}}
 td,th{{padding:3px 8px;border-bottom:1px solid #2a3464;text-align:left}}
 td.k{{color:#8ab4ff;width:40%}}
 .head{{display:flex;justify-content:space-between;align-items:center;margin-bottom:10px}}
 .tag{{background:#2a3464;color:#d6e0ff;border-radius:4px;padding:2px 6px;font-size:11px}}
 .full{{grid-column:1/3}}
 a{{color:#8ab4ff}}
</style></head>
<body>
<div class="head">
  <h1>TrendMaster v14 — ops view (auto-refresh 5 s)</h1>
  <span class="tag">{ts}</span>
</div>
<div class="grid">
  <div class="card">
    <h2>Daily PnL</h2>
    <table>{pnl_rows}</table>
  </div>
  <div class="card">
    <h2>Restarts</h2>
    <table>{restart_rows}</table>
    <p style="margin:8px 0 0;color:#666">JSON: <a href="/restarts">/restarts</a> · <a href="/pnl">/pnl</a> · <a href="/signals">/signals</a> · <a href="/healthz">/healthz</a></p>
  </div>
  <div class="card full">
    <h2>Per-symbol signals</h2>
    <table>
      <tr><th>symbol</th><th>direction</th><th>conf</th><th>ts</th><th>age (s)</th></tr>
      {sig_rows}
    </table>
  </div>
</div>
</body></html>
"""


if __name__ == "__main__":
    print(f"[dashboard] reading signal from: {SIGNAL_FILE}")
    print(f"[dashboard] brain log:           {BRAIN_ERR}")
    print(f"[dashboard] symbols:             {len(TRADING_PAIRS)} ({', '.join(TRADING_PAIRS) or 'none'})")
    print("[dashboard] serving on http://localhost:8000/")
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="warning")
