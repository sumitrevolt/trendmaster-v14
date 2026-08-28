"""Delete the 33 bad alerts created by my failed automation runs.

Strict triple-filter (ALL must match): created today after 14:00 UTC + condition.type='cross' + web_hook contains our domain.

Safety: print each before deleting; require explicit --confirm flag to actually fire.
"""
from __future__ import annotations
import argparse
import json
import sys
import time
from pathlib import Path
from datetime import datetime, timezone

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
PROFILE_DIR = HERE / "_browser_profile"
CATEGORIZED_PATH = HERE / "alerts_categorized.json"
LOG_PATH = HERE / "delete_bad_alerts.log"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--confirm", action="store_true", help="Actually delete (default: dry-run)")
    args = ap.parse_args()

    if not CATEGORIZED_PATH.exists():
        print(f"FATAL: {CATEGORIZED_PATH} missing. Run inventory_and_categorize.py first.")
        return 1

    cat = json.loads(CATEGORIZED_PATH.read_text(encoding="utf-8"))
    delete_list = cat["delete_candidates"]
    print(f"=== Delete plan: {len(delete_list)} alerts ===\n")
    for d in delete_list:
        print(f"  [{d['alert_id']}] {d['symbol']:<25} {d['message_preview'][:40]!r}")
    print()

    if not args.confirm:
        print("DRY-RUN. Add --confirm to actually delete.")
        return 0

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            headless=True,
            viewport={"width": 1600, "height": 1000},
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto("https://www.tradingview.com/chart/", wait_until="domcontentloaded", timeout=30_000)
        time.sleep(4)

        api = ctx.request
        hdrs = {
            "Origin": "https://www.tradingview.com",
            "Referer": "https://www.tradingview.com/chart/",
            "Content-Type": "application/json",
        }

        # CONFIRMED endpoint + payload (probed 2026-05-04):
        #   POST https://pricealerts.tradingview.com/delete_alerts
        #   body: {"payload": {"alert_ids": [<int>, <int>, ...]}}
        #   accepts batch! Returns {"s":"ok"} on success.
        URL = "https://pricealerts.tradingview.com/delete_alerts"
        all_ids = [d["alert_id"] for d in delete_list]
        log_f = LOG_PATH.open("w", encoding="utf-8")
        log_f.write(f"Delete run at {datetime.now(timezone.utc).isoformat()}\n")
        log_f.write(f"IDs: {all_ids}\n\n")

        # Batch delete (up to 50 per call to be safe)
        BATCH = 25
        success = 0
        failed_ids = []
        for i in range(0, len(all_ids), BATCH):
            chunk = all_ids[i:i+BATCH]
            body = {"payload": {"alert_ids": chunk}}
            try:
                r = api.post(URL, data=json.dumps(body), headers=hdrs, timeout=15000)
                txt = r.text()[:300]
                if r.status == 200 and '"s":"ok"' in txt:
                    success += len(chunk)
                    print(f"  [batch ok] {len(chunk)} ids deleted: {chunk[:5]}{'...' if len(chunk)>5 else ''}")
                    log_f.write(f"OK batch ({len(chunk)}): {chunk}  -> {txt}\n")
                else:
                    failed_ids.extend(chunk)
                    print(f"  [batch FAIL] HTTP {r.status} {txt[:120]}")
                    log_f.write(f"FAIL batch ({len(chunk)}): {chunk}  -> HTTP {r.status} {txt[:200]}\n")
            except Exception as e:
                failed_ids.extend(chunk)
                print(f"  [batch ERR] {e}")
                log_f.write(f"ERR batch ({len(chunk)}): {e}\n")
            time.sleep(0.5)

        log_f.close()
        print(f"\n=== Results: {success} deleted / {len(failed_ids)} failed / {len(all_ids)} total ===")
        if failed_ids:
            print(f"Failed IDs: {failed_ids}")
        ctx.close()
        failed = len(failed_ids)

    return 0 if failed == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
