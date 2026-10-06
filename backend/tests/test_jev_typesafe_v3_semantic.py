from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from app.jev.typesafe_evaluation import typesafe_model_cohort_key
from app.jev.typesafe_models import (
    JEV_TYPESAFE_DISPOSITION_POLICY_VERSION_V3,
    JEV_TYPESAFE_QUESTION_CONTRACT_VERSION_V3,
    JEV_TYPESAFE_PROJECTOR_VERSION_V3,
    JEV_TYPESAFE_STATE_CONTRACT_VERSION_V3,
    TypeSafeJevTrialProtocolSpec,
)
from app.jev.typesafe_policy_v3 import (
    JEV_TYPESAFE_DISPOSITION_POLICY_HASH_V3,
    decide_typesafe_disposition_v3,
)
from app.jev.typesafe_projection import project_typesafe_review
from app.jev.typesafe_provider import FakeTypeSafeJevProvider
from app.jev.typesafe_questions_v3 import (
    JEV_TYPESAFE_QUESTION_IDS_V3,
    JEV_TYPESAFE_QUESTION_SET_HASH_V3,
)
from app.jev.typesafe_service import build_system_one_request, review_once
from app.jev.typesafe_state_v3 import (
    JEV_TYPESAFE_PROJECTOR_HASH_V3,
    JEV_TYPESAFE_STATE_CONTRACT_HASH_V3,
    project_typesafe_state_v3,
)
from app.prospective.catalog import ProspectiveCatalog
from app.prospective.models import (
    PROSPECTIVE_CAPTURE_VERSION,
    ProspectiveCaptureRequest,
)
from app.simulation.strategy_governance import current_strategy_definitions
from app.strategy.condition_semantics import condition_sources
from app.strategy.entry_semantics import (
    EntryRuleRepresentation,
    evaluate_entry_semantics,
)
from app.strategy.engine import StrategyEngine
from app.strategy.models import StrategyInput, StrategyName
from app.strategy.semantic_contract import (
    ROLE_EXECUTABLE_ENTRY,
    SEMANTIC_STATUS_COMPLETE,
    SEMANTIC_STATUS_STALE_VERSION,
    authored_strategy_keys,
    resolve_strategy_semantic_contract,
    semantic_contract_hash,
)
from app.strategy.semantic_source import (
    build_semantic_source,
    verify_semantic_source,
)
from tools.data.migrate_prospective_vnp2s2 import migrate_prospective_store


def _binding(strategy_key: str) -> tuple[str, str]:
    item = next(
        row for row in current_strategy_definitions()
        if row.strategy_key == strategy_key
    )
    return item.strategy_version_id, item.definition_hash


def _candidate(
    *,
    executable_entry_range: bool = False,
    price_basis: str = "현재가가 20일 이동평균선 위",
    action: str = "ENTRY_CANDIDATE",
) -> dict:
    strategy = StrategyName.TREND_FOLLOWING.value
    version_id, definition_hash = _binding(strategy)
    total = len(condition_sources(strategy))
    return {
        "market": "KOSPI",
        "code": "005930",
        "name": "LOCAL_ONLY_FIXTURE",
        "rank": 1,
        "data_date": "2026-10-07",
        "candidate_state": "READY",
        "strategy": strategy,
        "strategy_version_id": version_id,
        "strategy_definition_hash": definition_hash,
        "action": action,
        "conditions": {
            "passed": total,
            "total": total,
            "missing": 0,
            "top_missing": [],
        },
        "entry_risk_guide": {
            "price_rule": {
                "kind": "ABOVE",
                "status": "PASS",
                "basis": price_basis,
                "semantic_role": "STRATEGY_CONDITION_THRESHOLD",
                "executable_entry_range": executable_entry_range,
            },
            "action": {"status": action},
        },
    }


def _sample(candidate: dict | None = None) -> dict:
    snapshot = dict(candidate or _candidate())
    if "semantic_source" not in snapshot:
        snapshot["semantic_source"] = build_semantic_source(snapshot)
    return {
        "capture_run_id": "capture-local",
        "sample_index": 0,
        "market": "KOSPI",
        "ticker": "005930",
        "name": "MUST_STAY_LOCAL",
        "rank": 1,
        "action": "ENTRY_CANDIDATE",
        "candidate_state": "READY",
        "strategy": snapshot["strategy"],
        "signal_date": "2026-10-07",
        "horizon_intent": "SHORT",
        "horizon_policy_version": "HORIZON-V1",
        "snapshot_hash": "candidate-snapshot-hash",
        "scanner_version": "scanner-fixture",
        "scanner_baseline": "baseline-fixture",
        "input_fingerprint": "input-fixture",
        "snapshot": snapshot,
    }


def _v3_protocol_dict() -> dict:
    return {
        "provider_id": "FAKE",
        "model_requested": "FAKE-JEV-V3",
        "expected_model_returned": "FAKE-JEV-V3",
        "state_contract_version": JEV_TYPESAFE_STATE_CONTRACT_VERSION_V3,
        "state_contract_hash": JEV_TYPESAFE_STATE_CONTRACT_HASH_V3,
        "projector_version": JEV_TYPESAFE_PROJECTOR_VERSION_V3,
        "projector_hash": JEV_TYPESAFE_PROJECTOR_HASH_V3,
        "question_contract_version": JEV_TYPESAFE_QUESTION_CONTRACT_VERSION_V3,
        "question_set_hash": JEV_TYPESAFE_QUESTION_SET_HASH_V3,
        "disposition_policy_version": JEV_TYPESAFE_DISPOSITION_POLICY_VERSION_V3,
        "disposition_policy_hash": JEV_TYPESAFE_DISPOSITION_POLICY_HASH_V3,
        "threshold_strategy": 0.70,
        "deadline_seconds": 12.0,
    }


def test_strategy_semantic_contract_covers_exactly_ten_operating_strategies() -> None:
    expected = {
        item.value for item in StrategyName
        if item is not StrategyName.NO_TRADE
    }
    assert set(authored_strategy_keys()) == expected
    for definition in current_strategy_definitions():
        resolved = resolve_strategy_semantic_contract(
            strategy_key=definition.strategy_key,
            strategy_version_id=definition.strategy_version_id,
            strategy_definition_hash=definition.definition_hash,
        )
        assert resolved.status == SEMANTIC_STATUS_COMPLETE
        assert resolved.contract is not None
        assert semantic_contract_hash(resolved.contract) == resolved.contract[
            "semantic_contract_hash"
        ]

        stale = resolve_strategy_semantic_contract(
            strategy_key=definition.strategy_key,
            strategy_version_id=definition.strategy_version_id,
            strategy_definition_hash="wrong-hash",
        )
        assert stale.status == SEMANTIC_STATUS_STALE_VERSION


def test_condition_mapping_matches_current_strategy_engine_condition_labels() -> None:
    engine = StrategyEngine()
    data = StrategyInput(code="fixture", market="KOSPI", current_price=100.0)
    for strategy in StrategyName:
        if strategy is StrategyName.NO_TRADE:
            continue
        evaluations = engine.evaluate_all(data, allowed_strategies={strategy})
        evaluation = next(item for item in evaluations if item.strategy is strategy)
        actual = set(evaluation.reasons) | set(evaluation.unmet)
        assert actual == set(condition_sources(strategy.value))


def test_q1_and_q2_readiness_are_isolated() -> None:
    missing_q2 = _candidate(price_basis="unregistered basis")
    source = build_semantic_source(missing_q2)
    assert source["readiness"]["q1_status"] == "COMPLETE"
    assert source["readiness"]["q2_status"] == "MISSING"

    conflict_q2 = _candidate(executable_entry_range=True)
    source = build_semantic_source(conflict_q2)
    assert source["readiness"]["q1_status"] == "COMPLETE"
    assert source["readiness"]["q2_status"] == "COMPLETE"
    assert source["local_entry_semantic_result"] == {
        "status": "CONFLICT",
        "reason_code": "CONFLICT_CONFIRMATION_AS_EXECUTION",
    }


def test_q2_truth_table_keeps_local_deterministic_ownership() -> None:
    candidate = _candidate()
    source = build_semantic_source(candidate)
    strategy = source["strategy"]
    resolved = resolve_strategy_semantic_contract(
        strategy_key=candidate["strategy"],
        strategy_version_id=strategy["strategy_version_id"],
        strategy_definition_hash=strategy["strategy_definition_hash"],
    )
    assert resolved.contract is not None

    represented = EntryRuleRepresentation(
        "COMPLETE",
        None,
        {
            "represented_rule_id": "ma20-reference",
            "represented_role": "CONFIRMATION_ONLY",
            "executable_entry_range": False,
            "representation_contract_version": "fixture",
            "representation_contract_hash": "fixture",
        },
    )
    assert evaluate_entry_semantics(
        strategy_contract=resolved.contract,
        representation=represented,
    ).status == "MATCH"

    modified = json.loads(json.dumps(resolved.contract))
    rule = next(
        item for item in modified["entry_rules"]
        if item["rule_id"] == "ma20-reference"
    )
    rule["intent_role"] = ROLE_EXECUTABLE_ENTRY
    result = evaluate_entry_semantics(
        strategy_contract=modified,
        representation=represented,
    )
    assert result.status == "CONFLICT"
    assert result.reason_code == "CONFLICT_EXECUTION_AS_CONFIRMATION"


def test_v3_state_contains_only_q1_semantics_and_no_local_identity() -> None:
    sample = _sample()
    projection = project_typesafe_state_v3(sample)
    assert set(projection.state) == {
        "strategy_intent",
        "term_definitions",
        "passed_condition_meanings",
    }
    encoded = json.dumps(projection.state, ensure_ascii=False)
    for forbidden in (
        "005930",
        "MUST_STAY_LOCAL",
        "candidate-snapshot-hash",
        "entry_rule",
        "local_entry_semantic_result",
        "semantic_contract_hash",
        "risk",
        "target",
        "stop",
    ):
        assert forbidden not in encoded


def test_v3_protocol_requires_only_strategy_threshold() -> None:
    spec = TypeSafeJevTrialProtocolSpec(
        name="V3 fake offline",
        provider_id="FAKE",
        model_requested="FAKE-JEV-V3",
        expected_model_returned="FAKE-JEV-V3",
        state_contract_version=JEV_TYPESAFE_STATE_CONTRACT_VERSION_V3,
        state_contract_hash=JEV_TYPESAFE_STATE_CONTRACT_HASH_V3,
        projector_version=JEV_TYPESAFE_PROJECTOR_VERSION_V3,
        projector_hash=JEV_TYPESAFE_PROJECTOR_HASH_V3,
        question_contract_version=JEV_TYPESAFE_QUESTION_CONTRACT_VERSION_V3,
        question_set_hash=JEV_TYPESAFE_QUESTION_SET_HASH_V3,
        disposition_policy_version=JEV_TYPESAFE_DISPOSITION_POLICY_VERSION_V3,
        disposition_policy_hash=JEV_TYPESAFE_DISPOSITION_POLICY_HASH_V3,
        threshold_strategy=0.70,
        threshold_entry=None,
        threshold_evidence=None,
        recruitment_duration_calendar_days=30,
        max_recruited_candidates=20,
        budget_limit_usd=1.0,
        per_call_reservation_usd=0.01,
    )
    assert spec.freeze_gaps() == []
    assert spec.status() == "FROZEN"


@pytest.mark.parametrize(
    ("probability", "expected"),
    [
        (0.69, "PASS_THROUGH"),
        (0.70, "REVIEW_REQUIRED"),
        (0.95, "REVIEW_REQUIRED"),
    ],
)
def test_v3_policy_is_one_sided(probability: float, expected: str) -> None:
    decision = decide_typesafe_disposition_v3(
        {"strategy_context_conflict": probability},
        threshold_strategy=0.70,
    )
    assert decision.disposition == expected


@pytest.mark.parametrize("bad", [True, float("nan"), float("inf"), -0.1, 1.1])
def test_v3_policy_rejects_invalid_probability(bad) -> None:
    with pytest.raises(ValueError):
        decide_typesafe_disposition_v3(
            {"strategy_context_conflict": bad},
            threshold_strategy=0.70,
        )


@pytest.mark.asyncio
async def test_v3_core_uses_exactly_one_noul_with_fake_provider() -> None:
    sample = _sample()
    protocol = _v3_protocol_dict()
    request, projection = build_system_one_request(sample, protocol)
    assert set(request["questions"]) == set(JEV_TYPESAFE_QUESTION_IDS_V3)
    assert len(request["questions"]) == 1
    assert request["questions"]["strategy_context_conflict"]["type"] == "noul"
    assert request["state"] == projection.state

    provider = FakeTypeSafeJevProvider(
        probabilities={"strategy_context_conflict": 0.81},
        returned_model="FAKE-JEV-V3",
    )
    result = await review_once(sample, protocol, provider)
    assert result.disposition == "REVIEW_REQUIRED"
    assert result.reason_codes == ("STRATEGY_CONTEXT_CONFLICT",)


def test_prospective_capture_v2_snapshots_semantic_source_without_schema_change(
    tmp_path: Path,
) -> None:
    db = tmp_path / "simulation.db"
    sqlite3.connect(db).close()
    migrate_prospective_store(db)
    catalog = ProspectiveCatalog(db)
    request = ProspectiveCaptureRequest(
        market_scope="KOSPI",
        requested_as_of="2026-10-07",
        candidate_limit=1,
        horizon_intent="SHORT",
        horizon_policy_version="HORIZON-V1",
        selection_policy_id="POLICY",
        selection_policy_hash="POLICY-HASH",
    )
    catalog.begin_capture(source_job_id="semantic-v3", request=request)
    candidate = _candidate()
    result = {
        "version": "scanner-fixture",
        "requested_as_of": "2026-10-07",
        "market_scope": "KOSPI",
        "data_dates": {"KOSPI": "2026-10-07"},
        "input_fingerprint": "fixture-input",
        "partial_data": False,
        "summary": {"candidate_count": 1},
        "candidates": [candidate],
        "more_candidates": [],
        "horizon_context": {"intent": "SHORT"},
        "strategy_selection_policy": {
            "policy_id": "POLICY",
            "policy_hash": "POLICY-HASH",
        },
        "diagnostics": {
            "reproducibility_audit": {"production_baseline": "BASELINE"}
        },
    }
    capture = catalog.finalize_capture(
        source_job_id="semantic-v3",
        request=request,
        result=result,
    )
    assert capture["capture_version"] == PROSPECTIVE_CAPTURE_VERSION
    assert PROSPECTIVE_CAPTURE_VERSION == "VN_P2_S2_CAPTURE_V2"

    sample = catalog.list_samples(capture_run_id=capture["id"])[0]
    source = sample["snapshot"]["semantic_source"]
    assert source["readiness"]["q1_status"] == "COMPLETE"
    assert verify_semantic_source(source) == (True, None)

    with sqlite3.connect(db) as conn:
        columns = {
            row[1]
            for row in conn.execute(
                "PRAGMA table_info(prospective_recommendation_sample)"
            ).fetchall()
        }
    assert "semantic_source_json" not in columns


def test_v3_stored_projection_and_cohort_identity_are_version_specific() -> None:
    sample = _sample()
    protocol = _v3_protocol_dict()
    review = {
        "status": "VALID",
        "disposition": "REVIEW_REQUIRED",
        "failure_code": None,
        "model_identity_status": "MATCHED",
        "provider_id": "FAKE",
        "model_requested": "FAKE-JEV-V3",
        "model_returned": "FAKE-JEV-V3",
        "state_contract_version": JEV_TYPESAFE_STATE_CONTRACT_VERSION_V3,
        "projector_version": JEV_TYPESAFE_PROJECTOR_VERSION_V3,
        "projector_hash": JEV_TYPESAFE_PROJECTOR_HASH_V3,
        "question_contract_version": JEV_TYPESAFE_QUESTION_CONTRACT_VERSION_V3,
        "question_set_hash": JEV_TYPESAFE_QUESTION_SET_HASH_V3,
        "disposition_policy_version": JEV_TYPESAFE_DISPOSITION_POLICY_VERSION_V3,
        "disposition_policy_hash": JEV_TYPESAFE_DISPOSITION_POLICY_HASH_V3,
        "adapter_version": "JEV_TYPESAFE_SYSTEMONE_ADAPTER_V1",
        "typed_answers": {
            "strategy_context_conflict": {"type": "noul", "noul": 0.81}
        },
    }
    projected = project_typesafe_review(review, protocol)
    assert projected.operational_status == "VALID"
    assert projected.disposition == "REVIEW_REQUIRED"
    assert projected.reason_codes == ("STRATEGY_CONTEXT_CONFLICT",)

    first = typesafe_model_cohort_key(
        protocol_spec_hash="protocol-hash",
        protocol_spec=protocol,
        review=review,
        sample=sample,
    )
    same_contract_new_candidate = json.loads(json.dumps(sample))
    same_contract_new_candidate["snapshot"]["semantic_source"][
        "source_snapshot_hash"
    ] = "different-candidate-specific-hash"
    second = typesafe_model_cohort_key(
        protocol_spec_hash="protocol-hash",
        protocol_spec=protocol,
        review=review,
        sample=same_contract_new_candidate,
    )
    assert first == second

    changed_contract = json.loads(json.dumps(sample))
    changed_contract["snapshot"]["semantic_source"]["strategy"][
        "semantic_contract_hash"
    ] = "different-semantic-contract"
    third = typesafe_model_cohort_key(
        protocol_spec_hash="protocol-hash",
        protocol_spec=protocol,
        review=review,
        sample=changed_contract,
    )
    assert third != first
