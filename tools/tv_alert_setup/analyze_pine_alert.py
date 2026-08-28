"""Extract one of the user's existing Pine alerts (cond=pine_alert) and dump
its full JSON structure so we can mimic it for CREATE."""
from __future__ import annotations
import json
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

HERE = Path(__file__).resolve().parent
INVENTORY_PATH = HERE / "alerts_full_inventory.json"
OUT_PATH = HERE / "pine_alert_template.json"

data = json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))
alerts = data.get("r", [])

# Find first pine_alert
pine_alerts = [a for a in alerts if (a.get("condition") or {}).get("type") == "pine_alert"]
print(f"=== Found {len(pine_alerts)} pine_alert entries ===\n")

if not pine_alerts:
    print("FATAL: no pine_alerts found")
    sys.exit(1)

# Pick the first one + write full structure
template = pine_alerts[0]
print(f"=== Sample pine_alert (alert_id={template.get('alert_id')}) ===\n")
print(json.dumps(template, indent=2)[:3000])
print()

# Also list the keys to see what we need
print(f"=== Keys in pine_alert: ===")
for k in sorted(template.keys()):
    v = template[k]
    if isinstance(v, (dict, list)):
        print(f"  {k:<25} = <{type(v).__name__}> {str(v)[:80]}")
    else:
        print(f"  {k:<25} = {str(v)[:80]!r}")

OUT_PATH.write_text(json.dumps(template, indent=2), encoding="utf-8")
print(f"\nFull template saved: {OUT_PATH}")

# Show condition structure specifically
print(f"\n=== condition.series structure ===")
cond = template.get("condition", {})
print(json.dumps(cond, indent=2)[:1500])
