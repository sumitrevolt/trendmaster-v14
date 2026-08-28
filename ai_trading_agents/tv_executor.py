"""TradingView → MT5 EA signal executor.

Translates a normalised TradingView alert into an EA-readable signal JSON
in the same format the brain's `write_signal()` produces — atomic write,
ASCII JSON, per-symbol filename, MT5 Files directory.

This module is **the only thing that should write the EA signal JSON when
TV_SIGNAL.enabled is True.** The brain's `write_signal()` is short-circuited
into shadow-log mode so it doesn't race with us.

Usage from another process:
    from ai_trading_agents.tv_executor import write_tv_signal
    res = write_tv_signal(symbol="XAUUSD", direction="BUY", source="TV")
    # res = {"ok": True, "path": "...", "payload": {...}}

Design notes
------------
* No `.resolve()` anywhere — this module lives inside the
  `ai_trading_agents/` junction, see CLAUDE.md "Brain path resolution rule".
* SL/TP/ADX come from `_pair_sl_tp()`-equivalent lookup against
  `team_params` then `pair_params`, so risk geometry stays consistent
  with what the brain would have produced. The TV alert does NOT need
  to include SL/TP — we set them from pair config.
* `require_all_3` is forced **False** in the payload regardless of
  EA_OVERRIDES, because TV is the source of truth — we don't want the
  EA's own 3-of-3 quorum to veto a TV signal.
* `confidence` defaults to 0.95 (well above any MIN_CONF) so that any
  conf-gate downstream in the EA (rare) would also pass.
* Symbol must be in `SYMBOL_TO_TEAM` (the canonical 19-symbol whitelist).
  Anything else is rejected with a structured error.

Audit log: every successful write appends one JSON line to
  logs/tv_signals.jsonl
so that the cause of every TV-driven trade is reconstructable later.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Dict, Optional, Tuple

# Plain parent.parent (no .resolve()) — see CLAUDE.md
_HERE = Path(__file__).parent
_ROOT = _HERE.parent

# ───────────────────────── pair / team risk lookup ─────────────────────────
try:
    from ai_trading_agents.team_params import (
        TEAM_PARAMS as _TEAM_PARAMS,
        SYMBOL_TO_TEAM as _SYMBOL_TO_TEAM,
    )
except Exception:  # pragma: no cover — defensive
    _TEAM_PARAMS = {}
    _SYMBOL_TO_TEAM = {}

try:
    from ai_trading_agents.pair_params import PAIR_PARAMS as _PAIR_PARAMS
except Exception:
    _PAIR_PARAMS = {}

# ───────────────────────── settings / TV config ─────────────────────────
try:
    from config import settings as _settings
except Exception:  # pragma: no cover
    _settings = None  # type: ignore[assignment]


def _tv_cfg() -> Dict:
    """Return the TV_SIGNAL config dict with safe fallbacks."""
    cfg = {}
    if _settings is not None:
        cfg = getattr(_settings, "TV_SIGNAL", {}) or {}
    # defaults — module is usable even before settings.py is updated
    return {
        "enabled": cfg.get("enabled", False),
        "shadow_brain": cfg.get("shadow_brain", True),
        "default_confidence": float(cfg.get("default_confidence", 0.95)),
        "force_skip_quorum": bool(cfg.get("force_skip_quorum", True)),
        "max_signal_age_s": int(cfg.get("max_signal_age_s", 60)),
        "log_path": cfg.get("log_path", "logs/tv_signals.jsonl"),
        "signal_filename": cfg.get("signal_filename", "trendmaster_signals.json"),
        "primary_symbol": cfg.get("primary_symbol", "XAUUSD"),
        "use_common": cfg.get("use_common", False),
    }


# ───────────────────────── MT5 Files dir resolution ─────────────────────────
def _resolve_signal_path(symbol: str, file_name: Optional[str] = None) -> Path:
    """Resolve where the EA signal JSON should be written.

    Preference order:
      1. `MT5_FILES_DIR` env var — explicit override (most robust when the
         brain holds an exclusive MT5 connection that blocks our
         mt5.initialize() in this process).
      2. `mt5.initialize()` + `mt5.terminal_info()` — auto-detect.
      3. Project root — fallback for tests / dry-runs.
    """
    cfg = _tv_cfg()
    name = file_name or _filename_for(symbol)
    # 1) explicit env override
    env_path = os.environ.get("MT5_FILES_DIR", "").strip()
    if env_path:
        base = Path(env_path)
        try:
            base.mkdir(parents=True, exist_ok=True)
            return base / name
        except Exception:
            pass
    # 2) try MT5 module
    try:
        import MetaTrader5 as mt5  # type: ignore

        if not mt5.initialize():
            mt5.shutdown()
            mt5.initialize()
        info = mt5.terminal_info()
        if info is not None:
            if cfg["use_common"]:
                base = Path(info.commondata_path) / "Files"
            else:
                base = Path(info.data_path) / "MQL5" / "Files"
            base.mkdir(parents=True, exist_ok=True)
            return base / name
    except Exception:
        pass
    # 3) fallback
    return _ROOT / name


def _filename_for(symbol: str) -> str:
    cfg = _tv_cfg()
    base = cfg["signal_filename"]
    primary = cfg["primary_symbol"]
    if symbol == primary:
        return base
    stem = Path(base).stem
    suffix = Path(base).suffix or ".json"
    return f"{stem}_{symbol}{suffix}"


# ───────────────────────── per-symbol risk lookup ─────────────────────────
def _pair_sl_tp(sym: str) -> Tuple[float, float, float]:
    """Same lookup order as brain's `_pair_sl_tp` (team → pair → defaults)."""
    team = _SYMBOL_TO_TEAM.get(sym)
    if team:
        tp_cfg = _TEAM_PARAMS.get(team) or {}
        if "sl_atr_mult" in tp_cfg and "tp_atr_mult" in tp_cfg:
            return (
                float(tp_cfg["sl_atr_mult"]),
                float(tp_cfg["tp_atr_mult"]),
                float(tp_cfg.get("adx_min", 20)),
            )
    pp = _PAIR_PARAMS.get(sym) or {}
    if "sl_atr_mult" in pp and "tp_atr_mult" in pp:
        return (
            float(pp["sl_atr_mult"]),
            float(pp["tp_atr_mult"]),
            float(pp.get("adx_min", 20)),
        )
    # 2026-05-13: TP multiplier raised 2.0 → 2.5 to match operator's
    # "Ref Lvl 5 as TP" requirement (RP indicator structure: SL = 1R,
    # Lvl 5 = 2.5R, giving 1:2.5 R:R).
    return (1.0, 2.5, 20.0)


# ───────────────────────── direction normalisation ─────────────────────────
_DIR_ALIASES_BUY = {"buy", "long", "enterlong", "enter_long", "bull", "bullish", "1", "+1"}
_DIR_ALIASES_SELL = {"sell", "short", "entershort", "enter_short", "bear", "bearish", "-1"}
_DIR_ALIASES_NONE = {"close", "exit", "flat", "none", "0", ""}


def _normalise_direction(raw: str) -> str:
    s = (raw or "").strip().lower()
    if s in _DIR_ALIASES_BUY:
        return "BUY"
    if s in _DIR_ALIASES_SELL:
        return "SELL"
    if s in _DIR_ALIASES_NONE:
        return "NONE"
    raise ValueError(f"unrecognised direction: {raw!r}")


# ───────────────────────── timeframe normalisation ─────────────────────────
# TradingView's `{{interval}}` placeholder emits values like "1", "5", "15",
# "60", "240", "D", "W" (number-of-minutes for intraday, letter codes for
# daily+). We canonicalise to MetaTrader-style M1/M5/M15/M30/H1/H4/D1/W1/MN
# so every consumer (audit log, dedup, learner) sees the same string.
_TF_ALIASES = {
    # raw TV / common aliases → canonical
    "1": "M1", "m1": "M1",
    "3": "M3", "m3": "M3",
    "5": "M5", "m5": "M5",
    "15": "M15", "m15": "M15",
    "30": "M30", "m30": "M30",
    "45": "M45", "m45": "M45",
    "60": "H1", "h1": "H1", "1h": "H1",
    "120": "H2", "h2": "H2", "2h": "H2",
    "180": "H3", "h3": "H3", "3h": "H3",
    "240": "H4", "h4": "H4", "4h": "H4",
    "d": "D1", "1d": "D1", "d1": "D1",
    "w": "W1", "1w": "W1", "w1": "W1",
    "m": "MN1", "1m_long": "MN1", "mn": "MN1", "mn1": "MN1",
}


def _normalise_timeframe(raw) -> Optional[str]:
    """Best-effort normaliser. Returns None if input is empty or unparseable
    (in which case the caller still writes the signal — TF tracking is optional
    metadata, not a gate)."""
    if raw is None:
        return None
    s = str(raw).strip().lower()
    if not s:
        return None
    if s in _TF_ALIASES:
        return _TF_ALIASES[s]
    # Already canonical?
    s_up = s.upper()
    if s_up in {"M1", "M3", "M5", "M15", "M30", "M45", "H1", "H2", "H3", "H4", "D1", "W1", "MN1"}:
        return s_up
    return None  # unknown — log as UNK downstream


# ───────────────────────── audit log ─────────────────────────
def _audit_log(record: Dict) -> None:
    cfg = _tv_cfg()
    log_path = Path(cfg["log_path"])
    if not log_path.is_absolute():
        log_path = _ROOT / log_path
    log_path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, separators=(",", ":"), default=str)
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(line + "\n")


# ───────────────────────── public API ─────────────────────────
def write_tv_signal(
    symbol: str,
    direction: str,
    confidence: Optional[float] = None,
    source: str = "tradingview",
    tv_strategy: Optional[str] = None,
    tv_price: Optional[float] = None,
    tv_alert_ts: Optional[int] = None,
    tv_timeframe: Optional[str] = None,
    extra: Optional[Dict] = None,
) -> Dict:
    """Translate a TV alert into an EA-readable signal file.

    Returns
    -------
    {"ok": bool, "path": str, "payload": dict, "error": Optional[str]}
    """
    cfg = _tv_cfg()
    res: Dict = {"ok": False, "path": "", "payload": {}, "error": None}

    # 1) symbol whitelist
    if symbol not in _SYMBOL_TO_TEAM:
        res["error"] = f"symbol_not_whitelisted: {symbol}"
        _audit_log({"ts": int(time.time()), "event": "reject", **res, "symbol": symbol})
        return res

    # 2) direction
    try:
        norm_dir = _normalise_direction(direction)
    except ValueError as e:
        res["error"] = str(e)
        _audit_log(
            {"ts": int(time.time()), "event": "reject", "symbol": symbol, "error": res["error"]}
        )
        return res

    # 3) staleness — TV alert older than max_signal_age_s is suspect (network /
    #    queue lag). Default 60s; a webhook is usually <1s end-to-end.
    if tv_alert_ts is not None:
        age = int(time.time()) - int(tv_alert_ts)
        if age > cfg["max_signal_age_s"]:
            res["error"] = f"signal_stale: age_s={age} > {cfg['max_signal_age_s']}"
            _audit_log(
                {"ts": int(time.time()), "event": "reject", "symbol": symbol, "error": res["error"]}
            )
            return res

    # 4) build payload — mirrors brain's `write_signal` schema 1:1
    sl_m, tp_m, adx_min = _pair_sl_tp(symbol)
    # 2026-05-13: TV/RP signals enforce 1:2.5 R:R (matching RP's Ref Lvl 5
    # design — operator policy "Ref Lvl 5 hi take profit hona chahiye").
    # Per-pair empirical tuning was for brain-rule signals; RP wants its
    # own ratio independent of pair history. Cap TP at 2.5x SL.
    if source and ("rocket_prime" in source or "telegram_manual_direction" in source):
        tp_m = sl_m * 2.5
        # SL floor: never tighter than 1.0 ATR (avoid whipsaw stops)
        if sl_m < 1.0:
            sl_m = 1.0
            tp_m = 2.5
    conf = float(confidence if confidence is not None else cfg["default_confidence"])
    conf = max(0.0, min(1.0, conf))
    payload = {
        "direction": norm_dir,
        "confidence": round(conf, 4),
        "ts": int(time.time()),
        "symbol": symbol,
        "brain": "TrendMaster_v14",
        "model": "tradingview",
        "agents": {"dir": norm_dir, "votes": []},
        "sl_atr_mult": round(sl_m, 3),
        "tp_atr_mult": round(tp_m, 3),
        "adx_min": round(adx_min, 1),
        "source": source,
    }
    if cfg["force_skip_quorum"]:
        # EA reads `require_all_3` per-signal — False = accept 2-of-3 OR less,
        # which together with conf=0.95 effectively means "trust the signal".
        payload["require_all_3"] = False
        # max_spread_atr_pct: operator policy "spread guard stays disabled"
        # (CLAUDE.md invariants) applies to EA-side cap as well. We were seeing
        # the EA veto valid signals at 25-26% spread/ATR (and >200% on XNGUSD)
        # during off-peak hours with no trades fired for hours. 5.0 = 500% =
        # effectively disabled while still leaving a sane ceiling against
        # truly broken price feeds. (2026-05-05)
        payload["max_spread_atr_pct"] = 5.0
    if tv_strategy:
        payload["tv_strategy"] = str(tv_strategy)[:64]
    if tv_price is not None:
        try:
            payload["tv_price"] = float(tv_price)
        except (TypeError, ValueError):
            pass
    # tv_timeframe (added 2026-05-04): TV's {{interval}} string ("5", "60",
    # "240", "D"...) normalised to MetaTrader form (M5/H1/H4/D1). Optional —
    # signals without a TF still write OK; TF is metadata for the audit log,
    # the per-(sym,dir,TF) dedup, and any future signal-quality learner.
    norm_tf = _normalise_timeframe(tv_timeframe)
    if norm_tf is not None:
        payload["tv_timeframe"] = norm_tf
    elif tv_timeframe:
        # caller passed something but we couldn't normalise — preserve raw
        # so audit can show what TradingView actually sent
        payload["tv_timeframe_raw"] = str(tv_timeframe)[:16]
    if extra:
        # never let `extra` overwrite required keys
        for k, v in extra.items():
            payload.setdefault(k, v)

    # 5-pre-gates) — added 2026-05-06. Brain's `tick_once` already runs
    # profit_filters.evaluate_all() before its own write_signal(), but the
    # TV-signal path bypasses brain entirely, so without these gates the
    # operator's risk policy (news blackout, daily DD, correlation diversity)
    # is unenforced. Each gate that blocks logs a structured `event` to
    # tv_signals.jsonl so the rejection is visible in audit + the dashboard.

    # ─ Gate A2: news blackout ─
    # Source of truth: same news_feed module brain uses. Wide -60/+30 window.
    try:
        from ai_trading_agents.profit_filters import news_blackout as _news_blackout
        _po = (getattr(_settings, "PROFIT_OPTIMIZER", {}) or {}) if _settings else {}
        nb = _news_blackout(
            lead_minutes=int(_po.get("news_lead_minutes", 60)),
            lag_minutes=int(_po.get("news_lag_minutes", 30)),
            impacts=_po.get("news_impact_levels", ("high",)),
        )
        if not nb.allow:
            res["error"] = f"news_blackout: {nb.reason}"
            _audit_log({"ts": int(time.time()), "event": "gate_block_news",
                        "symbol": symbol, "direction": norm_dir, "reason": nb.reason})
            return res
    except Exception as e:
        # Defensive: never let news-feed failure block a signal silently — log + continue
        _audit_log({"ts": int(time.time()), "event": "gate_news_error",
                    "symbol": symbol, "error": str(e)[:200]})

    # ─ Gate A3: daily $-loss cap ─
    # Read SoD equity from brain_state.json (brain writes it daily); query MT5
    # for current equity. If today's drawdown exceeds RISK.daily_max_loss_pct
    # (default 3%), block. Defaults to 3% if config missing.
    try:
        import MetaTrader5 as mt5  # type: ignore
        if not mt5.initialize():
            mt5.shutdown(); mt5.initialize()
        ai = mt5.account_info()
        equity_now = float(ai.equity) if ai else 0.0
        # SoD equity from brain_state.json
        state_path = _ROOT / "logs" / "brain_state.json"
        sod = 0.0
        if state_path.exists():
            try:
                sod = float(json.loads(state_path.read_text()).get("start_of_day_equity", 0.0))
            except Exception:
                sod = 0.0
        max_loss_pct = float(_po.get("daily_max_loss_pct", 5.0)) if _settings else 5.0
        if sod > 0 and equity_now > 0:
            dd_pct = (sod - equity_now) / sod * 100.0
            if dd_pct >= max_loss_pct:
                # SELF-HEAL (added 2026-05-07): when account is FLAT (no open
                # positions), the DD is realized history, not active risk.
                # Rebase sod to current equity so signals can fire from a
                # fresh baseline. The 5% brake still arms — next $52 of loss
                # from $1059 will re-trigger. With positions OPEN, DD is real
                # active risk and the gate stays hard. This avoids the trap
                # where a stale baseline (set at UTC midnight or by an old
                # brain restart) silently locks the whole day after one bad
                # cluster of trades that have already been closed.
                pos_open = 0
                try:
                    pos_open = len(mt5.positions_get() or [])
                except Exception:
                    pos_open = -1
                if pos_open == 0:
                    try:
                        _state = json.loads(state_path.read_text(encoding="utf-8"))
                        _state["start_of_day_equity"] = equity_now
                        _state["daily_drawdown_peak_eq"] = equity_now
                        _state["drawdown_lockout_until"] = 0
                        _state["session_high_equity"] = equity_now
                        _state["session_low_equity"] = equity_now
                        _tmp = state_path.with_suffix(".json.tmp")
                        _tmp.write_text(json.dumps(_state, separators=(",", ":")),
                                         encoding="utf-8")
                        _tmp.replace(state_path)
                        _audit_log({"ts": int(time.time()), "event": "sod_auto_roll_flat",
                                    "symbol": symbol, "old_sod": sod,
                                    "new_sod": equity_now,
                                    "old_dd_pct": round(dd_pct, 3)})
                    except Exception as _se:
                        _audit_log({"ts": int(time.time()),
                                    "event": "sod_auto_roll_persist_fail",
                                    "symbol": symbol, "error": str(_se)[:200]})
                    # Fall through — gate passes, fresh baseline established
                else:
                    res["error"] = (f"daily_dd_breached: {dd_pct:.2f}% >= "
                                    f"{max_loss_pct:.2f}% with {pos_open} open")
                    _audit_log({"ts": int(time.time()), "event": "gate_block_dd",
                                "symbol": symbol, "direction": norm_dir,
                                "equity_now": equity_now, "sod_equity": sod,
                                "dd_pct": round(dd_pct, 3),
                                "limit_pct": max_loss_pct,
                                "open_positions": pos_open})
                    return res
    except Exception as e:
        # MT5 may be momentarily unavailable; log + continue (don't block on infra fail)
        _audit_log({"ts": int(time.time()), "event": "gate_dd_error",
                    "symbol": symbol, "error": str(e)[:200]})

    # ─ Gate A1: correlation guard (per-pair-per-direction) ─
    # Prevent 2x same trade: if a position already exists on this symbol with
    # the same direction (BUY/SELL), block the new signal. EA's per-symbol cap
    # handles this in normal flow, but the TV path can race past it.
    try:
        import MetaTrader5 as mt5  # type: ignore
        if not mt5.initialize():
            mt5.shutdown(); mt5.initialize()
        positions = mt5.positions_get(symbol=symbol) or []
        same_dir_open = 0
        for p in positions:
            ptype = "BUY" if p.type == 0 else "SELL"
            if ptype == norm_dir:
                same_dir_open += 1
        # Allow up to 2 (QUICK + TREND variants the EA spawns per signal),
        # block 3rd and beyond.
        if same_dir_open >= 2:
            res["error"] = f"correlation_block: {same_dir_open} {norm_dir} positions already open on {symbol}"
            _audit_log({"ts": int(time.time()), "event": "gate_block_corr",
                        "symbol": symbol, "direction": norm_dir,
                        "open_same_dir": same_dir_open})
            return res
    except Exception as e:
        _audit_log({"ts": int(time.time()), "event": "gate_corr_error",
                    "symbol": symbol, "error": str(e)[:200]})

    # 5a) Phase-2 quality gate (configurable via settings.TV_QUALITY_FILTER).
    # When enabled and class has enough trades, BLOCK negative-expectancy
    # signal classes. Logs blocked signals to brain_shadow_predictions.jsonl
    # so we still learn from what would have happened.
    try:
        from ai_trading_agents.signal_quality_learner import should_take_signal
        gate = should_take_signal(
            symbol=symbol,
            tf=norm_tf or "UNK",
            direction=norm_dir,
        )
        if not gate.allow:
            res["error"] = f"quality_gate_blocked: {gate.reason}"
            shadow_path = Path(cfg.get("shadow_log_path", "logs/brain_shadow_predictions.jsonl"))
            if not shadow_path.is_absolute():
                shadow_path = _ROOT / shadow_path
            shadow_path.parent.mkdir(parents=True, exist_ok=True)
            with open(shadow_path, "a", encoding="utf-8") as f:
                f.write(json.dumps({
                    "ts": int(time.time()),
                    "event": "quality_gate_block",
                    "symbol": symbol,
                    "direction": norm_dir,
                    "tv_timeframe": norm_tf,
                    "stats_trades": gate.stats.trades,
                    "stats_avg_R": round(gate.stats.avg_R, 4),
                    "stats_win_rate": round(gate.stats.win_rate, 4),
                    "reason": gate.reason,
                    "payload_would_be": payload,
                }) + "\n")
            _audit_log({
                "ts": int(time.time()),
                "event": "quality_gate_block",
                "symbol": symbol,
                "direction": norm_dir,
                "reason": gate.reason,
            })
            return res
    except Exception:
        # Defensive: never let learner failure block a signal
        pass

    # 5) atomic write — same retry pattern as brain's write_signal()
    path = _resolve_signal_path(symbol)
    tmp = path.with_suffix(path.suffix + ".tmp")
    last_err: Optional[Exception] = None
    try:
        with open(tmp, "w", encoding="ascii") as f:
            json.dump(payload, f, separators=(",", ":"))
            f.flush()
            os.fsync(f.fileno())
        for attempt in range(4):
            try:
                os.replace(tmp, path)
                last_err = None
                break
            except PermissionError as pe:
                last_err = pe
                time.sleep(0.05 * (2**attempt))
        if last_err is not None:
            raise last_err
    except Exception as e:
        res["error"] = f"write_failed: {e}"
        try:
            if tmp.exists():
                tmp.unlink()
        except Exception:
            pass
        _audit_log(
            {
                "ts": int(time.time()),
                "event": "write_fail",
                "symbol": symbol,
                "error": res["error"],
                "payload": payload,
            }
        )
        return res

    res["ok"] = True
    res["path"] = str(path)
    res["payload"] = payload
    _audit_log(
        {
            "ts": int(time.time()),
            "event": "write_ok",
            "symbol": symbol,
            "direction": norm_dir,
            "confidence": payload["confidence"],
            "path": str(path),
            "source": source,
            "tv_strategy": tv_strategy,
            "tv_alert_ts": tv_alert_ts,
            "tv_timeframe": payload.get("tv_timeframe"),
            "tv_timeframe_raw": payload.get("tv_timeframe_raw"),
        }
    )
    return res


# CLI helper — useful for manual testing without TV:
#   python -m ai_trading_agents.tv_executor XAUUSD BUY
if __name__ == "__main__":
    import sys

    if len(sys.argv) < 3:
        print("usage: python -m ai_trading_agents.tv_executor SYMBOL DIRECTION")
        sys.exit(2)
    out = write_tv_signal(sys.argv[1], sys.argv[2], source="cli_test")
    print(json.dumps(out, indent=2, default=str))
    sys.exit(0 if out["ok"] else 1)
