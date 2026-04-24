"""
Data Fetcher Module
====================
Handles MetaTrader 5 connection and historical/live data retrieval.
Optimized for OctaFX broker.
"""

import MetaTrader5 as mt5
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Tuple
import logging
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import settings

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class MT5Connection:
    """Manages MetaTrader 5 connection and data retrieval."""
    
    # Timeframe mapping
    TIMEFRAMES = {
        'M1': mt5.TIMEFRAME_M1,
        'M3': mt5.TIMEFRAME_M3,
        'M5': mt5.TIMEFRAME_M5,
        'M15': mt5.TIMEFRAME_M15,
        'M30': mt5.TIMEFRAME_M30,
        'H1': mt5.TIMEFRAME_H1,
        'H4': mt5.TIMEFRAME_H4,
        'D1': mt5.TIMEFRAME_D1,
        'W1': mt5.TIMEFRAME_W1,
        'MN1': mt5.TIMEFRAME_MN1,
    }
    
    def __init__(self):
        """Initialize MT5 connection handler."""
        self.connected = False
        self.account_info = None
        
    def connect(self) -> bool:
        """
        Initialize connection to MetaTrader 5.
        
        Returns:
            bool: True if connection successful, False otherwise.
        """
        # Initialize MT5
        if not mt5.initialize():
            logger.error(f"MT5 initialization failed: {mt5.last_error()}")
            return False
        
        # Login to OctaFX account
        if settings.MT5_LOGIN and settings.MT5_PASSWORD:
            authorized = mt5.login(
                login=settings.MT5_LOGIN,
                password=settings.MT5_PASSWORD,
                server=settings.MT5_SERVER
            )
            
            if not authorized:
                logger.error(f"MT5 login failed: {mt5.last_error()}")
                mt5.shutdown()
                return False
                
            logger.info(f"Connected to OctaFX - Account: {settings.MT5_LOGIN}")
        else:
            logger.warning("No credentials provided - using existing MT5 session")
        
        self.connected = True
        self.account_info = mt5.account_info()
        
        if self.account_info:
            logger.info(f"Account Balance: ${self.account_info.balance:.2f}")
            logger.info(f"Account Equity: ${self.account_info.equity:.2f}")
            logger.info(f"Account Leverage: 1:{self.account_info.leverage}")
        
        return True
    
    def disconnect(self):
        """Shutdown MT5 connection."""
        mt5.shutdown()
        self.connected = False
        logger.info("Disconnected from MT5")
    
    def get_account_info(self) -> Dict:
        """
        Get current account information.
        
        Returns:
            Dict: Account details including balance, equity, margin, etc.
        """
        info = mt5.account_info()
        if info is None:
            return {}
        
        return {
            'balance': info.balance,
            'equity': info.equity,
            'margin': info.margin,
            'free_margin': info.margin_free,
            'margin_level': info.margin_level,
            'profit': info.profit,
            'leverage': info.leverage,
            'currency': info.currency,
        }
    
    def get_symbol_info(self, symbol: str) -> Optional[Dict]:
        """
        Get symbol information including pip value, contract size, etc.
        
        Args:
            symbol: Trading symbol (e.g., 'EURUSD')
            
        Returns:
            Dict: Symbol details or None if not found.
        """
        info = mt5.symbol_info(symbol)
        if info is None:
            logger.error(f"Symbol {symbol} not found")
            return None
        
        # Enable symbol if not visible
        if not info.visible:
            if not mt5.symbol_select(symbol, True):
                logger.error(f"Failed to select symbol {symbol}")
                return None
        
        tick = mt5.symbol_info_tick(symbol)
        
        return {
            'symbol': symbol,
            'bid': tick.bid if tick else 0,
            'ask': tick.ask if tick else 0,
            'spread': info.spread,
            'digits': info.digits,
            'point': info.point,
            'pip_value': info.point * 10,  # Approximate pip value
            'contract_size': info.trade_contract_size,
            'min_lot': info.volume_min,
            'max_lot': info.volume_max,
            'lot_step': info.volume_step,
            'swap_long': info.swap_long,
            'swap_short': info.swap_short,
        }
    
    def get_historical_data(
        self,
        symbol: str,
        timeframe: str = 'H1',
        num_candles: int = 1000,
        start_date: Optional[datetime] = None
    ) -> pd.DataFrame:
        """
        Fetch historical OHLCV data from MT5.
        
        Args:
            symbol: Trading symbol (e.g., 'EURUSD')
            timeframe: Timeframe string ('M1', 'M5', 'M15', 'M30', 'H1', 'H4', 'D1')
            num_candles: Number of candles to fetch
            start_date: Optional start date for data
            
        Returns:
            DataFrame: OHLCV data with datetime index.
        """
        # Ensure symbol is selected
        if not mt5.symbol_select(symbol, True):
            logger.error(f"Failed to select symbol {symbol}")
            return pd.DataFrame()
        
        tf = self.TIMEFRAMES.get(timeframe, mt5.TIMEFRAME_H1)
        
        if start_date:
            rates = mt5.copy_rates_from(symbol, tf, start_date, num_candles)
        else:
            rates = mt5.copy_rates_from_pos(symbol, tf, 0, num_candles)
        
        if rates is None or len(rates) == 0:
            logger.error(f"Failed to get data for {symbol}: {mt5.last_error()}")
            return pd.DataFrame()
        
        # Convert to DataFrame
        df = pd.DataFrame(rates)
        df['time'] = pd.to_datetime(df['time'], unit='s')
        df.set_index('time', inplace=True)
        
        # Rename columns for consistency
        df.columns = ['open', 'high', 'low', 'close', 'tick_volume', 'spread', 'real_volume']
        
        # Add volume column (use tick_volume as proxy if real_volume is 0)
        df['volume'] = np.where(df['real_volume'] > 0, df['real_volume'], df['tick_volume'])
        
        logger.info(f"Fetched {len(df)} candles for {symbol} {timeframe}")
        return df
    
    def get_live_tick(self, symbol: str) -> Optional[Dict]:
        """
        Get current live tick data for a symbol.
        
        Args:
            symbol: Trading symbol
            
        Returns:
            Dict: Current bid, ask, and timestamp.
        """
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            return None
        
        return {
            'symbol': symbol,
            'bid': tick.bid,
            'ask': tick.ask,
            'time': datetime.fromtimestamp(tick.time),
            'volume': tick.volume,
        }
    
    def get_open_positions(self, symbol: Optional[str] = None) -> List[Dict]:
        """
        Get all open positions, optionally filtered by symbol.
        
        Args:
            symbol: Optional symbol to filter by
            
        Returns:
            List[Dict]: List of open position details.
        """
        if symbol:
            positions = mt5.positions_get(symbol=symbol)
        else:
            positions = mt5.positions_get()
        
        if positions is None:
            return []
        
        result = []
        for pos in positions:
            result.append({
                'ticket': pos.ticket,
                'symbol': pos.symbol,
                'type': 'BUY' if pos.type == mt5.ORDER_TYPE_BUY else 'SELL',
                'volume': pos.volume,
                'open_price': pos.price_open,
                'current_price': pos.price_current,
                'sl': pos.sl,
                'tp': pos.tp,
                'profit': pos.profit,
                'swap': pos.swap,
                'magic': pos.magic,
                'comment': pos.comment,
                'open_time': datetime.fromtimestamp(pos.time),
            })
        
        return result
    
    def get_pending_orders(self, symbol: Optional[str] = None) -> List[Dict]:
        """
        Get all pending orders, optionally filtered by symbol.
        
        Args:
            symbol: Optional symbol to filter by
            
        Returns:
            List[Dict]: List of pending order details.
        """
        if symbol:
            orders = mt5.orders_get(symbol=symbol)
        else:
            orders = mt5.orders_get()
        
        if orders is None:
            return []
        
        result = []
        for order in orders:
            order_types = {
                mt5.ORDER_TYPE_BUY_LIMIT: 'BUY_LIMIT',
                mt5.ORDER_TYPE_SELL_LIMIT: 'SELL_LIMIT',
                mt5.ORDER_TYPE_BUY_STOP: 'BUY_STOP',
                mt5.ORDER_TYPE_SELL_STOP: 'SELL_STOP',
            }
            result.append({
                'ticket': order.ticket,
                'symbol': order.symbol,
                'type': order_types.get(order.type, 'UNKNOWN'),
                'volume': order.volume_current,
                'price': order.price_open,
                'sl': order.sl,
                'tp': order.tp,
                'magic': order.magic,
                'comment': order.comment,
            })
        
        return result


class DataFetcher:
    """High-level data fetching interface for the trading strategy."""
    
    def __init__(self, mt5_connection: MT5Connection):
        """
        Initialize DataFetcher with MT5 connection.
        
        Args:
            mt5_connection: Active MT5Connection instance
        """
        self.mt5 = mt5_connection
        self._cache = {}
        
    def get_analysis_data(
        self,
        symbol: str,
        primary_tf: str = 'H1',
        secondary_tf: str = 'M15',
        candles: int = 500
    ) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """
        Get data for both primary and secondary timeframes for analysis.
        
        Args:
            symbol: Trading symbol
            primary_tf: Primary timeframe for AMD detection
            secondary_tf: Secondary timeframe for entry refinement
            candles: Number of candles to fetch
            
        Returns:
            Tuple of (primary_df, secondary_df)
        """
        primary_df = self.mt5.get_historical_data(symbol, primary_tf, candles)
        secondary_df = self.mt5.get_historical_data(symbol, secondary_tf, candles * 4)
        
        return primary_df, secondary_df
    
    def refresh_data(self, symbol: str, timeframe: str = 'H1') -> pd.DataFrame:
        """
        Refresh and return latest data for a symbol.
        
        Args:
            symbol: Trading symbol
            timeframe: Timeframe to fetch
            
        Returns:
            DataFrame: Fresh OHLCV data
        """
        return self.mt5.get_historical_data(symbol, timeframe, 500)


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def initialize_mt5() -> Optional[MT5Connection]:
    """
    Initialize and return MT5 connection.
    
    Returns:
        MT5Connection instance if successful, None otherwise.
    """
    connection = MT5Connection()
    if connection.connect():
        return connection
    return None


if __name__ == "__main__":
    # Test the connection
    print("Testing OctaFX MT5 Connection...")
    print("=" * 50)
    
    conn = initialize_mt5()
    if conn:
        # Test account info
        print("\nAccount Info:")
        info = conn.get_account_info()
        for key, value in info.items():
            print(f"  {key}: {value}")
        
        # Test data fetch
        print("\nFetching EURUSD H1 data...")
        df = conn.get_historical_data('EURUSD', 'H1', 100)
        if not df.empty:
            print(df.tail())
        
        # Test symbol info
        print("\nSymbol Info for EURUSD:")
        sym_info = conn.get_symbol_info('EURUSD')
        if sym_info:
            for key, value in sym_info.items():
                print(f"  {key}: {value}")
        
        conn.disconnect()
    else:
        print("Failed to connect to MT5. Make sure:")
        print("1. MetaTrader 5 is installed and running")
        print("2. You have created a demo account with OctaFX")
        print("3. Your credentials are set in config/.env")
