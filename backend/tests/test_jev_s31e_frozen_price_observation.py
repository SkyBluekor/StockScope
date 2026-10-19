"""S31-E: existing evaluator on frozen synthetic receipt + strict EOD cutoff."""
from __future__ import annotations

from copy import deepcopy
from datetime import date, timedelta
import json
import sqlite3

import pytest

from app.jev.research_scanner_s24 import SOURCE, ResearchCaptureError, digest
from app.jev.s31e_frozen_price_observation import observe_frozen_candidates
from tools.data import jev_s31e_observe as cli


def _receipt():
    identity = {
        "strategy_key": "pullback",
        "strategy_version_id": "current-strategy-id",
        "definition_hash": "immutable-strategy-hash",
    }
    raw = []
    for i in range(5):
        raw.append({
            "code": str(1820 + i).zfill(6), "name": f"가상-{i}",
            "market": "KOSPI", "data_date": "2026-10-14",
            "action": "ENTRY_CANDIDATE", "strategy": identity["strategy_key"],
            "strategy_version_id": identity["strategy_version_id"],
            "strategy_definition_hash": identity["definition_hash"],
            "risk": {"status": "READY", "warning": False},
            "conditions": {"passed": 5, "total": 5, "missing": 0},
            "priority": {
                "rank": i + 1, "tie_group": 1, "tie_size": 5,
                "strict_rank": False, "tier": "READY",
                "tie_focus": i == 0, "tie_focus_order": 0 if i == 0 else 1,
                "tie_breaker": "STRUCTURAL_TARGET_NEAREST_PROMOTE",
                "structural_target_distance_pct": 4.0 + i,
                "historical_status": "DATA_UNAVAILABLE",
            },
            "entry_risk_guide": {
                "risk": {
                    "entry_reference_price": 100.0, "invalidation_price": 95.0,
                    "target1_price": 107.5, "rr1": 1.5,
                    "structural_target1_price": 104.0 + i,
                }
            },
        })
    body = {
        "version": "Q7_S24_ISOLATED_RESEARCH_SCANNER_V1",
        "authority": SOURCE, "execution_mode": "POSTHOC_TECHNICAL_SMOKE_ONLY",
        "q7_approval_eligible": False,
        "production_policy_activation_allowed": False,
        "trusted_precommit_timestamp_proven": False,
        "independent_capture_timestamp_proven": False,
        "market_publication_timestamp_proven": False,
        "jev_model_calls": 0,
        "source_date": "2026-10-14", "market_scope": "KOSPI",
        "original_strategy_rows": [identity],
        "original_scanner_candidates": raw,
        "candidate_count": 5, "entry_candidates": 5,
    }
    return {**body, "payload_hash": digest(body)}


def _market(tmp_path, *, future_days=20, missing_ticker_end_day=None):
    market = tmp_path / "market_history.db"
    with sqlite3.connect(market) as conn:
        conn.executescript("""
        CREATE TABLE day_status(
          bas_dd TEXT,market TEXT,kind TEXT,status TEXT
        );
        CREATE TABLE stock_daily(
          bas_dd TEXT,market TEXT,stock_code TEXT,row_json TEXT
        );
        CREATE TABLE main_index_daily(
          bas_dd TEXT,market TEXT,row_json TEXT
        );
        """)
        days = []
        cursor = date(2026, 10, 15)
        while len(days) < future_days:
            if cursor.weekday() < 5:
                days.append(cursor.strftime("%Y%m%d"))
            cursor += timedelta(days=1)
        base_day = "20261014"
        for i in range(5):
            conn.execute("INSERT INTO stock_daily VALUES(?,?,?,?)",
                (base_day, "KOSPI", str(1820 + i).zfill(6),
                 json.dumps({"date": base_day, "close": 100 + i})))
        for index, day in enumerate(days, 1):
            conn.execute("INSERT INTO day_status VALUES(?,?,?,?)",
                         (day, "KOSPI", "stock", "data"))
            conn.execute("INSERT INTO day_status VALUES(?,?,?,?)",
                         (day, "KOSPI", "index", "data"))
            conn.execute("INSERT INTO main_index_daily VALUES(?,?,?)",
                         (day, "KOSPI", json.dumps({"date": day, "close": 200})))
            for i in range(5):
                if missing_ticker_end_day == index and i == 0:
                    continue
                conn.execute("INSERT INTO stock_daily VALUES(?,?,?,?)",
                    (day, "KOSPI", str(1820 + i).zfill(6),
                     json.dumps({"date": day, "close": (100 + i)*(1 + index/100),
                                 "high": (100 + i)*(1 + index/100),
                                 "low": (100 + i)*(1 + index/100)})))
    return market


def test_eod_cutoff_prevents_lookahead_and_no_source_mutation(tmp_path, monkeypatch):
    market = _market(tmp_path, future_days=20)
    receipt = _receipt()
    unchanged = deepcopy(receipt)
    # Use a synthetic fixed clock so this test works before/after 2026-11.
    from app.jev import s31e_frozen_price_observation as module
    class Clock:
        @staticmethod
        def now(tz):
            return type("Time", (), {"date": lambda self: date(2026, 12, 31)})()
    monkeypatch.setattr(module, "datetime", Clock)
    report = observe_frozen_candidates(receipt, market, as_of="2026-10-19")
    assert receipt == unchanged
    assert report["candidate_count"] == 5
    assert report["observed_window_counts"] == {"5d": 0, "10d": 0, "20d": 0}
    assert all(x["completed_market_days_after_signal"] == 3 for x in report["candidates"])
    assert all(x["windows"]["5d"]["return_pct"] is None for x in report["candidates"])
    assert all(x["evaluated_through"] == "2026-10-19" for x in report["candidates"])
    assert report["jev_model_calls"] == 0
    assert report["market_network_requests"] == 0
    assert report["production_db_writes"] == 0


def test_observes_5_10_20_returns_on_complete_synthetic_eod(tmp_path, monkeypatch):
    market = _market(tmp_path)
    receipt = _receipt()
    from app.jev import s31e_frozen_price_observation as module
    class Clock:
        @staticmethod
        def now(tz):
            return type("Time", (), {"date": lambda self: date(2026, 12, 31)})()
    monkeypatch.setattr(module, "datetime", Clock)
    report = observe_frozen_candidates(receipt, market, as_of="2026-11-30")
    assert report["observed_window_counts"] == {"5d": 5, "10d": 5, "20d": 5}
    assert all(x["windows"]["5d"]["return_pct"] == 5.0 for x in report["candidates"])
    assert all(x["windows"]["10d"]["return_pct"] == 10.0 for x in report["candidates"])
    assert all(x["windows"]["20d"]["return_pct"] == 20.0 for x in report["candidates"])
    assert all(x["jev_decision"] is None for x in report["candidates"])
    assert report["signal_close_is_executable_entry"] is False
    assert report["q7_prospective_precommit_proven"] is False
    assert report["investment_uplift_proven"] is False


def test_target_day_missing_returns_are_null_not_zero(tmp_path, monkeypatch):
    market = _market(tmp_path, missing_ticker_end_day=5)
    from app.jev import s31e_frozen_price_observation as module
    class Clock:
        @staticmethod
        def now(tz):
            return type("Time", (), {"date": lambda self: date(2026, 12, 31)})()
    monkeypatch.setattr(module, "datetime", Clock)
    report = observe_frozen_candidates(_receipt(), market, as_of="2026-11-30")
    missing = report["candidates"][0]["windows"]["5d"]
    assert missing["status"] == "TARGET_DAY_STOCK_CLOSE_UNAVAILABLE"
    assert missing["return_pct"] is None
    assert report["observed_window_counts"]["5d"] == 4


def test_missing_signal_day_reference_never_fabricated(tmp_path, monkeypatch):
    market = _market(tmp_path)
    with sqlite3.connect(market) as conn:
        conn.execute(
            "DELETE FROM stock_daily WHERE bas_dd='20261014' AND stock_code='001820'"
        )
    from app.jev import s31e_frozen_price_observation as module
    class Clock:
        @staticmethod
        def now(tz):
            return type("Time", (), {"date": lambda self: date(2026, 12, 31)})()
    monkeypatch.setattr(module, "datetime", Clock)
    report = observe_frozen_candidates(_receipt(), market, as_of="2026-11-30")
    assert report["candidates"][0]["signal_close_reference"] is None
    assert report["candidates"][0]["windows"]["5d"]["status"] == "SIGNAL_CLOSE_UNAVAILABLE"
    assert report["candidates"][0]["windows"]["20d"]["return_pct"] is None


def test_missing_db_holds_without_creation(tmp_path):
    path = tmp_path / "not_there.db"
    with pytest.raises(ResearchCaptureError, match="S31E_MARKET_DB_NOT_FOUND"):
        observe_frozen_candidates(_receipt(), path, as_of="2026-10-19")
    assert not path.exists()


def test_invalid_source_and_future_date_holds(tmp_path):
    receipt = _receipt()
    receipt["original_scanner_candidates"][0]["risk"]["warning"] = True
    with pytest.raises(ResearchCaptureError, match="S28_RECEIPT_PAYLOAD_HASH_MISMATCH"):
        observe_frozen_candidates(receipt, tmp_path / "missing", as_of="2026-10-19")
    with pytest.raises(ResearchCaptureError, match="S31E_FUTURE_AS_OF_FORBIDDEN"):
        observe_frozen_candidates(_receipt(), tmp_path / "missing", as_of="2099-01-01")
    with pytest.raises(ResearchCaptureError, match="S31E_AS_OF_BEFORE_FROZEN_SOURCE"):
        observe_frozen_candidates(_receipt(), tmp_path / "missing", as_of="2026-10-13")


def test_cli_temporary_market_and_default_as_of_override(tmp_path, monkeypatch, capsys):
    market = _market(tmp_path, future_days=3)
    receipt_path = tmp_path / "frozen.json"
    receipt_path.write_text(json.dumps(_receipt(), ensure_ascii=False), encoding="utf8")
    monkeypatch.setattr(cli, "market_db_path", lambda: market)
    assert cli.main(["--receipt", str(receipt_path), "--as-of", "2026-10-19", "--json"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "LOCAL_POSTHOC_EOD_OBSERVATION_ONLY"
    assert result["observed_window_counts"]["5d"] == 0
    assert result["production_db_writes"] == 0
    assert result["jev_model_calls"] == 0


def test_cli_rejects_missing_db_and_missing_receipt(tmp_path, capsys):
    missing = tmp_path / "not_there.db"
    receipt_path = tmp_path / "frozen.json"
    receipt_path.write_text(json.dumps(_receipt(), ensure_ascii=False), encoding="utf8")
    assert cli.main([
        "--receipt", str(receipt_path), "--market-db", str(missing),
        "--as-of", "2026-10-19", "--json",
    ]) == 2
    result = json.loads(capsys.readouterr().out)
    assert result["reason_code"] == "S31E_MARKET_DB_NOT_FOUND"
    assert not missing.exists()
    assert cli.main(["--receipt", str(tmp_path / "absent")]) == 2
    assert "S31E_RECEIPT_FILE_MISSING_OR_TOO_LARGE" in capsys.readouterr().out
