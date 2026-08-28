"""Deep end-to-end health check — every layer.
Output is ASCII-safe (no unicode chars that break cp1252).
"""
import json, os, re, subprocess, sys, time, urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(r"C:\Users\Ratanshila\Documents\autmated trading")
ENV  = (ROOT / "config" / ".env").read_text(encoding="utf-8")

# Load .env into our process so we can validate it AND test telegram
sys.path.insert(0, str(ROOT))
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / "config" / ".env", override=True)
except Exception:
    pass

PASS = "[PASS]"
WARN = "[WARN]"
FAIL = "[FAIL]"
INFO = "[INFO]"

results = {"pass": 0, "warn": 0, "fail": 0}
def out(level, label, detail=""):
    if level == PASS: results["pass"] += 1
    elif level == WARN: results["warn"] += 1
    elif level == FAIL: results["fail"] += 1
    print(f"  {level} {label:<45} {detail}")

print("="*82)
print("LAYER 1: pipeline endpoints (HTTP)")
print("="*82)
for name, url, t in [
    ("webhook local",   "http://127.0.0.1:5005/health", 5),
    ("webhook public",  "https://shadow-cosmos-unending.ngrok-free.dev/health", 8),
    ("webhook /status", "http://127.0.0.1:5005/status", 5),
    ("dashboard root",  "http://127.0.0.1:8765/", 8),
    ("dashboard api",   "http://127.0.0.1:8765/api/status", 25),
]:
    try:
        r = urllib.request.urlopen(url, timeout=t)
        body = r.read()[:140].decode("utf-8", errors="replace")
        out(PASS if r.status == 200 else WARN, f"{name} HTTP {r.status}", body[:80])
    except Exception as e:
        out(FAIL, f"{name}", f"{type(e).__name__}: {str(e)[:60]}")

print()
print("="*82)
print("LAYER 2: process roster")
print("="*82)
def ps_count(needle):
    r = subprocess.run(["powershell","-NoProfile","-Command",
        f"(Get-CimInstance Win32_Process -Filter \"name='python.exe' OR name='pythonw.exe'\" | Where-Object {{$_.CommandLine -like '*{needle}*'}} | Measure-Object).Count"],
        capture_output=True, text=True, timeout=10)
    return int(r.stdout.strip() or "0")

def ps_count_proc(name):
    r = subprocess.run(["powershell","-NoProfile","-Command",
        f"(Get-Process -Name '{name}' -ErrorAction SilentlyContinue | Measure-Object).Count"],
        capture_output=True, text=True, timeout=10)
    return int(r.stdout.strip() or "0")

procs = [
    ("brain (trend_master_brain)",      ps_count("trend_master_brain"),      1),
    ("webhook (tv_webhook_receiver)",   ps_count("tv_webhook_receiver"),     1),
    ("executor (python_signal_exec)",   ps_count("python_signal_executor"), 1),
    ("dashboard (dashboard_server)",    ps_count("dashboard_server"),        1),
    ("trailing (trailing_stop_man)",    ps_count("trailing_stop_manager"),   1),
    ("ngrok",                            ps_count_proc("ngrok"),              1),
    ("MT5 terminal64",                   ps_count_proc("terminal64"),         1),
]
for name, cnt, expected_min in procs:
    if cnt == 0:
        out(FAIL, name, f"0 instances — DEAD")
    elif cnt > expected_min * 3:
        out(WARN, name, f"{cnt} instances (expected ~{expected_min}, watchdog respawn artifacts likely)")
    else:
        out(PASS, name, f"{cnt} instance(s)")

print()
print("="*82)
print("LAYER 3: MT5 + brain state")
print("="*82)
try:
    r = urllib.request.urlopen("http://127.0.0.1:8765/api/status", timeout=25)
    j = json.loads(r.read())
    acc = j.get("account", {})
    out(PASS if acc.get("connected") else FAIL, "MT5 connected", f"build={acc.get('build')} login={acc.get('login','?')}")
    out(PASS if acc.get("trade_allowed") else WARN, "MT5 trade_allowed", str(acc.get("trade_allowed")))
    bal = acc.get("balance", 0); eq = acc.get("equity", 0)
    out(INFO, "MT5 balance / equity", f"${bal:.2f} / ${eq:.2f}  floating={acc.get('floating_pl',0):+.2f}")
    np = acc.get("n_positions", 0)
    out(WARN if np > 20 else INFO, "MT5 open positions", f"{np}")
except Exception as e:
    out(FAIL, "MT5 query via dashboard", str(e)[:60])

# Brain state
bs = ROOT / "logs" / "brain_state.json"
if bs.exists():
    try:
        st = json.loads(bs.read_text())
        paused = st.get("trading_paused", False)
        out(PASS if not paused else WARN, "brain trading_paused", str(paused))
        sod = st.get("start_of_day_equity")
        out(INFO, "brain SoD equity", str(sod))
        dd_lockout = st.get("drawdown_lockout_until")
        out(INFO, "brain DD lockout", str(dd_lockout) or "none")
        # mtime
        mtime_age = time.time() - bs.stat().st_mtime
        out(PASS if mtime_age < 600 else WARN, "brain_state.json freshness",
            f"mtime={int(mtime_age)}s ago")
    except Exception as e:
        out(FAIL, "brain_state.json parse", str(e)[:60])

print()
print("="*82)
print("LAYER 4: webhook config (live process)")
print("="*82)
try:
    r = urllib.request.urlopen("http://127.0.0.1:5005/status", timeout=5)
    s = json.loads(r.read())
    m = s.get("metrics", {})
    out(INFO, "webhook uptime", f"{s.get('uptime_s',0)}s")
    out(INFO, "webhook requests_total", str(m.get("requests_total",0)))
    out(INFO, "webhook writes_ok", str(m.get("writes_ok",0)))
    out(INFO, "webhook duplicates", str(m.get("duplicates",0)))
    out(WARN if m.get("rejected",0) > 5 else INFO, "webhook rejected", str(m.get("rejected",0)))
    out(WARN if m.get("auth_fails",0) > 0 else PASS, "webhook auth_fails", str(m.get("auth_fails",0)))
except Exception as e:
    out(FAIL, "webhook /status", str(e)[:60])

# Verify TV_ALLOW_INFERRED is OFF in running webhook (send dryrun no-direction)
try:
    secret = re.search(r"^TV_WEBHOOK_SECRET=(\S+)", ENV, re.MULTILINE).group(1)
    url = f"http://127.0.0.1:5005/tv-signal?secret={secret}&symbol=BTCUSD&tf=15&dryrun=1"
    req = urllib.request.Request(url, data=b"#### BTCUSD ####", method="POST",
                                  headers={"Content-Type":"text/plain"})
    r = urllib.request.urlopen(req, timeout=10)
    j = json.loads(r.read())
    direction = j.get("direction", "")
    if direction == "":
        out(PASS, "TV_ALLOW_INFERRED in proc", "OFF (no-direction signal rejected)")
    elif direction in ("buy","sell"):
        out(WARN, "TV_ALLOW_INFERRED in proc", f"ON (returned {direction!r})")
    else:
        out(WARN, "dryrun unexpected", repr(j))
except Exception as e:
    out(FAIL, "dryrun probe", str(e)[:60])

print()
print("="*82)
print("LAYER 5: critical schtasks fresh activity")
print("="*82)
critical = [
    "TrendMaster Health Watchdog",
    "TrendMaster Live Dashboard",
    "TrendMaster Process Watchdog",
    "TrendMaster Brain Liveness",
    "TrendMaster Signal Pipeline Monitor",
    "TrendMaster TV Webhook Watchdog",
    "TrendMaster Junction Guard",
]
for tn in critical:
    r = subprocess.run(["schtasks","/Query","/TN",tn,"/FO","LIST","/V"], capture_output=True, text=True, timeout=10)
    if r.returncode != 0:
        out(FAIL, tn, "MISSING")
        continue
    ms = re.search(r"Scheduled Task State:\s+(\S+)", r.stdout)
    mlast = re.search(r"Last Run Time:\s+(.+)", r.stdout)
    enabled = ms.group(1) if ms else "?"
    last = mlast.group(1).strip() if mlast else "?"
    if enabled != "Enabled":
        out(WARN, tn, f"state={enabled} last={last}")
    else:
        out(PASS, tn, f"Enabled, last={last}")

print()
print("="*82)
print("LAYER 6: TV alerts on TradingView side (count)")
print("="*82)
# Check via API using existing capture cookies if possible
# Simpler: just count from previous recreate log
log_p = ROOT / "logs" / "recreate_rp.log"
if log_p.exists():
    txt = log_p.read_text(encoding="utf-8", errors="replace")
    m = re.search(r"Final Rocket Prime alerts:\s+(\d+)", txt)
    if m:
        n = int(m.group(1))
        out(PASS if n == 20 else WARN, "TV alerts (last recreate)", f"{n} active")
    out(INFO, "recreate log mtime",
        time.strftime("%Y-%m-%d %H:%M", time.localtime(log_p.stat().st_mtime)))

print()
print("="*82)
print("LAYER 7: recent log errors (last 1 hour)")
print("="*82)
import glob
log_dir = ROOT / "logs"
cutoff = time.time() - 3600
key_logs = ["tv_webhook.log", "python_executor.log", "trend_master_brain.log",
            "dashboard.log", "ngrok.out", "ngrok.err"]
for ln in key_logs:
    p = log_dir / ln
    if not p.exists():
        continue
    try:
        # tail last 30 lines, count 'ERROR' / 'CRITICAL' / 'Traceback'
        lines = p.read_text(encoding="utf-8", errors="replace").splitlines()[-50:]
        errs = [l for l in lines if "ERROR" in l or "CRITICAL" in l or "Traceback" in l]
        if errs:
            out(WARN, f"{ln}", f"{len(errs)} ERROR-level lines in last 50: {errs[-1][:60]}")
        else:
            out(PASS, f"{ln}", "no ERRORs in last 50 lines")
    except Exception as e:
        out(WARN, f"{ln}", f"read failed: {e}")

print()
print("="*82)
print("LAYER 8: autostart + popup hygiene")
print("="*82)
sf = Path(os.path.expandvars(r"%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"))
auto = sf / "TrendMaster_AutoStart.vbs"
out(PASS if auto.exists() else FAIL, "Startup VBS for autostart", str(auto))
ofold = list(sf.glob("OpenClaw*"))
out(PASS if not ofold else WARN, "OpenClaw startup remnants", f"{len(ofold)} files")
gw_cmd = Path(r"C:\Users\Ratanshila\.openclaw\gateway.cmd")
if gw_cmd.exists():
    txt = gw_cmd.read_text(errors="replace")
    is_noop = "exit /b 0" in txt and "node.exe" not in txt
    out(PASS if is_noop else WARN, "OpenClaw gateway.cmd neutered", "no-op" if is_noop else "still has node")

print()
print("="*82)
print("LAYER 9: telegram round-trip (outbound)")
print("="*82)
try:
    from ai_trading_agents.telegram_notifier import get_notifier
    n = get_notifier()
    if not n.enabled:
        out(FAIL, "telegram_notifier.enabled", "False")
    else:
        ok = n.send(f"[health-check {time.strftime('%H:%M:%S')}] ping")
        out(PASS if ok else FAIL, "telegram outbound", "delivered to your phone")
except Exception as e:
    out(FAIL, "telegram", str(e)[:60])

print()
print("="*82)
print(f"SUMMARY: PASS={results['pass']}  WARN={results['warn']}  FAIL={results['fail']}")
print("="*82)
