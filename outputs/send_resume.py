"""Send /resume Telegram command to brain bot to clear lockout."""
import os
import urllib.request as u
import urllib.parse as up
import time
import json
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(r"C:\Users\Ratanshila\Documents\autmated trading\config\.env")

BOT = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
CHAT = os.getenv("TELEGRAM_CHAT_ID", "").strip()

def send(msg):
    url = f"https://api.telegram.org/bot{BOT}/sendMessage"
    body = up.urlencode({"chat_id": CHAT, "text": msg}).encode()
    r = u.urlopen(u.Request(url, data=body), timeout=8)
    return json.loads(r.read().decode())

print("=== Sending /resume to brain ===")
res = send("/resume")
print(f"  Telegram response ok: {res.get('ok')}")
print(f"  message_id: {res.get('result',{}).get('message_id')}")

print("\n  Waiting 8 sec for brain to process command + save state...")
time.sleep(8)

state_path = Path(r"C:\Users\Ratanshila\Documents\autmated trading\logs\brain_state.json")
state = json.loads(state_path.read_text())
print(f"\n=== STATE NOW ===")
print(f"  drawdown_lockout_until: {state.get('drawdown_lockout_until')}")
print(f"  trading_paused:         {state.get('trading_paused')}")
print(f"  cooldown_until_ts:      {state.get('cooldown_until_ts')}")
