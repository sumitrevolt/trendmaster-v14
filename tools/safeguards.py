"""Safety checks the Python executor consults before placing any order.

Each function returns (allowed: bool, reason: str). The executor calls them
in sequence; the first one to refuse stops the trade and logs the reason.

Modules:
    1. news_blackout_active(symbol)         — skip trades around high-impact news
    2. drawdown_breaker_tripped()           — pause if today's DD > 5%
    3. spread_too_wide(symbol)              — skip if spread > 50% of ATR
    4. correlation_overexposed(symbol, dir) — limit USD exposure across pairs
    5. mt5_health_check()                   — detect disconnects (used by watchdog)
"""
from __future__ import annotations

import json
import logging
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Tuple

import MetaTrader5 as mt5

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

LOG_DIR = ROOT / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

log = logging.getLogger("safeguards")

# Persistent state
_DD_STATE_PATH = LOG_DIR / "dd_state.json"

# ──────────────────────────────────────────────────────────────────────
# 1. NEWS BLACKOUT
# ──────────────────────────────────────────────────────────────────────
NEWS_LEAD_MIN = 60   # block trades 60 min before high-impact news
NEWS_LAG_MIN = 30    # block trades 30 min after high-impact news
NEWS_CALENDAR_PATH = ROOT / "config" / "news_calendar.json"


def _currencies_for(symbol: str):
    """Extract currencies the symbol is exposed to.
    EURUSD → ('EUR', 'USD'); XAUUSD → ('XAU', 'USD'); BTCUSD → ('BTC', 'USD')."""
    s = symbol.upper()
    # 6-char standard FX
    if len(s) == 6:
        return (s[:3], s[3:])
    # Treat XAU/XAG/XTI/XBR/XNG as commodity vs USD
    if len(s) == 6 and s[:3] in ("XAU", "XAG", "XTI", "XBR", "XNG"):
        return (s[:3], "USD")
    return (s, "USD")


def news_blackout_active(symbol: str) -> Tuple[bool, str]:
    """True (blocked) if a high-impact news event for this symbol's currency
    is within [-LEAD, +LAG] minutes from now."""
    if not NEWS_CALENDAR_PATH.exists():
        return False, "no calendar"
    try:
        events = json.loads(NEWS_CALENDAR_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        log.warning("news calendar read failed: %s", e)
        return False, "calendar parse error"

    now = datetime.now(timezone.utc)
    syms = set(_currencies_for(symbol))
    for ev in events:
        impact = (ev.get("impact") or "").lower()
        if impact != "high":
            continue
        cur = (ev.get("currency") or "").upper()
        if cur not in syms:
            continue
        try:
            ev_time = datetime.fromisoformat(ev["datetime_utc"].replace("Z", "+00:00"))
        except Exception:
            continue
        lead = ev_time - timedelta(minutes=NEWS_LEAD_MIN)
        lag = ev_time + timedelta(minutes=NEWS_LAG_MIN)
        if lead <= now <= lag:
            return True, f"news blackout: {cur} {ev.get('event','?')} @ {ev_time.strftime('%H:%M')}UTC"
    return False, "no nearby news"


# ──────────────────────────────────────────────────────────────────────
# 2. DAILY DRAWDOWN CIRCUIT BREAKER
# ──────────────────────────────────────────────────────────────────────
MAX_DAILY_DD_PCT = 5.0  # if today's drawdown exceeds 5% of start equity, halt


def _today_str() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _load_dd_state() -> dict:
    if _DD_STATE_PATH.exists():
        try:
            return json.loads(_DD_STATE_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _save_dd_state(d: dict) -> None:
    try:
        _DD_STATE_PATH.write_text(json.dumps(d, indent=2), encoding="utf-8")
    except Exception:
        pass


def drawdown_breaker_tripped() -> Tuple[bool, str]:
    """Check today's drawdown vs start-of-day equity.
    Stores start_equity per day. If equity drops > MAX_DAILY_DD_PCT, returns True."""
    ai = mt5.account_info()
    if not ai:
        return False, "no account info"
    today = _today_str()
    state = _load_dd_state()
    if state.get("date") != today:
        # New day — record start equity
        state = {"date": today, "start_equity": ai.equity, "tripped": False, "trip_at": None}
        _save_dd_state(state)
        return False, "new day, recorded start"
    # Sticky trip — once tripped, stays tripped until midnight
    if state.get("tripped"):
        return True, f"DD tripped earlier today at equity={state.get('trip_at')}"
    start_eq = state.get("start_equity", ai.equity)
    dd_pct = (start_eq - ai.equity) / start_eq * 100 if start_eq > 0 else 0
    if dd_pct >= MAX_DAILY_DD_PCT:
        state["tripped"] = True
        state["trip_at"] = ai.equity
        state["trip_dd_pct"] = round(dd_pct, 2)
        _save_dd_state(state)
        return True, f"DD breaker TRIPPED: {dd_pct:.1f}% loss today (start={start_eq:.2f}, now={ai.equity:.2f})"
    return False, f"DD ok: {dd_pct:.2f}% today"


# ──────────────────────────────────────────────────────────────────────
# 3. SPREAD CHECK
# ──────────────────────────────────────────────────────────────────────
MAX_SPREAD_ATR_RATIO = 0.5  # spread > 50% of ATR(H1) → reject (truly broken price)


def spread_too_wide(symbol: str) -> Tuple[bool, str]:
    info = mt5.symbol_info(symbol)
    tick = mt5.symbol_info_tick(symbol)
    if not info or not tick:
        return False, "no tick"
    spread_pr = tick.ask - tick.bid
    if spread_pr <= 0:
        return False, "no spread (likely closed market)"
    # Get ATR(H1)
    rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_H1, 0, 15)
    if rates is None or len(rates) < 15:
        return False, "no ATR data"
    trs = []
    for i in range(1, len(rates)):
        h, l, pc = rates[i]["high"], rates[i]["low"], rates[i - 1]["close"]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    atr = sum(trs) / len(trs) if trs else 0
    if atr <= 0:
        return False, "atr=0"
    ratio = spread_pr / atr
    if ratio > MAX_SPREAD_ATR_RATIO:
        return True, f"spread too wide: {ratio*100:.0f}% of ATR (cap {MAX_SPREAD_ATR_RATIO*100:.0f}%)"
    return False, f"spread ok: {ratio*100:.0f}% of ATR"


# ──────────────────────────────────────────────────────────────────────
# 4. CORRELATION GUARD (USD exposure)
# ──────────────────────────────────────────────────────────────────────
MAX_SAME_SIDE_USD_POSITIONS = 3  # at most 3 positions tilting same way on USD


def _usd_side(symbol: str, is_buy: bool) -> int:
    """+1 = long USD; -1 = short USD; 0 = no USD exposure.

    [2026-05-17 operator policy] BTCUSD + ETHUSD exempt from USD-side cap.
    Crypto is its own asset class — not really USD exposure like USDJPY/GBPUSD.
    Cluster cap (CRYPTO max 2 same-direction) is the real concentration guard
    for crypto. Fixes weekend-block where BTCUSD SELL got blocked by
    'already 4 long-USD positions (cap 3)' on Sat 22:16 + Sun 08:05 IST 2026-05-16/17.
    """
    s = symbol.upper()
    # Crypto exemption — own asset class, not USD-correlated like FX
    if s in ("BTCUSD", "ETHUSD"):
        return 0
    if s.endswith("USD") or s.startswith("XAU") or s.startswith("XAG") or s in ("XTIUSD", "XBRUSD", "XNGUSD"):
        # XXXUSD — BUY = short USD, SELL = long USD
        return -1 if is_buy else +1
    if s.startswith("USD"):
        # USDXXX — BUY = long USD, SELL = short USD
        return +1 if is_buy else -1
    return 0  # cross-pair (EURJPY etc.) — no direct USD exposure


def correlation_overexposed(symbol: str, direction: str) -> Tuple[bool, str]:
    """Reject if adding this trade would put us > MAX same-side USD positions."""
    pos = mt5.positions_get() or []
    cur_long = 0
    cur_short = 0
    for p in pos:
        side = _usd_side(p.symbol, p.type == mt5.ORDER_TYPE_BUY)
        if side > 0:
            cur_long += 1
        elif side < 0:
            cur_short += 1
    new_side = _usd_side(symbol, direction.upper() == "BUY")
    if new_side > 0 and cur_long >= MAX_SAME_SIDE_USD_POSITIONS:
        return True, f"already {cur_long} long-USD positions (cap {MAX_SAME_SIDE_USD_POSITIONS})"
    if new_side < 0 and cur_short >= MAX_SAME_SIDE_USD_POSITIONS:
        return True, f"already {cur_short} short-USD positions (cap {MAX_SAME_SIDE_USD_POSITIONS})"
    return False, f"USD exposure ok (long={cur_long}, short={cur_short})"


# ──────────────────────────────────────────────────────────────────────
# 4b. CORRELATION CLUSTERS (2026-05-13 v2 — research-driven)
# ──────────────────────────────────────────────────────────────────────
# Industry guidance: positions in highly-correlated pairs aren't
# independent bets — they're one concentrated bet. EUR/USD + GBP/USD
# in same direction = doubling USD-side exposure. Cluster cap stops
# silent over-concentration that bypasses long-USD/short-USD limits.
#
# Cluster definitions sourced from rolling 90-day correlations published
# in retail FX risk research (ActivTrades, AlphaExCapital 2026 guides).
CORRELATION_CLUSTERS = {
    "USD_MAJORS":    {"EURUSD", "GBPUSD"},           # ~0.85 corr
    "USD_COMMODITY": {"AUDUSD", "NZDUSD"},           # ~0.88 corr
    "PRECIOUS":      {"XAUUSD", "XAGUSD"},           # ~0.80 corr (gold leads)
    "OIL":           {"XTIUSD", "XBRUSD"},           # ~0.95 corr (Brent ~ WTI + premium)
    "CRYPTO":        {"BTCUSD", "ETHUSD"},           # ~0.70 corr
    "JPY_RISK":      {"USDJPY", "EURJPY", "GBPJPY", "AUDJPY", "CADJPY"},  # carry-trade complex
}
MAX_PER_CLUSTER_SAME_DIR = 2  # never more than 2 same-direction trades within a cluster


def correlation_cluster_overexposed(symbol: str, direction: str) -> Tuple[bool, str]:
    """Reject if adding this trade would create > MAX_PER_CLUSTER_SAME_DIR
    same-direction positions within a correlation cluster.

    Example: already long XAUUSD + long XAGUSD, new XAGUSD BUY (same direction)
    would create 3 long PRECIOUS-cluster trades → reject.
    """
    sym_upper = symbol.upper()
    # Find which clusters this symbol belongs to
    relevant_clusters = [name for name, members in CORRELATION_CLUSTERS.items() if sym_upper in members]
    if not relevant_clusters:
        return False, "no cluster membership"

    pos = mt5.positions_get() or []
    new_dir = direction.upper()
    for cname in relevant_clusters:
        same_dir_count = 0
        for p in pos:
            if p.symbol.upper() not in CORRELATION_CLUSTERS[cname]:
                continue
            cur_dir = "BUY" if p.type == mt5.ORDER_TYPE_BUY else "SELL"
            if cur_dir == new_dir:
                same_dir_count += 1
        if same_dir_count >= MAX_PER_CLUSTER_SAME_DIR:
            return True, (f"cluster {cname} already has {same_dir_count} "
                          f"same-direction positions (cap {MAX_PER_CLUSTER_SAME_DIR})")
    return False, "cluster exposure ok"


# ──────────────────────────────────────────────────────────────────────
# 4c. EQUITY-TIER SCALING (2026-05-13 v2)
# ──────────────────────────────────────────────────────────────────────
# Caps scale with account size. Small account needs tighter concentration
# (single position can wipe out higher % of capital). Large account can
# diversify more.
EQUITY_TIERS = [
    # (max_equity_usd, max_total_open_positions, comment)
    # 2026-05-13: operator override — cap=10 for current account size.
    # Previous tier scaling (2/5/8/12) replaced with operator-chosen 10.
    # Justification: $1077 account at 0.5% risk × 10 = 5% max simultaneous
    # risk — still under daily DD breaker (5%) so account-level protection
    # remains intact. Operator wants more diversification room.
    (500,    5,  "micro: still tight for tiny accounts"),
    (999999, 10, "operator-chosen: 10 simultaneous positions"),
]


def equity_tier_check(symbol: str, direction: str) -> Tuple[bool, str]:
    """Reject if total open positions exceeds the equity-tier cap."""
    ai = mt5.account_info()
    if not ai:
        return False, "equity_tier: no account_info"
    equity = ai.equity
    pos = mt5.positions_get() or []
    n_open = len(pos)

    cap = 12  # default
    tier_label = "large"
    for max_eq, max_open, label in EQUITY_TIERS:
        if equity <= max_eq:
            cap = max_open
            tier_label = label
            break
    if n_open >= cap:
        return True, (f"equity-tier '{tier_label}' (eq=${equity:.0f}) "
                      f"cap={cap} reached (current={n_open})")
    return False, f"equity-tier ok ({n_open}/{cap}, {tier_label})"


# ──────────────────────────────────────────────────────────────────────
# 4d. PER-SYMBOL DAILY LOSS CAP (2026-05-13 v2)
# ──────────────────────────────────────────────────────────────────────
# Single symbol losing >X% of account in one day → block until next day.
# Prevents revenge trading on one bad pair.
PER_SYMBOL_DAILY_LOSS_PCT = 1.0  # 1% of equity = stop trading this symbol today


def per_symbol_daily_loss_blocked(symbol: str, direction: str) -> Tuple[bool, str]:
    """Reject if today's realized + unrealized PnL on this symbol < -X% of equity."""
    ai = mt5.account_info()
    if not ai:
        return False, "no account_info"
    equity = ai.equity
    if equity <= 0:
        return False, "zero equity"

    # Today's deals for this symbol
    now = datetime.now()
    day_start = datetime(now.year, now.month, now.day, 0, 0, 0)
    deals = mt5.history_deals_get(day_start, now) or []
    realized = sum(d.profit for d in deals if d.symbol == symbol.upper())

    # Floating PnL on this symbol
    pos = mt5.positions_get(symbol=symbol.upper()) or []
    floating = sum(p.profit for p in pos)

    total = realized + floating
    pct_of_equity = (total / equity) * 100.0
    if pct_of_equity <= -PER_SYMBOL_DAILY_LOSS_PCT:
        return True, (f"symbol {symbol} day-PnL ${total:.2f} ({pct_of_equity:.2f}%) "
                      f"≤ -{PER_SYMBOL_DAILY_LOSS_PCT}% cap — blocked rest of day")
    return False, f"symbol day-PnL ${total:.2f} ({pct_of_equity:+.2f}%) ok"


# ──────────────────────────────────────────────────────────────────────
# 4e. TIME-OF-DAY BLACKOUT (2026-05-13 v2)
# ──────────────────────────────────────────────────────────────────────
# Avoid thin-liquidity / weekend-gap risk windows. All times IST.
TOD_BLACKOUTS = [
    # (label, weekday[0=Mon, 6=Sun], start_hhmm_ist, end_hhmm_ist, reason)
    ("FRIDAY_LATE",   4, "21:00", "23:59", "Friday post-NY: weekend gap risk"),
    ("SUNDAY_EARLY",  6, "00:00", "04:00", "Sunday pre-Tokyo: thin liquidity"),
    ("SUNDAY_OPEN",   6, "04:00", "04:30", "Sunday FX open: spread spike"),
    ("TOKYO_OPEN",    0, "05:30", "05:45", "Tokyo open: spread widening"),  # Mon
    ("LONDON_OPEN",   0, "13:00", "13:15", "London open: spread widening"),  # All weekdays — see TOD_DAILY
]
# Daily windows (every weekday):
TOD_DAILY = [
    ("LONDON_OPEN_DAILY", "13:00", "13:15", "London FX open: spread spike"),
    ("NY_OPEN_DAILY",     "18:30", "18:45", "NY FX open: spread spike"),
]


def time_of_day_blackout(symbol: str, direction: str) -> Tuple[bool, str]:
    """Reject if current IST time falls in a configured blackout window.

    [2026-05-17 operator policy] BTCUSD + ETHUSD exempt from ALL time-of-day
    blackouts. Crypto trades 24/7 — no weekend gap, no FX session opens. Fixes
    weekend-block where ETHUSD SELL got blocked on Sun 00:01 IST 2026-05-17 by
    'SUNDAY_EARLY: Sunday pre-Tokyo: thin liquidity'.
    """
    sym_upper = symbol.upper()
    is_crypto = sym_upper in ("BTCUSD", "ETHUSD")
    if is_crypto:
        return False, "time-of-day ok (crypto 24/7 — exempt)"

    now = datetime.now()
    weekday = now.weekday()
    hhmm = now.strftime("%H:%M")

    # Daily windows (every weekday)
    if weekday < 5:  # Mon-Fri
        for label, start, end, reason in TOD_DAILY:
            if start <= hhmm < end:
                return True, f"time-of-day {label}: {reason}"

    # Specific weekday windows
    for label, wd, start, end, reason in TOD_BLACKOUTS:
        if wd == weekday and start <= hhmm < end:
            return True, f"time-of-day {label}: {reason}"

    return False, "time-of-day ok"


# ──────────────────────────────────────────────────────────────────────
# 4f. BRAIN DECISION VETO (2026-05-13 v2 — operator-requested)
# ──────────────────────────────────────────────────────────────────────
# Brain runs rule-based inference (EMA / RSI / ADX / BB-Z) on H1 frames.
# Operator policy: if brain STRONGLY disagrees with RP signal direction,
# block the trade. Brain doesn't approve positively — RP does. Brain
# is the safety check that catches signals where indicator and market
# context disagree.
#
# Brain veto rules:
#   - Brain confidence ≥ 0.65 AND direction differs from RP → BLOCK
#   - Brain has no recent view (>1 hr stale) → defer to RP (allow)
#   - Brain confidence < 0.65 → defer to RP (allow — low conviction)
#   - Brain agrees → allow
#
# Disable via `BRAIN_VETO_ENABLED=0` in config/.env.
BRAIN_VETO_ENABLED = True
BRAIN_VETO_MIN_CONFIDENCE = 0.65
BRAIN_VIEW_STALENESS_SEC = 3600

_BRAIN_STATE_PATH = LOG_DIR / "brain_state.json"


def brain_agrees_with_signal(symbol: str, direction: str) -> Tuple[bool, str]:
    """Return (blocked, reason). Block if brain strongly disagrees with RP."""
    import os as _os
    if _os.getenv("BRAIN_VETO_ENABLED", "1").strip() in ("0", "false", "FALSE", "no"):
        return False, "brain veto disabled (env)"
    if not BRAIN_VETO_ENABLED:
        return False, "brain veto disabled (config)"
    if not _BRAIN_STATE_PATH.exists():
        return False, "no brain_state.json — defer to RP"
    try:
        state = json.loads(_BRAIN_STATE_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        return False, f"brain_state.json read failed: {e}"

    sym = symbol.upper()
    sig_dir = direction.upper()

    last_signal_map = state.get("last_signal_per_symbol") or {}
    brain_view = last_signal_map.get(sym)
    if not brain_view:
        return False, "brain has no view for this symbol — defer to RP"

    brain_dir = (brain_view.get("direction") or "").upper()
    brain_conf = float(brain_view.get("confidence") or 0)
    brain_ts = int(brain_view.get("ts") or 0)

    age_s = time.time() - brain_ts
    if age_s > BRAIN_VIEW_STALENESS_SEC:
        return False, f"brain view {int(age_s/60)}min stale — defer to RP"

    # If brain says NONE, check pre-gate directional view
    if brain_dir == "NONE":
        directional_map = state.get("last_signal_direction") or {}
        brain_dir = (directional_map.get(sym) or "").upper()
        if brain_dir not in ("BUY", "SELL"):
            return False, "brain view NONE/empty — defer to RP"
        overall_ts = int(state.get("last_saved_at") or 0)
        if time.time() - overall_ts > BRAIN_VIEW_STALENESS_SEC:
            return False, "brain directional view stale — defer to RP"

    if brain_conf < BRAIN_VETO_MIN_CONFIDENCE:
        return False, (f"brain {brain_dir} conf={brain_conf:.2f} "
                       f"< {BRAIN_VETO_MIN_CONFIDENCE} — defer to RP")

    if brain_dir == sig_dir:
        return False, f"brain AGREES: {brain_dir} conf={brain_conf:.2f}"

    return True, (f"brain VETO: RP={sig_dir} brain={brain_dir} "
                  f"conf={brain_conf:.2f} age={int(age_s)}s")


# ──────────────────────────────────────────────────────────────────────
# 4g. STRICTER BRAIN GATE FOR FLIPS (2026-05-17 operator-requested)
# ──────────────────────────────────────────────────────────────────────
# brain_agrees_with_signal above is permissive — it "defers to RP" when
# brain has no view, weak conf, or stale data. That's fine for FIRST
# entries (no existing position to risk).
#
# For FLIPS (close existing position + open opposite), operator wants
# stricter: brain MUST explicitly endorse the new direction. If brain
# has no view / weak / stale / disagrees → BLOCK the flip, keep the
# existing position. Don't churn on uncertainty.
#
# Threshold lower than veto (0.65) because flip-permission is harder
# to earn than no-veto.
BRAIN_EXPLICIT_AGREE_MIN_CONF = 0.55


def brain_explicitly_agrees(symbol: str, direction: str) -> Tuple[bool, str]:
    """STRICTER than brain_agrees_with_signal. Returns (agrees, reason).

    agrees=True ONLY if:
      - brain_state.json exists AND parseable
      - brain has a view for this symbol
      - brain view age < BRAIN_VIEW_STALENESS_SEC
      - brain direction in (BUY, SELL) — not NONE / empty
      - brain confidence >= BRAIN_EXPLICIT_AGREE_MIN_CONF (0.55)
      - brain direction == signal direction

    Used for flip-on-opposite gating. Conservative — when in doubt, don't flip.
    """
    if not _BRAIN_STATE_PATH.exists():
        return False, "no brain_state.json — won't flip without brain confirmation"
    try:
        state = json.loads(_BRAIN_STATE_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        return False, f"brain_state.json read failed: {e} — won't flip"

    sym = symbol.upper()
    sig_dir = direction.upper()

    last_signal_map = state.get("last_signal_per_symbol") or {}
    brain_view = last_signal_map.get(sym)
    if not brain_view:
        return False, f"brain has no view for {sym} — won't flip"

    brain_dir = (brain_view.get("direction") or "").upper()
    brain_conf = float(brain_view.get("confidence") or 0)
    brain_ts = int(brain_view.get("ts") or 0)

    age_s = time.time() - brain_ts
    if age_s > BRAIN_VIEW_STALENESS_SEC:
        return False, f"brain view {int(age_s/60)}min stale — won't flip"

    if brain_dir == "NONE":
        # Try pre-gate directional view as fallback
        directional_map = state.get("last_signal_direction") or {}
        brain_dir = (directional_map.get(sym) or "").upper()
        if brain_dir not in ("BUY", "SELL"):
            return False, "brain view NONE — won't flip"
        overall_ts = int(state.get("last_saved_at") or 0)
        if time.time() - overall_ts > BRAIN_VIEW_STALENESS_SEC:
            return False, "brain directional view stale — won't flip"

    if brain_dir not in ("BUY", "SELL"):
        return False, f"brain dir invalid: {brain_dir!r} — won't flip"

    if brain_conf < BRAIN_EXPLICIT_AGREE_MIN_CONF:
        return False, (f"brain {brain_dir} conf={brain_conf:.2f} "
                       f"< {BRAIN_EXPLICIT_AGREE_MIN_CONF} — won't flip")

    if brain_dir != sig_dir:
        return False, (f"brain disagrees: brain={brain_dir} signal={sig_dir} "
                       f"conf={brain_conf:.2f} — won't flip")

    return True, f"brain agrees: {brain_dir} conf={brain_conf:.2f} age={int(age_s)}s"


# ──────────────────────────────────────────────────────────────────────
# 5. MT5 HEALTH CHECK (used by watchdog)
# ──────────────────────────────────────────────────────────────────────
def mt5_health_check() -> Tuple[bool, str]:
    """Return (healthy, msg). False if disconnected from broker."""
    if not mt5.initialize():
        return False, f"mt5.initialize failed: {mt5.last_error()}"
    ti = mt5.terminal_info()
    if not ti:
        return False, "no terminal_info"
    if not ti.connected:
        return False, "MT5 disconnected from broker"
    ai = mt5.account_info()
    if not ai:
        return False, "no account_info (login failed?)"
    return True, f"MT5 ok build={ti.build} balance=${ai.balance:.2f}"


# ──────────────────────────────────────────────────────────────────────
# Master gate — called by executor
# ──────────────────────────────────────────────────────────────────────
def check_all(symbol: str, direction: str) -> Tuple[bool, str]:
    """Run all order-time safeguards. Returns (allowed, reason).
    Order matters: cheapest checks first.

    2026-05-13 v2 — 4 new layers (correlation cluster, equity tier,
    per-symbol day cap, time-of-day) — research-driven, see skill
    trading-risk-management-v2/SKILL.md.
    """
    # Drawdown first (account-level, no per-symbol cost)
    blocked, reason = drawdown_breaker_tripped()
    if blocked:
        return False, reason
    # News (cheap file read)
    blocked, reason = news_blackout_active(symbol)
    if blocked:
        return False, reason
    # Time-of-day blackout (cheap — just clock check)
    blocked, reason = time_of_day_blackout(symbol, direction)
    if blocked:
        return False, reason
    # Per-symbol daily loss cap (one history query)
    blocked, reason = per_symbol_daily_loss_blocked(symbol, direction)
    if blocked:
        return False, reason
    # Equity tier cap (cheap account_info query)
    blocked, reason = equity_tier_check(symbol, direction)
    if blocked:
        return False, reason
    # USD-side correlation (cheap MT5 positions query)
    blocked, reason = correlation_overexposed(symbol, direction)
    if blocked:
        return False, reason
    # Correlation cluster (same query, different aggregation)
    blocked, reason = correlation_cluster_overexposed(symbol, direction)
    if blocked:
        return False, reason
    # BRAIN VETO (2026-05-13 operator-requested) — last filter before placing.
    # Brain checks if its current inference agrees with RP direction.
    blocked, reason = brain_agrees_with_signal(symbol, direction)
    if blocked:
        return False, reason
    # Spread (more expensive ATR fetch, last)
    blocked, reason = spread_too_wide(symbol)
    if blocked:
        return False, reason
    return True, "all safeguards passed"


if __name__ == "__main__":
    # CLI smoke test
    mt5.initialize()
    print("=== safeguards smoke test ===")
    for fn_name, fn in [
        ("DD breaker", lambda: drawdown_breaker_tripped()),
        ("news XAUUSD", lambda: news_blackout_active("XAUUSD")),
        ("news EURUSD", lambda: news_blackout_active("EURUSD")),
        ("spread XAUUSD", lambda: spread_too_wide("XAUUSD")),
        ("spread EURUSD", lambda: spread_too_wide("EURUSD")),
        ("corr XAUUSD BUY", lambda: correlation_overexposed("XAUUSD", "BUY")),
        ("MT5 health", lambda: mt5_health_check()),
    ]:
        blocked, reason = fn()
        mark = "BLOCK" if blocked else "OK   "
        print(f"  [{mark}] {fn_name}: {reason}")
    mt5.shutdown()
