"""
Launcher for Multi-Indicator Engine.
Loads .env then starts the engine with proper encoding.
"""
import os, sys, asyncio

# Fix Windows console encoding
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

# Load .env
ENV_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
if os.path.exists(ENV_FILE):
    with open(ENV_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())
    print("[OK] .env loaded")

# Verify Telegram
tok = os.getenv("TELEGRAM_BOT_TOKEN", "")
cid = os.getenv("TELEGRAM_CHAT_ID", "")
print(f"[OK] Telegram: {'ENABLED' if tok and cid else 'DISABLED'}")
print(f"[OK] Chat ID : {cid or 'NOT SET'}")

# Run engine
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from multi_indicator_engine import run_multi_indicator_gold

print("[OK] Starting Multi-Indicator Engine on XAUUSD M5...")
print("[OK] Waiting for MetaTrader5 data...")
print()

asyncio.run(run_multi_indicator_gold(
    dry_run=False,  # FIXED: was True — live trading enabled
    base_lot=0.01,
    telegram_token=tok,
    telegram_chat=cid,
))
