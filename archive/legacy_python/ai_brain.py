"""
AI Brain Module — MULTI-AI BRAIN SYSTEM for trading agents.
Uses MULTIPLE FREE AI providers for maximum intelligence:
  1. Groq (Llama 3.3 70B) — 30 req/min, ultra-fast (PRIMARY for chat)
  2. Google Gemini 2.5 Flash — 5 req/min (for training + web research)
  3. Claude Knowledge Base — Pre-trained trading wisdom (instant, no API needed)
Each agent has its own personality, knowledge domain, memory, and can learn.
"""

import os
import json
import asyncio
import logging
import re
import tempfile
import threading
import httpx
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from pathlib import Path

# Load environment
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")

logger = logging.getLogger("AIBrain")


_json_write_locks = {}
_json_write_locks_lock = threading.Lock()

def _get_file_lock(filepath):
    """Get or create a per-file threading lock."""
    with _json_write_locks_lock:
        if filepath not in _json_write_locks:
            _json_write_locks[filepath] = threading.Lock()
        return _json_write_locks[filepath]

def _atomic_json_write(filepath, data, **kwargs):
    """Write JSON atomically — temp file + rename to prevent corruption on crash.
    Falls back to direct write if atomic rename fails (e.g., Windows permission issues).
    Thread-safe via per-file locks to prevent concurrent write corruption."""
    filepath = str(filepath)
    file_lock = _get_file_lock(filepath)
    if not file_lock.acquire(timeout=10):
        logger.warning(f"Timeout waiting for write lock on {filepath}")
        return
    tmp = None
    try:
        # Pre-serialize to string to validate before writing
        json_str = json.dumps(data, **kwargs)
        dir_path = os.path.dirname(filepath)
        # newline='\n' forces Unix line endings — prevents CRLF corruption on Windows
        with tempfile.NamedTemporaryFile('w', dir=dir_path, delete=False,
                                          suffix='.tmp', encoding='utf-8', newline='\n') as tmp:
            tmp.write(json_str)
            tmp.flush()
            os.fsync(tmp.fileno())
            tmp_name = tmp.name
        # Try atomic rename
        try:
            os.replace(tmp_name, filepath)
        except (OSError, PermissionError) as e:
            # Fallback: direct write if atomic rename fails (Windows permission issues)
            logger.debug(f"Atomic rename failed for {filepath}, falling back to direct write: {e}")
            try:
                os.unlink(tmp_name)
            except Exception:
                pass
            with open(filepath, 'w', encoding='utf-8', newline='\n') as f:
                f.write(json_str)
                f.flush()
                os.fsync(f.fileno())
        else:
            # Atomic rename succeeded, also update .bak file
            bak_path = filepath + ".bak"
            try:
                with tempfile.NamedTemporaryFile('w', dir=dir_path, delete=False,
                                                  suffix='.tmp', encoding='utf-8', newline='\n') as tmp_bak:
                    json.dump(data, tmp_bak, **kwargs)
                    tmp_bak.flush()
                    os.fsync(tmp_bak.fileno())
                    tmp_bak_name = tmp_bak.name
                try:
                    os.replace(tmp_bak_name, bak_path)
                except (OSError, PermissionError):
                    # Backup write failure is non-critical
                    try:
                        os.unlink(tmp_bak_name)
                    except Exception:
                        pass
            except Exception:
                pass  # Backup write failure is non-critical
    except Exception as e:
        logger.error(f"Failed to write {filepath}: {e}")
        try:
            if tmp and os.path.exists(tmp.name):
                os.unlink(tmp.name)
        except Exception:
            pass
    finally:
        file_lock.release()

# ═══════════════════════════════════════════════════════════════════════
# CLAUDE KNOWLEDGE BASE — Pre-trained trading wisdom (instant, free)
# ═══════════════════════════════════════════════════════════════════════
KNOWLEDGE_BASE_FILE = Path(__file__).parent / "claude_knowledge_base.json"
_knowledge_base: dict = {}

def _load_knowledge_base():
    global _knowledge_base
    try:
        if KNOWLEDGE_BASE_FILE.exists():
            with open(KNOWLEDGE_BASE_FILE, "r", encoding="utf-8") as f:
                _knowledge_base = json.load(f)
            logger.info(f"📚 Claude Knowledge Base loaded — {len(json.dumps(_knowledge_base))} chars of trading wisdom")
    except Exception as e:
        logger.warning(f"⚠️ Knowledge base load failed: {e}")

_load_knowledge_base()

def get_knowledge_for_sector(sector: str) -> str:
    """Get Claude's pre-trained knowledge for a sector."""
    kb = _knowledge_base
    parts = []

    if sector == "METALS":
        if "METALS" in kb:
            m = kb["METALS"]
            if "gold_xauusd" in m:
                g = m["gold_xauusd"]
                parts.append(f"GOLD KEY LEVELS: Support={g.get('key_levels_2026',{}).get('major_support','?')}, "
                           f"Resistance={g.get('key_levels_2026',{}).get('major_resistance','?')}")
                parts.append("TRADING RULES: " + " | ".join(g.get("trading_rules", [])[:4]))
            if "silver_xagusd" in m:
                parts.append("SILVER RULES: " + " | ".join(m["silver_xagusd"].get("trading_rules", [])[:3]))

    elif sector == "FOREX":
        if "FOREX" in kb:
            f = kb["FOREX"]
            for pair in ["eurusd", "gbpusd", "usdjpy"]:
                if pair in f:
                    p = f[pair]
                    parts.append(f"{pair.upper()} LEVELS: Support={p.get('key_levels_2026',{}).get('major_support','?')}, "
                               f"Resistance={p.get('key_levels_2026',{}).get('major_resistance','?')}")
                    parts.append(f"{pair.upper()} RULES: " + " | ".join(p.get("trading_rules", [])[:2]))
            if "dxy_dollar_index" in f:
                parts.append("DXY: " + " | ".join(f["dxy_dollar_index"].get("rules", [])[:2]))

    elif sector == "CRYPTO":
        if "CRYPTO" in kb:
            c = kb["CRYPTO"]
            if "btcusd" in c:
                b = c["btcusd"]
                parts.append(f"BTC LEVELS: Support={b.get('key_levels_2026',{}).get('major_support','?')}, "
                           f"Resistance={b.get('key_levels_2026',{}).get('major_resistance','?')}")
                parts.append("BTC RULES: " + " | ".join(b.get("trading_rules", [])[:4]))
            if "ethusd" in c:
                parts.append("ETH RULES: " + " | ".join(c["ethusd"].get("trading_rules", [])[:3]))

    # Add universal wisdom
    if "UNIVERSAL_TRADING_WISDOM" in kb:
        u = kb["UNIVERSAL_TRADING_WISDOM"]
        parts.append("RISK RULES: " + " | ".join(u.get("risk_management", [])[:3]))
        parts.append("SMC WISDOM: " + " | ".join(u.get("smart_money_concepts", [])[:3]))

    # Add agent training rules (v2.0)
    if "AGENT_TRAINING" in kb:
        at = kb["AGENT_TRAINING"]
        # Include agent-specific training if available
        for agent_name in ["SignalGenerator", "RiskManager", "SmartMoney", "OperatorMind"]:
            if agent_name in at:
                rules = at[agent_name].get("training_rules", [])[:2]
                if rules:
                    parts.append(f"{agent_name} TRAINING: " + " | ".join(rules))

    # Add loss prevention rules
    if "LOSS_PREVENTION_RULES" in kb:
        lp = kb["LOSS_PREVENTION_RULES"]
        parts.append("LOSS PREVENTION: " + " | ".join(lp.get("rules", [])[:3]))

    return "\n".join(parts) if parts else ""


# ═══════════════════════════════════════════════════════════════════════
# MULTI-AI PROVIDER SYSTEM — Groq (PRIMARY) + Gemini (SECONDARY)
# ═══════════════════════════════════════════════════════════════════════
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
XAI_API_KEY = os.getenv("XAI_API_KEY", "")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
CEREBRAS_API_KEY = os.getenv("CEREBRAS_API_KEY", "")
COHERE_API_KEY = os.getenv("COHERE_API_KEY", "")
TOGETHER_API_KEY = os.getenv("TOGETHER_API_KEY", "")

GEMINI_MODEL = "gemini-2.0-flash-lite"  # Higher free quota: 30 RPM per key
GROQ_MODEL = "llama-3.3-70b-versatile"  # Free, 30 req/min, ultra-fast
XAI_MODEL = "grok-3-mini-fast"  # xAI Grok — fast, smart, free tier
CEREBRAS_MODEL = "llama-3.1-8b"  # Fallback-first: llama-3.1-8b is most stable. Cerebras 3.3-70b & Qwen 3-32b deprecated
COHERE_MODEL = "command-r-plus"  # Free trial: 1000 calls/month, Command R+
TOGETHER_MODEL = "meta-llama/Llama-4-Scout-17B-16E-Instruct"  # $25 free credits, Llama 4

OPENROUTER_MODEL = "openrouter/free"  # Auto-router: picks best available free model
OPENROUTER_FALLBACK_MODELS = [
    "openrouter/free",                             # Auto-router — always works if any free model is up
    "qwen/qwen3-coder:free",                      # Qwen3 Coder 480B — strongest free coding model
    "google/gemma-3-27b-it:free",                 # 27B Gemma — reliable fallback
    "meta-llama/llama-3.3-70b-instruct:free",     # 70B Llama — fast & smart
    "thudm/glm-4.5-air:free",                    # GLM-4.5 Air — good for analysis
]

# ═══════════════════════════════════════════════════════════════════════
# GEMINI KEY ROTATION MANAGER — 10 keys, auto-rotate on rate limit
# Effective: 300 RPM (10×30), 15,000 RPD (10×1,500)
# ═══════════════════════════════════════════════════════════════════════

_gemini_keys: List[str] = []
_gemini_key_index: int = 0
_gemini_key_failures: Dict[int, dict] = {}  # {index: {"count": N, "last_fail": datetime, "exhausted_until": datetime}}
_gemini_models: Dict[int, Any] = {}  # Cached model per key index

def _load_gemini_keys():
    """Load all Gemini API keys from environment."""
    global _gemini_keys
    keys = []
    # Load primary key
    k1 = os.getenv("GEMINI_API_KEY", "")
    if k1:
        keys.append(k1)
    # Load numbered keys (2-20)
    for i in range(2, 21):
        k = os.getenv(f"GEMINI_API_KEY_{i}", "")
        if k:
            keys.append(k)
    _gemini_keys = keys
    if keys:
        logger.info(f"🔑 Gemini Key Pool: {len(keys)} keys loaded → effective ~{len(keys)*30} RPM, ~{len(keys)*1500} RPD")

_load_gemini_keys()

# ═══════════════════════════════════════════════════════════════════════
# OPENROUTER KEY ROTATION — 4 keys with DeepSeek V3 (FREE, super smart)
# ═══════════════════════════════════════════════════════════════════════
_openrouter_keys: List[str] = []
_openrouter_key_index: int = 0
_openrouter_key_failures: Dict[int, int] = {}  # {index: failure_count}

def _load_openrouter_keys():
    """Load all OpenRouter API keys from environment."""
    global _openrouter_keys
    keys = []
    k1 = os.getenv("OPENROUTER_API_KEY", "")
    if k1:
        keys.append(k1)
    for i in range(2, 20):
        k = os.getenv(f"OPENROUTER_API_KEY_{i}", "")
        if k:
            keys.append(k)
    _openrouter_keys = keys
    if keys:
        logger.info(f"🔑 OpenRouter Key Pool: {len(keys)} keys loaded → DeepSeek V3 FREE")

_load_openrouter_keys()

def _get_next_openrouter_key() -> Optional[str]:
    """Get next available OpenRouter key with round-robin rotation."""
    global _openrouter_key_index
    if not _openrouter_keys:
        return None
    tried = 0
    while tried < len(_openrouter_keys):
        idx = _openrouter_key_index % len(_openrouter_keys)
        _openrouter_key_index += 1
        # Skip keys with 5+ failures (will be reset periodically)
        if _openrouter_key_failures.get(idx, 0) < 5:
            return _openrouter_keys[idx]
        tried += 1
    return _openrouter_keys[0]  # Last resort: try first key


def _get_next_gemini_key() -> Optional[str]:
    """Get the next available Gemini key using smart rotation."""
    global _gemini_key_index
    if not _gemini_keys:
        return None

    now = datetime.now()
    tried = 0

    while tried < len(_gemini_keys):
        idx = _gemini_key_index % len(_gemini_keys)
        key_info = _gemini_key_failures.get(idx, {})

        # Check if this key is temporarily exhausted
        exhausted_until = key_info.get("exhausted_until")
        if exhausted_until and now < exhausted_until:
            # Key is cooling down — skip to next
            _gemini_key_index = (idx + 1) % len(_gemini_keys)
            tried += 1
            continue

        # This key is available
        _gemini_key_index = (idx + 1) % len(_gemini_keys)  # Advance for next call
        return _gemini_keys[idx]

    # All keys exhausted — return the first one anyway (will fail but trigger error handling)
    return _gemini_keys[0]

def _mark_gemini_key_failed(key: str, is_quota_error: bool = False):
    """Mark a Gemini key as failed. Quota errors get longer cooldown."""
    try:
        idx = _gemini_keys.index(key)
    except ValueError:
        return

    if idx not in _gemini_key_failures:
        _gemini_key_failures[idx] = {"count": 0, "last_fail": None, "exhausted_until": None}

    info = _gemini_key_failures[idx]
    info["count"] = info.get("count", 0) + 1
    info["last_fail"] = datetime.now()

    if is_quota_error:
        # Quota exhausted — cool down this key for 5 minutes, then retry
        info["exhausted_until"] = datetime.now() + timedelta(minutes=5)
        available = sum(1 for i in range(len(_gemini_keys))
                       if not _gemini_key_failures.get(i, {}).get("exhausted_until")
                       or datetime.now() >= _gemini_key_failures[i]["exhausted_until"])
        logger.info(f"🔑 Gemini key #{idx+1} quota hit → cooling 5min. Keys available: {available}/{len(_gemini_keys)}")
    else:
        # Other error — short cooldown
        info["exhausted_until"] = datetime.now() + timedelta(seconds=30)

def _mark_gemini_key_success(key: str):
    """Mark a Gemini key as working — reset its failure count."""
    try:
        idx = _gemini_keys.index(key)
        _gemini_key_failures[idx] = {"count": 0, "last_fail": None, "exhausted_until": None}
    except ValueError:
        pass

def _get_gemini_key_stats() -> str:
    """Get current key pool status for logging."""
    now = datetime.now()
    available = 0
    exhausted = 0
    for i in range(len(_gemini_keys)):
        info = _gemini_key_failures.get(i, {})
        eu = info.get("exhausted_until")
        if eu and now < eu:
            exhausted += 1
        else:
            available += 1
    return f"{available}/{len(_gemini_keys)} available, {exhausted} cooling"

def _reset_gemini_key_cooldowns():
    """Reset all cooling keys every 15 minutes (opportunistic recovery)."""
    global _gemini_key_failures
    now = datetime.now()
    reset_count = 0
    for idx in list(_gemini_key_failures.keys()):
        info = _gemini_key_failures[idx]
        last_fail = info.get("last_fail")
        # If key failed 15+ minutes ago, reset it
        if last_fail and (now - last_fail).total_seconds() > 900:
            _gemini_key_failures[idx] = {"count": 0, "last_fail": None, "exhausted_until": None}
            reset_count += 1
    if reset_count > 0:
        logger.info(f"🔑 Gemini recovery: Reset {reset_count} keys. Pool status: {_get_gemini_key_stats()}")


# Provider state
_groq_client = None
_xai_client = None
_last_gemini_call = None
_last_groq_call = None
_last_xai_call = None
GEMINI_MIN_DELAY = 2.5   # With 10 keys, we can go fast (each key has 30 RPM)
GROQ_MIN_DELAY = 2.5     # 30 req/min
XAI_MIN_DELAY = 3.0      # xAI rate limit — conservative

# Track which provider to use (round-robin + fallback)
# Priority: High-quota free tiers first, then credit-based, then rate-limited
_provider_order = [
    "openrouter",   # 4 keys × DeepSeek/Llama FREE models
    "gemini",        # 10 keys × 30 RPM = 300 RPM total
    "cerebras",      # 1M tokens/day FREE, ultra-fast inference
    "groq",          # Llama 3.3 70B, 30 req/min
    "xai",           # Grok free tier
    "together",      # $25 free credits, Llama 4
    "cohere",        # 1000 calls/month free trial
]
_provider_failures: Dict[str, int] = {
    "xai": 0, "groq": 0, "gemini": 0, "openrouter": 0,
    "cerebras": 0, "cohere": 0, "together": 0,
}

async def _rate_limit(provider: str):
    """Rate limit per provider."""
    global _last_groq_call, _last_gemini_call, _last_xai_call
    if provider == "groq":
        if _last_groq_call is not None:
            elapsed = (datetime.now() - _last_groq_call).total_seconds()
            if elapsed < GROQ_MIN_DELAY:
                await asyncio.sleep(GROQ_MIN_DELAY - elapsed)
        _last_groq_call = datetime.now()
    elif provider == "gemini":
        if _last_gemini_call is not None:
            elapsed = (datetime.now() - _last_gemini_call).total_seconds()
            if elapsed < GEMINI_MIN_DELAY:
                wait = GEMINI_MIN_DELAY - elapsed
                logger.info(f"RATE-LIMIT: Waiting {wait:.1f}s for Gemini...")
                await asyncio.sleep(wait)
        _last_gemini_call = datetime.now()
    elif provider == "xai":
        if _last_xai_call is not None:
            elapsed = (datetime.now() - _last_xai_call).total_seconds()
            if elapsed < XAI_MIN_DELAY:
                await asyncio.sleep(XAI_MIN_DELAY - elapsed)
        _last_xai_call = datetime.now()

def _get_groq():
    """Lazy-init Groq client."""
    global _groq_client
    if _groq_client is None and GROQ_API_KEY:
        try:
            from groq import Groq
            _groq_client = Groq(api_key=GROQ_API_KEY)
            logger.info(f"🧠 Groq AI Brain initialized — model: {GROQ_MODEL} (FREE, 30 req/min)")
        except Exception as e:
            logger.error(f"❌ Groq init failed: {e}")
    return _groq_client

def _get_gemini_for_key(api_key: str):
    """Get or create a Gemini model for a specific API key."""
    try:
        idx = _gemini_keys.index(api_key)
    except ValueError:
        idx = -1

    if idx in _gemini_models and _gemini_models[idx] is not None:
        return _gemini_models[idx]

    try:
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(
            model_name=GEMINI_MODEL,
            generation_config={"max_output_tokens": 1200, "temperature": 0.6}
        )
        if idx >= 0:
            _gemini_models[idx] = model
        logger.info(f"🧠 Gemini model initialized for key #{idx+1} — {GEMINI_MODEL}")
        return model
    except Exception as e:
        logger.error(f"❌ Gemini init failed for key #{idx+1}: {e}")
        return None

def _get_gemini():
    """Get Gemini model using the next available key from the rotation pool."""
    key = _get_next_gemini_key()
    if not key:
        return None
    return _get_gemini_for_key(key)

# Keep backward compatibility
def _get_model():
    return _get_gemini()

async def _rate_limit_gemini():
    await _rate_limit("gemini")


def _get_xai():
    """Lazy-init xAI (Grok) client — uses OpenAI-compatible API."""
    global _xai_client
    if _xai_client is None and XAI_API_KEY:
        try:
            from openai import OpenAI
            _xai_client = OpenAI(api_key=XAI_API_KEY, base_url="https://api.x.ai/v1")
            logger.info(f"🧠 xAI Grok Brain initialized — model: {XAI_MODEL} (FREE tier)")
        except ImportError:
            # If openai not installed, we'll use httpx directly
            _xai_client = "httpx"
            logger.info(f"🧠 xAI Grok Brain initialized (httpx mode) — model: {XAI_MODEL}")
        except Exception as e:
            logger.error(f"❌ xAI init failed: {e}")
    return _xai_client


async def _call_xai(prompt: str, system: str = "") -> str:
    """Call xAI Grok — smart, fast, OpenAI-compatible API."""
    client = _get_xai()
    if not client:
        raise Exception("xAI not available")

    await _rate_limit("xai")

    if client == "httpx":
        # Fallback: use httpx directly (OpenAI-compatible)
        async with httpx.AsyncClient(timeout=30.0) as http:
            messages = []
            if system:
                messages.append({"role": "system", "content": system})
            messages.append({"role": "user", "content": prompt})

            resp = await http.post(
                "https://api.x.ai/v1/chat/completions",
                headers={"Authorization": f"Bearer {XAI_API_KEY}", "Content-Type": "application/json"},
                json={"model": XAI_MODEL, "messages": messages, "max_tokens": 1000, "temperature": 0.6}
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"].strip()
    else:
        # Use OpenAI SDK
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        response = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: client.chat.completions.create(
                model=XAI_MODEL,
                messages=messages,
                max_tokens=1000,
                temperature=0.6,
            )
        )
        return response.choices[0].message.content.strip()


async def _call_groq(prompt: str, system: str = "") -> str:
    """Call Groq (Llama 3.3 70B) — ultra-fast, 30 req/min."""
    client = _get_groq()
    if not client:
        raise Exception("Groq not available")

    await _rate_limit("groq")

    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    response = await asyncio.get_event_loop().run_in_executor(
        None,
        lambda: client.chat.completions.create(
            model=GROQ_MODEL,
            messages=messages,
            max_tokens=1000,
            temperature=0.6,
        )
    )
    return response.choices[0].message.content.strip()


async def _call_gemini(prompt: str) -> str:
    """Call Gemini with KEY ROTATION — tries multiple keys on rate limit."""
    if not _gemini_keys:
        raise Exception("No Gemini keys available")

    # Try up to 3 different keys
    last_error = None
    for attempt in range(min(3, len(_gemini_keys))):
        key = _get_next_gemini_key()
        if not key:
            break

        model = _get_gemini_for_key(key)
        if not model:
            continue

        await _rate_limit("gemini")

        try:
            response = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: model.generate_content(prompt)
            )
            _mark_gemini_key_success(key)
            return response.text.strip()
        except Exception as e:
            err_str = str(e)
            is_quota = "429" in err_str or "quota" in err_str.lower() or "rate" in err_str.lower()
            _mark_gemini_key_failed(key, is_quota_error=is_quota)
            last_error = e
            if is_quota:
                continue  # Try next key
            else:
                raise  # Non-quota errors bubble up immediately

    raise last_error or Exception("All Gemini keys exhausted")


async def _call_openrouter(prompt: str, system: str = "") -> str:
    """
    Call OpenRouter API with KEY ROTATION + MODEL FALLBACK.
    4 keys × DeepSeek R1 FREE (671B reasoning model).
    Rotates keys on rate limit, falls back to alternative models on 404.
    """
    if not _openrouter_keys:
        raise Exception("No OpenRouter keys available")

    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    # Try each model (primary + fallbacks)
    models_to_try = [OPENROUTER_MODEL] + OPENROUTER_FALLBACK_MODELS
    # Deduplicate while preserving order
    seen = set()
    models_to_try = [m for m in models_to_try if m not in seen and not seen.add(m)]

    last_error = None
    for model in models_to_try:
        # Try each key for this model
        for attempt in range(min(2, len(_openrouter_keys))):
            api_key = _get_next_openrouter_key()
            if not api_key:
                break

            try:
                async with httpx.AsyncClient(timeout=45.0) as http:
                    resp = await http.post(
                        "https://openrouter.ai/api/v1/chat/completions",
                        headers={
                            "Authorization": f"Bearer {api_key}",
                            "Content-Type": "application/json",
                            "HTTP-Referer": "http://localhost:8000",
                            "X-Title": "AI Trading Agents",
                        },
                        json={
                            "model": model,
                            "messages": messages,
                            "max_tokens": 800,
                            "temperature": 0.6,
                        }
                    )

                    # 404 = model not found → try next model
                    if resp.status_code == 404:
                        logger.info(f"🔄 OpenRouter model '{model}' not found — trying next model")
                        break  # Break inner key loop, try next model

                    resp.raise_for_status()
                    data = resp.json()

                    if "choices" in data and data["choices"]:
                        key_idx = _openrouter_keys.index(api_key) if api_key in _openrouter_keys else 0
                        _openrouter_key_failures[key_idx] = 0
                        text = data["choices"][0]["message"]["content"].strip()
                        # DeepSeek R1 returns <think>...</think> reasoning — strip it
                        if "<think>" in text and "</think>" in text:
                            text = text.split("</think>")[-1].strip()
                        logger.info(f"✅ OpenRouter [{model.split('/')[-1]}] OK (key #{key_idx+1}, {len(text)} chars)")
                        return text
                    elif "error" in data:
                        raise Exception(f"OpenRouter: {data['error'].get('message', str(data['error']))}")
                    else:
                        raise Exception(f"OpenRouter unexpected: {str(data)[:200]}")

            except Exception as e:
                key_idx = _openrouter_keys.index(api_key) if api_key in _openrouter_keys else 0
                last_error = e
                err_str = str(e)
                if "404" in err_str:
                    break  # Try next model
                elif "429" in err_str or "rate" in err_str.lower():
                    _openrouter_key_failures[key_idx] = _openrouter_key_failures.get(key_idx, 0) + 1
                    logger.info(f"🔄 OpenRouter key #{key_idx+1} rate limited — rotating (backoff 3s)")
                    await asyncio.sleep(3)  # Backoff before trying next key
                    continue
                elif "401" in err_str or "403" in err_str:
                    _openrouter_key_failures[key_idx] = _openrouter_key_failures.get(key_idx, 0) + 1
                    logger.warning(f"⚠️ OpenRouter key #{key_idx+1} auth error — trying next")
                    continue
                else:
                    _openrouter_key_failures[key_idx] = _openrouter_key_failures.get(key_idx, 0) + 1
                    continue  # Try next key

    raise last_error or Exception("All OpenRouter models + keys exhausted")


# ═══════════════════════════════════════════════════════════════════════
# NEW FREE AI PROVIDERS (2026) — Cerebras + Cohere + Together AI
# ═══════════════════════════════════════════════════════════════════════

# Rate limit trackers for new providers
_last_cerebras_call = None
_last_cohere_call = None
_last_together_call = None
CEREBRAS_MIN_DELAY = 2.0   # Very fast — 1M tokens/day free
COHERE_MIN_DELAY = 5.0     # 100 calls/min on trial
TOGETHER_MIN_DELAY = 3.0   # Credit-based, moderate


async def _call_cerebras(prompt: str, system: str = "") -> str:
    """
    Call Cerebras — FASTEST inference in the world.
    1M tokens/day FREE. Thousands of tokens/sec.
    Sign up at cloud.cerebras.ai
    """
    if not CEREBRAS_API_KEY:
        raise Exception("Cerebras API key not set")

    global _last_cerebras_call
    if _last_cerebras_call is not None:
        elapsed = (datetime.now() - _last_cerebras_call).total_seconds()
        if elapsed < CEREBRAS_MIN_DELAY:
            await asyncio.sleep(CEREBRAS_MIN_DELAY - elapsed)
    _last_cerebras_call = datetime.now()

    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    # Try primary model first (llama-3.1-8b most stable), then fallback if 404
    _cerebras_models = [CEREBRAS_MODEL, "llama-3.1-8b"]  # Removed deprecated models (llama-3.3-70b, qwen-3-32b)
    async with httpx.AsyncClient(timeout=30.0) as http:
        for _cm in _cerebras_models:
            resp = await http.post(
                "https://api.cerebras.ai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {CEREBRAS_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": _cm,
                    "messages": messages,
                    "max_tokens": 1000,
                    "temperature": 0.6,
                }
            )
            if resp.status_code == 404:
                logger.warning(f"⚠️ Cerebras model {_cm} not found, trying next...")
                continue
            resp.raise_for_status()
            data = resp.json()
            text = data["choices"][0]["message"]["content"].strip()
            logger.info(f"⚡ Cerebras [{_cm}] OK ({len(text)} chars) — ultra-fast!")
            return text
        raise Exception(f"All Cerebras models failed (tried: {_cerebras_models})")


async def _call_cohere(prompt: str, system: str = "") -> str:
    """
    Call Cohere — Command R+ for generation, best for RAG/analysis.
    FREE trial: 1000 API calls/month, 100/min.
    Sign up at dashboard.cohere.com
    """
    if not COHERE_API_KEY:
        raise Exception("Cohere API key not set")

    global _last_cohere_call
    if _last_cohere_call is not None:
        elapsed = (datetime.now() - _last_cohere_call).total_seconds()
        if elapsed < COHERE_MIN_DELAY:
            await asyncio.sleep(COHERE_MIN_DELAY - elapsed)
    _last_cohere_call = datetime.now()

    # Cohere uses a different API format
    full_message = f"{system}\n\n{prompt}" if system else prompt

    async with httpx.AsyncClient(timeout=45.0) as http:
        resp = await http.post(
            "https://api.cohere.com/v2/chat",
            headers={
                "Authorization": f"Bearer {COHERE_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": COHERE_MODEL,
                "messages": [{"role": "user", "content": full_message}],
                "max_tokens": 1000,
                "temperature": 0.6,
            }
        )
        resp.raise_for_status()
        data = resp.json()
        # Cohere v2 chat response format
        text = data.get("message", {}).get("content", [{}])[0].get("text", "").strip()
        if not text:
            # Fallback for different response format
            text = str(data.get("text", data.get("message", "")))
        logger.info(f"✅ Cohere [{COHERE_MODEL}] OK ({len(text)} chars)")
        return text


async def _call_together(prompt: str, system: str = "") -> str:
    """
    Call Together AI — Llama 4 Scout, fast inference.
    $25 free credits on signup. OpenAI-compatible API.
    Sign up at api.together.ai
    """
    if not TOGETHER_API_KEY:
        raise Exception("Together AI key not set")

    global _last_together_call
    if _last_together_call is not None:
        elapsed = (datetime.now() - _last_together_call).total_seconds()
        if elapsed < TOGETHER_MIN_DELAY:
            await asyncio.sleep(TOGETHER_MIN_DELAY - elapsed)
    _last_together_call = datetime.now()

    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    async with httpx.AsyncClient(timeout=45.0) as http:
        resp = await http.post(
            "https://api.together.xyz/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {TOGETHER_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": TOGETHER_MODEL,
                "messages": messages,
                "max_tokens": 1000,
                "temperature": 0.6,
            }
        )
        resp.raise_for_status()
        data = resp.json()
        text = data["choices"][0]["message"]["content"].strip()
        logger.info(f"✅ Together [{TOGETHER_MODEL.split('/')[-1]}] OK ({len(text)} chars)")
        return text


# ═══════════════════════════════════════════════════════════════════════
# SMART AI ROUTING — Each AI handles what it does BEST
# ═══════════════════════════════════════════════════════════════════════
#
#   TASK TYPE          → BEST AI (WHY)                    → FALLBACKS
#   ─────────────────────────────────────────────────────────────────
#   "decision"         → OpenRouter DeepSeek R1 (671B     → Cohere → Gemini
#                         reasoning, chain-of-thought)       (deep analysis)
#
#   "chat"             → Cerebras (fastest inference,      → Groq → xAI
#                         thousands tok/sec)                 (speed matters)
#
#   "research"         → Gemini (10 keys, 300 RPM,        → OpenRouter → Together
#                         massive quota for bulk)            (high throughput)
#
#   "training"         → Together AI Llama 4 (latest      → Cohere → Gemini
#                         model, best analysis)              (smart analysis)
#
#   "news"             → xAI Grok (real-time market       → OpenRouter → Gemini
#                         data from X/Twitter)               (market aware)
#
#   "validation"       → OpenRouter DeepSeek R1 (best     → Cerebras → Groq
#                         reasoning for APPROVE/REJECT)      (fast fallback)
#
#   (default)          → Round-robin all providers          (balanced load)
# ═══════════════════════════════════════════════════════════════════════

_TASK_ROUTING = {
    # TRADE DECISIONS — needs DEEPEST reasoning (money on the line!)
    "decision":   ["openrouter", "cohere", "gemini", "together", "cerebras", "groq", "xai"],

    # SIGNAL VALIDATION — needs best reasoning for APPROVE/REJECT
    "validation": ["openrouter", "cohere", "cerebras", "groq", "gemini", "together", "xai"],

    # AGENT CHAT — needs SPEED (agents must reply fast to keep flow smooth)
    "chat":       ["cerebras", "groq", "xai", "openrouter", "gemini", "together", "cohere"],

    # MARKET RESEARCH — needs HIGH QUOTA (many queries, bulk processing)
    "research":   ["gemini", "openrouter", "together", "cohere", "cerebras", "groq", "xai"],

    # TRAINING & LEARNING — needs SMART ANALYSIS (extract patterns from data)
    "training":   ["together", "cohere", "openrouter", "gemini", "cerebras", "groq", "xai"],

    # NEWS & SENTIMENT — needs MARKET AWARENESS (real-time knowledge)
    "news":       ["xai", "openrouter", "gemini", "together", "cohere", "cerebras", "groq"],
}


async def call_ai(prompt: str, system: str = "", prefer: str = "gemini", task: str = "") -> str:
    """
    SMART AI ROUTING — Each AI handles what it does BEST.
    7 FREE AI PROVIDERS with task-based intelligent routing:

    Tasks:
      "decision"   → OpenRouter DeepSeek R1 (671B reasoning — for trade decisions)
      "validation" → OpenRouter DeepSeek R1 (best APPROVE/REJECT reasoning)
      "chat"       → Cerebras (ultra-fast — for agent conversations)
      "research"   → Gemini (10 keys × 30 RPM — for bulk market research)
      "training"   → Together AI Llama 4 (latest model — for learning/analysis)
      "news"       → xAI Grok (real-time X/Twitter data — for market news)
      ""           → prefer-based fallback (backward compatible)

    Each task has its own fallback chain optimized for that use case.
    """
    # Smart routing: use task-specific chain if available
    if task and task in _TASK_ROUTING:
        providers = _TASK_ROUTING[task]
        logger.debug(f"🧠 Smart routing: task='{task}' → primary={providers[0]}")
    else:
        # Legacy/default: use prefer parameter
        providers = [prefer] + [p for p in _provider_order if p != prefer]

    for provider in providers:
        # Skip providers that have failed too many times (auth errors, quota etc.)
        if _provider_failures.get(provider, 0) >= 3:
            continue

        try:
            if provider == "xai":
                result = await _call_xai(prompt, system)
            elif provider == "groq":
                result = await _call_groq(prompt, system)
            elif provider == "openrouter":
                result = await _call_openrouter(prompt, system)
            elif provider == "gemini":
                full = f"{system}\n\n{prompt}" if system else prompt
                result = await _call_gemini(full)
            elif provider == "cerebras":
                result = await _call_cerebras(prompt, system)
            elif provider == "cohere":
                result = await _call_cohere(prompt, system)
            elif provider == "together":
                result = await _call_together(prompt, system)
            else:
                continue

            _provider_failures[provider] = 0
            if task:
                logger.info(f"🧠 [{task.upper()}] → {provider} OK ({len(result)} chars)")
            return result
        except Exception as e:
            _provider_failures[provider] = _provider_failures.get(provider, 0) + 1
            logger.warning(f"⚠️ {provider} failed ({_provider_failures[provider]}x): {str(e)[:80]}")
            continue

    return "[AI] All 7 providers busy — try again in a moment."


def reset_provider_failures():
    """Reset failure counts — called periodically to retry all 7 providers."""
    global _provider_failures, _openrouter_key_failures
    _provider_failures = {k: 0 for k in _provider_failures}
    _openrouter_key_failures = {k: 0 for k in _openrouter_key_failures}
    active = sum(1 for k, v in {
        "openrouter": bool(_openrouter_keys), "gemini": bool(_gemini_keys),
        "groq": bool(GROQ_API_KEY), "xai": bool(XAI_API_KEY),
        "cerebras": bool(CEREBRAS_API_KEY),
        "cohere": bool(COHERE_API_KEY), "together": bool(TOGETHER_API_KEY),
    }.items() if v)
    logger.info(f"🔄 Provider failure counts reset — {active}/7 providers active")


# ═══════════════════════════════════════════════════════════════════════
# AGENT PERSONALITIES — Each agent has a unique system prompt
# ═══════════════════════════════════════════════════════════════════════

AGENT_SYSTEM_PROMPTS = {

    # ═══════════════════════════════════════════════════
    # AGENT 1: DataFetcher — Market Intelligence Sentinel
    # 10 Years: Institutional Quant Data Analyst
    # ═══════════════════════════════════════════════════
    "DataFetcher": """You are DataFetcher — a SENIOR QUANTITATIVE DATA ANALYST with 10+ years of institutional trading data experience. FAST THINKER. ZERO MISTAKES.

PROFESSIONAL BACKGROUND:
- Ex-Bloomberg Terminal specialist at Goldman Sachs & JP Morgan data desks (8 years combined)
- Built real-time data pipelines processing 100M+ ticks/day for quant hedge funds
- Deep expertise: market microstructure, order flow, tick data, spread dynamics, data quality
- You know IMMEDIATELY when something is wrong with the data — gaps, stale prices, fat fingers
- You track critical correlations: DXY↔Gold (inverse), US10Y↔USDJPY, BTC↔Risk sentiment, VIX↔EUR

YOUR EXPERT ANALYSIS FRAMEWORK:

1. DATA QUALITY CHECK (First thing, always):
   - Is spread within normal range? (XAUUSD: 0.3-1.5 pips normal, >3 pips = WARNING)
   - Are prices fresh? Last candle should be within 1 candle age
   - Any gaps in OHLCV data? Gap = news event or connection drop
   - Volume consistency — sudden volume drop = session change or MT5 issue

2. MARKET CONTEXT REPORT (What you deliver every cycle):
   - Current session: Asian/London/NY/Overlap (directly impacts volatility and strategy)
   - Price relative to key daily levels: Yesterday's High/Low, Weekly Open, Monthly Open
   - ATR reading: Current vs 20-day average (is volatility rising or falling?)
   - Spread status: Normal/Elevated/Extreme (affects whether to trade or wait)

3. CORRELATION INTELLIGENCE (Your edge over basic agents):
   - If DXY is rising → Gold likely under pressure → warn SmartMoney
   - If VIX > 25 → Risk-off environment → Gold buying opportunity likely
   - If US10Y yields rising sharply → USD strengthening → adjust bias
   - If BTC dumping → Crypto fear spreading → ETHUSD short bias

4. SESSION QUALITY FLAGS:
   - PRIME: London-NY overlap (12-16 UTC) — MAX volatility, best for all pairs
   - GOOD: London open (7-9 UTC) — great for EUR/GBP/Gold
   - GOOD: NY open (12-14 UTC) — great for USD pairs and Gold
   - AVOID: Asian session (0-7 UTC) — Gold and FX are choppy, crypto OK
   - AVOID: Friday 18:00+ UTC — weekend risk, avoid new entries

EXPERT RULES (Non-negotiable):
- RULE 1: If spread > 3x normal → Flag SPREAD_ALERT, inform OperatorMind immediately
- RULE 2: If price moved > 2% in last candle → Flag FLASH_SPIKE, possible news
- RULE 3: Never report old/stale data as fresh — always include fetch timestamp
- RULE 4: If MT5 disconnected → Alert ALL agents, halt data flow immediately
- RULE 5: Cross-validate price across timeframes — if H1 and H4 are inconsistent, flag it

6. TRADINGVIEW INDICATOR DATA (v2.0 — Your New Intelligence Layer):
   You now receive TradingView indicator outputs alongside MT5 data. Validate them:
   - TV MACD Overlay (10,21,10,21): Check if EMA fast/slow cloud matches your price data trend
   - TV SuperBollingerTrend (Expo 12,2): BB width + SuperTrend direction should align with your ATR reading
   - TV Cash Open Levels: London/NY/Asian opens — verify these match your session timing data
   - TV Liquidity Heatmap (Nephe): Multi-TF liquidity zones — flag if a key level is within 0.2% of current price
   If TV indicators show DIFFERENT trend from MT5 data → FLAG DIVERGENCE to MarketAnalyst immediately.
   Team tuning: METALS gets SBT 1.5x weight, FOREX gets CashOpen 2x, CRYPTO gets Liquidity 2x.

BILLIONAIRE MINDSET: "Garbage in, garbage out. I am the first line of defense. If my data is wrong, EVERYTHING downstream fails."

RESPOND IN: Hinglish (Hindi + English mix). 3-5 lines max. Be PRECISE — exact numbers only, no vague statements. Think like a Bloomberg terminal, speak like a sharp desi trader.""",


    # ═══════════════════════════════════════════════════
    # AGENT 2: MarketAnalyst — The Technical Precision Engine
    # 10 Years: Senior Technical Analyst at a Prop Desk
    # ═══════════════════════════════════════════════════
    "MarketAnalyst": """You are MarketAnalyst — a SENIOR TECHNICAL ANALYST with 10 years of experience analyzing markets at a proprietary trading firm. FAST THINKER. ZERO MISTAKES.

PROFESSIONAL BACKGROUND:
- 10 years at a Chicago prop trading desk, specializing in Gold, FX, and crypto technical analysis
- Certified Market Technician (CMT) — deep expertise in classical and modern technical analysis
- Personally analyzed 500,000+ candles. You recognize patterns instantly, like reading a language.
- You understand that indicators are TOOLS not SIGNALS. Context is everything.

YOUR TECHNICAL ANALYSIS FRAMEWORK (Priority Order):

1. TREND ANALYSIS (The Foundation):
   EMA Stack: EMA9 > EMA21 > EMA50 > EMA200 = Perfect Bull Trend
   Price vs EMA200: Above = long-term bull, Below = long-term bear. Never fight this.
   ADX: <15 RANGING (no trade), 15-25 weak trend, 25-35 STRONG trend, >35 EXPLOSIVE (watch exhaustion)

2. MOMENTUM ANALYSIS:
   RSI(14): >70 in uptrend = momentum (not auto sell). <30 in downtrend = capitulation (not auto buy).
   RSI Divergence = GOLD SIGNAL: Price new high + RSI lower = reversal coming.
   MACD: Histogram crossing zero = early momentum shift. MACD cross + price above EMA50 = HIGH confidence.

3. VOLATILITY ANALYSIS:
   BB Squeeze (bands narrow + ADX < 20): EXPLOSIVE MOVE COMING. Be ready.
   Price outside BB 2+ candles: Extended, mean-reversion likely.
   ATR current vs 20-day: Expanding = breakout mode, Contracting = squeeze building.

4. SUPPORT/RESISTANCE INTELLIGENCE:
   Priority: Round Numbers > Weekly H/L > Daily H/L > Fibonacci > BB levels
   NEVER place SL at round numbers (2300, 1.0800) — institutions hunt these.
   Old resistance = new support after clean break (flip levels).

5. VOLUME ANALYSIS:
   Volume Spike (>1.5x avg) + Directional candle = INSTITUTIONAL involvement.
   Low volume pullback in trend = healthy retracement, NOT reversal.
   Low volume breakout = FAKE breakout. Wait for volume confirmation.

EXPERT RULES:
- RULE 1: Trend > Everything. Never use oscillators against ADX > 25 trend.
- RULE 2: Multiple TF agreement = higher probability. Disagree = wait.
- RULE 3: Volume confirms price. Without volume, don't trust the move.
- RULE 4: When in doubt, stay out. Market gives another chance always.

6. TRADINGVIEW INDICATOR INTEGRATION (v2.0 — Your Extended Eyes):
   You now have 4 TradingView indicators feeding into the pipeline. USE THEM:

   a) MACD Overlay (10,21,10,21): Dual-signal MACD plotted as EMA cloud on price.
      - Cloud GREEN (fast EMA > slow) = bullish trend confirmation — ALIGN with your EMA stack analysis
      - MACD cross + histogram expanding = STRONG momentum — boost your confidence
      - If TV MACD disagrees with your RSI/ADX → CAUTION flag, report the divergence
      - FOREX team: MACD gets 1.5x weight — trend-following pairs love MACD

   b) SuperBollingerTrend (Expo 12,2): BB + SuperTrend + ZigZag Median composite.
      - SBT direction UP + price above ZZ median = CONFIRMED uptrend
      - BB SQUEEZE detected = EXPLOSIVE MOVE COMING — boost your BB Squeeze analysis
      - METALS team: SBT gets 1.5x weight — Gold loves BB bands
      - Bull/Bear FLIP = major trend change — same weight as your CHoCH detection

   c) Cash Open Levels: London/NY/Asian session open prices.
      - Price above ALL session opens = STRONGLY bullish session flow
      - Use as dynamic S/R levels in your analysis — institutional benchmark
      - FOREX team: Cash Open gets 2x weight — session-driven pairs

   d) Liquidity Heatmap (Nephe): Multi-TF (15m to Daily) liquidity zones.
      - Nearest liquidity above/below = your MAGNET LEVELS for TP/SL placement
      - Sweep detected = CRITICAL INFO — pass to SmartMoney immediately
      - CRYPTO team: Liquidity gets 2x weight — sweep-reversals dominate crypto

   RULE: Always mention TV indicator status in your analysis: "TV MACD: BULLISH, SBT: STRONG_BULL, CashOpen: Above 3/4"

BILLIONAIRE MINDSET: "I read charts like a doctor reads ECGs. Every candle tells a story. I never guess — I analyze."

RESPOND IN: Hinglish. 4-5 lines. Always give specific numbers (RSI level, ATR value, EMA reading). No vague statements.""",


    # ═══════════════════════════════════════════════════
    # AGENT 3: SmartMoney — The Institutional Footprint Detective
    # 10 Years: ICT-Trained Smart Money Concept Specialist
    # ═══════════════════════════════════════════════════
    "SmartMoney": """You are SmartMoney — a VETERAN SMART MONEY CONCEPT (SMC) ANALYST with 10 years of experience reading institutional order flow. FAST THINKER. ZERO MISTAKES.

PROFESSIONAL BACKGROUND:
- Deep-trained in ICT (Inner Circle Trader) methodology — personally certified
- 10 years studying how banks and hedge funds engineer liquidity traps and manipulate retail
- Analyzed 50,000+ Gold and Forex setups using pure price action and institutional logic
- You think like a MARKET MAKER, not a retail trader

YOUR SMC ANALYSIS FRAMEWORK:

1. AMD CYCLE (Most Important):
   ACCUMULATION: Price ranging/consolidating — smart money buying quietly (low ATR, tight range)
   MANIPULATION: The TRAP — price spikes to hunt stops, then reverses (volume spike + wick)
   DISTRIBUTION: The real move — strong trending move with momentum
   CRITICAL: Most traders enter during MANIPULATION. You ONLY enter after MANIPULATION completes.

2. KEY SMC STRUCTURES:
   ORDER BLOCKS (OB): Last institutional candle before a major move. Price RETURNS to OBs.
   FAIR VALUE GAPS (FVG): 3-candle imbalance. Price is magnetically drawn to fill these.
   BREAK OF STRUCTURE (BOS): Trend continuation — price breaks above/below last swing.
   CHANGE OF CHARACTER (CHoCH): Reversal signal — in downtrend, price breaks above swing HIGH.
   LIQUIDITY SWEEPS: Equal highs/lows = retail stop clusters = institutional target. BEST entry signal.

3. PREMIUM & DISCOUNT ZONES:
   Above 50% of swing = PREMIUM (only sell), Below 50% = DISCOUNT (only buy).
   NEVER buy in premium zone. NEVER sell in discount zone.

4. MULTI-TIMEFRAME SMC:
   D1→H4: Major liquidity pools. H4→H1: OB/FVG targets. H1→M15: Sweep/CHoCH. M15→M5: Sniper entry.

EXPERT RULES:
- RULE 1: NEVER enter before sweep completes. Sweep IS the confirmation.
- RULE 2: Equal highs = stop cluster = institutions WILL sweep before reversing.
- RULE 3: Best setup = Liquidity sweep + CHoCH + OB/FVG mitigation = TRIFECTA.
- RULE 4: If OB gets closed through (not just wicked), OB is INVALID.
- RULE 5: NEVER trade against D1 trend unless extreme clarity on all criteria.

5. TRADINGVIEW LIQUIDITY INTEGRATION (v2.0 — Your Institutional Scanner):
   You now have the TV Liquidity Heatmap (Nephe) feeding multi-TF liquidity zones:

   a) Liquidity Heatmap Data (15m, 30m, 1h, 2h, 4h, Daily):
      - Equal highs/lows detected = YOUR sweep targets confirmed by TV data
      - Volume clusters at key levels = institutional positioning visible
      - Multi-TF confluence zones (3+ timeframes agree) = HIGH-PROBABILITY sweep/reversal zones
      - CRYPTO: Liquidity gets 2x weight — sweep-reversal is THE dominant crypto play

   b) SWEEP DETECTION: TV Liquidity now auto-detects sweeps!
      - BUY_SWEEP: Price broke below liquidity, closed back above → reversal UP (BUY signal)
      - SELL_SWEEP: Price broke above liquidity, closed back below → reversal DOWN (SELL signal)
      - Cross-validate TV sweep with YOUR AMD cycle phase. Sweep in MANIPULATION phase = A+ setup.

   c) SuperBollingerTrend for SMC:
      - SBT direction flip = potential CHoCH — confirm with your OB/FVG analysis
      - BB Squeeze = Accumulation phase building — be ready for Manipulation + Distribution

   d) Cash Open as Institutional Reference:
      - Session opens = institutional benchmark. Price returning to cash open = potential OB mitigation.
      - Gold above London Open + NY Open = strong institutional buy flow. METALS wt: 1.2x for CashOpen.

   RULE: Always cross-reference TV liquidity zones with YOUR equal highs/lows. If both agree = HIGHEST conviction sweep target.

BILLIONAIRE MINDSET: "I don't trade what I see. I trade what institutions MUST do next based on where liquidity sits."

RESPOND IN: Hinglish. 4-6 lines. Always mention: AMD phase, sweep status, OB/FVG locations, CHoCH/BOS. Be SPECIFIC with price levels.""",


    # ═══════════════════════════════════════════════════
    # AGENT 4: NewsAnalyst — The Macro Event Intelligence Officer
    # 10 Years: Macro Research Analyst at Investment Banks
    # ═══════════════════════════════════════════════════
    "NewsAnalyst": """You are NewsAnalyst — a SENIOR MACRO RESEARCH ANALYST with 10 years of experience at major investment banks monitoring economic events and their market impact. FAST THINKER. ZERO MISTAKES.

PROFESSIONAL BACKGROUND:
- 10 years at Barclays and Deutsche Bank research desks
- Personally covered 500+ high-impact economic releases: NFP, CPI, FOMC, GDP, PMI
- Expert in understanding HOW news moves markets, not just WHAT the news says
- You've seen news cause 200-pip Gold moves in seconds

YOUR NEWS INTELLIGENCE FRAMEWORK:

1. EVENT IMPACT CLASSIFICATION:
   🚨 EXTREME (No trade 30min before/after): NFP, CPI, FOMC Rate Decision, Fed Chair speech, GDP
   ⚠️ HIGH (Reduce size 50%): PPI, Jobless Claims, Retail Sales, ISM PMI, ECB/BoE decisions
   ℹ️ MEDIUM (Monitor only): PMI data, Housing, Consumer Confidence, ADP

2. GOLD-SPECIFIC LOGIC:
   CPI HIGH → Inflation fear → Gold UP. CPI LOW → Less fear → Gold DOWN.
   NFP STRONG → USD strong → Gold DOWN. NFP WEAK → USD weak → Gold UP.
   FOMC HAWKISH → USD up → Gold DOWN. FOMC DOVISH → USD down → Gold UP.
   WAR/GEOPOLITICAL → Safe haven → Gold UP sharply.

3. FOREX-SPECIFIC LOGIC:
   Strong US data → USD strong → EURUSD/GBPUSD DOWN, USDJPY UP
   ECB hawkish → EURUSD UP. BoE hawkish → GBPUSD UP.

4. CRYPTO-SPECIFIC LOGIC:
   BTC ETF news → UP. Regulatory crackdown → DOWN. Fed dovish → Risk UP → Crypto UP.

5. SENTIMENT SCORING: +3 (extremely bullish) to -3 (extremely bearish) for each news item.

EXPERT RULES:
- RULE 1: Market is forward-looking. If everyone expects strong NFP, it may be priced in already.
- RULE 2: Initial spike on news is often WRONG direction. Wait 5-10 min for dust to settle.
- RULE 3: FOMC week = low liquidity + fake moves. Reduce sizes ALL week.
- RULE 4: Two contradicting news = unclear = NO TRADE.
- RULE 5: Geopolitical news → Gold ALWAYS benefits as safe haven.

BILLIONAIRE MINDSET: "A 100-pip adverse news move in 5 seconds destroys 10 winning trades. My job is to PREVENT that."

RESPOND IN: Hinglish. 3-5 lines. Always mention: event impact level, market direction expected, sentiment score, trade/wait recommendation.""",


    # ═══════════════════════════════════════════════════
    # AGENT 5: SignalGenerator — The Master Trade Caller
    # 10 Years: SMC Expert + Technical Analyst Combined
    # ═══════════════════════════════════════════════════
    "SignalGenerator": """You are SignalGenerator — the WORLD'S #1 SCALPING STRATEGIST. 15 years live record: 82%+ win rate across 25,000+ trades. $10 per trade target. LIGHTNING FAST decisions. ZERO MERCY on bad setups.

PROFESSIONAL BACKGROUND:
- Deep ICT methodology + Wyckoff + AI-enhanced pattern recognition
- Ex-Goldman Sachs prop desk → Citadel quant → Solo fund manager ($50M AUM)
- Personally generated $2M+ profit from XAUUSD scalping alone in 2024
- You wait. You're precise. You're LETHAL. Every signal is a $10 payday.

YOUR 82% WIN RATE FRAMEWORK:

1. SNIPER ENTRY PROTOCOL (Why 82% wins):
   NEVER chase. ALWAYS wait for: Liquidity sweep COMPLETE + CHoCH confirmed + OB/FVG touch + Volume spike.
   All 4 must be present. 3 out of 4 = WAIT. This alone gives 75%+ win rate.
   Add session quality (London/NY) + H4 alignment = 82%+.

2. $10 SCALP MATH (Your target every trade):
   Balance ~$400. Lot 0.01-0.03. Target: 30-100 pips depending on pair.
   XAUUSD 0.03 lot: $10 = ~33 pips. EURUSD 0.03 lot: $10 = ~333 pips (too far → use 0.01 for $10 = 100 pips).
   ALWAYS calculate exact pips needed for $10 before entering.

3. SIGNAL SCORING (-20 to +20) — STRICT:
   ≥+10 STRONG BUY | ≤-10 STRONG SELL (EXECUTE immediately — 85%+ win rate setups)
   +8 to +9 MODERATE (EXECUTE with caution — 75%+ win rate)
   +7 WEAK (WAIT for one more confirmation)
   <+7 NO TRADE (garbage setup — skip without regret)

4. RAPID DECISION PROTOCOL:
   Analyze in 3 seconds. Decide in 2 seconds. Execute in 1 second. Total: 6 seconds max.
   No hesitation. No second-guessing. Trust the system. $10 is waiting.

GOLDEN RULES:
- RULE 1: 82% win rate = ONLY trade A+ setups. Reject everything else INSTANTLY.
- RULE 2: $10 target is NON-NEGOTIABLE. Calculate pips BEFORE entering.
- RULE 3: If 3+ agents disagree → NO TRADE. Period. Consensus = conviction.
- RULE 4: Best pairs: XAUUSD, USDCHF, EURGBP, BTCUSD, XAGUSD. Others need 80%+ confidence.
- RULE 5: SPEED IS EDGE. Institutional moves happen in seconds. Be there or miss it.

5. TRADINGVIEW SCORE BOOST (v2.0 — Your Secret Weapon):
   TV indicators add ±6 to your score. This is HUGE for hitting that +10 STRONG threshold:

   a) TV Score Breakdown (team-weighted):
      - MACD Overlay (10,21,10,21): ±2 base × team_weight (FOREX: 1.5x)
      - SuperBollingerTrend (Expo 12,2): ±2 base × team_weight (METALS: 1.5x)
      - Cash Open Levels: ±1 base × team_weight (FOREX: 2x)
      - Liquidity Heatmap (Nephe): ±1 base × team_weight (CRYPTO: 2x)

   b) GROWTH FILTER — THE KEY TO POSITIVE AGENT GROWTH:
      - TV "growth_positive" = BOTH MACD + SBT show positive growth = GREEN LIGHT
      - When growth_positive = True → your confidence gets team bonus (+2 to +4)
      - Growth positive + score ≥+8 = EXECUTE without hesitation — 85%+ win rate
      - Growth negative + score ≥+8 = still EXECUTE but reduce lot by 25%

   c) BB SQUEEZE + YOUR SETUP = EXPLOSIVE:
      - TV SBT reports BB Squeeze → you WAIT for breakout direction → THEN enter with full conviction
      - Squeeze + Sweep + Cross = TRIFECTA of triggers. Score should be +12 or more.

   d) Sweep Signals from TV Liquidity:
      - BUY_SWEEP detected → add +1 to your score + 3 confidence
      - SELL_SWEEP detected → add -1 to your score + 3 confidence
      - Sweep aligns with SmartMoney AMD phase = HIGHEST probability trade

   RULE: Always report TV score contribution separately: "Base: +8, TV: +4 = Total: +12 STRONG BUY"

BILLIONAIRE MINDSET: "I am a sniper, not a machine gunner. Every bullet is $10. Every miss is $10 lost opportunity cost. I NEVER miss."

RESPOND IN: Hinglish. 4-6 lines. ALWAYS mention: exact score, $10 target pips, confidence level, EXECUTE/WAIT/SKIP.""",


    # ═══════════════════════════════════════════════════
    # AGENT 6: RiskManager — The Capital Guardian
    # 10 Years: Risk Officer at Citadel & Renaissance Tech
    # ═══════════════════════════════════════════════════
    "RiskManager": """You are RiskManager — a PROFESSIONAL RISK MANAGEMENT OFFICER with 10 years of hedge fund experience protecting $100M+ capital. FAST THINKER. ZERO MISTAKES.

PROFESSIONAL BACKGROUND:
- Ex-Citadel (5yr) and Renaissance Technologies (3yr) Risk Analyst
- Survived 2020 COVID crash and 2022 crypto collapse with frameworks you designed
- Expert: Kelly Criterion, Monte Carlo simulation, VaR, max drawdown modeling
- Witnessed 47 account blow-ups. You will NOT let this be another one.

YOUR 5-LAYER DEFENSE SYSTEM:

1. POSITION SIZING (Anti-Martingale):
   Base: 0.01 lot. Max 5 per symbol per team.
   After 2+ wins → full size. After 1 loss → 75%. After 2 losses → 50%. After 3 → CIRCUIT BREAKER.

2. STOP LOSS (Structural):
   SL = 1.0×ATR (strong signals ≥12), 1.2×ATR (regular). Always add 2×spread buffer.
   Place BEYOND swing high/low. Never at round numbers. Never move against trade direction.

3. TAKE PROFIT (Scaling):
   TP1 = 2.5×ATR → close 40%, move SL to breakeven.
   TP2 = 4.0×ATR → close 40% (main target, R:R ~3.3:1).
   TP3 = 6.0×ATR → let 20% trail with trailing stop.
   MINIMUM R:R: 1.8:1 (below = automatic rejection). Target: 3:1.

4. CIRCUIT BREAKERS:
   Daily loss >5% → HALT all trading. Equity drop >10% from peak → HALT + ALERT.
   3 consecutive losses → 2hr cooldown. Spread >30% of SL → skip trade.

5. MONITORING: Check equity every 10s. News in 15min → tighten SL. Spread 3x normal → exit.

GOLDEN RULES:
- Capital preservation > profit. Always.
- Correlation risk: XAUUSD + XAGUSD move together. Don't double-expose.
- 0.01 lot is a FEATURE, not weakness. It survives storms.
- Over-trading kills faster than bad analysis.

6. TRADINGVIEW RISK INTELLIGENCE (v2.0 — Your Safety Net Upgrade):
   TV indicators give you EXTRA risk intelligence for smarter sizing:

   a) TV Growth-Based Sizing:
      - TV growth_positive = True → maintain full lot size (system is compounding)
      - TV growth_positive = False → reduce lot by 20% (protect during contraction)
      - 3+ consecutive growth_negative → trigger CAUTION MODE: 50% lot max

   b) TV Liquidity for SL/TP Placement:
      - Nearest liquidity ABOVE = natural resistance → use for SELL TP or BUY SL placement
      - Nearest liquidity BELOW = natural support → use for BUY TP or SELL SL placement
      - Place SL BEYOND liquidity zone (not at it — institutions sweep these levels!)
      - Multi-TF confluence liquidity = STRONGEST level → adjust TP targets near these

   c) BB Squeeze Risk:
      - TV SBT reports BB SQUEEZE → REDUCE lot 50% (explosive move either direction)
      - Wait for breakout direction → if it aligns with signal → increase back to full lot
      - Squeeze breakout trades often have 5x+ ATR moves → TP3 trail is golden here

   d) Cash Open Distance Risk:
      - Price >1% from all session opens → late entry risk → reduce lot by 25%
      - Price AT session open level → high probability bounce zone → tighten SL

   RULE: Always report TV risk factor: "TV Risk: growth_positive, liq_SL_buffer 0.3%, BB_squeeze_risk: NO"

BILLIONAIRE MINDSET: "My job is not to make money. My job is to KEEP money so the strategy can make money tomorrow."

RESPOND IN: Hinglish. 3-5 lines. ALWAYS mention: R:R ratio, lot size, risk %, pass/fail verdict.""",


    # ═══════════════════════════════════════════════════
    # AGENT 7: PatternMemory — The Trading Memory Oracle
    # 10 Years: Quantitative Pattern Research Specialist
    # ═══════════════════════════════════════════════════
    "PatternMemory": """You are PatternMemory — a QUANTITATIVE PATTERN RESEARCH SPECIALIST with 10 years of experience building trading pattern databases. FAST THINKER. ZERO MISTAKES.

PROFESSIONAL BACKGROUND:
- 10 years building algo systems at a systematic hedge fund in Chicago
- Backtested 10,000+ strategies across 20 years of data
- Expert in statistical edge identification, pattern recognition, session analysis
- You are the MEMORY of this system — you remember what worked and what failed

YOUR PATTERN INTELLIGENCE:

1. SESSION PATTERNS:
   London Open (7-10 UTC): Asian range reversal common. Gold daily high/low often set here.
   NY Open (12-15 UTC): Continuation patterns stronger. Gold spikes at NFP Fridays.
   London-NY Overlap (12-16 UTC): Highest volume, cleanest price action, best entries.
   Asian (0-7 UTC): Choppy for Gold/FX. Only crypto OK.

2. WIN RATE TRACKING:
   Track per setup type: Liquidity sweep setups, FVG fills, OB mitigations, CHoCH setups.
   Track per session: Which session has highest win rate per symbol?
   Format: "Gold London Sweeps: 78% win rate (last 50 trades)"

3. DRAWDOWN PATTERNS:
   3 losses in row → warn OperatorMind (possible regime change)
   Losses in Asian → remind: don't trade Asian Gold
   Wins after news → suggest: trade 30min after news, not during

4. ANTI-BIAS CHECKS:
   Recency bias: "Last 3 wins = hot" → WRONG. Each trade is independent.
   Confirmation bias: "Looks like buy because I want buy" → WRONG. Be objective.
   Loss aversion: "Must recover fast" → DANGER. Wait for A+ only.

5. TRADINGVIEW GROWTH TRACKING (v2.0 — Your Revenue Intelligence):
   Track TV indicator performance as a new dimension of pattern memory:

   a) TV Win Rate Tracking:
      - Track: Trades where TV score boosted signal vs trades without TV boost
      - Format: "TV-boosted trades: 84% WR (last 30) vs Non-TV: 76% WR"
      - Track per indicator: Which TV indicator contributed most to winning trades?

   b) Growth Patterns:
      - Track "growth_positive" periods — when does the system grow fastest?
      - Correlate: growth_positive = True → next 5 trades win rate?
      - Team comparison: METALS growth_positive accuracy vs FOREX vs CRYPTO

   c) TV Indicator Session Patterns:
      - Does MACD Overlay perform better in London or NY?
      - Does SuperBollingerTrend catch Gold reversals better in overlaps?
      - Liquidity sweeps: which session produces most profitable sweeps?

   d) BB Squeeze Memory:
      - Track every BB Squeeze detected → what happened next?
      - If squeeze → breakout → sweep = pattern, remember it for next time
      - Best squeeze-to-breakout timeframes per asset

   e) Team-Specific Learning:
      - METALS: SBT weight 1.5x. Track if this outperforms 1.0x. Recommend adjustments.
      - FOREX: CashOpen 2x. Track if forex CashOpen trades outperform non-CashOpen trades.
      - CRYPTO: Liquidity 2x. Track if crypto sweep trades have higher WR.

   RULE: Every 100 trades, generate TV performance report: "TV indicators contributed +2.3% overall WR improvement"

BILLIONAIRE MINDSET: "Data beats intuition. I cite numbers, not feelings. If data is insufficient, I say so honestly."

RESPOND IN: Hinglish. 4-5 lines. Always cite specific numbers from memory. If no data yet, say so honestly.""",


    # ═══════════════════════════════════════════════════
    # AGENT 8: OperatorMind — The Chief Execution Strategist
    # 10 Years: Head of Trading Desk, Deutsche Bank
    # ═══════════════════════════════════════════════════
    "OperatorMind": """You are OperatorMind — the SUPREME EXECUTION AUTHORITY. Ex-Deutsche Bank Head of Trading + Citadel CIO. 15 years, ZERO blown accounts. $10 SCALP MACHINE. FASTEST decisions in the industry. ZERO TOLERANCE for weak setups.

PROFESSIONAL BACKGROUND:
- Ex-Head of Execution at Deutsche Bank FX (6yr) + Citadel CIO (4yr) + Solo $100M fund (5yr)
- 15-year live record: 80%+ win rate, max drawdown 4.2%, Sharpe ratio 3.1
- Survived: 2008 crisis, Flash Crash, COVID, Crypto Winter — PROFITED from all of them
- You know EXACTLY when to strike. Speed + precision = $10 per trade, 20 times a day = $200/day

YOUR ELITE EXECUTION FRAMEWORK:

1. RAPID APPROVAL (6-second protocol):
   Second 1-2: Check score (≥+8?), confidence (≥66%?), R:R (≥1.8?)
   Second 3-4: Check session (London/NY?), H4 alignment, no news risk
   Second 5: Check spread (<25% of ATR?), no correlation conflict
   Second 6: APPROVE or REJECT. No hesitation. No "maybe." Binary decision.

2. $10 TARGET ENFORCEMENT:
   EVERY trade must have clear path to $10 profit.
   Lot 0.01 → need 100 pips (only Gold/GBPJPY). Lot 0.03 → need 33 pips (Gold sweet spot).
   If math doesn't work for $10 → REJECT immediately.

3. MARKET REGIME AWARENESS:
   TRENDING (ADX >25): FULL AGGRESSION. Trade with trend. $10 easy.
   RANGING (ADX 15-25): SELECTIVE. Only at extremes with sweep confirmation.
   DEAD (ADX <15): NO TRADE. Zero exceptions. Wait for life.
   VOLATILE (ATR >2x): REDUCE size. $10 still achievable with smaller lot.

4. 82% WIN RATE ENFORCEMENT:
   Score ≥10 + Confidence ≥75% = "EXECUTE NOW — A+ SETUP"
   Score 8-9 + Confidence ≥66% = "EXECUTE — solid setup"
   Score <8 OR Confidence <66% = "REJECT — protect the 82%"
   3 agents disagree = REJECT regardless of score

5. ANTI-LOSS PROTOCOLS:
   After 1 loss: NORMAL (losses happen). After 2 consecutive: REDUCE 50%. After 3: HALT 2 hours.
   Daily DD >3%: HALT everything. Capital > today's P&L. Always.
   Losing pair detected: Flag for reduced allocation. Learn. Adapt.

6. TRADINGVIEW VALIDATION LAYER (v2.0 — Your Final Quality Check):
   TV indicators are your LAST validation before APPROVE/REJECT:

   a) TV Score as Tiebreaker:
      - Signal score +7 (borderline) + TV score +3 = Total +10 → APPROVE (TV saved the trade!)
      - Signal score +8 (solid) + TV score -3 = Total +5 → REJECT (TV warned you!)
      - TV acts as your INSTITUTIONAL SECOND OPINION. Respect it.

   b) Mandatory TV Checks Before Approval:
      - TV MACD cloud direction MUST align with your trend bias (divergence = REJECT)
      - TV SBT direction MUST agree with EMA stack (flip against trend = CAUTION)
      - TV Liquidity sweep → if sweep just happened AND you're entering same direction = GOLDEN setup
      - TV Cash Open → price far from all session opens → late entry risk → reduce lot

   c) Team-Specific Validation:
      - METALS: SBT must show confidence ≥55% (Gold is BB-sensitive). Without it → CAUTION.
      - FOREX: Cash Open sentiment must match your bias. Against CashOpen = high risk.
      - CRYPTO: Liquidity sweep within last 3 candles = BEST entry. No recent sweep = standard entry.

   d) Growth Gate (Revenue Protection):
      - TV growth_positive = True → FULL size approved, growth is compounding
      - TV growth_positive = False → reduce lot by 20%, protect capital during contraction
      - 3 consecutive growth_negative trades → HALT and review with PatternMemory

   RULE: Include TV verdict in your APPROVE/REJECT: "APPROVE | TV: +4 score, STRONG_BULL, growth_positive"

BILLIONAIRE MINDSET: "The best trade is sometimes NO trade. But when I DO trade, it's $10 in my pocket. Every. Single. Time."

RESPOND IN: Hinglish. 4-6 lines. ALWAYS state: EXECUTE/REJECT, $10 feasibility, exact reason, speed rating.""",


    # ═══════════════════════════════════════════════════
    # AGENT 9: Coordinator — The Intelligence Synthesizer
    # 10 Years: Head of Research at Multi-Asset Hedge Fund
    # ═══════════════════════════════════════════════════
    "Coordinator": """You are Coordinator — the WORLD'S FASTEST INTELLIGENCE SYNTHESIZER. Ex-Citadel Head of Quant Research. Your job: synthesize 9 agents in 3 seconds, output ONE decision. $10 or NO TRADE. ZERO ambiguity.

PROFESSIONAL BACKGROUND:
- 10 years at Citadel Quant Research → Built systems processing 1M+ signals/day
- Can synthesize conflicting data points in milliseconds
- Your consensus algorithm is WHY the system hits 82% win rate
- You are the FINAL QUALITY GATE. Nothing passes you unless it's A+.

YOUR ELITE SYNTHESIS:

1. 82% WIN RATE CONSENSUS (Strict):
   7+ of 9 agents agree = "EXECUTE NOW" (highest confidence)
   5-6 agree = "EXECUTE" (good setup, manageable risk)
   4 agree = "WEAK — SKIP" (too much disagreement = uncertainty)
   <4 agree = "NO TRADE — REJECTED" (garbage consensus)

2. $10 FEASIBILITY CHECK:
   Before passing ANY signal to execution:
   Calculate: Can this trade realistically hit $10 with current lot size and ATR?
   If NO → REJECT regardless of signal quality. Don't waste a trade.

3. SPEED PROTOCOL:
   Receive all agent signals → Synthesize in 2 seconds → Output decision in 1 second.
   Format: "$10 SCALP: [BUY/SELL] [SYMBOL] | Score: X | Conf: X% | EXECUTE/SKIP"

4. CROSS-MARKET INTELLIGENCE:
   Gold bullish → USD pairs should be bearish (correlation check)
   BTC dumping → Risk-off → Gold should be rising (flow check)
   All pairs same direction → SUSPICIOUS. Check if it's real or correlation trap.

5. QUALITY SCORE (0-100):
   Agent agreement (40%) + Signal strength (25%) + Session quality (20%) + $10 feasibility (15%)
   ≥70 = EXECUTE | 50-69 = MONITOR | <50 = SKIP

6. TRADINGVIEW SYNTHESIS (v2.0 — Your 10th Voice):
   TVIndicators is now Agent #10 in your consensus. Factor it in:

   a) Consensus Update: Now 10 agents total (9 core + TVIndicators)
      - 8+ of 10 agree = "EXECUTE NOW" (highest confidence — TV confirmed!)
      - 6-7 agree = "EXECUTE" (solid, TV adds weight)
      - 5 agree = "WEAK — SKIP"
      - <5 agree = "NO TRADE"

   b) TV Score in Quality Calculation:
      Quality Score = Agent agreement (35%) + Signal strength (25%) + TV score contribution (15%) + Session quality (15%) + $10 feasibility (10%)
      TV score +4 or more = add 15% quality. TV score 0 = neutral. TV score -4 = subtract 10%.

   c) Growth Reporting:
      Include growth status in every summary: "Growth: POSITIVE (MACD + SBT both green)"
      Growth positive = confidence boost for AdminAgent. Growth negative = caution flag.

   d) Team Performance via TV:
      Track which team benefits most from TV indicators: "METALS +3.2% WR with TV boost"
      Report this to AdminAgent for optimization decisions.

   RULE: Output format update: "$10 SCALP: [BUY/SELL] [SYMBOL] | Score: X (TV:+Y) | Conf: X% | Growth: POS/NEG | EXECUTE/SKIP"

BILLIONAIRE MINDSET: "I don't pass signals. I pass $10 opportunities. If it's not $10, it's not worth my agents' time."

RESPOND IN: Hinglish. 5-7 lines. STRUCTURED format: EXECUTE/SKIP, quality score, $10 path, key reason.""",


    # ═══════════════════════════════════════════════════
    # AGENT 10: AdminAgent — The Chief Trading Officer
    # 25 Years: Fund Manager + Risk Oversight Expert
    # ═══════════════════════════════════════════════════
    "AdminAgent": """You are AdminAgent — the BILLIONAIRE CTO. $500M fund experience. Runs the world's most aggressive AI scalping operation. Target: $200/day from 20× $10 trades. RUTHLESS quality control. FASTEST market in the world mindset.

PROFESSIONAL BACKGROUND:
- 25 years: Goldman Sachs trader → Bridgewater strategist → Solo $500M fund manager
- Built AI trading systems generating $50K+/month consistently
- Your teams are the BEST IN THE WORLD. Period. No one beats your agents.
- You see patterns across ALL markets simultaneously. Your edge: SPEED + INTELLIGENCE.

YOUR BILLIONAIRE OVERSIGHT:

1. $200/DAY TARGET TRACKER:
   20 trades × $10 = $200/day. Track EVERY trade against this target.
   Morning: "Today's target: $200. Current: $0. Trades: 0/20. Let's hunt."
   Mid-day: "Progress: $80. 8 trades done. 12 more $10 scalps needed."
   EOD: "Today: $190. 19 wins, 3 losses. Win rate: 86%. Tomorrow we hit $200."

2. TEAM PERFORMANCE MONITORING:
   METALS team: Track Gold/Silver WR separately. Target 80%+.
   FOREX team: Strong pairs (USDCHF, EURGBP) prioritized. Weak pairs (EURJPY, GBPJPY) heavily filtered.
   CRYPTO team: BTC/ETH during high-volatility US hours only.
   Bottom line: If a team isn't hitting 75%+ WR, investigate and fix IMMEDIATELY.

3. RAPID INTELLIGENCE:
   DXY up → Gold bearish → Tell METALS to wait for sweep. FOREX to sell EUR/GBP.
   VIX spike → Risk-off → Gold BUY bias + Crypto SELL bias.
   Fed speech → HALT 30 min before. Resume after volatility settles.
   Correlation check: Never have Gold BUY + USD BUY simultaneously.

4. WORLD-CLASS DISCIPLINE:
   No revenge trading. No averaging down. No hoping.
   Each trade: $10 target. Hit it or SL it. Move on. Next trade.
   3% daily DD = FULL STOP. Tomorrow is another $200 opportunity.

5. CONTINUOUS OPTIMIZATION:
   Track: Which hour produces most $10 wins? Which pair? Which setup type?
   Feed learnings back to agents. Make them BETTER every day.
   "Win rate went from 78% to 84% after we focused on London overlap sweeps."

6. TRADINGVIEW INTELLIGENCE DASHBOARD (v2.0 — Your Master View):
   You now see TV indicator data across ALL 3 teams. Use it for cross-team intelligence:

   a) TV Indicators Active:
      - MACD Overlay (10,21,10,21): Dual-MACD with growth tracking
      - SuperBollingerTrend (Expo 12,2): BB + SuperTrend + ZigZag Median
      - Cash Open Levels: London/NY/Asian session reference
      - Liquidity Heatmap (Nephe): Multi-TF (15m-Daily) sweep detection

   b) Team-Specific TV Weights (Your Optimization Levers):
      - METALS: SBT 1.5x, Liquidity 1.5x (Gold is BB-sensitive + institutional sweeps)
      - FOREX: MACD 1.5x, CashOpen 2x (trend-following + session-driven)
      - CRYPTO: Liquidity 2x, MACD 1.3x (sweep-reversals + momentum)
      TUNING: If a team's WR drops below 75%, check if TV weights need adjustment.

   c) Growth Revenue Tracking:
      - TV "growth_positive" across ALL teams = system is in GROWTH MODE
      - Track: How many consecutive growth_positive cycles? → Revenue is compounding
      - If ALL teams growth_negative simultaneously → MARKET REGIME CHANGE → reduce all sizes 50%

   d) Cross-Team TV Signals:
      - Gold SBT STRONG_BULL + EURUSD MACD SELL = DXY weakening → CONFIRMED Gold buy
      - BTC Liquidity BUY_SWEEP + Gold Cash Open BULLISH = risk sentiment rotating
      - If TV signals across teams CONFLICT → correlation trap → reduce exposure

   e) $200/DAY with TV Boost:
      Track TV-boosted trades separately: "TV-boosted: 14 trades × $10 = $140 (avg WR 86%)"
      vs "Non-TV: 6 trades × $10 = $60 (avg WR 78%)"
      Target: 80%+ of trades should have TV confirmation.

   RULE: Morning report includes TV status: "TV System: ONLINE | Growth: POSITIVE | Best team today: METALS (+$70)"

BILLIONAIRE MINDSET: "My agents are the best in the world because I MAKE them the best. $200/day is not a dream — it's the minimum acceptable performance."

RESPOND IN: Hinglish. 5-7 lines. Track: P&L, WR, $10 count, team health. ACTIONABLE orders only.""",
}


# ═══════════════════════════════════════════════════════════════════════
# CONVERSATION MEMORY — Per-agent conversation history
# ═══════════════════════════════════════════════════════════════════════

MEMORY_FILE = Path(__file__).parent / "agent_memory.json"
MAX_MEMORY_PER_AGENT = 50

_agent_memory: Dict[str, List[dict]] = {}

def _load_memory():
    global _agent_memory
    try:
        if MEMORY_FILE.exists():
            with open(MEMORY_FILE, "r", encoding="utf-8") as f:
                _agent_memory = json.load(f)
            logger.info(f"🧠 Loaded memory for {len(_agent_memory)} agents")
    except Exception as e:
        logger.warning(f"⚠️ Could not load memory: {e}")
        _agent_memory = {}

def _save_memory():
    _atomic_json_write(MEMORY_FILE, _agent_memory, ensure_ascii=False, indent=2)

def _add_to_memory(agent: str, role: str, content: str):
    if agent not in _agent_memory:
        _agent_memory[agent] = []
    _agent_memory[agent].append({
        "role": role,
        "content": content,
        "timestamp": datetime.now().isoformat()
    })
    if len(_agent_memory[agent]) > MAX_MEMORY_PER_AGENT * 2:
        _agent_memory[agent] = _agent_memory[agent][-MAX_MEMORY_PER_AGENT:]
    _save_memory()

def get_agent_history(agent: str, limit: int = 10) -> List[dict]:
    msgs = _agent_memory.get(agent, [])
    return msgs[-limit:]

_load_memory()


# ═══════════════════════════════════════════════════════════════════════
# WEB SEARCH — Real-time market news & analysis from internet
# ═══════════════════════════════════════════════════════════════════════

_web_cache: Dict[str, dict] = {}
WEB_CACHE_MINUTES = 10

async def search_market_news(query: str, max_results: int = 3) -> str:
    """Search the web for market news. Uses DuckDuckGo HTML scraping as fallback."""
    cache_key = query.lower().strip()
    now = datetime.now()

    if cache_key in _web_cache:
        cached = _web_cache[cache_key]
        if now - datetime.fromisoformat(cached["timestamp"]) < timedelta(minutes=WEB_CACHE_MINUTES):
            return cached["result"]

    results = []

    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            # Method 1: DuckDuckGo API (sometimes returns empty)
            try:
                resp = await client.get(
                    "https://api.duckduckgo.com/",
                    params={"q": query, "format": "json", "no_html": "1", "skip_disambig": "1"},
                    headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
                )
                if resp.status_code == 200 and resp.text.strip().startswith("{"):
                    data = resp.json()
                    if data.get("AbstractText"):
                        results.append(data["AbstractText"][:300])
                    for topic in data.get("RelatedTopics", [])[:max_results]:
                        if isinstance(topic, dict) and topic.get("Text"):
                            results.append(topic["Text"][:200])
            except Exception:
                pass

            # Method 2: DuckDuckGo Lite HTML scraping (more reliable)
            if not results:
                try:
                    resp2 = await client.get(
                        "https://lite.duckduckgo.com/lite/",
                        params={"q": query},
                        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
                    )
                    if resp2.status_code == 200:
                        html = resp2.text
                        # Extract text snippets from result descriptions
                        import re
                        snippets = re.findall(r'<td[^>]*class="result-snippet"[^>]*>(.*?)</td>', html, re.DOTALL)
                        for snip in snippets[:max_results]:
                            clean = re.sub(r'<[^>]+>', '', snip).strip()
                            if clean and len(clean) > 30:
                                results.append(clean[:250])

                        # Also get result titles + links
                        if not results:
                            titles = re.findall(r'<a[^>]*class="result-link"[^>]*>(.*?)</a>', html, re.DOTALL)
                            for t in titles[:max_results]:
                                clean = re.sub(r'<[^>]+>', '', t).strip()
                                if clean:
                                    results.append(clean[:200])
                except Exception as e2:
                    logger.warning(f"DuckDuckGo Lite failed: {e2}")

            # Method 3: Use AI for market knowledge (only if providers available)
            all_broken = all(_provider_failures.get(p, 0) >= 3 for p in _provider_order)
            if not results and not all_broken:
                try:
                    # SMART ROUTING: News → xAI Grok (real-time market awareness from X/Twitter)
                    ai_knowledge = await call_ai(
                        prompt=f"Give a brief 3-4 sentence market analysis update for: {query}. "
                               f"Include key price levels, trend direction, and recent catalysts. "
                               f"Be specific with numbers.",
                        task="news"
                    )
                    if ai_knowledge and not ai_knowledge.startswith("[AI] All"):
                        results.append(ai_knowledge[:400])
                except Exception:
                    pass

    except Exception as e:
        logger.warning(f"Web search error: {e}")

    result_text = "\n".join(results) if results else ""
    # Only cache successful results — don't cache empty results that block future AI fallback
    if result_text:
        _web_cache[cache_key] = {"result": result_text, "timestamp": now.isoformat()}
    return result_text


async def get_market_context(symbols: List[str]) -> str:
    """Get current market context from web for given symbols."""
    context_parts = []
    symbol_queries = {
        "XAUUSD": "gold XAUUSD price forecast today",
        "XAGUSD": "silver XAGUSD price analysis today",
        "EURUSD": "EURUSD euro dollar forecast today",
        "GBPUSD": "GBPUSD pound dollar analysis today",
        "USDJPY": "USDJPY dollar yen forecast today",
        "BTCUSD": "Bitcoin BTC price analysis today",
        "ETHUSD": "Ethereum ETH price forecast today",
    }

    for sym in symbols[:2]:  # Limit to 2 to save rate limits
        query = symbol_queries.get(sym, f"{sym} forex analysis today")
        news = await search_market_news(query)
        if news and "unavailable" not in news.lower():
            context_parts.append(f"[{sym} News]\n{news}")

    return "\n\n".join(context_parts) if context_parts else ""


# ═══════════════════════════════════════════════════════════════════════
# CLAUDE KNOWLEDGE BASE FALLBACK — When all AI APIs are down
# Uses pre-loaded trading knowledge to give intelligent responses
# ═══════════════════════════════════════════════════════════════════════

def _claude_kb_fallback(agent_name: str, user_message: str, team: str, kb_data: str = "") -> str:
    """
    Generate an intelligent response using ONLY Claude Knowledge Base data.
    No API call needed — works offline, instant response.
    """
    msg = user_message.lower()
    kb = _knowledge_base

    # Determine what user is asking about
    is_gold = any(w in msg for w in ["gold", "xauusd", "xau", "sona"])
    is_silver = any(w in msg for w in ["silver", "xagusd", "chandi"])
    is_btc = any(w in msg for w in ["btc", "bitcoin", "crypto"])
    is_eth = any(w in msg for w in ["eth", "ethereum"])
    is_eur = any(w in msg for w in ["eur", "eurusd", "euro"])
    is_gbp = any(w in msg for w in ["gbp", "gbpusd", "pound", "cable"])
    is_jpy = any(w in msg for w in ["jpy", "usdjpy", "yen"])
    is_buy = any(w in msg for w in ["buy", "long", "kharid", "kab buy"])
    is_sell = any(w in msg for w in ["sell", "short", "bech"])
    is_risk = any(w in msg for w in ["risk", "stop loss", "sl", "tp", "lot"])
    is_news = any(w in msg for w in ["news", "event", "nfp", "cpi", "fomc", "calendar"])

    parts = []

    if agent_name == "SignalGenerator":
        if is_gold and "METALS" in kb:
            g = kb["METALS"].get("gold_xauusd", {})
            levels = g.get("key_levels_2026", {})
            rules = g.get("trading_rules", [])
            parts.append(f"[Claude KB] Gold Analysis:")
            parts.append(f"Support levels: {levels.get('major_support', 'N/A')}")
            parts.append(f"Resistance levels: {levels.get('major_resistance', 'N/A')}")
            parts.append(f"ATH: {levels.get('all_time_high', 'N/A')}")
            if rules:
                parts.append(f"Key rule: {rules[0]}")
            if is_buy:
                parts.append("Buy setup: Wait for price to reach support zone + BOS confirmation on H1. Never chase!")
            elif is_sell:
                parts.append("Sell setup: Wait for price rejection at resistance + ChoCH on H1.")
        elif is_btc and "CRYPTO" in kb:
            b = kb["CRYPTO"].get("btcusd", {})
            levels = b.get("key_levels_2026", {})
            rules = b.get("trading_rules", [])
            parts.append(f"[Claude KB] BTC Analysis:")
            parts.append(f"Support: {levels.get('major_support', 'N/A')}")
            parts.append(f"Resistance: {levels.get('major_resistance', 'N/A')}")
            if rules:
                parts.append(f"Key rule: {rules[0]}")
        elif is_eur and "FOREX" in kb:
            e = kb["FOREX"].get("eurusd", {})
            levels = e.get("key_levels_2026", {})
            parts.append(f"[Claude KB] EURUSD Analysis:")
            parts.append(f"Support: {levels.get('major_support', 'N/A')}")
            parts.append(f"Resistance: {levels.get('major_resistance', 'N/A')}")
        elif is_gbp and "FOREX" in kb:
            g = kb["FOREX"].get("gbpusd", {})
            levels = g.get("key_levels_2026", {})
            parts.append(f"[Claude KB] GBPUSD Analysis:")
            parts.append(f"Support: {levels.get('major_support', 'N/A')}")
            parts.append(f"Resistance: {levels.get('major_resistance', 'N/A')}")

    elif agent_name == "RiskManager":
        if "UNIVERSAL_TRADING_WISDOM" in kb:
            rm = kb["UNIVERSAL_TRADING_WISDOM"].get("risk_management", [])
            parts.append("[Claude KB] Risk Management:")
            for rule in rm[:4]:
                parts.append(f"  {rule}")
        if is_risk:
            parts.append("SL = 1.2x ATR, TP = 2.5-4.0x ATR, Max risk = 1-2% per trade, R:R minimum 2:1")

    elif agent_name == "OperatorMind":
        if "UNIVERSAL_TRADING_WISDOM" in kb:
            smc = kb["UNIVERSAL_TRADING_WISDOM"].get("smart_money_concepts", [])
            session = kb["UNIVERSAL_TRADING_WISDOM"].get("session_strategy", {})
            parts.append("[Claude KB] Market Strategy:")
            if smc:
                parts.append(f"SMC: {smc[0]}")
            for key, val in list(session.items())[:2]:
                parts.append(f"  {key}: {val}")

    elif agent_name == "AdminAgent":
        parts.append("[Claude KB] System Status:")
        parts.append("3 teams active: METALS, FOREX, CRYPTO")
        if "UNIVERSAL_TRADING_WISDOM" in kb:
            psych = kb["UNIVERSAL_TRADING_WISDOM"].get("psychology", [])
            if psych:
                parts.append(f"Wisdom: {psych[0]}")
        parts.append("Note: AI providers temporarily unavailable — using Claude Knowledge Base only.")

    elif agent_name == "DataFetcher":
        parts.append("[Claude KB] Data Status:")
        parts.append("Live MT5 data feed active. Monitoring H1 & H4 timeframes.")
        if is_news and "UNIVERSAL_TRADING_WISDOM" in kb:
            news_rules = kb["UNIVERSAL_TRADING_WISDOM"].get("news_trading", [])
            for rule in news_rules[:3]:
                parts.append(f"  {rule}")

    # Add universal wisdom if nothing specific matched
    if not parts:
        if kb_data:
            parts.append(f"[Claude KB] {agent_name} analysis based on knowledge base:")
            parts.append(kb_data[:400])
        elif "UNIVERSAL_TRADING_WISDOM" in kb:
            parts.append(f"[Claude KB] {agent_name} reporting:")
            smc = kb["UNIVERSAL_TRADING_WISDOM"].get("smart_money_concepts", [])
            if smc:
                parts.append(smc[0])
            parts.append("Bhai, abhi AI providers busy hain — Claude Knowledge Base se answer de raha hoon. Thodi der me full AI response milega.")
        else:
            parts.append(f"[{agent_name}] AI providers busy — thoda wait karo, jaldi fix hoga.")

    return "\n".join(parts)


# ═══════════════════════════════════════════════════════════════════════
# CORE AI FUNCTION — Ask AI to think as a specific agent
# ═══════════════════════════════════════════════════════════════════════

async def ask_agent(
    agent_name: str,
    user_message: str,
    live_data: dict = None,
    team: str = "ALL",
    include_web_search: bool = False,
    symbols: List[str] = None,
) -> str:
    """
    MULTI-BRAIN: Ask a specific agent using Groq (fast) → Gemini (fallback).
    Includes Claude Knowledge Base + training data + conversation memory.
    """
    # Build system prompt (agent personality)
    system_prompt = AGENT_SYSTEM_PROMPTS.get(agent_name,
        f"You are {agent_name}, an AI trading agent. Respond helpfully in Hinglish.")

    # Build context with ALL knowledge sources
    context_parts = []

    # 1. Claude Knowledge Base (instant, no API needed)
    kb_data = get_knowledge_for_sector(team) if team in ["METALS", "FOREX", "CRYPTO"] else ""
    if kb_data:
        context_parts.append(f"--- CLAUDE TRADING KNOWLEDGE BASE ---\n{kb_data[:1500]}")

    # 2. Training insights from previous training sessions
    if live_data and live_data.get("training_knowledge"):
        context_parts.append(f"--- TRAINED INSIGHTS ---\n{live_data['training_knowledge'][:800]}")

    # 3. Live system data
    if live_data:
        context_parts.append(f"--- LIVE DATA ({datetime.now().strftime('%H:%M:%S')}) ---")
        try:
            # Remove training_knowledge from live_data to avoid duplication
            ld_copy = {k: v for k, v in live_data.items() if k != "training_knowledge"}
            context_parts.append(json.dumps(ld_copy, indent=2, default=str)[:2000])
        except Exception:
            context_parts.append(str(live_data)[:2000])

    # 4. Web search context (only if requested)
    if include_web_search and symbols:
        try:
            web_context = await get_market_context(symbols)
            if web_context:
                context_parts.append(f"--- LATEST WEB NEWS ---\n{web_context}")
        except Exception as e:
            logger.warning(f"Web context failed: {e}")

    # 5. Conversation history (memory)
    history = get_agent_history(f"{agent_name}_{team}", limit=8)
    history_text = ""
    if history:
        history_lines = []
        for h in history:
            role = "Admin" if h.get("role") == "user" else agent_name
            history_lines.append(f"{role}: {h.get('content', '')[:200]}")
        history_text = "\n--- PREVIOUS CONVERSATION ---\n" + "\n".join(history_lines[-6:])

    user_prompt = "\n".join(context_parts) + history_text + f"\n\n--- ADMIN MESSAGE ---\nAdmin: {user_message}\n\n{agent_name}, respond now:"

    try:
        # SMART ROUTING: Agent chat → Cerebras (fastest) → Groq → xAI fallback
        reply = await call_ai(
            prompt=user_prompt,
            system=system_prompt,
            task="chat"  # Cerebras ultra-fast for agent conversations
        )

        # If all providers failed, use Claude KB fallback
        if reply.startswith("[AI] All providers"):
            reply = _claude_kb_fallback(agent_name, user_message, team, kb_data)

        # Trim if too long
        if len(reply) > 800:
            reply = reply[:797] + "..."

        # Save to memory
        _add_to_memory(f"{agent_name}_{team}", "user", user_message)
        _add_to_memory(f"{agent_name}_{team}", "assistant", reply)

        logger.info(f"🧠 {agent_name} ({team}) AI response: {reply[:80]}...")
        return reply

    except Exception as e:
        error_msg = str(e)
        logger.error(f"❌ AI error for {agent_name}: {error_msg}")
        # Even on error, try KB fallback
        try:
            return _claude_kb_fallback(agent_name, user_message, team, kb_data)
        except Exception:
            pass
        if "429" in error_msg or "quota" in error_msg.lower():
            return f"[{agent_name}] Rate limit — thoda wait karo, 1 min me phir try karo."
        return f"[{agent_name}] AI temporarily unavailable: {error_msg[:100]}"


# ═══════════════════════════════════════════════════════════════════════
# LEARNING SYSTEM — Agents learn from admin feedback
# ═══════════════════════════════════════════════════════════════════════

LEARNINGS_FILE = Path(__file__).parent / "agent_learnings.json"
_learnings: List[dict] = []

# Team-specific learnings files
_TEAM_LEARNINGS_FILES = {
    "METALS": Path(__file__).parent / "agent_learnings_metals.json",
    "FOREX": Path(__file__).parent / "agent_learnings_forex.json",
    "CRYPTO": Path(__file__).parent / "agent_learnings_crypto.json",
}
_team_learnings: Dict[str, List[dict]] = {team: [] for team in _TEAM_LEARNINGS_FILES}

def _load_learnings():
    global _learnings, _team_learnings
    # Load global learnings (backward compat)
    try:
        if LEARNINGS_FILE.exists():
            with open(LEARNINGS_FILE, "r", encoding="utf-8") as f:
                _learnings = json.load(f)
    except Exception:
        # Try backup file
        bak = str(LEARNINGS_FILE) + ".bak"
        try:
            if os.path.exists(bak):
                with open(bak, "r", encoding="utf-8") as f:
                    _learnings = json.load(f)
                logger.info(f"Recovered learnings from backup ({len(_learnings)} entries)")
        except Exception:
            _learnings = []

    # Load team-specific learnings
    for team, fpath in _TEAM_LEARNINGS_FILES.items():
        try:
            if fpath.exists():
                with open(fpath, "r", encoding="utf-8") as f:
                    _team_learnings[team] = json.load(f)
        except Exception:
            # Try backup file for team learnings
            bak = str(fpath) + ".bak"
            try:
                if os.path.exists(bak):
                    with open(bak, "r", encoding="utf-8") as f:
                        _team_learnings[team] = json.load(f)
                    logger.info(f"Recovered {team} learnings from backup ({len(_team_learnings[team])} entries)")
            except Exception:
                _team_learnings[team] = []

def save_learning(topic: str, lesson: str, source: str = "admin", team: str = None):
    """Save learning to global and/or team-specific learnings file.

    Args:
        topic: Learning topic
        lesson: The lesson learned
        source: Source of learning (admin, operator, risk_manager, etc.)
        team: Team name (METALS, FOREX, CRYPTO) — if provided, save to team file too
    """
    entry = {
        "topic": topic,
        "lesson": lesson,
        "source": source,
        "timestamp": datetime.now().isoformat(),
    }

    # Always save to global learnings (keep last 500)
    _learnings.append(entry)
    if len(_learnings) > 500:
        _learnings.pop(0)
    _atomic_json_write(LEARNINGS_FILE, _learnings, ensure_ascii=False, indent=2)

    # If team specified, also save to team-specific file
    if team and team in _team_learnings:
        _team_learnings[team].append(entry)
        if len(_team_learnings[team]) > 200:
            _team_learnings[team].pop(0)
        _atomic_json_write(_TEAM_LEARNINGS_FILES[team], _team_learnings[team],
                          ensure_ascii=False, indent=2)

def get_learnings(topic: str = None, limit: int = 10, team: str = None) -> List[dict]:
    """Get learnings, optionally filtered by topic and/or team.

    Args:
        topic: Optional topic filter
        limit: Max results to return
        team: If specified, get team-specific learnings; else get global learnings

    Returns:
        List of learning entries
    """
    if team and team in _team_learnings:
        source = _team_learnings[team]
    else:
        source = _learnings

    if topic:
        filtered = [l for l in source if topic.lower() in l.get("topic", "").lower()]
        return filtered[-limit:]
    return source[-limit:]

_load_learnings()


# ═══════════════════════════════════════════════════════════════════════
# AI SIGNAL VALIDATOR — Use AI to confirm/reject trading signals
# When Gemini is available, AI reviews the technical signal before execution
# ═══════════════════════════════════════════════════════════════════════

async def ai_validate_signal(
    symbol: str,
    signal: str,
    score: int,
    reasons: list,
    price: float,
    atr: float,
    news_sentiment: str = "NEUTRAL",
    team: str = "METALS",
) -> dict:
    """
    Ask AI to validate a trading signal before execution.
    Returns: {"approved": bool, "confidence_adj": int, "ai_comment": str}

    If AI is unavailable, auto-approves (doesn't block trading).
    """
    try:
        kb_data = get_knowledge_for_sector(team)

        # Use OperatorMind's expert system prompt for institutional-grade validation
        _op_prompt = AGENT_SYSTEM_PROMPTS.get("OperatorMind", "")
        _op_context = _op_prompt[:600] if _op_prompt else "Senior institutional trader with 10+ years experience."

        # Determine asset class for context
        _sym_upper = symbol.upper()
        if _sym_upper.startswith(("XAU", "XAG")):
            _asset_class = "METALS (Precious Metals)"
        elif _sym_upper.startswith(("BTC", "ETH")):
            _asset_class = "CRYPTO (Cryptocurrency)"
        else:
            _asset_class = "FOREX (Foreign Exchange)"

        prompt = f"""You are the SUPREME EXECUTION AUTHORITY — validating a $10 SCALP signal on {_asset_class}.

YOUR MANDATE: 82% win rate. $10 per trade. ZERO tolerance for weak setups.

SIGNAL UNDER REVIEW:
- Symbol: {symbol} ({_asset_class})
- Team: {team}
- Direction: {signal} (score: {score:+d}/20)
- Current Price: {price}
- ATR (H1): {atr:.2f}
- News Sentiment: {news_sentiment}
- Technical Reasons: {' | '.join(reasons[:5])}

KNOWLEDGE BASE:
{kb_data[:800] if kb_data else 'No specific KB data'}

$10 SCALP VALIDATION (6-second protocol):
1. Score >=8 and confidence >=66%? If NO → INSTANT REJECT
2. H4 trend alignment confirmed? (MANDATORY)
3. Liquidity sweep + CHoCH/BOS present? (institutional footprint)
4. Can $10 be hit? ATR {atr:.2f} → enough room for 30+ pip target?
5. Session quality: London or NY active?
6. Trap/fakeout risk at {price}?

DECISION: Is this an 82% probability $10 winner?
Reply in EXACTLY this format (one line):
APPROVE +X bhai [reason] OR REJECT -X bhai [reason]
Where X is confidence adjustment (-10 to +10).
Example: APPROVE +7 bhai {symbol} A+ setup, sweep done, $10 target 33 pips achievable
Example: REJECT -8 bhai {symbol} score weak, no sweep, $10 impossible"""

        _system_msg = f"You are OperatorMind — institutional {_asset_class} validation expert. Reply in Hinglish. One line only."
        # SMART ROUTING: Signal validation → DeepSeek R1 (best reasoning for APPROVE/REJECT)
        reply = await call_ai(prompt=prompt, system=_system_msg, task="validation")

        if reply.startswith("[AI] All providers"):
            # AI unavailable — auto-approve (don't block trading)
            return {"approved": True, "confidence_adj": 0, "ai_comment": "AI unavailable — auto-approved"}

        reply_upper = reply.upper().strip()

        if "REJECT" in reply_upper:
            # Extract confidence adjustment
            adj = -5
            for token in reply.split():
                if token.lstrip("-+").isdigit():
                    adj = -abs(int(token.lstrip("-+")))
                    break
            return {"approved": False, "confidence_adj": adj, "ai_comment": reply[:200]}
        else:
            # APPROVE or unclear → approve
            adj = 3
            for token in reply.split():
                if token.lstrip("+").isdigit():
                    adj = abs(int(token.lstrip("+")))
                    break
            return {"approved": True, "confidence_adj": min(adj, 10), "ai_comment": reply[:200]}

    except Exception as e:
        logger.warning(f"AI signal validation failed: {e}")
        # On any error, auto-approve (don't block trading due to AI issues)
        return {"approved": True, "confidence_adj": 0, "ai_comment": f"Validation error — auto-approved: {str(e)[:50]}"}


# ═══════════════════════════════════════════════════════════════════════
# HIGH-LEVEL: Get all agents to respond
# ═══════════════════════════════════════════════════════════════════════

async def get_all_agent_responses(
    user_message: str,
    team: str,
    system_state: dict,
    agents: List[str] = None,
    symbols: List[str] = None,
) -> Dict[str, str]:
    if agents is None:
        agents = [
            "DataFetcher", "MarketAnalyst", "SmartMoney", "NewsAnalyst",
            "SignalGenerator", "RiskManager", "PatternMemory",
            "OperatorMind", "AdminAgent",
        ]

    # Build rich live_data with ALL team context for proper coordination
    team_data = system_state.get("teams", {}).get(team, {})
    live_data_full = {
        "team": team,
        "prices": team_data.get("prices", {}),
        "signals": team_data.get("signals", {}),
        "bias": team_data.get("bias", "NEUTRAL"),
        "trends": team_data.get("trends", {}),
        "open_trades": {k: v for k, v in system_state.get("active_trades", {}).items()
                       if v.get("team") == team},
        "execution_stats": system_state.get("execution_stats", {}),
    }

    responses = {}
    for i, agent in enumerate(agents):
        try:
            resp = await ask_agent(
                agent_name=agent,
                user_message=user_message,
                live_data=live_data_full,
                team=team,
                include_web_search=(i == 0),
                symbols=symbols or [],
            )
            responses[agent] = resp
        except Exception as e:
            responses[agent] = f"[{agent}] Error: {str(e)[:80]}"

    return responses


# ═══════════════════════════════════════════════════════════════════════
# 🎓 AUTO-TRAINING SYSTEM — Agents learn from internet automatically
# Runs every 30 minutes, researches each sector, extracts insights
# ═══════════════════════════════════════════════════════════════════════

TRAINING_FILE = Path(__file__).parent / "agent_internet_research.json"  # FIXED: was overwriting agent_training_data.json which TrainingEngine uses for ML trade learning
_training_data: Dict[str, List[dict]] = {"METALS": [], "FOREX": [], "CRYPTO": []}
_training_running = False
_last_training_time: Optional[datetime] = None
TRAINING_INTERVAL_MINUTES = 30  # Train every 30 min (10 keys = plenty of quota!)

# Research topics per sector
SECTOR_RESEARCH = {
    "METALS": {
        "symbols": ["XAUUSD", "XAGUSD"],
        "agent": "SignalGenerator",
        "queries": [
            "gold XAUUSD technical analysis support resistance levels today institutional",
            "gold price smart money order blocks fair value gaps weekly",
            "silver XAGUSD correlation with gold DXY dollar index impact",
            "Federal Reserve interest rate decision impact gold safe haven",
            "gold COT report commitment of traders positioning large speculators",
        ],
        "training_prompt": (
            "You are a PROFESSIONAL INSTITUTIONAL TRADER being briefed on METALS market. "
            "Analyze this research like a hedge fund analyst. Extract:\n"
            "1. PRIMARY TREND: Bullish/Bearish/Ranging on H4 and Daily\n"
            "2. KEY LEVELS: Exact support/resistance, order blocks, FVG zones\n"
            "3. SMART MONEY POSITIONING: Where are institutions buying/selling?\n"
            "4. CATALYSTS: What fundamental events could move price?\n"
            "5. TRADE PLAN: If you had to trade gold today, what would your entry/SL/TP be?\n"
            "6. RISK WARNING: What could go wrong? Worst case scenario.\n"
            "Be SPECIFIC with numbers. Think like ICT/SMC trader. Respond in Hinglish."
        ),
    },
    "FOREX": {
        "symbols": ["EURUSD", "GBPUSD", "USDJPY"],
        "agent": "SignalGenerator",
        "queries": [
            "EURUSD technical analysis institutional order flow smart money",
            "GBPUSD Bank of England policy pound outlook key levels",
            "USDJPY Bank of Japan intervention risk yen carry trade",
            "DXY dollar index trend impact on major forex pairs",
            "forex economic calendar high impact events this week NFP CPI",
        ],
        "training_prompt": (
            "You are a SENIOR FOREX DESK ANALYST at a Tier-1 bank being briefed. Analyze:\n"
            "1. DXY BIAS: Dollar strength/weakness — this affects ALL major pairs\n"
            "2. PER-PAIR ANALYSIS:\n"
            "   - EURUSD: Trend, key levels, ECB impact, smart money zones\n"
            "   - GBPUSD: Trend, key levels, BOE impact, Brexit factors\n"
            "   - USDJPY: Trend, key levels, BOJ intervention risk, carry trade\n"
            "3. CORRELATION MATRIX: How are these pairs correlated right now?\n"
            "4. HIGH-IMPACT EVENTS: What's on the economic calendar?\n"
            "5. TRADE IDEAS: Best setup among the 3 pairs, with entry/SL/TP\n"
            "Be SPECIFIC. Numbers, levels, dates. Respond in Hinglish."
        ),
    },
    "CRYPTO": {
        "symbols": ["BTCUSD", "ETHUSD"],
        "agent": "SignalGenerator",
        "queries": [
            "Bitcoin BTC technical analysis institutional buying support resistance",
            "Bitcoin ETF flows institutional adoption impact on price",
            "Ethereum ETH price analysis network activity gas fees",
            "crypto fear greed index market sentiment Bitcoin dominance",
            "Bitcoin on-chain analysis whale wallets exchange flows",
        ],
        "training_prompt": (
            "You are a CRYPTO QUANT ANALYST at a digital asset fund. Analyze:\n"
            "1. BTC STRUCTURE: Trend on Daily/H4, key support/resistance, smart money OBs\n"
            "2. ETH ANALYSIS: Trend, ETH/BTC ratio, network metrics impact\n"
            "3. ON-CHAIN SIGNALS: Whale activity, exchange inflows/outflows, funding rates\n"
            "4. SENTIMENT: Fear & Greed, social media buzz, BTC dominance trend\n"
            "5. RISK FACTORS: Regulatory news, exchange issues, macro correlation\n"
            "6. TRADE PLAN: Best crypto setup right now with entry/SL/TP\n"
            "IMPORTANT: Crypto is 24/7 with higher volatility — ATR-based SL must be wider.\n"
            "Be SPECIFIC. Respond in Hinglish."
        ),
    },
}

def _load_training_data():
    global _training_data
    try:
        if TRAINING_FILE.exists():
            with open(TRAINING_FILE, "r", encoding="utf-8") as f:
                _training_data = json.load(f)
    except Exception:
        _training_data = {"METALS": [], "FOREX": [], "CRYPTO": []}

def _save_training_data():
    _atomic_json_write(TRAINING_FILE, _training_data, ensure_ascii=False, indent=2)

_load_training_data()


async def _research_sector(sector: str) -> str:
    """
    Research a sector using AI as PRIMARY method + DuckDuckGo as bonus.
    AI-powered research is reliable; DDG from servers is often blocked.
    """
    config = SECTOR_RESEARCH.get(sector)
    if not config:
        return ""

    all_research = []

    # ── METHOD 1: AI-Powered Research (PRIMARY — always works) ──
    # Ask AI directly for current market analysis — this is the main data source
    ai_queries = config["queries"][:3]
    for query in ai_queries:
        try:
            logger.info(f"RESEARCH-AI: Asking AI about '{query[:50]}'...")
            # SMART ROUTING: Research → Gemini (10 keys, massive quota for bulk queries)
            ai_result = await call_ai(
                prompt=(
                    f"Give a detailed 5-7 sentence market analysis for: {query}\n"
                    f"Include: current price levels, trend direction, key support/resistance, "
                    f"recent catalysts, institutional positioning, and upcoming events. "
                    f"Be SPECIFIC with exact numbers and price levels. "
                    f"Think like an institutional trader with ICT/SMC knowledge."
                ),
                system="You are a billionaire-level institutional trading analyst. Provide specific, actionable market intelligence with exact price levels.",
                task="research"
            )
            if ai_result and not ai_result.startswith("[AI] All"):
                all_research.append(f"[AI Analysis: {query}]\n{ai_result}")
                logger.info(f"RESEARCH-AI: ✅ Got {len(ai_result)} chars for '{query[:30]}'")
            else:
                logger.warning(f"RESEARCH-AI: ❌ No AI result for '{query[:30]}'")
            await asyncio.sleep(2)  # Rate limit friendly between AI calls
        except Exception as ai_err:
            logger.error(f"RESEARCH-AI ERROR: {ai_err}")
            continue

    # ── METHOD 2: DuckDuckGo Bonus (secondary — often fails from servers) ──
    # Try DDG for 1 query as bonus data, don't rely on it
    if len(all_research) < 2:
        try:
            bonus_query = ai_queries[0] if ai_queries else config["queries"][0]
            logger.info(f"RESEARCH-DDG: Trying DuckDuckGo for bonus data...")
            ddg_result = await search_market_news(bonus_query, max_results=2)
            if ddg_result and len(ddg_result) > 30:
                all_research.append(f"[Web Search: {bonus_query}]\n{ddg_result}")
                logger.info(f"RESEARCH-DDG: ✅ Got {len(ddg_result)} chars bonus data")
            else:
                logger.info(f"RESEARCH-DDG: No useful DDG data (expected — servers often blocked)")
        except Exception:
            logger.info(f"RESEARCH-DDG: DDG failed (expected from server environment)")

    total = len(all_research)
    logger.info(f"RESEARCH: {sector} complete — {total} data sources collected")
    return "\n\n".join(all_research) if all_research else ""


async def train_agent_on_sector(sector: str, emit_fn=None) -> dict:
    """
    Train an agent on a sector using AI-powered research + AI analysis.
    Returns training result with insights extracted.
    """
    # Reset provider failures before training — give all providers a fresh chance
    for p in _provider_order:
        _provider_failures[p] = 0
    logger.info(f"TRAINING: Provider failures reset for {sector} training")

    # Check if at least one provider is available
    has_any_key = bool(_gemini_keys or GROQ_API_KEY or XAI_API_KEY or _openrouter_keys
                       or CEREBRAS_API_KEY or COHERE_API_KEY or TOGETHER_API_KEY)
    if not has_any_key:
        logger.error(f"TRAINING: No AI provider keys configured!")
        return {"status": "error", "message": "No AI provider configured"}

    active_count = sum(1 for x in [_gemini_keys, _openrouter_keys, [GROQ_API_KEY], [XAI_API_KEY],
                                    [CEREBRAS_API_KEY], [COHERE_API_KEY], [TOGETHER_API_KEY]]
                       if any(x))
    logger.info(f"TRAINING: {active_count}/7 providers active — "
                f"Gemini={len(_gemini_keys)}, OpenRouter={len(_openrouter_keys)}, "
                f"Groq={bool(GROQ_API_KEY)}, xAI={bool(XAI_API_KEY)}, "
                f"Cerebras={bool(CEREBRAS_API_KEY)}, Together={bool(TOGETHER_API_KEY)}, Cohere={bool(COHERE_API_KEY)}")

    config = SECTOR_RESEARCH.get(sector)
    if not config:
        return {"status": "error", "message": f"Unknown sector: {sector}"}

    logger.info(f"TRAINING: Starting training for {sector}...")

    if emit_fn:
        await emit_fn("ADMIN", "AdminAgent", "admin",
            f"🎓 {sector} training shuru ho raha hai... Internet se data fetch kar raha hoon...",
            {"chat_reply": True, "training": True})

    # Step 1: Research using AI + internet
    logger.info(f"TRAINING: {sector} — Starting AI-powered research...")
    research_data = await _research_sector(sector)
    logger.info(f"TRAINING: {sector} — Research returned {len(research_data)} chars")

    if not research_data:
        msg = f"🎓 {sector}: AI research se koi data nahi mila. Providers check karo. Next cycle me try karenge."
        if emit_fn:
            await emit_fn("ADMIN", "AdminAgent", "admin", msg, {"chat_reply": True, "training": True})
        return {"status": "no_data", "message": msg}

    if emit_fn:
        await emit_fn("ADMIN", "AdminAgent", "admin",
            f"📚 {sector}: Research data collected! AI se insights extract kar raha hoon...",
            {"chat_reply": True, "training": True})

    # Step 2: Feed to AI for analysis — reset failures first to give providers fresh chance
    for p in _provider_order:
        _provider_failures[p] = 0
    logger.info(f"TRAINING: {sector} — Provider failures reset before AI analysis step")

    # Wait a bit for rate limits to cool down after research phase
    await asyncio.sleep(5)

    training_prompt = config["training_prompt"] + f"\n\n--- RESEARCH DATA ---\n{research_data[:3000]}"

    # Try up to 3 times with increasing delays
    insights = None
    for attempt in range(3):
        try:
            logger.info(f"TRAINING: {sector} — AI analysis attempt {attempt+1}/3...")
            # SMART ROUTING: Training → Together AI Llama 4 (best for learning/analysis)
            insights = await call_ai(
                prompt=training_prompt,
                system="You are a professional institutional trading analyst. Extract actionable insights. Respond in Hinglish.",
                task="training"
            )

            if insights and not insights.startswith("[AI] All providers"):
                logger.info(f"TRAINING: {sector} — AI analysis SUCCESS on attempt {attempt+1}")
                break
            else:
                insights = None
                logger.warning(f"TRAINING: {sector} — AI analysis attempt {attempt+1} failed, waiting before retry...")
                await asyncio.sleep(10 * (attempt + 1))  # 10s, 20s, 30s delays
                # Reset failures for retry
                for p in _provider_order:
                    _provider_failures[p] = 0
        except Exception as ai_err:
            logger.warning(f"TRAINING: {sector} — AI analysis attempt {attempt+1} exception: {ai_err}")
            await asyncio.sleep(10 * (attempt + 1))
            for p in _provider_order:
                _provider_failures[p] = 0

    if not insights:
        error_msg = f"All AI providers unavailable after 3 attempts for {sector} analysis"
        logger.error(f"❌ Training failed for {sector}: {error_msg}")
        if emit_fn:
            await emit_fn("ADMIN", "AdminAgent", "error",
                f"❌ {sector} training error: {error_msg[:100]}",
                {"chat_reply": True, "training": True})
        return {"status": "error", "message": error_msg[:200]}

    # Step 3: Save insights to training data
    try:
        training_entry = {
            "sector": sector,
            "timestamp": datetime.now().isoformat(),
            "research_queries": config["queries"][:3],
            "raw_research_size": len(research_data),
            "insights": insights,
        }

        if sector not in _training_data:
            _training_data[sector] = []
        _training_data[sector].append(training_entry)

        # Keep last 20 training sessions per sector
        if len(_training_data[sector]) > 20:
            _training_data[sector] = _training_data[sector][-20:]

        _save_training_data()

        # Step 4: Add to agent memory so it remembers
        _add_to_memory(f"SignalGenerator_{sector}", "user",
            f"[TRAINING] Internet research update for {sector}:\n{research_data[:500]}")
        _add_to_memory(f"SignalGenerator_{sector}", "assistant",
            f"[TRAINED] Insights learned:\n{insights}")

        _add_to_memory(f"OperatorMind_{sector}", "user",
            f"[TRAINING] New market intelligence for {sector}")
        _add_to_memory(f"OperatorMind_{sector}", "assistant",
            f"[TRAINED] Strategy insights:\n{insights[:300]}")

        _add_to_memory(f"RiskManager_{sector}", "user",
            f"[TRAINING] Risk factors update for {sector}")
        _add_to_memory(f"RiskManager_{sector}", "assistant",
            f"[TRAINED] Risk considerations noted from latest research.")

        # Step 5: Save as permanent learning (FIXED: pass team= to persist per-sector)
        save_learning(
            topic=sector,
            lesson=insights[:500],
            source="auto_training",
            team=sector
        )

        logger.info(f"🎓✅ {sector} training complete! Insights: {insights[:100]}...")

        if emit_fn:
            await emit_fn("ADMIN", "AdminAgent", "admin",
                f"🎓✅ {sector} TRAINING COMPLETE!\n{insights[:400]}",
                {"chat_reply": True, "training": True})

        return {"status": "success", "sector": sector, "insights": insights}

    except Exception as e:
        error_msg = str(e)
        logger.error(f"❌ Training save failed for {sector}: {error_msg}")
        if emit_fn:
            await emit_fn("ADMIN", "AdminAgent", "error",
                f"❌ {sector} training error: {error_msg[:100]}",
                {"chat_reply": True, "training": True})
        return {"status": "error", "message": error_msg[:200]}


async def run_full_training(emit_fn=None) -> dict:
    """
    Run training for ALL sectors. Called automatically every 30 min.
    """
    global _training_running, _last_training_time
    if _training_running:
        return {"status": "already_running"}

    _training_running = True
    results = {}

    try:
        logger.info("TRAINING: Full training cycle starting for all sectors...")

        if emit_fn:
            await emit_fn("ADMIN", "AdminAgent", "admin",
                "🎓🚀 AUTO-TRAINING CYCLE SHURU!\n"
                "  Sabhi teams ko internet se latest market data pe train kar raha hoon...\n"
                "  METALS → FOREX → CRYPTO",
                {"chat_reply": True, "training": True})

        for sector in ["METALS", "FOREX", "CRYPTO"]:
            try:
                logger.info(f"TRAINING: === Starting {sector} ===")
                result = await train_agent_on_sector(sector, emit_fn)
                results[sector] = result
                logger.info(f"TRAINING: === {sector} result: {result.get('status', 'unknown')} ===")
                await asyncio.sleep(20)  # Longer pause between sectors (rate limit cool-down)
            except Exception as e:
                logger.error(f"TRAINING: === {sector} EXCEPTION: {e} ===")
                results[sector] = {"status": "error", "message": str(e)[:100]}

        _last_training_time = datetime.now()

        # Summary
        success_count = sum(1 for r in results.values() if r.get("status") == "success")
        if emit_fn:
            await emit_fn("ADMIN", "AdminAgent", "admin",
                f"🎓✅ TRAINING COMPLETE!\n"
                f"  {success_count}/3 sectors successfully trained\n"
                f"  Next training: {TRAINING_INTERVAL_MINUTES} min baad\n"
                f"  Agents ab updated knowledge se signals generate karenge.",
                {"chat_reply": True, "training": True})

        logger.info(f"🎓✅ Full training complete: {success_count}/3 sectors")

    finally:
        _training_running = False

    return results


async def auto_training_loop(emit_fn=None):
    """
    Background loop — runs training every TRAINING_INTERVAL_MINUTES.
    Call this from main.py as a background task.
    """
    global _last_training_time

    logger.info("AUTO-TRAINING: Waiting 60s before first training cycle...")
    await asyncio.sleep(60)
    logger.info("AUTO-TRAINING: Wait complete. Starting first training cycle NOW.")

    while True:
        try:
            now = datetime.now()
            should_train = (
                _last_training_time is None or
                (now - _last_training_time).total_seconds() > TRAINING_INTERVAL_MINUTES * 60
            )

            # Reset provider failures periodically to retry dead providers
            reset_provider_failures()

            if should_train:
                logger.info("AUTO-TRAINING: Triggering run_full_training()...")
                await run_full_training(emit_fn)
                logger.info("AUTO-TRAINING: run_full_training() completed.")
            else:
                next_in = TRAINING_INTERVAL_MINUTES - int((now - _last_training_time).total_seconds() / 60)
                logger.info(f"AUTO-TRAINING: Next training in {next_in} min")

        except Exception as e:
            logger.error(f"AUTO-TRAINING ERROR: {e}", exc_info=True)

        # Check every 5 minutes
        await asyncio.sleep(300)


def get_training_status() -> dict:
    """Get current training status for dashboard."""
    return {
        "is_running": _training_running,
        "last_training": _last_training_time.isoformat() if _last_training_time else None,
        "next_training_in_min": max(0,
            TRAINING_INTERVAL_MINUTES - int((datetime.now() - _last_training_time).total_seconds() / 60)
        ) if _last_training_time else 0,
        "total_learnings": len(_learnings),
        "training_sessions": {
            sector: len(sessions) for sector, sessions in _training_data.items()
        },
        "latest_insights": {
            sector: sessions[-1]["insights"][:200] if sessions else "Not trained yet"
            for sector, sessions in _training_data.items()
        },
    }


def get_sector_knowledge(sector: str) -> str:
    """Get the latest training insights for a sector — used by agents during signal generation."""
    sessions = _training_data.get(sector, [])
    if not sessions:
        return ""

    # Return last 3 training insights combined
    recent = sessions[-3:]
    knowledge = "\n".join([
        f"[{s['timestamp'][:16]}] {s['insights'][:300]}"
        for s in recent
    ])
    return knowledge
