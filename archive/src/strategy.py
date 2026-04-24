"""
MULTI-MARKET ROTATION Strategy Module
========================================
Trades 10+ pairs across METALS, FOREX, CRYPTO simultaneously.
Targets 20+ trades/day (max 3 per symbol, then rotate).
Uses fast EMAs + RSI + Volume + SMC for high-probability entries.
Each market trades only during its best session hours.
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple
from datetime import datetime
import logging
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import settings
from src.indicators import AMDAnalyzer, TechnicalIndicators
from src.risk_manager import RiskManager, TradeFilter
from src.utils import is_trading_session
from src.liquidity_engine import LiquidityEngine, liquidity_engine

logger = logging.getLogger(__name__)


class GoldScalpStrategy:
    """
    Gold Scalping Strategy - 85% Win Rate Target
    ================================================

    TWO ENTRY MODES:
    1. TREND SCALP: M15 trend + M5 pullback to EMA + RSI + Volume
    2. SPIKE CATCH: Detect sudden gold move, ride with tight trailing SL

    Entry Requirements (need 3+ confluences out of ~8):
    1. Fast EMA trend alignment (9 > 21 > 50 for bullish)
    2. Pullback to EMA 9/21 zone
    3. RSI(7) oversold/overbought
    4. Volume spike (institutional activity)
    5. Candlestick pattern (engulfing, pin bar, hammer)
    6. VWAP alignment
    7. BB squeeze breakout
    8. SMC confirmation (OB/FVG/BOS)

    Exit Logic:
    - SL: 1.0x ATR (tight for scalping)
    - TP: 1.5x SL distance OR trailing stop
    - Trailing: Activate at 15 pips, trail 10 pips behind
    - Spike: Trail 5 pips behind (aggressive)
    """

    def __init__(self, risk_manager: RiskManager = None):
        """Initialize Gold Scalp Strategy."""
        self.analyzer = AMDAnalyzer()
        self.risk_manager = risk_manager or RiskManager()
        # FIX 2026-04-14: min_confluences now 4 (set in settings.SCALP, fallback=4)
        # Was 6 — too strict, zero trades in months. 4 = quality without blocking everything.
        self.min_confluences = getattr(settings, 'SCALP', {}).get('min_confluences', 4)
        self.trades_today = 0
        self.max_trades_per_day = settings.RISK.get('max_trades_per_day', 8)
        self.last_trade_date = None
        self.active_setups: Dict[str, Dict] = {}
        self.pending_signals: List[Dict] = {}
        # Signal cooldown: track last signal bar per symbol
        # FIX 2026-04-20 (v14 TrendMaster): 3 → 7. Backtest showed ~60% of losing
        # trades were re-entries within 3-4 bars of a prior loss (whipsaw). A
        # 7-bar (35 min on M5) cooldown blocks those re-entries without missing
        # valid fresh setups that always take longer than that to build.
        self._last_signal_bar: Dict[str, int] = {}
        self._signal_cooldown_bars = 7  # v14: 7 bars (~35 min on M5)

    def _reset_daily_counter(self):
        """Reset trade counter at start of new day."""
        today = datetime.now().date()
        if self.last_trade_date != today:
            self.trades_today = 0
            self.last_trade_date = today

    def analyze_market(self, symbol: str, df: pd.DataFrame) -> Dict:
        """Analyze market for scalping signals."""
        if df.empty or len(df) < 60:
            return {'symbol': symbol, 'signal': None, 'reason': 'Insufficient data'}

        analyzed_df = self.analyzer.analyze(df)
        current_state = self.analyzer.get_current_phase(analyzed_df)
        signal = self._check_scalp_signal(symbol, analyzed_df, current_state)

        return {
            'symbol': symbol,
            'current_phase': current_state['phase'],
            'signal': signal,
            'atr': current_state.get('atr', 0),
            'adx': current_state.get('adx', 0),
            'timestamp': datetime.now(),
        }

    def _check_scalp_signal(self, symbol: str, df: pd.DataFrame,
                            current_state: Dict) -> Optional[Dict]:
        """
        Check for scalping signals (trend scalps + spike catches).
        RULE: Only scalp in H1 EMA trend direction (9 > 21 > 50 = BUY only, vice versa).
        H4 alignment is enforced in the AI agents layer above.
        """
        self._reset_daily_counter()
        if self.trades_today >= self.max_trades_per_day:
            logger.info(f"Max trades per day reached ({self.max_trades_per_day})")
            return None

        if df.empty or len(df) < 30:
            return None

        last = df.iloc[-1]
        prev = df.iloc[-2] if len(df) > 1 else last

        # ── DETERMINE H1 TREND DIRECTION ──────────────────────────────
        # Only allow scalps in the direction of H1 EMA stack
        ema_fast = last.get('ema_fast', 0) or last.get('ema9', 0)
        ema_slow = last.get('ema_slow', 0) or last.get('ema21', 0)
        ema_trend = last.get('ema_trend', 0) or last.get('ema50', 0)

        # Full EMA stack validation: EMA9 > EMA21 > EMA50 = strong uptrend
        # This ensures we ONLY scalp when ALL three EMAs align
        close_price = float(last.get('close', 0))
        h1_bullish = (ema_fast > ema_slow > 0
                       and (ema_trend <= 0 or close_price > ema_trend))  # Price above EMA50
        h1_bearish = (ema_fast < ema_slow and ema_slow > 0
                       and (ema_trend <= 0 or close_price < ema_trend))  # Price below EMA50

        # Check for SPIKE entry first (higher priority, but STILL must align with trend)
        spike_signal = self._check_spike_entry(symbol, df, last, prev)
        if spike_signal:
            # Verify spike direction matches H1 trend
            spike_dir = spike_signal.get('direction', spike_signal.get('type', ''))
            if spike_dir == 'BUY' and not h1_bullish:
                logger.info(f"[SPIKE] {symbol}: Bullish spike BLOCKED — H1 trend is not bullish")
                return None
            if spike_dir == 'SELL' and not h1_bearish:
                logger.info(f"[SPIKE] {symbol}: Bearish spike BLOCKED — H1 trend is not bearish")
                return None
            return spike_signal

        # ── TREND SCALP — Only check in H1 trend direction ───────────
        if h1_bullish:
            # H1 is bullish → only check BUY setups
            if self._check_bullish_scalp(symbol, df, last, prev):
                return self._generate_scalp_signal(symbol, 'BUY', df, last, is_spike=False)
        elif h1_bearish:
            # H1 is bearish → only check SELL setups
            if self._check_bearish_scalp(symbol, df, last, prev):
                return self._generate_scalp_signal(symbol, 'SELL', df, last, is_spike=False)
        else:
            # H1 sideways/no clear trend → NO SCALP
            logger.debug(f"[SCALP] {symbol}: No clear H1 trend direction — skipping")

        return None

    def _check_spike_entry(self, symbol: str, df: pd.DataFrame,
                           last: pd.Series, prev: pd.Series) -> Optional[Dict]:
        """
        SPIKE DETECTION: Enter on sudden gold moves.
        Gold often spikes 30-100 pips in seconds due to news/institutional orders.
        FIXED: Added much stricter validation to avoid false spike entries.
        """
        # Check for recent spike (not the candle that spiked, but 1-2 candles after)
        recent_spike_up = bool(last.get('recent_spike_up', False))
        recent_spike_down = bool(last.get('recent_spike_down', False))

        # FIXED: Check spike cooldown (prevent double entries)
        if bool(last.get('spike_cooldown', False)):
            return None

        # FIXED: Require volume confirmation for spikes
        has_volume = bool(last.get('volume_spike', False))
        if not has_volume:
            return None

        if recent_spike_up:
            # FIXED: Multiple confirmations needed
            above_ema = last.get('close', 0) > last.get('ema_fast', 0)
            above_ema_slow = last.get('close', 0) > last.get('ema_slow', 0)
            adx_ok = last.get('adx', 0) > 20  # Need trending market

            if above_ema and above_ema_slow and adx_ok:
                sig = self._generate_scalp_signal(symbol, 'BUY', df, last, is_spike=True)
                if sig:
                    sig['reason'] = f"SPIKE BUY - {last.get('spike_pips', 0):.0f} pips spike + volume + trend confirmed"
                    logger.info(f"[SPIKE] BULLISH spike entry for {symbol} (volume + ADX confirmed)")
                return sig

        if recent_spike_down:
            below_ema = last.get('close', 0) < last.get('ema_fast', 0)
            below_ema_slow = last.get('close', 0) < last.get('ema_slow', 0)
            adx_ok = last.get('adx', 0) > 20

            if below_ema and below_ema_slow and adx_ok:
                sig = self._generate_scalp_signal(symbol, 'SELL', df, last, is_spike=True)
                if sig:
                    sig['reason'] = f"SPIKE SELL - {last.get('spike_pips', 0):.0f} pips spike + volume + trend confirmed"
                    logger.info(f"[SPIKE] BEARISH spike entry for {symbol} (volume + ADX confirmed)")
                return sig

        return None

    # =========================================================================
    # v3.0 HELPER METHODS — Choppy Market, RSI Divergence, HTF 200 EMA
    # =========================================================================

    def _is_choppy_market(self, last: pd.Series) -> bool:
        """
        ADX < 15 AND BB squeeze = choppy market, suppress all signals.
        FIX 2026-04-14: ADX threshold lowered from 18 to 15.
        ADX 15-18 is NOT choppy — it's a developing trend. Only suppress truly flat markets.
        Both conditions (low ADX AND BB squeeze) must be true to suppress.
        """
        adx = float(last.get('adx', 25))
        bb_width = float(last.get('bb_width', 0.02))
        max_squeeze = getattr(settings, 'SMART_FILTERS', {}).get('max_bb_width_for_squeeze', 0.015)
        # FIXED: was adx < 18. Now 15 — only suppress truly dead/flat markets
        return adx < 15 and bb_width < max_squeeze

    def _check_rsi_divergence_bull(self, df: pd.DataFrame, last: pd.Series) -> bool:
        """Bullish RSI divergence: price lower low but RSI higher low."""
        if len(df) < 10:
            return False
        try:
            lookback = min(10, len(df))
            recent = df.iloc[-lookback:]
            price_now = float(last.get('close', 0))
            rsi_now = float(last.get('rsi_fast', 50))
            prev_low_idx = recent['close'].iloc[:-1].idxmin()
            prev_rsi = float(df.loc[prev_low_idx, 'rsi_fast']) if 'rsi_fast' in df.columns else 50.0
            prev_low_price = float(recent['close'].iloc[:-1].min())
            return price_now <= prev_low_price and rsi_now > prev_rsi and rsi_now < 45
        except Exception:
            return False

    def _check_rsi_divergence_bear(self, df: pd.DataFrame, last: pd.Series) -> bool:
        """Bearish RSI divergence: price higher high but RSI lower high."""
        if len(df) < 10:
            return False
        try:
            lookback = min(10, len(df))
            recent = df.iloc[-lookback:]
            price_now = float(last.get('close', 0))
            rsi_now = float(last.get('rsi_fast', 50))
            prev_high_idx = recent['close'].iloc[:-1].idxmax()
            prev_rsi = float(df.loc[prev_high_idx, 'rsi_fast']) if 'rsi_fast' in df.columns else 50.0
            prev_high_price = float(recent['close'].iloc[:-1].max())
            return price_now >= prev_high_price and rsi_now < prev_rsi and rsi_now > 55
        except Exception:
            return False

    def _check_htf_200ema(self, last: pd.Series, direction: str) -> bool:
        """HTF 200 EMA alignment: price above = bullish, below = bearish."""
        close = float(last.get('close', 0))
        ema200 = float(last.get('ema200', 0) or last.get('ema_200', 0))
        if ema200 <= 0:
            return False
        return (close > ema200) if direction == 'BUY' else (close < ema200)

    # =========================================================================
    # v14 TrendMaster HELPERS (2026-04-20)
    # =========================================================================

    def _check_m15_alignment(self, df_m15: Optional[pd.DataFrame],
                             direction: str) -> bool:
        """
        v14: Require M15 EMA stack to agree with M5 entry direction.
        If no M15 data is passed (caller didn't provide it), we default to True
        so existing call-sites don't break — but the orchestrator SHOULD pass it.
        """
        if df_m15 is None or df_m15.empty or len(df_m15) < 50:
            return True  # no data → pass (don't block)
        try:
            last = df_m15.iloc[-1]
            ema_fast  = float(last.get('ema_fast', 0) or last.get('ema9', 0))
            ema_slow  = float(last.get('ema_slow', 0) or last.get('ema21', 0))
            ema_trend = float(last.get('ema_trend', 0) or last.get('ema50', 0))
            close     = float(last.get('close', 0))
            if direction == 'BUY':
                return ema_fast > ema_slow and (ema_trend <= 0 or close > ema_trend)
            else:
                return ema_fast < ema_slow and (ema_trend <= 0 or close < ema_trend)
        except Exception:
            return True  # on error don't block — fail-open

    def _adx_reversing_against(self, df: pd.DataFrame, direction: str,
                               lookback: int = 3) -> bool:
        """
        v14: Returns True if ADX has been dropping for `lookback` bars AND
        the trend is losing strength (ADX<20 now, was >25 recently).
        Used by position manager to close early instead of waiting for SL.
        """
        if df is None or df.empty or len(df) < lookback + 1:
            return False
        try:
            adx_col = 'adx' if 'adx' in df.columns else 'ADX'
            if adx_col not in df.columns:
                return False
            recent = df[adx_col].iloc[-(lookback + 1):]
            if float(recent.iloc[-1]) < 20 and float(recent.max()) > 25:
                # has the trend strength deteriorated?
                deltas = recent.diff().dropna()
                return (deltas < 0).sum() >= lookback - 1
            return False
        except Exception:
            return False

    def should_close_early(self, position: Dict, df: pd.DataFrame) -> Tuple[bool, str]:
        """
        v14 trend-reversal early exit hook.
        Call from the position manager on each bar close.
        Returns (close?, reason).
        """
        direction = position.get('direction', position.get('type', ''))
        if direction not in ('BUY', 'SELL'):
            return False, ''
        if self._adx_reversing_against(df, direction):
            return True, 'ADX_REVERSING'
        # Trend-line break: price crossed EMA50 against us for 2 closes
        try:
            ema50 = df['ema_trend'].iloc[-2:] if 'ema_trend' in df.columns else None
            closes = df['close'].iloc[-2:]
            if ema50 is not None:
                if direction == 'BUY' and all(closes.values < ema50.values):
                    return True, 'EMA50_BROKEN'
                if direction == 'SELL' and all(closes.values > ema50.values):
                    return True, 'EMA50_BROKEN'
        except Exception:
            pass
        return False, ''

    # =========================================================================

    def _check_bullish_scalp(self, symbol: str, df: pd.DataFrame,
                             last: pd.Series, prev: pd.Series) -> bool:
        """
        BULLISH SCALP ENTRY — v3.0 10-CONFLUENCE SYSTEM (min 6/10)
        ============================================================
        1. EMA Stack (+2 full, +1 partial)    6. BB lower band position
        2. Pullback to EMA zone               7. SMC (FVG/OB/BOS)
        3. RSI extreme oversold (<28, +1 if <20) 8. Candle pattern
        4. ADX > 25 trend strength            9. RSI Bullish Divergence
        5. Volume surge > 1.5x               10. HTF 200 EMA alignment
        Choppy market (ADX<18 + BB squeeze) → suppressed completely.
        """
        # ── CHOPPY MARKET SUPPRESSION (v3.0) ─────────────────────────
        if self._is_choppy_market(last):
            logger.debug(f"[v3] {symbol}: CHOPPY — signals suppressed")
            return False

        # ── ADX FILTER ────────────────────────────────────────────────
        # FIX 2026-04-14: ADX threshold lowered from 22 to 18
        # Markets spend most time between ADX 15-22. 22 was blocking >70% of valid setups.
        adx = float(last.get('adx', 25))
        if adx < 18:
            return False

        # Session check — each pair has its own best hours
        try:
            hour_utc = df.index[-1].hour
        except Exception:
            hour_utc = datetime.utcnow().hour

        best_hours = settings.PAIR_SESSION_FILTERS.get(symbol, {}).get('best_hours')
        if best_hours and hour_utc not in best_hours:
            return False

        # ── SIGNAL COOLDOWN ───────────────────────────────────────────
        bar_idx = len(df)
        if bar_idx - self._last_signal_bar.get(f"{symbol}_bull", 0) < self._signal_cooldown_bars:
            return False

        score = 0
        hits = []

        # 1. EMA Stack (MANDATORY — must have at least partial alignment)
        ema_full = bool(last.get('scalp_trend_bull', False))
        ema_partial = (float(last.get('ema_fast', 0)) > float(last.get('ema_slow', 0)))
        if ema_full:
            score += 2; hits.append('EMA_Full')
        elif ema_partial:
            score += 1; hits.append('EMA_Partial')

        # 2. Pullback to EMA
        if bool(last.get('pullback_to_ema_bull', False)):
            score += 1; hits.append('Pullback')

        # 3. RSI extreme oversold
        rsi_val = float(last.get('rsi_fast', 50))
        if rsi_val < 28:
            score += 1; hits.append('RSI_OS')
        if rsi_val < 20:
            score += 1; hits.append('RSI_Extreme')

        # 4. ADX trend strength
        if adx > 25:
            score += 1; hits.append('ADX_Strong')

        # 5. Volume surge
        vol_ratio = float(last.get('volume_ratio', 1.0))
        if vol_ratio > 1.5 or bool(last.get('volume_spike', False)):
            score += 1; hits.append('Volume')

        # 6. BB position — price near/below lower band
        close_p = float(last.get('close', 0))
        bb_lower = float(last.get('bb_lower', 0))
        if bb_lower > 0 and close_p <= bb_lower * 1.001:
            score += 1; hits.append('BB_Lower')
        elif bool(last.get('bb_bounce_up', False)) or bool(last.get('bb_breakout_up', False)):
            score += 1; hits.append('BB_Bounce')

        # 7. SMC (FVG / Order Block / BOS)
        lookback = min(10, len(df))
        recent = df.iloc[-lookback:]
        has_ob = bool('bullish_ob' in recent.columns and recent['bullish_ob'].iloc[-10:].any())
        has_fvg = bool('bullish_fvg' in recent.columns and recent['bullish_fvg'].iloc[-10:].any())
        has_bos = bool(last.get('bullish_bos', False) or last.get('bullish_choch', False))
        if has_ob or has_fvg or has_bos:
            score += 1; hits.append('SMC')

        # 8. Candle pattern
        has_pattern = bool(
            last.get('pin_bar_bullish', False) or last.get('engulfing_bullish', False) or
            last.get('hammer', False) or last.get('morning_star', False)
        )
        if has_pattern:
            score += 1; hits.append('Pattern')

        # 9. RSI Bullish Divergence (v3.0 new)
        if self._check_rsi_divergence_bull(df, last):
            score += 1; hits.append('RSI_Div')

        # 10. HTF 200 EMA (v3.0 new)
        if self._check_htf_200ema(last, 'BUY'):
            score += 1; hits.append('HTF_200EMA')

        # VWAP support bonus
        if bool(last.get('above_vwap', False)):
            score += 1; hits.append('VWAP')

        # Strict mode penalty: full EMA stack required
        smart = getattr(settings, 'SMART_FILTERS', {})
        if smart.get('require_trend_alignment', True) and not ema_full:
            score = max(0, score - 2)

        # Must have at least partial EMA alignment
        if not ema_partial:
            return False

        # Peak hour: threshold - 1
        peak_hours = settings.PAIR_SESSION_FILTERS.get(symbol, {}).get('peak_hours', [])
        is_peak = hour_utc in peak_hours
        threshold = self.min_confluences - (1 if is_peak else 0)

        if score >= threshold:
            logger.info(f"[SCALP v3] BULL {symbol}: score={score}/{threshold} hits={hits}" + (" [PEAK]" if is_peak else ""))
            self._last_signal_bar[f"{symbol}_bull"] = bar_idx
            return True

        logger.debug(f"[SCALP v3] {symbol}: BULL score={score}/{threshold} hits={hits}")
        return False

    def _check_bearish_scalp(self, symbol: str, df: pd.DataFrame,
                             last: pd.Series, prev: pd.Series) -> bool:
        """
        BEARISH SCALP ENTRY — v3.0 10-CONFLUENCE SYSTEM (min 6/10, mirror of bullish).
        """
        # ── CHOPPY MARKET SUPPRESSION ─────────────────────────────────
        if self._is_choppy_market(last):
            return False

        # ── ADX FILTER ────────────────────────────────────────────────
        # FIX 2026-04-14: ADX threshold lowered from 22 to 18 (mirror of bullish fix)
        adx = float(last.get('adx', 25))
        if adx < 18:
            return False

        try:
            hour_utc = df.index[-1].hour
        except Exception:
            hour_utc = datetime.utcnow().hour

        best_hours = settings.PAIR_SESSION_FILTERS.get(symbol, {}).get('best_hours')
        if best_hours and hour_utc not in best_hours:
            return False

        # ── SIGNAL COOLDOWN ───────────────────────────────────────────
        bar_idx = len(df)
        if bar_idx - self._last_signal_bar.get(f"{symbol}_bear", 0) < self._signal_cooldown_bars:
            return False

        score = 0
        hits = []

        # 1. EMA Stack
        ema_full = bool(last.get('scalp_trend_bear', False))
        ema_partial = (float(last.get('ema_fast', 0)) < float(last.get('ema_slow', 1)))
        if ema_full:
            score += 2; hits.append('EMA_Full')
        elif ema_partial:
            score += 1; hits.append('EMA_Partial')

        # 2. Pullback to EMA
        if bool(last.get('pullback_to_ema_bear', False)):
            score += 1; hits.append('Pullback')

        # 3. RSI extreme overbought
        rsi_val = float(last.get('rsi_fast', 50))
        if rsi_val > 72:
            score += 1; hits.append('RSI_OB')
        if rsi_val > 80:
            score += 1; hits.append('RSI_Extreme')

        # 4. ADX trend strength
        if adx > 25:
            score += 1; hits.append('ADX_Strong')

        # 5. Volume surge
        vol_ratio = float(last.get('volume_ratio', 1.0))
        if vol_ratio > 1.5 or bool(last.get('volume_spike', False)):
            score += 1; hits.append('Volume')

        # 6. BB position — price near/above upper band
        close_p = float(last.get('close', 0))
        bb_upper = float(last.get('bb_upper', 0))
        if bb_upper > 0 and close_p >= bb_upper * 0.999:
            score += 1; hits.append('BB_Upper')
        elif bool(last.get('bb_bounce_down', False)) or bool(last.get('bb_breakout_down', False)):
            score += 1; hits.append('BB_Bounce')

        # 7. SMC
        lookback = min(10, len(df))
        recent = df.iloc[-lookback:]
        has_ob = bool('bearish_ob' in recent.columns and recent['bearish_ob'].iloc[-10:].any())
        has_fvg = bool('bearish_fvg' in recent.columns and recent['bearish_fvg'].iloc[-10:].any())
        has_bos = bool(last.get('bearish_bos', False) or last.get('bearish_choch', False))
        if has_ob or has_fvg or has_bos:
            score += 1; hits.append('SMC')

        # 8. Candle pattern
        has_pattern = bool(
            last.get('pin_bar_bearish', False) or last.get('engulfing_bearish', False) or
            last.get('shooting_star', False) or last.get('evening_star', False)
        )
        if has_pattern:
            score += 1; hits.append('Pattern')

        # 9. RSI Bearish Divergence (v3.0 new)
        if self._check_rsi_divergence_bear(df, last):
            score += 1; hits.append('RSI_Div')

        # 10. HTF 200 EMA (v3.0 new)
        if self._check_htf_200ema(last, 'SELL'):
            score += 1; hits.append('HTF_200EMA')

        # VWAP resistance bonus
        if bool(last.get('below_vwap', False)):
            score += 1; hits.append('VWAP')

        # Strict mode penalty
        smart = getattr(settings, 'SMART_FILTERS', {})
        if smart.get('require_trend_alignment', True) and not ema_full:
            score = max(0, score - 2)

        if not ema_partial:
            return False

        peak_hours = settings.PAIR_SESSION_FILTERS.get(symbol, {}).get('peak_hours', [])
        is_peak = hour_utc in peak_hours
        threshold = self.min_confluences - (1 if is_peak else 0)

        if score >= threshold:
            logger.info(f"[SCALP v3] BEAR {symbol}: score={score}/{threshold} hits={hits}" + (" [PEAK]" if is_peak else ""))
            self._last_signal_bar[f"{symbol}_bear"] = bar_idx
            return True

        logger.debug(f"[SCALP v3] {symbol}: BEAR score={score}/{threshold} hits={hits}")
        return False

    def _generate_scalp_signal(self, symbol: str, direction: str,
                               df: pd.DataFrame, last: pd.Series,
                               is_spike: bool = False) -> Dict:
        """Generate a scalp trade signal with WIDER SL/TP to survive gold volatility."""
        atr = float(last.get('atr', 2.0))  # Gold ATR on M5 ~ $2-5
        entry_price = float(last['close'])

        # FIXED: SL based on ATR (2.5x ATR for normal, 1.5x for spike — was 1.5/1.0)
        sl_mult = settings.RISK['default_sl_atr_multiple']  # Now 2.5
        rr = settings.RISK['min_risk_reward']

        if direction == 'BUY':
            # FIXED: Spike SL is 1.5x ATR (was 1.0 — too tight)
            if is_spike:
                stop_loss = entry_price - (atr * 1.5)
            else:
                stop_loss = entry_price - (atr * sl_mult)
        else:
            if is_spike:
                stop_loss = entry_price + (atr * 1.5)
            else:
                stop_loss = entry_price + (atr * sl_mult)

        # TP = 2x SL distance (FIXED 1:2 RR - never lower)
        risk_distance = abs(entry_price - stop_loss)
        if direction == 'BUY':
            take_profit = entry_price + (risk_distance * rr)
        else:
            take_profit = entry_price - (risk_distance * rr)

        risk_reward = rr

        signal = {
            'symbol': symbol,
            'direction': direction,
            'entry_price': round(entry_price, 2),
            'stop_loss': round(stop_loss, 2),
            'take_profit': round(take_profit, 2),
            'atr': atr,
            'adx': float(last.get('adx', 25)),
            'risk_reward': round(risk_reward, 2),
            'is_spike': is_spike,
            'timestamp': datetime.now(),
            'reason': f"{'SPIKE' if is_spike else 'SCALP'} {direction} - RR: {risk_reward:.1f}",
        }

        self.trades_today += 1

        logger.info(
            f"{'SPIKE' if is_spike else 'SCALP'} Signal: {direction} {symbol} @ {entry_price:.2f} "
            f"SL: {stop_loss:.2f} TP: {take_profit:.2f} RR: {risk_reward:.1f}"
        )

        return signal

    def validate_signal(self, signal: Dict, symbol_info: Dict,
                        open_positions: List[Dict]) -> Dict:
        """Validate a signal against risk rules + 55/45 liquidity rule."""
        if signal is None:
            return {'valid': False, 'reason': 'No signal'}

        if not TradeFilter.check_spread(symbol_info):
            return {'valid': False, 'reason': 'Spread too high'}

        atr_val = signal.get('atr', 0)
        if atr_val <= 0:
            return {'valid': False, 'reason': 'Invalid ATR'}

        # Check max trades per day
        self._reset_daily_counter()
        if self.trades_today > self.max_trades_per_day:
            return {'valid': False, 'reason': 'Max daily trades reached'}

        # Check max open trades
        if len(open_positions) >= settings.RISK['max_open_trades']:
            return {'valid': False, 'reason': 'Max open trades reached'}

        can_trade = self.risk_manager.can_trade()
        if not can_trade['allowed']:
            return {'valid': False, 'reason': can_trade['reason']}

        # ── 55/45 LIQUIDITY RULE CHECK ──────────────────────────────
        # If liquidity analysis is attached, enforce the 55% rule
        liq_data = signal.get('liquidity_analysis')
        if liq_data:
            if liq_data.get('fake_signal_blocked'):
                return {'valid': False,
                        'reason': f"FAKE SIGNAL BLOCKED by Liquidity Engine: "
                                  f"{liq_data.get('reasons', ['unknown'])[0]}"}
            if liq_data.get('entry_valid') and not liq_data.get('sweep_55_rule_passed'):
                return {'valid': False,
                        'reason': f"55% Rule NOT met — liquidity sweep insufficient"}

        # ── CONFLUENCE-BASED TRADE MULTIPLIER ──────────────────────────
        # 2 indicators agree → 1 trade (normal)
        # 3+ indicators agree → 2 trades (double position)
        bull_pts = signal.get('bull_score', signal.get('confluence_score', 0))
        bear_pts = signal.get('bear_score', 0)
        direction = signal.get('direction', '')
        conf_score = bull_pts if direction == 'BUY' else bear_pts
        if conf_score >= 3:
            signal['trade_count'] = 2      # 3+ confluences = 2 trades
            signal['trade_label'] = f"STRONG {direction} [{conf_score}/6] >>> 2 TRADES"
        else:
            signal['trade_count'] = 1      # 2 confluences = 1 trade
            signal['trade_label'] = f"{direction} [{conf_score}/6] >>> 1 TRADE"

        return {'valid': True, 'signal': signal}

    def enhance_signal_with_liquidity(self, signal: Dict, liq_analysis: Dict) -> Dict:
        """
        Enhance a trade signal with liquidity data from LiquidityEngine.
        Applies the 55/45 rule: adjusts TP based on remaining 45% of zone.
        """
        if not signal or not liq_analysis:
            return signal

        signal['liquidity_analysis'] = liq_analysis

        # If liquidity engine found a valid entry → boost confidence and adjust TP
        if liq_analysis.get('entry_valid') and liq_analysis.get('sweep_55_rule_passed'):
            liq_dir = liq_analysis.get('liquidity_signal', 'NEUTRAL')
            sig_dir = signal.get('direction', '')

            if liq_dir == sig_dir:
                # Liquidity CONFIRMS signal → big boost
                signal['liquidity_confirmed'] = True
                # Override TP with liquidity-based 45% target
                if liq_analysis.get('profit_target', 0) > 0:
                    signal['take_profit_liq'] = liq_analysis['profit_target']
                if liq_analysis.get('stop_loss_suggestion', 0) > 0:
                    signal['stop_loss_liq'] = liq_analysis['stop_loss_suggestion']
                signal['reason'] = (
                    f"{signal.get('reason', '')} | "
                    f"✅ LIQUIDITY 55/45: {liq_analysis.get('reasons', [''])[0]}"
                )
                logger.info(
                    f"[LIQUIDITY] {signal['symbol']} {sig_dir} CONFIRMED by 55/45 rule — "
                    f"TP: {liq_analysis.get('profit_target', 0):.5f}"
                )
            elif liq_dir != 'NEUTRAL' and liq_dir != sig_dir:
                # Liquidity CONFLICTS with signal → block
                signal['liquidity_confirmed'] = False
                signal['liquidity_conflict'] = True
                logger.warning(
                    f"[LIQUIDITY] {signal['symbol']}: Signal={sig_dir} but "
                    f"Liquidity={liq_dir} — CONFLICT"
                )
        elif liq_analysis.get('fake_signal_blocked'):
            signal['liquidity_confirmed'] = False
            signal['fake_signal_blocked'] = True

        return signal

    def calculate_position_size(self, signal: Dict, symbol_info: Dict) -> float:
        """Calculate position size for scalp trade."""
        sl_distance = abs(signal['entry_price'] - signal['stop_loss'])
        sym = signal.get('symbol', symbol_info.get('symbol', ''))
        # Determine correct pip size per asset class
        if 'XAU' in sym or 'GOLD' in sym:
            pip_size = 0.10   # Gold: 1 pip = $0.10
        elif 'XAG' in sym or 'SILVER' in sym:
            pip_size = 0.01   # Silver: 1 pip = $0.01
        elif 'JPY' in sym:
            pip_size = 0.01   # JPY pairs: 1 pip = 0.01
        elif 'BTC' in sym:
            pip_size = 1.0    # BTCUSD: 1 pip = $1
        elif 'ETH' in sym:
            pip_size = 0.10   # ETHUSD: 1 pip = $0.10
        else:
            pip_size = 0.0001 # Standard forex: 1 pip = 0.0001
        sl_pips = sl_distance / pip_size
        # Pass symbol and raw prices to risk_manager for minimum SL enforcement
        return self.risk_manager.calculate_position_size(
            symbol_info, stop_loss_pips=sl_pips,
            entry_price=signal['entry_price'],
            stop_loss=signal['stop_loss'],
            symbol=sym
        )


class GoldSwingStrategy:
    """
    Gold SWING Trading Strategy (H4/Daily) - Replaces scalping for XAUUSD.
    ========================================================================

    WHY SWING INSTEAD OF SCALP FOR GOLD:
    - Gold has extremely high volatility (40+ pip spikes in seconds)
    - OctaFX spreads are 40+ pips during news (kills scalp entries)
    - Gold is fundamentally driven (wars, inflation, central banks)
    - H4/Daily gives cleaner structure and wider R:R

    ENTRY REQUIREMENTS (4+ out of 8 confluences):
    1. Daily trend alignment (EMA 21/50/200 stack)
    2. H4 structure (BOS/MSS at key level)
    3. Key level confluence (prev day H/L, weekly H/L, Fib levels)
    4. News catalyst within 4 hours (NFP, CPI, FOMC, etc.)
    5. Geopolitical bias alignment (wars, sanctions)
    6. RSI(14) oversold/overbought with divergence
    7. Volume confirmation (institutional activity)
    8. SMC (Order Block/FVG at entry zone)

    EXIT: SL = 5x ATR, TP1 = 2R (close 30%), TP2 = 3R (close 30%), TP3 = 5R runner (40%)
    MAX: 1 trade/day, 3 trades/week
    """

    def __init__(self, risk_manager: RiskManager = None):
        self.risk_manager = risk_manager or RiskManager()
        self.analyzer = AMDAnalyzer()
        self.swing_cfg = getattr(settings, 'GOLD_SWING', {})
        self.trades_this_week = 0
        self.trades_today = 0
        self.last_trade_date = None
        self.last_trade_time = None
        self._week_start = None

    def _reset_counters(self):
        """Reset daily/weekly trade counters."""
        now = datetime.now()
        today = now.date()
        if self.last_trade_date != today:
            self.trades_today = 0
            self.last_trade_date = today
        # Reset weekly counter on Monday
        if self._week_start is None or (now.weekday() == 0 and self._week_start != today):
            self.trades_this_week = 0
            self._week_start = today

    def analyze_market(self, symbol: str, df_h4: pd.DataFrame,
                       df_daily: pd.DataFrame = None,
                       news_events: list = None,
                       geopolitical_bias: str = "NEUTRAL") -> Dict:
        """
        Analyze gold for swing trade opportunities on H4/Daily.
        """
        if df_h4.empty or len(df_h4) < 50:
            return {'symbol': symbol, 'signal': None, 'reason': 'Insufficient H4 data'}

        self._reset_counters()

        # Check trade limits
        max_per_day = self.swing_cfg.get('max_trades_per_day', 1)
        max_per_week = self.swing_cfg.get('max_trades_per_week', 3)
        if self.trades_today >= max_per_day:
            return {'symbol': symbol, 'signal': None, 'reason': f'Max daily trades ({max_per_day}) reached'}
        if self.trades_this_week >= max_per_week:
            return {'symbol': symbol, 'signal': None, 'reason': f'Max weekly trades ({max_per_week}) reached'}

        # Check cooldown
        cooldown_hours = self.swing_cfg.get('trade_cooldown_hours', 8)
        if self.last_trade_time:
            hours_since = (datetime.now() - self.last_trade_time).total_seconds() / 3600
            if hours_since < cooldown_hours:
                return {'symbol': symbol, 'signal': None,
                        'reason': f'Cooldown: {cooldown_hours - hours_since:.1f}h remaining'}

        # Add indicators to H4 data
        analyzed = self._add_swing_indicators(df_h4)
        last = analyzed.iloc[-1]

        # Determine daily trend if available
        daily_trend = "SIDEWAYS"
        if df_daily is not None and len(df_daily) >= 200:
            df_daily = self._add_swing_indicators(df_daily)
            d_last = df_daily.iloc[-1]
            d_ema21 = float(d_last.get('ema_fast', 0))
            d_ema50 = float(d_last.get('ema_slow', 0))
            d_ema200 = float(d_last.get('ema_trend', 0))
            d_close = float(d_last.get('close', 0))
            if d_ema21 > d_ema50 > d_ema200 and d_close > d_ema200:
                daily_trend = "BULLISH"
            elif d_ema21 < d_ema50 < d_ema200 and d_close < d_ema200:
                daily_trend = "BEARISH"

        # Check for swing signal
        signal = self._check_swing_signal(
            symbol, analyzed, last, daily_trend,
            news_events=news_events or [],
            geopolitical_bias=geopolitical_bias,
        )

        return {
            'symbol': symbol,
            'signal': signal,
            'daily_trend': daily_trend,
            'strategy_mode': 'SWING',
            'atr': float(last.get('atr', 0)),
            'timestamp': datetime.now(),
        }

    def _add_swing_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add swing-optimized indicators."""
        cfg = self.swing_cfg
        from src.indicators import TechnicalIndicators as TI

        df = TI.add_atr(df, period=14)
        df = TI.add_adx(df, period=14)
        df = TI.add_rsi(df, period=cfg.get('rsi_period', 14))
        df = TI.add_bollinger_bands(df, period=20, std=2.0)
        df = TI.add_volume_indicators(df)
        df = TI.add_candle_analysis(df)
        df = TI.add_swing_points(df, lookback=5)

        # Swing EMAs (21/50/200)
        fast = cfg.get('ema_fast', 21)
        slow = cfg.get('ema_slow', 50)
        trend = cfg.get('ema_trend', 200)
        df['ema_fast'] = df['close'].ewm(span=fast, adjust=False).mean()
        df['ema_slow'] = df['close'].ewm(span=slow, adjust=False).mean()
        df['ema_trend'] = df['close'].ewm(span=trend, adjust=False).mean()

        # Fibonacci levels from recent swing
        if len(df) >= 50:
            recent = df.iloc[-50:]
            swing_high = recent['high'].max()
            swing_low = recent['low'].min()
            swing_range = swing_high - swing_low
            fib_levels = cfg.get('fib_levels', [0.236, 0.382, 0.5, 0.618, 0.786])
            for fib in fib_levels:
                df[f'fib_{fib}'] = swing_high - (swing_range * fib)

        # Previous day high/low (approximate from H4)
        if len(df) >= 6:  # 6 H4 candles per day
            prev_day = df.iloc[-12:-6] if len(df) >= 12 else df.iloc[:6]
            df['prev_day_high'] = prev_day['high'].max()
            df['prev_day_low'] = prev_day['low'].min()

        # SMC indicators
        try:
            df = TI.add_fair_value_gaps(df)
            df = TI.add_order_blocks(df, lookback=50)
            df = TI.add_break_of_structure(df, lookback=20)
        except Exception:
            pass

        return df

    def _check_swing_signal(self, symbol: str, df: pd.DataFrame,
                            last: pd.Series, daily_trend: str,
                            news_events: list = None,
                            geopolitical_bias: str = "NEUTRAL") -> Optional[Dict]:
        """Check for swing trade entry on H4."""
        close = float(last.get('close', 0))
        atr = float(last.get('atr', 0))
        rsi = float(last.get('rsi', 50))
        adx = float(last.get('adx', 20))
        ema_fast = float(last.get('ema_fast', 0))
        ema_slow = float(last.get('ema_slow', 0))
        ema_trend = float(last.get('ema_trend', 0))

        if atr <= 0:
            return None

        # Determine H4 trend
        h4_bullish = ema_fast > ema_slow and close > ema_trend
        h4_bearish = ema_fast < ema_slow and close < ema_trend

        # Check both directions
        for direction in ['BUY', 'SELL']:
            if direction == 'BUY' and not (h4_bullish or daily_trend == "BULLISH"):
                continue
            if direction == 'SELL' and not (h4_bearish or daily_trend == "BEARISH"):
                continue

            score = 0
            hits = []

            # 1. Daily trend alignment (+2 if matches, +1 if neutral)
            if daily_trend == ("BULLISH" if direction == "BUY" else "BEARISH"):
                score += 2; hits.append('D1_TREND')
            elif daily_trend == "SIDEWAYS":
                score += 1; hits.append('D1_NEUTRAL')

            # 2. H4 structure (BOS/MSS)
            if direction == 'BUY':
                has_bos = bool(last.get('bullish_bos', False) or last.get('bullish_choch', False))
            else:
                has_bos = bool(last.get('bearish_bos', False) or last.get('bearish_choch', False))
            if has_bos:
                score += 1; hits.append('H4_BOS')

            # 3. Key level confluence (prev day H/L, Fib levels)
            prev_day_high = float(last.get('prev_day_high', 0))
            prev_day_low = float(last.get('prev_day_low', 0))
            at_key_level = False
            if direction == 'BUY' and prev_day_low > 0:
                if abs(close - prev_day_low) < atr * 1.5:
                    at_key_level = True; hits.append('PREV_DAY_LOW')
            elif direction == 'SELL' and prev_day_high > 0:
                if abs(close - prev_day_high) < atr * 1.5:
                    at_key_level = True; hits.append('PREV_DAY_HIGH')

            # Check Fibonacci levels
            fib_levels = self.swing_cfg.get('fib_levels', [0.382, 0.5, 0.618, 0.786])
            for fib in fib_levels:
                fib_price = float(last.get(f'fib_{fib}', 0))
                if fib_price > 0 and abs(close - fib_price) < atr * 0.5:
                    if not at_key_level:
                        at_key_level = True; hits.append(f'FIB_{fib}')
                    break
            if at_key_level:
                score += 1

            # 4. News catalyst (BONUS — not mandatory since require_news_catalyst=False)
            # FIX 2026-04-14: News is now a bonus point, not a gating condition.
            # Gold moves technically even without scheduled news events.
            has_news = False
            require_news = self.swing_cfg.get('require_news_catalyst', False)
            if news_events:
                valid_events = self.swing_cfg.get('news_events', [])
                for event in news_events:
                    event_name = event if isinstance(event, str) else event.get('name', '')
                    if any(ne in event_name.upper() for ne in valid_events):
                        has_news = True; hits.append('NEWS_CATALYST')
                        break
            if has_news:
                score += 1  # Bonus point for news confluence
            elif require_news and not has_news:
                # Only skip if require_news_catalyst is explicitly True
                continue

            # 5. Geopolitical bias
            geo_bullish = geopolitical_bias in ("BULLISH", "BUY", "GOLD_BULLISH")
            geo_bearish = geopolitical_bias in ("BEARISH", "SELL", "GOLD_BEARISH")
            if direction == 'BUY' and geo_bullish:
                score += 1; hits.append('GEO_BULLISH')
            elif direction == 'SELL' and geo_bearish:
                score += 1; hits.append('GEO_BEARISH')

            # 6. RSI with zone check
            ob_threshold = self.swing_cfg.get('rsi_overbought', 70)
            os_threshold = self.swing_cfg.get('rsi_oversold', 30)
            if direction == 'BUY' and rsi < os_threshold:
                score += 1; hits.append('RSI_OVERSOLD')
            elif direction == 'SELL' and rsi > ob_threshold:
                score += 1; hits.append('RSI_OVERBOUGHT')
            elif direction == 'BUY' and 30 <= rsi <= 50:
                score += 0.5; hits.append('RSI_ZONE')
            elif direction == 'SELL' and 50 <= rsi <= 70:
                score += 0.5; hits.append('RSI_ZONE')

            # 7. Volume confirmation
            vol_ratio = float(last.get('volume_ratio', 1.0))
            if vol_ratio > 1.5:
                score += 1; hits.append('VOLUME')

            # 8. SMC (Order Block / FVG)
            lookback_n = min(10, len(df))
            recent = df.iloc[-lookback_n:]
            if direction == 'BUY':
                has_ob = bool('bullish_ob' in recent.columns and recent['bullish_ob'].any())
                has_fvg = bool('bullish_fvg' in recent.columns and recent['bullish_fvg'].any())
            else:
                has_ob = bool('bearish_ob' in recent.columns and recent['bearish_ob'].any())
                has_fvg = bool('bearish_fvg' in recent.columns and recent['bearish_fvg'].any())
            if has_ob or has_fvg:
                score += 1; hits.append('SMC_OB_FVG')

            # Check minimum confluences
            min_conf = self.swing_cfg.get('min_confluences', 4)
            if score >= min_conf:
                signal = self._generate_swing_signal(symbol, direction, df, last, hits, score)
                if signal:
                    logger.info(
                        f"[GOLD SWING] {direction} {symbol}: score={score}/{min_conf} "
                        f"hits={hits} daily={daily_trend} geo={geopolitical_bias}"
                    )
                    return signal

        return None

    def _generate_swing_signal(self, symbol: str, direction: str,
                               df: pd.DataFrame, last: pd.Series,
                               hits: list, score: float) -> Dict:
        """Generate swing trade signal with wide SL/TP."""
        atr = float(last.get('atr', 0))
        entry_price = float(last['close'])
        cfg = self.swing_cfg

        sl_mult = cfg.get('sl_atr_mult', 5.0)
        min_rr = cfg.get('min_rr', 2.0)

        if direction == 'BUY':
            stop_loss = entry_price - (atr * sl_mult)
            tp1 = entry_price + (atr * sl_mult * cfg.get('tp1_rr', 2.0))
            tp2 = entry_price + (atr * sl_mult * cfg.get('tp2_rr', 3.0))
            tp3 = entry_price + (atr * sl_mult * cfg.get('tp3_rr', 5.0))
        else:
            stop_loss = entry_price + (atr * sl_mult)
            tp1 = entry_price - (atr * sl_mult * cfg.get('tp1_rr', 2.0))
            tp2 = entry_price - (atr * sl_mult * cfg.get('tp2_rr', 3.0))
            tp3 = entry_price - (atr * sl_mult * cfg.get('tp3_rr', 5.0))

        risk_distance = abs(entry_price - stop_loss)
        risk_reward = abs(entry_price - tp2) / risk_distance if risk_distance > 0 else 0

        self.trades_today += 1
        self.trades_this_week += 1
        self.last_trade_time = datetime.now()

        signal = {
            'symbol': symbol,
            'direction': direction,
            'entry_price': round(entry_price, 2),
            'stop_loss': round(stop_loss, 2),
            'take_profit': round(tp2, 2),  # Primary TP at TP2
            'tp1': round(tp1, 2),
            'tp2': round(tp2, 2),
            'tp3': round(tp3, 2),
            'atr': atr,
            'adx': float(last.get('adx', 20)),
            'risk_reward': round(risk_reward, 2),
            'is_spike': False,
            'is_swing': True,
            'strategy_mode': 'SWING',
            'confluences': hits,
            'confluence_score': score,
            'timestamp': datetime.now(),
            'reason': f"SWING {direction} - {len(hits)} confluences: {', '.join(hits)}",
            'partial_tp': {
                'tp1_pct': cfg.get('partial_tp1_pct', 0.30),
                'tp2_pct': cfg.get('partial_tp2_pct', 0.30),
                'runner_pct': cfg.get('runner_pct', 0.40),
            },
        }

        logger.info(
            f"[GOLD SWING] Signal: {direction} {symbol} @ {entry_price:.2f} "
            f"SL: {stop_loss:.2f} TP1: {tp1:.2f} TP2: {tp2:.2f} TP3: {tp3:.2f} "
            f"RR: {risk_reward:.1f} Confluences: {hits}"
        )

        return signal


# Legacy alias for compatibility with main.py
AMDStrategy = GoldScalpStrategy


class MultiPairStrategy:
    """Manages scalping strategy across pairs."""

    def __init__(self, pairs: List[str] = None, risk_manager: RiskManager = None):
        self.pairs = pairs or settings.TRADING_PAIRS
        self.risk_manager = risk_manager or RiskManager()
        self.strategy = GoldScalpStrategy(self.risk_manager)
        self.pair_states: Dict[str, Dict] = {pair: {} for pair in self.pairs}

    def scan_all_pairs(self, data_dict: Dict[str, pd.DataFrame]) -> List[Dict]:
        """Scan all pairs for scalp signals."""
        signals = []
        for symbol, df in data_dict.items():
            if symbol not in self.pairs:
                continue
            try:
                result = self.strategy.analyze_market(symbol, df)
                if result.get('signal'):
                    signals.append(result)
                    logger.info(f"Scalp signal: {symbol} {result['signal']['direction']}")
                self.pair_states[symbol] = {
                    'phase': result.get('current_phase'),
                    'last_check': datetime.now(),
                    'signal': result.get('signal'),
                }
            except Exception as e:
                logger.error(f"Error analyzing {symbol}: {e}")
        return signals

    def filter_by_smart_rules(self, signal: Dict, symbol_info: Dict) -> Tuple[bool, str]:
        """Apply smart filters from settings.SMART_FILTERS"""
        smart = getattr(settings, 'SMART_FILTERS', {})

        # Check ADX range
        if smart.get('avoid_range_market', False):
            adx = signal.get('adx', 25)
            if adx < smart.get('min_adx_for_entry', 15):
                return False, 'ADX too low (ranging market)'

        # Check spread vs ATR
        if smart.get('max_spread_atr_ratio', 0):
            spread = symbol_info.get('spread', 0) / 10.0  # points to pips
            atr_pips = signal.get('atr', 1) / 0.10  # price to pips for gold
            if atr_pips > 0 and (spread / atr_pips) > smart['max_spread_atr_ratio']:
                return False, 'Spread too high vs ATR'

        return True, 'OK'

    def get_best_signal(self, signals: List[Dict], symbol_infos: Dict[str, Dict],
                        open_positions: List[Dict]) -> Optional[Dict]:
        """Select the best signal with improved scoring."""
        valid_signals = []
        for result in signals:
            signal = result.get('signal')
            if not signal:
                continue
            symbol = signal['symbol']
            symbol_info = symbol_infos.get(symbol, {})
            validation = self.strategy.validate_signal(signal, symbol_info, open_positions)
            if validation['valid']:
                # Apply smart filters
                passes_filters, filter_reason = self.filter_by_smart_rules(signal, symbol_info)
                if not passes_filters:
                    logger.info(f"Signal {symbol} filtered: {filter_reason}")
                    continue

                # Better scoring system
                score = 0
                if signal.get('is_spike', False):
                    score += 50

                # Get confluence score from signal's bull/bear scores
                if signal.get('direction') == 'BUY':
                    raw_score = signal.get('bull_score', 3)
                else:
                    raw_score = signal.get('bear_score', 3)
                score += raw_score * 10

                score += signal.get('risk_reward', 0) * 5

                # Check for London-NY overlap (session_overlap)
                try:
                    hour_utc = datetime.utcnow().hour
                    if 12 <= hour_utc <= 16:  # Prime London-NY overlap
                        score += 20
                except Exception:
                    pass

                # Check trend alignment from signal
                if signal.get('h1_trend_bull') and signal.get('direction') == 'BUY':
                    score += 15
                elif signal.get('h1_trend_bear') and signal.get('direction') == 'SELL':
                    score += 15

                signal['score'] = score
                valid_signals.append(signal)

        if not valid_signals:
            return None

        valid_signals.sort(key=lambda x: x.get('score', 0), reverse=True)
        return valid_signals[0]
