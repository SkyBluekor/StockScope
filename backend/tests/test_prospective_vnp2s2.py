from __future__ import annotations

import json
import sqlite3
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.prospective import (
    ProspectiveCatalog,
    ProspectiveCatalogError,
    ProspectiveEvaluator,
    ProspectiveService,
)
from app.prospective.models import ProspectiveCaptureRequest
from tools.data.common import DataToolError
from tools.data.migrate_prospective_vnp2s2 import migrate_prospective_store


def _simulation_db(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE simulation_placeholder(id INTEGER PRIMARY KEY)")
    return path


def _market_db(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        conn.executescript(
            """
            CREATE TABLE stock_daily(
                market TEXT NOT NULL,
                bas_dd TEXT NOT NULL,
                stock_code TEXT NOT NULL,
                row_json TEXT NOT NULL,
                PRIMARY KEY(market,bas_dd,stock_code)
            );
            CREATE TABLE main_index_daily(
                market TEXT NOT NULL,
                bas_dd TEXT NOT NULL,
                row_json TEXT NOT NULL,
                PRIMARY KEY(market,bas_dd)
            );
            CREATE TABLE day_status(
                market TEXT NOT NULL,
                bas_dd TEXT NOT NULL,
                kind TEXT NOT NULL,
                status TEXT NOT NULL,
                PRIMARY KEY(market,bas_dd,kind)
            );
            """
        )
    return path


def _business_days(start: str, count: int) -> list[str]:
    current = date.fromisoformat(start)
    result: list[str] = []
    while len(result) < count:
        if current.weekday() < 5:
            result.append(current.strftime("%Y%m%d"))
        current += timedelta(days=1)
    return result


def _seed_market(
    path: Path,
    *,
    start: str = "2025-09-01",
    count: int = 220,
    market: str = "KOSPI",
    ticker: str = "005930",
) -> list[str]:
    days = _business_days(start, count)
    with sqlite3.connect(path) as conn:
        for idx, bas_dd in enumerate(days):
            close = 100.0 + idx
            stock = {
                "date": bas_dd,
                "code": ticker,
                "name": "삼성전자",
                "open": close - 0.5,
                "high": close + 1.5,
                "low": close - 1.5,
                "close": close,
                "volume": 1000000 + idx,
            }
            index = {
                "date": bas_dd,
                "open": 2500 + idx,
                "high": 2505 + idx,
                "low": 2495 + idx,
                "close": 2500 + idx,
            }
            conn.execute(
                "INSERT INTO stock_daily VALUES(?,?,?,?)",
                (market, bas_dd, ticker, json.dumps(stock)),
            )
            conn.execute(
                "INSERT INTO main_index_daily VALUES(?,?,?)",
                (market, bas_dd, json.dumps(index)),
            )
            conn.execute(
                "INSERT INTO day_status VALUES(?,?,?,?)",
                (market, bas_dd, "stock", "data"),
            )
            conn.execute(
                "INSERT INTO day_status VALUES(?,?,?,?)",
                (market, bas_dd, "index", "data"),
            )
    return days


def _candidate(
    *,
    action: str = "WAIT",
    state: str = "WATCH",
    strategy: str = "pullback",
    ticker: str = "005930",
) -> dict:
    return {
        "market": "KOSPI",
        "code": ticker,
        "name": "삼성전자",
        "rank": 1,
        "strategy": strategy,
        "decision_status": state,
        "candidate_state": state,
        "action": action,
        "entry_risk_guide": {
            "price_rule": {
                "kind": "RANGE",
                "range_low": 100,
                "range_high": 110,
            },
            "risk": {
                "invalidation_price": 95,
                "target1_price": 120,
                "target2_price": 130,
            },
        },
    }


def _scanner_result(
    signal_date: str,
    *,
    fingerprint: str,
    candidate: dict | None = None,
) -> dict:
    row = candidate or _candidate()
    return {
        "version": "0.21.3.7",
        "scanner_cache_hit": False,
        "generated_at": f"{signal_date}T10:00:00",
        "requested_as_of": signal_date,
        "market_scope": "ALL",
        "data_dates": {"KOSPI": signal_date, "KOSDAQ": signal_date},
        "input_fingerprint": fingerprint,
        "partial_data": False,
        "summary": {
            "candidate_count": 1,
            "shown_count": 1,
        },
        "candidates": [row],
        "more_candidates": [],
        "horizon_context": {
            "intent": "LEGACY_UNSPECIFIED",
            "policy_version": "VN_P1_S2_HORIZON_CONTEXT_V1",
        },
        "diagnostics": {
            "reproducibility_audit": {
                "production_baseline": "BASELINE_TEST",
            }
        },
    }


def _payload(signal_date: str | None = None):
    return SimpleNamespace(
        market_scope="ALL",
        as_of_date=signal_date,
        candidate_limit=5,
        horizon_intent=None,
    )


def test_migration_is_idempotent_and_does_not_backfill_history(tmp_path: Path) -> None:
    simulation_db = _simulation_db(tmp_path / "simulation.db")

    first = migrate_prospective_store(simulation_db)
    second = migrate_prospective_store(simulation_db)

    assert first == second
    assert first["historical_backfill_performed"] is False
    with sqlite3.connect(simulation_db) as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM prospective_capture_run"
        ).fetchone()[0] == 0
        assert conn.execute(
            "SELECT COUNT(*) FROM prospective_recommendation_sample"
        ).fetchone()[0] == 0


def test_migration_rolls_back_on_incompatible_existing_table(tmp_path: Path) -> None:
    simulation_db = _simulation_db(tmp_path / "simulation.db")
    with sqlite3.connect(simulation_db) as conn:
        conn.execute(
            "CREATE TABLE prospective_capture_run(id TEXT PRIMARY KEY)"
        )

    with pytest.raises(DataToolError):
        migrate_prospective_store(simulation_db)

    with sqlite3.connect(simulation_db) as conn:
        names = {
            str(row[0])
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        assert "prospective_capture_run" in names
        assert "prospective_schema_meta" not in names
        assert "prospective_evaluation_protocol" not in names


def test_capture_is_independent_from_tracking_and_deduplicates_same_result(
    tmp_path: Path,
) -> None:
    simulation_db = _simulation_db(tmp_path / "simulation.db")
    market_db = _market_db(tmp_path / "market.db")
    migrate_prospective_store(simulation_db)
    service = ProspectiveService(simulation_db, market_db)

    first_begin = service.try_begin_scanner_capture(
        source_job_id="scanner-job-a",
        payload=_payload("2026-09-23"),
    )
    assert first_begin["status"] == "PENDING"

    result = _scanner_result("2026-09-23", fingerprint="fp-a")
    first = service.try_finalize_scanner_capture(
        source_job_id="scanner-job-a",
        payload=_payload("2026-09-23"),
        result=result,
    )
    assert first["status"] == "COMPLETE"
    assert first["returned_candidate_count"] == 1

    service.try_begin_scanner_capture(
        source_job_id="scanner-job-b",
        payload=_payload("2026-09-23"),
    )
    second = service.try_finalize_scanner_capture(
        source_job_id="scanner-job-b",
        payload=_payload("2026-09-23"),
        result=result,
    )
    assert second["status"] == "DUPLICATE"
    assert second["canonical_capture_id"] == first["capture_id"]

    samples = service.catalog.list_samples()
    assert len(samples) == 1
    assert samples[0]["ticker"] == "005930"
    assert samples[0]["signal_date"] == "2026-09-23"


def test_capture_not_ready_never_breaks_scanner_path(tmp_path: Path) -> None:
    simulation_db = _simulation_db(tmp_path / "simulation.db")
    service = ProspectiveService(
        simulation_db,
        tmp_path / "missing-market.db",
    )

    result = service.try_begin_scanner_capture(
        source_job_id="scanner-job",
        payload=_payload("2026-09-23"),
    )

    assert result["status"] == "NOT_READY"
    assert result["code"] == "PROSPECTIVE_MIGRATION_REQUIRED"


def test_pending_capture_and_running_evaluation_recover_as_interrupted(
    tmp_path: Path,
) -> None:
    simulation_db = _simulation_db(tmp_path / "simulation.db")
    market_db = _market_db(tmp_path / "market.db")
    migrate_prospective_store(simulation_db)
    service = ProspectiveService(simulation_db, market_db)

    service.try_begin_scanner_capture(
        source_job_id="pending-scanner",
        payload=_payload("2026-09-23"),
    )
    assert service.catalog.mark_pending_interrupted() == 1
    capture = service.catalog.get_capture_by_job("pending-scanner")
    assert capture is not None
    assert capture["status"] == "INTERRUPTED"

    protocol = service.create_protocol(
        client_request_id="protocol-recovery",
        name="recovery",
        market_scope="ALL",
        strategy=None,
        development_start="2026-01-01",
        development_end="2026-03-31",
        holdout_start="2026-05-01",
        holdout_end="2026-07-31",
        execution_mode="OBSERVATION_ONLY",
    )
    run = service.create_evaluation_run(
        protocol_id=protocol["id"],
        client_request_id="run-recovery",
    )
    service.catalog.begin_evaluation_run(run["id"])
    assert service.catalog.mark_running_evaluations_interrupted() == 1
    interrupted = service.catalog.get_evaluation_run(run["id"])
    assert interrupted is not None
    assert interrupted["status"] == "INTERRUPTED"

    restarted = service.catalog.begin_evaluation_run(run["id"])
    assert restarted["status"] == "RUNNING"
    assert restarted["restart_count"] == 1


def test_protocol_requires_explicit_development_and_holdout(tmp_path: Path) -> None:
    simulation_db = _simulation_db(tmp_path / "simulation.db")
    market_db = _market_db(tmp_path / "market.db")
    migrate_prospective_store(simulation_db)
    service = ProspectiveService(simulation_db, market_db)

    with pytest.raises(ProspectiveCatalogError) as caught:
        service.create_protocol(
            client_request_id="bad-protocol",
            name="bad",
            market_scope="ALL",
            strategy=None,
            development_start=None,
            development_end=None,
            holdout_start="2026-05-01",
            holdout_end="2026-07-31",
        )

    assert caught.value.code == "PROSPECTIVE_TIME_SPLIT_REQUIRED"


def test_time_split_purges_boundary_overlap_and_keeps_holdout_separate(
    tmp_path: Path,
) -> None:
    simulation_db = _simulation_db(tmp_path / "simulation.db")
    market_db = _market_db(tmp_path / "market.db")
    days = _seed_market(market_db, start="2025-09-01", count=260)
    migrate_prospective_store(simulation_db)
    service = ProspectiveService(simulation_db, market_db)

    # Pick actual seeded business dates so local-only evaluation has exact D rows.
    dev_signal = "2026-01-23"
    holdout_signal = "2026-02-03"
    assert dev_signal.replace("-", "") in days
    assert holdout_signal.replace("-", "") in days

    for job_id, signal, fp in [
        ("dev-job", dev_signal, "fp-dev"),
        ("hold-job", holdout_signal, "fp-hold"),
    ]:
        service.try_begin_scanner_capture(
            source_job_id=job_id,
            payload=_payload(signal),
        )
        finalized = service.try_finalize_scanner_capture(
            source_job_id=job_id,
            payload=_payload(signal),
            result=_scanner_result(signal, fingerprint=fp),
        )
        assert finalized["status"] == "COMPLETE"

    protocol = service.create_protocol(
        client_request_id="time-split-protocol",
        name="time split",
        market_scope="ALL",
        strategy=None,
        development_start="2026-01-01",
        development_end="2026-01-30",
        holdout_start="2026-02-02",
        holdout_end="2026-03-31",
        purge_trading_days=20,
        execution_mode="OBSERVATION_ONLY",
    )
    run = service.create_evaluation_run(
        protocol_id=protocol["id"],
        client_request_id="time-split-run",
    )
    detail = service.execute_evaluation_run(run["id"])

    assert detail["run"]["status"] == "COMPLETED"
    units = detail["units"]
    dev = next(unit for unit in units if unit["signal_date"] == dev_signal)
    hold = next(unit for unit in units if unit["signal_date"] == holdout_signal)
    assert dev["split"] == "PURGED"
    assert dev["exclusion_reason"] == "HOLDOUT_BOUNDARY_OVERLAP"
    assert hold["split"] == "HOLDOUT"
    assert hold["return_5d"] is not None
    assert detail["report"]["summary"]["split_counts"]["PURGED"] == 1
    assert detail["report"]["summary"]["split_counts"]["HOLDOUT"] == 1


def test_non_entry_candidate_is_not_virtual_execution(tmp_path: Path) -> None:
    simulation_db = _simulation_db(tmp_path / "simulation.db")
    market_db = _market_db(tmp_path / "market.db")
    days = _seed_market(market_db, start="2025-09-01", count=260)
    migrate_prospective_store(simulation_db)
    service = ProspectiveService(simulation_db, market_db)

    signal = "2026-02-03"
    assert signal.replace("-", "") in days
    service.try_begin_scanner_capture(
        source_job_id="wait-job",
        payload=_payload(signal),
    )
    service.try_finalize_scanner_capture(
        source_job_id="wait-job",
        payload=_payload(signal),
        result=_scanner_result(
            signal,
            fingerprint="wait-fp",
            candidate=_candidate(action="WAIT", state="WATCH"),
        ),
    )
    protocol = service.create_protocol(
        client_request_id="wait-protocol",
        name="wait",
        market_scope="ALL",
        strategy=None,
        development_start="2025-10-01",
        development_end="2025-12-31",
        holdout_start="2026-01-02",
        holdout_end="2026-03-31",
        execution_mode="PRODUCTION_POLICY",
    )
    run = service.create_evaluation_run(
        protocol_id=protocol["id"],
        client_request_id="wait-run",
    )
    detail = service.execute_evaluation_run(run["id"])
    unit = detail["units"][0]

    assert unit["execution_status"] == "NOT_EXECUTED"
    assert unit["execution_reason"] == "SCANNER_WAIT"
    assert unit["net_return_pct"] is None


def test_censored_mark_is_never_realized_return() -> None:
    protocol = {
        "id": "p1",
        "protocol_version": "VN_P2_S2_PROTOCOL_V1",
        "spec_hash": "hash",
        "spec": {},
    }
    base = {
        "capture_run_id": "capture",
        "sample_index": 0,
        "split": "HOLDOUT",
        "maturity_status": "IMMATURE",
        "market": "KOSPI",
        "strategy": "pullback",
        "return_5d": None,
        "return_10d": None,
        "return_20d": None,
        "execution_status": "CENSORED",
        "net_return_pct": None,
        "mark_return_pct": 3.25,
    }
    counts, report = ProspectiveEvaluator.summarize(
        protocol=protocol,
        units=[base],
    )

    assert counts["source_sample_count"] == 1
    assert report["virtual_execution"]["realized_net_return"]["sample_count"] == 0
    assert report["virtual_execution"]["censored_mark_return"]["sample_count"] == 1
    assert report["virtual_execution"]["censored_is_realized_return"] is False


def test_cancelled_evaluation_requires_new_run(tmp_path: Path) -> None:
    simulation_db = _simulation_db(tmp_path / "simulation.db")
    market_db = _market_db(tmp_path / "market.db")
    migrate_prospective_store(simulation_db)
    service = ProspectiveService(simulation_db, market_db)
    protocol = service.create_protocol(
        client_request_id="cancel-protocol",
        name="cancel",
        market_scope="ALL",
        strategy=None,
        development_start="2026-01-01",
        development_end="2026-03-31",
        holdout_start="2026-05-01",
        holdout_end="2026-07-31",
        execution_mode="OBSERVATION_ONLY",
    )
    run = service.create_evaluation_run(
        protocol_id=protocol["id"],
        client_request_id="cancel-run",
    )
    service.catalog.begin_evaluation_run(run["id"])
    service.cancel_evaluation_run(run["id"])
    assert service.catalog.evaluation_cancel_requested(run["id"]) is True
    service.catalog.mark_evaluation_cancelled(run["id"])

    with pytest.raises(ProspectiveCatalogError) as caught:
        service.catalog.begin_evaluation_run(run["id"])
    assert caught.value.code == "PROSPECTIVE_EVALUATION_CANCELLED"
