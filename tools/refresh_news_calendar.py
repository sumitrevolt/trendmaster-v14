"""Refresh config/news_calendar.json from ForexFactory's public JSON feed.

Source: https://nfs.faireconomy.media/ff_calendar_thisweek.json (public, no auth).

Maps FF schema -> brain schema:
  FF:    { "title": "Non-Farm Employment Change", "country": "USD",
           "date": "2026-05-09T12:30:00-04:00", "impact": "High", ... }
  brain: { "ts_utc": "2026-05-09T16:30:00Z", "event": "USD Non-Farm Employment Change",
           "impact": "high" }

Filters:
  - Only impact in {High} (brain only blocks 'high' currently)
  - Skips entries without a parseable date
  - Merges with existing calendar — keeps any hand-curated future entries

Run via Windows Task Scheduler weekly (Mon 06:00 IST).
"""
from __future__ import annotations
import json
import sys
import urllib.request as u
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CAL_PATH = ROOT / "config" / "news_calendar.json"
FF_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"


def _to_utc_iso(date_str: str) -> str | None:
    """Parse FF's ISO date with timezone and convert to UTC ISO with Z suffix."""
    try:
        dt = datetime.fromisoformat(date_str)
        if dt.tzinfo is None:
            return None
        return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except Exception:
        return None


def fetch_ff_calendar() -> list[dict]:
    req = u.Request(FF_URL, headers={"User-Agent": "Mozilla/5.0 TrendMaster"})
    with u.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode("utf-8"))


def main() -> int:
    print(f"=== Refreshing {CAL_PATH.name} ===")
    try:
        ff_data = fetch_ff_calendar()
        print(f"  fetched {len(ff_data)} events from ForexFactory")
    except Exception as e:
        print(f"FATAL: fetch failed: {e}")
        return 1

    new_events = []
    skipped_low = 0
    skipped_bad = 0
    for ev in ff_data:
        impact = (ev.get("impact") or "").strip().lower()
        if impact not in ("high",):
            skipped_low += 1
            continue
        ts_utc = _to_utc_iso(ev.get("date") or "")
        if ts_utc is None:
            skipped_bad += 1
            continue
        title = (ev.get("title") or "").strip()
        country = (ev.get("country") or "").strip()
        evt_name = f"{country} {title}" if country and not title.startswith(country) else title
        new_events.append({
            "ts_utc": ts_utc,
            "event": evt_name[:120],
            "impact": "high",
        })

    print(f"  high-impact kept: {len(new_events)}  low-skipped: {skipped_low}  bad-date: {skipped_bad}")

    # Backup existing
    if CAL_PATH.exists():
        bak = CAL_PATH.with_name(f"news_calendar.bak.{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
        bak.write_bytes(CAL_PATH.read_bytes())
        print(f"  backup: {bak.name}")

    # Merge: keep any FUTURE event from old calendar that isn't in new (hand-curated entries)
    existing = []
    if CAL_PATH.exists():
        try:
            existing = json.loads(CAL_PATH.read_text(encoding="utf-8"))
        except Exception:
            existing = []
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    new_keys = {(e["ts_utc"], e["event"]) for e in new_events}
    kept_old = [e for e in existing
                if isinstance(e, dict)
                and e.get("ts_utc", "") > now_iso
                and (e["ts_utc"], e.get("event", "")) not in new_keys
                and not str(e.get("event", "")).startswith("__HEADER__")]
    print(f"  kept {len(kept_old)} hand-curated future events from old calendar")

    merged = []
    # Header
    merged.append({
        "_note": (
            f"Auto-refreshed by tools/refresh_news_calendar.py at {datetime.now(timezone.utc).isoformat()}. "
            "Source: nfs.faireconomy.media (ForexFactory). High-impact only."
        ),
        "ts_utc": "1970-01-01T00:00:00Z",
        "event": "__HEADER__",
        "impact": "none",
    })
    merged.extend(sorted(new_events + kept_old, key=lambda x: x.get("ts_utc", "")))

    # Atomic write
    tmp = CAL_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(merged, indent=2), encoding="utf-8")
    tmp.replace(CAL_PATH)
    print(f"  wrote {len(merged)} entries -> {CAL_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
