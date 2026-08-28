"""Get FULL alert list via TV's API + categorize each as KEEP or DELETE-candidate.

KEEP rules (alert is preserved):
  - condition.type != 'cross'   (means it uses an indicator like Rocket Prime)
  - OR webhook URL doesn't match our auto-script's
  - OR created BEFORE 2026-05-04 14:00 UTC (= before today's automation runs)

DELETE-candidate rules (likely my bad auto-created alerts):
  - condition.type == 'cross' (default price crossing)
  - AND created >= 2026-05-04 14:00 UTC
  - AND web_hook contains 'shadow-cosmos-unending'

Operator MUST review and confirm before any deletion.
"""
from __future__ import annotations
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
INVENTORY_PATH = HERE / "alerts_full_inventory.json"
CATEGORIZED_PATH = HERE / "alerts_categorized.json"

CUTOFF_UTC = datetime(2026, 5, 4, 14, 0, 0, tzinfo=timezone.utc)
OUR_HOOK = "shadow-cosmos-unending"


def main() -> int:
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            headless=True,  # headless OK for API only
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
        r = api.post(
            "https://pricealerts.tradingview.com/list_alerts",
            data=json.dumps({"payload": {"limit": 5000}}),
            headers=hdrs,
            timeout=15000,
        )
        if r.status != 200:
            print(f"FATAL: list_alerts returned HTTP {r.status}")
            print(r.text()[:500])
            return 1

        data = r.json()
        alerts = data.get("r", [])
        print(f"=== Got {len(alerts)} total alerts from TV ===\n")

        INVENTORY_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
        print(f"Full inventory saved: {INVENTORY_PATH}\n")

        # Categorize
        keep = []
        delete_candidates = []
        for a in alerts:
            create_time_str = a.get("create_time", "")
            try:
                ct = datetime.fromisoformat(create_time_str.replace("Z", "+00:00"))
            except Exception:
                ct = None

            cond_type = (a.get("condition") or {}).get("type", "")
            web_hook = a.get("web_hook", "") or ""
            symbol_raw = a.get("symbol", "")
            message = (a.get("message") or "")[:80]
            alert_id = a.get("alert_id")
            resolution = a.get("resolution", "")

            # Extract clean symbol from "={\"symbol\":\"OANDA:XAGUSD\",...}"
            try:
                if symbol_raw.startswith("="):
                    sym_obj = json.loads(symbol_raw[1:])
                    clean_symbol = sym_obj.get("symbol", symbol_raw)
                else:
                    clean_symbol = symbol_raw
            except Exception:
                clean_symbol = symbol_raw

            row = {
                "alert_id": alert_id,
                "symbol": clean_symbol,
                "resolution": resolution,
                "condition_type": cond_type,
                "create_time": create_time_str,
                "message_preview": message,
                "has_our_hook": OUR_HOOK in web_hook,
                "web_hook_short": web_hook[:80] if web_hook else "(none)",
            }

            # Decide category
            is_today = ct is not None and ct >= CUTOFF_UTC
            is_default_cross = cond_type == "cross"
            is_our_hook = OUR_HOOK in web_hook

            if is_today and is_default_cross and is_our_hook:
                row["reason"] = "TODAY + cross condition + our hook = AUTO-CREATED bad alert"
                delete_candidates.append(row)
            else:
                reasons = []
                if not is_today:
                    reasons.append(f"older (created {create_time_str})")
                if not is_default_cross:
                    reasons.append(f"non-cross condition ({cond_type})")
                if not is_our_hook:
                    reasons.append("different webhook URL")
                row["reason"] = "KEEP - " + ", ".join(reasons)
                keep.append(row)

        # Print summary
        print(f"=== CATEGORIZATION ===")
        print(f"  KEEP (legitimate):       {len(keep)}")
        print(f"  DELETE candidates (mine): {len(delete_candidates)}")

        print(f"\n--- KEEP list ---")
        for k in keep:
            print(f"  [{k['alert_id']}] {k['symbol']:<25} res={k['resolution']:<3} cond={k['condition_type']:<8}  {k['reason']}")

        print(f"\n--- DELETE candidates ---")
        for d in delete_candidates:
            print(f"  [{d['alert_id']}] {d['symbol']:<25} res={d['resolution']:<3}  msg={d['message_preview'][:50]!r}")

        out = {
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "total": len(alerts),
            "keep_count": len(keep),
            "delete_count": len(delete_candidates),
            "keep": keep,
            "delete_candidates": delete_candidates,
        }
        CATEGORIZED_PATH.write_text(json.dumps(out, indent=2), encoding="utf-8")
        print(f"\n=== Categorized inventory saved: {CATEGORIZED_PATH} ===")
        print(f"Operator must review {CATEGORIZED_PATH} before running delete.")

        ctx.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
