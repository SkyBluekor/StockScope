from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import httpx
import pytest

from app.jev.typesafe_catalog import TypeSafeJevCatalog
from app.jev.typesafe_evaluation import (
    build_typesafe_comparison_report,
    build_typesafe_evaluation_summary,
)
from app.jev.typesafe_evaluation_catalog import TypeSafeJevEvaluationCatalog
from app.jev.typesafe_evaluation_models import JEV_TYPESAFE_EVALUATION_POLICY_ID
from app.jev.typesafe_models import TypeSafeJevTrialProtocolSpec
from app.jev.typesafe_policy import (
    JEV_TYPESAFE_DISPOSITION_POLICY_HASH,
    decide_typesafe_disposition,
)
from app.jev.typesafe_provider import (
    FakeTypeSafeJevProvider,
    TypeSafeJevProviderError,
    TypeSafeSystemOneProvider,
    validate_system_one_response,
)
from app.jev.typesafe_questions import (
    JEV_TYPESAFE_QUESTION_IDS,
    JEV_TYPESAFE_QUESTION_SET_HASH,
)
from app.jev.typesafe_service import build_system_one_request, review_once
from app.jev.typesafe_state import (
    JEV_TYPESAFE_PROJECTOR_HASH,
    JEV_TYPESAFE_STATE_CONTRACT_HASH,
    project_typesafe_state,
)
from app.prospective import ProspectiveCatalog
from app.prospective.models import ProspectiveCaptureRequest
from tools.data.migrate_jev_typesafe_v2 import migrate_jev_typesafe
from tools.data.migrate_jev_typesafe_evaluation_v2 import (
    migrate_jev_typesafe_evaluation,
)
from tools.data.migrate_prospective_vnp2s2 import migrate_prospective_store


def _db(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    sqlite3.connect(path).close()
    migrate_prospective_store(path)
    migrate_jev_typesafe(path)
    return path


def _snapshot() -> dict:
    details = [
        {
            "condition_id": "pass-1",
            "raw": "현재가가 20일 이동평균선 위",
            "label": "fixture",
            "detail": "fixture",
            "status": "PASS",
            "current_value": "현재 105 · 20일 평균 100",
            "required_value": "종가가 100 이상",
            "metric_key": "price_vs_ma20",
        },
        {
            "condition_id": "pass-2",
            "raw": "거래량 평균 이상",
            "label": "fixture",
            "detail": "fixture",
            "status": "PASS",
            "current_value": "1.2배",
            "required_value": "1.00배 이상",
            "metric_key": "volume_ratio_20",
        },
    ]
    return {
        "market": "KOSPI",
        "candidate_state": "READY",
        "strategy": "TREND_FOLLOWING",
        "strategy_version_id": "strategy-v1",
        "strategy_definition_hash": "strategy-hash",
        "strategy_description": "상승 흐름이 유지되는지 확인하는 전략입니다.",
        "action": "ENTRY_CANDIDATE",
        "conditions": {"passed": 2, "total": 2, "missing": 0, "top_missing": []},
        "risk": {"status": "READY", "warning": False, "warnings": []},
        "entry_risk_guide": {
            "price_rule": {
                "kind": "ABOVE",
                "status": "MET",
                "semantic_role": "STRATEGY_CONDITION_THRESHOLD",
                "executable_entry_range": False,
            },
            "action": {"status": "ENTRY_CANDIDATE"},
            "price_consistency": {
                "status": "OK",
                "classification": "SEPARATED",
                "semantic_overlap": False,
            },
        },
        "_repro_condition_details": details,
    }


def _sample() -> dict:
    return {
        "capture_run_id": "capture-1",
        "sample_index": 0,
        "market": "KOSPI",
        "ticker": "005930",
        "name": "SHOULD_NOT_LEAVE_LOCAL_AUDIT",
        "rank": 1,
        "action": "ENTRY_CANDIDATE",
        "candidate_state": "READY",
        "strategy": "TREND_FOLLOWING",
        "signal_date": "2026-10-06",
        "horizon_intent": "SHORT",
        "horizon_policy_version": "HORIZON-V1",
        "snapshot_hash": "snapshot-hash",
        "scanner_version": "SCANNER-V",
        "scanner_baseline": "BASELINE-V",
        "input_fingerprint": "input-fingerprint",
        "snapshot": _snapshot(),
    }


def _protocol_dict() -> dict:
    return {
        "provider_id": "FAKE",
        "model_requested": "FAKE-JEV-V2",
        "expected_model_returned": "FAKE-JEV-V2",
        "deadline_seconds": 12.0,
        "threshold_low": 0.15,
        "threshold_high": 0.85,
    }


def _protocol_spec() -> TypeSafeJevTrialProtocolSpec:
    return TypeSafeJevTrialProtocolSpec(
        name="TypeSafe fake V2",
        provider_id="FAKE",
        model_requested="FAKE-JEV-V2",
        expected_model_returned="FAKE-JEV-V2",
        state_contract_hash=JEV_TYPESAFE_STATE_CONTRACT_HASH,
        projector_hash=JEV_TYPESAFE_PROJECTOR_HASH,
        question_set_hash=JEV_TYPESAFE_QUESTION_SET_HASH,
        disposition_policy_hash=JEV_TYPESAFE_DISPOSITION_POLICY_HASH,
        threshold_low=0.15,
        threshold_high=0.85,
        recruitment_duration_calendar_days=30,
        max_recruited_candidates=20,
        budget_limit_usd=1.0,
        per_call_reservation_usd=0.01,
        extra={"fake_returned_model": "FAKE-JEV-V2"},
    )


def _prospective_sample(db: Path) -> tuple[str, int]:
    catalog = ProspectiveCatalog(db)
    request = ProspectiveCaptureRequest(
        market_scope="KOSPI",
        requested_as_of="2026-10-06",
        candidate_limit=1,
        horizon_intent="SHORT",
        horizon_policy_version="HORIZON-V1",
        selection_policy_id="POLICY",
        selection_policy_hash="POLICY-HASH",
    )
    catalog.begin_capture(source_job_id="job-1", request=request)
    result = {
        "version": "SCANNER-V",
        "requested_as_of": "2026-10-06",
        "market_scope": "KOSPI",
        "data_dates": {"KOSPI": "2026-10-06"},
        "input_fingerprint": "fingerprint",
        "partial_data": False,
        "summary": {"candidate_count": 1},
        "candidates": [
            {
                **_snapshot(),
                "code": "005930",
                "name": "fixture",
                "market": "KOSPI",
                "data_date": "2026-10-06",
                "rank": 1,
            }
        ],
        "more_candidates": [],
        "horizon_context": {"intent": "SHORT"},
        "strategy_selection_policy": {
            "policy_id": "POLICY",
            "policy_hash": "POLICY-HASH",
        },
        "diagnostics": {
            "reproducibility_audit": {"production_baseline": "BASELINE-V"}
        },
    }
    capture = catalog.finalize_capture(
        source_job_id="job-1",
        request=request,
        result=result,
    )
    return capture["id"], 0


def test_typesafe_state_is_minimized_and_has_no_risk_question() -> None:
    sample = _sample()
    projection = project_typesafe_state(sample)
    encoded = json.dumps(projection.state, ensure_ascii=False)
    assert "005930" not in encoded
    assert "SHOULD_NOT_LEAVE_LOCAL_AUDIT" not in encoded
    assert '"rank"' not in encoded
    assert "stop" not in encoded.lower()
    assert "target" not in encoded.lower()
    request, _ = build_system_one_request(sample, _protocol_dict())
    assert set(request) == {"state", "questions", "model"}
    assert set(request["questions"]) == set(JEV_TYPESAFE_QUESTION_IDS)
    assert "risk_context_caution" not in request["questions"]
    assert all(q["type"] == "noul" for q in request["questions"].values())


@pytest.mark.parametrize(
    ("probabilities", "expected"),
    [
        ({"strategy_context_conflict": .95, "entry_context_conflict": .05, "review_evidence_insufficient": .05}, "REVIEW_REQUIRED"),
        ({"strategy_context_conflict": .05, "entry_context_conflict": .95, "review_evidence_insufficient": .05}, "REVIEW_REQUIRED"),
        ({"strategy_context_conflict": .05, "entry_context_conflict": .05, "review_evidence_insufficient": .95}, "ABSTAIN"),
        ({"strategy_context_conflict": .50, "entry_context_conflict": .05, "review_evidence_insufficient": .05}, "ABSTAIN"),
        ({"strategy_context_conflict": .05, "entry_context_conflict": .05, "review_evidence_insufficient": .05}, "PASS_THROUGH"),
    ],
)
def test_typesafe_disposition_is_deterministic(probabilities, expected) -> None:
    result = decide_typesafe_disposition(
        probabilities, threshold_low=.15, threshold_high=.85
    )
    assert result.disposition == expected


def test_typesafe_native_validator_fail_closes() -> None:
    valid = {
        "model": "jev-versioned",
        "answers": {q: {"type": "noul", "noul": .1} for q in JEV_TYPESAFE_QUESTION_IDS},
        "usage": {"input_tokens": 10, "output_tokens": 2},
    }
    assert validate_system_one_response(
        valid, expected_model_returned="jev-versioned"
    )["model"] == "jev-versioned"

    missing = json.loads(json.dumps(valid))
    missing["answers"].pop(JEV_TYPESAFE_QUESTION_IDS[0])
    with pytest.raises(TypeSafeJevProviderError) as raised:
        validate_system_one_response(missing)
    assert raised.value.code == "TYPESAFE_ANSWER_SET_MISMATCH"

    bad = json.loads(json.dumps(valid))
    bad["answers"][JEV_TYPESAFE_QUESTION_IDS[0]]["noul"] = 1.2
    with pytest.raises(TypeSafeJevProviderError) as raised:
        validate_system_one_response(bad)
    assert raised.value.code == "TYPESAFE_PROBABILITY_INVALID"

    with pytest.raises(TypeSafeJevProviderError) as raised:
        validate_system_one_response(valid, expected_model_returned="other")
    assert raised.value.code == "TYPESAFE_MODEL_IDENTITY_CHANGED"


@pytest.mark.asyncio
async def test_typesafe_http_shape_uses_mock_transport_only(monkeypatch) -> None:
    sentinel = "TYPESAFE_TEST_KEY_NOT_A_REAL_SECRET"
    monkeypatch.setenv("JEV_API_KEY", sentinel)
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["authorization"] = request.headers["Authorization"]
        captured["body"] = json.loads(request.content.decode("utf-8"))
        return httpx.Response(
            200,
            json={
                "model": "jev-versioned",
                "answers": {
                    q: {"type": "noul", "noul": .1}
                    for q in JEV_TYPESAFE_QUESTION_IDS
                },
                "usage": {"input_tokens": 25, "output_tokens": 3},
            },
        )

    provider = TypeSafeSystemOneProvider(
        model_id="jev-versioned",
        transport=httpx.MockTransport(handler),
    )
    request, _ = build_system_one_request(
        _sample(), {**_protocol_dict(), "model_requested": "jev-versioned"}
    )
    result = await provider.review(request, deadline_seconds=1.0)
    assert captured["authorization"] == f"Bearer {sentinel}"
    assert set(captured["body"]) == {"state", "questions", "model"}
    for forbidden in ("instructions", "store", "reasoning", "max_output_tokens"):
        assert forbidden not in captured["body"]
    assert result.cost_usd is None
    assert result.cost_unknown is True


@pytest.mark.asyncio
async def test_fake_core_review_never_mutates_sample() -> None:
    sample = _sample()
    before = json.dumps(sample, ensure_ascii=False, sort_keys=True)
    provider = FakeTypeSafeJevProvider(
        probabilities={
            "strategy_context_conflict": .95,
            "entry_context_conflict": .05,
            "review_evidence_insufficient": .05,
        },
        returned_model="FAKE-JEV-V2",
    )
    result = await review_once(sample, _protocol_dict(), provider)
    assert result.disposition == "REVIEW_REQUIRED"
    assert result.reason_codes == ("STRATEGY_CONTEXT_CONFLICT",)
    assert json.dumps(sample, ensure_ascii=False, sort_keys=True) == before


def test_typesafe_catalog_recruitment_is_idempotent_and_budget_reserved(
    tmp_path: Path,
) -> None:
    db = _db(tmp_path / "simulation.db")
    capture_id, sample_index = _prospective_sample(db)
    catalog = TypeSafeJevCatalog(db)
    protocol = catalog.create_protocol(
        client_request_id="fake-v2", spec=_protocol_spec()
    )
    assert protocol["status"] == "FROZEN"
    activation = catalog.set_activation(
        protocol["id"], enabled=True, allow_network=False
    )
    assert activation["allow_network"] == 0

    kwargs = dict(
        protocol_id=protocol["id"],
        capture_run_id=capture_id,
        sample_index=sample_index,
        analysis_unit_key="KOSPI|005930|2026-10-06|strategy-v1|SHORT",
        candidate_snapshot_hash="snapshot-hash",
        callable=True,
        reserved_cost_usd=.01,
    )
    first = catalog.reserve_recruitment(**kwargs)
    second = catalog.reserve_recruitment(**kwargs)
    assert first["id"] == second["id"]
    assert first["reserved_cost_usd"] == pytest.approx(.01)


def test_typesafe_migration_has_zero_external_side_effects(tmp_path: Path) -> None:
    db = tmp_path / "simulation.db"
    sqlite3.connect(db).close()
    migrate_prospective_store(db)
    result = migrate_jev_typesafe(db)
    assert result["historical_backfill_performed"] is False
    assert result["external_network_requests"] == 0
    assert result["model_calls_executed"] == 0
    assert result["secret_values_read"] is False



def _typed_answers(
    *,
    strategy: float = 0.05,
    entry: float = 0.05,
    evidence: float = 0.05,
) -> dict:
    return {
        "strategy_context_conflict": {"type": "noul", "noul": strategy},
        "entry_context_conflict": {"type": "noul", "noul": entry},
        "review_evidence_insufficient": {"type": "noul", "noul": evidence},
    }


def _active_recruitment(
    db: Path,
    *,
    callable: bool = True,
    skip_reason: str | None = None,
) -> tuple[TypeSafeJevCatalog, dict, dict]:
    capture_id, sample_index = _prospective_sample(db)
    catalog = TypeSafeJevCatalog(db)
    protocol = catalog.create_protocol(
        client_request_id="monitor-v2",
        spec=_protocol_spec(),
    )
    catalog.set_activation(protocol["id"], enabled=True, allow_network=False)
    recruitment = catalog.reserve_recruitment(
        protocol_id=protocol["id"],
        capture_run_id=capture_id,
        sample_index=sample_index,
        analysis_unit_key="KOSPI|005930|2026-10-06|strategy-v1|SHORT",
        candidate_snapshot_hash="snapshot-hash",
        callable=callable,
        skip_reason=skip_reason,
        reserved_cost_usd=0.01 if callable else 0.0,
    )
    return catalog, protocol, recruitment


def test_typesafe_monitor_keeps_skipped_separate_from_abstain(
    tmp_path: Path,
) -> None:
    db = _db(tmp_path / "simulation.db")
    catalog, _, recruitment = _active_recruitment(
        db,
        callable=False,
        skip_reason="SEMANTIC_MAPPING_INCOMPLETE",
    )
    items = catalog.list_monitor_items(recruitment["capture_run_id"])
    assert len(items) == 1
    assert items[0]["operational_status"] == "SKIPPED"
    assert items[0]["disposition"] is None
    assert items[0]["skip_reason"] == "SEMANTIC_MAPPING_INCOMPLETE"

    status = catalog.monitor_status()
    assert status["engine"] == "TYPESAFE_V2"
    assert status["recruitment"]["skipped"] == 1
    assert status["disposition"]["abstain"] == 0


def test_typesafe_monitor_projects_valid_abstain_from_typed_answers(
    tmp_path: Path,
) -> None:
    db = _db(tmp_path / "simulation.db")
    catalog, protocol, recruitment = _active_recruitment(db)
    review = catalog.begin_review(
        recruitment_id=recruitment["id"],
        request_id="review-abstain",
        state={"fixture": True},
        protocol=protocol,
        deadline_at=None,
    )
    catalog.complete_review(
        review["id"],
        status="VALID",
        disposition="ABSTAIN",
        uncertainty_reason="MODEL_UNCERTAIN",
        failure_code=None,
        model_returned="FAKE-JEV-V2",
        model_identity_status="MATCHED",
        typed_answers=_typed_answers(strategy=0.5),
        raw_response_hash="raw-hash",
        latency_ms=12,
        usage={"input_tokens": 0, "output_tokens": 0},
        cost_usd=0.0,
        cost_unknown=False,
    )
    items = catalog.list_monitor_items(recruitment["capture_run_id"])
    assert items[0]["operational_status"] == "VALID"
    assert items[0]["disposition"] == "ABSTAIN"
    assert items[0]["uncertainty_reason"] == "MODEL_UNCERTAIN"
    assert items[0]["integrity_status"] == "MATCHED"


def test_typesafe_monitor_detects_disposition_integrity_mismatch(
    tmp_path: Path,
) -> None:
    db = _db(tmp_path / "simulation.db")
    catalog, protocol, recruitment = _active_recruitment(db)
    review = catalog.begin_review(
        recruitment_id=recruitment["id"],
        request_id="review-mismatch",
        state={"fixture": True},
        protocol=protocol,
        deadline_at=None,
    )
    catalog.complete_review(
        review["id"],
        status="VALID",
        disposition="PASS_THROUGH",
        uncertainty_reason=None,
        failure_code=None,
        model_returned="FAKE-JEV-V2",
        model_identity_status="MATCHED",
        typed_answers=_typed_answers(strategy=0.95),
        raw_response_hash="raw-hash",
        latency_ms=12,
        usage={"input_tokens": 0, "output_tokens": 0},
        cost_usd=0.0,
        cost_unknown=False,
    )
    item = catalog.list_monitor_items(recruitment["capture_run_id"])[0]
    assert item["operational_status"] == "ERROR"
    assert item["disposition"] is None
    assert item["failure_code"] == "DISPOSITION_INTEGRITY_MISMATCH"
    assert item["integrity_status"] == "MISMATCH"


def test_typesafe_evaluation_uses_recruitment_denominators_and_only_review_defer() -> None:
    recruitments = [
        {
            "id": "r1", "callable": 1, "review_id": "v1",
            "reserved_cost_usd": 0.01, "known_cost_usd": 0.0,
            "cost_unknown": 0,
        },
        {
            "id": "r2", "callable": 1, "review_id": "v2",
            "reserved_cost_usd": 0.01, "known_cost_usd": None,
            "cost_unknown": 1,
        },
        {
            "id": "r3", "callable": 0, "review_id": None,
            "reserved_cost_usd": 0.0, "known_cost_usd": None,
            "cost_unknown": 0,
        },
    ]
    units = [
        {
            "recruitment_id": "r1", "operational_status": "VALID",
            "disposition": "REVIEW_REQUIRED", "integrity_status": "MATCHED",
            "model_identity_status": "MATCHED", "model_cohort_key": "cohort",
            "maturity_status": "MATURE", "comparison_eligible": 1,
            "execution_status": "CLOSED", "net_return_pct": -10.0,
            "ticker": "AAA", "signal_date": "2026-10-01", "latency_ms": 10,
        },
        {
            "recruitment_id": "r2", "operational_status": "ERROR",
            "disposition": None, "integrity_status": "NOT_APPLICABLE",
            "model_identity_status": None, "model_cohort_key": "",
            "maturity_status": "MATURE", "comparison_eligible": 1,
            "execution_status": "CLOSED", "net_return_pct": 5.0,
            "ticker": "BBB", "signal_date": "2026-10-02", "latency_ms": 20,
        },
        {
            "recruitment_id": "r3", "operational_status": "SKIPPED",
            "disposition": None, "integrity_status": "NOT_APPLICABLE",
            "model_identity_status": None, "model_cohort_key": "",
            "maturity_status": "MATURE", "comparison_eligible": 1,
            "execution_status": "CLOSED", "net_return_pct": 2.0,
            "ticker": "CCC", "signal_date": "2026-10-03", "latency_ms": None,
        },
    ]
    comparison = build_typesafe_comparison_report(units)
    assert comparison["disagreement_count"] == 1
    assert comparison["baseline_mean_return_pct"] == pytest.approx(-1.0)
    assert comparison["shadow_mean_return_pct"] == pytest.approx(7 / 3)
    assert comparison["incremental_return_per_opportunity_pct"] == pytest.approx(
        10 / 3
    )

    gates = {
        "min_mature_candidates": 1,
        "min_closed_disagreements": 1,
        "max_skip_rate": 1.0,
        "min_attempt_coverage": 1.0,
        "max_error_rate": 1.0,
        "max_late_rate": 1.0,
        "max_interrupted_rate": 1.0,
        "max_abstain_rate": 1.0,
        "max_review_rate": 1.0,
        "max_single_ticker_share": 1.0,
        "max_single_signal_date_share": 1.0,
        "max_budget_exposure_usd": 10.0,
    }
    summary = build_typesafe_evaluation_summary(
        gates=gates,
        recruitments=recruitments,
        units=units,
        comparison=comparison,
        evaluation_as_of="2026-10-06",
        protocol_id="protocol-v2",
        protocol_spec_hash="protocol-hash",
        evaluation_policy_hash="policy-hash",
        exit_policy_token="exit-token",
    )
    assert summary["funnel"]["recruited"] == 3
    assert summary["funnel"]["callable"] == 2
    assert summary["funnel"]["review_created"] == 2
    assert summary["rates"]["skip_rate"] == pytest.approx(1 / 3)
    assert summary["rates"]["error_rate"] == pytest.approx(1 / 2)
    assert summary["cost"]["unknown_cost_count"] == 1
    assert summary["cost"]["budget_exposure_usd"] == pytest.approx(0.01)
    # Unknown cost is not silently converted into a PASS.
    assert "API_COST_INCOMPLETE" in summary["gate_results"]["operational"]["reasons"]
    assert summary["automatic_adoption_allowed"] is False


def test_typesafe_evaluation_migration_is_local_only(tmp_path: Path) -> None:
    db = _db(tmp_path / "simulation.db")
    result = migrate_jev_typesafe_evaluation(db)
    assert result["historical_backfill_performed"] is False
    assert result["external_network_requests"] == 0
    assert result["model_calls_executed"] == 0
    assert result["secret_values_read"] is False


def test_typesafe_evaluation_catalog_roundtrip(tmp_path: Path) -> None:
    db = _db(tmp_path / "simulation.db")
    migrate_jev_typesafe_evaluation(db)
    catalog, protocol, recruitment = _active_recruitment(db, callable=False)
    evaluation = TypeSafeJevEvaluationCatalog(db)
    run = evaluation.create_run(
        client_request_id="eval-v2-fixture",
        protocol_id=protocol["id"],
        protocol_spec_hash=protocol["spec_hash"],
        evaluation_policy_id=JEV_TYPESAFE_EVALUATION_POLICY_ID,
        evaluation_policy_hash="policy-hash",
        evaluation_as_of="2026-10-06",
        exit_policy_token="exit-token",
    )
    evaluation.begin_run(run["id"])
    unit = {
        "recruitment_id": recruitment["id"],
        "capture_run_id": recruitment["capture_run_id"],
        "sample_index": recruitment["sample_index"],
        "review_id": None,
        "market": "KOSPI",
        "ticker": "005930",
        "name": "fixture",
        "signal_date": "2026-10-06",
        "strategy": "TREND_FOLLOWING",
        "horizon": "SHORT",
        "callable": 0,
        "skip_reason": recruitment["skip_reason"],
        "operational_status": "SKIPPED",
        "disposition": None,
        "failure_code": None,
        "integrity_status": "NOT_APPLICABLE",
        "provider_id": None,
        "model_requested": None,
        "model_returned": None,
        "model_identity_status": None,
        "model_cohort_key": "",
        "latency_ms": None,
        "reserved_cost_usd": 0.0,
        "known_cost_usd": None,
        "cost_unknown": 0,
        "maturity_status": "IMMATURE",
        "available_trading_days": 0,
        "evaluated_through": None,
        "return_5d": None,
        "return_10d": None,
        "return_20d": None,
        "mfe_pct": None,
        "mae_pct": None,
        "execution_status": "NOT_EVALUATED",
        "execution_reason": None,
        "entry_date": None,
        "entry_price": None,
        "exit_date": None,
        "exit_price": None,
        "exit_reason": None,
        "holding_days": None,
        "gross_return_pct": None,
        "net_return_pct": None,
        "mark_return_pct": None,
        "comparison_eligible": 0,
        "details": {},
        "computed_at": "2026-10-06T00:00:00+00:00",
    }
    report = {
        "funnel": {
            "recruited": 1,
            "callable": 0,
            "review_created": 0,
            "valid": 0,
            "mature": 0,
            "comparable_closed": 0,
        },
        "comparison": {"disagreement_count": 0},
        "evaluation_state": "COLLECTING",
        "automatic_adoption_allowed": False,
    }
    completed = evaluation.complete_run(
        run_id=run["id"],
        units=[unit],
        report_summary=report,
        source_set_hash="source-hash",
    )
    assert completed["status"] == "COMPLETED"
    detail = evaluation.detail(run["id"])
    assert detail["report"]["summary"]["automatic_adoption_allowed"] is False
    assert detail["units"][0]["operational_status"] == "SKIPPED"
