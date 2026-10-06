from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from app.jev import (
    FakeJevProvider,
    JevCatalog,
    JevShadowService,
    JevTrialProtocolSpec,
    build_comparison_report,
)
from app.prospective import ProspectiveCatalog
from app.prospective.models import ProspectiveCaptureRequest
from tools.data.migrate_jev_shadow_v1 import migrate_jev_shadow_store
from tools.data.migrate_prospective_vnp2s2 import migrate_prospective_store


def _simulation_db(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        conn.execute(
            "CREATE TABLE simulation_placeholder(id INTEGER PRIMARY KEY)"
        )
    migrate_prospective_store(path)
    migrate_jev_shadow_store(path)
    return path


def _capture(
    path: Path,
    *,
    action: str = "ENTRY_CANDIDATE",
) -> dict:
    catalog = ProspectiveCatalog(path)
    request = ProspectiveCaptureRequest(
        market_scope="ALL",
        requested_as_of="2026-10-06",
        candidate_limit=5,
        horizon_intent="LEGACY_UNSPECIFIED",
        horizon_policy_version="VN_P1_S2_HORIZON_CONTEXT_V1",
        selection_policy_id="POLICY-TEST",
        selection_policy_hash="policy-hash",
    )
    catalog.begin_capture(
        source_job_id="jev-capture",
        request=request,
    )
    return catalog.finalize_capture(
        source_job_id="jev-capture",
        request=request,
        result={
            "version": "0.21.3.9",
            "requested_as_of": "2026-10-06",
            "market_scope": "ALL",
            "input_fingerprint": "fp-jev",
            "partial_data": False,
            "summary": {
                "candidate_count": 1,
                "shown_count": 1,
            },
            "diagnostics": {
                "reproducibility_audit": {
                    "production_baseline": "BASELINE-TEST",
                }
            },
            "candidates": [
                {
                    "market": "KOSPI",
                    "code": "005930",
                    "name": "삼성전자",
                    "rank": 1,
                    "strategy": "pullback",
                    "strategy_version_id": "STRAT-V1",
                    "strategy_definition_hash": "strategy-hash",
                    "decision_status": "READY",
                    "candidate_state": "READY",
                    "action": action,
                    "current_price": 100.0,
                    "conditions": {
                        "passed": 5,
                        "total": 5,
                        "missing": 0,
                        "top_missing": [],
                    },
                    "risk": {
                        "status": "READY",
                        "warning": False,
                        "warnings": [],
                    },
                    "entry_risk_guide": {
                        "current_price": 100.0,
                        "price_rule": {
                            "kind": "RANGE",
                            "status": "PASS",
                            "range_low": 98.0,
                            "range_high": 102.0,
                            "reference_price": 100.0,
                            "gap_pct": 0.0,
                        },
                        "risk": {
                            "available": True,
                            "status": "READY",
                            "reference_only": False,
                            "entry_reference_price": 100.0,
                            "invalidation_price": 95.0,
                            "stop_zone_low": 94.0,
                            "stop_zone_high": 96.0,
                            "target1_price": 110.0,
                            "target2_price": 120.0,
                            "risk_pct": 5.0,
                            "reward1_pct": 10.0,
                            "reward2_pct": 20.0,
                            "rr1": 2.0,
                            "rr2": 4.0,
                            "structure_rating": "GOOD",
                            "needs_recheck": False,
                        },
                        "action": {"status": action},
                        "historical_verification": {
                            "verified": True,
                            "status": "GOOD",
                            "future_return": 999.0,
                        },
                    },
                    "historical_fit": {
                        "status": "GOOD",
                        "trades": 999,
                        "win_rate": 99.0,
                    },
                    "news": {"headline": "MUST_NOT_LEAK"},
                    "event_evidence": {
                        "event": "MUST_NOT_LEAK"
                    },
                    "macro": {"state": "MUST_NOT_LEAK"},
                    "holdings": {"quantity": 123},
                    "future_outcome": {
                        "return_20d": 999.0
                    },
                }
            ],
            "more_candidates": [],
        },
    )


def _frozen_protocol(
    catalog: JevCatalog,
    *,
    fake_mode: str = "PASS_THROUGH",
) -> dict:
    protocol = catalog.create_protocol(
        client_request_id=f"protocol-{fake_mode}",
        spec=JevTrialProtocolSpec(
            name="fake shadow",
            provider_id="FAKE",
            model_id="FAKE-MODEL",
            model_revision="FAKE-REV-1",
            prompt_version="PROMPT-V1",
            prompt_hash="prompt-hash",
            generation_settings={"fake_mode": fake_mode},
            recruitment_start="2026-10-01",
            recruitment_end="2026-10-31",
            min_mature_candidates=10,
            min_disagreements=2,
            max_error_rate=0.10,
            max_abstain_rate=0.25,
            budget_limit_usd=1.0,
        ),
    )
    assert protocol["status"] == "FROZEN"
    catalog.set_activation(
        protocol["id"],
        enabled=True,
        allow_network=False,
    )
    return protocol


@pytest.mark.asyncio
async def test_quant_only_projection_and_baseline_immutability(
    tmp_path: Path,
) -> None:
    db = _simulation_db(tmp_path / "simulation.db")
    capture = _capture(db)
    catalog = JevCatalog(db)
    _frozen_protocol(catalog)

    with sqlite3.connect(db) as conn:
        before = conn.execute(
            """
            SELECT snapshot_json,snapshot_hash
            FROM prospective_recommendation_sample
            WHERE capture_run_id=? AND sample_index=0
            """,
            (capture["id"],),
        ).fetchone()

    service = JevShadowService(
        db,
        provider_override=FakeJevProvider(
            mode="PASS_THROUGH"
        ),
    )
    reviews = await service.process_capture(capture["id"])
    assert len(reviews) == 1
    review = reviews[0]
    assert review["status"] == "VALID"
    assert review["decision"] == "PASS_THROUGH"

    encoded = json.dumps(
        review["input"],
        ensure_ascii=False,
    ).lower()
    assert "future_outcome" not in review["input"]
    for forbidden in (
        "must_not_leak",
        "historical_fit",
        "historical_verification",
        "\"news\"",
        "event_evidence",
        "\"macro\"",
        "\"holdings\"",
    ):
        assert forbidden not in encoded

    with sqlite3.connect(db) as conn:
        after = conn.execute(
            """
            SELECT snapshot_json,snapshot_hash
            FROM prospective_recommendation_sample
            WHERE capture_run_id=? AND sample_index=0
            """,
            (capture["id"],),
        ).fetchone()
    assert before == after


@pytest.mark.asyncio
async def test_output_validation_error_falls_back(
    tmp_path: Path,
) -> None:
    db = _simulation_db(tmp_path / "simulation.db")
    capture = _capture(db)
    catalog = JevCatalog(db)
    _frozen_protocol(
        catalog,
        fake_mode="UNKNOWN_EVIDENCE",
    )
    service = JevShadowService(
        db,
        provider_override=FakeJevProvider(
            mode="UNKNOWN_EVIDENCE"
        ),
    )

    review = (await service.process_capture(capture["id"]))[0]
    assert review["status"] == "ERROR"
    assert review["decision"] == "ABSTAIN"
    assert review["abstain_reason"] == "MODEL_ERROR"
    assert (
        review["failure_code"]
        == "OUTPUT_VALIDATION_ERROR"
    )


def test_idempotency_and_restart_do_not_recall(
    tmp_path: Path,
) -> None:
    db = _simulation_db(tmp_path / "simulation.db")
    capture = _capture(db)
    catalog = JevCatalog(db)
    _frozen_protocol(catalog)
    service = JevShadowService(db)

    first = service.enqueue_capture(capture["id"])
    second = service.enqueue_capture(capture["id"])
    assert len(first) == 1
    assert len(second) == 1
    assert first[0]["id"] == second[0]["id"]
    assert first[0]["status"] == "PENDING"

    assert catalog.mark_pending_interrupted() == 1
    interrupted = catalog.get_review(first[0]["id"])
    assert interrupted is not None
    assert interrupted["status"] == "INTERRUPTED"
    assert (
        interrupted["failure_code"]
        == "PROCESS_RESTART"
    )


def test_non_entry_candidate_is_skipped(
    tmp_path: Path,
) -> None:
    db = _simulation_db(tmp_path / "simulation.db")
    capture = _capture(db, action="WAIT")
    catalog = JevCatalog(db)
    _frozen_protocol(catalog)
    service = JevShadowService(db)

    reviews = service.enqueue_capture(capture["id"])
    assert len(reviews) == 1
    assert reviews[0]["status"] == "SKIPPED"
    assert (
        reviews[0]["failure_code"]
        == "OUT_OF_SCOPE_ACTION"
    )


def test_secret_value_is_not_persisted(
    monkeypatch,
    tmp_path: Path,
) -> None:
    sentinel = "JEV_SECRET_SENTINEL_DO_NOT_STORE"
    monkeypatch.setenv("JEV_API_KEY", sentinel)
    db = _simulation_db(tmp_path / "simulation.db")
    _capture(db)
    catalog = JevCatalog(db)
    _frozen_protocol(catalog)

    with sqlite3.connect(db) as conn:
        dump = "\n".join(conn.iterdump())
    assert sentinel not in dump


def test_real_provider_is_not_callable_without_network_authorization(
    tmp_path: Path,
) -> None:
    db = _simulation_db(tmp_path / "simulation.db")
    capture = _capture(db)
    catalog = JevCatalog(db)
    protocol = catalog.create_protocol(
        client_request_id="real-unfrozen",
        spec=JevTrialProtocolSpec(
            name="real provider remains blocked",
            provider_id="UNFROZEN",
        ),
    )
    assert protocol["status"] == "UNFROZEN"
    catalog.set_activation(
        protocol["id"],
        enabled=True,
        allow_network=False,
    )

    review = JevShadowService(db).enqueue_capture(
        capture["id"]
    )[0]
    assert review["status"] == "SKIPPED"
    assert (
        review["failure_code"]
        == "JEV_NETWORK_NOT_AUTHORIZED"
    )


def test_comparison_uses_valid_review_required_and_closed_only() -> None:
    reviews = [
        {
            "id": "r1",
            "capture_run_id": "c1",
            "sample_index": 0,
            "requested_at": "2026-10-01T00:00:00Z",
            "attempt": 1,
            "status": "VALID",
            "decision": "REVIEW_REQUIRED",
        },
        {
            "id": "r2",
            "capture_run_id": "c1",
            "sample_index": 1,
            "requested_at": "2026-10-01T00:00:01Z",
            "attempt": 1,
            "status": "VALID",
            "decision": "REVIEW_REQUIRED",
        },
        {
            "id": "r3",
            "capture_run_id": "c1",
            "sample_index": 2,
            "requested_at": "2026-10-01T00:00:02Z",
            "attempt": 1,
            "status": "ERROR",
            "decision": "ABSTAIN",
        },
    ]
    outcomes = [
        {
            "capture_run_id": "c1",
            "sample_index": 0,
            "execution_status": "CLOSED",
            "net_return_pct": -10.0,
        },
        {
            "capture_run_id": "c1",
            "sample_index": 1,
            "execution_status": "CLOSED",
            "net_return_pct": 5.0,
        },
        {
            "capture_run_id": "c1",
            "sample_index": 2,
            "execution_status": "CLOSED",
            "net_return_pct": -2.0,
        },
        {
            "capture_run_id": "c1",
            "sample_index": 3,
            "execution_status": "CENSORED",
            "net_return_pct": None,
        },
    ]

    report = build_comparison_report(
        reviews,
        outcomes,
    )
    assert report["comparable_closed_count"] == 3
    assert report["disagreement_count"] == 2
    assert report["avoided_loss_pct_sum"] == 10.0
    assert report["missed_profit_pct_sum"] == 5.0
    assert report["baseline_mean_return_pct"] == pytest.approx(
        -7.0 / 3.0
    )
    assert report["shadow_mean_return_pct"] == pytest.approx(
        -2.0 / 3.0
    )
    assert report[
        "incremental_return_per_opportunity_pct"
    ] == pytest.approx(5.0 / 3.0)
    assert report["retained_candidate_loss_rate"] == 1.0
