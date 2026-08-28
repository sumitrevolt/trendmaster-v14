"""Hit /api/status, dump JSON to a file for inspection."""
import urllib.request, json
from pathlib import Path
OUT = Path(r"C:\Users\Ratanshila\Documents\autmated trading\outputs\api_probe.json")
try:
    r = urllib.request.urlopen("http://127.0.0.1:8765/api/status", timeout=15)
    data = json.loads(r.read().decode())
    # Just write the structural keys + sample values
    summary = {
        "account_keys": list(data.get("account",{}).keys()),
        "n_positions": data.get("account",{}).get("n_positions"),
        "positions_count": len(data.get("account",{}).get("positions",[])),
        "positions_sample": data.get("account",{}).get("positions",[])[:2],
        "deals_count": len(data.get("deals",{}).get("deals",[])),
        "deals_stats": data.get("deals",{}).get("stats"),
        "deals_sample": data.get("deals",{}).get("deals",[])[:2],
        "recent_skips_count": len(data.get("recent_skips",{}).get("items",[])),
        "recent_skips_sample": data.get("recent_skips",{}).get("items",[])[:2],
    }
    OUT.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
except Exception as e:
    OUT.write_text(f"ERROR: {e}", encoding="utf-8")
