"""S16 local outcomes: immutable 3-capture cohort, bounded and read-only."""
from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
import sqlite3
from zoneinfo import ZoneInfo

import pytest

from app.jev import q7_observation_s16 as s16
from tools.data import q7_precommit as cli


def _db(tmp_path):
    db = tmp_path / "sim.db"
    market = tmp_path / "market.db"
    with sqlite3.connect(db) as conn:
        conn.executescript("""
        CREATE TABLE prospective_capture_run (
            id TEXT PRIMARY KEY, status TEXT, completed_at TEXT
        );
        CREATE TABLE prospective_recommendation_sample (
            capture_run_id TEXT, sample_index INTEGER, action TEXT
        );
        INSERT INTO prospective_capture_run VALUES
            ('capture-1','COMPLETE','2026-10-14T09:00:00+09:00');
        INSERT INTO prospective_recommendation_sample VALUES
            ('capture-1',0,'ENTRY_CANDIDATE'),
            ('capture-1',1,'ENTRY_CANDIDATE'),
            ('capture-1',2,'ENTRY_CANDIDATE'),
            ('capture-1',3,'ENTRY_CANDIDATE'),
            ('capture-1',4,'REFERENCE_ONLY');
        """)
    with sqlite3.connect(market) as conn:
        conn.execute("CREATE TABLE marker(id INTEGER)")
    return db, market


def _pairs():
    def sample(index, strategy, ticker, category, action="ENTRY_CANDIDATE"):
        return (
            {"id": "capture-1", "status": "COMPLETE",
             "completed_at": "2026-10-14T09:00:00+09:00"},
            {"capture_run_id": "capture-1", "sample_index": index,
             "signal_date": "2026-10-12", "market": "KOSPI",
             "ticker": ticker, "strategy": strategy, "action": action,
             "snapshot_hash": str(index), "category": category,
             "snapshot": {"valid": True}},
        )
    return [
        sample(0, "pullback", "005930", "LEGACY_LIMITED"),
        sample(1, "pullback", "005930", "LEGACY_LIMITED"),
        sample(2, "ma20_rebound", "009150", "LOCAL_VALIDATED"),
        sample(3, "ma20_rebound", "000660", "INVALID"),
        sample(4, "pullback", "003280", "REFERENCE_ONLY", "REFERENCE_ONLY"),
    ]


class FakeEvaluator:
    calls = []

    def __init__(self, db):
        assert db.is_file()

    def evaluate_sample(self, *, sample, spec):
        self.calls.append(sample["sample_index"])
        assert spec["observation_windows"] == [5, 10, 20]
        if sample["sample_index"] == 2:
            return {
                "available_trading_days": 20,
                "evaluated_through": "2026-10-13",
                "return_5d": -2.0,
                "return_10d": 1.0,
                "return_20d": 3.0,
                "details": {"reference_price": 100.0},
            }
        return {
            "available_trading_days": 10,
            "evaluated_through": "2026-10-13",
            "return_5d": 2.0,
            "return_10d": None,
            "return_20d": None,
            "details": {"reference_price": 100.0},
        }


def _mock(monkeypatch, pairs=None, evaluator=FakeEvaluator):
    if pairs is None:
        pairs = _pairs()
    monkeypatch.setattr(s16, "load_frozen_candidates",
                        lambda db, *, capture_id, limit: list(pairs))
    monkeypatch.setattr(s16, "assess_frozen_candidate",
                        lambda c, s: {"category": s["category"]})
    monkeypatch.setattr(s16, "ProspectiveEvaluator", evaluator)


def test_real_simulation_db_inventory_uses_complete_denominators(tmp_path, monkeypatch):
    sim, market = _db(tmp_path)
    _mock(monkeypatch)
    FakeEvaluator.calls = []
    old_sim, old_market = sim.read_bytes(), market.read_bytes()
    report = s16.measure(sim, market, as_of=date(2026, 10, 14))
    assert sim.read_bytes() == old_sim and market.read_bytes() == old_market
    assert report["status"] == "DESCRIPTIVE_OBSERVATIONS_ONLY"
    assert report["counts_complete"] is True
    assert report["sample_count"] == 5
    assert report["entry_candidates"] == 4 and report["reference_only"] == 1
    assert report["integrity_counts"] == {
        "LOCAL_VALIDATED": 1, "LEGACY_LIMITED": 2, "INVALID": 1
    }
    assert report["duplicated_signal_keys"] == 1
    assert report["distinct_signal_keys"] == 3
    assert report["retrospective_or_later_capture_count"] == 4
    assert sorted(FakeEvaluator.calls) == [0, 1, 2]
    assert report["excluded_reason_counts"]["FROZEN_INTEGRITY_INVALID"] == 1
    assert report["windows"]["5d"]["readiness_denominator"] == 3
    assert report["windows"]["5d"]["observed"] == 3
    assert report["windows"]["5d"]["average_signal_close_change_pct"] == pytest.approx(2/3)
    assert report["windows"]["5d"]["positive_observations"] == 2
    assert report["windows"]["5d"]["negative_observations"] == 1
    assert report["windows"]["10d"]["observed"] == 1
    assert report["windows"]["10d"]["price_missing"] == 2
    assert report["windows"]["20d"]["observed"] == 1
    assert report["windows"]["20d"]["awaiting_future_trading_days"] == 2
    assert report["q7_approval_eligible"] is False
    assert report["production_activation_allowed"] is False
    assert report["model_uplift_verified"] is False
    assert report["runtime_db_writes"] == report["external_provider_calls"] == 0


def test_future_dated_market_bars_are_not_reported_as_returns(tmp_path, monkeypatch):
    sim, market = _db(tmp_path)
    class Future(FakeEvaluator):
        def evaluate_sample(self, *, sample, spec):
            result = super().evaluate_sample(sample=sample, spec=spec)
            result["evaluated_through"] = "2027-01-01"
            return result
    _mock(monkeypatch, evaluator=Future)
    report = s16.measure(sim, market, as_of=date(2026, 10, 14))
    assert report["windows"]["5d"]["observed"] == 0
    assert report["windows"]["5d"]["post_as_of_data_rejected"] == 3
    assert report["excluded_reason_counts"]["FUTURE_DATED_MARKET_EVIDENCE"] == 3


def test_price_missing_and_insufficient_days_are_not_zero_returns(tmp_path, monkeypatch):
    sim, market = _db(tmp_path)
    class Missing(FakeEvaluator):
        def evaluate_sample(self, *, sample, spec):
            return {
                "available_trading_days": 0,
                "evaluated_through": None,
                "return_5d": 5.0,
                "return_10d": None,
                "return_20d": None,
                "details": {"reference_price": None},
            }
    _mock(monkeypatch, evaluator=Missing)
    report = s16.measure(sim, market, as_of=date(2026, 10, 14))
    assert report["windows"]["5d"]["observed"] == 0
    assert report["windows"]["5d"]["awaiting_future_trading_days"] == 3
    assert report["windows"]["5d"]["average_signal_close_change_pct"] is None


def test_limit_fail_closed_no_partial_performance_denominator(tmp_path, monkeypatch):
    sim, market = _db(tmp_path)
    with sqlite3.connect(sim) as conn:
        conn.executemany(
            "INSERT INTO prospective_recommendation_sample VALUES(?,?,?)",
            [("capture-1", 100 + i, "REFERENCE_ONLY") for i in range(495)],
        )
    monkeypatch.setattr(
        s16, "load_frozen_candidates",
        lambda *a, **kw: pytest.fail("incomplete capture must not be inspected"),
    )
    result = s16.measure(sim, market, as_of=date(2026, 10, 14))
    assert result["status"] == "COHORT_TOO_LARGE_FOR_COMPLETE_AUDIT"
    assert result["counts_complete"] is False
    assert "entry_candidates" not in result


def test_no_source_and_future_asof_are_safe(tmp_path):
    sim = tmp_path / "missing_sim.db"
    market = tmp_path / "missing_market.db"
    assert s16.measure(sim, market)["status"] == "NO_SIMULATION_DB"
    assert not sim.exists() and not market.exists()
    with pytest.raises(ValueError, match="Q7_S16_AS_OF_FUTURE_OR_INVALID"):
        s16.measure(sim, market, as_of=date(2099, 1, 1))


def test_cli_observe_only_requires_existing_sources(tmp_path):
    missing = tmp_path / "none.db"
    args = cli.parser().parse_args([
        "observe", "--simulation-db", str(missing),
        "--market-db", str(tmp_path / "other.db"),
    ])
    value = cli.execute(args)
    assert value["status"] == "NO_SIMULATION_DB"
    assert value["runtime_db_writes"] == 0
    assert not missing.exists()
