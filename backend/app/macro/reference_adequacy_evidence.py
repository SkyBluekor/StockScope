from __future__ import annotations

from decimal import Decimal
from typing import Any

from app.macro.calibration_candidate import RATE_SPIKE_FEATURE_IDS
from app.macro.calibration_research import (
    validate_development_artifact,
    validate_distribution_research_artifact,
    validate_research_protocol,
)
from app.macro.eligibility_reconstruction import validate_eligibility_reconstruction
from app.macro.identity import content_hash
from app.macro.reference_adequacy_protocol import (
    MAD_FORWARD_ENVELOPE_BLOCKER,
    TAIL_FORWARD_ENVELOPE_BLOCKER,
    VALIDATION_SUFFIX_BLOCKER,
    validate_reference_adequacy_protocol,
)
from app.macro.reference_stability import (
    MAD_METHOD,
    TAIL_METHOD,
    _mad_states,
    _reference_prefix_hashes,
    _research_rows,
    validate_reference_stability_evidence,
)


REFERENCE_ADEQUACY_EVIDENCE_CONTRACT_VERSION = (
    "VN_NEXT6B_S4_2B16_R21_REFERENCE_ADEQUACY_EVIDENCE_V1"
)
REFERENCE_ADEQUACY_EVIDENCE_FAMILY_VERSION = (
    "VN_NEXT6B_S4_2B16_R21_REFERENCE_ADEQUACY_EVIDENCE_FAMILY_V1"
)
PATH_ENCODING_INTEGER = "RLE_INTEGER_V1"
PATH_ENCODING_DECIMAL = "RLE_DECIMAL_OR_NULL_V1"
TAIL_DENOMINATOR_RULE = "ANCHOR_N_TIMES_LATER_N"
CANDIDATE_SUPPORT_UNIVERSE = "B15_COMMON_SUPPORT_REVIEW_POINTS_ONLY"


def _decimal(value: Any) -> Decimal:
    result = Decimal(str(value))
    if not result.is_finite():
        raise ValueError("Reference adequacy evidence metric must be finite.")
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


def _rle_encode(values: list[Any]) -> list[list[Any]]:
    if not values:
        return []
    encoded: list[list[Any]] = []
    current = values[0]
    count = 1
    for value in values[1:]:
        if value == current:
            count += 1
            continue
        encoded.append([current, count])
        current = value
        count = 1
    encoded.append([current, count])
    return encoded


def _rle_decode(encoded: list[list[Any]]) -> list[Any]:
    result: list[Any] = []
    for item in encoded:
        if not isinstance(item, list) or len(item) != 2:
            raise ValueError("Invalid RLE evidence item.")
        value, count = item
        count_int = int(count)
        if count_int <= 0:
            raise ValueError("RLE evidence count must be positive.")
        result.extend([value] * count_int)
    return result


def _common_support_ns(stability: dict[str, Any]) -> list[int]:
    values = [
        int(item["minimum_prior_observations"])
        for item in stability["common_support_review_points"]
    ]
    if values != sorted(set(values)):
        raise ValueError("B.1.5 common support review points must be sorted unique.")
    if not values:
        raise ValueError("B.1.5 common support review points cannot be empty.")
    return values


def _prefix_cdf_count_rows(
    values: list[Decimal],
    *,
    max_prior: int,
) -> tuple[list[Decimal], list[tuple[int, ...]]]:
    if max_prior <= 0 or max_prior > len(values):
        raise ValueError("Invalid maximum prior count for ECDF evidence.")
    support = sorted(set(values))
    rank = {value: index for index, value in enumerate(support)}
    frequency = [0] * len(support)
    rows: list[tuple[int, ...]] = [tuple([0] * len(support))]

    for prior_count in range(1, max_prior + 1):
        frequency[rank[values[prior_count - 1]]] += 1
        running = 0
        cumulative: list[int] = []
        for count in frequency:
            running += count
            cumulative.append(running)
        rows.append(tuple(cumulative))
    return support, rows


def _tail_distance_numerator(
    *,
    anchor_n: int,
    later_n: int,
    anchor_counts: tuple[int, ...],
    later_counts: tuple[int, ...],
) -> int:
    if later_n <= anchor_n:
        raise ValueError("TAIL forward comparison must move after the anchor.")
    maximum = 0
    for anchor_count, later_count in zip(anchor_counts, later_counts):
        numerator = abs(anchor_n * later_count - later_n * anchor_count)
        if numerator > maximum:
            maximum = numerator
    return maximum


def _fraction_is_greater(
    left_numerator: int,
    left_denominator: int,
    right_numerator: int,
    right_denominator: int,
) -> bool:
    return left_numerator * right_denominator > (
        right_numerator * left_denominator
    )


def _tail_anchor_path(
    *,
    anchor_n: int,
    max_prior: int,
    prefix_counts: list[tuple[int, ...]],
) -> dict[str, Any]:
    numerators: list[int] = []
    best_numerator: int | None = None
    best_denominator: int | None = None
    best_later_n: int | None = None
    anchor_counts = prefix_counts[anchor_n]

    for later_n in range(anchor_n + 1, max_prior + 1):
        numerator = _tail_distance_numerator(
            anchor_n=anchor_n,
            later_n=later_n,
            anchor_counts=anchor_counts,
            later_counts=prefix_counts[later_n],
        )
        denominator = anchor_n * later_n
        numerators.append(numerator)
        if (
            best_numerator is None
            or _fraction_is_greater(
                numerator,
                denominator,
                best_numerator,
                int(best_denominator),
            )
        ):
            best_numerator = numerator
            best_denominator = denominator
            best_later_n = later_n

    return {
        "anchor_n": anchor_n,
        "first_later_n": anchor_n + 1 if numerators else None,
        "last_later_n": max_prior if numerators else None,
        "suffix_transition_count": len(numerators),
        "path_encoding": PATH_ENCODING_INTEGER,
        "distance_numerator_rle": _rle_encode(numerators),
        "distance_denominator_rule": TAIL_DENOMINATOR_RULE,
        "path_hash": content_hash(numerators),
        "max_distance": (
            None
            if best_numerator is None
            else {
                "numerator": best_numerator,
                "denominator": best_denominator,
                "later_n": best_later_n,
            }
        ),
        "selection_status": "NOT_SELECTED",
    }


def _max_decimal_path(
    values: list[str | None],
    *,
    first_later_n: int | None,
) -> dict[str, Any] | None:
    best: Decimal | None = None
    best_text: str | None = None
    best_n: int | None = None
    if first_later_n is None:
        return None
    for offset, value in enumerate(values):
        parsed = _decimal_or_none(value)
        if parsed is None:
            continue
        if best is None or parsed > best:
            best = parsed
            best_text = _decimal_text(parsed)
            best_n = first_later_n + offset
    if best is None:
        return None
    return {"value": best_text, "later_n": best_n}


def _mad_anchor_path(
    *,
    anchor_n: int,
    max_prior: int,
    states: dict[int, dict[str, Any]],
) -> dict[str, Any]:
    anchor = states.get(anchor_n)
    if anchor is None:
        raise ValueError("MAD anchor reference state is unavailable.")

    anchor_median = _decimal_or_none(anchor.get("prior_median"))
    anchor_mad = _decimal_or_none(anchor.get("prior_mad"))

    median_shifts: list[str | None] = []
    mad_shifts: list[str | None] = []
    relative_shifts: list[str | None] = []

    for later_n in range(anchor_n + 1, max_prior + 1):
        later = states.get(later_n)
        if later is None:
            raise ValueError("MAD later reference state is unavailable.")
        later_median = _decimal_or_none(later.get("prior_median"))
        later_mad = _decimal_or_none(later.get("prior_mad"))

        median_shift = (
            abs(later_median - anchor_median)
            if anchor_median is not None and later_median is not None
            else None
        )
        mad_shift = (
            abs(later_mad - anchor_mad)
            if anchor_mad is not None and later_mad is not None
            else None
        )
        relative_shift = None
        if anchor_mad is not None and anchor_mad != 0 and mad_shift is not None:
            relative_shift = mad_shift / abs(anchor_mad)

        median_shifts.append(_decimal_text(median_shift))
        mad_shifts.append(_decimal_text(mad_shift))
        relative_shifts.append(_decimal_text(relative_shift))

    first_later_n = anchor_n + 1 if median_shifts else None
    if anchor_mad is None:
        relative_status = "UNAVAILABLE_ANCHOR_SCALE"
    elif anchor_mad == 0:
        relative_status = "NON_COMPUTABLE_ZERO_SCALE"
    else:
        relative_status = "AVAILABLE_WHEN_LATER_SCALE_AVAILABLE"

    return {
        "anchor_n": anchor_n,
        "anchor_median": _decimal_text(anchor_median),
        "anchor_mad": _decimal_text(anchor_mad),
        "anchor_method_computable": bool(anchor.get("method_computable")),
        "first_later_n": first_later_n,
        "last_later_n": max_prior if median_shifts else None,
        "suffix_transition_count": len(median_shifts),
        "path_encoding": PATH_ENCODING_DECIMAL,
        "absolute_median_shift_rle": _rle_encode(median_shifts),
        "absolute_mad_shift_rle": _rle_encode(mad_shifts),
        "relative_mad_shift_rle": _rle_encode(relative_shifts),
        "relative_mad_shift_status": relative_status,
        "absolute_median_shift_path_hash": content_hash(median_shifts),
        "absolute_mad_shift_path_hash": content_hash(mad_shifts),
        "relative_mad_shift_path_hash": content_hash(relative_shifts),
        "max_absolute_median_shift": _max_decimal_path(
            median_shifts,
            first_later_n=first_later_n,
        ),
        "max_absolute_mad_shift": _max_decimal_path(
            mad_shifts,
            first_later_n=first_later_n,
        ),
        "max_relative_mad_shift": _max_decimal_path(
            relative_shifts,
            first_later_n=first_later_n,
        ),
        "selection_status": "NOT_SELECTED",
    }


def _reference_state_index(
    *,
    feature_id: str,
    prefix_hashes: list[str],
    max_prior: int,
) -> dict[str, Any]:
    hashes = [prefix_hashes[n] for n in range(1, max_prior + 1)]
    return {
        "feature_id": feature_id,
        "first_prior_count": 1,
        "last_prior_count": max_prior,
        "reference_hashes": hashes,
        "reference_hashes_hash": content_hash(hashes),
    }


def _tail_family(
    *,
    feature_id: str,
    rows: list[dict[str, Any]],
    common_ns: list[int],
) -> tuple[dict[str, Any], dict[str, Any]]:
    max_prior = max(int(row["prior_count"]) for row in rows)
    values = [_decimal(row["value"]) for row in rows]
    prefix_hashes = _reference_prefix_hashes(feature_id=feature_id, rows=rows)
    support, prefix_counts = _prefix_cdf_count_rows(
        values,
        max_prior=max_prior,
    )
    valid_ns = [n for n in common_ns if 1 <= n <= max_prior]
    if valid_ns != common_ns:
        raise ValueError("Common support N falls outside TAIL reference range.")

    anchors = [
        _tail_anchor_path(
            anchor_n=n,
            max_prior=max_prior,
            prefix_counts=prefix_counts,
        )
        for n in common_ns
    ]
    payload = {
        "contract_version": REFERENCE_ADEQUACY_EVIDENCE_FAMILY_VERSION,
        "feature_id": feature_id,
        "method": TAIL_METHOD,
        "reference_mode": "EXPANDING_STRICTLY_PRIOR",
        "candidate_support_universe": CANDIDATE_SUPPORT_UNIVERSE,
        "candidate_support_count": len(common_ns),
        "max_prior_count": max_prior,
        "evaluation_support": "OBSERVED_VALUES_UNION_ONLY",
        "invented_x_grid_points": 0,
        "observed_support_value_count": len(support),
        "path_metric": "EXACT_ECDF_SUP_DISTANCE",
        "path_encoding": PATH_ENCODING_INTEGER,
        "distance_denominator_rule": TAIL_DENOMINATOR_RULE,
        "anchors": anchors,
        "adequacy_tolerance": None,
        "adequacy_status": "UNRESOLVED",
        "selection_status": "NOT_SELECTED",
    }
    family_hash = content_hash(payload)
    return (
        {
            **payload,
            "family_id": f"RATEADEQEVIDFAM-{family_hash[:16]}",
            "family_hash": family_hash,
        },
        _reference_state_index(
            feature_id=feature_id,
            prefix_hashes=prefix_hashes,
            max_prior=max_prior,
        ),
    )


def _mad_family(
    *,
    feature_id: str,
    rows: list[dict[str, Any]],
    common_ns: list[int],
) -> dict[str, Any]:
    max_prior = max(int(row["prior_count"]) for row in rows)
    prefix_hashes = _reference_prefix_hashes(feature_id=feature_id, rows=rows)
    states = _mad_states(
        feature_id=feature_id,
        rows=rows,
        prefix_hashes=prefix_hashes,
    )
    valid_ns = [n for n in common_ns if n in states]
    if valid_ns != common_ns:
        raise ValueError("Common support N falls outside MAD reference range.")

    anchors = [
        _mad_anchor_path(
            anchor_n=n,
            max_prior=max_prior,
            states=states,
        )
        for n in common_ns
    ]
    payload = {
        "contract_version": REFERENCE_ADEQUACY_EVIDENCE_FAMILY_VERSION,
        "feature_id": feature_id,
        "method": MAD_METHOD,
        "reference_mode": "EXPANDING_STRICTLY_PRIOR",
        "candidate_support_universe": CANDIDATE_SUPPORT_UNIVERSE,
        "candidate_support_count": len(common_ns),
        "max_prior_count": max_prior,
        "path_metrics": [
            "ABSOLUTE_MEDIAN_SHIFT",
            "ABSOLUTE_MAD_SHIFT",
            "RELATIVE_MAD_SHIFT",
        ],
        "path_encoding": PATH_ENCODING_DECIMAL,
        "zero_scale_rule": "NON_COMPUTABLE_ZERO_SCALE",
        "null_to_zero_forbidden": True,
        "anchors": anchors,
        "adequacy_tolerances": {
            "absolute_median_shift": None,
            "absolute_mad_shift": None,
            "relative_mad_shift": None,
        },
        "weighted_stability_score": None,
        "adequacy_status": "UNRESOLVED",
        "selection_status": "NOT_SELECTED",
    }
    family_hash = content_hash(payload)
    return {
        **payload,
        "family_id": f"RATEADEQEVIDFAM-{family_hash[:16]}",
        "family_hash": family_hash,
    }


def build_reference_adequacy_evidence(
    *,
    development_dataset: dict[str, Any],
    protocol: dict[str, Any],
    research: dict[str, Any],
    reconstruction: dict[str, Any],
    stability: dict[str, Any],
    adequacy_protocol: dict[str, Any],
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
    reconstruction_state = validate_eligibility_reconstruction(reconstruction)
    stability_state = validate_reference_stability_evidence(stability)
    adequacy_state = validate_reference_adequacy_protocol(adequacy_protocol)

    reconstruction_source = reconstruction["source"]
    if reconstruction_source["development_dataset_hash"] != development_state[
        "dataset_hash"
    ]:
        raise ValueError("R2.1 reconstruction Development hash mismatch.")
    if reconstruction_source["protocol_hash"] != protocol_state["protocol_hash"]:
        raise ValueError("R2.1 reconstruction Protocol hash mismatch.")
    if reconstruction_source["research_hash"] != research_state["research_hash"]:
        raise ValueError("R2.1 reconstruction Research hash mismatch.")

    stability_source = stability["source"]
    if stability_source["reconstruction_hash"] != reconstruction[
        "reconstruction_hash"
    ]:
        raise ValueError("R2.1 stability reconstruction hash mismatch.")
    if stability_source["development_dataset_hash"] != development_state[
        "dataset_hash"
    ]:
        raise ValueError("R2.1 stability Development hash mismatch.")

    adequacy_source = adequacy_protocol["source"]
    if adequacy_source["reference_stability_hash"] != stability_state[
        "stability_hash"
    ]:
        raise ValueError("R2.1 adequacy protocol stability hash mismatch.")
    if adequacy_source["reconstruction_hash"] != reconstruction[
        "reconstruction_hash"
    ]:
        raise ValueError("R2.1 adequacy protocol reconstruction hash mismatch.")
    if adequacy_state["ready_for_evidence_generation"] is not True:
        raise ValueError("R2.1 adequacy protocol is not ready for evidence generation.")

    common_ns = _common_support_ns(stability)
    families: list[dict[str, Any]] = []
    indexes: dict[str, dict[str, Any]] = {}
    for feature_id in RATE_SPIKE_FEATURE_IDS:
        rows = _research_rows(research, feature_id)
        tail_family, index = _tail_family(
            feature_id=feature_id,
            rows=rows,
            common_ns=common_ns,
        )
        families.append(tail_family)
        families.append(
            _mad_family(
                feature_id=feature_id,
                rows=rows,
                common_ns=common_ns,
            )
        )
        indexes[feature_id] = index

    method_order = {TAIL_METHOD: 0, MAD_METHOD: 1}
    feature_order = {
        feature_id: index for index, feature_id in enumerate(RATE_SPIKE_FEATURE_IDS)
    }
    families.sort(
        key=lambda item: (
            feature_order[str(item["feature_id"])],
            method_order[str(item["method"])],
        )
    )

    forward_comparison_count = sum(
        int(anchor["suffix_transition_count"])
        for family in families
        for anchor in family["anchors"]
    )
    counts = {
        "common_support_point_count": len(common_ns),
        "tail_family_count": 3,
        "mad_family_count": 3,
        "reference_family_count": 6,
        "anchor_path_count": len(common_ns) * 6,
        "forward_comparison_count": forward_comparison_count,
    }
    source = {
        "development_dataset_hash": development_state["dataset_hash"],
        "protocol_hash": protocol_state["protocol_hash"],
        "research_hash": research_state["research_hash"],
        "reconstruction_id": reconstruction["reconstruction_id"],
        "reconstruction_hash": reconstruction["reconstruction_hash"],
        "reference_stability_id": stability["stability_id"],
        "reference_stability_hash": stability_state["stability_hash"],
        "reference_adequacy_protocol_id": adequacy_protocol[
            "adequacy_protocol_id"
        ],
        "reference_adequacy_protocol_hash": adequacy_state[
            "adequacy_protocol_hash"
        ],
        "raw_candidate_count": int(reconstruction_state["raw_candidate_count"]),
        "source_main_sha": source_main_sha or "UNSPECIFIED",
    }
    evidence_contract = {
        "candidate_support_universe": CANDIDATE_SUPPORT_UNIVERSE,
        "candidate_support_values_hash": content_hash(common_ns),
        "boundary_rule": "BOUNDARY_ANCHORED_FORWARD_ENVELOPE",
        "every_later_reference_preserved": True,
        "tail_metric": "EXACT_ECDF_SUP_DISTANCE",
        "tail_evaluation_support": "OBSERVED_VALUES_UNION_ONLY",
        "tail_invented_x_grid_points": 0,
        "tail_distance_encoding": {
            "numerator": PATH_ENCODING_INTEGER,
            "denominator_rule": TAIL_DENOMINATOR_RULE,
        },
        "mad_metrics": [
            "ABSOLUTE_MEDIAN_SHIFT",
            "ABSOLUTE_MAD_SHIFT",
            "RELATIVE_MAD_SHIFT",
        ],
        "mad_path_encoding": PATH_ENCODING_DECIMAL,
        "mad_zero_scale_rule": "NON_COMPUTABLE_ZERO_SCALE",
        "weighted_stability_score": None,
        "tolerance_selection_performed": False,
        "minimum_n_selection_performed": False,
        "validation_suffix_selection_performed": False,
        "temporal_perturbation_role": "OPTIONAL_DIAGNOSTIC_ONLY",
    }
    policy_state = {
        "evidence_generation_status": "COMPLETE",
        "reference_adequacy": "UNRESOLVED",
        "reference_adequacy_criterion": "UNRESOLVED",
        "tail_forward_envelope_tolerance": None,
        "mad_forward_envelope_tolerances": {
            "absolute_median_shift": None,
            "absolute_mad_shift": None,
            "relative_mad_shift": None,
        },
        "minimum_validation_suffix_transitions": None,
        "minimum_prior_observations": None,
        "recommended_support": None,
        "selection_status": "NOT_SELECTED",
        "eligibility_policy_status": "UNDEFINED",
        "admissibility_policy_status": "UNDEFINED",
        "final_candidate_status": "NOT_SELECTED",
        "ready_for_b2": False,
        "ready_for_holdout": False,
        "rate_spike_state": "UNCALIBRATED",
    }
    unresolved = [
        TAIL_FORWARD_ENVELOPE_BLOCKER,
        MAD_FORWARD_ENVELOPE_BLOCKER,
        VALIDATION_SUFFIX_BLOCKER,
    ]
    identity_payload = {
        "contract_version": REFERENCE_ADEQUACY_EVIDENCE_CONTRACT_VERSION,
        "source": source,
        "evidence_contract": evidence_contract,
        "counts": counts,
        "common_support_values": common_ns,
        "common_support_values_hash": content_hash(common_ns),
        "reference_state_index_hash": content_hash(indexes),
        "family_payload_hash": content_hash(families),
        "unresolved_policy_classes": unresolved,
        "policy_state": policy_state,
        "holdout_locked": True,
        "holdout_accessed": False,
        "network_requests": 0,
        "macro_db_writes": 0,
        "production_impact": "NONE",
    }
    evidence_hash = content_hash(identity_payload)
    return {
        **identity_payload,
        "evidence_id": f"RATEADEQEVID-{evidence_hash[:16]}",
        "evidence_hash": evidence_hash,
        "analysis_status": "COMPLETE",
        "reference_state_indexes": indexes,
        "families": families,
    }


def _family_payload(family: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in family.items()
        if key not in {"family_id", "family_hash"}
    }


def _identity_payload(artifact: dict[str, Any]) -> dict[str, Any]:
    return {
        key: artifact[key]
        for key in (
            "contract_version",
            "source",
            "evidence_contract",
            "counts",
            "common_support_values",
            "common_support_values_hash",
            "reference_state_index_hash",
            "family_payload_hash",
            "unresolved_policy_classes",
            "policy_state",
            "holdout_locked",
            "holdout_accessed",
            "network_requests",
            "macro_db_writes",
            "production_impact",
        )
    }


def _validate_anchor_path_common(
    anchor: dict[str, Any],
    *,
    max_prior: int,
) -> int:
    anchor_n = int(anchor["anchor_n"])
    expected_count = max_prior - anchor_n
    if int(anchor["suffix_transition_count"]) != expected_count:
        raise ValueError("R2.1 suffix transition count mismatch.")
    expected_first = anchor_n + 1 if expected_count else None
    expected_last = max_prior if expected_count else None
    if anchor.get("first_later_n") != expected_first:
        raise ValueError("R2.1 first later N mismatch.")
    if anchor.get("last_later_n") != expected_last:
        raise ValueError("R2.1 last later N mismatch.")
    if anchor.get("selection_status") != "NOT_SELECTED":
        raise ValueError("R2.1 anchor path cannot select support.")
    return expected_count


def _validate_tail_anchor(anchor: dict[str, Any], *, max_prior: int) -> None:
    count = _validate_anchor_path_common(anchor, max_prior=max_prior)
    if anchor.get("path_encoding") != PATH_ENCODING_INTEGER:
        raise ValueError("R2.1 TAIL path encoding mismatch.")
    if anchor.get("distance_denominator_rule") != TAIL_DENOMINATOR_RULE:
        raise ValueError("R2.1 TAIL denominator rule mismatch.")
    values = [int(value) for value in _rle_decode(anchor["distance_numerator_rle"])]
    if len(values) != count:
        raise ValueError("R2.1 TAIL path length mismatch.")
    if content_hash(values) != anchor.get("path_hash"):
        raise ValueError("R2.1 TAIL path hash mismatch.")

    anchor_n = int(anchor["anchor_n"])
    best: tuple[int, int, int] | None = None
    for offset, numerator in enumerate(values):
        later_n = anchor_n + 1 + offset
        denominator = anchor_n * later_n
        if best is None or _fraction_is_greater(
            numerator, denominator, best[0], best[1]
        ):
            best = (numerator, denominator, later_n)
    expected_max = (
        None
        if best is None
        else {"numerator": best[0], "denominator": best[1], "later_n": best[2]}
    )
    if anchor.get("max_distance") != expected_max:
        raise ValueError("R2.1 TAIL maximum distance mismatch.")


def _validate_mad_anchor(anchor: dict[str, Any], *, max_prior: int) -> None:
    count = _validate_anchor_path_common(anchor, max_prior=max_prior)
    if anchor.get("path_encoding") != PATH_ENCODING_DECIMAL:
        raise ValueError("R2.1 MAD path encoding mismatch.")

    fields = (
        ("absolute_median_shift_rle", "absolute_median_shift_path_hash"),
        ("absolute_mad_shift_rle", "absolute_mad_shift_path_hash"),
        ("relative_mad_shift_rle", "relative_mad_shift_path_hash"),
    )
    decoded: dict[str, list[str | None]] = {}
    for encoded_key, hash_key in fields:
        values = _rle_decode(anchor[encoded_key])
        if len(values) != count:
            raise ValueError("R2.1 MAD path length mismatch.")
        normalized = [
            None if value is None else _decimal_text(_decimal(value))
            for value in values
        ]
        if content_hash(normalized) != anchor.get(hash_key):
            raise ValueError("R2.1 MAD path hash mismatch.")
        decoded[encoded_key] = normalized

    first_later = anchor.get("first_later_n")
    if anchor.get("max_absolute_median_shift") != _max_decimal_path(
        decoded["absolute_median_shift_rle"],
        first_later_n=first_later,
    ):
        raise ValueError("R2.1 MAD median maximum mismatch.")
    if anchor.get("max_absolute_mad_shift") != _max_decimal_path(
        decoded["absolute_mad_shift_rle"],
        first_later_n=first_later,
    ):
        raise ValueError("R2.1 MAD scale maximum mismatch.")
    if anchor.get("max_relative_mad_shift") != _max_decimal_path(
        decoded["relative_mad_shift_rle"],
        first_later_n=first_later,
    ):
        raise ValueError("R2.1 MAD relative maximum mismatch.")

    anchor_mad = _decimal_or_none(anchor.get("anchor_mad"))
    if anchor_mad == 0:
        if anchor.get("relative_mad_shift_status") != "NON_COMPUTABLE_ZERO_SCALE":
            raise ValueError("R2.1 MAD zero-scale status mismatch.")
        if any(
            value is not None
            for value in decoded["relative_mad_shift_rle"]
        ):
            raise ValueError("R2.1 MAD zero-scale relative path must stay null.")


def validate_reference_adequacy_evidence(
    artifact: dict[str, Any],
) -> dict[str, Any]:
    if artifact.get("contract_version") != (
        REFERENCE_ADEQUACY_EVIDENCE_CONTRACT_VERSION
    ):
        raise ValueError("Unsupported reference adequacy evidence contract.")
    if artifact.get("analysis_status") != "COMPLETE":
        raise ValueError("Reference adequacy evidence must be COMPLETE.")
    if artifact.get("holdout_locked") is not True:
        raise ValueError("R2.1 evidence must keep Holdout locked.")
    if artifact.get("holdout_accessed") is not False:
        raise ValueError("R2.1 evidence must not access Holdout.")
    if int(artifact.get("network_requests") or 0) != 0:
        raise ValueError("R2.1 evidence must not use network.")
    if int(artifact.get("macro_db_writes") or 0) != 0:
        raise ValueError("R2.1 evidence must not write Macro DB.")
    if artifact.get("production_impact") != "NONE":
        raise ValueError("R2.1 evidence must have no Production impact.")

    contract = artifact.get("evidence_contract") or {}
    if contract.get("candidate_support_universe") != CANDIDATE_SUPPORT_UNIVERSE:
        raise ValueError("R2.1 candidate support universe changed.")
    if contract.get("boundary_rule") != "BOUNDARY_ANCHORED_FORWARD_ENVELOPE":
        raise ValueError("R2.1 boundary rule changed.")
    if contract.get("every_later_reference_preserved") is not True:
        raise ValueError("R2.1 must preserve every later comparison.")
    if contract.get("tail_invented_x_grid_points") != 0:
        raise ValueError("R2.1 TAIL cannot invent x-grid points.")
    if contract.get("weighted_stability_score") is not None:
        raise ValueError("R2.1 weighted stability score is forbidden.")
    if contract.get("tolerance_selection_performed") is not False:
        raise ValueError("R2.1 cannot select tolerances.")
    if contract.get("minimum_n_selection_performed") is not False:
        raise ValueError("R2.1 cannot select minimum N.")
    if contract.get("validation_suffix_selection_performed") is not False:
        raise ValueError("R2.1 cannot select suffix length.")

    common_ns = [int(value) for value in artifact.get("common_support_values") or []]
    if common_ns != sorted(set(common_ns)) or not common_ns:
        raise ValueError("R2.1 common support values must be sorted unique.")
    if content_hash(common_ns) != artifact.get("common_support_values_hash"):
        raise ValueError("R2.1 common support values hash mismatch.")

    indexes = artifact.get("reference_state_indexes") or {}
    if set(indexes) != set(RATE_SPIKE_FEATURE_IDS):
        raise ValueError("R2.1 reference state index feature set mismatch.")
    for feature_id, index in indexes.items():
        first = int(index["first_prior_count"])
        last = int(index["last_prior_count"])
        hashes = list(index["reference_hashes"])
        if first != 1 or len(hashes) != last:
            raise ValueError("R2.1 reference state index range mismatch.")
        if content_hash(hashes) != index.get("reference_hashes_hash"):
            raise ValueError("R2.1 reference state index hash mismatch.")
        if index.get("feature_id") != feature_id:
            raise ValueError("R2.1 reference state index feature mismatch.")
    if content_hash(indexes) != artifact.get("reference_state_index_hash"):
        raise ValueError("R2.1 reference state index payload hash mismatch.")

    families = list(artifact.get("families") or [])
    expected_pairs = {
        (feature_id, method)
        for feature_id in RATE_SPIKE_FEATURE_IDS
        for method in (TAIL_METHOD, MAD_METHOD)
    }
    actual_pairs = {
        (str(family["feature_id"]), str(family["method"]))
        for family in families
    }
    if actual_pairs != expected_pairs:
        raise ValueError("R2.1 reference family set mismatch.")
    if len(families) != 6:
        raise ValueError("R2.1 requires six reference families.")

    forward_count = 0
    for family in families:
        if family.get("candidate_support_universe") != CANDIDATE_SUPPORT_UNIVERSE:
            raise ValueError("R2.1 family candidate universe changed.")
        if int(family.get("candidate_support_count") or 0) != len(common_ns):
            raise ValueError("R2.1 family candidate count mismatch.")
        if family.get("adequacy_status") != "UNRESOLVED":
            raise ValueError("R2.1 family cannot approve adequacy.")
        if family.get("selection_status") != "NOT_SELECTED":
            raise ValueError("R2.1 family cannot select support.")
        anchors = list(family.get("anchors") or [])
        if [int(anchor["anchor_n"]) for anchor in anchors] != common_ns:
            raise ValueError("R2.1 family anchors must match common support N.")
        max_prior = int(family["max_prior_count"])
        for anchor in anchors:
            forward_count += int(anchor["suffix_transition_count"])
            if family["method"] == TAIL_METHOD:
                _validate_tail_anchor(anchor, max_prior=max_prior)
            else:
                _validate_mad_anchor(anchor, max_prior=max_prior)

        family_hash = content_hash(_family_payload(family))
        if family.get("family_hash") != family_hash:
            raise ValueError("R2.1 family hash mismatch.")
        if family.get("family_id") != f"RATEADEQEVIDFAM-{family_hash[:16]}":
            raise ValueError("R2.1 family id mismatch.")

    counts = artifact.get("counts") or {}
    if int(counts.get("common_support_point_count") or 0) != len(common_ns):
        raise ValueError("R2.1 common support count mismatch.")
    if int(counts.get("tail_family_count") or 0) != 3:
        raise ValueError("R2.1 TAIL family count mismatch.")
    if int(counts.get("mad_family_count") or 0) != 3:
        raise ValueError("R2.1 MAD family count mismatch.")
    if int(counts.get("reference_family_count") or 0) != 6:
        raise ValueError("R2.1 reference family count mismatch.")
    if int(counts.get("anchor_path_count") or 0) != len(common_ns) * 6:
        raise ValueError("R2.1 anchor path count mismatch.")
    if int(counts.get("forward_comparison_count") or 0) != forward_count:
        raise ValueError("R2.1 forward comparison count mismatch.")

    if content_hash(families) != artifact.get("family_payload_hash"):
        raise ValueError("R2.1 family payload hash mismatch.")

    expected_unresolved = [
        TAIL_FORWARD_ENVELOPE_BLOCKER,
        MAD_FORWARD_ENVELOPE_BLOCKER,
        VALIDATION_SUFFIX_BLOCKER,
    ]
    if artifact.get("unresolved_policy_classes") != expected_unresolved:
        raise ValueError("R2.1 unresolved policy class set changed.")

    policy = artifact.get("policy_state") or {}
    expected_policy = {
        "evidence_generation_status": "COMPLETE",
        "reference_adequacy": "UNRESOLVED",
        "reference_adequacy_criterion": "UNRESOLVED",
        "tail_forward_envelope_tolerance": None,
        "mad_forward_envelope_tolerances": {
            "absolute_median_shift": None,
            "absolute_mad_shift": None,
            "relative_mad_shift": None,
        },
        "minimum_validation_suffix_transitions": None,
        "minimum_prior_observations": None,
        "recommended_support": None,
        "selection_status": "NOT_SELECTED",
        "eligibility_policy_status": "UNDEFINED",
        "admissibility_policy_status": "UNDEFINED",
        "final_candidate_status": "NOT_SELECTED",
        "ready_for_b2": False,
        "ready_for_holdout": False,
        "rate_spike_state": "UNCALIBRATED",
    }
    if policy != expected_policy:
        raise ValueError("R2.1 policy state changed unexpectedly.")

    evidence_hash = content_hash(_identity_payload(artifact))
    if artifact.get("evidence_hash") != evidence_hash:
        raise ValueError("R2.1 evidence hash mismatch.")
    if artifact.get("evidence_id") != f"RATEADEQEVID-{evidence_hash[:16]}":
        raise ValueError("R2.1 evidence id mismatch.")

    return {
        "evidence_id": artifact["evidence_id"],
        "evidence_hash": evidence_hash,
        "common_support_point_count": len(common_ns),
        "forward_comparison_count": forward_count,
        "unresolved_policy_class_count": len(expected_unresolved),
        "ready_for_b2": False,
        "ready_for_holdout": False,
    }


def render_reference_adequacy_evidence_text(
    artifact: dict[str, Any],
) -> str:
    state = validate_reference_adequacy_evidence(artifact)
    policy = artifact["policy_state"]
    counts = artifact["counts"]
    lines = [
        "NEXT-6B-S4.2-B.1.6-R2.1 BOUNDARY-ANCHORED REFERENCE ADEQUACY EVIDENCE",
        "",
        f"Source Protocol       : {artifact['source']['reference_adequacy_protocol_id']}",
        f"Common support points : {counts['common_support_point_count']}",
        f"TAIL / MAD families   : {counts['tail_family_count']} / {counts['mad_family_count']}",
        "EPT reference gate    : EXCLUDED",
        f"Forward comparisons   : {state['forward_comparison_count']}",
        "Forward paths         : COMPLETE",
        "Tolerance selection   : NOT PERFORMED",
        "Minimum N selection   : NOT PERFORMED",
        "Suffix selection      : NOT PERFORMED",
        "",
        f"Reference adequacy    : {policy['reference_adequacy']}",
        f"Minimum prior N       : {policy['minimum_prior_observations']}",
        f"Unresolved classes    : {state['unresolved_policy_class_count']}",
        "",
        f"Holdout accessed      : {artifact['holdout_accessed']}",
        f"Network requests      : {artifact['network_requests']}",
        f"Macro DB writes       : {artifact['macro_db_writes']}",
        f"Production            : {artifact['production_impact']}",
        "",
        "B.2 readiness         : BLOCKED",
        "Holdout readiness     : BLOCKED",
    ]
    return "\n".join(lines)
