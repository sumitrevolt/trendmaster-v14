"""Run reactivate_inactive.py and capture output to file."""
import sys
import io
from pathlib import Path

ROOT = Path(r"C:\Users\Ratanshila\Documents\autmated trading")
LOG = ROOT / "outputs" / "reactivate_result.txt"

# Redirect stdout to log file
sys.path.insert(0, str(ROOT / "tools" / "tv_alert_setup"))
buf = io.StringIO()
old_stdout = sys.stdout
sys.stdout = buf

try:
    import reactivate_inactive
    rc = reactivate_inactive.main()
except Exception as e:
    print(f"ERROR: {e}")
    rc = 1

sys.stdout = old_stdout
output = buf.getvalue()
LOG.write_text(output + f"\n[exit code: {rc}]\n", encoding="utf-8")
