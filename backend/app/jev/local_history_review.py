"""S9: read-only post-selection history counterevidence for local JEV shadow.

The 3-year Scanner historical evidence is computed for explanation *after*
candidate selection and does not change baseline rank, Risk or entry.
This reviewer reads ONLY that frozen field (no market re-fetch/DB mutation)
and issues a narrow *non-adopted* shadow opinion for sufficiently supported
negative historical expectancy. It does not claim a logical Scanner bug or
prospective investment performance improvement.
"""
from __future__ import annotations

from collections import Counter
from datetime import date
from math import isfinite
from pathlib import Path
from typing import Any

from app.backtest.historical_evidence import (
    EVIDENCE_YEARS, MIN_SAMPLE_FOR_EVALUATION, validation_start_for_years,
)
from app.prospective.models import digest_json

from .decision_reviewer_offline import DecisionReviewContractError
from .local_evidence_audit import diagnose_candidate as audit_frozen_evidence
from .scanner_shadow_s7 import load_frozen_candidates


VERSION = "JEV_LOCAL_POST_RANK_HISTORY_REVIEW_V1"


def _verified_date(value: Any) -> date | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.isoformat() == value else None


def _finite_number(value: Any) -> float | None:
    if type(value) not in (int, float):
        return None
    try:
        converted = float(value)
    except (OverflowError, ValueError):
        return None
    return converted if isfinite(converted) else None


def _not_ready(identity: dict[str, Any], *, status: str, reason: str) -> dict[str, Any]:
    return {
        "version": VERSION,
        "identity": identity,
        "status": status,
        "reason_code": reason,
        "evidence_basis": None,
        "shadow_only_decision": None,
        "shadow_adoption_eligible": False,
        "prospective_evaluation_eligible": False,
        "provider_status": "PROVIDER_HOLD",
        "actual_provider_calls": 0,
        "db_writes": 0,
    }


def review_candidate(capture: dict[str, Any], sample: dict[str, Any]) -> dict[str, Any]:
    """Inspect a frozen, valid candidate without copying market-derived prose."""
    audit = audit_frozen_evidence(capture, sample)
    identity = audit["identity"]
    if audit["category"] == "REFERENCE_ONLY":
        return _not_ready(identity, status="REFERENCE_ONLY", reason="NOT_ENTRY_CANDIDATE")
    if audit["category"] != "LOCAL_VALIDATED":
        return _not_ready(
            identity, status="BLOCKED_BASELINE_INTEGRITY",
            reason="FULLY_VALIDATED_FROZEN_CANDIDATE_REQUIRED",
        )

    snapshot = sample["snapshot"]
    history = snapshot.get("historical_evidence")
    if not isinstance(history, dict):
        return _not_ready(
            identity, status="ABSTAIN", reason="HISTORICAL_EVIDENCE_NOT_FROZEN",
        )
    if snapshot.get("verification_level") != "CURRENT_AND_3Y_EVIDENCE":
        return _not_ready(
            identity, status="ABSTAIN", reason="HISTORY_VERIFICATION_LEVEL_UNCONFIRMED",
        )
    if history.get("verified") is not True or history.get("strategy") != sample.get("strategy"):
        return _not_ready(
            identity, status="ABSTAIN", reason="HISTORICAL_EVIDENCE_IDENTITY_UNVERIFIED",
        )
    if history.get("validation_years") != EVIDENCE_YEARS:
        return _not_ready(
            identity, status="ABSTAIN", reason="HISTORICAL_PERIOD_UNVERIFIED",
        )
    signal_date = _verified_date(sample.get("signal_date"))
    period = history.get("period")
    start = _verified_date(period.get("start")) if isinstance(period, dict) else None
    end = _verified_date(period.get("end")) if isinstance(period, dict) else None
    if (
        signal_date is None or start is None or end is None
        or end != signal_date
        or start != validation_start_for_years(end)
    ):
        return _not_ready(
            identity, status="ABSTAIN", reason="HISTORICAL_PERIOD_NOT_ASOF_SIGNAL",
        )

    n = history.get("sample_count")
    minimum = history.get("minimum_sample")
    enough = history.get("sample_sufficient")
    if (
        type(n) is not int or n < MIN_SAMPLE_FOR_EVALUATION
        or type(minimum) is not int or minimum != MIN_SAMPLE_FOR_EVALUATION
        or enough is not True or n < minimum
    ):
        return _not_ready(
            identity, status="ABSTAIN", reason="HISTORICAL_SAMPLE_NOT_SUFFICIENT",
        )

    expectancy = _finite_number(history.get("expectancy_pct"))
    if expectancy is None or history.get("status") not in {"GOOD", "FAIR", "WEAK"}:
        return _not_ready(
            identity, status="ABSTAIN", reason="HISTORICAL_METRICS_NOT_VERIFIED",
        )

    # GOOD and FAIR are produced only for positive expectancy by the
    # historical evidence scorer; contradictory frozen rows are untrusted.
    if history["status"] in {"GOOD", "FAIR"} and expectancy <= 0:
        return _not_ready(
            identity, status="ABSTAIN", reason="HISTORICAL_STATUS_METRIC_CONFLICT",
        )
    adverse = history["status"] == "WEAK" and expectancy < 0
    # This is an *additional post-rank perspective*, not independent source
    # provenance, TypeSafe semantics, or a prospective economic finding.
    body = {
        "version": VERSION,
        "identity": identity,
        "status": "LOCAL_SHADOW_REVIEW_ONLY" if adverse else "NO_ADVERSE_HISTORY_SIGNAL",
        "reason_code": (
            "POST_RANK_NEGATIVE_STRATEGY_EXPECTANCY"
            if adverse else "NO_STRICT_NEGATIVE_EXPECTANCY_CONTRAST"
        ),
        "evidence_basis": {
            "owner": "SCANNER_POST_RANK_HISTORY",
            "independent_of": "PRODUCTION_SELECTION_AND_RISK_ONLY",
            "evidence_refs": [
                "snapshot.historical_evidence.verified",
                "snapshot.historical_evidence.strategy",
                "snapshot.historical_evidence.period",
                "snapshot.historical_evidence.sample_count",
                "snapshot.historical_evidence.expectancy_pct",
                "snapshot.historical_evidence.status",
            ],
            "sample_count": n,
            "expectancy_pct": expectancy,
        },
        "shadow_only_decision": "REVIEW_REQUIRED" if adverse else None,
        "shadow_adoption_eligible": False,
        "prospective_evaluation_eligible": False,
        "provider_status": "PROVIDER_HOLD",
        "actual_provider_calls": 0,
        "db_writes": 0,
    }
    body["review_identity"] = digest_json({
        "review_version": VERSION,
        "snapshot_hash": sample["snapshot_hash"],
        "capture_id": capture["id"],
        "sample_index": sample["sample_index"],
        "reason_code": body["reason_code"],
    })
    return body


def review_capture(
    simulation_db: Path, *, capture_id: str | None,
    limit: int = 60, sample_index: int | None = None,
) -> dict[str, Any]:
    if not capture_id:
        raise DecisionReviewContractError("LOCAL_HISTORY_CAPTURE_ID_REQUIRED")
    if sample_index is not None and (
        type(sample_index) is not int or not 0 <= sample_index <= 500
    ):
        raise DecisionReviewContractError("LOCAL_HISTORY_SAMPLE_INDEX_INVALID")
    pairs = load_frozen_candidates(simulation_db, capture_id=capture_id, limit=limit)
    if sample_index is not None:
        pairs = [(c, s) for c, s in pairs if s["sample_index"] == sample_index]
        if not pairs:
            raise DecisionReviewContractError("LOCAL_HISTORY_SAMPLE_NOT_FOUND")
    records = [review_candidate(c, s) for c, s in pairs]
    counts = Counter(str(row["status"]) for row in records)
    return {
        "version": VERSION,
        "status": "LOCAL_HISTORY_SHADOW_OBSERVATION_ONLY",
        "capture_id": pairs[0][0]["id"] if pairs else capture_id,
        "total_records": len(records),
        "counts": dict(sorted(counts.items())),
        "provisional_review_count": counts["LOCAL_SHADOW_REVIEW_ONLY"],
        "prospective_evaluation_eligible": False,
        "records": records,
        "provider_status": "PROVIDER_HOLD",
        "actual_provider_calls": 0,
        "db_writes": 0,
    }
