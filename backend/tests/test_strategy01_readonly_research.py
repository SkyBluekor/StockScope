from __future__ import annotations

import json
import sqlite3
from datetime import date, timedelta
from pathlib import Path

import pytest

from tools.data.analyze_strategy01_existing10 import (
    ReadOnlyExitRegistry, _summary, checked_rows, open_readonly, study,
)


def _db(tmp_path: Path, *, sessions: int = 140) -> tuple[Path, str, list[str]]:
    path = tmp_path / "market.db"
    dates = []
    cursor = date(2026, 1, 1)
    while len(dates) < sessions:
        if cursor.weekday() < 5:
            dates.append(cursor.strftime("%Y%m%d"))
        cursor += timedelta(days=1)
    with sqlite3.connect(path) as con:
        con.executescript("""
            CREATE TABLE day_status(
                market TEXT, bas_dd TEXT, kind TEXT, status TEXT,
                PRIMARY KEY (market,bas_dd,kind));
            CREATE TABLE main_index_daily(
                market TEXT,bas_dd TEXT,row_json TEXT,
                PRIMARY KEY(market,bas_dd));
            CREATE TABLE stock_daily(
                market TEXT,bas_dd TEXT,stock_code TEXT,row_json TEXT,
                PRIMARY KEY(market,bas_dd,stock_code));
        """)
        for index, day in enumerate(dates):
            for market, code in (("KOSPI", "005930"), ("KOSDAQ", "171090")):
                for kind in ("stock", "index"):
                    con.execute("INSERT INTO day_status VALUES (?,?,?,?)",
                                (market, day, kind, "data"))
                con.execute("INSERT INTO main_index_daily VALUES (?,?,?)",
                            (market, day, json.dumps({
                                "date": day,
                                "close": 2500 + index * .3,
                                "change_rate": .15,
                            })))
                close = 100 + index * .12
                con.execute("INSERT INTO stock_daily VALUES (?,?,?,?)",
                            (market, day, code, json.dumps({
                                "date": day, "code": code, "open": close - .1,
                                "high": close + 1.2, "low": close - 1.1,
                                "close": close, "trade_value": 2_000_000_000,
                                "volume": 200_000,
                            })))
    return path, dates[-1], dates


def test_strategy01_missing_database_is_never_created(tmp_path: Path):
    absent = tmp_path / "missing.db"
    with pytest.raises(FileNotFoundError):
        open_readonly(absent)
    assert not absent.exists()


def test_strategy01_insufficient_common_history_is_explicit_and_readonly(tmp_path: Path):
    path, end, _ = _db(tmp_path, sessions=125)
    previous = (path.stat().st_size, path.stat().st_mtime_ns)
    with open_readonly(path) as conn:
        report = study(conn, end=end, days=40, warmup=120, check_only=True)
        with pytest.raises(sqlite3.OperationalError):
            conn.execute("DELETE FROM stock_daily")
    assert report["status"] == "DATA_INSUFFICIENT"
    assert report["reason"] == "INSUFFICIENT_COMMON_WARMUP_AND_EVALUATION_SESSIONS"
    assert report["required_common_sessions"] == 160
    assert report["production_decision_approved"] is False
    assert report["network_requests"] == report["db_writes"] == 0
    assert report["horizons"]["SHORT"]["support_status"] == "EVALUATION_PENDING"
    assert (path.stat().st_size, path.stat().st_mtime_ns) == previous


def test_strategy01_readonly_sample_selection_and_gap_detection(tmp_path: Path):
    path, end, days = _db(tmp_path, sessions=140)
    with open_readonly(path) as conn:
        result = study(conn, end=end, days=20, warmup=120,
                       per_market=1, check_only=True)
    assert result["status"] == "READY_TO_RESEARCH"
    assert result["sample"]["selected"] == [
        {"market": "KOSPI", "code": "005930"},
        {"market": "KOSDAQ", "code": "171090"},
    ]
    with sqlite3.connect(path) as conn:
        conn.execute(
            "DELETE FROM stock_daily WHERE market='KOSPI' AND stock_code='005930' AND bas_dd=?",
            (days[-1],),
        )
    with open_readonly(path) as conn:
        missing = study(conn, end=end, days=20, warmup=120,
                        per_market=1, check_only=True)
    assert missing["status"] == "READY_TO_RESEARCH"
    assert missing["sample"]["selected"] == [{"market": "KOSDAQ", "code": "171090"}]
    assert any(row.get("code") == "005930" and row["reason"] == "STOCK_INCOMPLETE"
               for row in missing["sample"]["exclusions"])


def test_strategy01_ignores_empty_holiday_markers_but_not_partial_data(tmp_path: Path):
    # An extra date in the cache is NOT necessarily a trading day.
    # Holiday/closure status='empty' must never block 160 complete KRX sessions.
    path, end, _ = _db(tmp_path, sessions=160)
    closed_day = "20260103"  # non-trading synthetic day inside the selected range
    before = (path.stat().st_size, path.stat().st_mtime_ns)
    with sqlite3.connect(path) as con:
        for market in ("KOSPI", "KOSDAQ"):
            for kind in ("stock", "index"):
                con.execute(
                    "INSERT INTO day_status VALUES (?,?,?,?)",
                    (market, closed_day, kind, "empty"),
                )
    stable = (path.stat().st_size, path.stat().st_mtime_ns)
    with open_readonly(path) as conn:
        valid = study(conn, end=end, days=40, warmup=120, per_market=1,
                      check_only=True)
        with pytest.raises(sqlite3.OperationalError):
            conn.execute("UPDATE day_status SET status='data'")
    assert valid["status"] == "READY_TO_RESEARCH"
    assert valid["ignored_nontrading_marker_dates"]["count"] == 1
    assert valid["ignored_nontrading_marker_dates"]["sample"] == [closed_day]
    assert (path.stat().st_size, path.stat().st_mtime_ns) == stable

    # The same date has a KOSPI stock-data marker but lacks 3 other data
    # markers. That is an incomplete source session, not a holiday.
    with sqlite3.connect(path) as con:
        con.execute(
            "UPDATE day_status SET status='data' WHERE market='KOSPI'"
            " AND bas_dd=? AND kind='stock'",
            (closed_day,),
        )
    with open_readonly(path) as conn:
        partial = study(conn, end=end, days=40, warmup=120, per_market=1,
                        check_only=True)
    assert partial["status"] == "DATA_INSUFFICIENT"
    assert partial["reason"] == "PARTIAL_KRX_MARKET_DAYS"
    assert closed_day in partial["partial_dates_sample"]
    assert partial["ignored_nontrading_marker_dates"]["count"] == 0


def test_strategy01_does_not_bootstrap_production_exit_mapping(tmp_path: Path):
    runtime = tmp_path / "research"
    runtime.mkdir()
    (runtime / "exit_policy_validation_report.json").write_text(
        '{"status":"COMPLETED","strategies":[]}', encoding="utf-8",
    )
    registry = ReadOnlyExitRegistry(runtime_dir=runtime)
    baseline = registry.resolve("pullback")
    assert baseline.policy_id == "TARGET1_FULL_EXIT"
    assert baseline.fallback_used is True
    assert not (runtime / "exit_policy_production.json").exists()


def test_strategy01_empty_trade_metrics_are_missing_not_zero():
    values = _summary([])
    assert values["closed_trades"] == 0
    assert values["win_rate_pct"] is None
    assert values["expectancy_pct"] is None
    assert values["profit_factor"] is None


def test_strategy01_reuses_ten_strategy_engine_on_existing_data(tmp_path: Path):
    path, end, _ = _db(tmp_path, sessions=140)
    previous = (path.stat().st_size, path.stat().st_mtime_ns)
    with open_readonly(path) as conn:
        result = study(conn, end=end, days=20, warmup=120, per_market=1,
                       cost=.3, max_hold=20, check_only=False)
    assert result["status"] == "RESEARCH_DESCRIPTIVE_ONLY"
    assert len(result["strategy_results"]) == 10
    assert result["sample"]["evaluated"][0]["signal_snapshots"] >= 2
    assert result["horizon_policy_approved"] is False
    assert result["policy_activation"] is False
    assert result["assumptions"]["round_trip_cost_pct_assumed"] == .3
    assert result["strategy_results"][0]["temporal_split"]["status"] == "DESCRIPTIVE_NOT_OOS"
    assert (path.stat().st_size, path.stat().st_mtime_ns) == previous
