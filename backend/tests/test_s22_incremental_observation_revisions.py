"""Synthetic S22 market observations, caches and revisions; no real KRX or DB."""
from __future__ import annotations

import asyncio
from datetime import date, timedelta
import json
from pathlib import Path
import sqlite3

import pytest

from app.jev import prospective_incremental_s22 as s22
from app.market.session_calendar_s21 import closure_evidence
from tools.data import prospective_incremental_s22 as cli


def _days(limit: int) -> list[str]:
    dates = []
    day = date(2026, 10, 9)
    while len(dates) < limit:
        if day.weekday() < 5 and closure_evidence(day) is None:
            dates.append(day.strftime("%Y%m%d"))
        day += timedelta(days=1)
    return dates


def _sim(tmp: Path, monkeypatch, *, categories=None, capture_count=1):
    db = tmp / "simulation.db"
    with sqlite3.connect(db) as c:
        c.executescript("""
            CREATE TABLE prospective_capture_run(
                id TEXT PRIMARY KEY,status TEXT NOT NULL,completed_at TEXT NOT NULL
            );
            CREATE TABLE prospective_recommendation_sample(
                capture_run_id TEXT NOT NULL,sample_index INTEGER NOT NULL
            );
        """)
        for i in range(capture_count):
            c.execute("INSERT INTO prospective_capture_run VALUES (?,?,?)",
                      (f"capture-{i:02d}", "COMPLETE", f"2026-10-09T{8+i:02d}:00:00+09:00"))
            c.execute("INSERT INTO prospective_recommendation_sample VALUES (?,?)",
                      (f"capture-{i:02d}", 0))
    categories = categories or ["LEGACY_LIMITED"] * capture_count
    def fake_load(db_path, *, capture_id, limit):
        i = int(capture_id[-2:])
        return [(
            {"id": capture_id, "status": "COMPLETE"},
            {"capture_run_id": capture_id, "sample_index": 0,
             "action": "ENTRY_CANDIDATE", "signal_date": "2026-10-08",
             "market": "KOSPI", "ticker": "000001",
             "strategy": "pullback", "snapshot_hash": "original-frozen-hash",
             "test_category": categories[i]},
        )]
    monkeypatch.setattr(s22, "load_frozen_candidates", fake_load)
    monkeypatch.setattr(s22, "assess_frozen_candidate",
                        lambda _, row: {"category": row["test_category"]})
    return db


def _bar(day: str, close: int) -> str:
    return json.dumps({
        "date": day, "code": "000001", "close": close,
        "open": close, "high": close, "low": close, "volume": 1,
    })


def _market(tmp: Path, sessions: int, *, missing=None):
    db = tmp / "market.db"
    with sqlite3.connect(db) as c:
        c.executescript("""
            CREATE TABLE day_status(
                market TEXT,bas_dd TEXT,kind TEXT,status TEXT,
                PRIMARY KEY(market,bas_dd,kind)
            );
            CREATE TABLE stock_daily(
                market TEXT,bas_dd TEXT,stock_code TEXT,row_json TEXT,
                PRIMARY KEY(market,bas_dd,stock_code)
            );
            CREATE TABLE main_index_daily(
                market TEXT,bas_dd TEXT,row_json TEXT,
                PRIMARY KEY(market,bas_dd)
            );
        """)
        for d in ["20261008", *_days(sessions)]:
            if d == missing:
                continue
            c.executemany("INSERT INTO day_status VALUES (?,?,?,'data')", [
                ("KOSPI", d, "stock"), ("KOSPI", d, "index"),
            ])
            c.execute("INSERT INTO stock_daily VALUES (?,?,?,?)",
                      ("KOSPI", d, "000001", _bar(d, 100 if d == "20261008" else 110)))
            c.execute("INSERT INTO main_index_daily VALUES (?,?,?)",
                      ("KOSPI", d, json.dumps({
                          "date": d, "name": "코스피", "close": 3000.0,
                      })))
    return db


def test_plan_no_create_and_all_three_horizons_wait_at_two_eod_days(tmp_path, monkeypatch):
    sim = _sim(tmp_path, monkeypatch)
    market = _market(tmp_path, 2)
    old_sim, old_market = sim.read_bytes(), market.read_bytes()
    report = s22.evaluate_batch(
        sim, market, today=date(2026, 10, 14),
    )
    assert report["status"] == "PLAN_ONLY"
    assert report["counts"]["awaiting_future_trading_days"] == 3
    assert report["observed_or_cached"] == []
    assert report["simulation_db_writes"] == 0
    assert sim.read_bytes() == old_sim and market.read_bytes() == old_market
    with sqlite3.connect(sim) as c:
        assert c.execute("SELECT COUNT(*) FROM sqlite_master WHERE name=?",
                         (s22.TABLE,)).fetchone()[0] == 0
    assert s22.apply_batch(sim, market, today=date(2026, 10, 14))[
        "status"] == "NO_NEW_MATURE_OBSERVATIONS"


def test_5d_matures_without_10d_or_20d_and_reuses_on_rerun(tmp_path, monkeypatch):
    sim = _sim(tmp_path, monkeypatch)
    market = _market(tmp_path, 5)
    kw = {"today": date(2026, 10, 17)}
    plan = s22.evaluate_batch(sim, market, **kw)
    assert plan["counts"] == {
        "awaiting_future_trading_days": 2, "entry_candidates": 1,
        "new_observation": 1, "s7_legacy_limited": 1,
    }
    row = plan["observed_or_cached"][0]
    assert row["horizon_days"] == 5
    assert row["target_date"] == "2026-10-16"
    assert row["close_change_pct"] == 10.0
    assert row["source_integrity"] == "LEGACY_LIMITED"
    before_market = market.read_bytes()
    applied = s22.apply_batch(sim, market, **kw)
    assert applied["simulation_db_writes"] == 1
    assert applied["new_observations_saved"] == 1
    assert market.read_bytes() == before_market
    repeated = s22.apply_batch(sim, market, **kw)
    assert repeated["status"] == "NO_NEW_MATURE_OBSERVATIONS"
    assert repeated["simulation_db_writes"] == 0
    plan_again = s22.evaluate_batch(sim, market, **kw)
    assert plan_again["counts"]["cache_hit"] == 1
    with sqlite3.connect(sim) as c:
        assert c.execute(f"SELECT COUNT(*) FROM {s22.TABLE}").fetchone()[0] == 1


def test_10d_maturity_only_adds_new_window_and_retains_original_5d(tmp_path, monkeypatch):
    sim = _sim(tmp_path, monkeypatch)
    market = _market(tmp_path, 10)
    earlier = s22.apply_batch(
        sim, market, as_of="2026-10-16", today=date(2026, 10, 24),
    )
    assert earlier["simulation_db_writes"] == 1
    subsequent = s22.apply_batch(
        sim, market, as_of="2026-10-23", today=date(2026, 10, 24),
    )
    assert subsequent["simulation_db_writes"] == 1
    assert subsequent["counts"]["cache_hit"] == 1
    assert subsequent["counts"]["new_observation"] == 1
    with sqlite3.connect(sim) as c:
        assert c.execute(
            f"SELECT horizon_days FROM {s22.TABLE} ORDER BY horizon_days"
        ).fetchall() == [(5,), (10,)]


def test_revised_price_creates_immutable_new_revision_and_reuses_after(tmp_path, monkeypatch):
    sim = _sim(tmp_path, monkeypatch)
    market = _market(tmp_path, 5)
    kw = {"today": date(2026, 10, 17)}
    assert s22.apply_batch(sim, market, **kw)["simulation_db_writes"] == 1
    with sqlite3.connect(market) as c:
        c.execute(
            "UPDATE stock_daily SET row_json=? "
            "WHERE market='KOSPI' AND bas_dd='20261016' AND stock_code='000001'",
            (_bar("20261016", 120),),
        )
    plan = s22.evaluate_batch(sim, market, **kw)
    assert plan["counts"]["revision_required"] == 1
    second = s22.apply_batch(sim, market, **kw)
    assert second["simulation_db_writes"] == 1
    assert second["revisions_saved"] == 1
    assert s22.apply_batch(sim, market, **kw)["simulation_db_writes"] == 0
    with sqlite3.connect(sim) as c:
        rows = c.execute(
            f"SELECT revision_id,evidence_hash,close_change_pct "
            f"FROM {s22.TABLE} ORDER BY revision_id"
        ).fetchall()
    assert len(rows) == 2
    assert rows[0][1] != rows[1][1]
    assert [r[2] for r in rows] == [10.0, 20.0]


def test_inserted_earlier_session_invalidates_old_five_day_target(tmp_path, monkeypatch):
    sim = _sim(tmp_path, monkeypatch)
    market = _market(tmp_path, 6, missing="20261014")
    kw = {"today": date(2026, 10, 20)}
    planned = s22.evaluate_batch(sim, market, **kw)
    assert planned["counts"]["unverified_calendar_or_market_gap"] == 3
    assert planned["observed_or_cached"] == []
    # Adding a formerly missing intermediate day makes 5d independently valid.
    with sqlite3.connect(market) as c:
        d = "20261014"
        c.executemany("INSERT INTO day_status VALUES (?,?,?,'data')", [
            ("KOSPI", d, "stock"), ("KOSPI", d, "index"),
        ])
        c.execute("INSERT INTO stock_daily VALUES (?,?,?,?)",
                  ("KOSPI", d, "000001", _bar(d, 110)))
        c.execute("INSERT INTO main_index_daily VALUES (?,?,?)",
                  ("KOSPI", d, json.dumps({
                      "date": d, "name": "코스피", "close": 3000.0,
                  })))
    planned = s22.evaluate_batch(sim, market, **kw)
    assert planned["counts"]["new_observation"] == 1
    assert planned["counts"]["awaiting_future_trading_days"] == 2
    assert planned["observed_or_cached"][0]["target_date"] == "2026-10-16"


def test_invalid_s7_never_added_to_denominator_or_cache(tmp_path, monkeypatch):
    sim = _sim(tmp_path, monkeypatch, categories=["INVALID"])
    market = _market(tmp_path, 10)
    report = s22.apply_batch(sim, market, today=date(2026, 10, 24))
    assert report["counts"] == {"entry_candidates": 1, "s7_invalid": 1}
    assert report["simulation_db_writes"] == 0


def test_paginated_captures_are_complete_and_cursor_continues(tmp_path, monkeypatch):
    sim = _sim(tmp_path, monkeypatch, capture_count=3)
    market = _market(tmp_path, 5)
    first = s22.evaluate_batch(
        sim, market, today=date(2026, 10, 17), limit_captures=2,
    )
    assert first["inspected_captures"] == 2
    assert first["complete_page"] is False
    assert first["next_cursor"]
    following = s22.evaluate_batch(
        sim, market, today=date(2026, 10, 17),
        limit_captures=2, after=first["next_cursor"],
    )
    assert following["inspected_captures"] == 1
    assert following["complete_page"] is True
    assert following["next_cursor"] is None


def test_missing_index_in_daily_market_evidence_does_not_certify_session(tmp_path, monkeypatch):
    sim = _sim(tmp_path, monkeypatch)
    market = _market(tmp_path, 5)
    with sqlite3.connect(market) as c:
        c.execute("DELETE FROM main_index_daily WHERE bas_dd='20261014'")
    res = s22.evaluate_batch(sim, market, today=date(2026, 10, 17))
    assert res["counts"]["unverified_calendar_or_market_gap"] == 3


def test_no_future_or_today_eod_and_explicit_write_ack(tmp_path, monkeypatch):
    sim = _sim(tmp_path, monkeypatch)
    market = _market(tmp_path, 5)
    with pytest.raises(s22.IncrementalObservationError, match="FUTURE_OR_TODAY"):
        s22.evaluate_batch(sim, market, as_of="2026-10-17",
                           today=date(2026, 10, 17))
    argv = ["apply", "--simulation-db", str(sim), "--market-db", str(market)]
    assert cli.main(argv) == 2
    with sqlite3.connect(sim) as c:
        assert c.execute("SELECT COUNT(*) FROM sqlite_master WHERE name=?",
                         (s22.TABLE,)).fetchone()[0] == 0


def test_source_day_price_revision_changes_fingerprint(tmp_path, monkeypatch):
    sim = _sim(tmp_path, monkeypatch)
    market = _market(tmp_path, 5)
    kw = {"today": date(2026, 10, 17)}
    s22.apply_batch(sim, market, **kw)
    with sqlite3.connect(market) as c:
        c.execute(
            "UPDATE stock_daily SET row_json=? "
            "WHERE bas_dd='20261008' AND stock_code='000001'",
            (_bar("20261008", 80),),
        )
    result = s22.evaluate_batch(sim, market, **kw)
    assert result["counts"]["revision_required"] == 1
    assert result["observed_or_cached"][0]["close_change_pct"] == 37.5
