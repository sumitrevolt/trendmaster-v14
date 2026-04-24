"""
Auto-setup Telegram for Multi-Indicator Engine.
1. Fetch chat ID from bot updates
2. Write to .env file
3. Send a test alert
"""
import urllib.request, json, os, sys, time

BOT_TOKEN = "8363810880:AAHSBuLmtI_V2Xef2DUN8wMf6ua5_hpCagc"
ENV_FILE  = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
OUT_FILE  = os.path.join(os.path.dirname(os.path.abspath(__file__)), "chat_id_result.txt")

def api(method, params=None):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/{method}"
    if params:
        url += "?" + "&".join(f"{k}={v}" for k,v in params.items())
    with urllib.request.urlopen(url, timeout=15) as r:
        return json.loads(r.read())

def get_chat_id():
    data = api("getUpdates")
    results = data.get("result", [])
    for upd in results:
        for key in ["message","channel_post","edited_message","my_chat_member"]:
            obj = upd.get(key)
            if not obj:
                continue
            # my_chat_member has nested chat
            chat = obj.get("chat") or (obj.get("new_chat_member",{}) and obj)
            if isinstance(chat, dict) and "id" in chat:
                return str(chat["id"]), chat.get("type","?"), chat.get("title") or chat.get("first_name","?")
    return None, None, None

def update_env(chat_id):
    """Update TELEGRAM_CHAT_ID in .env"""
    with open(ENV_FILE, "r", encoding="utf-8") as f:
        content = f.read()
    if "TELEGRAM_CHAT_ID=" in content:
        lines = content.splitlines()
        new_lines = []
        for line in lines:
            if line.startswith("TELEGRAM_CHAT_ID="):
                new_lines.append(f"TELEGRAM_CHAT_ID={chat_id}")
            else:
                new_lines.append(line)
        content = "\n".join(new_lines)
    else:
        content += f"\nTELEGRAM_CHAT_ID={chat_id}\n"
    with open(ENV_FILE, "w", encoding="utf-8") as f:
        f.write(content)
    return True

def send_test_alert(chat_id):
    msg = (
        "✅ <b>Multi-Indicator Engine - SETUP COMPLETE!</b>\n\n"
        "🟡 <b>XAUUSD M5 Signal Engine Ready</b>\n\n"
        "📊 <b>Indicators Active:</b>\n"
        "  1️⃣ MACD Overlay (12/26/9 + SMA89)\n"
        "  2️⃣ SuperBollingerTrend (BB12 + ATR)\n"
        "  3️⃣ ORB LuxAlgo (09:30-09:45 session)\n"
        "  4️⃣ Phoenix wSMD (Stoch+Divergence)\n\n"
        "📋 <b>Trading Rules:</b>\n"
        "  🔸 1 signal  → NO TRADE\n"
        "  🔸 2 signals → NORMAL lot (0.01)\n"
        "  🔸 3-4 signals → DOUBLE lot (0.02)\n\n"
        "🔔 Telegram alerts: <b>ENABLED</b> ✅\n"
        "🔊 Sound alerts: <b>ENABLED</b> ✅\n"
        "📈 MT5 chart indicator: <b>INSTALLED</b> ✅\n\n"
        "<i>Engine is ready. Start it via desktop shortcut!</i>"
    )
    params = {
        "chat_id": chat_id,
        "text": urllib.parse.quote(msg) if False else msg,
        "parse_mode": "HTML"
    }
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    data = json.dumps({"chat_id": chat_id, "text": msg, "parse_mode": "HTML"}).encode()
    req = urllib.request.Request(url, data=data,
                                  headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as r:
        result = json.loads(r.read())
    return result.get("ok", False)

# ── Main ──
lines = []
chat_id, chat_type, chat_name = get_chat_id()

if chat_id:
    lines.append(f"FOUND CHAT_ID={chat_id}  type={chat_type}  name={chat_name}")
    update_env(chat_id)
    lines.append("UPDATED .env with TELEGRAM_CHAT_ID")
    ok = send_test_alert(chat_id)
    lines.append(f"TEST_ALERT_SENT={ok}")
    lines.append("SETUP COMPLETE!")
else:
    lines.append("NO_UPDATES - send /start to your bot then rerun")

with open(OUT_FILE, "w") as f:
    f.write("\n".join(lines) + "\n")

print("\n".join(lines))
