"""Test the SAME Telegram token via urllib vs requests library to
see if they differ. Earlier (2026-05-09) urllib got 200; now (2026-05-12)
requests gets 404 from listener. Compare directly."""
from __future__ import annotations
import json
import os
import sys
import urllib.request
import urllib.error
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENV = ROOT / "config" / ".env"

token = ""
chat_id = ""
for line in ENV.read_text(encoding="utf-8").splitlines():
    if line.startswith("TELEGRAM_BOT_TOKEN"):
        token = line.split("=", 1)[1].strip().strip('"').strip("'")
    elif line.startswith("TELEGRAM_CHAT_ID"):
        chat_id = line.split("=", 1)[1].strip().strip('"').strip("'")

print(f"Token  : {token[:14]}...{token[-6:]}  (len={len(token)})")
print(f"ChatID : {chat_id}")
print()

# Test 1 — urllib
print("[1] urllib.request getMe:")
url = f"https://api.telegram.org/bot{token}/getMe"
try:
    with urllib.request.urlopen(url, timeout=10) as r:
        body = r.read().decode("utf-8")
        print(f"    HTTP {r.status}: {body[:200]}")
except urllib.error.HTTPError as e:
    print(f"    HTTP {e.code}: {e.read().decode()[:200]}")
except Exception as e:
    print(f"    EXC: {e}")

# Test 2 — requests
print()
print("[2] requests getMe:")
try:
    import requests  # type: ignore
    r = requests.get(url, timeout=10)
    print(f"    HTTP {r.status_code}: {r.text[:200]}")
except ImportError:
    print("    [SKIP] requests not installed")
except Exception as e:
    print(f"    EXC: {e}")

# Test 3 — urllib sendMessage
print()
print("[3] urllib sendMessage to chat_id:")
url = f"https://api.telegram.org/bot{token}/sendMessage"
payload = json.dumps({"chat_id": chat_id, "text": "dual-test from urllib"}).encode("utf-8")
try:
    req = urllib.request.Request(url, data=payload, method="POST",
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as r:
        body = r.read().decode("utf-8")
        print(f"    HTTP {r.status}: {body[:200]}")
except urllib.error.HTTPError as e:
    print(f"    HTTP {e.code}: {e.read().decode()[:200]}")
except Exception as e:
    print(f"    EXC: {e}")

print()
print("=== Diagnosis ===")
print("If [1] gives 200 but [2] gives 404, requests has a config/cert issue.")
print("If both give 404, token is revoked — fix at @BotFather.")
print("If [3] succeeds, you should see 'dual-test from urllib' in Telegram.")
