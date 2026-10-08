from __future__ import annotations

import json
import sqlite3
from copy import deepcopy
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.backtest.candidate_priority import rank_candidates
from app.backtest.reproducibility_audit import _candidate_snapshot
from app.main import app
from app.prospective.catalog import ProspectiveCatalog
from app.prospective.models import ProspectiveCaptureRequest
from app.prospective.rank_audit_adapter import extract_rank_evidence_from_audit
from app.prospective.rank_comparison import compare_capture_candidates
from app.prospective.rank_evidence import persist_rank_evidence
from tools.data.migrate_prospective_vnp2s2 import migrate_prospective_store
from tools.data.migrate_scanner_rank_evidence_jevx1 import migrate_scanner_rank_evidence_store


def _candidate(
    code: str, *, missing: int = 0, warning: bool = False, gap: float | None = 1.0,
    fit: float = 100.0, structural: float | None = None,
) -> dict:
    return {
        "market": "KOSPI", "code": code, "name": "종목" + code,
        "strategy": "pullback", "candidate_state": "READY",
        "action": "ENTRY_CANDIDATE", "current_price": 100.0,
        "conditions": {"passed": 6 - missing, "total": 6, "missing": missing},
        "risk": {"status": "WARNING" if warning else "READY", "warning": warning},
        "entry_risk_guide": {
            "price_rule": {"kind": "RANGE", "gap_pct": gap} if gap is not None
            else {"kind": "UNAVAILABLE"},
            "risk": {
                "entry_reference_price": 100.0,
                "structural_target1_price": structural,
            },
        },
        "_strategy_fit_score": fit,
    }


def _capture(
    tmp_path: Path, candidates: list[dict], *,
    partial: bool = False, migrate: bool = True, store: bool = True,
) -> tuple[Path, str, list[dict], list[dict]]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    db = tmp_path / "simulation.db"
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE placeholder(id INTEGER PRIMARY KEY)")
    migrate_prospective_store(db)
    if migrate:
        migrate_scanner_rank_evidence_store(db)
    ranked, _ = rank_candidates(deepcopy(candidates))
    audit_path = tmp_path / "scanner-repro_pair.json"
    audit_path.write_text(json.dumps({
        "scanner_version": "test", "analysis_date": "2026-10-07",
        "market_scope": "ALL", "result_source": "fresh_analysis",
        "candidate_count": len(ranked),
        "candidates": [_candidate_snapshot(row, i) for i, row in enumerate(ranked, 1)],
    }, ensure_ascii=False), encoding="utf-8")
    result = {
        "version": "test", "requested_as_of": "2026-10-07",
        "market_scope": "ALL", "partial_data": partial,
        "data_dates": {"KOSPI": "2026-10-07"},
        "summary": {"candidate_count": len(ranked), "shown_count": len(ranked)},
        "input_fingerprint": {"source": "test"},
        "candidates": ranked[:1], "more_candidates": ranked[1:],
        "diagnostics": {
            "reproducibility_audit": {"written": True, "path": str(audit_path)}
        },
    }
    evidence = extract_rank_evidence_from_audit(result, audit_root=tmp_path)
    assert evidence is not None and len(evidence) == len(ranked)
    request = ProspectiveCaptureRequest(
        market_scope="ALL", requested_as_of="2026-10-07",
        candidate_limit=5, horizon_intent="SHORT",
        horizon_policy_version="test",
    )
    catalog = ProspectiveCatalog(db)
    frozen = catalog.finalize_capture(source_job_id="first", request=request, result=result)
    assert frozen["status"] == ("PARTIAL" if partial else "COMPLETE")
    if store:
        assert persist_rank_evidence(
            db_path=db, capture={"capture_id": frozen["id"], "status": frozen["status"]},
            evidence_rows=evidence,
        )["status"] == ("STORED" if migrate else "RANK_EVIDENCE_MIGRATION_REQUIRED")
    return db, frozen["id"], ranked, evidence


@pytest.mark.parametrize(
    "a,b,field",
    [
        (_candidate("000101"), _candidate("000102", missing=1), "tier_order"),
        (_candidate("000101", missing=1), _candidate("000102", missing=2), "missing"),
        (_candidate("000101", missing=3), _candidate("000102", missing=3, warning=True), "risk_quality"),
        (_candidate("000101", gap=1.0), _candidate("000102", gap=None), "entry_gap_missing"),
        (_candidate("000101", gap=0.5), _candidate("000102", gap=1.5), "entry_gap_pct"),
        (_candidate("000101", fit=120.0), _candidate("000102", fit=70.0), "negative_strategy_fit"),
        (_candidate("000101", structural=110.0), _candidate("000102", structural=105.0), "tie_focus_order"),
        (_candidate("000101"), _candidate("000102"), "code"),
    ],
)
def test_each_actual_sort_dimension_is_explained(
    tmp_path: Path, a: dict, b: dict, field: str,
) -> None:
    db, capture_id, ranked, evidence = _capture(tmp_path, [a, b])
    answer = compare_capture_candidates(
        db_path=db, capture_id=capture_id, left_sample_index=0, right_sample_index=1,
    )
    assert answer["status"] == "AVAILABLE", answer
    assert answer["decisive_field"] == field
    assert answer["winner_sample_index"] == 0
    assert answer["ranking_changed"] is False
    assert answer["provider_called"] is False
    assert answer["factors"][list(x[0] for x in (
        ("tier_order",), ("missing",), ("risk_quality",), ("entry_gap_missing",),
        ("entry_gap_pct",), ("negative_strategy_fit",), ("tie_focus_order",), ("code",),
    )).index(field)]["decisive"] is True
    assert [x["code"] for x in ranked] == [x["code"] for x in sorted(ranked, key=lambda x: x["priority"]["rank"])]
    assert "3년" in " ".join(answer["limitations"])
    if field == "code":
        assert "투자 품질" in answer["decisive_reason"]


def test_reverse_order_resolves_correct_winner(tmp_path: Path) -> None:
    db, capture_id, _, _ = _capture(tmp_path, [_candidate("000101"), _candidate("000102", missing=1)])
    result = compare_capture_candidates(
        db_path=db, capture_id=capture_id, left_sample_index=1, right_sample_index=0,
    )
    assert result["status"] == "AVAILABLE"
    assert result["winner_sample_index"] == 0
    assert result["left"]["final_rank"] == 2
    assert result["right"]["final_rank"] == 1


def test_missing_legacy_duplicate_and_partial_behavior(tmp_path: Path) -> None:
    db, capture_id, _, _ = _capture(
        tmp_path / "one", [_candidate("000101"), _candidate("000102", missing=1)],
        store=False,
    )
    result = compare_capture_candidates(
        db_path=db, capture_id=capture_id, left_sample_index=0, right_sample_index=1,
    )
    assert result["status"] == "NOT_AVAILABLE_LEGACY"

    other = tmp_path / "two"
    other.mkdir()
    db2, partial_id, _, _ = _capture(
        other, [_candidate("000101"), _candidate("000102", missing=1)], partial=True,
    )
    partial = compare_capture_candidates(
        db_path=db2, capture_id=partial_id, left_sample_index=0, right_sample_index=1,
    )
    assert partial["status"] == "AVAILABLE"
    assert partial["capture_status"] == "PARTIAL"
    assert "부분 데이터" in " ".join(partial["limitations"])


def test_capture_validation_api_and_hash_guard(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    db, capture_id, _, _ = _capture(
        tmp_path, [_candidate("000101"), _candidate("000102", missing=1)],
    )
    monkeypatch.setenv("STOCKSCOPE_SIM_DB", str(db))
    client = TestClient(app)
    path = "/api/simulation/prospective/captures/" + capture_id + "/candidate-comparison"
    good = client.get(path, params={"left_sample_index": 0, "right_sample_index": 1})
    assert good.status_code == 200 and good.json()["status"] == "AVAILABLE"
    assert client.get(path, params={"left_sample_index": 0, "right_sample_index": 0}).status_code == 422
    assert client.get(path, params={"left_sample_index": 0, "right_sample_index": 99}).status_code == 422
    assert client.get(path, params={"left_sample_index": -1, "right_sample_index": 1}).status_code == 422
    assert client.get(path.replace(capture_id, "not-found"), params={
        "left_sample_index": 0, "right_sample_index": 1,
    }).status_code == 404

    with sqlite3.connect(db) as conn:
        conn.execute("DROP TRIGGER trg_scanner_rank_evidence_immutable")
        conn.execute(
            "UPDATE scanner_rank_evidence SET evidence_hash='incorrect' "
            "WHERE capture_run_id=? AND sample_index=0",
            (capture_id,),
        )
    tampered = client.get(path, params={"left_sample_index": 0, "right_sample_index": 1})
    assert tampered.status_code == 200
    assert tampered.json()["status"] == "EVIDENCE_HASH_MISMATCH"


def test_migration_guard(tmp_path: Path) -> None:
    db, capture_id, _, _ = _capture(
        tmp_path, [_candidate("000101"), _candidate("000102", missing=1)],
        migrate=False, store=False,
    )
    assert compare_capture_candidates(
        db_path=db, capture_id=capture_id, left_sample_index=0, right_sample_index=1,
    )["status"] == "RANK_EVIDENCE_MIGRATION_REQUIRED"


def test_duplicate_resolves_canonical_evidence(tmp_path: Path) -> None:
    db, original_id, ranked, _ = _capture(
        tmp_path, [_candidate("000101"), _candidate("000102", missing=1)]
    )
    request = ProspectiveCaptureRequest(
        market_scope="ALL", requested_as_of="2026-10-07",
        candidate_limit=5, horizon_intent="SHORT", horizon_policy_version="test",
    )
    # Copy exact result fields required by the canonical identity.
    # A duplicate request from a different job should never create new rank proof.
    with sqlite3.connect(db) as conn:
        first = conn.execute(
            "SELECT request_json FROM prospective_capture_run WHERE id=?", (original_id,)
        ).fetchone()
    assert first is not None
    original = compare_capture_candidates(
        db_path=db, capture_id=original_id, left_sample_index=0, right_sample_index=1,
    )
    assert original["status"] == "AVAILABLE"
    # Verify canonical duplicate read path without reranking or inserting evidence.
    with sqlite3.connect(db) as conn:
        conn.execute(
            "INSERT INTO prospective_capture_run("
            "id,capture_version,source_job_id,status,request_json,market_scope,"
            "requested_as_of,candidate_limit,canonical_capture_id,created_at,updated_at)"
            " SELECT ?,capture_version,?, 'DUPLICATE',request_json,market_scope,"
            "requested_as_of,candidate_limit,id,created_at,updated_at"
            " FROM prospective_capture_run WHERE id=?",
            ("synthetic-duplicate", "other-job", original_id),
        )
    duplicated = compare_capture_candidates(
        db_path=db, capture_id="synthetic-duplicate",
        left_sample_index=0, right_sample_index=1,
    )
    assert duplicated["status"] == "AVAILABLE"
    assert duplicated["capture_id"] == original_id
