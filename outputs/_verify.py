"""One-shot verification script — run real tests + import + smoke every new module."""
import os, sys, subprocess, json
os.chdir(r"C:\Users\Ratanshila\Documents\autmated trading")
sys.path.insert(0, os.getcwd())

print("=" * 70)
print("  TrendMaster v14 — FINAL VERIFICATION")
print("=" * 70)

# 1. pytest
print("\n[1/5] Running full pytest suite...")
r = subprocess.run([sys.executable, "-m", "pytest", "tests/", "-v", "--no-header", "--tb=no"],
                   capture_output=True, text=True, timeout=240)
files = {}
for line in r.stdout.splitlines():
    if "::" in line and ("PASSED" in line or "FAILED" in line):
        fname = line.split("::")[0].replace("\\", "/").split("/")[-1]
        d = files.setdefault(fname, [0, 0])
        d[0 if "PASSED" in line else 1] += 1
for f in sorted(files):
    p, fl = files[f]
    mark = "OK" if fl == 0 else "FAIL"
    print(f"  [{mark:4s}] {f:40s}  passed={p:3d}  failed={fl}")
summary = [l for l in r.stdout.splitlines() if "passed" in l or "failed" in l][-1:]
print(f"\n  SUMMARY: {summary[0] if summary else '(no summary line)'}")

# 2. Module imports
print("\n[2/5] Importing every new module...")
mods = [
    "ai_trading_agents.drift_detector",
    "ai_trading_agents.kelly_sizer",
    "ai_trading_agents.metrics",
    "ai_trading_agents.structured_log",
    "ai_trading_agents.panic",
    "ai_trading_agents.meta_labeler",
    "ai_trading_agents.regime_hmm",
    "ai_trading_agents.news_feed",
    "ai_trading_agents.rolling_corr",
    "ai_trading_agents.portfolio_risk",
    "ai_trading_agents.event_log",
    "ai_trading_agents.ab_test",
    "ai_trading_agents.online_learner",
    "tools.cpcv",
    "tools.slippage_model",
    "tools.stress_test",
]
import importlib
for m in mods:
    try:
        importlib.import_module(m)
        print(f"  OK  {m}")
    except Exception as e:
        print(f"  FAIL {m}: {e!r}")

# 3. Settings flags
print("\n[3/5] Settings flags state:")
from config import settings
for k in ("METRICS", "DRIFT", "KELLY_SIZING", "PANIC", "PORTFOLIO_RISK",
         "EVENT_LOG", "META_LABELER", "REGIME_HMM", "ROLLING_CORR",
         "AB_TEST", "ONLINE_LEARNER"):
    v = getattr(settings, k, None)
    en = v.get("enabled") if isinstance(v, dict) else "MISSING"
    mark = "ON " if en is True else ("off" if en is False else "???")
    print(f"  [{mark}] {k:20s} enabled={en}")

# 4. Brain import + wired modules
print("\n[4/5] Brain import + wired-module inventory...")
from ai_trading_agents import trend_master_brain as brn
wired = ["_portfolio_risk", "_event_log", "_MetaLabeler", "_RegimeHMM",
         "_RollingCorr", "_ABTester", "_OnlineLearner", "_drift",
         "_metrics", "_kelly_apply", "_panic_flatten"]
for w in wired:
    obj = getattr(brn, w, None)
    print(f"  {'OK' if obj is not None else 'MISSING':4s} brain.{w}")

# 5. Stress-test smoke + VaR snapshot smoke
print("\n[5/5] Functional smoke tests:")
from tools.stress_test import run_all
pnls = [2.0, -1.0, 3.5, -2.0, 1.5, 4.0, -1.5, 2.5, 0.5, -0.5] * 20
report = run_all(pnls)
print(f"  stress_test.run_all  robustness={report.robustness_score:.1f}/100  scenarios={len(report.scenarios)}")

from ai_trading_agents.portfolio_risk import snapshot
pnls2 = [1.2, -0.8, 2.1, -1.5, 0.5, 1.8, -2.3, 0.9, 1.1, -0.3] * 10
snap = snapshot(pnls2, confidence=0.95)
print(f"  portfolio_risk.snapshot historical VaR=${snap['historical']['var']:.2f} "
      f"CVaR=${snap['historical']['cvar']:.2f}")

from ai_trading_agents.event_log import get_log
log = get_log()
log.append("signal", "XAUUSD", {"direction": "BUY", "conf": 0.72})
log.flush()
events = log.read_since(0, limit=5)
print(f"  event_log append+read {len(events)} event(s), last kind={events[-1]['k'] if events else '?'}")

from ai_trading_agents.drift_detector import ADWIN
det = ADWIN()
for i in range(50):
    det.update(0.1)
print(f"  drift_detector.update processed 50 obs, window={det.state.current_window_size}")

from ai_trading_agents.kelly_sizer import compute_multiplier, KellyConfig
dec = compute_multiplier([1.0, -0.5, 1.5, -0.3, 1.2] * 10, KellyConfig(min_samples=20))
print(f"  kelly_sizer multiplier={dec.multiplier:.3f} (win_rate={dec.win_rate:.0%})")

from ai_trading_agents.metrics import render_text
txt = render_text()
print(f"  metrics.render_text {len(txt)} chars, uptime_line="
      f"{'OK' if 'trendmaster_uptime_seconds' in txt else 'MISSING'}")

print("\n" + "=" * 70)
print("  VERIFICATION COMPLETE")
print("=" * 70)
