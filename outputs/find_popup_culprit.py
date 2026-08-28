"""Find ALL scheduled tasks + processes that could pop terminal windows.

Reports:
1. Every schtask whose "Task To Run" launches python.exe (visible) or cmd.exe
2. Every schtask running every <= 5 min
3. Every cmd.exe / conhost.exe / WindowsTerminal.exe currently running
4. Every pythonw.exe holding open file/socket
"""
import subprocess
import re
import json
import sys
from pathlib import Path

OUT = Path(__file__).parent / "popup_diag_report.txt"

with open(OUT, "w", encoding="utf-8") as out:
    out.write(f"=== Popup-source diagnostic — {__import__('datetime').datetime.now()} ===\n\n")

    # 1. Get ALL schtasks (raw)
    out.write("=" * 60 + "\n")
    out.write("PART 1: schtasks that could pop windows\n")
    out.write("=" * 60 + "\n")
    try:
        r = subprocess.run(["schtasks", "/Query", "/FO", "CSV", "/V"], capture_output=True, text=True, timeout=20)
        lines = r.stdout.splitlines()
        if not lines:
            out.write("  (no schtasks found)\n")
        else:
            header = lines[0].lower()
            # Find column indices
            cols = [c.strip('"') for c in lines[0].split(",")]
            idx_task = next((i for i, c in enumerate(cols) if "taskname" in c.lower()), 0)
            idx_run = next((i for i, c in enumerate(cols) if "task to run" in c.lower()), 8)
            idx_status = next((i for i, c in enumerate(cols) if c.lower() == "status"), 3)
            idx_schedtype = next((i for i, c in enumerate(cols) if "schedule type" in c.lower()), 5)

            popup_risk = []
            for line in lines[1:]:
                # Naive CSV parse (works for schtasks output)
                parts = [p.strip('"') for p in line.split('","')]
                if len(parts) < max(idx_task, idx_run, idx_status, idx_schedtype) + 1:
                    continue
                task = parts[idx_task] if idx_task < len(parts) else ""
                run = parts[idx_run] if idx_run < len(parts) else ""
                status = parts[idx_status] if idx_status < len(parts) else ""
                schedtype = parts[idx_schedtype] if idx_schedtype < len(parts) else ""

                if status.lower() not in ("ready", "running"):
                    continue
                run_lower = run.lower()
                # Identify popup risk:
                # 1. Uses python.exe (visible) — but only if not pythonw
                # 2. Uses cmd.exe directly
                # 3. Uses powershell.exe directly
                # 4. Uses a .cmd or .bat file (which often has /MIN cmd inside)
                risk = None
                if "python.exe" in run_lower and "pythonw.exe" not in run_lower:
                    risk = "python.exe (visible console)"
                elif "cmd.exe" in run_lower and "wscript" not in run_lower:
                    risk = "cmd.exe direct"
                elif "powershell.exe" in run_lower:
                    risk = "powershell.exe direct"
                elif run_lower.endswith(".cmd") or run_lower.endswith(".bat"):
                    risk = ".cmd/.bat may have internal start /MIN"

                if risk:
                    popup_risk.append({
                        "task": task,
                        "run": run,
                        "status": status,
                        "schedule": schedtype,
                        "risk": risk,
                    })

            if popup_risk:
                out.write(f"  Found {len(popup_risk)} potential popup-causing schtasks:\n\n")
                for r in popup_risk:
                    out.write(f"  TASK: {r['task']}\n")
                    out.write(f"    Status:   {r['status']}\n")
                    out.write(f"    Schedule: {r['schedule']}\n")
                    out.write(f"    Run:      {r['run'][:200]}\n")
                    out.write(f"    Risk:     {r['risk']}\n\n")
            else:
                out.write("  No clearly popup-risky schtasks found.\n\n")
    except Exception as e:
        out.write(f"  schtasks query failed: {e}\n\n")

    # 2. Currently running cmd / conhost / WindowsTerminal processes
    out.write("=" * 60 + "\n")
    out.write("PART 2: Currently running terminal-related processes\n")
    out.write("=" * 60 + "\n")
    try:
        import psutil
        terminal_procs = []
        for p in psutil.process_iter(['pid', 'name', 'cmdline', 'create_time']):
            try:
                name = (p.info.get('name') or '').lower()
                if name in ('cmd.exe', 'conhost.exe', 'windowsterminal.exe', 'openconsole.exe', 'wt.exe'):
                    cmd = " ".join(p.info.get('cmdline') or [])
                    import datetime
                    age = (datetime.datetime.now().timestamp() - (p.info.get('create_time') or 0))
                    terminal_procs.append({
                        "pid": p.info['pid'],
                        "name": name,
                        "age_sec": int(age),
                        "cmd": cmd[:200],
                    })
            except Exception:
                pass

        out.write(f"  Found {len(terminal_procs)} terminal processes:\n\n")
        for tp in sorted(terminal_procs, key=lambda x: x['age_sec']):
            out.write(f"  PID {tp['pid']:>6} | {tp['name']:<22} | age={tp['age_sec']:>6}s | {tp['cmd']}\n")
        out.write("\n")
    except Exception as e:
        out.write(f"  psutil query failed: {e}\n\n")

    # 3. Currently running TrendMaster python(w) processes
    out.write("=" * 60 + "\n")
    out.write("PART 3: TrendMaster-related python(w) processes\n")
    out.write("=" * 60 + "\n")
    try:
        import psutil
        py_procs = []
        for p in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                name = (p.info.get('name') or '').lower()
                if name in ('python.exe', 'pythonw.exe'):
                    cmd = " ".join(p.info.get('cmdline') or [])
                    if 'trendmaster' in cmd.lower() or 'autmated' in cmd.lower() or 'ai_trading' in cmd.lower() or 'health_watchdog' in cmd.lower() or 'tv_webhook' in cmd.lower() or 'python_signal_executor' in cmd.lower() or 'telegram_direction' in cmd.lower() or 'trailing_stop' in cmd.lower():
                        py_procs.append({
                            "pid": p.info['pid'],
                            "name": name,
                            "cmd": cmd[:200],
                        })
            except Exception:
                pass
        out.write(f"  Found {len(py_procs)} TrendMaster python processes:\n\n")
        for pp in py_procs:
            out.write(f"  PID {pp['pid']:>6} | {pp['name']:<14} | {pp['cmd']}\n")
        out.write("\n")
    except Exception as e:
        out.write(f"  psutil query failed: {e}\n\n")

print(f"Wrote diagnostic to {OUT}")
