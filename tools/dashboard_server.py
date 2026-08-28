# -*- coding: utf-8 -*-
"""TrendMaster Dashboard - Comprehensive Edition

http://localhost:8765

Features (all 14):
  1. Per-pair P/L breakdown table
  2. Equity curve graph (Chart.js)
  3. Modify SL/TP on open positions
  4. Live spread monitor
  5. Close individual position buttons
  6. News calendar viewer
  7. Brain learning state
  8. TV alerts manager (cached)
  9. Trade duration stats
 10. CSV export of closed trades
 11. Mobile-responsive layout
 12. Audio alert on big P/L moves (Web Audio API)
 13. Theme toggle (dark/light)
 14. Background equity logger thread (60s interval)

Plus original features: master switches, per-pair toggles, settings,
schtasks viewer, logs viewer, backtest reports list, postmortems.

Stack: stdlib HTTP server (no Flask) + psutil (no console flash).
"""
from __future__ import annotations

import csv
import io
import json
import logging
import os
import statistics
import subprocess
import sys
import threading
import time
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from threading import Lock

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import MetaTrader5 as mt5

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# [2026-05-09] Load .env at module import so get_notifier() — built lazily on
# first button press — sees TELEGRAM_BOT_TOKEN. Without this, the dashboard's
# Test Telegram + Send Snapshot buttons silently return {"ok": false} because
# the singleton TelegramNotifier was constructed with empty creds.
try:
    from dotenv import load_dotenv
    for _cand in (ROOT / ".env", ROOT / "config" / ".env"):
        if _cand.exists():
            load_dotenv(_cand, override=True)
            break
except ImportError:
    pass

LOG_DIR = ROOT / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
CONFIG_PATH = LOG_DIR / "dashboard_config.json"
EQUITY_LOG_PATH = LOG_DIR / "equity_history.jsonl"
REPORTS_DIR = ROOT / "reports"
POSTMORTEMS_DIR = ROOT / "docs" / "POSTMORTEMS"
NEWS_CALENDAR_PATH = ROOT / "config" / "news_calendar.json"
SIGNAL_OUTCOMES_PATH = LOG_DIR / "signal_outcomes.jsonl"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler(LOG_DIR / "dashboard.log", encoding="utf-8")],
)
log = logging.getLogger("dashboard")

_CREATE_NO_WINDOW = 0x08000000

DEFAULT_CONFIG = {
    "trading_enabled": True,
    "safeguards": {
        "news_blackout": True,
        "dd_circuit_breaker": True,
        "spread_check": True,
        "correlation_guard": True,
    },
    "trailing_enabled": True,
    "brain_filter_enabled": True,
    "two_leg_enabled": True,
    "fixed_lot": 0.01,
    "quick_tp_atr": 1.5,
    "quick_sl_atr": 3.0,
    "trend_tp_atr": 5.0,
    "trend_sl_atr": 3.0,
    "max_daily_dd_pct": 5.0,
    "cooldown_sec": 300,
    "audio_alert_threshold": 50.0,  # alert when |P/L change| > $50
    "pairs_enabled": {
        s: True for s in [
            "XAUUSD", "XAGUSD", "EURUSD", "GBPUSD", "USDJPY", "USDCHF", "USDCAD",
            "AUDUSD", "NZDUSD", "EURJPY", "GBPJPY", "AUDJPY", "CADJPY", "EURGBP",
            "EURAUD", "BTCUSD", "ETHUSD", "XTIUSD", "XBRUSD", "XNGUSD",
        ]
    },
}

ALL_SYMBOLS = list(DEFAULT_CONFIG["pairs_enabled"].keys())

_config_lock = Lock()
_tv_alerts_cache = {"data": None, "ts": 0}


def load_config() -> dict:
    if CONFIG_PATH.exists():
        try:
            data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            return {**DEFAULT_CONFIG, **data,
                    "safeguards": {**DEFAULT_CONFIG["safeguards"], **(data.get("safeguards") or {})},
                    "pairs_enabled": {**DEFAULT_CONFIG["pairs_enabled"], **(data.get("pairs_enabled") or {})}}
        except Exception:
            pass
    return DEFAULT_CONFIG.copy()


def save_config(cfg: dict) -> None:
    with _config_lock:
        CONFIG_PATH.write_text(json.dumps(cfg, indent=2), encoding="utf-8")


if not CONFIG_PATH.exists():
    save_config(DEFAULT_CONFIG)


# ─── psutil-based process inspection ────────────────────────────────────
def _list_processes_cmd_lower():
    try:
        import psutil
        out = []
        for p in psutil.process_iter(["pid", "cmdline"]):
            try:
                cl = p.info.get("cmdline") or []
                out.append((p.info["pid"], " ".join(cl).lower()))
            except Exception:
                continue
        return out
    except ImportError:
        return []


def _kill_processes_by_cmd_match(needle: str) -> int:
    needle = needle.lower()
    killed = 0
    try:
        import psutil
        for p in psutil.process_iter(["pid", "cmdline"]):
            try:
                cl = p.info.get("cmdline") or []
                if needle in " ".join(cl).lower():
                    p.kill()
                    killed += 1
            except Exception:
                continue
    except ImportError:
        pass
    return killed


# ─── Account / market state ─────────────────────────────────────────────
def get_account_state() -> dict:
    mt5.initialize()
    ti = mt5.terminal_info()
    ai = mt5.account_info()
    pos = mt5.positions_get() or []
    out = {
        "connected": ti.connected if ti else False,
        "trade_allowed": ti.trade_allowed if ti else False,
        "build": ti.build if ti else None,
        "balance": ai.balance if ai else 0,
        "equity": ai.equity if ai else 0,
        "margin": ai.margin if ai else 0,
        "margin_free": ai.margin_free if ai else 0,
        "floating_pl": sum(p.profit for p in pos),
        "n_positions": len(pos),
        "positions": [
            _enrich_position(p) for p in sorted(pos, key=lambda x: x.symbol)
        ],
    }
    return out


def _enrich_position(p) -> dict:
    """Add: entry time, duration, % move from entry, R-progress, comment source."""
    info = mt5.symbol_info(p.symbol)
    digits = info.digits if info else 5
    is_buy = p.type == 0
    open_px = p.price_open
    cur_px = p.price_current
    # % move from entry (positive = in our favor)
    if open_px > 0:
        pct = ((cur_px - open_px) / open_px) * 100 * (1 if is_buy else -1)
    else:
        pct = 0
    # R-progress: how far between entry and TP (1.0 = TP hit, -1.0 = SL hit)
    r_progress = None
    if p.sl > 0 and p.tp > 0:
        risk_dist = abs(open_px - p.sl)
        reward_dist = abs(p.tp - open_px)
        if is_buy:
            move = cur_px - open_px
        else:
            move = open_px - cur_px
        if move >= 0 and reward_dist > 0:
            r_progress = round(move / reward_dist, 2)  # 0 to 1
        elif move < 0 and risk_dist > 0:
            r_progress = round(move / risk_dist, 2)    # 0 to -1

    age_sec = int(time.time() - p.time)
    if age_sec < 60:
        duration = f"{age_sec}s"
    elif age_sec < 3600:
        duration = f"{age_sec//60}m"
    else:
        duration = f"{age_sec//3600}h{(age_sec%3600)//60}m"

    open_time = datetime.fromtimestamp(p.time).strftime("%H:%M:%S")
    return {
        "ticket": p.ticket, "symbol": p.symbol,
        "dir": "BUY" if is_buy else "SELL",
        "leg": "QUICK" if p.magic == 14014 else ("TREND" if p.magic == 14015 else f"M{p.magic}"),
        "lots": p.volume, "open": round(open_px, digits),
        "current": round(cur_px, digits),
        "sl": round(p.sl, digits) if p.sl > 0 else None,
        "tp": round(p.tp, digits) if p.tp > 0 else None,
        "profit": round(p.profit, 2),
        "age_min": age_sec // 60,
        "duration": duration,
        "open_time": open_time,
        "pct_move": round(pct, 3),         # NEW: % from entry
        "r_progress": r_progress,          # NEW: -1.0 to 1.0 (-SL to +TP)
        "comment": (p.comment or "")[:30], # NEW: source tag from executor
        "digits": digits,
    }


def get_recent_deals(hours: int = 24) -> dict:
    mt5.initialize()
    since = datetime.now() - timedelta(hours=hours)
    deals = mt5.history_deals_get(since, datetime.now()) or []
    closed = [d for d in deals if d.entry == mt5.DEAL_ENTRY_OUT]
    wins = sum(1 for d in closed if d.profit > 0)
    losses = sum(1 for d in closed if d.profit < 0)
    total = sum(d.profit for d in closed)
    avg_w = (sum(d.profit for d in closed if d.profit > 0) / wins) if wins else 0
    avg_l = (sum(d.profit for d in closed if d.profit < 0) / losses) if losses else 0
    # Build IN/OUT pairs to compute duration + entry price per closed trade
    by_position = {}
    for d in deals:
        pid = d.position_id
        if pid not in by_position:
            by_position[pid] = {"in": None, "out": None}
        if d.entry == mt5.DEAL_ENTRY_IN:
            by_position[pid]["in"] = d
        elif d.entry == mt5.DEAL_ENTRY_OUT:
            by_position[pid]["out"] = d

    enriched_deals = []
    for d in sorted(closed, key=lambda x: x.time, reverse=True)[:30]:
        pair = by_position.get(d.position_id, {})
        in_d = pair.get("in")
        duration_min = None
        entry_price = None
        exit_reason = "?"
        r_mult = None
        if in_d:
            duration_min = int((d.time - in_d.time) / 60)
            entry_price = round(in_d.price, 5)
            # Determine exit reason from comment
            cmt = (d.comment or "").lower()
            if "tp" in cmt or "take" in cmt:
                exit_reason = "TP HIT"
            elif "sl" in cmt or "stop" in cmt:
                exit_reason = "SL HIT"
            elif "close" in cmt or "manual" in cmt or "dash" in cmt:
                exit_reason = "MANUAL"
            elif "trail" in cmt:
                exit_reason = "TRAIL"
            else:
                exit_reason = cmt[:18] if cmt else "?"
        enriched_deals.append({
            "time": datetime.fromtimestamp(d.time).strftime("%H:%M:%S"),
            "ts": int(d.time), "symbol": d.symbol,
            "dir": "BUY" if d.type == mt5.DEAL_TYPE_BUY else "SELL",
            # NOTE: the exit deal's type is REVERSE of the original trade direction.
            # If trade was BUY (long), exit is SELL deal. So flip back:
            "trade_dir": "SELL" if d.type == mt5.DEAL_TYPE_BUY else "BUY",
            "lots": d.volume, "profit": round(d.profit, 2),
            "entry_price": entry_price,
            "exit_price": round(d.price, 5),
            "duration_min": duration_min,
            "exit_reason": exit_reason,
            "comment": (d.comment or "")[:30],
        })

    out = {
        "deals": enriched_deals,
        "stats": {
            "n": len(closed), "wins": wins, "losses": losses,
            "wr": round(wins / len(closed) * 100, 1) if closed else 0,
            "total_pl": round(total, 2),
            "avg_win": round(avg_w, 2), "avg_loss": round(avg_l, 2),
            "profit_factor": round(abs(sum(d.profit for d in closed if d.profit>0) / sum(d.profit for d in closed if d.profit<0)), 2) if losses else None,
        },
    }
    return out


def get_per_pair_pnl(hours: int = 168) -> list:
    """Per-pair total/win/loss + open floating, sorted by total P/L."""
    mt5.initialize()
    since = datetime.now() - timedelta(hours=hours)
    deals = mt5.history_deals_get(since, datetime.now()) or []
    closed = [d for d in deals if d.entry == mt5.DEAL_ENTRY_OUT]
    pos = mt5.positions_get() or []
    by_sym = defaultdict(lambda: {"closed_pl": 0, "wins": 0, "losses": 0,
                                    "n_closed": 0, "open_pl": 0, "n_open": 0})
    for d in closed:
        s = by_sym[d.symbol]
        s["closed_pl"] += d.profit
        s["n_closed"] += 1
        if d.profit > 0:
            s["wins"] += 1
        elif d.profit < 0:
            s["losses"] += 1
    for p in pos:
        s = by_sym[p.symbol]
        s["open_pl"] += p.profit
        s["n_open"] += 1
    out = []
    for sym, s in by_sym.items():
        wr = round(s["wins"] / s["n_closed"] * 100, 1) if s["n_closed"] else None
        out.append({
            "symbol": sym,
            "n_closed": s["n_closed"],
            "wins": s["wins"], "losses": s["losses"], "wr": wr,
            "closed_pl": round(s["closed_pl"], 2),
            "open_pl": round(s["open_pl"], 2),
            "n_open": s["n_open"],
            "total_pl": round(s["closed_pl"] + s["open_pl"], 2),
        })
    out.sort(key=lambda x: -x["total_pl"])
    return out


def get_trade_duration_stats(hours: int = 168) -> dict:
    """Avg/median trade duration, plus quick-vs-trend."""
    mt5.initialize()
    since = datetime.now() - timedelta(hours=hours)
    deals = mt5.history_deals_get(since, datetime.now()) or []
    # Pair open + close by position_id
    by_pos = defaultdict(list)
    for d in deals:
        by_pos[d.position_id].append(d)
    durations = []
    quick_durs = []
    trend_durs = []
    for pid, dlist in by_pos.items():
        if len(dlist) < 2:
            continue
        dlist.sort(key=lambda x: x.time)
        dur = dlist[-1].time - dlist[0].time
        if dur <= 0:
            continue
        durations.append(dur)
        magic = dlist[0].magic
        if magic == 14014:
            quick_durs.append(dur)
        elif magic == 14015:
            trend_durs.append(dur)
    mt5.shutdown()
    def stats(arr):
        if not arr:
            return {"n": 0}
        return {"n": len(arr),
                "avg_min": round(statistics.mean(arr) / 60, 1),
                "median_min": round(statistics.median(arr) / 60, 1),
                "max_min": round(max(arr) / 60, 1)}
    return {
        "all": stats(durations),
        "quick": stats(quick_durs),
        "trend": stats(trend_durs),
    }


def get_spread_monitor() -> list:
    """Current spread per pair + spread/ATR ratio."""
    mt5.initialize()
    out = []
    for sym in ALL_SYMBOLS:
        info = mt5.symbol_info(sym)
        tick = mt5.symbol_info_tick(sym)
        if not info or not tick:
            continue
        spread_pts = (tick.ask - tick.bid) / info.point if info.point > 0 else 0
        # Quick ATR (last 14 H1 bars)
        rates = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_H1, 0, 15)
        atr = 0
        if rates is not None and len(rates) >= 15:
            trs = []
            for i in range(1, len(rates)):
                h, l, pc = rates[i]["high"], rates[i]["low"], rates[i - 1]["close"]
                trs.append(max(h - l, abs(h - pc), abs(l - pc)))
            atr = sum(trs) / len(trs) if trs else 0
        ratio_pct = round((tick.ask - tick.bid) / atr * 100, 1) if atr > 0 else None
        out.append({
            "symbol": sym, "bid": round(tick.bid, info.digits), "ask": round(tick.ask, info.digits),
            "spread_pts": int(spread_pts), "atr": round(atr, info.digits) if atr > 0 else None,
            "ratio_pct": ratio_pct,
            "warn": ratio_pct is not None and ratio_pct > 30,
        })
    return out


def get_news_calendar() -> list:
    """Upcoming high-impact news in next 24h."""
    if not NEWS_CALENDAR_PATH.exists():
        return []
    try:
        events = json.loads(NEWS_CALENDAR_PATH.read_text(encoding="utf-8"))
    except Exception:
        return []
    now = datetime.now(tz=None).timestamp()
    out = []
    for ev in events:
        try:
            ev_time_str = ev.get("datetime_utc", "")
            ev_time = datetime.fromisoformat(ev_time_str.replace("Z", "+00:00"))
            ev_ts = ev_time.timestamp()
            if 0 < ev_ts - now < 86400:
                out.append({
                    "time": ev_time.strftime("%m-%d %H:%M"),
                    "currency": ev.get("currency", "?"),
                    "impact": ev.get("impact", "?"),
                    "event": ev.get("event", "")[:60],
                    "minutes_to_go": int((ev_ts - now) / 60),
                })
        except Exception:
            continue
    out.sort(key=lambda x: x["minutes_to_go"])
    return out[:20]


def get_brain_learning_stats() -> dict:
    """Aggregate signal outcomes per (sym, dir) class."""
    if not SIGNAL_OUTCOMES_PATH.exists():
        return {"total": 0, "by_class": []}
    classes = defaultdict(lambda: {"n": 0, "wins": 0, "total_r": 0})
    for line in SIGNAL_OUTCOMES_PATH.open(encoding="utf-8"):
        try:
            o = json.loads(line)
            key = f"{o.get('symbol','?')}:{o.get('direction','?')}"
            c = classes[key]
            c["n"] += 1
            if o.get("win"):
                c["wins"] += 1
            c["total_r"] += float(o.get("R", 0))
        except Exception:
            continue
    out = []
    for key, c in classes.items():
        wr = round(c["wins"] / c["n"] * 100, 1) if c["n"] else 0
        avg_r = round(c["total_r"] / c["n"], 3) if c["n"] else 0
        out.append({"class": key, "n": c["n"], "wr": wr, "avg_r": avg_r,
                    "total_r": round(c["total_r"], 2),
                    "blocked": avg_r < -0.1 and c["n"] >= 10})
    out.sort(key=lambda x: -x["total_r"])
    return {"total": sum(c["n"] for c in classes.values()),
            "by_class": out, "filter_min_n": 10, "filter_threshold_r": -0.1}


def get_recent_signals(n: int = 30) -> dict:
    sf = ROOT / "logs" / "tv_signals.jsonl"
    if not sf.exists():
        return {"signals": [], "by_symbol": []}
    rocket = []
    by_symbol = Counter()
    last_fire = {}
    try:
        lines = sf.read_text(encoding="utf-8", errors="replace").splitlines()[-1000:]
        for line in lines:
            try:
                obj = json.loads(line)
                strat = str(obj.get("tv_strategy", "")).lower()
                if "rocket_prime" not in strat:
                    continue
                sym = obj.get("symbol", "?")
                ts = obj.get("ts", 0)
                by_symbol[sym] += 1
                if ts > last_fire.get(sym, 0):
                    last_fire[sym] = ts
                rocket.append(obj)
            except Exception:
                continue
    except Exception:
        pass
    now = int(time.time())
    by_sym_list = [
        {"symbol": s, "count": c, "last_min_ago": int((now - last_fire.get(s, 0)) / 60) if last_fire.get(s) else None}
        for s, c in sorted(by_symbol.items(), key=lambda x: -x[1])
    ]
    out = []
    for o in rocket[-n:][::-1]:
        ts = o.get("ts", 0)
        out.append({"time": datetime.fromtimestamp(ts).strftime("%m-%d %H:%M"),
                    "symbol": o.get("symbol", "?"), "dir": o.get("direction", "?"),
                    "strategy": o.get("tv_strategy", "-"),
                    "tf": o.get("tv_timeframe") or "-",
                    "conf": round(float(o.get("confidence", 0)) * 100)})
    return {"signals": out, "by_symbol": by_sym_list}


def get_process_health() -> dict:
    """Mode-aware component health (2026-08-22).

    LOCAL brain mode (TV_SIGNAL.enabled=False): EA on chart executes directly
    from brain signal JSONs. TV-mode components (executor/trailing/receiver/
    tunnel/listener) are intentionally OFF -> reported as 'na', NOT 'DEAD'.
    Essential here: mt5 + brain + dashboard.

    TV mode (Pro renewed): original expectations return; brain shadowed.
    """
    try:
        from config import settings as _s
        tv_mode = bool((getattr(_s, "TV_SIGNAL", {}) or {}).get("enabled", False))
    except Exception:
        tv_mode = False
    procs = _list_processes_cmd_lower()
    all_cmd = " ".join(c[1] for c in procs)

    def up(needle: str) -> bool:
        return needle.lower() in all_cmd

    if tv_mode:
        out = {"mode": "tv"}
        for key, needle in {
            "executor": "python_signal_executor",
            "trailing": "trailing_stop_manager",
            "receiver": "tv_webhook_receiver",
            "tunnel": None,  # ngrok OR cloudflared
            "telegram_listener": "telegram_direction_listener",
            "dashboard": "dashboard_server",
            "brain_shadow": "trend_master_brain",
            "mt5": "terminal64",
        }.items():
            if needle is None:
                out[key] = up("ngrok") or up("cloudflared")
            else:
                out[key] = up(needle)
        return out

    # LOCAL brain mode
    out = {
        "mode": "local",
        "mt5": up("terminal64"),
        "brain": up("trend_master_brain"),
        "dashboard": up("dashboard_server"),
        # TV-mode components — off by design in local mode
        "executor": "na",
        "trailing": "na",
        "receiver": up("tv_webhook_receiver"),   # informational: idle but harmless
        "tunnel": ("na" if not (up("ngrok") or up("cloudflared"))
                   else True),
        "telegram_listener": "na",
        "brain_shadow": "na",
    }
    return out


def get_ocr_pipeline_stats() -> dict:
    """Chart-OCR pipeline metrics (2026-05-13). Reads rp_ocr_audit.jsonl
    written by ai_trading_agents/chart_scrape_ocr.py.
    """
    audit_path = ROOT / "logs" / "rp_ocr_audit.jsonl"
    if not audit_path.exists():
        return {"enabled": True, "count_total": 0, "count_buy": 0, "count_sell": 0,
                "count_none": 0, "last_ts": None, "last_symbol": None,
                "last_direction": None, "last_confidence": None}
    try:
        lines = audit_path.read_text(encoding="utf-8", errors="replace").splitlines()
        total = len(lines)
        n_buy = n_sell = n_none = 0
        last = None
        for line in lines[-200:]:
            try:
                row = json.loads(line)
                d = row.get("direction", "NONE")
                if d == "BUY":
                    n_buy += 1
                elif d == "SELL":
                    n_sell += 1
                else:
                    n_none += 1
                last = row
            except Exception:
                pass
        out = {"enabled": True, "count_total": total,
               "count_buy": n_buy, "count_sell": n_sell, "count_none": n_none}
        if last:
            out["last_ts"] = last.get("ts")
            out["last_symbol"] = last.get("symbol")
            out["last_direction"] = last.get("direction")
            meta = last.get("meta") or {}
            out["last_confidence"] = meta.get("confidence")
        return out
    except Exception as e:
        return {"enabled": True, "error": str(e)}


def get_recent_skips(limit: int = 30) -> dict:
    """Parse logs/python_executor.log for recently SKIPPED signals.

    Operator visibility requirement (2026-05-14): when RP signal arrives
    but trade doesn't fire, dashboard must show WHY (which safeguard
    layer blocked). This function parses the executor log for skip
    patterns + classifies them.

    Categories (most important first):
      - SAFEGUARD_BLOCK: 9-layer risk gate refused (operator-actionable)
      - BRAIN_VETO: brain disagreed with RP direction
      - STRATEGY_FILTER: tv_strategy not in whitelist
      - STALE: signal too old by the time executor saw it
      - NEWS: news blackout
      - DD: drawdown breaker tripped

    Returns recent N events with ts/symbol/direction/category/reason.
    """
    import re
    log_path = LOG_DIR / "python_executor.log"
    if not log_path.exists():
        return {"items": [], "by_category": {}, "msg": "executor log missing"}

    try:
        # Read last ~600 lines (one heartbeat batch is ~10 lines, so 60 cycles)
        with open(log_path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        tail = lines[-800:]

        # Patterns
        rx_safeguard = re.compile(
            r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),\d+ \[\w+\] SAFEGUARD BLOCK (\w+) (\w+):\s*(.+)$"
        )
        rx_skip_filter = re.compile(
            r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),\d+ \[\w+\] skip (\S+):\s*tv_strategy=(.+)$"
        )
        rx_stale = re.compile(
            r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),\d+ \[\w+\] skip (\w+):\s*stale signal\s*\(age=(\d+)s"
        )
        # [2026-05-17] FLIP BLOCKED — brain didn't explicitly agree with new direction
        rx_flip_blocked = re.compile(
            r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),\d+ \[\w+\] FLIP BLOCKED (\w+) (\w+):\s*(.+)$"
        )

        items = []
        # Dedup stale skips (executor logs same stale every 5 sec — only keep
        # latest per symbol)
        latest_stale_per_sym = {}

        for line in tail:
            line = line.rstrip()
            m = rx_safeguard.match(line)
            if m:
                ts, sym, direction, reason = m.groups()
                # Classify by reason keyword
                rl = reason.lower()
                if "brain veto" in rl or "brain disagrees" in rl:
                    cat = "BRAIN_VETO"
                elif "cluster" in rl:
                    cat = "CLUSTER_CAP"
                elif "long-usd" in rl or "short-usd" in rl:
                    cat = "USD_SIDE_CAP"
                elif "equity-tier" in rl:
                    cat = "TIER_CAP"
                elif "day-pnl" in rl or "day-loss" in rl:
                    cat = "PER_SYMBOL_LOSS"
                elif "time-of-day" in rl:
                    cat = "TIME_BLACKOUT"
                elif "news" in rl:
                    cat = "NEWS_BLACKOUT"
                elif "drawdown" in rl or "dd " in rl:
                    cat = "DRAWDOWN"
                elif "spread" in rl:
                    cat = "SPREAD"
                else:
                    cat = "SAFEGUARD_OTHER"
                items.append({
                    "ts": ts,
                    "symbol": sym,
                    "direction": direction,
                    "category": cat,
                    "reason": reason[:140],
                })
                continue

            m = rx_skip_filter.match(line)
            if m:
                ts, fname, rest = m.groups()
                # Extract strategy name from rest
                sym = fname.replace("trendmaster_signals_", "").replace(".json", "")
                if sym == "trendmaster_signals":
                    sym = "XAUUSD"  # default for that filename
                items.append({
                    "ts": ts,
                    "symbol": sym,
                    "direction": "?",
                    "category": "STRATEGY_FILTER",
                    "reason": f"tv_strategy={rest[:80]}",
                })
                continue

            m = rx_stale.match(line)
            if m:
                ts, sym, age = m.groups()
                latest_stale_per_sym[sym] = {
                    "ts": ts,
                    "symbol": sym,
                    "direction": "?",
                    "category": "STALE",
                    "reason": f"signal {age}s old (limit 90s)",
                }
                continue

            # [2026-05-17] FLIP BLOCKED — brain didn't explicitly agree with new direction
            m = rx_flip_blocked.match(line)
            if m:
                ts, sym, direction, reason = m.groups()
                items.append({
                    "ts": ts,
                    "symbol": sym,
                    "direction": direction,
                    "category": "FLIP_BLOCKED",
                    "reason": f"FLIP blocked: {reason[:130]}",
                })
                continue

        # Add latest stale entries (deduped per symbol)
        items.extend(latest_stale_per_sym.values())

        # Sort by timestamp descending, take latest N
        items.sort(key=lambda x: x["ts"], reverse=True)

        # [2026-05-14] Filter out events older than 5 min. Auto-archive now
        # cleans stale signal files immediately, so any STALE shown should be
        # very recent. Old entries are historical noise — let them age out.
        # 5-min window is short enough that ongoing problems re-trigger
        # quickly (executor heartbeat is every 5s), so currently-active
        # issues will always appear here.
        from datetime import datetime, timedelta
        cutoff = datetime.now() - timedelta(minutes=5)
        fresh_items = []
        for it in items:
            try:
                ev_dt = datetime.strptime(it["ts"], "%Y-%m-%d %H:%M:%S")
                if ev_dt >= cutoff:
                    fresh_items.append(it)
            except (ValueError, TypeError):
                # If ts parse fails, keep the item (defensive)
                fresh_items.append(it)
        items = fresh_items[:limit]

        # Tally by category
        by_cat = {}
        for it in items:
            by_cat[it["category"]] = by_cat.get(it["category"], 0) + 1

        # Add operator-actionable detail per category
        CAT_DETAILS = {
            "FLIP_BLOCKED": {
                "explain": "Opposite-direction RP signal arrived but brain wouldn't EXPLICITLY agree with the new direction. Operator policy 2026-05-17: only flip an existing position if brain has a fresh view (< 1hr) with conf >= 0.55 AND direction matches. Otherwise keep existing — don't churn on uncertainty.",
                "action": "Check chart yourself. If you trust the new RP direction, manually close the running position; the next same-direction RP signal can then open. To relax: lower BRAIN_EXPLICIT_AGREE_MIN_CONF in tools/safeguards.py (default 0.55).",
            },
            "BRAIN_VETO": {
                "explain": "Brain's rule-based inference contradicts RP direction with high confidence. Either RP is wrong-direction (rare) or market context shifted. Bot blocked the trade to protect account.",
                "action": "Check chart manually. If you trust RP, you can lower BRAIN_VETO_MIN_CONFIDENCE in tools/safeguards.py (default 0.65). Or set env BRAIN_VETO_ENABLED=0 to disable entirely.",
            },
            "USD_SIDE_CAP": {
                "explain": "Bot already holds 3 positions on this USD side (long-USD or short-USD). Adding more would over-concentrate the account on dollar direction.",
                "action": "Wait for one position to close OR raise MAX_SAME_SIDE_USD_POSITIONS in tools/safeguards.py (default 3, recommended: keep at 3 for account < $2000).",
            },
            "CLUSTER_CAP": {
                "explain": "Within correlation cluster (e.g. CRYPTO {BTC,ETH} or PRECIOUS {XAU,XAG}), bot already has 2 same-direction trades. Adding a 3rd = effectively 3× exposure to the same move.",
                "action": "Wait for one cluster position to close. This protects you from amplified drawdowns in correlated moves.",
            },
            "TIER_CAP": {
                "explain": "Account equity tier cap reached. Currently set to max 10 simultaneous open positions (operator-chosen). Adding more = risk overload.",
                "action": "Wait for trades to close. Or edit EQUITY_TIERS in tools/safeguards.py to raise cap.",
            },
            "PER_SYMBOL_LOSS": {
                "explain": "This symbol has lost >1% of equity today. Bot blocks further trades on it to prevent revenge trading + concentration in losing pair.",
                "action": "Symbol resets at midnight IST. Or close negative positions on this symbol to reduce loss, then it may re-allow.",
            },
            "TIME_BLACKOUT": {
                "explain": "Current time falls in known thin-liquidity / weekend-gap window (Sun pre-open, Fri close, daily session opens 13:00/18:30 IST).",
                "action": "Wait for the blackout to end. Reasons: spread spikes 2-3× during these windows.",
            },
            "NEWS_BLACKOUT": {
                "explain": "High-impact news event scheduled within -60 / +30 min window. Bot pauses to avoid post-news whipsaw.",
                "action": "Wait for the news event + 30 min. Check config/news_calendar.json for upcoming events.",
            },
            "DRAWDOWN": {
                "explain": "Daily drawdown limit (5% of starting equity) has been breached. ALL trading paused until midnight IST.",
                "action": "Day is done. Wait for midnight reset. Review closed trades to understand what caused the drawdown.",
            },
            "SPREAD": {
                "explain": "Spread exceeds threshold (% of ATR). Trading in wide spread = unfavorable entry.",
                "action": "Wait for spread to normalize. Note: this layer is DISABLED by default per operator policy.",
            },
            "STRATEGY_FILTER": {
                "explain": "Signal's tv_strategy tag is not in ALLOWED_STRATEGIES whitelist. Either signal source is unknown or whitelist needs update.",
                "action": "Check tools/python_signal_executor.py ALLOWED_STRATEGIES set. Operator policy: only Rocket Prime signals allowed.",
            },
            "STALE": {
                "explain": "Signal file exists but its timestamp is older than 90 seconds. Executor refuses to act on old data.",
                "action": "Usually means executor was down when signal arrived. Health Watchdog should respawn within 60 sec.",
            },
            "SAFEGUARD_OTHER": {
                "explain": "Safeguard layer blocked the trade for an uncategorized reason.",
                "action": "Check the reason text for details.",
            },
        }
        for it in items:
            d = CAT_DETAILS.get(it["category"], CAT_DETAILS["SAFEGUARD_OTHER"])
            it["explain"] = d["explain"]
            it["action"] = d["action"]

        return {"items": items, "by_category": by_cat, "count": len(items)}
    except Exception as e:
        return {"items": [], "by_category": {}, "error": str(e)}


def get_telegram_pending() -> dict:
    """Pending Telegram BUY/SELL prompts awaiting operator tap.
    Reads logs/pending_signals.jsonl written by telegram_direction_helper.
    """
    p = ROOT / "logs" / "pending_signals.jsonl"
    if not p.exists():
        return {"pending_count": 0, "items": []}
    try:
        lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
        pending = []
        now = time.time()
        for line in lines:
            try:
                row = json.loads(line)
                if row.get("resolved"):
                    continue
                # Only show non-stale (under 20 min old)
                ts = row.get("ts") or 0
                age_s = now - ts
                if age_s > 1200:
                    continue
                pending.append({
                    "sig_id": row.get("sig_id"),
                    "symbol": row.get("symbol"),
                    "tf": row.get("tf"),
                    "age_s": int(age_s),
                })
            except Exception:
                pass
        return {"pending_count": len(pending), "items": pending}
    except Exception as e:
        return {"error": str(e)}


def get_trading_mode() -> dict:
    """Current trading mode flags — what's enabled/disabled per ops policy."""
    env_path = ROOT / "config" / ".env"
    # 2026-08-22: read actual signal source instead of hardcoded TV pivot
    try:
        from config import settings as _s
        flags = {
            "tv_signal_mode": bool((getattr(_s, "TV_SIGNAL", {}) or {}).get("enabled", False)),
            "local_brain_mode": not ((getattr(_s, "TV_SIGNAL", {}) or {}).get("enabled", False)),
        }
    except Exception:
        flags = {"tv_signal_mode": True, "local_brain_mode": False}
    flags.update({
        "inferred_enabled": False,      # banned 2026-05-13 after 2 wrong-direction trades
        "chart_ocr_enabled": False,     # TV-only feature; off in local brain mode
        "telegram_tap_fallback": False, # TV-only fallback; off in local brain mode
    })
    try:
        if env_path.exists():
            txt = env_path.read_text(encoding="utf-8", errors="replace")
            for line in txt.splitlines():
                line = line.strip()
                if line.startswith("TV_ALLOW_INFERRED="):
                    val = line.split("=", 1)[1].strip()
                    flags["inferred_enabled"] = val in ("1", "true", "TRUE", "yes")
                elif line.startswith("CHART_OCR_ENABLED="):
                    flags["chart_ocr_enabled"] = (line.split("=", 1)[1].strip()
                                                  not in ("0", "false", "FALSE", "no")) and flags["tv_signal_mode"]
    except Exception:
        pass
    return flags


def get_brain_state() -> dict:
    sp = ROOT / "logs" / "brain_state.json"
    if not sp.exists():
        return {"status": "no state file"}
    try:
        data = json.loads(sp.read_text(encoding="utf-8"))
        return {
            "halted": data.get("halted", False),
            "trading_paused": data.get("trading_paused", False),
            "drawdown_lockout_until": data.get("drawdown_lockout_until"),
            "start_of_day_equity": data.get("start_of_day_equity"),
            "last_signal_count": len(data.get("last_signal_per_symbol") or {}),
            "recent_results_count": len(data.get("recent_results") or []),
        }
    except Exception as e:
        return {"error": str(e)}


def get_schtasks() -> list:
    try:
        out = subprocess.check_output(["schtasks", "/Query", "/FO", "CSV", "/V"],
                                       timeout=15, creationflags=_CREATE_NO_WINDOW
                                       ).decode("utf-8", errors="replace")
        lines = out.splitlines()
        if not lines:
            return []
        header = [h.strip('"') for h in lines[0].split('","')]
        try:
            name_i = header.index("TaskName"); run_i = header.index("Next Run Time"); stat_i = header.index("Status")
        except ValueError:
            return []
        results = []
        for line in lines[1:]:
            parts = [p.strip('"') for p in line.split('","')]
            if len(parts) <= max(name_i, run_i, stat_i):
                continue
            if "TrendMaster" not in parts[name_i]:
                continue
            results.append({"name": parts[name_i].replace("\\TrendMaster ", "").replace("\\", ""),
                            "next_run": parts[run_i], "status": parts[stat_i]})
        return sorted(results, key=lambda x: x["next_run"])
    except Exception as e:
        return [{"error": str(e)}]


def get_log_tail(name: str, n: int = 200) -> list:
    valid = {"executor": "python_executor.log", "trailing": "trailing_stop.log",
             "receiver": "tv_webhook.log", "watchdog": "process_watchdog.log",
             "outcomes": "signal_outcome_collector.log", "dashboard": "dashboard.log",
             "renewer": "alert_renewer.log", "brain": "trend_master_brain.out"}
    if name not in valid:
        return [f"unknown log: {name}"]
    p = LOG_DIR / valid[name]
    if not p.exists():
        return [f"log file not found: {p.name}"]
    try:
        return p.read_text(encoding="utf-8", errors="replace").splitlines()[-n:]
    except Exception as e:
        return [f"read error: {e}"]


def get_backtest_reports() -> list:
    if not REPORTS_DIR.exists():
        return []
    out = []
    for f in REPORTS_DIR.glob("*.json"):
        try:
            out.append({"name": f.name, "size_kb": round(f.stat().st_size / 1024, 1),
                        "mtime": datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y-%m-%d %H:%M")})
        except Exception:
            continue
    return sorted(out, key=lambda x: x["mtime"], reverse=True)[:30]


def get_postmortems() -> list:
    if not POSTMORTEMS_DIR.exists():
        return []
    return [{"name": f.name, "size_kb": round(f.stat().st_size / 1024, 1)}
            for f in sorted(POSTMORTEMS_DIR.glob("*.md"), reverse=True)[:20]]


# ── 2026-08-22 dashboard merge: collectors ported from unified_dashboard.py ──
def get_brain_liveness() -> dict:
    """Brain liveness via brain_state.json heartbeat (last_saved_at freshness).
    Lightweight — no process scanning per poll."""
    sp = LOG_DIR / "brain_state.json"
    out = {"pids": [], "alive": False, "boot_line": "", "last_saved_ago_s": None}
    log_p = LOG_DIR / "trend_master_brain.out"
    if log_p.exists():
        try:
            for ln in reversed(log_p.read_text(encoding="utf-8", errors="replace").splitlines()):
                if "brain online" in ln:
                    out["boot_line"] = ln.strip()
                    break
        except Exception:
            pass
    if not sp.exists():
        return out
    try:
        data = json.loads(sp.read_text(encoding="utf-8"))
        saved = float(data.get("last_saved_at") or 0)
        if saved:
            ago = max(0, int(time.time() - saved))
            out["last_saved_ago_s"] = ago
            # brain saves state every cycle (~3s); 120s slack for GC pauses
            out["alive"] = ago < 120
    except Exception:
        pass
    return out


def get_configs() -> dict:
    """TEAM_PARAMS summary from ai_trading_agents.team_params."""
    try:
        sys.path.insert(0, str(ROOT))
        from ai_trading_agents.team_params import TEAM_PARAMS, SYMBOL_TO_TEAM
        teams = TEAM_PARAMS or {}
        return {
            "teams": {k: {kk: vv for kk, vv in v.items() if isinstance(vv, (int, float, str, bool))}
                      for k, v in list(teams.items())[:12]},
            "pair_count": len(SYMBOL_TO_TEAM or {}),
        }
    except Exception as e:
        return {"error": str(e)}


def get_skills() -> list:
    """Installed skill folders under docs/skills (unified /api/skills)."""
    sd = ROOT / "docs" / "skills"
    if not sd.exists():
        return []
    out = []
    for d in sorted(sd.iterdir()):
        if d.is_dir() and (d / "SKILL.md").exists():
            try:
                desc = ""
                for ln in (d / "SKILL.md").read_text(encoding="utf-8", errors="replace").splitlines():
                    if ln.startswith("description:") or ln.startswith("# "):
                        desc = ln.split(":", 1)[-1].strip()[:110]
                        break
                out.append({"name": d.name, "desc": desc})
            except Exception:
                continue
    return out


def get_mission_state() -> dict:
    """System process matrix (mission_control /api/mission equivalent)."""
    counts = {k: 0 for k in ("mt5", "brain", "webhook_receiver", "dashboard",
                             "executor", "trailing", "watchdog")}
    try:
        import psutil
        for proc in psutil.process_iter(["name", "cmdline"]):
            try:
                info = proc.info
                name = (info.get("name") or "").lower()
                if name == "terminal64.exe":
                    counts["mt5"] += 1
                    continue
                if name not in ("python.exe", "pythonw.exe"):
                    continue
                low = " ".join(info.get("cmdline") or []).lower()
                if "trend_master_brain" in low:
                    counts["brain"] += 1
                elif "tv_webhook_receiver" in low:
                    counts["webhook_receiver"] += 1
                elif "dashboard_server" in low:
                    counts["dashboard"] += 1
                elif "python_signal_executor" in low:
                    counts["executor"] += 1
                elif "trailing_stop_manager" in low:
                    counts["trailing"] += 1
                elif "process_watchdog" in low:
                    counts["watchdog"] += 1
            except Exception:
                continue
    except Exception as e:
        return {"error": str(e)}
    return {"counts": counts}


def get_equity_history(hours: int = 24) -> list:
    """Return equity log points from background logger."""
    if not EQUITY_LOG_PATH.exists():
        return []
    cutoff = time.time() - hours * 3600
    out = []
    try:
        for line in EQUITY_LOG_PATH.open(encoding="utf-8"):
            try:
                o = json.loads(line)
                if o.get("ts", 0) >= cutoff:
                    out.append(o)
            except Exception:
                continue
    except Exception:
        pass
    return out


def get_tv_alerts_status() -> dict:
    """Return TV alerts list from cache (refreshed every 5 min by background thread)."""
    return _tv_alerts_cache.get("data") or {"alerts": [], "cached_at": None, "msg": "loading..."}


# ─── Trade actions ──────────────────────────────────────────────────────
def close_one_position(ticket: int) -> dict:
    if not mt5.initialize():
        return {"ok": False, "error": "mt5.initialize failed"}
    pos = mt5.positions_get(ticket=ticket) or []
    if not pos:
        mt5.shutdown()
        return {"ok": False, "error": f"position {ticket} not found"}
    p = pos[0]
    info = mt5.symbol_info(p.symbol); tick = mt5.symbol_info_tick(p.symbol)
    if not info or not tick:
        mt5.shutdown()
        return {"ok": False, "error": "no symbol info"}
    is_buy = p.type == mt5.ORDER_TYPE_BUY
    request = {"action": mt5.TRADE_ACTION_DEAL, "symbol": p.symbol, "volume": p.volume,
               "type": mt5.ORDER_TYPE_SELL if is_buy else mt5.ORDER_TYPE_BUY,
               "position": p.ticket, "price": tick.bid if is_buy else tick.ask,
               "deviation": 50, "magic": p.magic, "comment": "DASH-CLOSE",
               "type_time": mt5.ORDER_TIME_GTC, "type_filling": mt5.ORDER_FILLING_IOC}
    res = mt5.order_send(request)
    mt5.shutdown()
    if res and res.retcode == mt5.TRADE_RETCODE_DONE:
        return {"ok": True, "profit": round(p.profit, 2)}
    return {"ok": False, "error": res.comment if res else "send failed"}


def modify_position_sltp(ticket: int, sl: float, tp: float) -> dict:
    if not mt5.initialize():
        return {"ok": False, "error": "mt5.initialize failed"}
    pos = mt5.positions_get(ticket=ticket) or []
    if not pos:
        mt5.shutdown()
        return {"ok": False, "error": "position not found"}
    p = pos[0]
    info = mt5.symbol_info(p.symbol)
    request = {"action": mt5.TRADE_ACTION_SLTP, "position": p.ticket, "symbol": p.symbol,
               "sl": round(float(sl), info.digits) if sl else 0.0,
               "tp": round(float(tp), info.digits) if tp else 0.0,
               "magic": p.magic}
    res = mt5.order_send(request)
    mt5.shutdown()
    if res and res.retcode == mt5.TRADE_RETCODE_DONE:
        return {"ok": True}
    return {"ok": False, "error": res.comment if res else "send failed",
            "retcode": res.retcode if res else None}


def close_all_positions() -> dict:
    """Close every open position. Patched 2026-05-07 — adds:
      - explicit MT5 login from .env (fixes silent fail when terminal not yet authenticated)
      - per-position FOK fallback (some brokers reject IOC)
      - mt5_lock acquisition to avoid race with equity_logger thread
      - no shutdown (other threads share the connection)
      - per-position result detail in response so frontend can display reasons
    """
    import os
    from dotenv import load_dotenv
    _ROOT = Path(__file__).parent.parent
    for _cand in (_ROOT / ".env", _ROOT / "config" / ".env"):
        if _cand.exists():
            load_dotenv(_cand, override=True)
            break

    with _mt5_lock:
        try:
            login = os.getenv("MT5_LOGIN", "").strip()
            password = os.getenv("MT5_PASSWORD", "").strip()
            server = os.getenv("MT5_SERVER", "").strip()
            init_ok = mt5.initialize(login=int(login), password=password, server=server) if login else mt5.initialize()
            if not init_ok:
                err = mt5.last_error()
                log.warning("close_all: mt5.initialize failed: %s", err)
                return {"ok": False, "error": f"mt5.initialize failed: {err}", "closed": 0, "failed": 0, "total": 0}

            pos = mt5.positions_get() or []
            results = []
            closed = 0
            failed = 0
            for p in pos:
                info = mt5.symbol_info(p.symbol)
                tick = mt5.symbol_info_tick(p.symbol)
                if not info or not tick:
                    failed += 1
                    results.append({"ticket": p.ticket, "ok": False, "error": "no symbol info/tick"})
                    continue
                is_buy = p.type == mt5.ORDER_TYPE_BUY
                base_req = {
                    "action": mt5.TRADE_ACTION_DEAL,
                    "symbol": p.symbol,
                    "volume": p.volume,
                    "type": mt5.ORDER_TYPE_SELL if is_buy else mt5.ORDER_TYPE_BUY,
                    "position": p.ticket,
                    "price": tick.bid if is_buy else tick.ask,
                    "deviation": 50,
                    "magic": p.magic,
                    "comment": "PANIC-CLOSE",
                    "type_time": mt5.ORDER_TIME_GTC,
                }
                # IOC primary
                req = {**base_req, "type_filling": mt5.ORDER_FILLING_IOC}
                res = mt5.order_send(req)
                if res is None or res.retcode != mt5.TRADE_RETCODE_DONE:
                    # FOK fallback
                    req["type_filling"] = mt5.ORDER_FILLING_FOK
                    res2 = mt5.order_send(req)
                    if res2 and res2.retcode == mt5.TRADE_RETCODE_DONE:
                        closed += 1
                        results.append({"ticket": p.ticket, "ok": True, "filling": "FOK", "pnl": round(p.profit, 2)})
                    else:
                        failed += 1
                        err = (res2.comment if res2 else "no response") if res2 else (res.comment if res else "no response")
                        results.append({"ticket": p.ticket, "ok": False,
                                        "retcode_ioc": res.retcode if res else None,
                                        "retcode_fok": res2.retcode if res2 else None,
                                        "error": err})
                else:
                    closed += 1
                    results.append({"ticket": p.ticket, "ok": True, "filling": "IOC", "pnl": round(p.profit, 2)})

            log.info("close_all: closed=%d failed=%d total=%d", closed, failed, len(pos))
            try:
                send_telegram(f"<b>PANIC CLOSE issued from Dashboard</b>\nClosed: {closed}/{len(pos)}, Failed: {failed}")
            except Exception:
                pass
            # NOTE: do NOT call mt5.shutdown() — other threads share this connection.
            return {"ok": True, "closed": closed, "failed": failed, "total": len(pos), "details": results}
        except Exception as e:
            log.exception("close_all_positions raised")
            return {"ok": False, "error": f"exception: {e}", "closed": 0, "failed": 0, "total": 0}


def csv_export_deals(hours: int = 168) -> str:
    if not mt5.initialize():
        return ""
    since = datetime.now() - timedelta(hours=hours)
    deals = mt5.history_deals_get(since, datetime.now()) or []
    closed = [d for d in deals if d.entry == mt5.DEAL_ENTRY_OUT]
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["time_utc", "symbol", "direction", "lots", "price", "profit",
                "magic", "comment", "ticket"])
    for d in sorted(closed, key=lambda x: x.time):
        w.writerow([datetime.fromtimestamp(d.time).strftime("%Y-%m-%d %H:%M:%S"),
                    d.symbol, "BUY" if d.type == 0 else "SELL",
                    d.volume, d.price, round(d.profit, 2),
                    d.magic, d.comment, d.ticket])
    mt5.shutdown()
    return buf.getvalue()


def send_telegram(text: str) -> bool:
    try:
        from ai_trading_agents.telegram_notifier import get_notifier
        tg = get_notifier()
        return bool(tg and tg.enabled and tg.send(text))
    except Exception:
        return False


# ─── Background threads ─────────────────────────────────────────────────
_mt5_lock = Lock()


def _equity_logger_loop():
    """Logs balance/equity every 60 sec. Uses lock to avoid contention with HTTP requests."""
    log.info("Equity logger thread started")
    while True:
        try:
            with _mt5_lock:
                mt5.initialize()
                ai = mt5.account_info()
                pos = mt5.positions_get() or []
                if ai:
                    EQUITY_LOG_PATH.open("a", encoding="utf-8").write(
                        json.dumps({"ts": int(time.time()), "balance": ai.balance,
                                    "equity": ai.equity, "n_pos": len(pos),
                                    "floating": round(sum(p.profit for p in pos), 2)}) + "\n"
                    )
                # NOTE: do NOT call mt5.shutdown() here — it kills connection
                # for any concurrent HTTP request handler. mt5.initialize() is
                # idempotent and cheap if already inited.
        except Exception as e:
            log.warning("equity logger failed: %s", e)
        time.sleep(60)


def _refresh_tv_alerts_now(reactivate: bool = False) -> dict:
    """One-shot TV alerts refresh. Used by /api/refresh-tv-alerts endpoint
    so operator can force-update the dashboard table without waiting for
    the 5-min background loop. If reactivate=True, also flips any inactive
    RP alerts back to active via TV's restart_alerts API.
    """
    try:
        from playwright.sync_api import sync_playwright
        PROFILE = ROOT / "tools" / "tv_alert_setup" / "_browser_profile"
        ROCKET_PRIME = "PUB;56f0fb74de7f4eed9325b987428b727e"
        hdrs = {"Origin": "https://www.tradingview.com",
                "Referer": "https://www.tradingview.com/chart/",
                "Content-Type": "application/json"}
        with sync_playwright() as p:
            ctx = p.chromium.launch_persistent_context(user_data_dir=str(PROFILE), headless=True)
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            page.goto("https://www.tradingview.com/chart/", wait_until="domcontentloaded", timeout=30_000)
            time.sleep(2)
            api = ctx.request
            r = api.post("https://pricealerts.tradingview.com/list_alerts",
                         data=json.dumps({"payload": {"limit": 5000}}),
                         headers=hdrs, timeout=15_000)
            alerts = r.json().get("r", [])

            # Optionally reactivate any inactive RP alerts
            reactivated = []
            if reactivate:
                for a in alerts:
                    cond = a.get("condition") or {}
                    if cond.get("type") != "pine_alert":
                        continue
                    if ((cond.get("series") or [{}])[0]).get("pine_id") != ROCKET_PRIME:
                        continue
                    if not a.get("active"):
                        aid = a["alert_id"]
                        try:
                            rr = api.post("https://pricealerts.tradingview.com/restart_alerts",
                                          data=json.dumps({"payload": {"alert_ids": [aid]}}),
                                          headers=hdrs, timeout=10_000)
                            if rr.status == 200 and '"s":"ok"' in rr.text():
                                reactivated.append(aid)
                        except Exception:
                            pass
                # Refetch after reactivation so the cache reflects new state
                if reactivated:
                    time.sleep(1)
                    r = api.post("https://pricealerts.tradingview.com/list_alerts",
                                 data=json.dumps({"payload": {"limit": 5000}}),
                                 headers=hdrs, timeout=15_000)
                    alerts = r.json().get("r", [])

            ctx.close()

        # Rebuild cache (same logic as the loop)
        now_unix = int(time.time())
        rp_alerts = []
        ROCKET_PRIME = "PUB;56f0fb74de7f4eed9325b987428b727e"
        for a in alerts:
            cond = a.get("condition") or {}
            if cond.get("type") != "pine_alert":
                continue
            if ((cond.get("series") or [{}])[0]).get("pine_id") != ROCKET_PRIME:
                continue
            sym_raw = a.get("symbol", "")
            try:
                sym = json.loads(sym_raw[1:]).get("symbol", sym_raw) if sym_raw.startswith("=") else sym_raw
            except Exception:
                sym = sym_raw
            exp_str = a.get("expiration", "")
            try:
                exp = datetime.fromisoformat(exp_str.replace("Z", "+00:00"))
                days_left = round((exp - datetime.now(tz=exp.tzinfo)).total_seconds() / 86400, 1)
            except Exception:
                days_left = None
            wh = a.get("web_hook") or ""
            lf = a.get("last_fire_time")
            lf_min_ago = None
            if lf:
                try:
                    if isinstance(lf, str) and "T" in lf:
                        lf_dt = datetime.fromisoformat(lf.replace("Z", "+00:00"))
                        lf_min_ago = int((now_unix - lf_dt.timestamp()) / 60)
                    else:
                        lf_min_ago = int((now_unix - int(lf)) / 60)
                except Exception:
                    lf_min_ago = None
            rp_alerts.append({
                "id": a.get("alert_id"), "symbol": sym,
                "tf": str(a.get("resolution", "")),
                "active": a.get("active"),
                "webhook_ok": "secret=" in wh,
                "days_left": days_left,
                "last_fire_min_ago": lf_min_ago,
            })
        _tv_alerts_cache["data"] = {"alerts": rp_alerts, "cached_at": now_unix,
                                      "total": len(rp_alerts)}
        return {"ok": True, "total": len(rp_alerts), "reactivated": reactivated}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _tv_alerts_refresh_loop():
    """Refresh TV alerts cache every 5 min (so dashboard /api/status is fast).

    2026-05-13: ALSO auto-reactivates any inactive RP alerts each cycle.
    Operator policy: alerts must stay always-active. After webhook delivery
    failures TV auto-deactivates → this thread heals automatically without
    operator intervention.
    """
    log.info("TV alerts refresh thread started (with auto-heal)")
    while True:
        try:
            from playwright.sync_api import sync_playwright
            PROFILE = ROOT / "tools" / "tv_alert_setup" / "_browser_profile"
            ROCKET_PRIME = "PUB;56f0fb74de7f4eed9325b987428b727e"
            hdrs = {"Origin": "https://www.tradingview.com",
                    "Referer": "https://www.tradingview.com/chart/",
                    "Content-Type": "application/json"}
            reactivated_ids = []
            with sync_playwright() as p:
                ctx = p.chromium.launch_persistent_context(user_data_dir=str(PROFILE), headless=True)
                page = ctx.pages[0] if ctx.pages else ctx.new_page()
                page.goto("https://www.tradingview.com/chart/", wait_until="domcontentloaded", timeout=30_000)
                time.sleep(2)
                api = ctx.request
                r = api.post("https://pricealerts.tradingview.com/list_alerts",
                             data=json.dumps({"payload": {"limit": 5000}}),
                             headers=hdrs, timeout=15_000)
                alerts = r.json().get("r", [])

                # AUTO-HEAL: reactivate any inactive RP alerts
                inactive_rp = []
                for a in alerts:
                    cond = a.get("condition") or {}
                    if cond.get("type") != "pine_alert":
                        continue
                    if ((cond.get("series") or [{}])[0]).get("pine_id") != ROCKET_PRIME:
                        continue
                    if not a.get("active"):
                        inactive_rp.append(a["alert_id"])
                if inactive_rp:
                    log.info("AUTO-HEAL: reactivating %d inactive RP alerts", len(inactive_rp))
                    for aid in inactive_rp:
                        try:
                            rr = api.post("https://pricealerts.tradingview.com/restart_alerts",
                                          data=json.dumps({"payload": {"alert_ids": [aid]}}),
                                          headers=hdrs, timeout=10_000)
                            if rr.status == 200 and '"s":"ok"' in rr.text():
                                reactivated_ids.append(aid)
                        except Exception as _e:
                            log.warning("reactivate %s failed: %s", aid, _e)
                    # Refetch updated list
                    if reactivated_ids:
                        time.sleep(1)
                        r = api.post("https://pricealerts.tradingview.com/list_alerts",
                                     data=json.dumps({"payload": {"limit": 5000}}),
                                     headers=hdrs, timeout=15_000)
                        alerts = r.json().get("r", [])
                ctx.close()
            if reactivated_ids:
                log.info("AUTO-HEAL: reactivated %d alerts", len(reactivated_ids))
            now_unix = int(time.time())
            rp_alerts = []
            for a in alerts:
                cond = a.get("condition") or {}
                if cond.get("type") != "pine_alert":
                    continue
                series = cond.get("series") or [{}]
                if series[0].get("pine_id") != ROCKET_PRIME:
                    continue
                sym_raw = a.get("symbol", "")
                try:
                    sym = json.loads(sym_raw[1:]).get("symbol", sym_raw) if sym_raw.startswith("=") else sym_raw
                except Exception:
                    sym = sym_raw
                exp_str = a.get("expiration", "")
                try:
                    exp = datetime.fromisoformat(exp_str.replace("Z", "+00:00"))
                    days_left = round((exp - datetime.now(tz=exp.tzinfo)).total_seconds() / 86400, 1)
                except Exception:
                    days_left = None
                wh = a.get("web_hook") or ""
                lf = a.get("last_fire_time")
                # last_fire_time can be either int (unix ts) or ISO string
                lf_min_ago = None
                if lf:
                    try:
                        if isinstance(lf, str) and "T" in lf:
                            lf_dt = datetime.fromisoformat(lf.replace("Z", "+00:00"))
                            lf_min_ago = int((now_unix - lf_dt.timestamp()) / 60)
                        else:
                            lf_min_ago = int((now_unix - int(lf)) / 60)
                    except Exception:
                        lf_min_ago = None
                rp_alerts.append({
                    "id": a.get("alert_id"), "symbol": sym,
                    "tf": str(a.get("resolution", "")),
                    "active": a.get("active"),
                    "webhook_ok": "secret=" in wh,
                    "days_left": days_left,
                    "last_fire_min_ago": lf_min_ago,
                })
            _tv_alerts_cache["data"] = {"alerts": rp_alerts, "cached_at": now_unix,
                                          "total": len(rp_alerts)}
            log.info("TV alerts cache refreshed: %d alerts", len(rp_alerts))
        except Exception as e:
            log.warning("TV alerts refresh failed: %s", e)
            _tv_alerts_cache["data"] = {"alerts": [], "cached_at": int(time.time()),
                                          "error": str(e)}
        time.sleep(300)


# ─── HTTP server ────────────────────────────────────────────────────────
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

PORT = 8765

DASHBOARD_HTML = r"""<!DOCTYPE html>
<html lang="en"><head><title>TrendMaster</title>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
:root { --bg: #0f1419; --bg2: #1a212c; --bg3: #243040; --border: #2a3140; --text: #e6e6e6; --muted: #8a9aa8; --acc: #4fc3f7; --pos: #4caf50; --neg: #f44336; --warn: #ffa726; }
[data-theme="light"] { --bg: #fafafa; --bg2: #fff; --bg3: #eef2f7; --border: #d0d7de; --text: #1f2328; --muted: #57606a; --acc: #0969da; --pos: #1a7f37; --neg: #cf222e; --warn: #bf8700; }
* { box-sizing: border-box; }
body { font-family: -apple-system, sans-serif; margin: 0; padding: 8px; background: var(--bg); color: var(--text); font-size: 13px; }
h1 { color: var(--acc); margin: 4px 0; font-size: 18px; }
h2 { color: var(--acc); margin: 8px 0 4px; font-size: 13px; border-bottom: 1px solid var(--border); padding-bottom: 3px; }
.tabs { display: flex; flex-wrap: wrap; gap: 2px; margin: 8px 0; border-bottom: 2px solid var(--border); }
.tab { padding: 7px 12px; cursor: pointer; background: var(--bg2); color: var(--muted); border: 1px solid var(--border); border-bottom: none; border-radius: 4px 4px 0 0; font-size: 12px; }
.tab.active { background: var(--bg3); color: var(--acc); font-weight: bold; }
.section { display: none; }
.section.active { display: block; }
.grid { display: grid; gap: 8px; }
.g3 { grid-template-columns: 1fr 1fr 1fr; }
.g2 { grid-template-columns: 1fr 1fr; }
@media (max-width: 800px) { .g3, .g2 { grid-template-columns: 1fr; } }
.panel { background: var(--bg2); padding: 10px; border-radius: 6px; border: 1px solid var(--border); }
table { width: 100%; border-collapse: collapse; font-size: 12px; }
th, td { padding: 4px 6px; text-align: left; border-bottom: 1px solid var(--border); }
th { background: var(--bg3); color: var(--acc); position: sticky; top: 0; }
.pos { color: var(--pos); font-weight: bold; }
.neg { color: var(--neg); font-weight: bold; }
.ok { color: var(--pos); font-weight: bold; }
.bad { color: var(--neg); font-weight: bold; }
.warn { color: var(--warn); font-weight: bold; }
.stat { display: inline-block; margin: 2px 10px 2px 0; }
.stat-label { color: var(--muted); font-size: 10px; text-transform: uppercase; }
.stat-val { font-size: 16px; font-weight: bold; }
.switch { display: flex; justify-content: space-between; align-items: center; padding: 4px 0; border-bottom: 1px solid var(--bg3); }
.toggle { position: relative; display: inline-block; width: 38px; height: 20px; }
.toggle input { opacity: 0; width: 0; height: 0; }
.slider { position: absolute; cursor: pointer; top: 0; left: 0; right: 0; bottom: 0; background-color: #444; transition: .3s; border-radius: 20px; }
.slider:before { position: absolute; content: ""; height: 14px; width: 14px; left: 3px; bottom: 3px; background-color: white; transition: .3s; border-radius: 50%; }
input:checked + .slider { background-color: var(--pos); }
input:checked + .slider:before { transform: translateX(18px); }
button { background: var(--acc); color: var(--bg); border: none; padding: 6px 10px; border-radius: 4px; cursor: pointer; font-weight: bold; margin: 3px 2px; font-size: 11px; }
button:hover { opacity: 0.85; }
button.danger { background: var(--neg); color: white; }
button.warn { background: var(--warn); color: var(--bg); }
button.tiny { padding: 2px 6px; font-size: 10px; }
.pair-grid { display: grid; grid-template-columns: 1fr 1fr 1fr 1fr; gap: 3px; }
@media (max-width: 800px) { .pair-grid { grid-template-columns: 1fr 1fr; } }
.pair-row { display: flex; justify-content: space-between; align-items: center; padding: 3px 6px; background: var(--bg3); border-radius: 3px; font-size: 11px; }
input[type=number], input[type=text] { background: var(--bg3); color: var(--text); border: 1px solid var(--border); padding: 3px 5px; border-radius: 3px; width: 90px; font-size: 11px; }
select { background: var(--bg3); color: var(--text); border: 1px solid var(--border); padding: 4px; border-radius: 3px; }
.timestamp { color: var(--muted); font-size: 10px; }
.health-grid { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 6px; }
@media (max-width: 800px) { .health-grid { grid-template-columns: 1fr 1fr; } }
.health-card { background: var(--bg3); padding: 6px; border-radius: 3px; text-align: center; }
.health-card .label { font-size: 10px; color: var(--muted); }
.health-card .val { font-size: 14px; font-weight: bold; }
.chip { display:inline-block; padding:3px 8px; margin:2px; border-radius:10px; font-size:11px; font-weight:bold; }
.hidden { display: none; }
.muted { color: var(--muted); }
.chip.ok { background: rgba(34,197,94,0.15); color: var(--pos); border:1px solid rgba(34,197,94,0.3); }
.chip.warn { background: rgba(234,179,8,0.18); color: #ca8a04; border:1px solid rgba(234,179,8,0.35); }
.chip.bad { background: rgba(239,68,68,0.15); color: var(--neg); border:1px solid rgba(239,68,68,0.3); }
pre { background: #0a0e13; color: #b6cdda; padding: 8px; border-radius: 3px; max-height: 600px; overflow-y: auto; font-size: 11px; line-height: 1.4; font-family: Consolas, monospace; white-space: pre-wrap; word-break: break-word; }
.theme-btn { float: right; margin-right: 8px; background: var(--bg3); color: var(--text); }
canvas { max-width: 100%; }
.bar-cell { background: linear-gradient(90deg, var(--bg3) 0%, var(--bg3) var(--bar-pct), transparent var(--bar-pct)); }
</style>
</head><body data-theme="dark">

<h1>TrendMaster Dashboard
<button class="theme-btn" onclick="toggleTheme()" id="theme-btn">Light</button>
<span class="timestamp" id="ts"></span></h1>

<div class="grid g2">
  <div class="panel">
    <h2>Account</h2>
    <div id="account"></div>
  </div>
  <div class="panel">
    <h2>Pipeline Health</h2>
    <div class="health-grid" id="health"></div>
    <div id="trading-mode" style="margin-top:10px;padding:8px;background:rgba(0,0,0,0.05);border-radius:6px"></div>
  </div>
</div>

<!-- 2026-05-14: Recently Blocked Signals — show WHY trades didn't fire -->
<div class="panel" style="margin-top:14px">
  <h2>Recently Blocked Signals <span id="skips-summary" style="font-size:13px;font-weight:normal;color:var(--muted)"></span></h2>
  <div style="font-size:12px;color:var(--muted);margin-bottom:6px">
    Last 30 skip events from <code>logs/python_executor.log</code> — operator can see exactly why a signal didn't trade.
  </div>
  <table>
    <thead>
      <tr><th>Time</th><th>Sym</th><th>Dir</th><th>Layer</th><th>Reason</th></tr>
    </thead>
    <tbody id="skips-rows"></tbody>
  </table>
</div>

<div class="tabs">
  <div class="tab active" onclick="showTab(event,'overview')">Overview</div>
  <div class="tab" onclick="showTab(event,'analytics')">Analytics</div>
  <div class="tab" onclick="showTab(event,'market')">Market</div>
  <div class="tab" onclick="showTab(event,'signals')">Signals</div>
  <div class="tab" onclick="showTab(event,'control')">Control</div>
  <div class="tab" onclick="showTab(event,'tvalerts')">TV Alerts</div>
  <div class="tab" onclick="showTab(event,'tasks')">Schtasks</div>
  <div class="tab" onclick="showTab(event,'logs')">Logs</div>
  <div class="tab" onclick="showTab(event,'reports')">Reports</div>
  <div class="tab" onclick="showTab(event,'system')">System</div>
</div>

<!-- OVERVIEW: positions + recent closed -->
<div class="section active" id="overview">
  <div class="grid g2">
    <div class="panel">
      <h2>Open Positions <span id="pos-count"></span></h2>
      <table style="font-size:12px">
        <thead>
          <tr>
            <th>Sym</th><th>Dir</th><th>Leg</th><th>Lots</th>
            <th>Open</th><th>Now</th><th>SL</th><th>TP</th>
            <th>P/L</th><th>%</th><th>R</th>
            <th>Duration</th><th>Source</th><th>Actions</th>
          </tr>
        </thead>
        <tbody id="positions"></tbody>
      </table>
    </div>
    <div class="panel">
      <h2>Closed Trades 24h <span id="deal-stats" style="font-size:12px;font-weight:normal;color:var(--muted)"></span></h2>
      <table style="font-size:12px">
        <thead>
          <tr>
            <th>Time</th><th>Sym</th><th>Dir</th><th>Lots</th>
            <th>P/L</th><th>Duration</th><th>Exit</th>
          </tr>
        </thead>
        <tbody id="deals"></tbody>
      </table>
    </div>
  </div>
</div>

<!-- ANALYTICS: equity curve + per-pair P/L + duration -->
<div class="section" id="analytics">
  <div class="panel">
    <h2>Equity Curve (last 24h)</h2>
    <canvas id="equity-chart" height="80"></canvas>
  </div>
  <div class="grid g2" style="margin-top:8px">
    <div class="panel">
      <h2>Per-Pair P/L (last 7 days) <button class="tiny" onclick="downloadCSV()">Export CSV</button></h2>
      <table><thead><tr><th>Symbol</th><th>Closed</th><th>WR</th><th>Closed P/L</th><th>Open P/L</th><th>Total</th></tr></thead><tbody id="per-pair-pnl"></tbody></table>
    </div>
    <div class="panel">
      <h2>Trade Duration Stats</h2>
      <table><thead><tr><th>Leg</th><th>Count</th><th>Avg min</th><th>Median min</th><th>Max min</th></tr></thead><tbody id="duration"></tbody></table>
    </div>
  </div>
</div>

<!-- MARKET: spread monitor + news calendar -->
<div class="section" id="market">
  <div class="grid g2">
    <div class="panel">
      <h2>Live Spread Monitor</h2>
      <table><thead><tr><th>Sym</th><th>Bid</th><th>Ask</th><th>Spread (pts)</th><th>Spread/ATR%</th></tr></thead><tbody id="spread"></tbody></table>
    </div>
    <div class="panel">
      <h2>News Calendar (next 24h, high impact)</h2>
      <table><thead><tr><th>Time</th><th>Cur</th><th>Event</th><th>In</th></tr></thead><tbody id="news"></tbody></table>
    </div>
  </div>
</div>

<!-- SIGNALS: per-symbol + recent + brain learning -->
<div class="section" id="signals">
  <div class="grid g2">
    <div class="panel">
      <h2>Per-Symbol Rocket Prime Stats</h2>
      <table><thead><tr><th>Symbol</th><th>Total fires</th><th>Last fire</th></tr></thead><tbody id="sig-by-symbol"></tbody></table>
    </div>
    <div class="panel">
      <h2>Recent Signals</h2>
      <table><thead><tr><th>Time</th><th>Sym</th><th>Dir</th><th>Conf</th><th>Strategy</th></tr></thead><tbody id="signals-list"></tbody></table>
    </div>
  </div>
  <div class="panel" style="margin-top:8px">
    <h2>Brain Learning State <span id="brain-total"></span></h2>
    <table><thead><tr><th>Class (sym:dir)</th><th>N</th><th>WR</th><th>Avg R</th><th>Total R</th><th>Status</th></tr></thead><tbody id="brain-classes"></tbody></table>
  </div>
</div>

<!-- CONTROL: switches + settings + actions + per-pair -->
<div class="section" id="control">
  <div class="grid g3">
    <div class="panel">
      <h2>Master Switches</h2>
      <div id="master"></div>
    </div>
    <div class="panel">
      <h2>Strategy Settings</h2>
      <div id="settings"></div>
    </div>
    <div class="panel">
      <h2>Actions</h2>
      <button class="danger" onclick="dashAction('/api/close-all','Close ALL positions?')">PANIC: Close All</button>
      <button class="warn" onclick="dashAction('/api/halt-all','HALT trading?')">HALT</button>
      <button onclick="dashAction('/api/resume')">Resume</button>
      <button onclick="dashAction('/api/restart-executor','Restart executor process?')">Restart Exec</button>
      <button onclick="dashAction('/api/restart-trailing','Restart trailing manager?')">Restart Trail</button>
      <!-- 2026-05-13 additions: webhook + telegram listener restart + OCR test + telegram pending clear -->
      <button onclick="dashAction('/api/restart-webhook','Restart TV webhook receiver?')">Restart Webhook</button>
      <button onclick="dashAction('/api/restart-telegram-listener','Restart Telegram listener?')">Restart Telegram Listener</button>
      <button onclick="testOcr()">Test OCR (EURUSD M15)</button>
      <button class="warn" onclick="dashAction('/api/clear-telegram-pending','Clear all pending Telegram operator prompts?')">Clear Pending Prompts</button>
      <button onclick="dashAction('/api/refresh-tv-alerts')">Refresh TV Alerts</button>
      <button class="warn" onclick="dashAction('/api/refresh-tv-alerts?reactivate=1','Reactivate all inactive RP alerts via TV API?')">Reactivate All RP Alerts</button>
      <button onclick="dashAction('/api/test-telegram')">Test Telegram</button>
      <button onclick="dashAction('/api/send-snapshot')">Send Snapshot</button>
      <div id="action-result" style="margin-top:8px; font-size:0.85em; color:#9cf; min-height:24px"></div>
    </div>
  </div>
  <div class="panel" style="margin-top:8px">
    <h2>Per-Pair Toggles</h2>
    <div class="pair-grid" id="pairs"></div>
  </div>
</div>

<!-- TV ALERTS -->
<div class="section" id="tvalerts">
  <div class="panel">
    <h2>TradingView Rocket Prime Alerts <span class="timestamp" id="tv-cache-ts"></span></h2>
    <table><thead><tr><th>Symbol</th><th>TF</th><th>Active</th><th>Webhook</th><th>Days left</th><th>Last fire</th></tr></thead><tbody id="tv-alerts"></tbody></table>
  </div>
</div>

<!-- TASKS -->
<div class="section" id="tasks">
  <div class="panel">
    <h2>TrendMaster Scheduled Tasks</h2>
    <table><thead><tr><th>Task</th><th>Next Run</th><th>Status</th></tr></thead><tbody id="schtasks"></tbody></table>
  </div>
</div>

<!-- LOGS -->
<div class="section" id="logs">
  <div class="panel">
    <h2>Log Viewer</h2>
    <select id="log-pick" onchange="loadLog()">
      <option value="executor">executor</option><option value="trailing">trailing</option>
      <option value="receiver">webhook receiver</option><option value="watchdog">watchdog</option>
      <option value="outcomes">outcome collector</option><option value="dashboard">dashboard</option>
      <option value="renewer">alert renewer</option><option value="brain">brain</option>
    </select>
    <button onclick="loadLog()">Refresh</button>
    <span class="timestamp" id="log-ts"></span>
    <pre id="log-content">(pick a log)</pre>
  </div>
</div>

<!-- REPORTS -->
<div class="section" id="reports">
  <div class="grid g2">
    <div class="panel">
      <h2>Backtest Reports</h2>
      <table><thead><tr><th>File</th><th>Size</th><th>Modified</th></tr></thead><tbody id="reports-list"></tbody></table>
    </div>
    <div class="panel">
      <h2>Postmortems</h2>
      <table><thead><tr><th>File</th><th>Size</th></tr></thead><tbody id="postmortems"></tbody></table>
    </div>
  </div>
</div>

<!-- SYSTEM: merged from unified_dashboard + mission_control (2026-08-22) -->
<div class="section" id="system">
  <div class="grid g2">
    <div class="panel">
      <h2>Process Matrix</h2>
      <table style="font-size:12px"><thead><tr><th>Component</th><th>Procs</th><th>Status</th></tr></thead><tbody id="mission-rows"></tbody></table>
    </div>
    <div class="panel">
      <h2>Brain Liveness</h2>
      <div id="brain-liveness" style="font-size:12px;font-family:monospace"></div>
    </div>
  </div>
  <div class="grid g2">
    <div class="panel">
      <h2>Team Configs</h2>
      <table style="font-size:11px"><thead><tr><th>Team</th><th>Params</th></tr></thead><tbody id="configs-rows"></tbody></table>
    </div>
    <div class="panel">
      <h2>Skills (docs/skills)</h2>
      <table style="font-size:11px"><thead><tr><th>Skill</th><th>Description</th></tr></thead><tbody id="skills-rows"></tbody></table>
    </div>
  </div>
</div>

<!-- Modal for SL/TP modify -->
<div id="sltp-modal" style="display:none;position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,0.7);z-index:1000;justify-content:center;align-items:center">
  <div style="background:var(--bg2);padding:20px;border-radius:8px;min-width:300px;border:1px solid var(--border)">
    <h2>Modify SL/TP for ticket <span id="modal-ticket"></span></h2>
    <div>Symbol: <span id="modal-sym"></span> | Open: <span id="modal-open"></span></div>
    <div style="margin:10px 0">
      <label>SL: <input type="number" step="0.00001" id="modal-sl"></label><br>
      <label>TP: <input type="number" step="0.00001" id="modal-tp"></label>
    </div>
    <button onclick="submitSLTP()">Save</button>
    <button onclick="closeModal()">Cancel</button>
  </div>
</div>

<script>
let lastEquity = null;
let equityChart = null;
const audioCtx = window.AudioContext ? new (window.AudioContext || window.webkitAudioContext)() : null;
function beep() { if (!audioCtx) return; const o=audioCtx.createOscillator(); const g=audioCtx.createGain(); o.connect(g); g.connect(audioCtx.destination); o.frequency.value=800; g.gain.value=0.1; o.start(); setTimeout(()=>{o.stop()}, 200); }
function toggleTheme() {
  const cur = document.body.getAttribute('data-theme');
  const next = cur === 'dark' ? 'light' : 'dark';
  document.body.setAttribute('data-theme', next);
  document.getElementById('theme-btn').textContent = next === 'dark' ? 'Light' : 'Dark';
  localStorage.setItem('theme', next);
}
const savedTheme = localStorage.getItem('theme'); if (savedTheme) { document.body.setAttribute('data-theme', savedTheme); document.getElementById('theme-btn').textContent = savedTheme === 'dark' ? 'Light' : 'Dark'; }

function showTab(e, id) {
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.section').forEach(s => s.classList.remove('active'));
  e.target.classList.add('active');
  document.getElementById(id).classList.add('active');
  if (id === 'logs' && document.getElementById('log-content').textContent === '(pick a log)') loadLog();
  if (id === 'analytics') drawEquityChart();
}
function tog(key, val) { return `<label class="toggle"><input type="checkbox" ${val?'checked':''} onchange="toggle('${key}', this.checked)"><span class="slider"></span></label>`; }
async function toggle(key, val) { await fetch('/api/toggle?key='+key+'&val='+val, {method:'POST'}); refresh(); }
async function setVal(key, val) { await fetch('/api/set?key='+key+'&val='+val, {method:'POST'}); }

// 2026-05-07 — unified action handler with confirm + result display
async function dashAction(path, confirmMsg) {
  const out = document.getElementById('action-result');
  if (confirmMsg && !confirm(confirmMsg)) return;
  if (out) { out.style.color = '#fc6'; out.textContent = '⏳ ' + path + ' running...'; }
  try {
    const r = await fetch(path, {method: 'POST'});
    const j = await r.json();
    if (out) {
      const ok = j.ok === true || j.ok === undefined;
      out.style.color = ok ? '#6f6' : '#f66';
      let msg = ok ? '✅ ' : '❌ ';
      if (path.includes('close-all')) {
        msg += `${path}: closed ${j.closed||0}/${j.total||0}, failed ${j.failed||0}`;
        if (j.error) msg += ' — ' + j.error;
      } else if (path.includes('test-telegram') || path.includes('send-snapshot')) {
        msg += path + ': ' + (ok ? 'sent' : 'fail');
      } else if (path.includes('restart-')) {
        // 2026-05-13: restart endpoints now respawn directly (not relying on watchdog)
        msg += path + ': killed ' + (j.killed||0) + (j.new_pid ? ', spawned new PID ' + j.new_pid : ', respawn FAILED');
      } else {
        msg += path + ': ' + JSON.stringify(j).slice(0,200);
      }
      out.textContent = msg;
    }
    if (path.includes('close-all') || path.includes('halt') || path.includes('resume')) refresh();
  } catch (e) {
    if (out) { out.style.color = '#f66'; out.textContent = '❌ ' + path + ': ' + e; }
  }
}
async function loadLog() {
  const which = document.getElementById('log-pick').value;
  const r = await fetch('/api/log?name='+which+'&n=200'); const j = await r.json();
  document.getElementById('log-content').textContent = j.lines.join('\n');
  document.getElementById('log-ts').textContent = '(' + new Date().toLocaleTimeString() + ')';
}
async function testOcr() {
  // 2026-05-13: trigger chart-OCR scrape live and show result
  const out = document.getElementById('action-result');
  if (out) { out.style.color = '#fc6'; out.textContent = '⏳ OCR scraping EURUSD M15 chart (~10s)...'; }
  try {
    const r = await fetch('/api/test-ocr?symbol=EURUSD&tf=M15', {method: 'POST'});
    const j = await r.json();
    if (out) {
      if (j.ok) {
        const conf = (j.meta && j.meta.confidence) || '?';
        const elapsed = (j.meta && j.meta.elapsed_s) || '?';
        out.style.color = j.direction === 'NONE' ? '#fc6' : '#6f6';
        out.textContent = '✅ OCR ' + j.symbol + ' ' + j.tf + ': ' + j.direction + ' (conf=' + conf + ', ' + elapsed + 's)';
      } else {
        out.style.color = '#f66';
        out.textContent = '❌ OCR failed: ' + (j.error || 'unknown');
      }
    }
  } catch (e) {
    if (out) { out.style.color = '#f66'; out.textContent = '❌ OCR test: ' + e; }
  }
}
function downloadCSV() { window.location = '/api/csv-export?hours=168'; }
async function closePos(ticket) {
  if (!confirm('Close position ' + ticket + '?')) return;
  const r = await fetch('/api/close-position?ticket='+ticket, {method:'POST'});
  const j = await r.json(); alert(j.ok ? 'Closed P/L: '+j.profit : 'Failed: '+j.error); refresh();
}
let modalCtx = null;
function openSLTP(ticket, sym, openPx, sl, tp, digits) {
  modalCtx = {ticket, digits};
  document.getElementById('modal-ticket').textContent = ticket;
  document.getElementById('modal-sym').textContent = sym;
  document.getElementById('modal-open').textContent = openPx;
  document.getElementById('modal-sl').value = sl || '';
  document.getElementById('modal-tp').value = tp || '';
  document.getElementById('sltp-modal').style.display = 'flex';
}
function closeModal() { document.getElementById('sltp-modal').style.display = 'none'; }
async function submitSLTP() {
  const sl = document.getElementById('modal-sl').value;
  const tp = document.getElementById('modal-tp').value;
  const r = await fetch(`/api/modify-sltp?ticket=${modalCtx.ticket}&sl=${sl}&tp=${tp}`, {method:'POST'});
  const j = await r.json();
  alert(j.ok ? 'Modified' : 'Failed: '+j.error); closeModal(); refresh();
}

function drawEquityChart() {
  if (!window.Chart) return;
  fetch('/api/equity-history?hours=24').then(r=>r.json()).then(data => {
    const ctx = document.getElementById('equity-chart').getContext('2d');
    if (equityChart) equityChart.destroy();
    equityChart = new Chart(ctx, {
      type: 'line',
      data: {
        labels: data.map(d => new Date(d.ts*1000).toLocaleTimeString()),
        datasets: [
          {label:'Balance', data:data.map(d=>d.balance), borderColor:'#4fc3f7', tension:0.2, pointRadius:0},
          {label:'Equity',  data:data.map(d=>d.equity),  borderColor:'#4caf50', tension:0.2, pointRadius:0},
        ]
      },
      options: {responsive:true, scales:{x:{ticks:{maxTicksLimit:10}}}}
    });
  });
}

async function refresh() {
  try {
    const r = await fetch('/api/status'); const s = await r.json();
    document.getElementById('ts').textContent = new Date().toLocaleString();
    const a = s.account; const flC = a.floating_pl >= 0 ? 'pos' : 'neg'; const flS = a.floating_pl >= 0 ? '+' : '';
    document.getElementById('account').innerHTML = `
      <div class="stat"><div class="stat-label">Balance</div><div class="stat-val">$${a.balance.toFixed(2)}</div></div>
      <div class="stat"><div class="stat-label">Equity</div><div class="stat-val">$${a.equity.toFixed(2)}</div></div>
      <div class="stat"><div class="stat-label">Floating</div><div class="stat-val ${flC}">${flS}${a.floating_pl.toFixed(2)}</div></div>
      <div class="stat"><div class="stat-label">Open</div><div class="stat-val">${a.n_positions}</div></div>
      <div class="stat"><div class="stat-label">Free</div><div class="stat-val">$${a.margin_free.toFixed(0)}</div></div>
      <div><span class="${a.connected?'ok':'bad'}">MT5 ${a.connected?'OK':'DOWN'}</span> | <span class="${a.trade_allowed?'ok':'bad'}">Trade ${a.trade_allowed?'OK':'BLOCKED'}</span></div>`;
    // Audio alert on big P/L change
    if (lastEquity !== null && a.equity > 0) {
      const delta = a.equity - lastEquity;
      const thresh = (s.config.audio_alert_threshold || 50);
      if (Math.abs(delta) > thresh) beep();
    }
    lastEquity = a.equity;

    const h = s.health;
    // 2026-08-22: mode-aware health. Values: true=ALIVE, false=DEAD, 'na'=off by design.
    const isLocal = (s.trading_mode && s.trading_mode.local_brain_mode) || h.mode === 'local';
    const essential = isLocal
      ? ['mt5','brain','dashboard']
      : ['executor','trailing','receiver','tunnel','telegram_listener','dashboard'];
    const label = {mt5:'MT5 Terminal', brain:'Brain (primary)', dashboard:'Dashboard',
                   executor:'Executor', trailing:'Trailing', receiver:'TV Receiver',
                   tunnel:'Tunnel', telegram_listener:'Telegram Listener'};
    const cell = (k) => {
      const v = h[k];
      if (v === 'na') return `<div class="health-card" style="opacity:0.45"><div class="label">${label[k]||k}</div><div class="val">N/A (${isLocal?'local':'tv'} mode)</div></div>`;
      return `<div class="health-card"><div class="label">${label[k]||k}</div><div class="val ${v?'ok':'bad'}">${v?'ALIVE':'DEAD'}</div></div>`;
    };
    let healthHtml = essential.map(cell).join('');
    if (isLocal) {
      healthHtml += cell('receiver');
    } else {
      const brainShadow = h.brain_shadow || h.brain;
      healthHtml += `<div class="health-card" style="opacity:0.65"><div class="label">brain (shadow)</div><div class="val">${brainShadow ? 'LEARNING' : 'OFFLINE (by design)'}</div></div>`;
    }
    document.getElementById('health').innerHTML = healthHtml;

    // Trading mode banner
    const tm = s.trading_mode || {};
    const tp = s.telegram_pending || {};
    const op = s.ocr_pipeline || {};
    const modeEl = document.getElementById('trading-mode');
    if (modeEl) {
      let chips = [];
      chips.push(isLocal
        ? `<span class="chip ok">Local Brain Mode</span>`
        : `<span class="chip ok">TV-Signal Mode</span>`);
      if (!isLocal) chips.push(`<span class="chip ${tm.chart_ocr_enabled?'ok':'warn'}">Chart-OCR ${tm.chart_ocr_enabled?'ON':'OFF'}</span>`);
      if (!isLocal) {
        chips.push(`<span class="chip ${tm.inferred_enabled?'bad':'ok'}">INFERRED ${tm.inferred_enabled?'ON (RISKY)':'OFF'}</span>`);
        chips.push(`<span class="chip ${tm.telegram_tap_fallback?'ok':'warn'}">Telegram Tap Fallback</span>`);
      } else {
        chips.push(`<span class="chip ok">EA executes brain signals</span>`);
        chips.push(`<span class="chip ${h.mt5?'ok':'bad'}">${h.mt5?'AutoTrading ON':'MT5 DOWN'}</span>`);
      }
      if ((tp.pending_count||0) > 0 && !isLocal) {
        chips.push(`<span class="chip warn">${tp.pending_count} signal(s) awaiting operator tap</span>`);
      }
      let ocrLine = '';
      if (op.count_total && !isLocal) {
        const lastDir = op.last_direction || '?';
        const lastSym = op.last_symbol || '?';
        const lastConf = op.last_confidence || '?';
        ocrLine = `<div style="margin-top:6px;font-size:12px;opacity:0.85">OCR: total=${op.count_total} (BUY=${op.count_buy||0} SELL=${op.count_sell||0} NONE=${op.count_none||0}) | last: ${lastSym} ${lastDir} (${lastConf})</div>`;
      }
      modeEl.innerHTML = chips.join(' ') + ocrLine;
    }

    // 2026-05-14: Recently Blocked Signals — INLINE explanations (no click needed)
    // Wrapped in own try/catch so a render glitch here doesn't kill positions/deals below.
    try {
      const skipsData = s.recent_skips || {items: [], by_category: {}};
      const skipsEl = document.getElementById('skips-rows');
      const skipsSumEl = document.getElementById('skips-summary');
      // Category color map (declared in outer scope so summary chips can reuse it)
      const catColor = {
        FLIP_BLOCKED: '#ec4899',     // pink — flip-on-opposite blocked by brain
        BRAIN_VETO: '#a855f7', CLUSTER_CAP: '#f97316', USD_SIDE_CAP: '#f59e0b',
        TIER_CAP: '#eab308', PER_SYMBOL_LOSS: '#ef4444', TIME_BLACKOUT: '#06b6d4',
        NEWS_BLACKOUT: '#3b82f6', DRAWDOWN: '#dc2626', SPREAD: '#94a3b8',
        STRATEGY_FILTER: '#64748b', STALE: '#71717a', SAFEGUARD_OTHER: '#a3a3a3',
      };
      if (skipsEl) {
        if (!skipsData.items || skipsData.items.length === 0) {
          skipsEl.innerHTML = '<tr><td colspan="5" style="color:var(--muted);text-align:center;padding:12px">No recent skips — all signals are passing safeguards ✓</td></tr>';
        } else {
          skipsEl.innerHTML = skipsData.items.map((it) => {
            const color = catColor[it.category] || '#888';
            const dirColor = it.direction === 'BUY' ? 'var(--pos)' : it.direction === 'SELL' ? 'var(--neg)' : 'var(--muted)';
            const timeShort = (it.ts || '').split(' ')[1] || it.ts;
            const explain = it.explain || '';
            const action = it.action || '';
            // Single row, explanation INLINE under the reason text (no click required)
            return `<tr>
              <td style="font-family:monospace;font-size:11px;vertical-align:top;padding-top:8px">${timeShort}</td>
              <td style="vertical-align:top;padding-top:8px"><b>${it.symbol}</b></td>
              <td style="color:${dirColor};font-weight:bold;vertical-align:top;padding-top:8px">${it.direction}</td>
              <td style="vertical-align:top;padding-top:8px"><span style="background:${color};color:white;padding:2px 7px;border-radius:8px;font-size:10px;font-weight:bold;white-space:nowrap">${it.category}</span></td>
              <td style="font-size:12px;line-height:1.5;padding:8px 8px">
                <div style="font-weight:600">${it.reason}</div>
                ${explain ? `<div style="margin-top:4px;color:#9cf;font-size:11px"><b>What:</b> ${explain}</div>` : ''}
                ${action ? `<div style="margin-top:2px;color:#9f9;font-size:11px"><b>Do:</b> ${action}</div>` : ''}
              </td>
            </tr>`;
          }).join('');
        }
        const cats = skipsData.by_category || {};
        const catChips = Object.entries(cats).map(([k,v]) =>
          `<span style="margin-left:6px;background:${catColor[k]||'#888'};color:white;padding:1px 6px;border-radius:6px;font-size:10px">${k}: ${v}</span>`
        ).join('');
        if (skipsSumEl) skipsSumEl.innerHTML = `(${skipsData.count || 0} events)${catChips}`;
      }
    } catch (e) { console.error('skips render failed:', e); }

    // Master + settings — defensive: if config block is malformed, log + skip; don't kill the rest of refresh()
    try {
      const c = s.config || {};
      const sg = c.safeguards || {};
      let m = `<div class="switch"><label><b>Trading</b></label>${tog('trading_enabled', c.trading_enabled)}</div>`;
      for (const k of ['news_blackout','dd_circuit_breaker','spread_check','correlation_guard']) {
        m += `<div class="switch"><label>${k.replace(/_/g,' ')}</label>${tog('safeguards.'+k, sg[k])}</div>`;
      }
      m += `<div class="switch"><label>Trailing SL</label>${tog('trailing_enabled', c.trailing_enabled)}</div>`;
      m += `<div class="switch"><label>Brain Filter</label>${tog('brain_filter_enabled', c.brain_filter_enabled)}</div>`;
      m += `<div class="switch"><label>2-leg</label>${tog('two_leg_enabled', c.two_leg_enabled)}</div>`;
      const masterEl = document.getElementById('master'); if (masterEl) masterEl.innerHTML = m;
      const setEl = document.getElementById('settings');
      if (setEl) setEl.innerHTML = ['fixed_lot','quick_tp_atr','quick_sl_atr','trend_tp_atr','trend_sl_atr','max_daily_dd_pct','cooldown_sec','audio_alert_threshold'].map(k =>
        `<div class="switch"><label>${k.replace(/_/g,' ')}</label><input type="number" step="0.01" value="${c[k]||0}" onchange="setVal('${k}', this.value)"></div>`
      ).join('');
    } catch (e) { console.error('master/settings render failed:', e); }

    // POSITIONS — isolated try/catch so upstream failures never blank this critical table
    try {
      const posList = (a && Array.isArray(a.positions)) ? a.positions : [];
      const pcEl = document.getElementById('pos-count'); if (pcEl) pcEl.textContent = `(${posList.length})`;
      const posEl = document.getElementById('positions');
      if (posEl) {
        if (posList.length === 0) {
          posEl.innerHTML = '<tr><td colspan="14" style="text-align:center;color:var(--muted);padding:14px">no open positions</td></tr>';
        } else {
          posEl.innerHTML = posList.map(p => {
            const pctMove = (p.pct_move !== null && p.pct_move !== undefined) ? p.pct_move : 0;
            const pctC = pctMove >= 0 ? 'pos' : 'neg';
            const pctS = pctMove >= 0 ? '+' : '';
            const rprog = p.r_progress;
            const rC = (rprog === null || rprog === undefined) ? 'muted' : (rprog >= 0 ? 'pos' : 'neg');
            const rStr = (rprog === null || rprog === undefined) ? '-' : `${rprog >= 0 ? '+' : ''}${rprog}R`;
            const cmt = p.comment || '';
            const srcShort = cmt.replace('rocket_prime_chart_ocr','OCR').replace('telegram_manual_direction','TG').slice(0,12) || '?';
            const dirColor = p.dir==='BUY' ? 'var(--pos)' : 'var(--neg)';
            return `<tr title="Opened ${p.open_time||'?'} | ${p.duration||'?'} ago | source: ${cmt||'?'}">
              <td><b>${p.symbol}</b></td>
              <td style="color:${dirColor};font-weight:bold">${p.dir}</td>
              <td><span style="font-size:10px;background:rgba(0,0,0,0.15);padding:1px 5px;border-radius:4px">${p.leg||'-'}</span></td>
              <td>${p.lots}</td>
              <td>${p.open}</td>
              <td>${p.current}</td>
              <td>${p.sl||'-'}</td>
              <td>${p.tp||'-'}</td>
              <td class="${p.profit>=0?'pos':'neg'}">${p.profit>=0?'+':''}${p.profit}</td>
              <td class="${pctC}" style="font-size:11px">${pctS}${pctMove}%</td>
              <td class="${rC}" style="font-size:11px">${rStr}</td>
              <td style="font-size:11px">${p.duration||'-'}</td>
              <td style="font-size:10px;color:var(--muted)" title="${cmt}">${srcShort}</td>
              <td><button class="tiny" onclick="openSLTP(${p.ticket},'${p.symbol}',${p.open},${p.sl||0},${p.tp||0},${p.digits||5})">SL/TP</button>
                  <button class="tiny danger" onclick="closePos(${p.ticket})">X</button></td></tr>`;
          }).join('');
        }
      }
    } catch (e) {
      console.error('positions render failed:', e);
      const posEl = document.getElementById('positions');
      if (posEl) posEl.innerHTML = `<tr><td colspan="14" style="color:#f88;text-align:center;padding:10px">render error: ${e.message} — check console</td></tr>`;
    }

    // DEALS — isolated try/catch
    try {
      const dealsObj = s.deals || {stats:{}, deals:[]};
      const ds = dealsObj.stats || {};
      const dealList = Array.isArray(dealsObj.deals) ? dealsObj.deals : [];
      const pfStr = ds.profit_factor ? ` PF:${ds.profit_factor}` : '';
      const dsEl = document.getElementById('deal-stats');
      if (dsEl) dsEl.textContent = `${ds.n||0}T ${ds.wr||0}%WR ${(ds.total_pl||0)>=0?'+':''}${ds.total_pl||0}${pfStr} | avg+${ds.avg_win||0} avg${ds.avg_loss||0}`;
      const dEl = document.getElementById('deals');
      if (dEl) {
        if (dealList.length === 0) {
          dEl.innerHTML = '<tr><td colspan="7" style="text-align:center;color:var(--muted);padding:14px">no closed trades</td></tr>';
        } else {
          dEl.innerHTML = dealList.map(d => {
            const dm = d.duration_min;
            const dur = (dm !== null && dm !== undefined) ? (dm < 60 ? `${dm}m` : `${Math.floor(dm/60)}h${dm%60}m`) : '-';
            const reasonColor = d.exit_reason === 'TP HIT' ? 'var(--pos)' : d.exit_reason === 'SL HIT' ? 'var(--neg)' : '#9cf';
            const dirColor = d.trade_dir==='BUY' ? 'var(--pos)' : 'var(--neg)';
            return `<tr title="Entry ${d.entry_price||'?'} → Exit ${d.exit_price||'?'} (${dur}) | ${d.comment||''}">
              <td style="font-family:monospace;font-size:11px">${d.time}</td>
              <td><b>${d.symbol}</b></td>
              <td style="color:${dirColor};font-weight:bold">${d.trade_dir}</td>
              <td>${d.lots}</td>
              <td class="${d.profit>=0?'pos':'neg'}">${d.profit>=0?'+':''}${d.profit}</td>
              <td style="font-size:11px">${dur}</td>
              <td style="font-size:11px;color:${reasonColor}">${d.exit_reason||'?'}</td>
            </tr>`;
          }).join('');
        }
      }
    } catch (e) {
      console.error('deals render failed:', e);
      const dEl = document.getElementById('deals');
      if (dEl) dEl.innerHTML = `<tr><td colspan="7" style="color:#f88;text-align:center;padding:10px">render error: ${e.message} — check console</td></tr>`;
    }

    // Signals tab — isolated
    try {
      const sigs = (s.signals && Array.isArray(s.signals.signals)) ? s.signals.signals : [];
      const bySym = (s.signals && Array.isArray(s.signals.by_symbol)) ? s.signals.by_symbol : [];
      const slEl = document.getElementById('signals-list');
      if (slEl) slEl.innerHTML = sigs.map(g => `<tr><td>${g.time}</td><td>${g.symbol}</td><td>${g.dir}</td><td>${g.conf}%</td><td>${g.strategy}</td></tr>`).join('') || '<tr><td colspan="5">no signals yet</td></tr>';
      const ssEl = document.getElementById('sig-by-symbol');
      if (ssEl) ssEl.innerHTML = bySym.map(g => `<tr><td>${g.symbol}</td><td>${g.count}</td><td>${g.last_min_ago === null ? '-' : g.last_min_ago + ' min ago'}</td></tr>`).join('') || '<tr><td colspan="3">no signals</td></tr>';
      const pe = (s.config && s.config.pairs_enabled) ? s.config.pairs_enabled : {};
      const pairsEl = document.getElementById('pairs');
      if (pairsEl) pairsEl.innerHTML = Object.entries(pe).map(([k,v]) => `<div class="pair-row"><span>${k}</span>${tog('pairs_enabled.'+k, v)}</div>`).join('');
    } catch (e) { console.error('signals render failed:', e); }

    // Analytics / per-pair / spread / news / brain / TV alerts / schtasks — each isolated
    try {
      const ppEl = document.getElementById('per-pair-pnl');
      if (ppEl) ppEl.innerHTML = (s.per_pair_pnl||[]).map(p =>
        `<tr><td>${p.symbol}</td><td>${p.n_closed}</td><td>${p.wr===null?'-':p.wr+'%'}</td><td class="${p.closed_pl>=0?'pos':'neg'}">${p.closed_pl>=0?'+':''}${p.closed_pl}</td><td class="${p.open_pl>=0?'pos':'neg'}">${p.open_pl>=0?'+':''}${p.open_pl}</td><td class="${p.total_pl>=0?'pos':'neg'}"><b>${p.total_pl>=0?'+':''}${p.total_pl}</b></td></tr>`).join('') || '<tr><td colspan="6">no data</td></tr>';
    } catch (e) { console.error('per-pair render failed:', e); }

    try {
      const dEl = document.getElementById('duration');
      if (dEl) {
        const dur = s.duration || {};
        dEl.innerHTML = ['all','quick','trend'].map(k => {
          const d = dur[k] || {n:0};
          return `<tr><td>${k}</td><td>${d.n}</td><td>${d.avg_min||'-'}</td><td>${d.median_min||'-'}</td><td>${d.max_min||'-'}</td></tr>`;
        }).join('');
      }
    } catch (e) { console.error('duration render failed:', e); }

    try {
      const spEl = document.getElementById('spread');
      if (spEl) spEl.innerHTML = (s.spread||[]).map(s2 =>
        `<tr><td>${s2.symbol}</td><td>${s2.bid}</td><td>${s2.ask}</td><td>${s2.spread_pts}</td><td class="${s2.warn?'warn':''}">${s2.ratio_pct===null?'-':s2.ratio_pct+'%'}</td></tr>`).join('') || '<tr><td colspan="5">no data</td></tr>';
    } catch (e) { console.error('spread render failed:', e); }

    try {
      const nEl = document.getElementById('news');
      if (nEl) nEl.innerHTML = (s.news||[]).map(n =>
        `<tr><td>${n.time}</td><td><b>${n.currency}</b></td><td>${n.event}</td><td>${n.minutes_to_go}m</td></tr>`).join('') || '<tr><td colspan="4">no news in next 24h</td></tr>';
    } catch (e) { console.error('news render failed:', e); }

    try {
      const bs = s.brain_learning || {by_class:[], total:0};
      const btEl = document.getElementById('brain-total'); if (btEl) btEl.textContent = `(${bs.total||0} outcomes logged)`;
      const bcEl = document.getElementById('brain-classes');
      if (bcEl) bcEl.innerHTML = (bs.by_class||[]).map(c =>
        `<tr><td>${c.class}</td><td>${c.n}</td><td>${c.wr}%</td><td class="${c.avg_r>=0?'pos':'neg'}">${c.avg_r>=0?'+':''}${c.avg_r}</td><td class="${c.total_r>=0?'pos':'neg'}">${c.total_r}</td><td>${c.blocked?'<span class="bad">BLOCKED</span>':'<span class="ok">PASS</span>'}</td></tr>`).join('') || '<tr><td colspan="6">no closed-trade outcomes yet</td></tr>';
    } catch (e) { console.error('brain render failed:', e); }

    try {
      const tv = s.tv_alerts || {alerts:[]};
      const tcEl = document.getElementById('tv-cache-ts');
      if (tcEl) tcEl.textContent = tv.cached_at ? '(refreshed ' + new Date(tv.cached_at*1000).toLocaleTimeString() + ')' : '(loading...)';
      const taEl = document.getElementById('tv-alerts');
      if (taEl) taEl.innerHTML = (tv.alerts||[]).map(a =>
        `<tr><td>${a.symbol}</td><td>${a.tf}</td><td class="${a.active?'ok':'bad'}">${a.active?'YES':'no'}</td><td class="${a.webhook_ok?'ok':'bad'}">${a.webhook_ok?'OK':'NO SECRET'}</td><td>${a.days_left||'-'}</td><td>${a.last_fire_min_ago===null?'never':a.last_fire_min_ago+' min ago'}</td></tr>`).join('') || '<tr><td colspan="6">loading TV alerts...</td></tr>';
    } catch (e) { console.error('tv-alerts render failed:', e); }

    try {
      const stEl = document.getElementById('schtasks');
      if (stEl) stEl.innerHTML = (s.schtasks||[]).map(t =>
        `<tr><td>${t.name}</td><td>${t.next_run}</td><td>${t.status==='Ready'?'<span class="ok">'+t.status+'</span>':(t.status==='Disabled'?'<span class="bad">'+t.status+'</span>':'<span class="warn">'+t.status+'</span>')}</td></tr>`).join('') || '<tr><td colspan="3">none</td></tr>';
      const rEl = document.getElementById('reports-list');
      if (rEl) rEl.innerHTML = (s.reports||[]).map(r => `<tr><td>${r.name}</td><td>${r.size_kb} KB</td><td>${r.mtime}</td></tr>`).join('');
      const pmEl = document.getElementById('postmortems');
      if (pmEl) pmEl.innerHTML = (s.postmortems||[]).map(p => `<tr><td>${p.name}</td><td>${p.size_kb} KB</td></tr>`).join('');
    } catch (e) { console.error('schtasks/reports render failed:', e); }

    try {
      // System tab (merged from unified_dashboard + mission_control)
      const ms = s.mission || {counts:{}};
      const c = ms.counts || {};
      const mrEl = document.getElementById('mission-rows');
      if (mrEl) {
        const rows = [['MT5 Terminal', c.mt5],['Brain', c.brain],['Webhook Receiver', c.webhook_receiver],
                      ['Dashboard', c.dashboard],['Executor', c.executor],['Trailing Manager', c.trailing],['Watchdog', c.watchdog]];
        mrEl.innerHTML = rows.map(([k,v]) =>
          `<tr><td>${k}</td><td>${v==null?'-':v}</td><td>${(v&&v>0)?'<span class="ok">UP</span>':'<span class="bad">DOWN</span>'}</td></tr>`).join('');
      }
      const bl = s.brain_liveness || {};
      const blEl = document.getElementById('brain-liveness');
      if (blEl) blEl.innerHTML =
        `<div>Status: ${bl.alive?'<span class="ok">ALIVE</span>':'<span class="bad">DEAD</span>'} &nbsp; PIDs: ${(bl.pids||[]).join(', ')||'-'}</div>` +
        `<div style="margin-top:6px;opacity:0.8">${bl.boot_line||''}</div>`;
      const cf = s.configs || {};
      const cfEl = document.getElementById('configs-rows');
      if (cfEl) cfEl.innerHTML = Object.entries(cf.teams||{}).map(([k,v]) =>
        `<tr><td>${k}</td><td style="font-family:monospace">${JSON.stringify(v)}</td></tr>`).join('') ||
        ((cf.error||cf.pair_count===undefined) ? `<tr><td colspan="2">${cf.error||'loading...'}</td></tr>` : `<tr><td colspan="2">${cf.pair_count} pairs configured</td></tr>`);
      const skEl = document.getElementById('skills-rows');
      if (skEl) skEl.innerHTML = (s.skills||[]).map(k =>
        `<tr><td>${k.name}</td><td>${(k.desc||'').slice(0,80)}</td></tr>`).join('') || '<tr><td colspan="2">none</td></tr>';
    } catch (e) { console.error('system render failed:', e); }
  } catch (e) { console.error('refresh outer failed:', e); }
}
refresh(); setInterval(refresh, 5000);
setInterval(() => { if (document.getElementById('analytics').classList.contains('active')) drawEquityChart(); }, 30000);
</script>
</body></html>"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def _send_json(self, obj, status=200):
        body = json.dumps(obj, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, html):
        body = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_csv(self, csv_text, filename="trades.csv"):
        body = csv_text.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/csv")
        self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        url = urlparse(self.path); qs = parse_qs(url.query)
        if url.path in ("/", "/index.html"):
            self._send_html(DASHBOARD_HTML)
        elif url.path == "/api/status":
            with _mt5_lock:
                mt5.initialize()
                payload = {
                    "account": get_account_state(),
                    "deals": get_recent_deals(24),
                    "signals": get_recent_signals(30),
                    "health": get_process_health(),
                    "config": load_config(),
                    "schtasks": get_schtasks(),
                    "reports": get_backtest_reports(),
                    "postmortems": get_postmortems(),
                    "brain": get_brain_state(),
                    "per_pair_pnl": get_per_pair_pnl(168),
                    "duration": get_trade_duration_stats(168),
                    "spread": get_spread_monitor(),
                    "news": get_news_calendar(),
                    "brain_learning": get_brain_learning_stats(),
                    "tv_alerts": get_tv_alerts_status(),
                    # 2026-05-13 additions: TV-mode pipeline status
                    "ocr_pipeline": get_ocr_pipeline_stats(),
                    "telegram_pending": get_telegram_pending(),
                    "trading_mode": get_trading_mode(),
                    # 2026-05-14: skip reasons for operator visibility
                    "recent_skips": get_recent_skips(30),
                    # 2026-08-22 dashboard merge: single source of truth
                    "brain_liveness": get_brain_liveness(),
                    "configs": get_configs(),
                    "skills": get_skills(),
                    "mission": get_mission_state(),
                }
            self._send_json(payload)
        elif url.path == "/api/log":
            name = (qs.get("name") or ["executor"])[0]
            n = int((qs.get("n") or ["200"])[0])
            self._send_json({"lines": get_log_tail(name, n)})
        elif url.path == "/api/equity-history":
            hours = int((qs.get("hours") or ["24"])[0])
            self._send_json(get_equity_history(hours))
        elif url.path == "/api/csv-export":
            hours = int((qs.get("hours") or ["168"])[0])
            self._send_csv(csv_export_deals(hours), f"trendmaster_trades_{hours}h.csv")
        else:
            self._send_json({"error": "not found"}, 404)

    def do_POST(self):
        url = urlparse(self.path); qs = parse_qs(url.query)
        if url.path == "/api/toggle":
            key = (qs.get("key") or [""])[0]; val = (qs.get("val") or ["false"])[0].lower() == "true"
            cfg = load_config(); parts = key.split("."); d = cfg
            for p in parts[:-1]: d = d.setdefault(p, {})
            d[parts[-1]] = val; save_config(cfg)
            self._send_json({"ok": True})
        elif url.path == "/api/set":
            key = (qs.get("key") or [""])[0]
            try: val = float((qs.get("val") or ["0"])[0])
            except ValueError: val = 0
            cfg = load_config(); parts = key.split("."); d = cfg
            for p in parts[:-1]: d = d.setdefault(p, {})
            d[parts[-1]] = val; save_config(cfg)
            self._send_json({"ok": True})
        elif url.path == "/api/close-all":
            self._send_json(close_all_positions())
        elif url.path == "/api/close-position":
            ticket = int((qs.get("ticket") or ["0"])[0])
            self._send_json(close_one_position(ticket))
        elif url.path == "/api/modify-sltp":
            ticket = int((qs.get("ticket") or ["0"])[0])
            sl = float((qs.get("sl") or ["0"])[0]) if (qs.get("sl") or [""])[0] else 0
            tp = float((qs.get("tp") or ["0"])[0]) if (qs.get("tp") or [""])[0] else 0
            self._send_json(modify_position_sltp(ticket, sl, tp))
        elif url.path == "/api/halt-all":
            cfg = load_config(); cfg["trading_enabled"] = False; save_config(cfg)
            send_telegram("<b>HALT issued from Dashboard</b>")
            self._send_json({"ok": True})
        elif url.path == "/api/resume":
            cfg = load_config(); cfg["trading_enabled"] = True; save_config(cfg)
            send_telegram("<b>Trading RESUMED from Dashboard</b>")
            self._send_json({"ok": True})
        elif url.path == "/api/restart-executor":
            n = _kill_processes_by_cmd_match("python_signal_executor")
            time.sleep(1.5)
            pid = _silent_spawn_component(ROOT / "tools" / "python_signal_executor.py")
            self._send_json({"ok": pid is not None, "killed": n, "new_pid": pid})
        elif url.path == "/api/restart-trailing":
            n = _kill_processes_by_cmd_match("trailing_stop_manager")
            time.sleep(1.5)
            pid = _silent_spawn_component(ROOT / "tools" / "trailing_stop_manager.py")
            self._send_json({"ok": pid is not None, "killed": n, "new_pid": pid})
        elif url.path == "/api/restart-webhook":
            n = _kill_processes_by_cmd_match("tv_webhook_receiver")
            time.sleep(2)
            pid = _silent_spawn_module("ai_trading_agents.tv_webhook_receiver")
            self._send_json({"ok": pid is not None, "killed": n, "new_pid": pid})
        elif url.path == "/api/restart-telegram-listener":
            n = _kill_processes_by_cmd_match("telegram_direction_listener")
            time.sleep(1.5)
            pid = _silent_spawn_component(ROOT / "tools" / "telegram_direction_listener.py")
            self._send_json({"ok": pid is not None, "killed": n, "new_pid": pid})
        elif url.path == "/api/test-ocr":
            # Force-scrape an OCR test on a symbol+tf and return the result
            sym = (qs.get("symbol") or ["EURUSD"])[0]
            tf = (qs.get("tf") or ["M15"])[0]
            try:
                from ai_trading_agents.chart_scrape_ocr import scrape_rp_direction
                direction, meta = scrape_rp_direction(sym, tf)
                self._send_json({"ok": True, "symbol": sym, "tf": tf, "direction": direction, "meta": meta})
            except Exception as e:
                self._send_json({"ok": False, "error": str(e)})
        elif url.path == "/api/refresh-tv-alerts":
            # Force-refresh TV alerts cache. ?reactivate=1 also flips any
            # inactive RP alerts back to active via TV restart_alerts API.
            do_react = (qs.get("reactivate") or ["0"])[0] in ("1", "true", "TRUE", "yes")
            res = _refresh_tv_alerts_now(reactivate=do_react)
            self._send_json(res)
        elif url.path == "/api/clear-telegram-pending":
            # Mark all pending Telegram signals as resolved (skipped by operator)
            p = ROOT / "logs" / "pending_signals.jsonl"
            if not p.exists():
                self._send_json({"ok": True, "cleared": 0})
            else:
                try:
                    lines = p.read_text(encoding="utf-8").splitlines()
                    new_lines = []
                    cleared = 0
                    for line in lines:
                        try:
                            row = json.loads(line)
                            if not row.get("resolved"):
                                row["resolved"] = True
                                row["cleared_by"] = "dashboard"
                                cleared += 1
                            new_lines.append(json.dumps(row, separators=(",", ":")))
                        except Exception:
                            new_lines.append(line)
                    p.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
                    self._send_json({"ok": True, "cleared": cleared})
                except Exception as e:
                    self._send_json({"ok": False, "error": str(e)})
        elif url.path == "/api/test-telegram":
            ok = send_telegram("<b>Dashboard test</b>")
            self._send_json({"ok": ok})
        elif url.path == "/api/send-snapshot":
            ai = get_account_state()
            msg = (f"<b>Snapshot</b>\nBalance: ${ai.get('balance',0):.2f}  Equity: ${ai.get('equity',0):.2f}\n"
                   f"Open: {ai.get('n_positions',0)}  Floating: {ai.get('floating_pl',0):+.2f}")
            self._send_json({"ok": send_telegram(msg)})
        else:
            self._send_json({"error": "not found"}, 404)


def _silent_spawn_component(script_path):
    """Spawn a tools/*.py script via pythonw with no console window.
    Returns the new PID or None on failure."""
    try:
        pythonw = ROOT / ".venv" / "Scripts" / "pythonw.exe"
        proc = subprocess.Popen(
            [str(pythonw), str(script_path)],
            cwd=str(ROOT),
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=0x00000008 | 0x08000000,  # DETACHED | CREATE_NO_WINDOW
            close_fds=True,
        )
        return proc.pid
    except Exception:
        return None


def _silent_spawn_module(module_name):
    """Spawn a python -m <module> via pythonw with no console window."""
    try:
        pythonw = ROOT / ".venv" / "Scripts" / "pythonw.exe"
        proc = subprocess.Popen(
            [str(pythonw), "-m", module_name],
            cwd=str(ROOT),
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=0x00000008 | 0x08000000,
            close_fds=True,
        )
        return proc.pid
    except Exception:
        return None


_DASH_LOCK_HANDLE = None


def _acquire_dashboard_lock() -> bool:
    """Singleton file lock so only ONE dashboard runs at a time.
    Without this, watchdogs spawn many competing servers fighting for port 8765
    and all of them hang."""
    global _DASH_LOCK_HANDLE
    import msvcrt as _msvcrt
    from pathlib import Path as _Path
    lock_path = _Path("C:/Users/Ratanshila/Documents/autmated trading/logs/dashboard_server.lock")
    lock_path.parent.mkdir(exist_ok=True)
    try:
        f = open(lock_path, "a+", encoding="utf-8")
        try:
            _msvcrt.locking(f.fileno(), _msvcrt.LK_NBLCK, 1)
        except OSError:
            log.warning("dashboard_server lock held by another instance — exiting cleanly")
            f.close()
            return False
        f.seek(0); f.truncate()
        f.write(f"{os.getpid()}\n")
        f.flush()
        _DASH_LOCK_HANDLE = f
        return True
    except Exception as e:
        log.exception("dashboard singleton lock failed: %s", e)
        return True


def main():
    if not _acquire_dashboard_lock():
        return 0
    log.info("Comprehensive dashboard starting on http://localhost:%d", PORT)
    threading.Thread(target=_equity_logger_loop, daemon=True).start()
    threading.Thread(target=_tv_alerts_refresh_loop, daemon=True).start()
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    server.serve_forever()


if __name__ == "__main__":
    sys.exit(main() or 0)
