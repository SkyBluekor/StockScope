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

from app.strategy.condition_semantics import condition_sources
from app.simulation.strategy_governance import (
    StrategyGovernanceError,
    strategy_definition,
)
from app.strategy.models import StrategyName

ENGINE_VERIFIED_SOURCE = "LEGACY_ENGINE_IDENTITY_VERIFIED"
LEGACY_SELECTION_SOURCE = "LEGACY_CURRENT_10_FALLBACK"
ENGINE_CONDITION_SOURCE = "SCANNER_ENGINE_PASSED_CONDITIONS_V1"


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

    
def attest_scanner_passed_conditions(
    *,
    strategy_key: Any,
    condition_state: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Retain proof of *observed engine PASS facts*, never synthesize from counts."""
    if not isinstance(condition_state, dict):
        return None
    consistency = condition_state.get("consistency")
    rows = condition_state.get("conditions")
    key = str(strategy_key or "")
    if (
        not isinstance(consistency, dict)
        or consistency.get("ok") is not True
        or not isinstance(rows, list)
        or not rows
    ):
        return None
    expected = condition_sources(key)
    if not expected or len(rows) != len(expected):
        return None
    raw = [str(item.get("raw") or "") for item in rows if isinstance(item, dict)]
    if len(raw) != len(expected) or len(set(raw)) != len(expected) or set(raw) != set(expected):
        return None
    if any(
        item.get("status") != "PASS"
        or not str(item.get("condition_id") or "")
        for item in rows
    ):
        return None
    try:
        counts_match = (
            int(condition_state.get("passed") or 0) == len(expected)
            and int(condition_state.get("total") or 0) == len(expected)
            and int(condition_state.get("missing") or 0) == 0
        )
    except (TypeError, ValueError):
        return None
    if not counts_match:
        return None
    return {
        "source": ENGINE_CONDITION_SOURCE,
        "strategy_key": key,
        "items": [
            {
                "condition_id": str(item["condition_id"]),
                "source_condition": str(item["raw"]),
                "status": "PASS",
            }
            for item in rows
        ],
        "passed": len(rows),
        "total": len(rows),
        "missing": 0,
    }


def _valid_scanner_condition_proof(candidate: dict[str, Any], key: str) -> bool:
    evidence = candidate.get("semantic_condition_evidence")
    conditions = candidate.get("conditions")
    if not isinstance(evidence, dict) or not isinstance(conditions, dict):
        return False
    if evidence.get("source") != ENGINE_CONDITION_SOURCE or evidence.get("strategy_key") != key:
        return False
    rows = evidence.get("items")
    expected = condition_sources(key)
    if not isinstance(rows, list) or not expected or len(rows) != len(expected):
        return False
    names = [
        str(item.get("source_condition") or "")
        for item in rows if isinstance(item, dict)
    ]
    if len(names) != len(expected) or len(set(names)) != len(expected) or set(names) != set(expected):
        return False
    if any(
        item.get("status") != "PASS"
        or not str(item.get("condition_id") or "")
        for item in rows
    ):
        return False
    try:
        return (
            evidence.get("passed") == len(expected)
            and evidence.get("total") == len(expected)
            and evidence.get("missing") == 0
            and int(conditions.get("passed") or 0) == len(expected)
            and int(conditions.get("total") or 0) == len(expected)
            and int(conditions.get("missing") or 0) == 0
        )
    except (TypeError, ValueError):
        return False


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
    if not _valid_scanner_condition_proof(result, key):
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
