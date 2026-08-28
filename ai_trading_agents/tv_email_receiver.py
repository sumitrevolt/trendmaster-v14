"""TradingView email receiver — IMAP poller that feeds write_tv_signal().

BACKUP signal path when TV webhooks are unavailable (Free plan / tunnel
outage). Polls Gmail via IMAP for alert emails from TradingView, parses
symbol/direction/timeframe, and dispatches through the same
`tv_executor.write_tv_signal()` the webhook uses. Latency ~10-20s.

Activation (see config/settings.py::TV_EMAIL comment block):
  1. Gmail App Password -> config/.env:  TV_EMAIL_USER, TV_EMAIL_APP_PASSWORD
  2. config/settings.py: TV_EMAIL["enabled"] = True
  3. start_tv_email.cmd   (or run this module directly)

Parsing priority (operator policy: direction is NEVER inferred numerically):
  P0  RP|<ticker>|tf=<interval>|p0=..|p1=.. pipe format in body
      (plot placeholders survive into emails; p0!=0&p1==0 -> BUY,
       p1!=0&p0==0 -> SELL, conf 0.90 — mirrors webhook Priority 0)
  P1  explicit direction keywords in subject/body:
      "Buy Observation" / "Sell Observation", BUY/LONG, SELL/SHORT
  P2  no direction found -> REJECT + log (never guess)

Symbol extraction: any whitelisted symbol token (tv_executor._SYMBOL_TO_TEAM)
found in subject or body, exchange prefix stripped ("OANDA:XAUUSD"->XAUUSD).
"""
from __future__ import annotations

import collections
import email as email_lib
from email.header import decode_header, make_header
from email.utils import parsedate_to_datetime
from html import unescape as html_unescape
import imaplib
import logging
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional, Tuple

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from dotenv import load_dotenv

_ROOT = Path(__file__).parent.parent
load_dotenv(_ROOT / "config" / ".env")

from ai_trading_agents.tv_executor import write_tv_signal, _SYMBOL_TO_TEAM  # noqa: E402

LOGS = _ROOT / "logs"
LOG_FILE = LOGS / "tv_email.log"
STATE_FILE = LOGS / "tv_email_state.json"

# ───────────────────────── config ─────────────────────────
def _cfg() -> Dict:
    """Merge settings.TV_EMAIL with .env credentials; fail soft on import."""
    try:
        from config import settings as s
        base = dict(getattr(s, "TV_EMAIL", {}) or {})
    except Exception:
        base = {}
    return {
        "enabled": bool(base.get("enabled", False)),
        "poll_interval_s": int(base.get("poll_interval_s", 10)),
        "from_filter": str(base.get("from_filter", "noreply@tradingview.com")),
        "max_age_minutes": int(base.get("max_age_minutes", 5)),
        "telegram_echo": bool(base.get("telegram_echo", True)),
        "dedup_window": int(base.get("dedup_window", 256)),
        "search_hours_back": int(base.get("search_hours_back", 1)),
        "backoff_min_s": int(base.get("backoff_min_s", 5)),
        "backoff_max_s": int(base.get("backoff_max_s", 120)),
        "imap_host": os.getenv("TV_EMAIL_IMAP_HOST", "imap.gmail.com"),
        "imap_port": int(os.getenv("TV_EMAIL_IMAP_PORT", "993")),
        "user": os.getenv("TV_EMAIL_USER", "").strip(),
        "password": os.getenv("TV_EMAIL_APP_PASSWORD", "").strip(),
    }


LOG = logging.getLogger("tv_email")


def _setup_logging() -> None:
    LOG.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s", "%Y-%m-%d %H:%M:%S")
    LOG.handlers.clear()
    fh = logging.FileHandler(LOG_FILE, encoding="utf-8")
    fh.setFormatter(fmt)
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    LOG.addHandler(fh)
    LOG.addHandler(sh)


# ───────────────────────── helpers ─────────────────────────
_TF_MAP = {
    "1": "M1", "3": "M3", "5": "M5", "15": "M15", "30": "M30", "45": "M45",
    "60": "H1", "120": "H2", "180": "H3", "240": "H4",
    "1 minute": "M1", "5 minutes": "M5", "15 minutes": "M15", "30 minutes": "M30",
    "45 minutes": "M45", "1 hour": "H1", "2 hours": "H2", "3 hours": "H3",
    "4 hours": "H4", "daily": "D1", "1 day": "D1", "weekly": "W1", "monthly": "MN1",
}


def _norm_tf(raw: Optional[str]) -> Optional[str]:
    if not raw:
        return None
    key = str(raw).strip().lower()
    if key in _TF_MAP:
        return _TF_MAP[key]
    m = re.fullmatch(r"(\d+)\s*(?:m|min|minute|minutes)", key)
    if m:
        return _TF_MAP.get(m.group(1))
    m = re.fullmatch(r"(\d+)\s*(?:h|hour|hours)", key)
    if m:
        return _TF_MAP.get(str(int(m.group(1)) * 60))
    up = key.upper()
    if up in {"M1", "M3", "M5", "M15", "M30", "M45", "H1", "H2", "H3", "H4", "D1", "W1", "MN1"}:
        return up
    return None


def _extract_symbol(*texts: str) -> Optional[str]:
    """Find a whitelisted symbol in the given texts (exchange prefixes stripped)."""
    for text in texts:
        if not text:
            continue
        for sym in _SYMBOL_TO_TEAM:
            # word-ish boundary before/after; allow exchange prefix (OANDA:XAUUSD)
            if re.search(rf"(?:^|[^A-Z])(?:[A-Z]+:)?{re.escape(sym)}(?![A-Z])", text.upper()):
                return sym
    return None


_BUY_WORDS = re.compile(r"\b(buy observation|buy|long|cross up)\b", re.IGNORECASE)
_SELL_WORDS = re.compile(r"\b(sell observation|sell|short|cross down)\b", re.IGNORECASE)


def _parse_pipe_format(body: str) -> Optional[Dict]:
    """RP|TICKER|tf=5|p0=..|p1=..|... -> {symbol?, tf?, direction?, strategy}."""
    if "RP|" not in body:
        return None
    fields = {}
    parts = body.replace("\r", "").replace("\n", "").split("|")
    for i, part in enumerate(parts):
        part = part.strip()
        if "=" in part:
            k, _, v = part.partition("=")
            fields[k.strip().lower()] = v.strip()
    plots = {}
    for n in range(20):
        v = fields.get(f"p{n}")
        if v is None:
            continue
        try:
            plots[n] = float(v)
        except ValueError:
            continue
    direction = None
    strategy = None
    confidence = None
    if plots:
        p0, p1 = plots.get(0), plots.get(1)
        if p0 and p0 != 0 and (p1 == 0 or p1 is None):
            direction, strategy, confidence = "BUY", "rocket_prime_plot0_email", 0.90
        elif p1 and p1 != 0 and (p0 == 0 or p0 is None):
            direction, strategy, confidence = "SELL", "rocket_prime_plot1_email", 0.90
    return {
        "symbol": fields.get("ticker"),
        "tf": _norm_tf(fields.get("tf")),
        "direction": direction,
        "strategy": strategy,
        "confidence": confidence,
        "plots": plots,
    }


def parse_alert(subject: str, body: str) -> Dict:
    """Extract symbol/direction/tf from a TV alert email. Never guesses."""
    out: Dict = {"symbol": None, "direction": None, "tf": None,
                 "strategy": None, "confidence": None}
    pipe = _parse_pipe_format(body)
    if pipe:
        out.update({k: pipe[k] for k in ("symbol", "direction", "tf", "strategy", "confidence")})
    sym = _extract_symbol(subject, body) or (
        pipe["symbol"] if pipe else None)
    if sym:
        out["symbol"] = sym
    if out["direction"]:
        return out
    haystack = f"{subject}\n{body}"
    buy = bool(_BUY_WORDS.search(haystack))
    sell = bool(_SELL_WORDS.search(haystack))
    if buy and not sell:
        out["direction"] = "BUY"
        out["strategy"] = "email_keyword_buy"
        out["confidence"] = 0.85
    elif sell and not buy:
        out["direction"] = "SELL"
        out["strategy"] = "email_keyword_sell"
        out["confidence"] = 0.85
    if out["tf"] is None:
        m = re.search(
            r"\b(\d+\s*(?:min(?:ute)?s?|h|hours?)|daily|weekly|monthly)\b", haystack, re.IGNORECASE)
        out["tf"] = _norm_tf(m.group(1)) if m else None
    return out


def _decode_mime_part(part) -> str:
    payload = part.get_payload(decode=True)
    if payload is None:
        return ""
    charset = part.get_content_charset() or "utf-8"
    try:
        return payload.decode(charset, errors="replace")
    except LookupError:
        return payload.decode("utf-8", errors="replace")


def extract_text(msg) -> Tuple[str, str]:
    """Return (subject, plain-text-ish body). HTML stripped crudely."""
    raw_subject = msg.get("Subject", "")
    try:
        subject = str(make_header(decode_header(raw_subject)))
    except Exception:
        subject = raw_subject
    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            if ctype == "text/plain":
                body += _decode_mime_part(part)
            elif ctype == "text/html" and not body.strip():
                body += re.sub(r"<[^>]+>", " ", _decode_mime_part(part))
    else:
        body = _decode_mime_part(msg)
    body = html_unescape(re.sub(r"[ \t]+", " ", body))
    return subject, body


# ───────────────────────── dedup state ─────────────────────────
class SeenIds:
    def __init__(self, cap: int):
        self.cap = cap
        self.ids = collections.OrderedDict()
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        if STATE_FILE.exists():
            try:
                for mid in json_loads_safe(STATE_FILE.read_text(encoding="utf-8"))[-cap:]:
                    self.ids[mid] = 0
            except Exception:
                pass

    def seen(self, mid: str) -> bool:
        return mid in self.ids

    def add(self, mid: str) -> None:
        self.ids[mid] = int(time.time())
        while len(self.ids) > self.cap:
            self.ids.popitem(last=False)
        try:
            STATE_FILE.write_text(json_dumps_safe(list(self.ids)), encoding="utf-8")
        except Exception:
            pass


def json_loads_safe(text: str):
    import json
    return json.loads(text)


def json_dumps_safe(obj) -> str:
    import json
    return json.dumps(obj)


# ───────────────────────── IMAP poller ─────────────────────────
def _connect(cfg: Dict) -> imaplib.IMAP4_SSL:
    M = imaplib.IMAP4_SSL(cfg["imap_host"], cfg["imap_port"])
    M.login(cfg["user"], cfg["password"])
    M.select("INBOX")
    return M


_SINCE_FMT = "%d-%b-%Y"


def poll_once(M: imaplib.IMAP4_SSL, cfg: Dict, seen: SeenIds) -> int:
    """Fetch unseen TV emails; returns number processed (written or rejected)."""
    since = (datetime.now(timezone.utc).timestamp()
             - cfg["search_hours_back"] * 3600)
    since_str = datetime.fromtimestamp(since, timezone.utc).strftime(_SINCE_FMT)
    status, data = M.search(None, f'(UNSEEN FROM "{cfg["from_filter"]}" SINCE {since_str})')
    if status != "OK":
        return 0
    ids = (data[0].split() if data and data[0] else [])
    processed = 0
    for num in ids:
        status, parts = M.fetch(num, "(RFC822)")
        if status != "OK" or not parts or parts[0] is None:
            continue
        msg_bytes = parts[0][1]
        try:
            msg = email_lib.message_from_bytes(msg_bytes)
            subject, body = extract_text(msg)
            mid = (msg.get("Message-ID") or f"{num.decode()}-{int(time.time())}").strip()
            date_hdr = msg.get("Date")
            try:
                alert_dt = parsedate_to_datetime(date_hdr) if date_hdr else None
            except Exception:
                alert_dt = None
            alert_ts = int(alert_dt.timestamp()) if alert_dt else None

            if seen.seen(mid):
                continue

            age_min = ((time.time() - alert_ts) / 60.0) if alert_ts else 0.0
            if alert_ts and age_min > cfg["max_age_minutes"]:
                LOG.info("SKIP stale email (%.1f min old) subj=%r", age_min, subject[:80])
                seen.add(mid)
                continue

            info = parse_alert(subject, body)
            symbol, direction, tf = info["symbol"], info["direction"], info["tf"]
            LOG.info("EMAIL subj=%r -> sym=%s dir=%s tf=%s src=%s",
                     subject[:70], symbol, direction, tf, info["strategy"])

            if not symbol or not direction:
                LOG.warning("REJECT unparsable email mid=%s subj=%r body[:100]=%r",
                            mid, subject[:60], body[:100])
                seen.add(mid)
                processed += 1
                continue

            res = write_tv_signal(
                symbol=symbol,
                direction=direction,
                confidence=info["confidence"],
                source="tradingview_email",
                tv_strategy=info["strategy"],
                tv_alert_ts=alert_ts,
                tv_timeframe=tf,
            )
            if res.get("ok"):
                LOG.info("TV→EA OK %s %s tf=%s conf=%.2f path=%s",
                         symbol, res["payload"]["direction"], tf,
                         res["payload"]["confidence"], res["path"])
                if cfg["telegram_echo"]:
                    try:
                        from ai_trading_agents.telegram_notifier import notify_signal
                        notify_signal(symbol, res["payload"]["direction"],
                                      res["payload"]["confidence"],
                                      note="email path")
                    except Exception as tg_e:
                        LOG.warning("telegram echo failed: %s", tg_e)
            else:
                LOG.warning("rejected %s %s err=%s", symbol, direction, res.get("error"))
            seen.add(mid)
            processed += 1
        except Exception:
            LOG.exception("failed processing message %s", num)
        finally:
            # mark as read regardless so UNSEEN search shrinks
            try:
                M.store(num, "+FLAGS", "\\Seen")
            except Exception:
                pass
    return processed


def main() -> int:
    _setup_logging()
    cfg = _cfg()
    if not cfg["user"] or not cfg["password"]:
        LOG.error("TV_EMAIL_USER / TV_EMAIL_APP_PASSWORD not set in config/.env")
        return 2
    if not cfg["enabled"]:
        LOG.warning("TV_EMAIL.enabled=False in config/settings.py — running anyway "
                    "(set True to silence this warning)")
    LOG.info("TV email poller starting: user=%s host=%s:%d poll=%ds",
             cfg["user"], cfg["imap_host"], cfg["imap_port"], cfg["poll_interval_s"])
    seen = SeenIds(cfg["dedup_window"])
    backoff = cfg["backoff_min_s"]
    while True:
        try:
            M = _connect(cfg)
            try:
                poll_once(M, cfg, seen)
            finally:
                try:
                    M.logout()
                except Exception:
                    pass
            backoff = cfg["backoff_min_s"]
            time.sleep(cfg["poll_interval_s"])
        except KeyboardInterrupt:
            LOG.info("shutdown requested")
            return 0
        except Exception as e:
            LOG.error("poll failed: %s — retrying in %ds", e, backoff)
            time.sleep(backoff)
            backoff = min(backoff * 2, cfg["backoff_max_s"])


if __name__ == "__main__":
    sys.exit(main())
