"""
🧠 TRADE RECORDER & STATISTICS MODULE
=================================================
Records all trades for performance analysis.
NO decision-making power — pure strategy drives all trades.

Features:
1. Trade Memory - Stores all trades with features
2. Performance Tracking - Win rate, streak, P/L
3. Pattern Analysis - Identifies which features correlate with wins
4. Statistics Only - Never overrides or gates strategy decisions
"""

import json
import os
import tempfile
import threading
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


class TradingBrain:
    """
    Trade recorder and statistics tracker.
    Records every trade for performance analysis.
    Does NOT influence trading decisions — pure strategy only.
    """
    
    def __init__(self, memory_file: str = 'logs/brain_memory.json'):
        """Initialize the trade recorder."""
        self.memory_file = Path(memory_file)
        self.memory_file.parent.mkdir(parents=True, exist_ok=True)
        
        # Load existing memory or create new
        self.memory = self._load_memory()
        
        # Feature tracking (for statistics only — never used for decisions)
        self.feature_weights = self.memory.get('feature_weights', {
            'trend_aligned': 1.0,
            'liquidity_sweep': 1.0,
            'structure_shift': 1.0,
            'order_block': 1.0,
            'fvg': 1.0,
            'ema_aligned': 1.0,
            'candle_pattern': 1.0,
            'rsi_optimal': 1.0,
            'rsi_divergence': 1.0,
            'volume_spike': 1.0,
            'good_volatility': 1.0,
            'session_london': 1.0,
            'session_ny': 1.0,
            'session_overlap': 1.0,
            'session_asian': 1.0,
        })
        
        # Performance tracking (read-only statistics)
        self.recent_performance = self.memory.get('recent_performance', {
            'wins': 0,
            'losses': 0,
            'streak': 0,
            'total_profit': 0.0,
        })
        
        # Trade history for analysis
        self.trade_history: List[Dict] = self.memory.get('trade_history', [])
        
        logger.info("📊 Trade Recorder initialized with %d historical trades", len(self.trade_history))
    
    def _load_memory(self) -> Dict:
        """Load brain memory from file."""
        if self.memory_file.exists():
            try:
                with open(self.memory_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Could not load brain memory: {e}")
        return {}
    
    _save_lock = threading.Lock()

    def _save_memory(self):
        """Save trade history to file using atomic write to prevent corruption."""
        self.memory = {
            'feature_weights': self.feature_weights,
            'recent_performance': self.recent_performance,
            'trade_history': self.trade_history[-500:],  # Keep last 500 trades
            'last_updated': datetime.now().isoformat(),
        }
        with self._save_lock:
            try:
                # Atomic write: write to temp file, fsync, then rename
                dir_path = self.memory_file.parent
                fd, tmp_path = tempfile.mkstemp(dir=str(dir_path), suffix='.tmp')
                try:
                    with os.fdopen(fd, 'w') as f:
                        json.dump(self.memory, f, indent=2, default=str)
                        f.flush()
                        os.fsync(f.fileno())
                    # Atomic rename (POSIX) / replace (Windows)
                    os.replace(tmp_path, str(self.memory_file))
                except:
                    # Clean up temp file on failure
                    if os.path.exists(tmp_path):
                        os.unlink(tmp_path)
                    raise
            except Exception as e:
                logger.error(f"Could not save brain memory: {e}")
    
    def record_trade(self, trade_data: Dict):
        """
        Record a completed trade for statistics.
        Does NOT influence future trading decisions.
        
        Args:
            trade_data: Dict with trade details including:
                - symbol, direction, entry_price, exit_price
                - profit (positive or negative)
                - features: dict of which features were present
                - exit_reason: 'Take Profit', 'Stop Loss', 'Trailing Stop', etc.
        """
        # Add timestamp if not present
        if 'timestamp' not in trade_data:
            trade_data['timestamp'] = datetime.now().isoformat()
        
        # Determine if win or loss
        is_win = trade_data.get('profit', 0) > 0
        trade_data['is_win'] = is_win
        
        # Update performance stats
        if is_win:
            self.recent_performance['wins'] += 1
            self.recent_performance['streak'] = max(1, self.recent_performance['streak'] + 1)
        else:
            self.recent_performance['losses'] += 1
            self.recent_performance['streak'] = min(-1, self.recent_performance['streak'] - 1)
        
        self.recent_performance['total_profit'] += trade_data.get('profit', 0)
        
        # Store trade
        self.trade_history.append(trade_data)
        
        # Save
        self._save_memory()
        
        logger.info(
            f"📊 Trade recorded: {'WIN' if is_win else 'LOSS'} | "
            f"Streak: {self.recent_performance['streak']} | "
            f"Total P/L: ${self.recent_performance['total_profit']:.2f}"
        )
    
    def analyze_patterns(self) -> Dict:
        """
        Analyze trade history to find winning patterns.
        
        Returns:
            Dict with pattern analysis results
        """
        if len(self.trade_history) < 10:
            return {'error': 'Not enough trades for pattern analysis'}
        
        # Convert to DataFrame for analysis
        df = pd.DataFrame(self.trade_history)
        
        # Feature win rates
        feature_stats = {}
        for feature in self.feature_weights.keys():
            col = f'feat_{feature}' if f'feat_{feature}' in df.columns else feature
            if col in df.columns or (isinstance(df.iloc[0].get('features', {}), dict)):
                # Extract feature from nested dict if needed
                if 'features' in df.columns:
                    feature_present = df['features'].apply(lambda x: x.get(feature, False) if isinstance(x, dict) else False)
                else:
                    feature_present = df.get(col, pd.Series([False] * len(df)))
                
                trades_with_feature = df[feature_present == True]
                if len(trades_with_feature) >= 3:
                    win_rate = trades_with_feature['is_win'].mean() * 100
                    feature_stats[feature] = {
                        'win_rate': win_rate,
                        'trades': len(trades_with_feature),
                        'weight': self.feature_weights.get(feature, 1.0),
                    }
        
        # Best and worst times
        if 'timestamp' in df.columns:
            df['hour'] = pd.to_datetime(df['timestamp']).dt.hour
            hourly_stats = df.groupby('hour')['is_win'].agg(['mean', 'count'])
            best_hours = hourly_stats[hourly_stats['count'] >= 3].nsmallest(3, 'mean').index.tolist()
            worst_hours = hourly_stats[hourly_stats['count'] >= 3].nlargest(3, 'mean').index.tolist()
        else:
            best_hours = []
            worst_hours = []
        
        # Overall stats
        total_trades = len(df)
        win_rate = df['is_win'].mean() * 100
        
        return {
            'total_trades': total_trades,
            'win_rate': win_rate,
            'feature_stats': feature_stats,
            'best_hours': best_hours,
            'worst_hours': worst_hours,
            'current_streak': self.recent_performance['streak'],
            'total_profit': self.recent_performance['total_profit'],
            'top_features': sorted(
                [(k, v['win_rate']) for k, v in feature_stats.items()],
                key=lambda x: x[1],
                reverse=True
            )[:5],
        }
    
    def get_brain_status(self) -> str:
        """Get a human-readable status of the trade recorder."""
        total = self.recent_performance['wins'] + self.recent_performance['losses']
        if total == 0:
            return "📊 Trade Recorder: No trades recorded yet"
        
        win_rate = (self.recent_performance['wins'] / total) * 100
        streak = self.recent_performance['streak']
        streak_str = f"+{streak} wins" if streak > 0 else f"{streak} losses" if streak < 0 else "neutral"
        
        return (
            f"📊 Trade Recorder Status:\n"
            f"   Trades Recorded: {total}\n"
            f"   Win Rate: {win_rate:.1f}%\n"
            f"   Current Streak: {streak_str}\n"
            f"   Total P/L: ${self.recent_performance['total_profit']:.2f}\n"
            f"   Mode: PURE STRATEGY (no sentiment/adaptive overrides)"
        )
    
    def train_feature_weights(self):
        """
        === ENHANCEMENT: BRAIN TRAINING ===

        Analyze trade history and update feature weights based on actual win rates.
        Features that correlate with winning trades get higher weights (up to 2.0).
        Features that correlate with losing trades get lower weights (down to 0.3).

        This does NOT gate trades — it provides insight data for reporting.
        Weights are saved to brain_memory.json for cross-session persistence.
        """
        if len(self.trade_history) < 20:
            logger.info("Brain: Not enough trades to train (need 20+, have %d)", len(self.trade_history))
            return

        # Use last 200 trades for recency bias
        recent_trades = self.trade_history[-200:]

        overall_win_rate = sum(1 for t in recent_trades if t.get('is_win', False)) / len(recent_trades)

        for feature in list(self.feature_weights.keys()):
            # Count trades where this feature was present
            trades_with = [t for t in recent_trades
                          if isinstance(t.get('features', {}), dict)
                          and t['features'].get(feature, False)]

            if len(trades_with) < 5:
                # Not enough data, keep weight at 1.0
                continue

            feature_win_rate = sum(1 for t in trades_with if t.get('is_win', False)) / len(trades_with)

            # Weight = feature_win_rate / overall_win_rate, clamped to [0.3, 2.0]
            # Features that win more than average get boosted
            # Features that win less than average get penalized
            if overall_win_rate > 0:
                raw_weight = feature_win_rate / overall_win_rate
            else:
                raw_weight = 1.0

            # Smooth update: 70% old weight + 30% new weight (prevents wild swings)
            old_weight = self.feature_weights.get(feature, 1.0)
            new_weight = 0.7 * old_weight + 0.3 * max(0.3, min(2.0, raw_weight))
            self.feature_weights[feature] = round(new_weight, 3)

        self._save_memory()

        # Log top and bottom features
        sorted_features = sorted(self.feature_weights.items(), key=lambda x: x[1], reverse=True)
        top3 = sorted_features[:3]
        bottom3 = sorted_features[-3:]
        logger.info(
            f"Brain TRAINED on {len(recent_trades)} trades (win rate: {overall_win_rate*100:.1f}%). "
            f"Top features: {', '.join(f'{k}={v:.2f}' for k,v in top3)} | "
            f"Weakest: {', '.join(f'{k}={v:.2f}' for k,v in bottom3)}"
        )

        return {
            'trades_analyzed': len(recent_trades),
            'overall_win_rate': overall_win_rate,
            'updated_weights': dict(self.feature_weights),
            'top_features': top3,
            'weakest_features': bottom3,
        }

    def get_feature_insights(self) -> Dict:
        """
        Return feature correlation insights for reporting.
        Shows which features most strongly predict winning trades.
        """
        if len(self.trade_history) < 10:
            return {}

        recent = self.trade_history[-200:]
        insights = {}

        for feature in self.feature_weights.keys():
            trades_with = [t for t in recent
                          if isinstance(t.get('features', {}), dict)
                          and t['features'].get(feature, False)]
            trades_without = [t for t in recent
                             if isinstance(t.get('features', {}), dict)
                             and not t['features'].get(feature, False)]

            if len(trades_with) >= 3 and len(trades_without) >= 3:
                wr_with = sum(1 for t in trades_with if t.get('is_win')) / len(trades_with)
                wr_without = sum(1 for t in trades_without if t.get('is_win')) / len(trades_without)
                insights[feature] = {
                    'win_rate_with': round(wr_with * 100, 1),
                    'win_rate_without': round(wr_without * 100, 1),
                    'edge': round((wr_with - wr_without) * 100, 1),
                    'sample_size': len(trades_with),
                    'weight': self.feature_weights.get(feature, 1.0),
                }

        return insights

    def reset_learning(self):
        """Reset all recorded statistics."""
        self.feature_weights = {k: 1.0 for k in self.feature_weights}
        self.recent_performance = {'wins': 0, 'losses': 0, 'streak': 0, 'total_profit': 0.0}
        self.trade_history = []
        self._save_memory()
        logger.info("📊 Trade recorder reset to defaults")


# Global brain instance
_brain_instance: Optional[TradingBrain] = None


def get_brain() -> TradingBrain:
    """Get or create the global brain instance."""
    global _brain_instance
    if _brain_instance is None:
        _brain_instance = TradingBrain()
    return _brain_instance


if __name__ == "__main__":
    # Test the brain
    print("🧠 Testing Trading Brain...")
    
    brain = TradingBrain()
    
    # Simulate some trades
    test_trades = [
        {'profit': 50, 'features': {'trend_aligned': True, 'liquidity_sweep': True, 'ema_aligned': True}},
        {'profit': 30, 'features': {'trend_aligned': True, 'volume_spike': True, 'candle_pattern': True}},
        {'profit': -20, 'features': {'trend_aligned': False, 'liquidity_sweep': True}},
        {'profit': 40, 'features': {'trend_aligned': True, 'rsi_divergence': True, 'good_volatility': True}},
        {'profit': -15, 'features': {'trend_aligned': True, 'liquidity_sweep': False}},
        {'profit': 60, 'features': {'trend_aligned': True, 'liquidity_sweep': True, 'structure_shift': True}},
    ]
    
    for trade in test_trades:
        brain.record_trade(trade)
    
    print("\n" + brain.get_brain_status())
    
    # Test pattern analysis
    print("\n📊 Pattern Analysis:")
    analysis = brain.analyze_patterns()
    print(f"   Win Rate: {analysis.get('win_rate', 0):.1f}%")
    print(f"   Top Features: {analysis.get('top_features', [])}")
    
    # Test trade decision
    test_features = {
        'trend_aligned': True,
        'liquidity_sweep': True,
        'structure_shift': True,
        'ema_aligned': True,
        'volume_spike': True,
    }
    should_trade, confidence, reason = brain.should_take_trade(test_features)
    print(f"\n🎯 Should take trade: {should_trade} (Confidence: {confidence:.0f}%)")
    print(f"   Reason: {reason}")
