"""Read-only semantic provenance from the already-written Scanner repro audit.

The production Scanner and its frozen baseline are never modified. For the
legacy selection fallback, only the matching real engine PASS condition details
from its immutable reproducibility artifact may justify semantic-only binding.
No HTTP, raw market replay, provider call or policy activation is performed.
"""
from __future__ import annotations

from functools import lru_cache
import json
from pathlib import Path
from typing import Any

from app.simulation.strategy_governance import StrategyGovernanceError, strategy_definition
from app.strategy.condition_semantics import condition_sources
from app.strategy.models import StrategyName

ENGINE_VERIFIED_SOURCE = "LEGACY_ENGINE_IDENTITY_VERIFIED"
ENGINE_CONDITION_SOURCE = "SCANNER_REPRO_ENGINE_PASSED_CONDITIONS_V1"
LEGACY_SELECTION_SOURCE = "LEGACY_CURRENT_10_FALLBACK"
PROJECT_ROOT = Path(__file__).resolve().parents[3]
REPRO_ROOT = PROJECT_ROOT / "scanner-repro"
MAX_REPRO_BYTES = 32 * 1024 * 1024


@lru_cache(maxsize=16)
def _current_engine_identity(key: str) -> tuple[str, str] | None:
    try:
        version = strategy_definition(StrategyName(key))
    except (ValueError, StrategyGovernanceError):
        return None
    if version.strategy_key != key or version.operational_status != "OPERATING":
        return None
    return version.strategy_version_id, version.definition_hash


def _row_key(candidate: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(candidate.get("market") or ""),
        str(candidate.get("code") or ""),
        str(candidate.get("rank") or ""),
    )


def verified_scanner_repro_rows(result: dict[str, Any]) -> dict[tuple[str, str, str], dict[str, Any]]:
    """Admit only fresh local audit rows matching the delivered Scanner result.

    Caller may safely pass malformed, cached or stale results: they yield no
    attestation rather than an optimistic fallback or exception.
    """
    if result.get("scanner_cache_hit") is not False:
        return {}
    diagnostics = result.get("diagnostics")
    meta = diagnostics.get("reproducibility_audit") if isinstance(diagnostics, dict) else None
    if not isinstance(meta, dict) or meta.get("written") is not True:
        return {}
    if meta.get("result_source") != "fresh_analysis":
        return {}
    filename = str(meta.get("filename") or "")
    location = str(meta.get("path") or "")
    if not filename.startswith("scanner-repro_") or not filename.endswith(".json") or not location:
        return {}
    try:
        trusted_root = REPRO_ROOT.resolve(strict=True)
        path = Path(location).resolve(strict=True)
        if path.parent != trusted_root or path.name != filename:
            return {}
        if path.stat().st_size > MAX_REPRO_BYTES:
            return {}
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return {}
        if (
            raw.get("result_source") != "fresh_analysis"
            or raw.get("scanner_version") != result.get("version")
            or raw.get("analysis_date") != result.get("requested_as_of")
            or raw.get("market_scope") != result.get("market_scope")
            or raw.get("existing_latest_day_fingerprint") != result.get("input_fingerprint")
            or meta.get("analysis_date") != raw.get("analysis_date")
            or raw.get("candidate_pool_complete") is not True
        ):
            return {}
        rows = raw.get("candidates")
        if not isinstance(rows, list) or raw.get("candidate_count") != len(rows):
            return {}
        if meta.get("candidate_count") != len(rows):
            return {}
        out = {}
        for row in rows:
            if not isinstance(row, dict):
                return {}
            key = _row_key(row)
            if not all(key) or key in out:
                return {}
            out[key] = row
        return out
    except (OSError, ValueError, TypeError, UnicodeError, json.JSONDecodeError):
        return {}


def _actual_passed_conditions(
    candidate: dict[str, Any], audited: dict[str, Any],
) -> dict[str, Any] | None:
    key = str(candidate.get("strategy") or "")
    expected = condition_sources(key)
    if not expected:
        return None
    for name in (
        "market", "code", "rank", "strategy", "action",
        "candidate_state", "data_date", "current_price", "conditions", "risk",
    ):
        if candidate.get(name) != audited.get(name):
            return None
    state = candidate.get("conditions")
    details = audited.get("scanner_inputs")
    details = details.get("condition_details") if isinstance(details, dict) else None
    if not isinstance(state, dict) or not isinstance(details, list):
        return None
    if len(details) != len(expected):
        return None
    names = [str(x.get("raw") or "") for x in details if isinstance(x, dict)]
    if len(names) != len(expected) or len(set(names)) != len(expected) or set(names) != set(expected):
        return None
    if any(
        row.get("status") != "PASS"
        or not str(row.get("condition_id") or "")
        for row in details
    ):
        return None
    try:
        if (
            int(state.get("passed") or 0) != len(expected)
            or int(state.get("total") or 0) != len(expected)
            or int(state.get("missing") or 0) != 0
        ):
            return None
    except (TypeError, ValueError):
        return None
    return {
        "source": ENGINE_CONDITION_SOURCE,
        "strategy_key": key,
        "passed": len(details),
        "total": len(details),
        "missing": 0,
        "items": [
            {
                "condition_id": str(row["condition_id"]),
                "source_condition": str(row["raw"]),
                "status": "PASS",
            }
            for row in details
        ],
    }


def semantic_projection_candidate(
    candidate: dict[str, Any],
    *,
    selection_policy: dict[str, Any] | None,
    audited: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a temporary semantic input; do NOT override Scanner identity."""
    projected = dict(candidate)
    if projected.get("strategy_version_id") is not None or projected.get(
        "strategy_definition_hash"
    ) is not None:
        return projected
    if (
        not isinstance(selection_policy, dict)
        or selection_policy.get("policy_source") != LEGACY_SELECTION_SOURCE
        or selection_policy.get("fallback_used") is not True
        or not str(selection_policy.get("policy_id") or "")
        or not str(selection_policy.get("policy_hash") or "")
        or not isinstance(audited, dict)
    ):
        return projected
    evidence = _actual_passed_conditions(candidate, audited)
    if evidence is None:
        return projected
    key = str(projected.get("strategy") or "")
    version = _current_engine_identity(key)
    if version is None:
        return projected
    projected["strategy_version_id"], projected["strategy_definition_hash"] = version
    projected["semantic_strategy_identity"] = {
        "source": ENGINE_VERIFIED_SOURCE,
        "strategy_key": key,
        "strategy_version_id": version[0],
        "strategy_definition_hash": version[1],
        "selection_policy_id": selection_policy["policy_id"],
        "selection_policy_hash": selection_policy["policy_hash"],
    }
    projected["semantic_condition_evidence"] = evidence
    return projected
