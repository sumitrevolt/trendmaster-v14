"""Unit tests for ai_trading_agents.cross_asset_join (Phase B1 plumbing).

All tests run offline -- requests.get is patched. Cache files use
``tmp_path`` to avoid touching the real ``data/external/``.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, time, timezone
from pathlib import Path
from unittest import mock

import numpy as np
import pandas as pd
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from ai_trading_agents import cross_asset_join as caj  # noqa: E402
from ai_trading_agents.cross_asset_join import (  # noqa: E402
    CrossAssetConfigError,
    CrossAssetSchemaError,
    Z_WINDOW,
    align_to_h1,
    fetch_cot_weekly,
    fetch_eia_ng_storage,
)


# ---------------------------------------------------------------------------
# helpers


def _h1_index(ts_list: list[str]) -> pd.DatetimeIndex:
    return pd.DatetimeIndex([pd.Timestamp(t).tz_localize("UTC") for t in ts_list])


def _make_synthetic_cot_records(n_weeks: int, contracts: list[str]) -> list[dict]:
    """Synthesize n_weeks Tuesday report_dates x len(contracts) records."""
    contract_market_names = {
        "GC": "GOLD - COMMODITY EXCHANGE INC.",
        "SI": "SILVER - COMMODITY EXCHANGE INC.",
        "6E": "EURO FX - CHICAGO MERCANTILE EXCHANGE",
    }
    base = pd.Timestamp("2024-01-02")  # Tuesday
    records = []
    rng = np.random.default_rng(42)
    for week in range(n_weeks):
        rep_date = base + pd.Timedelta(days=7 * week)
        for c in contracts:
            longs = float(50_000 + rng.normal(0, 5_000))
            shorts = float(30_000 + rng.normal(0, 5_000))
            records.append(
                {
                    "report_date_as_yyyy_mm_dd": rep_date.strftime("%Y-%m-%dT00:00:00.000"),
                    "contract_market_name": contract_market_names[c],
                    "m_money_positions_long_all": str(longs),
                    "m_money_positions_short_all": str(shorts),
                }
            )
    return records


# ---------------------------------------------------------------------------
# 1. align_to_h1 default is a strict no-op


def test_align_default_is_noop():
    idx = _h1_index(["2026-01-09 10:00", "2026-01-09 11:00", "2026-01-09 12:00"])
    df = pd.DataFrame({"close": [1.0, 2.0, 3.0], "volume": [10, 20, 30]}, index=idx)
    out = align_to_h1(df)
    pd.testing.assert_frame_equal(out, df)


# ---------------------------------------------------------------------------
# 2. fetch_cot_weekly: cache is fresh -> no HTTP call


def test_fetch_cot_uses_cache_when_fresh(tmp_path):
    cache = tmp_path / "cot.parquet"
    idx = pd.DatetimeIndex(pd.date_range("2025-01-01", periods=3, freq="7D"), name="report_date")
    cached_df = pd.DataFrame({"GC_spec_delta_z": [0.1, 0.2, 0.3]}, index=idx)
    # Try parquet, fall back to CSV (project may not have pyarrow).
    try:
        cached_df.to_parquet(cache)
    except Exception:
        cache = tmp_path / "cot.csv"
        cached_df.to_csv(cache)

    with mock.patch.object(caj, "requests") as mock_requests:
        mock_requests.get.side_effect = AssertionError("HTTP must not be called")
        out = fetch_cot_weekly(cache_path=cache)
    assert "GC_spec_delta_z" in out.columns
    assert len(out) == 3


# ---------------------------------------------------------------------------
# 3. fetch_cot_weekly: stale cache -> HTTP fetch + z-score correctness


def test_fetch_cot_refreshes_when_stale(tmp_path):
    cache = tmp_path / "cot.parquet"
    cache.write_bytes(b"stale")
    eight_days_ago = datetime.now().timestamp() - 8 * 86400
    os.utime(cache, (eight_days_ago, eight_days_ago))

    contracts = ["GC", "SI"]
    n_weeks = 60
    records = _make_synthetic_cot_records(n_weeks, contracts)

    with mock.patch.object(caj, "requests") as mock_requests:
        mock_resp = mock.MagicMock()
        mock_resp.json.return_value = records
        mock_resp.raise_for_status = mock.MagicMock()
        mock_requests.get.return_value = mock_resp

        out = fetch_cot_weekly(contracts=contracts, cache_path=cache)
        assert mock_requests.get.called

    # Each contract: first 51 weeks NaN, weeks 52..60 finite.
    for c in contracts:
        col = f"{c}_spec_delta_z"
        assert col in out.columns
        z = out[col].to_numpy()
        assert np.isnan(z[: Z_WINDOW - 1]).all(), f"{c} warm-up should be NaN"
        assert np.isfinite(z[Z_WINDOW - 1 :]).all(), f"{c} post-warmup must be finite"

    # Cache file written.
    assert cache.exists() or cache.with_suffix(".csv").exists()


# ---------------------------------------------------------------------------
# 4. Schema drift in COT raises a clean exception


def test_fetch_cot_schema_drift_raises(tmp_path):
    cache = tmp_path / "cot.parquet"  # does not exist -> stale path
    bad_records = [
        {
            "report_date_as_yyyy_mm_dd": "2024-01-02",
            "contract_market_name": "GOLD",
            # m_money_positions_long_all DELIBERATELY MISSING
            "m_money_positions_short_all": "1000",
        }
    ]

    with mock.patch.object(caj, "requests") as mock_requests:
        mock_resp = mock.MagicMock()
        mock_resp.json.return_value = bad_records
        mock_resp.raise_for_status = mock.MagicMock()
        mock_requests.get.return_value = mock_resp

        with pytest.raises(CrossAssetSchemaError) as exc_info:
            fetch_cot_weekly(contracts=["GC"], cache_path=cache)
    assert "m_money_positions_long_all" in str(exc_info.value)


# ---------------------------------------------------------------------------
# 5. EIA without API key raises a config error with the registration URL


def test_eia_no_api_key_raises(tmp_path, monkeypatch):
    monkeypatch.delenv("EIA_API_KEY", raising=False)
    cache = tmp_path / "eia.parquet"  # does not exist
    with pytest.raises(CrossAssetConfigError) as exc_info:
        fetch_eia_ng_storage(cache_path=cache, force_refresh=True)
    msg = str(exc_info.value)
    assert "https://www.eia.gov/opendata/register.php" in msg
    assert "EIA_API_KEY" in msg


# ---------------------------------------------------------------------------
# 6. align_to_h1 respects COT publish-lag (Friday 20:30 UTC)


def test_align_friday_publish_lag():
    # COT report Tuesday 2026-01-06; expected publish Friday 2026-01-09 20:30 UTC.
    cot_idx = pd.DatetimeIndex([pd.Timestamp("2026-01-06")], name="report_date")
    cot_df = pd.DataFrame({"GC_spec_delta_z": [10.0]}, index=cot_idx)

    h1_idx = _h1_index(
        [
            "2026-01-09 18:00",  # before publish
            "2026-01-09 21:00",  # after publish
            "2026-01-12 12:00",  # following Monday
        ]
    )
    sym = pd.DataFrame({"close": [1.0, 1.0, 1.0]}, index=h1_idx)

    out = align_to_h1(sym, include_smartmoney=True, cot_df=cot_df, eia_df=pd.DataFrame())
    vals = out["GC_spec_delta_z"].to_numpy()
    assert np.isnan(vals[0]), "18:00 row is before 20:30 publish; must be NaN"
    assert vals[1] == 10.0, "21:00 row is after publish; should see 10.0"
    assert vals[2] == 10.0, "Monday should still carry 10.0 forward"


# ---------------------------------------------------------------------------
# 7. align_to_h1 handles weekend gaps (FX no-Sat/Sun bars)


def test_align_weekend_gap():
    cot_idx = pd.DatetimeIndex([pd.Timestamp("2026-01-06")], name="report_date")
    cot_df = pd.DataFrame({"GC_spec_delta_z": [7.0]}, index=cot_idx)
    # H1 frame: Friday post-publish, then Monday/Tuesday only (no weekend).
    h1_idx = _h1_index(
        [
            "2026-01-09 21:00",
            "2026-01-12 09:00",
            "2026-01-13 09:00",
        ]
    )
    sym = pd.DataFrame({"close": [1.0, 1.0, 1.0]}, index=h1_idx)
    out = align_to_h1(sym, include_smartmoney=True, cot_df=cot_df, eia_df=pd.DataFrame())
    vals = out["GC_spec_delta_z"].to_numpy()
    assert vals[0] == 7.0
    assert vals[1] == 7.0  # Monday open carries Friday value
    assert vals[2] == 7.0
