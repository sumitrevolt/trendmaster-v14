"""Diagnose autostart + pipeline health.

Reports:
1. Which key processes are running (dashboard, executor, webhook, brain, trailing, ngrok)
2. Dashboard reachability at http://localhost:8765
3. Schtasks that are supposed to fire at boot/logon
4. Startup folder shortcuts
5. Run-key entries
6. Recent boot time vs last process-start times
"""
from __future__ import annotations
import datetime
import json
import subprocess
import sys
import time
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import psutil
import urllib.request
import urllib.error

ROOT = Path(__file__).resolve().parent.parent
PROCESS_KEYWORDS = {
    "dashboard":          ("dashboard_server",),
    "python_executor":    ("python_signal_executor",),
    "tv_webhook":         ("tv_webhook_receiver", "webhook_receiver"),
    "trailing_stop":      ("trailing_stop_manager",),
    "brain":              ("trend_master_brain",),
    "ngrok":              ("ngrok",),
    "cloudflared":        ("cloudflared",),
    "mt5_terminal":       ("terminal64.exe",),
}

KNOWN_SCHTASKS = [
    "TrendMaster Auto Start",
    "TrendMaster Boot",
    "TrendMaster Boot Pipeline",
    "TrendMaster Trading Bot",
    "TV Webhook Watchdog",
    "TrendMaster Zero Trades Watchdog",
    "TrendMaster EA Parity Nightly",
    "TrendMaster Dashboard",
    "TrendMaster Executor",
    "TrendMaster Pipeline",
]

def find_running():
    found: dict[str, list[tuple[int, float, str]]] = {k: [] for k in PROCESS_KEYWORDS}
    for p in psutil.process_iter(["pid", "name", "cmdline", "create_time"]):
        try:
            cmd = " ".join(p.info.get("cmdline") or [])
            for label, keywords in PROCESS_KEYWORDS.items():
                if any(k in cmd for k in keywords):
                    found[label].append((p.info["pid"], p.info["create_time"], cmd[:160]))
        except Exception:
            continue
    return found


def boot_time():
    return datetime.datetime.fromtimestamp(psutil.boot_time())


def reach_dashboard():
    try:
        with urllib.request.urlopen("http://localhost:8765/api/status", timeout=4) as r:
            return r.status, len(r.read())
    except urllib.error.URLError as e:
        return None, str(e)
    except Exception as e:
        return None, str(e)


def schtasks_query():
    found = []
    for name in KNOWN_SCHTASKS:
        try:
            r = subprocess.run(
                ["schtasks", "/Query", "/TN", name, "/V", "/FO", "LIST"],
                capture_output=True, text=True, timeout=5,
                creationflags=0x08000000,
            )
            if r.returncode == 0:
                # parse Status, Last Run Time, Next Run Time, Last Result
                info = {"name": name}
                for line in r.stdout.splitlines():
                    line = line.strip()
                    for k_label, k_match in (("status", "Status:"),
                                              ("last_run", "Last Run Time:"),
                                              ("next_run", "Next Run Time:"),
                                              ("last_result", "Last Result:")):
                        if line.startswith(k_match):
                            info[k_label] = line.split(":", 1)[1].strip()
                found.append(info)
            else:
                found.append({"name": name, "missing": True})
        except Exception as e:
            found.append({"name": name, "error": str(e)})
    return found


def startup_folder_items():
    user_startup = Path.home() / "AppData" / "Roaming" / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
    common_startup = Path("C:/ProgramData/Microsoft/Windows/Start Menu/Programs/StartUp")
    items = []
    for d in (user_startup, common_startup):
        if d.exists():
            for f in d.iterdir():
                items.append(str(f))
    return items


def run_keys():
    """Read HKCU and HKLM Run keys."""
    out = []
    try:
        import winreg
        for hive, path in [
            (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run"),
            (winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\Run"),
        ]:
            try:
                with winreg.OpenKey(hive, path) as k:
                    i = 0
                    while True:
                        try:
                            name, val, _ = winreg.EnumValue(k, i)
                            out.append({"hive": "HKCU" if hive == winreg.HKEY_CURRENT_USER else "HKLM",
                                        "name": name, "value": val})
                            i += 1
                        except OSError:
                            break
            except FileNotFoundError:
                continue
    except Exception as e:
        out.append({"error": str(e)})
    return out


def main():
    bt = boot_time()
    print(f"Boot time:    {bt}")
    print(f"Now:          {datetime.datetime.now()}")
    print(f"Uptime:       {datetime.datetime.now() - bt}")
    print()

    print("=== Process status ===")
    found = find_running()
    for label, procs in found.items():
        if procs:
            for pid, ct, cmd in procs:
                start = datetime.datetime.fromtimestamp(ct)
                age = datetime.datetime.now() - start
                # tag if started near boot vs after
                tag = "BOOT" if (start - bt).total_seconds() < 180 else "MANUAL"
                print(f"  [OK]   {label:18} pid={pid:<7} started {start.strftime('%Y-%m-%d %H:%M:%S')} ({age}) {tag}")
        else:
            print(f"  [DOWN] {label:18}")
    print()

    print("=== Dashboard reachability (http://localhost:8765/api/status) ===")
    status, info = reach_dashboard()
    if status == 200:
        print(f"  [OK]   HTTP 200, body={info} bytes")
    else:
        print(f"  [DOWN] {info}")
    print()

    print("=== Schtasks (autostart candidates) ===")
    for t in schtasks_query():
        if t.get("missing"):
            continue
        if t.get("error"):
            print(f"  [ERR]  {t['name']}: {t['error']}")
            continue
        print(f"  {t['name']}")
        print(f"    status:      {t.get('status')}")
        print(f"    last_run:    {t.get('last_run')}")
        print(f"    last_result: {t.get('last_result')}")
        print(f"    next_run:    {t.get('next_run')}")
    missing = [t['name'] for t in schtasks_query() if t.get('missing')]
    if missing:
        print(f"  [MISSING] {', '.join(missing)}")
    print()

    print("=== Startup folder shortcuts ===")
    for s in startup_folder_items():
        print(f"  {s}")
    if not startup_folder_items():
        print("  (none)")
    print()

    print("=== Registry Run keys ===")
    for r in run_keys():
        print(f"  {r}")


if __name__ == "__main__":
    sys.exit(main() or 0)
