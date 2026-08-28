"""TradingView alert API: capture once, replay 75x.

Phase 1 (CAPTURE):
    Opens Playwright browser. User creates ONE alert manually with the right
    webhook URL + message body. Script intercepts the POST request to TV's
    alert-creation endpoint, saves URL + body + headers to capture.json.

Phase 2 (REPLAY):
    Reads alerts_config.json + capture.json. For each (symbol, TF) combo,
    modifies the captured request body (symbol field, message body etc.)
    and replays via page.context.request.post() — uses the same browser
    session/cookies, bypassing DOM entirely.

Usage:
    # Phase 1 — capture (you create 1 alert manually):
    .venv\\Scripts\\python.exe tools\\tv_alert_setup\\capture_and_replay.py --capture

    # Phase 2 — replay all 75 remaining alerts:
    .venv\\Scripts\\python.exe tools\\tv_alert_setup\\capture_and_replay.py --replay

    # Replay a single alert (testing):
    .venv\\Scripts\\python.exe tools\\tv_alert_setup\\capture_and_replay.py --replay --filter-symbol XAGUSD --filter-tf H1
"""
from __future__ import annotations
import argparse
import json
import sys
import time
from copy import deepcopy
from pathlib import Path
from typing import Optional

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from playwright.sync_api import sync_playwright, Request, Response

HERE = Path(__file__).resolve().parent
PROFILE_DIR = HERE / "_browser_profile"
CONFIG_PATH = HERE / "alerts_config.json"
CAPTURE_PATH = HERE / "capture.json"
REPLAY_LOG = HERE / "replay.log"

# Endpoints we suspect TV uses for alert creation (will detect actual one at capture time)
LIKELY_ALERT_ENDPOINTS = (
    "/alerts/manage/",
    "/alerts/v2/manage/",
    "/api/v1/alerts",
    "/api/v2/alerts",
    "/alerts/create",
)
# Default: any POST/PUT/DELETE to *.tradingview.com/alerts/* during capture
ALERT_URL_HINT = "alerts"


# ────────────────────────── CAPTURE ──────────────────────────
def capture_mode() -> int:
    captured: list[dict] = []
    print("\n=== PHASE 1: CAPTURE ===")
    print("Steps:")
    print("  1. Browser will open to TradingView XAUUSD M5 chart.")
    print("  2. Press Alt+A in the browser to open the alert dialog.")
    print("  3. Configure the alert MANUALLY:")
    print("     - Condition: pick your indicator's signal (Rocket Prime etc.)")
    print("     - Notifications: enable Webhook URL")
    print("     - Webhook URL: https://shadow-cosmos-unending.ngrok-free.dev/tv-signal")
    print("     - Message: paste the JSON body for XAUUSD M5 from alerts_config.json")
    print("  4. Click 'Create' to save the alert.")
    print("  5. Script captures the POST request that TV sent.")
    print()
    print("CRITICAL: ONLY click Create ONCE. Multiple clicks = multiple captures = noise.")
    print("Once captured, close the browser window or press Ctrl+C in this terminal.")
    print()

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            headless=False,
            viewport={"width": 1600, "height": 1000},
            args=["--start-maximized"],
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        def _on_request(req: Request) -> None:
            try:
                # Capture ALL POST/PUT/PATCH/DELETE to *.tradingview.com.
                # We'll filter for the actual create endpoint after capture.
                # Skip GET (read-only) + non-TV requests + offline_fire polls.
                if req.method not in ("POST", "PUT", "PATCH", "DELETE"):
                    return
                if "tradingview.com" not in req.url:
                    return
                # Filter out the noisy polling endpoints
                noise = ("get_offline_fires", "get_offline_fire_controls",
                         "/heartbeat", "/telemetry", "/metrics", "/stats")
                if any(n in req.url for n in noise):
                    return
                body = None
                try:
                    body = req.post_data
                except Exception:
                    pass
                captured.append({
                    "method": req.method,
                    "url": req.url,
                    "headers": dict(req.headers),
                    "post_data": body,
                    "ts": time.time(),
                })
                print(f"\n*** CAPTURED [{len(captured)}] *** {req.method} {req.url}")
                if body:
                    print(f"   body[:300]: {body[:300]!r}")
            except Exception as e:
                print(f"  [capture err] {e}")

        page.on("request", _on_request)

        url = "https://www.tradingview.com/chart/?symbol=OANDA%3AXAUUSD&interval=5"
        print(f"Navigating to {url}")
        page.goto(url, wait_until="domcontentloaded", timeout=30_000)
        page.wait_for_timeout(8000)

        print("\nReady. Create the alert manually now. Script captures ALL POST/PUT to TV.")
        print("CLOSE the browser window when done — that signals capture complete.")
        # Block until browser is closed manually
        try:
            while True:
                time.sleep(2)
                # Check if context is still open
                try:
                    if not ctx.pages:
                        print("\nBrowser closed; saving captures.")
                        break
                except Exception:
                    print("\nBrowser context closed; saving captures.")
                    break
        except KeyboardInterrupt:
            print("\nInterrupted by user — saving captures so far.")

        if captured:
            CAPTURE_PATH.write_text(
                json.dumps(captured, indent=2, default=str), encoding="utf-8"
            )
            print(f"\nWrote {len(captured)} request(s) to: {CAPTURE_PATH}")
        else:
            print("\n[!] Nothing captured. Either no alert was created, or the URL pattern")
            print("    doesn't include 'alerts'. Check the browser DevTools Network tab")
            print("    for the actual POST request when creating an alert and update")
            print("    ALERT_URL_HINT in this script.")
            return 1

        try:
            ctx.close()
        except Exception:
            pass
    return 0


# ────────────────────────── REPLAY ──────────────────────────
def _adapt_body(captured_body: str, alert: dict) -> tuple[str, str]:
    """Modify the captured body for a different (symbol, TF) combo.

    TV's alert-creation API typically accepts a multipart or JSON form with
    fields like:
        symbol = "OANDA:XAUUSD"
        resolution = "5"  (TF)
        message = "..."
        notifications = "webhook,..."
        webhook_url = "..."

    We do a best-effort adaptation: substitute the OLD symbol & resolution
    with the new ones, replace the message body if it looks like a JSON we
    can identify. We DON'T touch other fields (auth tokens, session keys etc).

    Returns: (adapted_body, content_type_hint)
    """
    body = captured_body or ""
    content_type = "application/x-www-form-urlencoded"
    # Try parse as JSON first
    try:
        parsed = json.loads(body)
        if isinstance(parsed, dict):
            for k_sym in ("symbol", "ticker"):
                if k_sym in parsed:
                    parsed[k_sym] = f"{alert['exchange']}:{alert['broker_symbol']}"
            for k_res in ("resolution", "interval", "timeframe"):
                if k_res in parsed:
                    parsed[k_res] = alert["tv_interval"]
            for k_msg in ("message", "msg", "alert_message"):
                if k_msg in parsed:
                    parsed[k_msg] = alert["message_body"]
            for k_url in ("webhook_url", "url"):
                if k_url in parsed:
                    parsed[k_url] = alert["webhook_url"]
            return json.dumps(parsed), "application/json"
    except (ValueError, TypeError):
        pass

    # Try parse as form-encoded (a=b&c=d)
    if "=" in body and "&" in body:
        from urllib.parse import parse_qs, urlencode
        try:
            parsed_q = parse_qs(body, keep_blank_values=True)
            for k_sym in ("symbol", "ticker"):
                if k_sym in parsed_q:
                    parsed_q[k_sym] = [f"{alert['exchange']}:{alert['broker_symbol']}"]
            for k_res in ("resolution", "interval", "timeframe"):
                if k_res in parsed_q:
                    parsed_q[k_res] = [alert["tv_interval"]]
            for k_msg in ("message", "msg", "alert_message"):
                if k_msg in parsed_q:
                    parsed_q[k_msg] = [alert["message_body"]]
            for k_url in ("webhook_url", "url"):
                if k_url in parsed_q:
                    parsed_q[k_url] = [alert["webhook_url"]]
            adapted = urlencode(parsed_q, doseq=True)
            return adapted, content_type
        except Exception as e:
            print(f"  [warn] form-decode fail: {e}")

    # Fallback: do a string-replace on the captured body
    OLD_SYMBOL = "OANDA:XAUUSD"
    OLD_INTERVAL = "5"
    adapted = body.replace(OLD_SYMBOL, f"{alert['exchange']}:{alert['broker_symbol']}")
    return adapted, content_type


def replay_mode(filter_symbol: Optional[str], filter_tf: Optional[str], dry_run: bool) -> int:
    if not CAPTURE_PATH.exists():
        print(f"FATAL: {CAPTURE_PATH} missing. Run with --capture first.")
        return 1
    if not CONFIG_PATH.exists():
        print(f"FATAL: {CONFIG_PATH} missing. Run generate_alerts_config.py first.")
        return 1

    captures = json.loads(CAPTURE_PATH.read_text(encoding="utf-8"))
    if not captures:
        print("FATAL: capture.json is empty.")
        return 1
    template = captures[0]   # use the first POST as template
    print(f"=== Using template: {template['method']} {template['url']} ===")

    alerts = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    if filter_symbol:
        alerts = [a for a in alerts if a["symbol"] == filter_symbol.upper()]
    if filter_tf:
        alerts = [a for a in alerts if a["timeframe"] == filter_tf.upper()]

    print(f"=== Replaying {len(alerts)} alert(s). dry_run={dry_run} ===\n")

    success = 0
    failures = 0
    REPLAY_LOG.parent.mkdir(parents=True, exist_ok=True)
    log_f = REPLAY_LOG.open("a", encoding="utf-8")
    log_f.write(f"\n=== replay run {time.strftime('%Y-%m-%dT%H:%M:%S%z')} ===\n")

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            headless=True,  # headless OK for API replay — no UI needed
            viewport={"width": 1600, "height": 1000},
        )
        api = ctx.request

        for i, alert in enumerate(alerts):
            adapted_body, content_type = _adapt_body(template.get("post_data") or "", alert)
            headers = dict(template.get("headers") or {})
            # Drop hop-by-hop / forbidden headers Playwright manages
            for k in (
                "host", "content-length", "cookie", "connection", "accept-encoding",
                "user-agent", "accept",
            ):
                headers.pop(k, None)
                headers.pop(k.title(), None)
            if content_type:
                headers["Content-Type"] = content_type

            print(f"[{i+1}/{len(alerts)}] {alert['id']:<28} -> ", end="", flush=True)
            log_f.write(f"[{alert['id']}] body[:200]={adapted_body[:200]!r}\n")
            if dry_run:
                print(f"DRY (would POST {len(adapted_body)} bytes to {template['url'][:60]}...)")
                continue

            try:
                resp = api.post(
                    template["url"],
                    data=adapted_body,
                    headers=headers,
                    timeout=15_000,
                )
                status = resp.status
                body_preview = (resp.text() or "")[:180]
                if 200 <= status < 300:
                    success += 1
                    print(f"OK  ({status})  {body_preview[:80]}")
                else:
                    failures += 1
                    print(f"FAIL ({status})  {body_preview[:120]}")
                log_f.write(f"  -> {status}  {body_preview}\n")
            except Exception as e:
                failures += 1
                print(f"EXC  {e}")
                log_f.write(f"  -> EXC  {e}\n")
            time.sleep(0.6)  # be polite to TV's API

        log_f.close()
        try:
            ctx.close()
        except Exception:
            pass

    print(f"\n=== Done. {success} ok / {failures} failed / {len(alerts)} total ===")
    return 0 if failures == 0 else 2


# ────────────────────────── main ──────────────────────────
def main() -> int:
    ap = argparse.ArgumentParser()
    grp = ap.add_mutually_exclusive_group(required=True)
    grp.add_argument("--capture", action="store_true", help="Phase 1: capture template request")
    grp.add_argument("--replay", action="store_true", help="Phase 2: replay for all configs")
    ap.add_argument("--dry-run", action="store_true", help="(replay) don't actually POST")
    ap.add_argument("--filter-symbol", default=None)
    ap.add_argument("--filter-tf", default=None)
    args = ap.parse_args()
    if args.capture:
        return capture_mode()
    return replay_mode(args.filter_symbol, args.filter_tf, args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
