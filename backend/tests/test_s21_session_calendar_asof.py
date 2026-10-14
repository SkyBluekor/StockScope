"""S21 sourced closures, historical as-of, and independent 5/10/20 readiness."""
from __future__ import annotations

from datetime import date, timedelta
import sqlite3

from app.market.session_calendar_s21 import closure_evidence, unresolved_weekdays
from app.jev.q7_observation_s16 import _record_windows
from app.prospective.evaluation import ReadOnlyMarketEvidence


def _sessions():
    days = []
    d = date(2026, 10, 9)
    while len(days) < 20:
        if d.weekday() < 5 and closure_evidence(d) is None:
            days.append(d.isoformat())
        d += timedelta(days=1)
    return days


def _payload(days, available=None):
    count = len(days) if available is None else available
    return {
        "available_trading_days": count,
        "evaluated_through": days[-1] if days else None,
        "return_5d": 1.0,
        "return_10d": 2.0,
        "return_20d": 3.0,
        "details": {
            "reference_price": 100.0,
            "observed_market_days": list(days),
            "observation_window_end_dates": {
                f"{w}d": days[w-1] if count >= w else None
                for w in (5, 10, 20)
            },
        },
    }


def test_krx_confirmed_hangul_and_national_foundation_closures_only():
    for day in (date(2026, 10, 5), date(2026, 10, 9)):
        evidence = closure_evidence(day)
        assert evidence is not None
        assert evidence["status"] == "CLOSED_VERIFIED"
        assert evidence["source"].startswith("https://trn.krx.co.kr")
    assert closure_evidence(date(2026, 10, 10))["reason"] == "WEEKEND"
    # A generic weekday is NEVER certified open just because it is not listed.
    assert closure_evidence(date(2026, 10, 12)) is None
    assert closure_evidence(date(2027, 10, 9))["reason"] == "WEEKEND"


def test_closed_holiday_does_not_count_as_missing_market_eod():
    assert unresolved_weekdays(
        date(2026, 10, 8), date(2026, 10, 13),
        [date(2026, 10, 12), date(2026, 10, 13)],
    ) == []


def test_missing_unproven_weekday_is_not_fabricated_as_market_session():
    assert unresolved_weekdays(
        date(2026, 10, 8), date(2026, 10, 13),
        [date(2026, 10, 13)],
    ) == ["2026-10-12"]


def test_complete_5d_remains_observed_while_10d_and_20d_are_future():
    payload = _payload(_sessions())
    result, issue = _record_windows(
        payload, date(2026, 10, 16), signal_date="2026-10-08",
    )
    assert result[5] == ("OBSERVED", 1.0)
    assert result[10] == ("POST_AS_OF_DATA_REJECTED", None)
    assert result[20] == ("POST_AS_OF_DATA_REJECTED", None)
    assert issue == "FUTURE_DATED_MARKET_EVIDENCE"


def test_missing_midwindow_market_day_blocks_falsely_mature_result():
    sample_days = [
        "2026-10-12", "2026-10-13",
        # October 14 intentionally absent, later session shifts the 5th row.
        "2026-10-15", "2026-10-16", "2026-10-19",
    ]
    outcome = _payload(sample_days)
    result, _ = _record_windows(
        outcome, date(2026, 10, 19), signal_date="2026-10-08",
    )
    assert result[5] == ("UNVERIFIED_CALENDAR_OR_DATA_GAP", None)
    assert result[10] == ("UNVERIFIED_CALENDAR_OR_DATA_GAP", None)
    assert result[20] == ("UNVERIFIED_CALENDAR_OR_DATA_GAP", None)


def test_expected_not_yet_due_is_different_from_data_gap():
    observed = _payload(["2026-10-12", "2026-10-13"])
    states, _ = _record_windows(
        observed, date(2026, 10, 13), signal_date="2026-10-08",
    )
    assert all(states[w][0] == "AWAITING_FUTURE_DAYS" for w in (5, 10, 20))
    states, _ = _record_windows(
        observed, date(2026, 10, 14), signal_date="2026-10-08",
    )
    assert all(states[w][0] == "UNVERIFIED_CALENDAR_OR_DATA_GAP" for w in (5, 10, 20))


def test_ro_market_day_query_never_uses_bars_after_requested_asof(tmp_path):
    path = tmp_path / "market.db"
    with sqlite3.connect(path) as conn:
        conn.execute(
            "CREATE TABLE day_status (market TEXT, bas_dd TEXT, "
            "kind TEXT, status TEXT)"
        )
        conn.executemany(
            "INSERT INTO day_status VALUES (?,?,?,?)",
            [
                ("KOSPI", raw, "stock", "data")
                for raw in ("20261008", "20261012", "20261013", "20261014", "20261015")
            ],
        )
    original = path.read_bytes()
    with sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True) as conn:
        conn.row_factory = sqlite3.Row
        assert ReadOnlyMarketEvidence.market_days(
            conn, market="KOSPI", after_date="2026-10-08", limit=20,
            through_date="2026-10-13",
        ) == ["20261012", "20261013"]
        assert ReadOnlyMarketEvidence.market_days(
            conn, market="KOSPI", after_date="2026-10-08", limit=20,
        ) == ["20261012", "20261013", "20261014", "20261015"]
    assert path.read_bytes() == original


def test_strict_market_day_requires_both_markers_and_actual_rows(tmp_path):
    path = tmp_path / "market_complete.db"
    with sqlite3.connect(path) as conn:
        conn.executescript("""
        CREATE TABLE day_status(market TEXT,bas_dd TEXT,kind TEXT,status TEXT);
        CREATE TABLE stock_daily(market TEXT,bas_dd TEXT,stock_code TEXT,row_json TEXT);
        CREATE TABLE main_index_daily(market TEXT,bas_dd TEXT,row_json TEXT);
        """)
        conn.executemany("INSERT INTO day_status VALUES(?,?,?,?)", [
            ("KOSPI", "20261012", "stock", "data"),
            ("KOSPI", "20261012", "index", "data"),
            ("KOSPI", "20261013", "stock", "data"),  # missing index evidence
            ("KOSPI", "20261014", "stock", "data"),
            ("KOSPI", "20261014", "index", "data"),  # no actual index row
        ])
        conn.executemany("INSERT INTO stock_daily VALUES(?,?,?,?)", [
            ("KOSPI", d, "000001", "{}") for d in (
                "20261012", "20261013", "20261014"
            )
        ])
        conn.execute("INSERT INTO main_index_daily VALUES(?,?,?)",
                     ("KOSPI", "20261012", "{}"))
    with sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True) as conn:
        conn.row_factory = sqlite3.Row
        selected = ReadOnlyMarketEvidence.market_days(
            conn, market="KOSPI", after_date="2026-10-08", limit=20,
            through_date="2026-10-14", complete_only=True,
        )
        assert selected == ["20261012"]
