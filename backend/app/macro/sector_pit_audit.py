from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from app.macro.identity import content_hash
from app.macro.sector_evidence import (
    assess_sector_membership_evidence,
    validate_sector_membership_evidence,
)


SECTOR_PIT_COVERAGE_AUDIT_CONTRACT_VERSION = (
    "VN_NEXT6C_S2_SECTOR_PIT_COVERAGE_AUDIT_V1"
)

_STATUS_ORDER = (
    "PIT_ELIGIBLE",
    "STATIC_ONLY",
    "MAPPING_MISSING",
    "EFFECTIVE_RANGE_MISMATCH",
    "SOURCE_TIME_UNPROVEN",
    "BENCHMARK_UNRESOLVED",
    "CONFLICTING_PIT_EVIDENCE",
)


def _aware_utc(value: str, field: str) -> datetime:
    raw = str(value or "").strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise ValueError(
            f"{field} must be a timezone-aware ISO-8601 datetime."
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(
            f"{field} must be a timezone-aware ISO-8601 datetime."
        )
    return parsed.astimezone(timezone.utc)


def _date_text(value: str | date, field: str) -> str:
    if isinstance(value, date):
        return value.isoformat()
    raw = str(value or "").strip()
    if len(raw) == 8 and raw.isdigit():
        return date(int(raw[:4]), int(raw[4:6]), int(raw[6:8])).isoformat()
    try:
        return date.fromisoformat(raw).isoformat()
    except ValueError as exc:
        raise ValueError(f"{field} must be YYYY-MM-DD or YYYYMMDD.") from exc


def _target_record(target: dict[str, Any]) -> dict[str, str]:
    ticker = str(target.get("ticker") or "").strip().upper()
    market = str(target.get("market") or "").strip().upper()
    if not ticker:
        raise ValueError("target ticker is required.")
    if market not in {"KOSPI", "KOSDAQ"}:
        raise ValueError("target market must be KOSPI or KOSDAQ.")
    return {
        "ticker": ticker,
        "market": market,
        "target_date": _date_text(target.get("target_date"), "target_date"),
    }


def _status_from_assessments(
    assessments: list[dict[str, Any]],
) -> tuple[str, str | None, dict[str, Any] | None]:
    if not assessments:
        return "MAPPING_MISSING", "NO_KNOWN_MAPPING_EVIDENCE", None

    eligible = [
        item for item in assessments if item["status"] == "PIT_ELIGIBLE"
    ]
    if eligible:
        identities = {
            (
                item.get("sector_group"),
                item.get("benchmark_identity"),
            )
            for item in eligible
        }
        if len(identities) > 1:
            return (
                "CONFLICTING_PIT_EVIDENCE",
                "MULTIPLE_PIT_MEMBERSHIP_IDENTITIES",
                None,
            )
        selected = sorted(
            eligible,
            key=lambda item: str(item["evidence_hash"]),
        )[0]
        return "PIT_ELIGIBLE", None, selected

    priority = (
        "STATIC_ONLY",
        "EFFECTIVE_RANGE_MISMATCH",
        "SOURCE_TIME_UNPROVEN",
        "BENCHMARK_UNRESOLVED",
    )
    for status in priority:
        matching = [item for item in assessments if item["status"] == status]
        if matching:
            selected = sorted(
                matching,
                key=lambda item: str(item["evidence_hash"]),
            )[0]
            return status, str(selected.get("reason") or ""), selected

    return "MAPPING_MISSING", "NO_USABLE_MAPPING_EVIDENCE", None


def build_sector_pit_coverage_audit(
    *,
    targets: list[dict[str, Any]] | tuple[dict[str, Any], ...],
    evidences: list[dict[str, Any]] | tuple[dict[str, Any], ...],
    decision_cutoff: str,
    available_benchmark_identities: set[str] | frozenset[str],
) -> dict[str, Any]:
    """Audit PIT sector-membership coverage without inferring missing history.

    Evidence whose known_at is after the frozen decision cutoff is ignored
    entirely. This makes future evidence additions incapable of rewriting a
    past audit result.
    """

    cutoff_dt = _aware_utc(decision_cutoff, "decision_cutoff")
    cutoff = cutoff_dt.isoformat()
    normalized_targets = sorted(
        (_target_record(target) for target in targets),
        key=lambda item: (
            item["target_date"],
            item["market"],
            item["ticker"],
        ),
    )
    if not normalized_targets:
        raise ValueError("At least one sector PIT audit target is required.")

    benchmark_ids = sorted(
        {
            str(item).strip()
            for item in available_benchmark_identities
            if str(item).strip()
        }
    )
    benchmark_set = set(benchmark_ids)

    target_keys = {
        (target["ticker"], target["market"])
        for target in normalized_targets
    }
    known_evidences: list[dict[str, Any]] = []
    for evidence in evidences:
        validate_sector_membership_evidence(evidence)
        if (evidence["ticker"], evidence["market"]) not in target_keys:
            continue
        known_at = _aware_utc(str(evidence["known_at"]), "known_at")
        if known_at <= cutoff_dt:
            known_evidences.append(evidence)

    known_evidences.sort(
        key=lambda item: (
            str(item["market"]),
            str(item["ticker"]),
            str(item["evidence_hash"]),
        )
    )

    results: list[dict[str, Any]] = []
    for target in normalized_targets:
        candidates = [
            evidence
            for evidence in known_evidences
            if evidence["ticker"] == target["ticker"]
            and evidence["market"] == target["market"]
        ]
        assessments = [
            assess_sector_membership_evidence(
                evidence,
                target_date=target["target_date"],
                decision_cutoff=cutoff,
                available_benchmark_identities=benchmark_set,
            )
            for evidence in candidates
        ]
        status, reason, selected = _status_from_assessments(assessments)

        results.append(
            {
                **target,
                "status": status,
                "reason": reason,
                "production_safe": status == "PIT_ELIGIBLE",
                "selected_evidence_id": (
                    selected.get("evidence_id") if selected else None
                ),
                "selected_evidence_hash": (
                    selected.get("evidence_hash") if selected else None
                ),
                "sector_group": (
                    selected.get("sector_group") if selected else None
                ),
                "benchmark_name": (
                    selected.get("benchmark_name") if selected else None
                ),
                "benchmark_identity": (
                    selected.get("benchmark_identity") if selected else None
                ),
                "known_candidate_count": len(candidates),
            }
        )

    status_counts = {
        status: sum(1 for result in results if result["status"] == status)
        for status in _STATUS_ORDER
    }
    pit_count = status_counts["PIT_ELIGIBLE"]
    if pit_count == len(results):
        coverage_status = "AVAILABLE"
    elif pit_count > 0:
        coverage_status = "PARTIAL"
    else:
        coverage_status = "UNAVAILABLE"

    identity_payload = {
        "contract_version": SECTOR_PIT_COVERAGE_AUDIT_CONTRACT_VERSION,
        "decision_cutoff": cutoff,
        "targets": normalized_targets,
        "known_evidence_hashes": [
            str(item["evidence_hash"]) for item in known_evidences
        ],
        "available_benchmark_identities": benchmark_ids,
        "results": results,
        "summary": {
            "status": coverage_status,
            "total_targets": len(results),
            "pit_eligible": pit_count,
            "status_counts": status_counts,
        },
        "governance": {
            "claim_scope": "COVERAGE_AUDIT_ONLY",
            "static_current_promotable": False,
            "production_decision_approved": False,
            "strategy_input_approved": False,
            "scanner_input_approved": False,
            "risk_gate_input_approved": False,
            "holdings_plan_input_approved": False,
            "network_access": False,
        },
    }
    audit_hash = content_hash(identity_payload)
    return {
        **identity_payload,
        "audit_id": f"SECPITAUD-{audit_hash[:16]}",
        "audit_hash": audit_hash,
    }
