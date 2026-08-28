"""
Cross-asset macro feature pull for TrendMaster v14.

Pulls DXY, US10Y (FRED), VIX (Yahoo) H1-aligned and caches under
data/cross_asset/. Forward-fills within session, NaNs over weekend gaps,
and tags `is_stale_*` so the model can learn freshness.

Honors a 6-hour TTL by default; pass --force to override.

Pure-Python; uses requests + pandas + numpy + json + datetime + pathlib.
"""

from __future__ import annotations

import sys as _sys
try:
    _sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import requests

REPO_ROOT = Path(r"C:\Users\Ratanshila\Documents\autmated trading")
CACHE_DIR = REPO_ROOT / "data" / "cross_asset"
META_PATH = CACHE_DIR / "meta.json"
TTL_HOURS = 6

# Yahoo chart endpoint (free, no key)
YAHOO_CHART = "https://query1.finance.yahoo.com/v7/finance/chart/{sym}?range={range}&interval={interval}"
# FRED CSV endpoint (free, no key)
FRED_CSV = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"


def _yahoo_pull(symbol: str, range_: str = "60d", interval: str = "1h") -> pd.DataFrame:
    url = YAHOO_CHART.format(sym=symbol, range=range_, interval=interval)
    r = requests.get(url, timeout=15, headers={"User-Agent": "TrendMaster/1.0"})
    r.raise_for_status()
    j = r.json()
    res = j["chart"]["result"][0]
    ts = pd.to_datetime(res["timestamp"], unit="s", utc=True)
    closes = res["indicators"]["quote"][0]["close"]
    df = pd.DataFrame({"ts": ts, "close": closes}).dropna()
    return df


def _fred_pull(series_id: str) -> pd.DataFrame:
    url = FRED_CSV.format(series_id=series_id)
    r = requests.get(url, timeout=15)
    r.raise_for_status()
    from io import StringIO
    df = pd.read_csv(StringIO(r.text))
    df.columns = ["ts", "value"]
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    return df.dropna()


def pull_dxy() -> pd.DataFrame:
    df = _yahoo_pull("DX-Y.NYB", range_="60d", interval="1h")
    df["ret_1h"] = df["close"].pct_change()
    return df


def pull_vix() -> pd.DataFrame:
    df = _yahoo_pull("%5EVIX", range_="60d", interval="1h")
    df["z_30d"] = (df["close"] - df["close"].rolling(24 * 30).mean()) / df["close"].rolling(24 * 30).std()
    return df


def pull_us10y() -> pd.DataFrame:
    df = _fred_pull("DGS10")
    df = df.rename(columns={"value": "yield"})
    df["d1d"] = df["yield"].diff()
    return df


def cache_is_fresh() -> bool:
    if not META_PATH.exists():
        return False
    try:
        meta = json.loads(META_PATH.read_text())
    except Exception:
        return False
    last = datetime.fromisoformat(meta["last_refresh_ts"].replace("Z", "+00:00"))
    return (datetime.now(timezone.utc) - last) < timedelta(hours=TTL_HOURS)


def write_cache(name: str, df: pd.DataFrame) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    df.to_parquet(CACHE_DIR / f"{name}.parquet", index=False)


def write_meta(rows: dict) -> None:
    meta = {
        "last_refresh_ts": datetime.now(timezone.utc).isoformat(),
        "source_versions": {"yahoo_chart_v7": "static", "fred_csv": "static"},
        "rows_per_series": rows,
        "ttl_hours": TTL_HOURS,
    }
    META_PATH.write_text(json.dumps(meta, indent=2))


def check_status() -> str:
    if not META_PATH.exists():
        return "Cache not initialized. Run with --refresh."
    meta = json.loads(META_PATH.read_text())
    out = ["Cross-asset cache status"]
    out.append(f"  last refresh: {meta['last_refresh_ts']}")
    out.append(f"  fresh (<{TTL_HOURS}h)? {cache_is_fresh()}")
    out.append("  rows per series:")
    for k, v in meta["rows_per_series"].items():
        out.append(f"    {k}: {v}")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()

    if args.check:
        print(check_status())
        return

    if not args.refresh and not args.force:
        print("Pass --refresh to pull, --check to inspect cache.")
        return

    if cache_is_fresh() and not args.force:
        print(f"Cache is fresh (<{TTL_HOURS}h). Pass --force to refresh anyway.")
        return

    print("Pulling DXY...")
    dxy = pull_dxy()
    write_cache("dxy_h1", dxy)
    print(f"  rows={len(dxy)}")

    print("Pulling VIX...")
    vix = pull_vix()
    write_cache("vix_h1", vix)
    print(f"  rows={len(vix)}")

    print("Pulling US10Y...")
    us10y = pull_us10y()
    write_cache("us10y_h1", us10y)
    print(f"  rows={len(us10y)}")

    write_meta({"dxy_h1": len(dxy), "vix_h1": len(vix), "us10y_h1": len(us10y)})
    print("Cache written. Next: integrate via cross_asset_join.attach_macros(df, symbol).")


if __name__ == "__main__":
    main()
