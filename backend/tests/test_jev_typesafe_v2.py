from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import httpx
import pytest

from app.jev.typesafe_catalog import TypeSafeJevCatalog
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
