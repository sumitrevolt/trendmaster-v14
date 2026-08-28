"""Check MT5 trade activity + brain state to understand what triggered trades recently."""
import json
from pathlib import Path
from datetime import datetime

ROOT = Path(r"C:\Users\Ratanshila\Documents\autmated trading")
MT5_FILES = Path(r"C:\Users\Ratanshila\AppData\Roaming\MetaQuotes\Terminal\D0E8209F77C8CF37AD8BF550E51FF075\MQL5\Files")

# 1. List MT5 signal files written by webhook
print("=== MT5 signal files (written by webhook) ===")
for f in sorted(MT5_FILES.glob("trendmaster_signals*.json")):
    try:
        st = f.stat()
        age_min = (datetime.now().timestamp() - st.st_mtime) / 60
        content = f.read_text()[:200]
        print(f"  {f.name:40} mtime: {datetime.fromtimestamp(st.st_mtime).isoformat(timespec='seconds')} ({age_min:.1f} min ago)")
        print(f"    content: {content}")
    except Exception as e:
        print(f"  {f.name}: ERROR {e}")

# 2. Brain state — recent results, paused state, etc.
state_path = ROOT / "logs" / "brain_state.json"
print(f"\n=== Brain state ({state_path.name}) ===")
if state_path.exists():
    state = json.loads(state_path.read_text())
    print(f"  trading_paused: {state.get('trading_paused')}")
    print(f"  drawdown_lockout_until: {state.get('drawdown_lockout_until')}")
    print(f"  start_of_day_equity: {state.get('start_of_day_equity')}")
    rr = state.get('recent_results') or []
    print(f"  recent_results count: {len(rr)}")
    for r in rr[-5:]:
        print(f"    - {r}")
    last_sigs = state.get('last_signal_per_symbol') or {}
    print(f"\n  last_signal_per_symbol (5 most-recent):")
    sigs = sorted(last_sigs.items(), key=lambda x: x[1].get('ts', 0) if isinstance(x[1], dict) else 0, reverse=True)
    for sym, sig in sigs[:5]:
        ts = sig.get('ts') if isinstance(sig, dict) else None
        ts_iso = datetime.fromtimestamp(ts).isoformat(timespec='seconds') if ts else '-'
        print(f"    {sym}: ts={ts_iso}, dir={sig.get('direction') if isinstance(sig, dict) else sig}")
else:
    print("  not found")

# 3. tv_signals.jsonl tail with timestamps converted
print(f"\n=== Last 8 webhook signals (with absolute time) ===")
sig_path = ROOT / "logs" / "tv_signals.jsonl"
if sig_path.exists():
    lines = sig_path.read_text().splitlines()
    for line in lines[-8:]:
        try:
            d = json.loads(line)
            ts = d.get('ts')
            ts_iso = datetime.fromtimestamp(ts).isoformat(timespec='seconds') if ts else '?'
            age_min = (datetime.now().timestamp() - ts) / 60 if ts else 0
            print(f"  {ts_iso} ({age_min:5.1f}min ago) {d.get('symbol'):8} {d.get('direction'):4} tf={d.get('tv_timeframe') or '-'} src={d.get('tv_strategy') or '?'}")
        except Exception:
            pass

# 4. Brain process check
import subprocess
print(f"\n=== Brain process ===")
res = subprocess.run(['powershell', '-NoProfile', '-Command',
                      "Get-CimInstance Win32_Process -Filter \"name='python.exe'\" | Where-Object { $_.CommandLine -like '*trend_master_brain*' } | Select-Object ProcessId, @{N='Started';E={$_.CreationDate}}"],
                     capture_output=True, text=True, timeout=10)
print(res.stdout or "(no brain process running)")
