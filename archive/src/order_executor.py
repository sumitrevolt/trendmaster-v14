"""
Order Executor Module
======================
Handles trade execution, modification, and closure via MetaTrader 5.
"""

import MetaTrader5 as mt5
import logging
from typing import Dict, Optional, List
from datetime import datetime
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import settings

logger = logging.getLogger(__name__)


class OrderExecutor:
    """
    Executes and manages trading orders via MetaTrader 5.
    Enhanced with pre-flight validation and error recovery.
    """

    # Minimum stop loss distances per asset class (in price units, not pips)
    MIN_SL_DISTANCE = {
        'XAUUSD': 5.0,      # Gold: $5 minimum
        'XAGUSD': 0.30,     # Silver: $0.30 minimum
        'BTCUSD': 100.0,    # Bitcoin: $100 minimum
        'ETHUSD': 5.0,      # Ethereum: $5 minimum
    }
    # Defaults by category
    MIN_SL_DISTANCE_JPY = 0.15     # JPY pairs: 15 pips (increased — OctaFX requires wider stops)
    MIN_SL_DISTANCE_DEFAULT = 0.0010  # Standard forex: 10 pips (doubled — prevents "Invalid stops" on USDCHF etc.)

    def __init__(self):
        """Initialize order executor."""
        self.magic_number = settings.ORDER['magic_number']
        self.deviation = settings.ORDER['deviation']
        self.comment = settings.ORDER['comment']
        self.consecutive_failures = 0
        self.max_consecutive_failures = 5  # Pause after 5 consecutive execution failures

    def _get_min_sl_distance(self, symbol: str) -> float:
        """Get minimum stop loss distance in price units for a symbol.

        Dynamically queries MT5 trade_stops_level (in points) and converts
        to price units. Falls back to hardcoded minimums if MT5 query fails.
        """
        # Try to get broker's actual minimum stop level from MT5
        try:
            sym_info = mt5.symbol_info(symbol)
            if sym_info is not None and sym_info.trade_stops_level > 0:
                # trade_stops_level is in points; convert to price distance
                # Add 2-point buffer to avoid edge-case rejections
                broker_min = (sym_info.trade_stops_level + 2) * sym_info.point
                # Use the larger of broker minimum and our hardcoded minimum
                hardcoded_min = self.MIN_SL_DISTANCE.get(symbol,
                    self.MIN_SL_DISTANCE_JPY if 'JPY' in symbol else self.MIN_SL_DISTANCE_DEFAULT)
                return max(broker_min, hardcoded_min)
        except Exception:
            pass
        # Fallback to hardcoded minimums
        if symbol in self.MIN_SL_DISTANCE:
            return self.MIN_SL_DISTANCE[symbol]
        if 'JPY' in symbol:
            return self.MIN_SL_DISTANCE_JPY
        return self.MIN_SL_DISTANCE_DEFAULT

    def _preflight_check(self, symbol: str, volume: float, stop_loss: float,
                          take_profit: float, price: float, order_type: str) -> Optional[Dict]:
        """
        Pre-flight validation before sending order to MT5.
        Returns None if all checks pass, or error dict if validation fails.
        """
        # 1. Check for execution circuit breaker
        if self.consecutive_failures >= self.max_consecutive_failures:
            return {
                'success': False,
                'error': f'Execution paused: {self.consecutive_failures} consecutive failures. '
                         f'Needs manual restart or wait for reset.'
            }

        # 2. Check account balance/margin
        account_info = mt5.account_info()
        if account_info is None:
            return {'success': False, 'error': 'Cannot get account info — MT5 disconnected'}

        if account_info.balance <= 0:
            return {'success': False, 'error': f'Account balance depleted: ${account_info.balance:.2f}'}

        # Rough margin check: free margin must be > 0
        if account_info.margin_free is not None and account_info.margin_free <= 0:
            return {'success': False, 'error': f'No free margin: ${account_info.margin_free:.2f}'}

        # 3. Validate stop loss distance meets broker minimums
        sl_distance = abs(price - stop_loss)
        min_sl = self._get_min_sl_distance(symbol)
        if sl_distance < min_sl:
            return {
                'success': False,
                'error': f'SL too tight for {symbol}: {sl_distance:.5f} < min {min_sl:.5f}'
            }

        # 4. Validate TP is on correct side
        if order_type.upper() == 'BUY':
            if take_profit <= price:
                return {'success': False, 'error': f'TP below entry for BUY: TP={take_profit}, Entry={price}'}
            if stop_loss >= price:
                return {'success': False, 'error': f'SL above entry for BUY: SL={stop_loss}, Entry={price}'}
        else:
            if take_profit >= price:
                return {'success': False, 'error': f'TP above entry for SELL: TP={take_profit}, Entry={price}'}
            if stop_loss <= price:
                return {'success': False, 'error': f'SL below entry for SELL: SL={stop_loss}, Entry={price}'}

        # 5. Sanity check on volume
        if volume <= 0 or volume > 10:
            return {'success': False, 'error': f'Invalid volume: {volume}'}

        return None  # All checks passed
    
    def _get_filling_mode(self, symbol_info) -> int:
        """
        Get the supported filling mode for a symbol.
        
        Args:
            symbol_info: MT5 symbol info object
            
        Returns:
            Appropriate filling mode constant
        """
        filling_mode = symbol_info.filling_mode
        
        # Filling mode flags: FOK=1, IOC=2, RETURN=0
        # Check supported modes (bit flags)
        if filling_mode & 1:  # FOK supported
            return mt5.ORDER_FILLING_FOK
        elif filling_mode & 2:  # IOC supported
            return mt5.ORDER_FILLING_IOC
        else:
            # Return mode (partial fills) - usually supported
            return mt5.ORDER_FILLING_RETURN
    
    def place_market_order(
        self,
        symbol: str,
        order_type: str,
        volume: float,
        stop_loss: float,
        take_profit: float,
        comment: str = None
    ) -> Dict:
        """
        Place a market order.
        
        Args:
            symbol: Trading symbol
            order_type: 'BUY' or 'SELL'
            volume: Position size in lots
            stop_loss: Stop loss price
            take_profit: Take profit price
            comment: Optional order comment
            
        Returns:
            Dict with order result
        """
        # Get symbol info
        symbol_info = mt5.symbol_info(symbol)
        if symbol_info is None:
            return {'success': False, 'error': f'Symbol {symbol} not found'}
        
        if not symbol_info.visible:
            if not mt5.symbol_select(symbol, True):
                return {'success': False, 'error': f'Failed to select symbol {symbol}'}
        
        # Get current price
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            return {'success': False, 'error': 'Failed to get current price'}

        # Prepare order request
        if order_type.upper() == 'BUY':
            price = tick.ask
            mt5_order_type = mt5.ORDER_TYPE_BUY
        else:
            price = tick.bid
            mt5_order_type = mt5.ORDER_TYPE_SELL

        # Round prices to symbol digits
        digits = symbol_info.digits
        price = round(price, digits)
        stop_loss = round(stop_loss, digits)
        take_profit = round(take_profit, digits)

        # === AUTO-ADJUST SL IF TOO TIGHT ===
        # Instead of rejecting, widen the SL to broker minimum + buffer
        min_sl_dist = self._get_min_sl_distance(symbol)
        sl_distance = abs(price - stop_loss)
        if sl_distance < min_sl_dist and sl_distance > 0:
            if order_type.upper() == 'BUY':
                stop_loss = round(price - min_sl_dist, digits)
                # Also widen TP proportionally to maintain risk/reward ratio
                old_rr = abs(take_profit - price) / sl_distance if sl_distance > 0 else 2.0
                take_profit = round(price + min_sl_dist * old_rr, digits)
            else:
                stop_loss = round(price + min_sl_dist, digits)
                old_rr = abs(price - take_profit) / sl_distance if sl_distance > 0 else 2.0
                take_profit = round(price - min_sl_dist * old_rr, digits)
            logger.info(f"Auto-adjusted {symbol} SL from {sl_distance:.{digits}f} to {min_sl_dist:.{digits}f} "
                        f"(broker minimum). New SL={stop_loss}, TP={take_profit}")

        # === PRE-FLIGHT VALIDATION ===
        preflight_error = self._preflight_check(symbol, volume, stop_loss, take_profit, price, order_type)
        if preflight_error is not None:
            logger.warning(f"Pre-flight rejected {order_type} {symbol}: {preflight_error['error']}")
            return preflight_error

        # Get supported filling mode
        filling_mode = self._get_filling_mode(symbol_info)

        # Prepare request
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": volume,
            "type": mt5_order_type,
            "price": price,
            "sl": stop_loss,
            "tp": take_profit,
            "deviation": self.deviation,
            "magic": self.magic_number,
            "comment": comment or self.comment,
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": filling_mode,
        }

        # Send order
        result = mt5.order_send(request)

        if result is None:
            error = mt5.last_error()
            self.consecutive_failures += 1
            logger.error(f"Order send failed ({self.consecutive_failures} consecutive): {error}")
            return {'success': False, 'error': f'Order send failed: {error}'}

        if result.retcode != mt5.TRADE_RETCODE_DONE:
            self.consecutive_failures += 1
            error_msg = result.comment

            # === ERROR RECOVERY: retry with reduced volume on "No money" ===
            if 'No money' in error_msg and volume > 0.01:
                reduced_volume = max(0.01, round(volume * 0.5, 2))
                logger.warning(
                    f"'No money' on {symbol} with {volume} lots — retrying with {reduced_volume} lots"
                )
                request['volume'] = reduced_volume
                result = mt5.order_send(request)
                if result and result.retcode == mt5.TRADE_RETCODE_DONE:
                    self.consecutive_failures = 0  # Reset on success
                    logger.info(
                        f"Recovery order placed: {order_type} {reduced_volume} {symbol} @ {price} "
                        f"SL: {stop_loss} TP: {take_profit} Ticket: {result.order}"
                    )
                    return {
                        'success': True,
                        'ticket': result.order,
                        'price': result.price,
                        'volume': result.volume,
                        'symbol': symbol,
                        'type': order_type,
                        'sl': stop_loss,
                        'tp': take_profit,
                        'recovered': True,
                    }

            logger.error(
                f"Order failed ({self.consecutive_failures} consecutive): {error_msg} "
                f"[{order_type} {volume} {symbol}]"
            )
            return {
                'success': False,
                'error': f'Order failed: {error_msg}',
                'retcode': result.retcode
            }

        # Success — reset failure counter
        self.consecutive_failures = 0

        logger.info(
            f"Order placed: {order_type} {volume} {symbol} @ {price} "
            f"SL: {stop_loss} TP: {take_profit} Ticket: {result.order}"
        )

        return {
            'success': True,
            'ticket': result.order,
            'price': result.price,
            'volume': result.volume,
            'symbol': symbol,
            'type': order_type,
            'sl': stop_loss,
            'tp': take_profit,
        }
    
    def place_pending_order(
        self,
        symbol: str,
        order_type: str,
        volume: float,
        entry_price: float,
        stop_loss: float,
        take_profit: float,
        comment: str = None
    ) -> Dict:
        """
        Place a pending order (limit or stop).
        
        Args:
            symbol: Trading symbol
            order_type: 'BUY_LIMIT', 'SELL_LIMIT', 'BUY_STOP', 'SELL_STOP'
            volume: Position size in lots
            entry_price: Desired entry price
            stop_loss: Stop loss price
            take_profit: Take profit price
            comment: Optional order comment
            
        Returns:
            Dict with order result
        """
        symbol_info = mt5.symbol_info(symbol)
        if symbol_info is None:
            return {'success': False, 'error': f'Symbol {symbol} not found'}
        
        # Map order types
        order_type_map = {
            'BUY_LIMIT': mt5.ORDER_TYPE_BUY_LIMIT,
            'SELL_LIMIT': mt5.ORDER_TYPE_SELL_LIMIT,
            'BUY_STOP': mt5.ORDER_TYPE_BUY_STOP,
            'SELL_STOP': mt5.ORDER_TYPE_SELL_STOP,
        }
        
        mt5_order_type = order_type_map.get(order_type.upper())
        if mt5_order_type is None:
            return {'success': False, 'error': f'Invalid order type: {order_type}'}
        
        digits = symbol_info.digits
        filling_mode = self._get_filling_mode(symbol_info)
        
        request = {
            "action": mt5.TRADE_ACTION_PENDING,
            "symbol": symbol,
            "volume": volume,
            "type": mt5_order_type,
            "price": round(entry_price, digits),
            "sl": round(stop_loss, digits),
            "tp": round(take_profit, digits),
            "deviation": self.deviation,
            "magic": self.magic_number,
            "comment": comment or self.comment,
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": filling_mode,
        }
        
        result = mt5.order_send(request)
        
        if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
            error = result.comment if result else mt5.last_error()
            return {'success': False, 'error': f'Pending order failed: {error}'}
        
        logger.info(
            f"Pending order placed: {order_type} {volume} {symbol} @ {entry_price} "
            f"Ticket: {result.order}"
        )
        
        return {
            'success': True,
            'ticket': result.order,
            'price': entry_price,
            'volume': volume,
            'type': order_type,
        }
    
    def modify_position(
        self,
        ticket: int,
        new_sl: Optional[float] = None,
        new_tp: Optional[float] = None
    ) -> Dict:
        """
        Modify stop loss and/or take profit of an open position.
        
        Args:
            ticket: Position ticket number
            new_sl: New stop loss price (optional)
            new_tp: New take profit price (optional)
            
        Returns:
            Dict with modification result
        """
        # Get position info
        position = mt5.positions_get(ticket=ticket)
        if not position:
            return {'success': False, 'error': f'Position {ticket} not found'}
        
        pos = position[0]
        symbol_info = mt5.symbol_info(pos.symbol)
        digits = symbol_info.digits
        
        request = {
            "action": mt5.TRADE_ACTION_SLTP,
            "position": ticket,
            "symbol": pos.symbol,
            "sl": round(new_sl, digits) if new_sl else pos.sl,
            "tp": round(new_tp, digits) if new_tp else pos.tp,
        }
        
        result = mt5.order_send(request)
        
        if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
            error = result.comment if result else mt5.last_error()
            return {'success': False, 'error': f'Modification failed: {error}'}
        
        logger.info(f"Position {ticket} modified: SL={new_sl}, TP={new_tp}")
        
        return {'success': True, 'ticket': ticket, 'sl': new_sl, 'tp': new_tp}
    
    def close_position(
        self,
        ticket: int,
        partial_volume: Optional[float] = None
    ) -> Dict:
        """
        Close an open position (fully or partially).
        
        Args:
            ticket: Position ticket number
            partial_volume: Volume to close (optional, closes all if not specified)
            
        Returns:
            Dict with close result
        """
        # Get position info
        position = mt5.positions_get(ticket=ticket)
        if not position:
            return {'success': False, 'error': f'Position {ticket} not found'}
        
        pos = position[0]
        symbol_info = mt5.symbol_info(pos.symbol)
        
        # Get current price
        tick = mt5.symbol_info_tick(pos.symbol)
        
        # Determine close price and type
        if pos.type == mt5.ORDER_TYPE_BUY:
            price = tick.bid
            close_type = mt5.ORDER_TYPE_SELL
        else:
            price = tick.ask
            close_type = mt5.ORDER_TYPE_BUY
        
        volume = partial_volume if partial_volume else pos.volume
        
        # Get symbol info for filling mode
        symbol_info = mt5.symbol_info(pos.symbol)
        filling_mode = self._get_filling_mode(symbol_info) if symbol_info else mt5.ORDER_FILLING_RETURN
        
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "position": ticket,
            "symbol": pos.symbol,
            "volume": volume,
            "type": close_type,
            "price": price,
            "deviation": self.deviation,
            "magic": self.magic_number,
            "comment": "AMD_Close",
            "type_filling": filling_mode,
        }
        
        result = mt5.order_send(request)
        
        if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
            error = result.comment if result else mt5.last_error()
            return {'success': False, 'error': f'Close failed: {error}'}
        
        logger.info(f"Position {ticket} closed: {volume} lots @ {result.price}")
        
        return {
            'success': True,
            'ticket': ticket,
            'closed_volume': volume,
            'close_price': result.price,
            'profit': pos.profit,
        }
    
    def close_all_positions(self, symbol: Optional[str] = None) -> Dict:
        """
        Close all open positions (optionally filtered by symbol).
        
        Args:
            symbol: Optional symbol to filter by
            
        Returns:
            Dict with close results
        """
        if symbol:
            positions = mt5.positions_get(symbol=symbol)
        else:
            positions = mt5.positions_get()
        
        if not positions:
            return {'success': True, 'closed_count': 0}
        
        results = []
        for pos in positions:
            if pos.magic == self.magic_number:  # Only close our bot's positions
                result = self.close_position(pos.ticket)
                results.append(result)
        
        closed = sum(1 for r in results if r['success'])
        
        return {
            'success': True,
            'closed_count': closed,
            'total_positions': len(positions),
            'results': results
        }
    
    def cancel_pending_order(self, ticket: int) -> Dict:
        """
        Cancel a pending order.
        
        Args:
            ticket: Order ticket number
            
        Returns:
            Dict with cancellation result
        """
        request = {
            "action": mt5.TRADE_ACTION_REMOVE,
            "order": ticket,
        }
        
        result = mt5.order_send(request)
        
        if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
            error = result.comment if result else mt5.last_error()
            return {'success': False, 'error': f'Cancellation failed: {error}'}
        
        logger.info(f"Pending order {ticket} cancelled")
        
        return {'success': True, 'ticket': ticket}
    
    def get_position_profit(self, ticket: int) -> Optional[float]:
        """
        Get current profit of an open position.
        
        Args:
            ticket: Position ticket number
            
        Returns:
            Current profit/loss or None if not found
        """
        position = mt5.positions_get(ticket=ticket)
        if not position:
            return None
        return position[0].profit
    
    def trail_stop_loss(
        self,
        ticket: int,
        trail_distance: float,
        current_price: float
    ) -> Dict:
        """
        Trail stop loss for an open position.

        Args:
            ticket: Position ticket number
            trail_distance: Distance to trail behind current price
            current_price: Current market price

        Returns:
            Dict with trail result
        """
        position = mt5.positions_get(ticket=ticket)
        if not position:
            return {'success': False, 'error': f'Position {ticket} not found'}

        pos = position[0]

        if pos.type == mt5.ORDER_TYPE_BUY:
            # For buy, trail stop below price
            new_sl = current_price - trail_distance
            # Only move if new SL is higher than current
            if new_sl > pos.sl:
                return self.modify_position(ticket, new_sl=new_sl)
        else:
            # For sell, trail stop above price
            new_sl = current_price + trail_distance
            # Only move if new SL is lower than current
            if new_sl < pos.sl:
                return self.modify_position(ticket, new_sl=new_sl)

        return {'success': True, 'message': 'No trailing needed', 'current_sl': pos.sl}

    def move_stop_to_breakeven(self, ticket: int, current_price: float, atr: float, take_partial: bool = False) -> Dict:
        """
        === ENHANCEMENT 4+: PROGRESSIVE TRAILING STOP LOGIC ===

        Phase 1: When trade moves 1 ATR in profit → move SL to break-even.
        Phase 2: After break-even, trail SL every 0.5 ATR to lock in more profit.
                 SL follows at (current_profit - 0.5*ATR) from current price.

        This converts losing trades into break-even AND captures more upside
        on winning trades instead of giving back profit.

        Args:
            ticket: Position ticket number
            current_price: Current market price
            atr: ATR value for the position's timeframe

        Returns:
            Dict with modification result (success, error, or no_action)
        """
        position = mt5.positions_get(ticket=ticket)
        if not position:
            return {'success': False, 'error': f'Position {ticket} not found'}

        pos = position[0]
        entry_price = pos.price_open
        current_sl = pos.sl

        if pos.type == mt5.ORDER_TYPE_BUY:
            profit_distance = current_price - entry_price

            if profit_distance >= atr:
                partial_taken = False
                if take_partial and pos.volume >= 0.02:
                    logger.info(f"PARTIAL TP: Position {ticket} (BUY) reached 1 ATR profit. Closing 50%.")
                    self.close_position(ticket, partial_volume=round(pos.volume * 0.5, 2))
                    partial_taken = True

                # Phase 2: Progressive trailing — trail SL at (price - 0.5*ATR)
                # Only move SL up, never down
                progressive_sl = current_price - (0.5 * atr)
                # Ensure at least break-even
                progressive_sl = max(progressive_sl, entry_price)

                if progressive_sl > current_sl:
                    result = self.modify_position(ticket, new_sl=round(progressive_sl, 5))
                    if result['success']:
                        locked_profit = progressive_sl - entry_price
                        logger.info(
                            f"TRAILING: Position {ticket} (BUY) profit={profit_distance:.5f}, "
                            f"SL moved {current_sl:.5f} → {progressive_sl:.5f} "
                            f"(locked profit: {locked_profit:.5f})"
                        )
                    result['partial_taken'] = partial_taken
                    return result
                
                if partial_taken:
                    return {'success': True, 'action': 'partial_taken', 'partial_taken': True}

        else:  # SELL
            profit_distance = entry_price - current_price

            if profit_distance >= atr:
                partial_taken = False
                if take_partial and pos.volume >= 0.02:
                    logger.info(f"PARTIAL TP: Position {ticket} (SELL) reached 1 ATR profit. Closing 50%.")
                    self.close_position(ticket, partial_volume=round(pos.volume * 0.5, 2))
                    partial_taken = True

                # Phase 2: Progressive trailing — trail SL at (price + 0.5*ATR)
                progressive_sl = current_price + (0.5 * atr)
                # Ensure at least break-even
                progressive_sl = min(progressive_sl, entry_price)

                if progressive_sl < current_sl:
                    result = self.modify_position(ticket, new_sl=round(progressive_sl, 5))
                    if result['success']:
                        locked_profit = entry_price - progressive_sl
                        logger.info(
                            f"TRAILING: Position {ticket} (SELL) profit={profit_distance:.5f}, "
                            f"SL moved {current_sl:.5f} → {progressive_sl:.5f} "
                            f"(locked profit: {locked_profit:.5f})"
                        )
                    result['partial_taken'] = partial_taken
                    return result
                
                if partial_taken:
                    return {'success': True, 'action': 'partial_taken', 'partial_taken': True}

        return {'success': True, 'action': 'no_trailing_needed', 'partial_taken': False}


if __name__ == "__main__":
    print("Order Executor Module - Testing")
    print("=" * 50)
    print("This module requires active MT5 connection to test.")
    print("Use main.py to run the full trading system.")
