"""Probe /api/status - dump full shape to a file we can read."""
import json
import urllib.request
from pathlib import Path

OUT = Path(__file__).parent / "config_probe.json"

try:
    with urllib.request.urlopen("http://127.0.0.1:8765/api/status", timeout=10) as resp:
        data = json.loads(resp.read())
except Exception as e:
    OUT.write_text(json.dumps({"error": str(e)}), encoding="utf-8")
    raise SystemExit(1)

cfg = data.get("config")
out = {
    "top_level_keys": list(data.keys()),
    "config_type": type(cfg).__name__,
    "n_positions": len(data.get("account", {}).get("positions", [])) if isinstance(data.get("account"), dict) else None,
    "n_deals": len(data.get("deals", {}).get("deals", [])) if isinstance(data.get("deals"), dict) else None,
}
if isinstance(cfg, dict):
    out["config_keys"] = list(cfg.keys())
    sg = cfg.get("safeguards")
    out["safeguards_type"] = type(sg).__name__
    if isinstance(sg, dict):
        out["safeguards_keys"] = list(sg.keys())
    out["sample_values"] = {k: cfg.get(k, "MISSING") for k in
        ['trading_enabled', 'trailing_enabled', 'brain_filter_enabled', 'two_leg_enabled',
         'fixed_lot', 'quick_tp_atr', 'quick_sl_atr', 'audio_alert_threshold', 'pairs_enabled']}
OUT.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
