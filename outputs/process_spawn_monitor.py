"""Watch ALL process spawns for 90 sec.
Logs every new process with name + cmdline + parent.
This catches the popup culprit live.
"""
import psutil
import time
import sys
from pathlib import Path

OUT = Path(__file__).parent / "spawn_monitor.log"
WATCH_NAMES = {
    "cmd.exe", "conhost.exe", "openconsole.exe",
    "windowsterminal.exe", "wt.exe",
    "python.exe", "pythonw.exe",
    "powershell.exe", "powershell_ise.exe",
    "wscript.exe", "cscript.exe",
    "taskkill.exe",
}

# 1. Capture baseline
baseline = {}
for p in psutil.process_iter(['pid', 'name', 'create_time', 'cmdline']):
    try:
        name = (p.info.get('name') or '').lower()
        if name in WATCH_NAMES:
            baseline[p.info['pid']] = (name, p.info.get('create_time'), " ".join(p.info.get('cmdline') or []))
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        pass

print(f"Baseline: {len(baseline)} processes watched")
print(f"Monitoring for 90 sec — logging new spawns to {OUT}")

with open(OUT, "w", encoding="utf-8") as f:
    f.write(f"=== Spawn monitor — start {time.strftime('%H:%M:%S')} ===\n")
    f.write(f"Baseline: {len(baseline)} relevant processes\n\n")

    start = time.time()
    seen = set(baseline.keys())
    while time.time() - start < 90:
        time.sleep(0.5)
        for p in psutil.process_iter(['pid', 'name', 'create_time', 'cmdline', 'ppid']):
            try:
                pid = p.info['pid']
                if pid in seen:
                    continue
                name = (p.info.get('name') or '').lower()
                if name not in WATCH_NAMES:
                    continue
                seen.add(pid)

                # Get parent info
                try:
                    parent = psutil.Process(p.info.get('ppid', 0))
                    parent_info = f"{parent.name()} (PID {parent.pid})"
                    try:
                        parent_cmd = " ".join(parent.cmdline()[:3])
                    except Exception:
                        parent_cmd = "?"
                except Exception:
                    parent_info = f"PID {p.info.get('ppid', 0)} (gone)"
                    parent_cmd = "?"

                cmd = " ".join(p.info.get('cmdline') or [])
                elapsed = int(time.time() - start)
                line = (
                    f"[+{elapsed:>2}s] SPAWN PID={pid} name={name} "
                    f"parent={parent_info}\n"
                    f"        cmd:    {cmd[:150]}\n"
                    f"        pcmd:   {parent_cmd[:150]}\n"
                )
                print(line, end="")
                f.write(line)
                f.flush()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

    f.write(f"\n=== END {time.strftime('%H:%M:%S')} — saw {len(seen) - len(baseline)} new spawns ===\n")

print(f"Done. {len(seen) - len(baseline)} new spawns logged.")
