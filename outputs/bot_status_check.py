"""Comprehensive bot status check."""
import psutil
import time
import json
import urllib.request
from pathlib import Path

ROOT = Path(r"C:\Users\Ratanshila\Documents\autmated trading")
OUT = ROOT / "outputs" / "bot_status_report.txt"

with open(OUT, "w", encoding="utf-8") as f:
    f.write(f"=== Bot status — {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n\n")

    # 1. Component processes
    f.write("=" * 60 + "\n")
    f.write("1. RUNNING COMPONENTS\n")
    f.write("=" * 60 + "\n\n")
    components = {
        "tv_webhook_receiver": "TV Webhook Receiver",
        "python_signal_executor": "Python Signal Executor",
        "trailing_stop_manager": "Trailing Stop Manager",
        "telegram_direction_listener": "Telegram Direction Listener",
        "dashboard_server": "Dashboard Server",
        "ngrok": "Ngrok Tunnel",
    }
    found = {k: [] for k in components}
    for p in psutil.process_iter(['pid', 'name', 'cmdline', 'create_time']):
        try:
            cmd = " ".join(p.info.get('cmdline') or [])
            for key, label in components.items():
                if key in cmd.lower() or (key == "ngrok" and (p.info.get('name') or '').lower() == "ngrok.exe"):
                    age_min = (time.time() - (p.info.get('create_time') or 0)) / 60
                    found[key].append((p.info['pid'], age_min))
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    for key, label in components.items():
        procs = found[key]
        if procs:
            ages = ", ".join(f"PID {pid} ({age:.1f}min old)" for pid, age in procs)
            status = "OK"
        else:
            ages = "(none running)"
            status = "DEAD"
        f.write(f"  [{status:4}] {label:<32} {ages}\n")

    # 2. Webhook health
    f.write("\n" + "=" * 60 + "\n")
    f.write("2. WEBHOOK HEALTH CHECK\n")
    f.write("=" * 60 + "\n\n")
    try:
        r = urllib.request.urlopen("http://127.0.0.1:5005/health", timeout=4)
        f.write(f"  [OK] http://127.0.0.1:5005/health → {r.read().decode()}\n")
    except Exception as e:
        f.write(f"  [DEAD] /health failed: {e}\n")

    # 3. Dashboard health (commonly port 8080 or 8088)
    f.write("\n" + "=" * 60 + "\n")
    f.write("3. DASHBOARD HEALTH CHECK\n")
    f.write("=" * 60 + "\n\n")
    for port in (8765, 8080, 8088, 5000, 5050):
        try:
            r = urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=2)
            f.write(f"  [OK] http://127.0.0.1:{port}/ responds (HTTP {r.status})\n")
        except Exception as e:
            f.write(f"  [DEAD] port {port}: {type(e).__name__}\n")

    # 4. MT5 + open positions
    f.write("\n" + "=" * 60 + "\n")
    f.write("4. MT5 CONNECTION + OPEN POSITIONS\n")
    f.write("=" * 60 + "\n\n")
    try:
        import MetaTrader5 as mt5
        if mt5.initialize():
            ai = mt5.account_info()
            f.write(f"  [OK] Account {ai.login} balance=${ai.balance:.2f} equity=${ai.equity:.2f}\n")
            f.write(f"      profit_today=${ai.profit:.2f} margin_free=${ai.margin_free:.2f}\n")
            pos = mt5.positions_get()
            if pos:
                f.write(f"\n  Open positions ({len(pos)}):\n")
                for p in pos:
                    direction = "BUY" if p.type == 0 else "SELL"
                    f.write(f"    {p.symbol:<8} {direction:<4} {p.volume} lots @ {p.price_open:.5f} | PnL: ${p.profit:+.2f}\n")
            else:
                f.write("  (no open positions)\n")
            mt5.shutdown()
        else:
            f.write(f"  [DEAD] MT5 connect failed: {mt5.last_error()}\n")
    except Exception as e:
        f.write(f"  [ERROR] MT5 check: {e}\n")

    # 5. Recent webhook activity
    f.write("\n" + "=" * 60 + "\n")
    f.write("5. RECENT WEBHOOK ACTIVITY (last 30 min)\n")
    f.write("=" * 60 + "\n\n")
    try:
        wh_log = ROOT / "logs" / "tv_webhook.log"
        if wh_log.exists():
            with open(wh_log, "r", encoding="utf-8", errors="replace") as wf:
                lines = wf.readlines()
            cutoff = time.time() - 1800  # 30 min ago
            recent = []
            for line in lines[-200:]:
                if not line.startswith("2026-"):
                    continue
                try:
                    ts_str = line[:19]
                    ts = time.mktime(time.strptime(ts_str, "%Y-%m-%d %H:%M:%S"))
                    if ts >= cutoff:
                        recent.append(line.strip())
                except Exception:
                    pass
            if recent:
                f.write(f"  Last {len(recent)} events:\n")
                for line in recent[-15:]:
                    f.write(f"    {line[:200]}\n")
            else:
                f.write("  No events in last 30 min — webhook idle but listening.\n")
        else:
            f.write("  (webhook log missing)\n")
    except Exception as e:
        f.write(f"  log read error: {e}\n")

    # 6. Recent executor activity
    f.write("\n" + "=" * 60 + "\n")
    f.write("6. RECENT EXECUTOR HEARTBEAT (last)\n")
    f.write("=" * 60 + "\n\n")
    try:
        ex_log = ROOT / "logs" / "python_executor.log"
        if ex_log.exists():
            with open(ex_log, "r", encoding="utf-8", errors="replace") as ef:
                # Just last few lines containing 'heartbeat'
                lines = ef.readlines()
            hbs = [ln.strip() for ln in lines[-500:] if "heartbeat" in ln]
            if hbs:
                f.write(f"  Last 3 heartbeats:\n")
                for hb in hbs[-3:]:
                    f.write(f"    {hb[:200]}\n")
            else:
                f.write("  No heartbeats in last 500 lines\n")
    except Exception as e:
        f.write(f"  log read error: {e}\n")

    # 7. Telegram listener
    f.write("\n" + "=" * 60 + "\n")
    f.write("7. TELEGRAM LISTENER HEARTBEAT\n")
    f.write("=" * 60 + "\n\n")
    try:
        tl_log = ROOT / "logs" / "telegram_direction_listener.log"
        if tl_log.exists():
            with open(tl_log, "r", encoding="utf-8", errors="replace") as tf:
                lines = tf.readlines()
            hbs = [ln.strip() for ln in lines[-100:] if "heartbeat" in ln or "starting" in ln]
            if hbs:
                f.write(f"  Last 3 entries:\n")
                for hb in hbs[-3:]:
                    f.write(f"    {hb[:200]}\n")
    except Exception as e:
        f.write(f"  log read error: {e}\n")

print(f"Wrote {OUT}")
