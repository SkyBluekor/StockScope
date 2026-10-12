"""JEV-ACT2-S2: readonly horizon and real authored-rule reachability guards."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.horizon import (
    HORIZON_POLICY_VERSION,
    HorizonPolicyError,
    horizon_policy_catalog,
    require_horizon_activatable,
    resolve_horizon_context,
)
from app.jev import semantic_reachability as reachability_module
from app.jev.semantic_reachability import audit_current_pass_mapping_reachability
from app.prospective.service import ProspectiveService
from app.strategy.condition_assertions import STANCE_SUPPORTS, STANCE_UNRESOLVED
from app.strategy.semantic_composition import (
    LOCAL_MATCH,
    RESIDUAL_SEMANTIC_REVIEW,
    compose_semantics,
)


def test_all_ten_current_authored_pass_mappings_have_no_residual_route() -> None:
    report = audit_current_pass_mapping_reachability()
    assert report["scope"] == "STRUCTURAL_ONLY_CURRENT_AUTHORED_COMPLETE_PASS_MAPPINGS"
    assert report["strategy_count"] == report["complete_contracts"] == 10
    assert report["local_match_routes"] == 10
    assert report["residual_routes"] == report["undetermined_contracts"] == 0
    assert report["real_market_samples_tested"] == report["provider_calls"] == 0
    assert report["conclusion"] == "NO_RESIDUAL_FROM_CURRENT_COMPLETE_PASS_MAPPINGS"
    assert len({row["strategy"] for row in report["strategies"]}) == 10
    for row in report["strategies"]:
        assert row["pass_conditions"] > 0
        assert row["assertion_stances"] == [STANCE_SUPPORTS]
        assert row["relation_kinds"] == ["REQUIRES_ALL"]
        assert row["relation_materialities"] == ["HARD"]
        assert row["composition_status"] == LOCAL_MATCH
        assert row["verdict"] == "LOCAL_MATCH_FROM_PASS_MAPPING"


def test_unavailable_mapping_does_not_claim_structural_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = reachability_module.assertion_sources
    monkeypatch.setattr(
        reachability_module,
        "assertion_sources",
        lambda key: () if key == "trend_following" else original(key),
    )
    report = audit_current_pass_mapping_reachability()
    assert report["undetermined_contracts"] >= 1
    assert report["conclusion"] == "UNDETERMINED_CONTRACTS"


def test_semantic_composer_can_express_synthetic_residual_but_not_from_current_pass() -> None:
    contract = {
        "concepts": [{"concept_id": "only", "definition_id": "only", "text": "example"}],
        "relations": [
            {
                "relation_id": "synthetic-required",
                "kind": "REQUIRES_ALL",
                "members": ["only"],
                "guards": [],
                "materiality": "HARD",
            }
        ],
    }
    outcome = compose_semantics(
        relation_contract=contract,
        assertions=[{"stance": STANCE_UNRESOLVED, "concept_refs": ["only"]}],
    )
    assert outcome.status == RESIDUAL_SEMANTIC_REVIEW
    # This demonstrates the composer capability, not an observed Scanner case.


@pytest.mark.parametrize("intent", ["SHORT", "MEDIUM"])
def test_unapproved_explicit_horizon_rejected_before_new_scanner_capture(intent: str) -> None:
    context = resolve_horizon_context(intent)
    assert context.policy_version == HORIZON_POLICY_VERSION
    assert context.support_status == "EVALUATION_PENDING"
    assert context.reason_code == "HORIZON_NUMERIC_POLICY_NOT_APPROVED"
    assert context.review_cycle_trading_days is None
    assert context.time_stop_trading_days is None
    assert context.strategy_support is None
    assert context.required_inputs is None
    assert context.confirmation_policy is None
    with pytest.raises(HorizonPolicyError) as error:
        require_horizon_activatable(context)
    assert error.value.code == "HORIZON_POLICY_NOT_ACTIVE"

    # Capture helper may serialize the intent; the Scanner HTTP entry gate
    # above must approve it before any real job/capture begins.
    request = ProspectiveService.capture_request_from_scanner_payload(
        SimpleNamespace(
            market_scope="ALL",
            candidate_limit=5,
            as_of_date="2026-10-08",
            horizon_intent=intent,
        )
    )
    assert request.horizon_intent == intent
    assert request.horizon_policy_version == HORIZON_POLICY_VERSION


def test_legacy_capture_scope_and_numeric_approval_not_silently_changed() -> None:
    context = resolve_horizon_context(None)
    assert context.intent == "LEGACY_UNSPECIFIED"
    assert context.policy_version is None
    require_horizon_activatable(context)  # Existing legacy Scanner still allowed.
    catalog = horizon_policy_catalog()
    assert catalog["numeric_policy_approved"] is False
    assert catalog["rules"]["legacy_backfill_forbidden"] is True
    assert all(item["support_status"] == "EVALUATION_PENDING" for item in catalog["options"])
