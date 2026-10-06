from __future__ import annotations

import json

import pytest

from app.jev.typesafe_evaluation import typesafe_model_cohort_key
from app.jev.typesafe_models import (
    JEV_TYPESAFE_DISPOSITION_POLICY_VERSION_V1,
    JEV_TYPESAFE_DISPOSITION_POLICY_VERSION_V2,
    JEV_TYPESAFE_QUESTION_CONTRACT_VERSION_V1,
    JEV_TYPESAFE_QUESTION_CONTRACT_VERSION_V2,
    TypeSafeJevTrialProtocolSpec,
)
from app.jev.typesafe_policy import decide_typesafe_disposition
from app.jev.typesafe_policy_v2 import (
    JEV_TYPESAFE_DISPOSITION_POLICY_HASH_V2,
    decide_typesafe_disposition_v2,
)
from app.jev.typesafe_provider import FakeTypeSafeJevProvider
from app.jev.typesafe_questions import (
    JEV_TYPESAFE_QUESTION_IDS,
    JEV_TYPESAFE_QUESTION_SET_HASH,
)
from app.jev.typesafe_questions_v2 import (
    JEV_TYPESAFE_QUESTION_IDS_V2,
    JEV_TYPESAFE_QUESTION_SET_HASH_V2,
    OVERALL_SEMANTIC_REVIEW_INSUFFICIENT,
)
from app.jev.typesafe_service import review_once


def test_v1_contract_stays_v1() -> None:
    assert JEV_TYPESAFE_QUESTION_CONTRACT_VERSION_V1 == "JEV_TYPESAFE_QUESTIONS_V1"
    assert JEV_TYPESAFE_DISPOSITION_POLICY_VERSION_V1 == (
        "JEV_TYPESAFE_DISPOSITION_POLICY_V1"
    )
    assert JEV_TYPESAFE_QUESTION_IDS == (
        "strategy_context_conflict",
        "entry_context_conflict",
        "review_evidence_insufficient",
    )
    result = decide_typesafe_disposition(
        {
            "strategy_context_conflict": 0.50,
            "entry_context_conflict": 0.05,
            "review_evidence_insufficient": 0.05,
        },
        threshold_low=0.15,
        threshold_high=0.85,
    )
    assert result.disposition == "ABSTAIN"
    assert result.uncertainty_reason == "MODEL_UNCERTAIN"


def test_v2_question_contract_is_exact_three_noul_without_risk() -> None:
    assert JEV_TYPESAFE_QUESTION_CONTRACT_VERSION_V2 == "JEV_TYPESAFE_QUESTIONS_V2"
    assert JEV_TYPESAFE_QUESTION_IDS_V2 == (
        "strategy_context_conflict",
        "entry_context_conflict",
        "overall_semantic_review_insufficient",
    )
    assert OVERALL_SEMANTIC_REVIEW_INSUFFICIENT in JEV_TYPESAFE_QUESTION_IDS_V2
    assert "review_evidence_insufficient" not in JEV_TYPESAFE_QUESTION_IDS_V2
    assert "risk_context_caution" not in JEV_TYPESAFE_QUESTION_IDS_V2


@pytest.mark.parametrize(
    ("p1", "p2", "p3", "disposition", "reasons", "uncertainty"),
    [
        (0.90, 0.10, 0.95, "REVIEW_REQUIRED", ("STRATEGY_CONTEXT_CONFLICT",), None),
        (0.10, 0.90, 0.95, "REVIEW_REQUIRED", ("ENTRY_CONTEXT_CONFLICT",), None),
        (
            0.90,
            0.90,
            0.95,
            "REVIEW_REQUIRED",
            ("STRATEGY_CONTEXT_CONFLICT", "ENTRY_CONTEXT_CONFLICT"),
            None,
        ),
        (0.10, 0.10, 0.95, "ABSTAIN", (), "EVIDENCE_INSUFFICIENT"),
        (
            0.10,
            0.10,
            0.10,
            "PASS_THROUGH",
            ("NO_ADDITIONAL_CONTEXT_CONFLICT",),
            None,
        ),
    ],
)
def test_v2_conflict_first_truth_table(
    p1,
    p2,
    p3,
    disposition,
    reasons,
    uncertainty,
) -> None:
    result = decide_typesafe_disposition_v2(
        {
            "strategy_context_conflict": p1,
            "entry_context_conflict": p2,
            "overall_semantic_review_insufficient": p3,
        },
        threshold_strategy=0.65,
        threshold_entry=0.65,
        threshold_evidence=0.75,
    )
    assert result.disposition == disposition
    assert result.reason_codes == reasons
    assert result.uncertainty_reason == uncertainty


@pytest.mark.parametrize("bad", [True, float("nan"), float("inf"), -0.1, 1.1])
def test_v2_rejects_invalid_probability(bad) -> None:
    with pytest.raises(ValueError):
        decide_typesafe_disposition_v2(
            {
                "strategy_context_conflict": bad,
                "entry_context_conflict": 0.1,
                "overall_semantic_review_insufficient": 0.1,
            },
            threshold_strategy=0.65,
            threshold_entry=0.65,
            threshold_evidence=0.75,
        )


def test_trial_spec_freeze_dispatches_v1_and_v2_threshold_shapes() -> None:
    common = dict(
        name="fixture",
        provider_id="FAKE",
        model_requested="fake",
        expected_model_returned="fake",
        state_contract_hash="state",
        projector_hash="projector",
        recruitment_duration_calendar_days=1,
        max_recruited_candidates=1,
        budget_limit_usd=1.0,
        per_call_reservation_usd=0.01,
    )
    v1 = TypeSafeJevTrialProtocolSpec(
        **common,
        question_set_hash=JEV_TYPESAFE_QUESTION_SET_HASH,
        disposition_policy_hash="v1-policy",
        threshold_low=0.15,
        threshold_high=0.85,
    )
    assert "threshold_strategy" not in v1.freeze_gaps()
    assert v1.status() == "FROZEN"

    v2 = TypeSafeJevTrialProtocolSpec(
        **common,
        question_contract_version=JEV_TYPESAFE_QUESTION_CONTRACT_VERSION_V2,
        question_set_hash=JEV_TYPESAFE_QUESTION_SET_HASH_V2,
        disposition_policy_version=JEV_TYPESAFE_DISPOSITION_POLICY_VERSION_V2,
        disposition_policy_hash=JEV_TYPESAFE_DISPOSITION_POLICY_HASH_V2,
        threshold_strategy=0.65,
        threshold_entry=0.65,
        threshold_evidence=0.75,
    )
    assert "threshold_low" not in v2.freeze_gaps()
    assert v2.status() == "FROZEN"


def test_v2_cohort_identity_uses_three_thresholds() -> None:
    review = {
        "provider_id": "TYPESAFE_SYSTEM_ONE",
        "model_requested": "jev-latest",
        "model_returned": "jev-1.13.0",
        "model_identity_status": "MATCHED",
        "state_contract_version": "JEV_TYPESAFE_STATE_V1",
        "projector_version": "JEV_TYPESAFE_PROJECTOR_V1",
        "projector_hash": "projector",
        "question_contract_version": JEV_TYPESAFE_QUESTION_CONTRACT_VERSION_V2,
        "question_set_hash": JEV_TYPESAFE_QUESTION_SET_HASH_V2,
        "disposition_policy_version": JEV_TYPESAFE_DISPOSITION_POLICY_VERSION_V2,
        "disposition_policy_hash": JEV_TYPESAFE_DISPOSITION_POLICY_HASH_V2,
        "adapter_version": "JEV_TYPESAFE_SYSTEMONE_ADAPTER_V1",
    }
    base = {
        "threshold_strategy": 0.65,
        "threshold_entry": 0.65,
        "threshold_evidence": 0.75,
    }
    first = typesafe_model_cohort_key(
        protocol_spec_hash="protocol",
        protocol_spec=base,
        review=review,
    )
    second = typesafe_model_cohort_key(
        protocol_spec_hash="protocol",
        protocol_spec={**base, "threshold_entry": 0.80},
        review=review,
    )
    assert first != second


@pytest.mark.asyncio
async def test_fake_provider_uses_v2_question_set_and_conflict_first() -> None:
    sample = {
        "market": "KOSPI",
        "ticker": "LOCAL_ONLY",
        "name": "LOCAL_ONLY",
        "rank": 1,
        "action": "ENTRY_CANDIDATE",
        "candidate_state": "READY",
        "strategy": "TREND_FOLLOWING",
        "signal_date": "2026-10-06",
        "horizon_intent": "SHORT",
        "snapshot": {
            "market": "KOSPI",
            "candidate_state": "READY",
            "strategy": "TREND_FOLLOWING",
            "strategy_version_id": "s",
            "strategy_definition_hash": "h",
            "strategy_description": "Rising context is intended.",
            "action": "ENTRY_CANDIDATE",
            "conditions": {"passed": 1, "total": 1, "missing": 0, "top_missing": []},
            "risk": {"status": "READY", "warning": False, "warnings": []},
            "entry_risk_guide": {
                "price_rule": {
                    "kind": "RANGE",
                    "status": "MET",
                    "semantic_role": "EXECUTABLE_ENTRY_RANGE",
                    "executable_entry_range": True,
                },
                "action": {"status": "ENTRY_CANDIDATE"},
                "price_consistency": {
                    "status": "OK",
                    "classification": "ALIGNED",
                    "semantic_overlap": False,
                },
            },
            "_repro_condition_details": [
                {
                    "condition_id": "1",
                    "raw": "fixture",
                    "label": "fixture",
                    "detail": "fixture",
                    "status": "PASS",
                    "current_value": "rising",
                    "required_value": "rising",
                    "metric_key": "ma20_slope",
                }
            ],
        },
    }
    protocol = {
        "provider_id": "FAKE",
        "model_requested": "fake-v2",
        "expected_model_returned": "fake-v2",
        "deadline_seconds": 1.0,
        "question_contract_version": JEV_TYPESAFE_QUESTION_CONTRACT_VERSION_V2,
        "disposition_policy_version": JEV_TYPESAFE_DISPOSITION_POLICY_VERSION_V2,
        "threshold_strategy": 0.65,
        "threshold_entry": 0.65,
        "threshold_evidence": 0.75,
    }
    provider = FakeTypeSafeJevProvider(
        probabilities={
            "strategy_context_conflict": 0.90,
            "entry_context_conflict": 0.10,
            "overall_semantic_review_insufficient": 0.95,
        },
        returned_model="fake-v2",
    )
    result = await review_once(sample, protocol, provider)
    assert set(result.request["questions"]) == set(JEV_TYPESAFE_QUESTION_IDS_V2)
    assert result.disposition == "REVIEW_REQUIRED"
    assert result.reason_codes == ("STRATEGY_CONTEXT_CONFLICT",)
    assert result.bands == {}
    assert result.gate_results["overall_semantic_review_insufficient"] is True
    assert "LOCAL_ONLY" not in json.dumps(result.request["state"], ensure_ascii=False)
