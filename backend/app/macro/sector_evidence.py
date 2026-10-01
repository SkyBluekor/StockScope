from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from app.macro.identity import content_hash


SECTOR_MEMBERSHIP_EVIDENCE_CONTRACT_VERSION = (
    "VN_NEXT6C_S2_SECTOR_MEMBERSHIP_EVIDENCE_V1"
)

TEMPORAL_POINT_IN_TIME = "POINT_IN_TIME"
TEMPORAL_STATIC_CURRENT = "STATIC_CURRENT"
TEMPORAL_UNKNOWN = "UNKNOWN"

_ALLOWED_TEMPORAL_STATUS = {
    TEMPORAL_POINT_IN_TIME,
    TEMPORAL_STATIC_CURRENT,
    TEMPORAL_UNKNOWN,
}
_ALLOWED_MARKETS = {"KOSPI", "KOSDAQ"}


def _market(value: str) -> str:
    market = str(value or "").strip().upper()
    if market not in _ALLOWED_MARKETS:
        raise ValueError("market must be KOSPI or KOSDAQ.")
    return market


def _date_text(value: str | date | None, field: str) -> str | None:
    if value is None:
        return None
    if isinstance(value, date):
        parsed = value
    else:
        raw = str(value or "").strip()
        if not raw:
            return None
        if len(raw) == 8 and raw.isdigit():
            parsed = date(int(raw[:4]), int(raw[4:6]), int(raw[6:8]))
        else:
            try:
                parsed = date.fromisoformat(raw)
            except ValueError as exc:
                raise ValueError(
                    f"{field} must be YYYY-MM-DD or YYYYMMDD."
                ) from exc
    return parsed.isoformat()


def _aware_utc(value: str, field: str) -> str:
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
    return parsed.astimezone(timezone.utc).isoformat()


def _hash_text(value: str, field: str) -> str:
    text = str(value or "").strip().lower()
    if len(text) != 64 or any(ch not in "0123456789abcdef" for ch in text):
        raise ValueError(f"{field} must be a 64-character hexadecimal hash.")
    return text


def build_sector_membership_evidence(
    *,
    ticker: str,
    market: str,
    sector_group: str | None,
    benchmark_name: str | None,
    benchmark_identity: str | None,
    effective_from: str | date,
    effective_to: str | date | None,
    known_at: str,
    source: str,
    source_revision: str,
    source_hash: str,
    temporal_status: str,
    mapping_method: str,
    historical_membership_proven: bool,
    source_time_proven: bool,
    limitations: list[str] | tuple[str, ...] = (),
) -> dict[str, Any]:
    """Build immutable stock-to-sector membership evidence.

    Membership effective dates and the time this evidence became knowable are
    deliberately separate. STATIC_CURRENT evidence is recorded but never
    upgraded to POINT_IN_TIME.
    """

    ticker_key = str(ticker or "").strip().upper()
    if not ticker_key:
        raise ValueError("ticker is required.")

    temporal = str(temporal_status or "").strip().upper()
    if temporal not in _ALLOWED_TEMPORAL_STATUS:
        raise ValueError("Unsupported sector temporal_status.")

    effective_start = _date_text(effective_from, "effective_from")
    effective_end = _date_text(effective_to, "effective_to")
    if effective_start is None:
        raise ValueError("effective_from is required.")
    if effective_end is not None and effective_end < effective_start:
        raise ValueError("effective_to cannot be earlier than effective_from.")

    known_at_utc = _aware_utc(known_at, "known_at")
    source_name = str(source or "").strip()
    revision = str(source_revision or "").strip()
    method = str(mapping_method or "").strip()
    if not source_name:
        raise ValueError("source is required.")
    if not revision:
        raise ValueError("source_revision is required.")
    if not method:
        raise ValueError("mapping_method is required.")

    sector = str(sector_group or "").strip() or None
    benchmark = str(benchmark_name or "").strip() or None
    benchmark_id = str(benchmark_identity or "").strip() or None

    normalized_limitations = sorted(
        {str(item).strip() for item in limitations if str(item).strip()}
    )
    if temporal == TEMPORAL_STATIC_CURRENT:
        normalized_limitations = sorted(
            {*normalized_limitations, "STATIC_CURRENT_NOT_HISTORICAL_PIT"}
        )
    if not historical_membership_proven:
        normalized_limitations = sorted(
            {*normalized_limitations, "HISTORICAL_MEMBERSHIP_NOT_PROVEN"}
        )
    if not source_time_proven:
        normalized_limitations = sorted(
            {*normalized_limitations, "SOURCE_TIME_NOT_PROVEN"}
        )

    payload = {
        "contract_version": SECTOR_MEMBERSHIP_EVIDENCE_CONTRACT_VERSION,
        "ticker": ticker_key,
        "market": _market(market),
        "sector_group": sector,
        "benchmark_name": benchmark,
        "benchmark_identity": benchmark_id,
        "effective_from": effective_start,
        "effective_to": effective_end,
        "known_at": known_at_utc,
        "source": source_name,
        "source_revision": revision,
        "source_hash": _hash_text(source_hash, "source_hash"),
        "temporal_status": temporal,
        "mapping_method": method,
        "historical_membership_proven": bool(historical_membership_proven),
        "source_time_proven": bool(source_time_proven),
        "limitations": normalized_limitations,
    }
    evidence_hash = content_hash(payload)
    result = {
        **payload,
        "evidence_id": f"SECPIT-{evidence_hash[:16]}",
        "evidence_hash": evidence_hash,
    }
    validate_sector_membership_evidence(result)
    return result


def validate_sector_membership_evidence(
    evidence: dict[str, Any],
) -> dict[str, Any]:
    if (
        evidence.get("contract_version")
        != SECTOR_MEMBERSHIP_EVIDENCE_CONTRACT_VERSION
    ):
        raise ValueError("Unsupported sector membership evidence contract.")

    temporal = str(evidence.get("temporal_status") or "")
    if temporal not in _ALLOWED_TEMPORAL_STATUS:
        raise ValueError("Unsupported sector temporal_status.")

    effective_start = _date_text(
        evidence.get("effective_from"),
        "effective_from",
    )
    effective_end = _date_text(evidence.get("effective_to"), "effective_to")
    if effective_start is None:
        raise ValueError("effective_from is required.")
    if effective_end is not None and effective_end < effective_start:
        raise ValueError("effective_to cannot be earlier than effective_from.")

    _aware_utc(str(evidence.get("known_at") or ""), "known_at")
    _hash_text(str(evidence.get("source_hash") or ""), "source_hash")

    if temporal == TEMPORAL_STATIC_CURRENT and evidence.get(
        "historical_membership_proven"
    ):
        raise ValueError(
            "STATIC_CURRENT evidence cannot claim historical membership proof."
        )

    identity_payload = {
        key: evidence[key]
        for key in (
            "contract_version",
            "ticker",
            "market",
            "sector_group",
            "benchmark_name",
            "benchmark_identity",
            "effective_from",
            "effective_to",
            "known_at",
            "source",
            "source_revision",
            "source_hash",
            "temporal_status",
            "mapping_method",
            "historical_membership_proven",
            "source_time_proven",
            "limitations",
        )
    }
    expected_hash = content_hash(identity_payload)
    if evidence.get("evidence_hash") != expected_hash:
        raise ValueError("Sector membership evidence hash mismatch.")
    if evidence.get("evidence_id") != f"SECPIT-{expected_hash[:16]}":
        raise ValueError("Sector membership evidence id mismatch.")

    return {
        "evidence_hash": expected_hash,
        "temporal_status": temporal,
        "historical_membership_proven": bool(
            evidence.get("historical_membership_proven")
        ),
        "source_time_proven": bool(evidence.get("source_time_proven")),
    }


def assess_sector_membership_evidence(
    evidence: dict[str, Any],
    *,
    target_date: str | date,
    decision_cutoff: str,
    available_benchmark_identities: set[str] | frozenset[str],
) -> dict[str, Any]:
    """Assess one evidence record for PIT eligibility at a frozen cutoff."""

    validate_sector_membership_evidence(evidence)
    target = _date_text(target_date, "target_date")
    if target is None:
        raise ValueError("target_date is required.")

    cutoff = _aware_utc(decision_cutoff, "decision_cutoff")
    known_at = _aware_utc(str(evidence["known_at"]), "known_at")

    if known_at > cutoff:
        status = "FUTURE_KNOWN_EVIDENCE"
        reason = "MAPPING_NOT_KNOWN_BY_DECISION_CUTOFF"
    elif (
        target < str(evidence["effective_from"])
        or (
            evidence.get("effective_to") is not None
            and target > str(evidence["effective_to"])
        )
    ):
        status = "EFFECTIVE_RANGE_MISMATCH"
        reason = "TARGET_DATE_OUTSIDE_MEMBERSHIP_RANGE"
    elif evidence["temporal_status"] == TEMPORAL_STATIC_CURRENT:
        status = "STATIC_ONLY"
        reason = "STATIC_CURRENT_NOT_HISTORICAL_PIT"
    elif evidence["temporal_status"] != TEMPORAL_POINT_IN_TIME:
        status = "SOURCE_TIME_UNPROVEN"
        reason = "TEMPORAL_STATUS_NOT_POINT_IN_TIME"
    elif not evidence["historical_membership_proven"]:
        status = "SOURCE_TIME_UNPROVEN"
        reason = "HISTORICAL_MEMBERSHIP_NOT_PROVEN"
    elif not evidence["source_time_proven"]:
        status = "SOURCE_TIME_UNPROVEN"
        reason = "SOURCE_TIME_NOT_PROVEN"
    elif not evidence.get("benchmark_identity"):
        status = "BENCHMARK_UNRESOLVED"
        reason = "BENCHMARK_IDENTITY_MISSING"
    elif str(evidence["benchmark_identity"]) not in available_benchmark_identities:
        status = "BENCHMARK_UNRESOLVED"
        reason = "BENCHMARK_IDENTITY_NOT_AVAILABLE"
    else:
        status = "PIT_ELIGIBLE"
        reason = None

    return {
        "status": status,
        "reason": reason,
        "target_date": target,
        "decision_cutoff": cutoff,
        "evidence_id": evidence["evidence_id"],
        "evidence_hash": evidence["evidence_hash"],
        "ticker": evidence["ticker"],
        "market": evidence["market"],
        "sector_group": evidence["sector_group"],
        "benchmark_name": evidence["benchmark_name"],
        "benchmark_identity": evidence["benchmark_identity"],
        "temporal_status": evidence["temporal_status"],
        "production_safe": status == "PIT_ELIGIBLE",
    }
