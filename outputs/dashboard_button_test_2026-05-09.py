"""Hit every dashboard endpoint and report which work, which don't."""
import json, urllib.request, urllib.parse, time

BASE = "http://127.0.0.1:8765"

# (method, path, what it does)  — start with READ-ONLY + idempotent ones
TESTS = [
    ("GET",  "/api/status",                "live MT5+config snapshot"),
    ("GET",  "/api/log?name=brain&n=20",   "tail brain log"),
    ("GET",  "/api/log?name=executor&n=20","tail executor log"),
    ("GET",  "/api/log?name=webhook&n=20", "tail webhook log"),
    ("GET",  "/api/equity-history?hours=2","equity curve data"),
    ("POST", "/api/test-telegram",         "send test telegram"),
    ("POST", "/api/send-snapshot",         "send snapshot telegram"),
    ("POST", "/api/halt-all",              "set trading_enabled=False"),
    ("POST", "/api/resume",                "set trading_enabled=True"),
    # destructive — NOT TESTED LIVE: close-all, close-position, modify-sltp, restart-executor, restart-trailing
]

print(f"{'METHOD':<6} {'STATUS':<8} {'TIME':<7} PATH")
print("-" * 80)
for method, path, desc in TESTS:
    t0 = time.time()
    try:
        req = urllib.request.Request(BASE + path, method=method)
        r = urllib.request.urlopen(req, timeout=20)
        body = r.read().decode("utf-8", errors="replace")[:120]
        # Try to parse for "ok": false
        verdict = "OK"
        try:
            j = json.loads(body)
            if isinstance(j, dict) and j.get("ok") is False:
                verdict = "BUG"
            elif isinstance(j, dict) and "error" in j:
                verdict = "BUG"
        except Exception:
            pass
        print(f"{method:<6} [{r.status}]    {time.time()-t0:>5.2f}s  {path}  --> {verdict}")
        if verdict == "BUG":
            print(f"          body: {body}")
    except Exception as e:
        print(f"{method:<6} [FAIL]  {time.time()-t0:>5.2f}s  {path}  --> {type(e).__name__}: {str(e)[:80]}")

# Bonus: check the toggle endpoint with a known harmless key
print()
print("--- toggle test (master switch flip+restore) ---")
for val in ("false", "true"):
    try:
        url = f"{BASE}/api/toggle?key=trading_enabled&val={val}"
        r = urllib.request.urlopen(urllib.request.Request(url, method="POST"), timeout=10)
        print(f"  toggle trading_enabled={val} -> {r.status} {r.read().decode()[:80]}")
    except Exception as e:
        print(f"  toggle trading_enabled={val} -> FAIL: {e!r}")
