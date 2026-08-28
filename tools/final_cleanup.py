"""Final cleanup: keep only the LISTENING dashboard, kill non-listening dups."""
from __future__ import annotations
import sys
import time
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import psutil

DASH_PORT = 8765
WEB_PORT = 5005


def find(needle):
    out = []
    for p in psutil.process_iter(["pid", "name", "cmdline", "create_time"]):
        try:
            cmd = " ".join(p.info.get("cmdline") or [])
            if needle in cmd:
                out.append((p.info["pid"], p.info["create_time"]))
        except Exception:
            pass
    return out


def listening_pid(port):
    for c in psutil.net_connections(kind="tcp"):
        if c.laddr and c.laddr.port == port and c.status == "LISTEN":
            return c.pid
    return None


def main():
    print("=== Cleanup zombie singleton scripts ===\n", flush=True)

    # 1. Dashboard: keep only the one bound to 8765
    dash_serve = listening_pid(DASH_PORT)
    print(f"Dashboard listening on :{DASH_PORT} = pid {dash_serve}", flush=True)
    dash_pids = find("dashboard_server")
    print(f"  total dashboard processes: {len(dash_pids)} {[p[0] for p in dash_pids]}", flush=True)
    killed = 0
    for pid, _ in dash_pids:
        if pid == dash_serve:
            continue
        try:
            psutil.Process(pid).kill()
            killed += 1
        except Exception:
            pass
    print(f"  killed {killed} non-serving dashboards\n", flush=True)

    # 2. Executor: keep oldest (the one with the file lock)
    for label, needle in [("python_signal_executor", "python_signal_executor"),
                          ("trailing_stop_manager", "trailing_stop_manager")]:
        procs = find(needle)
        procs.sort(key=lambda r: r[1])  # oldest first
        if not procs:
            print(f"{label}: none\n", flush=True)
            continue
        keeper = procs[0][0]
        print(f"{label}: {len(procs)} procs, keep oldest pid={keeper}", flush=True)
        n = 0
        for pid, _ in procs[1:]:
            try:
                psutil.Process(pid).kill()
                n += 1
            except Exception:
                pass
        print(f"  killed {n} dups\n", flush=True)

    time.sleep(2)

    print("=== Post-cleanup ===\n", flush=True)
    for label, needle in [("dashboard", "dashboard_server"),
                          ("executor", "python_signal_executor"),
                          ("trailing", "trailing_stop_manager"),
                          ("webhook",  "tv_webhook_receiver")]:
        ps = find(needle)
        n = len(ps)
        tag = "OK" if n == 1 else (f"OK ({n})" if n > 0 else "DOWN")
        if needle == "tv_webhook_receiver" and n > 1:
            tag = f"OK ({n} — webhook is multi-thread, OK)"
        print(f"  {label:12} : {tag}  pids={[p[0] for p in ps]}", flush=True)

    print(f"\n  port {DASH_PORT} listener: pid {listening_pid(DASH_PORT)}", flush=True)
    print(f"  port {WEB_PORT}  listener: pid {listening_pid(WEB_PORT)}", flush=True)


if __name__ == "__main__":
    sys.exit(main() or 0)
