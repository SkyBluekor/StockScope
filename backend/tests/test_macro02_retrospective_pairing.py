from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from tools.data.analyze_macro02_eod_relation import (
    _macro_obs,
    market_days,
    pair_retro,
    stock_relative_example,
)


def _sample_macro(day: str, value: str, quality: str = "DATE_ONLY") -> dict:
    return {
        "observation_date": day,
        "normalized_value": value,
        "source_unit": "PERCENT",
        "available_at": "2026-11-02T02:40:49+00:00",
        "time_quality": quality,
        "source_published_at": None,
    }


def test_macro02_never_pairs_same_us_date_as_krx_day_or_claims_pit() -> None:
    cutoff = datetime(2026, 11, 2, 3, tzinfo=timezone.utc)
    obs = _macro_obs([
        _sample_macro("2026-10-27", "4.80"),
        _sample_macro("2026-10-29", "4.98"),
        _sample_macro("2026-10-30", "5.50"),
    ], cutoff=cutoff)
    paired = pair_retro([
        {"day": "20261030", "KOSPI": Decimal("-3.48"), "KOSDAQ": Decimal("-3.83")},
    ], obs)
    assert paired["mode"] == "RETROSPECTIVE_DESCRIPTIVE_ONLY"
    assert paired["policy_input_approved"] is False
    assert paired["relation_status"] == "RELATION_UNVERIFIED"
    assert paired["paired_sessions"] == 1
    assert paired["last_pair"]["us_observation_date"] == "2026-10-29"
    assert paired["last_pair"]["dgs10_change_bp"] == 18.0
    assert paired["pit_verified_pairs"] == 0
    assert paired["groups"]["rate_up"]["kospi_mean_pct"] == -3.48


def test_macro02_counts_missing_and_stale_us_dates_and_reuse() -> None:
    cutoff = datetime(2026, 11, 2, 3, tzinfo=timezone.utc)
    obs = _macro_obs([
        _sample_macro("2026-09-01", "3.90"),
        _sample_macro("2026-09-29", "3.95"),
        _sample_macro("2026-10-01", "4.00"),
    ], cutoff=cutoff)
    paired = pair_retro([
        {"day": "20260831", "KOSPI": Decimal("1"), "KOSDAQ": Decimal("1")},
        {"day": "20260902", "KOSPI": Decimal("1"), "KOSDAQ": Decimal("1")},
        {"day": "20261002", "KOSPI": Decimal("-1"), "KOSDAQ": Decimal("-1")},
        {"day": "20261003", "KOSPI": Decimal("-1"), "KOSDAQ": Decimal("-1")},
        {"day": "20261015", "KOSPI": Decimal("-1"), "KOSDAQ": Decimal("-1")},
    ], obs)
    assert paired["paired_sessions"] == 1
    assert paired["excluded"] == {
        "NO_PRIOR_US_OBSERVATION": 1,
        "US_OBSERVATION_TOO_OLD": 1,
        "US_BASELINE_MISSING_OR_TOO_OLD": 1,
        "US_DAY_REUSED": 1,
    }


def test_macro02_window_excludes_future_available_and_malformed_values() -> None:
    cutoff = datetime(2026, 11, 2, 3, tzinfo=timezone.utc)
    rows = [
        _sample_macro("2026-10-29", "4.00"),
        {**_sample_macro("2026-10-30", "4.20"), "available_at": "2026-11-03T00:00:00+00:00"},
        _sample_macro("2026-10-31", "NaN"),
        {**_sample_macro("2026-10-31", "4.30"), "source_unit": "BASIS_POINT"},
    ]
    result = _macro_obs(rows, cutoff=cutoff)
    assert [x["day"].isoformat() for x in result] == ["2026-10-29"]


def _market_db(tmp_path: Path) -> Path:
    path = tmp_path / "market.db"
    with sqlite3.connect(path) as conn:
        conn.executescript("""
            CREATE TABLE day_status (market TEXT, bas_dd TEXT, kind TEXT, status TEXT);
            CREATE TABLE main_index_daily (market TEXT, bas_dd TEXT, row_json TEXT);
            CREATE TABLE stock_daily (market TEXT, bas_dd TEXT, stock_code TEXT, row_json TEXT);
        """)
        for day, kospi, kosdaq, price in [
            ("20261029", "1000", "100", "100"),
            ("20261030", "965.2", "96.17", "110"),
        ]:
            for market, close, daily in (
                ("KOSPI", kospi, "-3.48"),
                ("KOSDAQ", kosdaq, "-3.83"),
            ):
                for kind in ("index", "stock"):
                    conn.execute(
                        "INSERT INTO day_status VALUES (?,?,?,?)",
                        (market, day, kind, "data"),
                    )
                conn.execute(
                    "INSERT INTO main_index_daily VALUES (?,?,?)",
                    (market, day, json.dumps({
                        "date": day, "close": close, "change_rate": daily,
                    })),
                )
                conn.execute(
                    "INSERT INTO stock_daily VALUES (?,?,?,?)",
                    (market, day, "000001",
                     json.dumps({"date": day, "close": "10", "code": "000001"})),
                )
            conn.execute(
                "INSERT INTO stock_daily VALUES (?,?,?,?)",
                ("KOSDAQ", day, "171090",
                 json.dumps({"date": day, "close": price, "code": "171090"})),
            )
    return path


def test_macro02_market_reader_requires_all_markers_and_is_read_only(tmp_path: Path) -> None:
    path = _market_db(tmp_path)
    before = (path.stat().st_size, path.stat().st_mtime_ns)
    days = market_days(path, end=date(2026, 10, 30), limit=120)
    assert [x["day"] for x in days] == ["20261029", "20261030"]
    assert days[-1]["KOSPI"] == Decimal("-3.48")
    stock = stock_relative_example(path, market="KOSDAQ", ticker="171090",
                                   end=date(2026, 10, 30))
    assert stock["status"] == "AVAILABLE"
    assert stock["stock_return_pct"] == 10.0
    assert stock["market_return_pct"] == -3.83
    assert stock["stock_vs_market_pctp"] == 13.83
    assert (path.stat().st_size, path.stat().st_mtime_ns) == before

    with sqlite3.connect(path) as conn:
        conn.execute("""
            UPDATE day_status SET status='empty'
            WHERE market='KOSPI' AND bas_dd='20261030' AND kind='index'
        """)
    assert [x["day"] for x in market_days(path, end=date(2026, 10, 30), limit=120)] == ["20261029"]


def test_macro02_missing_database_never_creates_it(tmp_path: Path) -> None:
    path = tmp_path / "missing.db"
    with pytest.raises(FileNotFoundError):
        market_days(path, end=date(2026, 10, 30), limit=120)
    assert not path.exists()
