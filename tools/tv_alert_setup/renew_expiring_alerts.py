"""Renew Rocket Prime TV alerts that are about to expire.

Runs weekly via schtask. For each Rocket Prime alert whose expiration is
within 10 days, deletes + recreates it with a fresh 30-day expiration so
the alert stays active continuously.
"""
from __future__ import annotations

import copy
import json
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
PROFILE = HERE / "_browser_profile"
CAPTURE_PATH = HERE / "capture_create_post.json"
PINE_TEMPLATE_PATH = HERE / "pine_alert_template.json"
ROOT = HERE.parent.parent
ENV_PATH = ROOT / "config" / ".env"
LOG_PATH = ROOT / "logs" / "alert_renewer.log"
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
ROCKET_PRIME = "PUB;56f0fb74de7f4eed9325b987428b727e"

RENEWAL_THRESHOLD_DAYS = 10  # renew if expiry within N days
NEW_EXPIRY_DAYS = 30         # extend by N days

SECRET = None
for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
    if line.startswith("TV_WEBHOOK_SECRET"):
        SECRET = line.split("=", 1)[1].strip().strip('"').strip("'")
        break
WEBHOOK_URL = f"https://shadow-cosmos-unending.ngrok-free.dev/tv-signal?secret={SECRET}"


def _log(msg: str) -> None:
    line = f"{datetime.now().isoformat(timespec='seconds')} {msg}"
    print(line)
    try:
        LOG_PATH.open("a", encoding="utf-8").write(line + "\n")
    except Exception:
        pass


def _try_send_telegram(text: str) -> None:
    try:
        sys.path.insert(0, str(ROOT))
        from ai_trading_agents.telegram_notifier import get_notifier
        tg = get_notifier()
        if tg and tg.enabled:
            tg.send(text)
    except Exception:
        pass


def main():
    if not CAPTURE_PATH.exists() or not PINE_TEMPLATE_PATH.exists():
        _log("FATAL: missing capture or template files")
        return 1

    captures = json.loads(CAPTURE_PATH.read_text(encoding="utf-8"))
    cap = captures[0]
    captured_url = cap["url"]
    captured_headers = cap.get("headers") or {}
    captured_body = json.loads(cap.get("post_data") or "{}")
    base_payload = captured_body.get("payload", {})
    pine_template = json.loads(PINE_TEMPLATE_PATH.read_text(encoding="utf-8"))
    pine_condition = pine_template["condition"]

    create_hdrs = {k: v for k, v in captured_headers.items()
                   if k.lower() not in ("host", "content-length", "cookie", "connection",
                                         "accept-encoding")}
    create_hdrs["Origin"] = "https://www.tradingview.com"
    create_hdrs["Referer"] = "https://www.tradingview.com/"
    create_hdrs["Content-Type"] = "text/plain;charset=UTF-8"

    json_hdrs = {"Origin": "https://www.tradingview.com",
                 "Referer": "https://www.tradingview.com/chart/",
                 "Content-Type": "application/json"}

    now = datetime.now(timezone.utc)
    threshold = now + timedelta(days=RENEWAL_THRESHOLD_DAYS)

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(user_data_dir=str(PROFILE), headless=True)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto("https://www.tradingview.com/chart/", wait_until="domcontentloaded", timeout=30_000)
        time.sleep(3)
        api = ctx.request

        r = api.post("https://pricealerts.tradingview.com/list_alerts",
                     data=json.dumps({"payload": {"limit": 5000}}),
                     headers=json_hdrs, timeout=15_000)
        alerts = r.json().get("r", [])

        # Find Rocket Prime alerts expiring soon
        expiring = []
        all_rp = 0
        for a in alerts:
            cond = a.get("condition") or {}
            if cond.get("type") != "pine_alert":
                continue
            series = cond.get("series") or [{}]
            if series[0].get("pine_id") != ROCKET_PRIME:
                continue
            all_rp += 1
            exp_str = a.get("expiration", "")
            try:
                exp_dt = datetime.fromisoformat(exp_str.replace("Z", "+00:00"))
            except Exception:
                continue
            days_left = (exp_dt - now).total_seconds() / 86400
            if exp_dt < threshold:
                expiring.append((a, days_left))

        _log(f"Total Rocket Prime alerts: {all_rp}")
        _log(f"Expiring within {RENEWAL_THRESHOLD_DAYS} days: {len(expiring)}")

        if not expiring:
            _log("Nothing to renew. Done.")
            ctx.close()
            return 0

        # Renew each (delete + recreate with fresh expiration)
        success = 0
        failed = 0
        for a, days_left in expiring:
            sym_raw = a.get("symbol", "")
            try:
                sym_obj = json.loads(sym_raw[1:]) if sym_raw.startswith("=") else {}
                full_sym = sym_obj.get("symbol", sym_raw)
            except Exception:
                full_sym = sym_raw

            # 1. Delete the old alert
            del_r = api.post("https://pricealerts.tradingview.com/delete_alerts",
                             data=json.dumps({"payload": {"alert_ids": [a["alert_id"]]}}),
                             headers=json_hdrs, timeout=15_000)
            del_ok = del_r.status == 200 and '"s":"ok"' in del_r.text()
            if not del_ok:
                _log(f"  [DEL FAIL] {full_sym}: {del_r.text()[:120]}")
                failed += 1
                continue

            # 2. Recreate with fresh expiration
            new_exp = (now + timedelta(days=NEW_EXPIRY_DAYS)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
            new_condition = copy.deepcopy(pine_condition)
            new_condition["resolution"] = a.get("resolution", "60")

            payload = copy.deepcopy(base_payload)
            payload["symbol"] = sym_raw
            payload["resolution"] = a.get("resolution", "60")
            payload["expiration"] = new_exp
            payload["message"] = ""
            payload["conditions"] = [new_condition]
            payload["name"] = None
            payload["web_hook"] = WEBHOOK_URL
            for k in ("condition", "complexity", "type", "kinds", "cross_interval",
                      "expiration_policy", "pro_symbol", "presentation_data",
                      "mutable_study_data"):
                payload.pop(k, None)

            time.sleep(0.4)
            create_r = api.post(captured_url, data=json.dumps({"payload": payload}),
                                headers=create_hdrs, timeout=15_000)
            create_ok = create_r.status == 200 and '"s":"ok"' in create_r.text()
            if create_ok:
                aid = None
                try:
                    aid = create_r.json().get("r", {}).get("alert_id")
                except Exception:
                    pass
                _log(f"  [RENEW OK] {full_sym} (was {days_left:.1f}d left → +{NEW_EXPIRY_DAYS}d)  new_id={aid}")
                success += 1
            else:
                _log(f"  [CREATE FAIL] {full_sym}: {create_r.text()[:150]}")
                failed += 1
            time.sleep(0.4)

        ctx.close()

    summary = f"TV alert renewal: {success} renewed, {failed} failed (out of {len(expiring)} expiring soon)"
    _log(summary)
    if success or failed:
        _try_send_telegram(f"<b>🔄 TV Alerts Renewed</b>\n{summary}")
    return 0 if failed == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
