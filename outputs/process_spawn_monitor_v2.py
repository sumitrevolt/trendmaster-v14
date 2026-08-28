"""V2: Watch ALL process spawns for 4 minutes — wider net to find any popup.

This catches anything new appearing in process list, regardless of name.
Filters out clearly benign noise (svchost, RuntimeBroker, etc.) to focus
on user-visible candidates.
"""
import psutil
import time
import sys
from pathlib import Path

OUT = Path(__file__).parent / "spawn_monitor_v2.log"

# Background-only processes — silent, don't show windows
BENIGN_PREFIXES = {
    "svchost.exe", "runtimebroker.exe", "searchindexer.exe", "searchprotocolhost.exe",
    "csrss.exe", "smss.exe", "wininit.exe", "lsass.exe", "services.exe",
    "audiodg.exe", "dllhost.exe", "fontdrvhost.exe", "mscorsvw.exe",
    "msmpeng.exe", "mpdefendercoreservice.exe", "securityhealthservice.exe",
    "wuauclt.exe", "trustedinstaller.exe", "tiworker.exe", "wmiprvse.exe",
    "ngrok.exe",  # already running, hidden
    "metatrader.exe", "terminal64.exe",  # MT5
    "msedge.exe", "chrome.exe",  # browsers
    "spotify.exe", "discord.exe",
    "explorer.exe", "dwm.exe", "taskhostw.exe", "sihost.exe", "ctfmon.exe",
    "shellexperiencehost.exe", "applicationframehost.exe",
    "phonelink.exe",
    "smartscreen.exe",
    "backgroundtaskhost.exe",
    "startmenuexperiencehost.exe",
}

# Process names that DO show windows or could flash one
WATCH_NAMES = {
    "cmd.exe", "conhost.exe", "openconsole.exe",
    "windowsterminal.exe", "wt.exe",
    "python.exe", "pythonw.exe",
    "powershell.exe", "powershell_ise.exe", "pwsh.exe",
    "wscript.exe", "cscript.exe",
    "taskkill.exe", "tasklist.exe",
    "schtasks.exe",
    "notepad.exe", "calc.exe",
    "explorer.exe",
    "msinfo32.exe",
    "rundll32.exe",
    "regsvr32.exe",
    "control.exe",
    "msiexec.exe",
    "where.exe",
    "ipconfig.exe",
    "net.exe",
    "netsh.exe",
    "telegram.exe",
    "outlook.exe",
}

# 1. Capture baseline
baseline = {}
print("Capturing baseline...")
for p in psutil.process_iter(['pid', 'name', 'create_time', 'cmdline']):
    try:
        baseline[p.info['pid']] = p.info.get('name', '?')
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        pass

duration = 240  # 4 minutes
print(f"Baseline: {len(baseline)} processes")
print(f"Monitoring for {duration}s — logging ALL new spawns to {OUT}")

with open(OUT, "w", encoding="utf-8") as f:
    f.write(f"=== Spawn monitor V2 — start {time.strftime('%H:%M:%S')} ===\n")
    f.write(f"Baseline: {len(baseline)} processes\n\n")

    start = time.time()
    seen = set(baseline.keys())
    count_watched = 0
    count_other = 0
    while time.time() - start < duration:
        time.sleep(0.5)
        for p in psutil.process_iter(['pid', 'name', 'create_time', 'cmdline', 'ppid']):
            try:
                pid = p.info['pid']
                if pid in seen:
                    continue
                seen.add(pid)
                name = (p.info.get('name') or '').lower()
                if name in BENIGN_PREFIXES:
                    continue

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
                marker = "★ WATCH" if name in WATCH_NAMES else "  other"
                line = (
                    f"[+{elapsed:>3}s] {marker} PID={pid} name={name} parent={parent_info}\n"
                    f"           cmd:    {cmd[:180]}\n"
                )
                f.write(line)
                f.flush()
                if name in WATCH_NAMES:
                    count_watched += 1
                else:
                    count_other += 1
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

    f.write(f"\n=== END {time.strftime('%H:%M:%S')} — watched={count_watched}, other={count_other} ===\n")

print(f"Done.")
