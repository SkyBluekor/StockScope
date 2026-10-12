"""Fail-closed semantic-only verification of the Scanner's *pinned* selection policy.

The registry resolves and validates ACTIVE/ROLLBACK snapshots and baseline before
the Scanner starts. We verify the exact immutable pin against its Scanner result
and Prospective request, without re-reading mutable runtime policy references.
No Scanner decision, stored historical capture, or V4 activation is changed.
"""
from __future__ import annotations

from typing import Any

from app.strategy.models import StrategyName
from app.strategy.production_selection_policy import (
    SELECTION_POLICY_CONTRACT_VERSION,
    SelectionPolicyPin,
    legacy_selection_policy,
)

VERIFIED_POLICY = "VERIFIED_PINNED_EXECUTION"
UNVERIFIED_POLICY = "UNVERIFIED"
LEGACY_SOURCE = "LEGACY_CURRENT_10_FALLBACK"
ACTIVE_SOURCE = "ACTIVE_SELECTION_POLICY"
ROLLBACK_SOURCE = "ROLLBACK_FALLBACK"


def validate_pinned_selection_policy(
    *,
    scanner_policy: dict[str, Any] | None,
    request_policy_id: str | None,
    request_policy_hash: str | None,
    pin: SelectionPolicyPin | None,
) -> tuple[bool, str]:
    """Require an actual execution pin; metadata or today's policy alone is not proof."""
    if pin is None or not isinstance(scanner_policy, dict):
        return False, "POLICY_PROVENANCE_MISSING"
    if not pin.policy_id or not pin.policy_hash or not request_policy_id or not request_policy_hash:
        return False, "POLICY_PROVENANCE_MISSING"
    if pin.policy_id != request_policy_id or pin.policy_hash != request_policy_hash:
        return False, "POLICY_PIN_MISMATCH"
    # Compare all fields, including baseline fingerprints and fallback reason.
    # Omissions and forged claims must not create semantic proof.
    if scanner_policy != pin.metadata():
        return False, "POLICY_PIN_MISMATCH"
    if pin.policy_contract_version != SELECTION_POLICY_CONTRACT_VERSION:
        return False, "POLICY_DEFINITION_MISMATCH"

    rows = pin.operating_strategies
    keys = [key for _, key, _ in rows]
    allowed = {item.value for item in StrategyName if item is not StrategyName.NO_TRADE}
    if not rows or len(keys) != len(set(keys)) or any(key not in allowed for key in keys):
        return False, "POLICY_DEFINITION_MISMATCH"

    if pin.policy_source == LEGACY_SOURCE:
        legacy = legacy_selection_policy()
        expected_rows = tuple(
            (row.get("strategy_version_id"), row["strategy_key"], row.get("definition_hash"))
            for row in legacy["operating_strategies"]
        )
        if (
            pin.policy_id != legacy["policy_id"]
            or pin.policy_hash != legacy["policy_hash"]
            or pin.fallback_used is not True
            or rows != expected_rows
            or pin.scanner_baseline_id is not None
            or pin.production_fingerprint is not None
            or pin.production_policy_fingerprint is not None
        ):
            return False, "POLICY_DEFINITION_MISMATCH"
    elif pin.policy_source in {ACTIVE_SOURCE, ROLLBACK_SOURCE}:
        if (
            pin.fallback_used is not (pin.policy_source == ROLLBACK_SOURCE)
            or not pin.scanner_baseline_id
            or not pin.production_fingerprint
            or not pin.production_policy_fingerprint
            or any(not version or not definition_hash for version, _, definition_hash in rows)
        ):
            return False, "POLICY_DEFINITION_MISMATCH"
        # The originating ProductionStrategySelectionRegistry already validated
        # snapshot hash and current baseline when constructing this pin.
    else:
        return False, "POLICY_PROVENANCE_MISSING"
    return True, "POLICY_PIN_VERIFIED"


def verify_candidate_policy_binding(
    candidate: dict[str, Any], pin: SelectionPolicyPin | None,
) -> tuple[bool, str]:
    if pin is None:
        return False, "POLICY_PROVENANCE_MISSING"
    strategy = str(candidate.get("strategy") or "")
    reference = pin.strategy_reference(strategy)
    if reference is None:
        return False, "POLICY_STRATEGY_BINDING_MISMATCH"
    version = candidate.get("strategy_version_id")
    definition_hash = candidate.get("strategy_definition_hash")
    if pin.policy_source == LEGACY_SOURCE:
        if version is not None or definition_hash is not None:
            return False, "POLICY_STRATEGY_BINDING_MISMATCH"
        return True, "POLICY_CANDIDATE_VERIFIED"
    if (
        not reference["strategy_version_id"]
        or not reference["definition_hash"]
        or version != reference["strategy_version_id"]
        or definition_hash != reference["definition_hash"]
    ):
        return False, "POLICY_STRATEGY_BINDING_MISMATCH"
    return True, "POLICY_CANDIDATE_VERIFIED"


def semantic_policy_record(pin: SelectionPolicyPin, *, reason: str) -> dict[str, Any]:
    if reason != "POLICY_CANDIDATE_VERIFIED":
        return {"status": UNVERIFIED_POLICY, "reason": reason}
    return {
        "status": VERIFIED_POLICY,
        "policy_source": pin.policy_source,
        "policy_id": pin.policy_id,
        "policy_hash": pin.policy_hash,
        "policy_contract_version": pin.policy_contract_version,
        "fallback_used": pin.fallback_used,
    }
