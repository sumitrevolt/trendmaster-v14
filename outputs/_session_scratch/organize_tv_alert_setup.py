"""Organize tools/tv_alert_setup/ — keep essentials at top level, move the rest to _archive/."""
from pathlib import Path
import shutil

ROOT = Path(r"C:\Users\Ratanshila\Documents\autmated trading\tools\tv_alert_setup")
ARCHIVE = ROOT / "_archive"
ARCHIVE.mkdir(exist_ok=True)

# ESSENTIAL — keep in tools/tv_alert_setup/ (used in production workflow)
KEEP = {
    # Core data
    "pine_alert_template.json",       # Rocket Prime template (critical)
    "capture_create_post.json",       # Auth-validated POST capture (critical)
    "alerts_config.json",             # Format B config from this session
    "alerts_done.json",               # Checkpoint
    # Core scripts (the API path that works)
    "api_create_alerts.py",
    "delete_all_rocket_then_recreate.py",
    "recreate_top5_instant.py",
    "list_alerts.py",
    "inventory_and_categorize.py",
    "verify_coverage.py",
    "analyze_pine_alert.py",
    # Format B helpers (this session)
    "generate_alerts_format_b.py",
    # Useful future-utility
    "renew_expiring_alerts.py",
    # README
    "README.md",
    # Playwright UI fallback (may be useful if API ever changes)
    "setup_tv_alerts.py",
    # Browser profile + cache + log dirs
    "_browser_profile",
    "_archive",
    "__pycache__",
    "delete_bad_alerts.log",
    "api_create.log",
}

print(f"=== Organizing {ROOT} ===")
moved = 0
kept = 0
for item in ROOT.iterdir():
    if item.name in KEEP:
        print(f"  KEEP    {item.name}")
        kept += 1
    else:
        target = ARCHIVE / item.name
        if target.exists():
            # already there — skip
            print(f"  SKIP    {item.name}  (already in _archive)")
            continue
        try:
            shutil.move(str(item), str(target))
            print(f"  MOVED   {item.name}  ->  _archive/")
            moved += 1
        except Exception as e:
            print(f"  FAIL    {item.name}: {e}")

print(f"\n=== Summary: {kept} kept, {moved} moved to _archive/ ===")
