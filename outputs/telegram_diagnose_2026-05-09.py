"""Diagnose the Telegram 404 spam in trend_master_brain.out.

Pings api.telegram.org with the current TELEGRAM_BOT_TOKEN from
config/.env. Tells operator what to do based on response code:
  - 200: bot is healthy → 404 in brain.out is a different issue
         (chat_id wrong, or bot blocked by user, or message too long)
  - 401: token revoked → operator regenerates via @BotFather /token
  - 404: bot deleted → operator creates new bot via @BotFather /newbot

Read-only — does NOT change config/.env. Operator pastes new token if needed.
"""
from __future__ import annotations

import json
import os
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load_env(env_path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    if not env_path.exists():
        return env
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def call_get_me(token: str) -> tuple[int, dict | None, str]:
    url = f"https://api.telegram.org/bot{token}/getMe"
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            return resp.status, json.loads(body), ""
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        try:
            return e.code, json.loads(body), ""
        except Exception:
            return e.code, None, body
    except Exception as e:
        return -1, None, str(e)


def call_send_message(token: str, chat_id: str, text: str) -> tuple[int, dict | None, str]:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = json.dumps({"chat_id": chat_id, "text": text}).encode("utf-8")
    try:
        req = urllib.request.Request(url, data=payload, method="POST",
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            return resp.status, json.loads(body), ""
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        try:
            return e.code, json.loads(body), ""
        except Exception:
            return e.code, None, body
    except Exception as e:
        return -1, None, str(e)


def main() -> int:
    print(f"=== Telegram bot diagnostic ({datetime.now()}) ===")
    print()

    env = load_env(ROOT / "config" / ".env")
    token = env.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = env.get("TELEGRAM_CHAT_ID", "")
    enabled = env.get("TELEGRAM_ENABLED", "")

    if not token:
        print("[X] TELEGRAM_BOT_TOKEN missing in config/.env")
        return 1
    if not chat_id:
        print("[X] TELEGRAM_CHAT_ID missing in config/.env")
        return 1

    print(f"  TELEGRAM_ENABLED  = {enabled}")
    print(f"  TELEGRAM_BOT_TOKEN= {token[:10]}...{token[-6:]}  (length={len(token)})")
    print(f"  TELEGRAM_CHAT_ID  = {chat_id}")
    print()

    # 1. getMe — verifies token + bot existence
    print("[1/2] Calling getMe to verify bot identity...")
    code, body, err = call_get_me(token)
    if code == 200 and body and body.get("ok"):
        bot = body.get("result", {})
        print(f"  OK   bot id={bot.get('id')} username=@{bot.get('username')} name={bot.get('first_name')}")
        print(f"       can_join_groups={bot.get('can_join_groups')} can_read_all_messages={bot.get('can_read_all_group_messages')}")
        bot_ok = True
    elif code == 401:
        print(f"  X    HTTP 401 Unauthorized — token REVOKED or invalid")
        print(f"       body: {body or err}")
        print()
        print("  REPAIR:")
        print("    1. Open Telegram, search @BotFather")
        print("    2. Send /token, pick @Sumits_jarvis_bot, copy new token")
        print("    3. Update config/.env line: TELEGRAM_BOT_TOKEN=<new>")
        print("    4. Restart brain (start_brain_clean.cmd) to pick up new token")
        return 2
    elif code == 404:
        print(f"  X    HTTP 404 Not Found — bot DELETED or token format wrong")
        print(f"       body: {body or err}")
        print()
        print("  REPAIR:")
        print("    1. Open Telegram, search @BotFather")
        print("    2. Send /mybots — check if bot still exists")
        print("    3. If gone: /newbot to create fresh bot")
        print("    4. If still exists but token bad: /token to regen")
        print("    5. Update config/.env TELEGRAM_BOT_TOKEN")
        print("    6. Send /start to the new bot from your account so chat_id stays valid")
        print("    7. Restart brain")
        return 2
    else:
        print(f"  X    HTTP {code}")
        print(f"       body: {body or err}")
        return 2

    # 2. sendMessage — verifies chat_id reachability
    print()
    print("[2/2] Calling sendMessage to verify chat_id is reachable...")
    test_msg = f"[{datetime.now().strftime('%H:%M:%S')}] Telegram diagnostic OK from outputs/telegram_diagnose"
    code, body, err = call_send_message(token, chat_id, test_msg)
    if code == 200 and body and body.get("ok"):
        msg_id = body.get("result", {}).get("message_id")
        print(f"  OK   message delivered, message_id={msg_id}")
        print()
        print("  CONCLUSION: Telegram pipeline is healthy. The 404 spam in")
        print("  trend_master_brain.out is from BEFORE this diagnostic — possibly")
        print("  a transient API outage. Brain should recover automatically on")
        print("  next message attempt. If 404 persists in fresh log lines, look")
        print("  for stale token caching in telegram_notifier.py.")
        return 0
    elif code == 400:
        print(f"  X    HTTP 400 — likely 'chat not found' or message format issue")
        print(f"       body: {body or err}")
        print()
        print("  REPAIR (chat_id):")
        print(f"    Operator must send /start to bot from chat_id={chat_id}.")
        print(f"    To find the correct chat_id: send any msg to bot, then call")
        print(f"    https://api.telegram.org/bot{token[:8]}.../getUpdates and look")
        print(f"    for the 'from.id' field.")
        return 3
    elif code == 403:
        print(f"  X    HTTP 403 — user blocked the bot")
        print(f"       body: {body or err}")
        print(f"  REPAIR: open Telegram, find the bot, send /start to unblock.")
        return 3
    elif code == 404:
        print(f"  X    HTTP 404 on sendMessage but getMe was OK")
        print(f"       body: {body or err}")
        print(f"  This is unusual. Possibly chat_id={chat_id} doesn't exist or")
        print(f"  bot was kicked from group. Send /start to bot from operator account.")
        return 3
    else:
        print(f"  X    HTTP {code}")
        print(f"       body: {body or err}")
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
