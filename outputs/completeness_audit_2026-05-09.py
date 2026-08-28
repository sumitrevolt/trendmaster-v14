"""Final completeness audit - find missing connections in TrendMaster v14."""
import json, os, re, subprocess, time, urllib.request
from pathlib import Path

ROOT = Path(r"C:\Users\Ratanshila\Documents\autmated trading")
ENV  = (ROOT / "config" / ".env").read_text(encoding="utf-8")

REPORT = []
def add(category, name, status, detail=""):
    REPORT.append((category, name, status, detail))

# ---------- 1. .env credential coverage ----------
def env_get(k):
    m = re.search(rf"^{k}=(.*)$", ENV, re.MULTILINE)
    return m.group(1).strip() if m else None

required_creds = [
    ("MT5_LOGIN",          "REQUIRED - broker login"),
    ("MT5_PASSWORD",       "REQUIRED - broker password"),
    ("MT5_SERVER",         "REQUIRED - broker server"),
    ("TELEGRAM_BOT_TOKEN", "REQUIRED - Telegram bot"),
    ("TELEGRAM_CHAT_ID",   "REQUIRED - operator chat"),
    ("TV_WEBHOOK_SECRET",  "REQUIRED - webhook auth"),
    ("NGROK_DOMAIN",       "REQUIRED - public tunnel"),
    ("TV_PUBLIC_URL",      "REQUIRED - public URL"),
]
optional_creds = [
    ("EIA_API_KEY",            "optional - natural gas storage feature for V2 model (32→33 features)"),
    ("CTRADER_CLIENT_ID",      "optional - cTrader IC Markets dual-broker mode"),
    ("CTRADER_ACCESS_TOKEN",   "optional - cTrader OAuth (parked 2026-05-07)"),
    ("CTRADER_ACCOUNT_ID",     "optional - IC Markets account"),
    ("TV_EMAIL_USER",          "deprecated - webhook is active path"),
    ("TV_EMAIL_APP_PASSWORD",  "deprecated - webhook is active path"),
]

print(f"\n{'='*72}")
print("1. .env credential coverage")
print('='*72)
for k, desc in required_creds:
    v = env_get(k)
    state = "OK" if v else "MISSING"
    add("env", k, state, desc)
    print(f"  [{state:<7}] {k:<26} {desc}")
for k, desc in optional_creds:
    v = env_get(k)
    state = "OK" if v else "blank"
    add("env_opt", k, state, desc)
    print(f"  [{state:<7}] {k:<26} {desc}")

# ---------- 2. Brain process status ----------
print(f"\n{'='*72}")
print("2. Brain process (rule-based inference / shadow learner)")
print('='*72)
r = subprocess.run(["powershell","-NoProfile","-Command",
    "(Get-CimInstance Win32_Process -Filter \"name='python.exe' OR name='pythonw.exe'\" | Where-Object {$_.CommandLine -like '*trend_master_brain*'} | Measure-Object).Count"],
    capture_output=True, text=True, timeout=10)
brain_count = int(r.stdout.strip() or "0")
state = "RUNNING" if brain_count else "DEAD"
add("process", "brain", state, f"trend_master_brain.py instances={brain_count}")
print(f"  [{state:<7}] brain (trend_master_brain.py): {brain_count} instances")
print(f"           Note: TV is source of truth - brain may be intentionally idle in shadow mode.")

# ---------- 3. Pipeline endpoints ----------
print(f"\n{'='*72}")
print("3. Pipeline endpoints")
print('='*72)
endpoints = [
    ("webhook local",     "http://127.0.0.1:5005/health",                                 5),
    ("webhook public",    "https://shadow-cosmos-unending.ngrok-free.dev/health",         8),
    ("dashboard",         "http://127.0.0.1:8765/api/status",                            20),
]
for name, url, t in endpoints:
    try:
        r = urllib.request.urlopen(url, timeout=t)
        state = "OK" if r.status == 200 else f"HTTP {r.status}"
    except Exception as e:
        state = f"FAIL {type(e).__name__}"
    add("endpoint", name, state, url)
    print(f"  [{state:<7}] {name:<20} {url}")

# ---------- 4. Critical schtasks coverage ----------
print(f"\n{'='*72}")
print("4. Critical schtasks state")
print('='*72)
critical = [
    "TrendMaster Health Watchdog",
    "TrendMaster Live Dashboard",
    "TrendMaster Process Watchdog",
    "TrendMaster Brain Liveness",
    "TrendMaster Signal Pipeline Monitor",
    "TrendMaster Junction Guard",
    "TrendMaster Walkforward Lab",
    "TrendMaster Reactivate Alerts",
    "TrendMaster Zero Trades Watchdog",
]
for tn in critical:
    r = subprocess.run(["schtasks","/Query","/TN",tn,"/FO","LIST"], capture_output=True, text=True, timeout=10)
    if r.returncode != 0:
        state = "MISSING"
    else:
        m = re.search(r"Scheduled Task State:\s+(\S+)", r.stdout)
        state = m.group(1) if m else "UNKNOWN"
    add("schtask", tn, state)
    print(f"  [{state:<8}] {tn}")

# ---------- 5. ngrok stability outlook ----------
print(f"\n{'='*72}")
print("5. ngrok stability")
print('='*72)
# ngrok-free reserved domain auto-disconnects approx every 2 hours
# Check if NGROK_AUTHTOKEN is paid (longer connection life)
ngrok_yml = Path(os.path.expandvars(r"%LOCALAPPDATA%\ngrok\ngrok.yml"))
if ngrok_yml.exists():
    txt = ngrok_yml.read_text(encoding="utf-8", errors="replace")
    has_token = "authtoken" in txt
    add("infra", "ngrok.yml", "OK" if has_token else "NO_TOKEN", str(ngrok_yml))
    print(f"  [{'OK' if has_token else 'NO_TOKEN':<7}] ngrok.yml found at {ngrok_yml}")
    print(f"           Note: ngrok-free has ~2hr session limit. Paid plan removes this.")
else:
    add("infra", "ngrok.yml", "MISSING", str(ngrok_yml))
    print(f"  [MISSING] ngrok.yml - would cause ERR_NGROK_4018 after restart")

# ---------- 6. Git / GitHub sync ----------
print(f"\n{'='*72}")
print("6. Git status (project version control)")
print('='*72)
r = subprocess.run(["git","-C",str(ROOT),"status","--short"], capture_output=True, text=True, timeout=10)
if r.returncode == 0:
    dirty_lines = [ln for ln in r.stdout.splitlines() if ln.strip()]
    add("infra", "git", "DIRTY" if dirty_lines else "CLEAN", f"{len(dirty_lines)} uncommitted files")
    print(f"  [{'DIRTY' if dirty_lines else 'CLEAN':<7}] {len(dirty_lines)} uncommitted files")
    if dirty_lines[:5]:
        for ln in dirty_lines[:5]:
            print(f"           {ln}")
        if len(dirty_lines) > 5:
            print(f"           ... +{len(dirty_lines)-5} more")
else:
    add("infra", "git", "NO_REPO", r.stderr.strip()[:100])

r2 = subprocess.run(["git","-C",str(ROOT),"log","-1","--format=%cI %h %s"], capture_output=True, text=True, timeout=10)
if r2.returncode == 0:
    print(f"  Last commit: {r2.stdout.strip()}")

# ---------- 7. Backup state files ----------
print(f"\n{'='*72}")
print("7. State backups")
print('='*72)
key_state_files = [
    ROOT / "logs" / "brain_state.json",
    ROOT / "logs" / "watchdog_state.json",
    ROOT / "logs" / "tv_signals.jsonl",
    ROOT / "logs" / "trades.csv",
]
for f in key_state_files:
    if f.exists():
        size = f.stat().st_size
        mtime = time.strftime("%Y-%m-%d %H:%M", time.localtime(f.stat().st_mtime))
        state = "OK" if size > 0 else "EMPTY"
        add("state", f.name, state, f"size={size} mtime={mtime}")
        print(f"  [{state:<5}] {f.name:<28} {size:>8} bytes  mtime={mtime}")
    else:
        add("state", f.name, "MISSING", str(f))
        print(f"  [MISSING] {f.name}")

# ---------- 8. Telegram inbound (commands) ----------
print(f"\n{'='*72}")
print("8. Telegram inbound (operator-command path)")
print('='*72)
# Check if there's a telegram_commands listener registered
r = subprocess.run(["powershell","-NoProfile","-Command",
    "(Get-CimInstance Win32_Process -Filter \"name='python.exe' OR name='pythonw.exe'\" | Where-Object {$_.CommandLine -like '*telegram_commands*'} | Measure-Object).Count"],
    capture_output=True, text=True, timeout=10)
n = int(r.stdout.strip() or "0")
state = "RUNNING" if n else "NOT_RUNNING"
add("optional", "telegram_commands", state, f"{n} instances")
print(f"  [{state:<11}] telegram_commands.py listener: {n} instances")
print(f"           Currently only outbound. To enable /halt /resume /status from phone,")
print(f"           run python -m ai_trading_agents.telegram_commands.")

# ---------- summary ----------
print(f"\n{'='*72}")
print("SUMMARY")
print('='*72)
issues = [r for r in REPORT if r[2] in ("MISSING","FAIL","DEAD","NOT_RUNNING","NO_TOKEN","blank","DIRTY")]
print(f"  Total checks: {len(REPORT)}")
critical_issues = [r for r in issues if r[0] in ("env","endpoint","schtask","infra")]
print(f"  Critical issues: {len(critical_issues)}")
optional_issues = [r for r in issues if r[0] not in ("env","endpoint","schtask","infra")]
print(f"  Optional/informational: {len(optional_issues)}")
print()
if critical_issues:
    print("  CRITICAL items needing attention:")
    for cat, name, state, detail in critical_issues:
        print(f"    [{state}] {name} - {detail[:80]}")

# Save JSON for programmatic re-check
out = ROOT / "outputs" / "completeness_audit_2026-05-09.json"
out.write_text(json.dumps([{"category":c,"name":n,"state":s,"detail":d} for c,n,s,d in REPORT], indent=2))
print(f"\n  Full JSON: {out}")
