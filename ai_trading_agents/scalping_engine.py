"""Advanced scalping engine for TrendMaster v14.

Two complementary, latency-tolerant scalping modes:

1. SMC liquidity-sweep (momentum) - runs in London / NY overlap.
   Hunts sell-side / buy-side liquidity pools, waits for a sweep + CHoCH,
   then enters via a BUY_LIMIT / SELL_LIMIT at the origin order block
   (discount/OTE zone). Classic Smart-Money-Concepts structure.

2. Statistical mean-reversion - runs in the quiet Asian session.
   Fades Bollinger / z-score extremes with RSI confirmation, limit entry
   at the band extreme, target the VWAP / mid-band.

Both modes are LIMIT-order based (server-side fills) with hard filters:
spread cap, session gate, HTF-bias alignment, consecutive-loss kill-switch,
per-symbol / per-minute rate limits. This makes the async brain->executor
path viable for retail scalping where market-order latency is not.

Emits signals in the same schema the executor already consumes
(trendmaster_scalp_<SYM>.json) plus entry_price / order_kind so the
executor places a pending order instead of a market order.

MT5 access is optional: if MetaTrader5 is unavailable the engine falls back
to a provided dataframe source so it stays unit-testable and backtestable.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

import numpy as np

try:
    import MetaTrader5 as mt5  # type: ignore
    _HAS_MT5 = True
except Exception:
    mt5 = None
    _HAS_MT5 = False

_TF = {
    "M1": 1, "M5": 5, "M15": 15, "M30": 30,
    "H1": 60, "H4": 240, "D1": 1440,
}


def _tf_int(tf: str) -> int:
    return _TF.get(tf, 5)


def _rates(symbol: str, tf: str, n: int) -> Optional[Dict[str, np.ndarray]]:
    if not _HAS_MT5:
        return None
    try:
        r = mt5.copy_rates_from_pos(symbol, _tf_int(tf), 0, n)
    except Exception:
        return None
    if r is None or len(r) == 0:
        return None
    return {
        "time": np.array([int(x["time"]) for x in r]),
        "open": np.array([float(x["open"]) for x in r]),
        "high": np.array([float(x["high"]) for x in r]),
        "low": np.array([float(x["low"]) for x in r]),
        "close": np.array([float(x["close"]) for x in r]),
        "tick_volume": np.array([float(x["tick_volume"]) for x in r]),
    }


def _sma(a: np.ndarray, n: int) -> np.ndarray:
    if len(a) < n:
        return np.full(len(a), np.nan)
    out = np.full(len(a), np.nan)
    c = np.cumsum(a)
    out[n - 1:] = (c[n - 1:] - c[: len(a) - n + 1]) / n
    return out


def _ema(a: np.ndarray, n: int) -> np.ndarray:
    if len(a) == 0:
        return a
    k = 2.0 / (n + 1)
    out = np.empty(len(a))
    out[0] = a[0]
    for i in range(1, len(a)):
        out[i] = a[i] * k + out[i - 1] * (1 - k)
    return out


def _stdev(a: np.ndarray, n: int) -> np.ndarray:
    if len(a) < n:
        return np.full(len(a), np.nan)
    out = np.full(len(a), np.nan)
    c = np.cumsum(a)
    c2 = np.cumsum(a * a)
    for i in range(n - 1, len(a)):
        s = c[i] - c[i - n]
        s2 = c2[i] - c2[i - n]
        var = s2 / n - (s / n) ** 2
        out[i] = float(np.sqrt(max(var, 0.0)))
    return out


def _rsi(close: np.ndarray, n: int = 14) -> np.ndarray:
    out = np.full(len(close), np.nan)
    if len(close) < n + 1:
        return out
    delta = np.diff(close)
    gain = np.where(delta > 0, delta, 0.0)
    loss = np.where(delta < 0, -delta, 0.0)
    ag = _ema(gain, n)
    al = _ema(loss, n)
    rs = np.divide(ag, al, out=np.full_like(ag, np.nan), where=al > 0)
    out[1:] = 100.0 - 100.0 / (1.0 + rs)
    return out


def _atr(h: np.ndarray, l: np.ndarray, c: np.ndarray, n: int = 14) -> np.ndarray:
    if len(c) < 2:
        return np.full(len(c), np.nan)
    prev = c[:-1]
    tr = np.maximum.reduce([
        h[1:] - l[1:],
        np.abs(h[1:] - prev),
        np.abs(l[1:] - prev),
    ])
    out = np.full(len(c), np.nan)
    if len(tr) >= n:
        out[n] = np.mean(tr[:n])
        ema = out[n]
        for i in range(n + 1, len(c)):
            ema = (tr[i - 1] + (n - 1) * ema) / n
            out[i] = ema
    return out


def _pivots(high: np.ndarray, low: np.ndarray, left: int, right: int):
    highs = []
    lows = []
    n = len(high)
    for i in range(left, n - right):
        win_h = high[i - left:i + right + 1]
        win_l = low[i - left:i + right + 1]
        if high[i] >= win_h.max():
            highs.append(i)
        if low[i] <= win_l.min():
            lows.append(i)
    return highs, lows


def _fvg(high: np.ndarray, low: np.ndarray) -> List[tuple]:
    """Fair Value Gaps. A bullish FVG exists when low[i+1] > high[i-1] (price
    gapped up, leaving an unfilled zone [high[i-1], low[i+1]]). A bearish FVG
    when high[i+1] < low[i-1]. Returns (idx, top, bottom, direction). Used as a
    confluence filter (Unicorn model = OB + FVG) to raise SMC quality."""
    out = []
    n = len(high)
    for i in range(1, n - 1):
        if low[i + 1] > high[i - 1]:
            out.append((i, high[i - 1], low[i + 1], 1))
        if high[i + 1] < low[i - 1]:
            out.append((i, low[i - 1], high[i - 1], -1))
    return out


def _adx(h: np.ndarray, l: np.ndarray, c: np.ndarray, n: int = 14) -> float:
    if len(c) < n + 1:
        return np.nan
    prev = c[:-1]
    tr = np.maximum.reduce([h[1:] - l[1:], np.abs(h[1:] - prev), np.abs(l[1:] - prev)])
    up = h[1:] - h[:-1]
    dn = l[1:] - l[1:]
    plus_dm = np.where((up > dn) & (up > 0), up, 0.0)
    minus_dm = np.where((dn > up) & (dn > 0), dn, 0.0)
    atr_e = _ema(tr, n)
    pdi = 100 * _ema(plus_dm, n) / (atr_e + 1e-9)
    mdi = 100 * _ema(minus_dm, n) / (atr_e + 1e-9)
    dx = 100 * np.abs(pdi - mdi) / (pdi + mdi + 1e-9)
    return float(_ema(dx[1:], n)[-1])


def _session_utc() -> str:
    h = datetime.now(timezone.utc).hour
    if 7 <= h <= 10:
        return "london_open"
    if 12 <= h <= 16:
        return "london_ny_overlap"
    if 13 <= h <= 17:
        return "ny_open"
    if 0 <= h <= 5:
        return "asian"
    return "other"


def _spread_points(symbol: str) -> Optional[float]:
    if not _HAS_MT5:
        return None
    try:
        t = mt5.symbol_info_tick(symbol)
        info = mt5.symbol_info(symbol)
        if t is None or info is None:
            return None
        return (t.ask - t.bid) / info.point
    except Exception:
        return None


class ScalpingEngine:
    def __init__(self, cfg: Optional[dict] = None):
        self.cfg = cfg or {}
        self._per_symbol_day: Dict[str, Dict[str, int]] = {}
        self._minute_stamps: List[float] = []
        self.last_setup: Dict[str, Optional[dict]] = {}

    def _rate_ok(self) -> bool:
        now = time.time()
        self._minute_stamps = [s for s in self._minute_stamps if now - s < 60]
        if len(self._minute_stamps) >= int(self.cfg.get("max_per_minute", 6)):
            return False
        return True

    def _per_day_ok(self, symbol: str) -> bool:
        day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        bucket = self._per_symbol_day.get(symbol)
        if bucket is None or bucket.get("day") != day:
            self._per_symbol_day[symbol] = {"day": day, "count": 0}
            return True
        if bucket["count"] >= int(self.cfg.get("max_per_symbol_per_day", 8)):
            return False
        return True

    def _bump(self, symbol: str) -> None:
        now = time.time()
        self._minute_stamps.append(now)
        self._per_symbol_day.setdefault(symbol, {"day": datetime.now(timezone.utc).strftime("%Y-%m-%d"), "count": 0})
        self._per_symbol_day[symbol]["count"] += 1

    def _htf_bias(self, symbol: str) -> Tuple[int, float]:
        h1 = _rates(symbol, "H1", 60)
        if h1 is None:
            return 0, np.nan
        c = h1["close"]
        e20 = _ema(c, 20)
        e50 = _ema(c, 50)
        adx = _adx(h1["high"], h1["low"], c, 14)
        if np.isnan(e20[-1]) or np.isnan(e50[-1]):
            return 0, adx
        if e20[-1] > e50[-1]:
            return +1, adx
        if e20[-1] < e50[-1]:
            return -1, adx
        return 0, adx

    def _detect_smc(self, symbol: str, m5: dict, session: str) -> Optional[dict]:
        sc = self.cfg.get("smc", {})
        c = m5["close"]; h = m5["high"]; l = m5["low"]
        atr = _atr(h, l, c, 14)
        if np.isnan(atr[-1]) or atr[-1] <= float(self.cfg.get("min_atr", 0.0)):
            return None
        a = atr[-1]
        left = int(sc.get("pivot_left", 3)); right = int(sc.get("pivot_right", 3))
        ph, pl = _pivots(h, l, left, right)
        if len(ph) < 2 or len(pl) < 2:
            return None
        look = int(sc.get("swing_lookback", 60))
        last = len(c) - 1
        ph_r = [i for i in ph if i >= len(c) - look]
        pl_r = [i for i in pl if i >= len(c) - look]
        if not ph_r or not pl_r:
            return None
        # Liquidity pools are PRIOR swings, not the sweep bar itself. The sweep
        # bar makes a new extreme; the level it takes is the most recent swing
        # strictly before the last bar.
        pl_prev = [i for i in pl_r if i < last]
        ph_prev = [i for i in ph_r if i < last]
        if not pl_prev or not ph_prev:
            return None
        bias, adx = self._htf_bias(symbol)
        min_adx = float(sc.get("min_htf_adx", 18))
        if not np.isnan(adx) and adx < min_adx:
            return None
        last = len(c) - 1
        rev = sc.get("fib_low", 0.50); rf = sc.get("fib_high", 0.79)
        tp_ratio = float(sc.get("tp_sl_ratio", 1.8))
        sl_buf = float(sc.get("sl_buffer_atr", 0.3)) * a
        vol_z = float(sc.get("vol_z", 1.2))
        min_sweep_atr = float(sc.get("min_sweep_atr", 0.3))
        fvgs = _fvg(h, l)
        require_fvg = float(sc.get("require_fvg", 1.0))
        min_disp = float(sc.get("min_displacement_atr", 1.0))
        reasons: List[str] = ["smc"]

        ssl = max(pl_prev)
        if l[last] < l[ssl] and c[last] > l[ssl] and bias >= 0:
            # --- structural quality gates (opt-in via config; disabled when 0) ---
            vol = m5.get("tick_volume")
            weak = False
            if vol_z > 0 and vol is not None and last >= 20:
                vavg = float(np.mean(vol[last - 20:last]))
                if vavg > 0 and vol[last] < vol_z * vavg:
                    weak = True  # sweep without volume confirmation
            if (not weak) and (min_sweep_atr <= 0 or (l[ssl] - l[last]) >= min_sweep_atr * a):
                swing_low = l[ssl]
                choch = None
                for i in range(ssl + 1, last):
                    if l[i] > swing_low and c[i] > c[ssl]:
                        choch = i
                        break
                if choch is not None:
                    ob_end = choch
                    ob = None
                    for i in range(ob_end - 1, max(ob_end - int(sc.get("ob_lookback", 30)), 0), -1):
                        body = abs(c[i] - m5["open"][i])
                        if body > 0.4 * a and c[i] < m5["open"][i]:
                            ob = (m5["open"][i], c[i])
                            break
                    if ob is None:
                        ob = (m5["open"][ob_end], c[ob_end])
                    leg_hi = h[choch]
                    entry = swing_low + (leg_hi - swing_low) * (rev + (rf - rev) * 0.5)
                    # Must be a genuine discount: BUY LIMIT sits BELOW market.
                    # If price already traded through the zone, the dip is gone —
                    # skip rather than buy a breakout at a worse fill.
                    if entry >= c[last]:
                        return None
                    # --- confluence gates (Unicorn: OB + FVG + displacement) ---
                    ok = True
                    disp = abs(c[choch] - m5["open"][choch])
                    if min_disp > 0 and disp < min_disp * a:
                        ok = False  # CHoCH lacked real displacement
                    if require_fvg > 0 and ok:
                        has_fvg = any(fv[3] == 1 and ssl < fv[0] <= choch for fv in fvgs)
                        if not has_fvg:
                            ok = False
                    if ok:
                        sl = swing_low - sl_buf
                        tp = entry + tp_ratio * (entry - sl)
                        slm = (entry - sl) / (a + 1e-12)  # 1R partial target
                        conf = 0.60 + 0.05 * (2 + (1 if bias > 0 else 0) + (1 if not np.isnan(adx) else 0))
                        if require_fvg > 0:
                            conf += 0.05  # FVG confluence premium
                        if bias > 0:
                            reasons.append("htf_bias_up")
                        reasons += ["ssl_sweep", "choch", "ob"]
                        if require_fvg > 0:
                            reasons.append("fvg")
                        if min_disp > 0:
                            reasons.append("displacement")
                        return self._pack("BUY", conf, "LIMIT", entry, sl, tp, a, reasons, symbol,
                                          tp1_atr_mult=slm)

        bsl = max(ph_prev)
        if h[last] > h[bsl] and c[last] < h[bsl] and bias <= 0:
            vol = m5.get("tick_volume")
            weak = False
            if vol_z > 0 and vol is not None and last >= 20:
                vavg = float(np.mean(vol[last - 20:last]))
                if vavg > 0 and vol[last] < vol_z * vavg:
                    weak = True
            if (not weak) and (min_sweep_atr <= 0 or (h[last] - h[bsl]) >= min_sweep_atr * a):
                swing_high = h[bsl]
                choch = None
                for i in range(bsl + 1, last):
                    if h[i] < swing_high and c[i] < c[bsl]:
                        choch = i
                        break
                if choch is not None:
                    ob_end = choch
                    ob = None
                    for i in range(ob_end - 1, max(ob_end - int(sc.get("ob_lookback", 30)), 0), -1):
                        body = abs(c[i] - m5["open"][i])
                        if body > 0.4 * a and c[i] > m5["open"][i]:
                            ob = (m5["open"][i], c[i])
                            break
                    if ob is None:
                        ob = (m5["open"][ob_end], c[ob_end])
                    leg_lo = l[choch]
                    entry = swing_high - (swing_high - leg_lo) * (rev + (rf - rev) * 0.5)
                    # SELL LIMIT must sit ABOVE market (true premium) or skip.
                    if entry <= c[last]:
                        return None
                    ok = True
                    disp = abs(c[choch] - m5["open"][choch])
                    if min_disp > 0 and disp < min_disp * a:
                        ok = False
                    if require_fvg > 0 and ok:
                        has_fvg = any(fv[3] == -1 and bsl < fv[0] <= choch for fv in fvgs)
                        if not has_fvg:
                            ok = False
                    if ok:
                        sl = swing_high + sl_buf
                        tp = entry - tp_ratio * (sl - entry)
                        slm = (sl - entry) / (a + 1e-12)  # 1R partial target
                        conf = 0.60 + 0.05 * (2 + (1 if bias < 0 else 0) + (1 if not np.isnan(adx) else 0))
                        if require_fvg > 0:
                            conf += 0.05
                        if bias < 0:
                            reasons.append("htf_bias_down")
                        reasons += ["bsl_sweep", "choch", "ob"]
                        if require_fvg > 0:
                            reasons.append("fvg")
                        if min_disp > 0:
                            reasons.append("displacement")
                        return self._pack("SELL", conf, "LIMIT", entry, sl, tp, a, reasons, symbol,
                                          tp1_atr_mult=slm)
        return None

    def _detect_mean_reversion(self, symbol: str, m5: dict) -> Optional[dict]:
        mc = self.cfg.get("meanrev", {})
        c = m5["close"]; h = m5["high"]; l = m5["low"]
        atr = _atr(h, l, c, 14)
        if np.isnan(atr[-1]) or atr[-1] <= float(self.cfg.get("min_atr", 0.0)):
            return None
        a = atr[-1]
        bp = int(mc.get("boll_period", 20)); bs = float(mc.get("boll_std", 2.0))
        mid = _sma(c, bp)
        sd = _stdev(c, bp)
        upper = mid + bs * sd
        lower = mid - bs * sd
        zp = int(mc.get("zscore_period", 50))
        zmid = _sma(c, zp)
        zsd = _stdev(c, zp)
        z = (c - zmid) / (zsd + 1e-9)
        rsi = _rsi(c, int(mc.get("rsi_period", 14)))
        rsi_ext = float(mc.get("rsi_extreme", 28))
        _, adx = self._htf_bias(symbol)
        if not np.isnan(adx) and adx > float(mc.get("max_htf_adx", 24)):
            return None
        last = len(c) - 1
        zent = float(mc.get("zscore_entry", 2.0))
        slm = float(mc.get("sl_atr_mult", 1.0)); tpm = float(mc.get("tp_atr_mult", 1.4))
        reasons = ["meanrev"]
        if c[last] < lower[last] and z[last] < -zent and rsi[last] < rsi_ext:
            entry = lower[last]
            sl = entry - slm * a
            tp = mid[last]
            conf = 0.62 + 0.05 * (1 if not np.isnan(adx) else 0)
            reasons += ["lower_band", "zscore_extreme", "rsi_oversold"]
            return self._pack("BUY", conf, "LIMIT", entry, sl, tp, a, reasons, symbol)
        if c[last] > upper[last] and z[last] > zent and rsi[last] > (100 - rsi_ext):
            entry = upper[last]
            sl = entry + slm * a
            tp = mid[last]
            conf = 0.62 + 0.05 * (1 if not np.isnan(adx) else 0)
            reasons += ["upper_band", "zscore_extreme", "rsi_overbought"]
            return self._pack("SELL", conf, "LIMIT", entry, sl, tp, a, reasons, symbol)
        return None

    def _pack(self, direction, conf, order_kind, entry, sl, tp, atr, reasons, symbol,
              tp1_atr_mult=None) -> dict:
        sl_mult = abs(entry - sl) / (atr + 1e-12)
        tp_mult = abs(tp - entry) / (atr + 1e-12)
        if tp1_atr_mult is None:
            tp1_atr_mult = tp_mult  # default: full exit (no scale-out)
        return {
            "direction": direction,
            "confidence": round(min(0.95, conf), 4),
            "mode": reasons[0],
            "entry_price": round(float(entry), 6),
            "order_kind": order_kind,
            "sl_atr_mult": round(float(sl_mult), 3),
            "tp_atr_mult": round(float(tp_mult), 3),
            "tp1_atr_mult": round(float(tp1_atr_mult), 3),
            "symbol": symbol,
            "ts": int(time.time()),
            "brain": "ScalpEngine",
            "tv_strategy": "scalp",
            "reasons": reasons,
        }

    def evaluate(self, symbol: str) -> Optional[dict]:
        if not self._rate_ok() or not self._per_day_ok(symbol):
            return None
        session = _session_utc()
        allowed = self.cfg.get("sessions", {})
        if session != "other" and session not in allowed:
            return None
        sp = _spread_points(symbol)
        max_sp = int(self.cfg.get("max_spread_points_per_symbol", {}).get(symbol, self.cfg.get("max_spread_points", 35)))
        if sp is not None and sp > max_sp:
            return None
        m5 = _rates(symbol, "M5", 120)
        if m5 is None:
            return None
        mom_sessions = self.cfg.get("momentum_sessions", [])
        mr_sessions = self.cfg.get("meanrev_sessions", [])
        setup = None
        if session in mom_sessions:
            setup = self._detect_smc(symbol, m5, session)
        if setup is None and session in mr_sessions:
            setup = self._detect_mean_reversion(symbol, m5)
        if setup is None and session == "other":
            setup = self._detect_smc(symbol, m5, session) or self._detect_mean_reversion(symbol, m5)
        if setup is None:
            self.last_setup[symbol] = None
            return None
        if setup["confidence"] < float(self.cfg.get("min_confidence", 0.60)):
            return None
        self._bump(symbol)
        self.last_setup[symbol] = setup
        return setup

    def scan_all(self, symbols: List[str]) -> Dict[str, Optional[dict]]:
        out = {}
        for s in symbols:
            try:
                out[s] = self.evaluate(s)
            except Exception:
                out[s] = None
        return out
