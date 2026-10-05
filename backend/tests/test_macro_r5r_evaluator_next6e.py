from __future__ import annotations

import json
from fractions import Fraction
from pathlib import Path

from app.macro.r5r_evaluator import (
    R5R_CANDIDATE_DOMAIN_SHA256,
    R5R_CHRONOLOGY_HASH_CONTRACT,
    R5R_METHOD_CONTRACT_SHA256,
    R5R_METHOD_DESIGN_SHA256,
    R5R_NUMERIC_CONTRACT,
    R5R_POLICY_SCHEMA,
    R5R_POLICY_SHA256,
    R5R_WINDOW_PROFILE_SHA256,
    TAU_L,
    TAU_S,
    TAU_T,
    canonical_rational,
    ecdf_sup_distance,
    effective_candidate_mapping,
    evaluate_r5r,
    midpoint_mad,
    midpoint_median,
    parse_canonical_rational,
    select_common_n,
    window_length,
)


ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "docs" / "fixtures"


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _policy() -> dict:
    return {
        "schema_id": R5R_POLICY_SCHEMA,
        "semantic_contract_sha256": R5R_POLICY_SHA256,
        "tolerances": {
            "tau_T": {"exact": canonical_rational(TAU_T)},
            "tau_L": {"exact": canonical_rational(TAU_L)},
            "tau_S": {"exact": canonical_rational(TAU_S)},
        },
    }


def _bound(values: list[int]) -> dict:
    rows = [
        {
            "i": index,
            "observation_date": f"2026-01-{index:02d}",
            "features": {
                "delta_bp_1obs": value,
                "delta_bp_5obs": value,
                "delta_bp_10obs": value,
            },
        }
        for index, value in enumerate(values, start=1)
    ]
    n = len(rows)
    return {
        "dataset_id": "SYNTHETIC-R5R",
        "dataset_hash": "a" * 64,
        "vintage_id": "SYNTHETIC",
        "feature_contract_version": "VN_NEXT6B_S1_MACRO_FEATURE_V1",
        "joint_chronology_hash": "b" * 64,
        "joint_row_count": n,
        "window_length": window_length(n),
        "effective_candidate_mapping": effective_candidate_mapping(n),
        "method_contract_sha256": R5R_METHOD_CONTRACT_SHA256,
        "method_design_sha256": R5R_METHOD_DESIGN_SHA256,
        "candidate_domain_sha256": R5R_CANDIDATE_DOMAIN_SHA256,
        "window_profile_sha256": R5R_WINDOW_PROFILE_SHA256,
        "policy_contract_sha256": R5R_POLICY_SHA256,
        "chronology_hash_contract_id": R5R_CHRONOLOGY_HASH_CONTRACT,
        "numeric_contract_id": R5R_NUMERIC_CONTRACT,
        "limitations": [],
        "joint_rows": rows,
    }


def test_hand_derived_primitive_fixtures() -> None:
    fixture = _load("NEXT6E_S6A_R5R_DETERMINISTIC_FIXTURES_V1.json")
    by_id = {item["fixture_id"]: item for item in fixture["fixtures"]}

    odd = by_id["F-A1_ODD_MEDIAN_MAD"]
    assert midpoint_median(odd["input"]) == Fraction(5)
    assert midpoint_mad(odd["input"]) == Fraction(2)

    even = by_id["F-A2_EVEN_MEDIAN_MAD"]
    assert midpoint_median(even["input"]) == Fraction(5)
    assert midpoint_mad(even["input"]) == Fraction(3)

    ties = by_id["F-A3_TIES_MIDPOINT"]
    assert midpoint_median(ties["input"]) == Fraction(5)
    assert midpoint_mad(ties["input"]) == Fraction(5)

    zero = by_id["F-A4_ZERO_MAD"]
    assert midpoint_median(zero["input"]) == Fraction(2)
    assert midpoint_mad(zero["input"]) == 0

    ecdf = by_id["F-A5_EXACT_ECDF_SUP"]["input"]
    assert ecdf_sup_distance(ecdf["anchor"], ecdf["later"]) == Fraction(1, 2)

    location = by_id["F-A6_T_L_S_LOCATION"]["input"]
    anchor_med = midpoint_median(location["anchor"])
    anchor_mad = midpoint_mad(location["anchor"])
    later_med = midpoint_median(location["later"])
    later_mad = midpoint_mad(location["later"])
    assert ecdf_sup_distance(location["anchor"], location["later"]) == Fraction(1, 2)
    assert abs(later_med - anchor_med) / anchor_mad == Fraction(1)
    assert abs(later_mad - anchor_mad) / anchor_mad == Fraction(0)


def test_window_and_candidate_collision_match_hand_fixture() -> None:
    fixture = _load("NEXT6E_S6A_R5R_DETERMINISTIC_FIXTURES_V1.json")
    by_id = {item["fixture_id"]: item for item in fixture["fixtures"]}
    expected = by_id["F-B3_CANDIDATE_COLLISION_N11"]["expected"]

    assert window_length(11) == 2
    assert effective_candidate_mapping(11) == [
        {"j": 2, "N": 2},
        {"j": 4, "N": 3},
        {"j": 6, "N": 4},
        {"j": 8, "N": 5},
        {"j": 10, "N": 6},
        {"j": 11, "N": 7},
        {"j": 13, "N": 8},
        {"j": 15, "N": 9},
        {"j": 17, "N": 10},
    ]
    assert [item["N"] for item in effective_candidate_mapping(11)] == (
        expected["effective_mapped_anchors"]
    )


def test_common_n_selects_earliest_supported_anchor() -> None:
    candidates = [
        {"N": 2, "status": "EXCEEDS_POLICY"},
        {"N": 3, "status": "SUPPORTED_WITHIN_POLICY"},
        {"N": 4, "status": "SUPPORTED_WITHIN_POLICY"},
    ]
    assert select_common_n(candidates) == 3


def test_exact_rational_boundary_matches_br1_fixture() -> None:
    targeted = _load("NEXT6E_S6A_R5R_MUR3_BR1_TARGETED_FIXTURES_V1.json")
    by_id = {item["fixture_id"]: item for item in targeted["fixtures"]}

    equal = by_id["BR1-F03-A_EXACT_EQUALITY_BOUNDARY"]["input"]
    assert parse_canonical_rational(equal["metric"]) <= parse_canonical_rational(
        equal["tolerance"]
    )

    below = by_id["BR1-F03-B_EXACT_DECIMAL_BELOW_ONE_THIRD"]["input"]
    assert parse_canonical_rational(below["metric"]) > parse_canonical_rational(
        below["tolerance"]
    )


def test_zero_mad_blocks_all_candidates() -> None:
    result = evaluate_r5r(_bound([2] * 11), policy=_policy())

    assert result["result_status"] == "BLOCKED"
    assert result["failure_code"] == "NO_COMPUTABLE_APPROVED_ANCHOR"
    assert result["OBSERVED_PATH_COMMON_N"] is None
    assert result["candidates"]
    assert all(item["status"] == "BLOCKED" for item in result["candidates"])
    assert all(
        "ANCHOR_EMPIRICAL_MAD_ZERO" in item["failure_codes"]
        for item in result["candidates"]
    )


def test_latest_state_is_included_and_policy_is_exact() -> None:
    # n=11 => w=2. A02/N=2 has anchor [0, 1].
    # Latest window becomes [1, 20], which must exceed the frozen policy.
    result = evaluate_r5r(
        _bound([0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 20]),
        policy=_policy(),
    )

    first = result["candidates"][0]
    assert first["N"] == 2
    assert first["status"] == "EXCEEDS_POLICY"
    for horizon in ("1", "5", "10"):
        state = first["per_horizon"][horizon]
        assert state["latest_T_EMP"] is not None
        assert state["latest_L_EMP"] is not None
        assert state["latest_S_EMP"] is not None

    assert result["tau_T"] == {"numerator": "1", "denominator": "10"}
    assert result["tau_L"] == {"numerator": "1", "denominator": "2"}
    assert result["tau_S"] == {"numerator": "1", "denominator": "4"}


def test_bound_payload_missing_horizon_fails_closed_without_filtering() -> None:
    bound = _bound(list(range(11)))
    del bound["joint_rows"][4]["features"]["delta_bp_10obs"]

    result = evaluate_r5r(bound, policy=_policy())

    assert result["result_status"] == "BLOCKED"
    assert result["failure_code"] == "MISSING_REQUIRED_HORIZON"
    assert result["candidates"] == []


def test_method_and_policy_identity_mismatch_fail_closed() -> None:
    bound = _bound(list(range(11)))
    bound["method_contract_sha256"] = "0" * 64
    result = evaluate_r5r(bound, policy=_policy())
    assert result["failure_code"] == "METHOD_CONTRACT_MISMATCH"

    bound = _bound(list(range(11)))
    policy = _policy()
    policy["semantic_contract_sha256"] = "0" * 64
    result = evaluate_r5r(bound, policy=policy)
    assert result["failure_code"] == "POLICY_TOLERANCE_UNBOUND"


def test_evaluator_source_has_no_runtime_io_network_or_randomness() -> None:
    source = (
        ROOT / "backend" / "app" / "macro" / "r5r_evaluator.py"
    ).read_text(encoding="utf-8")

    for forbidden in (
        "sqlite3",
        "requests",
        "httpx",
        "urllib",
        "open(",
        "Path(",
        "datetime.now",
        "datetime.utcnow",
        "random.",
        "os.getenv",
    ):
        assert forbidden not in source
