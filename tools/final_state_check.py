"""End-to-end pipeline health snapshot."""
from __future__ import annotations
import datetime
import sys
import urllib.request
import urllib.error
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import psutil


def find(needle):
    pids = []
    for p in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            cmd = " ".join(p.info.get("cmdline") or [])
            if needle in cmd:
                pids.append(p.info["pid"])
        except Exception:
            pass
    return pids


def http_check(url, timeout=4):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            body = r.read()[:200].decode("utf-8", errors="replace")
            return r.status, body
    except Exception as e:
        return None, str(e)


def main():
    print(f"=== Pipeline state @ {datetime.datetime.now().isoformat(timespec='seconds')} ===\n")
    components = [
        ("dashboard",        "dashboard_server"),
        ("python_executor",  "python_signal_executor"),
        ("trailing_manager", "trailing_stop_manager"),
        ("tv_webhook",       "tv_webhook_receiver"),
    ]
    for label, needle in components:
        pids = find(needle)
        n = len(pids)
        status = f"OK ({n} instance{'s' if n > 1 else ''}: {pids})" if pids else "DOWN"
        print(f"  {label:18} : {status}")

    # ngrok by exe name
    ngrok = []
    for p in psutil.process_iter(["pid", "name"]):
        try:
            if (p.info.get("name") or "").lower() == "ngrok.exe":
                ngrok.append(p.info["pid"])
        except Exception:
            pass
    print(f"  {'ngrok':18} : {'OK ('+str(ngrok)+')' if ngrok else 'DOWN'}")

    print("\n=== HTTP health ===")
    for label, url in [
        ("dashboard /api/status",  "http://localhost:8765/api/status"),
        ("local webhook /health",   "http://127.0.0.1:5005/health"),
        ("public webhook /health",  "https://shadow-cosmos-unending.ngrok-free.dev/health"),
    ]:
        st, body = http_check(url, timeout=8)
        if st == 200:
            print(f"  [OK]   {label}: HTTP {st}")
            print(f"         body: {body[:160]}")
        else:
            print(f"  [DOWN] {label}: {body}")


if __name__ == "__main__":
    sys.exit(main() or 0)
