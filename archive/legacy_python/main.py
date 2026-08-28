"""
GOLD SCALPING BOT - Main Entry Point (LEGACY)
=======================================
⚠️  LEGACY ENTRYPOINT — replaced 2026-04-20 by v14 TrendMaster stack
   (AI_SUPERBB_v14_TrendMaster.mq5 + ai_trading_agents/trend_master_brain.py).
   Kept for reference; disabled by default to prevent signal collision with
   the new system (same magic number, same symbol).

   Set env var  ALLOW_LEGACY_MAIN=1  to force-enable this old bot.

Automated XAUUSD Trading System on M15/M30/H1/H4 with spike detection.
Targets 7-8 trades/day, 85% win rate, trailing stop loss.

Usage:
    python main.py              # Refuses to start unless ALLOW_LEGACY_MAIN=1
    python main.py --demo       # Demo mode (still gated)
    python main.py --scan       # Single scan (gated)
"""

import argparse
import os
import time
import signal
import sys
import asyncio
from datetime import datetime, timedelta
from typing import Dict, Optional
import logging

import pandas as pd

# ── LEGACY GUARD (v14 TrendMaster, 2026-04-20) ─────────────────────────────
# This file used to be the live entrypoint. It would open trades with the
# same magic number as the new v14 EA (AI_SUPERBB_v14_TrendMaster.mq5) and
# the new Python brain (ai_trading_agents/trend_master_brain.py). Running
# both simultaneously caused conflicting orders, partial fills, and was a
# core reason for the 36.4% backtest accuracy. This guard lets the user
# opt back in if they really want, but refuses to start by default.
if os.getenv('ALLOW_LEGACY_MAIN', '0') != '1':
    print("=" * 70)
    print("  LEGACY main.py is DISABLED (v14 TrendMaster replaced it 2026-04-20)")
    print("  Use this entrypoint instead:")
    print("     python ai_trading_agents/trend_master_brain.py")
    print("  To force-enable legacy (NOT recommended):")
    print("     set ALLOW_LEGACY_MAIN=1   &&   python main.py")
    print("=" * 70)
    sys.exit(0)

# Add project root to path
sys.path.insert(0, '.')

from config import settings
from src.data_fetcher import MT5Connection, DataFetcher, initialize_mt5
from src.indicators import AMDAnalyzer
from src.strategy import GoldScalpStrategy, MultiPairStrategy
from src.risk_manager import RiskManager
from src.order_executor import OrderExecutor
from src.brain import get_brain, TradingBrain
from src.utils import (
    setup_logging, print_banner, is_trading_session,
    get_next_candle_time, save_state, load_state, log_trade
)
from src.telegram_notifier import TelegramNotifier


def _tg_send(notifier: 'TelegramNotifier', coro):
    """Helper: run async Telegram send without crashing if event loop unavailable."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            loop.create_task(coro)
        else:
            loop.run_until_complete(coro)
    except Exception:
        pass


class GoldScalpingBot:
    """
    Gold Scalping Bot - Multi-Timeframe
    ======================================
    Scans XAUUSD on M15, M30, H1, H4 simultaneously for entries.
    Uses fast EMAs + RSI(7) + Volume + SMC for high-probability trades.
    Trailing stop: scales with entry timeframe.
    """

    def __init__(self, demo_mode: bool = True):
        self.demo_mode = demo_mode
        self.running = False

        # Components
        self.mt5: Optional[MT5Connection] = None
        self.data_fetcher: Optional[DataFetcher] = None
        self.risk_manager: Optional[RiskManager] = None
        self.strategy: Optional[MultiPairStrategy] = None
        self.executor: Optional[OrderExecutor] = None

        # Telegram Notifier
        self.telegram = TelegramNotifier()

        # State
        self.last_scan_time: Optional[datetime] = None
        self.last_trade_time: Optional[datetime] = None
        # Per-timeframe duplicate signal protection
        self.last_signal_candle_time: Dict[str, Optional[datetime]] = {}
        self.scan_count = 0
        self.signals_generated = 0
        self.trades_executed = 0

        # Trade recorder (statistics only — no decision influence)
        self.brain: TradingBrain = get_brain()
        self.tracked_positions: Dict[int, Dict] = {}

        # Logging
        self.logger = setup_logging(
            settings.LOGGING['log_level'],
            settings.LOGGING['log_file']
        )

    def initialize(self) -> bool:
        """Initialize bot, connect to MT5."""
        print_banner()
        self.logger.info("Initializing Gold Scalping Bot...")
        self.logger.info(f"Mode: {'DEMO' if self.demo_mode else 'LIVE'}")

        self.mt5 = initialize_mt5()
        if self.mt5 is None:
            self.logger.error("Failed to connect to MT5")
            self._print_connection_help()
            return False

        account = self.mt5.get_account_info()
        if not account:
            self.logger.error("Failed to get account info")
            return False

        self.logger.info(f"Connected - Balance: ${account['balance']:.2f}, Leverage: 1:{account['leverage']}")

        self.data_fetcher = DataFetcher(self.mt5)
        self.risk_manager = RiskManager(account['balance'])
        self.strategy = MultiPairStrategy(
            pairs=settings.TRADING_PAIRS,
            risk_manager=self.risk_manager
        )
        self.executor = OrderExecutor()

        state = load_state()
        if state:
            self.logger.info("Previous session state loaded")

        self.logger.info(f"Trading: {', '.join(settings.TRADING_PAIRS)}")
        entry_tfs = list(getattr(settings, 'ENTRY_TIMEFRAMES', {'M15': {}}).keys())
        self.logger.info(f"Entry Timeframes: {', '.join(entry_tfs)}")
        self.logger.info(f"Max trades/day: {settings.RISK.get('max_trades_per_day', 8)}")
        self.logger.info("Initialization complete!")
        return True

    def _print_connection_help(self):
        print("\n" + "=" * 60)
        print("CONNECTION FAILED - TROUBLESHOOTING:")
        print("=" * 60)
        print("1. Make sure MetaTrader 5 is installed and running")
        print("2. Open an OctaFX-Demo account in MT5")
        print("3. Set credentials in config/.env")
        print("4. Run again: python main.py")
        print("=" * 60 + "\n")

    def run(self):
        """Main scalping loop - scans every 10 seconds."""
        if not self.initialize():
            return

        self.running = True
        signal.signal(signal.SIGINT, self._shutdown_handler)
        signal.signal(signal.SIGTERM, self._shutdown_handler)

        SCAN_INTERVAL = settings.SCALP.get('scan_interval_seconds', 10)
        self.logger.info(f"Starting scalp loop (every {SCAN_INTERVAL}s)...")
        print(f"\nBot scanning every {SCAN_INTERVAL}s. Press Ctrl+C to stop.\n")

        try:
            while self.running:
                self._scalp_cycle()

                sleep_remaining = SCAN_INTERVAL
                while sleep_remaining > 0 and self.running:
                    time.sleep(min(3, sleep_remaining))
                    sleep_remaining -= 3
        except Exception as e:
            self.logger.error(f"Error in main loop: {e}")
            raise
        finally:
            self.shutdown()

    def _scalp_cycle(self):
        """One scalp cycle: fetch data from ALL entry timeframes, analyze, trade, trail."""
        self.scan_count += 1
        self.last_scan_time = datetime.now()

        if self.scan_count % 10 == 1:  # Log header every 10 scans
            self.logger.info(f"\n{'='*50}")
            self.logger.info(f"SCAN #{self.scan_count} - {self.last_scan_time.strftime('%H:%M:%S')}")
            self.logger.info(f"{'='*50}")

        # Check risk limits
        can_trade = self.risk_manager.can_trade()
        if not can_trade['allowed']:
            if self.scan_count % 30 == 1:
                self.logger.warning(f"Trading paused: {can_trade['reason']}")
            # Still manage existing positions even if can't open new ones
            open_positions = self.mt5.get_open_positions()
            if open_positions:
                self._manage_positions(open_positions)
            return

        # Update account info (every 5th scan to reduce load)
        if self.scan_count % 5 == 1:
            account = self.mt5.get_account_info()
            if account:
                self.risk_manager.update_account(account['balance'], account['equity'])

        # Get open positions
        open_positions = self.mt5.get_open_positions()

        # ALWAYS manage positions (trailing stop)
        self._manage_positions(open_positions)

        # Check for closed trades and learn
        self._check_closed_trades_and_learn(open_positions)

        # Check max open trades (use both MT5 positions AND tracked to prevent race condition)
        max_open = settings.RISK.get('max_open_trades', 2)
        tracked_count = len(self.tracked_positions)
        if len(open_positions) >= max_open or tracked_count >= max_open:
            return

        # ANTI-HEDGE: Don't open opposite direction to existing positions
        existing_dirs = set()
        for pos in open_positions:
            if pos.get('magic') == settings.ORDER['magic_number']:
                existing_dirs.add(pos.get('type', ''))

        # Scan for scalp signals using strategy module
        signals = self._scan_scalp_signals()
        if not signals:
            return

        # Get symbol info for all signals
        symbol_infos = {}
        for result in signals:
            symbol = result.get('signal', {}).get('symbol')
            if symbol and symbol not in symbol_infos:
                symbol_infos[symbol] = self.mt5.get_symbol_info(symbol)

        # Get best signal (spikes prioritized)
        best_signal = self.strategy.get_best_signal(signals, symbol_infos, open_positions)
        if not best_signal:
            return

        # ANTI-HEDGE: Block if opposite direction already open on same symbol
        sig_dir = best_signal['direction']
        opposite = 'SELL' if sig_dir == 'BUY' else 'BUY'
        if opposite in existing_dirs:
            self.logger.info(f"Anti-hedge: Blocked {sig_dir} — {opposite} already open")
            return

        # PURE STRATEGY: Execute directly — no brain/sentiment gate
        # Extract features for trade recording/statistics only
        m5_last = None
        m5_df = None
        for result in signals:
            if result.get('signal', {}).get('symbol') == best_signal['symbol']:
                m5_last = result.get('m5_last')
                m5_df = result.get('m5_df')
                break

        features = self._extract_features(best_signal, m5_last=m5_last, m5_df=m5_df)
        features['symbol'] = best_signal['symbol']
        features['direction'] = best_signal['direction']

        score = best_signal.get('bull_score', 0) if best_signal['direction'] == 'BUY' else best_signal.get('bear_score', 0)
        self.logger.info(f"PURE STRATEGY: {best_signal['direction']} {best_signal['symbol']} score={score}")

        self._execute_trade(best_signal, symbol_infos.get(best_signal['symbol'], {}), features)

    def _scan_scalp_signals(self):
        """
        MULTI-TIMEFRAME ENTRY SCANNER
        ================================
        Scans M15, M30, H1, H4 simultaneously for entry signals.
        Each TF uses its own higher-TF trend context:
          M15 → H4 trend    M30 → H4 trend
          H1  → H4 trend    H4  → D1 trend

        Picks the best signal across all timeframes.
        Same confluence scoring and entry logic per TF.

        ATR-based trailing parameters passed from config per timeframe.
        Session bonus: London-NY overlap (12-16 UTC) reduces required confluences by 1.
        """
        signals = []
        analyzer = AMDAnalyzer()
        min_confluences = getattr(settings, 'SCALP', {}).get('min_confluences', 3)
        min_confluences_spike = getattr(settings, 'SCALP', {}).get('min_confluences_spike', 3)
        entry_timeframes = getattr(settings, 'ENTRY_TIMEFRAMES', {'M15': {'trend_tf': 'H4', 'min_candles': 60, 'candle_seconds': 900, 'tf_multiplier': 1.5, 'max_candles_in_trade': 16}})

        # Session bonus detection (London-NY overlap: 12-16 UTC)
        hour_utc = datetime.utcnow().hour
        session_bonus = 1 if 12 <= hour_utc < 16 else 0

        for symbol in settings.TRADING_PAIRS:
            # Cache trend TF data to avoid re-fetching (multiple entry TFs may share a trend TF)
            trend_cache = {}  # trend_tf -> (trend_bull, trend_bear)

            for entry_tf, tf_config in entry_timeframes.items():
                try:
                    trend_tf = tf_config.get('trend_tf', 'H1')
                    min_candles = tf_config.get('min_candles', 60)

                    # Fetch entry TF data
                    df_entry = self.data_fetcher.refresh_data(symbol, entry_tf)
                    if df_entry is None or df_entry.empty or len(df_entry) < min_candles:
                        continue

                    # Analyze entry TF with AMDAnalyzer
                    entry_analyzed = analyzer.analyze(df_entry)
                    last = entry_analyzed.iloc[-1]

                    # --- DUPLICATE SIGNAL PROTECTION (per-TF) ---
                    try:
                        candle_time = entry_analyzed.index[-1]
                        last_candle = self.last_signal_candle_time.get(entry_tf)
                        if last_candle and candle_time <= last_candle:
                            continue
                    except Exception:
                        pass

                    # Get trend TF data (cached across entry TFs)
                    h_trend_bull = False
                    h_trend_bear = False
                    if trend_tf in trend_cache:
                        h_trend_bull, h_trend_bear = trend_cache[trend_tf]
                    else:
                        try:
                            df_trend = self.data_fetcher.refresh_data(symbol, trend_tf)
                            if df_trend is not None and not df_trend.empty and len(df_trend) >= 30:
                                trend_analyzed = analyzer.analyze(df_trend)
                                trend_last = trend_analyzed.iloc[-1]
                                h_trend_bull = bool(trend_last.get('scalp_trend_bull', False))
                                h_trend_bear = bool(trend_last.get('scalp_trend_bear', False))
                            trend_cache[trend_tf] = (h_trend_bull, h_trend_bear)
                        except Exception as e:
                            self.logger.debug(f"{trend_tf} data unavailable for {symbol}: {e}")
                            trend_cache[trend_tf] = (False, False)

                    # Read raw scores from analyzer
                    bull_score = int(last.get('scalp_bull_score', 0))
                    bear_score = int(last.get('scalp_bear_score', 0))
                    entry_trend_bull = bool(last.get('scalp_trend_bull', False))
                    entry_trend_bear = bool(last.get('scalp_trend_bear', False))

                    # Spike detection
                    spike_up = bool(last.get('spike_up', False))
                    spike_down = bool(last.get('spike_down', False))
                    signal_dir = None
                    is_spike_entry = False

                    # --- MODE 1: SPIKE CATCH (requires score >= min_confluences_spike for quality) ---
                    if spike_up and bull_score >= min_confluences_spike:
                        signal_dir = 'BUY'
                        is_spike_entry = True
                    elif spike_down and bear_score >= min_confluences_spike:
                        signal_dir = 'SELL'
                        is_spike_entry = True

                    # --- MODE 2: TREND SCALP (higher-TF trend ALWAYS REQUIRED) ---
                    # Apply session bonus during London-NY overlap
                    effective_min_confluences = max(1, min_confluences - session_bonus)

                    if signal_dir is None:
                        if bull_score >= effective_min_confluences and entry_trend_bull and h_trend_bull:
                            signal_dir = 'BUY'

                    if signal_dir is None:
                        if bear_score >= effective_min_confluences and entry_trend_bear and h_trend_bear:
                            signal_dir = 'SELL'

                    if not signal_dir:
                        continue

                    # Generate signal with SL/TP
                    atr = float(last.get('atr', 2.0))
                    entry_price = float(last['close'])
                    sl_mult = 1.0 if is_spike_entry else settings.RISK['default_sl_atr_multiple']
                    rr = settings.RISK['min_risk_reward']

                    if signal_dir == 'BUY':
                        stop_loss = entry_price - (atr * sl_mult)
                    else:
                        stop_loss = entry_price + (atr * sl_mult)

                    risk_distance = abs(entry_price - stop_loss)
                    if signal_dir == 'BUY':
                        take_profit = entry_price + (risk_distance * rr)
                    else:
                        take_profit = entry_price - (risk_distance * rr)

                    score = bull_score if signal_dir == 'BUY' else bear_score
                    mode = "SPIKE" if is_spike_entry else "SCALP"
                    h_ok = (signal_dir == 'BUY' and h_trend_bull) or (signal_dir == 'SELL' and h_trend_bear)

                    sig = {
                        'symbol': symbol,
                        'direction': signal_dir,
                        'entry_price': round(entry_price, 2),
                        'stop_loss': round(stop_loss, 2),
                        'take_profit': round(take_profit, 2),
                        'atr': atr,
                        'risk_reward': round(rr, 2),
                        'is_spike': is_spike_entry,
                        'timestamp': datetime.now(),
                        'reason': f"{mode} {signal_dir} {entry_tf} score={score} Trend({trend_tf})={'Y' if h_ok else 'N'}",
                        'h1_trend_bull': h_trend_bull,
                        'h1_trend_bear': h_trend_bear,
                        'bull_score': bull_score,
                        'bear_score': bear_score,
                        'entry_timeframe': entry_tf,
                        'trend_timeframe': trend_tf,
                        'tf_multiplier': tf_config.get('tf_multiplier', 1.0),
                        'max_candles_in_trade': tf_config.get('max_candles_in_trade', 20),
                        'candle_seconds': tf_config.get('candle_seconds', 300),
                        'breakeven_atr': tf_config.get('breakeven_atr', 0.5),
                        'activation_atr': tf_config.get('activation_atr', 0.8),
                        'trail_atr': tf_config.get('trail_atr', 0.4),
                    }

                    result = {
                        'symbol': symbol,
                        'signal': sig,
                        'current_phase': 'scalp',
                        'atr': atr,
                        'm5_last': last,
                        'm5_df': entry_analyzed,
                    }
                    signals.append(result)

                    self.logger.info(
                        f"[{mode}] {signal_dir} {symbol} {entry_tf} @ {entry_price:.2f} "
                        f"Score:{score} RR:{rr:.1f} Trend({trend_tf}):{'Y' if h_ok else 'N'}"
                    )

                except Exception as e:
                    self.logger.error(f"Error scanning {symbol} {entry_tf}: {e}")

        return signals

    def _extract_features(self, signal: Dict, m5_last: pd.Series = None, m5_df: pd.DataFrame = None) -> Dict:
        """
        Extract REAL features from signal and M5 analyzed data for brain learning.
        Uses rolling lookback (last 10 candles) for event-based features like FVG,
        structure shift, and liquidity sweep since they may not fire on the exact last candle.
        """
        features = {
            'trend_aligned': False,
            'liquidity_sweep': False,
            'structure_shift': False,
            'order_block': False,
            'fvg': False,
            'ema_aligned': False,
            'candle_pattern': False,
            'rsi_optimal': False,
            'rsi_divergence': False,
            'volume_spike': False,
            'good_volatility': False,
            'session_london': False,
            'session_ny': False,
            'session_overlap': False,
            'session_asian': False,
        }

        if m5_last is not None:
            direction = signal.get('direction', '')

            # Rolling lookback: check last 5 M5 candles for event features (25 min window)
            lookback = 5
            recent = m5_df.iloc[-lookback:] if m5_df is not None and len(m5_df) >= lookback else None

            if direction == 'BUY':
                features['trend_aligned'] = bool(signal.get('h1_trend_bull', False))
                features['ema_aligned'] = bool(m5_last.get('scalp_trend_bull', False))

                # Event features: check rolling window (last 10 candles)
                if recent is not None:
                    features['liquidity_sweep'] = bool(recent['bullish_manipulation'].any()) if 'bullish_manipulation' in recent.columns else False
                    features['structure_shift'] = bool(
                        recent['bullish_bos'].any() if 'bullish_bos' in recent.columns else False or
                        recent['bullish_choch'].any() if 'bullish_choch' in recent.columns else False
                    )
                    features['order_block'] = bool(recent['bullish_ob'].any()) if 'bullish_ob' in recent.columns else False
                    features['fvg'] = bool(recent['bullish_fvg'].any()) if 'bullish_fvg' in recent.columns else False
                    features['candle_pattern'] = bool(
                        (recent.get('pin_bar_bullish', pd.Series(dtype=bool)).any()) or
                        (recent.get('engulfing_bullish', pd.Series(dtype=bool)).any()) or
                        (recent.get('hammer', pd.Series(dtype=bool)).any()) or
                        (recent.get('morning_star', pd.Series(dtype=bool)).any())
                    )
                    features['rsi_divergence'] = bool(recent['bullish_divergence'].any()) if 'bullish_divergence' in recent.columns else False
                    features['volume_spike'] = bool(recent['volume_spike'].any()) if 'volume_spike' in recent.columns else False
                else:
                    # Fallback to single candle
                    features['liquidity_sweep'] = bool(m5_last.get('bullish_manipulation', False))
                    features['structure_shift'] = bool(
                        m5_last.get('bullish_bos', False) or m5_last.get('bullish_choch', False)
                    )
                    features['order_block'] = bool(m5_last.get('bullish_ob', False))
                    features['fvg'] = bool(m5_last.get('bullish_fvg', False))
                    features['candle_pattern'] = bool(
                        m5_last.get('pin_bar_bullish', False) or
                        m5_last.get('engulfing_bullish', False) or
                        m5_last.get('hammer', False) or
                        m5_last.get('morning_star', False)
                    )
                    features['rsi_divergence'] = bool(m5_last.get('bullish_divergence', False))
                    features['volume_spike'] = bool(m5_last.get('volume_spike', False))
            else:
                features['trend_aligned'] = bool(signal.get('h1_trend_bear', False))
                features['ema_aligned'] = bool(m5_last.get('scalp_trend_bear', False))

                if recent is not None:
                    features['liquidity_sweep'] = bool(recent['bearish_manipulation'].any()) if 'bearish_manipulation' in recent.columns else False
                    features['structure_shift'] = bool(
                        recent['bearish_bos'].any() if 'bearish_bos' in recent.columns else False or
                        recent['bearish_choch'].any() if 'bearish_choch' in recent.columns else False
                    )
                    features['order_block'] = bool(recent['bearish_ob'].any()) if 'bearish_ob' in recent.columns else False
                    features['fvg'] = bool(recent['bearish_fvg'].any()) if 'bearish_fvg' in recent.columns else False
                    features['candle_pattern'] = bool(
                        (recent.get('pin_bar_bearish', pd.Series(dtype=bool)).any()) or
                        (recent.get('engulfing_bearish', pd.Series(dtype=bool)).any()) or
                        (recent.get('shooting_star', pd.Series(dtype=bool)).any()) or
                        (recent.get('evening_star', pd.Series(dtype=bool)).any())
                    )
                    features['rsi_divergence'] = bool(recent['bearish_divergence'].any()) if 'bearish_divergence' in recent.columns else False
                    features['volume_spike'] = bool(recent['volume_spike'].any()) if 'volume_spike' in recent.columns else False
                else:
                    features['liquidity_sweep'] = bool(m5_last.get('bearish_manipulation', False))
                    features['structure_shift'] = bool(
                        m5_last.get('bearish_bos', False) or m5_last.get('bearish_choch', False)
                    )
                    features['order_block'] = bool(m5_last.get('bearish_ob', False))
                    features['fvg'] = bool(m5_last.get('bearish_fvg', False))
                    features['candle_pattern'] = bool(
                        m5_last.get('pin_bar_bearish', False) or
                        m5_last.get('engulfing_bearish', False) or
                        m5_last.get('shooting_star', False) or
                        m5_last.get('evening_star', False)
                    )
                    features['rsi_divergence'] = bool(m5_last.get('bearish_divergence', False))
                    features['volume_spike'] = bool(m5_last.get('volume_spike', False))

            # Direction-independent features (current candle is fine)
            rsi_val = m5_last.get('rsi', 50)
            try:
                rsi_val = float(rsi_val)
            except Exception:
                rsi_val = 50
            features['rsi_optimal'] = bool(25 < rsi_val < 75)
            features['good_volatility'] = bool(m5_last.get('good_volatility', False))

            # Session detection for brain learning
            try:
                hour_utc = signal.get('timestamp', datetime.utcnow()).hour if hasattr(signal.get('timestamp', datetime.utcnow()), 'hour') else datetime.utcnow().hour
            except Exception:
                hour_utc = datetime.utcnow().hour
            features['session_asian'] = bool(0 <= hour_utc < 7)
            features['session_london'] = bool(7 <= hour_utc < 16)
            features['session_ny'] = bool(12 <= hour_utc < 21)
            features['session_overlap'] = bool(12 <= hour_utc < 16)

        return features

    def _execute_trade(self, signal: Dict, symbol_info: Dict, features: Dict = None):
        """
        Execute a scalp trade.
        CONFLUENCE RULE:
          - 2 indicator signals → 1 trade (normal lot)
          - 3+ indicator signals → 2 trades (2x lot = double position)
        """
        self.signals_generated += 1

        # Determine trade count from confluence score
        trade_count = signal.get('trade_count', 1)
        trade_label = signal.get('trade_label', signal['direction'])

        self.logger.info(
            f"Executing [{trade_label}]: {signal['direction']} {signal['symbol']} "
            f"@ {signal['entry_price']:.2f} SL:{signal['stop_loss']:.2f} "
            f"TP:{signal['take_profit']:.2f} RR:{signal['risk_reward']:.1f} "
            f"TRADES:{trade_count}"
        )

        position_size = self.strategy.strategy.calculate_position_size(signal, symbol_info)
        self.logger.info(f"  Lot size: {position_size} x {trade_count}")

        if position_size <= 0:
            self.logger.warning("Invalid position size, skipping")
            return

        mode = "SPIKE" if signal.get('is_spike') else "SCALP"
        entry_tf = signal.get('entry_timeframe', 'M5')

        # Execute trade_count times (1 or 2 depending on confluence)
        for trade_num in range(1, trade_count + 1):
            comment = f"{mode}_{entry_tf}_{signal['direction']}_T{trade_num}"
            result = self.executor.place_market_order(
                symbol=signal['symbol'],
                order_type=signal['direction'],
                volume=position_size,
                stop_loss=signal['stop_loss'],
                take_profit=signal['take_profit'],
                comment=comment
            )

            if not result['success']:
                self.logger.warning(f"  Trade {trade_num}/{trade_count} failed: {result.get('error','?')}")
                break  # Don't attempt 2nd trade if 1st failed

            self.trades_executed += 1
            self.last_trade_time = datetime.now()
            try:
                self.last_signal_candle_time[entry_tf] = signal.get('timestamp', datetime.now())
            except Exception:
                pass
            self.logger.info(
                f"  Trade {trade_num}/{trade_count} #{self.trades_executed} "
                f"executed! Ticket: {result['ticket']}"
            )

            # Telegram notification for each trade
            _tg_send(self.telegram, self.telegram.send_trade_opened(
                symbol=signal['symbol'],
                direction=signal['direction'],
                entry_price=result['price'],
                sl=signal['stop_loss'],
                tp=signal['take_profit'],
                lot_size=position_size,
            ))

            self.tracked_positions[result['ticket']] = {
                'symbol': signal['symbol'],
                'direction': signal['direction'],
                'entry_price': result['price'],
                'stop_loss': signal['stop_loss'],
                'take_profit': signal['take_profit'],
                'atr': signal.get('atr', 0),
                'features': features or {},
                'is_spike': signal.get('is_spike', False),
                'entry_time': datetime.now().isoformat(),
                'entry_timeframe': signal.get('entry_timeframe', 'M5'),
                'tf_multiplier': signal.get('tf_multiplier', 1.0),
                'max_candles_in_trade': signal.get('max_candles_in_trade', 20),
                'candle_seconds': signal.get('candle_seconds', 300),
                'volume': position_size,
                'partial_tp_taken': False,
                'breakeven_atr_mult': signal.get('breakeven_atr', 0.5),
                'activation_atr_mult': signal.get('activation_atr', 0.8),
                'trail_atr_mult': signal.get('trail_atr', 0.4),
                'trade_num': trade_num,
                'trade_count': trade_count,
            }

            self.risk_manager.record_trade(
                symbol=signal['symbol'],
                trade_type=signal['direction'],
                entry_price=result['price'],
                volume=position_size,
                stop_loss=signal['stop_loss'],
                take_profit=signal['take_profit'],
                ticket=result['ticket']
            )

        # Send summary if double trade
        if trade_count >= 2:
            _tg_send(self.telegram, self.telegram.send_alert(
                f"🔥 DOUBLE TRADE: {signal['direction']} {signal['symbol']} "
                f"[{trade_label}] — 2 positions opened!"
            ))
        return  # confluence-based multi-trade logic above handles everything

    def _manage_positions(self, positions: list):
        """
        MULTI-TIMEFRAME POSITION MANAGEMENT - ATR-BASED ADAPTIVE TRAILING
        ===================================================================
        Uses ATR-based dynamic trailing with per-timeframe multipliers.

        Four exit mechanisms:
        1. PARTIAL TP: Close 50% at 1:1 RR, move SL to breakeven+1pip
        2. BREAKEVEN: Move SL to entry+1pip after ATR*breakeven_atr distance
        3. TRAILING: ATR-based distance with step = atr * 0.1
        4. TIME EXIT: Only if NEGATIVE profit after max_candles

        For XAUUSD: 1 pip = $0.10 = 0.10 price movement.
        """
        trailing_enabled = settings.RISK.get('trailing_stop_enabled', True)
        if not trailing_enabled:
            return

        for pos in positions:
            if pos.get('magic') != settings.ORDER['magic_number']:
                continue

            symbol = pos['symbol']
            tick = self.mt5.get_live_tick(symbol)
            if not tick:
                continue

            current_price = tick['bid'] if pos['type'] == 'SELL' else tick['ask']
            entry = pos['open_price']
            sl = pos['sl']
            ticket = pos['ticket']

            # Get per-TF settings from tracked position
            tracked = self.tracked_positions.get(ticket, {})
            max_candles = tracked.get('max_candles_in_trade', settings.RISK.get('max_candles_in_trade', 15))
            candle_seconds = tracked.get('candle_seconds', 300)
            entry_tf = tracked.get('entry_timeframe', 'M5')
            atr = tracked.get('atr', 2.0)
            position_volume = tracked.get('volume', pos.get('volume', 0))

            # ATR-based trail parameters (stored at entry)
            breakeven_atr_mult = tracked.get('breakeven_atr_mult', 0.5)
            activation_atr_mult = tracked.get('activation_atr_mult', 0.8)
            trail_atr_mult = tracked.get('trail_atr_mult', 0.4)

            # Gold pip value
            if 'XAU' in symbol or 'GOLD' in symbol:
                pip_value = 0.10
            elif 'JPY' in symbol:
                pip_value = 0.01
            else:
                pip_value = 0.0001

            # Profit in pips
            if pos['type'] == 'BUY':
                profit_pips = (current_price - entry) / pip_value
            else:
                profit_pips = (entry - current_price) / pip_value

            # Calculate ATR-based distances
            breakeven_dist = atr * breakeven_atr_mult
            activation_dist = atr * activation_atr_mult
            trail_dist = atr * trail_atr_mult
            step_dist = atr * 0.1

            # Check if this is a spike trade
            is_spike = tracked.get('is_spike', False)

            # ====== 0. PARTIAL TAKE PROFIT AT 1:1 RR ======
            # Calculate 1R distance (entry to stop loss = risk distance)
            risk_dist = abs(entry - sl) / pip_value
            if risk_dist > 0:
                one_r_dist = risk_dist
                partial_tp_taken = tracked.get('partial_tp_taken', False)

                if not partial_tp_taken and profit_pips >= one_r_dist:
                    # Close 50% of position
                    partial_volume = position_volume * 0.5
                    self.logger.info(
                        f"[PARTIAL TP] {ticket} ({entry_tf}): Closing 50% ({partial_volume:.2f}) at 1:1 RR | +{profit_pips:.0f} pips"
                    )
                    self.executor.close_position(ticket, partial_volume=partial_volume)
                    tracked['partial_tp_taken'] = True

                    # Move SL to breakeven (entry + 1 pip)
                    if pos['type'] == 'BUY':
                        be_sl = entry + (1 * pip_value)
                    else:
                        be_sl = entry - (1 * pip_value)
                    be_sl = round(be_sl, 2) if 'XAU' in symbol else round(be_sl, 5)
                    self.logger.info(
                        f"[PARTIAL SL] {ticket} ({entry_tf}): SL {sl:.2f} -> {be_sl:.2f} (breakeven+1pip)"
                    )
                    self.executor.modify_position(ticket, new_sl=be_sl)
                    sl = be_sl
                    continue

            # ====== 1. BREAKEVEN LOGIC (ATR-based distance) ======
            if profit_pips >= breakeven_dist:
                if pos['type'] == 'BUY' and sl < entry:
                    be_sl = entry + (1 * pip_value)
                    be_sl = round(be_sl, 2) if 'XAU' in symbol else round(be_sl, 5)
                    self.logger.info(
                        f"[BREAKEVEN] {ticket} ({entry_tf}): SL {sl:.2f} -> {be_sl:.2f} "
                        f"(entry+1pip) | +{profit_pips:.0f} pips | ATR-triggered ({breakeven_dist:.2f})"
                    )
                    self.executor.modify_position(ticket, new_sl=be_sl)
                    sl = be_sl

                elif pos['type'] == 'SELL' and sl > entry:
                    be_sl = entry - (1 * pip_value)
                    be_sl = round(be_sl, 2) if 'XAU' in symbol else round(be_sl, 5)
                    self.logger.info(
                        f"[BREAKEVEN] {ticket} ({entry_tf}): SL {sl:.2f} -> {be_sl:.2f} "
                        f"(entry-1pip) | +{profit_pips:.0f} pips | ATR-triggered ({breakeven_dist:.2f})"
                    )
                    self.executor.modify_position(ticket, new_sl=be_sl)
                    sl = be_sl

            # ====== 2. TRAILING STOP - ATR-based trail ======
            if profit_pips >= activation_dist:
                trail_mode = "SPIKE" if is_spike else "NORMAL"
                trail_distance = trail_dist * pip_value
                step_distance = step_dist * pip_value

                if pos['type'] == 'BUY':
                    new_sl = current_price - trail_distance
                    new_sl = round(new_sl, 2) if 'XAU' in symbol else round(new_sl, 5)

                    if new_sl > sl and (new_sl - sl) >= step_distance:
                        self.logger.info(
                            f"[{trail_mode}] TRAIL {ticket} ({entry_tf}): SL {sl:.2f} -> {new_sl:.2f} | "
                            f"+{profit_pips:.0f} pips | ATR-trail: {trail_dist:.2f} (atr*{trail_atr_mult})"
                        )
                        self.executor.modify_position(ticket, new_sl=new_sl)

                elif pos['type'] == 'SELL':
                    new_sl = current_price + trail_distance
                    new_sl = round(new_sl, 2) if 'XAU' in symbol else round(new_sl, 5)

                    if new_sl < sl and (sl - new_sl) >= step_distance:
                        self.logger.info(
                            f"[{trail_mode}] TRAIL {ticket} ({entry_tf}): SL {sl:.2f} -> {new_sl:.2f} | "
                            f"+{profit_pips:.0f} pips | ATR-trail: {trail_dist:.2f} (atr*{trail_atr_mult})"
                        )
                        self.executor.modify_position(ticket, new_sl=new_sl)

            # ====== 3. TIME-BASED EXIT (only if NEGATIVE profit) ======
            if max_candles and ticket in self.tracked_positions:
                entry_time_str = self.tracked_positions[ticket].get('entry_time')
                if entry_time_str:
                    try:
                        entry_time = datetime.fromisoformat(entry_time_str)
                        candles_elapsed = (datetime.now() - entry_time).total_seconds() / candle_seconds

                        if candles_elapsed >= max_candles:
                            if profit_pips < 0:
                                self.logger.info(
                                    f"[TIME EXIT] {ticket} ({entry_tf}): {candles_elapsed:.0f} candles, "
                                    f"{profit_pips:.1f} pips (negative) - closing stale trade"
                                )
                                self.executor.close_position(ticket)
                    except Exception as e:
                        self.logger.error(f"Time exit check error for {ticket}: {e}")

    def _check_closed_trades_and_learn(self, open_positions: list):
        """Check closed trades and teach the brain."""
        open_tickets = {pos['ticket'] for pos in open_positions}
        closed_tickets = set(self.tracked_positions.keys()) - open_tickets

        for ticket in closed_tickets:
            trade_data = self.tracked_positions.pop(ticket, None)
            if not trade_data:
                continue

            try:
                import MetaTrader5 as mt5

                from_date = datetime.now() - timedelta(days=1)
                to_date = datetime.now()
                deals = mt5.history_deals_get(from_date, to_date)

                close_deal = None
                for deal in deals if deals else []:
                    if deal.position_id == ticket and deal.entry == mt5.DEAL_ENTRY_OUT:
                        close_deal = deal
                        break

                if close_deal:
                    profit = close_deal.profit
                    exit_price = close_deal.price
                    entry = trade_data['entry_price']
                    sl = trade_data['stop_loss']
                    direction = trade_data['direction']
                    risk_distance = abs(entry - sl)

                    if direction == 'BUY':
                        profit_pips = exit_price - entry
                    else:
                        profit_pips = entry - exit_price

                    rr_achieved = profit_pips / risk_distance if risk_distance > 0 else 0
                    outcome = 'win' if profit > 0 else 'loss'

                    brain_data = {
                        'symbol': trade_data['symbol'],
                        'direction': direction,
                        'outcome': outcome,
                        'features': trade_data['features'],
                        'entry_price': entry,
                        'exit_price': exit_price,
                        'stop_loss': sl,
                        'take_profit': trade_data['take_profit'],
                        'profit': profit,
                        'exit_reason': 'Closed',
                    }
                    # Record for statistics only — no strategy influence
                    self.brain.record_trade(brain_data)

                    # Feed result to risk manager for circuit breaker tracking
                    is_win = profit > 0
                    self.risk_manager.record_trade_result(is_win, profit)

                    self.logger.info(
                        f"Trade recorded: {ticket} {outcome.upper()} "
                        f"RR:{rr_achieved:.2f} ${profit:.2f}"
                    )

                    # === TELEGRAM: Trade Closed Notification ===
                    balance = 300.0
                    try:
                        import MetaTrader5 as _mt5
                        acc = _mt5.account_info()
                        if acc:
                            balance = acc.balance
                    except Exception:
                        pass
                    pnl_pct = (profit / balance * 100) if balance > 0 else 0
                    _tg_send(self.telegram, self.telegram.send_trade_closed(
                        symbol=trade_data['symbol'],
                        direction=direction,
                        entry_price=entry,
                        exit_price=exit_price,
                        pnl=profit,
                        pnl_pct=pnl_pct,
                    ))
            except Exception as e:
                self.logger.error(f"Error learning from trade {ticket}: {e}")

    def scan_once(self):
        """Single scan across all entry timeframes without trading."""
        if not self.initialize():
            return

        entry_timeframes = getattr(settings, 'ENTRY_TIMEFRAMES', {'M5': {'trend_tf': 'H1'}})
        print(f"\nMulti-TF scan: {', '.join(entry_timeframes.keys())}")

        for symbol in settings.TRADING_PAIRS:
            print(f"\n--- {symbol} ---")
            for entry_tf, tf_config in entry_timeframes.items():
                trend_tf = tf_config.get('trend_tf', 'H1')
                df = self.data_fetcher.refresh_data(symbol, entry_tf)
                if df is None or df.empty:
                    print(f"  [{entry_tf}] No data")
                    continue

                result = self.strategy.strategy.analyze_market(symbol, df)
                print(f"  [{entry_tf}] Phase: {result.get('current_phase')} | ATR: {result.get('atr', 0):.2f}")

                if result.get('signal'):
                    sig = result['signal']
                    mode = "SPIKE" if sig.get('is_spike') else "SCALP"
                    print(f"  [{entry_tf}] [{mode}] {sig['direction']} @ {sig['entry_price']:.2f}")
                    print(f"  [{entry_tf}] SL: {sig['stop_loss']:.2f} TP: {sig['take_profit']:.2f} RR: {sig['risk_reward']:.1f}")
                    print(f"  [{entry_tf}] Trend TF: {trend_tf}")
                else:
                    print(f"  [{entry_tf}] No signal")

        self.shutdown()

    def _shutdown_handler(self, signum, frame):
        self.logger.info("Shutdown signal received...")
        self.running = False

    def shutdown(self):
        """Clean shutdown."""
        self.logger.info("Shutting down Gold Scalping Bot...")

        state = {
            'last_scan': self.last_scan_time.isoformat() if self.last_scan_time else None,
            'scan_count': self.scan_count,
            'signals': self.signals_generated,
            'trades': self.trades_executed,
        }
        save_state(state)

        if self.mt5:
            self.mt5.disconnect()

        print("\n" + "=" * 50)
        print("GOLD SCALP BOT - SESSION SUMMARY")
        print("=" * 50)
        print(f"Scans: {self.scan_count}")
        print(f"Signals: {self.signals_generated}")
        print(f"Trades Executed: {self.trades_executed}")

        if self.risk_manager:
            stats = self.risk_manager.get_daily_stats()
            print(f"Daily P/L: ${stats.get('profit_loss', 0):.2f}")

        brain_perf = self.brain.recent_performance
        total_recorded = brain_perf.get('wins', 0) + brain_perf.get('losses', 0)
        print(f"\nTrades recorded: {total_recorded}")
        if total_recorded > 0:
            wr = brain_perf.get('wins', 0) / total_recorded * 100
            print(f"Win Rate: {wr:.1f}%")
        print("=" * 50 + "\n")


# Legacy alias
AMDTradingBot = GoldScalpingBot


def main():
    parser = argparse.ArgumentParser(description='Gold Scalping Bot')
    parser.add_argument('--demo', action='store_true', default=True, help='Demo mode (default)')
    parser.add_argument('--live', action='store_true', help='Live mode (real money!)')
    parser.add_argument('--scan', action='store_true', help='Single market scan')

    args = parser.parse_args()

    if args.live:
        print("\nWARNING: LIVE MODE - Real money!")
        confirm = input("Type 'YES' to confirm: ")
        if confirm != 'YES':
            print("Cancelled.")
            return
        demo_mode = False
    else:
        demo_mode = True

    bot = GoldScalpingBot(demo_mode=demo_mode)

    if args.scan:
        bot.scan_once()
    else:
        bot.run()


if __name__ == "__main__":
    main()
