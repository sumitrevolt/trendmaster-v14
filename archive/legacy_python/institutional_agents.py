"""
INSTITUTIONAL AGENTS — Follow the Big Players
================================================
6 Specialized Agents that track institutional/smart money activity:

1. InstitutionalFlowAgent  — COT data, large volume detection, OB scoring
2. WebResearchAgent        — Continuous web search for trade setups & analysis
3. CrossMarketAgent        — DXY, VIX, bond yields, cross-asset correlations
4. EconomicCalendarAgent   — Upcoming high-impact events, avoid news bombs
5. AgentCommunicationBus   — All agents share signals via message bus
6. AgentRewardSystem       — Track which agents produce profitable signals

RULE: Every signal must pass through ALL agents before execution.
      If any agent flags a conflict → HOLD (no trade).
"""

import asyncio
import aiohttp
import logging
import json
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from collections import defaultdict

logger = logging.getLogger(__name__)


# ═════════════════════════════════════════════════════════════════════
# AGENT COMMUNICATION BUS — All agents talk to each other here
# ═════════════════════════════════════════════════════════════════════
class AgentCommunicationBus:
    """
    Central message bus for inter-agent communication.
    Every agent posts signals/warnings here.
    Other agents read the bus before making decisions.

    Message format:
    {
        "agent": "InstitutionalFlow",
        "symbol": "XAUUSD",
        "type": "SIGNAL" | "WARNING" | "BLOCK" | "INFO",
        "direction": "BUY" | "SELL" | "NEUTRAL",
        "confidence": 0-100,
        "message": "COT shows institutions net long gold...",
        "timestamp": datetime,
        "ttl_minutes": 60,  # Message expires after this
    }
    """
    _messages: List[Dict] = []
    _max_messages = 500

    @classmethod
    def post(cls, agent: str, symbol: str, msg_type: str,
             direction: str, confidence: int, message: str,
             ttl_minutes: int = 60, data: dict = None):
        """Post a message to the bus."""
        msg = {
            "agent": agent,
            "symbol": symbol,
            "type": msg_type,
            "direction": direction,
            "confidence": confidence,
            "message": message,
            "timestamp": datetime.utcnow(),
            "ttl_minutes": ttl_minutes,
            "data": data or {},
        }
        cls._messages.append(msg)
        # Keep last N messages
        if len(cls._messages) > cls._max_messages:
            cls._messages = cls._messages[-cls._max_messages:]
        logger.info(f"[BUS] {agent} → {symbol}: {msg_type} {direction} ({confidence}%) — {message[:80]}")

    @classmethod
    def get_signals(cls, symbol: str, max_age_minutes: int = 60) -> List[Dict]:
        """Get all active signals for a symbol (not expired)."""
        now = datetime.utcnow()
        return [
            m for m in cls._messages
            if m["symbol"] == symbol
            and (now - m["timestamp"]).total_seconds() < m["ttl_minutes"] * 60
            and m["type"] in ("SIGNAL", "WARNING", "BLOCK")
        ]

    @classmethod
    def get_blocks(cls, symbol: str) -> List[Dict]:
        """Get any active BLOCK messages for a symbol."""
        now = datetime.utcnow()
        return [
            m for m in cls._messages
            if m["symbol"] == symbol
            and m["type"] == "BLOCK"
            and (now - m["timestamp"]).total_seconds() < m["ttl_minutes"] * 60
        ]

    @classmethod
    def get_consensus(cls, symbol: str) -> Dict:
        """
        Calculate consensus from all agents for a symbol.
        Returns: {"direction": BUY/SELL/NEUTRAL, "score": int, "agents_agree": int,
                  "agents_disagree": int, "blocked": bool, "reasons": [...]}
        """
        signals = cls.get_signals(symbol, max_age_minutes=30)
        blocks = cls.get_blocks(symbol)

        if blocks:
            return {
                "direction": "NEUTRAL",
                "score": 0,
                "agents_agree": 0,
                "agents_disagree": 0,
                "blocked": True,
                "reasons": [f"⛔ BLOCKED by {b['agent']}: {b['message'][:60]}" for b in blocks],
            }

        buy_score = 0
        sell_score = 0
        buy_agents = []
        sell_agents = []
        neutral_agents = []
        reasons = []

        for sig in signals:
            if sig["direction"] == "BUY":
                buy_score += sig["confidence"]
                buy_agents.append(sig["agent"])
                reasons.append(f"📈 {sig['agent']}: BUY {sig['confidence']}% — {sig['message'][:50]}")
            elif sig["direction"] == "SELL":
                sell_score += sig["confidence"]
                sell_agents.append(sig["agent"])
                reasons.append(f"📉 {sig['agent']}: SELL {sig['confidence']}% — {sig['message'][:50]}")
            else:
                neutral_agents.append(sig["agent"])

        if buy_score > sell_score and buy_score > 0:
            direction = "BUY"
            score = buy_score - sell_score
        elif sell_score > buy_score and sell_score > 0:
            direction = "SELL"
            score = sell_score - buy_score
        else:
            direction = "NEUTRAL"
            score = 0

        return {
            "direction": direction,
            "score": score,
            "agents_agree": len(buy_agents) if direction == "BUY" else len(sell_agents),
            "agents_disagree": len(sell_agents) if direction == "BUY" else len(buy_agents),
            "blocked": False,
            "reasons": reasons,
            "buy_agents": buy_agents,
            "sell_agents": sell_agents,
        }

    @classmethod
    def report(cls) -> str:
        """Summary of recent bus activity."""
        now = datetime.utcnow()
        active = [m for m in cls._messages
                  if (now - m["timestamp"]).total_seconds() < 1800]  # Last 30 min
        if not active:
            return "No active agent signals"
        lines = []
        for m in active[-10:]:
            age = int((now - m["timestamp"]).total_seconds() / 60)
            lines.append(f"  {m['agent']:20s} → {m['symbol']:8s} {m['type']:7s} {m['direction']:7s} {m['confidence']:3d}% ({age}m ago)")
        return "\n".join(lines)


# ═════════════════════════════════════════════════════════════════════
# AGENT 1: INSTITUTIONAL FLOW — COT Data + Volume Detection
# ═════════════════════════════════════════════════════════════════════
class InstitutionalFlowAgent:
    """
    Tracks institutional positioning via:
    1. COT Report (weekly) — Net long/short positions of large speculators
    2. Volume spikes on MT5 — Detect institutional order flow in real-time
    3. Order Block strength — Score unmitigated OBs for institutional presence
    4. Session killzones — When institutions are most active

    Posts to AgentCommunicationBus with direction bias.
    """

    # COT contract codes for our symbols
    COT_CODES = {
        "XAUUSD": "088691",  # Gold futures
        "XAGUSD": "084691",  # Silver futures
        "EURUSD": "099741",  # Euro FX
        "GBPUSD": "096742",  # British Pound
        "USDJPY": "097741",  # Japanese Yen
        "AUDUSD": "232741",  # Australian Dollar
        "USDCAD": "090741",  # Canadian Dollar
        "NZDUSD": "112741",  # New Zealand Dollar
        "BTCUSD": "133741",  # Bitcoin futures
    }

    # Institutional session killzones (UTC) — when big players execute
    KILLZONES = {
        "LONDON_OPEN":  (7, 9),    # London banks start executing
        "NY_OPEN":      (12, 14),  # NY banks start executing
        "LONDON_CLOSE": (15, 17),  # London banks squaring positions
        "ASIAN_OPEN":   (0, 2),    # Asian banks start
    }

    _cot_cache: Dict = {}
    _cot_last_fetch: float = 0
    COT_CACHE_TTL = 3600 * 6  # Refresh every 6 hours (COT is weekly anyway)

    @classmethod
    async def analyze(cls, symbol: str, df_h1=None, tick_volume: float = 0,
                      avg_volume: float = 0) -> Dict:
        """
        Full institutional analysis for a symbol.
        Returns: {"bias": BUY/SELL/NEUTRAL, "confidence": 0-100,
                  "cot_bias": str, "volume_signal": str, "killzone": str}
        """
        result = {
            "bias": "NEUTRAL",
            "confidence": 50,
            "cot_bias": "UNKNOWN",
            "cot_change": 0,
            "volume_signal": "NORMAL",
            "killzone": "NONE",
            "killzone_active": False,
            "reasons": [],
        }

        try:
            # 1. COT Data analysis
            cot = await cls._fetch_cot(symbol)
            if cot:
                result["cot_bias"] = cot["bias"]
                result["cot_change"] = cot.get("change", 0)
                if cot["bias"] == "BULLISH":
                    result["confidence"] += 15
                    result["reasons"].append(
                        f"📊 COT: Institutions NET LONG ({cot.get('net_pos', '?')} contracts, "
                        f"change: {cot.get('change', 0):+d})"
                    )
                elif cot["bias"] == "BEARISH":
                    result["confidence"] -= 15
                    result["reasons"].append(
                        f"📊 COT: Institutions NET SHORT ({cot.get('net_pos', '?')} contracts, "
                        f"change: {cot.get('change', 0):+d})"
                    )

            # 2. Volume spike detection (institutional order flow)
            if tick_volume > 0 and avg_volume > 0:
                vol_ratio = tick_volume / avg_volume
                if vol_ratio >= 3.0:
                    result["volume_signal"] = "MASSIVE_INSTITUTIONAL"
                    result["confidence"] += 20
                    result["reasons"].append(
                        f"🏦 MASSIVE volume spike ({vol_ratio:.1f}x avg) — institutional order flow detected"
                    )
                elif vol_ratio >= 2.0:
                    result["volume_signal"] = "HIGH_INSTITUTIONAL"
                    result["confidence"] += 10
                    result["reasons"].append(
                        f"🏦 High volume ({vol_ratio:.1f}x avg) — likely institutional activity"
                    )
                elif vol_ratio <= 0.5:
                    result["volume_signal"] = "LOW_RETAIL"
                    result["reasons"].append(
                        f"⚠️ Low volume ({vol_ratio:.1f}x avg) — mostly retail, no institutional backing"
                    )

            # 3. Killzone check (when institutions trade)
            hour_utc = datetime.utcnow().hour
            for kz_name, (start, end) in cls.KILLZONES.items():
                if start <= hour_utc < end:
                    result["killzone"] = kz_name
                    result["killzone_active"] = True
                    result["confidence"] += 5
                    result["reasons"].append(
                        f"⏰ KILLZONE ACTIVE: {kz_name} ({start}-{end} UTC) — institutions executing now"
                    )
                    break

            if not result["killzone_active"]:
                result["reasons"].append(
                    f"🌙 Outside killzones ({hour_utc}:xx UTC) — institutional activity lower"
                )

            # 4. Determine final bias
            if result["confidence"] >= 65:
                result["bias"] = result.get("cot_bias", "NEUTRAL")
                if result["bias"] == "UNKNOWN":
                    result["bias"] = "NEUTRAL"
            elif result["confidence"] <= 35:
                # Reverse of COT (if institutions are against us)
                if result["cot_bias"] == "BULLISH":
                    result["bias"] = "BEARISH"
                elif result["cot_bias"] == "BEARISH":
                    result["bias"] = "BULLISH"

            # Post to bus
            AgentCommunicationBus.post(
                agent="InstitutionalFlow",
                symbol=symbol,
                msg_type="SIGNAL",
                direction=result["bias"] if result["bias"] != "UNKNOWN" else "NEUTRAL",
                confidence=min(100, max(0, result["confidence"])),
                message=result["reasons"][0] if result["reasons"] else "No institutional data",
                ttl_minutes=30,
                data=result,
            )

        except Exception as e:
            logger.error(f"InstitutionalFlowAgent error [{symbol}]: {e}")
            result["reasons"].append(f"⚠️ Institutional analysis error: {str(e)[:60]}")

        return result

    @classmethod
    async def _fetch_cot(cls, symbol: str) -> Optional[Dict]:
        """Fetch COT data from CFTC public API (Socrata)."""
        code = cls.COT_CODES.get(symbol)
        if not code:
            return None

        # Check cache
        cache_key = f"{symbol}_{code}"
        now = time.time()
        if cache_key in cls._cot_cache and (now - cls._cot_last_fetch) < cls.COT_CACHE_TTL:
            return cls._cot_cache[cache_key]

        try:
            # CFTC Socrata API — free, no key needed
            url = (
                f"https://publicreporting.cftc.gov/resource/jun7-fc8e.json"
                f"?$where=cftc_contract_market_code='{code}'"
                f"&$order=report_date_as_yyyy_mm_dd DESC"
                f"&$limit=2"
            )
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status != 200:
                        return None
                    data = await resp.json()

            if not data or len(data) < 1:
                return None

            latest = data[0]
            # Net position = Noncommercial Long - Noncommercial Short
            # (Noncommercial = large speculators / hedge funds)
            try:
                nc_long = int(latest.get("noncomm_positions_long_all", 0))
                nc_short = int(latest.get("noncomm_positions_short_all", 0))
                net_pos = nc_long - nc_short

                # Compare with previous week
                change = 0
                if len(data) >= 2:
                    prev = data[1]
                    prev_long = int(prev.get("noncomm_positions_long_all", 0))
                    prev_short = int(prev.get("noncomm_positions_short_all", 0))
                    prev_net = prev_long - prev_short
                    change = net_pos - prev_net

                # For JPY/CAD/CHF: invert (these are quoted as USD/XXX)
                if symbol in ("USDJPY", "USDCAD", "USDCHF"):
                    net_pos = -net_pos
                    change = -change

                bias = "BULLISH" if net_pos > 0 else "BEARISH" if net_pos < 0 else "NEUTRAL"

                result = {
                    "bias": bias,
                    "net_pos": net_pos,
                    "change": change,
                    "long": nc_long,
                    "short": nc_short,
                    "report_date": latest.get("report_date_as_yyyy_mm_dd", "?"),
                }

                cls._cot_cache[cache_key] = result
                cls._cot_last_fetch = now
                return result

            except (ValueError, TypeError) as e:
                logger.debug(f"COT parse error [{symbol}]: {e}")
                return None

        except asyncio.TimeoutError:
            logger.debug(f"COT timeout [{symbol}]")
            return None
        except Exception as e:
            logger.debug(f"COT fetch error [{symbol}]: {e}")
            return None


# ═════════════════════════════════════════════════════════════════════
# AGENT 2: WEB RESEARCH — Continuous web search for trade setups
# ═════════════════════════════════════════════════════════════════════
class WebResearchAgent:
    """
    Continuously searches the web for:
    1. TradingView community ideas (bullish/bearish consensus)
    2. Analyst forecasts and price targets
    3. Breaking news that affects markets
    4. Sentiment from financial RSS feeds

    Uses FREE sources only (no API keys):
    - Yahoo Finance RSS
    - Google News RSS
    - Investing.com RSS
    """

    _cache: Dict[str, tuple] = {}
    CACHE_TTL = 300  # 5 minutes

    # RSS feeds for market analysis
    ANALYSIS_FEEDS = {
        "XAUUSD": [
            "https://feeds.finance.yahoo.com/rss/2.0/headline?s=GC%3DF&region=US&lang=en-US",
            "https://news.google.com/rss/search?q=gold+price+forecast+today&hl=en-US",
        ],
        "EURUSD": [
            "https://feeds.finance.yahoo.com/rss/2.0/headline?s=EURUSD%3DX&region=US&lang=en-US",
            "https://news.google.com/rss/search?q=EURUSD+forecast+today&hl=en-US",
        ],
        "GBPUSD": [
            "https://feeds.finance.yahoo.com/rss/2.0/headline?s=GBPUSD%3DX&region=US&lang=en-US",
        ],
        "BTCUSD": [
            "https://feeds.finance.yahoo.com/rss/2.0/headline?s=BTC-USD&region=US&lang=en-US",
            "https://news.google.com/rss/search?q=bitcoin+price+prediction+today&hl=en-US",
        ],
    }

    # Sentiment keywords (expanded for research)
    STRONG_BULLISH = {
        "buy", "bullish", "surge", "rally", "breakout", "upside", "target",
        "accumulate", "strong buy", "outperform", "upgrade", "higher",
        "all-time high", "ATH", "moon", "pump", "institutional buying",
        "central bank buying", "record high", "demand", "support holds",
    }
    STRONG_BEARISH = {
        "sell", "bearish", "crash", "plunge", "breakdown", "downside",
        "underperform", "downgrade", "lower", "correction", "bear market",
        "dump", "institutional selling", "risk-off", "recession",
        "rate hike", "hawkish", "overvalued", "resistance holds",
    }

    @classmethod
    async def research(cls, symbol: str) -> Dict:
        """
        Conduct web research for a symbol.
        Returns: {"sentiment": BUY/SELL/NEUTRAL, "confidence": 0-100,
                  "headlines": [...], "analyst_bias": str}
        """
        cached = cls._cache.get(symbol)
        if cached and (time.time() - cached[0]) < cls.CACHE_TTL:
            return cached[1]

        result = {
            "sentiment": "NEUTRAL",
            "confidence": 50,
            "headlines": [],
            "bull_count": 0,
            "bear_count": 0,
            "total_articles": 0,
            "reasons": [],
        }

        try:
            feeds = cls.ANALYSIS_FEEDS.get(symbol, [
                f"https://news.google.com/rss/search?q={symbol}+forecast+today&hl=en-US"
            ])

            all_headlines = []
            for feed_url in feeds:
                try:
                    headlines = await cls._fetch_rss(feed_url)
                    all_headlines.extend(headlines)
                except Exception:
                    continue

            if not all_headlines:
                result["reasons"].append(f"📰 No web research data available for {symbol}")
                cls._cache[symbol] = (time.time(), result)
                return result

            # Analyze sentiment from headlines
            bull = 0
            bear = 0
            for h in all_headlines[:15]:
                words = set(w.strip(".,!?;:\"'()[]").lower() for w in h.split())
                b = len(words & cls.STRONG_BULLISH)
                s = len(words & cls.STRONG_BEARISH)
                bull += b
                bear += s

            result["headlines"] = all_headlines[:5]
            result["bull_count"] = bull
            result["bear_count"] = bear
            result["total_articles"] = len(all_headlines)

            # Determine sentiment
            score = bull - bear
            if score >= 3:
                result["sentiment"] = "BUY"
                result["confidence"] = min(80, 50 + score * 5)
                result["reasons"].append(
                    f"🌐 Web research BULLISH: {bull} bullish vs {bear} bearish signals "
                    f"from {len(all_headlines)} articles"
                )
            elif score <= -3:
                result["sentiment"] = "SELL"
                result["confidence"] = min(80, 50 + abs(score) * 5)
                result["reasons"].append(
                    f"🌐 Web research BEARISH: {bear} bearish vs {bull} bullish signals "
                    f"from {len(all_headlines)} articles"
                )
            else:
                result["sentiment"] = "NEUTRAL"
                result["confidence"] = 50
                result["reasons"].append(
                    f"🌐 Web research MIXED: {bull} bullish, {bear} bearish "
                    f"from {len(all_headlines)} articles — no clear bias"
                )

            # Post to bus
            AgentCommunicationBus.post(
                agent="WebResearch",
                symbol=symbol,
                msg_type="SIGNAL",
                direction=result["sentiment"],
                confidence=result["confidence"],
                message=result["reasons"][0] if result["reasons"] else "No data",
                ttl_minutes=15,
                data=result,
            )

        except Exception as e:
            logger.error(f"WebResearchAgent error [{symbol}]: {e}")
            result["reasons"].append(f"⚠️ Web research error: {str(e)[:60]}")

        cls._cache[symbol] = (time.time(), result)
        return result

    @classmethod
    async def _fetch_rss(cls, url: str) -> List[str]:
        """Fetch headlines from RSS feed."""
        try:
            headers = {"User-Agent": "Mozilla/5.0 (compatible; TradingBot/2.0)"}
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=8),
                                       headers=headers) as resp:
                    if resp.status != 200:
                        return []
                    text = await resp.text()

            root = ET.fromstring(text)
            headlines = []
            for item in root.iter("item"):
                title = item.find("title")
                if title is not None and title.text:
                    headlines.append(title.text.strip())
                if len(headlines) >= 10:
                    break
            return headlines
        except Exception:
            return []


# ═════════════════════════════════════════════════════════════════════
# AGENT 3: CROSS-MARKET — DXY, VIX, Bonds, Correlations
# ═════════════════════════════════════════════════════════════════════
class CrossMarketAgent:
    """
    Monitors cross-market correlations to confirm trade direction:
    1. DXY (Dollar Index) — Strong DXY = bearish for EUR, GBP, AUD, Gold
    2. VIX (Fear Index) — High VIX = risk-off = bullish Gold, JPY, CHF
    3. US10Y (10-Year Treasury) — Rising yields = strong USD
    4. Crude Oil — Affects CAD, AUD

    Correlations:
    - DXY ↑ → EURUSD ↓, GBPUSD ↓, XAUUSD ↓, AUDUSD ↓
    - DXY ↓ → EURUSD ↑, GBPUSD ↑, XAUUSD ↑, AUDUSD ↑
    - VIX ↑ → XAUUSD ↑, USDJPY ↓ (safe havens rally)
    - VIX ↓ → Risk-on assets rally (crypto, AUD)
    """

    # Symbol correlations with DXY
    DXY_CORRELATION = {
        "EURUSD": -0.95,   # Strong negative (EUR is biggest DXY component)
        "GBPUSD": -0.80,   # Negative
        "AUDUSD": -0.75,   # Negative
        "NZDUSD": -0.70,   # Negative
        "USDCAD": +0.60,   # Positive (both USD)
        "USDJPY": +0.50,   # Moderate positive
        "USDCHF": +0.85,   # Strong positive
        "XAUUSD": -0.70,   # Gold inversely correlated with USD
        "XAGUSD": -0.65,   # Silver too
        "BTCUSD": -0.30,   # Weak negative
        "ETHUSD": -0.25,   # Weak negative
    }

    # VIX correlation (risk-off indicator)
    VIX_CORRELATION = {
        "XAUUSD": +0.60,   # Gold is safe haven
        "XAGUSD": +0.40,   # Silver too (weaker)
        "USDJPY": -0.50,   # JPY strengthens in risk-off
        "USDCHF": -0.40,   # CHF is safe haven
        "AUDUSD": -0.50,   # AUD is risk currency
        "BTCUSD": -0.30,   # Crypto drops in risk-off
        "ETHUSD": -0.35,
        "GBPJPY": -0.60,   # Big risk-off mover
    }

    _dxy_cache: Dict = {}
    _cache_time: float = 0
    CACHE_TTL = 600  # 10 minutes

    @classmethod
    async def analyze(cls, symbol: str) -> Dict:
        """
        Cross-market analysis for a symbol.
        Returns direction bias based on DXY and VIX movements.
        """
        result = {
            "bias": "NEUTRAL",
            "confidence": 50,
            "dxy_direction": "UNKNOWN",
            "vix_level": "UNKNOWN",
            "correlation_signal": "NEUTRAL",
            "reasons": [],
        }

        try:
            # Fetch DXY and VIX data from Yahoo Finance RSS
            dxy_data = await cls._fetch_market_sentiment("DXY")
            vix_data = await cls._fetch_market_sentiment("VIX")

            # DXY analysis
            dxy_corr = cls.DXY_CORRELATION.get(symbol, 0)
            if dxy_data and dxy_corr != 0:
                dxy_sent = dxy_data.get("sentiment", "NEUTRAL")
                result["dxy_direction"] = dxy_sent

                if dxy_sent == "BULLISH":  # DXY rising
                    if dxy_corr < 0:
                        result["confidence"] -= int(abs(dxy_corr) * 15)
                        result["reasons"].append(
                            f"💲 DXY RISING → BEARISH for {symbol} (corr: {dxy_corr:+.2f})"
                        )
                    else:
                        result["confidence"] += int(abs(dxy_corr) * 15)
                        result["reasons"].append(
                            f"💲 DXY RISING → BULLISH for {symbol} (corr: {dxy_corr:+.2f})"
                        )
                elif dxy_sent == "BEARISH":  # DXY falling
                    if dxy_corr < 0:
                        result["confidence"] += int(abs(dxy_corr) * 15)
                        result["reasons"].append(
                            f"💲 DXY FALLING → BULLISH for {symbol} (corr: {dxy_corr:+.2f})"
                        )
                    else:
                        result["confidence"] -= int(abs(dxy_corr) * 15)
                        result["reasons"].append(
                            f"💲 DXY FALLING → BEARISH for {symbol} (corr: {dxy_corr:+.2f})"
                        )

            # VIX analysis
            vix_corr = cls.VIX_CORRELATION.get(symbol, 0)
            if vix_data and vix_corr != 0:
                vix_sent = vix_data.get("sentiment", "NEUTRAL")
                result["vix_level"] = vix_sent

                if vix_sent == "BULLISH":  # VIX rising = fear = risk-off
                    if vix_corr > 0:
                        result["confidence"] += int(abs(vix_corr) * 10)
                        result["reasons"].append(
                            f"😰 VIX RISING (risk-off) → BULLISH for {symbol} (safe haven)"
                        )
                    else:
                        result["confidence"] -= int(abs(vix_corr) * 10)
                        result["reasons"].append(
                            f"😰 VIX RISING (risk-off) → BEARISH for {symbol} (risk asset)"
                        )

            # Determine final bias
            if result["confidence"] >= 60:
                result["bias"] = "BUY"
            elif result["confidence"] <= 40:
                result["bias"] = "SELL"
            else:
                result["bias"] = "NEUTRAL"

            # Post to bus
            AgentCommunicationBus.post(
                agent="CrossMarket",
                symbol=symbol,
                msg_type="SIGNAL",
                direction=result["bias"],
                confidence=min(100, max(0, result["confidence"])),
                message=" | ".join(result["reasons"][:2]) if result["reasons"] else "No cross-market data",
                ttl_minutes=20,
                data=result,
            )

        except Exception as e:
            logger.error(f"CrossMarketAgent error [{symbol}]: {e}")

        return result

    @classmethod
    async def _fetch_market_sentiment(cls, indicator: str) -> Optional[Dict]:
        """Fetch sentiment for DXY or VIX via Yahoo Finance RSS."""
        try:
            feeds = {
                "DXY": "https://feeds.finance.yahoo.com/rss/2.0/headline?s=DX-Y.NYB&region=US&lang=en-US",
                "VIX": "https://feeds.finance.yahoo.com/rss/2.0/headline?s=%5EVIX&region=US&lang=en-US",
            }
            url = feeds.get(indicator)
            if not url:
                return None

            headers = {"User-Agent": "Mozilla/5.0 (compatible; TradingBot/2.0)"}
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=6),
                                       headers=headers) as resp:
                    if resp.status != 200:
                        return None
                    text = await resp.text()

            root = ET.fromstring(text)
            headlines = []
            for item in root.iter("item"):
                title = item.find("title")
                if title is not None and title.text:
                    headlines.append(title.text.strip())
                if len(headlines) >= 5:
                    break

            if not headlines:
                return None

            # Simple keyword sentiment
            bull_words = {"rises", "rise", "up", "high", "higher", "surge", "gains",
                          "rally", "climbs", "jumps", "spikes", "strong", "increase"}
            bear_words = {"falls", "fall", "down", "low", "lower", "drops", "plunge",
                          "decline", "sinks", "tumbles", "weak", "decrease"}

            bull = sum(1 for h in headlines for w in h.lower().split() if w in bull_words)
            bear = sum(1 for h in headlines for w in h.lower().split() if w in bear_words)

            if bull > bear:
                return {"sentiment": "BULLISH", "bull": bull, "bear": bear}
            elif bear > bull:
                return {"sentiment": "BEARISH", "bull": bull, "bear": bear}
            return {"sentiment": "NEUTRAL", "bull": bull, "bear": bear}

        except Exception:
            return None


# ═════════════════════════════════════════════════════════════════════
# AGENT 4: ECONOMIC CALENDAR — High-Impact Event Detection
# ═════════════════════════════════════════════════════════════════════
class EconomicCalendarAgent:
    """
    Monitors upcoming economic events to:
    1. BLOCK trades 30 min before high-impact events (NFP, CPI, FOMC, etc.)
    2. Provide directional bias after events (rate hike = USD bullish)
    3. Track event history for pattern recognition

    Uses Forex Factory calendar scraping (free, no API key).
    """

    # High-impact events that move markets
    HIGH_IMPACT_KEYWORDS = {
        "nonfarm", "non-farm", "nfp", "employment", "fomc", "fed",
        "interest rate", "cpi", "inflation", "gdp", "pmi",
        "ecb", "boe", "boj", "rba", "rbnz",
        "retail sales", "trade balance", "unemployment",
    }

    # Currency-to-event mapping
    CURRENCY_MAP = {
        "USD": ["XAUUSD", "XAGUSD", "EURUSD", "GBPUSD", "USDJPY",
                "USDCHF", "AUDUSD", "USDCAD", "NZDUSD", "BTCUSD", "ETHUSD"],
        "EUR": ["EURUSD", "EURJPY", "EURGBP"],
        "GBP": ["GBPUSD", "GBPJPY", "EURGBP"],
        "JPY": ["USDJPY", "GBPJPY", "EURJPY"],
        "AUD": ["AUDUSD"],
        "CAD": ["USDCAD"],
        "NZD": ["NZDUSD"],
        "CHF": ["USDCHF"],
    }

    _calendar_cache: List[Dict] = []
    _last_fetch: float = 0
    CACHE_TTL = 1800  # 30 minutes

    @classmethod
    async def check_events(cls, symbol: str) -> Dict:
        """
        Check for upcoming high-impact events affecting this symbol.
        Returns: {"safe_to_trade": bool, "next_event": str, "minutes_until": int}
        """
        result = {
            "safe_to_trade": True,
            "next_event": None,
            "minutes_until": 999,
            "event_impact": "NONE",
            "affected_symbols": [],
            "reasons": [],
        }

        try:
            events = await cls._fetch_calendar()

            now = datetime.utcnow()
            for event in events:
                # Check if this event affects our symbol
                event_currency = event.get("currency", "").upper()
                affected = cls.CURRENCY_MAP.get(event_currency, [])

                if symbol not in affected:
                    continue

                # Check if event is upcoming (within 60 minutes)
                event_time = event.get("datetime")
                if not event_time:
                    continue

                try:
                    if isinstance(event_time, str):
                        event_dt = datetime.fromisoformat(event_time.replace("Z", "+00:00"))
                    else:
                        event_dt = event_time
                    # Make both timezone-naive for comparison (strip tz info)
                    if hasattr(event_dt, 'tzinfo') and event_dt.tzinfo is not None:
                        event_dt = event_dt.replace(tzinfo=None)
                except (ValueError, TypeError):
                    continue

                diff_minutes = (event_dt - now).total_seconds() / 60

                # High-impact event +/- 30 minutes = BLOCK (Before and After)
                is_high_impact = event.get("impact", "").lower() == "high" or \
                    any(kw in event.get("title", "").lower() for kw in cls.HIGH_IMPACT_KEYWORDS)

                if is_high_impact and -30 <= diff_minutes <= 30:
                    result["safe_to_trade"] = False
                    result["next_event"] = event.get("title", "Unknown Event")
                    result["minutes_until"] = int(diff_minutes)
                    result["event_impact"] = "HIGH"
                    result["affected_symbols"] = affected
                    
                    time_msg = f"in {int(diff_minutes)} min" if diff_minutes > 0 else f"{abs(int(diff_minutes))} min ago"
                    result["reasons"].append(
                        f"⛔ HIGH-IMPACT EVENT {time_msg}: "
                        f"{event.get('title', '?')} ({event_currency}) — BLOCK ALL TRADES"
                    )

                    # Post BLOCK to bus
                    ttl_val = int(30 + diff_minutes) if diff_minutes < 0 else int(diff_minutes + 30)
                    AgentCommunicationBus.post(
                        agent="EconomicCalendar",
                        symbol=symbol,
                        msg_type="BLOCK",
                        direction="NEUTRAL",
                        confidence=0,
                        message=f"HIGH-IMPACT: {event.get('title', '?')} {time_msg}",
                        ttl_minutes=ttl_val,
                    )
                    break

                elif is_high_impact and 30 < diff_minutes <= 60:
                    result["next_event"] = event.get("title", "Unknown")
                    result["minutes_until"] = int(diff_minutes)
                    result["event_impact"] = "WARNING"
                    result["reasons"].append(
                        f"⚠️ High-impact event in {int(diff_minutes)} min: "
                        f"{event.get('title', '?')} ({event_currency}) — trade with caution"
                    )

            if result["safe_to_trade"] and not result["reasons"]:
                result["reasons"].append(f"✅ No upcoming high-impact events for {symbol}")

            # Post to bus (even if safe — other agents need to know)
            if result["safe_to_trade"]:
                AgentCommunicationBus.post(
                    agent="EconomicCalendar",
                    symbol=symbol,
                    msg_type="INFO",
                    direction="NEUTRAL",
                    confidence=50,
                    message=result["reasons"][0] if result["reasons"] else "Calendar clear",
                    ttl_minutes=15,
                )

        except Exception as e:
            logger.error(f"EconomicCalendarAgent error [{symbol}]: {e}")
            result["reasons"].append(f"⚠️ Calendar check error: {str(e)[:60]}")

        return result

    @classmethod
    async def _fetch_calendar(cls) -> List[Dict]:
        """Fetch economic calendar (cached)."""
        if time.time() - cls._last_fetch < cls.CACHE_TTL and cls._calendar_cache:
            return cls._calendar_cache

        try:
            # Use Forex Factory XML calendar (free, no API key)
            url = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                    if resp.status != 200:
                        return cls._calendar_cache
                    data = await resp.json()

            events = []
            for item in data:
                events.append({
                    "title": item.get("title", ""),
                    "currency": item.get("country", ""),
                    "impact": item.get("impact", ""),
                    "datetime": item.get("date", ""),
                    "forecast": item.get("forecast", ""),
                    "previous": item.get("previous", ""),
                })

            cls._calendar_cache = events
            cls._last_fetch = time.time()
            return events

        except Exception as e:
            logger.debug(f"Calendar fetch error: {e}")
            return cls._calendar_cache


# ═════════════════════════════════════════════════════════════════════
# AGENT 5: REWARD SYSTEM — Track and reward profitable agents
# ═════════════════════════════════════════════════════════════════════
class AgentRewardSystem:
    """
    Tracks which agents contribute to profitable trades.
    Agents that produce better signals get higher confidence weight.

    Scoring:
    - Agent correctly predicted direction → +10 points
    - Agent correctly identified killzone → +5 points
    - Agent blocked a trade that would have lost → +15 points
    - Agent's signal led to a loss → -10 points

    Top agents get confidence multiplier:
    - Score > 100: 1.2x confidence weight
    - Score > 50:  1.1x confidence weight
    - Score < -20: 0.8x confidence weight (penalized)
    """

    _scores: Dict[str, int] = defaultdict(int)
    _trade_log: List[Dict] = []
    _SAVE_FILE = "agent_rewards.json"

    @classmethod
    def load(cls):
        """Load reward scores from disk."""
        try:
            import os
            path = os.path.join(os.path.dirname(__file__), cls._SAVE_FILE)
            if os.path.exists(path):
                with open(path, "r") as f:
                    data = json.load(f)
                    cls._scores = defaultdict(int, data.get("scores", {}))
                    cls._trade_log = data.get("log", [])[-200:]
        except Exception as e:
            logger.debug(f"Reward system load error: {e}")

    @classmethod
    def save(cls):
        """Save reward scores to disk using atomic writes."""
        try:
            import os
            import tempfile
            path = os.path.join(os.path.dirname(__file__), cls._SAVE_FILE)
            dir_path = os.path.dirname(path)
            # Atomic write: temp file + os.replace() prevents corruption on crash
            with tempfile.NamedTemporaryFile('w', dir=dir_path, delete=False,
                                              suffix='.tmp', encoding='utf-8') as tmp:
                json.dump({
                    "scores": dict(cls._scores),
                    "log": cls._trade_log[-200:],
                }, tmp, indent=2)
                tmp.flush()
                os.fsync(tmp.fileno())
            os.replace(tmp.name, path)
        except Exception as e:
            logger.debug(f"Reward system save error: {e}")
            try:
                if 'tmp' in locals() and os.path.exists(tmp.name):
                    os.unlink(tmp.name)
            except Exception:
                pass

    @classmethod
    def reward(cls, agent: str, points: int, reason: str):
        """Award/penalize an agent."""
        cls._scores[agent] += points
        cls._trade_log.append({
            "agent": agent,
            "points": points,
            "reason": reason,
            "timestamp": datetime.utcnow().isoformat(),
            "total": cls._scores[agent],
        })
        icon = "🏆" if points > 0 else "📉"
        logger.info(f"{icon} REWARD: {agent} {points:+d} pts — {reason} (total: {cls._scores[agent]})")

    @classmethod
    def record_trade_result(cls, symbol: str, direction: str,
                            is_profit: bool, agents_involved: List[str]):
        """Record trade outcome and reward/penalize contributing agents."""
        if is_profit:
            for agent in agents_involved:
                cls.reward(agent, +10, f"Profitable {direction} {symbol}")
        else:
            for agent in agents_involved:
                cls.reward(agent, -8, f"Loss on {direction} {symbol}")
        cls.save()

    @classmethod
    def record_blocked_trade(cls, symbol: str, blocking_agent: str,
                             would_have_lost: bool):
        """Reward agent for correctly blocking a bad trade."""
        if would_have_lost:
            cls.reward(blocking_agent, +15, f"Correctly blocked losing trade on {symbol}")
        else:
            cls.reward(blocking_agent, -5, f"Wrongly blocked profitable trade on {symbol}")
        cls.save()

    @classmethod
    def get_multiplier(cls, agent: str) -> float:
        """Get confidence multiplier for an agent based on its score."""
        score = cls._scores.get(agent, 0)
        if score > 100:
            return 1.2
        elif score > 50:
            return 1.1
        elif score < -20:
            return 0.8
        return 1.0

    @classmethod
    def leaderboard(cls) -> str:
        """Return agent leaderboard."""
        sorted_agents = sorted(cls._scores.items(), key=lambda x: x[1], reverse=True)
        if not sorted_agents:
            return "No agent scores yet"
        lines = []
        for i, (agent, score) in enumerate(sorted_agents, 1):
            medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else "  "
            mult = cls.get_multiplier(agent)
            lines.append(f"{medal} #{i} {agent:25s}: {score:+5d} pts (×{mult:.1f})")
        return "\n".join(lines)


# ═════════════════════════════════════════════════════════════════════
# MASTER FUNCTION: Run all institutional agents for a symbol
# ═════════════════════════════════════════════════════════════════════
async def run_institutional_analysis(symbol: str, df_h1=None,
                                      tick_volume: float = 0,
                                      avg_volume: float = 0) -> Dict:
    """
    Run ALL institutional agents concurrently for a symbol.
    Returns combined analysis with consensus direction.

    This is called by the main team loop for every symbol, every cycle.
    """
    try:
        # Run all agents concurrently (fast!)
        inst_task = InstitutionalFlowAgent.analyze(symbol, df_h1, tick_volume, avg_volume)
        web_task = WebResearchAgent.research(symbol)
        cross_task = CrossMarketAgent.analyze(symbol)
        calendar_task = EconomicCalendarAgent.check_events(symbol)

        inst, web, cross, calendar = await asyncio.gather(
            inst_task, web_task, cross_task, calendar_task,
            return_exceptions=True,
        )

        # Handle exceptions gracefully (zero-error tolerance)
        if isinstance(inst, Exception):
            logger.error(f"InstitutionalFlow error: {inst}")
            inst = {"bias": "NEUTRAL", "confidence": 50, "reasons": [f"⚠️ Error: {inst}"]}
        if isinstance(web, Exception):
            logger.error(f"WebResearch error: {web}")
            web = {"sentiment": "NEUTRAL", "confidence": 50, "reasons": [f"⚠️ Error: {web}"]}
        if isinstance(cross, Exception):
            logger.error(f"CrossMarket error: {cross}")
            cross = {"bias": "NEUTRAL", "confidence": 50, "reasons": [f"⚠️ Error: {cross}"]}
        if isinstance(calendar, Exception):
            logger.error(f"Calendar error: {calendar}")
            calendar = {"safe_to_trade": True, "reasons": [f"⚠️ Error: {calendar}"]}

        # Get consensus from communication bus
        consensus = AgentCommunicationBus.get_consensus(symbol)

        # Compile all reasons
        all_reasons = []
        all_reasons.extend(inst.get("reasons", []))
        all_reasons.extend(web.get("reasons", []))
        all_reasons.extend(cross.get("reasons", []))
        all_reasons.extend(calendar.get("reasons", []))

        return {
            "symbol": symbol,
            "consensus": consensus,
            "institutional": inst,
            "web_research": web,
            "cross_market": cross,
            "calendar": calendar,
            "safe_to_trade": calendar.get("safe_to_trade", True) and not consensus.get("blocked", False),
            "institutional_direction": consensus.get("direction", "NEUTRAL"),
            "institutional_score": consensus.get("score", 0),
            "agents_agree": consensus.get("agents_agree", 0),
            "agents_disagree": consensus.get("agents_disagree", 0),
            "reasons": all_reasons,
        }

    except Exception as e:
        logger.error(f"run_institutional_analysis error [{symbol}]: {e}", exc_info=True)
        return {
            "symbol": symbol,
            "consensus": {"direction": "NEUTRAL", "score": 0, "blocked": False},
            "safe_to_trade": True,
            "institutional_direction": "NEUTRAL",
            "institutional_score": 0,
            "agents_agree": 0,
            "agents_disagree": 0,
            "institutional": {},
            "web_research": {},
            "cross_market": {"bias": "NEUTRAL", "confidence": 50, "reasons": []},
            "calendar": {"safe_to_trade": True, "reasons": [f"⚠️ Error: {e}"]},
            "reasons": [f"⚠️ run_institutional_analysis failed: {e}"],
        }
