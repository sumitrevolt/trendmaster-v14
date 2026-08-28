"""IMMEDIATE TRIAGE: restore pipeline that didn't autostart properly.

1. Kill all dashboard_server zombies (8 competing for port 8765 → all hung)
2. Start ONE clean dashboard via pythonw
3. Start ngrok tunnel (so TV signals can reach our webhook)
4. Start brain (shadow learner) — only if not already running
5. Verify each component
"""
from __future__ import annotations
import os
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
PY  = ROOT / ".venv/Scripts/python.exe"
DASH = ROOT / "tools/dashboard_server.py"
NGROK_EXE = Path("C:/Users/Ratanshila/AppData/Local/Microsoft/WinGet/Packages/Ngrok.Ngrok_Microsoft.Winget.Source_8wekyb3d8bbwe/ngrok.exe")
NGROK_DOMAIN = "shadow-cosmos-unending.ngrok-free.dev"
WEBHOOK_PORT = 5005
DASH_PORT = 8765

DETACHED_PROCESS = 0x00000008
CREATE_NEW_PROCESS_GROUP = 0x00000200
CREATE_NO_WINDOW = 0x08000000
HIDDEN_FLAGS = DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW


def find_by_cmd(needles: list[str]):
    pids = []
    for p in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            cmd = " ".join(p.info.get("cmdline") or [])
            if any(n in cmd for n in needles):
                pids.append((p.info["pid"], cmd[:120]))
        except Exception:
            continue
    return pids


def kill_pids(pids: list[int], label: str):
    n = 0
    for pid in pids:
        try:
            psutil.Process(pid).kill()
            n += 1
        except Exception:
            pass
    print(f"  killed {n}/{len(pids)} {label}", flush=True)
    return n


def start_detached(args: list[str], log_out: Path, log_err: Path, label: str) -> int | None:
    log_out.parent.mkdir(exist_ok=True)
    fout = open(log_out, "ab")
    ferr = open(log_err, "ab")
    try:
        p = subprocess.Popen(
            args, cwd=str(ROOT),
            stdout=fout, stderr=ferr, stdin=subprocess.DEVNULL,
            creationflags=HIDDEN_FLAGS, close_fds=True,
        )
        print(f"  [OK] started {label} pid={p.pid}", flush=True)
        return p.pid
    except Exception as e:
        print(f"  [ERR] could not start {label}: {e}", flush=True)
        return None


def http_check(url: str, timeout: float = 4) -> tuple[bool, str]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            body = r.read()[:200].decode("utf-8", errors="replace")
            return r.status == 200, f"HTTP {r.status} body[:200]={body}"
    except urllib.error.URLError as e:
        return False, f"URLError: {e}"
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


def main():
    print("=" * 70, flush=True)
    print("Step 1: Kill all dashboard zombies", flush=True)
    dash_procs = find_by_cmd(["dashboard_server"])
    print(f"  found {len(dash_procs)} dashboard processes", flush=True)
    kill_pids([p[0] for p in dash_procs], "dashboard")
    time.sleep(2)

    print("\nStep 2: Verify nothing on port 8765 (release the bind)", flush=True)
    # Kill anything LISTENING on 8765
    for c in psutil.net_connections(kind="tcp"):
        if c.laddr and c.laddr.port == DASH_PORT and c.status == "LISTEN":
            try:
                psutil.Process(c.pid).kill()
                print(f"  killed port-{DASH_PORT} listener pid={c.pid}", flush=True)
            except Exception:
                pass
    time.sleep(1)

    print("\nStep 3: Start ONE clean dashboard", flush=True)
    log_dir = ROOT / "logs"
    start_detached(
        [str(PYW), str(DASH)],
        log_dir / "dashboard.out", log_dir / "dashboard.err",
        "dashboard_server",
    )
    time.sleep(3)
    ok, info = http_check(f"http://localhost:{DASH_PORT}/api/status", timeout=8)
    print(f"  health: {'OK' if ok else 'DOWN'} — {info[:200]}", flush=True)

    print("\nStep 4: Check + start ngrok", flush=True)
    ngrok_procs = find_by_cmd(["ngrok"])
    real_ngrok = [p for p in ngrok_procs if "ngrok" in p[1].lower() and "ngrok-free" in p[1].lower() or "ngrok.exe" in p[1].lower()]
    if real_ngrok:
        print(f"  ngrok already running (pids {[p[0] for p in real_ngrok]})", flush=True)
    elif not NGROK_EXE.exists():
        print(f"  [ERR] ngrok.exe not at {NGROK_EXE}", flush=True)
    else:
        start_detached(
            [str(NGROK_EXE), "http", str(WEBHOOK_PORT),
             f"--domain={NGROK_DOMAIN}", "--log=stdout"],
            log_dir / "ngrok.out", log_dir / "ngrok.err",
            "ngrok",
        )
        time.sleep(5)
    ok, info = http_check(f"https://{NGROK_DOMAIN}/health", timeout=10)
    print(f"  public webhook health: {'OK' if ok else 'DOWN'} — {info[:200]}", flush=True)

    print("\nStep 5: Verify webhook receiver on :5005", flush=True)
    ok, info = http_check(f"http://127.0.0.1:{WEBHOOK_PORT}/health", timeout=4)
    print(f"  local webhook: {'OK' if ok else 'DOWN'} — {info[:200]}", flush=True)
    if not ok:
        print("  [WARN] webhook receiver not responding — restarting", flush=True)
        # kill any stale receiver
        recv = find_by_cmd(["tv_webhook_receiver"])
        kill_pids([p[0] for p in recv], "tv_webhook_receiver")
        time.sleep(1)
        start_detached(
            [str(PYW), "-u", "-m", "ai_trading_agents.tv_webhook_receiver"],
            log_dir / "tv_webhook.bootstrap.out",
            log_dir / "tv_webhook.bootstrap.err",
            "tv_webhook_receiver",
        )
        time.sleep(4)
        ok, info = http_check(f"http://127.0.0.1:{WEBHOOK_PORT}/health", timeout=4)
        print(f"  local webhook (after restart): {'OK' if ok else 'DOWN'} — {info[:200]}", flush=True)

    print("\nStep 6: Check brain", flush=True)
    brain_procs = find_by_cmd(["trend_master_brain"])
    if brain_procs:
        print(f"  brain already running (pids {[p[0] for p in brain_procs]})", flush=True)
    else:
        print("  brain DOWN — leaving stopped (operator decides whether to restart;", flush=True)
        print("  it's only a shadow learner under TV-signal mode)", flush=True)

    print("\nStep 7: Final pipeline summary", flush=True)
    pieces = {
        "dashboard": ("dashboard_server",),
        "ngrok":     ("ngrok",),
        "tv_webhook":("tv_webhook_receiver",),
        "executor":  ("python_signal_executor",),
        "trailing":  ("trailing_stop_manager",),
        "brain":     ("trend_master_brain",),
    }
    for label, needles in pieces.items():
        ps = find_by_cmd(list(needles))
        # skip ngrok matches that aren't really ngrok.exe — already handled above
        if label == "ngrok":
            ps = [p for p in ps if "ngrok.exe" in p[1].lower() or "ngrok-free" in p[1].lower()]
        status = f"OK ({len(ps)})" if ps else "DOWN"
        print(f"  {label:12} : {status}", flush=True)

    print("=" * 70, flush=True)
    print("Done. Open dashboard at http://localhost:8765", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
