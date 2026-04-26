"""Smart-money cross-asset feature joins (Phase B1 + B1.5 hotfix, data plumbing only).

This module fetches the two slow-moving "smart-money" datasets identified
in the Phase A2 cross-asset edge report and aligns them onto an H1 symbol
DataFrame. It does NOT touch FEATURE_COLS, infer_ml, or any brain gate;
Phase B2 is responsible for wiring these features into model training and
inference.

CFTC report tier (Phase B1.5 correction)
----------------------------------------
We use the CFTC LEGACY (futures-only) report endpoint
``6dca-aqww.json``. That report exposes Non-Commercial / Commercial /
Non-Reportable categories -- NOT Managed Money / Lev Money / Other
Reportable, which only live on the Disaggregated (``72hf-taqq``) and
TFF endpoints. Phase B1 originally tried to read ``m_money_*`` columns
from the legacy endpoint, which silently produced empty result sets;
Phase B1.5 corrects this to ``noncomm_positions_long_all`` /
``noncomm_positions_short_all``, matching what Phase A2's correlation
study (reports/influencer_correlation_phaseA2_2026-04-26.md) used to
find EDGE-class signals on GC/SI/6E/6J/6C/CL/BTC. The legacy report
gives ~16 years of weekly history (851 rows on flagship contracts);
that long history is the explicit reason Phase A2 chose legacy over
disaggregated.

The constructed signal is "Non-Commercial Net" =
non-commercial longs - non-commercial shorts, which in legacy COT
parlance is the "speculator" category and is what the literature and
Phase A2 refer to interchangeably. The variable name ``spec_net``
reflects this; we are not feeding Disaggregated managed-money data
despite the conceptual proximity.

Data sources
------------
1. CFTC Commitments of Traders (legacy_fut, weekly):
       https://publicreporting.cftc.gov/resource/6dca-aqww.json
   Released Friday 15:30 ET for the prior Tuesday's positions.
   Publish-lag-aware: at H1 timestamp T, the visible row is the one
   whose publish_ts (= report_date Friday + business-days offset, time
   20:30 UTC) is <= T.

2. EIA Weekly Natural Gas Storage v2 (NG.NW2_EPG0_SWO_R48_BCF.W):
       https://api.eia.gov/v2/natural-gas/stor/wkly/data/
   Released Thursday 10:30 ET (= 14:30 UTC).

Caching
-------
data/external/*.parquet (or *.csv if pyarrow is unavailable). Stale-by-7-day
rule: a cache file whose mtime is older than CACHE_STALE_DAYS triggers a
refetch. force_refresh bypasses the rule.

Path discipline
---------------
This module lives inside the ai_trading_agents/ junction. We MUST use
Path(__file__).parent.parent (NOT .resolve()) -- see CLAUDE.md "junction
trap" for the postmortem.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, time
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

try:
    import requests  # type: ignore
except ImportError:  # pragma: no cover - requests is in the project deps
    requests = None  # type: ignore[assignment]

log = logging.getLogger(__name__)

# IMPORTANT: do NOT use Path(__file__).resolve() inside this module -- the
# ai_trading_agents/ folder is a Windows NTFS junction and .resolve() will
# walk it to C:\ and break every config-file lookup. See CLAUDE.md.
PROJECT_ROOT = Path(__file__).parent.parent
EXTERNAL_DIR = PROJECT_ROOT / "data" / "external"

# CFTC market codes (Socrata returns contract_market_name as a string we
# match by case-insensitive substring). The mapping is intentionally
# explicit so a Socrata schema/name change is loud rather than silent.
DEFAULT_COT_CONTRACTS: list[str] = ["GC", "SI", "6E", "6J", "6C", "CL", "BTC"]
COT_CONTRACT_MARKET_PATTERNS: dict[str, list[str]] = {
    "GC": ["gold"],
    "SI": ["silver"],
    "6E": ["euro fx"],
    "6J": ["japanese yen"],
    "6C": ["canadian dollar"],
    # Phase B1.5: drop the bare "wti" pattern -- it matched
    # "WTI-PHYSICAL - NEW YORK MERCANTILE EXCHANGE" which only has
    # 220 weekly rows (2022 onwards). The classic CL futures contract
    # has the pattern below and gives the full 16-year history.
    "CL": ["crude oil, light sweet"],
    "BTC": ["bitcoin"],
}

Z_WINDOW = 52  # weeks
CACHE_STALE_DAYS = 7
USER_AGENT = "TrendMaster-research/1.0"
REQUEST_TIMEOUT_SEC = 30

CFTC_ENDPOINT = "https://publicreporting.cftc.gov/resource/6dca-aqww.json"
EIA_NG_ENDPOINT = "https://api.eia.gov/v2/natural-gas/stor/wkly/data/"
EIA_NG_SERIES_ID = "NW2_EPG0_SWO_R48_BCF.W"

# COT publish convention: Friday 15:30 ET == 20:30 UTC (winter; close
# enough year-round for our forward-fill -- we use 20:30 UTC year-round).
COT_PUBLISH_TIME_UTC = time(20, 30)
# EIA publish convention: Thursday 10:30 ET == 14:30 UTC.
EIA_PUBLISH_TIME_UTC = time(14, 30)


class CrossAssetSchemaError(RuntimeError):
    """Raised when an upstream data source returns an unexpected schema."""


class CrossAssetConfigError(RuntimeError):
    """Raised when required configuration (API keys, etc.) is missing."""


# ---------------------------------------------------------------------------
# Cache helpers


def _ensure_external_dir() -> Path:
    EXTERNAL_DIR.mkdir(parents=True, exist_ok=True)
    return EXTERNAL_DIR


def _cache_is_fresh(path: Path) -> bool:
    if not path.exists():
        return False
    age = datetime.now().timestamp() - path.stat().st_mtime
    return age < CACHE_STALE_DAYS * 86400


def _read_cache(path: Path) -> pd.DataFrame | None:
    if not path.exists():
        return None
    try:
        if path.suffix == ".parquet":
            try:
                return pd.read_parquet(path)
            except Exception:
                # pyarrow may be missing; try sibling CSV.
                csv_path = path.with_suffix(".csv")
                if csv_path.exists():
                    return pd.read_csv(csv_path, index_col=0, parse_dates=[0])
                return None
        return pd.read_csv(path, index_col=0, parse_dates=[0])
    except Exception as exc:  # pragma: no cover - defensive
        log.warning("Failed to read cache %s: %s", path, exc)
        return None


def _write_cache(df: pd.DataFrame, path: Path) -> None:
    _ensure_external_dir()
    try:
        if path.suffix == ".parquet":
            try:
                df.to_parquet(path)
                return
            except Exception as exc:
                log.warning(
                    "Parquet write failed (%s); falling back to CSV alongside %s",
                    exc,
                    path,
                )
                csv_path = path.with_suffix(".csv")
                df.to_csv(csv_path)
                return
        df.to_csv(path)
    except Exception as exc:  # pragma: no cover - defensive
        log.warning("Failed to write cache %s: %s", path, exc)


def _http_get_json(url: str, params: dict | None = None) -> object:
    if requests is None:  # pragma: no cover - requests is project dep
        raise CrossAssetConfigError("requests library not available; cannot fetch cross-asset data")
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    resp = requests.get(url, params=params, headers=headers, timeout=REQUEST_TIMEOUT_SEC)
    resp.raise_for_status()
    return resp.json()


# ---------------------------------------------------------------------------
# CFTC COT


_COT_REQUIRED_COLS = (
    "report_date_as_yyyy_mm_dd",
    "contract_market_name",
    # Phase B1.5: the legacy_fut endpoint exposes Non-Commercial /
    # Commercial / Non-Reportable categories. Managed-Money columns
    # (m_money_*) only exist on the Disaggregated (72hf-taqq) endpoint
    # which Phase A2 deliberately avoided because of its shorter history.
    "noncomm_positions_long_all",
    "noncomm_positions_short_all",
)


def _match_contract(contract_market_name: str, code: str) -> bool:
    name = (contract_market_name or "").lower()
    return any(p in name for p in COT_CONTRACT_MARKET_PATTERNS.get(code, []))


def _cot_records_to_frame(records: list[dict], contracts: Iterable[str]) -> pd.DataFrame:
    if not records:
        raise CrossAssetSchemaError("CFTC endpoint returned empty record list")
    sample = records[0]
    for col in _COT_REQUIRED_COLS:
        if col not in sample:
            raise CrossAssetSchemaError(
                f"CFTC response missing required column '{col}'. Got keys: {sorted(sample.keys())[:10]}..."
            )

    contracts = list(contracts)
    rows = []
    for rec in records:
        try:
            longs = float(rec["noncomm_positions_long_all"])
            shorts = float(rec["noncomm_positions_short_all"])
        except (TypeError, ValueError):
            continue
        rep_date = pd.to_datetime(rec["report_date_as_yyyy_mm_dd"], errors="coerce")
        if pd.isna(rep_date):
            continue
        market = rec.get("contract_market_name", "")
        for code in contracts:
            if _match_contract(market, code):
                rows.append(
                    {
                        "report_date": rep_date.normalize(),
                        "contract": code,
                        "spec_net": longs - shorts,
                    }
                )
                break

    if not rows:
        raise CrossAssetSchemaError(
            f"CFTC response had no rows matching any of the requested contract codes {contracts}"
        )

    df = pd.DataFrame(rows)
    df = df.sort_values("report_date").drop_duplicates(subset=["report_date", "contract"], keep="last")
    wide = df.pivot(index="report_date", columns="contract", values="spec_net")
    wide = wide.sort_index()

    out = pd.DataFrame(index=wide.index)
    for code in contracts:
        if code not in wide.columns:
            out[f"{code}_spec_delta_z"] = np.nan
            continue
        s = wide[code]
        roll = s.rolling(Z_WINDOW, min_periods=Z_WINDOW)
        z = (s - roll.mean()) / roll.std(ddof=0)
        out[f"{code}_spec_delta_z"] = z
    out.index.name = "report_date"
    return out


def fetch_cot_weekly(
    contracts: list[str] | None = None,
    cache_path: Path | None = None,
    force_refresh: bool = False,
) -> pd.DataFrame:
    """Fetch CFTC Commitments of Traders weekly data.

    Returns a DataFrame indexed by report_date_as_yyyy_mm_dd
    (datetime64[ns]), columns "<CODE>_spec_delta_z" -- a 52-week rolling
    z-score of (non-commercial longs - non-commercial shorts) from the
    CFTC LEGACY (futures-only) report. Sorted ascending.

    Note: legacy_fut "non-commercial" is the speculator category in
    classical COT parlance; this is what Phase A2's correlation study
    used and what generated the EDGE-class verdicts in the report.

    Parameters
    ----------
    contracts : list[str] | None
        CFTC market codes (default: DEFAULT_COT_CONTRACTS).
    cache_path : Path | None
        Path to parquet cache. Default:
        ``data/external/cot_weekly_cache.parquet``.
    force_refresh : bool
        Bypass the stale-by-7-day cache rule.

    Raises
    ------
    CrossAssetSchemaError
        If the upstream Socrata response is missing a required column.
    """
    contracts = list(contracts) if contracts else list(DEFAULT_COT_CONTRACTS)
    cache_path = cache_path or (EXTERNAL_DIR / "cot_weekly_cache.parquet")

    if not force_refresh and _cache_is_fresh(cache_path):
        cached = _read_cache(cache_path)
        if cached is not None and not cached.empty:
            cached.index = pd.to_datetime(cached.index)
            return cached.sort_index()

    # Phase B1.5: paginate per contract using a SoQL $where clause -- the
    # default Socrata $limit (5000 records across the whole dataset) only
    # reaches back ~36 weeks because the universe spans ~140 markets per
    # week. Phase A2 found that filtering by market_and_exchange_names per
    # contract with $limit=50000 reliably returns the full 16-year history
    # (851 weekly rows on flagship contracts).
    all_records: list[dict] = []
    for code in contracts:
        patterns = COT_CONTRACT_MARKET_PATTERNS.get(code, [])
        if not patterns:
            log.warning("No COT pattern for contract code %s; skipping", code)
            continue
        # Use a like-style filter on contract_market_name; SoQL doesn't
        # support case-insensitive LIKE so we upper-case the pattern (the
        # dataset stores names in upper case).
        # Wrap each pattern with % wildcards.
        like_clauses = " OR ".join(f"upper(contract_market_name) like '%{p.upper()}%'" for p in patterns)
        where = f"({like_clauses}) AND report_date_as_yyyy_mm_dd >= '2010-01-01T00:00:00.000'"
        params = {
            "$where": where,
            "$select": (
                "report_date_as_yyyy_mm_dd,contract_market_name,noncomm_positions_long_all,noncomm_positions_short_all"
            ),
            "$order": "report_date_as_yyyy_mm_dd ASC",
            "$limit": "50000",
        }
        try:
            recs = _http_get_json(CFTC_ENDPOINT, params=params)
        except Exception as exc:
            log.warning("CFTC fetch for %s failed (%s); will try other contracts", code, exc)
            continue
        if isinstance(recs, list) and recs:
            all_records.extend(recs)

    if not all_records:
        log.warning("CFTC: no records fetched for any contract; falling back to cache if any")
        cached = _read_cache(cache_path)
        if cached is not None:
            cached.index = pd.to_datetime(cached.index)
            return cached.sort_index()
        raise CrossAssetSchemaError("CFTC fetch returned no records for any requested contract")

    df = _cot_records_to_frame(all_records, contracts)
    _write_cache(df, cache_path)
    return df


# ---------------------------------------------------------------------------
# EIA natural-gas storage


_EIA_REQUIRED_COLS = ("period", "value")


def _eia_records_to_frame(records: list[dict]) -> pd.DataFrame:
    if not records:
        raise CrossAssetSchemaError("EIA endpoint returned empty record list")
    sample = records[0]
    for col in _EIA_REQUIRED_COLS:
        if col not in sample:
            raise CrossAssetSchemaError(
                f"EIA response missing required column '{col}'. Got keys: {sorted(sample.keys())[:10]}..."
            )

    rows = []
    for rec in records:
        try:
            val = float(rec["value"])
        except (TypeError, ValueError):
            continue
        period = pd.to_datetime(rec["period"], errors="coerce")
        if pd.isna(period):
            continue
        rows.append({"period": period.normalize(), "ng_storage_bcf": val})
    if not rows:
        raise CrossAssetSchemaError("EIA response yielded no parseable rows")

    df = pd.DataFrame(rows).sort_values("period").drop_duplicates(subset=["period"], keep="last")
    df = df.set_index("period")
    df["ng_storage_delta_bcf"] = df["ng_storage_bcf"].diff()
    roll = df["ng_storage_delta_bcf"].rolling(Z_WINDOW, min_periods=Z_WINDOW)
    df["ng_storage_delta_z"] = (df["ng_storage_delta_bcf"] - roll.mean()) / roll.std(ddof=0)
    return df


def fetch_eia_ng_storage(
    cache_path: Path | None = None,
    force_refresh: bool = False,
    api_key: str | None = None,
) -> pd.DataFrame:
    """Fetch EIA Weekly Natural Gas Storage (US Lower 48 working gas).

    Returns a DataFrame indexed by period (datetime64[ns]) with columns:

      * ng_storage_bcf
      * ng_storage_delta_bcf  (week-over-week change)
      * ng_storage_delta_z    (52-week rolling z-score of delta)

    Parameters
    ----------
    cache_path : Path | None
        Default: ``data/external/eia_ng_cache.parquet``.
    force_refresh : bool
        Bypass the stale-by-7-day cache rule.
    api_key : str | None
        EIA Open Data v2 API key. If None, reads ``EIA_API_KEY`` env var.

    Raises
    ------
    CrossAssetConfigError
        If no API key is available (and force_refresh is True or cache
        is stale/missing).
    """
    cache_path = cache_path or (EXTERNAL_DIR / "eia_ng_cache.parquet")

    if not force_refresh and _cache_is_fresh(cache_path):
        cached = _read_cache(cache_path)
        if cached is not None and not cached.empty:
            cached.index = pd.to_datetime(cached.index)
            return cached.sort_index()

    if api_key is None:
        api_key = os.environ.get("EIA_API_KEY")
    if not api_key:
        raise CrossAssetConfigError(
            "EIA_API_KEY not set. Register at "
            "https://www.eia.gov/opendata/register.php (free) and either "
            "export EIA_API_KEY=... or pass api_key= explicitly."
        )

    params = {
        "api_key": api_key,
        "frequency": "weekly",
        "data[0]": "value",
        "facets[series][]": EIA_NG_SERIES_ID,
        "sort[0][column]": "period",
        "sort[0][direction]": "desc",
        "offset": "0",
        "length": "5000",
    }
    try:
        payload = _http_get_json(EIA_NG_ENDPOINT, params=params)
    except Exception as exc:
        log.warning("EIA fetch failed (%s); falling back to cache if any", exc)
        cached = _read_cache(cache_path)
        if cached is not None:
            cached.index = pd.to_datetime(cached.index)
            return cached.sort_index()
        raise

    if not isinstance(payload, dict):
        raise CrossAssetSchemaError(f"EIA endpoint returned non-dict payload (type={type(payload).__name__})")
    response = payload.get("response")
    if not isinstance(response, dict):
        raise CrossAssetSchemaError(f"EIA payload missing 'response' object; top-level keys: {sorted(payload.keys())}")
    records = response.get("data")
    if not isinstance(records, list):
        raise CrossAssetSchemaError(f"EIA payload 'response.data' is not a list; got type={type(records).__name__}")

    df = _eia_records_to_frame(records)
    _write_cache(df, cache_path)
    return df


# ---------------------------------------------------------------------------
# H1 alignment with publish-lag


def _business_day_offset(d: pd.Timestamp, n: int) -> pd.Timestamp:
    """Return d shifted forward by n business days (Mon-Fri).

    n=0 returns d unchanged. We don't honour US federal holidays here --
    publish-lag is mostly Mon-Fri and a once-a-year holiday slip is
    smaller than the 1-week update cadence of these datasets.
    """
    return d + pd.tseries.offsets.BusinessDay(n)


def _cot_publish_ts(report_date: pd.Timestamp) -> pd.Timestamp:
    """Compute the UTC publish timestamp for a COT report_date.

    COT report_date is the Tuesday-of-record. The release is the
    following Friday at 15:30 ET (== 20:30 UTC, ignoring DST). That is
    3 business days after Tuesday.
    """
    day = _business_day_offset(report_date.normalize(), 3)
    return pd.Timestamp.combine(day.date(), COT_PUBLISH_TIME_UTC).tz_localize("UTC")


def _eia_publish_ts(period: pd.Timestamp) -> pd.Timestamp:
    """Compute the UTC publish timestamp for an EIA NG period.

    EIA NG period is the Friday week-ending. The release is the
    following Thursday at 10:30 ET (== 14:30 UTC). Friday + 6 calendar
    days lands on Thursday.
    """
    day = period.normalize() + pd.Timedelta(days=6)
    return pd.Timestamp.combine(day.date(), EIA_PUBLISH_TIME_UTC).tz_localize("UTC")


def _ffill_with_publish_lag(
    target_index: pd.DatetimeIndex,
    src_df: pd.DataFrame,
    publish_ts_fn,
) -> pd.DataFrame:
    """Forward-fill src_df rows onto target_index using publish_ts_fn.

    For each row in src_df, compute publish_ts; reindex to the union of
    target_index and publish_ts and ffill, then drop back to target_index.
    Rows not yet published as of a target timestamp remain NaN.
    """
    if src_df is None or src_df.empty:
        return pd.DataFrame(index=target_index, columns=[])
    src = src_df.copy()
    publish_idx = pd.DatetimeIndex(
        [publish_ts_fn(pd.Timestamp(ts)) for ts in src.index],
        name="publish_ts",
    )
    src.index = publish_idx
    src = src.sort_index()
    if target_index.tz is None:
        target_index = pd.DatetimeIndex(target_index).tz_localize("UTC")
    aligned = src.reindex(target_index.union(src.index)).sort_index().ffill().reindex(target_index)
    return aligned


def align_to_h1(
    symbol_h1_df: pd.DataFrame,
    *,
    include_smartmoney: bool = False,
    cot_df: pd.DataFrame | None = None,
    eia_df: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Align cross-asset data onto an H1 symbol DataFrame.

    Default (include_smartmoney=False) is a no-op: returns the input
    unchanged so existing brain callers keep working without code
    changes. Phase B2 will flip this default once FEATURE_COLS is wired.

    With include_smartmoney=True, forward-fills COT and EIA values onto
    each H1 timestamp, respecting the publish-lag of each source:

      * COT: publish_ts = report_date + 3 business days at 20:30 UTC
      * EIA: publish_ts = period (Friday) + 6 days at 14:30 UTC

    Parameters
    ----------
    symbol_h1_df : pd.DataFrame
        DataFrame indexed by tz-aware UTC H1 timestamps. Not mutated.
    include_smartmoney : bool
        Enable COT/EIA forward-fill (default False).
    cot_df, eia_df : pd.DataFrame | None
        Pre-fetched frames; if None and include_smartmoney=True, they
        are fetched via ``fetch_cot_weekly()`` / ``fetch_eia_ng_storage()``.

    Returns
    -------
    pd.DataFrame
        New DataFrame; with include_smartmoney=False, byte-equal to input.
    """
    if not include_smartmoney:
        return symbol_h1_df

    if cot_df is None:
        cot_df = fetch_cot_weekly()
    if eia_df is None:
        try:
            eia_df = fetch_eia_ng_storage()
        except CrossAssetConfigError:
            log.info("EIA_API_KEY not configured; skipping NG storage features")
            eia_df = pd.DataFrame()

    out = symbol_h1_df.copy()
    target = pd.DatetimeIndex(out.index)
    if target.tz is None:
        target = target.tz_localize("UTC")

    if cot_df is not None and not cot_df.empty:
        cot_aligned = _ffill_with_publish_lag(target, cot_df, _cot_publish_ts)
        for col in cot_aligned.columns:
            out[col] = cot_aligned[col].to_numpy()

    if eia_df is not None and not eia_df.empty:
        eia_aligned = _ffill_with_publish_lag(target, eia_df, _eia_publish_ts)
        for col in eia_aligned.columns:
            out[col] = eia_aligned[col].to_numpy()
    else:
        # Phase B1.5: keep the column contract stable. If EIA is unavailable
        # (no API key, network down, etc.) we still surface the expected
        # ng_storage_delta_z column as all-NaN so downstream feature builders
        # (e.g. feature_cols_v2.build_features_v2) don't error. dropna() in
        # the walkforward then removes those rows / columns naturally.
        if "ng_storage_delta_z" not in out.columns:
            out["ng_storage_delta_z"] = np.nan

    return out


__all__ = [
    "CrossAssetSchemaError",
    "CrossAssetConfigError",
    "DEFAULT_COT_CONTRACTS",
    "Z_WINDOW",
    "CACHE_STALE_DAYS",
    "fetch_cot_weekly",
    "fetch_eia_ng_storage",
    "align_to_h1",
]
