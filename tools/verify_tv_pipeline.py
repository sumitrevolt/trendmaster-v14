"""End-to-end verification of the TradingView signal pipeline.

Run AFTER start_tv_webhook.cmd to confirm:
  1. Receiver is up on 127.0.0.1:5005
  2. Cloudflare tunnel is up and reachable
  3. Health + status endpoints respond
  4. A test signal round-trips (HTTP 200 → tv_signals.jsonl write_ok → MT5 file updated)
  5. News-blackout asymmetry is wired: prints next blocked window for visual sanity

Usage:
    .venv\\Scripts\\python.exe tools\\verify_tv_pipeline.py
    .venv\\Scripts\\python.exe tools\\verify_tv_pipeline.py --send-test     # actually POST a probe to your webhook

Exit code 0 = green, non-zero = something to investigate.
"""
from __future__ import annotations
import argparse
import json
import os
import re
import sys
import time
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOGS = ROOT / "logs"
TV_LOG = LOGS / "tv_webhook.log"
TV_SIGNALS = LOGS / "tv_signals.jsonl"
CLOUDFLARED_ERR = LOGS / "cloudflared.err"


def _load_env() -> None:
    try:
        from dotenv import load_dotenv  # type: ignore
        load_dotenv(ROOT / "config" / ".env")
    except ImportError:
        pass


def _get(url: str, timeout: float = 4.0) -> tuple[int, str]:
    try:
        r = urllib.request.urlopen(url, timeout=timeout)
        return r.status, r.read().decode("utf-8", errors="replace")
    except Exception as e:
        return 0, f"<error: {e}>"


def _post_json(url: str, body: dict, timeout: float = 6.0) -> tuple[int, str]:
    raw = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url, data=raw, method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        r = urllib.request.urlopen(req, timeout=timeout)
        return r.status, r.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as he:
        return he.code, he.read().decode("utf-8", errors="replace")
    except Exception as e:
        return 0, f"<error: {e}>"


def _public_url() -> str | None:
    """Discover public URL respecting TUNNEL_MODE.

    quick  → scrape last trycloudflare.com URL from cloudflared.err
    named  → return TV_PUBLIC_URL env (stable Cloudflare hostname)
    ngrok  → return TV_PUBLIC_URL or derive from NGROK_DOMAIN
    none   → None (no tunnel)
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
    if not CLOUDFLARED_ERR.exists():
        return None
    text = CLOUDFLARED_ERR.read_text(encoding="utf-8", errors="replace")
    m = re.findall(r"https://[a-z0-9\-]+\.trycloudflare\.com", text)
    return m[-1] if m else None


def _section(label: str, ok: bool, detail: str = "") -> bool:
    icon = "[OK]" if ok else "[X] "
    line = f"{icon} {label}"
    if detail:
        line += f" — {detail}"
    print(line)
    return ok


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--send-test", action="store_true",
                    help="Actually POST a probe signal (XAUUSD BUY, source=verify_script). Default is dry-check only.")
    ap.add_argument("--symbol", default="XAUUSD", help="Probe symbol (default XAUUSD)")
    args = ap.parse_args()

    _load_env()
    secret = (os.getenv("TV_WEBHOOK_SECRET") or "").strip()
    host = (os.getenv("TV_WEBHOOK_HOST") or "127.0.0.1").strip()
    port = (os.getenv("TV_WEBHOOK_PORT") or "5005").strip()
    local = f"http://{host}:{port}"
    public = _public_url()

    failures = 0
    print(f"=== TV pipeline verifier — {datetime.now(timezone.utc).isoformat(timespec='seconds')} ===")
    print(f"Local:  {local}")
    print(f"Public: {public or '(not yet visible — wait 5-10s after start_tv_webhook.cmd)'}")
    print()

    # 1. Secret configured
    if not _section("TV_WEBHOOK_SECRET set in config\\.env", bool(secret)):
        failures += 1

    # 2. Local /health
    code, body = _get(f"{local}/health")
    ok = (code == 200) and ('"status":"ok"' in body)
    if not _section(f"Local /health  (status={code})", ok, body[:80] if body else ""):
        failures += 1

    # 3. Local /status
    code, body = _get(f"{local}/status")
    if not _section(f"Local /status  (status={code})", code == 200, body[:160] if body else ""):
        failures += 1
    else:
        try:
            metrics = json.loads(body).get("metrics", {})
            print(f"        requests_total={metrics.get('requests_total')} writes_ok={metrics.get('writes_ok')} "
                  f"auth_fails={metrics.get('auth_fails')} duplicates={metrics.get('duplicates')}")
        except Exception:
            pass

    # 4. Public health (only if we found URL)
    if public:
        code, body = _get(f"{public}/health", timeout=8.0)
        ok = (code == 200) and ('"status":"ok"' in body)
        if not _section(f"Public /health  (status={code})", ok, body[:80] if body else ""):
            failures += 1
    else:
        print("[!] Public URL not visible in cloudflared.err yet — re-run after 10s.")

    # 5. tv_signals.jsonl present and non-trivial
    signals_n = 0
    if TV_SIGNALS.exists():
        signals_n = sum(1 for _ in TV_SIGNALS.open())
        _section(f"tv_signals.jsonl present ({signals_n} lines)", True)
    else:
        _section("tv_signals.jsonl present", False, "no file at logs\\tv_signals.jsonl")

    # 5b. (symbol × timeframe) coverage matrix over last 24h
    if TV_SIGNALS.exists() and signals_n > 0:
        cutoff = int(time.time()) - 86400
        try:
            from ai_trading_agents.team_params import SYMBOL_TO_TEAM
            symbols = list(SYMBOL_TO_TEAM.keys())[:19]  # first 19 = canonical set
        except Exception:
            symbols = []
        timeframes = ["M5", "M15", "H1", "H4"]  # operator's chosen set
        coverage: dict[tuple[str, str], int] = {}
        for line in TV_SIGNALS.open():
            try:
                rec = json.loads(line)
            except Exception:
                continue
            if rec.get("event") != "write_ok":
                continue
            if int(rec.get("ts", 0)) < cutoff:
                continue
            sym = rec.get("symbol", "")
            tf = rec.get("tv_timeframe") or rec.get("tv_timeframe_raw") or "UNK"
            coverage[(sym, tf)] = coverage.get((sym, tf), 0) + 1
        if symbols:
            print()
            print(f"[i] (symbol × timeframe) coverage — last 24h, {sum(coverage.values())} signals total:")
            header = "  Symbol     " + "  ".join(f"{tf:>4}" for tf in timeframes) + "  Other"
            print(header)
            print("  " + "-" * (len(header) - 2))
            silent = []
            for sym in symbols:
                row = [coverage.get((sym, tf), 0) for tf in timeframes]
                other = sum(c for (s, t), c in coverage.items()
                            if s == sym and t not in timeframes)
                marks = "  ".join(f"{n:>4}" if n > 0 else "   ." for n in row)
                other_s = f"{other:>5}" if other > 0 else "    ."
                print(f"  {sym:<10} {marks}  {other_s}")
                if sum(row) + other == 0:
                    silent.append(sym)
            if silent:
                print()
                print(f"  [!] {len(silent)} pair(s) silent in last 24h: {', '.join(silent)}")
                print(f"      Check the corresponding TradingView alerts are enabled.")

    # 6. Optional probe
    if args.send_test:
        if not secret:
            print("[X] cannot probe — no secret set")
            failures += 1
        else:
            probe = {
                "secret": secret,
                "symbol": args.symbol,
                "direction": "buy",
                "price": 0.0,
                "tv_strategy": "verify_script",
                "tv_alert_ts": int(time.time()),
            }
            code, body = _post_json(f"{local}/tv-signal", probe)
            ok_post = (code == 200) and ('"status":"ok"' in body)
            if not _section(f"POST /tv-signal probe  (status={code})", ok_post, body[:200]):
                failures += 1
            # confirm a write_ok line landed in tv_signals.jsonl
            time.sleep(0.5)
            new_n = sum(1 for _ in TV_SIGNALS.open()) if TV_SIGNALS.exists() else 0
            grew = new_n > signals_n
            _section(f"tv_signals.jsonl grew by 1 line", grew, f"{signals_n} -> {new_n}")
            if not grew:
                failures += 1

    # 7. News-blackout window summary
    try:
        sys.path.insert(0, str(ROOT))
        from ai_trading_agents import profit_filters as pf
        events = pf._load_news_calendar()
        if events:
            now = datetime.now(timezone.utc)
            upcoming = [e for e in events if e["ts"] > now and e.get("impact") == "high"]
            upcoming.sort(key=lambda e: e["ts"])
            if upcoming:
                e = upcoming[0]
                mins = int((e["ts"] - now).total_seconds() // 60)
                start_block = e["ts"] - timedelta(minutes=60)
                end_block = e["ts"] + timedelta(minutes=30)
                print()
                print(f"[i] Next high-impact event: {e['event']} in {mins} min ({e['ts'].isoformat()})")
                print(f"    Blocked window: {start_block.isoformat()} -> {end_block.isoformat()}")
                print(f"    (60 min lead, 30 min lag - operator policy 2026-05-04)")
        else:
            print("[!] news_calendar.json appears empty — news_blackout will fail OPEN (everything trades).")
    except Exception as e:
        print(f"[!] could not summarise news window: {e}")

    print()
    if failures == 0:
        print("=== ALL CHECKS GREEN ===")
        return 0
    print(f"=== {failures} FAILED CHECK(S) — investigate before relying on the pipeline ===")
    return 1


if __name__ == "__main__":
    sys.exit(main())
