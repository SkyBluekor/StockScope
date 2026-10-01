from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from statistics import median
from typing import Any

from app.macro.distribution import median_absolute_deviation
from app.macro.identity import content_hash
from app.macro.reference_stability import (
    MAD_METHOD,
    TAIL_METHOD,
    ecdf_sup_drift_for_append,
    validate_reference_stability_evidence,
)


REFERENCE_DIAGNOSTIC_CONTRACT_VERSION = (
    "VN_NEXT6B_S4_2B16_REFERENCE_DIAGNOSTIC_V1"
)
REFERENCE_DIAGNOSTIC_AS_OF = "AS_OF"
REFERENCE_DIAGNOSTIC_RETROSPECTIVE = "RETROSPECTIVE"
REFERENCE_DIAGNOSTIC_CONTEXT_PROJECTION_VERSION = (
    "VN_NEXT6B_S4_2B16_REFERENCE_DIAGNOSTIC_CONTEXT_V1"
)

RATE_SPIKE_FEATURE_IDS = (
    "delta_bp_1obs",
    "delta_bp_5obs",
    "delta_bp_10obs",
)
_FEATURE_DISTANCE = {
    "delta_bp_1obs": 1,
    "delta_bp_5obs": 5,
    "delta_bp_10obs": 10,
}

AS_OF_ALLOWED_USAGE = (
    "REFERENCE_CONTEXT",
    "HISTORICAL_EVALUATION",
    "SHADOW_RESEARCH",
    "USER_INFORMATION",
)
RETROSPECTIVE_ALLOWED_USAGE = (
    "HISTORICAL_REVIEW",
    "SHADOW_RESEARCH",
)
PROHIBITED_CONSUMERS = (
    "SHOCK_CALIBRATION",
    "SHOCK_DETECTION_APPROVAL",
    "STRATEGY_INPUT",
    "MARKET_REGIME_OVERRIDE",
    "RISK_GATE",
    "ORDER_DECISION",
    "PRODUCTION_POLICY",
    "AUTO_BUY",
    "AUTO_SELL",
)

_BASE_LIMITATIONS = (
    "INFERENCE_UNRESOLVED",
    "NUMERIC_ADEQUACY_NOT_DEFINED",
)


def _aware_utc(value: str, field: str) -> datetime:
    text = str(value or "").strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(
            f"{field} must be a timezone-aware ISO-8601 datetime."
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(
            f"{field} must be a timezone-aware ISO-8601 datetime."
        )
    return parsed.astimezone(timezone.utc)


def _decimal_or_none(value: Any) -> Decimal | None:
    if value in {None, "", "."}:
        return None
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    if not result.is_finite():
        return None
    return result


def _decimal_text(value: Decimal | None) -> str | None:
    if value is None:
        return None
    text = format(value.normalize(), "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return "0" if text in {"", "-0"} else text


def _fraction(numerator: int, denominator: int) -> str | None:
    if denominator <= 0:
        return None
    return _decimal_text(Decimal(numerator) / Decimal(denominator))


def _row_ref(row: dict[str, Any]) -> str:
    return str(
        row.get("normalized_hash")
        or row.get("id")
        or row.get("observation_key")
        or ""
    )


def _select_as_of_rows(
    observations: list[dict[str, Any]] | tuple[dict[str, Any], ...],
    *,
    decision_cutoff: str,
) -> tuple[str, list[dict[str, Any]]]:
    cutoff = _aware_utc(decision_cutoff, "decision_cutoff")
    eligible: list[dict[str, Any]] = []

    for original in observations:
        row = dict(original)
        available_at = row.get("available_at")
        if available_at is None:
            raise ValueError(
                "AS-OF reference diagnostic requires available_at lineage."
            )
        if _aware_utc(str(available_at), "available_at") <= cutoff:
            eligible.append(row)

    chosen: dict[str, dict[str, Any]] = {}
    for row in eligible:
        observation_key = str(row.get("observation_key") or "").strip()
        observation_date = str(row.get("observation_date") or "").strip()
        if not observation_key or not observation_date:
            raise ValueError(
                "AS-OF reference diagnostic requires observation identity."
            )

        previous = chosen.get(observation_key)
        if previous is None:
            chosen[observation_key] = row
            continue

        rank = (
            _aware_utc(str(row["available_at"]), "available_at"),
            int(row.get("revision_no") or 0),
        )
        previous_rank = (
            _aware_utc(str(previous["available_at"]), "available_at"),
            int(previous.get("revision_no") or 0),
        )
        if rank > previous_rank:
            chosen[observation_key] = row

    rows = sorted(
        chosen.values(),
        key=lambda item: (
            str(item["observation_date"]),
            _aware_utc(str(item["available_at"]), "available_at"),
            int(item.get("revision_no") or 0),
        ),
    )

    dates = [str(row["observation_date"]) for row in rows]
    if len(dates) != len(set(dates)):
        raise ValueError(
            "AS-OF reference diagnostic requires unique observation dates."
        )

    return cutoff.isoformat(), rows


def _derived_feature_series(
    rows: list[dict[str, Any]],
    *,
    feature_id: str,
) -> tuple[list[dict[str, Any]], int]:
    distance = _FEATURE_DISTANCE[feature_id]
    values = [_decimal_or_none(row.get("normalized_value")) for row in rows]
    series: list[dict[str, Any]] = []
    unavailable = 0

    for index in range(distance, len(rows)):
        current = values[index]
        baseline = values[index - distance]
        if current is None or baseline is None:
            unavailable += 1
            continue

        value = (current - baseline) * Decimal("100")
        current_row = rows[index]
        baseline_row = rows[index - distance]
        source = {
            "feature_id": feature_id,
            "observation_date": str(current_row["observation_date"]),
            "current_observation_ref": _row_ref(current_row),
            "baseline_observation_ref": _row_ref(baseline_row),
            "observation_distance": distance,
            "value": _decimal_text(value),
        }
        row_hash = content_hash(source)
        series.append(
            {
                **source,
                "value_decimal": value,
                "row_hash": row_hash,
            }
        )

    return series, unavailable


def _reference_values(
    series: list[dict[str, Any]],
    *,
    current_observation_date: str | None,
) -> list[dict[str, Any]]:
    if current_observation_date is None:
        return []
    return [
        item
        for item in series
        if str(item["observation_date"]) < current_observation_date
    ]


def _tail_diagnostic(
    *,
    feature_id: str,
    reference_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    values = [item["value_decimal"] for item in reference_rows]
    reference_count = len(values)
    previous_values = values[:-1]

    if reference_count == 0:
        status = "INSUFFICIENT_HISTORY"
        reason = "NO_STRICTLY_PRIOR_FEATURE_VALUES"
        drift = None
    elif reference_count == 1:
        status = "PARTIAL"
        reason = "NO_PREVIOUS_REFERENCE_STATE"
        drift = None
    else:
        status = "AVAILABLE"
        reason = None
        drift = ecdf_sup_drift_for_append(
            previous_values,
            values[-1],
        )

    reference_payload = {
        "feature_id": feature_id,
        "reference_mode": "EXPANDING_STRICTLY_PRIOR",
        "reference_count": reference_count,
        "row_hashes": [str(item["row_hash"]) for item in reference_rows],
    }
    return {
        "method": TAIL_METHOD,
        "status": status,
        "reason": reason,
        "reference_count": reference_count,
        "previous_reference_count": max(0, reference_count - 1),
        "reference_hash": (
            content_hash(reference_payload) if reference_count else None
        ),
        "ecdf_sup_drift_from_previous": _decimal_text(drift),
        "ecdf_sup_drift_unit": "ABSOLUTE_PROBABILITY_DIFFERENCE",
        "empirical_probability_resolution": _fraction(1, reference_count),
        "current_observation_excluded": True,
        "adequacy_pass": None,
        "threshold": None,
    }


def _mad_diagnostic(
    *,
    feature_id: str,
    reference_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    values = [item["value_decimal"] for item in reference_rows]
    reference_count = len(values)

    if reference_count == 0:
        return {
            "method": MAD_METHOD,
            "status": "INSUFFICIENT_HISTORY",
            "reason": "NO_STRICTLY_PRIOR_FEATURE_VALUES",
            "reference_count": 0,
            "previous_reference_count": 0,
            "reference_hash": None,
            "median": None,
            "mad": None,
            "scale_status": "UNAVAILABLE",
            "absolute_median_change_from_previous": None,
            "absolute_mad_change_from_previous": None,
            "normalized_median_shift_from_previous": None,
            "normalized_median_shift_status": "UNAVAILABLE",
            "relative_mad_change_from_previous": None,
            "relative_mad_change_status": "UNAVAILABLE",
            "value_unit": "BASIS_POINT",
            "current_observation_excluded": True,
            "adequacy_pass": None,
            "threshold": None,
        }

    current_median = median(values)
    current_mad = median_absolute_deviation(values)
    previous_values = values[:-1]
    previous_median = median(previous_values) if previous_values else None
    previous_mad = (
        median_absolute_deviation(previous_values)
        if previous_values
        else None
    )

    median_change = (
        abs(current_median - previous_median)
        if previous_median is not None
        else None
    )
    mad_change = (
        abs(current_mad - previous_mad)
        if current_mad is not None and previous_mad is not None
        else None
    )

    if previous_mad is None:
        normalized_median = None
        relative_mad = None
        normalized_status = "UNAVAILABLE"
        relative_status = "UNAVAILABLE"
    elif previous_mad == 0:
        normalized_median = None
        relative_mad = None
        normalized_status = "NON_COMPUTABLE_ZERO_SCALE"
        relative_status = "NON_COMPUTABLE_ZERO_SCALE"
    else:
        normalized_median = (
            median_change / abs(previous_mad)
            if median_change is not None
            else None
        )
        relative_mad = (
            mad_change / abs(previous_mad)
            if mad_change is not None
            else None
        )
        normalized_status = (
            "AVAILABLE" if normalized_median is not None else "UNAVAILABLE"
        )
        relative_status = (
            "AVAILABLE" if relative_mad is not None else "UNAVAILABLE"
        )

    scale_status = (
        "NON_COMPUTABLE_ZERO_SCALE"
        if current_mad == 0
        else "AVAILABLE"
    )

    if reference_count == 1:
        status = "PARTIAL"
        reason = "NO_PREVIOUS_REFERENCE_STATE"
    elif (
        normalized_status == "NON_COMPUTABLE_ZERO_SCALE"
        or relative_status == "NON_COMPUTABLE_ZERO_SCALE"
    ):
        status = "PARTIAL"
        reason = "PREVIOUS_MAD_ZERO"
    else:
        status = "AVAILABLE"
        reason = None

    reference_payload = {
        "feature_id": feature_id,
        "reference_mode": "EXPANDING_STRICTLY_PRIOR",
        "reference_count": reference_count,
        "row_hashes": [str(item["row_hash"]) for item in reference_rows],
    }
    return {
        "method": MAD_METHOD,
        "status": status,
        "reason": reason,
        "reference_count": reference_count,
        "previous_reference_count": max(0, reference_count - 1),
        "reference_hash": content_hash(reference_payload),
        "median": _decimal_text(current_median),
        "mad": _decimal_text(current_mad),
        "scale_status": scale_status,
        "absolute_median_change_from_previous": _decimal_text(
            median_change
        ),
        "absolute_mad_change_from_previous": _decimal_text(mad_change),
        "normalized_median_shift_from_previous": _decimal_text(
            normalized_median
        ),
        "normalized_median_shift_status": normalized_status,
        "relative_mad_change_from_previous": _decimal_text(relative_mad),
        "relative_mad_change_status": relative_status,
        "value_unit": "BASIS_POINT",
        "current_observation_excluded": True,
        "adequacy_pass": None,
        "threshold": None,
    }


def _governance(
    *,
    allowed_usage: tuple[str, ...],
    point_in_time_eligible: bool,
) -> dict[str, Any]:
    return {
        "claim_scope": "DESCRIPTIVE_ONLY",
        "allowed_usage": list(allowed_usage),
        "prohibited_consumers": list(PROHIBITED_CONSUMERS),
        "point_in_time_eligible": point_in_time_eligible,
        "numeric_policy_defined": False,
        "reference_adequacy": "UNRESOLVED",
        "minimum_prior_observations": None,
        "recommended_support": None,
        "rate_spike_state": "UNCALIBRATED",
        "production_decision_approved": False,
    }


def build_as_of_reference_diagnostic(
    observations: list[dict[str, Any]] | tuple[dict[str, Any], ...],
    *,
    decision_cutoff: str,
    series_id: str = "US_10Y_CONSTANT_MATURITY_YIELD",
) -> dict[str, Any]:
    cutoff, rows = _select_as_of_rows(
        observations,
        decision_cutoff=decision_cutoff,
    )
    current_observation_date = (
        str(rows[-1]["observation_date"]) if rows else None
    )

    horizons: list[dict[str, Any]] = []
    for feature_id in RATE_SPIKE_FEATURE_IDS:
        series, unavailable = _derived_feature_series(
            rows,
            feature_id=feature_id,
        )
        reference_rows = _reference_values(
            series,
            current_observation_date=current_observation_date,
        )
        current_feature = next(
            (
                item
                for item in reversed(series)
                if item["observation_date"] == current_observation_date
            ),
            None,
        )
        tail = _tail_diagnostic(
            feature_id=feature_id,
            reference_rows=reference_rows,
        )
        mad = _mad_diagnostic(
            feature_id=feature_id,
            reference_rows=reference_rows,
        )
        horizons.append(
            {
                "feature_id": feature_id,
                "observation_distance": _FEATURE_DISTANCE[feature_id],
                "current_feature_available": current_feature is not None,
                "current_feature_value": (
                    _decimal_text(current_feature["value_decimal"])
                    if current_feature is not None
                    else None
                ),
                "derived_feature_unavailable_count": unavailable,
                "reference_count": len(reference_rows),
                "tail": tail,
                "mad": mad,
            }
        )

    family_statuses = [
        component["status"]
        for horizon in horizons
        for component in (horizon["tail"], horizon["mad"])
    ]
    if not rows:
        status = "UNAVAILABLE"
    elif all(value == "AVAILABLE" for value in family_statuses):
        status = "AVAILABLE"
    else:
        status = "PARTIAL"

    limitations = list(_BASE_LIMITATIONS)
    if status != "AVAILABLE":
        limitations.append("REFERENCE_DIAGNOSTIC_PARTIAL")

    observation_refs = [
        {
            "observation_key": str(row["observation_key"]),
            "revision_no": int(row.get("revision_no") or 0),
            "observation_date": str(row["observation_date"]),
            "available_at": str(row["available_at"]),
            "normalized_hash": str(row.get("normalized_hash") or ""),
            "time_quality": str(row.get("time_quality") or ""),
        }
        for row in rows
    ]
    source = {
        "series_id": series_id,
        "decision_cutoff": cutoff,
        "eligible_observation_count": len(rows),
        "observation_refs": observation_refs,
        "observation_refs_hash": content_hash(observation_refs),
        "current_observation_date": current_observation_date,
    }
    governance = _governance(
        allowed_usage=AS_OF_ALLOWED_USAGE,
        point_in_time_eligible=True,
    )
    identity_payload = {
        "contract_version": REFERENCE_DIAGNOSTIC_CONTRACT_VERSION,
        "projection_mode": REFERENCE_DIAGNOSTIC_AS_OF,
        "status": status,
        "source": source,
        "horizons": horizons,
        "limitations": sorted(set(limitations)),
        "governance": governance,
    }
    diagnostic_hash = content_hash(identity_payload)
    result = {
        **identity_payload,
        "diagnostic_id": f"RATEDIAG-{diagnostic_hash[:16]}",
        "diagnostic_hash": diagnostic_hash,
    }
    validate_reference_diagnostic(result)
    return result


def build_retrospective_reference_diagnostic(
    stability: dict[str, Any],
) -> dict[str, Any]:
    validate_reference_stability_evidence(stability)

    families = {
        (str(family["feature_id"]), str(family["method"])): family
        for family in stability["families"]
    }
    horizons: list[dict[str, Any]] = []
    for feature_id in RATE_SPIKE_FEATURE_IDS:
        tail = families[(feature_id, TAIL_METHOD)]
        mad = families[(feature_id, MAD_METHOD)]
        horizons.append(
            {
                "feature_id": feature_id,
                "observation_distance": _FEATURE_DISTANCE[feature_id],
                "tail": {
                    "method": TAIL_METHOD,
                    "status": "AVAILABLE",
                    "transition_count": int(tail["transition_count"]),
                    "descriptive_summaries": tail["descriptive_summaries"],
                    "adequacy_pass": None,
                    "threshold": None,
                },
                "mad": {
                    "method": MAD_METHOD,
                    "status": "AVAILABLE",
                    "transition_count": int(mad["transition_count"]),
                    "descriptive_summaries": mad["descriptive_summaries"],
                    "adequacy_pass": None,
                    "threshold": None,
                },
            }
        )

    source = {
        "stability_id": str(stability["stability_id"]),
        "stability_hash": str(stability["stability_hash"]),
        "reference_mode": "EXPANDING_STRICTLY_PRIOR",
    }
    governance = _governance(
        allowed_usage=RETROSPECTIVE_ALLOWED_USAGE,
        point_in_time_eligible=False,
    )
    limitations = sorted(
        {
            *_BASE_LIMITATIONS,
            "RETROSPECTIVE_RESEARCH_ONLY",
            "NOT_POINT_IN_TIME",
            "NOT_POLICY_INPUT",
        }
    )
    identity_payload = {
        "contract_version": REFERENCE_DIAGNOSTIC_CONTRACT_VERSION,
        "projection_mode": REFERENCE_DIAGNOSTIC_RETROSPECTIVE,
        "status": "AVAILABLE",
        "source": source,
        "horizons": horizons,
        "limitations": limitations,
        "governance": governance,
    }
    diagnostic_hash = content_hash(identity_payload)
    result = {
        **identity_payload,
        "diagnostic_id": f"RATEDIAG-{diagnostic_hash[:16]}",
        "diagnostic_hash": diagnostic_hash,
    }
    validate_reference_diagnostic(result)
    return result


def project_reference_diagnostic_for_context(
    diagnostic: dict[str, Any],
) -> dict[str, Any]:
    """Build a bounded MacroContext-safe projection of an AS-OF diagnostic.

    Full observation refs remain in the diagnostic identity and are represented
    here only by count/hash lineage. Retrospective research projections are
    rejected so MacroContext cannot accidentally expose non-PIT evidence.
    """
    validate_reference_diagnostic(diagnostic)
    if diagnostic.get("projection_mode") != REFERENCE_DIAGNOSTIC_AS_OF:
        raise ValueError(
            "MacroContext only accepts AS-OF reference diagnostics."
        )

    source = diagnostic["source"]
    source_projection = {
        "series_id": source["series_id"],
        "decision_cutoff": source["decision_cutoff"],
        "eligible_observation_count": source[
            "eligible_observation_count"
        ],
        "observation_refs_hash": source["observation_refs_hash"],
        "current_observation_date": source["current_observation_date"],
    }
    payload = {
        "projection_contract_version": (
            REFERENCE_DIAGNOSTIC_CONTEXT_PROJECTION_VERSION
        ),
        "diagnostic_contract_version": diagnostic["contract_version"],
        "diagnostic_id": diagnostic["diagnostic_id"],
        "diagnostic_hash": diagnostic["diagnostic_hash"],
        "projection_mode": diagnostic["projection_mode"],
        "status": diagnostic["status"],
        "source": source_projection,
        "horizons": diagnostic["horizons"],
        "limitations": diagnostic["limitations"],
        "governance": diagnostic["governance"],
    }
    projection_hash = content_hash(payload)
    return {
        **payload,
        "context_projection_hash": projection_hash,
    }


def validate_reference_diagnostic(
    diagnostic: dict[str, Any],
) -> dict[str, Any]:
    if (
        diagnostic.get("contract_version")
        != REFERENCE_DIAGNOSTIC_CONTRACT_VERSION
    ):
        raise ValueError("Unsupported reference diagnostic contract.")

    mode = str(diagnostic.get("projection_mode") or "")
    if mode not in {
        REFERENCE_DIAGNOSTIC_AS_OF,
        REFERENCE_DIAGNOSTIC_RETROSPECTIVE,
    }:
        raise ValueError("Unsupported reference diagnostic projection mode.")

    horizons = list(diagnostic.get("horizons") or [])
    if [item.get("feature_id") for item in horizons] != list(
        RATE_SPIKE_FEATURE_IDS
    ):
        raise ValueError(
            "Reference diagnostic must disclose all three rate horizons."
        )

    governance = diagnostic.get("governance") or {}
    if governance.get("claim_scope") != "DESCRIPTIVE_ONLY":
        raise ValueError("Reference diagnostic claim scope changed.")
    if governance.get("numeric_policy_defined") is not False:
        raise ValueError("Reference diagnostic cannot define numeric policy.")
    if governance.get("reference_adequacy") != "UNRESOLVED":
        raise ValueError("Reference adequacy must remain unresolved.")
    if governance.get("minimum_prior_observations") is not None:
        raise ValueError("Reference diagnostic cannot select minimum N.")
    if governance.get("recommended_support") is not None:
        raise ValueError("Reference diagnostic cannot recommend support.")
    if governance.get("rate_spike_state") != "UNCALIBRATED":
        raise ValueError("Reference diagnostic cannot calibrate RATE_SPIKE.")
    if governance.get("production_decision_approved") is not False:
        raise ValueError("Reference diagnostic cannot approve Production.")

    prohibited = set(governance.get("prohibited_consumers") or [])
    if not set(PROHIBITED_CONSUMERS).issubset(prohibited):
        raise ValueError("Reference diagnostic consumer restrictions changed.")

    if mode == REFERENCE_DIAGNOSTIC_AS_OF:
        if governance.get("point_in_time_eligible") is not True:
            raise ValueError("AS-OF diagnostic must be point-in-time eligible.")
        for horizon in horizons:
            for component_name in ("tail", "mad"):
                component = horizon.get(component_name) or {}
                if component.get("current_observation_excluded") is not True:
                    raise ValueError(
                        "AS-OF diagnostic leaked the current observation."
                    )
                if component.get("adequacy_pass") is not None:
                    raise ValueError(
                        "AS-OF diagnostic cannot produce adequacy pass/fail."
                    )
                if component.get("threshold") is not None:
                    raise ValueError(
                        "AS-OF diagnostic cannot define a threshold."
                    )
    else:
        if governance.get("point_in_time_eligible") is not False:
            raise ValueError(
                "Retrospective diagnostic cannot be point-in-time eligible."
            )
        limitations = set(diagnostic.get("limitations") or [])
        required = {
            "RETROSPECTIVE_RESEARCH_ONLY",
            "NOT_POINT_IN_TIME",
            "NOT_POLICY_INPUT",
        }
        if not required.issubset(limitations):
            raise ValueError(
                "Retrospective diagnostic restrictions are incomplete."
            )

    identity_payload = {
        key: diagnostic[key]
        for key in (
            "contract_version",
            "projection_mode",
            "status",
            "source",
            "horizons",
            "limitations",
            "governance",
        )
    }
    expected_hash = content_hash(identity_payload)
    if diagnostic.get("diagnostic_hash") != expected_hash:
        raise ValueError("Reference diagnostic hash mismatch.")
    if diagnostic.get("diagnostic_id") != (
        f"RATEDIAG-{expected_hash[:16]}"
    ):
        raise ValueError("Reference diagnostic id mismatch.")

    return {
        "diagnostic_hash": expected_hash,
        "projection_mode": mode,
        "status": diagnostic["status"],
        "reference_adequacy": "UNRESOLVED",
        "rate_spike_state": "UNCALIBRATED",
        "production_decision_approved": False,
    }
