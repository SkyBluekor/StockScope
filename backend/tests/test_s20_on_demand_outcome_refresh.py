"""S20 opt-in market gap filling tests: all synthetic, no network or runtime DB."""
from __future__ import annotations

import asyncio
from datetime import date
import json
from pathlib import Path
import sqlite3

import pytest

from tools.data import prospective_outcome_refresh as s20


def _market(tmp_path: Path) -> Path:
    db = tmp_path / "market.db"
    with sqlite3.connect(db) as c:
        c.executescript("""
            CREATE TABLE stock_daily (
                market TEXT NOT NULL, bas_dd TEXT NOT NULL,
                stock_code TEXT NOT NULL, row_json TEXT NOT NULL,
                PRIMARY KEY(market,bas_dd,stock_code)
            );
            CREATE TABLE main_index_daily (
                market TEXT NOT NULL, bas_dd TEXT NOT NULL,
                row_json TEXT NOT NULL, PRIMARY KEY(market,bas_dd)
            );
            CREATE TABLE day_status (
                market TEXT NOT NULL, bas_dd TEXT NOT NULL,
                kind TEXT NOT NULL, status TEXT NOT NULL,
                PRIMARY KEY(market,bas_dd,kind)
            );
        """)
        _populate(c, "KOSPI", "20261008")
    return db


def _stock_rows(market: str, day: str, count: int = 110) -> list[dict]:
    return [
        {"date": day, "code": f"{i:06d}", "market": market,
         "close": 1000 + i, "open": 990, "high": 1010, "low": 980}
        for i in range(count)
    ]


def _index(market: str, day: str) -> dict:
    return {"date": day, "name": "코스피" if market == "KOSPI" else "코스닥",
            "close": 3000.0}


def _populate(c: sqlite3.Connection, market: str, day: str) -> None:
    c.executemany(
        "INSERT INTO stock_daily VALUES (?,?,?,?)",
        [(market, day, r["code"], json.dumps(r)) for r in _stock_rows(market, day)],
    )
    c.execute("INSERT INTO main_index_daily VALUES (?,?,?)",
              (market, day, json.dumps(_index(market, day))))
    c.executemany(
        "INSERT INTO day_status VALUES (?,?,?,'data')",
        [(market, day, kind) for kind in ("stock", "index")],
    )


def _simulation(tmp_path: Path, monkeypatch) -> Path:
    db = tmp_path / "sim.db"
    with sqlite3.connect(db) as c:
        c.executescript("""
            CREATE TABLE prospective_capture_run(
                id TEXT PRIMARY KEY, status TEXT, completed_at TEXT
            );
            CREATE TABLE prospective_recommendation_sample(
                capture_run_id TEXT, sample_index INTEGER
            );
            INSERT INTO prospective_capture_run VALUES
                ('cap1','COMPLETE','2026-10-09T10:00:00+09:00');
            INSERT INTO prospective_recommendation_sample VALUES ('cap1',0);
        """)
    def fake_load(path, *, capture_id, limit):
        assert capture_id == "cap1" and limit == 500
        return [
            ({"id": "cap1", "status": "COMPLETE"},
             {"action": "ENTRY_CANDIDATE", "market": "KOSPI",
              "signal_date": "2026-10-08", "ticker": "000001",
              "strategy": "pullback"}),
        ]
    monkeypatch.setattr(s20, "load_frozen_candidates", fake_load)
    monkeypatch.setattr(s20, "assess_frozen_candidate",
                        lambda *a: {"category": "LEGACY_LIMITED"})
    monkeypatch.setattr(s20, "observe",
                        lambda *a, **kw: {"status": "DESCRIPTIVE_OBSERVATIONS_ONLY",
                                        "windows": {"5d": {"observed": 0}}})
    return db


class FakeKrx:
    api_key = "synthetic"

    def __init__(self, *, bad_day=None, fail_day=None, wrong_index=False):
        self.bad_day = bad_day
        self.fail_day = fail_day
        self.wrong_index = wrong_index
        self.started = self.closed = False
        self.calls = 0

    async def open_session(self):
        self.started = True

    async def close_session(self):
        self.closed = True

    async def stock_daily(self, market, day):
        self.calls += 1
        if day == self.fail_day:
            raise RuntimeError("provider offline")
        if day == "2026-10-09":
            return {"date": "20261009", "rows": []}
        count = 10 if day == self.bad_day else 110
        return {"date": day.replace("-", ""), "rows": _stock_rows(market, day.replace("-", ""), count)}

    async def index_daily(self, market, day):
        self.calls += 1
        if day == "2026-10-09":
            return {"date": "20261009", "rows": []}
        item = _index(market, day.replace("-", ""))
        if self.wrong_index:
            item["name"] = "OTHER"
        return {"date": day.replace("-", ""), "rows": [item]}

    def request_stats(self):
        return {"network_requests": self.calls}

    def assert_budget(self, estimated_requests):
        assert estimated_requests > 0
        return {"remaining_after": 100}


def test_plan_pure_ro_and_exact_date_gap_selection(tmp_path, monkeypatch):
    sim = _simulation(tmp_path, monkeypatch)
    market = _market(tmp_path)
    original = (sim.read_bytes(), market.read_bytes())
    report = s20.plan(sim, market, through="2026-10-13", today=date(2026, 10, 14))
    assert (sim.read_bytes(), market.read_bytes()) == original
    assert report["status"] == "PLAN_ONLY"
    assert report["date_counts"] == {"MISSING": 3}
    assert [(x["market"], x["date"]) for x in report["days"]] == [
        ("KOSPI", "2026-10-09"), ("KOSPI", "2026-10-12"),
        ("KOSPI", "2026-10-13"),
    ]
    assert report["cohort"]["s7_legacy_limited"] == 1
    assert report["runtime_db_writes"] == report["network_requests"] == 0


def test_apply_appends_complete_dates_atomically_and_does_not_invent_holiday(tmp_path, monkeypatch):
    sim = _simulation(tmp_path, monkeypatch)
    market = _market(tmp_path)
    provider = FakeKrx()
    result = asyncio.run(s20.apply(
        sim, market, through="2026-10-13", today=date(2026, 10, 14),
        provider=provider,
    ))
    assert result["status"] == "PARTIAL_OR_UNVERIFIED_GAPS"
    assert result["stored_days"] == 2
    assert result["remaining_date_counts"] == {"MISSING": 1, "STORED_COMPLETE": 2}
    assert result["outstanding_calendar_verification"]
    assert provider.started and provider.closed
    with sqlite3.connect(market) as c:
        assert c.execute(
            "SELECT bas_dd,kind FROM day_status WHERE bas_dd>'20261008' "
            "ORDER BY bas_dd,kind"
        ).fetchall() == [
            ("20261012", "index"), ("20261012", "stock"),
            ("20261013", "index"), ("20261013", "stock"),
        ]
        assert c.execute(
            "SELECT COUNT(*) FROM stock_daily WHERE bas_dd='20261012'"
        ).fetchone()[0] == 110
        assert c.execute(
            "SELECT COUNT(*) FROM main_index_daily WHERE bas_dd='20261012'"
        ).fetchone()[0] == 1
    # Repeating the operation cannot overwrite either previously stored day.
    again = asyncio.run(s20.apply(
        sim, market, through="2026-10-13", today=date(2026, 10, 14),
        provider=FakeKrx(),
    ))
    assert again["stored_days"] == 0
    assert again["remaining_date_counts"] == {"MISSING": 1, "STORED_COMPLETE": 2}


def test_reject_existing_partial_day_before_network(tmp_path, monkeypatch):
    sim = _simulation(tmp_path, monkeypatch)
    market = _market(tmp_path)
    with sqlite3.connect(market) as c:
        c.execute("INSERT INTO day_status VALUES ('KOSPI','20261012','stock','data')")
    bad = FakeKrx()
    with pytest.raises(s20.GapFillError, match="PARTIAL_EXISTING"):
        asyncio.run(s20.apply(
            sim, market, through="2026-10-13", today=date(2026, 10, 14),
            provider=bad,
        ))
    assert not bad.started and bad.calls == 0


def test_truncated_response_rolls_back_one_market_day(tmp_path, monkeypatch):
    sim = _simulation(tmp_path, monkeypatch)
    market = _market(tmp_path)
    response = asyncio.run(s20.apply(
        sim, market, through="2026-10-13", today=date(2026, 10, 14),
        provider=FakeKrx(bad_day="2026-10-12"),
    ))
    assert response["status"] == "PARTIAL_OR_UNVERIFIED_GAPS"
    assert response["stored_days"] == 0
    assert response["errors"][0].endswith("STOCK_RESPONSE_TOO_SMALL")
    with sqlite3.connect(market) as c:
        assert c.execute(
            "SELECT COUNT(*) FROM day_status WHERE bas_dd>'20261008'"
        ).fetchone()[0] == 0


def test_provider_failure_not_a_holiday_and_no_scanner_side_effect(tmp_path, monkeypatch):
    sim = _simulation(tmp_path, monkeypatch)
    market = _market(tmp_path)
    provider = FakeKrx(fail_day="2026-10-12")
    response = asyncio.run(s20.apply(
        sim, market, through="2026-10-13", today=date(2026, 10, 14),
        provider=provider,
    ))
    assert response["status"] == "PARTIAL_OR_UNVERIFIED_GAPS"
    assert "RuntimeError" in response["errors"][0]
    assert response["new_captures"] == response["scanner_runs"] == 0
    assert provider.closed


def test_reject_today_or_future_and_excessive_range(tmp_path, monkeypatch):
    sim = _simulation(tmp_path, monkeypatch)
    market = _market(tmp_path)
    with pytest.raises(s20.GapFillError, match="ONLY_PRIOR"):
        s20.plan(sim, market, through="2026-10-14", today=date(2026, 10, 14))
    with pytest.raises(s20.GapFillError, match="RANGE_TOO_WIDE"):
        s20.plan(sim, market, through="2027-01-15", today=date(2027, 1, 16))


def test_apply_needs_acknowledgement_even_when_zero_days(monkeypatch):
    monkeypatch.setattr(s20, "simulation_db_path", lambda: Path("sim.db"))
    monkeypatch.setattr(s20, "market_db_path", lambda: Path("market.db"))
    assert s20.main(["apply"]) == 2


def test_atomic_append_never_replaces_existing_data_and_validates_identity(tmp_path):
    market = _market(tmp_path)
    before = market.read_bytes()
    with pytest.raises(s20.GapFillError, match="EXISTING_DAY"):
        s20._commit_new_day(market, "KOSPI", "2026-10-08",
                            _stock_rows("KOSPI", "20261008"), _index("KOSPI", "20261008"))
    assert market.read_bytes() == before
    rows = _stock_rows("KOSPI", "20261012")
    rows[1]["code"] = rows[0]["code"]
    with pytest.raises(s20.GapFillError, match="STOCK_IDENTITY"):
        s20._commit_new_day(market, "KOSPI", "2026-10-12",
                            rows, _index("KOSPI", "20261012"))
    with sqlite3.connect(market) as c:
        assert c.execute(
            "SELECT COUNT(*) FROM stock_daily WHERE bas_dd='20261012'"
        ).fetchone()[0] == 0


def test_cap_refuses_partial_apply_without_network(tmp_path, monkeypatch):
    sim = _simulation(tmp_path, monkeypatch)
    market = _market(tmp_path)
    provider = FakeKrx()
    with pytest.raises(s20.GapFillError, match="EXPLICIT_CAP"):
        asyncio.run(s20.apply(
            sim, market, through="2026-10-13", today=date(2026, 10, 14),
            provider=provider, max_days=2,
        ))
    assert provider.calls == 0



def test_budget_block_prevents_any_market_write(tmp_path, monkeypatch):
    sim = _simulation(tmp_path, monkeypatch)
    market = _market(tmp_path)
    provider = FakeKrx()
    def reject(*a):
        raise RuntimeError("quota exhausted")
    provider.assert_budget = reject
    before = market.read_bytes()
    with pytest.raises(s20.GapFillError, match="BUDGET_PREFLIGHT"):
        asyncio.run(s20.apply(
            sim, market, through="2026-10-13",
            today=date(2026, 10, 14), provider=provider,
        ))
    assert market.read_bytes() == before
    assert provider.calls == 0
    assert not provider.started
