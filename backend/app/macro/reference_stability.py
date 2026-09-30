from __future__ import annotations

from bisect import bisect_left, bisect_right
from decimal import Decimal, ROUND_FLOOR
from typing import Any

from app.macro.calibration_candidate import RATE_SPIKE_FEATURE_IDS
from app.macro.calibration_research import (
    validate_development_artifact,
    validate_distribution_research_artifact,
    validate_research_protocol,
)
from app.macro.eligibility_reconstruction import (
    validate_eligibility_reconstruction,
)
from app.macro.identity import content_hash


REFERENCE_STABILITY_CONTRACT_VERSION = (
    "VN_NEXT6B_S4_2B15_REFERENCE_STABILITY_V1"
)
REFERENCE_STABILITY_FAMILY_CONTRACT_VERSION = (
    "VN_NEXT6B_S4_2B15_REFERENCE_STABILITY_FAMILY_V1"
)
REFERENCE_TRANSITION_CONTRACT_VERSION = (
    "VN_NEXT6B_S4_2B15_REFERENCE_TRANSITION_V1"
)
REFERENCE_STATE_CONTRACT_VERSION = (
    "VN_NEXT6B_S4_2B15_REFERENCE_STATE_V1"
)
OBSERVED_ORDER_STATISTIC_METHOD = "OBSERVED_ORDER_STATISTIC_FLOOR_V1"

TAIL_METHOD = "EXPANDING_POSITIVE_TAIL_FRACTION"
MAD_METHOD = "EXPANDING_ROBUST_MAD"
EPT_METHOD = "EMPIRICAL_POSITIVE_TAIL"
STABILITY_METHODS = (TAIL_METHOD, MAD_METHOD)

_FEATURE_ORDER = {
    feature_id: index for index, feature_id in enumerate(RATE_SPIKE_FEATURE_IDS)
}
_METHOD_ORDER = {TAIL_METHOD: 0, MAD_METHOD: 1}
_FEATURE_LABELS = {
    "delta_bp_1obs": "1obs",
    "delta_bp_5obs": "5obs",
    "delta_bp_10obs": "10obs",
}
_METHOD_LABELS = {
    TAIL_METHOD: "TAIL",
    MAD_METHOD: "MAD",
}


def _decimal(value: Any) -> Decimal:
    result = Decimal(str(value))
    if not result.is_finite():
        raise ValueError("Reference stability metric must be finite.")
    return result


def _decimal_or_none(value: Any) -> Decimal | None:
    if value is None:
        return None
    return _decimal(value)


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


def ecdf_sup_drift_for_append(
    prior_values: list[Decimal],
    added_value: Decimal,
) -> Decimal | None:
    """Exact sup drift between an empirical CDF and the CDF after one append.

    The supremum is evaluated over observed support only. For an old reference
    of size n and appended value y:
      x < y  -> difference = F_n(x)/(n+1)
      x >= y -> difference = (1-F_n(x))/(n+1)
    Therefore the exact maximum depends only on the old counts strictly below
    and less-than-or-equal to y. No synthetic x-grid is introduced.
    """
    if not prior_values:
        return None
    ordered = sorted(prior_values)
    n = len(ordered)
    left_count = bisect_left(ordered, added_value)
    le_count = bisect_right(ordered, added_value)
    denominator = Decimal(n * (n + 1))
    left = Decimal(left_count) / denominator
    right = Decimal(n - le_count) / denominator
    return max(left, right)


def _reference_prefix_hashes(
    *,
    feature_id: str,
    rows: list[dict[str, Any]],
) -> list[str]:
    hashes = [
        content_hash(
            {
                "feature_id": feature_id,
                "reference_mode": "EXPANDING_STRICTLY_PRIOR",
                "prior_count": 0,
                "previous_prefix_hash": None,
                "added_row_hash": None,
                "added_value": None,
            }
        )
    ]
    for index, row in enumerate(rows, start=1):
        hashes.append(
            content_hash(
                {
                    "feature_id": feature_id,
                    "reference_mode": "EXPANDING_STRICTLY_PRIOR",
                    "prior_count": index,
                    "previous_prefix_hash": hashes[-1],
                    "added_row_hash": str(row["row_hash"]),
                    "added_value": str(row["value"]),
                }
            )
        )
    return hashes


def _observed_summary(values: list[Decimal | None]) -> dict[str, Any]:
    concrete = sorted(value for value in values if value is not None)
    null_count = len(values) - len(concrete)
    if not concrete:
        return {
            "status": "NO_VALUES",
            "quantile_method": OBSERVED_ORDER_STATISTIC_METHOD,
            "count": 0,
            "null_count": null_count,
            "unique_value_count": 0,
            "min": None,
            "q1": None,
            "median": None,
            "q3": None,
            "max": None,
        }
    last = len(concrete) - 1

    def observed(percentile: Decimal) -> Decimal:
        index = int(
            (Decimal(last) * percentile).to_integral_value(
                rounding=ROUND_FLOOR
            )
        )
        return concrete[index]

    return {
        "status": "DESCRIPTIVE_ONLY",
        "quantile_method": OBSERVED_ORDER_STATISTIC_METHOD,
        "count": len(concrete),
        "null_count": null_count,
        "unique_value_count": len(set(concrete)),
        "min": _decimal_text(concrete[0]),
        "q1": _decimal_text(observed(Decimal("0.25"))),
        "median": _decimal_text(observed(Decimal("0.50"))),
        "q3": _decimal_text(observed(Decimal("0.75"))),
        "max": _decimal_text(concrete[-1]),
    }


def _research_rows(
    research: dict[str, Any],
    feature_id: str,
) -> list[dict[str, Any]]:
    rows = [
        dict(row)
        for row in research["feature_results"][feature_id]["expanding"]["rows"]
    ]
    rows.sort(key=lambda item: int(item["prior_count"]))
    expected = list(range(len(rows)))
    actual = [int(row["prior_count"]) for row in rows]
    if actual != expected:
        raise ValueError(
            "Reference stability requires contiguous expanding prior counts."
        )
    return rows


def _tail_transitions(
    *,
    feature_id: str,
    rows: list[dict[str, Any]],
    prefix_hashes: list[str],
) -> list[dict[str, Any]]:
    values = [_decimal(row["value"]) for row in rows]
    transitions: list[dict[str, Any]] = []
    max_prior = len(rows) - 1
    for prior_before in range(1, max_prior):
        prior_after = prior_before + 1
        prior_values = values[:prior_before]
        added_value = values[prior_before]
        drift = ecdf_sup_drift_for_append(prior_values, added_value)
        if drift is None:
            raise ValueError("TAIL transition requires non-empty prior.")

        payload = {
            "contract_version": REFERENCE_TRANSITION_CONTRACT_VERSION,
            "feature_id": feature_id,
            "method": TAIL_METHOD,
            "reference_mode": "EXPANDING_STRICTLY_PRIOR",
            "prior_count_before": prior_before,
            "prior_count_after": prior_after,
            "reference_hash_before": prefix_hashes[prior_before],
            "reference_hash_after": prefix_hashes[prior_after],
            "added_observation_row_hash": str(rows[prior_before]["row_hash"]),
            "added_observation_value": str(rows[prior_before]["value"]),
            "ecdf_sup_drift": _decimal_text(drift),
            "empirical_probability_resolution_before": _fraction(
                1, prior_before
            ),
            "empirical_probability_resolution_after": _fraction(
                1, prior_after
            ),
            "invented_x_grid_points": 0,
            "current_observation_excluded": True,
            "selection_status": "NOT_SELECTED",
        }
        transition_hash = content_hash(payload)
        transitions.append(
            {
                **payload,
                "transition_id": f"RATESTABTR-{transition_hash[:16]}",
                "transition_hash": transition_hash,
            }
        )
    return transitions


def _mad_states(
    *,
    feature_id: str,
    rows: list[dict[str, Any]],
    prefix_hashes: list[str],
) -> dict[int, dict[str, Any]]:
    states: dict[int, dict[str, Any]] = {}
    for row in rows:
        prior_count = int(row["prior_count"])
        if prior_count <= 0:
            continue
        prior_median = _decimal_or_none(row.get("prior_median"))
        prior_mad = _decimal_or_none(row.get("prior_mad"))
        method_computable = (
            prior_median is not None
            and prior_mad is not None
            and prior_mad > 0
            and row.get("robust_deviation_mad") is not None
        )
        states[prior_count] = {
            "prior_count": prior_count,
            "reference_hash": prefix_hashes[prior_count],
            "prior_median": _decimal_text(prior_median),
            "prior_mad": _decimal_text(prior_mad),
            "method_computable": method_computable,
            "method_reason": (
                None if method_computable else str(row.get("reason") or "UNAVAILABLE")
            ),
        }
    return states


def _mad_transitions(
    *,
    feature_id: str,
    rows: list[dict[str, Any]],
    prefix_hashes: list[str],
) -> tuple[list[dict[str, Any]], dict[int, dict[str, Any]]]:
    states = _mad_states(
        feature_id=feature_id,
        rows=rows,
        prefix_hashes=prefix_hashes,
    )
    transitions: list[dict[str, Any]] = []
    max_prior = len(rows) - 1
    for prior_before in range(1, max_prior):
        prior_after = prior_before + 1
        before = states[prior_before]
        after = states[prior_after]
        before_median = _decimal_or_none(before["prior_median"])
        after_median = _decimal_or_none(after["prior_median"])
        before_mad = _decimal_or_none(before["prior_mad"])
        after_mad = _decimal_or_none(after["prior_mad"])

        median_change = (
            abs(after_median - before_median)
            if before_median is not None and after_median is not None
            else None
        )
        mad_change = (
            abs(after_mad - before_mad)
            if before_mad is not None and after_mad is not None
            else None
        )
        relative_mad_change = None
        relative_status = "UNAVAILABLE"
        if before_mad is not None and after_mad is not None:
            if before_mad == 0:
                relative_status = "NON_COMPUTABLE_ZERO_SCALE"
            else:
                relative_mad_change = mad_change / abs(before_mad)
                relative_status = "AVAILABLE"

        payload = {
            "contract_version": REFERENCE_TRANSITION_CONTRACT_VERSION,
            "feature_id": feature_id,
            "method": MAD_METHOD,
            "reference_mode": "EXPANDING_STRICTLY_PRIOR",
            "prior_count_before": prior_before,
            "prior_count_after": prior_after,
            "reference_hash_before": prefix_hashes[prior_before],
            "reference_hash_after": prefix_hashes[prior_after],
            "added_observation_row_hash": str(rows[prior_before]["row_hash"]),
            "added_observation_value": str(rows[prior_before]["value"]),
            "median_before": before["prior_median"],
            "median_after": after["prior_median"],
            "mad_before": before["prior_mad"],
            "mad_after": after["prior_mad"],
            "absolute_median_change": _decimal_text(median_change),
            "absolute_mad_change": _decimal_text(mad_change),
            "relative_mad_change": _decimal_text(relative_mad_change),
            "relative_mad_change_status": relative_status,
            "method_computable_before": bool(before["method_computable"]),
            "method_computable_after": bool(after["method_computable"]),
            "current_observation_excluded": True,
            "selection_status": "NOT_SELECTED",
        }
        transition_hash = content_hash(payload)
        transitions.append(
            {
                **payload,
                "transition_id": f"RATESTABTR-{transition_hash[:16]}",
                "transition_hash": transition_hash,
            }
        )
    return transitions, states


def _incoming_transition_map(
    transitions: list[dict[str, Any]],
) -> dict[int, dict[str, Any]]:
    return {
        int(item["prior_count_after"]): item
        for item in transitions
    }


def _tail_reference_state(
    *,
    feature_id: str,
    prior_count: int,
    prefix_hashes: list[str],
    incoming: dict[int, dict[str, Any]],
) -> dict[str, Any]:
    if prior_count <= 0 or prior_count >= len(prefix_hashes):
        return {
            "contract_version": REFERENCE_STATE_CONTRACT_VERSION,
            "feature_id": feature_id,
            "method": TAIL_METHOD,
            "prior_count": prior_count,
            "status": "OUT_OF_RANGE",
            "reference_hash": None,
            "method_computable": False,
            "ecdf_sup_drift_from_previous": None,
            "empirical_probability_resolution": None,
        }
    transition = incoming.get(prior_count)
    return {
        "contract_version": REFERENCE_STATE_CONTRACT_VERSION,
        "feature_id": feature_id,
        "method": TAIL_METHOD,
        "prior_count": prior_count,
        "status": "OBSERVED_REFERENCE_STATE",
        "reference_hash": prefix_hashes[prior_count],
        "method_computable": True,
        "ecdf_sup_drift_from_previous": (
            transition["ecdf_sup_drift"] if transition else None
        ),
        "empirical_probability_resolution": _fraction(1, prior_count),
    }


def _mad_reference_state(
    *,
    feature_id: str,
    prior_count: int,
    states: dict[int, dict[str, Any]],
    incoming: dict[int, dict[str, Any]],
) -> dict[str, Any]:
    state = states.get(prior_count)
    if state is None:
        return {
            "contract_version": REFERENCE_STATE_CONTRACT_VERSION,
            "feature_id": feature_id,
            "method": MAD_METHOD,
            "prior_count": prior_count,
            "status": "OUT_OF_RANGE",
            "reference_hash": None,
            "method_computable": False,
            "prior_median": None,
            "prior_mad": None,
            "absolute_median_change_from_previous": None,
            "absolute_mad_change_from_previous": None,
            "relative_mad_change_from_previous": None,
            "relative_mad_change_status": "UNAVAILABLE",
        }
    transition = incoming.get(prior_count)
    return {
        "contract_version": REFERENCE_STATE_CONTRACT_VERSION,
        "feature_id": feature_id,
        "method": MAD_METHOD,
        "prior_count": prior_count,
        "status": "OBSERVED_REFERENCE_STATE",
        "reference_hash": state["reference_hash"],
        "method_computable": bool(state["method_computable"]),
        "method_reason": state["method_reason"],
        "prior_median": state["prior_median"],
        "prior_mad": state["prior_mad"],
        "absolute_median_change_from_previous": (
            transition["absolute_median_change"] if transition else None
        ),
        "absolute_mad_change_from_previous": (
            transition["absolute_mad_change"] if transition else None
        ),
        "relative_mad_change_from_previous": (
            transition["relative_mad_change"] if transition else None
        ),
        "relative_mad_change_status": (
            transition["relative_mad_change_status"]
            if transition
            else "UNAVAILABLE"
        ),
    }


def _family_support_points(
    reconstruction: dict[str, Any],
    *,
    feature_id: str,
    method: str,
) -> list[dict[str, Any]]:
    for family in reconstruction["families"]:
        if (
            str(family["feature_id"]) == feature_id
            and str(family["method"]) == method
        ):
            curve = family["observed_support_counterfactual"]
            return [dict(point) for point in curve.get("points", [])]
    raise ValueError("B.1 reconstruction is missing a required family.")


def _tail_family(
    *,
    feature_id: str,
    rows: list[dict[str, Any]],
    prefix_hashes: list[str],
    reconstruction: dict[str, Any],
) -> dict[str, Any]:
    transitions = _tail_transitions(
        feature_id=feature_id,
        rows=rows,
        prefix_hashes=prefix_hashes,
    )
    incoming = _incoming_transition_map(transitions)
    support_points = _family_support_points(
        reconstruction,
        feature_id=feature_id,
        method=TAIL_METHOD,
    )

    overlay: list[dict[str, Any]] = []
    supports = [int(point["minimum_prior_observations"]) for point in support_points]
    for index, point in enumerate(support_points):
        support = int(point["minimum_prior_observations"])
        overlay.append(
            {
                "minimum_prior_observations": support,
                "previous_b1_support_point": (
                    supports[index - 1] if index > 0 else None
                ),
                "next_b1_support_point": (
                    supports[index + 1]
                    if index + 1 < len(supports)
                    else None
                ),
                "b1_point_hash": content_hash(point),
                "reference_state": _tail_reference_state(
                    feature_id=feature_id,
                    prior_count=support,
                    prefix_hashes=prefix_hashes,
                    incoming=incoming,
                ),
            }
        )

    first_usable = next(
        (
            int(row["prior_count"])
            for row in rows
            if row.get("positive_tail_fraction_ge") is not None
        ),
        None,
    )
    summary = {
        "ecdf_sup_drift": _observed_summary(
            [_decimal_or_none(item["ecdf_sup_drift"]) for item in transitions]
        ),
        "empirical_probability_resolution_after": _observed_summary(
            [
                _decimal_or_none(
                    item["empirical_probability_resolution_after"]
                )
                for item in transitions
            ]
        ),
    }
    payload = {
        "contract_version": REFERENCE_STABILITY_FAMILY_CONTRACT_VERSION,
        "feature_id": feature_id,
        "method": TAIL_METHOD,
        "reference_support_applicable": True,
        "reference_mode": "EXPANDING_STRICTLY_PRIOR",
        "first_usable_prior_count": first_usable,
        "transition_count": len(transitions),
        "transition_hashes": [
            str(item["transition_hash"]) for item in transitions
        ],
        "transitions": transitions,
        "descriptive_summaries": summary,
        "b1_support_overlay": overlay,
        "b1_support_point_count": len(overlay),
        "analysis_status": "COMPLETE",
        "reference_adequacy_criterion": "UNSET",
        "minimum_prior_observations": None,
        "selection_status": "NOT_SELECTED",
        "recommended_support": None,
    }
    family_hash = content_hash(payload)
    return {
        **payload,
        "family_id": f"RATESTABFAM-{family_hash[:16]}",
        "family_hash": family_hash,
    }


def _mad_family(
    *,
    feature_id: str,
    rows: list[dict[str, Any]],
    prefix_hashes: list[str],
    reconstruction: dict[str, Any],
) -> dict[str, Any]:
    transitions, states = _mad_transitions(
        feature_id=feature_id,
        rows=rows,
        prefix_hashes=prefix_hashes,
    )
    incoming = _incoming_transition_map(transitions)
    support_points = _family_support_points(
        reconstruction,
        feature_id=feature_id,
        method=MAD_METHOD,
    )

    overlay: list[dict[str, Any]] = []
    supports = [int(point["minimum_prior_observations"]) for point in support_points]
    for index, point in enumerate(support_points):
        support = int(point["minimum_prior_observations"])
        overlay.append(
            {
                "minimum_prior_observations": support,
                "previous_b1_support_point": (
                    supports[index - 1] if index > 0 else None
                ),
                "next_b1_support_point": (
                    supports[index + 1]
                    if index + 1 < len(supports)
                    else None
                ),
                "b1_point_hash": content_hash(point),
                "reference_state": _mad_reference_state(
                    feature_id=feature_id,
                    prior_count=support,
                    states=states,
                    incoming=incoming,
                ),
            }
        )

    first_usable = next(
        (
            prior_count
            for prior_count in sorted(states)
            if bool(states[prior_count]["method_computable"])
        ),
        None,
    )
    summary = {
        "absolute_median_change": _observed_summary(
            [
                _decimal_or_none(item["absolute_median_change"])
                for item in transitions
            ]
        ),
        "absolute_mad_change": _observed_summary(
            [
                _decimal_or_none(item["absolute_mad_change"])
                for item in transitions
            ]
        ),
        "relative_mad_change": _observed_summary(
            [
                _decimal_or_none(item["relative_mad_change"])
                for item in transitions
            ]
        ),
    }
    payload = {
        "contract_version": REFERENCE_STABILITY_FAMILY_CONTRACT_VERSION,
        "feature_id": feature_id,
        "method": MAD_METHOD,
        "reference_support_applicable": True,
        "reference_mode": "EXPANDING_STRICTLY_PRIOR",
        "first_usable_prior_count": first_usable,
        "transition_count": len(transitions),
        "transition_hashes": [
            str(item["transition_hash"]) for item in transitions
        ],
        "transitions": transitions,
        "descriptive_summaries": summary,
        "b1_support_overlay": overlay,
        "b1_support_point_count": len(overlay),
        "analysis_status": "COMPLETE",
        "reference_adequacy_criterion": "UNSET",
        "minimum_prior_observations": None,
        "selection_status": "NOT_SELECTED",
        "recommended_support": None,
    }
    family_hash = content_hash(payload)
    return {
        **payload,
        "family_id": f"RATESTABFAM-{family_hash[:16]}",
        "family_hash": family_hash,
    }


def _ept_exclusions() -> list[dict[str, Any]]:
    return [
        {
            "feature_id": feature_id,
            "method": EPT_METHOD,
            "reference_support_applicable": False,
            "exclusion_reason": (
                "METHOD_DOES_NOT_USE_EXPANDING_REFERENCE_DISTRIBUTION"
            ),
            "selection_status": "NOT_APPLICABLE",
        }
        for feature_id in RATE_SPIKE_FEATURE_IDS
    ]


def _common_review_points(
    *,
    families: list[dict[str, Any]],
    research: dict[str, Any],
) -> list[dict[str, Any]]:
    family_by_key = {
        (str(family["feature_id"]), str(family["method"])): family
        for family in families
    }
    union = sorted(
        {
            int(item["minimum_prior_observations"])
            for family in families
            for item in family["b1_support_overlay"]
        }
    )
    result: list[dict[str, Any]] = []

    state_resources: dict[
        tuple[str, str],
        tuple[list[str], dict[int, dict[str, Any]], dict[int, dict[str, Any]]],
    ] = {}
    for feature_id in RATE_SPIKE_FEATURE_IDS:
        rows = _research_rows(research, feature_id)
        prefixes = _reference_prefix_hashes(
            feature_id=feature_id,
            rows=rows,
        )
        tail_family = family_by_key[(feature_id, TAIL_METHOD)]
        tail_incoming = _incoming_transition_map(tail_family["transitions"])
        mad_family = family_by_key[(feature_id, MAD_METHOD)]
        mad_incoming = _incoming_transition_map(mad_family["transitions"])
        mad_states = _mad_states(
            feature_id=feature_id,
            rows=rows,
            prefix_hashes=prefixes,
        )
        state_resources[(feature_id, TAIL_METHOD)] = (
            prefixes,
            tail_incoming,
            {},
        )
        state_resources[(feature_id, MAD_METHOD)] = (
            prefixes,
            mad_incoming,
            mad_states,
        )

    for support in union:
        family_states: list[dict[str, Any]] = []
        for feature_id in RATE_SPIKE_FEATURE_IDS:
            prefixes, incoming, _ = state_resources[
                (feature_id, TAIL_METHOD)
            ]
            family_states.append(
                _tail_reference_state(
                    feature_id=feature_id,
                    prior_count=support,
                    prefix_hashes=prefixes,
                    incoming=incoming,
                )
            )
            prefixes, incoming, mad_states = state_resources[
                (feature_id, MAD_METHOD)
            ]
            family_states.append(
                _mad_reference_state(
                    feature_id=feature_id,
                    prior_count=support,
                    states=mad_states,
                    incoming=incoming,
                )
            )

        result.append(
            {
                "minimum_prior_observations": support,
                "family_states": family_states,
                "family_state_payload_hash": content_hash(family_states),
                "selection_status": "NOT_SELECTED",
            }
        )
    return result


def build_reference_stability_evidence(
    *,
    development_dataset: dict[str, Any],
    protocol: dict[str, Any],
    research: dict[str, Any],
    reconstruction: dict[str, Any],
    source_main_sha: str | None = None,
) -> dict[str, Any]:
    development_state = validate_development_artifact(development_dataset)
    protocol_state = validate_research_protocol(
        protocol,
        development_dataset_hash=development_state["dataset_hash"],
    )
    research_state = validate_distribution_research_artifact(
        research,
        development_dataset_hash=development_state["dataset_hash"],
        protocol_hash=protocol_state["protocol_hash"],
    )
    reconstruction_state = validate_eligibility_reconstruction(
        reconstruction
    )

    source = reconstruction["source"]
    if source["development_dataset_hash"] != development_state["dataset_hash"]:
        raise ValueError("B.1 reconstruction Development hash mismatch.")
    if source["protocol_hash"] != protocol_state["protocol_hash"]:
        raise ValueError("B.1 reconstruction Protocol hash mismatch.")
    if source["research_hash"] != research_state["research_hash"]:
        raise ValueError("B.1 reconstruction Research hash mismatch.")
    if int(reconstruction["counts"]["raw_candidate_count"]) != int(
        reconstruction_state["raw_candidate_count"]
    ):
        raise ValueError("B.1 reconstruction raw candidate count mismatch.")

    families: list[dict[str, Any]] = []
    for feature_id in RATE_SPIKE_FEATURE_IDS:
        rows = _research_rows(research, feature_id)
        prefixes = _reference_prefix_hashes(
            feature_id=feature_id,
            rows=rows,
        )
        families.append(
            _tail_family(
                feature_id=feature_id,
                rows=rows,
                prefix_hashes=prefixes,
                reconstruction=reconstruction,
            )
        )
        families.append(
            _mad_family(
                feature_id=feature_id,
                rows=rows,
                prefix_hashes=prefixes,
                reconstruction=reconstruction,
            )
        )

    families.sort(
        key=lambda item: (
            _FEATURE_ORDER[str(item["feature_id"])],
            _METHOD_ORDER[str(item["method"])],
        )
    )
    ept_exclusions = _ept_exclusions()
    common_review_points = _common_review_points(
        families=families,
        research=research,
    )

    policy_state = {
        "reference_adequacy": "UNDEFINED",
        "reference_adequacy_criterion": "UNSET",
        "minimum_prior_observations": None,
        "recommended_support": None,
        "selection_status": "NOT_SELECTED",
        "eligibility_policy_status": "UNDEFINED",
        "admissibility_policy_status": "UNDEFINED",
        "final_candidate_status": "NOT_SELECTED",
        "ready_for_holdout": False,
        "rate_spike_state": "UNCALIBRATED",
    }
    source_payload = {
        "development_dataset_hash": development_state["dataset_hash"],
        "protocol_hash": protocol_state["protocol_hash"],
        "research_hash": research_state["research_hash"],
        "reconstruction_id": reconstruction["reconstruction_id"],
        "reconstruction_hash": reconstruction["reconstruction_hash"],
        "raw_candidate_count": int(
            reconstruction["counts"]["raw_candidate_count"]
        ),
        "raw_candidate_hashes_hash": reconstruction[
            "raw_candidate_hashes_hash"
        ],
        "source_main_sha": source_main_sha or "UNSPECIFIED",
    }
    counts = {
        "tail_family_count": sum(
            family["method"] == TAIL_METHOD for family in families
        ),
        "mad_family_count": sum(
            family["method"] == MAD_METHOD for family in families
        ),
        "ept_excluded_family_count": len(ept_exclusions),
        "reference_family_count": len(families),
        "transition_count": sum(
            int(family["transition_count"]) for family in families
        ),
        "b1_overlay_point_count": sum(
            int(family["b1_support_point_count"]) for family in families
        ),
        "common_review_point_count": len(common_review_points),
    }
    identity_payload = {
        "contract_version": REFERENCE_STABILITY_CONTRACT_VERSION,
        "source": source_payload,
        "reference_contract": {
            "reference_mode": "EXPANDING_STRICTLY_PRIOR",
            "current_observation_excluded": True,
            "tail_metric": "ECDF_SUP_DRIFT",
            "tail_evaluation_support": "OBSERVED_VALUES_UNION_ONLY",
            "tail_invented_x_grid_points": 0,
            "mad_metrics": [
                "ABSOLUTE_MEDIAN_CHANGE",
                "ABSOLUTE_MAD_CHANGE",
                "RELATIVE_MAD_CHANGE",
            ],
            "weighted_stability_score": None,
            "quantile_method": OBSERVED_ORDER_STATISTIC_METHOD,
        },
        "counts": counts,
        "family_payload_hash": content_hash(families),
        "ept_exclusion_payload_hash": content_hash(ept_exclusions),
        "common_review_payload_hash": content_hash(common_review_points),
        "policy_state": policy_state,
        "holdout_locked": True,
        "holdout_accessed": False,
        "network_requests": 0,
        "macro_db_writes": 0,
        "production_impact": "NONE",
    }
    stability_hash = content_hash(identity_payload)
    return {
        **identity_payload,
        "stability_id": f"RATESTAB-{stability_hash[:16]}",
        "stability_hash": stability_hash,
        "analysis_status": "COMPLETE",
        "families": families,
        "ept_exclusions": ept_exclusions,
        "common_support_review_points": common_review_points,
    }


def _transition_payload(transition: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in transition.items()
        if key not in {"transition_id", "transition_hash"}
    }


def _family_payload(family: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in family.items()
        if key not in {"family_id", "family_hash"}
    }


def validate_reference_stability_evidence(
    artifact: dict[str, Any],
) -> dict[str, Any]:
    if artifact.get("contract_version") != REFERENCE_STABILITY_CONTRACT_VERSION:
        raise ValueError("Unsupported reference stability contract.")
    if artifact.get("analysis_status") != "COMPLETE":
        raise ValueError("Reference stability analysis must be COMPLETE.")
    if artifact.get("holdout_locked") is not True:
        raise ValueError("Reference stability must keep Holdout locked.")
    if artifact.get("holdout_accessed") is not False:
        raise ValueError("Reference stability must not access Holdout.")
    if int(artifact.get("network_requests") or 0) != 0:
        raise ValueError("Reference stability must not use network.")
    if int(artifact.get("macro_db_writes") or 0) != 0:
        raise ValueError("Reference stability must not write Macro DB.")
    if artifact.get("production_impact") != "NONE":
        raise ValueError("Reference stability must have no Production impact.")

    policy = artifact.get("policy_state") or {}
    expected_policy = {
        "reference_adequacy": "UNDEFINED",
        "reference_adequacy_criterion": "UNSET",
        "minimum_prior_observations": None,
        "recommended_support": None,
        "selection_status": "NOT_SELECTED",
        "eligibility_policy_status": "UNDEFINED",
        "admissibility_policy_status": "UNDEFINED",
        "final_candidate_status": "NOT_SELECTED",
        "ready_for_holdout": False,
        "rate_spike_state": "UNCALIBRATED",
    }
    if policy != expected_policy:
        raise ValueError("Reference stability policy state changed unexpectedly.")

    families = list(artifact.get("families") or [])
    ept_exclusions = list(artifact.get("ept_exclusions") or [])
    common_points = list(artifact.get("common_support_review_points") or [])
    counts = artifact.get("counts") or {}

    if len(families) != 6:
        raise ValueError("Reference stability requires six TAIL/MAD families.")
    if len(ept_exclusions) != 3:
        raise ValueError("Reference stability requires three EPT exclusions.")
    if int(counts.get("tail_family_count") or 0) != 3:
        raise ValueError("Reference stability requires three TAIL families.")
    if int(counts.get("mad_family_count") or 0) != 3:
        raise ValueError("Reference stability requires three MAD families.")
    if int(counts.get("ept_excluded_family_count") or 0) != 3:
        raise ValueError("EPT exclusion accounting mismatch.")

    expected_pairs = {
        (feature_id, method)
        for feature_id in RATE_SPIKE_FEATURE_IDS
        for method in STABILITY_METHODS
    }
    actual_pairs = {
        (str(family["feature_id"]), str(family["method"]))
        for family in families
    }
    if actual_pairs != expected_pairs:
        raise ValueError("Reference stability family set mismatch.")

    transition_count = 0
    overlay_count = 0
    for family in families:
        if family.get("reference_support_applicable") is not True:
            raise ValueError("TAIL/MAD reference support must be applicable.")
        if family.get("analysis_status") != "COMPLETE":
            raise ValueError("Reference stability family must be COMPLETE.")
        if family.get("reference_adequacy_criterion") != "UNSET":
            raise ValueError("Reference adequacy criterion must stay UNSET.")
        if family.get("minimum_prior_observations") is not None:
            raise ValueError("Minimum prior observations must stay unset.")
        if family.get("recommended_support") is not None:
            raise ValueError("Reference stability cannot recommend support.")
        if family.get("selection_status") != "NOT_SELECTED":
            raise ValueError("Reference stability cannot select support.")

        transitions = list(family.get("transitions") or [])
        transition_count += len(transitions)
        if int(family.get("transition_count") or 0) != len(transitions):
            raise ValueError("Reference stability transition count mismatch.")
        expected_hashes = []
        for transition in transitions:
            if transition.get("current_observation_excluded") is not True:
                raise ValueError("Current observation leaked into reference.")
            if transition.get("selection_status") != "NOT_SELECTED":
                raise ValueError("Transition cannot select support.")
            if (
                family["method"] == TAIL_METHOD
                and int(transition.get("invented_x_grid_points") or 0) != 0
            ):
                raise ValueError("TAIL stability cannot invent an x-grid.")
            transition_hash = content_hash(
                _transition_payload(transition)
            )
            if transition.get("transition_hash") != transition_hash:
                raise ValueError("Reference transition hash mismatch.")
            if transition.get("transition_id") != (
                f"RATESTABTR-{transition_hash[:16]}"
            ):
                raise ValueError("Reference transition id mismatch.")
            expected_hashes.append(transition_hash)
        if family.get("transition_hashes") != expected_hashes:
            raise ValueError("Reference transition hash list mismatch.")

        overlay = list(family.get("b1_support_overlay") or [])
        overlay_count += len(overlay)
        if int(family.get("b1_support_point_count") or 0) != len(overlay):
            raise ValueError("B.1 support overlay count mismatch.")

        family_hash = content_hash(_family_payload(family))
        if family.get("family_hash") != family_hash:
            raise ValueError("Reference stability family hash mismatch.")
        if family.get("family_id") != f"RATESTABFAM-{family_hash[:16]}":
            raise ValueError("Reference stability family id mismatch.")

    if int(counts.get("transition_count") or 0) != transition_count:
        raise ValueError("Reference stability total transition count mismatch.")
    if int(counts.get("b1_overlay_point_count") or 0) != overlay_count:
        raise ValueError("B.1 overlay total count mismatch.")
    if int(counts.get("common_review_point_count") or 0) != len(
        common_points
    ):
        raise ValueError("Common review point count mismatch.")

    supports = [
        int(point["minimum_prior_observations"])
        for point in common_points
    ]
    if supports != sorted(set(supports)):
        raise ValueError("Common review points must be unique and sorted.")
    for point in common_points:
        states = list(point.get("family_states") or [])
        if len(states) != 6:
            raise ValueError("Common review point requires six family states.")
        if point.get("family_state_payload_hash") != content_hash(states):
            raise ValueError("Common review family state hash mismatch.")
        if point.get("selection_status") != "NOT_SELECTED":
            raise ValueError("Common review point cannot select support.")

    if artifact.get("family_payload_hash") != content_hash(families):
        raise ValueError("Reference stability family payload hash mismatch.")
    if artifact.get("ept_exclusion_payload_hash") != content_hash(
        ept_exclusions
    ):
        raise ValueError("EPT exclusion payload hash mismatch.")
    if artifact.get("common_review_payload_hash") != content_hash(
        common_points
    ):
        raise ValueError("Common review payload hash mismatch.")

    identity_payload = {
        key: artifact[key]
        for key in (
            "contract_version",
            "source",
            "reference_contract",
            "counts",
            "family_payload_hash",
            "ept_exclusion_payload_hash",
            "common_review_payload_hash",
            "policy_state",
            "holdout_locked",
            "holdout_accessed",
            "network_requests",
            "macro_db_writes",
            "production_impact",
        )
    }
    expected_hash = content_hash(identity_payload)
    if artifact.get("stability_hash") != expected_hash:
        raise ValueError("Reference stability artifact hash mismatch.")
    if artifact.get("stability_id") != f"RATESTAB-{expected_hash[:16]}":
        raise ValueError("Reference stability artifact id mismatch.")

    return {
        "stability_hash": expected_hash,
        "tail_family_count": 3,
        "mad_family_count": 3,
        "ept_excluded_family_count": 3,
        "common_review_point_count": len(common_points),
        "holdout_accessed": False,
        "ready_for_holdout": False,
    }


def render_reference_stability_text(
    artifact: dict[str, Any],
) -> str:
    validate_reference_stability_evidence(artifact)

    headers = (
        "Feat",
        "Meth",
        "Transitions",
        "First usable prior",
        "Stability evidence",
    )
    rows: list[tuple[str, ...]] = []
    for family in artifact["families"]:
        rows.append(
            (
                _FEATURE_LABELS[str(family["feature_id"])],
                _METHOD_LABELS[str(family["method"])],
                str(family["transition_count"]),
                str(family["first_usable_prior_count"]),
                str(family["analysis_status"]),
            )
        )
    widths = [
        max(len(headers[index]), *(len(row[index]) for row in rows))
        for index in range(len(headers))
    ]

    def format_row(row: tuple[str, ...]) -> str:
        return "  ".join(
            value.ljust(widths[index])
            for index, value in enumerate(row)
        )

    counts = artifact["counts"]
    policy = artifact["policy_state"]
    lines = [
        "NEXT-6B-S4.2-B.1.5 REFERENCE STABILITY EVIDENCE",
        "",
        (
            "Source Reconstruction : "
            f"{artifact['source']['reconstruction_id']} "
            f"({artifact['source']['reconstruction_hash']})"
        ),
        (
            "Raw Candidate Universe: "
            f"{artifact['source']['raw_candidate_count']}"
        ),
        "",
        (
            "Reference Families    : "
            f"TAIL {counts['tail_family_count']} / "
            f"MAD {counts['mad_family_count']} / "
            f"EPT Excluded {counts['ept_excluded_family_count']}"
        ),
        "",
        format_row(headers),
        format_row(tuple("-" * width for width in widths)),
    ]
    lines.extend(format_row(row) for row in rows)
    lines.extend(
        [
            "",
            (
                "Common Review Points / B.1 Overlay : "
                f"{counts['common_review_point_count']} / "
                f"{counts['b1_overlay_point_count']}"
            ),
            (
                "Reference Adequacy / Minimum Prior Observations / "
                "Recommended Support : "
                f"{policy['reference_adequacy']} / "
                f"{policy['minimum_prior_observations']} / "
                f"{policy['recommended_support']}"
            ),
            (
                "Holdout locked / accessed / ready : "
                f"{artifact['holdout_locked']} / "
                f"{artifact['holdout_accessed']} / "
                f"{policy['ready_for_holdout']}"
            ),
            (
                "RATE_SPIKE / Network / Macro DB writes / Production : "
                f"{policy['rate_spike_state']} / "
                f"{artifact['network_requests']} / "
                f"{artifact['macro_db_writes']} / "
                f"{artifact['production_impact']}"
            ),
            "",
            (
                "Stability status: COMPLETE "
                "(no adequacy criterion or support selected)"
            ),
        ]
    )
    return "\n".join(lines)
