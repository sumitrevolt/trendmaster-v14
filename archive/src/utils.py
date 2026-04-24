"""
Utility Functions for AMD Trading Bot
======================================
Helper functions for logging, time management, and common operations.
"""

import logging
import os
from datetime import datetime, timedelta
from pathlib import Path
import json
import csv
from typing import Dict, List, Optional
import sys

# Add parent to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def setup_logging(
    log_level: str = 'INFO',
    log_file: str = 'logs/trading.log'
) -> logging.Logger:
    """
    Set up logging configuration.
    
    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR)
        log_file: Path to log file
        
    Returns:
        Configured logger
    """
    # Create logs directory if needed
    log_path = Path(log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Configure logging
    level = getattr(logging, log_level.upper(), logging.INFO)
    
    # Create formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    
    # File handler
    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)
    
    # Configure root logger
    logger = logging.getLogger()
    logger.setLevel(level)
    logger.addHandler(console_handler)
    logger.addHandler(file_handler)
    
    return logger


def log_trade(
    trade_data: Dict,
    journal_file: str = 'logs/trades.csv'
) -> None:
    """
    Log a trade to the trade journal CSV.
    
    Args:
        trade_data: Trade information dictionary
        journal_file: Path to trade journal file
    """
    journal_path = Path(journal_file)
    journal_path.parent.mkdir(parents=True, exist_ok=True)
    
    file_exists = journal_path.exists()
    
    # Define CSV columns
    columns = [
        'timestamp', 'symbol', 'type', 'entry_price', 'volume',
        'stop_loss', 'take_profit', 'ticket', 'status', 'exit_price',
        'profit', 'exit_time', 'duration_hours', 'notes'
    ]
    
    with open(journal_path, 'a', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        
        if not file_exists:
            writer.writeheader()
        
        # Add missing fields with defaults
        row = {col: trade_data.get(col, '') for col in columns}
        writer.writerow(row)


def is_trading_session(
    utc_hour: int = None,
    sessions: Dict = None
) -> Dict:
    """
    Check if current time is within trading session.
    
    Args:
        utc_hour: Hour in UTC (defaults to current)
        sessions: Session configuration (defaults to settings)
        
    Returns:
        Dict with session info
    """
    from config import settings
    
    if utc_hour is None:
        utc_hour = datetime.utcnow().hour
    
    sessions = sessions or settings.SESSIONS
    
    london_active = sessions['london_open'] <= utc_hour < sessions['london_close']
    ny_active = sessions['ny_open'] <= utc_hour < sessions['ny_close']
    overlap = sessions['ny_open'] <= utc_hour < sessions['london_close']
    asian = 0 <= utc_hour < sessions['london_open'] or utc_hour >= sessions['ny_close']
    
    can_trade = False
    session_name = 'Asian'
    
    if overlap and sessions.get('trade_overlap', True):
        can_trade = True
        session_name = 'London-NY Overlap'
    elif london_active and sessions.get('trade_london', True):
        can_trade = True
        session_name = 'London'
    elif ny_active and sessions.get('trade_ny', True):
        can_trade = True
        session_name = 'New York'
    elif asian and not sessions.get('avoid_asian', True):
        can_trade = True
        session_name = 'Asian'
    
    return {
        'can_trade': can_trade,
        'session': session_name,
        'london': london_active,
        'new_york': ny_active,
        'overlap': overlap,
        'asian': asian,
        'utc_hour': utc_hour
    }


def format_price(price: float, digits: int = 5) -> str:
    """Format price with correct decimal places."""
    return f"{price:.{digits}f}"


def pips_to_price(pips: float, symbol: str) -> float:
    """
    Convert pips to price difference.
    
    Args:
        pips: Number of pips
        symbol: Trading symbol
        
    Returns:
        Price difference
    """
    if 'JPY' in symbol:
        return pips * 0.01
    else:
        return pips * 0.0001


def price_to_pips(price_diff: float, symbol: str) -> float:
    """
    Convert price difference to pips.
    
    Args:
        price_diff: Price difference
        symbol: Trading symbol
        
    Returns:
        Number of pips
    """
    if 'JPY' in symbol:
        return price_diff * 100
    else:
        return price_diff * 10000


def calculate_profit_loss(
    entry_price: float,
    exit_price: float,
    volume: float,
    trade_type: str,
    symbol: str
) -> float:
    """
    Calculate profit/loss in account currency.
    
    Args:
        entry_price: Entry price
        exit_price: Exit price
        volume: Position size in lots
        trade_type: 'BUY' or 'SELL'
        symbol: Trading symbol
        
    Returns:
        Profit/loss amount
    """
    if trade_type == 'BUY':
        pips = price_to_pips(exit_price - entry_price, symbol)
    else:
        pips = price_to_pips(entry_price - exit_price, symbol)
    
    # Standard pip value: $10 per pip per standard lot
    if 'JPY' in symbol:
        pip_value = 1000 * volume  # JPY pairs
    else:
        pip_value = 10 * volume  # Standard pairs
    
    return pips * pip_value


def get_next_candle_time(timeframe: str) -> datetime:
    """
    Calculate when the next candle will close.
    
    Args:
        timeframe: Timeframe string (M1, M5, M15, H1, etc.)
        
    Returns:
        Datetime of next candle close
    """
    now = datetime.utcnow()
    
    timeframe_minutes = {
        'M1': 1, 'M5': 5, 'M15': 15, 'M30': 30,
        'H1': 60, 'H4': 240, 'D1': 1440
    }
    
    minutes = timeframe_minutes.get(timeframe, 60)
    
    # Calculate next candle close
    current_minute = now.minute
    next_close_minute = ((current_minute // minutes) + 1) * minutes
    
    if minutes >= 60:
        hours = minutes // 60
        current_hour = now.hour
        next_close_hour = ((current_hour // hours) + 1) * hours
        if next_close_hour >= 24:
            next_close = now.replace(hour=0, minute=0, second=0, microsecond=0)
            next_close += timedelta(days=1)
        else:
            next_close = now.replace(hour=next_close_hour, minute=0, second=0, microsecond=0)
    else:
        if next_close_minute >= 60:
            next_close = now.replace(minute=0, second=0, microsecond=0)
            next_close += timedelta(hours=1)
        else:
            next_close = now.replace(minute=next_close_minute, second=0, microsecond=0)
    
    return next_close


def save_state(state: Dict, filepath: str = 'logs/bot_state.json') -> None:
    """
    Save bot state to file.
    
    Args:
        state: State dictionary
        filepath: Path to state file
    """
    path = Path(filepath)
    path.parent.mkdir(parents=True, exist_ok=True)
    
    # Convert datetime objects to strings
    def convert(obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        return obj
    
    # Atomic write: temp file + rename to prevent corruption on crash
    import tempfile
    json_str = json.dumps(state, indent=2, default=convert)
    dir_path = str(path.parent)
    try:
        with tempfile.NamedTemporaryFile('w', dir=dir_path, delete=False,
                                          suffix='.tmp', encoding='utf-8', newline='\n') as tmp:
            tmp.write(json_str)
            tmp.flush()
            os.fsync(tmp.fileno())
            tmp_name = tmp.name
        os.replace(tmp_name, str(path))
    except (OSError, PermissionError):
        # Fallback to direct write if atomic rename fails (e.g., Windows locking)
        try:
            os.unlink(tmp_name)
        except Exception:
            pass
        with open(path, 'w', encoding='utf-8', newline='\n') as f:
            f.write(json_str)
            f.flush()
            os.fsync(f.fileno())


def load_state(filepath: str = 'logs/bot_state.json') -> Dict:
    """
    Load bot state from file.
    
    Args:
        filepath: Path to state file
        
    Returns:
        State dictionary or empty dict if not found
    """
    path = Path(filepath)
    
    if not path.exists():
        return {}
    
    try:
        with open(path, 'r') as f:
            return json.load(f)
    except json.JSONDecodeError:
        return {}


def print_banner():
    """Print startup banner."""
    banner = """
+==============================================================+
|                                                              |
|     AAA   M   M  DDDD      BBBB   OOO  TTTTT                 |
|    A   A  MM MM  D   D     B   B O   O   T                   |
|    AAAAA  M M M  D   D     BBBB  O   O   T                   |
|    A   A  M   M  D   D     B   B O   O   T                   |
|    A   A  M   M  DDDD      BBBB   OOO    T                   |
|                                                              |
|         Accumulation - Manipulation - Distribution           |
|              Smart Money Forex Trading System                |
|                                                              |
|                    Broker: OctaFX                            |
|                                                              |
+==============================================================+
    """
    print(banner)


if __name__ == "__main__":
    # Test utilities
    print_banner()
    
    print("\nSession Check:")
    session = is_trading_session()
    for key, value in session.items():
        print(f"  {key}: {value}")
    
    print(f"\nNext H1 candle: {get_next_candle_time('H1')}")
    print(f"10 pips in EURUSD: {pips_to_price(10, 'EURUSD')}")
    print(f"0.0050 EURUSD to pips: {price_to_pips(0.0050, 'EURUSD')}")
