"""Inspect the boot launcher and find what's responsible for autostart."""
from __future__ import annotations
import os
import subprocess
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = Path("C:/Users/Ratanshila/Documents/autmated trading")
STARTUP = Path.home() / "AppData/Roaming/Microsoft/Windows/Start Menu/Programs/Startup"


def shortcut_target(lnk: Path):
    try:
        import win32com.client
        wsh = win32com.client.Dispatch("WScript.Shell")
        sc = wsh.CreateShortcut(str(lnk))
        return {"target": sc.TargetPath, "args": sc.Arguments,
                "work": sc.WorkingDirectory, "style": sc.WindowStyle}
    except ImportError:
        # fallback: read raw
        return {"target": "<pywin32 not installed>", "raw_size": lnk.stat().st_size}


def main():
    print(f"=== Startup folder: {STARTUP} ===")
    for f in STARTUP.iterdir():
        if f.suffix.lower() == ".lnk":
            info = shortcut_target(f)
            print(f"  {f.name}")
            for k, v in info.items():
                print(f"    {k}: {v}")
        else:
            print(f"  {f.name}  (not a .lnk)")

    print(f"\n=== Boot/start scripts in {ROOT} ===")
    for pat in ("boot*", "start*.cmd", "start*.bat", "*pipeline*.cmd",
                "*autostart*.cmd", "Boot_OpenClaw_Trading*"):
        for f in ROOT.glob(pat):
            print(f"  {f.relative_to(ROOT)}")

    print("\n=== schtasks (TrendMaster/trading/Boot) ===")
    try:
        r = subprocess.run(["schtasks", "/Query", "/FO", "CSV"],
                            capture_output=True, text=True, timeout=10,
                            creationflags=0x08000000)
        for line in r.stdout.splitlines():
            low = line.lower()
            if any(k in low for k in ("trendmaster", "trading", "auto", "boot",
                                       "ngrok", "pipeline", "dashboard", "executor",
                                       "openclaw", "webhook")):
                print(f"  {line[:200]}")
    except Exception as e:
        print(f"  err: {e}")

    print("\n=== Files referenced in Boot_OpenClaw_Trading.lnk target ===")
    lnk = STARTUP / "Boot_OpenClaw_Trading.lnk"
    if lnk.exists():
        info = shortcut_target(lnk)
        target = info.get("target", "")
        if target:
            tp = Path(target)
            if tp.exists() and tp.is_file() and tp.suffix.lower() in (".cmd", ".bat", ".vbs", ".ps1"):
                print(f"  --- {tp} ---")
                try:
                    print(tp.read_text(encoding="utf-8", errors="replace")[:4000])
                except Exception as e:
                    print(f"  read err: {e}")


if __name__ == "__main__":
    main()
