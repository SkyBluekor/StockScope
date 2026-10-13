"""S10: bounded, read-only denominator audit for local JEV shadow observations.

This is *not* an accuracy estimate or an economic comparison. The same frozen
Prospective sample cohort contains both provisional adverse-history observations
and abstentions. A row-limit hit never proves that the entire capture was read.
No provider, outcomes database, model, migration or Scanner execution.
"""
from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from app.strategy.models import StrategyName

from .decision_reviewer_offline import DecisionReviewContractError
from .local_history_review import review_candidate
from .scanner_shadow_s7 import load_frozen_candidates


VERSION = "JEV_LOCAL_SHADOW_COHORT_AUDIT_V1"

ENTRY = "ENTRY_CANDIDATE"
PROVISIONAL = "LOCAL_SHADOW_REVIEW_ONLY"
NO_ADVERSE = "NO_ADVERSE_HISTORY_SIGNAL"
ABSTAIN = "ABSTAIN"
BLOCKED = "BLOCKED_BASELINE_INTEGRITY"
REFERENCE = "REFERENCE_ONLY"

_ENTRY_STATUSES = frozenset({PROVISIONAL, NO_ADVERSE, ABSTAIN, BLOCKED})
_ALLOWED_STATUSES = _ENTRY_STATUSES | {REFERENCE}
_KNOWN_STRATEGIES = frozenset(item.value for item in StrategyName)
_ROW_COUNTS = (
    "entry_candidates", "reviewable", "provisional_recheck", "no_adverse_signal",
    "abstained", "integrity_blocked",
)


def _percent(numerator: int, denominator: int) -> float | None:
    return round(100.0 * numerator / denominator, 2) if denominator else None


def _safe_strategy(sample: dict[str, Any]) -> str:
    strategy = sample.get("strategy")
    return strategy if type(strategy) is str and strategy in _KNOWN_STRATEGIES else "UNKNOWN_STRATEGY"


def _validate_record(
    capture: dict[str, Any], sample: dict[str, Any], observation: dict[str, Any],
) -> str:
    """Fail closed if the reviewer response cannot be bound to this exact sample."""
    if not isinstance(observation, dict):
        raise DecisionReviewContractError("LOCAL_COHORT_REVIEW_STATUS_INVALID")
    identity = observation.get("identity")
    if not isinstance(identity, dict) or (
        identity.get("capture_id") != capture["id"]
        or identity.get("sample_index") != sample["sample_index"]
        or identity.get("snapshot_hash") != sample["snapshot_hash"]
    ):
        raise DecisionReviewContractError("LOCAL_COHORT_REVIEW_IDENTITY_MISMATCH")
    status = observation.get("status")
    if type(status) is not str or status not in _ALLOWED_STATUSES:
        raise DecisionReviewContractError("LOCAL_COHORT_REVIEW_STATUS_INVALID")
    is_entry = sample.get("action") == ENTRY
    if (is_entry and status not in _ENTRY_STATUSES) or (
        not is_entry and status != REFERENCE
    ):
        raise DecisionReviewContractError("LOCAL_COHORT_REVIEW_SCOPE_MISMATCH")

    decision = observation.get("shadow_only_decision")
    if (status == PROVISIONAL and decision != "REVIEW_REQUIRED") or (
        status != PROVISIONAL and decision is not None
    ):
        raise DecisionReviewContractError("LOCAL_COHORT_UNSUPPORTED_DECISION")
    if (
        observation.get("shadow_adoption_eligible") is not False
        or observation.get("prospective_evaluation_eligible") is not False
        or observation.get("provider_status") != "PROVIDER_HOLD"
        or observation.get("actual_provider_calls") != 0
        or observation.get("db_writes") != 0
    ):
        raise DecisionReviewContractError("LOCAL_COHORT_UNAUTHORIZED_SIDE_EFFECT")
    return str(status)


def _new_counts() -> dict[str, int]:
    return {key: 0 for key in _ROW_COUNTS}


def _add_entry(counts: dict[str, int], status: str) -> None:
    counts["entry_candidates"] += 1
    if status == PROVISIONAL:
        counts["provisional_recheck"] += 1
        counts["reviewable"] += 1
    elif status == NO_ADVERSE:
        counts["no_adverse_signal"] += 1
        counts["reviewable"] += 1
    elif status == ABSTAIN:
        counts["abstained"] += 1
    elif status == BLOCKED:
        counts["integrity_blocked"] += 1


def _reason(observation: dict[str, Any]) -> str:
    # Fixed diagnostic codes only; do not relay free-text/market-derived content.
    value = observation.get("reason_code")
    if (type(value) is str and 1 <= len(value) <= 80
            and all(c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_" for c in value)):
        return value
    return "UNSPECIFIED_REASON"


def build_cohort_report(
    pairs: list[tuple[dict[str, Any], dict[str, Any]]], *,
    requested_capture_id: str, limit: int,
) -> dict[str, Any]:
    """Pure cohort aggregation. No individual security/market values emitted."""
    if not requested_capture_id or type(limit) is not int or not 1 <= limit <= 500:
        raise DecisionReviewContractError("LOCAL_COHORT_REQUEST_INVALID")
    if len(pairs) > limit:
        raise DecisionReviewContractError("LOCAL_COHORT_RETURN_LIMIT_VIOLATED")

    counts = _new_counts()
    reasons: Counter[str] = Counter()
    by_strategy: dict[str, dict[str, int]] = {}
    seen: set[tuple[str, int]] = set()
    canonical_capture_id: str | None = None
    reference_count = 0

    for capture, sample in pairs:
        if not isinstance(capture, dict) or not isinstance(sample, dict):
            raise DecisionReviewContractError("LOCAL_COHORT_SOURCE_INVALID")
        cid = capture.get("id")
        index = sample.get("sample_index")
        if (
            not isinstance(cid, str) or not cid
            or capture.get("status") != "COMPLETE"
            or type(index) is not int or index < 0
            or sample.get("capture_run_id") != cid
            or not isinstance(sample.get("snapshot_hash"), str)
            or not sample["snapshot_hash"]
        ):
            raise DecisionReviewContractError("LOCAL_COHORT_CAPTURE_IDENTITY_INVALID")
        if canonical_capture_id is None:
            canonical_capture_id = cid
        elif canonical_capture_id != cid:
            raise DecisionReviewContractError("LOCAL_COHORT_MIXED_CAPTURE")
        key = (cid, index)
        if key in seen:
            raise DecisionReviewContractError("LOCAL_COHORT_DUPLICATE_SAMPLE")
        seen.add(key)

        observation = review_candidate(capture, sample)
        status = _validate_record(capture, sample, observation)
        if status == REFERENCE:
            reference_count += 1
            continue
        _add_entry(counts, status)
        name = _safe_strategy(sample)
        if name not in by_strategy:
            by_strategy[name] = _new_counts()
        _add_entry(by_strategy[name], status)
        reasons[_reason(observation)] += 1

    eligible = counts["reviewable"]
    entries = counts["entry_candidates"]
    if sum(counts[k] for k in (
        "provisional_recheck", "no_adverse_signal", "abstained", "integrity_blocked",
    )) != entries or eligible != (
        counts["provisional_recheck"] + counts["no_adverse_signal"]
    ):
        raise DecisionReviewContractError("LOCAL_COHORT_DENOMINATOR_INCONSISTENT")
    limited = len(pairs) == limit
    return {
        "version": VERSION,
        "status": "LOCAL_SHADOW_COHORT_MEASUREMENT_ONLY",
        "requested_capture_id": requested_capture_id,
        "canonical_capture_id": canonical_capture_id,
        "scope": {
            "returned_samples": len(pairs),
            "limit": limit,
            "completeness": (
                "UNKNOWN_LIMIT_REACHED" if limited else "COMPLETE_WITHIN_CAPTURE"
            ),
            "full_capture_claim_allowed": not limited,
        },
        "counts": {
            **counts,
            "reference_only": reference_count,
        },
        "rates_pct": {
            "reviewable_of_entries": _percent(eligible, entries),
            "provisional_of_entries": _percent(counts["provisional_recheck"], entries),
            "provisional_of_reviewable": _percent(counts["provisional_recheck"], eligible),
            "abstained_of_entries": _percent(counts["abstained"], entries),
            "blocked_of_entries": _percent(counts["integrity_blocked"], entries),
        },
        "strategy_counts": {
            k: by_strategy[k] for k in sorted(by_strategy)
        },
        "reason_counts": dict(sorted(reasons.items())),
        "outcome_comparison": None,
        "incremental_investment_value": None,
        "evaluation_status": "NOT_EVALUATED_NO_APPROVED_OUTCOME_BINDING",
        "source_evidence_scope": "SCANNER_POST_RANK_HISTORY_NOT_INDEPENDENT_SOURCE",
        "adoption_eligible": False,
        "provider_status": "PROVIDER_HOLD",
        "actual_provider_calls": 0,
        "db_writes": 0,
    }


def measure_capture(
    simulation_db: Path, *, capture_id: str | None, limit: int = 60,
) -> dict[str, Any]:
    if not capture_id:
        raise DecisionReviewContractError("LOCAL_COHORT_CAPTURE_ID_REQUIRED")
    if type(limit) is not int or not 1 <= limit <= 500:
        raise DecisionReviewContractError("LOCAL_COHORT_LIMIT_INVALID")
    pairs = load_frozen_candidates(
        simulation_db, capture_id=capture_id, limit=limit,
    )
    return build_cohort_report(pairs, requested_capture_id=capture_id, limit=limit)
