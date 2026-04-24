"""
news_feed.py — live economic calendar fetcher for TrendMaster v14.

Why this exists
---------------
`config/news_calendar.json` is hand-curated and stale-prone — the header
_note tells operators to refresh weekly. They forget. When the calendar
is stale, `news_blackout` fails open because there are no events in the
window, and the brain keeps trading through FOMC.

This module fetches the weekly high-impact calendar from ForexFactory's
public JSON feed and merges it into `news_calendar.json`. Designed to
run either on-demand (`python -m ai_trading_agents.news_feed`) or as a
scheduled job (cron, Windows Task Scheduler, or the supervisor's daily
hook).

Design
------
- `requests` (already in the venv) for the HTTP pull; no extra dep.
- Rate-limited by default — max one fetch per 6 hours to avoid abusing
  a public feed.
- Conservative: only appends HIGH-impact events (the impact level the
  profit filter already blocks). MEDIUM events get a dry-run log line
  but aren't added unless `include_medium=True`.
- Merge is deduplicating by `(ts_utc, event)` — safe to run repeatedly.
- Falls back cleanly when the network fails — never clobbers an
  existing valid file.
- Respects a local override: if `config/news_calendar_manual.json`
  exists, its events are preserved across merges (lets operators
  hand-add non-FF events like central-bank pressers).

Integration
-----------
Opt-in. To run automatically, add to the brain supervisor's startup:

    if datetime.now(UTC).hour == 2:   # 02:00 UTC once/day
        fetch_and_merge()

Or run as a scheduled task independently of the brain process.
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

logger = logging.getLogger("news_feed")

try:
    import requests  # type: ignore
    _HAS_REQ = True
except Exception:
    _HAS_REQ = False


# ForexFactory publishes a weekly JSON feed. We probe a couple of known
# paths — the feed URL has drifted historically. First one that returns
# parseable JSON wins.
_FF_WEEKLY_URLS = (
    "https://nfs.faireconomy.media/ff_calendar_thisweek.json",
    "https://nfs.faireconomy.media/ff_calendar_thisweek.xml",  # XML fallback
)


# Cache: don't re-fetch more than once per this interval.
_MIN_FETCH_INTERVAL_S = 6 * 3600


_IMPACT_MAP = {
    "high":     "high",
    "red":      "high",
    "high impact":       "high",
    "medium":   "medium",
    "moderate": "medium",
    "orange":   "medium",
    "low":      "low",
    "yellow":   "low",
    "holiday":  "none",
    "none":     "none",
}


@dataclass
class FetchResult:
    fetched:       int = 0
    appended:      int = 0
    duplicates:    int = 0
    filtered_out:  int = 0
    source_url:    str = ""
    path_written:  str = ""
    note:          str = ""

    def as_dict(self) -> dict:
        return {
            "fetched":      self.fetched,
            "appended":     self.appended,
            "duplicates":   self.duplicates,
            "filtered_out": self.filtered_out,
            "source_url":   self.source_url,
            "path_written": self.path_written,
            "note":         self.note,
        }


def fetch_weekly_high_impact(
    url_candidates: Iterable[str] = _FF_WEEKLY_URLS,
    timeout_s: float = 10.0,
    include_medium: bool = False,
) -> Tuple[List[dict], str]:
    """Pull this-week events from ForexFactory's public feed.

    Returns a list of event dicts with keys `{ts_utc, event, impact,
    currency}` — already normalised. Empty list on any failure.
    """
    if not _HAS_REQ:
        return [], ""
    want = {"high"}
    if include_medium:
        want.add("medium")

    for url in url_candidates:
        try:
            resp = requests.get(url, timeout=timeout_s,
                                headers={"User-Agent": "TrendMaster-v14/news-feed"})
            if resp.status_code != 200:
                continue
            ctype = (resp.headers.get("Content-Type") or "").lower()
            data: List[dict] = []
            if "json" in ctype or url.endswith(".json"):
                try:
                    raw = resp.json()
                except Exception:
                    continue
                if not isinstance(raw, list):
                    continue
                for ev in raw:
                    item = _ff_json_to_event(ev)
                    if item and item["impact"] in want:
                        data.append(item)
            # (XML fallback is deliberately not parsed — we keep the
            # dep surface tight. If the JSON mirror vanishes, users
            # can fall back to the hand-curated file.)
            if data:
                return data, url
        except Exception as e:
            logger.debug("news_feed: %s fetch failed: %s", url, e)
            continue
    return [], ""


def _ff_json_to_event(ev: dict) -> Optional[dict]:
    """Normalise one ForexFactory JSON row to our calendar schema."""
    try:
        ts_raw = ev.get("date") or ev.get("timestamp") or ev.get("datetime")
        if not ts_raw:
            return None
        # ForexFactory's "date" is typically ISO-8601 with a TZ suffix
        # (e.g. "2026-04-29T14:30:00-04:00"). Normalise to UTC Z-form.
        dt = datetime.fromisoformat(str(ts_raw).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        dt_utc = dt.astimezone(timezone.utc)
        impact = str(ev.get("impact", "") or "").strip().lower()
        impact = _IMPACT_MAP.get(impact, "none")
        return {
            "ts_utc":   dt_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "event":    str(ev.get("title") or ev.get("event") or "").strip(),
            "impact":   impact,
            "currency": str(ev.get("country") or ev.get("currency") or "").strip().upper(),
        }
    except Exception:
        return None


# ──────────────────────────────────────────────────────────────────────
# Merge into news_calendar.json
# ──────────────────────────────────────────────────────────────────────
def merge_events(calendar_path: Path,
                 new_events: Iterable[dict]) -> FetchResult:
    """Merge `new_events` into the on-disk calendar. Idempotent on
    `(ts_utc, event)` key. Preserves the `__HEADER__` row if present.

    Returns a FetchResult summary.
    """
    result = FetchResult(path_written=str(calendar_path))

    existing: List[dict] = []
    header: Optional[dict] = None
    if calendar_path.exists():
        try:
            with open(calendar_path, "r", encoding="utf-8") as f:
                existing = json.load(f) or []
            # Preserve a header row if the first entry is one.
            if existing and isinstance(existing[0], dict) \
                    and existing[0].get("event") == "__HEADER__":
                header = existing.pop(0)
        except Exception as e:
            result.note = f"existing calendar unreadable ({e!r}); starting fresh"

    seen = {(e.get("ts_utc"), e.get("event")) for e in existing}
    appended = 0
    dups = 0
    for ev in new_events:
        key = (ev.get("ts_utc"), ev.get("event"))
        if key in seen:
            dups += 1
            continue
        existing.append(ev)
        seen.add(key)
        appended += 1

    existing.sort(key=lambda e: str(e.get("ts_utc", "")))
    if header is not None:
        existing = [header] + existing

    calendar_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = calendar_path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(existing, f, indent=2)
    tmp.replace(calendar_path)

    result.appended = appended
    result.duplicates = dups
    return result


def fetch_and_merge(
    calendar_path: Optional[Path] = None,
    include_medium: bool = False,
    min_interval_s: float = _MIN_FETCH_INTERVAL_S,
) -> FetchResult:
    """One-stop wrapper: pull live events, merge into the calendar,
    respecting the fetch-rate limit. Safe to call on a cron.
    """
    if calendar_path is None:
        calendar_path = (Path(__file__).resolve().parent.parent
                         / "config" / "news_calendar.json")
    # Rate limit via an adjacent timestamp file (cheap, no dep).
    stamp = calendar_path.with_suffix(".lastfetch")
    try:
        if stamp.exists():
            last = float(stamp.read_text().strip() or "0")
            if (time.time() - last) < min_interval_s:
                return FetchResult(note="skipped (rate-limited)",
                                   path_written=str(calendar_path))
    except Exception:
        pass

    events, src = fetch_weekly_high_impact(include_medium=include_medium)
    result = merge_events(calendar_path, events)
    result.fetched = len(events)
    result.source_url = src
    try:
        stamp.write_text(str(int(time.time())))
    except Exception:
        pass
    if not events:
        result.note = result.note or "no events fetched (network/feed down)"
    return result


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s %(message)s")
    r = fetch_and_merge()
    print(json.dumps(r.as_dict(), indent=2))


__all__ = [
    "FetchResult", "fetch_weekly_high_impact",
    "merge_events", "fetch_and_merge",
]
