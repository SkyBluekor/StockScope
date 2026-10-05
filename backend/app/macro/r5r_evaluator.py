from __future__ import annotations

from collections import Counter
from fractions import Fraction
from math import gcd
from typing import Any, Iterable, Mapping, Sequence


R5R_EVALUATOR_VERSION = "NEXT6E_R5R_EVALUATOR_V1"
R5R_TARGET_ID = "NEXT6E_S6A_R5R_OBSERVED_PATH_EMPIRICAL_STABILITY_V1"
R5R_METHOD_ID = "NEXT6E_S6A_R5R_EMPIRICAL_STABILITY_V1"

R5R_METHOD_CONTRACT_SCHEMA = "NEXT6E_S6A_R5R_METHOD_CONTRACT_V2"
R5R_METHOD_CONTRACT_SHA256 = (
    "5519ad12a6e3dafb30041935c6ead2869d35148aadb2a6bab8443521ea8310c4"
)
R5R_METHOD_DESIGN_SHA256 = (
    "05852b077e6c29820643299f66984f496ffe806d88c6544c577ee3357c5f74eb"
)
R5R_CANDIDATE_DOMAIN_ID = "NEXT6E_S6A_R5R_CANDIDATE_DOMAIN_V1"
R5R_CANDIDATE_DOMAIN_SHA256 = (
    "2f89ea3fdf775d718fabf955ee266b5cf36736f68b0fe97ced2cc5da83e0cdb4"
)
R5R_WINDOW_PROFILE_ID = "NEXT6E_S6A_R5R_WINDOW_PROFILE_V1"
R5R_WINDOW_PROFILE_SHA256 = (
    "47a11455b159564db80eaf2c61bd89710a4bf56aea5d740eb60617ac2a3d385c"
)
R5R_POLICY_SCHEMA = "NEXT6E_S6B_R5R_POLICY_V1"
R5R_POLICY_SHA256 = (
    "8934d99d808b8c7afa837fb71601695457154747fbcafd592da44b337343bc22"
)
R5R_CHRONOLOGY_HASH_CONTRACT = "R5R_JOINT_CHRONOLOGY_HASH_V1"
R5R_NUMERIC_CONTRACT = "R5R_EXACT_RATIONAL_V1"

HORIZONS = (1, 5, 10)
FEATURE_BY_HORIZON = {
    1: "delta_bp_1obs",
    5: "delta_bp_5obs",
    10: "delta_bp_10obs",
}

TAU_T = Fraction(1, 10)
TAU_L = Fraction(1, 2)
TAU_S = Fraction(1, 4)


class R5RContractError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def canonical_rational(value: Fraction | int) -> dict[str, str]:
    rational = value if isinstance(value, Fraction) else Fraction(value)
    return {
        "numerator": str(rational.numerator),
        "denominator": str(rational.denominator),
    }


def parse_canonical_rational(value: Mapping[str, Any]) -> Fraction:
    try:
        numerator_text = str(value["numerator"])
        denominator_text = str(value["denominator"])
        numerator = int(numerator_text)
        denominator = int(denominator_text)
    except (KeyError, TypeError, ValueError) as exc:
        raise R5RContractError(
            "NUMERIC_CONTRACT_MISMATCH",
            "R5R rational must contain base-10 numerator/denominator strings.",
        ) from exc

    if numerator_text != str(numerator) or denominator_text != str(denominator):
        raise R5RContractError(
            "NUMERIC_CONTRACT_MISMATCH",
            "R5R rational is not canonically encoded.",
        )
    if denominator <= 0 or gcd(abs(numerator), denominator) != 1:
        raise R5RContractError(
            "NUMERIC_CONTRACT_MISMATCH",
            "R5R rational must be reduced with a positive denominator.",
        )
    if numerator == 0 and denominator != 1:
        raise R5RContractError(
            "NUMERIC_CONTRACT_MISMATCH",
            "R5R zero must be encoded as 0/1.",
        )
    return Fraction(numerator, denominator)


def midpoint_median(values: Sequence[int | Fraction]) -> Fraction:
    if not values:
        raise ValueError("median requires at least one value")
    ordered = sorted(Fraction(value) for value in values)
    size = len(ordered)
    middle = size // 2
    if size % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2


def midpoint_mad(values: Sequence[int | Fraction]) -> Fraction:
    center = midpoint_median(values)
    return midpoint_median([abs(Fraction(value) - center) for value in values])


def ecdf_sup_distance(
    anchor: Sequence[int | Fraction],
    later: Sequence[int | Fraction],
) -> Fraction:
    if not anchor or not later:
        raise ValueError("ECDF distance requires two non-empty samples")

    left = [Fraction(value) for value in anchor]
    right = [Fraction(value) for value in later]
    left_counts = Counter(left)
    right_counts = Counter(right)
    support = sorted(set(left_counts) | set(right_counts))

    left_cumulative = 0
    right_cumulative = 0
    maximum = Fraction(0, 1)
    for value in support:
        left_cumulative += left_counts.get(value, 0)
        right_cumulative += right_counts.get(value, 0)
        distance = abs(
            Fraction(left_cumulative, len(left))
            - Fraction(right_cumulative, len(right))
        )
        if distance > maximum:
            maximum = distance
    return maximum


def window_length(n: int) -> int:
    if n < 11:
        raise R5RContractError(
            "INSUFFICIENT_EMPIRICAL_WINDOW",
            "R5R requires joint chronology n >= 11.",
        )
    length = (n + 9) // 10
    if length < 2:
        raise R5RContractError(
            "INSUFFICIENT_EMPIRICAL_WINDOW",
            "R5R empirical window must contain at least two observations.",
        )
    return length


def effective_candidate_mapping(n: int) -> list[dict[str, int]]:
    width = window_length(n)
    canonical: dict[int, int] = {}
    for j in range(2, 20):
        mapped = (j * n + 19) // 20
        canonical.setdefault(mapped, j)

    return [
        {"j": j, "N": mapped}
        for mapped, j in sorted(canonical.items())
        if mapped >= width and mapped < n
    ]


def select_common_n(candidates: Sequence[Mapping[str, Any]]) -> int | None:
    supported = sorted(
        int(candidate["N"])
        for candidate in candidates
        if candidate.get("status") == "SUPPORTED_WITHIN_POLICY"
    )
    return supported[0] if supported else None


def _fraction_output(value: Fraction | None) -> dict[str, str] | None:
    return None if value is None else canonical_rational(value)


def _feature_value(row: Mapping[str, Any], feature_id: str) -> int:
    features = row.get("features")
    if not isinstance(features, Mapping) or feature_id not in features:
        raise R5RContractError(
            "MISSING_REQUIRED_HORIZON",
            f"Bound row is missing required feature {feature_id}.",
        )
    value = features[feature_id]
    if isinstance(value, bool) or not isinstance(value, int):
        raise R5RContractError(
            "INVALID_FEATURE_LATTICE",
            f"{feature_id} must be an exact signed integer basis-point value.",
        )
    return value


def _validate_runtime_contracts(
    bound: Mapping[str, Any],
    policy: Mapping[str, Any],
) -> None:
    expected = {
        "method_contract_sha256": R5R_METHOD_CONTRACT_SHA256,
        "method_design_sha256": R5R_METHOD_DESIGN_SHA256,
        "candidate_domain_sha256": R5R_CANDIDATE_DOMAIN_SHA256,
        "window_profile_sha256": R5R_WINDOW_PROFILE_SHA256,
        "policy_contract_sha256": R5R_POLICY_SHA256,
    }
    for field, required in expected.items():
        actual = str(bound.get(field) or "")
        if actual != required:
            code = {
                "method_contract_sha256": "METHOD_CONTRACT_MISMATCH",
                "method_design_sha256": "METHOD_CONTRACT_MISMATCH",
                "candidate_domain_sha256": "CANDIDATE_DOMAIN_MISMATCH",
                "window_profile_sha256": "WINDOW_PROFILE_MISMATCH",
                "policy_contract_sha256": "POLICY_TOLERANCE_UNBOUND",
            }[field]
            raise R5RContractError(
                code,
                f"{field} does not match the frozen R5R contract.",
            )

    if str(bound.get("chronology_hash_contract_id")) != R5R_CHRONOLOGY_HASH_CONTRACT:
        raise R5RContractError(
            "CHRONOLOGY_HASH_CONTRACT_MISMATCH",
            "Chronology hash contract does not match R5R_JOINT_CHRONOLOGY_HASH_V1.",
        )
    if str(bound.get("numeric_contract_id")) != R5R_NUMERIC_CONTRACT:
        raise R5RContractError(
            "NUMERIC_CONTRACT_MISMATCH",
            "Numeric contract does not match R5R_EXACT_RATIONAL_V1.",
        )

    if str(policy.get("schema_id")) != R5R_POLICY_SCHEMA:
        raise R5RContractError(
            "POLICY_TOLERANCE_UNBOUND",
            "R5R policy schema is not the frozen Policy V1.",
        )
    if str(policy.get("semantic_contract_sha256")) != R5R_POLICY_SHA256:
        raise R5RContractError(
            "POLICY_TOLERANCE_UNBOUND",
            "R5R policy hash is not the frozen Policy V1 hash.",
        )

    tolerances = policy.get("tolerances")
    if not isinstance(tolerances, Mapping):
        raise R5RContractError(
            "POLICY_TOLERANCE_UNBOUND",
            "R5R policy tolerances are missing.",
        )
    actual_t = parse_canonical_rational(tolerances["tau_T"]["exact"])
    actual_l = parse_canonical_rational(tolerances["tau_L"]["exact"])
    actual_s = parse_canonical_rational(tolerances["tau_S"]["exact"])
    if (actual_t, actual_l, actual_s) != (TAU_T, TAU_L, TAU_S):
        raise R5RContractError(
            "POLICY_TOLERANCE_UNBOUND",
            "R5R policy tolerances do not match the frozen Policy V1.",
        )


def _validate_bound_rows(bound: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    rows = bound.get("joint_rows")
    if not isinstance(rows, list) or not rows:
        raise R5RContractError(
            "INVALID_DATA_IDENTITY",
            "Bound R5R input must contain a non-empty joint_rows list.",
        )

    dates: list[str] = []
    for expected_i, row in enumerate(rows, start=1):
        if not isinstance(row, Mapping):
            raise R5RContractError(
                "INVALID_DATA_IDENTITY",
                "Bound R5R row must be an object.",
            )
        if int(row.get("i") or 0) != expected_i:
            raise R5RContractError(
                "INVALID_CHRONOLOGY",
                "Bound chronology indices must be contiguous from 1..n.",
            )
        date = str(row.get("observation_date") or "")
        if len(date) != 10 or date[4:5] != "-" or date[7:8] != "-":
            raise R5RContractError(
                "INVALID_CHRONOLOGY",
                "Bound chronology dates must use YYYY-MM-DD.",
            )
        dates.append(date)
        for feature_id in FEATURE_BY_HORIZON.values():
            _feature_value(row, feature_id)

    if dates != sorted(dates) or len(dates) != len(set(dates)):
        raise R5RContractError(
            "INVALID_CHRONOLOGY",
            "Bound chronology must be strictly ascending and unique.",
        )

    if int(bound.get("joint_row_count") or 0) != len(rows):
        raise R5RContractError(
            "INVALID_DATA_IDENTITY",
            "joint_row_count does not match bound rows.",
        )

    expected_window = window_length(len(rows))
    if int(bound.get("window_length") or 0) != expected_window:
        raise R5RContractError(
            "WINDOW_PROFILE_MISMATCH",
            "Bound window length does not match ceil(n/10).",
        )

    expected_candidates = effective_candidate_mapping(len(rows))
    if bound.get("effective_candidate_mapping") != expected_candidates:
        raise R5RContractError(
            "CANDIDATE_DOMAIN_MISMATCH",
            "Bound candidate mapping does not match the frozen candidate domain.",
        )
    return rows


def _update_max(
    current_value: Fraction | None,
    current_arg: int | None,
    value: Fraction,
    later_state: int,
) -> tuple[Fraction, int]:
    if current_value is None or value > current_value:
        return value, later_state
    if value == current_value and (current_arg is None or later_state < current_arg):
        return value, later_state
    return current_value, int(current_arg)


def _evaluate_candidate(
    *,
    series_by_horizon: Mapping[int, Sequence[int]],
    n: int,
    width: int,
    candidate: Mapping[str, int],
) -> dict[str, Any]:
    anchor_n = int(candidate["N"])
    per_horizon: dict[str, Any] = {}
    candidate_blocked = False
    candidate_exceeds = False
    blocked_codes: list[str] = []

    for horizon in HORIZONS:
        series = series_by_horizon[horizon]
        anchor_values = series[anchor_n - width : anchor_n]
        anchor_median = midpoint_median(anchor_values)
        anchor_mad = midpoint_mad(anchor_values)

        if anchor_mad == 0:
            candidate_blocked = True
            blocked_codes.append("ANCHOR_EMPIRICAL_MAD_ZERO")
            per_horizon[str(horizon)] = {
                "status": "BLOCKED",
                "failure_code": "ANCHOR_EMPIRICAL_MAD_ZERO",
                "anchor_median": _fraction_output(anchor_median),
                "anchor_mad": _fraction_output(anchor_mad),
                "max_T_EMP": None,
                "argmax_T_EMP": None,
                "max_L_EMP": None,
                "argmax_L_EMP": None,
                "max_S_EMP": None,
                "argmax_S_EMP": None,
                "latest_T_EMP": None,
                "latest_L_EMP": None,
                "latest_S_EMP": None,
            }
            continue

        max_t: Fraction | None = None
        arg_t: int | None = None
        max_l: Fraction | None = None
        arg_l: int | None = None
        max_s: Fraction | None = None
        arg_s: int | None = None
        latest_t: Fraction | None = None
        latest_l: Fraction | None = None
        latest_s: Fraction | None = None
        horizon_exceeds = False

        for later_n in range(anchor_n + 1, n + 1):
            later_values = series[later_n - width : later_n]
            later_median = midpoint_median(later_values)
            later_mad = midpoint_mad(later_values)

            t_emp = ecdf_sup_distance(anchor_values, later_values)
            l_emp = abs(later_median - anchor_median) / anchor_mad
            s_emp = abs(later_mad - anchor_mad) / anchor_mad

            max_t, arg_t = _update_max(max_t, arg_t, t_emp, later_n)
            max_l, arg_l = _update_max(max_l, arg_l, l_emp, later_n)
            max_s, arg_s = _update_max(max_s, arg_s, s_emp, later_n)

            if t_emp > TAU_T or l_emp > TAU_L or s_emp > TAU_S:
                horizon_exceeds = True

            if later_n == n:
                latest_t = t_emp
                latest_l = l_emp
                latest_s = s_emp

        candidate_exceeds = candidate_exceeds or horizon_exceeds
        per_horizon[str(horizon)] = {
            "status": "EXCEEDS_POLICY" if horizon_exceeds else "SUPPORTED_WITHIN_POLICY",
            "failure_code": None,
            "anchor_median": _fraction_output(anchor_median),
            "anchor_mad": _fraction_output(anchor_mad),
            "max_T_EMP": _fraction_output(max_t),
            "argmax_T_EMP": arg_t,
            "max_L_EMP": _fraction_output(max_l),
            "argmax_L_EMP": arg_l,
            "max_S_EMP": _fraction_output(max_s),
            "argmax_S_EMP": arg_s,
            "latest_T_EMP": _fraction_output(latest_t),
            "latest_L_EMP": _fraction_output(latest_l),
            "latest_S_EMP": _fraction_output(latest_s),
        }

    if candidate_blocked:
        status = "BLOCKED"
    elif candidate_exceeds:
        status = "EXCEEDS_POLICY"
    else:
        status = "SUPPORTED_WITHIN_POLICY"

    return {
        "j": int(candidate["j"]),
        "N": anchor_n,
        "status": status,
        "failure_codes": sorted(set(blocked_codes)),
        "per_horizon": per_horizon,
    }


def _blocked_result(code: str, message: str) -> dict[str, Any]:
    return {
        "result_generation_version": R5R_EVALUATOR_VERSION,
        "target_id": R5R_TARGET_ID,
        "method_id": R5R_METHOD_ID,
        "result_status": "BLOCKED",
        "result_code": None,
        "failure_code": code,
        "failure_message": message,
        "OBSERVED_PATH_COMMON_N": None,
        "candidates": [],
    }


def evaluate_r5r(
    bound: Mapping[str, Any],
    *,
    policy: Mapping[str, Any],
) -> dict[str, Any]:
    try:
        _validate_runtime_contracts(bound, policy)
        rows = _validate_bound_rows(bound)
    except R5RContractError as exc:
        return _blocked_result(exc.code, str(exc))

    n = len(rows)
    width = window_length(n)
    candidates = effective_candidate_mapping(n)
    if not candidates:
        return _blocked_result(
            "NO_ELIGIBLE_GRID_ANCHOR",
            "No approved R5R grid anchor has a full window and later state.",
        )

    series_by_horizon = {
        horizon: [
            _feature_value(row, FEATURE_BY_HORIZON[horizon])
            for row in rows
        ]
        for horizon in HORIZONS
    }

    evaluated = [
        _evaluate_candidate(
            series_by_horizon=series_by_horizon,
            n=n,
            width=width,
            candidate=candidate,
        )
        for candidate in candidates
    ]

    common_n = select_common_n(evaluated)
    if common_n is not None:
        result_status = "SUPPORTED_WITHIN_POLICY"
        result_code = None
        failure_code = None
    else:
        computable = [
            candidate
            for candidate in evaluated
            if candidate["status"] != "BLOCKED"
        ]
        if not computable:
            return {
                **_blocked_result(
                    "NO_COMPUTABLE_APPROVED_ANCHOR",
                    "All structurally eligible R5R anchors are blocked.",
                ),
                "candidates": evaluated,
            }
        result_status = "NOT_SUPPORTED"
        result_code = "NO_SUPPORTED_OBSERVED_PATH_ANCHOR"
        failure_code = None

    return {
        "result_generation_version": R5R_EVALUATOR_VERSION,
        "target_id": R5R_TARGET_ID,
        "method_id": R5R_METHOD_ID,
        "method_contract_sha256": R5R_METHOD_CONTRACT_SHA256,
        "design_hash_sha256": R5R_METHOD_DESIGN_SHA256,
        "dataset_id": bound["dataset_id"],
        "dataset_hash": bound["dataset_hash"],
        "vintage_id": bound["vintage_id"],
        "feature_contract_version": bound["feature_contract_version"],
        "joint_chronology_hash": bound["joint_chronology_hash"],
        "joint_row_count": n,
        "window_profile_id": R5R_WINDOW_PROFILE_ID,
        "window_profile_sha256": R5R_WINDOW_PROFILE_SHA256,
        "window_length": width,
        "candidate_domain_id": R5R_CANDIDATE_DOMAIN_ID,
        "candidate_domain_sha256": R5R_CANDIDATE_DOMAIN_SHA256,
        "policy_contract_reference": R5R_POLICY_SCHEMA,
        "policy_contract_sha256": R5R_POLICY_SHA256,
        "tau_T": canonical_rational(TAU_T),
        "tau_L": canonical_rational(TAU_L),
        "tau_S": canonical_rational(TAU_S),
        "horizon_set": list(HORIZONS),
        "chronology_hash_contract_id": R5R_CHRONOLOGY_HASH_CONTRACT,
        "numeric_contract_id": R5R_NUMERIC_CONTRACT,
        "limitations": list(bound.get("limitations") or []),
        "result_status": result_status,
        "result_code": result_code,
        "failure_code": failure_code,
        "OBSERVED_PATH_COMMON_N": common_n,
        "candidates": evaluated,
    }
