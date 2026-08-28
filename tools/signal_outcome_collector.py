"""Periodic MT5 trade outcome collector.

Polls MT5 for newly-closed deals and joins each with the most recent matching
TV webhook signal (by symbol + direction + time-window). Writes joined records
to logs/signal_outcomes.jsonl which signal_quality_learner reads.

Idempotent: tracks the last-processed deal ticket via state file, so re-runs
only emit new outcomes.

Run via Task Scheduler every 5 min HIDDEN (use hidden_signal_outcome_collector.vbs).
"""
from __future__ import annotations
import json
import logging
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

LOG_DIR = ROOT / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
SIGNALS_PATH = LOG_DIR / "tv_signals.jsonl"
OUTCOMES_PATH = LOG_DIR / "signal_outcomes.jsonl"
STATE_PATH = LOG_DIR / "signal_outcome_collector_state.json"
LOG_PATH = LOG_DIR / "signal_outcome_collector.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler(LOG_PATH, encoding="utf-8")],
)
log = logging.getLogger("outcome_collector")

# Tunables
SIGNAL_MATCH_WINDOW_S = 600  # signal must be within 10 min before deal open
LOOKBACK_HOURS = 48          # initial scan window for "new" deals


def _load_state() -> dict:
    if STATE_PATH.exists():
        try:
            return json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _save_state(s: dict) -> None:
    STATE_PATH.write_text(json.dumps(s, indent=2), encoding="utf-8")


def _load_recent_signals(cutoff_ts: float) -> list[dict]:
    """Read tv_signals.jsonl, return write_ok records since cutoff."""
    out: list[dict] = []
    if not SIGNALS_PATH.exists():
        return out
    try:
        with SIGNALS_PATH.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                if rec.get("event") != "write_ok":
                    continue
                ts = rec.get("ts", 0)
                if ts < cutoff_ts:
                    continue
                out.append(rec)
    except OSError:
        pass
    return out


def _find_matching_signal(deal_open_ts: float, symbol: str, direction: str,
                          signals: list[dict]) -> dict | None:
    """Find the most recent signal matching this deal."""
    best = None
    for s in signals:
        if s.get("symbol") != symbol:
            continue
        if (s.get("direction") or "").upper() != direction.upper():
            continue
        ts = s.get("ts", 0)
        # Signal must be BEFORE the deal (with some tolerance for clock skew)
        if not (deal_open_ts - SIGNAL_MATCH_WINDOW_S <= ts <= deal_open_ts + 30):
            continue
        if best is None or ts > best.get("ts", 0):
            best = s
    return best


def _normalize_tf(tf_raw) -> str:
    """Normalize TF; mirrors tv_executor._normalise_timeframe but for output."""
    if not tf_raw:
        return "UNK"
    s = str(tf_raw).strip().upper()
    aliases = {"1": "M1", "5": "M5", "15": "M15", "30": "M30", "60": "H1",
               "120": "H2", "180": "H3", "240": "H4", "D": "D1", "W": "W1"}
    return aliases.get(s.lower(), s)


def main() -> int:
    log.info("--- outcome collector run ---")
    state = _load_state()
    last_deal_ticket = int(state.get("last_deal_ticket", 0))
    last_run_ts = float(state.get("last_run_ts", 0))

    # 1) Pull deals from MT5
    try:
        import MetaTrader5 as mt5
    except ImportError:
        log.error("MetaTrader5 not installed; cannot collect outcomes.")
        return 1

    if not mt5.initialize():
        log.error(f"mt5.initialize() failed: {mt5.last_error()}")
        return 2

    # Look back enough to catch any deals missed in prior runs
    lookback_start = datetime.now(timezone.utc) - timedelta(hours=LOOKBACK_HOURS)
    deals = mt5.history_deals_get(lookback_start, datetime.now(timezone.utc))
    if deals is None:
        log.error(f"history_deals_get failed: {mt5.last_error()}")
        mt5.shutdown()
        return 3

    log.info(f"MT5 returned {len(deals)} deals in last {LOOKBACK_HOURS}h")

    # Group deals by position_id (open + close legs of same trade)
    pos_legs: dict[int, list] = {}
    for d in deals:
        if d.position_id == 0:
            continue
        pos_legs.setdefault(d.position_id, []).append(d)

    # 2) Build closed trades (need both open + close leg)
    closed_trades = []
    for pos_id, legs in pos_legs.items():
        legs.sort(key=lambda x: x.time)
        if len(legs) < 2:
            continue  # still open
        open_leg = legs[0]
        close_leg = legs[-1]
        if open_leg.entry != mt5.DEAL_ENTRY_IN:
            continue
        if close_leg.entry != mt5.DEAL_ENTRY_OUT:
            continue
        # Skip if we've already processed this position
        if close_leg.ticket <= last_deal_ticket:
            continue
        direction = "BUY" if open_leg.type == mt5.DEAL_TYPE_BUY else "SELL"
        # Compute R-multiple: profit / (sl_distance * lot * tick_value) — approximate
        # Simpler: use profit in account currency normalized by initial risk_pct estimate
        # Most useful proxy: profit > 0 → win, R = profit / abs(swap+commission+fee) baseline
        # For now: use profit in account currency, R = profit / 10 (rough scale)
        profit = close_leg.profit + open_leg.profit + open_leg.swap + open_leg.commission + close_leg.swap + close_leg.commission
        # R-approximation: if profit is positive = win, magnitude in account currency / 10
        # Better: pull the SL from the order ticket; complexity for later.
        R_approx = profit / 10.0
        closed_trades.append({
            "position_id": pos_id,
            "ticket_close": close_leg.ticket,
            "ticket_open": open_leg.ticket,
            "symbol": open_leg.symbol,
            "direction": direction,
            "open_ts": open_leg.time,
            "close_ts": close_leg.time,
            "open_price": open_leg.price,
            "close_price": close_leg.price,
            "volume": open_leg.volume,
            "profit": profit,
            "R": R_approx,
            "win": profit > 0,
        })

    log.info(f"Found {len(closed_trades)} newly-closed trades to process")

    # ─── Telegram notification: per-trade close ────────────────────────────
    try:
        from ai_trading_agents.telegram_notifier import get_notifier
        _tg = get_notifier()
    except Exception:
        _tg = None
    if _tg and _tg.enabled and closed_trades:
        # Get current account state for context
        ai = mt5.account_info()
        for t in closed_trades:
            emoji = "🟢" if t["win"] else "🔴"
            dir_emoji = "📈" if t["direction"] == "BUY" else "📉"
            sign = "+" if t["profit"] >= 0 else ""
            msg = (
                f"<b>{emoji} {t['symbol']} {dir_emoji} CLOSED</b>\n"
                f"P/L: <b>{sign}${t['profit']:.2f}</b>  R: {t['R']:+.2f}\n"
                f"Open: <code>{t['open_price']:.5f}</code>  "
                f"Close: <code>{t['close_price']:.5f}</code>\n"
                f"Lots: {t['volume']}  Hold: {(t['close_ts'] - t['open_ts']) // 60}m"
            )
            if ai:
                msg += f"\nBalance: ${ai.balance:.2f}  Equity: ${ai.equity:.2f}"
            try:
                _tg.send(msg)
            except Exception as e:
                log.warning(f"telegram send failed for close: {e}")
    mt5.shutdown()

    # 3) Load recent signals to join with
    signals = _load_recent_signals(cutoff_ts=lookback_start.timestamp() - 3600)
    log.info(f"Loaded {len(signals)} recent signals from tv_signals.jsonl")

    # 4) Join + write outcomes
    written = 0
    new_max_ticket = last_deal_ticket
    with OUTCOMES_PATH.open("a", encoding="utf-8") as f:
        for trade in closed_trades:
            sig = _find_matching_signal(
                deal_open_ts=trade["open_ts"],
                symbol=trade["symbol"],
                direction=trade["direction"],
                signals=signals,
            )
            outcome = {
                "ts_signal": sig.get("ts") if sig else trade["open_ts"],
                "ts_open": trade["open_ts"],
                "ts_close": trade["close_ts"],
                "symbol": trade["symbol"],
                "direction": trade["direction"],
                "tf": _normalize_tf(sig.get("tv_timeframe") if sig else None),
                "tv_strategy": sig.get("tv_strategy") if sig else None,
                "profit": round(trade["profit"], 2),
                "R": round(trade["R"], 4),
                "win": trade["win"],
                "matched_signal": bool(sig),
                "position_id": trade["position_id"],
            }
            f.write(json.dumps(outcome, separators=(",", ":")) + "\n")
            written += 1
            if trade["ticket_close"] > new_max_ticket:
                new_max_ticket = trade["ticket_close"]

    log.info(f"Wrote {written} outcomes -> {OUTCOMES_PATH.name}")

    # 5) Save state
    _save_state({
        "last_deal_ticket": new_max_ticket,
        "last_run_ts": datetime.now(timezone.utc).timestamp(),
        "last_processed_count": written,
    })
    log.info(f"State saved. last_deal_ticket={new_max_ticket}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
