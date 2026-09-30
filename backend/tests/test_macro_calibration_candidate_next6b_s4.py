from __future__ import annotations

from copy import deepcopy

import pytest

from app.macro.calibration_candidate import (
    RATE_SPIKE_FEATURE_IDS,
    build_rate_spike_candidate_set,
    generate_feature_candidates,
    validate_candidate_set_artifact,
)
from app.macro.admissibility_review import (
    build_admissibility_review,
    render_admissibility_review_text,
    validate_admissibility_review,
)
from app.macro.candidate_compression import (
    build_compressed_candidate_frontier,
    validate_compressed_frontier_artifact,
)
from app.macro.frontier_admissibility import (
    build_frontier_admissibility_diagnostic,
    build_unset_rate_spike_admissibility_policy,
    classify_positive_capture_for_admissibility,
    validate_frontier_admissibility_diagnostic,
)
from app.macro.calibration_protocol import build_calibration_research_protocol
from app.macro.calibration_research import build_distribution_research
from app.macro.features import MACRO_FEATURE_CONTRACT_VERSION
from app.macro.identity import content_hash
from tools.data.freeze_macro_calibration_candidates_next6b_s4 import (
    build_parser,
)
from tools.data.diagnose_macro_calibration_frontier_next6b_s4_1r import (
    build_parser as build_s4_1r_parser,
)
from tools.data.review_macro_admissibility_next6b_s4_2a import (
    build_parser as build_s4_2a_parser,
)


SERIES = "US_10Y_CONSTANT_MATURITY_YIELD"
DELTA_VALUES = (-3, -1, 0, 1, 2, 3, -2, 4, 5, -4, 6, 7)


def _feature(
    feature_id: str,
    value: str,
    unit: str,
    date: str,
) -> dict[str, object]:
    return {
        "feature_id": feature_id,
        "status": "AVAILABLE",
        "value": value,
        "unit": unit,
        "current_observation_ref": "ref",
        "baseline_observation_ref": None,
        "current_observation_date": date,
        "baseline_observation_date": None,
        "observation_distance": None,
        "calendar_distance_days": None,
        "reason": None,
        "contract_version": MACRO_FEATURE_CONTRACT_VERSION,
    }


def _row(index: int, date: str) -> dict[str, object]:
    delta = DELTA_VALUES[index]
    features = [
        _feature(
            "rate_level_pct",
            f"{2 + index / 10:.1f}",
            "PERCENT",
            date,
        ),
        _feature("delta_bp_1obs", str(delta), "BASIS_POINT", date),
        _feature("delta_bp_5obs", str(delta * 2), "BASIS_POINT", date),
        _feature("delta_bp_10obs", str(delta * 3), "BASIS_POINT", date),
    ]
    feature_set_hash = content_hash(
        {
            "contract_version": MACRO_FEATURE_CONTRACT_VERSION,
            "series_id": SERIES,
            "features": features,
        }
    )
    identity = {
        "split_role": "DEVELOPMENT",
        "series_id": SERIES,
        "vintage_id": "2023-12-29",
        "observation_key": f"KEY-{index}",
        "observation_date": date,
        "normalized_hash": f"{index + 1:064x}",
        "feature_contract_version": MACRO_FEATURE_CONTRACT_VERSION,
        "feature_set_hash": feature_set_hash,
    }
    return {
        **identity,
        "revision_no": 1,
        "time_quality": "DATE_ONLY",
        "historical_pit_eligible": False,
        "features": features,
        "row_hash": content_hash(identity),
    }


def _development_dataset() -> dict[str, object]:
    dates = [
        "2020-01-02",
        "2020-02-03",
        "2020-03-02",
        "2021-01-04",
        "2021-02-01",
        "2021-03-01",
        "2022-01-03",
        "2022-02-01",
        "2022-03-01",
        "2023-01-03",
        "2023-02-01",
        "2023-03-01",
    ]
    rows = [_row(index, date) for index, date in enumerate(dates)]
    manifest = {
        "contract_version": "VN_NEXT6B_S2_CALIBRATION_DATASET_V1",
        "series_id": SERIES,
        "provider": "FRED",
        "provider_series_id": "DGS10",
        "split_role": "DEVELOPMENT",
        "observation_start": dates[0],
        "observation_end": dates[-1],
        "vintage_id": "2023-12-29",
        "source_archive_hash": "a" * 64,
        "source_revision_policy": "LATEST_PUBLISHED_REVISION_WITHIN_FIXED_VINTAGE",
        "feature_contract_version": MACRO_FEATURE_CONTRACT_VERSION,
        "warmup_rule": "MAX_FEATURE_OBSERVATION_DISTANCE",
        "warmup_required": 10,
        "warmup_count": 10,
        "analysis_row_count": len(rows),
        "feature_status_counts": {},
        "time_quality_counts": {"DATE_ONLY": len(rows)},
        "historical_pit_eligible_count": 0,
        "usage_scope": "REFERENCE_RESEARCH_ONLY",
        "limitations": ["HISTORICAL_TIME_NOT_PROVEN"],
        "production_decision_approved": False,
    }
    dataset_hash = content_hash(
        {
            "manifest": manifest,
            "row_hashes": [row["row_hash"] for row in rows],
        }
    )
    return {
        "contract_version": "VN_NEXT6B_S2_CALIBRATION_DATASET_V1",
        "dataset_id": f"MACROCAL-DEV-{dataset_hash[:16]}",
        "dataset_hash": dataset_hash,
        "status": "READY_REFERENCE_RESEARCH",
        "reason": None,
        "split_role": "DEVELOPMENT",
        "manifest": manifest,
        "rows": rows,
        "historical_evaluation_eligible": False,
        "production_decision_approved": False,
    }


def _protocol(development: dict[str, object]) -> dict[str, object]:
    holdout = {
        "status": "READY_REFERENCE_RESEARCH",
        "split_role": "HOLDOUT",
        "dataset_hash": "b" * 64,
        "manifest": {
            "series_id": SERIES,
            "feature_contract_version": MACRO_FEATURE_CONTRACT_VERSION,
            "observation_start": "2024-01-02",
            "observation_end": "2025-12-31",
            "vintage_id": "2025-12-31",
        },
    }
    return build_calibration_research_protocol(
        development_dataset=development,
        holdout_dataset=holdout,
    ).to_dict()


def _inputs():
    development = _development_dataset()
    protocol = _protocol(development)
    research = build_distribution_research(
        development_dataset=development,
        protocol=protocol,
    )
    return development, protocol, research


def test_candidate_thresholds_are_observed_development_breakpoints():
    development, protocol, research = _inputs()
    feature_result = research["feature_results"]["delta_bp_1obs"]

    generated = generate_feature_candidates(
        feature_id="delta_bp_1obs",
        feature_result=feature_result,
        development_dataset_hash=development["dataset_hash"],
        protocol_hash=protocol["protocol_hash"],
        research_hash=research["research_hash"],
    )
    empirical = generated["methods"]["EMPIRICAL_POSITIVE_TAIL"]
    empirical_hashes = set(empirical["generated_candidate_hashes"])
    frozen_and_removed = (
        generated["frozen_candidates"] + generated["dominated_candidates"]
    )
    empirical_candidates = [
        item
        for item in frozen_and_removed
        if item["method"] == "EMPIRICAL_POSITIVE_TAIL"
    ]

    observed_positive = {
        str(value)
        for value in DELTA_VALUES
        if value > 0
    }
    assert empirical["generated_count"] == len(observed_positive)
    assert {
        str(item["candidate_hash"]) for item in empirical_candidates
    } == empirical_hashes
    assert {
        str(item["threshold_value"]) for item in empirical_candidates
    } == observed_positive


def test_candidate_set_excludes_rate_level_and_keeps_holdout_locked():
    development, protocol, research = _inputs()

    candidate_set = build_rate_spike_candidate_set(
        development_dataset=development,
        protocol=protocol,
        research=research,
    )

    assert set(candidate_set["per_feature"]) == set(RATE_SPIKE_FEATURE_IDS)
    assert all(
        candidate["feature_id"] != "rate_level_pct"
        for candidate in candidate_set["frozen_candidates"]
    )
    assert candidate_set["candidate_set_status"] == "FROZEN"
    assert candidate_set["holdout_locked"] is True
    assert candidate_set["holdout_accessed"] is False
    assert candidate_set["final_candidate_selected"] is False
    assert candidate_set["selected_candidate_id"] is None
    assert candidate_set["rate_spike_state"] == "UNCALIBRATED"
    assert candidate_set["normal_labels_created"] == 0
    assert candidate_set["detected_labels_created"] == 0
    assert candidate_set["network_requests"] == 0
    assert candidate_set["macro_db_writes"] == 0
    assert candidate_set["production_decision_approved"] is False
    assert candidate_set["exploration_manifest"][
        "generated_candidate_count"
    ] == (
        candidate_set["exploration_manifest"]["frozen_candidate_count"]
        + candidate_set["exploration_manifest"]["dominated_candidate_count"]
    )


def test_candidate_set_hash_is_deterministic():
    development, protocol, research = _inputs()

    first = build_rate_spike_candidate_set(
        development_dataset=development,
        protocol=protocol,
        research=research,
    )
    second = build_rate_spike_candidate_set(
        development_dataset=development,
        protocol=protocol,
        research=research,
    )

    assert first["candidate_set_hash"] == second["candidate_set_hash"]
    assert first["candidate_set_id"] == second["candidate_set_id"]


def test_tampered_research_is_rejected_before_candidate_generation():
    development, protocol, research = _inputs()
    tampered = deepcopy(research)
    tampered["feature_results"]["delta_bp_1obs"]["summary"]["max"] = "999"

    with pytest.raises(ValueError, match="research_hash"):
        build_rate_spike_candidate_set(
            development_dataset=development,
            protocol=protocol,
            research=tampered,
        )


def test_robust_candidates_require_positive_rate_move_and_nonzero_prior_mad():
    development, protocol, research = _inputs()
    generated = generate_feature_candidates(
        feature_id="delta_bp_1obs",
        feature_result=research["feature_results"]["delta_bp_1obs"],
        development_dataset_hash=development["dataset_hash"],
        protocol_hash=protocol["protocol_hash"],
        research_hash=research["research_hash"],
    )
    candidates = [
        item
        for item in (
            generated["frozen_candidates"]
            + generated["dominated_candidates"]
        )
        if item["method"] == "EXPANDING_ROBUST_MAD"
    ]

    assert candidates
    assert all(
        item["required_condition"] == "PRIOR_MAD_NON_ZERO"
        for item in candidates
    )
    assert all(
        item["direction"] == "UP"
        for item in candidates
    )
    assert all(
        float(item["threshold_value"]) > 0
        for item in candidates
    )


def test_s4_cli_intentionally_has_no_holdout_argument():
    parser = build_parser()
    option_strings = {
        option
        for action in parser._actions
        for option in action.option_strings
    }

    assert "--development-artifact" in option_strings
    assert "--protocol-artifact" in option_strings
    assert "--research-artifact" in option_strings
    assert "--holdout-artifact" not in option_strings


def test_candidate_set_artifact_validator_detects_payload_tampering():
    development, protocol, research = _inputs()
    candidate_set = build_rate_spike_candidate_set(
        development_dataset=development,
        protocol=protocol,
        research=research,
    )

    state = validate_candidate_set_artifact(candidate_set)
    assert state["holdout_accessed"] is False

    tampered = deepcopy(candidate_set)
    if tampered["frozen_candidates"]:
        tampered["frozen_candidates"][0]["development_signal_count"] += 1
        with pytest.raises(ValueError, match="candidate_hash"):
            validate_candidate_set_artifact(tampered)
    else:
        pytest.skip("Synthetic fixture produced no frozen candidates.")


def test_s4_1_compression_replays_v1_and_preserves_holdout_guardrails():
    development, protocol, research = _inputs()
    v1 = build_rate_spike_candidate_set(
        development_dataset=development,
        protocol=protocol,
        research=research,
    )
    frontier = build_compressed_candidate_frontier(
        development_dataset=development,
        protocol=protocol,
        research=research,
    )
    state = validate_compressed_frontier_artifact(frontier)
    manifest = frontier["stage_manifest"]

    assert manifest["raw_candidate_count"] == v1["exploration_manifest"][
        "generated_candidate_count"
    ]
    assert manifest["method_local_pareto_count"] == v1[
        "exploration_manifest"
    ]["frozen_candidate_count"]
    assert manifest["compressed_frontier_count"] <= manifest[
        "method_local_pareto_count"
    ]
    assert state["holdout_accessed"] is False
    assert frontier["holdout_locked"] is True
    assert frontier["holdout_accessed"] is False
    assert frontier["final_candidate_selected"] is False
    assert frontier["minimum_sample_selected"] is False
    assert frontier["rate_spike_state"] == "UNCALIBRATED"
    assert frontier["normal_labels_created"] == 0
    assert frontier["detected_labels_created"] == 0
    assert frontier["network_requests"] == 0
    assert frontier["macro_db_writes"] == 0
    assert frontier["production_decision_approved"] is False

    behavior_hashes = [
        group["behavior_signature_hash"]
        for group in frontier["behavior_groups"]
    ]
    assert len(behavior_hashes) == len(set(behavior_hashes))


def test_s4_1r_capture_diagnostics_have_no_sub_100_percent_cutoff():
    assert classify_positive_capture_for_admissibility("1") == (
        "TRIVIAL_DIRECTION_RULE"
    )
    assert classify_positive_capture_for_admissibility("0.999") == (
        "DIAGNOSTIC_ONLY"
    )
    assert classify_positive_capture_for_admissibility("0.98") == (
        "DIAGNOSTIC_ONLY"
    )
    assert classify_positive_capture_for_admissibility("0.95") == (
        "DIAGNOSTIC_ONLY"
    )


def test_s4_1r_frontier_diagnostic_replays_structure_and_blocks_holdout():
    development, protocol, research = _inputs()
    candidate_set = build_rate_spike_candidate_set(
        development_dataset=development,
        protocol=protocol,
        research=research,
    )
    frontier = build_compressed_candidate_frontier(
        development_dataset=development,
        protocol=protocol,
        research=research,
    )
    diagnostic = build_frontier_admissibility_diagnostic(
        development_dataset=development,
        protocol=protocol,
        research=research,
    )
    state = validate_frontier_admissibility_diagnostic(diagnostic)

    assert diagnostic["source_candidate_set_hash"] == candidate_set[
        "candidate_set_hash"
    ]
    assert diagnostic["source_frontier_hash"] == frontier["frontier_hash"]
    assert diagnostic["compression_manifest"]["raw_candidate_count"] == (
        candidate_set["exploration_manifest"]["generated_candidate_count"]
    )
    assert diagnostic["compression_manifest"][
        "method_local_pareto_count"
    ] == candidate_set["exploration_manifest"]["frozen_candidate_count"]
    assert diagnostic["compression_manifest"][
        "compressed_frontier_count"
    ] == frontier["stage_manifest"]["compressed_frontier_count"]

    assert len(diagnostic["families"]) == 9
    assert state["family_count"] == 9
    assert diagnostic["candidate_generation_status"] == "COMPLETE"
    assert diagnostic["compression_status"] == "COMPRESSION_COMPLETE"
    assert diagnostic["diagnostics_status"] == "COMPLETE"
    assert diagnostic["admissibility_status"] == (
        "ADMISSIBILITY_POLICY_UNDEFINED"
    )
    assert diagnostic["ready_for_holdout"] is False
    assert diagnostic["holdout_locked"] is True
    assert diagnostic["holdout_accessed"] is False
    assert diagnostic["readiness"]["candidate_generation"] == "COMPLETE"
    assert diagnostic["readiness"]["structural_compression"] == "COMPLETE"
    assert diagnostic["readiness"]["behavior_rarity_diagnostics"] == "COMPLETE"
    assert diagnostic["readiness"]["admissibility_policy"] == "UNDEFINED"
    assert diagnostic["readiness"]["ready_for_holdout"] is False
    assert diagnostic["event_unit_diagnostics"]["event_unit"] == "UNSET"
    assert diagnostic["final_candidate_selected"] is False
    assert diagnostic["final_threshold_selected"] is False
    assert diagnostic["minimum_sample_selected"] is False
    assert diagnostic["event_unit_selected"] is False
    assert diagnostic["rate_spike_state"] == "UNCALIBRATED"
    assert diagnostic["normal_labels_created"] == 0
    assert diagnostic["detected_labels_created"] == 0
    assert diagnostic["network_requests"] == 0
    assert diagnostic["macro_db_writes"] == 0
    assert diagnostic["production_decision_approved"] is False


def test_s4_1r_unset_policy_contract_is_explicit():
    policy = build_unset_rate_spike_admissibility_policy()

    assert policy == {
        "contract_version": (
            "VN_NEXT6B_S4_1_RATE_SPIKE_ADMISSIBILITY_POLICY_V1"
        ),
        "policy_id": "RATE_SPIKE_ADMISSIBILITY_UNSET",
        "policy_version": "UNSET",
        "shock_type": "RATE_SPIKE",
        "direction": "UP",
        "event_unit": "UNSET",
        "maximum_signal_fraction": None,
        "maximum_positive_capture": None,
        "maximum_episode_rate": None,
        "minimum_year_coverage": None,
        "minimum_sample": None,
        "evaluation_rule": "UNSET",
        "status": "UNDEFINED",
        "approved": False,
        "production_decision_approved": False,
    }


def test_s4_1r_diagnostic_hash_and_family_hashes_are_deterministic():
    development, protocol, research = _inputs()

    first = build_frontier_admissibility_diagnostic(
        development_dataset=development,
        protocol=protocol,
        research=research,
    )
    second = build_frontier_admissibility_diagnostic(
        development_dataset=development,
        protocol=protocol,
        research=research,
    )

    assert first["diagnostic_hash"] == second["diagnostic_hash"]
    assert first["diagnostic_id"] == second["diagnostic_id"]
    assert [item["family_hash"] for item in first["families"]] == [
        item["family_hash"] for item in second["families"]
    ]


def test_s4_1r_cli_has_no_holdout_or_admissibility_cutoff_arguments():
    parser = build_s4_1r_parser()
    option_strings = {
        option
        for action in parser._actions
        for option in action.option_strings
    }

    assert "--development-artifact" in option_strings
    assert "--protocol-artifact" in option_strings
    assert "--research-artifact" in option_strings
    assert "--write-artifact" in option_strings
    assert "--holdout-artifact" not in option_strings
    assert "--maximum-signal-fraction" not in option_strings
    assert "--maximum-positive-capture" not in option_strings
    assert "--minimum-sample" not in option_strings
    assert "--event-unit" not in option_strings


def test_s4_2a_review_preserves_nine_families_and_guardrails():
    development, protocol, research = _inputs()
    diagnostic = build_frontier_admissibility_diagnostic(
        development_dataset=development,
        protocol=protocol,
        research=research,
    )
    review = build_admissibility_review(diagnostic)
    state = validate_admissibility_review(review)

    assert review["source"]["diagnostic_hash"] == diagnostic[
        "diagnostic_hash"
    ]
    assert review["counts"]["family_count"] == 9
    assert state["family_count"] == 9
    assert sorted(item["family_hash"] for item in review["families"]) == sorted(
        item["family_hash"] for item in diagnostic["families"]
    )
    assert review["holdout_locked"] is True
    assert review["holdout_accessed"] is False
    assert review["network_requests"] == 0
    assert review["macro_db_writes"] == 0
    assert review["production_impact"] == "NONE"
    assert review["policy_state"]["admissibility_policy"] == "UNDEFINED"
    assert review["policy_state"]["event_unit"] == "UNSET"
    assert review["policy_state"]["evaluation_rule"] == "UNSET"
    assert review["policy_state"]["final_threshold_selected"] is False
    assert review["policy_state"]["minimum_sample_selected"] is False
    assert review["policy_state"]["event_unit_selected"] is False
    assert review["policy_state"]["ready_for_holdout"] is False
    assert review["policy_state"]["rate_spike_state"] == "UNCALIBRATED"
    assert all(
        family["observation_status"] == "OBSERVED"
        and family["admissibility_decision"] == "NOT_DEFINED"
        and family["automatic_rejection_count"] == 0
        for family in review["families"]
    )


def test_s4_2a_review_renders_compact_family_comparison():
    development, protocol, research = _inputs()
    diagnostic = build_frontier_admissibility_diagnostic(
        development_dataset=development,
        protocol=protocol,
        research=research,
    )
    review = build_admissibility_review(diagnostic)
    rendered = render_admissibility_review_text(review)

    assert "NEXT-6B-S4.2-A ADMISSIBILITY REVIEW" in rendered
    assert rendered.count("\n1obs") == 3
    assert rendered.count("\n5obs") == 3
    assert rendered.count("\n10obs") == 3
    assert "EPT=EMPIRICAL_POSITIVE_TAIL" in rendered
    assert "TAIL=EXPANDING_POSITIVE_TAIL_FRACTION" in rendered
    assert "MAD=EXPANDING_ROBUST_MAD" in rendered
    assert "Policy / Event unit / Evaluation rule : UNDEFINED / UNSET / UNSET" in rendered
    assert "Review status: REVIEW_REQUIRED" in rendered
    assert all(
        family["signal_fraction_display"].endswith("%")
        and family["positive_capture_display"].endswith("%")
        for family in review["families"]
    )


def test_s4_2a_rejects_tampered_source_diagnostic():
    development, protocol, research = _inputs()
    diagnostic = build_frontier_admissibility_diagnostic(
        development_dataset=development,
        protocol=protocol,
        research=research,
    )
    tampered = deepcopy(diagnostic)
    tampered["families"][0]["candidate_count"] += 1

    with pytest.raises(ValueError, match="Family diagnostic hash mismatch"):
        build_admissibility_review(tampered)


def test_s4_2a_review_hash_is_deterministic():
    development, protocol, research = _inputs()
    diagnostic = build_frontier_admissibility_diagnostic(
        development_dataset=development,
        protocol=protocol,
        research=research,
    )

    first = build_admissibility_review(diagnostic)
    second = build_admissibility_review(diagnostic)

    assert first["review_hash"] == second["review_hash"]
    assert first["review_id"] == second["review_id"]
    assert first["family_review_payload_hash"] == second[
        "family_review_payload_hash"
    ]


def test_s4_2a_cli_is_review_only_and_has_no_policy_or_holdout_inputs():
    parser = build_s4_2a_parser()
    option_strings = {
        option
        for action in parser._actions
        for option in action.option_strings
    }

    assert "--diagnostic-artifact" in option_strings
    assert "--holdout-artifact" not in option_strings
    assert "--select" not in option_strings
    assert "--approve" not in option_strings
    assert "--threshold" not in option_strings
    assert "--max-signal-fraction" not in option_strings
    assert "--minimum-sample" not in option_strings
    assert "--event-unit" not in option_strings
    assert "--write-artifact" not in option_strings
