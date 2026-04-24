"""
ADVANCED TRADING AGENTS — New Intelligence Layer
===================================================
4 New Agents to enhance trading decision quality:

1. CorrelationAgent     — Real-time cross-asset correlation tracking
2. OrderFlowAgent       — Tick volume analysis + buy/sell pressure
3. MarketRegimeAgent    — Detect trending/ranging/volatile regimes
4. DrawdownRecoveryAgent — Adaptive risk after losses (Kelly Criterion)

All agents post to AgentCommunicationBus for cross-system intelligence.
"""

import logging
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from collections import defaultdict

logger = logging.getLogger(__name__)

try:
    from institutional_agents import AgentCommunicationBus
except ImportError:
    try:
        from ai_trading_agents.institutional_agents import AgentCommunicationBus
    except ImportError:
        AgentCommunicationBus = None

MT5_AVAILABLE = False
mt5 = None
try:
    import MetaTrader5 as _mt5
    MT5_AVAILABLE = True
    mt5 = _mt5
except ImportError:
    pass


# ═════════════════════════════════════════════════════════════════════════
# AGENT 1: CORRELATION AGENT — Cross-Asset Correlation Tracking
# ═════════════════════════════════════════════════════════════════════════
class CorrelationAgent:
    """
    Tracks real-time correlations between trading pairs and related assets.

    Key Correlations:
    - XAUUSD vs DXY (inverse) — strong dollar = weak gold
    - XAUUSD vs US10Y (inverse) — rising yields = weak gold
    - GBPJPY vs Nikkei 225 (positive) — risk-on = both up
    - GBPJPY vs USDJPY (positive) — JPY weakness drives both
    - BTCUSD vs SPX (variable) — sometimes correlated, sometimes not

    SIGNAL LOGIC:
    - Normal correlation → confirm signal direction
    - Correlation breakdown → WARNING (potential regime change)
    - Divergence detected → BLOCK or fade signal
    """

    # Correlation matrix (expected relationships)
    EXPECTED_CORRELATIONS = {
        'XAUUSD': {
            'DXY': -0.80,       # Strong inverse with USD
            'US10Y': -0.60,     # Inverse with yields
            'XAGUSD': 0.90,     # Strong positive with silver
            'EURUSD': 0.60,     # Moderate positive (both anti-USD)
        },
        'GBPJPY': {
            'USDJPY': 0.85,     # Strong positive (JPY weakness)
            'GBPUSD': 0.50,     # Moderate positive (GBP strength)
            'EURJPY': 0.90,     # Strong positive (JPY cross)
        },
        'BTCUSD': {
            'ETHUSD': 0.95,     # Very strong positive
            'SPX': 0.40,        # Moderate (risk appetite)
        },
    }

    # Correlation pairs to fetch from MT5
    CORRELATION_SYMBOLS = {
        'XAUUSD': ['XAGUSD', 'EURUSD', 'USDJPY'],
        'GBPJPY': ['USDJPY', 'GBPUSD', 'EURJPY'],
        'BTCUSD': ['ETHUSD'],
    }

    _cache: Dict[str, Dict] = {}
    _cache_time: Dict[str, float] = {}
    CACHE_TTL = 300  # 5 minutes

    @classmethod
    def analyze(cls, symbol: str, df_h1: pd.DataFrame = None) -> Dict:
        """
        Analyze cross-asset correlations for a symbol.
        Returns correlation status, divergences, and trading bias.
        """
        import time
        cache_key = symbol
        now = time.time()
        if cache_key in cls._cache and (now - cls._cache_time.get(cache_key, 0)) < cls.CACHE_TTL:
            return cls._cache[cache_key]

        result = {
            "symbol": symbol,
            "correlations": {},
            "divergences": [],
            "bias": "NEUTRAL",
            "confidence_adjustment": 0,
            "reasons": [],
            "warning": False,
        }

        try:
            corr_symbols = cls.CORRELATION_SYMBOLS.get(symbol, [])
            if not corr_symbols or not MT5_AVAILABLE or df_h1 is None or df_h1.empty:
                result["reasons"].append("No correlation data available")
                return result

            close_main = df_h1['close'].values if len(df_h1) >= 50 else None
            if close_main is None:
                return result

            for corr_sym in corr_symbols:
                try:
                    # Fetch correlated symbol data from MT5
                    rates = mt5.copy_rates_from_pos(corr_sym, mt5.TIMEFRAME_H1, 0, 100)
                    if rates is None or len(rates) < 50:
                        continue

                    corr_df = pd.DataFrame(rates)
                    close_corr = corr_df['close'].values

                    # Align lengths
                    min_len = min(len(close_main), len(close_corr), 50)
                    main_returns = np.diff(close_main[-min_len:]) / close_main[-min_len:-1]
                    corr_returns = np.diff(close_corr[-min_len:]) / close_corr[-min_len:-1]

                    # Calculate rolling correlation (20-period)
                    if len(main_returns) >= 20:
                        correlation = np.corrcoef(main_returns[-20:], corr_returns[-20:])[0, 1]
                    else:
                        correlation = 0.0

                    expected = cls.EXPECTED_CORRELATIONS.get(symbol, {}).get(corr_sym, 0)

                    result["correlations"][corr_sym] = {
                        "current": round(correlation, 3),
                        "expected": expected,
                        "deviation": round(abs(correlation - expected), 3),
                    }

                    # Check for divergence (correlation breakdown)
                    deviation = abs(correlation - expected)
                    if deviation > 0.5:
                        result["divergences"].append({
                            "pair": corr_sym,
                            "expected": expected,
                            "actual": round(correlation, 3),
                            "severity": "HIGH" if deviation > 0.7 else "MEDIUM",
                        })
                        result["warning"] = True
                        result["confidence_adjustment"] -= 10
                        result["reasons"].append(
                            f"CORRELATION BREAKDOWN: {symbol} vs {corr_sym} "
                            f"(expected {expected:.2f}, actual {correlation:.2f})"
                        )
                    elif deviation > 0.3:
                        result["confidence_adjustment"] -= 5
                        result["reasons"].append(
                            f"Correlation drift: {symbol} vs {corr_sym} "
                            f"({correlation:.2f} vs expected {expected:.2f})"
                        )
                    else:
                        result["confidence_adjustment"] += 3
                        result["reasons"].append(
                            f"Correlation normal: {symbol} vs {corr_sym} = {correlation:.2f}"
                        )

                except Exception as e:
                    logger.debug(f"Correlation fetch error [{corr_sym}]: {e}")
                    continue

            # Post to communication bus
            if AgentCommunicationBus:
                msg_type = "WARNING" if result["warning"] else "INFO"
                AgentCommunicationBus.post(
                    agent="CorrelationAgent",
                    symbol=symbol,
                    msg_type=msg_type,
                    direction="NEUTRAL",
                    confidence=max(0, min(100, 50 + result["confidence_adjustment"])),
                    message=result["reasons"][0] if result["reasons"] else "Correlation check complete",
                    ttl_minutes=10,
                    data=result,
                )

        except Exception as e:
            logger.error(f"CorrelationAgent error [{symbol}]: {e}")
            result["reasons"].append(f"Error: {str(e)[:60]}")

        cls._cache[cache_key] = result
        cls._cache_time[cache_key] = now
        return result


# ═════════════════════════════════════════════════════════════════════════
# AGENT 2: ORDER FLOW AGENT — Tick Volume Analysis
# ═════════════════════════════════════════════════════════════════════════
class OrderFlowAgent:
    """
    Analyzes order flow using tick volume data from MT5.

    Metrics:
    1. Volume Delta — Estimated buy vs sell pressure
    2. Volume Climax — Extreme volume (potential exhaustion/reversal)
    3. Absorption — High volume but no price movement (accumulation)
    4. Block Trade Detection — Single candle with 5x+ average volume
    5. Volume Profile — Where volume concentrates (fair value)

    RULE: High buy volume + price at support = BUY confirmation
          High sell volume + price at resistance = SELL confirmation
          Volume climax at extreme = potential reversal (fade)
    """

    @classmethod
    def analyze(cls, symbol: str, df: pd.DataFrame) -> Dict:
        """Analyze order flow from tick volume data."""
        result = {
            "symbol": symbol,
            "volume_delta": "NEUTRAL",
            "delta_score": 0,
            "volume_climax": False,
            "absorption": False,
            "block_trade": False,
            "bias": "NEUTRAL",
            "confidence_adjustment": 0,
            "reasons": [],
        }

        if df is None or df.empty or len(df) < 20:
            result["reasons"].append("Insufficient data for order flow analysis")
            return result

        try:
            volume = df['tick_volume'].values if 'tick_volume' in df.columns else df['volume'].values
            close = df['close'].values
            open_p = df['open'].values
            high = df['high'].values
            low = df['low'].values

            # 1. VOLUME DELTA ESTIMATION
            # Approximate buy/sell volume using candle structure
            # Bullish candle: more buy volume; Bearish candle: more sell volume
            # Wick analysis refines the estimate
            body = np.abs(close - open_p)
            full_range = high - low
            full_range = np.where(full_range == 0, 1e-8, full_range)

            # Buying pressure = (close - low) / range * volume
            buy_pressure = ((close - low) / full_range) * volume
            sell_pressure = ((high - close) / full_range) * volume

            # Recent delta (last 10 candles)
            recent_buy = np.sum(buy_pressure[-10:])
            recent_sell = np.sum(sell_pressure[-10:])
            delta = recent_buy - recent_sell
            total = recent_buy + recent_sell

            if total > 0:
                delta_ratio = delta / total
                if delta_ratio > 0.15:
                    result["volume_delta"] = "BUYING"
                    result["delta_score"] = round(delta_ratio * 100, 1)
                    result["confidence_adjustment"] += 5
                    result["reasons"].append(
                        f"Buy pressure dominant ({delta_ratio:.1%} delta)"
                    )
                elif delta_ratio < -0.15:
                    result["volume_delta"] = "SELLING"
                    result["delta_score"] = round(delta_ratio * 100, 1)
                    result["confidence_adjustment"] -= 5
                    result["reasons"].append(
                        f"Sell pressure dominant ({delta_ratio:.1%} delta)"
                    )
                else:
                    result["reasons"].append(f"Volume balanced ({delta_ratio:.1%} delta)")

            # 2. VOLUME CLIMAX (extreme volume = potential exhaustion)
            vol_mean = np.mean(volume[-50:]) if len(volume) >= 50 else np.mean(volume)
            vol_std = np.std(volume[-50:]) if len(volume) >= 50 else np.std(volume)
            last_vol = volume[-1]

            if vol_mean > 0 and last_vol > vol_mean + 3 * vol_std:
                result["volume_climax"] = True
                result["reasons"].append(
                    f"VOLUME CLIMAX: {last_vol / vol_mean:.1f}x average (potential reversal)"
                )
                result["confidence_adjustment"] -= 5  # Caution on climax

            # 3. ABSORPTION (high volume, small body = institutions absorbing)
            last_body = body[-1]
            last_range = full_range[-1]
            body_ratio = last_body / last_range if last_range > 0 else 0
            vol_ratio = last_vol / vol_mean if vol_mean > 0 else 1

            if vol_ratio > 2.0 and body_ratio < 0.3:
                result["absorption"] = True
                result["reasons"].append(
                    f"ABSORPTION detected: {vol_ratio:.1f}x volume with {body_ratio:.1%} body "
                    f"(institutions accumulating)"
                )
                result["confidence_adjustment"] += 8

            # 4. BLOCK TRADE DETECTION
            if last_vol > vol_mean * 5:
                result["block_trade"] = True
                result["reasons"].append(
                    f"BLOCK TRADE: {last_vol / vol_mean:.1f}x average volume (institutional order)"
                )
                result["confidence_adjustment"] += 10

            # 5. Determine bias
            if result["volume_delta"] == "BUYING" and not result["volume_climax"]:
                result["bias"] = "BUY"
            elif result["volume_delta"] == "SELLING" and not result["volume_climax"]:
                result["bias"] = "SELL"

            # Post to bus
            if AgentCommunicationBus:
                AgentCommunicationBus.post(
                    agent="OrderFlowAgent",
                    symbol=symbol,
                    msg_type="SIGNAL" if result["bias"] != "NEUTRAL" else "INFO",
                    direction=result["bias"],
                    confidence=max(0, min(100, 50 + result["confidence_adjustment"])),
                    message=result["reasons"][0] if result["reasons"] else "Order flow neutral",
                    ttl_minutes=5,
                    data=result,
                )

        except Exception as e:
            logger.error(f"OrderFlowAgent error [{symbol}]: {e}")
            result["reasons"].append(f"Error: {str(e)[:60]}")

        return result


# ═════════════════════════════════════════════════════════════════════════
# AGENT 3: MARKET REGIME AGENT — Trending/Ranging/Volatile Detection
# ═════════════════════════════════════════════════════════════════════════
class MarketRegimeAgent:
    """
    Detects market regime to select appropriate strategy.

    Regimes:
    1. TRENDING     — ADX > 25, clear directional movement
    2. RANGING      — ADX < 20, price oscillating in channel
    3. VOLATILE     — High ATR percentile + rapid regime changes
    4. BREAKOUT     — Transitioning from ranging to trending (BB squeeze)
    5. EXHAUSTION   — ADX dropping from high levels, trend ending

    Strategy Mapping:
    - TRENDING   → Trade with trend (SMC, EMA entries)
    - RANGING    → Trade range extremes (BB bounces, support/resistance)
    - VOLATILE   → Reduce position size, wider stops
    - BREAKOUT   → Aggressive entry with tight trailing
    - EXHAUSTION → Avoid or prepare for reversal

    Uses: ADX, ATR percentile, BB width, Hurst exponent (simplified)
    """

    _regimes: Dict[str, Dict] = {}  # symbol -> regime data

    @classmethod
    def analyze(cls, symbol: str, df: pd.DataFrame) -> Dict:
        """Detect current market regime."""
        result = {
            "symbol": symbol,
            "regime": "UNKNOWN",
            "sub_regime": None,
            "confidence": 50,
            "trend_direction": "NEUTRAL",
            "volatility_state": "NORMAL",
            "strategy_recommendation": "DEFAULT",
            "position_size_mult": 1.0,
            "reasons": [],
        }

        if df is None or df.empty or len(df) < 50:
            result["reasons"].append("Insufficient data for regime detection")
            return result

        try:
            close = df['close'].values
            high = df['high'].values
            low = df['low'].values

            # Calculate indicators if not present
            adx = float(df['adx'].iloc[-1]) if 'adx' in df.columns else 20
            atr = float(df['atr'].iloc[-1]) if 'atr' in df.columns else 0
            bb_width = float(df['bb_width'].iloc[-1]) if 'bb_width' in df.columns else 0.02

            # ADX history for trend strength trajectory
            adx_series = df['adx'].values if 'adx' in df.columns else np.full(len(df), 20)
            adx_current = adx_series[-1] if len(adx_series) > 0 else 20
            adx_prev = adx_series[-5] if len(adx_series) >= 5 else adx_current
            adx_trend = adx_current - adx_prev  # Rising = strengthening

            # ATR percentile (volatility rank)
            if 'atr' in df.columns:
                atr_series = df['atr'].values
                atr_percentile = np.sum(atr_series <= atr) / len(atr_series) * 100
            else:
                atr_percentile = 50

            # BB squeeze detection
            if 'bb_width' in df.columns:
                bb_series = df['bb_width'].values
                bb_percentile = np.sum(bb_series <= bb_width) / len(bb_series) * 100
            else:
                bb_percentile = 50

            # Simplified Hurst exponent (trend persistence)
            hurst = cls._estimate_hurst(close[-50:])

            # ── REGIME CLASSIFICATION ──
            if adx_current > 30 and adx_trend > 0:
                result["regime"] = "TRENDING"
                result["sub_regime"] = "STRONG_TREND"
                result["confidence"] = 80
                result["strategy_recommendation"] = "TREND_FOLLOWING"
                result["position_size_mult"] = 1.2  # Slightly larger for strong trends
                result["reasons"].append(
                    f"Strong trend: ADX={adx_current:.0f} (rising +{adx_trend:.0f}), Hurst={hurst:.2f}"
                )
            elif adx_current > 25:
                result["regime"] = "TRENDING"
                result["sub_regime"] = "MODERATE_TREND"
                result["confidence"] = 70
                result["strategy_recommendation"] = "TREND_FOLLOWING"
                result["reasons"].append(
                    f"Moderate trend: ADX={adx_current:.0f}, Hurst={hurst:.2f}"
                )
            elif adx_current < 20 and bb_percentile < 25:
                result["regime"] = "BREAKOUT"
                result["sub_regime"] = "SQUEEZE"
                result["confidence"] = 65
                result["strategy_recommendation"] = "BREAKOUT_ENTRY"
                result["position_size_mult"] = 0.8  # Smaller until confirmed
                result["reasons"].append(
                    f"BB squeeze: width percentile={bb_percentile:.0f}%, ADX={adx_current:.0f}"
                )
            elif adx_current < 20:
                result["regime"] = "RANGING"
                result["confidence"] = 70
                result["strategy_recommendation"] = "RANGE_TRADING"
                result["position_size_mult"] = 0.7  # Smaller in range
                result["reasons"].append(
                    f"Ranging market: ADX={adx_current:.0f}, low directional movement"
                )
            elif adx_current > 25 and adx_trend < -5:
                result["regime"] = "EXHAUSTION"
                result["confidence"] = 60
                result["strategy_recommendation"] = "AVOID_OR_FADE"
                result["position_size_mult"] = 0.5
                result["reasons"].append(
                    f"Trend exhaustion: ADX dropping ({adx_trend:.0f}), potential reversal"
                )

            # Volatility state
            if atr_percentile > 85:
                result["volatility_state"] = "HIGH"
                result["position_size_mult"] *= 0.7  # Reduce in high vol
                result["reasons"].append(
                    f"High volatility: ATR percentile={atr_percentile:.0f}%"
                )
            elif atr_percentile < 15:
                result["volatility_state"] = "LOW"
                result["reasons"].append(
                    f"Low volatility: ATR percentile={atr_percentile:.0f}%"
                )

            # Trend direction
            if 'ema_fast' in df.columns and 'ema_slow' in df.columns:
                ema_f = float(df['ema_fast'].iloc[-1])
                ema_s = float(df['ema_slow'].iloc[-1])
                if ema_f > ema_s:
                    result["trend_direction"] = "BULLISH"
                elif ema_f < ema_s:
                    result["trend_direction"] = "BEARISH"

            # Store for history
            cls._regimes[symbol] = {
                "regime": result["regime"],
                "timestamp": datetime.utcnow(),
                "adx": adx_current,
                "hurst": hurst,
            }

            # Post to bus
            if AgentCommunicationBus:
                msg_type = "WARNING" if result["regime"] in ("EXHAUSTION", "RANGING") else "INFO"
                AgentCommunicationBus.post(
                    agent="MarketRegimeAgent",
                    symbol=symbol,
                    msg_type=msg_type,
                    direction=result["trend_direction"] if result["regime"] == "TRENDING" else "NEUTRAL",
                    confidence=result["confidence"],
                    message=f"Regime: {result['regime']} | {result['reasons'][0]}" if result["reasons"] else "Unknown",
                    ttl_minutes=15,
                    data=result,
                )

        except Exception as e:
            logger.error(f"MarketRegimeAgent error [{symbol}]: {e}")
            result["reasons"].append(f"Error: {str(e)[:60]}")

        return result

    @staticmethod
    def _estimate_hurst(prices: np.ndarray) -> float:
        """
        Simplified Hurst exponent estimation.
        H > 0.5 = trending (persistent)
        H = 0.5 = random walk
        H < 0.5 = mean-reverting (ranging)
        """
        if len(prices) < 20:
            return 0.5

        try:
            returns = np.diff(np.log(prices))
            n = len(returns)

            # R/S analysis (simplified)
            lags = [2, 4, 8, 16]
            rs_values = []
            for lag in lags:
                if lag > n:
                    continue
                # Split into windows
                n_windows = n // lag
                if n_windows < 1:
                    continue
                rs_sum = 0
                for w in range(n_windows):
                    window = returns[w * lag:(w + 1) * lag]
                    mean_r = np.mean(window)
                    cumdev = np.cumsum(window - mean_r)
                    r = np.max(cumdev) - np.min(cumdev)
                    s = np.std(window, ddof=1) if np.std(window, ddof=1) > 0 else 1e-8
                    rs_sum += r / s
                rs_values.append((np.log(lag), np.log(rs_sum / n_windows)))

            if len(rs_values) >= 2:
                x = np.array([v[0] for v in rs_values])
                y = np.array([v[1] for v in rs_values])
                # Linear regression: slope = Hurst exponent
                slope = np.polyfit(x, y, 1)[0]
                return max(0.0, min(1.0, slope))
        except Exception:
            pass

        return 0.5

    @classmethod
    def get_regime(cls, symbol: str) -> str:
        """Get last known regime for a symbol."""
        data = cls._regimes.get(symbol)
        if data:
            # Expire after 30 minutes
            age = (datetime.utcnow() - data["timestamp"]).total_seconds()
            if age < 1800:
                return data["regime"]
        return "UNKNOWN"


# ═════════════════════════════════════════════════════════════════════════
# AGENT 4: DRAWDOWN RECOVERY AGENT — Adaptive Risk After Losses
# ═════════════════════════════════════════════════════════════════════════
class DrawdownRecoveryAgent:
    """
    Dynamically adjusts risk based on recent trading performance.

    PHILOSOPHY:
    - After losses: REDUCE risk (smaller lots, stricter filters)
    - After wins: GRADUALLY increase risk (not immediately)
    - Never chase losses with bigger positions (anti-martingale)
    - Use Kelly Criterion for optimal sizing

    MODES:
    1. NORMAL       — Standard risk (1x lot)
    2. CONSERVATIVE — After 2 consecutive losses (0.5x lot, +2 confluence)
    3. RECOVERY     — After 3+ losses or >3% drawdown (0.25x lot, only A+ setups)
    4. AGGRESSIVE   — After 3+ consecutive wins (1.5x lot, standard filters)
    5. LOCKDOWN     — After 5%+ drawdown or 5 consecutive losses (NO TRADING)

    Kelly Criterion: f* = (bp - q) / b
    where b = avg_win/avg_loss, p = win_rate, q = 1-p
    """

    _state: Dict[str, Dict] = {}  # Per-symbol state
    _global_state = {
        "mode": "NORMAL",
        "consecutive_wins": 0,
        "consecutive_losses": 0,
        "daily_pnl": 0.0,
        "daily_trades": 0,
        "peak_equity": 0.0,
        "current_drawdown_pct": 0.0,
        "lot_multiplier": 1.0,
        "extra_confluence": 0,
        "last_reset": None,
    }

    @classmethod
    def update(cls, trade_result: Dict):
        """
        Update state after a trade closes.
        trade_result: {"symbol": str, "is_win": bool, "pnl": float, "equity": float}
        """
        is_win = trade_result.get("is_win", False)
        pnl = trade_result.get("pnl", 0)
        equity = trade_result.get("equity", 0)

        state = cls._global_state

        # Reset daily counters
        today = datetime.now().date()
        if state["last_reset"] != today:
            state["daily_pnl"] = 0.0
            state["daily_trades"] = 0
            state["last_reset"] = today

        state["daily_pnl"] += pnl
        state["daily_trades"] += 1

        if is_win:
            state["consecutive_wins"] += 1
            state["consecutive_losses"] = 0
        else:
            state["consecutive_losses"] += 1
            state["consecutive_wins"] = 0

        # Update peak equity and drawdown
        if equity > state["peak_equity"]:
            state["peak_equity"] = equity
        if state["peak_equity"] > 0:
            state["current_drawdown_pct"] = (
                (state["peak_equity"] - equity) / state["peak_equity"] * 100
            )

        # Determine mode
        cls._update_mode()

        logger.info(
            f"[DRAWDOWN] Trade closed: {'WIN' if is_win else 'LOSS'} ${pnl:.2f} | "
            f"Mode: {state['mode']} | Streak: {'W' if is_win else 'L'}"
            f"{state['consecutive_wins'] if is_win else state['consecutive_losses']} | "
            f"Daily: ${state['daily_pnl']:.2f} | DD: {state['current_drawdown_pct']:.1f}%"
        )

    @classmethod
    def _update_mode(cls):
        """Update trading mode based on current state."""
        state = cls._global_state

        # LOCKDOWN: 5%+ drawdown or 5 consecutive losses
        if state["current_drawdown_pct"] >= 5.0 or state["consecutive_losses"] >= 5:
            state["mode"] = "LOCKDOWN"
            state["lot_multiplier"] = 0.0
            state["extra_confluence"] = 99  # Effectively blocks all trades
            logger.warning(
                f"LOCKDOWN MODE: DD={state['current_drawdown_pct']:.1f}%, "
                f"Consecutive losses={state['consecutive_losses']}"
            )
            return

        # RECOVERY: 3+ losses or >3% drawdown
        if state["consecutive_losses"] >= 3 or state["current_drawdown_pct"] >= 3.0:
            state["mode"] = "RECOVERY"
            state["lot_multiplier"] = 0.25
            state["extra_confluence"] = 3  # Only A+ setups
            return

        # CONSERVATIVE: 2 consecutive losses
        if state["consecutive_losses"] >= 2:
            state["mode"] = "CONSERVATIVE"
            state["lot_multiplier"] = 0.5
            state["extra_confluence"] = 2
            return

        # AGGRESSIVE: 3+ consecutive wins (with protection)
        if state["consecutive_wins"] >= 3 and state["current_drawdown_pct"] < 1.0:
            state["mode"] = "AGGRESSIVE"
            state["lot_multiplier"] = 1.5
            state["extra_confluence"] = 0
            return

        # NORMAL
        state["mode"] = "NORMAL"
        state["lot_multiplier"] = 1.0
        state["extra_confluence"] = 0

    @classmethod
    def get_adjustments(cls) -> Dict:
        """
        Get current risk adjustments.
        Returns: lot_multiplier, extra_confluence_required, can_trade, mode
        """
        state = cls._global_state
        return {
            "mode": state["mode"],
            "lot_multiplier": state["lot_multiplier"],
            "extra_confluence": state["extra_confluence"],
            "can_trade": state["mode"] != "LOCKDOWN",
            "consecutive_wins": state["consecutive_wins"],
            "consecutive_losses": state["consecutive_losses"],
            "daily_pnl": state["daily_pnl"],
            "drawdown_pct": state["current_drawdown_pct"],
            "reason": cls._mode_reason(),
        }

    @classmethod
    def _mode_reason(cls) -> str:
        state = cls._global_state
        reasons = {
            "NORMAL": "Standard risk parameters",
            "CONSERVATIVE": f"2 consecutive losses — reduced lot (0.5x), +2 confluence required",
            "RECOVERY": f"Recovery mode — minimal lot (0.25x), only A+ setups",
            "AGGRESSIVE": f"3+ wins streak — increased lot (1.5x)",
            "LOCKDOWN": f"TRADING HALTED — DD={state['current_drawdown_pct']:.1f}%, "
                        f"losses={state['consecutive_losses']}",
        }
        return reasons.get(state["mode"], "Unknown mode")

    @classmethod
    def kelly_criterion(cls, win_rate: float, avg_win: float, avg_loss: float) -> float:
        """
        Calculate optimal position size using Kelly Criterion.
        Returns fraction of capital to risk (0.0 to max 0.05 = 5%).
        """
        if avg_loss == 0 or win_rate <= 0 or win_rate >= 1:
            return 0.01  # Default 1%

        b = avg_win / abs(avg_loss)  # Win/loss ratio
        p = win_rate
        q = 1 - p

        kelly = (b * p - q) / b

        # Half-Kelly for safety (less volatile)
        half_kelly = kelly / 2

        # Clamp between 0.5% and 5%
        return max(0.005, min(0.05, half_kelly))

    @classmethod
    def reset(cls):
        """Reset to normal mode (manual override)."""
        cls._global_state["mode"] = "NORMAL"
        cls._global_state["lot_multiplier"] = 1.0
        cls._global_state["extra_confluence"] = 0
        cls._global_state["consecutive_wins"] = 0
        cls._global_state["consecutive_losses"] = 0
        logger.info("[DRAWDOWN] Manual reset to NORMAL mode")

    @classmethod
    def status_report(cls) -> str:
        """Human-readable status report."""
        s = cls._global_state
        return (
            f"Mode: {s['mode']} | Lot: {s['lot_multiplier']:.2f}x | "
            f"Streak: W{s['consecutive_wins']}/L{s['consecutive_losses']} | "
            f"Daily P&L: ${s['daily_pnl']:.2f} | DD: {s['current_drawdown_pct']:.1f}% | "
            f"Extra confluence: +{s['extra_confluence']}"
        )
