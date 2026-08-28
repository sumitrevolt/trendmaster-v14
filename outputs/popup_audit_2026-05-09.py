"""Comprehensive popup audit — finds every schtask, startup, run-key, or
service that touches this project AND would pop a console window.

Output: outputs/popup_audit_2026-05-09.json + readable summary on stdout.

Classification:
  SILENT_VBS   — wscript .vbs (no console window, ever)
  SILENT_PYW   — pythonw.exe (no console window)
  SILENT_PS    — powershell -WindowStyle Hidden
  POPUP_PY     — python.exe directly (window pops)
  POPUP_CMD    — cmd.exe / *.cmd (window pops)
  POPUP_PS     — powershell.exe without Hidden (window pops)
  OTHER        — non-popup tools (taskkill, robocopy, etc.)
"""
import csv, json, os, subprocess, sys, time
from pathlib import Path

ROOT = Path(r"C:\Users\Ratanshila\Documents\autmated trading")
OUT_JSON = ROOT / "outputs" / "popup_audit_2026-05-09.json"
SCHTASKS_CSV = ROOT / "logs" / "schtasks_audit_2026-05-09.csv"
PROJECT_KEY = "autmated trading"


def classify(action: str) -> str:
    a = (action or "").lower()
    if "wscript" in a or ".vbs" in a:
        return "SILENT_VBS"
    if "pythonw.exe" in a:
        return "SILENT_PYW"
    if "powershell" in a and "-windowstyle hidden" in a:
        return "SILENT_PS"
    if "python.exe" in a:
        return "POPUP_PY"
    if "cmd.exe" in a or ".cmd" in a or "cmd /" in a:
        return "POPUP_CMD"
    if "powershell" in a:
        return "POPUP_PS"
    return "OTHER"


def main():
    # Refresh schtasks dump
    print(">> dumping schtasks ...")
    r = subprocess.run(["schtasks", "/Query", "/FO", "CSV", "/V"], capture_output=True, text=True)
    SCHTASKS_CSV.write_text(r.stdout, encoding="utf-8")

    rows = list(csv.DictReader(open(SCHTASKS_CSV, encoding="utf-8")))
    seen = set()
    project_tasks = []
    for r in rows:
        tn = r.get("TaskName") or ""
        if tn in seen:
            continue
        action = r.get("Task To Run") or ""
        startin = r.get("Start In") or ""
        haystack = (action + " " + startin + " " + tn).lower()
        if PROJECT_KEY in haystack or "trendmaster" in tn.lower() or "openclaw" in tn.lower() or "ngrok" in tn.lower() or "tv-bot" in tn.lower():
            seen.add(tn)
            project_tasks.append({
                "name": tn,
                "status": r.get("Status"),
                "next_run": r.get("Next Run Time"),
                "last_run": r.get("Last Run Time"),
                "action": action,
                "start_in": startin,
                "kind": classify(action),
                "logon_mode": r.get("Logon Mode"),
                "scheduled_state": r.get("Scheduled Task State"),
            })

    # Also enumerate Run / RunOnce registry keys via reg.exe
    print(">> dumping HKCU Run / RunOnce ...")
    run_keys = []
    for hive in ("HKCU", "HKLM"):
        for sub in (r"\SOFTWARE\Microsoft\Windows\CurrentVersion\Run",
                    r"\SOFTWARE\Microsoft\Windows\CurrentVersion\RunOnce"):
            r = subprocess.run(["reg", "query", hive + sub], capture_output=True, text=True)
            for ln in r.stdout.splitlines():
                ln = ln.strip()
                if not ln or ln.startswith("HKEY_") or ln.startswith("End of"):
                    continue
                # format: name TYPE  value  -> split on tabs/multispace
                parts = [p for p in ln.split("    ") if p]
                if len(parts) >= 3:
                    name, tp, val = parts[0].strip(), parts[1].strip(), "    ".join(parts[2:]).strip()
                    if PROJECT_KEY in val.lower() or "trendmaster" in val.lower() or "openclaw" in val.lower() or "ngrok" in val.lower():
                        run_keys.append({"hive": hive, "subkey": sub, "name": name, "type": tp, "value": val, "kind": classify(val)})

    # Startup folder
    print(">> scanning Startup folder ...")
    startup_dir = Path(os.path.expandvars(r"%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"))
    startup_files = []
    if startup_dir.is_dir():
        for f in startup_dir.iterdir():
            if PROJECT_KEY in str(f).lower() or "trendmaster" in str(f).lower() or "openclaw" in str(f).lower():
                startup_files.append({"path": str(f), "kind": classify(str(f))})
            else:
                # generic — include only if file extension is .lnk/.cmd/.bat/.vbs
                if f.suffix.lower() in (".lnk", ".cmd", ".bat", ".vbs"):
                    startup_files.append({"path": str(f), "kind": classify(str(f)), "note": "generic"})

    summary = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "schtasks_count": len(project_tasks),
        "schtasks_by_kind": {},
        "schtasks": project_tasks,
        "run_keys": run_keys,
        "startup_files": startup_files,
    }
    for t in project_tasks:
        summary["schtasks_by_kind"].setdefault(t["kind"], 0)
        summary["schtasks_by_kind"][t["kind"]] += 1

    OUT_JSON.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print()
    print("=" * 80)
    print(f"PROJECT-RELATED SCHTASKS: {len(project_tasks)}")
    print("=" * 80)
    print()
    print(f"  {'KIND':<14} {'STATE':<10} {'LAST_RUN':<22} TASK_NAME")
    print(f"  {'-'*14} {'-'*10} {'-'*22} {'-'*40}")
    for t in sorted(project_tasks, key=lambda x: (x["kind"], x["name"])):
        st = (t.get("scheduled_state") or "")[:8]
        last = (t.get("last_run") or "")[:19]
        print(f"  {t['kind']:<14} {st:<10} {last:<22} {t['name']}")
    print()
    print("=" * 80)
    print("BY KIND")
    print("=" * 80)
    for k, v in sorted(summary["schtasks_by_kind"].items()):
        marker = " <-- POPUP RISK" if k.startswith("POPUP") else ""
        print(f"  {k:<14} {v}{marker}")
    print()
    if run_keys:
        print(f"REGISTRY RUN KEYS ({len(run_keys)}):")
        for k in run_keys:
            print(f"  [{k['kind']}] {k['hive']}\\...\\{k['name']} = {k['value'][:90]}")
    if startup_files:
        print(f"STARTUP FOLDER ({len(startup_files)}):")
        for f in startup_files:
            print(f"  [{f['kind']}] {f['path']}")
    print()
    print(f"Full report: {OUT_JSON}")


if __name__ == "__main__":
    main()
