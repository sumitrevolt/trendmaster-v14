"""Master autostart — single entry point for laptop-boot AND on-demand.

Brings up the entire trading pipeline IDEMPOTENTLY:
  - tv_webhook_receiver  (port 5005)
  - ngrok tunnel         (shadow-cosmos-unending.ngrok-free.dev → 5005)
  - python_signal_executor (1 instance, has singleton-lock)
  - trailing_stop_manager  (1 instance, has singleton-lock)
  - dashboard_server     (port 8765)

Idempotent: if a component is already running, leave it alone.
Safe to run repeatedly (e.g. via watchdog or after laptop sleep/wake).

Boot launcher path:
    BOOT_AUTO_START_HIDDEN.vbs → wscript /B (hidden) → cmd → this script
"""
from __future__ import annotations
import datetime
import subprocess
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import psutil

ROOT = Path("C:/Users/Ratanshila/Documents/autmated trading")
PYW = ROOT / ".venv/Scripts/pythonw.exe"
NGROK_EXE = Path("C:/Users/Ratanshila/AppData/Local/Microsoft/WinGet/Packages/Ngrok.Ngrok_Microsoft.Winget.Source_8wekyb3d8bbwe/ngrok.exe")
NGROK_DOMAIN = "shadow-cosmos-unending.ngrok-free.dev"
WEBHOOK_PORT = 5005
DASH_PORT = 8765
LOGS = ROOT / "logs"
LOGS.mkdir(exist_ok=True)

DETACHED_PROCESS = 0x00000008
CREATE_NEW_PROCESS_GROUP = 0x00000200
CREATE_NO_WINDOW = 0x08000000
HIDDEN_FLAGS = DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW

LOG = LOGS / "master_autostart.log"


def log(msg: str):
    line = f"[{datetime.datetime.now().isoformat(timespec='seconds')}] {msg}"
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass
    print(line, flush=True)


def find(needle: str):
    pids = []
    for p in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            cmd = " ".join(p.info.get("cmdline") or [])
            if needle in cmd:
                pids.append(p.info["pid"])
        except Exception:
            pass
    return pids


def http_ok(url: str, timeout: float = 4) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.status == 200
    except Exception:
        return False


def launch(args, label, log_out, log_err):
    fout = open(log_out, "ab")
    ferr = open(log_err, "ab")
    try:
        p = subprocess.Popen(
            args, cwd=str(ROOT),
            stdout=fout, stderr=ferr, stdin=subprocess.DEVNULL,
            creationflags=HIDDEN_FLAGS, close_fds=True,
        )
        log(f"  started {label} pid={p.pid}")
        return p.pid
    except Exception as e:
        log(f"  ERROR starting {label}: {e}")
        return None


def ensure_webhook():
    pids = find("tv_webhook_receiver")
    if pids:
        log(f"webhook receiver already running pids={pids}")
        return True
    launch([str(PYW), "-u", "-m", "ai_trading_agents.tv_webhook_receiver"],
           "tv_webhook_receiver",
           LOGS / "tv_webhook.bootstrap.out",
           LOGS / "tv_webhook.bootstrap.err")
    time.sleep(4)
    return http_ok(f"http://127.0.0.1:{WEBHOOK_PORT}/health")


def ensure_ngrok():
    # Match real ngrok.exe by argv (avoid matching our scripts that mention ngrok)
    real = []
    for p in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            name = (p.info.get("name") or "").lower()
            cmd = " ".join(p.info.get("cmdline") or []).lower()
            if name == "ngrok.exe" or ("ngrok.exe" in cmd and "http 5005" in cmd):
                real.append(p.info["pid"])
        except Exception:
            pass
    if real:
        log(f"ngrok already running pids={real}")
        return True
    if not NGROK_EXE.exists():
        log(f"ERROR: ngrok.exe not found at {NGROK_EXE}")
        return False
    launch([str(NGROK_EXE), "http", str(WEBHOOK_PORT),
            f"--domain={NGROK_DOMAIN}", "--log=stdout"],
           "ngrok",
           LOGS / "ngrok.out", LOGS / "ngrok.err")
    time.sleep(5)
    return http_ok(f"https://{NGROK_DOMAIN}/health", timeout=10)


def ensure_dashboard():
    pids = find("dashboard_server")
    if len(pids) == 1 and http_ok(f"http://localhost:{DASH_PORT}/api/status", timeout=6):
        log(f"dashboard healthy pid={pids[0]}")
        return True
    if len(pids) > 1:
        log(f"dashboard had {len(pids)} zombies — killing all and starting one clean")
        for pid in pids:
            try: psutil.Process(pid).kill()
            except Exception: pass
        time.sleep(2)
    launch([str(PYW), str(ROOT / "tools/dashboard_server.py")],
           "dashboard_server",
           LOGS / "dashboard.out", LOGS / "dashboard.err")
    time.sleep(4)
    return http_ok(f"http://localhost:{DASH_PORT}/api/status", timeout=6)


def ensure_executor():
    pids = find("python_signal_executor")
    if pids:
        log(f"executor already running pids={pids}")
        return True
    launch([str(PYW), str(ROOT / "tools/python_signal_executor.py")],
           "python_signal_executor",
           LOGS / "python_signal_executor.out",
           LOGS / "python_signal_executor.err")
    time.sleep(2)
    return bool(find("python_signal_executor"))


def ensure_trailing():
    pids = find("trailing_stop_manager")
    if pids:
        log(f"trailing already running pids={pids}")
        return True
    launch([str(PYW), str(ROOT / "tools/trailing_stop_manager.py")],
           "trailing_stop_manager",
           LOGS / "trailing_stop_manager.out",
           LOGS / "trailing_stop_manager.err")
    time.sleep(2)
    return bool(find("trailing_stop_manager"))


def main():
    log("=" * 60)
    log("master_autostart starting")
    results = {
        "webhook_receiver": ensure_webhook(),
        "ngrok_tunnel":     ensure_ngrok(),
        "dashboard":        ensure_dashboard(),
        "executor":         ensure_executor(),
        "trailing":         ensure_trailing(),
    }
    log("Final status:")
    for k, v in results.items():
        log(f"  {k:18}: {'OK' if v else 'FAIL'}")
    all_ok = all(results.values())
    log(f"master_autostart {'OK' if all_ok else 'PARTIAL'}")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
