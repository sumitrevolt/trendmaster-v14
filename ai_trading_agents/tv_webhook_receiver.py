"""TradingView webhook receiver — stdlib HTTP server, zero new deps.

Listens on TV_WEBHOOK_HOST:TV_WEBHOOK_PORT for POSTs from a TradingView
alert (Premium plan, "Webhook URL" feature). Validates the shared secret,
parses the alert body, and hands off to `tv_executor.write_tv_signal()`
which writes the EA-readable signal JSON.

Endpoints:
    GET  /health    → 200 {"status":"ok","ts":...}    (for ngrok / monitor)
    POST /tv-signal → see body schema below

Body schema (paste this template into the TV alert "Message" field):
    {
      "secret":"YOUR_SECRET",
      "symbol":"{{ticker}}",
      "direction":"{{strategy.order.action}}",
      "price":{{close}},
      "tv_strategy":"{{strategy.order.comment}}",
      "tv_alert_ts":{{timenow}}
    }

Strategy alerts give you `{{strategy.order.action}}` = buy/sell. For
plain indicator alerts you can hardcode the direction per-alert and use:
    {"secret":"...","symbol":"{{ticker}}","direction":"buy","price":{{close}}}

Run:
    python -m ai_trading_agents.tv_webhook_receiver
or via:
    start_tv_webhook.cmd

Environment (config/.env):
    TV_WEBHOOK_SECRET=<32+ char random string — required>
    TV_WEBHOOK_HOST=127.0.0.1   (default; bind to localhost — tunnel exposes)
    TV_WEBHOOK_PORT=5005        (default)

Security:
* Bind to 127.0.0.1 by default and tunnel to TV via ngrok / Cloudflare.
  Never bind 0.0.0.0 without TLS — that's the broker account on the line.
* Shared secret check is `hmac.compare_digest` (constant-time).
* Reject any payload > 4 KiB (TV alerts are tiny — anything bigger is junk).
* Symbol whitelist enforced inside `tv_executor.write_tv_signal`.
"""
from __future__ import annotations

import hmac
import json
import logging
import os
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Dict

# Plain parent.parent — see CLAUDE.md "Brain path resolution rule"
_HERE = Path(__file__).parent
_ROOT = _HERE.parent

# ─── .env loading (same pattern telegram_notifier.py uses) ────────────────
try:
    from dotenv import load_dotenv  # type: ignore

    # 2026-05-13 fix: override=True so config/.env always wins over OS env.
    # Earlier override=False caused stale TELEGRAM_BOT_TOKEN from OS env
    # to win, breaking Telegram helper with 404s.
    for _cand in (_ROOT / "config" / ".env", _ROOT / ".env", _HERE / ".env"):
        if _cand.exists():
            load_dotenv(_cand, override=True)
except ImportError:
    pass

# Logging — file + stderr. Same logs/ dir convention as the brain.
_LOG_DIR = _ROOT / "logs"
_LOG_DIR.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(_LOG_DIR / "tv_webhook.log", encoding="utf-8"),
        # NOTE: removed StreamHandler(sys.stderr) — when launched detached
        # via `cmd /c start /MIN`, stderr's parent console can disappear
        # after the launching shell exits, causing the receiver to crash
        # on the first log write (broken pipe). FileHandler alone is safe.
    ],
)
logger = logging.getLogger("tv_webhook")

# Lazy import — keeps a missing config from blowing up at import time.
try:
    from ai_trading_agents.tv_executor import write_tv_signal
except Exception as e:  # pragma: no cover
    logger.error("Cannot import tv_executor: %s", e)
    raise


# ─── config ───────────────────────────────────────────────────────────────
SECRET = os.getenv("TV_WEBHOOK_SECRET", "").strip()
HOST = os.getenv("TV_WEBHOOK_HOST", "127.0.0.1").strip()
PORT = int(os.getenv("TV_WEBHOOK_PORT", "5005"))
MAX_BODY_BYTES = 4096  # TV alerts are tiny; anything bigger is junk

# In-memory dedup + lightweight runtime metrics for /status endpoint.
import threading

_DEDUP_LOCK = threading.Lock()
_DEDUP_CACHE: Dict[str, float] = {}
DEDUP_WINDOW_S = float(os.getenv("TV_WEBHOOK_DEDUP_WINDOW_S", "20"))

_METRICS: Dict[str, int] = {
    "started_at": int(time.time()),
    "requests_total": 0,
    "auth_fails": 0,
    "rejected": 0,
    "duplicates": 0,
    "writes_ok": 0,
}


# ─── handler ──────────────────────────────────────────────────────────────
class TVHandler(BaseHTTPRequestHandler):
    # Silence the default request log — we log structured records ourselves.
    def log_message(self, fmt, *args):  # noqa: A003 (override stdlib)
        return

    def _send(self, status: int, body: dict) -> None:
        raw = json.dumps(body, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    # --- GET /health and /status -----------------------------------------
    def do_GET(self):  # noqa: N802 (stdlib name)
        path = self.path.split("?", 1)[0]
        if path == "/health":
            self._send(200, {"status": "ok", "ts": int(time.time())})
            return
        if path == "/status":
            uptime = int(time.time()) - _METRICS["started_at"]
            self._send(
                200,
                {
                    "status": "ok",
                    "uptime_s": uptime,
                    "metrics": dict(_METRICS),
                    "dedup_window_s": DEDUP_WINDOW_S,
                    "ts": int(time.time()),
                },
            )
            return
        self._send(404, {"error": "not_found"})

    # --- POST /tv-signal --------------------------------------------------
    def do_POST(self):  # noqa: N802
        if self.path.split("?", 1)[0] != "/tv-signal":
            self._send(404, {"error": "not_found"})
            return

        # 1) read body (size-bounded)
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self._send(400, {"error": "bad_content_length"})
            return
        if content_length <= 0 or content_length > MAX_BODY_BYTES:
            self._send(413, {"error": "body_too_large_or_empty", "limit": MAX_BODY_BYTES})
            return
        try:
            raw = self.rfile.read(content_length)
        except Exception as e:
            logger.warning("read failed: %s", e)
            self._send(400, {"error": "read_failed"})
            return

        # 2) parse — try JSON first, fall back to text-format parser
        # (Rocket Prime indicator and similar paid invite-only indicators
        # don't let you customise the message; their default text is what
        # arrives. We extract symbol from query param ?symbol= or from any
        # token in the body that's in our SYMBOL_TO_TEAM whitelist, and
        # direction from "Buy/Sell Observation" / "buy"/"sell" keywords.)
        body_text = raw.decode("utf-8", errors="replace")
        body: dict = {}
        is_json = False
        try:
            obj = json.loads(body_text)
            if isinstance(obj, dict):
                body = obj
                is_json = True
        except json.JSONDecodeError:
            pass

        # 3) auth — accept secret from JSON body OR URL query (?secret=...)
        # so plain-text indicator messages can still be authenticated by
        # putting the secret in the webhook URL.
        if not SECRET:
            logger.error("TV_WEBHOOK_SECRET not set — refusing to accept signals")
            self._send(503, {"error": "secret_not_configured"})
            return
        provided = str(body.get("secret", "")) if is_json else ""
        if not provided and "?" in self.path:
            # try query param
            from urllib.parse import urlparse, parse_qs

            qs = parse_qs(urlparse(self.path).query)
            provided = (qs.get("secret") or [""])[0]
        if not hmac.compare_digest(str(provided), SECRET):
            _METRICS["auth_fails"] += 1
            logger.warning("auth fail from %s (json=%s)", self.client_address, is_json)
            self._send(401, {"error": "unauthorized"})
            return

        # 4) extract symbol + direction (+ optional timeframe metadata)
        if is_json:
            symbol = str(body.get("symbol", "")).upper().strip()
            direction = str(body.get("direction", body.get("action", "")))
            confidence = body.get("confidence")
            tv_strategy = body.get("tv_strategy") or body.get("strategy")
            tv_price = body.get("price") or body.get("tv_price")
            tv_alert_ts = body.get("tv_alert_ts") or body.get("ts")
            # TF: TradingView emits {{interval}} as "5", "60", "240", "D"
            # Accept any of the three common JSON keys.
            tv_timeframe = (
                body.get("tv_timeframe")
                or body.get("timeframe")
                or body.get("interval")
            )
        else:
            # Text-mode: use the email parser's symbol+direction extraction.
            # The "subject" we pass is the URL query (which contains ticker if
            # the user added &symbol={{ticker}} to their webhook URL); the
            # body is the raw indicator message.
            from urllib.parse import urlparse, parse_qs
            from ai_trading_agents.tv_email_receiver import (
                _extract_symbol,
                _extract_direction,
            )

            qs = parse_qs(urlparse(self.path).query)
            sym_hint = (qs.get("symbol") or [""])[0]
            symbol = (
                _extract_symbol(sym_hint, body_text)
                or _extract_symbol("", body_text)
                or ""
            )
            direction = _extract_direction(body_text) or ""
            confidence = None
            tv_strategy = "rocket_prime_text"
            tv_price = None
            tv_alert_ts = None
            # TF for text mode: ?tf=15 / ?interval=H1 query param.
            tv_timeframe = (qs.get("tf") or qs.get("interval") or [""])[0] or None
            # Debug: log full body when direction extraction fails (one-time).
            if not direction:
                try:
                    debug_path = _LOG_DIR / "tv_webhook_unparsed_bodies.log"
                    with open(debug_path, "a", encoding="utf-8") as df:
                        df.write(f"\n=== {time.strftime('%Y-%m-%dT%H:%M:%S')} sym={symbol!r} ===\n")
                        df.write(f"URL query: {self.path}\n")
                        df.write(f"Body ({len(body_text)} chars):\n")
                        df.write(body_text)
                        df.write("\n--- end body ---\n")
                except Exception:
                    pass
            # PRIORITY 0 (added 2026-05-07 evening, extended 2026-05-10):
            # parse plot values to determine direction. Rocket Prime indicator
            # exposes plots that encode buy/sell signals.
            #
            # 2026-05-07 approach: put placeholders in MESSAGE body field. This
            #   FAILED because Pine alert() function call hardcodes the message
            #   body to "#### TICKER ####", overriding any template.
            #
            # 2026-05-10 fix: TV substitutes placeholders in WEBHOOK URL too,
            #   and URL is a SEPARATE field that alert() does NOT override.
            #   So we read p0..p9 from the URL QUERY first (new path), then
            #   fall back to body parse (legacy path, kept for backwards
            #   compat with any non-RP indicator that follows the body
            #   convention). Diagnostic dump fires for both paths so we can
            #   verify which one delivered.
            #
            # Heuristic: a NON-ZERO plot at the BUY or SELL conventional index
            # is the direction signal:
            #   p0 (or "Buy"-named plot)  > 0  -> BUY
            #   p1 (or "Sell"-named plot) > 0  -> SELL
            # If the convention turns out wrong, swap indices in this block.
            # Diagnostic log entry written for every signal so we can audit
            # the (plot_values -> chart visual) correlation.
            plot_values: dict[int, float] = {}
            plot_source = None
            # New path: URL query plot params (2026-05-10)
            if not direction and symbol and "?" in self.path:
                from urllib.parse import urlparse, parse_qs
                import re as _re_url
                _qs_url = parse_qs(urlparse(self.path).query)
                for k, vlist in _qs_url.items():
                    m = _re_url.match(r"^p(\d+)$", k)
                    if not m:
                        continue
                    try:
                        plot_values[int(m.group(1))] = float(vlist[0])
                    except (ValueError, OverflowError, IndexError):
                        pass
                if plot_values:
                    plot_source = "url"
            # Legacy path: body text
            if not direction and not plot_values and symbol and "RP|" in body_text:
                import re
                for m in re.finditer(r"p(\d+)=([-+]?\d*\.?\d+)", body_text):
                    try:
                        plot_values[int(m.group(1))] = float(m.group(2))
                    except (ValueError, OverflowError):
                        pass
                if plot_values:
                    plot_source = "body"
            if not direction and plot_values and symbol:
                # Diagnostic dump (always, for forensic correlation later)
                try:
                    diag_path = _LOG_DIR / "tv_plot_values.jsonl"
                    with open(diag_path, "a", encoding="utf-8") as df:
                        df.write(json.dumps({
                            "ts": int(time.time()),
                            "symbol": symbol,
                            "tf": tv_timeframe,
                            "plots": plot_values,
                            "plot_source": plot_source,
                            "url": self.path[:300],
                            "body_preview": body_text[:200],
                        }, separators=(",", ":")) + "\n")
                except Exception:
                    pass
                # Heuristic: non-zero plot at index 0 -> BUY, index 1 -> SELL
                # (default convention; swap below if observation says otherwise).
                p0 = plot_values.get(0, 0.0)
                p1 = plot_values.get(1, 0.0)
                if abs(p0) > 1e-9 and abs(p1) < 1e-9:
                    direction = "buy"
                    tv_strategy = "rocket_prime_plot0"
                    confidence = 0.90
                    logger.info(
                        "PLOT-DIRECTION BUY for %s tf=%s (p0=%.4f p1=%.4f)",
                        symbol, tv_timeframe, p0, p1,
                    )
                elif abs(p1) > 1e-9 and abs(p0) < 1e-9:
                    direction = "sell"
                    tv_strategy = "rocket_prime_plot1"
                    confidence = 0.90
                    logger.info(
                        "PLOT-DIRECTION SELL for %s tf=%s (p0=%.4f p1=%.4f)",
                        symbol, tv_timeframe, p0, p1,
                    )
                # else: both zero or both non-zero -> fall through to next priority

            # PRIORITY 1 (added 2026-05-07): explicit `&direction=buy|sell` URL param.
            # When TV alert URL has the direction baked in, trust it over text
            # inference. This is the canonical way to route Buy alerts to Buy
            # trades and Sell alerts to Sell trades from invite-only indicators
            # (Rocket Prime etc.) whose alert text doesn't include the word
            # Buy/Sell.
            if not direction and symbol and "?" in self.path:
                from urllib.parse import urlparse, parse_qs
                _qs = parse_qs(urlparse(self.path).query)
                _url_dir = (_qs.get("direction") or _qs.get("dir") or [""])[0].strip().lower()
                if _url_dir in ("buy", "sell", "long", "short"):
                    direction = "buy" if _url_dir in ("buy", "long") else "sell"
                    tv_strategy = "rocket_prime_url_direction"
                    confidence = 0.95
                    logger.info(
                        "URL-DIRECTION %s for %s tf=%s (no inference needed)",
                        direction.upper(), symbol, tv_timeframe,
                    )

            # PRIORITY 1.5 (2026-05-13): chart-scrape OCR direction extraction.
            # Replaces the failed Method 99 (URL plot placeholders don't substitute
            # under alert()) and supersedes INFERRED (banned after 2 wrong-direction
            # trades — see project_2026-05-13_inferred_failed_again.md memory).
            #
            # Loads the TV chart for (symbol, tf) using persistent Playwright
            # profile, screenshots it, and detects RP's green "Buy Observation"
            # vs red/purple "Sell Observation" label colors in the right-side
            # crop. Returns NONE if ambiguous — falls through to Telegram tap.
            # Latency ~8-10s. Disable via CHART_OCR_ENABLED=0 in config/.env.
            if not direction and symbol:
                try:
                    from ai_trading_agents.chart_scrape_ocr import scrape_rp_direction
                    ocr_dir, ocr_meta = scrape_rp_direction(symbol, tv_timeframe or "M15")
                    if ocr_dir in ("BUY", "SELL"):
                        # Require medium-or-better confidence to act. Low-conf
                        # results return NONE from the module already, but
                        # double-check here in case logic changes.
                        if ocr_meta.get("confidence") in ("high", "medium"):
                            direction = ocr_dir.lower()
                            tv_strategy = "rocket_prime_chart_ocr"
                            confidence = 0.88 if ocr_meta.get("confidence") == "high" else 0.72
                            logger.info(
                                "OCR-DIRECTION %s for %s tf=%s (green_px=%s red_px=%s conf=%s)",
                                ocr_dir, symbol, tv_timeframe,
                                ocr_meta.get("green_label_px"),
                                ocr_meta.get("red_label_px"),
                                ocr_meta.get("confidence"),
                            )
                except Exception as e:
                    logger.warning("chart_scrape_ocr failed for %s: %s", symbol, e)

            # PRIORITY 2: direction inference fallback. DISABLED by default
            # after 2 wrong-direction incidents:
            #   - 2026-05-08 BTCUSD M15: indicator SELL, INFERRED BUY → loss
            #   - 2026-05-13 USDJPY M15: indicator BUY @ 157.564, INFERRED SELL
            # Win rate 0/2 = 0% (worse than coin flip). Permanently OFF in
            # config/.env (TV_ALLOW_INFERRED=0). If you find yourself reading
            # this and thinking "let me re-enable to unblock signals" — DON'T.
            # The OCR scraper above handles 80%+ of cases; ambiguous ones fall
            # to Telegram tap which is 100% accurate (operator decides).
            # See memory: project_2026-05-13_inferred_failed_again.md
            allow_infer = os.getenv("TV_ALLOW_INFERRED", "0").strip() in ("1", "true", "TRUE", "yes")
            if not direction and symbol and allow_infer:
                try:
                    from ai_trading_agents.direction_inference import infer_direction
                    inferred, infer_meta = infer_direction(symbol, tv_timeframe or "M5")
                    if inferred in ("BUY", "SELL"):
                        direction = inferred.lower()
                        tv_strategy = "rocket_prime_inferred"
                        if infer_meta.get("confidence_strong"):
                            confidence = 0.85
                        elif infer_meta.get("weak_signal"):
                            confidence = 0.55
                        else:
                            confidence = 0.70
                        logger.info(
                            "INFERRED %s for %s  pos_in_range=%s last3_pct=%s rsi=%s conf=%.2f",
                            inferred, symbol,
                            infer_meta.get("pos_in_range"),
                            infer_meta.get("last3_diff_pct"),
                            infer_meta.get("rsi"),
                            confidence,
                        )
                except Exception as e:
                    logger.warning("direction_inference failed for %s: %s", symbol, e)
            elif not direction and symbol and not allow_infer:
                # 2026-05-13: instead of silent reject, push to Telegram
                # with BUY/SELL/SKIP inline buttons. Operator taps in <60s
                # → telegram_direction_listener writes signal → bot trades.
                # Direction is operator-decided, never inferred.
                _sig_id = None
                try:
                    from ai_trading_agents.telegram_direction_helper import send_direction_prompt
                    _sig_id = send_direction_prompt(symbol, tv_timeframe, source="rocket_prime")
                except Exception as _tg_e:
                    logger.warning("send_direction_prompt raised: %s", _tg_e)

                if _sig_id:
                    logger.info(
                        "NO-DIRECTION → Telegram prompt sent for %s tf=%s sig=%s "
                        "(awaiting operator BUY/SELL tap; HTTP response to TV "
                        "is non-load-bearing — signal is queued)",
                        symbol, tv_timeframe, _sig_id,
                    )
                    # Try to send 202 to TV. If TV already dropped the
                    # connection (WinError 10053 from waiting), that's fine —
                    # the pending signal lives in pending_signals.jsonl, and
                    # the listener picks it up regardless of HTTP response.
                    try:
                        self._send(202, {"status": "queued_for_operator",
                                          "symbol": symbol, "tf": tv_timeframe,
                                          "sig_id": _sig_id})
                    except Exception:
                        pass  # TV connection dropped; pending state intact
                    return
                logger.warning(
                    "Telegram prompt failed — falling back to REJECT for %s tf=%s "
                    "(check listener log; verify TELEGRAM_BOT_TOKEN reaches bot)",
                    symbol, tv_timeframe,
                )
                logger.warning(
                    "REJECT no-direction signal for %s tf=%s body[:80]=%r "
                    "(Telegram helper unavailable; set TV_ALLOW_INFERRED=1 "
                    "in config/.env to allow guessing, OR fix Telegram bot)",
                    symbol, tv_timeframe, body_text[:80],
                )
            logger.info(
                "TEXT mode parse: symbol=%s direction=%s tf=%s body[:80]=%r",
                symbol,
                direction,
                tv_timeframe,
                body_text[:80],
            )

        # TV sometimes posts numbers as strings — coerce safely.
        if isinstance(tv_alert_ts, str):
            try:
                tv_alert_ts = int(float(tv_alert_ts))
            except ValueError:
                tv_alert_ts = None
        if isinstance(confidence, str):
            try:
                confidence = float(confidence)
            except ValueError:
                confidence = None

        # 5) dedup — skip duplicate (symbol, direction, timeframe) within
        # DEDUP_WINDOW_S. Per-TF dedup added 2026-05-04: previously M5 BUY
        # and H1 BUY firing within 20s would dedupe each other (same
        # (symbol,dir) key); now they're tracked separately so the operator
        # gets one trade per timeframe. If TF is missing/unknown, the key
        # falls back to "UNK" — which still dedupes legitimate same-second
        # duplicates from a single alert.
        if symbol and direction:
            norm_dir = direction.strip().upper()
            if norm_dir in {"LONG", "BULL"}:
                norm_dir = "BUY"
            elif norm_dir in {"SHORT", "BEAR"}:
                norm_dir = "SELL"
            # Provisional TF normaliser — mirrors tv_executor._normalise_timeframe
            # (kept inline so the receiver doesn't have to import it just for
            # the dedup key). Lower-case the raw, look up alias, fall back to UNK.
            tf_key = "UNK"
            if tv_timeframe is not None:
                _tf_raw = str(tv_timeframe).strip().lower()
                _tf_map = {
                    "1": "M1", "3": "M3", "5": "M5", "15": "M15", "30": "M30",
                    "45": "M45", "60": "H1", "120": "H2", "180": "H3", "240": "H4",
                    "d": "D1", "1d": "D1", "w": "W1", "1w": "W1",
                }
                tf_key = _tf_map.get(_tf_raw, _tf_raw.upper() or "UNK")
            cache_key = f"{symbol}:{norm_dir}:{tf_key}"
            now = time.time()
            with _DEDUP_LOCK:
                last = _DEDUP_CACHE.get(cache_key, 0.0)
                if now - last < DEDUP_WINDOW_S:
                    _METRICS["duplicates"] += 1
                    logger.info(
                        "dedup hit: %s within %.1fs (window=%.1fs)",
                        cache_key,
                        now - last,
                        DEDUP_WINDOW_S,
                    )
                    self._send(
                        200,
                        {"status": "duplicate_skipped", "symbol": symbol,
                         "direction": norm_dir, "timeframe": tf_key},
                    )
                    return
                _DEDUP_CACHE[cache_key] = now
                # Trim cache if it grows large. With 19 pairs × 4 TFs × 2 dirs
                # = 152 possible keys we'd realistically see, bumping the cap
                # from 200 → 400 keeps a couple of full cycles in memory.
                if len(_DEDUP_CACHE) > 400:
                    cutoff = now - max(DEDUP_WINDOW_S * 4, 60)
                    for k in [k for k, v in _DEDUP_CACHE.items() if v < cutoff]:
                        _DEDUP_CACHE.pop(k, None)

        _METRICS["requests_total"] += 1

        # 6) DRYRUN short-circuit (added 2026-05-06 after a verification-test
        # incident opened 6 unintended trades). When the URL has ?dryrun=1
        # (or 'true'/'yes'), we count the request, log it for audit, and
        # return 200 WITHOUT touching tv_executor / the MT5 signal file.
        # Use this for any pipeline-routing test so EA never sees the probe.
        _dryrun = False
        if "?" in self.path:
            from urllib.parse import urlparse, parse_qs
            _qs = parse_qs(urlparse(self.path).query)
            _dr = (_qs.get("dryrun") or [""])[0].strip().lower()
            _dryrun = _dr in {"1", "true", "yes", "on"}
        if _dryrun:
            _METRICS.setdefault("dryruns", 0)
            _METRICS["dryruns"] += 1
            logger.info(
                "DRYRUN  symbol=%s dir=%s tf=%s strategy=%s  (no MT5 write)",
                symbol, direction, tv_timeframe, tv_strategy,
            )
            self._send(
                200,
                {"status": "dryrun_ok", "symbol": symbol, "direction": direction,
                 "timeframe": tv_timeframe, "note": "no MT5 file written -- safe for tests"},
            )
            return

        try:
            res = write_tv_signal(
                symbol=symbol,
                direction=direction,
                confidence=confidence,
                source="tradingview_webhook",
                tv_strategy=tv_strategy,
                tv_price=tv_price,
                tv_alert_ts=tv_alert_ts,
                tv_timeframe=tv_timeframe,
            )
        except Exception as e:
            logger.exception("write_tv_signal raised")
            self._send(500, {"error": "executor_failed", "detail": str(e)})
            return

        if not res.get("ok"):
            _METRICS["rejected"] += 1
            logger.warning(
                "rejected: symbol=%s direction=%s err=%s", symbol, direction, res.get("error")
            )
            # 422 = client-fixable (bad symbol / direction / staleness)
            self._send(422, {"error": "rejected", "detail": res.get("error"), "symbol": symbol})
            return

        _METRICS["writes_ok"] += 1
        logger.info(
            "TV→EA OK  symbol=%s dir=%s tf=%s conf=%.3f path=%s strategy=%s",
            symbol,
            res["payload"]["direction"],
            res["payload"].get("tv_timeframe") or res["payload"].get("tv_timeframe_raw") or "-",
            res["payload"]["confidence"],
            res["path"],
            tv_strategy,
        )
        self._send(
            200,
            {
                "status": "ok",
                "symbol": symbol,
                "direction": res["payload"]["direction"],
                "timeframe": res["payload"].get("tv_timeframe"),
                "confidence": res["payload"]["confidence"],
                "ts": res["payload"]["ts"],
            },
        )


def main() -> int:
    # Pre-flight: warn loudly if secret not set; refuse to bind 0.0.0.0
    # without one — that's a brokerage attack surface.
    if not SECRET:
        if HOST != "127.0.0.1":
            logger.error(
                "TV_WEBHOOK_SECRET not set AND HOST=%s — refusing to start. Set TV_WEBHOOK_SECRET in config/.env",
                HOST,
            )
            return 2
        logger.warning(
            "TV_WEBHOOK_SECRET not set — server will refuse all POSTs with 503. Set it in config/.env to accept signals."
        )

    addr = (HOST, PORT)
    httpd = ThreadingHTTPServer(addr, TVHandler)
    logger.info("TV webhook listening on http://%s:%d (secret_set=%s)", HOST, PORT, bool(SECRET))
    logger.info("  GET  /health")
    logger.info("  POST /tv-signal")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        logger.info("shutdown requested")
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
