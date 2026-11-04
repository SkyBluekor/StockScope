"""LIVE-04R contract regression: never invent horizon or strategy identity.

Existing Prospective capture writer binds the *scanner request's* horizon and
the immutable verified production selection pin. Local AI readiness may report
its limits; it must not manufacture original evidence for old Scanner runs.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.horizon import HORIZON_POLICY_VERSION, HorizonPolicyError
from app.prospective.service import ProspectiveService
from app.strategy.models import StrategyName
from app.strategy.production_selection_policy import (
    SELECTION_POLICY_CONTRACT_VERSION, SelectionPolicyPin,
)
from app.strategy.semantic_policy_provenance import (
    verify_candidate_policy_binding,
)


def _payload(horizon):
    return SimpleNamespace(
        market_scope="ALL", as_of_date="2026-10-28",
        candidate_limit=5, horizon_intent=horizon,
    )


def test_unrequested_horizon_is_not_defaulted_by_new_capture_request():
    request = ProspectiveService.capture_request_from_scanner_payload(_payload(None))
    assert request.horizon_intent == "LEGACY_UNSPECIFIED"
    assert request.horizon_policy_version is None


def test_explicit_horizon_is_preserved_with_its_version_not_activated():
    request = ProspectiveService.capture_request_from_scanner_payload(_payload("SHORT"))
    assert request.horizon_intent == "SHORT"
    assert request.horizon_policy_version == HORIZON_POLICY_VERSION
    assert request.selection_policy_id is None
    assert request.selection_policy_hash is None


def test_unrecognized_horizon_cannot_be_silently_backfilled():
    with pytest.raises(HorizonPolicyError) as exc:
        ProspectiveService.capture_request_from_scanner_payload(_payload("SOMEDAY"))
    assert exc.value.code == "HORIZON_INTENT_INVALID"


def test_unverified_or_missing_original_strategy_is_not_promoted_from_policy_pin():
    strategy = next(s.value for s in StrategyName if s is not StrategyName.NO_TRADE)
    pin = SelectionPolicyPin(
        policy_id="ACTIVE-ONLY-TEST", policy_hash="synthetic-hash",
        policy_contract_version=SELECTION_POLICY_CONTRACT_VERSION,
        policy_source="ACTIVE_SELECTION_POLICY", fallback_used=False,
        fallback_reason=None,
        operating_strategies=(("ver-1", strategy, "definition-hash-1"),),
        scanner_baseline_id="baseline-test",
        production_fingerprint="scanner-test",
        production_policy_fingerprint="policy-test",
    )
    original = {"strategy": strategy, "strategy_version_id": "ver-1",
                "strategy_definition_hash": "definition-hash-1"}
    valid, _ = verify_candidate_policy_binding(original, pin)
    assert valid is True

    # Missing original identity is not made authentic merely because an active
    # Selection Policy happens to contain the same strategy key.
    valid_missing, code_missing = verify_candidate_policy_binding(
        {"strategy": strategy}, pin,
    )
    assert valid_missing is False
    assert code_missing == "POLICY_STRATEGY_BINDING_MISMATCH"

    valid_mismatch, code_mismatch = verify_candidate_policy_binding(
        {**original, "strategy_definition_hash": "old-different-hash"}, pin,
    )
    assert valid_mismatch is False
    assert code_mismatch == "POLICY_STRATEGY_BINDING_MISMATCH"
