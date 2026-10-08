from __future__ import annotations

import sqlite3
from copy import deepcopy
from pathlib import Path

import pytest

from app.backtest.candidate_priority import rank_candidates
from app.prospective.catalog import ProspectiveCatalog
from app.prospective.models import ProspectiveCaptureRequest, digest_json
from app.prospective.rank_evidence import persist_rank_evidence, read_rank_evidence
from tools.data.migrate_prospective_vnp2s2 import migrate_prospective_store
from tools.data.migrate_scanner_rank_evidence_jevx1 import migrate_scanner_rank_evidence_store


def _setup(path: Path) -> Path:
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE simulation_placeholder(id INTEGER PRIMARY KEY)")
    migrate_prospective_store(path)
    return path


def _source() -> tuple[dict, list[dict]]:
    candidate = {
        "market": "KOSPI", "code": "000123", "name": "synthetic",
        "strategy": "pullback", "candidate_state": "READY",
        "action": "ENTRY_CANDIDATE", "current_price": 100.0,
        "conditions": {"passed": 6, "total": 6, "missing": 0},
        "risk": {"status": "READY", "warning": False, "warnings": []},
        "entry_risk_guide": {
            "price_rule": {"kind": "RANGE", "gap_pct": 1.0},
            "risk": {"entry_reference_price": 100.0, "structural_target1_price": 110.0},
        },
        "_strategy_fit_score": 100.0,
    }
    traces: list[dict] = []
    ranked, _ = rank_candidates([candidate], evidence_sink=traces)
    result = {
        "version": "test", "requested_as_of": "2026-10-07",
        "market_scope": "ALL", "data_dates": {"KOSPI": "2026-10-07"},
        "input_fingerprint": {"source": "test"},
        "partial_data": False, "summary": {"candidate_count": 1, "shown_count": 1},
        "candidates": ranked, "more_candidates": [],
        "horizon_context": {"intent": "SHORT"},
    }
    return result, traces


def _request() -> ProspectiveCaptureRequest:
    return ProspectiveCaptureRequest(
        market_scope="ALL", requested_as_of="2026-10-07",
        candidate_limit=5, horizon_intent="SHORT",
        horizon_policy_version="test",
    )


def test_capture_hash_is_unchanged_and_evidence_is_append_only(tmp_path: Path) -> None:
    db = _setup(tmp_path / "simulation.db")
    catalog = ProspectiveCatalog(db)
    result, traces = _source()
    snapshots = [catalog._candidate_snapshot(x) for x in result["candidates"]]
    original = catalog._result_identity(request=_request(), result=result, candidates=snapshots)
    enriched = deepcopy(result)
    enriched["_rank_evidence"] = traces
    assert catalog._result_identity(
        request=_request(), result=enriched, candidates=snapshots
    ) == original

    first = catalog.finalize_capture(
        source_job_id="one", request=_request(), result=result
    )
    assert first["status"] == "COMPLETE"
    payload = {**first, "capture_id": first["id"]}
    with sqlite3.connect(db) as conn:
        before = conn.execute(
            "SELECT snapshot_json,snapshot_hash FROM prospective_recommendation_sample"
        ).fetchone()
    assert persist_rank_evidence(
        db_path=db, capture=payload, evidence_rows=traces
    )["status"] == "RANK_EVIDENCE_MIGRATION_REQUIRED"
    assert migrate_scanner_rank_evidence_store(db)["historical_backfill_performed"] is False
    assert persist_rank_evidence(
        db_path=db, capture=payload, evidence_rows=traces
    ) == {"status": "STORED", "stored": 1}
    assert persist_rank_evidence(
        db_path=db, capture=payload, evidence_rows=traces
    ) == {"status": "REUSED", "stored": 1}
    loaded = read_rank_evidence(db_path=db, capture_id=first["id"], sample_index=0)
    assert loaded["status"] == "AVAILABLE"
    assert loaded["evidence_hash"] == digest_json(loaded["evidence"])
    with sqlite3.connect(db) as conn:
        after = conn.execute(
            "SELECT snapshot_json,snapshot_hash FROM prospective_recommendation_sample"
        ).fetchone()
        assert before == after
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("UPDATE scanner_rank_evidence SET evidence_hash='bad'")
        conn.rollback()
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("DELETE FROM scanner_rank_evidence")
        conn.rollback()


def test_duplicate_reuses_canonical_and_no_historical_backfill(tmp_path: Path) -> None:
    db = _setup(tmp_path / "simulation.db")
    migrate_scanner_rank_evidence_store(db)
    catalog = ProspectiveCatalog(db)
    result, traces = _source()
    first = catalog.finalize_capture(source_job_id="one", request=_request(), result=result)
    second = catalog.finalize_capture(source_job_id="two", request=_request(), result=result)
    assert first["status"] == "COMPLETE"
    assert second["status"] == "DUPLICATE"
    assert read_rank_evidence(
        db_path=db, capture_id=second["id"], sample_index=0
    )["status"] == "NOT_AVAILABLE_LEGACY"
    assert persist_rank_evidence(
        db_path=db, capture={**second, "capture_id": second["id"]},
        evidence_rows=traces,
    )["status"] == "DUPLICATE_USE_CANONICAL_IF_PRESENT"
    assert persist_rank_evidence(
        db_path=db, capture={**first, "capture_id": first["id"]},
        evidence_rows=traces,
    )["status"] == "STORED"
    assert read_rank_evidence(
        db_path=db, capture_id=second["id"], sample_index=0
    )["status"] == "AVAILABLE"
    modified = deepcopy(traces)
    modified[0]["sort_components"]["entry_gap_pct"] = 100.0
    assert persist_rank_evidence(
        db_path=db, capture={**first, "capture_id": first["id"]},
        evidence_rows=modified,
    )["status"] == "EVIDENCE_CONFLICT"
