"""TradingView webhook receiver watchdog.

Solves the May-1 -> May-4 silent-3-day-death incident: the receiver and
cloudflared both died on 2026-05-01 and nobody noticed for 72h. A real
NZDJPY signal got dropped during that window. This watchdog runs every
5 minutes via Task Scheduler and:

    1. Hits http://127.0.0.1:5005/health      (receiver alive?)
    2. Confirms cloudflared.exe in tasklist   (tunnel process alive?)
    3. Scrapes a recent trycloudflare URL out of cloudflared.err
       and hits its /health                   (tunnel actually routing?)
    4. (Optional, market-hours only) Confirms tv_signals.jsonl has
       grown in the last `quiet_threshold_min` minutes — silent during
       active hours = TV alerts misconfigured.

On any failure it:
    a) Tries one auto-restart via start_tv_webhook.cmd
    b) Posts a Telegram alert (one-shot, deduped via a state file so we
       don't spam during a long outage)

Verdicts (exit codes):
    OK            (0)  - everything green
    AUTO_HEALED   (0)  - found dead, restarted, now green
    DEGRADED      (1)  - found dead, restart failed, alert sent
    SILENT_HOURS  (1)  - process up but no signals during market hours
    SECRET_MISSING(2)  - TV_WEBHOOK_SECRET not configured (refuses to run)

Usage
-----
    .venv\\Scripts\\python.exe tools\\tv_webhook_watchdog.py
    .venv\\Scripts\\python.exe tools\\tv_webhook_watchdog.py --no-restart   # alert only

Scheduled via tools\\install_tv_webhook_watchdog.cmd (every 5 min).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

LOGS = REPO_ROOT / "logs"
TV_LOG = LOGS / "tv_webhook.log"
TV_SIGNALS = LOGS / "tv_signals.jsonl"
CLOUDFLARED_ERR = LOGS / "cloudflared.err"
WATCHDOG_STATE = LOGS / "tv_webhook_watchdog_state.json"
LAUNCHER = REPO_ROOT / "start_tv_webhook.cmd"

QUIET_THRESHOLD_MIN = 90        # signals expected during market hours
ALERT_DEDUP_S = 1800             # don't re-alert same condition more often than 30 min
MARKET_OPEN_UTC_HOUR = 6         # london open ish
MARKET_CLOSE_UTC_HOUR = 21       # ny close ish


# ───────────────────────── helpers ─────────────────────────
def _load_env() -> None:
    try:
        from dotenv import load_dotenv  # type: ignore
        load_dotenv(REPO_ROOT / "config" / ".env")
    except ImportError:
        pass


def _http_get(url: str, timeout: float = 4.0) -> tuple[int, str]:
    try:
        r = urllib.request.urlopen(url, timeout=timeout)
        return r.status, r.read().decode("utf-8", errors="replace")
    except Exception as e:
        return 0, f"<error: {e}>"


def _public_url() -> str | None:
    """Discover public URL based on TUNNEL_MODE.

    quick  -> scrape last trycloudflare.com URL out of cloudflared.err
    named  -> return TV_PUBLIC_URL from env (stable Cloudflare hostname)
    ngrok  -> return TV_PUBLIC_URL, or derive from NGROK_DOMAIN
    none   -> return None (no tunnel expected)
    """
    mode = (os.getenv("TUNNEL_MODE") or "quick").strip().lower()
    if mode in ("named", "ngrok"):
        url = (os.getenv("TV_PUBLIC_URL") or "").strip()
        if url:
            return url.rstrip("/")
        if mode == "ngrok":
            dom = (os.getenv("NGROK_DOMAIN") or "").strip()
            if dom:
                return f"https://{dom}"
        return None
    if mode == "none":
        return None
    # quick (default): scrape from cloudflared err log
    if not CLOUDFLARED_ERR.exists():
        return None
    try:
        text = CLOUDFLARED_ERR.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    m = re.findall(r"https://[a-z0-9\-]+\.trycloudflare\.com", text)
    return m[-1] if m else None


def _tunnel_process_name() -> str:
    """Which binary should be alive based on mode."""
    mode = (os.getenv("TUNNEL_MODE") or "quick").strip().lower()
    if mode == "ngrok":
        return "ngrok.exe"
    if mode == "none":
        return ""  # nothing to check
    return "cloudflared.exe"


def _process_alive(name_substring: str) -> bool:
    """Returns True if any tasklist row's image name matches the substring."""
    try:
        out = subprocess.check_output(
            ["tasklist", "/FO", "CSV", "/NH"],
            stderr=subprocess.DEVNULL,
            timeout=5,
        ).decode("utf-8", errors="replace")
    except Exception:
        return False
    return name_substring.lower() in out.lower()


def _last_signal_age_s() -> float | None:
    if not TV_SIGNALS.exists():
        return None
    try:
        with TV_SIGNALS.open("rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            tail = b""
            chunk = 4096
            pos = max(0, size - chunk)
            f.seek(pos)
            tail = f.read()
        last_line = tail.splitlines()[-1] if tail else b""
        rec = json.loads(last_line.decode("utf-8", errors="replace"))
        return time.time() - float(rec.get("ts", 0))
    except Exception:
        return None


def _market_hours_now() -> bool:
    h = datetime.now(timezone.utc).hour
    dow = datetime.now(timezone.utc).weekday()  # Mon=0 ... Sun=6
    if dow >= 5:  # Sat/Sun — FX closed; crypto trades but coverage gap is fine
        return False
    return MARKET_OPEN_UTC_HOUR <= h < MARKET_CLOSE_UTC_HOUR


def _read_state() -> dict:
    if not WATCHDOG_STATE.exists():
        return {}
    try:
        return json.loads(WATCHDOG_STATE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write_state(s: dict) -> None:
    WATCHDOG_STATE.parent.mkdir(parents=True, exist_ok=True)
    WATCHDOG_STATE.write_text(json.dumps(s, indent=2), encoding="utf-8")


def _send_telegram(title: str, body: str, dedup_key: str) -> bool:
    """One-shot, deduped Telegram alert. Returns False if dedup-suppressed."""
    state = _read_state()
    last = state.get("last_alert", {}).get(dedup_key, 0)
    if time.time() - last < ALERT_DEDUP_S:
        print(f"[telegram] dedup-suppressed ({dedup_key}), last fired {int(time.time() - last)}s ago")
        return False
    try:
        from ai_trading_agents.telegram_notifier import get_notifier  # type: ignore
    except Exception as e:
        print(f"[telegram] import failed: {e}")
        return False
    try:
        get_notifier().notify_alert(title, body, emoji="🚨")
        state.setdefault("last_alert", {})[dedup_key] = time.time()
        _write_state(state)
        return True
    except Exception as e:
        print(f"[telegram] notify_alert failed: {e}")
        return False


def _restart_launcher() -> tuple[bool, str]:
    """Run start_tv_webhook.cmd. Returns (ok, captured_output).

    2026-05-13: added CREATE_NO_WINDOW to suppress conhost flash. Plus
    the .cmd itself was patched to use wscript run_hidden.vbs for nested
    starts (no more visible cmd windows from the launcher).
    """
    if not LAUNCHER.exists():
        return False, f"launcher missing at {LAUNCHER}"
    try:
        proc = subprocess.run(
            ["cmd.exe", "/c", str(LAUNCHER)],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=45,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        out = (proc.stdout or "") + (proc.stderr or "")
        ok = proc.returncode == 0
        return ok, out[-1500:]  # last 1.5k chars enough for diagnosis
    except subprocess.TimeoutExpired:
        return False, "launcher timed out after 45s"
    except Exception as e:
        return False, f"launcher exec failed: {e}"


# ───────────────────────── main ─────────────────────────
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-restart", action="store_true",
                    help="Diagnose only; never run start_tv_webhook.cmd")
    ap.add_argument("--quiet-threshold-min", type=int, default=QUIET_THRESHOLD_MIN,
                    help="Alert if no signals during market hours for this many minutes")
    args = ap.parse_args()

    _load_env()
    secret = (os.getenv("TV_WEBHOOK_SECRET") or "").strip()
    host = (os.getenv("TV_WEBHOOK_HOST") or "127.0.0.1").strip()
    port = (os.getenv("TV_WEBHOOK_PORT") or "5005").strip()

    if not secret:
        print("[SECRET_MISSING] TV_WEBHOOK_SECRET not set in config\\.env — refusing to run.")
        return 2

    mode = (os.getenv("TUNNEL_MODE") or "quick").strip().lower()
    print(f"=== tv_webhook watchdog — {datetime.now(timezone.utc).isoformat(timespec='seconds')} ===")
    print(f"  TUNNEL_MODE: {mode}")

    # 1) local /health
    code, body = _http_get(f"http://{host}:{port}/health")
    local_ok = (code == 200) and ('"status":"ok"' in body)
    print(f"  local /health: {'OK' if local_ok else 'FAIL'} (status={code})")

    # 2) tunnel process (mode-dependent; skip in 'none' mode)
    tun_name = _tunnel_process_name()
    if tun_name:
        cf_alive = _process_alive(tun_name)
        print(f"  {tun_name} in tasklist: {'YES' if cf_alive else 'NO'}")
    else:
        cf_alive = True  # no tunnel expected
        print(f"  tunnel process check: SKIP (mode=none)")

    # 3) public tunnel /health
    public = _public_url()
    public_ok = False
    if public and local_ok:
        code_p, body_p = _http_get(f"{public}/health", timeout=8.0)
        public_ok = (code_p == 200) and ('"status":"ok"' in body_p)
        print(f"  public  /health: {'OK' if public_ok else 'FAIL'}  ({public})")
    elif local_ok and mode != "none":
        if mode in ("named", "ngrok"):
            print(f"  TV_PUBLIC_URL not set in .env — cannot probe public side (mode={mode})")
        else:
            print(f"  public URL not visible in {CLOUDFLARED_ERR.name} — tunnel may be down")

    # In 'none' mode, public_ok isn't expected
    public_required = (mode != "none") and bool(public)

    # ─── healing path ───
    if not (local_ok and cf_alive and (public_ok or not public_required)):
        if args.no_restart:
            print("[DEGRADED] would restart but --no-restart set; sending alert.")
            _send_telegram(
                "TV webhook DEGRADED (no auto-restart)",
                f"local={'OK' if local_ok else 'FAIL'} cf={'OK' if cf_alive else 'FAIL'} "
                f"public={'OK' if public_ok else 'FAIL'}",
                dedup_key="degraded_no_restart",
            )
            return 1

        print("  -> attempting auto-restart via start_tv_webhook.cmd ...")
        restart_ok, restart_out = _restart_launcher()
        # Re-check
        time.sleep(3)
        code2, body2 = _http_get(f"http://{host}:{port}/health")
        recovered = (code2 == 200) and ('"status":"ok"' in body2)
        if recovered:
            print(f"[AUTO_HEALED] receiver back up after restart")
            _send_telegram(
                "TV webhook auto-healed 🔧",
                f"Was down (local={local_ok} cf={cf_alive} public={public_ok}). "
                f"Restart succeeded; /health green now. Tunnel URL may have rotated — "
                f"check `tools\\verify_tv_pipeline.py` for the new URL and update TradingView alerts if so.",
                dedup_key="auto_healed",
            )
            return 0
        print(f"[DEGRADED] restart did not bring /health back. Output tail:\n{restart_out}")
        _send_telegram(
            "TV webhook DOWN — restart FAILED",
            f"start_tv_webhook.cmd returned ok={restart_ok} but /health still {code2}. "
            f"Manual intervention needed. Last 1500 chars of launcher output:\n{restart_out}",
            dedup_key="restart_failed",
        )
        return 1

    # ─── silence check (only during market hours) ───
    age_s = _last_signal_age_s()
    if _market_hours_now() and age_s is not None:
        age_min = age_s / 60.0
        if age_min > args.quiet_threshold_min:
            print(f"[SILENT_HOURS] no signals for {int(age_min)} min during market hours")
            _send_telegram(
                "TV webhook silent during market hours",
                f"Receiver is healthy but no TV signal received for {int(age_min)} min "
                f"(threshold {args.quiet_threshold_min}). Check that TradingView alerts are "
                f"enabled and pointing at the current tunnel URL. Run `tools\\verify_tv_pipeline.py` "
                f"to see the per-(symbol × TF) coverage matrix.",
                dedup_key="silent_market_hours",
            )
            return 1
        print(f"  last signal age: {int(age_min)} min (under {args.quiet_threshold_min} threshold)")
    elif age_s is None:
        print("  no signals in tv_signals.jsonl yet — fresh install or not configured")
    else:
        print(f"  outside market hours; last signal age: {int(age_s/60)} min (silence not alerted)")

    print("[OK] tv_webhook pipeline healthy.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
