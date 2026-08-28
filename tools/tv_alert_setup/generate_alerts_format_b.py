"""Generate alerts_config.json in Format B (URL secret + indicator's own message).

Format B is for indicators (e.g. Rocket Prime Engine) that emit their own
'Buy Observation @ price' / 'Sell Observation @ price' text via alert()
calls. The TV alert's Message field is left empty/untouched -- routing
info travels in the webhook URL query params.

URL pattern:
  https://<TV_PUBLIC_URL>/tv-signal?secret=<TV_WEBHOOK_SECRET>&symbol=<SYM>&tf=<TV_INTERVAL>

The receiver:
  * Validates secret
  * Routes by symbol param (overrides anything in body)
  * Parses direction from body text ("Buy" / "Sell" / "Long" / "Short")
  * Stamps tv_timeframe from tf param

Why: TradingView Free / Pro plans + invite-only indicators (Rocket Prime,
Goldbach, etc.) hardcode the alert message and don't let you template it.
Format A (JSON body) breaks. Format B works on every plan.

Usage:
  .venv\\Scripts\\python.exe tools\\tv_alert_setup\\generate_alerts_format_b.py
  .venv\\Scripts\\python.exe tools\\tv_alert_setup\\generate_alerts_format_b.py \\
      --symbols XAUUSD,EURUSD,USDJPY,GBPUSD,BTCUSD \\
      --timeframes M5,M15,M30,H1
"""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

# MetaTrader-style TF -> TradingView's `interval` value
TF_TO_TV_INTERVAL = {
    "M1": "1",   "M5": "5",   "M15": "15", "M30": "30",
    "H1": "60",  "H2": "120", "H4": "240",
    "D1": "D",   "W1": "W",
}
TF_TO_TV_LABEL = {
    "M1": "1 minute", "M5": "5 minutes", "M15": "15 minutes", "M30": "30 minutes",
    "H1": "1 hour", "H2": "2 hours", "H4": "4 hours",
    "D1": "1 day", "W1": "1 week",
}


def _load_env() -> dict:
    env = {}
    env_path = ROOT / "config" / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    return env


def _broker_exchange(symbol: str) -> str:
    """Map TrendMaster symbol to TradingView exchange prefix."""
    if symbol in {"BTCUSD", "ETHUSD"}:
        return "BINANCE"
    if symbol in {"XTIUSD", "XBRUSD", "XNGUSD"}:
        return "TVC"
    return "OANDA"


def _broker_symbol(symbol: str) -> str:
    """Convert TrendMaster symbol -> exchange-specific ticker."""
    overrides = {
        "BTCUSD": "BTCUSDT",   # Binance pair
        "ETHUSD": "ETHUSDT",
        "XTIUSD": "USOIL",
        "XBRUSD": "UKOIL",
        "XNGUSD": "NATGASUSD",
    }
    return overrides.get(symbol, symbol)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", default="XAUUSD,EURUSD,USDJPY,GBPUSD,BTCUSD",
                    help="Comma-separated symbols (default: top-Sharpe 5)")
    ap.add_argument("--timeframes", default="M5,M15,M30,H1",
                    help="Comma-separated TFs (default: M5,M15,M30,H1)")
    ap.add_argument("--out", default=None,
                    help="Output path (default: alerts_config.json next to script)")
    args = ap.parse_args()

    env = _load_env()
    secret = env.get("TV_WEBHOOK_SECRET", "").strip()
    public_url = env.get("TV_PUBLIC_URL", "").strip().rstrip("/")
    if not secret:
        print("FATAL: TV_WEBHOOK_SECRET missing in config/.env"); return 1
    if not public_url:
        print("FATAL: TV_PUBLIC_URL missing in config/.env"); return 1

    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    timeframes = [tf.strip().upper() for tf in args.timeframes.split(",") if tf.strip()]
    for tf in timeframes:
        if tf not in TF_TO_TV_INTERVAL:
            print(f"FATAL: unknown timeframe {tf}; supported: {list(TF_TO_TV_INTERVAL.keys())}")
            return 1

    alerts = []
    for sym in symbols:
        ex = _broker_exchange(sym)
        broker_sym = _broker_symbol(sym)
        for tf in timeframes:
            tv_interval = TF_TO_TV_INTERVAL[tf]
            # Format B: secret + symbol + tf go in the URL query, message empty
            webhook_url = (
                f"{public_url}/tv-signal"
                f"?secret={secret}"
                f"&symbol={sym}"
                f"&tf={tv_interval}"
            )
            alerts.append({
                "id": f"{sym}_{tf}_RP",
                "symbol": sym,
                "exchange": ex,
                "broker_symbol": broker_sym,
                "timeframe": tf,
                "tv_interval": tv_interval,
                "tv_timeframe_label": TF_TO_TV_LABEL[tf],
                "direction": "AUTO",       # parsed from indicator text
                "format": "B",             # tells setup script to skip message fill
                "name": f"TrendMaster {sym} {tf} RocketPrime",
                "webhook_url": webhook_url,
                "message_body": "",        # empty -> Rocket Prime alert() text passes through
            })

    out_path = Path(args.out) if args.out else Path(__file__).resolve().parent / "alerts_config.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(alerts, indent=2), encoding="utf-8")
    print(f"[OK] Wrote {len(alerts)} Format-B alert specs -> {out_path}")
    print(f"     Public URL : {public_url}")
    print(f"     Symbols    : {symbols}")
    print(f"     Timeframes : {timeframes}")
    print(f"     Per alert  : 1 (direction parsed from indicator output)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
