"""
LIQUIDITY ENGINE — Major Liquidity Zone Detection & 55/45 Rule
================================================================
Detects buy-side and sell-side liquidity on H1 and H4 timeframes.
Implements the 55% GRAB → 45% PROFIT rule across ALL teams.

CORE LOGIC:
1. Map liquidity pools: swing highs (buy-side), swing lows (sell-side), equal H/L
2. Detect liquidity sweeps in real-time on H1 and H4
3. ONLY allow entry AFTER 55% of liquidity zone has been grabbed
4. Target remaining 45% of the zone as profit target
5. Ultra-strict fake signal filter — multi-layer validation

Applied to: METALS, FOREX, CRYPTO (all teams, all pairs)
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════
# LIQUIDITY ZONE DETECTION
# ═══════════════════════════════════════════════════════════════════════

class LiquidityZone:
    """Represents a single liquidity zone (buy-side or sell-side)."""

    def __init__(self, level: float, zone_type: str, strength: int,
                 touches: int, timeframe: str, created_at: str = "",
                 zone_high: float = 0, zone_low: float = 0):
        self.level = level              # Exact price level
        self.zone_type = zone_type      # 'buy_side' or 'sell_side'
        self.strength = strength        # 1-10 (how much liquidity rests here)
        self.touches = touches          # How many times price touched this zone
        self.timeframe = timeframe      # 'H1' or 'H4'
        self.created_at = created_at
        self.zone_high = zone_high or level * 1.001
        self.zone_low = zone_low or level * 0.999
        self.swept = False              # Has liquidity been grabbed?
        self.sweep_pct = 0.0            # How much % was grabbed (0-100)
        self.sweep_time = ""
        self.is_equal_hl = False        # Equal highs/lows = extra liquidity

    def to_dict(self) -> dict:
        return {
            "level": round(self.level, 5),
            "zone_type": self.zone_type,
            "strength": self.strength,
            "touches": self.touches,
            "timeframe": self.timeframe,
            "zone_high": round(self.zone_high, 5),
            "zone_low": round(self.zone_low, 5),
            "swept": self.swept,
            "sweep_pct": round(self.sweep_pct, 1),
            "is_equal_hl": self.is_equal_hl,
            "created_at": self.created_at,
            "sweep_time": self.sweep_time,
        }


class LiquidityEngine:
    """
    Core engine for detecting and tracking liquidity zones on H1/H4.

    THE 55/45 RULE (Sumit's Final Rule for ALL Teams):
    ──────────────────────────────────────────────────
    1. Find major liquidity zone (buy-side or sell-side) on H1/H4
    2. Wait for price to SWEEP the zone (grab liquidity)
    3. Measure how much liquidity was grabbed (sweep_pct)
    4. ONLY enter when sweep_pct >= 55% (55% liquidity grabbed)
    5. Target = remaining 45% of the zone range as profit
    6. If sweep_pct < 55% → NO ENTRY (fake sweep / partial grab)
    """

    # Configurable parameters (can be overridden via settings)
    SWING_LOOKBACK_H1 = 20        # Candles to look back for swing points on H1
    SWING_LOOKBACK_H4 = 15        # Candles to look back for swing points on H4
    EQUAL_HL_TOLERANCE = 0.0015   # 0.15% tolerance for equal highs/lows
    MIN_ZONE_STRENGTH = 2         # Minimum strength to consider a zone valid
    SWEEP_CONFIRM_CANDLES = 2     # Candles to confirm sweep (not just a wick)
    MIN_SWEEP_PCT = 55.0          # MINIMUM 55% liquidity grab required
    PROFIT_TARGET_PCT = 45.0      # Target remaining 45% as profit
    ZONE_EXPIRY_CANDLES = 100     # Zones older than this are stale
    MAX_ZONES_PER_SIDE = 5        # Max zones to track per side per TF

    def __init__(self, config: dict = None):
        """Initialize with optional config overrides."""
        if config:
            for key, val in config.items():
                if hasattr(self, key.upper()):
                    setattr(self, key.upper(), val)

        # Active liquidity zones per symbol
        self._zones: Dict[str, Dict[str, List[LiquidityZone]]] = {}
        # Last sweep events
        self._recent_sweeps: Dict[str, List[dict]] = {}

    # ─── SWING POINT DETECTION (Foundation for liquidity zones) ──────

    @staticmethod
    def find_swing_highs(df: pd.DataFrame, lookback: int = 20) -> List[dict]:
        """Find swing highs — these are BUY-SIDE liquidity (stop losses above)."""
        highs = []
        for i in range(lookback, len(df) - 2):
            # A swing high: highest point in lookback window
            window = df.iloc[i - lookback:i + 3]
            if df.iloc[i]['high'] == window['high'].max():
                # Verify it's a true swing (at least 2 lower highs on each side)
                left_lower = all(df.iloc[j]['high'] < df.iloc[i]['high']
                               for j in range(max(0, i-3), i))
                right_lower = all(df.iloc[j]['high'] < df.iloc[i]['high']
                                for j in range(i+1, min(len(df), i+3)))
                if left_lower and right_lower:
                    highs.append({
                        'index': i,
                        'level': float(df.iloc[i]['high']),
                        'time': str(df.iloc[i].get('time', '')),
                        'volume': float(df.iloc[i].get('volume', 0)),
                    })
        return highs

    @staticmethod
    def find_swing_lows(df: pd.DataFrame, lookback: int = 20) -> List[dict]:
        """Find swing lows — these are SELL-SIDE liquidity (stop losses below)."""
        lows = []
        for i in range(lookback, len(df) - 2):
            window = df.iloc[i - lookback:i + 3]
            if df.iloc[i]['low'] == window['low'].min():
                left_higher = all(df.iloc[j]['low'] > df.iloc[i]['low']
                                for j in range(max(0, i-3), i))
                right_higher = all(df.iloc[j]['low'] > df.iloc[i]['low']
                                 for j in range(i+1, min(len(df), i+3)))
                if left_higher and right_higher:
                    lows.append({
                        'index': i,
                        'level': float(df.iloc[i]['low']),
                        'time': str(df.iloc[i].get('time', '')),
                        'volume': float(df.iloc[i].get('volume', 0)),
                    })
        return lows

    # ─── EQUAL HIGHS/LOWS DETECTION (Extra Liquidity Pools) ────────

    @staticmethod
    def find_equal_highs(swing_highs: List[dict], tolerance_pct: float = 0.0015) -> List[dict]:
        """
        Find equal highs — when 2+ swing highs are at nearly the same level.
        Equal highs = MASSIVE buy-side liquidity pool (everyone's stops are there).
        """
        if len(swing_highs) < 2:
            return []

        equal_groups = []
        used = set()

        for i, sh1 in enumerate(swing_highs):
            if i in used:
                continue
            group = [sh1]
            for j, sh2 in enumerate(swing_highs):
                if j <= i or j in used:
                    continue
                # Check if levels are within tolerance
                diff_pct = abs(sh1['level'] - sh2['level']) / sh1['level']
                if diff_pct <= tolerance_pct:
                    group.append(sh2)
                    used.add(j)

            if len(group) >= 2:
                used.add(i)
                avg_level = sum(g['level'] for g in group) / len(group)
                equal_groups.append({
                    'level': avg_level,
                    'count': len(group),
                    'touches': len(group),
                    'max_level': max(g['level'] for g in group),
                    'min_level': min(g['level'] for g in group),
                })

        return equal_groups

    @staticmethod
    def find_equal_lows(swing_lows: List[dict], tolerance_pct: float = 0.0015) -> List[dict]:
        """
        Find equal lows — when 2+ swing lows are at nearly the same level.
        Equal lows = MASSIVE sell-side liquidity pool.
        """
        if len(swing_lows) < 2:
            return []

        equal_groups = []
        used = set()

        for i, sl1 in enumerate(swing_lows):
            if i in used:
                continue
            group = [sl1]
            for j, sl2 in enumerate(swing_lows):
                if j <= i or j in used:
                    continue
                diff_pct = abs(sl1['level'] - sl2['level']) / sl1['level']
                if diff_pct <= tolerance_pct:
                    group.append(sl2)
                    used.add(j)

            if len(group) >= 2:
                used.add(i)
                avg_level = sum(g['level'] for g in group) / len(group)
                equal_groups.append({
                    'level': avg_level,
                    'count': len(group),
                    'touches': len(group),
                    'max_level': max(g['level'] for g in group),
                    'min_level': min(g['level'] for g in group),
                })

        return equal_groups

    # ─── BUILD LIQUIDITY MAP FOR A TIMEFRAME ────────────────────────

    def build_liquidity_map(self, df: pd.DataFrame, timeframe: str,
                            symbol: str, atr: float = 0) -> Dict[str, List[LiquidityZone]]:
        """
        Build complete liquidity map (buy-side + sell-side zones) for a timeframe.

        Returns:
            {
                'buy_side': [LiquidityZone, ...],   # Above price — stop losses
                'sell_side': [LiquidityZone, ...],   # Below price — stop losses
            }
        """
        if df is None or len(df) < 30:
            return {'buy_side': [], 'sell_side': []}

        lookback = self.SWING_LOOKBACK_H1 if timeframe == 'H1' else self.SWING_LOOKBACK_H4
        current_price = float(df.iloc[-1]['close'])

        # Calculate ATR for zone width if not provided
        if atr <= 0:
            try:
                tr = pd.concat([
                    df['high'] - df['low'],
                    abs(df['high'] - df['close'].shift(1)),
                    abs(df['low'] - df['close'].shift(1))
                ], axis=1).max(axis=1)
                atr = float(tr.rolling(14).mean().iloc[-1])
            except Exception:
                atr = float((df['high'] - df['low']).mean())

        # Zone buffer (half ATR on each side of the level)
        zone_buffer = atr * 0.3

        # 1. Find swing highs (buy-side liquidity)
        swing_highs = self.find_swing_highs(df, lookback)
        # 2. Find swing lows (sell-side liquidity)
        swing_lows = self.find_swing_lows(df, lookback)
        # 3. Find equal highs/lows (extra strong liquidity)
        equal_highs = self.find_equal_highs(swing_highs, self.EQUAL_HL_TOLERANCE)
        equal_lows = self.find_equal_lows(swing_lows, self.EQUAL_HL_TOLERANCE)

        buy_side_zones = []
        sell_side_zones = []

        # Build buy-side zones from swing highs
        for sh in swing_highs:
            if sh['level'] > current_price:  # Only zones ABOVE current price
                # Check if this is part of an equal high group
                is_equal = any(
                    abs(sh['level'] - eh['level']) / sh['level'] < self.EQUAL_HL_TOLERANCE
                    for eh in equal_highs
                )
                strength = 3 if is_equal else 2  # Equal highs = stronger

                # Check how many times price approached this level
                touches = sum(1 for _, row in df.iterrows()
                            if abs(row['high'] - sh['level']) / sh['level'] < 0.002)
                strength = min(10, strength + touches)

                zone = LiquidityZone(
                    level=sh['level'],
                    zone_type='buy_side',
                    strength=strength,
                    touches=touches,
                    timeframe=timeframe,
                    created_at=sh.get('time', ''),
                    zone_high=sh['level'] + zone_buffer,
                    zone_low=sh['level'] - zone_buffer,
                )
                zone.is_equal_hl = is_equal
                buy_side_zones.append(zone)

        # Add equal high zones not already covered
        for eh in equal_highs:
            if eh['level'] > current_price:
                already_exists = any(
                    abs(z.level - eh['level']) / z.level < 0.002 for z in buy_side_zones
                )
                if not already_exists:
                    zone = LiquidityZone(
                        level=eh['level'],
                        zone_type='buy_side',
                        strength=min(10, eh['count'] * 2 + 2),
                        touches=eh['count'],
                        timeframe=timeframe,
                        zone_high=eh['max_level'] + zone_buffer,
                        zone_low=eh['min_level'] - zone_buffer,
                    )
                    zone.is_equal_hl = True
                    buy_side_zones.append(zone)

        # Build sell-side zones from swing lows
        for sl in swing_lows:
            if sl['level'] < current_price:  # Only zones BELOW current price
                is_equal = any(
                    abs(sl['level'] - el['level']) / sl['level'] < self.EQUAL_HL_TOLERANCE
                    for el in equal_lows
                )
                strength = 3 if is_equal else 2

                touches = sum(1 for _, row in df.iterrows()
                            if abs(row['low'] - sl['level']) / sl['level'] < 0.002)
                strength = min(10, strength + touches)

                zone = LiquidityZone(
                    level=sl['level'],
                    zone_type='sell_side',
                    strength=strength,
                    touches=touches,
                    timeframe=timeframe,
                    created_at=sl.get('time', ''),
                    zone_high=sl['level'] + zone_buffer,
                    zone_low=sl['level'] - zone_buffer,
                )
                zone.is_equal_hl = is_equal
                sell_side_zones.append(zone)

        # Add equal low zones
        for el in equal_lows:
            if el['level'] < current_price:
                already_exists = any(
                    abs(z.level - el['level']) / z.level < 0.002 for z in sell_side_zones
                )
                if not already_exists:
                    zone = LiquidityZone(
                        level=el['level'],
                        zone_type='sell_side',
                        strength=min(10, el['count'] * 2 + 2),
                        touches=el['count'],
                        timeframe=timeframe,
                        zone_high=el['max_level'] + zone_buffer,
                        zone_low=el['min_level'] - zone_buffer,
                    )
                    zone.is_equal_hl = True
                    sell_side_zones.append(zone)

        # Sort by proximity to current price (nearest first)
        buy_side_zones.sort(key=lambda z: z.level - current_price)
        sell_side_zones.sort(key=lambda z: current_price - z.level)

        # Limit zones
        buy_side_zones = buy_side_zones[:self.MAX_ZONES_PER_SIDE]
        sell_side_zones = sell_side_zones[:self.MAX_ZONES_PER_SIDE]

        # Cache zones
        key = f"{symbol}_{timeframe}"
        self._zones[key] = {
            'buy_side': buy_side_zones,
            'sell_side': sell_side_zones,
        }

        return {'buy_side': buy_side_zones, 'sell_side': sell_side_zones}

    # ─── LIQUIDITY SWEEP DETECTION ──────────────────────────────────

    def detect_sweep(self, df: pd.DataFrame, zone: LiquidityZone,
                     current_price: float) -> dict:
        """
        Detect if a liquidity zone has been swept.

        A SWEEP occurs when:
        1. Price pierces through the zone (takes out stops)
        2. Then REVERSES back (the "grab and go" move)

        Returns sweep info with sweep_pct (how much was grabbed).
        """
        if df is None or len(df) < 5:
            return {'swept': False, 'sweep_pct': 0, 'valid_entry': False}

        recent = df.iloc[-self.SWEEP_CONFIRM_CANDLES - 3:]

        if zone.zone_type == 'buy_side':
            # Buy-side sweep: price goes ABOVE zone, then reverses DOWN
            # This grabs buy-side liquidity (stop losses of shorts)
            max_high = float(recent['high'].max())

            if max_high >= zone.zone_low:  # Price entered the zone
                # Calculate sweep percentage
                zone_range = zone.zone_high - zone.zone_low
                if zone_range > 0:
                    penetration = min(max_high, zone.zone_high) - zone.zone_low
                    sweep_pct = (penetration / zone_range) * 100
                else:
                    sweep_pct = 100.0 if max_high >= zone.level else 0.0

                # Check for reversal (price came back down)
                reversed_down = current_price < zone.level
                # Check wick rejection (big upper wick = institutional rejection)
                last_candle = recent.iloc[-1]
                upper_wick = float(last_candle['high'] - max(last_candle['close'], last_candle['open']))
                body = abs(float(last_candle['close'] - last_candle['open']))
                wick_rejection = upper_wick > body * 1.5 if body > 0 else False

                # Volume confirmation at sweep
                vol_at_sweep = float(recent['volume'].max())
                avg_vol = float(df['volume'].tail(20).mean()) if len(df) >= 20 else vol_at_sweep
                volume_confirmed = vol_at_sweep > avg_vol * 1.3

                return {
                    'swept': sweep_pct >= 30,  # At least 30% penetration = sweep started
                    'sweep_pct': round(sweep_pct, 1),
                    'valid_entry': sweep_pct >= self.MIN_SWEEP_PCT and reversed_down,
                    'direction': 'SELL',  # After buy-side sweep → SELL
                    'reversed': reversed_down,
                    'wick_rejection': wick_rejection,
                    'volume_confirmed': volume_confirmed,
                    'zone_level': zone.level,
                    'max_penetration': max_high,
                }

        elif zone.zone_type == 'sell_side':
            # Sell-side sweep: price goes BELOW zone, then reverses UP
            # This grabs sell-side liquidity (stop losses of longs)
            min_low = float(recent['low'].min())

            if min_low <= zone.zone_high:  # Price entered the zone
                zone_range = zone.zone_high - zone.zone_low
                if zone_range > 0:
                    penetration = zone.zone_high - max(min_low, zone.zone_low)
                    sweep_pct = (penetration / zone_range) * 100
                else:
                    sweep_pct = 100.0 if min_low <= zone.level else 0.0

                reversed_up = current_price > zone.level
                last_candle = recent.iloc[-1]
                lower_wick = float(min(last_candle['close'], last_candle['open']) - last_candle['low'])
                body = abs(float(last_candle['close'] - last_candle['open']))
                wick_rejection = lower_wick > body * 1.5 if body > 0 else False

                vol_at_sweep = float(recent['volume'].max())
                avg_vol = float(df['volume'].tail(20).mean()) if len(df) >= 20 else vol_at_sweep
                volume_confirmed = vol_at_sweep > avg_vol * 1.3

                return {
                    'swept': sweep_pct >= 30,
                    'sweep_pct': round(sweep_pct, 1),
                    'valid_entry': sweep_pct >= self.MIN_SWEEP_PCT and reversed_up,
                    'direction': 'BUY',  # After sell-side sweep → BUY
                    'reversed': reversed_up,
                    'wick_rejection': wick_rejection,
                    'volume_confirmed': volume_confirmed,
                    'zone_level': zone.level,
                    'max_penetration': min_low,
                }

        return {'swept': False, 'sweep_pct': 0, 'valid_entry': False}

    # ─── FULL LIQUIDITY ANALYSIS (H1 + H4 Combined) ────────────────

    def analyze(self, symbol: str, df_h1: pd.DataFrame,
                df_h4: pd.DataFrame, current_price: float,
                atr_h1: float = 0, atr_h4: float = 0) -> dict:
        """
        Full liquidity analysis combining H1 + H4 zones.

        This is the MAIN method called by the agent pipeline.
        Returns a comprehensive liquidity report with:
        - All active zones (buy-side + sell-side) on H1 and H4
        - Sweep detection results
        - Entry signal based on 55/45 rule
        - Fake signal filter results
        - Profit targets based on remaining 45%
        """
        result = {
            'symbol': symbol,
            'timestamp': datetime.now().strftime('%H:%M:%S'),
            'h1_zones': {'buy_side': [], 'sell_side': []},
            'h4_zones': {'buy_side': [], 'sell_side': []},
            'active_sweeps': [],
            'liquidity_signal': 'NEUTRAL',  # BUY / SELL / NEUTRAL
            'liquidity_score': 0,            # -10 to +10
            'liquidity_confidence': 0,       # 0-100
            'entry_valid': False,
            'sweep_55_rule_passed': False,
            'fake_signal_blocked': False,
            'profit_target': 0.0,
            'stop_loss_suggestion': 0.0,
            'nearest_buy_side': None,
            'nearest_sell_side': None,
            'reasons': [],
            'zone_count': 0,
        }

        # Build H1 liquidity map
        h1_map = self.build_liquidity_map(df_h1, 'H1', symbol, atr_h1)
        result['h1_zones'] = {
            'buy_side': [z.to_dict() for z in h1_map['buy_side']],
            'sell_side': [z.to_dict() for z in h1_map['sell_side']],
        }

        # Build H4 liquidity map
        h4_map = self.build_liquidity_map(df_h4, 'H4', symbol, atr_h4)
        result['h4_zones'] = {
            'buy_side': [z.to_dict() for z in h4_map['buy_side']],
            'sell_side': [z.to_dict() for z in h4_map['sell_side']],
        }

        # Combine all zones
        all_buy_side = h1_map['buy_side'] + h4_map['buy_side']
        all_sell_side = h1_map['sell_side'] + h4_map['sell_side']
        result['zone_count'] = len(all_buy_side) + len(all_sell_side)

        # Track nearest zones
        if all_buy_side:
            nearest_bs = min(all_buy_side, key=lambda z: abs(z.level - current_price))
            result['nearest_buy_side'] = nearest_bs.to_dict()
        if all_sell_side:
            nearest_ss = min(all_sell_side, key=lambda z: abs(z.level - current_price))
            result['nearest_sell_side'] = nearest_ss.to_dict()

        # ── SWEEP DETECTION ON ALL ZONES ──────────────────────────────
        best_sweep = None
        best_sweep_score = 0

        # Check buy-side sweeps (leads to SELL signals)
        for zone in all_buy_side:
            sweep = self.detect_sweep(df_h1, zone, current_price)
            if sweep.get('swept'):
                zone.swept = True
                zone.sweep_pct = sweep['sweep_pct']

                sweep_info = {
                    'zone': zone.to_dict(),
                    'sweep': sweep,
                    'timeframe': zone.timeframe,
                }
                result['active_sweeps'].append(sweep_info)

                # Score this sweep
                score = self._score_sweep(sweep, zone)
                if score > best_sweep_score:
                    best_sweep_score = score
                    best_sweep = sweep_info

        # Check sell-side sweeps (leads to BUY signals)
        for zone in all_sell_side:
            sweep = self.detect_sweep(df_h1, zone, current_price)
            if sweep.get('swept'):
                zone.swept = True
                zone.sweep_pct = sweep['sweep_pct']

                sweep_info = {
                    'zone': zone.to_dict(),
                    'sweep': sweep,
                    'timeframe': zone.timeframe,
                }
                result['active_sweeps'].append(sweep_info)

                score = self._score_sweep(sweep, zone)
                if score > best_sweep_score:
                    best_sweep_score = score
                    best_sweep = sweep_info

        # ── APPLY 55/45 RULE ──────────────────────────────────────────
        if best_sweep:
            sweep_data = best_sweep['sweep']
            zone_data = best_sweep['zone']
            sweep_pct = sweep_data.get('sweep_pct', 0)
            direction = sweep_data.get('direction', 'NEUTRAL')

            if sweep_pct >= self.MIN_SWEEP_PCT:
                # ✅ 55% RULE PASSED — Valid entry
                result['sweep_55_rule_passed'] = True
                result['entry_valid'] = True
                result['liquidity_signal'] = direction

                # Calculate profit target (remaining 45% of zone)
                zone_range = abs(zone_data['zone_high'] - zone_data['zone_low'])
                remaining_pct = (100 - sweep_pct) / 100.0
                profit_target_distance = zone_range * remaining_pct

                # Apply 45% profit target rule
                if direction == 'BUY':
                    result['profit_target'] = round(current_price + profit_target_distance, 5)
                    result['stop_loss_suggestion'] = round(
                        zone_data['zone_low'] - (zone_range * 0.1), 5  # SL below zone
                    )
                elif direction == 'SELL':
                    result['profit_target'] = round(current_price - profit_target_distance, 5)
                    result['stop_loss_suggestion'] = round(
                        zone_data['zone_high'] + (zone_range * 0.1), 5  # SL above zone
                    )

                # Confidence based on sweep quality
                confidence = 50
                confidence += 10 if sweep_data.get('volume_confirmed') else 0
                confidence += 10 if sweep_data.get('wick_rejection') else 0
                confidence += 5 if sweep_data.get('reversed') else 0
                confidence += 5 if zone_data.get('is_equal_hl') else 0
                confidence += 5 if zone_data.get('timeframe') == 'H4' else 0  # H4 zones stronger
                confidence += min(10, zone_data.get('strength', 0) * 2)
                result['liquidity_confidence'] = min(95, confidence)

                # Score
                score = 5 if direction == 'BUY' else -5
                if sweep_data.get('volume_confirmed'):
                    score += 2 if direction == 'BUY' else -2
                if sweep_data.get('wick_rejection'):
                    score += 1 if direction == 'BUY' else -1
                if zone_data.get('is_equal_hl'):
                    score += 1 if direction == 'BUY' else -1
                result['liquidity_score'] = score

                result['reasons'].append(
                    f"✅ 55% RULE PASSED: {zone_data['zone_type']} sweep {sweep_pct:.0f}% "
                    f"on {zone_data['timeframe']} → {direction} "
                    f"(TP: {result['profit_target']:.5f}, remaining {100-sweep_pct:.0f}%)"
                )
                if sweep_data.get('volume_confirmed'):
                    result['reasons'].append("📊 Volume CONFIRMED at sweep")
                if sweep_data.get('wick_rejection'):
                    result['reasons'].append("🕯️ Wick REJECTION detected (institutional)")
                if zone_data.get('is_equal_hl'):
                    result['reasons'].append("⚡ EQUAL H/L zone (massive liquidity pool)")

            else:
                # ❌ 55% RULE FAILED — Not enough liquidity grabbed
                result['sweep_55_rule_passed'] = False
                result['entry_valid'] = False
                result['fake_signal_blocked'] = True
                result['reasons'].append(
                    f"❌ 55% RULE FAILED: Only {sweep_pct:.0f}% swept "
                    f"(need ≥{self.MIN_SWEEP_PCT:.0f}%) — FAKE SWEEP, no entry"
                )
        else:
            result['reasons'].append(
                f"🔍 No active liquidity sweeps detected — monitoring "
                f"{len(all_buy_side)} buy-side, {len(all_sell_side)} sell-side zones"
            )

        # ── ULTRA-STRICT FAKE SIGNAL FILTER ───────────────────────────
        result = self._apply_fake_signal_filter(result, df_h1, df_h4, current_price)

        return result

    # ─── SWEEP SCORING ──────────────────────────────────────────────

    def _score_sweep(self, sweep: dict, zone: LiquidityZone) -> float:
        """Score a sweep for quality ranking."""
        score = 0
        score += sweep.get('sweep_pct', 0) / 10  # Higher sweep % = better
        score += 3 if sweep.get('volume_confirmed') else 0
        score += 2 if sweep.get('wick_rejection') else 0
        score += 2 if sweep.get('reversed') else 0
        score += 2 if zone.is_equal_hl else 0
        score += zone.strength
        score += 3 if zone.timeframe == 'H4' else 1  # H4 zones weighted higher
        return score

    # ─── ULTRA-STRICT FAKE SIGNAL FILTER ────────────────────────────

    def _apply_fake_signal_filter(self, result: dict, df_h1: pd.DataFrame,
                                   df_h4: pd.DataFrame, current_price: float) -> dict:
        """
        Multi-layer validation to block fake signals.

        FILTER LAYERS:
        1. Volume validation — sweep must have volume confirmation
        2. Structure validation — price must reverse (not just wick)
        3. MTF alignment — H1 and H4 must agree on direction
        4. Sweep depth — must be ≥55% (already checked)
        5. Candle body validation — reversal candle must have substantial body
        6. Time validation — sweep must complete within reasonable candles
        """
        if not result.get('entry_valid'):
            return result

        filters_passed = 0
        total_filters = 6
        filter_reasons = []

        # FILTER 1: Volume confirmation
        for sweep_info in result.get('active_sweeps', []):
            if sweep_info['sweep'].get('volume_confirmed'):
                filters_passed += 1
                filter_reasons.append("✅ Volume confirmed")
                break
        else:
            filter_reasons.append("⚠️ No volume at sweep")

        # FILTER 2: Price reversal (not just wick touch)
        for sweep_info in result.get('active_sweeps', []):
            if sweep_info['sweep'].get('reversed'):
                filters_passed += 1
                filter_reasons.append("✅ Price reversed after sweep")
                break
        else:
            filter_reasons.append("⚠️ No reversal confirmed")

        # FILTER 3: MTF alignment (H1 and H4 should not conflict)
        if df_h1 is not None and df_h4 is not None and len(df_h1) >= 20 and len(df_h4) >= 10:
            h1_trend = 'UP' if float(df_h1.iloc[-1]['close']) > float(df_h1.iloc[-20]['close']) else 'DOWN'
            h4_trend = 'UP' if float(df_h4.iloc[-1]['close']) > float(df_h4.iloc[-10]['close']) else 'DOWN'
            signal_dir = result.get('liquidity_signal', 'NEUTRAL')

            # After buy-side sweep → SELL should align with bearish trend
            # After sell-side sweep → BUY should align with bullish trend
            if signal_dir == 'BUY' and h4_trend == 'UP':
                filters_passed += 1
                filter_reasons.append("✅ H4 trend confirms BUY")
            elif signal_dir == 'SELL' and h4_trend == 'DOWN':
                filters_passed += 1
                filter_reasons.append("✅ H4 trend confirms SELL")
            elif signal_dir == 'BUY' and h1_trend == 'UP':
                filters_passed += 1
                filter_reasons.append("✅ H1 trend confirms BUY (H4 neutral)")
            elif signal_dir == 'SELL' and h1_trend == 'DOWN':
                filters_passed += 1
                filter_reasons.append("✅ H1 trend confirms SELL (H4 neutral)")
            else:
                filter_reasons.append(f"⚠️ MTF conflict: signal={signal_dir}, H1={h1_trend}, H4={h4_trend}")
        else:
            filters_passed += 1  # Skip if insufficient data
            filter_reasons.append("ℹ️ MTF check skipped (insufficient data)")

        # FILTER 4: Sweep depth ≥55% (already enforced above)
        if result.get('sweep_55_rule_passed'):
            filters_passed += 1
            filter_reasons.append("✅ 55% sweep rule passed")
        else:
            filter_reasons.append("❌ Sweep depth < 55%")

        # FILTER 5: Reversal candle body validation
        if df_h1 is not None and len(df_h1) >= 2:
            last = df_h1.iloc[-1]
            body = abs(float(last['close'] - last['open']))
            candle_range = float(last['high'] - last['low'])
            if candle_range > 0 and body / candle_range > 0.3:
                filters_passed += 1
                filter_reasons.append("✅ Reversal candle has strong body")
            else:
                filter_reasons.append("⚠️ Reversal candle body too small (doji-like)")
        else:
            filters_passed += 1

        # FILTER 6: Momentum confirmation (not exhausted move)
        if df_h1 is not None and len(df_h1) >= 5:
            recent_momentum = float(df_h1['close'].iloc[-1] - df_h1['close'].iloc[-3])
            signal_dir = result.get('liquidity_signal', 'NEUTRAL')
            if (signal_dir == 'BUY' and recent_momentum > 0) or \
               (signal_dir == 'SELL' and recent_momentum < 0):
                filters_passed += 1
                filter_reasons.append("✅ Momentum confirms direction")
            else:
                filter_reasons.append("⚠️ Momentum against signal direction")
        else:
            filters_passed += 1

        # VERDICT: Need at least 4 of 6 filters to pass
        min_filters_required = 4

        if filters_passed < min_filters_required:
            result['entry_valid'] = False
            result['fake_signal_blocked'] = True
            result['liquidity_signal'] = 'NEUTRAL'
            result['liquidity_score'] = 0
            result['liquidity_confidence'] = 0
            result['reasons'].append(
                f"🚫 FAKE SIGNAL BLOCKED: Only {filters_passed}/{total_filters} filters passed "
                f"(need ≥{min_filters_required})"
            )
        else:
            result['reasons'].append(
                f"✅ ULTRA-STRICT FILTER PASSED: {filters_passed}/{total_filters} filters OK"
            )

        result['filter_details'] = filter_reasons
        result['filters_passed'] = filters_passed
        result['total_filters'] = total_filters

        return result

    # ─── CONVENIENCE: Get zones for dashboard display ───────────────

    def get_dashboard_data(self, symbol: str) -> dict:
        """Get all cached zone data for dashboard display."""
        h1_key = f"{symbol}_H1"
        h4_key = f"{symbol}_H4"

        h1_zones = self._zones.get(h1_key, {'buy_side': [], 'sell_side': []})
        h4_zones = self._zones.get(h4_key, {'buy_side': [], 'sell_side': []})

        return {
            'h1_buy_side': [z.to_dict() for z in h1_zones.get('buy_side', [])],
            'h1_sell_side': [z.to_dict() for z in h1_zones.get('sell_side', [])],
            'h4_buy_side': [z.to_dict() for z in h4_zones.get('buy_side', [])],
            'h4_sell_side': [z.to_dict() for z in h4_zones.get('sell_side', [])],
        }


# ═══════════════════════════════════════════════════════════════════════
# SINGLETON INSTANCE — shared across all teams
# ═══════════════════════════════════════════════════════════════════════
liquidity_engine = LiquidityEngine()
