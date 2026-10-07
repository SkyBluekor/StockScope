from __future__ import annotations

import asyncio
import hashlib
import json
import math
from copy import deepcopy

import pytest

from app.jev.typesafe_models import (
    JEV_TYPESAFE_DISPOSITION_POLICY_VERSION_V1,
    JEV_TYPESAFE_DISPOSITION_POLICY_VERSION_V2,
    JEV_TYPESAFE_DISPOSITION_POLICY_VERSION_V3,
    JEV_TYPESAFE_DISPOSITION_POLICY_VERSION_V4,
    JEV_TYPESAFE_QUESTION_CONTRACT_VERSION_V1,
    JEV_TYPESAFE_QUESTION_CONTRACT_VERSION_V2,
    JEV_TYPESAFE_QUESTION_CONTRACT_VERSION_V3,
    JEV_TYPESAFE_QUESTION_CONTRACT_VERSION_V4,
)
from app.jev.typesafe_policy_v4 import decide_typesafe_disposition_v4
from app.jev.typesafe_provider import FakeTypeSafeJevProvider
from app.jev.typesafe_questions_v4 import (
    JEV_TYPESAFE_QUESTION_IDS_V4,
    JEV_TYPESAFE_QUESTION_SET_HASH_V4,
    STRATEGY_RELATION_CONFLICT,
    build_typesafe_questions_v4,
)
from app.jev.typesafe_service import (
    _contract_family,
    build_system_one_request,
    review_once,
)
from app.jev.typesafe_state import TypeSafeStateProjectionError
from app.jev.typesafe_state_v4 import (
    PROVIDER_CALL_ELIGIBLE,
    SKIPPED_LOCAL_CONFLICT,
    SKIPPED_LOCAL_MATCH,
    SKIPPED_SOURCE_AMBIGUOUS,
    SKIPPED_SOURCE_INCOMPLETE,
    route_typesafe_state_v4,
)
from app.simulation.strategy_governance import current_strategy_definitions
from app.strategy.condition_assertions import (
    STANCE_CONTRADICTS,
    STANCE_WEAKENS,
)
from app.strategy.condition_semantics import condition_sources
from app.strategy.models import StrategyName
from app.strategy.semantic_composition import (
    LOCAL_AMBIGUOUS,
    LOCAL_CONFLICT,
    LOCAL_INCOMPLETE,
    LOCAL_MATCH,
    RESIDUAL_SEMANTIC_REVIEW,
    compose_semantics,
)
from app.strategy.semantic_source_v2 import build_semantic_source_v2


def _digest_source_body(source: dict) -> str:
    body = dict(source)
    body.pop("source_snapshot_hash", None)
    encoded = json.dumps(
        body,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _base_source() -> dict:
    binding = next(
        item
        for item in current_strategy_definitions()
        if item.strategy_key == StrategyName.TREND_FOLLOWING.value
    )
    total = len(condition_sources(StrategyName.TREND_FOLLOWING.value))
    candidate = {
        "strategy": StrategyName.TREND_FOLLOWING.value,
        "strategy_version_id": binding.strategy_version_id,
        "strategy_definition_hash": binding.definition_hash,
        "action": "ENTRY_CANDIDATE",
        "conditions": {"passed": total, "total": total, "missing": 0},
    }
    source = build_semantic_source_v2(candidate)
    assert source["local_semantic_composition"]["status"] == LOCAL_MATCH
    return source


def _source_for_status(status: str) -> dict:
    source = deepcopy(_base_source())
    items = source["conditions"]["items"]

    relative_rows = [
        item for item in items if "relative_strength" in item["concept_refs"]
    ]
    assert len(relative_rows) >= 2

    if status == LOCAL_MATCH:
        pass
    elif status == LOCAL_CONFLICT:
        for item in relative_rows:
            item["stance"] = STANCE_CONTRADICTS
    elif status == LOCAL_AMBIGUOUS:
        relative_rows[0]["stance"] = STANCE_CONTRADICTS
    elif status == RESIDUAL_SEMANTIC_REVIEW:
        for item in relative_rows:
            item["stance"] = STANCE_WEAKENS
    elif status == LOCAL_INCOMPLETE:
        source["conditions"]["items"] = [
            item
            for item in items
            if "relative_strength" not in item["concept_refs"]
        ]
    else:
        raise AssertionError(status)

    composition = compose_semantics(
        relation_contract=source["relations"],
        assertions=source["conditions"]["items"],
    )
    assert composition.status == status
    source["local_semantic_composition"] = {
        "status": composition.status,
        "reason_codes": list(composition.reason_codes),
        "relation_results": [dict(item) for item in composition.relation_results],
    }
    source["readiness"]["local_semantic_status"] = composition.status
    source["readiness"]["local_semantic_reasons"] = list(composition.reason_codes)
    source["readiness"]["residual_review_eligible"] = (
        composition.status == RESIDUAL_SEMANTIC_REVIEW
    )
    source["source_snapshot_hash"] = _digest_source_body(source)
    return source


def _sample(status: str) -> dict:
    return {
        "action": "ENTRY_CANDIDATE",
        "horizon_intent": "SHORT",
        "capture_run_id": "synthetic-v4-core-test",
        "sample_index": 1,
        "snapshot_hash": "synthetic-snapshot",
        "snapshot": {"semantic_source_v2": _source_for_status(status)},
    }


def _protocol(threshold: float = 0.7) -> dict:
    return {
        "question_contract_version": JEV_TYPESAFE_QUESTION_CONTRACT_VERSION_V4,
        "disposition_policy_version": JEV_TYPESAFE_DISPOSITION_POLICY_VERSION_V4,
        "model_requested": "fake-jev-v4",
        "expected_model_returned": "fake-jev-v4",
        "threshold_strategy": threshold,
        "deadline_seconds": 1.0,
    }


@pytest.mark.parametrize(
    ("status", "reason"),
    [
        (LOCAL_MATCH, SKIPPED_LOCAL_MATCH),
        (LOCAL_CONFLICT, SKIPPED_LOCAL_CONFLICT),
        (LOCAL_INCOMPLETE, SKIPPED_SOURCE_INCOMPLETE),
        (LOCAL_AMBIGUOUS, SKIPPED_SOURCE_AMBIGUOUS),
    ],
)
def test_v4_local_terminal_states_never_build_provider_request(
    status: str,
    reason: str,
) -> None:
    sample = _sample(status)
    route = route_typesafe_state_v4(sample)
    assert route.provider_eligible is False
    assert route.reason_code == reason

    with pytest.raises(TypeSafeStateProjectionError) as exc_info:
        build_system_one_request(sample, _protocol())
    assert exc_info.value.code == reason


def test_v4_residual_state_is_provider_eligible_and_wire_is_minimized() -> None:
    sample = _sample(RESIDUAL_SEMANTIC_REVIEW)
    route = route_typesafe_state_v4(sample)
    assert route.provider_eligible is True
    assert route.reason_code == PROVIDER_CALL_ELIGIBLE

    request, projection = build_system_one_request(sample, _protocol())
    assert set(request) == {"state", "questions", "model"}
    assert request["model"] == "fake-jev-v4"
    assert set(projection.state) == {
        "strategy_intent",
        "term_definitions",
        "authored_relations",
        "passed_condition_meanings",
    }

    serialized = json.dumps(projection.state, ensure_ascii=False)
    lowered = serialized.lower()
    forbidden_wire_keys = (
        "local_semantic_status",
        '"stance"',
        '"gold"',
        "expected_disposition",
        '"ticker"',
        '"name"',
        '"rank"',
        '"price"',
        '"risk"',
        '"entry"',
        '"stop"',
        '"target"',
        '"rr"',
        '"holdings"',
        "future_return",
    )
    for forbidden in forbidden_wire_keys:
        assert forbidden not in lowered

    assert '"concept_refs"' in serialized
    assert '"authored_relations"' in serialized


def test_v4_question_is_single_deterministic_semantic_question() -> None:
    first = build_typesafe_questions_v4()
    second = build_typesafe_questions_v4()
    assert first == second
    assert tuple(first) == JEV_TYPESAFE_QUESTION_IDS_V4
    assert JEV_TYPESAFE_QUESTION_IDS_V4 == (STRATEGY_RELATION_CONFLICT,)
    assert len(JEV_TYPESAFE_QUESTION_SET_HASH_V4) == 64

    text = json.dumps(first, ensure_ascii=False).lower()
    for forbidden in (" buy ", " sell ", " target ", "future return"):
        assert forbidden not in f" {text} "


@pytest.mark.parametrize(
    ("probability", "expected"),
    [
        (0.69, "PASS_THROUGH"),
        (0.70, "REVIEW_REQUIRED"),
        (0.90, "REVIEW_REQUIRED"),
    ],
)
def test_v4_policy_uses_raw_external_threshold(
    probability: float,
    expected: str,
) -> None:
    decision = decide_typesafe_disposition_v4(
        {STRATEGY_RELATION_CONFLICT: probability},
        threshold_strategy=0.70,
    )
    assert decision.disposition == expected


@pytest.mark.parametrize(
    "probability",
    [float("nan"), float("inf"), float("-inf"), -0.01, 1.01],
)
def test_v4_policy_rejects_invalid_probability(probability: float) -> None:
    with pytest.raises(ValueError, match="JEV_TYPESAFE_PROBABILITY_INVALID"):
        decide_typesafe_disposition_v4(
            {STRATEGY_RELATION_CONFLICT: probability},
            threshold_strategy=0.70,
        )


def test_v4_service_dispatches_fake_provider_without_network() -> None:
    provider = FakeTypeSafeJevProvider(
        probabilities={STRATEGY_RELATION_CONFLICT: 0.82},
        returned_model="fake-jev-v4",
    )
    review = asyncio.run(
        review_once(
            _sample(RESIDUAL_SEMANTIC_REVIEW),
            _protocol(0.70),
            provider,
        )
    )
    assert review.disposition == "REVIEW_REQUIRED"
    assert review.reason_codes == ("STRATEGY_RELATION_CONFLICT",)
    assert review.gate_results == {STRATEGY_RELATION_CONFLICT: True}


def test_contract_family_preserves_v1_v2_v3_and_adds_v4() -> None:
    pairs = [
        (
            JEV_TYPESAFE_QUESTION_CONTRACT_VERSION_V1,
            JEV_TYPESAFE_DISPOSITION_POLICY_VERSION_V1,
            "V1",
        ),
        (
            JEV_TYPESAFE_QUESTION_CONTRACT_VERSION_V2,
            JEV_TYPESAFE_DISPOSITION_POLICY_VERSION_V2,
            "V2",
        ),
        (
            JEV_TYPESAFE_QUESTION_CONTRACT_VERSION_V3,
            JEV_TYPESAFE_DISPOSITION_POLICY_VERSION_V3,
            "V3",
        ),
        (
            JEV_TYPESAFE_QUESTION_CONTRACT_VERSION_V4,
            JEV_TYPESAFE_DISPOSITION_POLICY_VERSION_V4,
            "V4",
        ),
    ]
    for question_version, policy_version, expected in pairs:
        assert _contract_family(
            {
                "question_contract_version": question_version,
                "disposition_policy_version": policy_version,
            }
        ) == expected
