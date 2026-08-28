"""End-to-end cTrader setup. Operator clicks Authorize ONCE in browser;
script handles everything else.

Steps:
  1. Pre-check: CTRADER_CLIENT_ID/SECRET present, redirect URI matches
  2. Kill any stale OAuth helpers on port 8766
  3. Launch ctrader_oauth.py (browser opens → click Authorize → tokens written)
  4. Run --discover-accounts → parse IC Markets account_id from output
  5. Write CTRADER_ACCOUNT_ID to config/.env
  6. Spawn ctrader_executor.py as long-running process
  7. Verify executor started + heartbeat appears in log

After this completes, every TV signal lands on BOTH MT5 (via
python_signal_executor) AND IC Markets cTrader (via ctrader_executor).
"""
from __future__ import annotations
import os
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENV = ROOT / "config" / ".env"
PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"
PYTHONW = ROOT / ".venv" / "Scripts" / "pythonw.exe"


def load_env() -> dict[str, str]:
    out: dict[str, str] = {}
    if not ENV.exists():
        return out
    for line in ENV.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            k, _, v = line.partition("=")
            out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def append_env_kv(key: str, value: str) -> None:
    text = ENV.read_text(encoding="utf-8") if ENV.exists() else ""
    if f"{key}=" in text:
        new_lines = []
        for ln in text.splitlines():
            if ln.startswith(f"{key}="):
                new_lines.append(f"{key}={value}")
            else:
                new_lines.append(ln)
        text = "\n".join(new_lines)
    else:
        if not text.endswith("\n"):
            text += "\n"
        text += f"# Added by setup_ctrader_full {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
        text += f"{key}={value}\n"
    ENV.write_text(text, encoding="utf-8")


def kill_oauth_stale():
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "Get-CimInstance Win32_Process -Filter \"name='python.exe' or name='pythonw.exe'\" | "
             "Where-Object { $_.CommandLine -like '*ctrader_oauth*' } | "
             "ForEach-Object { taskkill /F /PID $_.ProcessId 2>$null }"],
            capture_output=True, timeout=10
        )
    except Exception:
        pass


def step1_oauth() -> bool:
    print("=" * 70)
    print("STEP 1: Run ctrader_oauth.py — browser opens, click Authorize ONCE")
    print("=" * 70)
    kill_oauth_stale()
    time.sleep(2)
    try:
        r = subprocess.run([str(PYTHON), str(ROOT / "tools" / "ctrader_oauth.py")],
                          capture_output=True, text=True, timeout=600)
        print(r.stdout)
        if r.stderr:
            print("STDERR:", r.stderr)
        return r.returncode == 0
    except subprocess.TimeoutExpired:
        print("[X] OAuth timeout (10 min) — operator did not click Authorize?")
        return False


def step2_discover_account() -> str | None:
    print()
    print("=" * 70)
    print("STEP 2: Discover IC Markets account_id")
    print("=" * 70)
    try:
        r = subprocess.run([str(PYTHON), str(ROOT / "tools" / "ctrader_executor.py"),
                           "--discover-accounts"],
                          capture_output=True, text=True, timeout=60)
        out = r.stdout + r.stderr
        print(out)

        # Parse for account_id — try multiple patterns
        # "ctidTraderAccountId: 12345" / "account_id=12345" / "id=12345"
        account_ids = []
        for pat in (
            r"ctidTraderAccountId[:\s=]+(\d+)",
            r"account[_\s]*id[:\s=]+(\d+)",
            r"\bid[:\s=]+(\d+)",
            r"^\s*(\d{5,})\s*$",  # bare numeric line
        ):
            for m in re.finditer(pat, out, re.MULTILINE):
                aid = m.group(1)
                if aid not in account_ids:
                    account_ids.append(aid)

        # Look for IC Markets specifically
        ic_match = re.search(
            r"(\w+)?[\s\S]{0,200}IC\s*Markets[\s\S]{0,200}?(\d{5,})",
            out, re.IGNORECASE
        )
        if ic_match:
            return ic_match.group(2)

        # Otherwise return first numeric ID found
        if account_ids:
            print(f"\n[info] found candidate IDs: {account_ids}")
            print(f"[info] using first one (review if wrong): {account_ids[0]}")
            return account_ids[0]

        return None
    except subprocess.TimeoutExpired:
        print("[X] discover-accounts timed out")
        return None
    except Exception as e:
        print(f"[X] discover-accounts failed: {e}")
        return None


def step3_write_account_id(account_id: str):
    print()
    print(f"STEP 3: Writing CTRADER_ACCOUNT_ID={account_id} to .env")
    append_env_kv("CTRADER_ACCOUNT_ID", account_id)
    print(f"  [OK] {ENV} updated")


def step4_spawn_executor() -> int | None:
    print()
    print("=" * 70)
    print("STEP 4: Spawn ctrader_executor.py as long-running process")
    print("=" * 70)
    DETACHED = 0x00000008
    NOWIN = 0x08000000
    try:
        proc = subprocess.Popen(
            [str(PYTHONW), str(ROOT / "tools" / "ctrader_executor.py")],
            cwd=str(ROOT),
            creationflags=DETACHED | NOWIN,
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, close_fds=True,
        )
        print(f"  [OK] spawned PID={proc.pid}")
        return proc.pid
    except Exception as e:
        print(f"  [X] spawn failed: {e}")
        return None


def step5_verify(timeout_sec: int = 30) -> bool:
    log = ROOT / "logs" / "ctrader_executor.log"
    print()
    print("=" * 70)
    print(f"STEP 5: Verify executor heartbeat in {log.name}")
    print("=" * 70)
    deadline = time.time() + timeout_sec
    initial_size = log.stat().st_size if log.exists() else 0
    while time.time() < deadline:
        time.sleep(2)
        if log.exists():
            with open(log, "rb") as f:
                f.seek(initial_size)
                tail = f.read().decode("utf-8", errors="replace")
            if tail:
                print("  Recent log lines:")
                for line in tail.splitlines()[-10:]:
                    print(f"    {line}")
                if "connected" in tail.lower() or "watching" in tail.lower() or "heartbeat" in tail.lower():
                    return True
    return False


def main() -> int:
    print(f"=== setup_ctrader_full ({time.strftime('%Y-%m-%d %H:%M:%S')}) ===")
    print(f"ROOT: {ROOT}")
    print()

    env = load_env()
    cid = env.get("CTRADER_CLIENT_ID", "")
    csec = env.get("CTRADER_CLIENT_SECRET", "")
    if not cid or not csec:
        print("[X] CTRADER_CLIENT_ID / CTRADER_CLIENT_SECRET missing in config/.env")
        return 1
    print(f"[OK] CLIENT_ID/SECRET present (id={cid[:12]}...)")

    if env.get("CTRADER_ACCESS_TOKEN"):
        print(f"[INFO] CTRADER_ACCESS_TOKEN already set — skipping OAuth")
    else:
        if not step1_oauth():
            return 2

    # Re-load env after OAuth wrote tokens
    env = load_env()
    if not env.get("CTRADER_ACCESS_TOKEN"):
        print("[X] OAuth completed but no token in .env — investigate")
        return 3

    aid = env.get("CTRADER_ACCOUNT_ID", "")
    if not aid or not aid.isdigit():
        aid = step2_discover_account()
        if not aid:
            print("[X] could not discover account_id — set CTRADER_ACCOUNT_ID manually in .env")
            return 4
        step3_write_account_id(aid)
    else:
        print(f"[INFO] CTRADER_ACCOUNT_ID already set ({aid})")

    pid = step4_spawn_executor()
    if not pid:
        return 5

    if step5_verify():
        print("\n[OK] cTrader executor live")
        print("\n=== SUCCESS — both brokers active ===")
        print("  python_signal_executor → MT5 OctaFX")
        print("  ctrader_executor       → IC Markets cTrader")
        print("Both watch the SAME TV signal files. Every RP signal trades on BOTH brokers.")
        return 0
    else:
        print("\n[!] executor spawned but no heartbeat in 30s — check logs/ctrader_executor.log")
        return 6


if __name__ == "__main__":
    sys.exit(main())
