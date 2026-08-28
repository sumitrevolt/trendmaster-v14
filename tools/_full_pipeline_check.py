"""End-to-end pipeline health check.

Verifies every link in the chain: TV alerts -> webhook receiver -> ngrok tunnel
-> JSON files -> Python executor -> MT5 orders -> outcome collector -> brain.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


GREEN = "[OK]"
RED = "[FAIL]"
YELLOW = "[WARN]"
INFO = "[INFO]"


def section(title):
    print()
    print("=" * 70)
    print(f"  {title}")
    print("=" * 70)


def check_mt5():
    section("1. MT5 CONNECTION")
    try:
        import MetaTrader5 as mt5
        if not mt5.initialize():
            print(f"{RED} mt5.initialize failed: {mt5.last_error()}")
            return False
        ti = mt5.terminal_info()
        ai = mt5.account_info()
        print(f"{GREEN} MT5 connected, build={ti.build}")
        print(f"{GREEN} Account {ai.login}, balance ${ai.balance:.2f}, equity ${ai.equity:.2f}")
        print(f"      trade_allowed={ti.trade_allowed}, account.trade_expert={ai.trade_expert}")
        print(f"      Margin used ${ai.margin:.2f}, free ${ai.margin_free:.2f}")
        if not ti.trade_allowed:
            print(f"{RED} Python API trade_allowed=False — orders will be rejected!")
            mt5.shutdown(); return False
        pos = mt5.positions_get() or []
        floating = sum(p.profit for p in pos)
        print(f"{INFO} Open positions: {len(pos)}, floating P/L: {floating:+.2f}")
        mt5.shutdown()
        return True
    except Exception as e:
        print(f"{RED} {e}")
        return False


def check_processes():
    section("2. RUNNING PROCESSES (executor, receiver, ngrok)")
    ok = True
    expected = {
        "python_signal_executor": False,
        "tv_webhook_receiver":   False,
        "ngrok":                 False,
    }
    try:
        out = subprocess.check_output(
            ["powershell.exe", "-NoProfile", "-Command",
             "Get-CimInstance Win32_Process | Select-Object ProcessId,Name,CommandLine | ConvertTo-Json -Depth 3"],
            timeout=15,
        ).decode("utf-8", "replace")
        procs = json.loads(out)
        if isinstance(procs, dict):
            procs = [procs]
        for p in procs:
            cmd = (p.get("CommandLine") or "").lower()
            for key in expected:
                if key in cmd:
                    expected[key] = True
                    print(f"{GREEN} {key}: PID {p.get('ProcessId')}")
        for key, found in expected.items():
            if not found:
                print(f"{RED} {key}: NOT RUNNING")
                ok = False
    except Exception as e:
        print(f"{RED} could not enumerate processes: {e}")
        ok = False
    return ok


def check_webhook_local():
    section("3. WEBHOOK RECEIVER (localhost:5005/status)")
    try:
        req = urllib.request.Request("http://127.0.0.1:5005/status", method="GET")
        with urllib.request.urlopen(req, timeout=5) as r:
            body = r.read().decode("utf-8", "replace")
            if r.status == 200:
                print(f"{GREEN} receiver responding on localhost:5005")
                try:
                    data = json.loads(body)
                    print(f"      requests_total={data.get('requests_total')} writes_ok={data.get('writes_ok')} duplicates={data.get('duplicates')}")
                except Exception:
                    print(f"      body: {body[:200]}")
                return True
            else:
                print(f"{RED} status code {r.status}: {body[:200]}")
                return False
    except Exception as e:
        print(f"{RED} could not reach localhost:5005 — {e}")
        return False


def check_ngrok_public():
    section("4. NGROK PUBLIC TUNNEL")
    domain = "shadow-cosmos-unending.ngrok-free.dev"
    url = f"https://{domain}/status"
    try:
        req = urllib.request.Request(url, method="GET",
                                      headers={"User-Agent": "PipelineCheck/1.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            print(f"{GREEN} ngrok tunnel reachable from internet ({r.status})")
            return True
    except Exception as e:
        print(f"{RED} could not reach {url} — {e}")
        return False


def check_tv_alerts():
    section("5. TRADINGVIEW ALERTS (Rocket Prime H1)")
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print(f"{YELLOW} playwright not available — skipping")
        return True
    HERE = Path(__file__).resolve().parent
    PROFILE = HERE / "tv_alert_setup" / "_browser_profile"
    if not PROFILE.exists():
        print(f"{YELLOW} TV browser profile missing — skipping")
        return True
    ROCKET_PRIME = "PUB;56f0fb74de7f4eed9325b987428b727e"
    GOOD_URL = "https://shadow-cosmos-unending.ngrok-free.dev/tv-signal"
    try:
        with sync_playwright() as p:
            ctx = p.chromium.launch_persistent_context(user_data_dir=str(PROFILE), headless=True)
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            page.goto("https://www.tradingview.com/chart/", wait_until="domcontentloaded", timeout=30_000)
            time.sleep(3)
            api = ctx.request
            r = api.post(
                "https://pricealerts.tradingview.com/list_alerts",
                data=json.dumps({"payload": {"limit": 5000}}),
                headers={"Origin": "https://www.tradingview.com",
                         "Referer": "https://www.tradingview.com/chart/",
                         "Content-Type": "application/json"},
                timeout=15_000,
            )
            alerts = r.json().get("r", [])
            ctx.close()
        rp_h1 = []
        for a in alerts:
            cond = a.get("condition") or {}
            if cond.get("type") != "pine_alert":
                continue
            series = cond.get("series") or [{}]
            if series[0].get("pine_id") != ROCKET_PRIME:
                continue
            res = str(a.get("resolution", ""))
            if res != "60":
                continue
            sym_raw = a.get("symbol", "")
            try:
                sym_obj = json.loads(sym_raw[1:]) if sym_raw.startswith("=") else {}
                sym = sym_obj.get("symbol", "")
            except Exception:
                sym = sym_raw
            wh = a.get("web_hook") or ""
            active = a.get("active")
            last_fire = a.get("last_fire_time")
            rp_h1.append((sym, active, GOOD_URL in wh, last_fire))
        rp_h1.sort()
        active_count = sum(1 for _, act, ok, _ in rp_h1 if act and ok)
        print(f"{GREEN if active_count >= 15 else YELLOW} Rocket Prime H1 alerts: {len(rp_h1)} total, {active_count} active+webhook-ok")
        any_recent = False
        now_unix = int(time.time())
        for sym, act, wh_ok, lf in rp_h1:
            mark = GREEN if (act and wh_ok) else RED
            age = ""
            if lf:
                try:
                    age = f"  last_fire={now_unix - int(lf)}s ago"
                    if now_unix - int(lf) < 7200:
                        any_recent = True
                except Exception:
                    pass
            print(f"  {mark} {sym:<25} active={act} webhook_ok={wh_ok}{age}")
        if not any_recent:
            print(f"{INFO} No alerts have fired in last 2 hours (normal — Rocket Prime fires when its alert() condition triggers, which depends on market action).")
        return active_count >= 15
    except Exception as e:
        print(f"{RED} TV check failed: {e}")
        return False


def check_signal_files():
    section("6. SIGNAL JSON FILES (MT5/MQL5/Files)")
    try:
        import MetaTrader5 as mt5
        mt5.initialize()
        ti = mt5.terminal_info()
        files_dir = Path(ti.data_path) / "MQL5" / "Files"
        mt5.shutdown()
    except Exception as e:
        print(f"{RED} could not locate MT5 Files dir: {e}")
        return False
    if not files_dir.exists():
        print(f"{RED} {files_dir} does not exist")
        return False
    print(f"{INFO} Files dir: {files_dir}")
    sigs = sorted(files_dir.glob("trendmaster_signals*.json"))
    print(f"{INFO} Found {len(sigs)} signal JSON files")
    by_strategy = {}
    fresh_count = 0
    now_unix = int(time.time())
    for p in sigs:
        try:
            j = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        strat = j.get("tv_strategy") or "(none)"
        by_strategy[strat] = by_strategy.get(strat, 0) + 1
        ts = j.get("ts")
        if ts and (now_unix - int(ts)) < 600:
            fresh_count += 1
    for strat, n in sorted(by_strategy.items()):
        mark = YELLOW if strat == "local_generator" else GREEN
        print(f"  {mark} strategy={strat}: {n} files")
    print(f"{INFO} Files written within last 10 min: {fresh_count}/{len(sigs)}")
    return True


def check_logs():
    section("7. LIVE LOGS (last activity)")
    ROOT = Path(__file__).resolve().parent.parent
    log_paths = [
        ("webhook receiver", ROOT / "logs/tv_webhook.log"),
        ("python executor",  ROOT / "logs/python_executor.log"),
        ("outcome collector",ROOT / "logs/signal_outcome_collector.log"),
        ("local generator (should be old/quiet)", ROOT / "logs/local_signal_generator.log"),
    ]
    for name, p in log_paths:
        if not p.exists():
            print(f"{YELLOW} {name}: no log file")
            continue
        mtime = p.stat().st_mtime
        age = time.time() - mtime
        size = p.stat().st_size
        if name.startswith("local generator"):
            mark = GREEN if age > 300 else YELLOW
        else:
            mark = GREEN if age < 600 else YELLOW
        age_s = f"{int(age)}s" if age < 3600 else f"{int(age/60)}m"
        print(f"  {mark} {name:<45} size={size:>9}B  last_write={age_s} ago")


def check_brain():
    section("8. BRAIN (signal quality learner)")
    ROOT = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(ROOT))
    try:
        from config import settings
        tv_filter = getattr(settings, "TV_QUALITY_FILTER", {})
        print(f"  enabled: {tv_filter.get('enabled')}")
        print(f"  min_trades_to_filter: {tv_filter.get('min_trades_to_filter')}")
        print(f"  expectancy_threshold_R: {tv_filter.get('expectancy_threshold_R')}")
        outcomes = ROOT / "logs/signal_outcomes.jsonl"
        if outcomes.exists():
            n = sum(1 for _ in outcomes.open(encoding="utf-8"))
            print(f"  closed-trade outcomes logged so far: {n}")
            if n < 30:
                print(f"  {INFO} Phase 1 mode (collect data first). Filter will activate when classes have ≥30 trades.")
            else:
                print(f"  {GREEN} Enough data — can flip enabled=True to start filtering")
        else:
            print(f"  {INFO} No outcomes yet (waiting for first trade to close)")
    except Exception as e:
        print(f"  {YELLOW} could not load settings: {e}")


def main():
    print()
    print("#" * 70)
    print("  TRENDMASTER PIPELINE HEALTH CHECK")
    print(f"  {datetime.now().isoformat(timespec='seconds')}")
    print("#" * 70)

    results = {}
    results["mt5"] = check_mt5()
    results["procs"] = check_processes()
    results["webhook_local"] = check_webhook_local()
    results["ngrok_public"] = check_ngrok_public()
    results["tv_alerts"] = check_tv_alerts()
    check_signal_files()
    check_logs()
    check_brain()

    section("SUMMARY")
    for k, v in results.items():
        mark = GREEN if v else RED
        print(f"  {mark} {k}")
    all_ok = all(results.values())
    print()
    print("ALL OK" if all_ok else "ISSUES DETECTED — see above")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
