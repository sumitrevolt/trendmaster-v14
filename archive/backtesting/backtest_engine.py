"""
Backtesting Engine for AMD Strategy
=====================================
Test the AMD strategy on historical data.
WITH BRAIN LEARNING INTEGRATION - learns from backtest trades!
WITH PARTIAL TP + ATR-BASED ADAPTIVE TRAILING!
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import settings
from src.indicators import AMDAnalyzer
from src.strategy import GoldScalpStrategy
from src.risk_manager import RiskManager
from src.brain import get_brain, TradingBrain


class BacktestTrade:
    """
    BILLIONAIRE SNIPER TRADE with Partial TP + Trailing Stop Loss System.

    KEY FEATURES:
    - Partial TP at 1:1 RR (closes 50%, moves SL to breakeven)
    - Trailing stop activates at configurable RR level
    - SL trails behind price by ATR-multiplied distance
    - Protects profits while letting winners run
    """

    def __init__(
        self,
        symbol: str,
        direction: str,
        entry_price: float,
        entry_time: datetime,
        stop_loss: float,
        take_profit: float,
        volume: float,
        features: Optional[Dict] = None
    ):
        self.symbol = symbol
        self.direction = direction
        self.entry_price = entry_price
        self.entry_time = entry_time
        self.stop_loss = stop_loss
        self.take_profit = take_profit
        self.volume = volume

        # Calculate TP1 at 1:1 RR (for partial TP system)
        sl_distance = abs(entry_price - stop_loss)
        if direction == 'BUY':
            self.take_profit_1 = entry_price + sl_distance  # 1:1
        else:
            self.take_profit_1 = entry_price - sl_distance  # 1:1

        self.exit_price: Optional[float] = None
        self.exit_time: Optional[datetime] = None
        self.profit: float = 0.0
        self.exit_reason: str = ""
        self.closed = False

        # Partial TP tracking
        self.partial_tp_taken = False
        self.partial_volume = 0.0  # Volume closed at TP1
        self.partial_profit = 0.0  # Profit from TP1 close

        # Trailing stop tracking
        self.trailing_activated = False
        self.highest_profit_price = entry_price  # For BUY: highest price seen
        self.lowest_profit_price = entry_price   # For SELL: lowest price seen

        # Original values for reference
        self.original_sl = stop_loss
        self.original_volume = volume
        self.original_tp = take_profit

        # Store entry-time features/confluences for research & tuning
        self.features: Dict = features or {}
        self.is_spike: bool = False  # Set True for spike entries (tighter trail)
        self.candle_count: int = 0   # Track candles since entry for time-based exit
        self.entry_atr: float = 0.0  # ATR at entry time for dynamic trailing

        # ATR-based adaptive trail settings
        self.trail_atr_mult: float = 0.0  # 0 = use global settings
        self.breakeven_atr_mult: float = 0.0  # 0 = use global settings
        self.activation_atr_mult: float = 0.0  # 0 = use global settings

        # Per-TF fixed trail settings (override ATR-based when set)
        self.tf_breakeven_pips: float = 0    # 0 = use global settings
        self.tf_activation_pips: float = 0   # 0 = use global settings
        self.tf_trail_pips: float = 0        # 0 = use ATR-based trail
        self.tf_max_candles: int = 0         # 0 = use global settings

    def check_exit(self, high: float, low: float, current_time: datetime) -> bool:
        """
        GOLD SCALPING EXIT SYSTEM - Partial TP + Breakeven + Trailing:
        1. Check PARTIAL TP (1:1 RR) - close 50%, move SL to breakeven
        2. Check FULL TP hit
        3. Move to breakeven after breakeven distance
        4. Activate trailing after activation distance
        5. Time-based exit after max candles
        6. Check SL hit (includes trailing and breakeven)
        """
        if self.closed:
            return False

        self.candle_count += 1

        is_gold = 'XAU' in self.symbol or 'GOLD' in self.symbol
        pip_size = 0.10 if is_gold else 0.0001
        if 'JPY' in self.symbol:
            pip_size = 0.01

        # =====================================================================
        # CALCULATE DISTANCES (ATR-based or fixed pip-based)
        # =====================================================================

        # Use per-TF settings if set, otherwise fall back to ATR-based
        if self.tf_breakeven_pips > 0:
            breakeven_distance = self.tf_breakeven_pips * pip_size
        else:
            # ATR-based breakeven
            breakeven_atr_mult = self.breakeven_atr_mult if self.breakeven_atr_mult > 0 else settings.RISK.get('breakeven_atr_mult', 0.5)
            breakeven_distance = self.entry_atr * breakeven_atr_mult if self.entry_atr > 0 else settings.RISK.get('breakeven_pips', 8) * pip_size

        if self.tf_activation_pips > 0:
            activation_distance = self.tf_activation_pips * pip_size
        else:
            # ATR-based activation
            activation_atr_mult = self.activation_atr_mult if self.activation_atr_mult > 0 else settings.RISK.get('activation_atr_mult', 1.0)
            activation_distance = self.entry_atr * activation_atr_mult if self.entry_atr > 0 else settings.RISK.get('trailing_activation_pips', 15) * pip_size

        # Trailing distance - ATR-based or fixed
        if self.tf_trail_pips > 0:
            trail_pips_spike = settings.SPIKE.get('trail_pips', 5)
            trail_pips = trail_pips_spike if self.is_spike else self.tf_trail_pips
            trail_distance = trail_pips * pip_size
        else:
            # ATR-based trailing
            trail_atr_mult = self.trail_atr_mult if self.trail_atr_mult > 0 else settings.RISK.get('trail_atr_multiplier', 0.5)
            trail_atr_mult_spike = settings.RISK.get('trail_atr_multiplier_spike', 0.3)
            max_trail_pips = settings.RISK.get('max_trail_pips', 10)
            max_trail_pips_spike = settings.RISK.get('max_trail_pips_spike', 5)
            if self.entry_atr > 0:
                base_mult = trail_atr_mult_spike if self.is_spike else trail_atr_mult
                trail_distance = self.entry_atr * base_mult
                max_trail = (max_trail_pips_spike if self.is_spike else max_trail_pips) * pip_size
                trail_distance = min(trail_distance, max_trail)
            else:
                trail_distance = (max_trail_pips_spike if self.is_spike else max_trail_pips) * pip_size

        if self.direction == 'BUY':
            # --- CHECK PARTIAL TP AT 1:1 RR ---
            if not self.partial_tp_taken and high >= self.take_profit_1:
                # Close 50% at 1:1 RR
                partial_vol = self.volume / 2
                self.partial_tp_taken = True
                self.partial_volume = partial_vol
                self.partial_profit = (self.take_profit_1 - self.entry_price) * partial_vol * 100

                # Move SL to breakeven (or slightly above for slippage)
                self.volume -= partial_vol  # Remaining volume for second half
                self.stop_loss = self.entry_price + (1 * pip_size)  # BE + 1 pip
                if is_gold:
                    self.stop_loss = round(self.stop_loss, 2)

            # --- CHECK FULL TP ---
            if high >= self.take_profit:
                self.exit_price = self.take_profit
                self.exit_time = current_time
                if self.partial_tp_taken:
                    self.exit_reason = 'FULL_TP'
                    # Remaining volume closes at full TP
                    self.profit = self.partial_profit + (self.take_profit - self.entry_price) * self.volume * 100
                else:
                    self.exit_reason = 'FULL_TP'
                    self.profit = (self.take_profit - self.entry_price) * (self.partial_volume + self.volume) * 100
                self.closed = True
                return True

            # Update highest price
            if high > self.highest_profit_price:
                self.highest_profit_price = high

            current_profit = self.highest_profit_price - self.entry_price

            # Move to breakeven after breakeven_distance (if not already at breakeven)
            if current_profit >= breakeven_distance and self.stop_loss < self.entry_price:
                be_sl = self.entry_price + (1 * pip_size)  # BE + 1 pip
                if is_gold:
                    be_sl = round(be_sl, 2)
                self.stop_loss = be_sl

            # Activate trailing for spike trades or after significant move
            if current_profit >= activation_distance:
                self.trailing_activated = True
                new_sl = self.highest_profit_price - trail_distance
                if is_gold:
                    new_sl = round(new_sl, 2)
                if new_sl > self.stop_loss:
                    self.stop_loss = new_sl

            # Time-based exit: cut stale trades
            max_candles = self.tf_max_candles if self.tf_max_candles > 0 else settings.RISK.get('max_candles_in_trade', 15)
            if max_candles and self.candle_count >= max_candles:
                mid_price = (high + low) / 2
                pnl = mid_price - self.entry_price
                if pnl < 5 * pip_size and not self.trailing_activated:
                    self.exit_price = mid_price
                    self.exit_time = current_time
                    if self.partial_tp_taken:
                        self.profit = self.partial_profit + (mid_price - self.entry_price) * self.volume * 100
                    else:
                        self.profit = pnl * (self.partial_volume + self.volume) * 100
                    self.exit_reason = 'TIME_EXIT'
                    self.closed = True
                    return True

            # Check SL
            if low <= self.stop_loss:
                self.exit_price = self.stop_loss
                self.exit_time = current_time
                pnl = self.stop_loss - self.entry_price
                if self.partial_tp_taken:
                    self.profit = self.partial_profit + pnl * self.volume * 100
                else:
                    self.profit = pnl * (self.partial_volume + self.volume) * 100

                if self.stop_loss > self.entry_price:
                    self.exit_reason = 'TRAILING_STOP' if self.trailing_activated else 'BREAKEVEN'
                elif self.stop_loss >= self.entry_price:
                    self.exit_reason = 'BREAKEVEN'
                    if self.partial_tp_taken:
                        self.profit = self.partial_profit
                else:
                    self.exit_reason = 'STOP_LOSS'
                self.closed = True
                return True

        else:  # SELL
            # --- CHECK PARTIAL TP AT 1:1 RR ---
            if not self.partial_tp_taken and low <= self.take_profit_1:
                # Close 50% at 1:1 RR
                partial_vol = self.volume / 2
                self.partial_tp_taken = True
                self.partial_volume = partial_vol
                self.partial_profit = (self.entry_price - self.take_profit_1) * partial_vol * 100

                # Move SL to breakeven
                self.volume -= partial_vol  # Remaining volume
                self.stop_loss = self.entry_price - (1 * pip_size)  # BE - 1 pip
                if is_gold:
                    self.stop_loss = round(self.stop_loss, 2)

            # --- CHECK FULL TP ---
            if low <= self.take_profit:
                self.exit_price = self.take_profit
                self.exit_time = current_time
                if self.partial_tp_taken:
                    self.exit_reason = 'FULL_TP'
                    self.profit = self.partial_profit + (self.entry_price - self.take_profit) * self.volume * 100
                else:
                    self.exit_reason = 'FULL_TP'
                    self.profit = (self.entry_price - self.take_profit) * (self.partial_volume + self.volume) * 100
                self.closed = True
                return True

            # Update lowest price
            if low < self.lowest_profit_price:
                self.lowest_profit_price = low

            current_profit = self.entry_price - self.lowest_profit_price

            # Move to breakeven
            if current_profit >= breakeven_distance and self.stop_loss > self.entry_price:
                be_sl = self.entry_price - (1 * pip_size)  # BE - 1 pip
                if is_gold:
                    be_sl = round(be_sl, 2)
                self.stop_loss = be_sl

            # Trailing for spike trades or significant moves
            if current_profit >= activation_distance:
                self.trailing_activated = True
                new_sl = self.lowest_profit_price + trail_distance
                if is_gold:
                    new_sl = round(new_sl, 2)
                if new_sl < self.stop_loss:
                    self.stop_loss = new_sl

            # Time-based exit
            max_candles = self.tf_max_candles if self.tf_max_candles > 0 else settings.RISK.get('max_candles_in_trade', 15)
            if max_candles and self.candle_count >= max_candles:
                mid_price = (high + low) / 2
                pnl = self.entry_price - mid_price
                if pnl < 5 * pip_size and not self.trailing_activated:
                    self.exit_price = mid_price
                    self.exit_time = current_time
                    if self.partial_tp_taken:
                        self.profit = self.partial_profit + pnl * self.volume * 100
                    else:
                        self.profit = pnl * (self.partial_volume + self.volume) * 100
                    self.exit_reason = 'TIME_EXIT'
                    self.closed = True
                    return True

            # Check SL
            if high >= self.stop_loss:
                self.exit_price = self.stop_loss
                self.exit_time = current_time
                pnl = self.entry_price - self.stop_loss
                if self.partial_tp_taken:
                    self.profit = self.partial_profit + pnl * self.volume * 100
                else:
                    self.profit = pnl * (self.partial_volume + self.volume) * 100

                if self.stop_loss < self.entry_price:
                    self.exit_reason = 'TRAILING_STOP' if self.trailing_activated else 'BREAKEVEN'
                elif self.stop_loss <= self.entry_price:
                    self.exit_reason = 'BREAKEVEN'
                    if self.partial_tp_taken:
                        self.profit = self.partial_profit
                else:
                    self.exit_reason = 'STOP_LOSS'
                self.closed = True
                return True

        return False

    def _calculate_profit(self):
        """
        Calculate profit/loss in dollars.
        Uses proper pip calculation based on symbol.
        """
        # Pip multipliers based on symbol
        if 'XAU' in self.symbol or 'GOLD' in self.symbol:
            pip_multiplier = 10  # Gold: 1 pip = 0.1
            pip_value_per_lot = 1  # $1 per pip per 0.01 lot
        elif 'JPY' in self.symbol:
            pip_multiplier = 100  # JPY pairs: 1 pip = 0.01
            pip_value_per_lot = 100  # $1 per pip per 0.01 lot
        else:
            pip_multiplier = 10000  # Standard forex: 1 pip = 0.0001
            pip_value_per_lot = 10  # $10 per pip per lot

        if self.direction == 'BUY':
            price_diff = self.exit_price - self.entry_price
        else:
            price_diff = self.entry_price - self.exit_price

        # Profit = price_diff * volume * pip_value_per_lot
        # Simplified: just use the actual price difference
        self.profit = price_diff * self.volume * 100  # Normalized profit

    def to_dict(self) -> Dict:
        """Convert trade to dictionary."""
        base = {
            'symbol': self.symbol,
            'direction': self.direction,
            'entry_price': self.entry_price,
            'entry_time': self.entry_time,
            'exit_price': self.exit_price,
            'exit_time': self.exit_time,
            'stop_loss': self.stop_loss,
            'original_sl': self.original_sl,
            'take_profit': self.take_profit,
            'original_tp': self.original_tp,
            'trailing_activated': self.trailing_activated,
            'volume': self.original_volume,
            'profit': self.profit,
            'partial_tp_taken': self.partial_tp_taken,
            'partial_volume': self.partial_volume,
            'partial_profit': self.partial_profit,
            'exit_reason': self.exit_reason,
        }

        for key, value in (self.features or {}).items():
            base[f'feat_{key}'] = value

        return base


class BacktestEngine:
    """
    Backtesting engine for AMD strategy.
    """

    def __init__(
        self,
        initial_balance: float = 10000,
        risk_percent: float = 1.0,
        commission_per_lot: float = 7.0
    ):
        """
        Initialize backtesting engine.

        Args:
            initial_balance: Starting account balance
            risk_percent: Risk per trade as percentage
            commission_per_lot: Commission per lot round trip
        """
        self.initial_balance = initial_balance
        self.risk_percent = risk_percent
        self.commission_per_lot = commission_per_lot

        self.strategy = GoldScalpStrategy()
        self.analyzer = AMDAnalyzer()

        # Self-learning brain integration
        self.brain: TradingBrain = get_brain()
        self.learn_from_backtest = True  # Enable brain learning from backtest trades

        # Results
        self.trades: List[BacktestTrade] = []
        self.balance_history: List[Tuple[datetime, float]] = []

    def _teach_brain_from_trade(self, trade: 'BacktestTrade'):
        """
        Teach the brain from a completed backtest trade.
        Feature keys MUST match brain.feature_weights keys exactly!
        """
        if not self.learn_from_backtest:
            return

        # Map trade features to brain feature_weights keys (MUST match exactly)
        raw = trade.features or {}
        brain_features = {
            'trend_aligned': bool(raw.get('trend_aligned', False)),
            'liquidity_sweep': bool(raw.get('liquidity_sweep', False)),
            'structure_shift': bool(raw.get('structure_shift', False)),
            'order_block': bool(raw.get('order_block', False)),
            'fvg': bool(raw.get('fvg', False)),
            'ema_aligned': bool(raw.get('ema_aligned', False)),
            'candle_pattern': bool(raw.get('candle_pattern', False)),
            'rsi_optimal': bool(raw.get('rsi_optimal', False)),
            'rsi_divergence': bool(raw.get('rsi_divergence', False)),
            'volume_spike': bool(raw.get('volume_spike', False)),
            'good_volatility': bool(raw.get('good_volatility', False)),
            'session_london': bool(raw.get('session_london', False)),
            'session_ny': bool(raw.get('session_ny', False)),
            'session_overlap': bool(raw.get('session_overlap', False)),
            'session_asian': bool(raw.get('session_asian', False)),
        }

        # Determine outcome
        outcome = 'win' if trade.profit > 0 else 'loss'

        # Record to brain
        trade_data = {
            'symbol': trade.symbol,
            'direction': trade.direction,
            'outcome': outcome,
            'features': brain_features,
            'entry_price': trade.entry_price,
            'exit_price': trade.exit_price or trade.entry_price,
            'stop_loss': trade.stop_loss,
            'take_profit': trade.take_profit,
            'profit': trade.profit,
            'exit_reason': trade.exit_reason,
        }
        self.brain.record_trade(trade_data)

    def run(
        self,
        data: pd.DataFrame,
        symbol: str = 'EURUSD'
    ) -> Dict:
        """
        Run backtest on historical data.

        Args:
            data: OHLCV DataFrame
            symbol: Trading symbol

        Returns:
            Dict with backtest results
        """
        if len(data) < 200:
            return {'error': 'Insufficient data for backtesting'}

        balance = self.initial_balance
        self.balance_history = [(data.index[0], balance)]
        self.trades = []

        active_trade: Optional[BacktestTrade] = None

        # Analyze all data first
        analyzed_data = self.analyzer.analyze(data)

        # Walk through data
        for i in range(100, len(data)):
            current = data.iloc[i]
            current_time = data.index[i]

            # Check if active trade should be closed
            if active_trade and not active_trade.closed:
                if active_trade.check_exit(current['high'], current['low'], current_time):
                    # Apply commission
                    commission = self.commission_per_lot * active_trade.original_volume
                    profit = active_trade.profit - commission

                    balance += profit
                    self.balance_history.append((current_time, balance))
                    self.trades.append(active_trade)
                    self._teach_brain_from_trade(active_trade)  # BRAIN LEARNS!
                    active_trade = None

            # Skip if we have an active trade
            if active_trade and not active_trade.closed:
                continue

            # Get data up to current point for analysis
            # Avoid per-iteration DataFrame copies for speed.
            lookback_data = analyzed_data.iloc[:i+1]

            # Check for signals
            last = lookback_data.iloc[-1]
            prev = lookback_data.iloc[-2]

            signal = None

            # Check for bullish setup
            if self._check_bullish_entry(lookback_data, last, prev, symbol):
                signal = {
                    'direction': 'BUY',
                    'entry_price': current['close'],
                    'atr': last.get('atr', 0.001)
                }
            # Check for bearish setup
            elif self._check_bearish_entry(lookback_data, last, prev, symbol):
                signal = {
                    'direction': 'SELL',
                    'entry_price': current['close'],
                    'atr': last.get('atr', 0.001)
                }

            if signal:
                # Calculate SL/TP
                atr = signal['atr']
                entry = signal['entry_price']

                if signal['direction'] == 'BUY':
                    sl = entry - (atr * settings.RISK['default_sl_atr_multiple'])
                else:
                    sl = entry + (atr * settings.RISK['default_sl_atr_multiple'])
                # FIXED PROFIT ONLY: TP is always 1:2 of SL distance
                risk_distance = abs(entry - sl)
                reward_distance = risk_distance * settings.RISK['min_risk_reward']
                tp = entry + reward_distance if signal['direction'] == 'BUY' else entry - reward_distance

                # Calculate position size (gold-aware)
                risk_amount = balance * (self.risk_percent / 100)
                if 'XAU' in symbol or 'GOLD' in symbol:
                    sl_pips = abs(entry - sl) / 0.10  # Gold: 1 pip = $0.10
                    pip_value_per_lot = 0.10
                elif 'JPY' in symbol:
                    sl_pips = abs(entry - sl) * 100
                    pip_value_per_lot = 1000
                else:
                    sl_pips = abs(entry - sl) * 10000
                    pip_value_per_lot = 10
                volume = risk_amount / (sl_pips * pip_value_per_lot) if sl_pips > 0 else 0.01
                volume = round(max(0.01, min(volume, 10)), 2)

                # Open trade
                # Capture entry-time features using rolling lookback (last 10 candles)
                # keys MUST match brain.feature_weights
                lb = 10
                recent = lookback_data.iloc[-lb:] if len(lookback_data) >= lb else lookback_data

                def _any_col(col):
                    return bool(recent[col].any()) if col in recent.columns else False

                if signal['direction'] == 'BUY':
                    _trend = bool(last.get('bullish_ema_stack', False) or last.get('above_all_ema', False))
                    _ema = _trend
                    _sweep = _any_col('bullish_manipulation')
                    _struct = _any_col('bullish_bos') or _any_col('bullish_choch')
                    _ob = _any_col('bullish_ob')
                    _fvg = _any_col('bullish_fvg')
                    _candle = _any_col('pin_bar_bullish') or _any_col('engulfing_bullish') or _any_col('hammer') or _any_col('morning_star')
                    _div = _any_col('bullish_divergence')
                else:
                    _trend = bool(last.get('bearish_ema_stack', False) or last.get('below_all_ema', False))
                    _ema = _trend
                    _sweep = _any_col('bearish_manipulation')
                    _struct = _any_col('bearish_bos') or _any_col('bearish_choch')
                    _ob = _any_col('bearish_ob')
                    _fvg = _any_col('bearish_fvg')
                    _candle = _any_col('pin_bar_bearish') or _any_col('engulfing_bearish') or _any_col('shooting_star') or _any_col('evening_star')
                    _div = _any_col('bearish_divergence')

                _hour = current_time.hour if hasattr(current_time, 'hour') else 12
                entry_features = {
                    'trend_aligned': _trend,
                    'ema_aligned': _ema,
                    'liquidity_sweep': _sweep,
                    'structure_shift': _struct,
                    'order_block': _ob,
                    'fvg': _fvg,
                    'candle_pattern': _candle,
                    'rsi_optimal': bool(25 < last.get('rsi', 50) < 75),
                    'rsi_divergence': _div,
                    'volume_spike': _any_col('volume_spike') or _any_col('volume_climax'),
                    'good_volatility': bool(last.get('good_volatility', False)),
                    'session_asian': bool(0 <= _hour < 7),
                    'session_london': bool(7 <= _hour < 16),
                    'session_ny': bool(12 <= _hour < 21),
                    'session_overlap': bool(12 <= _hour < 16),
                }

                active_trade = BacktestTrade(
                    symbol=symbol,
                    direction=signal['direction'],
                    entry_price=entry,
                    entry_time=current_time,
                    stop_loss=sl,
                    take_profit=tp,
                    volume=volume,
                    features=entry_features
                )
                active_trade.entry_atr = signal.get('atr', 0)

        # Close any remaining trade at end of data
        if active_trade and not active_trade.closed:
            active_trade.exit_price = data.iloc[-1]['close']
            active_trade.exit_time = data.index[-1]
            active_trade.exit_reason = 'End of Data'
            active_trade._calculate_profit()
            active_trade.closed = True

            commission = self.commission_per_lot * active_trade.original_volume
            balance += active_trade.profit - commission
            self.trades.append(active_trade)
            self._teach_brain_from_trade(active_trade)  # BRAIN LEARNS!

        return self._calculate_results(balance)

    def run_multi_timeframe(
        self,
        data_by_tf: Dict[str, pd.DataFrame],
        symbol: str = 'EURUSD',
        trend_tf: str = 'H4',
        setup_tf: str = 'H1',
        entry_tf: str = 'M15',
    ) -> Dict:
        """Run a multi-timeframe backtest.

        Design goal:
        - Trend filter on higher TF (default H4)
        - Setup confirmation on mid TF (default H1)
        - Entry timing on lower TF (default M15)

        This is a practical way to keep A+ strictness while still finding
        enough opportunities across pairs/timeframes.
        """

        if not isinstance(data_by_tf, dict):
            return {'error': 'data_by_tf must be a dict of timeframe -> DataFrame'}

        for tf in (trend_tf, setup_tf, entry_tf):
            if tf not in data_by_tf:
                return {'error': f'Missing timeframe {tf} in data_by_tf'}

        raw_trend = data_by_tf[trend_tf]
        raw_setup = data_by_tf[setup_tf]
        raw_entry = data_by_tf[entry_tf]

        if len(raw_entry) < 400 or len(raw_setup) < 200 or len(raw_trend) < 100:
            return {'error': 'Insufficient data for multi-timeframe backtesting'}

        def _is_true(val) -> bool:
            try:
                return bool(val) if pd.notna(val) else False
            except Exception:
                return False

        def _asof_join(base_df: pd.DataFrame, ctx_df: pd.DataFrame, cols: List[str], suffix: str) -> pd.DataFrame:
            ctx_cols = [c for c in cols if c in ctx_df.columns]
            if not ctx_cols:
                return base_df
            ctx = ctx_df[ctx_cols].copy()
            ctx.rename(columns={c: f"{c}{suffix}" for c in ctx_cols}, inplace=True)

            base_reset = base_df.reset_index().rename(columns={'index': 'time'})
            ctx_reset = ctx.reset_index().rename(columns={'index': 'time'})

            merged = pd.merge_asof(
                base_reset.sort_values('time'),
                ctx_reset.sort_values('time'),
                on='time',
                direction='backward',
            )
            merged.set_index('time', inplace=True)
            return merged

        balance = self.initial_balance
        self.trades = []

        entry_analyzed = self.analyzer.analyze(raw_entry)
        setup_analyzed = self.analyzer.analyze(raw_setup)
        trend_analyzed = self.analyzer.analyze(raw_trend)

        # Join trend context from H1 onto entry timeframe (M5)
        trend_cols = [
            'scalp_trend_bull', 'scalp_trend_bear',
            'scalp_bull_score', 'scalp_bear_score',
        ]
        setup_cols = []  # Not using setup rolling windows anymore

        merged = _asof_join(entry_analyzed, setup_analyzed, setup_cols, suffix=f'_{setup_tf.lower()}')
        merged = _asof_join(merged, trend_analyzed, trend_cols, suffix=f'_{trend_tf.lower()}')

        self.balance_history = [(merged.index[0], balance)]
        active_trades: List[BacktestTrade] = []  # Support multiple concurrent trades

        best_hours = None
        if isinstance(getattr(settings, 'PAIR_SESSION_FILTERS', None), dict):
            best_hours = settings.PAIR_SESSION_FILTERS.get(symbol, {}).get('best_hours')

        # Daily trade counter
        max_trades_per_day = settings.RISK.get('max_trades_per_day', 8)
        max_open_trades = settings.RISK.get('max_open_trades', 3)
        min_confluences = getattr(settings, 'SCALP', {}).get('min_confluences', 5)
        current_day = None
        day_trade_count = 0
        last_entry_time = None  # For cooldown tracking

        is_gold = 'XAU' in symbol or 'GOLD' in symbol
        pip_size = 0.10 if is_gold else 0.0001
        if 'JPY' in symbol:
            pip_size = 0.01

        start_idx = 120  # allow indicators to warm up
        for i in range(start_idx, len(merged)):
            current_time = merged.index[i]
            current = merged.iloc[i]

            # Reset daily trade counter
            trade_day = current_time.date()
            if trade_day != current_day:
                current_day = trade_day
                day_trade_count = 0

            # Exit management for ALL active trades
            for trade in active_trades[:]:  # iterate copy so we can remove
                if not trade.closed:
                    if trade.check_exit(float(current['high']), float(current['low']), current_time):
                        commission = self.commission_per_lot * trade.original_volume
                        profit = trade.profit - commission
                        balance += profit
                        self.balance_history.append((current_time, balance))
                        self.trades.append(trade)
                        self._teach_brain_from_trade(trade)
                        active_trades.remove(trade)

            # Skip new entries if max open trades reached
            if len(active_trades) >= max_open_trades:
                continue

            # Session filter - REMOVED: 24/7 trading enabled
            # Brain learns session performance via session features

            # Daily trade limit
            if day_trade_count >= max_trades_per_day:
                continue

            # ====================================================================
            # GOLD SCALPING ENTRY LOGIC - Using Confluence Scores
            # ====================================================================
            # Entry uses scalp_bull_score / scalp_bear_score from AMDAnalyzer
            # H1 trend context for confirmation
            # Spike detection for momentum entries
            # ====================================================================

            bull_score = 0
            bear_score = 0
            try:
                bull_score = int(current.get('scalp_bull_score', 0))
            except Exception:
                pass
            try:
                bear_score = int(current.get('scalp_bear_score', 0))
            except Exception:
                pass

            # H1 trend context (joined via asof)
            h1_trend_bull = _is_true(current.get(f'scalp_trend_bull_{trend_tf.lower()}', False))
            h1_trend_bear = _is_true(current.get(f'scalp_trend_bear_{trend_tf.lower()}', False))

            # H1 confluence score for quality filtering
            h1_bull_score = 0
            h1_bear_score = 0
            try:
                h1_bull_score = int(current.get(f'scalp_bull_score_{trend_tf.lower()}', 0))
            except Exception:
                pass
            try:
                h1_bear_score = int(current.get(f'scalp_bear_score_{trend_tf.lower()}', 0))
            except Exception:
                pass

            # Spike detection from M5 data
            spike_up = _is_true(current.get('spike_up', False))
            spike_down = _is_true(current.get('spike_down', False))
            # Trend alignment on entry TF (M5)
            entry_trend_bull = _is_true(current.get('scalp_trend_bull', False))
            entry_trend_bear = _is_true(current.get('scalp_trend_bear', False))

            signal = None
            is_spike_entry = False

            # --- MODE 1: SPIKE CATCH ---
            # Spike entries: immediate entry on strong move, tighter trailing
            if spike_up and bull_score >= 5:
                signal = {'direction': 'BUY', 'entry_price': float(current['close']),
                          'atr': float(current.get('atr', 0.001))}
                is_spike_entry = True
            elif spike_down and bear_score >= 5:
                signal = {'direction': 'SELL', 'entry_price': float(current['close']),
                          'atr': float(current.get('atr', 0.001))}
                is_spike_entry = True

            # --- MODE 2: TREND SCALP ---
            # H1 trend ALWAYS REQUIRED (no waiver)
            if signal is None:
                # BUY: M5 score + M5 trend + H1 trend
                if bull_score >= min_confluences and entry_trend_bull and h1_trend_bull:
                    signal = {'direction': 'BUY', 'entry_price': float(current['close']),
                              'atr': float(current.get('atr', 0.001))}

                # SELL: M5 score + M5 trend + H1 trend
                if signal is None and bear_score >= min_confluences and entry_trend_bear and h1_trend_bear:
                    signal = {'direction': 'SELL', 'entry_price': float(current['close']),
                              'atr': float(current.get('atr', 0.001))}

            if not signal:
                continue

            atr = signal['atr']
            entry = signal['entry_price']

            # SL/TP calculation
            sl_mult = 1.0 if is_spike_entry else settings.RISK['default_sl_atr_multiple']
            if signal['direction'] == 'BUY':
                sl = entry - (atr * sl_mult)
            else:
                sl = entry + (atr * sl_mult)

            risk_distance = abs(entry - sl)
            reward_distance = risk_distance * settings.RISK['min_risk_reward']
            tp = entry + reward_distance if signal['direction'] == 'BUY' else entry - reward_distance

            # Position sizing
            risk_amount = balance * (self.risk_percent / 100)
            sl_pips = risk_distance / pip_size
            # Gold: $10 per pip per standard lot (100 oz * $0.10)
            pip_value_per_lot = 10.0 if is_gold else (1000 if 'JPY' in symbol else 10)
            volume = risk_amount / (sl_pips * pip_value_per_lot) if sl_pips > 0 else 0.01
            volume = round(max(0.01, min(volume, settings.RISK.get('max_lot_size', 0.10))), 2)

            # Feature tracking - keys MUST match brain.feature_weights exactly
            # Use rolling lookback (last 10 candles) for event features
            rsi_val = current.get('rsi', 50)
            try:
                rsi_val = float(rsi_val)
            except Exception:
                rsi_val = 50
            volume_ok = _is_true(current.get('volume_spike', False))

            # Rolling lookback for event features
            lb = 10
            recent_slice = merged.iloc[max(0, i-lb):i+1]

            def _any_recent(col):
                return bool(recent_slice[col].any()) if col in recent_slice.columns else False

            direction = signal['direction']
            if direction == 'BUY':
                candle_ok = _any_recent('pin_bar_bullish') or _any_recent('engulfing_bullish') or _any_recent('hammer') or _any_recent('morning_star')
                struct_shift = _any_recent('bullish_bos') or _any_recent('bullish_choch')
                ob_ok = _any_recent('bullish_ob')
                fvg_ok = _any_recent('bullish_fvg')
                manip_ok = _any_recent('bullish_manipulation')
                div_ok = _any_recent('bullish_divergence')
                volume_ok = _any_recent('volume_spike')
            else:
                candle_ok = _any_recent('pin_bar_bearish') or _any_recent('engulfing_bearish') or _any_recent('shooting_star') or _any_recent('evening_star')
                struct_shift = _any_recent('bearish_bos') or _any_recent('bearish_choch')
                ob_ok = _any_recent('bearish_ob')
                fvg_ok = _any_recent('bearish_fvg')
                manip_ok = _any_recent('bearish_manipulation')
                div_ok = _any_recent('bearish_divergence')
                volume_ok = _any_recent('volume_spike')

            _hour = current_time.hour if hasattr(current_time, 'hour') else 12
            entry_features = {
                'trend_aligned': bool(h1_trend_bull if direction == 'BUY' else h1_trend_bear),
                'ema_aligned': bool(entry_trend_bull if direction == 'BUY' else entry_trend_bear),
                'liquidity_sweep': bool(manip_ok),
                'structure_shift': bool(struct_shift),
                'order_block': bool(ob_ok),
                'fvg': bool(fvg_ok),
                'candle_pattern': bool(candle_ok),
                'rsi_optimal': bool(25 < rsi_val < 75),
                'rsi_divergence': bool(div_ok),
                'volume_spike': bool(volume_ok),
                'good_volatility': _is_true(current.get('good_volatility', False)),
                'session_asian': bool(0 <= _hour < 7),
                'session_london': bool(7 <= _hour < 16),
                'session_ny': bool(12 <= _hour < 21),
                'session_overlap': bool(12 <= _hour < 16),
                'is_spike': is_spike_entry,
                'bull_score': bull_score,
                'bear_score': bear_score,
            }

            active_trade = BacktestTrade(
                symbol=symbol,
                direction=signal['direction'],
                entry_price=entry,
                entry_time=current_time,
                stop_loss=sl,
                take_profit=tp,
                volume=volume,
                features=entry_features,
            )
            active_trade.is_spike = is_spike_entry
            active_trade.entry_atr = atr

            # Set per-TF ATR-based trail settings from ENTRY_TIMEFRAMES config
            entry_tf_config = getattr(settings, 'ENTRY_TIMEFRAMES', {}).get(entry_tf, {})
            active_trade.trail_atr_mult = entry_tf_config.get('trail_atr_mult', 0)
            active_trade.breakeven_atr_mult = entry_tf_config.get('breakeven_atr_mult', 0)
            active_trade.activation_atr_mult = entry_tf_config.get('activation_atr_mult', 0)

            # Also support legacy fixed pip settings
            active_trade.tf_breakeven_pips = entry_tf_config.get('breakeven_pips', 0)
            active_trade.tf_activation_pips = entry_tf_config.get('activation_pips', 0)
            active_trade.tf_trail_pips = entry_tf_config.get('trail_pips', 0)
            active_trade.tf_max_candles = entry_tf_config.get('max_candles_in_trade', 0)

            active_trades.append(active_trade)
            last_entry_time = current_time
            day_trade_count += 1

        # Close any remaining trades at end of data
        for trade in active_trades:
            if not trade.closed:
                trade.exit_price = float(merged.iloc[-1]['close'])
                trade.exit_time = merged.index[-1]
                trade.exit_reason = 'End of Data'
                trade._calculate_profit()
                trade.closed = True

                commission = self.commission_per_lot * trade.original_volume
                balance += trade.profit - commission
                self.trades.append(trade)
                self._teach_brain_from_trade(trade)

        return self._calculate_results(balance)

    def _check_bullish_entry(
        self,
        df: pd.DataFrame,
        last: pd.Series,
        prev: pd.Series,
        symbol: str = 'EURUSD'
    ) -> bool:
        """BILLIONAIRE SNIPER - Bullish Entry (A/A+ only).

        Strict by-category confirmation to reduce overtrading.
        - A+ = 7/7 mandatory + >=2 bonuses
        - A  = 6/7 mandatory + >=1 bonus
        """
        lookback = min(10, len(df))
        recent = df.iloc[-lookback:]

        close = last.get('close', 0)
        open_price = last.get('open', 0)
        high = last.get('high', 0)
        low = last.get('low', 0)

        # ---------------- Session filter (pair best-hours) ----------------
        best_hours = settings.PAIR_SESSION_FILTERS.get(symbol, {}).get('best_hours') if isinstance(getattr(settings, 'PAIR_SESSION_FILTERS', None), dict) else None
        if best_hours and df.index[-1].hour not in best_hours:
            return False

        # ---------------- Hard Gates (must-have) ----------------
        liquidity_sweep = bool('bullish_manipulation' in recent.columns and recent['bullish_manipulation'].iloc[-10:].any())
        structure_shift = bool(last.get('bullish_bos', False) or last.get('bullish_choch', False) or prev.get('bullish_bos', False) or prev.get('bullish_choch', False))
        ema_ok = bool(last.get('bullish_ema_stack', False) or last.get('above_all_ema', False))
        if not (liquidity_sweep and structure_shift and ema_ok):
            return False

        # ---------------- Confluences (counted) ----------------
        liquidity_zone = bool('accumulation_zone' in recent.columns and recent['accumulation_zone'].iloc[-10:].any())
        order_block = bool('bullish_ob' in recent.columns and recent['bullish_ob'].iloc[-10:].any())
        fvg = bool('bullish_fvg' in recent.columns and recent['bullish_fvg'].iloc[-10:].any())
        smc_ok = bool(order_block or fvg)

        sniper_rsi_range = getattr(settings, 'SNIPER', {}).get('rsi_range', (35, 65))
        rsi = last.get('rsi', 50)
        rsi_ok = bool(sniper_rsi_range[0] < rsi < sniper_rsi_range[1])
        candle_pattern = bool(last.get('pin_bar_bullish', False) or last.get('engulfing_bullish', False) or last.get('morning_star', False))
        volume_ok = bool(last.get('volume_spike', False) or last.get('volume_climax', False))
        volatility_ok = bool(last.get('good_volatility', False))

        confluences = {
            'LiquidityZone': liquidity_zone,
            'SMC(OB/FVG)': smc_ok,
            'RSI_Optimal': rsi_ok,
            'CandlePattern': candle_pattern,
            'Volume': volume_ok,
            'GoodVolatility': volatility_ok,
        }

        hard_hits = 4  # Session + LiquiditySweep + StructureShift + EMA
        confluence_hits = [k for k, v in confluences.items() if v]
        total_hits = hard_hits + len(confluence_hits)
        bonus_count = sum(1 for k in ['CandlePattern', 'Volume', 'GoodVolatility'] if confluences.get(k, False))

        if total_hits >= 8 and bonus_count >= 2:
            return True
        if total_hits >= 7 and bonus_count >= 1:
            return True

        # Optional threshold mode
        if not getattr(settings, 'SNIPER', {}).get('perfect_entry_only', True):
            return total_hits >= getattr(settings, 'SNIPER', {}).get('min_confluences', 5)

        return False

    def _check_bearish_entry(
        self,
        df: pd.DataFrame,
        last: pd.Series,
        prev: pd.Series,
        symbol: str = 'EURUSD'
    ) -> bool:
        """BILLIONAIRE SNIPER - Bearish Entry (A/A+ only)."""
        lookback = min(10, len(df))
        recent = df.iloc[-lookback:]

        # Session filter (pair best-hours)
        best_hours = settings.PAIR_SESSION_FILTERS.get(symbol, {}).get('best_hours') if isinstance(getattr(settings, 'PAIR_SESSION_FILTERS', None), dict) else None
        if best_hours and df.index[-1].hour not in best_hours:
            return False

        # Hard gates
        liquidity_sweep = bool('bearish_manipulation' in recent.columns and recent['bearish_manipulation'].iloc[-10:].any())
        structure_shift = bool(last.get('bearish_bos', False) or last.get('bearish_choch', False) or prev.get('bearish_bos', False) or prev.get('bearish_choch', False))
        ema_ok = bool(last.get('bearish_ema_stack', False) or last.get('below_all_ema', False))
        if not (liquidity_sweep and structure_shift and ema_ok):
            return False

        # Confluences
        liquidity_zone = bool('accumulation_zone' in recent.columns and recent['accumulation_zone'].iloc[-10:].any())
        order_block = bool('bearish_ob' in recent.columns and recent['bearish_ob'].iloc[-10:].any())
        fvg = bool('bearish_fvg' in recent.columns and recent['bearish_fvg'].iloc[-10:].any())
        smc_ok = bool(order_block or fvg)

        sniper_rsi_range = getattr(settings, 'SNIPER', {}).get('rsi_range', (35, 65))
        rsi = last.get('rsi', 50)
        rsi_ok = bool(sniper_rsi_range[0] < rsi < sniper_rsi_range[1])
        candle_pattern = bool(last.get('pin_bar_bearish', False) or last.get('engulfing_bearish', False) or last.get('evening_star', False))
        volume_ok = bool(last.get('volume_spike', False) or last.get('volume_climax', False))
        volatility_ok = bool(last.get('good_volatility', False))

        confluences = {
            'LiquidityZone': liquidity_zone,
            'SMC(OB/FVG)': smc_ok,
            'RSI_Optimal': rsi_ok,
            'CandlePattern': candle_pattern,
            'Volume': volume_ok,
            'GoodVolatility': volatility_ok,
        }

        hard_hits = 4
        confluence_hits = [k for k, v in confluences.items() if v]
        total_hits = hard_hits + len(confluence_hits)
        bonus_count = sum(1 for k in ['CandlePattern', 'Volume', 'GoodVolatility'] if confluences.get(k, False))

        if total_hits >= 8 and bonus_count >= 2:
            return True
        if total_hits >= 7 and bonus_count >= 1:
            return True

        if not getattr(settings, 'SNIPER', {}).get('perfect_entry_only', True):
            return total_hits >= getattr(settings, 'SNIPER', {}).get('min_confluences', 5)

        return False

    def _calculate_results(self, final_balance: float) -> Dict:
        """
        Calculate backtest performance metrics.

        Args:
            final_balance: Final account balance

        Returns:
            Dict with performance metrics
        """
        if not self.trades:
            return {
                'total_trades': 0,
                'final_balance': final_balance,
                'return_pct': 0,
                'message': 'No trades executed'
            }

        # Basic stats
        total_trades = len(self.trades)
        winners = [t for t in self.trades if t.profit > 0]
        losers = [t for t in self.trades if t.profit <= 0]

        win_rate = len(winners) / total_trades * 100 if total_trades > 0 else 0

        # Profit stats
        gross_profit = sum(t.profit for t in winners)
        gross_loss = abs(sum(t.profit for t in losers))
        net_profit = final_balance - self.initial_balance
        return_pct = (net_profit / self.initial_balance) * 100

        # Average trade
        avg_win = gross_profit / len(winners) if winners else 0
        avg_loss = gross_loss / len(losers) if losers else 0

        # Average win AFTER partial TP (only counting full wins or partial+trailed)
        full_tp_trades = [t for t in winners if t.exit_reason == 'FULL_TP']
        partial_then_trailed = [t for t in winners if t.partial_tp_taken and t.exit_reason == 'TRAILING_STOP']
        avg_win_optimized = 0
        if full_tp_trades or partial_then_trailed:
            opt_wins = full_tp_trades + partial_then_trailed
            avg_win_optimized = sum(t.profit for t in opt_wins) / len(opt_wins) if opt_wins else avg_win

        # Profit factor
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')

        # Drawdown calculation
        max_balance = self.initial_balance
        max_drawdown = 0

        for _, balance in self.balance_history:
            if balance > max_balance:
                max_balance = balance
            drawdown = (max_balance - balance) / max_balance * 100
            if drawdown > max_drawdown:
                max_drawdown = drawdown

        # Trade breakdown by exit type (NEW: tracking all exit reasons)
        full_tp_exits = len([t for t in self.trades if t.exit_reason == 'FULL_TP'])
        partial_tp1_exits = len([t for t in self.trades if t.partial_tp_taken and t.exit_reason == 'PARTIAL_TP1'])
        partial_tp_then_trailed = len([t for t in self.trades if t.partial_tp_taken and t.exit_reason == 'TRAILING_STOP'])
        trailing_stop_exits = len([t for t in self.trades if t.exit_reason == 'TRAILING_STOP'])
        sl_exits = len([t for t in self.trades if t.exit_reason == 'STOP_LOSS'])
        breakeven_exits = len([t for t in self.trades if t.exit_reason == 'BREAKEVEN'])
        time_exits = len([t for t in self.trades if t.exit_reason == 'TIME_EXIT'])

        # Feature win rates (quick research aid)
        feature_stats: Dict[str, Dict[str, float]] = {}
        if self.trades:
            # Collect all feature keys present
            feature_keys = set()
            for t in self.trades:
                for k in (t.features or {}).keys():
                    feature_keys.add(k)

            for key in sorted(feature_keys):
                subset = [t for t in self.trades if (t.features or {}).get(key) is True]
                if not subset:
                    continue
                wins = len([t for t in subset if t.profit > 0])
                feature_stats[key] = {
                    'trades': len(subset),
                    'wins': wins,
                    'win_rate': round((wins / len(subset)) * 100, 2),
                }

        return {
            'initial_balance': self.initial_balance,
            'final_balance': round(final_balance, 2),
            'net_profit': round(net_profit, 2),
            'return_pct': round(return_pct, 2),
            'total_trades': total_trades,
            'winners': len(winners),
            'losers': len(losers),
            'win_rate': round(win_rate, 2),
            'gross_profit': round(gross_profit, 2),
            'gross_loss': round(gross_loss, 2),
            'profit_factor': round(profit_factor, 2),
            'avg_win': round(avg_win, 2),
            'avg_win_optimized': round(avg_win_optimized, 2),
            'avg_loss': round(avg_loss, 2),
            'max_drawdown': round(max_drawdown, 2),
            'full_tp_exits': full_tp_exits,
            'partial_tp1_exits': partial_tp1_exits,
            'partial_tp_then_trailed': partial_tp_then_trailed,
            'trailing_stop_exits': trailing_stop_exits,
            'sl_exits': sl_exits,
            'breakeven_exits': breakeven_exits,
            'time_exits': time_exits,
            'feature_stats': feature_stats,
        }

    def get_trades_df(self) -> pd.DataFrame:
        """Get trades as DataFrame."""
        return pd.DataFrame([t.to_dict() for t in self.trades])

    def print_results(self, results: Dict):
        """Pretty print backtest results."""
        print("\n" + "=" * 60)
        print("BACKTEST RESULTS")
        print("=" * 60)

        if 'message' in results:
            print(f"\n{results['message']}")
            print(f"Final Balance: ${results.get('final_balance', 0):,.2f}")
            print("=" * 60 + "\n")
            return

        print(f"\nInitial Balance:  ${results['initial_balance']:,.2f}")
        print(f"Final Balance:    ${results['final_balance']:,.2f}")
        print(f"Net Profit:       ${results['net_profit']:,.2f}")
        print(f"Return:           {results['return_pct']:.2f}%")
        print(f"\nTotal Trades:     {results['total_trades']}")
        print(f"Winners:          {results['winners']}")
        print(f"Losers:           {results['losers']}")
        print(f"Win Rate:         {results['win_rate']:.2f}%")
        print(f"\nProfit Factor:    {results['profit_factor']:.2f}")
        print(f"Avg Winner:       ${results['avg_win']:.2f}")
        print(f"Avg Winner (Opt): ${results.get('avg_win_optimized', 0):.2f}")
        print(f"Avg Loser:        ${results['avg_loss']:.2f}")
        print(f"Max Drawdown:     {results['max_drawdown']:.2f}%")
        print(f"\nExit Breakdown:")
        print(f"  Full TP (1:2):           {results['full_tp_exits']}")
        print(f"  Partial TP @ 1:1:        {results['partial_tp1_exits']}")
        print(f"  Partial TP then Trailed: {results['partial_tp_then_trailed']}")
        print(f"  Trailing Stop:           {results['trailing_stop_exits']}")
        print(f"  Stop Loss:               {results['sl_exits']}")
        print(f"  Breakeven:               {results['breakeven_exits']}")
        print(f"  Time Exit:               {results['time_exits']}")

        feature_stats = results.get('feature_stats', {})
        if feature_stats:
            # Print a compact feature leaderboard (min 3 trades)
            eligible = [(k, v) for k, v in feature_stats.items() if v.get('trades', 0) >= 3]
            eligible.sort(key=lambda kv: (kv[1].get('win_rate', 0), kv[1].get('trades', 0)), reverse=True)
            if eligible:
                print("\nFeature Win Rates (>=3 trades):")
                for k, v in eligible[:8]:
                    print(f"  - {k}: {v['win_rate']:.2f}% ({v['trades']} trades)")

        # Trade recorder stats (statistics only — no strategy influence)
        print("\n📊 TRADE RECORDER:")
        brain_perf = self.brain.recent_performance
        total_recorded = brain_perf.get('wins', 0) + brain_perf.get('losses', 0)
        print(f"   Trades Recorded: {total_recorded}")
        print(f"   Wins: {brain_perf.get('wins', 0)} | Losses: {brain_perf.get('losses', 0)}")
        if total_recorded > 0:
            brain_wr = brain_perf.get('wins', 0) / total_recorded * 100
            print(f"   Win Rate: {brain_wr:.1f}%")
        print(f"   Mode: PURE STRATEGY (no adaptive overrides)")

        print("=" * 60 + "\n")


def run_backtest_demo():
    """Run a demo backtest with simulated data."""
    print("AMD Strategy Backtest - Demo Mode")
    print("=" * 50)
    print("\nGenerating simulated price data...")

    # Generate realistic-looking price data
    np.random.seed(42)
    periods = 2000  # About 3 months of H1 data
    dates = pd.date_range(start='2025-01-01', periods=periods, freq='H')

    # Generate price with trends and ranges
    price = 1.1000
    prices = []

    for i in range(periods):
        # Add some trend and mean reversion
        trend = np.sin(i / 100) * 0.0002  # Long-term cycle
        noise = np.random.randn() * 0.0008  # Random walk
        reversion = (1.1000 - price) * 0.001  # Mean reversion

        price += trend + noise + reversion
        prices.append(price)

    df = pd.DataFrame({
        'open': prices,
        'high': [p + abs(np.random.exponential(0.0005)) for p in prices],
        'low': [p - abs(np.random.exponential(0.0005)) for p in prices],
        'close': [p + np.random.randn() * 0.0003 for p in prices],
        'volume': np.random.randint(1000, 10000, periods),
    }, index=dates)

    # Fix OHLC consistency
    df['high'] = df[['open', 'high', 'close']].max(axis=1)
    df['low'] = df[['open', 'low', 'close']].min(axis=1)

    print(f"Generated {len(df)} candles from {df.index[0]} to {df.index[-1]}")

    # Run backtest
    print("\nRunning backtest...")
    engine = BacktestEngine(
        initial_balance=10000,
        risk_percent=1.0,
        commission_per_lot=7.0
    )

    results = engine.run(df, symbol='EURUSD')
    engine.print_results(results)

    # Show some trades
    if engine.trades:
        print("\nSample Trades:")
        trades_df = engine.get_trades_df()
        print(trades_df.head(10).to_string())


if __name__ == "__main__":
    run_backtest_demo()
