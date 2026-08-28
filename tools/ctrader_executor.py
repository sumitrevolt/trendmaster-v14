"""cTrader Open API executor — places trades on IC Markets cTrader for every
TV signal file written by tv_executor.

Runs in parallel to python_signal_executor.py (which handles OctaFX MT5).
Both watch the same signal files. Same signal -> 2 trades on 2 brokers.

Setup: see docs/IC_MARKETS_CTRADER_SETUP.md

Reads from config/.env:
  CTRADER_CLIENT_ID
  CTRADER_CLIENT_SECRET
  CTRADER_ACCESS_TOKEN  (from ctrader_oauth.py)
  CTRADER_REFRESH_TOKEN (optional, for auto-renew)
  CTRADER_ACCOUNT_ID    (set after --discover-accounts)
  CTRADER_HOST          (live.ctraderapi.com or demo.ctraderapi.com)
  CTRADER_PORT          (5035)

Usage:
  --discover-accounts    Just list accounts available with current token, exit
  (no flag)              Run as long-running executor

Logs to logs/ctrader_executor.log.
"""
from __future__ import annotations
import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Dict, Optional

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / "config" / ".env", override=True)

LOG_DIR = ROOT / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler(LOG_DIR / "ctrader_executor.log", encoding="utf-8")],
)
log = logging.getLogger("ctrader_exec")

# ─── Config ─────────────────────────────────────────────────────────────
HOST = os.getenv("CTRADER_HOST", "live.ctraderapi.com").strip()
PORT = int(os.getenv("CTRADER_PORT", "5035").strip() or "5035")
CLIENT_ID = os.getenv("CTRADER_CLIENT_ID", "").strip()
CLIENT_SECRET = os.getenv("CTRADER_CLIENT_SECRET", "").strip()
ACCESS_TOKEN = os.getenv("CTRADER_ACCESS_TOKEN", "").strip()
REFRESH_TOKEN = os.getenv("CTRADER_REFRESH_TOKEN", "").strip()
ACCOUNT_ID_RAW = os.getenv("CTRADER_ACCOUNT_ID", "").strip()
ACCOUNT_ID = int(ACCOUNT_ID_RAW) if ACCOUNT_ID_RAW.isdigit() else 0

FIXED_LOT_SIZE = 0.01           # mirrors python_signal_executor
SIGNAL_MAX_AGE_S = 90
PER_SYMBOL_DIR_COOLDOWN_S = 300
MAX_OPEN_PER_SYMBOL = 2

# Symbols mirror the python_signal_executor list (TrendMaster's universe).
# cTrader uses different naming for some pairs (e.g. "XAUUSD" -> "XAUUSD" same;
# but BTCUSD might be "BTCUSD.spot" or similar on IC). We map at runtime via
# PROTO_OA_SYMBOLS_LIST_REQ.
SYMBOLS = [
    "XAUUSD", "XAGUSD",
    "EURUSD", "GBPUSD", "USDJPY", "USDCHF", "USDCAD",
    "AUDUSD", "NZDUSD", "EURJPY", "GBPJPY", "AUDJPY",
    "CADJPY", "EURGBP", "EURAUD",
    "BTCUSD", "ETHUSD",
]

# Cooldown tracker (persisted to disk)
_COOLDOWN_FILE = LOG_DIR / "ctrader_cooldown.json"
_LAST_ORDER: Dict[str, float] = {}


def _load_cooldown():
    global _LAST_ORDER
    if _COOLDOWN_FILE.exists():
        try:
            _LAST_ORDER = json.loads(_COOLDOWN_FILE.read_text(encoding="utf-8"))
        except Exception:
            _LAST_ORDER = {}


def _save_cooldown():
    try:
        _COOLDOWN_FILE.write_text(json.dumps(_LAST_ORDER, indent=2), encoding="utf-8")
    except Exception as e:
        log.warning("cooldown save failed: %s", e)


# ─── Singleton lock ─────────────────────────────────────────────────────
import msvcrt
_LOCK_FILE = LOG_DIR / "ctrader_executor.lock"
_LOCK_HANDLE = None


def _acquire_lock() -> bool:
    global _LOCK_HANDLE
    try:
        _LOCK_HANDLE = open(_LOCK_FILE, "a+", encoding="utf-8")
        msvcrt.locking(_LOCK_HANDLE.fileno(), msvcrt.LK_NBLCK, 1)
        _LOCK_HANDLE.seek(0)
        _LOCK_HANDLE.truncate()
        _LOCK_HANDLE.write(f"{os.getpid()}\n")
        _LOCK_HANDLE.flush()
        return True
    except OSError:
        log.warning("ctrader_executor lock held by another instance — exiting")
        return False


# ─── cTrader Open API client (Twisted-based) ────────────────────────────
def _check_creds() -> Optional[str]:
    """Return error string if creds incomplete, else None."""
    if not CLIENT_ID:
        return "CTRADER_CLIENT_ID missing — register app at openapi.ctrader.com"
    if not CLIENT_SECRET:
        return "CTRADER_CLIENT_SECRET missing"
    if not ACCESS_TOKEN:
        return "CTRADER_ACCESS_TOKEN missing — run tools\\ctrader_oauth.py"
    return None


def _connect_and_run(discover_only: bool = False):
    """Connects to cTrader Open API. Authenticates app + account. Then either
    discovers accounts (if discover_only) or starts the polling loop."""
    err = _check_creds()
    if err:
        log.error(err)
        print(f"[X] {err}")
        return 1

    # Lazy import — module is heavy
    from ctrader_open_api import Client, Protobuf, TcpProtocol, EndPoints
    from ctrader_open_api.messages.OpenApiMessages_pb2 import (
        ProtoOAApplicationAuthReq, ProtoOAApplicationAuthRes,
        ProtoOAAccountAuthReq, ProtoOAAccountAuthRes,
        ProtoOAGetAccountListByAccessTokenReq, ProtoOAGetAccountListByAccessTokenRes,
        ProtoOASymbolsListReq, ProtoOASymbolsListRes,
        ProtoOANewOrderReq, ProtoOAExecutionEvent,
        ProtoOAErrorRes,
    )
    from ctrader_open_api.messages.OpenApiModelMessages_pb2 import (
        ProtoOAOrderType, ProtoOATradeSide,
    )
    from twisted.internet import reactor, defer

    state = {"client": None, "symbols_by_name": {}, "polling": False}

    def on_connected(client):
        log.info("Connected to %s:%s", HOST, PORT)
        req = ProtoOAApplicationAuthReq()
        req.clientId = CLIENT_ID
        req.clientSecret = CLIENT_SECRET
        d = client.send(req)
        d.addCallback(lambda r: log.info("App authenticated"))
        d.addErrback(lambda f: log.error("App auth failed: %s", f))

        if discover_only:
            # List accounts available with the access token
            req = ProtoOAGetAccountListByAccessTokenReq()
            req.accessToken = ACCESS_TOKEN
            d = client.send(req)
            d.addCallback(_on_accounts_list)
        else:
            # Authenticate the configured account directly
            if ACCOUNT_ID == 0:
                log.error("CTRADER_ACCOUNT_ID not set — run with --discover-accounts first")
                reactor.stop()
                return
            req = ProtoOAAccountAuthReq()
            req.ctidTraderAccountId = ACCOUNT_ID
            req.accessToken = ACCESS_TOKEN
            d = client.send(req)
            d.addCallback(_on_account_auth)
            d.addErrback(lambda f: log.error("Account auth failed: %s", f))

    def _on_accounts_list(message):
        res = Protobuf.extract(message)
        log.info("Accounts available with token:")
        print("\n=== cTrader accounts available ===")
        for a in res.ctidTraderAccount:
            broker_label = "DEMO" if not a.isLive else "LIVE"
            print(f"  account_id={a.ctidTraderAccountId}  ({broker_label})  broker={a.brokerTitleShort}")
        print("\nPick the IC Markets one and add CTRADER_ACCOUNT_ID=<id> to config\\.env")
        reactor.callLater(1, reactor.stop)

    def _on_account_auth(message):
        log.info("Account %d authenticated", ACCOUNT_ID)
        # Get symbols list to map name -> symbolId
        req = ProtoOASymbolsListReq()
        req.ctidTraderAccountId = ACCOUNT_ID
        d = state["client"].send(req)
        d.addCallback(_on_symbols)

    def _on_symbols(message):
        res = Protobuf.extract(message)
        for s in res.symbol:
            state["symbols_by_name"][s.symbolName.upper()] = s.symbolId
        log.info("Symbol map loaded (%d symbols)", len(state["symbols_by_name"]))
        log.info("Starting signal poll loop...")
        state["polling"] = True
        reactor.callLater(0, _poll_signals)

    def _poll_signals():
        if not state["polling"]:
            return
        try:
            mt5_files = Path(os.getenv("MT5_FILES_DIR", "")).expanduser()
            if not mt5_files.exists():
                # Fall back to default
                mt5_files = Path(r"C:\Users\Ratanshila\AppData\Roaming\MetaQuotes\Terminal\D0E8209F77C8CF37AD8BF550E51FF075\MQL5\Files")
            now = time.time()
            placed = 0
            for sym in SYMBOLS:
                fpath = mt5_files / f"trendmaster_signals_{sym}.json"
                if not fpath.exists():
                    continue
                try:
                    sig = json.loads(fpath.read_text(encoding="utf-8"))
                except Exception:
                    continue
                ts = float(sig.get("ts", 0))
                if now - ts > SIGNAL_MAX_AGE_S:
                    continue
                direction = (sig.get("direction") or "").upper()
                if direction not in ("BUY", "SELL"):
                    continue
                # Cooldown check
                key = f"{sym}|{direction}"
                last = _LAST_ORDER.get(key, 0)
                if now - last < PER_SYMBOL_DIR_COOLDOWN_S:
                    continue

                symbol_id = state["symbols_by_name"].get(sym.upper())
                if not symbol_id:
                    log.warning("Symbol %s not found in cTrader map; skip", sym)
                    continue

                # Place market order
                req = ProtoOANewOrderReq()
                req.ctidTraderAccountId = ACCOUNT_ID
                req.symbolId = symbol_id
                req.orderType = ProtoOAOrderType.MARKET
                req.tradeSide = ProtoOATradeSide.BUY if direction == "BUY" else ProtoOATradeSide.SELL
                # Volume in cTrader is in 1/100th of contract (so 100 = 0.01 lot for FX, varies per symbol)
                # IC Markets convention: volume = lot * 100 for FX/Metals
                req.volume = int(FIXED_LOT_SIZE * 100 * 1000)  # 0.01 * 100 * 1000 = 1000 (=0.01 std lot)
                req.comment = f"PyExec-cTrader-{direction[:1]}"

                d = state["client"].send(req)
                d.addCallback(lambda r, s=sym, dr=direction: _on_order_done(s, dr, r))
                d.addErrback(lambda f, s=sym: log.error("Order send failed for %s: %s", s, f))
                _LAST_ORDER[key] = now
                _save_cooldown()
                placed += 1
            if placed:
                log.info("polled: placed %d order(s) this round", placed)
        except Exception as e:
            log.exception("poll loop error: %s", e)
        # Re-schedule
        reactor.callLater(5, _poll_signals)

    def _on_order_done(sym, direction, message):
        try:
            res = Protobuf.extract(message)
            if hasattr(res, "errorCode") and res.errorCode:
                log.error("Order rejected for %s %s: %s", sym, direction, res.description if hasattr(res, "description") else res)
            else:
                log.info("ORDER PLACED on cTrader: %s %s (response: %s)", sym, direction, type(res).__name__)
        except Exception as e:
            log.error("Order callback parse error: %s", e)

    def on_disconnected(client, reason):
        log.warning("Disconnected: %s", reason)

    def on_message_received(client, message):
        # Errors come through here
        if hasattr(message, "payloadType") and message.payloadType == 50:  # PROTO_OA_ERROR_RES
            try:
                err = Protobuf.extract(message)
                log.error("cTrader error: %s — %s", err.errorCode, err.description)
            except Exception:
                pass

    client = Client(HOST, PORT, TcpProtocol)
    state["client"] = client
    client.setConnectedCallback(on_connected)
    client.setDisconnectedCallback(on_disconnected)
    client.setMessageReceivedCallback(on_message_received)
    client.startService()
    log.info("Connecting to %s:%s ...", HOST, PORT)
    print(f"Connecting to cTrader Open API at {HOST}:{PORT} ...")
    reactor.run()
    return 0


# ─── main ─────────────────────────────────────────────────────────────
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--discover-accounts", action="store_true",
                    help="Just list accounts available with current access token and exit")
    args = ap.parse_args()

    if not args.discover_accounts and not _acquire_lock():
        return 0

    _load_cooldown()
    log.info("ctrader_executor starting (host=%s port=%s account_id=%s discover=%s)",
             HOST, PORT, ACCOUNT_ID or "?", args.discover_accounts)
    return _connect_and_run(discover_only=args.discover_accounts)


if __name__ == "__main__":
    sys.exit(main())
