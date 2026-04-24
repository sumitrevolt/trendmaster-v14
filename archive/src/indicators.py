"""
GOLD SCALPING Indicators Module
=================================
Optimized for XAUUSD M1/M5 scalping with spike detection.
Combines fast scalping indicators with Smart Money Concepts.
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Tuple, Optional
import ta
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import settings


class TechnicalIndicators:
    """Technical indicators optimized for gold scalping."""

    @staticmethod
    def add_atr(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
        """Add Average True Range indicator."""
        df['atr'] = ta.volatility.average_true_range(
            df['high'], df['low'], df['close'], window=period
        )
        return df

    @staticmethod
    def add_bollinger_bands(df: pd.DataFrame, period: int = 20, std: float = 2.0) -> pd.DataFrame:
        """Add Bollinger Bands and bandwidth."""
        bb = ta.volatility.BollingerBands(df['close'], window=period, window_dev=std)
        df['bb_upper'] = bb.bollinger_hband()
        df['bb_middle'] = bb.bollinger_mavg()
        df['bb_lower'] = bb.bollinger_lband()
        df['bb_width'] = (df['bb_upper'] - df['bb_lower']) / df['bb_middle']
        return df

    @staticmethod
    def add_adx(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
        """Add ADX and directional indicators."""
        adx = ta.trend.ADXIndicator(df['high'], df['low'], df['close'], window=period)
        df['adx'] = adx.adx()
        df['di_plus'] = adx.adx_pos()
        df['di_minus'] = adx.adx_neg()
        return df

    @staticmethod
    def add_rsi(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
        """Add RSI indicator."""
        df['rsi'] = ta.momentum.rsi(df['close'], window=period)
        return df

    @staticmethod
    def add_volume_indicators(df: pd.DataFrame) -> pd.DataFrame:
        """Add volume-based indicators."""
        df['volume_sma'] = df['volume'].rolling(window=20).mean()
        df['volume_ratio'] = df['volume'] / df['volume_sma']
        df['volume_trend'] = df['volume'].rolling(window=5).mean().diff()
        return df

    @staticmethod
    def add_swing_points(df: pd.DataFrame, lookback: int = 5) -> pd.DataFrame:
        """Identify swing highs and lows."""
        df['swing_high'] = df['high'].rolling(window=lookback, center=True).max()
        df['swing_low'] = df['low'].rolling(window=lookback, center=True).min()
        df['is_swing_high'] = (df['high'] == df['swing_high'])
        df['is_swing_low'] = (df['low'] == df['swing_low'])
        return df

    @staticmethod
    def add_candle_analysis(df: pd.DataFrame) -> pd.DataFrame:
        """Analyze candle characteristics."""
        df['body'] = abs(df['close'] - df['open'])
        df['range'] = df['high'] - df['low']
        df['upper_wick'] = df['high'] - df[['open', 'close']].max(axis=1)
        df['lower_wick'] = df[['open', 'close']].min(axis=1) - df['low']
        df['upper_wick_ratio'] = np.where(df['range'] > 0, df['upper_wick'] / df['range'], 0)
        df['lower_wick_ratio'] = np.where(df['range'] > 0, df['lower_wick'] / df['range'], 0)
        df['bullish'] = df['close'] > df['open']
        df['bearish'] = df['close'] < df['open']
        return df

    # =========================================================================
    # GOLD SCALPING INDICATORS
    # =========================================================================

    @staticmethod
    def add_scalp_emas(df: pd.DataFrame) -> pd.DataFrame:
        """
        Add fast EMAs for scalping (9/21 crossover + 50 trend).
        Gold scalping uses faster EMAs than swing trading.
        """
        scalp = getattr(settings, 'SCALP', {})
        fast = scalp.get('ema_fast', 9)
        slow = scalp.get('ema_slow', 21)
        trend = scalp.get('ema_trend', 50)

        df['ema_fast'] = df['close'].ewm(span=fast, adjust=False).mean()
        df['ema_slow'] = df['close'].ewm(span=slow, adjust=False).mean()
        df['ema_trend'] = df['close'].ewm(span=trend, adjust=False).mean()
        # v3.0: HTF 200 EMA for macro trend filter (new)
        df['ema200'] = df['close'].ewm(span=200, adjust=False).mean()

        # EMA crossover signals
        df['ema_cross_bull'] = (df['ema_fast'] > df['ema_slow']) & (df['ema_fast'].shift(1) <= df['ema_slow'].shift(1))
        df['ema_cross_bear'] = (df['ema_fast'] < df['ema_slow']) & (df['ema_fast'].shift(1) >= df['ema_slow'].shift(1))

        # Trend alignment
        df['scalp_trend_bull'] = (df['ema_fast'] > df['ema_slow']) & (df['close'] > df['ema_trend'])
        df['scalp_trend_bear'] = (df['ema_fast'] < df['ema_slow']) & (df['close'] < df['ema_trend'])

        # Pullback to EMA (price near fast/slow EMA in trending market)
        ema_zone = df['atr'] * 0.3 if 'atr' in df.columns else (df['high'] - df['low']).rolling(14).mean() * 0.3
        df['pullback_to_ema_bull'] = (
            (df['low'] <= df['ema_fast'] + ema_zone) &
            (df['close'] > df['ema_fast']) &
            df['scalp_trend_bull']
        )
        df['pullback_to_ema_bear'] = (
            (df['high'] >= df['ema_fast'] - ema_zone) &
            (df['close'] < df['ema_fast']) &
            df['scalp_trend_bear']
        )

        return df

    @staticmethod
    def add_fast_rsi(df: pd.DataFrame) -> pd.DataFrame:
        """
        Add fast RSI (period 7) for scalping entries.
        Overbought/oversold zones for counter-trend scalps.
        """
        scalp = getattr(settings, 'SCALP', {})
        period = scalp.get('rsi_period', 7)
        df['rsi_fast'] = ta.momentum.rsi(df['close'], window=period)

        ob = scalp.get('rsi_overbought', 72)
        os_val = scalp.get('rsi_oversold', 28)
        df['rsi_oversold'] = df['rsi_fast'] < os_val
        df['rsi_overbought'] = df['rsi_fast'] > ob
        df['rsi_neutral'] = (df['rsi_fast'] >= os_val) & (df['rsi_fast'] <= ob)

        # RSI turning points (momentum shift)
        df['rsi_turning_up'] = (df['rsi_fast'] > df['rsi_fast'].shift(1)) & (df['rsi_fast'].shift(1) <= df['rsi_fast'].shift(2))
        df['rsi_turning_down'] = (df['rsi_fast'] < df['rsi_fast'].shift(1)) & (df['rsi_fast'].shift(1) >= df['rsi_fast'].shift(2))

        return df

    @staticmethod
    def add_spike_detection(df: pd.DataFrame) -> pd.DataFrame:
        """
        Detect sudden price spikes on gold (institutional moves, news).
        A spike = candle body > 2x ATR with high volume.
        These are the money-making moves we want to catch with trailing SL.
        """
        spike_cfg = getattr(settings, 'SPIKE', {})
        atr_mult = spike_cfg.get('atr_multiplier', 2.0)
        vol_mult = spike_cfg.get('volume_multiplier', 2.0)
        min_spike_pips = spike_cfg.get('min_spike_pips', 30)

        if 'atr' not in df.columns:
            df = TechnicalIndicators.add_atr(df)
        if 'volume_sma' not in df.columns:
            df = TechnicalIndicators.add_volume_indicators(df)

        pip_value = 0.10  # Gold: 1 pip = $0.10

        # Spike conditions
        body = abs(df['close'] - df['open'])
        big_body = body > (df['atr'] * atr_mult)
        big_volume = df['volume'] > (df['volume_sma'] * vol_mult)
        large_move = body >= (min_spike_pips * pip_value)

        df['spike_up'] = big_body & (df['close'] > df['open']) & big_volume & large_move
        df['spike_down'] = big_body & (df['close'] < df['open']) & big_volume & large_move
        df['spike'] = df['spike_up'] | df['spike_down']

        # Spike magnitude in pips
        df['spike_pips'] = np.where(df['spike'], body / pip_value, 0)

        # Recent spike detection (within last N candles)
        cooldown = spike_cfg.get('cooldown_candles', 5)
        max_delay = spike_cfg.get('max_entry_delay', 3)
        df['recent_spike_up'] = df['spike_up'].rolling(max_delay, min_periods=1).max().astype(bool)
        df['recent_spike_down'] = df['spike_down'].rolling(max_delay, min_periods=1).max().astype(bool)

        # Spike cooldown ENABLED — prevent double-entry on same spike event
        df['spike_cooldown'] = df['spike'].rolling(cooldown, min_periods=1).max().astype(bool) & ~df['spike']

        return df

    @staticmethod
    def add_momentum(df: pd.DataFrame) -> pd.DataFrame:
        """
        Add price momentum indicators for scalping.
        Rate of change + acceleration for trend strength assessment.
        """
        # Rate of change (5-period)
        df['roc_5'] = df['close'].pct_change(5) * 100
        # Rate of change (10-period)
        df['roc_10'] = df['close'].pct_change(10) * 100
        # Momentum acceleration
        df['momentum_accel'] = df['roc_5'] - df['roc_5'].shift(3)

        # Strong momentum (above/below threshold)
        df['strong_momentum_up'] = df['roc_5'] > 0.15
        df['strong_momentum_down'] = df['roc_5'] < -0.15

        return df

    @staticmethod
    def add_vwap(df: pd.DataFrame) -> pd.DataFrame:
        """
        Add VWAP (Volume Weighted Average Price) - institutional reference.
        Gold often bounces at VWAP during scalping sessions.
        Uses rolling VWAP since we don't have session boundaries.
        """
        typical_price = (df['high'] + df['low'] + df['close']) / 3
        vol = df['volume'].replace(0, 1)
        # Rolling 50-period VWAP
        df['vwap'] = (typical_price * vol).rolling(50).sum() / vol.rolling(50).sum()
        # Price relative to VWAP
        df['above_vwap'] = df['close'] > df['vwap']
        df['below_vwap'] = df['close'] < df['vwap']
        # Distance from VWAP as percentage of ATR
        if 'atr' in df.columns:
            df['vwap_distance'] = abs(df['close'] - df['vwap']) / df['atr']
            df['near_vwap'] = df['vwap_distance'] < 0.5  # Within 0.5 ATR of VWAP
        else:
            df['near_vwap'] = False
        return df

    @staticmethod
    def add_bb_squeeze(df: pd.DataFrame) -> pd.DataFrame:
        """
        Detect Bollinger Band squeeze (consolidation before breakout).
        Tight bands = low volatility = potential explosive move coming.
        """
        if 'bb_width' not in df.columns:
            df = TechnicalIndicators.add_bollinger_bands(df)

        # BB width percentile (lower = tighter squeeze)
        df['bb_percentile'] = df['bb_width'].rolling(100, min_periods=20).apply(
            lambda x: pd.Series(x).rank(pct=True).iloc[-1], raw=False
        )
        df['bb_squeeze'] = df['bb_percentile'] < 0.20  # Bottom 20% = squeeze

        # Breakout from squeeze
        df['bb_breakout_up'] = (df['close'] > df['bb_upper']) & df['bb_squeeze'].shift(1)
        df['bb_breakout_down'] = (df['close'] < df['bb_lower']) & df['bb_squeeze'].shift(1)

        # Bounce from bands (mean reversion)
        df['bb_bounce_up'] = (df['low'] <= df['bb_lower']) & (df['close'] > df['bb_lower'])
        df['bb_bounce_down'] = (df['high'] >= df['bb_upper']) & (df['close'] < df['bb_upper'])

        return df

    # =========================================================================
    # LEGACY INDICATORS (kept for SMC/AMD compatibility)
    # =========================================================================

    @staticmethod
    def add_ema_alignment(df: pd.DataFrame) -> pd.DataFrame:
        """Add EMA 20, 50, 200 for trend alignment (legacy + scalping)."""
        df['ema_20'] = df['close'].ewm(span=20, adjust=False).mean()
        df['ema_50'] = df['close'].ewm(span=50, adjust=False).mean()
        df['ema_200'] = df['close'].ewm(span=200, adjust=False).mean()

        df['bullish_ema_stack'] = (df['ema_20'] > df['ema_50']) & (df['ema_50'] > df['ema_200'])
        df['bearish_ema_stack'] = (df['ema_20'] < df['ema_50']) & (df['ema_50'] < df['ema_200'])
        df['above_all_ema'] = (df['close'] > df['ema_20']) & (df['close'] > df['ema_50']) & (df['close'] > df['ema_200'])
        df['below_all_ema'] = (df['close'] < df['ema_20']) & (df['close'] < df['ema_50']) & (df['close'] < df['ema_200'])

        return df
    
    @staticmethod
    def add_sniper_candlestick_patterns(df: pd.DataFrame) -> pd.DataFrame:
        """
        Detect high-probability candlestick patterns for scalp entries.
        Optimized: uses vectorized operations where possible.
        """
        df['pin_bar_bullish'] = False
        df['pin_bar_bearish'] = False
        df['engulfing_bullish'] = False
        df['engulfing_bearish'] = False
        df['morning_star'] = False
        df['evening_star'] = False
        df['hammer'] = False
        df['shooting_star'] = False

        if 'body' not in df.columns or 'range' not in df.columns:
            df = TechnicalIndicators.add_candle_analysis(df)

        body = df['body']
        rng = df['range'].replace(0, np.nan)
        lw_ratio = df['lower_wick'] / rng
        uw_ratio = df['upper_wick'] / rng
        body_ratio = body / rng

        # Pin bars (vectorized)
        df['pin_bar_bullish'] = (lw_ratio > 0.60) & (body_ratio < 0.30) & df['bullish']
        df['pin_bar_bearish'] = (uw_ratio > 0.60) & (body_ratio < 0.30) & df['bearish']

        # Hammer (bullish, long lower wick at lows)
        df['hammer'] = (lw_ratio > 0.60) & (body_ratio < 0.30)
        df['shooting_star'] = (uw_ratio > 0.60) & (body_ratio < 0.30)

        for i in range(2, len(df)):
            curr = df.iloc[i]
            prev = df.iloc[i - 1]
            prev2 = df.iloc[i - 2]
            b = abs(curr['close'] - curr['open'])
            prev_b = abs(prev['close'] - prev['open'])

            # Bullish Engulfing
            if prev['close'] < prev['open'] and curr['close'] > curr['open']:
                if curr['close'] > prev['open'] and curr['open'] < prev['close']:
                    if b > prev_b * 1.1:
                        df.iloc[i, df.columns.get_loc('engulfing_bullish')] = True

            # Bearish Engulfing
            if prev['close'] > prev['open'] and curr['close'] < curr['open']:
                if curr['open'] > prev['close'] and curr['close'] < prev['open']:
                    if b > prev_b * 1.1:
                        df.iloc[i, df.columns.get_loc('engulfing_bearish')] = True

            # Morning Star
            prev2_bearish = prev2['close'] < prev2['open']
            prev_doji = abs(prev['close'] - prev['open']) < (prev['high'] - prev['low']) * 0.3
            curr_bullish = curr['close'] > curr['open'] and curr['close'] > prev2['open']
            if prev2_bearish and prev_doji and curr_bullish:
                df.iloc[i, df.columns.get_loc('morning_star')] = True

            # Evening Star
            prev2_bullish = prev2['close'] > prev2['open']
            curr_bearish = curr['close'] < curr['open'] and curr['close'] < prev2['open']
            if prev2_bullish and prev_doji and curr_bearish:
                df.iloc[i, df.columns.get_loc('evening_star')] = True

        return df
    
    @staticmethod
    def add_rsi_divergence(df: pd.DataFrame, lookback: int = 14) -> pd.DataFrame:
        """
        Detect RSI divergence - powerful reversal signal.
        Bullish: Price makes lower low, RSI makes higher low
        Bearish: Price makes higher high, RSI makes lower high
        """
        df['bullish_divergence'] = False
        df['bearish_divergence'] = False
        
        for i in range(lookback, len(df)):
            # Get recent price and RSI data
            recent_price = df.iloc[i-lookback:i+1]
            
            # Find local lows for bullish divergence
            price_lows = recent_price['low'].rolling(5, center=True).min()
            rsi_at_lows = recent_price['rsi']
            
            # Simple divergence check
            if len(recent_price) >= 10:
                # Last 5 candles vs previous 5
                price_low_recent = recent_price['low'].iloc[-5:].min()
                price_low_prev = recent_price['low'].iloc[-10:-5].min()
                rsi_low_recent = recent_price['rsi'].iloc[-5:].min()
                rsi_low_prev = recent_price['rsi'].iloc[-10:-5].min()
                
                # Bullish divergence: Price lower low, RSI higher low
                if price_low_recent < price_low_prev and rsi_low_recent > rsi_low_prev:
                    df.iloc[i, df.columns.get_loc('bullish_divergence')] = True
                
                # Find highs for bearish divergence
                price_high_recent = recent_price['high'].iloc[-5:].max()
                price_high_prev = recent_price['high'].iloc[-10:-5].max()
                rsi_high_recent = recent_price['rsi'].iloc[-5:].max()
                rsi_high_prev = recent_price['rsi'].iloc[-10:-5].max()
                
                # Bearish divergence: Price higher high, RSI lower high
                if price_high_recent > price_high_prev and rsi_high_recent < rsi_high_prev:
                    df.iloc[i, df.columns.get_loc('bearish_divergence')] = True
        
        return df
    
    @staticmethod
    def add_volume_spike(df: pd.DataFrame) -> pd.DataFrame:
        """
        Detect significant volume spikes for SNIPER confirmation.
        High volume at reversal = institutional activity.
        """
        df['volume_sma_20'] = df['volume'].rolling(20).mean()
        df['volume_spike'] = df['volume'] > (df['volume_sma_20'] * 1.5)
        df['volume_climax'] = df['volume'] > (df['volume_sma_20'] * 2.5)
        return df
    
    @staticmethod
    def add_atr_filter(df: pd.DataFrame) -> pd.DataFrame:
        """
        ATR filter for SNIPER - avoid low volatility and extreme volatility.
        """
        if 'atr' not in df.columns:
            df['atr'] = ta.volatility.average_true_range(
                df['high'], df['low'], df['close'], window=14
            )
        
        atr_percentile = df['atr'].rolling(100).apply(
            lambda x: pd.Series(x).rank(pct=True).iloc[-1], raw=False
        )
        df['atr_percentile'] = atr_percentile
        
        # Good volatility range: 10% to 90% (wider range for gold M5 live trading)
        df['good_volatility'] = (df['atr_percentile'] > 0.10) & (df['atr_percentile'] < 0.90)
        return df
    
    @staticmethod
    def add_fair_value_gaps(df: pd.DataFrame) -> pd.DataFrame:
        """
        Detect Fair Value Gaps (FVG) - SMC concept.
        FVG occurs when there's a gap between candle 1's high/low and candle 3's low/high.
        """
        df['bullish_fvg'] = False
        df['bearish_fvg'] = False
        df['fvg_high'] = np.nan
        df['fvg_low'] = np.nan
        
        for i in range(2, len(df)):
            # Bullish FVG: Candle 1 high < Candle 3 low (gap up)
            if df.iloc[i-2]['high'] < df.iloc[i]['low']:
                df.iloc[i, df.columns.get_loc('bullish_fvg')] = True
                df.iloc[i, df.columns.get_loc('fvg_low')] = df.iloc[i-2]['high']
                df.iloc[i, df.columns.get_loc('fvg_high')] = df.iloc[i]['low']
            
            # Bearish FVG: Candle 1 low > Candle 3 high (gap down)
            if df.iloc[i-2]['low'] > df.iloc[i]['high']:
                df.iloc[i, df.columns.get_loc('bearish_fvg')] = True
                df.iloc[i, df.columns.get_loc('fvg_high')] = df.iloc[i-2]['low']
                df.iloc[i, df.columns.get_loc('fvg_low')] = df.iloc[i]['high']
        
        return df
    
    @staticmethod
    def add_order_blocks(df: pd.DataFrame, lookback: int = 50) -> pd.DataFrame:
        """
        Detect Order Blocks - SMC concept.
        Bullish OB: Last bearish candle before a strong bullish move.
        Bearish OB: Last bullish candle before a strong bearish move.
        """
        df['bullish_ob'] = False
        df['bearish_ob'] = False
        df['ob_high'] = np.nan
        df['ob_low'] = np.nan
        
        atr = df['atr'].mean() if 'atr' in df.columns else (df['high'] - df['low']).mean()
        min_move = atr * 2  # Require 2x ATR move for OB
        
        for i in range(5, min(len(df), lookback)):
            # Look for bullish order block
            if df.iloc[i-1]['close'] < df.iloc[i-1]['open']:  # Previous candle bearish
                # Check if current and next candles make strong bullish move
                if i + 3 < len(df):
                    move = df.iloc[i:i+3]['high'].max() - df.iloc[i-1]['low']
                    if move > min_move:
                        df.iloc[i-1, df.columns.get_loc('bullish_ob')] = True
                        df.iloc[i-1, df.columns.get_loc('ob_low')] = df.iloc[i-1]['low']
                        df.iloc[i-1, df.columns.get_loc('ob_high')] = df.iloc[i-1]['high']
            
            # Look for bearish order block
            if df.iloc[i-1]['close'] > df.iloc[i-1]['open']:  # Previous candle bullish
                if i + 3 < len(df):
                    move = df.iloc[i-1]['high'] - df.iloc[i:i+3]['low'].min()
                    if move > min_move:
                        df.iloc[i-1, df.columns.get_loc('bearish_ob')] = True
                        df.iloc[i-1, df.columns.get_loc('ob_high')] = df.iloc[i-1]['high']
                        df.iloc[i-1, df.columns.get_loc('ob_low')] = df.iloc[i-1]['low']
        
        return df
    
    @staticmethod
    def add_break_of_structure(df: pd.DataFrame, lookback: int = 20) -> pd.DataFrame:
        """
        Detect Break of Structure (BOS) and Change of Character (CHoCH) - SMC concepts.
        BOS: Price breaks previous swing high/low in trend direction.
        CHoCH: Price breaks structure against the trend (reversal signal).
        """
        df['bullish_bos'] = False
        df['bearish_bos'] = False
        df['bullish_choch'] = False
        df['bearish_choch'] = False
        
        # Find recent swing highs and lows
        for i in range(lookback, len(df)):
            recent = df.iloc[i-lookback:i]
            
            # Get highest high and lowest low
            highest_high = recent['high'].max()
            lowest_low = recent['low'].min()
            
            # Determine trend based on recent closes
            trend_up = recent['close'].iloc[-5:].mean() > recent['close'].iloc[:5].mean()
            
            current = df.iloc[i]
            
            # Bullish BOS: Price breaks above highest high in uptrend
            if current['close'] > highest_high:
                if trend_up:
                    df.iloc[i, df.columns.get_loc('bullish_bos')] = True
                else:
                    df.iloc[i, df.columns.get_loc('bullish_choch')] = True  # CHoCH - reversal
            
            # Bearish BOS: Price breaks below lowest low in downtrend
            if current['close'] < lowest_low:
                if not trend_up:
                    df.iloc[i, df.columns.get_loc('bearish_bos')] = True
                else:
                    df.iloc[i, df.columns.get_loc('bearish_choch')] = True  # CHoCH - reversal
        
        return df


class HTFLiquidityIndicators:
    """
    Higher Timeframe Liquidity Indicators for H1/H4.
    Adds liquidity-related columns to DataFrames for the LiquidityEngine.
    """

    @staticmethod
    def add_liquidity_levels(df: pd.DataFrame, lookback: int = 20) -> pd.DataFrame:
        """
        Add buy-side and sell-side liquidity level columns.
        Buy-side = recent swing highs (stop losses of shorts rest above)
        Sell-side = recent swing lows (stop losses of longs rest below)
        """
        df['liq_buy_side'] = df['high'].rolling(window=lookback).max()
        df['liq_sell_side'] = df['low'].rolling(window=lookback).min()

        # Distance to nearest liquidity
        df['dist_to_buy_liq'] = (df['liq_buy_side'] - df['close']) / df['close'] * 100
        df['dist_to_sell_liq'] = (df['close'] - df['liq_sell_side']) / df['close'] * 100

        # Near liquidity zone (within 0.3% of a level)
        df['near_buy_liq'] = df['dist_to_buy_liq'] < 0.3
        df['near_sell_liq'] = df['dist_to_sell_liq'] < 0.3

        return df

    @staticmethod
    def add_equal_hl_detection(df: pd.DataFrame, tolerance_pct: float = 0.0015) -> pd.DataFrame:
        """
        Detect equal highs and equal lows in the data.
        Equal H/L = massive liquidity pool where many stops are clustered.
        """
        df['equal_highs'] = False
        df['equal_lows'] = False

        for i in range(5, len(df)):
            recent_highs = df.iloc[max(0, i-20):i]['high']
            recent_lows = df.iloc[max(0, i-20):i]['low']
            current_high = df.iloc[i]['high']
            current_low = df.iloc[i]['low']

            # Check for equal highs (multiple touches at same level)
            near_same_high = sum(1 for h in recent_highs
                                if abs(h - current_high) / current_high < tolerance_pct)
            if near_same_high >= 2:
                df.iloc[i, df.columns.get_loc('equal_highs')] = True

            # Check for equal lows
            near_same_low = sum(1 for lo in recent_lows
                               if abs(lo - current_low) / current_low < tolerance_pct)
            if near_same_low >= 2:
                df.iloc[i, df.columns.get_loc('equal_lows')] = True

        return df

    @staticmethod
    def add_sweep_indicators(df: pd.DataFrame) -> pd.DataFrame:
        """
        Add sweep detection indicators.
        A sweep = price pierces beyond liquidity level then reverses.
        """
        df['sweep_up'] = False
        df['sweep_down'] = False
        df['sweep_volume'] = False

        if 'liq_buy_side' not in df.columns:
            df = HTFLiquidityIndicators.add_liquidity_levels(df)

        for i in range(2, len(df)):
            prev_buy_liq = df.iloc[i-1].get('liq_buy_side', 0)
            prev_sell_liq = df.iloc[i-1].get('liq_sell_side', float('inf'))

            # Sweep UP: wick goes above buy-side liquidity, closes below
            if (df.iloc[i]['high'] > prev_buy_liq and
                df.iloc[i]['close'] < prev_buy_liq):
                df.iloc[i, df.columns.get_loc('sweep_up')] = True

            # Sweep DOWN: wick goes below sell-side liquidity, closes above
            if (df.iloc[i]['low'] < prev_sell_liq and
                df.iloc[i]['close'] > prev_sell_liq):
                df.iloc[i, df.columns.get_loc('sweep_down')] = True

        # Volume at sweep
        if 'volume_sma' not in df.columns:
            df['volume_sma'] = df['volume'].rolling(20).mean()
        df['sweep_volume'] = (df['sweep_up'] | df['sweep_down']) & (df['volume'] > df['volume_sma'] * 1.3)

        return df

    @staticmethod
    def add_all_liquidity(df: pd.DataFrame, lookback: int = 20,
                          tolerance_pct: float = 0.0015) -> pd.DataFrame:
        """Add all liquidity indicators in one call."""
        df = HTFLiquidityIndicators.add_liquidity_levels(df, lookback)
        df = HTFLiquidityIndicators.add_equal_hl_detection(df, tolerance_pct)
        df = HTFLiquidityIndicators.add_sweep_indicators(df)
        return df


class AccumulationDetector:
    """
    Detect Accumulation Phase
    --------------------------
    Characteristics:
    - Low volatility (tight Bollinger Bands)
    - Low ATR percentile
    - Ranging/consolidating price
    - Declining volume
    - Weak ADX (< 20)
    """
    
    def __init__(self, params: Dict = None):
        self.params = params or settings.ACCUMULATION
    
    def detect(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Detect accumulation zones in the data.
        
        Args:
            df: DataFrame with OHLCV data
            
        Returns:
            DataFrame with accumulation signals added
        """
        df = df.copy()
        
        # Add required indicators
        df = TechnicalIndicators.add_atr(df, self.params['atr_period'])
        df = TechnicalIndicators.add_bollinger_bands(
            df, self.params['bb_period'], self.params['bb_std']
        )
        df = TechnicalIndicators.add_adx(df)
        df = TechnicalIndicators.add_volume_indicators(df)
        
        # Calculate ATR percentile (lower = more consolidation)
        df['atr_percentile'] = df['atr'].rolling(100).apply(
            lambda x: pd.Series(x).rank(pct=True).iloc[-1] if len(x) > 0 else 0.5
        )
        
        # Accumulation conditions
        low_volatility = df['atr_percentile'] < self.params['atr_percentile_threshold']
        tight_bands = df['bb_width'] < self.params['bb_squeeze_threshold']
        weak_trend = df['adx'] < self.params['adx_threshold']
        declining_volume = df['volume_trend'] < 0
        
        # Price in range (within Bollinger Bands)
        price_ranging = (
            (df['close'] > df['bb_lower']) & 
            (df['close'] < df['bb_upper']) &
            (df['high'] < df['bb_upper'] * 1.001) &
            (df['low'] > df['bb_lower'] * 0.999)
        )
        
        # Combined accumulation signal
        df['accumulation'] = (
            low_volatility & 
            (tight_bands | weak_trend) & 
            price_ranging
        )
        
        # Accumulation zone (consecutive accumulation candles)
        df['accumulation_zone'] = df['accumulation'].rolling(
            self.params['min_consolidation_candles']
        ).sum() >= self.params['min_consolidation_candles']
        
        # Store accumulation high/low for later reference
        df['accumulation_high'] = np.where(
            df['accumulation_zone'],
            df['high'].rolling(self.params['min_consolidation_candles']).max(),
            np.nan
        )
        df['accumulation_low'] = np.where(
            df['accumulation_zone'],
            df['low'].rolling(self.params['min_consolidation_candles']).min(),
            np.nan
        )
        
        # Fill forward accumulation levels
        df['accumulation_high'] = df['accumulation_high'].ffill()
        df['accumulation_low'] = df['accumulation_low'].ffill()
        
        return df


class ManipulationDetector:
    """
    Detect Manipulation Phase (Liquidity Grab / Fake Breakout)
    -----------------------------------------------------------
    Characteristics:
    - Price breaks above/below accumulation zone
    - High volume spike
    - Long wick (rejection)
    - Quick reversal back into range
    """
    
    def __init__(self, params: Dict = None):
        self.params = params or settings.MANIPULATION
    
    def detect(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Detect manipulation (liquidity grab) signals.
        
        Args:
            df: DataFrame with accumulation data
            
        Returns:
            DataFrame with manipulation signals added
        """
        df = df.copy()
        
        # Ensure we have candle analysis
        df = TechnicalIndicators.add_candle_analysis(df)
        df = TechnicalIndicators.add_swing_points(df, self.params['swing_lookback'])
        
        if 'volume_ratio' not in df.columns:
            df = TechnicalIndicators.add_volume_indicators(df)
        
        # Volume spike condition
        volume_spike = df['volume_ratio'] >= self.params['volume_spike_multiplier']
        
        # Wick rejection conditions
        strong_upper_wick = df['upper_wick_ratio'] >= self.params['wick_ratio_threshold']
        strong_lower_wick = df['lower_wick_ratio'] >= self.params['wick_ratio_threshold']
        
        # Break of swing points
        if 'accumulation_high' in df.columns and 'accumulation_low' in df.columns:
            # Broke above accumulation high
            broke_high = df['high'] > df['accumulation_high'].shift(1)
            # Broke below accumulation low
            broke_low = df['low'] < df['accumulation_low'].shift(1)
        else:
            # Use swing points if no accumulation data
            broke_high = df['high'] > df['swing_high'].shift(1)
            broke_low = df['low'] < df['swing_low'].shift(1)
        
        # Bullish manipulation (sweep lows, then reverse up)
        # Price takes out lows, has strong lower wick, closes bullish
        df['bullish_manipulation'] = (
            broke_low &
            strong_lower_wick &
            df['bullish'] &
            volume_spike
        )
        
        # Bearish manipulation (sweep highs, then reverse down)
        # Price takes out highs, has strong upper wick, closes bearish
        df['bearish_manipulation'] = (
            broke_high &
            strong_upper_wick &
            df['bearish'] &
            volume_spike
        )
        
        # Overall manipulation signal
        df['manipulation'] = df['bullish_manipulation'] | df['bearish_manipulation']
        
        # Store manipulation levels (the sweep wick extremes)
        df['manipulation_level'] = np.where(
            df['bullish_manipulation'],
            df['low'],  # Bullish manipulation low = potential entry zone
            np.where(
                df['bearish_manipulation'],
                df['high'],  # Bearish manipulation high = potential entry zone
                np.nan
            )
        )
        
        return df


class DistributionDetector:
    """
    Detect Distribution Phase (Real Directional Move)
    ---------------------------------------------------
    Characteristics:
    - Strong directional move after manipulation
    - Rising ADX (> 25)
    - Volume confirmation
    - Break of market structure
    """
    
    def __init__(self, params: Dict = None):
        self.params = params or settings.DISTRIBUTION
    
    def detect(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Detect distribution (real move) signals.
        
        Args:
            df: DataFrame with manipulation data
            
        Returns:
            DataFrame with distribution signals added
        """
        df = df.copy()
        
        if 'adx' not in df.columns:
            df = TechnicalIndicators.add_adx(df)
        
        if 'atr' not in df.columns:
            df = TechnicalIndicators.add_atr(df)
        
        # Strong trend condition
        strong_trend = df['adx'] > self.params['adx_threshold']
        
        # Bullish distribution - upward move
        bullish_momentum = (
            (df['di_plus'] > df['di_minus']) &
            (df['close'] > df['open']) &
            (df['close'] > df['close'].shift(1))
        )
        
        # Bearish distribution - downward move
        bearish_momentum = (
            (df['di_minus'] > df['di_plus']) &
            (df['close'] < df['open']) &
            (df['close'] < df['close'].shift(1))
        )
        
        # Move must be significant (at least 1x ATR)
        significant_move = (df['high'] - df['low']) >= (df['atr'] * self.params['min_move_atr_multiple'])
        
        # Check for prior manipulation
        had_bullish_manipulation = df['bullish_manipulation'].rolling(
            self.params['momentum_confirmation_candles']
        ).sum() > 0
        
        had_bearish_manipulation = df['bearish_manipulation'].rolling(
            self.params['momentum_confirmation_candles']
        ).sum() > 0
        
        # Distribution signals (must follow manipulation)
        df['bullish_distribution'] = (
            bullish_momentum &
            strong_trend &
            significant_move &
            had_bullish_manipulation.shift(1)  # Manipulation in previous candles
        )
        
        df['bearish_distribution'] = (
            bearish_momentum &
            strong_trend &
            significant_move &
            had_bearish_manipulation.shift(1)  # Manipulation in previous candles
        )
        
        df['distribution'] = df['bullish_distribution'] | df['bearish_distribution']
        
        return df


class AMDAnalyzer:
    """
    Complete AMD (Accumulation-Manipulation-Distribution) Analyzer
    ===============================================================
    Combines all three phases to identify high-probability trading setups.
    
    SNIPER 85% WIN RATE VERSION - Requires 5+ confluences for entry.
    """
    
    def __init__(self):
        self.accumulation = AccumulationDetector()
        self.manipulation = ManipulationDetector()
        self.distribution = DistributionDetector()
        
    def analyze(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Run complete scalping analysis on price data.

        GOLD SCALPING STRATEGY combines:
        1. AMD (Accumulation, Manipulation, Distribution)
        2. SMC (Order Blocks, Fair Value Gaps, Break of Structure)
        3. SCALPING (Fast EMAs, Fast RSI, Spike detection, VWAP, Momentum)

        Args:
            df: DataFrame with OHLCV data

        Returns:
            DataFrame with all scalping signals
        """
        # Phase 1: Accumulation (Consolidation zone)
        df = self.accumulation.detect(df)

        # Phase 2: Manipulation (Liquidity hunt)
        df = self.manipulation.detect(df)

        # Phase 3: Distribution (Trend move)
        df = self.distribution.detect(df)

        # Base indicators
        df = TechnicalIndicators.add_rsi(df)
        df = TechnicalIndicators.add_candle_analysis(df)

        # SMC indicators
        df = TechnicalIndicators.add_fair_value_gaps(df)
        df = TechnicalIndicators.add_order_blocks(df)
        df = TechnicalIndicators.add_break_of_structure(df)

        # Legacy EMA alignment
        df = TechnicalIndicators.add_ema_alignment(df)
        df = TechnicalIndicators.add_sniper_candlestick_patterns(df)
        df = TechnicalIndicators.add_rsi_divergence(df)
        df = TechnicalIndicators.add_volume_spike(df)
        df = TechnicalIndicators.add_atr_filter(df)

        # ===== NEW SCALPING INDICATORS =====
        df = TechnicalIndicators.add_scalp_emas(df)
        df = TechnicalIndicators.add_fast_rsi(df)
        df = TechnicalIndicators.add_spike_detection(df)
        df = TechnicalIndicators.add_momentum(df)
        df = TechnicalIndicators.add_vwap(df)
        df = TechnicalIndicators.add_bb_squeeze(df)

        # AMD phase labels
        df['amd_phase'] = 'None'
        df.loc[df['accumulation_zone'], 'amd_phase'] = 'Accumulation'
        df.loc[df['manipulation'], 'amd_phase'] = 'Manipulation'
        df.loc[df['distribution'], 'amd_phase'] = 'Distribution'

        # ===== SCALPING CONFLUENCE SCORE =====
        df['scalp_bull_score'] = 0
        df['scalp_bear_score'] = 0

        # 1. Trend alignment (fast EMA crossover) +2
        df.loc[df['scalp_trend_bull'], 'scalp_bull_score'] += 2
        df.loc[df['scalp_trend_bear'], 'scalp_bear_score'] += 2

        # 2. Pullback to EMA +2
        df.loc[df['pullback_to_ema_bull'], 'scalp_bull_score'] += 2
        df.loc[df['pullback_to_ema_bear'], 'scalp_bear_score'] += 2

        # 3. RSI condition (oversold for buy, overbought for sell) +2
        df.loc[df['rsi_oversold'], 'scalp_bull_score'] += 2
        df.loc[df['rsi_overbought'], 'scalp_bear_score'] += 2
        # RSI neutral but trending = +1
        df.loc[df['rsi_neutral'] & df['scalp_trend_bull'], 'scalp_bull_score'] += 1
        df.loc[df['rsi_neutral'] & df['scalp_trend_bear'], 'scalp_bear_score'] += 1

        # 4. Volume spike +1
        if 'volume_spike' in df.columns:
            df.loc[df['volume_spike'], 'scalp_bull_score'] += 1
            df.loc[df['volume_spike'], 'scalp_bear_score'] += 1

        # 5. Candle pattern +2
        if 'pin_bar_bullish' in df.columns:
            df.loc[df['pin_bar_bullish'] | df['engulfing_bullish'] | df['hammer'], 'scalp_bull_score'] += 2
            df.loc[df['pin_bar_bearish'] | df['engulfing_bearish'] | df['shooting_star'], 'scalp_bear_score'] += 2

        # 6. Momentum confirmation +1
        df.loc[df['strong_momentum_up'], 'scalp_bull_score'] += 1
        df.loc[df['strong_momentum_down'], 'scalp_bear_score'] += 1

        # 7. VWAP bounce +1
        df.loc[df['above_vwap'] & df['near_vwap'], 'scalp_bull_score'] += 1
        df.loc[df['below_vwap'] & df['near_vwap'], 'scalp_bear_score'] += 1

        # 8. BB squeeze breakout +2
        df.loc[df['bb_breakout_up'], 'scalp_bull_score'] += 2
        df.loc[df['bb_breakout_down'], 'scalp_bear_score'] += 2
        df.loc[df['bb_bounce_up'], 'scalp_bull_score'] += 1
        df.loc[df['bb_bounce_down'], 'scalp_bear_score'] += 1

        # 9. SMC confirmations +1 each
        if 'bullish_ob' in df.columns:
            df.loc[df['bullish_ob'], 'scalp_bull_score'] += 1
            df.loc[df['bearish_ob'], 'scalp_bear_score'] += 1
        if 'bullish_fvg' in df.columns:
            df.loc[df['bullish_fvg'], 'scalp_bull_score'] += 1
            df.loc[df['bearish_fvg'], 'scalp_bear_score'] += 1
        if 'bullish_bos' in df.columns:
            df.loc[df['bullish_bos'], 'scalp_bull_score'] += 1
            df.loc[df['bearish_bos'], 'scalp_bear_score'] += 1

        # 10. Spike detection +3 (high priority for spike trades)
        df.loc[df['recent_spike_up'], 'scalp_bull_score'] += 3
        df.loc[df['recent_spike_down'], 'scalp_bear_score'] += 3

        # Legacy sniper scores (for compatibility)
        df['sniper_bullish_score'] = df['scalp_bull_score']
        df['sniper_bearish_score'] = df['scalp_bear_score']

        min_score = getattr(settings, 'SCALP', {}).get('min_confluences', 3)
        df['sniper_buy_signal'] = df['scalp_bull_score'] >= min_score
        df['sniper_sell_signal'] = df['scalp_bear_score'] >= min_score

        return df
    
    def get_current_phase(self, df: pd.DataFrame) -> Dict:
        """
        Get the current AMD phase and relevant information.
        
        Args:
            df: Analyzed DataFrame
            
        Returns:
            Dict with current phase info
        """
        if df.empty:
            return {'phase': 'Unknown', 'signal': None}
        
        last = df.iloc[-1]
        
        return {
            'phase': last.get('amd_phase', 'None'),
            'accumulation_active': last.get('accumulation_zone', False),
            'bullish_manipulation': last.get('bullish_manipulation', False),
            'bearish_manipulation': last.get('bearish_manipulation', False),
            'bullish_distribution': last.get('bullish_distribution', False),
            'bearish_distribution': last.get('bearish_distribution', False),
            'atr': last.get('atr', 0),
            'adx': last.get('adx', 0),
            'accumulation_high': last.get('accumulation_high', None),
            'accumulation_low': last.get('accumulation_low', None),
        }
    
    def find_trade_setups(self, df: pd.DataFrame) -> List[Dict]:
        """
        Find complete AMD trade setups in the data.
        
        Args:
            df: Analyzed DataFrame
            
        Returns:
            List of trade setup dictionaries
        """
        setups = []
        
        for i in range(len(df)):
            row = df.iloc[i]
            
            # Look for manipulation followed by distribution
            if row.get('bullish_distribution', False):
                # Find the manipulation candle
                lookback = min(i, 10)
                for j in range(i - lookback, i):
                    if df.iloc[j].get('bullish_manipulation', False):
                        setups.append({
                            'type': 'BUY',
                            'entry_time': df.index[i],
                            'manipulation_time': df.index[j],
                            'manipulation_low': df.iloc[j]['low'],
                            'entry_price': row['close'],
                            'stop_loss': df.iloc[j]['low'] - (row['atr'] * 0.5),
                            'take_profit': row['close'] + (row['atr'] * 3),
                            'atr': row['atr'],
                        })
                        break
            
            elif row.get('bearish_distribution', False):
                lookback = min(i, 10)
                for j in range(i - lookback, i):
                    if df.iloc[j].get('bearish_manipulation', False):
                        setups.append({
                            'type': 'SELL',
                            'entry_time': df.index[i],
                            'manipulation_time': df.index[j],
                            'manipulation_high': df.iloc[j]['high'],
                            'entry_price': row['close'],
                            'stop_loss': df.iloc[j]['high'] + (row['atr'] * 0.5),
                            'take_profit': row['close'] - (row['atr'] * 3),
                            'atr': row['atr'],
                        })
                        break
        
        return setups


if __name__ == "__main__":
    # Test with sample data
    print("AMD Indicator Module - Testing")
    print("=" * 50)
    
    # Create sample data for testing
    np.random.seed(42)
    dates = pd.date_range(start='2025-01-01', periods=200, freq='H')
    
    # Simulate price data with AMD pattern
    base_price = 1.1000
    prices = [base_price]
    
    for i in range(199):
        # Add some random walk
        change = np.random.randn() * 0.0010
        prices.append(prices[-1] + change)
    
    df = pd.DataFrame({
        'open': prices,
        'high': [p + abs(np.random.randn() * 0.0005) for p in prices],
        'low': [p - abs(np.random.randn() * 0.0005) for p in prices],
        'close': [p + np.random.randn() * 0.0003 for p in prices],
        'volume': np.random.randint(1000, 10000, 200),
    }, index=dates)
    
    # Ensure high >= open, close and low <= open, close
    df['high'] = df[['open', 'high', 'close']].max(axis=1)
    df['low'] = df[['open', 'low', 'close']].min(axis=1)
    
    # Run AMD analysis
    analyzer = AMDAnalyzer()
    result = analyzer.analyze(df)
    
    print("\nSample Analysis Results:")
    print(result[['close', 'atr', 'adx', 'amd_phase']].tail(20))
    
    print("\nCurrent Phase:")
    phase_info = analyzer.get_current_phase(result)
    for key, value in phase_info.items():
        print(f"  {key}: {value}")
    
    print("\nTrade Setups Found:", len(analyzer.find_trade_setups(result)))
