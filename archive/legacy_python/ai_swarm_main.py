"""
ai_swarm_main.py  — LEGACY 4-agent swarm entrypoint.
⚠️  Replaced 2026-04-20 by v14 TrendMaster (trend_master_brain.py).
    Gated behind ALLOW_LEGACY_SWARM=1 env var to prevent signal collision.
"""
import time
import signal
import sys
import os
import logging
import json
import tempfile
from datetime import datetime, timedelta
from typing import Dict, List, Optional

# ── LEGACY GUARD (v14 TrendMaster, 2026-04-20) ─────────────────────────────
if os.getenv('ALLOW_LEGACY_SWARM', '0') != '1':
    print("=" * 70)
    print("  LEGACY ai_swarm_main.py is DISABLED (v14 TrendMaster replaced it)")
    print("  Use instead:   python ai_trading_agents/trend_master_brain.py")
    print("  Force-enable:  set ALLOW_LEGACY_SWARM=1  &&  python ai_swarm_main.py")
    print("=" * 70)
    sys.exit(0)

# Import existing project modules
from config import settings
from src.data_fetcher import MT5Connection, DataFetcher, initialize_mt5
from src.indicators import AMDAnalyzer
from src.strategy import MultiPairStrategy
from src.risk_manager import RiskManager
from src.order_executor import OrderExecutor
from src.brain import get_brain, TradingBrain
from src.utils import setup_logging, print_banner

# Import institutional & geopolitical agents (graceful degradation if deps missing)
try:
    from ai_trading_agents.institutional_agents import (
        AgentCommunicationBus, InstitutionalFlowAgent, WebResearchAgent,
        CrossMarketAgent, EconomicCalendarAgent, AgentRewardSystem
    )
    INSTITUTIONAL_AVAILABLE = True
except ImportError as e:
    INSTITUTIONAL_AVAILABLE = False
    # Will log warning after logger is set up

try:
    from ai_trading_agents.geopolitical_agent import GeopoliticalRiskAgent
    GEOPOLITICAL_AVAILABLE = True
except ImportError as e:
    GEOPOLITICAL_AVAILABLE = False

# Import training engine for ML feedback loop
try:
    from ai_trading_agents.agent_training import TrainingEngine
    TRAINING_AVAILABLE = True
except ImportError:
    TRAINING_AVAILABLE = False

# Configure Logging
logger = setup_logging(settings.LOGGING['log_level'], settings.LOGGING.get('log_file', 'logs/ai_swarm.log'))

if not INSTITUTIONAL_AVAILABLE:
    logger.warning("Institutional agents unavailable (missing aiohttp?). Trading without COT/news/calendar filters.")
if not GEOPOLITICAL_AVAILABLE:
    logger.warning("Geopolitical agent unavailable. Trading without war/conflict risk adjustment.")
if not TRAINING_AVAILABLE:
    logger.warning("Training engine unavailable. ML feedback loop disabled.")

# ==========================================
# MULTI-AGENT SWARM ARCHITECTURE
# Target 80% Win Rate on XAUUSD & ETHUSD
# ==========================================

class DataOracleAgent:
    """Agent responsible for ingesting market data across timeframes."""
    def __init__(self, data_fetcher: DataFetcher):
        self.fetcher = data_fetcher
        self.logger = logging.getLogger("DataOracle")
        
    def fetch_market_context(self, symbol: str, entry_tf: str, trend_tf: str):
        self.logger.info(f"Oracle: Fetching real-time context for {symbol} on {entry_tf}...")
        df_entry = self.fetcher.refresh_data(symbol, entry_tf)
        df_trend = self.fetcher.refresh_data(symbol, trend_tf)
        return df_entry, df_trend


# ==========================================
# SESSION FILTER HELPER FUNCTIONS
# ==========================================

def get_utc_hour() -> int:
    """Get current UTC hour (0-23)."""
    return datetime.utcnow().hour


# ==========================================
# CORRELATION GROUPS — Prevent correlated losses
# ==========================================
# When we have an open position in one currency, avoid opening
# conflicting positions in correlated pairs (same exposure direction).
# E.g., BUY EURUSD + BUY GBPUSD = doubled EUR-long risk.
CORRELATION_GROUPS = {
    'USD_WEAK': ['EURUSD', 'GBPUSD', 'AUDUSD', 'NZDUSD'],  # All rally when USD weakens
    'USD_STRONG': ['USDJPY', 'USDCHF', 'USDCAD'],           # All rally when USD strengthens
    'JPY_CROSS': ['GBPJPY', 'EURJPY'],                       # Correlated JPY crosses
    'METALS': ['XAUUSD', 'XAGUSD'],                          # Gold/Silver move together
    'CRYPTO': ['BTCUSD', 'ETHUSD'],                          # Crypto correlated
}

def _get_correlation_group(symbol: str) -> Optional[str]:
    """Get the correlation group for a symbol."""
    for group, symbols in CORRELATION_GROUPS.items():
        if symbol in symbols:
            return group
    return None

def _check_correlation_conflict(symbol: str, direction: str) -> bool:
    """
    Check if opening a position in the given symbol/direction conflicts with
    existing open positions in correlated pairs.
    Returns True if there IS a conflict (should skip trade).
    """
    try:
        import MetaTrader5 as _mt5_corr
        positions = _mt5_corr.positions_get()
        if not positions:
            return False

        group = _get_correlation_group(symbol)
        if not group:
            return False

        group_symbols = CORRELATION_GROUPS[group]

        for pos in positions:
            if pos.symbol in group_symbols and pos.symbol != symbol:
                # Same group, different symbol — check direction conflict
                pos_dir = 'BUY' if pos.type == 0 else 'SELL'
                # For USD_WEAK group: BUY EURUSD + BUY GBPUSD = same directional risk
                # For USD_STRONG group: BUY USDJPY + BUY USDCHF = same directional risk
                if pos_dir == direction:
                    return True  # Same direction in correlated pair = conflict
        return False
    except Exception:
        return False  # If check fails, don't block trade

def is_high_liquidity_session(symbol: str) -> tuple:
    """
    Check if current time is in a high-liquidity trading session.

    Returns:
        tuple: (is_allowed: bool, session_name: str, confidence_boost: float)
               confidence_boost: +1.0 for Asian session on crypto (reduced liquidity)
    """
    utc_hour = get_utc_hour()

    # London session: 07:00-16:00 UTC
    if 7 <= utc_hour < 16:
        return True, "London", 0.0

    # New York session: 12:00-21:00 UTC
    if 12 <= utc_hour < 21:
        return True, "New York", 0.0

    # For crypto: allow 24/7 but penalize during Asian session
    if symbol in ['BTCUSD', 'ETHUSD']:
        # Asian session: 21:00-07:00 UTC (reduced liquidity)
        if utc_hour >= 21 or utc_hour < 7:
            return True, "Asian (crypto 24/7)", 1.0  # +1 confidence requirement
        else:
            return True, "Crypto session", 0.0

    # Forex during Asian session: not allowed
    return False, "Asian (forex closed)", 0.0


class VertexStrategyAgent:
    """Agent responsible for analyzing SMC footprints and dictating entries."""
    def __init__(self, strategy: MultiPairStrategy):
        self.analyzer = AMDAnalyzer()
        self.strategy = strategy
        self.logger = logging.getLogger("StrategyBrain")
        
    def analyze_opportunity(self, symbol: str, df_entry, df_trend, entry_tf: str, df_m5=None) -> Optional[Dict]:
        self.logger.info(f"StrategyBrain: Analyzing liquidity and order blocks for {symbol}...")
        if df_entry is None or df_entry.empty or df_trend is None or df_trend.empty:
            return None

        entry_analyzed = self.analyzer.analyze(df_entry)
        trend_analyzed = self.analyzer.analyze(df_trend)

        last_entry = entry_analyzed.iloc[-1]
        last_trend = trend_analyzed.iloc[-1]

        # --- WRITE LIVE FOOTPRINT FOR MT5 VISUAL DASHBOARD ---
        self._write_mt5_visual_bridge(symbol, entry_analyzed)

        bull_score = int(last_entry.get('scalp_bull_score', 0))
        bear_score = int(last_entry.get('scalp_bear_score', 0))
        h_trend_bull = bool(last_trend.get('scalp_trend_bull', False))
        h_trend_bear = bool(last_trend.get('scalp_trend_bear', False))

        # 80% WIN RATE CONSTRAINT: Minimum 9 Confluences + Trend Alignment
        min_confluences = settings.SCALP.get('min_confluences', 9)

        signal_dir = None
        if bull_score >= min_confluences and h_trend_bull:
            signal_dir = 'BUY'
        elif bear_score >= min_confluences and h_trend_bear:
            signal_dir = 'SELL'

        if not signal_dir:
            self.logger.debug(f"StrategyBrain: No high-probability setup for {symbol}. Yielding.")
            return None

        # === ENHANCEMENT 1: MULTI-TIMEFRAME CONFIRMATION (M5 SHORT-TERM MOMENTUM) ===
        if df_m5 is not None and not df_m5.empty:
            m5_analyzed = self.analyzer.analyze(df_m5)
            last_m5 = m5_analyzed.iloc[-1]
            m5_bull = bool(last_m5.get('scalp_trend_bull', False))
            m5_bear = bool(last_m5.get('scalp_trend_bear', False))

            # M5 trend must align with M15 signal
            if signal_dir == 'BUY' and not m5_bull:
                self.logger.info(
                    f"StrategyBrain: M5 momentum disagrees (M15 BUY but M5 not bullish) for {symbol}. "
                    f"Skipping trade to reduce false signals."
                )
                return None
            elif signal_dir == 'SELL' and not m5_bear:
                self.logger.info(
                    f"StrategyBrain: M5 momentum disagrees (M15 SELL but M5 not bearish) for {symbol}. "
                    f"Skipping trade to reduce false signals."
                )
                return None

            self.logger.debug(f"StrategyBrain: M5 confirmation passed for {symbol} {signal_dir}")

        atr = float(last_entry.get('atr', 2.0))
        entry_price = float(last_entry['close'])
        sl_mult = settings.RISK['default_sl_atr_multiple']
        rr = settings.RISK['min_risk_reward']

        if signal_dir == 'BUY':
            stop_loss = entry_price - (atr * sl_mult)
            take_profit = entry_price + (abs(entry_price - stop_loss) * rr)
        else:
            stop_loss = entry_price + (atr * sl_mult)
            take_profit = entry_price - (abs(entry_price - stop_loss) * rr)

        # === FIX: Use symbol-specific decimal precision instead of hardcoded round(2) ===
        # USDCHF needs 5 digits, USDJPY needs 3, XAUUSD needs 2, BTCUSD needs 2
        # Without this, SL gets rounded to same price as entry → "Invalid stops" error
        import MetaTrader5 as _mt5
        _sym_info = _mt5.symbol_info(symbol)
        _digits = _sym_info.digits if _sym_info else 5  # safe default = 5 digits

        # === ENHANCEMENT: Enforce minimum SL distance to prevent "Invalid stops" ===
        # When ATR is tiny relative to price precision, SL can round to same as entry
        _rounded_entry = round(entry_price, _digits)
        _rounded_sl = round(stop_loss, _digits)
        _min_distance = 10 ** (-_digits) * 10  # At least 10 points in smallest digit
        if abs(_rounded_entry - _rounded_sl) < _min_distance:
            if signal_dir == 'BUY':
                _rounded_sl = _rounded_entry - _min_distance
            else:
                _rounded_sl = _rounded_entry + _min_distance
            _rounded_sl = round(_rounded_sl, _digits)
            # Recalculate TP based on corrected SL distance
            _sl_dist = abs(_rounded_entry - _rounded_sl)
            if signal_dir == 'BUY':
                take_profit = _rounded_entry + (_sl_dist * rr)
            else:
                take_profit = _rounded_entry - (_sl_dist * rr)
            self.logger.info(
                f"StrategyBrain: Adjusted SL for {symbol} to enforce min distance "
                f"({_min_distance}). Entry={_rounded_entry}, SL={_rounded_sl}"
            )

        return {
            'symbol': symbol,
            'direction': signal_dir,
            'entry_price': _rounded_entry,
            'stop_loss': _rounded_sl,
            'take_profit': round(take_profit, _digits),
            'confidence_score_out_of_15': bull_score if signal_dir == 'BUY' else bear_score,
            'entry_timeframe': entry_tf,
            'atr': atr
        }

    def _write_mt5_visual_bridge(self, symbol: str, df_analyzed):
        """Writes current signals to the MT5 Terminal Common file directory so the MT5 Indicator can paint it on the chart natively."""
        try:
            # Common MT5 Data Folder Path for sharing between Python and MT5 Terminals
            common_data_path = os.path.join(os.environ['APPDATA'], 'MetaQuotes', 'Terminal', 'Common', 'Files')
            os.makedirs(common_data_path, exist_ok=True)
            
            signal_file = os.path.join(common_data_path, 'ai_swarm_signals.csv')
            
            # Extract footprints for the last 150 candles
            signals_to_draw = []
            recent_df = df_analyzed.tail(150)
            
            for index, row in recent_df.iterrows():
                candle_time = index.strftime('%Y.%m.%d %H:%M')
                
                if row.get('bullish_fvg', False):
                    signals_to_draw.append(f"FVG_BUY,{candle_time},{row['low']},Buy FVG")
                if row.get('bearish_fvg', False):
                    signals_to_draw.append(f"FVG_SELL,{candle_time},{row['high']},Sell FVG")
                if row.get('bullish_manipulation', False) or row.get('bearish_manipulation', False):
                    price = row['low'] if row.get('bullish_manipulation', False) else row['high']
                    signals_to_draw.append(f"LIQ_SWEEP,{candle_time},{price},Liquidity Sweep")
                
            if signals_to_draw:
                # Overwrite the CSV for the indicator to fetch cleanly
                with open(signal_file, 'w', newline='\n') as f:
                    for s in signals_to_draw:
                        f.write(s + '\n')
                        
        except Exception as e:
            self.logger.debug(f"Could not bridge to MT5 Common Directory: {e}")

class ExecutionShieldAgent:
    """Agent responsible for preserving capital, risk sizing, and trade execution."""
    def __init__(self, risk_manager: RiskManager, executor: OrderExecutor, mt5: MT5Connection):
        self.risk_manager = risk_manager
        self.executor = executor
        self.mt5 = mt5
        self.logger = logging.getLogger("ExecutionShield")
        self._consecutive_no_money = 0
        self._no_money_pause_until = None
        self._NO_MONEY_THRESHOLD = 3   # pause after 3 consecutive "No money" errors (was 5)
        self._NO_MONEY_PAUSE_MIN = 30  # base pause = 30 minutes
        self._no_money_backoff_level = 0  # exponential backoff: 30, 60, 120, 240 min
        self._position_atr_cache = {}  # Track ATR for each ticket to use in trailing stop
        self._position_partial_taken = set()  # Track tickets where 50% partial profit was booked

    def execute_and_protect(self, signal: Dict):
        # Circuit breaker: if account has no funds, pause scanning to save resources
        if self._no_money_pause_until:
            if datetime.now() < self._no_money_pause_until:
                return  # silently skip — already logged the pause
            else:
                self.logger.info("Shield: No-money pause expired. Resuming trade attempts.")
                self._no_money_pause_until = None
                self._consecutive_no_money = 0

        # === ENHANCEMENT: Pre-flight free margin check ===
        # Avoid sending orders that will instantly fail with "No money"
        try:
            import MetaTrader5 as _mt5_margin
            acct = _mt5_margin.account_info()
            if acct and acct.margin_free is not None:
                if acct.margin_free < 1.0:  # less than $1 free margin
                    self.logger.warning(
                        f"Shield: Free margin too low (${acct.margin_free:.2f}). "
                        f"Skipping trade to avoid 'No money' error. Fund account to resume."
                    )
                    self._consecutive_no_money += 1
                    if self._consecutive_no_money >= self._NO_MONEY_THRESHOLD:
                        pause_min = self._NO_MONEY_PAUSE_MIN * (2 ** self._no_money_backoff_level)
                        pause_min = min(pause_min, 480)  # cap at 8 hours
                        self._no_money_pause_until = datetime.now() + timedelta(minutes=pause_min)
                        self._no_money_backoff_level += 1
                        self.logger.warning(
                            f"Shield: CIRCUIT BREAKER — free margin depleted. "
                            f"Pausing for {pause_min} min (backoff level {self._no_money_backoff_level})."
                        )
                    return
        except Exception:
            pass  # If MT5 check fails, proceed normally

        can_trade = self.risk_manager.can_trade()
        if not can_trade['allowed']:
            self.logger.warning(f"Shield: Trade Blocked - {can_trade['reason']}")
            return

        symbol_info = self.mt5.get_symbol_info(signal['symbol'])
        if not symbol_info:
            return

        # === ENHANCEMENT 3: SPREAD VALIDATION CHECK ===
        import MetaTrader5 as mt5
        tick = mt5.symbol_info_tick(signal['symbol'])
        if tick:
            spread = tick.ask - tick.bid
            atr = signal.get('atr', 2.0)
            sl_distance = abs(signal['entry_price'] - signal['stop_loss'])
            max_allowed_spread = 2.0 * atr  # or you could use 2x SL distance

            if spread > max_allowed_spread:
                self.logger.warning(
                    f"Shield: Spread too wide for {signal['symbol']} — "
                    f"Current spread {spread:.6f} > 2x ATR-based max {max_allowed_spread:.6f}. "
                    f"Skipping trade to avoid slippage."
                )
                return

        position_size = self.risk_manager.calculate_position_size(
            symbol=signal['symbol'],
            entry_price=signal['entry_price'],
            stop_loss=signal['stop_loss'],
            symbol_info=symbol_info
        )

        if position_size <= 0:
            self.logger.warning("Shield: Position size is 0. Trade aborted.")
            return

        self.logger.info(f"Shield: Executing {signal['direction']} on {signal['symbol']} (Lot: {position_size})")
        result = self.executor.place_market_order(
            symbol=signal['symbol'],
            order_type=signal['direction'],
            volume=position_size,
            stop_loss=signal['stop_loss'],
            take_profit=signal['take_profit'],
            comment="AI_SWARM_AGENT"
        )

        if result['success']:
            self._consecutive_no_money = 0  # reset on success
            self.logger.info(f"Shield: Trade executed successfully! Ticket {result['ticket']}")
            # Cache ATR for this position to use in trailing stop logic
            self._position_atr_cache[result['ticket']] = signal.get('atr', 2.0)
            self.risk_manager.record_trade(
                symbol=signal['symbol'],
                trade_type=signal['direction'],
                entry_price=result['price'],
                volume=position_size,
                stop_loss=signal['stop_loss'],
                take_profit=signal['take_profit'],
                ticket=result['ticket']
            )
        else:
            error_msg = result.get('error', '')
            self.logger.error(f"Shield: Execution failed - {error_msg}")

            # Track "No money" errors and pause if persistent (exponential backoff)
            if 'No money' in error_msg or 'no money' in error_msg.lower():
                self._consecutive_no_money += 1
                if self._consecutive_no_money >= self._NO_MONEY_THRESHOLD:
                    pause_min = self._NO_MONEY_PAUSE_MIN * (2 ** self._no_money_backoff_level)
                    pause_min = min(pause_min, 480)  # cap at 8 hours
                    self._no_money_pause_until = datetime.now() + timedelta(minutes=pause_min)
                    self._no_money_backoff_level += 1
                    self.logger.warning(
                        f"Shield: CIRCUIT BREAKER — {self._consecutive_no_money} consecutive 'No money' errors. "
                        f"Account needs funding. Pausing for {pause_min} min (backoff level {self._no_money_backoff_level})."
                    )
            else:
                self._consecutive_no_money = 0  # different error, reset counter

    def monitor_and_trail_positions(self):
        """
        === ENHANCEMENT 4: TRAILING STOP MONITORING ===

        Periodically check open positions and apply trailing stop logic.
        When a position moves 1 ATR in profit, move SL to break-even.
        """
        try:
            import MetaTrader5 as mt5
            positions = mt5.positions_get()
            if not positions:
                return

            for pos in positions:
                # Only manage positions opened by this bot
                if pos.magic != self.executor.magic_number:
                    continue

                ticket = pos.ticket
                atr = self._position_atr_cache.get(ticket, 2.0)

                # Get current price
                tick = mt5.symbol_info_tick(pos.symbol)
                if tick:
                    current_price = tick.bid if pos.type == mt5.ORDER_TYPE_BUY else tick.ask
                    
                    take_partial = ticket not in self._position_partial_taken
                    result = self.executor.move_stop_to_breakeven(ticket, current_price, atr, take_partial=take_partial)
                    
                    if result and result.get('partial_taken'):
                        self._position_partial_taken.add(ticket)

        except Exception as e:
            self.logger.debug(f"Shield: Error monitoring positions: {e}")


def _check_aged_positions(mt5_conn):
    """
    Check for positions open longer than 7 days and AUTO-CLOSE them.
    Called at startup to free up margin from stuck positions.

    === ENHANCEMENT (2026-03-31): Auto-close aged positions ===
    Previously only logged warnings. Now actively closes positions older than
    14 days to prevent permanent margin drain. Positions 7-14 days old get
    a warning; 14+ days get auto-closed.
    """
    try:
        import MetaTrader5 as mt5
        positions = mt5.positions_get()
        if not positions:
            return

        now = datetime.now()
        aged_positions = []
        auto_close_positions = []

        for pos in positions:
            # Calculate how long position has been open
            open_time = datetime.fromtimestamp(pos.time)
            days_open = (now - open_time).days

            pos_info = {
                'ticket': pos.ticket,
                'symbol': pos.symbol,
                'type': 'BUY' if pos.type == 0 else 'SELL',
                'type_mt5': pos.type,
                'volume': pos.volume,
                'open_price': pos.price_open,
                'current_price': pos.price_current,
                'profit': pos.profit,
                'days_open': days_open,
                'open_time': open_time.isoformat()
            }

            if days_open >= 14:
                auto_close_positions.append(pos_info)
            elif days_open >= 7:
                aged_positions.append(pos_info)

        # Auto-close positions older than 14 days
        if auto_close_positions:
            logger.warning(
                f"Coordinator: AUTO-CLOSING {len(auto_close_positions)} positions (14+ days old) to free margin:"
            )
            for pos in auto_close_positions:
                logger.warning(
                    f"  • Closing Ticket {pos['ticket']}: {pos['symbol']} {pos['type']} "
                    f"({pos['days_open']}d old) | P&L: ${pos['profit']:.2f}"
                )
                try:
                    # Determine close direction (opposite of open)
                    close_type = mt5.ORDER_TYPE_SELL if pos['type_mt5'] == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
                    tick = mt5.symbol_info_tick(pos['symbol'])
                    if tick:
                        close_price = tick.bid if pos['type_mt5'] == mt5.ORDER_TYPE_BUY else tick.ask
                        request = {
                            "action": mt5.TRADE_ACTION_DEAL,
                            "symbol": pos['symbol'],
                            "volume": pos['volume'],
                            "type": close_type,
                            "position": pos['ticket'],
                            "price": close_price,
                            "deviation": 20,
                            "magic": settings.ORDER['magic_number'],
                            "comment": "AI_SWARM_AUTO_CLOSE_AGED",
                            "type_time": mt5.ORDER_TIME_GTC,
                            "type_filling": mt5.ORDER_FILLING_IOC,
                        }
                        result = mt5.order_send(request)
                        if result and result.retcode == mt5.TRADE_RETCODE_DONE:
                            logger.info(f"  ✅ Ticket {pos['ticket']} closed successfully")
                        else:
                            error_code = result.retcode if result else 'N/A'
                            logger.warning(f"  ❌ Failed to close ticket {pos['ticket']}: code={error_code}")
                except Exception as close_err:
                    logger.warning(f"  ❌ Error closing ticket {pos['ticket']}: {close_err}")

        # Warn about 7-14 day old positions
        if aged_positions:
            logger.warning(
                f"Coordinator: WARNING — {len(aged_positions)} positions 7-14 days old (will auto-close at 14 days):"
            )
            for pos in aged_positions:
                logger.warning(
                    f"  • Ticket {pos['ticket']}: {pos['symbol']} {pos['type']} "
                    f"({pos['days_open']}d old, opened {pos['open_time']}) | "
                    f"Volume: {pos['volume']} | Entry: {pos['open_price']:.5f} | Current: {pos['current_price']:.5f} | "
                    f"P&L: ${pos['profit']:.2f}"
                )
    except Exception as e:
        logger.debug(f"Coordinator: Could not check aged positions: {e}")


class MasterCoordinatorAgent:
    """Orchestrates the Oracle, Brain, and Shield agents."""
    def __init__(self):
        self.running = False
        self.mt5 = initialize_mt5()
        if not self.mt5:
            logger.error("Coordinator: Failed to boot MT5 terminal.")
            sys.exit(1)
            
        account = self.mt5.get_account_info()
        self.data_fetcher = DataFetcher(self.mt5)
        self.risk_manager = RiskManager(account['balance'] if account else 1000)
        self.executor = OrderExecutor()
        self.multi_strategy = MultiPairStrategy(settings.TRADING_PAIRS, self.risk_manager)
        
        # Initialize specialized agents
        self.oracle = DataOracleAgent(self.data_fetcher)
        self.brain = VertexStrategyAgent(self.multi_strategy)
        self.shield = ExecutionShieldAgent(self.risk_manager, self.executor, self.mt5)

        # Initialize institutional intelligence agents
        self.institutional_enabled = INSTITUTIONAL_AVAILABLE
        self.geopolitical_enabled = GEOPOLITICAL_AVAILABLE
        self.training_enabled = TRAINING_AVAILABLE

        if self.institutional_enabled:
            AgentRewardSystem.load()

        # Prediction tracking for ML feedback loop
        self._predictions = {}  # symbol -> {direction, price, confidence, timestamp}

        self.logger = logging.getLogger("MasterCoordinator")
        self.logger.info(
            f"Agents loaded: Oracle ✓ | Brain ✓ | Shield ✓ | "
            f"Institutional {'✓' if self.institutional_enabled else '✗'} | "
            f"Geopolitical {'✓' if self.geopolitical_enabled else '✗'} | "
            f"Training {'✓' if self.training_enabled else '✗'}"
        )
        
    def run_swarm(self):
        self.running = True
        signal.signal(signal.SIGINT, self.stop)

        print_banner()
        self.logger.info("Initializing 80% Win Rate AI Trading Swarm...")
        self.logger.info(f"Target Assets: {', '.join(settings.TRADING_PAIRS)}")

        # === ENHANCEMENT 5: Check for aged positions at startup ===
        _check_aged_positions(self.mt5)

        self._scan_count = 0
        self._last_health_log = time.time()

        while self.running:
            try:
                self.logger.info("Coordinator: Initiating Market Scan Cycle...")
                self._scan_count += 1

                # Periodic health check every 50 scans (~8 min)
                if self._scan_count % 50 == 0 or (time.time() - self._last_health_log > 600):
                    self._log_health()

                # === ENHANCEMENT 4: Monitor and trail open positions every scan ===
                self.shield.monitor_and_trail_positions()

                # Check if executor has hit its failure circuit breaker
                if hasattr(self.executor, 'consecutive_failures') and \
                   self.executor.consecutive_failures >= self.executor.max_consecutive_failures:
                    self.logger.warning(
                        f"Coordinator: Executor circuit breaker active "
                        f"({self.executor.consecutive_failures} consecutive failures). "
                        f"Sleeping 5 min before reset."
                    )
                    time.sleep(300)  # 5 min cooldown
                    self.executor.consecutive_failures = 0  # Reset and retry
                    continue

                for symbol in settings.TRADING_PAIRS:
                    if not self.running:
                        break
                    try:
                        # === ENHANCEMENT 2: SESSION FILTER ===
                        is_allowed, session_name, confidence_boost = is_high_liquidity_session(symbol)
                        if not is_allowed:
                            self.logger.debug(
                                f"Coordinator: {symbol} skipped — {session_name}. Only trading high-liquidity sessions."
                            )
                            continue

                        self.logger.info(f"Coordinator: Scanning {symbol} during {session_name} session...")

                        # Fetch M15 and H4 for main signal, plus M5 for momentum confirmation
                        df_entry, df_trend = self.oracle.fetch_market_context(symbol, 'M15', 'H4')
                        df_m5 = self.data_fetcher.refresh_data(symbol, 'M5')

                        # === ENHANCEMENT: VOLATILITY REGIME FILTER ===
                        # Skip trading when ATR is extremely low (range-bound market = many false signals)
                        # Uses last 50 candles ATR vs last 200 candles ATR to detect contraction
                        if df_entry is not None and len(df_entry) >= 200:
                            try:
                                atr_col = 'atr' if 'atr' in df_entry.columns else None
                                if atr_col is None and 'high' in df_entry.columns and 'low' in df_entry.columns:
                                    # Calculate simple ATR from high-low range
                                    recent_range = (df_entry['high'] - df_entry['low']).tail(50).mean()
                                    long_range = (df_entry['high'] - df_entry['low']).tail(200).mean()
                                else:
                                    recent_range = df_entry[atr_col].tail(50).mean() if atr_col else 0
                                    long_range = df_entry[atr_col].tail(200).mean() if atr_col else 0

                                if long_range > 0 and (recent_range / long_range) < 0.25:
                                    self.logger.debug(
                                        f"Coordinator: {symbol} — volatility squeeze detected "
                                        f"(short ATR={recent_range:.5f} / long ATR={long_range:.5f} = "
                                        f"{recent_range/long_range:.2f}). Skipping to avoid false signals."
                                    )
                                    continue
                            except Exception:
                                pass  # If calculation fails, proceed normally

                        signal_data = self.brain.analyze_opportunity(
                            symbol, df_entry, df_trend, 'M15', df_m5=df_m5
                        )

                        if signal_data:
                            # === ENHANCEMENT: CORRELATION FILTER ===
                            # Check if we already have an open position in a correlated pair
                            sig_dir = signal_data.get('direction', '')
                            if _check_correlation_conflict(symbol, sig_dir):
                                self.logger.info(
                                    f"Coordinator: {symbol} {sig_dir} skipped — correlated pair already open. "
                                    f"Avoiding doubled exposure."
                                )
                                continue

                            # === INSTITUTIONAL INTELLIGENCE LAYER ===
                            signal_data = self._apply_institutional_filters(symbol, signal_data, df_entry)

                            # If institutional layer killed the signal, skip
                            if signal_data is None:
                                continue

                            self.logger.info(f"Coordinator: High probability setup verified. Handing over to Shield.")
                            result = self.shield.execute_and_protect(signal_data)

                            # === ML FEEDBACK: Track prediction for later evaluation ===
                            self._track_prediction(symbol, signal_data)
                    except Exception as sym_err:
                        self.logger.warning(f"Coordinator: Error scanning {symbol}: {sym_err}")
                        continue

                # Evaluate past predictions on every scan cycle for timely ML feedback
                if self._scan_count % 5 == 0:
                    self._evaluate_predictions()

                time.sleep(settings.SCALP.get('scan_interval_seconds', 10))

            except Exception as cycle_err:
                self.logger.error(f"Coordinator: Scan cycle error — {cycle_err}. Retrying in 30s...")
                time.sleep(30)

    def _apply_institutional_filters(self, symbol: str, signal_data: dict, df_entry=None) -> Optional[dict]:
        """
        Run institutional intelligence agents on the signal. Returns modified signal_data
        with adjusted confidence, or None if the signal should be blocked.
        """
        sig_dir = signal_data.get('direction', '')
        base_confidence = signal_data.get('confidence', 50)
        adj_confidence = base_confidence
        reasons = []

        # --- 1. ECONOMIC CALENDAR CHECK (highest priority — can BLOCK) ---
        if self.institutional_enabled:
            try:
                cal_result = EconomicCalendarAgent.check_events(symbol)
                if cal_result and not cal_result.get('safe_to_trade', True):
                    event_name = cal_result.get('next_event', 'high-impact event')
                    mins = cal_result.get('minutes_until', '?')
                    self.logger.warning(
                        f"BLOCKED by EconomicCalendarAgent: {symbol} — "
                        f"{event_name} in {mins} min. Skipping trade."
                    )
                    AgentCommunicationBus.post(
                        "EconomicCalendar", symbol, "BLOCK", "NEUTRAL",
                        95, f"High-impact event {event_name} in {mins} min"
                    )
                    return None
            except Exception as e:
                self.logger.debug(f"EconomicCalendar check failed: {e}")

        # --- 2. GEOPOLITICAL RISK ADJUSTMENT ---
        if self.geopolitical_enabled:
            try:
                geo_result = GeopoliticalRiskAgent.get_symbol_adjustment(symbol)
                if geo_result and geo_result.get('wars_count', 0) > 0:
                    geo_dir = geo_result.get('direction', 'NEUTRAL')
                    geo_adj = geo_result.get('confidence_adj', 0)
                    if geo_dir != 'NEUTRAL':
                        if geo_dir == sig_dir:
                            # War bias confirms our direction — boost confidence
                            adj_confidence += geo_adj
                            reasons.append(f"Geopolitical +{geo_adj} ({geo_result.get('wars_count')} conflicts favor {geo_dir})")
                        else:
                            # War bias conflicts — reduce confidence
                            adj_confidence -= geo_adj
                            reasons.append(f"Geopolitical -{geo_adj} (conflicts favor opposite direction)")
                    self.logger.info(
                        f"GeopoliticalAgent: {symbol} — {geo_result.get('wars_count')} active conflicts, "
                        f"bias={geo_dir}, adj={geo_adj}"
                    )
            except Exception as e:
                self.logger.debug(f"Geopolitical check failed: {e}")

        # --- 3. INSTITUTIONAL FLOW ANALYSIS ---
        if self.institutional_enabled:
            try:
                flow_result = InstitutionalFlowAgent.analyze(symbol, df_h1=df_entry)
                if flow_result:
                    flow_bias = flow_result.get('bias', 'NEUTRAL')
                    flow_conf = flow_result.get('confidence', 50)
                    if flow_bias != 'NEUTRAL' and flow_conf > 60:
                        if flow_bias == sig_dir:
                            boost = min(int((flow_conf - 50) * 0.3), 10)
                            adj_confidence += boost
                            reasons.append(f"InstitutionalFlow +{boost} (COT/volume confirms {flow_bias})")
                        else:
                            penalty = min(int((flow_conf - 50) * 0.2), 8)
                            adj_confidence -= penalty
                            reasons.append(f"InstitutionalFlow -{penalty} (COT/volume opposes)")
            except Exception as e:
                self.logger.debug(f"InstitutionalFlow check failed: {e}")

        # --- 4. CROSS-MARKET CORRELATION ---
        if self.institutional_enabled:
            try:
                cross_result = CrossMarketAgent.analyze(symbol)
                if cross_result:
                    cross_bias = cross_result.get('bias', 'NEUTRAL')
                    cross_conf = cross_result.get('confidence', 50)
                    if cross_bias != 'NEUTRAL' and cross_conf > 55:
                        if cross_bias == sig_dir:
                            boost = min(int((cross_conf - 50) * 0.2), 6)
                            adj_confidence += boost
                            reasons.append(f"CrossMarket +{boost} (DXY/VIX confirms)")
                        else:
                            penalty = min(int((cross_conf - 50) * 0.15), 5)
                            adj_confidence -= penalty
                            reasons.append(f"CrossMarket -{penalty} (DXY/VIX opposes)")
            except Exception as e:
                self.logger.debug(f"CrossMarket check failed: {e}")

        # --- 5. WEB RESEARCH SENTIMENT ---
        if self.institutional_enabled:
            try:
                web_result = WebResearchAgent.research(symbol)
                if web_result and web_result.get('total_articles', 0) >= 3:
                    web_sent = web_result.get('sentiment', 'NEUTRAL')
                    web_conf = web_result.get('confidence', 50)
                    if web_sent != 'NEUTRAL' and web_conf > 55:
                        if web_sent == sig_dir:
                            boost = min(int((web_conf - 50) * 0.15), 5)
                            adj_confidence += boost
                            reasons.append(f"WebSentiment +{boost} ({web_result.get('total_articles')} articles favor {web_sent})")
                        else:
                            penalty = min(int((web_conf - 50) * 0.1), 4)
                            adj_confidence -= penalty
                            reasons.append(f"WebSentiment -{penalty} (news opposes)")
            except Exception as e:
                self.logger.debug(f"WebResearch check failed: {e}")

        # --- 6. AGENT REWARD MULTIPLIER ---
        if self.institutional_enabled:
            try:
                multiplier = AgentRewardSystem.get_multiplier("MasterCoordinator")
                if multiplier != 1.0:
                    adj_confidence = int(adj_confidence * multiplier)
                    reasons.append(f"RewardMultiplier x{multiplier:.2f}")
            except Exception as e:
                self.logger.debug(f"RewardSystem check failed: {e}")

        # --- 7. CONSENSUS CHECK (if agents posted to bus) ---
        if self.institutional_enabled:
            try:
                consensus = AgentCommunicationBus.get_consensus(symbol)
                if consensus and consensus.get('blocked', False):
                    block_reasons = consensus.get('reasons', [])
                    self.logger.warning(
                        f"BLOCKED by agent consensus: {symbol} — {'; '.join(block_reasons)}"
                    )
                    return None
            except Exception as e:
                self.logger.debug(f"Consensus check failed: {e}")

        # Clamp confidence to valid range
        adj_confidence = max(10, min(95, adj_confidence))

        if reasons:
            self.logger.info(
                f"Institutional layer: {symbol} {sig_dir} confidence "
                f"{base_confidence} → {adj_confidence} | {'; '.join(reasons)}"
            )

        signal_data['confidence'] = adj_confidence
        signal_data['institutional_reasons'] = reasons
        return signal_data

    def _track_prediction(self, symbol: str, signal_data: dict):
        """Record a trade prediction for ML feedback evaluation."""
        try:
            sig_dir = signal_data.get('direction', '')
            price = signal_data.get('entry_price', signal_data.get('price', 0))
            confidence = signal_data.get('confidence', 50)
            self._predictions[symbol] = {
                'direction': sig_dir,
                'price': price,
                'confidence': confidence,
                'timestamp': datetime.utcnow().isoformat(),
            }

            # Record to training engine if available
            if self.training_enabled:
                try:
                    TrainingEngine.load()
                    trade_entry = {
                        "symbol": symbol,
                        "direction": sig_dir,
                        "score": signal_data.get('score', 0),
                        "confidence": confidence,
                        "hour_utc": datetime.utcnow().hour,
                        "entry_time": datetime.utcnow().isoformat(),
                        "source": "swarm_execution",
                        "institutional_reasons": signal_data.get('institutional_reasons', []),
                    }
                    TrainingEngine._data.setdefault("trades", []).append(trade_entry)
                    TrainingEngine.save()
                except Exception as te:
                    self.logger.debug(f"Training record failed: {te}")
        except Exception as e:
            self.logger.debug(f"Prediction tracking failed: {e}")

    def _evaluate_predictions(self):
        """Evaluate past predictions against current prices for ML feedback."""
        if not self._predictions:
            return
        try:
            for symbol, pred in list(self._predictions.items()):
                try:
                    df = self.data_fetcher.refresh_data(symbol, 'M15')
                    if df is None or df.empty:
                        continue
                    current_price = float(df['close'].iloc[-1])
                    entry_price = pred['price']
                    if entry_price <= 0:
                        continue

                    pct_move = (current_price - entry_price) / entry_price * 100
                    min_move = 0.30 if symbol in ('BTCUSD', 'ETHUSD') else 0.15

                    if abs(pct_move) < min_move:
                        continue  # Not enough movement to evaluate

                    direction = pred['direction']
                    is_correct = (direction == 'BUY' and pct_move > 0) or \
                                 (direction == 'SELL' and pct_move < 0)

                    # Record outcome to training engine
                    if self.training_enabled:
                        try:
                            TrainingEngine.record_outcome(
                                symbol=symbol, direction=direction,
                                is_win=is_correct,
                                pnl=round(abs(pct_move) * 0.5 if is_correct else -(abs(pct_move) * 0.5), 2)
                            )
                            self.logger.info(
                                f"ML FEEDBACK: {symbol} {direction} → "
                                f"{'CORRECT' if is_correct else 'WRONG'} ({pct_move:+.2f}%)"
                            )
                        except Exception:
                            pass

                    # Record to reward system
                    if self.institutional_enabled:
                        try:
                            AgentRewardSystem.record_trade_result(
                                symbol=symbol, direction=direction,
                                is_profit=is_correct,
                                agents_involved=["MasterCoordinator", "VertexStrategy", "ExecutionShield"]
                            )
                        except Exception:
                            pass

                    # Remove evaluated prediction
                    del self._predictions[symbol]

                except Exception:
                    continue
        except Exception as e:
            self.logger.debug(f"Prediction evaluation failed: {e}")

    def _log_health(self):
        """Periodic health check — logs account balance, scan stats, and open positions."""
        try:
            account = self.mt5.get_account_info()
            balance = account.get('balance', 'N/A') if account else 'N/A'
            equity = account.get('equity', 'N/A') if account else 'N/A'
            profit = account.get('profit', 0) if account else 0
            exec_failures = getattr(self.executor, 'consecutive_failures', 0)

            # Count open positions
            import MetaTrader5 as _mt5_health
            positions = _mt5_health.positions_get()
            open_count = len(positions) if positions else 0

            self.logger.info(
                f"HEALTH: scans={self._scan_count} | balance=${balance} | equity=${equity} | "
                f"unrealized_pnl=${profit} | open_positions={open_count} | "
                f"no_money_paused={self.shield._no_money_pause_until is not None} | "
                f"exec_failures={exec_failures} | "
                f"trailing_cache={len(self.shield._position_atr_cache)}"
            )
            self._last_health_log = time.time()

            # === ENHANCEMENT: BRAIN TRAINING (accelerated 2026-03-31) ===
            # Every 100 scans (~15 min), train feature weights from trade history
            # Accelerated from 200 scans to learn faster from recent outcomes
            if self._scan_count % 100 == 0:
                try:
                    brain = get_brain()
                    result = brain.train_feature_weights()
                    if result:
                        self.logger.info(
                            f"BRAIN TRAINED: {result['trades_analyzed']} trades analyzed, "
                            f"win rate={result['overall_win_rate']*100:.1f}%"
                        )
                except Exception as brain_err:
                    self.logger.debug(f"Brain training skipped: {brain_err}")

            # === ML FEEDBACK: Evaluate past predictions every 25 scans ===
            if self._scan_count % 25 == 0:
                self._evaluate_predictions()

            # === GEOPOLITICAL SCAN: Update war/conflict status every 50 scans ===
            if self.geopolitical_enabled and self._scan_count % 50 == 0:
                try:
                    geo_status = GeopoliticalRiskAgent.scan()
                    active_wars = sum(1 for w in geo_status.values()
                                      if isinstance(w, dict) and w.get('status') == 'ACTIVE')
                    self.logger.info(f"GEOPOLITICAL: {active_wars} active conflicts monitored")
                except Exception as geo_err:
                    self.logger.debug(f"Geopolitical scan skipped: {geo_err}")

            # === INSTITUTIONAL: Log agent reward standings every 200 scans ===
            if self.institutional_enabled and self._scan_count % 200 == 0:
                try:
                    report = AgentCommunicationBus.report()
                    if report:
                        self.logger.info(f"AGENT BUS: {report[:200]}")
                except Exception:
                    pass

        except Exception as e:
            self.logger.debug(f"Health check failed: {e}")

    def stop(self, signum, frame):
        self.logger.info("Coordinator: Shutting down AI Swarm...")
        self.running = False


if __name__ == "__main__":
    MAX_RESTARTS = 100  # Increased from 10 for 24/7 uptime — auto-restarts after crashes
    restart_count = 0
    while restart_count < MAX_RESTARTS:
        try:
            coordinator = MasterCoordinatorAgent()
            coordinator.run_swarm()
            break  # clean exit
        except SystemExit:
            break
        except KeyboardInterrupt:
            break
        except Exception as e:
            restart_count += 1
            logger.error(f"FATAL CRASH #{restart_count}: {e}. Restarting in 60s...")
            time.sleep(60)
