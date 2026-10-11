"""Attested, semantics-only bridge for Scanner's legacy selection fallback.

The legacy policy intentionally contains no strategy version/hash. A *fresh
Scanner evaluation* can nevertheless attest the selected production engine
definition without changing that policy, the candidate's original identity,
its rank or its risk decision. Cached and foreign results must carry matching
attestation before they can be used.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Any

from app.simulation.strategy_governance import (
    StrategyGovernanceError,
    strategy_definition,
)
from app.strategy.models import StrategyName

ENGINE_VERIFIED_SOURCE = "LEGACY_ENGINE_IDENTITY_VERIFIED"
LEGACY_SELECTION_SOURCE = "LEGACY_CURRENT_10_FALLBACK"


@lru_cache(maxsize=16)
def _engine_definition(key: str) -> tuple[str, str] | None:
    try:
        definition = strategy_definition(StrategyName(key))
    except (ValueError, StrategyGovernanceError):
        return None
    if definition.operational_status != "OPERATING" or definition.strategy_key != key:
        return None
    return definition.strategy_version_id, definition.definition_hash


def attest_legacy_scanner_identity(
    *,
    strategy_key: Any,
    policy_binding_version: Any,
    policy_binding_hash: Any,
    selection_policy: dict[str, Any] | None,
) -> dict[str, str] | None:
    """Called only during actual Scanner strategy evaluation, never from DB."""
    if not isinstance(selection_policy, dict):
        return None
    if (
        selection_policy.get("policy_source") != LEGACY_SELECTION_SOURCE
        or selection_policy.get("fallback_used") is not True
        or policy_binding_version is not None
        or policy_binding_hash is not None
    ):
        return None
    policy_id = str(selection_policy.get("policy_id") or "")
    policy_hash = str(selection_policy.get("policy_hash") or "")
    key = str(strategy_key or "")
    if not policy_id or not policy_hash or not key:
        return None
    current = _engine_definition(key)
    if current is None:
        return None
    version, definition_hash = current
    return {
        "source": ENGINE_VERIFIED_SOURCE,
        "strategy_key": key,
        "strategy_version_id": version,
        "strategy_definition_hash": definition_hash,
        "selection_policy_id": policy_id,
        "selection_policy_hash": policy_hash,
    }


def semantic_projection_candidate(
    candidate: dict[str, Any],
    *,
    selection_policy: dict[str, Any] | None,
) -> dict[str, Any]:
    """Build a temporary semantic input; never mutate the Scanner result.

    A matching engine attestation is necessary but is not a new Selection
    Policy approval. Unsupported/stale/partial claims safely remain missing.
    """
    result = dict(candidate)
    if result.get("strategy_version_id") is not None or result.get(
        "strategy_definition_hash"
    ) is not None:
        return result
    if not isinstance(selection_policy, dict) or (
        selection_policy.get("policy_source") != LEGACY_SELECTION_SOURCE
        or selection_policy.get("fallback_used") is not True
    ):
        return result
    claim = result.get("semantic_strategy_identity")
    if not isinstance(claim, dict) or claim.get("source") != ENGINE_VERIFIED_SOURCE:
        return result
    key = str(result.get("strategy") or "")
    if not key or claim.get("strategy_key") != key:
        return result
    if (
        claim.get("selection_policy_id") != selection_policy.get("policy_id")
        or claim.get("selection_policy_hash") != selection_policy.get("policy_hash")
    ):
        return result
    current = _engine_definition(key)
    if current is None or (
        claim.get("strategy_version_id"),
        claim.get("strategy_definition_hash"),
    ) != current:
        return result
    result["strategy_version_id"] = current[0]
    result["strategy_definition_hash"] = current[1]
    return result
