"""
Risk Manager Module
====================
Handles position sizing, risk limits, and trade filters
for safe automated trading.
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, Optional, List, Tuple
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import settings

logger = logging.getLogger(__name__)


class RiskManager:
    """
    Manages trading risk including position sizing, drawdown limits,
    session filters, and circuit breakers for safe automated trading.
    """

    def __init__(self, account_balance: float = 10000.0):
        """
        Initialize Risk Manager.

        Args:
            account_balance: Starting account balance
        """
        self.initial_balance = account_balance
        self.current_balance = account_balance
        self.current_equity = account_balance

        self.risk_percent = settings.RISK['risk_percent']
        self.max_daily_drawdown = settings.RISK['max_daily_drawdown_percent']
        self.max_open_trades = settings.RISK['max_open_trades']
        self.min_risk_reward = settings.RISK['min_risk_reward']

        # Daily tracking
        self.daily_start_balance = account_balance
        self.daily_profit_loss = 0.0
        self.trades_today = 0
        self.last_reset_date = datetime.now().date()

        # Trade history for analysis
        self.trade_history: List[Dict] = []

        # Circuit breaker settings
        self.consecutive_losses = 0
        self.max_consecutive_losses = settings.RISK.get('max_consecutive_losses', 2)
        self.peak_equity = account_balance
        self.equity_drawdown_halt_pct = settings.RISK.get('equity_drawdown_halt_pct', 6)
        self.cooldown_until: Optional[datetime] = None
        self.cooldown_duration_hours = settings.RISK.get('cooldown_duration_hours', 1)

        # Track recent results for position sizing adjustment
        self.recent_trade_results: List[bool] = []  # True = win, False = loss

        # Weekly loss tracking (higher limit for 20+ trades/day strategy)
        self.weekly_losses = 0
        self.max_weekly_losses = 15  # 15 losses/week max (volume trading has more trades = more losses are normal)
        self.week_start_date = datetime.now().date()

        # Per-symbol trade tracking (for market rotation enforcement)
        self.symbol_trades_today: Dict[str, int] = {}
        self.max_trades_per_symbol = settings.RISK.get('max_trades_per_symbol_per_day', 3)
    
    def update_account(self, balance: float, equity: float):
        """
        Update current account state.
        
        Args:
            balance: Current account balance
            equity: Current account equity
        """
        # Reset daily tracking if new day
        if datetime.now().date() != self.last_reset_date:
            self._reset_daily_stats()
        
        self.current_balance = balance
        self.current_equity = equity
        self.daily_profit_loss = equity - self.daily_start_balance
    
    def _reset_daily_stats(self):
        """Reset daily statistics at start of new trading day."""
        self.daily_start_balance = self.current_balance
        self.daily_profit_loss = 0.0
        self.trades_today = 0
        self.symbol_trades_today = {}  # Reset per-symbol counters
        self.last_reset_date = datetime.now().date()
        logger.info("Daily statistics reset — all symbol trade counters cleared")

    def can_trade_symbol(self, symbol: str) -> bool:
        """Check if we can still trade this symbol today (market rotation enforcement)."""
        count = self.symbol_trades_today.get(symbol, 0)
        if count >= self.max_trades_per_symbol:
            logger.info(f"Symbol {symbol} reached daily limit ({count}/{self.max_trades_per_symbol}) — rotate to other markets")
            return False
        return True

    def record_symbol_trade(self, symbol: str):
        """Record a trade on this symbol for rotation tracking."""
        self.symbol_trades_today[symbol] = self.symbol_trades_today.get(symbol, 0) + 1
        logger.info(f"Symbol {symbol} trade count: {self.symbol_trades_today[symbol]}/{self.max_trades_per_symbol}")

    def record_trade_result(self, is_win: bool, profit: float):
        """
        Record trade result and update circuit breaker state.

        Args:
            is_win: True if trade was profitable, False if loss
            profit: Profit/loss amount from the trade
        """
        # Weekly loss tracking
        today = datetime.now().date()
        if (today - self.week_start_date).days >= 7:
            self.weekly_losses = 0
            self.week_start_date = today

        if is_win:
            # Win: reset consecutive losses and update peak equity
            self.consecutive_losses = 0
            self.recent_trade_results.append(True)
            if self.current_equity > self.peak_equity:
                self.peak_equity = self.current_equity
            logger.info(f"Trade win recorded. Consecutive losses reset to 0")
        else:
            # Loss: increment consecutive losses counter
            self.consecutive_losses += 1
            self.weekly_losses += 1
            self.recent_trade_results.append(False)
            logger.warning(f"Trade loss recorded. Consecutive losses: {self.consecutive_losses}/{self.max_consecutive_losses} | Weekly: {self.weekly_losses}/{self.max_weekly_losses}")

            # Check if circuit breaker triggered (2 consecutive losses = STOP)
            if self.consecutive_losses >= self.max_consecutive_losses:
                self.cooldown_until = datetime.now() + timedelta(hours=self.cooldown_duration_hours)
                logger.critical(
                    f"CIRCUIT BREAKER TRIGGERED: {self.consecutive_losses} consecutive losses. "
                    f"Trading halted for {self.cooldown_duration_hours} hours until {self.cooldown_until}"
                )

            # Weekly loss limit
            if self.weekly_losses >= self.max_weekly_losses:
                # Halt until next week
                days_until_monday = (7 - today.weekday()) % 7
                if days_until_monday == 0:
                    days_until_monday = 7
                self.cooldown_until = datetime.now() + timedelta(days=days_until_monday)
                logger.critical(
                    f"WEEKLY LOSS LIMIT HIT: {self.weekly_losses} losses this week. "
                    f"Trading halted until next Monday."
                )

        # Keep only last 10 trades for position sizing decisions
        if len(self.recent_trade_results) > 10:
            self.recent_trade_results.pop(0)
    
    def can_trade(self) -> Dict:
        """
        Check if trading is allowed based on risk rules.

        Returns:
            Dict with 'allowed' boolean and 'reason' if not allowed
        """
        # Reset daily stats if new day
        if datetime.now().date() != self.last_reset_date:
            self._reset_daily_stats()

        # Check consecutive losses circuit breaker
        if self.consecutive_losses >= self.max_consecutive_losses:
            return {
                'allowed': False,
                'reason': f'Circuit breaker triggered: {self.consecutive_losses} consecutive losses'
            }

        # Check cooldown timer
        if self.cooldown_until and datetime.now() < self.cooldown_until:
            time_remaining = (self.cooldown_until - datetime.now()).total_seconds() / 60
            return {
                'allowed': False,
                'reason': f'Trading cooldown active. Resume in {time_remaining:.1f} minutes'
            }
        elif self.cooldown_until and datetime.now() >= self.cooldown_until:
            # Cooldown expired, reset
            self.cooldown_until = None
            self.consecutive_losses = 0
            logger.info("Cooldown period expired. Circuit breaker reset.")

        # Check equity drawdown halt
        if self.peak_equity > 0:
            equity_drawdown_pct = ((self.peak_equity - self.current_equity) / self.peak_equity) * 100
            if equity_drawdown_pct > self.equity_drawdown_halt_pct:
                return {
                    'allowed': False,
                    'reason': f'Equity drawdown halt triggered: {equity_drawdown_pct:.2f}% (max: {self.equity_drawdown_halt_pct}%)'
                }

        # Check max trades per day (scalping limit)
        max_trades = settings.RISK.get('max_trades_per_day', 8)
        if self.trades_today >= max_trades:
            return {
                'allowed': False,
                'reason': f'Max daily trades reached: {self.trades_today}/{max_trades}'
            }

        # Check daily drawdown limit
        daily_dd_percent = (self.daily_profit_loss / self.daily_start_balance) * 100

        if daily_dd_percent <= -self.max_daily_drawdown:
            return {
                'allowed': False,
                'reason': f'Daily drawdown limit reached: {daily_dd_percent:.2f}%'
            }

        # Session filter - London + NY only for gold scalping
        if settings.SESSIONS.get('avoid_asian', True):
            current_hour = datetime.utcnow().hour
            if not self._in_trading_session(current_hour):
                return {
                    'allowed': False,
                    'reason': 'Outside London/NY session'
                }

        return {'allowed': True, 'reason': None}
    
    def _in_trading_session(self, hour_utc: int) -> bool:
        """
        Check if current time is within trading session.
        
        Args:
            hour_utc: Current hour in UTC
            
        Returns:
            True if in trading session
        """
        london_open = settings.SESSIONS.get('london_open', 8)
        london_close = settings.SESSIONS.get('london_close', 16)
        ny_open = settings.SESSIONS.get('ny_open', 13)
        ny_close = settings.SESSIONS.get('ny_close', 21)
        
        in_london = london_open <= hour_utc < london_close
        in_ny = ny_open <= hour_utc < ny_close
        
        if settings.SESSIONS.get('trade_overlap', True):
            # London-NY overlap (13:00 - 16:00 UTC)
            in_overlap = (ny_open <= hour_utc < london_close)
            return in_london or in_ny or in_overlap
        
        if settings.SESSIONS.get('trade_london', True) and in_london:
            return True
        if settings.SESSIONS.get('trade_ny', True) and in_ny:
            return True
        
        return False
    
    def calculate_position_size(
        self,
        symbol_info: Dict,
        stop_loss_pips: float = 0,
        account_currency: str = 'USD',
        symbol: str = None,
        entry_price: float = None,
        stop_loss: float = None,
    ) -> float:
        """
        Calculate optimal position size based on risk parameters.
        Optimized for 50,000 INR (~$600 USD) account.
        Implements anti-martingale strategy: reduce size after loss, normal after 2 wins.

        Args:
            symbol_info: Symbol information from MT5
            stop_loss_pips: Distance to stop loss in pips (if provided directly)
            account_currency: Account currency
            symbol: Symbol name (optional, used to derive stop_loss_pips)
            entry_price: Entry price (optional, used with stop_loss to derive pips)
            stop_loss: Stop loss price (optional, used with entry_price to derive pips)

        Returns:
            Position size in lots
        """
        # If stop_loss_pips not provided, calculate from entry_price and stop_loss
        if stop_loss_pips <= 0 and entry_price and stop_loss:
            sym = symbol or symbol_info.get('symbol', '')
            pip_size = 0.01 if 'JPY' in sym else 0.0001
            if 'XAU' in sym or 'GOLD' in sym:
                pip_size = 0.1  # Gold pip = $0.10
            elif 'XAG' in sym or 'SILVER' in sym:
                pip_size = 0.01
            stop_loss_pips = abs(entry_price - stop_loss) / pip_size

        # ALWAYS enforce minimum stop distance to avoid broker "Invalid stops" errors
        # This applies whether stop_loss_pips was passed directly or calculated above
        sym = symbol or symbol_info.get('symbol', '')
        if 'XAU' in sym or 'GOLD' in sym:
            min_sl_pips = 50  # Gold: minimum 50 pips ($5.00)
        elif 'XAG' in sym or 'SILVER' in sym:
            min_sl_pips = 30  # Silver: minimum 30 pips
        elif 'JPY' in sym:
            min_sl_pips = 10  # JPY pairs: minimum 10 pips
        elif 'BTC' in sym:
            min_sl_pips = 100  # BTCUSD: minimum 100 pips ($100)
        elif 'ETH' in sym:
            min_sl_pips = 50   # ETHUSD: minimum 50 pips ($5)
        else:
            min_sl_pips = 5   # Standard forex: minimum 5 pips
        if 0 < stop_loss_pips < min_sl_pips:
            logger.warning(f"Stop loss {stop_loss_pips:.1f} pips below minimum {min_sl_pips} for {sym}, adjusting up")
            stop_loss_pips = min_sl_pips

        if stop_loss_pips <= 0:
            logger.error("Invalid stop loss distance")
            return 0.0

        # Calculate risk amount in account currency
        risk_amount = self.current_balance * (self.risk_percent / 100)

        # Get pip value (approximate)
        pip_value = symbol_info.get('pip_value', 0.0001)
        contract_size = symbol_info.get('contract_size', 100000)

        # For most forex pairs, 1 pip = $10 per standard lot
        # This is a simplified calculation - actual pip value varies by pair
        symbol = symbol_info.get('symbol', '')

        if 'JPY' in symbol:
            pip_value_per_lot = 1000  # Approximate for JPY pairs
        elif 'XAU' in symbol or 'GOLD' in symbol:
            pip_value_per_lot = 10  # Gold: 1 pip ($0.10) x 100oz = $10 per standard lot
        else:
            pip_value_per_lot = 10  # Standard forex pairs

        # Calculate position size
        # Position = Risk Amount / (Stop Loss in Pips * Pip Value per Lot)
        position_size = risk_amount / (stop_loss_pips * pip_value_per_lot)

        # Anti-martingale for volume trading (less aggressive — some losses are normal)
        if len(self.recent_trade_results) > 0:
            # If last 2 trades were losses, reduce by 25%
            if (len(self.recent_trade_results) >= 2
                    and not self.recent_trade_results[-1]
                    and not self.recent_trade_results[-2]):
                position_size *= 0.75
                logger.info("Position size reduced by 25% after 2 consecutive losses (anti-martingale)")
            # If last 3+ trades were losses, reduce to minimum
            if (len(self.recent_trade_results) >= 3
                    and not self.recent_trade_results[-1]
                    and not self.recent_trade_results[-2]
                    and not self.recent_trade_results[-3]):
                position_size = settings.RISK.get('min_lot_size', 0.01)
                logger.warning("Position size set to MINIMUM after 3 consecutive losses")
            # If last 2 trades were wins, allow normal sizing
            elif (len(self.recent_trade_results) >= 2
                    and self.recent_trade_results[-2]
                    and self.recent_trade_results[-1]):
                logger.info("Position size normal after 2 consecutive wins")

        # Round to lot step and ensure within limits
        min_lot = symbol_info.get('min_lot', 0.01)
        max_lot = symbol_info.get('max_lot', 100)
        lot_step = symbol_info.get('lot_step', 0.01)

        # Cap position size for smaller accounts (50,000 INR / $600)
        # Max 0.10 lots for gold scalping to preserve capital
        max_lot_for_account = settings.RISK.get('max_lot_size', 0.10)
        max_lot = min(max_lot, max_lot_for_account)

        # Round to nearest lot step
        position_size = round(position_size / lot_step) * lot_step

        # Clamp to limits
        position_size = max(min_lot, min(position_size, max_lot))

        logger.info(
            f"Position size calculated: {position_size:.2f} lots "
            f"(Risk: ${risk_amount:.2f}, SL: {stop_loss_pips} pips)"
        )

        return position_size
    
    def calculate_stop_loss(
        self,
        entry_price: float,
        atr: float,
        trade_type: str,
        manipulation_level: Optional[float] = None
    ) -> float:
        """
        Calculate stop loss price.

        Args:
            entry_price: Trade entry price
            atr: Current ATR value
            trade_type: 'BUY' or 'SELL'
            manipulation_level: Optional manipulation wick level

        Returns:
            Stop loss price
        """
        sl_distance = atr * settings.RISK['default_sl_atr_multiple']

        if trade_type == 'BUY':
            if manipulation_level:
                # Place SL below manipulation low with buffer
                sl = manipulation_level - (atr * 0.5)
            else:
                sl = entry_price - sl_distance
        else:  # SELL
            if manipulation_level:
                # Place SL above manipulation high with buffer
                sl = manipulation_level + (atr * 0.5)
            else:
                sl = entry_price + sl_distance

        return round(sl, 5)
    
    def calculate_take_profit(
        self,
        entry_price: float,
        stop_loss: float,
        trade_type: str,
        atr: float
    ) -> float:
        """
        Calculate take profit price based on risk-reward ratio.

        Args:
            entry_price: Trade entry price
            stop_loss: Stop loss price
            trade_type: 'BUY' or 'SELL'
            atr: Current ATR value

        Returns:
            Take profit price
        """
        risk_distance = abs(entry_price - stop_loss)
        reward_distance = risk_distance * self.min_risk_reward

        if trade_type == 'BUY':
            tp = entry_price + reward_distance
        else:  # SELL
            tp = entry_price - reward_distance

        return round(tp, 5)
    
    def validate_trade(
        self,
        entry_price: float,
        stop_loss: float,
        take_profit: float,
        trade_type: str
    ) -> Dict:
        """
        Validate if a trade meets risk requirements.

        Args:
            entry_price: Proposed entry price
            stop_loss: Proposed stop loss
            take_profit: Proposed take profit
            trade_type: 'BUY' or 'SELL'

        Returns:
            Dict with 'valid' boolean and details
        """
        # Check if we can trade
        can_trade_check = self.can_trade()
        if not can_trade_check['allowed']:
            return {'valid': False, 'reason': can_trade_check['reason']}

        # Calculate risk-reward ratio
        if trade_type == 'BUY':
            risk = entry_price - stop_loss
            reward = take_profit - entry_price
        else:
            risk = stop_loss - entry_price
            reward = entry_price - take_profit

        if risk <= 0:
            return {'valid': False, 'reason': 'Invalid stop loss position'}

        rr_ratio = reward / risk

        if rr_ratio < self.min_risk_reward:
            return {
                'valid': False,
                'reason': f'Risk-reward ratio too low: {rr_ratio:.2f} (min: {self.min_risk_reward})'
            }

        return {
            'valid': True,
            'risk_reward': rr_ratio,
            'risk_pips': risk * 10000 if risk < 1 else risk,  # Convert to pips
            'reward_pips': reward * 10000 if reward < 1 else reward,
        }
    
    def record_trade(
        self,
        symbol: str,
        trade_type: str,
        entry_price: float,
        volume: float,
        stop_loss: float,
        take_profit: float,
        ticket: int = 0
    ):
        """
        Record a trade for tracking.

        Args:
            symbol: Trading symbol
            trade_type: 'BUY' or 'SELL'
            entry_price: Entry price
            volume: Position size in lots
            stop_loss: Stop loss price
            take_profit: Take profit price
            ticket: MT5 ticket number
        """
        self.trades_today += 1

        trade = {
            'timestamp': datetime.now(),
            'symbol': symbol,
            'type': trade_type,
            'entry_price': entry_price,
            'volume': volume,
            'stop_loss': stop_loss,
            'take_profit': take_profit,
            'ticket': ticket,
            'status': 'OPEN',
        }

        self.trade_history.append(trade)
        logger.info(f"Trade recorded: {trade_type} {symbol} @ {entry_price}")
    
    def get_daily_stats(self) -> Dict:
        """
        Get daily trading statistics.

        Returns:
            Dict with daily stats
        """
        daily_dd_percent = (self.daily_profit_loss / self.daily_start_balance) * 100

        return {
            'date': self.last_reset_date.isoformat(),
            'start_balance': self.daily_start_balance,
            'current_equity': self.current_equity,
            'profit_loss': self.daily_profit_loss,
            'drawdown_percent': daily_dd_percent,
            'trades_today': self.trades_today,
            'max_allowed_dd': self.max_daily_drawdown,
            'can_trade': self.can_trade()['allowed'],
            'consecutive_losses': self.consecutive_losses,
            'peak_equity': self.peak_equity,
            'cooldown_until': self.cooldown_until.isoformat() if self.cooldown_until else None,
        }


class TradeFilter:
    """Additional trade filters for entry validation."""

    @staticmethod
    def check_spread(symbol_info: Dict, max_spread_pips: float = 10.0) -> bool:
        """
        Check if spread is acceptable.

        Args:
            symbol_info: Symbol information from MT5
            max_spread_pips: Maximum allowed spread in pips (10 for gold)

        Returns:
            True if spread is acceptable
        """
        spread = symbol_info.get('spread', 0)
        digits = symbol_info.get('digits', 5)

        # Convert spread points to pips
        # For forex (5/3 digits): 1 pip = 10 points
        # For gold/indices (2 digits): 1 pip = 10 points
        # Default: divide by 10 to convert points to pips
        spread_pips = spread / 10.0

        return spread_pips <= max_spread_pips

    @staticmethod
    def check_spread_vs_atr(symbol_info: Dict, atr: float, max_ratio: float = 0.3) -> bool:
        """
        Check if spread is reasonable relative to ATR (volatility).
        Prevents trading when spread is too expensive relative to the move.

        Args:
            symbol_info: Symbol information from MT5
            atr: Current ATR value
            max_ratio: Maximum acceptable ratio of spread to ATR (default 0.3 = 30%)

        Returns:
            True if spread is acceptable relative to ATR
        """
        if atr <= 0:
            logger.warning("Invalid ATR value for spread vs ATR check")
            return False

        spread = symbol_info.get('spread', 0)
        digits = symbol_info.get('digits', 5)

        # Convert spread points to pips
        spread_pips = spread / 10.0

        # Calculate spread to ATR ratio
        spread_to_atr_ratio = spread_pips / atr

        if spread_to_atr_ratio > max_ratio:
            logger.warning(
                f"Spread too expensive: {spread_to_atr_ratio:.2%} of ATR "
                f"(spread: {spread_pips} pips, ATR: {atr:.4f}, max: {max_ratio:.0%})"
            )
            return False

        return True

    @staticmethod
    def check_volatility(atr: float, min_atr: float = 0.0001, max_atr: float = 100.0) -> bool:
        """
        Check if volatility is within acceptable range.

        Args:
            atr: Current ATR value
            min_atr: Minimum ATR for trading (relaxed for all instruments)
            max_atr: Maximum ATR for trading (100 to support XAUUSD)

        Returns:
            True if volatility is acceptable
        """
        # Relaxed check - allow wide range for gold and forex
        return atr > min_atr

    @staticmethod
    def check_trending_market(adx_value: float, min_adx: float = 15) -> bool:
        """
        Check if market is trending (ADX above threshold).
        Prevents trading in ranging markets with low ADX.

        Args:
            adx_value: Current ADX value
            min_adx: Minimum ADX for trending market (default 15)

        Returns:
            True if market is trending, False if ranging
        """
        if adx_value < min_adx:
            logger.info(
                f"Market is ranging (ADX: {adx_value:.2f} < {min_adx}). "
                f"Skip this trade setup."
            )
            return False

        return True

    @staticmethod
    def check_correlation(
        open_positions: List[Dict],
        new_symbol: str,
        new_direction: str
    ) -> bool:
        """
        Check for correlated positions to avoid overexposure.

        Args:
            open_positions: List of open positions
            new_symbol: Symbol for new trade
            new_direction: Direction of new trade ('BUY' or 'SELL')

        Returns:
            True if trade is allowed (not too correlated)
        """
        # Define correlated pairs
        correlations = {
            'EURUSD': ['GBPUSD', 'AUDUSD'],
            'GBPUSD': ['EURUSD', 'AUDUSD'],
            'USDJPY': ['USDCHF', 'USDCAD'],
        }

        correlated = correlations.get(new_symbol, [])

        for pos in open_positions:
            if pos['symbol'] in correlated and pos['type'] == new_direction:
                return False

        return True


if __name__ == "__main__":
    # Test risk manager
    print("Risk Manager Module - Testing")
    print("=" * 50)
    
    rm = RiskManager(account_balance=10000)
    
    # Test can_trade
    print("\nCan Trade Check:")
    print(rm.can_trade())
    
    # Test position sizing
    symbol_info = {
        'symbol': 'EURUSD',
        'pip_value': 0.0001,
        'contract_size': 100000,
        'min_lot': 0.01,
        'max_lot': 100,
        'lot_step': 0.01,
    }
    
    position = rm.calculate_position_size(symbol_info, stop_loss_pips=30)
    print(f"\nPosition Size for 30 pip SL: {position} lots")
    
    # Test SL/TP calculation
    sl = rm.calculate_stop_loss(1.1000, 0.0015, 'BUY', 1.0980)
    tp = rm.calculate_take_profit(1.1000, sl, 'BUY', 0.0015)
    print(f"\nEntry: 1.1000, SL: {sl}, TP: {tp}")
    
    # Validate trade
    validation = rm.validate_trade(1.1000, sl, tp, 'BUY')
    print(f"\nTrade Validation: {validation}")
    
    # Daily stats
    print(f"\nDaily Stats: {rm.get_daily_stats()}")
