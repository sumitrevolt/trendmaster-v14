"""
2026-05-14 — One-shot cleanup of stale MT5 signal files + executor health check.

Strategy:
  1. Locate MT5 MQL5/Files via terminal_info.data_path
  2. List every trendmaster_signals*.json with its age
  3. Delete (archive) any file older than 90s — the same threshold the executor uses
  4. Report exactly what was cleaned + check if executor is alive (via sentinel + psutil)
  5. Write summary to outputs/stale_signal_cleanup_report.json
"""
import json
import shutil
import time
from datetime import datetime
from pathlib import Path

REPORT = Path(__file__).parent / "stale_signal_cleanup_report.json"
STALE_THRESHOLD_S = 90
PROJECT_ROOT = Path(__file__).parent.parent

report = {
    "ts": datetime.now().isoformat(timespec="seconds"),
    "stale_threshold_s": STALE_THRESHOLD_S,
    "phase": "",
    "errors": [],
}

# --- Phase 1: locate MT5 data path via MetaTrader5 module ---
report["phase"] = "locate_mt5"
try:
    import MetaTrader5 as mt5  # type: ignore
    if not mt5.initialize():
        report["errors"].append(f"mt5.initialize failed: {mt5.last_error()}")
    else:
        ti = mt5.terminal_info()
        if not ti:
            report["errors"].append("terminal_info returned None")
        else:
            sig_dir = Path(ti.data_path) / "MQL5" / "Files"
            report["sig_dir"] = str(sig_dir)
            report["sig_dir_exists"] = sig_dir.exists()
        mt5.shutdown()
except ImportError as e:
    report["errors"].append(f"MetaTrader5 import failed: {e}")
    sig_dir = None

# --- Phase 2: scan signal files, classify by age ---
report["phase"] = "scan"
sig_dir = Path(report.get("sig_dir", "")) if report.get("sig_dir") else None

now = time.time()
files_info = []
archive_dir = None

if sig_dir and sig_dir.exists():
    # Set up archive dir for moved-not-deleted strategy
    archive_dir = sig_dir / "stale_archive"
    archive_dir.mkdir(exist_ok=True)
    report["archive_dir"] = str(archive_dir)

    for f in sig_dir.glob("trendmaster_signals*.json"):
        try:
            mtime = f.stat().st_mtime
            age = now - mtime
            # Also try to read the embedded ts field
            try:
                content = json.loads(f.read_text(encoding="utf-8"))
                embedded_ts = content.get("ts", 0)
                embedded_age = now - embedded_ts if embedded_ts else None
                symbol = content.get("symbol", f.stem.replace("trendmaster_signals_", ""))
                direction = content.get("direction", content.get("dir", "?"))
            except Exception:
                embedded_age = None
                symbol = f.stem
                direction = "?"

            stale = age > STALE_THRESHOLD_S
            files_info.append({
                "name": f.name,
                "symbol": symbol,
                "direction": direction,
                "file_age_s": int(age),
                "embedded_age_s": int(embedded_age) if embedded_age is not None else None,
                "stale": stale,
                "path": str(f),
            })
        except Exception as e:
            report["errors"].append(f"scan error {f.name}: {e}")

report["found_count"] = len(files_info)
report["files"] = files_info
report["stale_count"] = sum(1 for f in files_info if f["stale"])
report["fresh_count"] = sum(1 for f in files_info if not f["stale"])

# --- Phase 3: move stale files to archive (SAFER than delete) ---
report["phase"] = "archive"
moved = []
for f in files_info:
    if not f["stale"]:
        continue
    src = Path(f["path"])
    if not archive_dir:
        report["errors"].append("no archive_dir available")
        break
    # Archive name: original + timestamp suffix
    stamp = datetime.fromtimestamp(now - f["file_age_s"]).strftime("%Y%m%d_%H%M%S")
    dst = archive_dir / f"{src.stem}_{stamp}{src.suffix}"
    try:
        shutil.move(str(src), str(dst))
        moved.append({"symbol": f["symbol"], "age_s": f["file_age_s"], "archived_to": dst.name})
    except Exception as e:
        report["errors"].append(f"archive failed {src.name}: {e}")
report["moved_count"] = len(moved)
report["moved"] = moved

# --- Phase 4: executor health check ---
report["phase"] = "executor_health"
try:
    import psutil
    exec_procs = []
    for p in psutil.process_iter(["pid", "name", "cmdline", "create_time"]):
        try:
            cl = " ".join(p.info["cmdline"] or [])
            if "python_signal_executor.py" in cl:
                exec_procs.append({
                    "pid": p.info["pid"],
                    "uptime_s": int(now - p.info["create_time"]),
                })
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    report["executor_pids"] = exec_procs
    report["executor_running"] = len(exec_procs) > 0
except ImportError:
    report["errors"].append("psutil not available — could not check executor")

# Check executor sentinel file (py_executor.alive)
if sig_dir and sig_dir.exists():
    sentinel = sig_dir / "py_executor.alive"
    if sentinel.exists():
        try:
            sentinel_ts = int(sentinel.read_text().strip())
            report["sentinel_age_s"] = int(now - sentinel_ts)
            report["sentinel_alive"] = (now - sentinel_ts) < 120  # 2min threshold
        except Exception as e:
            report["errors"].append(f"sentinel read failed: {e}")
    else:
        report["sentinel_exists"] = False

# --- Final: write report ---
report["phase"] = "done"
REPORT.write_text(json.dumps(report, indent=2), encoding="utf-8")

# Print compact summary for stdout
print(f"FOUND={report['found_count']} STALE={report['stale_count']} ARCHIVED={report['moved_count']}")
print(f"EXECUTOR_RUNNING={report.get('executor_running', '?')} SENTINEL_AGE={report.get('sentinel_age_s', '?')}s")
if report["errors"]:
    print(f"ERRORS: {report['errors']}")
print(f"Full report: {REPORT}")
