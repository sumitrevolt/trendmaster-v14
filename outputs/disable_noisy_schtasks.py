"""Disable schtasks that contribute to popup spam but are redundant or non-critical.

KEEPS enabled (essential):
- TrendMaster Health Watchdog (1 min, now silent via psutil)
- TrendMaster Telegram Direction Listener (long-running)
- TrendMaster Live Dashboard (operator-facing)
- TrendMaster Daily Summary / Hourly Snapshot (pythonw, silent)

DISABLES (redundant or noisy):
- TV Webhook Watchdog (5 min) — Health Watchdog covers webhook
- Watch-Pets (1-2 min) — redundant
- Brain Watchpet (5 min) — redundant
- Brain Liveness (5 min) — redundant with Health Watchdog
- Junction Guard (15 min) — rare regression
- Signal Pipeline Monitor (5 min) — redundant
- Signal-to-Trade SLA (1 min) — diagnostic
- Signal Outcome Collector (5 min) — diagnostic
- Schtasks Audit — diagnostic
- Code Graph Rebuild — daily, non-critical
- Brain Forensics (every 30s) — diagnostic
- Alert Bridge (every 1 min) — third-party bridge
- Auto Research, Walkforward Lab — heavy R&D
- Events Rotator — log rotation
- Pytest Health Check
- News Calendar Refresh — runs daily
- Reactivate Alerts
- EA Parity Nightly
"""
import subprocess
import sys
import time

KEEP_ENABLED = {
    "TrendMaster Health Watchdog",      # 1 min, silent psutil-only
    "TrendMaster Telegram Direction Listener",
    "TrendMaster Live Dashboard",
    "TrendMaster Daily Summary",
    "TrendMaster Hourly Snapshot",
    "TrendMaster TV Alert Renewer",     # operator-critical, pythonw silent
    "TrendMaster Morning Routine",      # 8:30 IST, once/day
}

# Anything else with TrendMaster prefix gets disabled
result = subprocess.run(
    ["schtasks", "/Query", "/FO", "CSV"],
    capture_output=True, text=True, timeout=15,
    creationflags=subprocess.CREATE_NO_WINDOW,
)
lines = result.stdout.splitlines()

disabled = []
skipped_keep = []
errors = []
for line in lines[1:]:
    parts = [p.strip('"') for p in line.split('","')]
    if len(parts) < 1:
        continue
    task = parts[0]
    if not task.startswith("\\TrendMaster"):
        continue
    # Strip leading \
    name = task.lstrip("\\")
    if name in KEEP_ENABLED:
        skipped_keep.append(name)
        continue

    # Disable
    r = subprocess.run(
        ["schtasks", "/Change", "/TN", task, "/DISABLE"],
        capture_output=True, text=True, timeout=8,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    if r.returncode == 0:
        disabled.append(name)
    else:
        errors.append((name, r.stderr.strip() or r.stdout.strip()))

from pathlib import Path
out = Path(__file__).parent / "disable_schtasks.log"
with open(out, "w", encoding="utf-8") as f:
    f.write(f"=== Disable noisy schtasks — {time.strftime('%H:%M:%S')} ===\n\n")
    f.write(f"KEPT ENABLED ({len(skipped_keep)}):\n")
    for n in skipped_keep:
        f.write(f"  - {n}\n")
    f.write(f"\nDISABLED ({len(disabled)}):\n")
    for n in disabled:
        f.write(f"  - {n}\n")
    if errors:
        f.write(f"\nERRORS ({len(errors)}):\n")
        for n, e in errors:
            f.write(f"  - {n}: {e}\n")
    f.write(f"\nTo re-enable any: schtasks /Change /TN \"\\TrendMaster <NAME>\" /ENABLE\n")

print(f"Disabled {len(disabled)}, kept {len(skipped_keep)}, errors {len(errors)}")
