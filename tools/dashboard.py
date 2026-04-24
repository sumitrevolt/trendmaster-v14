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
    a dict with at least {symbol, direction, confidence, ts} plus the
    agents-vote block and EA runtime overrides if the brain wrote them
    (Round 11+). Missing fields are reported as None / sentinel so the
    dashboard can render partial state."""
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
                # Agent breakdown + EA gate overrides (Round 11). Kept
                # as nested dicts so the HTML/v2 page can render per-
                # agent vote + reason without a second request.
                "agents": data.get("agents"),
                "sl_atr_mult": data.get("sl_atr_mult"),
                "tp_atr_mult": data.get("tp_atr_mult"),
                "adx_min": data.get("adx_min"),
                "require_all_3": data.get("require_all_3"),
                "max_spread_atr_pct": data.get("max_spread_atr_pct"),
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
        "agents": None,
        "sl_atr_mult": None,
        "tp_atr_mult": None,
        "adx_min": None,
        "require_all_3": None,
        "max_spread_atr_pct": None,
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


# ─── Advanced single dashboard at /  (replaces classic ops view) ──────────
#
# Single operator view. Read-only — can never interfere with a live brain.
# Classic HTML-table ops view was removed 2026-04-24; everything merged
# into the Chart.js-powered page below.


def _team_of(symbol: str) -> str:
    """Best-effort symbol → team mapping. Falls back to settings.TEAMS if
    the project exposes it, otherwise uses a static v14-era grouping."""
    try:
        from ai_trading_agents.risk_manager import team_of  # type: ignore

        t = team_of(symbol)
        if t:
            return t
    except Exception:
        pass
    s = (symbol or "").upper()
    if s in {"XAUUSD", "XAGUSD"}:
        return "METALS"
    if s in {"BTCUSD", "ETHUSD", "LTCUSD", "XRPUSD"}:
        return "CRYPTO"
    if s in {"XTIUSD", "XBRUSD", "XNGUSD", "USOIL", "UKOIL"}:
        return "COMMODITIES"
    return "FOREX"


def _agents_payload() -> Dict[str, Any]:
    """Per-symbol agent-vote matrix. Each row = {symbol, team,
    final_dir, final_conf, age_sec, agents:[{name, vote, reason}]}."""
    rows = []
    for s in _signals_payload():
        agents_block = s.get("agents") or {}
        votes = agents_block.get("votes") or []
        rows.append(
            {
                "symbol": s.get("symbol"),
                "team": _team_of(s.get("symbol") or ""),
                "final_dir": s.get("direction"),
                "final_conf": s.get("confidence"),
                "pre_agent_dir": agents_block.get("dir"),
                "age_sec": s.get("age_sec"),
                "votes": votes,
                "require_all_3": s.get("require_all_3"),
                "adx_min": s.get("adx_min"),
                "max_spread_atr_pct": s.get("max_spread_atr_pct"),
            }
        )
    # Ordered by age (freshest first) so stale data sinks.
    rows.sort(key=lambda r: (r.get("age_sec") is None, r.get("age_sec") or 0))
    return {"rows": rows, "ts": dt.datetime.now().isoformat(timespec="seconds")}


def _teams_payload() -> Dict[str, Any]:
    """Per-team performance aggregation from state.recent_results."""
    state = _read_brain_state()
    recent = list(state.get("recent_results", []) or [])
    buckets: Dict[str, Dict[str, Any]] = {}
    for r in recent:
        if not isinstance(r, dict):
            continue
        sym = r.get("symbol") or r.get("sym") or ""
        team = _team_of(sym)
        b = buckets.setdefault(team, {"team": team, "trades": 0, "wins": 0, "losses": 0, "pnl": 0.0})
        pnl = _pnl_of(r)
        b["trades"] += 1
        b["pnl"] += pnl
        if pnl > 0:
            b["wins"] += 1
        elif pnl < 0:
            b["losses"] += 1
    out = []
    for team in ("METALS", "FOREX", "CRYPTO", "COMMODITIES"):
        b = buckets.get(team, {"team": team, "trades": 0, "wins": 0, "losses": 0, "pnl": 0.0})
        wr = (b["wins"] / b["trades"] * 100.0) if b["trades"] else 0.0
        out.append({**b, "pnl": round(b["pnl"], 2), "win_rate_pct": round(wr, 1)})
    return {"teams": out}


def _equity_curve_payload() -> Dict[str, Any]:
    """Equity time series. Uses state.equity_snapshots if the brain writes
    them; otherwise falls back to the sequence of recent_results P&L."""
    state = _read_brain_state()
    snaps = state.get("equity_snapshots") or []
    series = []
    if isinstance(snaps, list) and snaps:
        for e in snaps:
            if isinstance(e, dict) and "ts" in e and "equity" in e:
                try:
                    series.append({"ts": int(e["ts"]), "equity": float(e["equity"])})
                except (TypeError, ValueError):
                    continue
    if not series:
        # Fallback: cumulative P&L from recent_results.
        base = float(state.get("start_of_day_equity") or 0.0)
        cum = base
        for r in state.get("recent_results", []) or []:
            if not isinstance(r, dict):
                continue
            ts = r.get("ts")
            pnl = _pnl_of(r)
            if ts:
                cum += pnl
                try:
                    series.append({"ts": int(ts), "equity": round(cum, 2)})
                except (TypeError, ValueError):
                    continue
    return {"series": series, "base_equity": state.get("start_of_day_equity")}


def _risk_payload() -> Dict[str, Any]:
    """Snapshot of risk-manager + portfolio risk if modules are enabled."""
    out: Dict[str, Any] = {}
    state = _read_brain_state()
    # Current exposure from MT5 if available (read-only)
    if HAVE_MT5:
        try:
            if mt5.initialize():
                try:
                    positions = mt5.positions_get() or []
                    out["open_positions"] = len(positions)
                    out["open_volume"] = round(sum(p.volume for p in positions), 2)
                    out["open_profit"] = round(sum(p.profit for p in positions), 2)
                finally:
                    mt5.shutdown()
        except Exception:
            pass
    # Kelly multiplier from state
    out["kelly_multiplier"] = state.get("kelly_multiplier")
    out["drawdown_lockout_active"] = bool(state.get("drawdown_lockout_until", 0) or 0) > 0
    # VaR/CVaR if computed recently
    for k in ("var_95", "cvar_95", "portfolio_var", "stress_loss"):
        if k in state:
            out[k] = state[k]
    return out


@app.get("/api/agents")
def api_agents() -> JSONResponse:
    return JSONResponse(_agents_payload())


@app.get("/api/teams")
def api_teams() -> JSONResponse:
    return JSONResponse(_teams_payload())


@app.get("/api/equity_curve")
def api_equity_curve() -> JSONResponse:
    return JSONResponse(_equity_curve_payload())


@app.get("/api/risk")
def api_risk() -> JSONResponse:
    return JSONResponse(_risk_payload())


_V2_HTML = r"""<!doctype html>
<html><head><meta charset="utf-8">
<title>TrendMaster v14 — Pro</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
<style>
 body{background:#0b1020;color:#d6e0ff;font:13px/1.45 ui-monospace,Consolas,monospace;margin:0;padding:16px}
 h1{margin:0 0 12px 0;color:#ffd84a;font:600 17px ui-monospace}
 h2{margin:0 0 8px 0;color:#8ab4ff;font:600 13px ui-monospace;letter-spacing:.3px}
 .grid{display:grid;grid-template-columns:repeat(12,1fr);gap:12px}
 .card{background:#14193a;border:1px solid #2a3464;border-radius:8px;padding:10px 12px;overflow:hidden}
 .span3{grid-column:span 3}.span4{grid-column:span 4}.span6{grid-column:span 6}.span8{grid-column:span 8}.span12{grid-column:span 12}
 .ok{color:#52e08a}.bad{color:#ff6b6b}.warn{color:#ffb347}.dim{color:#8090b8}
 table{border-collapse:collapse;width:100%}
 td,th{padding:3px 6px;border-bottom:1px solid #2a3464;text-align:left;white-space:nowrap}
 th{color:#8ab4ff;font-weight:600}
 .kpi{display:flex;flex-direction:column;align-items:center;justify-content:center;min-height:60px}
 .kpi .v{font:700 22px ui-monospace;color:#ffd84a}
 .kpi .l{color:#8090b8;font-size:11px;text-transform:uppercase;letter-spacing:.5px}
 .vote-chip{display:inline-block;min-width:22px;text-align:center;padding:1px 5px;margin:0 2px;border-radius:3px;font-weight:600;font-size:11px}
 .v-buy{background:#143e25;color:#52e08a;border:1px solid #2b6a41}
 .v-sell{background:#3e1414;color:#ff6b6b;border:1px solid #6a2b2b}
 .v-none{background:#272b3e;color:#8090b8;border:1px solid #3a3e55}
 .reason{color:#8090b8;font-size:11px;font-style:italic}
 .head{display:flex;justify-content:space-between;align-items:center;margin-bottom:12px}
 .tag{background:#2a3464;color:#d6e0ff;border-radius:4px;padding:2px 6px;font-size:11px}
 canvas{max-height:240px}
 a{color:#8ab4ff}
</style></head>
<body>
<div class="head">
  <h1>TrendMaster v14 — Pro view</h1>
  <span class="tag" id="ts">—</span>
</div>

<div class="grid">
  <div class="card span3 kpi"><div class="l">Trading state</div><div class="v" id="kpi-state">—</div></div>
  <div class="card span3 kpi"><div class="l">P/L today</div><div class="v" id="kpi-pnl">—</div></div>
  <div class="card span3 kpi"><div class="l">Trades (W/L)</div><div class="v" id="kpi-trades">—</div></div>
  <div class="card span3 kpi"><div class="l">Restart count</div><div class="v" id="kpi-restart">—</div></div>

  <div class="card span8">
    <h2>Agent votes per symbol</h2>
    <table id="tbl-agents">
      <thead><tr><th>symbol</th><th>team</th><th>final</th><th>conf</th>
      <th>trend H4</th><th>momentum H1</th><th>timing M30</th>
      <th class="dim">age (s)</th></tr></thead>
      <tbody></tbody>
    </table>
  </div>

  <div class="card span4">
    <h2>Per-team P/L</h2>
    <table id="tbl-teams">
      <thead><tr><th>team</th><th>trades</th><th>W</th><th>L</th><th>WR%</th><th>P/L</th></tr></thead>
      <tbody></tbody>
    </table>
  </div>

  <div class="card span8">
    <h2>Equity curve</h2>
    <canvas id="ch-equity"></canvas>
  </div>

  <div class="card span4">
    <h2>Risk snapshot</h2>
    <table id="tbl-risk"><tbody></tbody></table>
  </div>

  <div class="card span6">
    <h2>Agent activity (vote totals across all symbols)</h2>
    <canvas id="ch-agents"></canvas>
  </div>

  <div class="card span6">
    <h2>Signal confidence distribution</h2>
    <canvas id="ch-conf"></canvas>
  </div>

  <div class="card span12">
    <h2>Project graph &nbsp;<span class="dim" style="font-size:11px;font-weight:400">— code-review-graph Leiden community viz (2 MB). Drag to pan, scroll to zoom.</span></h2>
    <iframe id="graph-frame" src="/graph" loading="lazy"
            style="width:100%;height:640px;border:1px solid #2a3464;border-radius:6px;background:#0b1020"></iframe>
  </div>
</div>

<script>
const fmt = (v, d=2) => (v===null||v===undefined||Number.isNaN(+v)) ? "—" : (+v).toFixed(d);
const colorPL = v => (v>0?"ok":(v<0?"bad":""));
const VOTE_MAP = {1:{lbl:"BUY",cls:"v-buy"}, "-1":{lbl:"SELL",cls:"v-sell"}, 0:{lbl:"—",cls:"v-none"}};
function voteChip(v){ const m = VOTE_MAP[v+""] || VOTE_MAP[0]; return `<span class="vote-chip ${m.cls}">${m.lbl}</span>`; }

let chEquity=null, chConf=null, chAgents=null;

async function j(url){ try{const r=await fetch(url); return await r.json()}catch(e){return null} }

async function refresh(){
  const [pnl, rst, ag, tm, eq, risk] = await Promise.all([
    j("/pnl"), j("/restarts"), j("/api/agents"), j("/api/teams"),
    j("/api/equity_curve"), j("/api/risk")
  ]);

  document.getElementById("ts").textContent = new Date().toISOString().slice(0,19);

  // KPIs
  if(rst){
    document.getElementById("kpi-state").innerHTML = rst.trading_paused
      ? "<span class='bad'>HALTED</span>"
      : (rst.drawdown_lockout_active ? "<span class='bad'>DD-LOCK</span>" : "<span class='ok'>LIVE</span>");
    document.getElementById("kpi-restart").textContent = rst.restart_count ?? "—";
  }
  if(pnl){
    const p = pnl.pnl, pp = pnl.pnl_pct;
    document.getElementById("kpi-pnl").innerHTML = `<span class="${colorPL(p)}">${fmt(p)} (${fmt(pp,2)}%)</span>`;
    document.getElementById("kpi-trades").innerHTML =
      `${pnl.trades_today??0} (<span class="ok">${pnl.wins_today??0}</span>/<span class="bad">${pnl.losses_today??0}</span>)`;
  }

  // Agent-vote table
  if(ag && ag.rows){
    const byName = { trend_h4:null, momentum_h1:null, timing_m30:null };
    const tb = document.querySelector("#tbl-agents tbody");
    tb.innerHTML = ag.rows.map(r=>{
      const map = Object.assign({}, byName);
      (r.votes||[]).forEach(v=>{ if(v && v.name in map) map[v.name] = v; });
      const cell = v => v
        ? `${voteChip(v.vote)}<div class="reason">${(v.reason||"").slice(0,40)}</div>`
        : `${voteChip(0)}`;
      const dirCls = r.final_dir==="BUY"?"ok":(r.final_dir==="SELL"?"bad":"dim");
      return `<tr>
        <td>${r.symbol||"—"}</td><td class="dim">${r.team||""}</td>
        <td class="${dirCls}">${r.final_dir||"—"}</td><td>${fmt(r.final_conf,3)}</td>
        <td>${cell(map.trend_h4)}</td>
        <td>${cell(map.momentum_h1)}</td>
        <td>${cell(map.timing_m30)}</td>
        <td class="dim">${fmt(r.age_sec,1)}</td>
      </tr>`;
    }).join("");
  }

  // Per-team table
  if(tm && tm.teams){
    const tb = document.querySelector("#tbl-teams tbody");
    tb.innerHTML = tm.teams.map(t=>
      `<tr><td>${t.team}</td><td>${t.trades}</td>
       <td class="ok">${t.wins}</td><td class="bad">${t.losses}</td>
       <td>${t.win_rate_pct}%</td>
       <td class="${colorPL(t.pnl)}">${fmt(t.pnl)}</td></tr>`
    ).join("");
  }

  // Risk table
  if(risk){
    const rows = [];
    if("open_positions" in risk) rows.push(["open positions", risk.open_positions]);
    if("open_volume" in risk) rows.push(["open volume", fmt(risk.open_volume)]);
    if("open_profit" in risk) rows.push(["open profit",
      `<span class="${colorPL(risk.open_profit)}">${fmt(risk.open_profit)}</span>`]);
    if(risk.kelly_multiplier!=null) rows.push(["Kelly ×", fmt(risk.kelly_multiplier,3)]);
    if(risk.var_95!=null) rows.push(["VaR 95%", fmt(risk.var_95)]);
    if(risk.cvar_95!=null) rows.push(["CVaR 95%", fmt(risk.cvar_95)]);
    rows.push(["DD lockout", risk.drawdown_lockout_active?"<span class='bad'>ACTIVE</span>":"<span class='ok'>clear</span>"]);
    document.querySelector("#tbl-risk tbody").innerHTML = rows.map(([k,v])=>
      `<tr><td class="dim">${k}</td><td>${v}</td></tr>`).join("");
  }

  // Equity curve
  if(eq && Array.isArray(eq.series)){
    const labels = eq.series.map(p => new Date(p.ts*1000).toISOString().slice(11,19));
    const data = eq.series.map(p => p.equity);
    if(!chEquity){
      const ctx = document.getElementById("ch-equity");
      chEquity = new Chart(ctx, {
        type:"line",
        data:{labels,datasets:[{label:"equity",data,borderColor:"#ffd84a",backgroundColor:"rgba(255,216,74,.08)",
              fill:true,tension:.25,pointRadius:0}]},
        options:{animation:false,plugins:{legend:{display:false}},
          scales:{x:{ticks:{color:"#8090b8",maxTicksLimit:8}},y:{ticks:{color:"#8090b8"}}}}
      });
    } else {
      chEquity.data.labels = labels; chEquity.data.datasets[0].data = data; chEquity.update("none");
    }
  }

  // Confidence distribution
  if(ag && ag.rows){
    const buckets = Array(10).fill(0);
    ag.rows.forEach(r=>{ const c = +r.final_conf; if(!isNaN(c) && c>=0 && c<=1) buckets[Math.min(9,Math.floor(c*10))]++; });
    const labels = buckets.map((_,i)=>`${(i/10).toFixed(1)}–${((i+1)/10).toFixed(1)}`);
    if(!chConf){
      const ctx = document.getElementById("ch-conf");
      chConf = new Chart(ctx, {
        type:"bar",
        data:{labels,datasets:[{label:"symbols",data:buckets,backgroundColor:"#8ab4ff"}]},
        options:{animation:false,plugins:{legend:{display:false}},
          scales:{x:{ticks:{color:"#8090b8"}},y:{ticks:{color:"#8090b8"},beginAtZero:true}}}
      });
    } else {
      chConf.data.datasets[0].data = buckets; chConf.update("none");
    }
  }

  // Agent activity — stacked bar: per agent, BUY/SELL/NONE counts across all symbols
  if(ag && ag.rows){
    const agentNames = ["trend_h4","momentum_h1","timing_m30"];
    const buys  = agentNames.map(()=>0);
    const sells = agentNames.map(()=>0);
    const nones = agentNames.map(()=>0);
    ag.rows.forEach(r=>{
      (r.votes||[]).forEach(v=>{
        const i = agentNames.indexOf(v.name);
        if(i<0) return;
        if(v.vote===1) buys[i]++;
        else if(v.vote===-1) sells[i]++;
        else nones[i]++;
      });
    });
    const datasets = [
      {label:"BUY",  data:buys,  backgroundColor:"#52e08a"},
      {label:"SELL", data:sells, backgroundColor:"#ff6b6b"},
      {label:"NONE", data:nones, backgroundColor:"#3a3e55"},
    ];
    if(!chAgents){
      const ctx = document.getElementById("ch-agents");
      chAgents = new Chart(ctx, {
        type:"bar",
        data:{labels:agentNames, datasets},
        options:{
          animation:false,
          plugins:{legend:{labels:{color:"#d6e0ff"}}},
          scales:{
            x:{stacked:true,ticks:{color:"#8090b8"}},
            y:{stacked:true,ticks:{color:"#8090b8"},beginAtZero:true}
          }
        }
      });
    } else {
      chAgents.data.datasets[0].data = buys;
      chAgents.data.datasets[1].data = sells;
      chAgents.data.datasets[2].data = nones;
      chAgents.update("none");
    }
  }
}

refresh();
setInterval(refresh, 2000);
</script>
</body></html>
"""


@app.get("/", response_class=HTMLResponse)
def home() -> str:
    return _V2_HTML


@app.get("/graph", response_class=HTMLResponse)
def project_graph() -> HTMLResponse:
    """Serve the code-review-graph interactive HTML from docs/.
    Rebuilt by `code-review-graph visualize` / `rebuild_graph.cmd` /
    the daily scheduled task. 2 MB self-contained; safe to embed in an
    iframe."""
    p = ROOT / "docs" / "code_review_graph.html"
    if not p.exists():
        return HTMLResponse(
            "<h2 style='color:#ffb347;font-family:monospace'>"
            "Project graph not built yet. Run "
            "<code>code-review-graph visualize --mode community --format html</code> "
            "and copy the output to docs/code_review_graph.html.</h2>",
            status_code=200,
        )
    try:
        return HTMLResponse(p.read_text(encoding="utf-8", errors="ignore"))
    except Exception as e:
        return HTMLResponse(
            f"<h2 style='color:#ff6b6b;font-family:monospace'>Graph load error: {e!r}</h2>",
            status_code=500,
        )


if __name__ == "__main__":
    print(f"[dashboard] reading signal from: {SIGNAL_FILE}")
    print(f"[dashboard] brain log:           {BRAIN_ERR}")
    print(f"[dashboard] symbols:             {len(TRADING_PAIRS)} ({', '.join(TRADING_PAIRS) or 'none'})")
    print("[dashboard] serving on http://localhost:8000/  (classic)  +  /v2  (pro)")
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="warning")
