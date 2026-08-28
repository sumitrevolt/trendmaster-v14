"""Just import dashboard_server module to find any syntax/import errors."""
import sys, traceback
from pathlib import Path

OUT = Path(r"C:\Users\Ratanshila\Documents\autmated trading\outputs\dash_import_check.txt")
ROOT = Path(r"C:\Users\Ratanshila\Documents\autmated trading")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

lines = ["=== Dashboard import check ==="]
try:
    import dashboard_server
    lines.append(f"✓ Imported dashboard_server from {dashboard_server.__file__}")
    lines.append(f"  Has PORT: {getattr(dashboard_server, 'PORT', '?')}")
    lines.append(f"  Has _refresh_tv_alerts_now: {hasattr(dashboard_server, '_refresh_tv_alerts_now')}")
    lines.append(f"  Has _silent_spawn_component: {hasattr(dashboard_server, '_silent_spawn_component')}")
except Exception as e:
    lines.append(f"✗ IMPORT FAILED: {type(e).__name__}: {e}")
    lines.append(traceback.format_exc())

OUT.write_text("\n".join(lines), encoding="utf-8")
print(OUT)
