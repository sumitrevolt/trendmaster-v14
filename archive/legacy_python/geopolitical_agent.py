"""
GEOPOLITICAL RISK AGENT — War/Conflict Tracking & Auto-Adjustment
===================================================================
Tracks active wars/conflicts and auto-adjusts trading bias.

CURRENT ACTIVE CONFLICTS (March 2026):
1. US-Iran War (Feb 2026+) — Oil surge, Gold $5300+, USD strong
2. Russia-Ukraine (Feb 2022+) — Energy crisis, EUR weak, Gold bullish
3. Israel-Gaza/Hezbollah (Oct 2023+) — Middle East risk, Gold bullish
4. Pakistan-Afghanistan (Feb 2026+) — Regional instability
5. Sudan Civil War — Humanitarian crisis
6. Myanmar Civil War — Regional instability

HOW IT WORKS:
1. Scans news every 5 minutes for war/conflict/ceasefire keywords
2. Maintains WAR_STATUS for each conflict zone
3. When war ACTIVE → adjusts symbol biases (gold bullish, risk-off)
4. When ceasefire/peace detected → auto-reduces war premium
5. When war ENDS → auto-disables war mode for that conflict

MARKET IMPACT MAP:
  War escalation → Gold ↑, Silver ↑, JPY ↑, CHF ↑, Oil ↑
  War escalation → EUR ↓, GBP ↓, AUD ↓, Crypto mixed
  War de-escalation → Gold ↓, Risk assets ↑
  Ceasefire → Reverse of escalation
"""

import logging
import time
import asyncio
import aiohttp
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from collections import defaultdict

logger = logging.getLogger(__name__)

try:
    from institutional_agents import AgentCommunicationBus
except ImportError:
    AgentCommunicationBus = None


# ═════════════════════════════════════════════════════════════════════
# CONFLICT DEFINITIONS — Current active wars (March 2026)
# ═════════════════════════════════════════════════════════════════════
CONFLICTS = {
    "US_IRAN": {
        "name": "US-Iran War",
        "start": "2026-02-28",
        "status": "ACTIVE",       # ACTIVE / CEASEFIRE / ENDED
        "severity": "HIGH",       # HIGH / MEDIUM / LOW
        "region": "MIDDLE_EAST",
        "keywords_active": [
            "iran war", "iran strike", "iran attack", "iran missile",
            "us iran", "israel iran", "strait of hormuz", "persian gulf",
            "iran retaliation", "iran nuclear", "iran escalation",
            "iran conflict", "iran bomb", "middle east war",
        ],
        "keywords_ceasefire": [
            "iran ceasefire", "iran peace", "iran deal", "iran negotiation",
            "iran truce", "iran de-escalation", "iran talks", "iran diplomacy",
            "iran agreement", "iran settlement",
        ],
        "impact": {
            # Symbol: (direction_when_active, confidence_boost)
            "XAUUSD": ("BUY", 15),    # Gold is #1 safe haven
            "XAGUSD": ("BUY", 10),    # Silver follows gold
            "USDJPY": ("SELL", 8),    # JPY strengthens (safe haven)
            "USDCHF": ("SELL", 8),    # CHF strengthens (safe haven)
            "EURUSD": ("SELL", 5),    # EUR weakens (energy crisis)
            "GBPUSD": ("SELL", 3),    # GBP weakens
            "AUDUSD": ("SELL", 5),    # AUD weakens (risk-off)
            "USDCAD": ("SELL", 5),    # CAD strengthens (oil surge)
            "BTCUSD": ("NEUTRAL", 0), # Crypto mixed in war
        },
    },
    "RUSSIA_UKRAINE": {
        "name": "Russia-Ukraine War",
        "start": "2022-02-24",
        "status": "ACTIVE",
        "severity": "HIGH",
        "region": "EASTERN_EUROPE",
        "keywords_active": [
            "russia ukraine", "ukraine war", "russia attack", "ukraine strike",
            "russia missile", "ukraine front", "russia escalation",
            "nato russia", "russia nuclear", "ukraine offensive",
            "donbas", "kherson", "zaporizhzhia",
        ],
        "keywords_ceasefire": [
            "ukraine ceasefire", "ukraine peace", "russia peace",
            "ukraine truce", "ukraine deal", "ukraine negotiation",
            "minsk", "ukraine settlement", "ukraine talks",
            "russia ceasefire", "russia truce",
        ],
        "impact": {
            "XAUUSD": ("BUY", 10),
            "XAGUSD": ("BUY", 5),
            "EURUSD": ("SELL", 8),    # EUR most affected (European war)
            "GBPUSD": ("SELL", 3),
            "USDJPY": ("SELL", 5),
            "USDCHF": ("SELL", 5),
        },
    },
    "ISRAEL_GAZA": {
        "name": "Israel-Gaza/Hezbollah Conflict",
        "start": "2023-10-07",
        "status": "ACTIVE",
        "severity": "HIGH",
        "region": "MIDDLE_EAST",
        "keywords_active": [
            "israel gaza", "hamas", "hezbollah", "israel attack",
            "gaza war", "israel strike", "israel bomb", "lebanon war",
            "israel hezbollah", "israel iran", "rafah", "gaza ceasefire collapse",
        ],
        "keywords_ceasefire": [
            "gaza ceasefire", "gaza peace", "gaza deal", "gaza truce",
            "hamas deal", "hostage deal", "gaza negotiation",
            "gaza reconstruction", "gaza agreement",
        ],
        "impact": {
            "XAUUSD": ("BUY", 12),
            "XAGUSD": ("BUY", 6),
            "USDJPY": ("SELL", 5),
            "USDCHF": ("SELL", 5),
            "EURUSD": ("SELL", 3),
        },
    },
    "PAKISTAN_AFGHANISTAN": {
        "name": "Pakistan-Afghanistan War",
        "start": "2026-02-27",
        "status": "ACTIVE",
        "severity": "MEDIUM",
        "region": "SOUTH_ASIA",
        "keywords_active": [
            "pakistan afghanistan", "pakistan war", "pakistan bomb",
            "kabul strike", "pakistan attack", "ghazab lil haq",
            "pakistan taliban", "pakistan air strike",
        ],
        "keywords_ceasefire": [
            "pakistan ceasefire", "pakistan peace", "pakistan talks",
            "pakistan afghanistan deal",
        ],
        "impact": {
            "XAUUSD": ("BUY", 5),    # Minor gold impact
            "XAGUSD": ("BUY", 3),
        },
    },
}


class GeopoliticalRiskAgent:
    """
    Monitors geopolitical conflicts and adjusts trading signals.

    Scans news feeds every 5 minutes for war/ceasefire keywords.
    Maintains real-time WAR_STATUS for each conflict.
    Auto-adjusts symbol biases when wars start/escalate/end.
    """

    _war_status: Dict[str, Dict] = {}  # conflict_id → status
    _last_scan: float = 0
    SCAN_INTERVAL = 300  # 5 minutes
    _headlines_cache: List[str] = []
    _cache_time: float = 0

    # News RSS feeds for geopolitical monitoring
    NEWS_FEEDS = [
        "https://news.google.com/rss/search?q=war+conflict+ceasefire+peace+military&hl=en-US",
        "https://feeds.bbci.co.uk/news/world/rss.xml",
        "https://feeds.finance.yahoo.com/rss/2.0/headline?s=GC%3DF&region=US&lang=en-US",
    ]

    @classmethod
    def _init_status(cls):
        """Initialize war status from conflict definitions."""
        if not cls._war_status:
            for cid, conf in CONFLICTS.items():
                cls._war_status[cid] = {
                    "name": conf["name"],
                    "status": conf["status"],
                    "severity": conf["severity"],
                    "last_escalation_seen": None,
                    "last_ceasefire_seen": None,
                    "escalation_count": 0,
                    "ceasefire_count": 0,
                    "confidence": 70 if conf["status"] == "ACTIVE" else 30,
                }

    @classmethod
    async def scan(cls) -> Dict:
        """
        Scan news for war/ceasefire updates.
        Returns: {conflict_id: {status, severity, confidence, headlines}}
        """
        cls._init_status()

        now = time.time()
        if now - cls._last_scan < cls.SCAN_INTERVAL:
            return cls._war_status
        cls._last_scan = now

        # Fetch fresh headlines
        headlines = await cls._fetch_headlines()
        if not headlines:
            return cls._war_status

        headlines_lower = [h.lower() for h in headlines]

        # Check each conflict against headlines
        for cid, conf in CONFLICTS.items():
            escalation_hits = 0
            ceasefire_hits = 0
            matched_headlines = []

            for i, h in enumerate(headlines_lower):
                # Check escalation keywords
                for kw in conf["keywords_active"]:
                    if kw in h:
                        escalation_hits += 1
                        matched_headlines.append(headlines[i][:80])
                        break

                # Check ceasefire keywords
                for kw in conf["keywords_ceasefire"]:
                    if kw in h:
                        ceasefire_hits += 1
                        break

            status = cls._war_status[cid]

            # Update status based on news
            if escalation_hits >= 2:
                # War is definitely active / escalating
                status["status"] = "ACTIVE"
                status["severity"] = "HIGH" if escalation_hits >= 3 else conf["severity"]
                status["last_escalation_seen"] = datetime.utcnow().isoformat()
                status["escalation_count"] += escalation_hits
                status["confidence"] = min(95, 70 + escalation_hits * 5)
                status["recent_headlines"] = matched_headlines[:3]
                logger.info(
                    f"🔴 WAR ACTIVE: {conf['name']} — {escalation_hits} escalation signals in news"
                )

            elif ceasefire_hits >= 2 and escalation_hits == 0:
                # Ceasefire signals detected, no escalation
                if status["status"] == "ACTIVE":
                    status["status"] = "CEASEFIRE"
                    status["severity"] = "LOW"
                    status["confidence"] = max(20, status["confidence"] - 20)
                    status["last_ceasefire_seen"] = datetime.utcnow().isoformat()
                    status["ceasefire_count"] += ceasefire_hits
                    logger.info(
                        f"🟡 CEASEFIRE: {conf['name']} — {ceasefire_hits} ceasefire signals detected"
                    )

            elif ceasefire_hits >= 3 and escalation_hits == 0:
                # Strong ceasefire/peace signals — war likely ending
                status["status"] = "ENDING"
                status["severity"] = "LOW"
                status["confidence"] = max(10, status["confidence"] - 30)
                logger.info(
                    f"🟢 WAR ENDING: {conf['name']} — strong peace/ceasefire signals"
                )

            # Decay: if no news about this conflict for a while, reduce confidence
            last_esc = status.get("last_escalation_seen")
            if last_esc and escalation_hits == 0 and ceasefire_hits == 0:
                try:
                    last_dt = datetime.fromisoformat(last_esc)
                    hours_since = (datetime.utcnow() - last_dt).total_seconds() / 3600
                    if hours_since > 24:
                        # No news for 24+ hours — reduce war premium
                        status["confidence"] = max(20, status["confidence"] - 5)
                    if hours_since > 72:
                        # No news for 3+ days — war likely de-escalating
                        if status["status"] == "ACTIVE":
                            status["status"] = "COOLING"
                            status["severity"] = "MEDIUM"
                except (ValueError, TypeError):
                    pass

        return cls._war_status

    @classmethod
    def get_symbol_adjustment(cls, symbol: str) -> Dict:
        """
        Get trading adjustment for a symbol based on active wars.
        Returns: {"direction": BUY/SELL/NEUTRAL, "confidence_adj": int,
                  "wars_active": [...], "reasons": [...]}
        """
        cls._init_status()

        total_adj = 0
        direction_score = 0  # Positive = BUY, negative = SELL
        active_wars = []
        reasons = []

        for cid, conf in CONFLICTS.items():
            status = cls._war_status.get(cid, {})
            war_status = status.get("status", "UNKNOWN")
            war_conf = status.get("confidence", 50)

            if symbol not in conf.get("impact", {}):
                continue

            impact_dir, impact_strength = conf["impact"][symbol]

            if war_status == "ACTIVE":
                # War is active — apply full impact
                scale = war_conf / 100  # Scale by confidence
                adj = int(impact_strength * scale)

                if impact_dir == "BUY":
                    direction_score += adj
                    total_adj += adj
                elif impact_dir == "SELL":
                    direction_score -= adj
                    total_adj += adj

                active_wars.append(conf["name"])
                severity_icon = "🔴" if status.get("severity") == "HIGH" else "🟡"
                reasons.append(
                    f"{severity_icon} {conf['name']}: {impact_dir} {symbol} "
                    f"(+{adj} conf, war {war_conf}% active)"
                )

            elif war_status == "CEASEFIRE":
                # Ceasefire — reduce impact by 60%
                adj = int(impact_strength * 0.4 * (war_conf / 100))
                if impact_dir == "BUY":
                    direction_score += adj
                elif impact_dir == "SELL":
                    direction_score -= adj
                reasons.append(
                    f"🟡 {conf['name']}: CEASEFIRE — {impact_dir} impact reduced 60%"
                )

            elif war_status in ("ENDING", "COOLING"):
                # War ending — minimal impact, almost reversed
                reasons.append(
                    f"🟢 {conf['name']}: {war_status} — war premium fading"
                )

        # Determine overall direction
        if direction_score > 5:
            direction = "BUY"
        elif direction_score < -5:
            direction = "SELL"
        else:
            direction = "NEUTRAL"

        result = {
            "direction": direction,
            "confidence_adj": min(25, total_adj),  # Cap at 25 max
            "direction_score": direction_score,
            "wars_active": active_wars,
            "wars_count": len(active_wars),
            "reasons": reasons,
        }

        # Post to communication bus
        if AgentCommunicationBus and active_wars:
            AgentCommunicationBus.post(
                agent="GeopoliticalRisk",
                symbol=symbol,
                msg_type="SIGNAL" if active_wars else "INFO",
                direction=direction,
                confidence=min(80, 50 + total_adj),
                message=f"Wars active: {', '.join(active_wars[:2])} → {direction} {symbol}",
                ttl_minutes=30,
                data=result,
            )

        return result

    @classmethod
    async def _fetch_headlines(cls) -> List[str]:
        """Fetch latest headlines from multiple news sources."""
        now = time.time()
        if now - cls._cache_time < 120 and cls._headlines_cache:  # 2 min cache
            return cls._headlines_cache

        all_headlines = []
        for feed_url in cls.NEWS_FEEDS:
            try:
                headers = {"User-Agent": "Mozilla/5.0 (compatible; TradingBot/2.0)"}
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        feed_url,
                        timeout=aiohttp.ClientTimeout(total=8),
                        headers=headers,
                    ) as resp:
                        if resp.status != 200:
                            continue
                        text = await resp.text()

                root = ET.fromstring(text)
                for item in root.iter("item"):
                    title = item.find("title")
                    if title is not None and title.text:
                        all_headlines.append(title.text.strip())
                    if len(all_headlines) >= 50:
                        break

            except Exception:
                continue

        cls._headlines_cache = all_headlines
        cls._cache_time = now
        return all_headlines

    @classmethod
    def report(cls) -> str:
        """Generate war status report."""
        cls._init_status()
        lines = ["🌍 GEOPOLITICAL STATUS:"]

        for cid, status in cls._war_status.items():
            conf = CONFLICTS.get(cid, {})
            s = status.get("status", "UNKNOWN")
            sev = status.get("severity", "?")
            c = status.get("confidence", 0)

            icon = "🔴" if s == "ACTIVE" else "🟡" if s in ("CEASEFIRE", "COOLING") else "🟢" if s == "ENDING" else "⚪"
            lines.append(
                f"  {icon} {conf.get('name', cid)}: {s} (severity: {sev}, conf: {c}%)"
            )

            # Show affected symbols
            impacts = []
            for sym, (d, strength) in conf.get("impact", {}).items():
                if strength > 0 and s == "ACTIVE":
                    impacts.append(f"{sym}→{d}")
            if impacts:
                lines.append(f"      Impact: {', '.join(impacts[:5])}")

        return "\n".join(lines)
