from __future__ import annotations

from copy import deepcopy

import pytest

from app.macro.calibration_candidate import (
    RATE_SPIKE_FEATURE_IDS,
    build_rate_spike_candidate_set,
    generate_feature_candidates,
    validate_candidate_set_artifact,
)
from app.macro.admissibility_evidence import (
    build_admissibility_evidence,
    render_admissibility_evidence_text,
    validate_admissibility_evidence,
)
from app.macro.eligibility_reconstruction import (
    build_eligibility_reconstruction,
    build_unset_eligibility_policy,
    render_eligibility_reconstruction_text,
    validate_eligibility_reconstruction,
)
from app.macro.reference_stability import (
    MAD_METHOD,
    TAIL_METHOD,
    build_reference_stability_evidence,
    ecdf_sup_drift_for_append,
    render_reference_stability_text,
    validate_reference_stability_evidence,
)
from app.macro.reference_adequacy_protocol import (
    PROTOCOL_STATUS as ADEQUACY_PROTOCOL_STATUS,
    build_reference_adequacy_protocol,
    render_reference_adequacy_protocol_text,
    validate_reference_adequacy_protocol,
)
from app.macro.reference_adequacy_evidence import (
    build_reference_adequacy_evidence,
    render_reference_adequacy_evidence_text,
    validate_reference_adequacy_evidence,
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
from tools.data.build_macro_admissibility_evidence_next6b_s4_2b import (
    build_parser as build_s4_2b_parser,
)
from tools.data.reconstruct_macro_eligibility_next6b_s4_2b1 import (
    build_parser as build_s4_2b1_parser,
)
from tools.data.analyze_macro_reference_stability_next6b_s4_2b15 import (
    build_parser as build_s4_2b15_parser,
)
from tools.data.preregister_macro_reference_adequacy_next6b_s4_2b16 import (
    build_parser as build_s4_2b16_parser,
)
from tools.data.build_macro_reference_adequacy_evidence_next6b_s4_2b16_r21 import (
    build_parser as build_s4_2b16_r21_parser,
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
        family["signal_fraction_display"] == "N/A"
        or family["signal_fraction_display"].endswith("%")
        for family in review["families"]
    )
    assert all(
        family["positive_capture_display"] == "N/A"
        or family["positive_capture_display"].endswith("%")
        for family in review["families"]
    )
    assert any(
        family["signal_fraction_display"].endswith("%")
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


def _s4_2b_inputs():
    development, protocol, research = _inputs()
    diagnostic = build_frontier_admissibility_diagnostic(
        development_dataset=development,
        protocol=protocol,
        research=research,
    )
    return development, protocol, research, diagnostic


def test_s4_2b_evidence_replays_frontier_and_preserves_guardrails():
    development, protocol, research, diagnostic = _s4_2b_inputs()

    evidence = build_admissibility_evidence(
        diagnostic=diagnostic,
        development_dataset=development,
        protocol=protocol,
        research=research,
    )
    state = validate_admissibility_evidence(evidence)

    assert evidence["source"]["diagnostic_hash"] == diagnostic[
        "diagnostic_hash"
    ]
    assert evidence["source"]["source_frontier_hash"] == diagnostic[
        "source_frontier_hash"
    ]
    assert evidence["source"]["replayed_frontier_hash"] == diagnostic[
        "source_frontier_hash"
    ]
    assert evidence["source"]["frontier_replay_verified"] is True
    assert evidence["counts"]["family_count"] == 9
    assert state["family_count"] == 9
    assert len(evidence["evidence_rows"]) == evidence["counts"][
        "compressed_frontier_count"
    ]
    assert state["frontier_group_count"] == len(evidence["evidence_rows"])
    assert all(
        row["episode_start_count"] == row["episode_count"]
        and row["holdout_accessed"] is False
        for row in evidence["evidence_rows"]
    )
    assert evidence["policy_state"] == {
        "admissibility_policy": "UNDEFINED",
        "policy_defined": False,
        "policy_approved": False,
        "event_unit": "UNSET",
        "episode_rate_unit": "UNSET",
        "minimum_sample_unit": "UNSET",
        "evaluation_rule": "UNSET",
        "final_threshold_selected": False,
        "minimum_sample_selected": False,
        "event_unit_selected": False,
        "ready_for_holdout": False,
        "rate_spike_state": "UNCALIBRATED",
    }
    assert evidence["holdout_locked"] is True
    assert evidence["holdout_accessed"] is False
    assert evidence["network_requests"] == 0
    assert evidence["macro_db_writes"] == 0
    assert evidence["production_impact"] == "NONE"


def test_s4_2b_breakpoints_are_observed_frontier_values_only():
    development, protocol, research, diagnostic = _s4_2b_inputs()
    evidence = build_admissibility_evidence(
        diagnostic=diagnostic,
        development_dataset=development,
        protocol=protocol,
        research=research,
    )
    rows_by_hash = {
        row["behavior_group_hash"]: row
        for row in evidence["evidence_rows"]
    }

    for family in evidence["families"]:
        members = [
            rows_by_hash[item]
            for item in family["behavior_group_hashes"]
        ]
        for axis, curve in family["observed_breakpoint_curves"].items():
            observed = sorted(
                {
                    str(row[axis])
                    for row in members
                }
            )
            curve_values = sorted(
                {
                    str(point["value"])
                    for point in curve["points"]
                }
            )
            assert curve_values == observed
            assert curve["source"] == "OBSERVED_FRONTIER_VALUES_ONLY"
            assert curve["invented_grid_points"] == 0


def test_s4_2b_descriptive_quantiles_are_observed_values_not_interpolated():
    development, protocol, research, diagnostic = _s4_2b_inputs()
    evidence = build_admissibility_evidence(
        diagnostic=diagnostic,
        development_dataset=development,
        protocol=protocol,
        research=research,
    )
    rows_by_hash = {
        row["behavior_group_hash"]: row
        for row in evidence["evidence_rows"]
    }

    for family in evidence["families"]:
        members = [
            rows_by_hash[item]
            for item in family["behavior_group_hashes"]
        ]
        for axis, summary in family["descriptive_summaries"].items():
            if not members:
                assert summary["status"] == "NO_VALUES"
                continue
            observed = {str(row[axis]) for row in members}
            assert summary["status"] == "DESCRIPTIVE_ONLY"
            assert summary["quantile_method"] == (
                "OBSERVED_ORDER_STATISTIC_FLOOR_V1"
            )
            assert str(summary["q1"]) in observed
            assert str(summary["median"]) in observed
            assert str(summary["q3"]) in observed


def test_s4_2b_joint_profiles_are_deterministic_and_unranked():
    development, protocol, research, diagnostic = _s4_2b_inputs()

    first = build_admissibility_evidence(
        diagnostic=diagnostic,
        development_dataset=development,
        protocol=protocol,
        research=research,
    )
    second = build_admissibility_evidence(
        diagnostic=diagnostic,
        development_dataset=development,
        protocol=protocol,
        research=research,
    )

    assert first["evidence_hash"] == second["evidence_hash"]
    assert first["evidence_id"] == second["evidence_id"]
    assert [
        item["evidence_family_hash"] for item in first["families"]
    ] == [
        item["evidence_family_hash"] for item in second["families"]
    ]
    assert all(
        profile["rank"] is None
        and profile["score"] is None
        and profile["recommended"] is False
        for family in first["families"]
        for profile in family["exact_joint_profiles"]
    )


def test_s4_2b_rejects_tampered_diagnostic_before_evidence_build():
    development, protocol, research, diagnostic = _s4_2b_inputs()
    tampered = deepcopy(diagnostic)
    tampered["families"][0]["candidate_count"] += 1

    with pytest.raises(ValueError, match="Family diagnostic hash mismatch"):
        build_admissibility_evidence(
            diagnostic=tampered,
            development_dataset=development,
            protocol=protocol,
            research=research,
        )


def test_s4_2b_rejects_valid_but_wrong_frontier_identity():
    development, protocol, research, diagnostic = _s4_2b_inputs()
    mismatched = deepcopy(diagnostic)
    mismatched["source_frontier_hash"] = "f" * 64

    identity_keys = (
        "contract_version",
        "candidate_generation_status",
        "compression_status",
        "diagnostics_status",
        "admissibility_status",
        "ready_for_holdout",
        "development_dataset_hash",
        "protocol_hash",
        "research_hash",
        "holdout_dataset_hash_reference",
        "source_candidate_set_hash",
        "source_frontier_hash",
        "family_payload_hash",
        "feature_payload_hash",
        "admissibility_policy",
        "readiness",
        "event_unit_diagnostics",
        "diagnostic_status",
        "holdout_locked",
        "holdout_accessed",
        "final_candidate_selected",
        "rate_spike_state",
        "production_decision_approved",
    )
    new_hash = content_hash(
        {key: mismatched[key] for key in identity_keys}
    )
    mismatched["diagnostic_hash"] = new_hash
    mismatched["diagnostic_id"] = f"RATEFRONTDIAG-{new_hash[:16]}"

    with pytest.raises(
        ValueError,
        match="Replayed frontier hash differs",
    ):
        build_admissibility_evidence(
            diagnostic=mismatched,
            development_dataset=development,
            protocol=protocol,
            research=research,
        )


def test_s4_2b_render_is_compact_and_review_only():
    development, protocol, research, diagnostic = _s4_2b_inputs()
    evidence = build_admissibility_evidence(
        diagnostic=diagnostic,
        development_dataset=development,
        protocol=protocol,
        research=research,
    )
    rendered = render_admissibility_evidence_text(evidence)

    assert "NEXT-6B-S4.2-B ADMISSIBILITY EVIDENCE MATRIX" in rendered
    assert "Replay Frontier" in rendered
    assert "PASS" in rendered
    assert "Observed breakpoint curves / Exact joint profiles : COMPLETE / COMPLETE" in rendered
    assert "Policy / Event unit / Episode rate unit / Minimum sample unit : UNDEFINED / UNSET / UNSET / UNSET" in rendered
    assert "Evidence status: COMPLETE (no admissibility policy selected)" in rendered


def test_s4_2b_cli_has_no_holdout_or_policy_selection_arguments():
    parser = build_s4_2b_parser()
    option_strings = {
        option
        for action in parser._actions
        for option in action.option_strings
    }

    assert "--diagnostic-artifact" in option_strings
    assert "--development-artifact" in option_strings
    assert "--protocol-artifact" in option_strings
    assert "--research-artifact" in option_strings
    assert "--write-artifact" in option_strings
    assert "--holdout-artifact" not in option_strings
    assert "--select" not in option_strings
    assert "--approve" not in option_strings
    assert "--threshold" not in option_strings
    assert "--maximum-signal-fraction" not in option_strings
    assert "--maximum-positive-capture" not in option_strings
    assert "--maximum-episode-rate" not in option_strings
    assert "--minimum-year-coverage" not in option_strings
    assert "--minimum-sample" not in option_strings
    assert "--event-unit" not in option_strings
    assert "--episode-rate-unit" not in option_strings


def _s4_2b1_inputs():
    development, protocol, research, diagnostic = _s4_2b_inputs()
    evidence = build_admissibility_evidence(
        diagnostic=diagnostic,
        development_dataset=development,
        protocol=protocol,
        research=research,
    )
    return development, protocol, research, diagnostic, evidence


def test_s4_2b1_reconstructs_full_raw_universe_and_legacy_lineage():
    development, protocol, research, diagnostic, evidence = _s4_2b1_inputs()

    reconstruction = build_eligibility_reconstruction(
        development_dataset=development,
        protocol=protocol,
        research=research,
        diagnostic=diagnostic,
        evidence=evidence,
    )
    state = validate_eligibility_reconstruction(reconstruction)

    raw_count = reconstruction["counts"]["raw_candidate_count"]
    assert raw_count == reconstruction["raw_replay"]["raw_candidate_count"]
    assert raw_count == len(reconstruction["legacy_lineage"])
    assert raw_count == len(reconstruction["prior_support_audits"])
    assert state["raw_candidate_count"] == raw_count
    assert reconstruction["raw_replay"]["raw_replay_status"] == "PASS"
    assert reconstruction["counts"]["family_count"] == 9
    assert state["family_count"] == 9

    lineage_hashes = {
        item["candidate_hash"]
        for item in reconstruction["legacy_lineage"]
    }
    audit_hashes = {
        item["candidate_hash"]
        for item in reconstruction["prior_support_audits"]
    }
    assert lineage_hashes == audit_hashes
    assert len(lineage_hashes) == raw_count

    statuses = {
        item["legacy_pipeline_status"]
        for item in reconstruction["legacy_lineage"]
    }
    assert "FINAL_FRONTIER" in statuses
    assert statuses <= {
        "METHOD_LOCAL_DOMINATED",
        "TRIVIAL_DIRECTION_REMOVED",
        "BEHAVIOR_DUPLICATE_GROUPED",
        "CROSS_METHOD_DOMINATED",
        "FINAL_FRONTIER",
    }


def test_s4_2b1_keeps_eligibility_and_admissibility_unselected():
    development, protocol, research, diagnostic, evidence = _s4_2b1_inputs()
    reconstruction = build_eligibility_reconstruction(
        development_dataset=development,
        protocol=protocol,
        research=research,
        diagnostic=diagnostic,
        evidence=evidence,
    )

    assert reconstruction["policy_state"] == {
        "eligibility_policy": build_unset_eligibility_policy(),
        "eligibility_policy_defined": False,
        "minimum_prior_observations_selected": False,
        "admissibility_policy_defined": False,
        "final_candidate_selected": False,
        "ready_for_holdout": False,
        "rate_spike_state": "UNCALIBRATED",
    }
    assert reconstruction["ordering_contract"]["pipeline_order"] == [
        "RAW_CANDIDATE_GENERATION",
        "ELIGIBILITY",
        "ADMISSIBILITY",
        "BEHAVIOR_GROUPING",
        "POLICY_PRESERVING_COMPRESSION",
    ]
    assert reconstruction["ordering_contract"]["admissibility_applied"] is False
    assert reconstruction["ordering_contract"][
        "post_admissibility_compression"
    ] == "NOT_READY"
    assert reconstruction["holdout_locked"] is True
    assert reconstruction["holdout_accessed"] is False
    assert reconstruction["network_requests"] == 0
    assert reconstruction["macro_db_writes"] == 0
    assert reconstruction["production_impact"] == "NONE"


def test_s4_2b1_legacy_derived_support_is_audit_only():
    development, protocol, research, diagnostic, evidence = _s4_2b1_inputs()
    reconstruction = build_eligibility_reconstruction(
        development_dataset=development,
        protocol=protocol,
        research=research,
        diagnostic=diagnostic,
        evidence=evidence,
    )

    assert reconstruction["prior_support_audits"]
    assert all(
        item["legacy_derived_minimum_prior_support"] >= 1
        and item["legacy_support_is_eligibility_enforced"] is False
        and item["legacy_support_is_statistical_precision_guarantee"] is False
        and item["approved_reference_support"] == "UNSET"
        and item["signal_before_reference_policy_count"] == "NOT_EVALUATED"
        for item in reconstruction["prior_support_audits"]
    )

    ept = [
        item
        for item in reconstruction["prior_support_audits"]
        if item["method"] == "EMPIRICAL_POSITIVE_TAIL"
    ]
    adaptive = [
        item
        for item in reconstruction["prior_support_audits"]
        if item["method"] != "EMPIRICAL_POSITIVE_TAIL"
    ]
    assert ept and adaptive
    assert all(item["reference_support_applicable"] is False for item in ept)
    assert all(item["reference_support_applicable"] is True for item in adaptive)


def test_s4_2b1_support_counterfactual_uses_observed_prior_counts_only():
    development, protocol, research, diagnostic, evidence = _s4_2b1_inputs()
    reconstruction = build_eligibility_reconstruction(
        development_dataset=development,
        protocol=protocol,
        research=research,
        diagnostic=diagnostic,
        evidence=evidence,
    )

    for family in reconstruction["families"]:
        curve = family["observed_support_counterfactual"]
        assert curve["source"] == "OBSERVED_PRIOR_COUNTS_ONLY"
        assert curve["algorithm"] == "BISECT_SUFFIX_COUNTS_V1"
        assert curve["invented_grid_points"] == 0
        assert curve["recommended_support"] is None
        if family["method"] == "EMPIRICAL_POSITIVE_TAIL":
            assert curve["status"] == "NOT_APPLICABLE"
            assert curve["reference_support_applicable"] is False
            assert curve["point_count"] == 0
            continue

        assert curve["status"] in {
            "DIAGNOSTIC_ONLY",
            "NO_OBSERVED_PRIOR_COUNTS",
        }
        if curve["status"] == "DIAGNOSTIC_ONLY":
            supports = [
                point["minimum_prior_observations"]
                for point in curve["points"]
            ]
            assert supports == sorted(set(supports))
            observed = {
                int(row["prior_count"])
                for row in research["feature_results"][
                    family["feature_id"]
                ]["expanding"]["rows"]
                if int(row["prior_count"]) > 0
            }
            assert set(supports) <= observed
            assert curve["point_count"] <= len(observed)


def test_s4_2b1_preserves_episode_and_left_boundary_semantics():
    development, protocol, research, diagnostic, evidence = _s4_2b1_inputs()
    reconstruction = build_eligibility_reconstruction(
        development_dataset=development,
        protocol=protocol,
        research=research,
        diagnostic=diagnostic,
        evidence=evidence,
    )
    episode = reconstruction["episode_semantics"]

    assert episode["start_rule"] == "FALSE_OR_UNKNOWN_TO_TRUE"
    assert episode["continue_rule"] == "ADJACENT_OBSERVATION_TRUE"
    assert episode["end_rule"] == "TRUE_TO_FALSE_OR_UNKNOWN"
    assert episode["gap_tolerance_observations"] == 0
    assert episode["event_count_semantics"] == "EPISODE_START"
    assert episode["left_boundary_episode_state_rule"] == "REQUIRE_PRIOR_STATE"
    assert episode["left_boundary_rule_status"] == "DEFINED"
    assert episode["calendar_day_adjacency"] is False


def test_s4_2b1_rejects_tampered_s4_2b_evidence():
    development, protocol, research, diagnostic, evidence = _s4_2b1_inputs()
    tampered = deepcopy(evidence)
    tampered["counts"]["frontier_group_count"] += 1

    with pytest.raises(ValueError):
        build_eligibility_reconstruction(
            development_dataset=development,
            protocol=protocol,
            research=research,
            diagnostic=diagnostic,
            evidence=tampered,
        )


def test_s4_2b1_reconstruction_identity_is_deterministic():
    development, protocol, research, diagnostic, evidence = _s4_2b1_inputs()

    first = build_eligibility_reconstruction(
        development_dataset=development,
        protocol=protocol,
        research=research,
        diagnostic=diagnostic,
        evidence=evidence,
    )
    second = build_eligibility_reconstruction(
        development_dataset=development,
        protocol=protocol,
        research=research,
        diagnostic=diagnostic,
        evidence=evidence,
    )

    assert first["reconstruction_hash"] == second["reconstruction_hash"]
    assert first["reconstruction_id"] == second["reconstruction_id"]
    assert first["raw_candidate_hashes_hash"] == second[
        "raw_candidate_hashes_hash"
    ]
    assert first["lineage_payload_hash"] == second["lineage_payload_hash"]
    assert first["prior_support_audit_payload_hash"] == second[
        "prior_support_audit_payload_hash"
    ]


def test_s4_2b1_render_is_compact_and_policy_free():
    development, protocol, research, diagnostic, evidence = _s4_2b1_inputs()
    reconstruction = build_eligibility_reconstruction(
        development_dataset=development,
        protocol=protocol,
        research=research,
        diagnostic=diagnostic,
        evidence=evidence,
    )
    rendered = render_eligibility_reconstruction_text(reconstruction)

    assert "NEXT-6B-S4.2-B.1 RAW UNIVERSE & ELIGIBILITY AUDIT" in rendered
    assert "Raw Replay / Legacy Lineage / Eligibility Audit : PASS / COMPLETE / COMPLETE" in rendered
    assert "FROZEN_RAW_GENERATION" in rendered
    assert "NOT_READY" in rendered
    assert "Reference Support Policy / Minimum Prior Observations : UNDEFINED / None" in rendered
    assert "Reconstruction status: COMPLETE" in rendered


def test_s4_2b1_cli_has_no_holdout_or_policy_selection_arguments():
    parser = build_s4_2b1_parser()
    option_strings = {
        option
        for action in parser._actions
        for option in action.option_strings
    }

    assert "--development-artifact" in option_strings
    assert "--protocol-artifact" in option_strings
    assert "--research-artifact" in option_strings
    assert "--diagnostic-artifact" in option_strings
    assert "--evidence-artifact" in option_strings
    assert "--write-artifact" in option_strings

    assert "--holdout-artifact" not in option_strings
    assert "--minimum-prior-observations" not in option_strings
    assert "--minimum-event-count" not in option_strings
    assert "--maximum-signal-fraction" not in option_strings
    assert "--maximum-episode-rate" not in option_strings
    assert "--minimum-year-coverage" not in option_strings
    assert "--select" not in option_strings
    assert "--approve" not in option_strings


def _s4_2b15_inputs():
    development, protocol, research, diagnostic, evidence = _s4_2b1_inputs()
    reconstruction = build_eligibility_reconstruction(
        development_dataset=development,
        protocol=protocol,
        research=research,
        diagnostic=diagnostic,
        evidence=evidence,
    )
    return development, protocol, research, reconstruction


def test_s4_2b15_ecdf_sup_drift_matches_bruteforce_observed_support():
    from decimal import Decimal

    prior = [Decimal("-2"), Decimal("0"), Decimal("3"), Decimal("3")]
    added = Decimal("1")
    exact = ecdf_sup_drift_for_append(prior, added)

    old = sorted(prior)
    new = sorted(prior + [added])
    support = sorted(set(old + new))

    def cdf(values, x):
        return Decimal(sum(value <= x for value in values)) / Decimal(len(values))

    brute = max(abs(cdf(old, x) - cdf(new, x)) for x in support)
    assert exact == brute


def test_s4_2b15_builds_six_reference_families_and_three_ept_exclusions():
    development, protocol, research, reconstruction = _s4_2b15_inputs()
    artifact = build_reference_stability_evidence(
        development_dataset=development,
        protocol=protocol,
        research=research,
        reconstruction=reconstruction,
        source_main_sha="test-main-sha",
    )
    state = validate_reference_stability_evidence(artifact)

    assert state["tail_family_count"] == 3
    assert state["mad_family_count"] == 3
    assert state["ept_excluded_family_count"] == 3
    assert len(artifact["families"]) == 6
    assert len(artifact["ept_exclusions"]) == 3
    assert {
        family["method"] for family in artifact["families"]
    } == {TAIL_METHOD, MAD_METHOD}
    assert all(
        item["reference_support_applicable"] is False
        and item["exclusion_reason"]
        == "METHOD_DOES_NOT_USE_EXPANDING_REFERENCE_DISTRIBUTION"
        for item in artifact["ept_exclusions"]
    )


def test_s4_2b15_keeps_selection_and_holdout_guardrails_closed():
    development, protocol, research, reconstruction = _s4_2b15_inputs()
    artifact = build_reference_stability_evidence(
        development_dataset=development,
        protocol=protocol,
        research=research,
        reconstruction=reconstruction,
        source_main_sha="test-main-sha",
    )

    assert artifact["policy_state"] == {
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
    assert artifact["holdout_locked"] is True
    assert artifact["holdout_accessed"] is False
    assert artifact["network_requests"] == 0
    assert artifact["macro_db_writes"] == 0
    assert artifact["production_impact"] == "NONE"
    assert artifact["reference_contract"]["weighted_stability_score"] is None
    assert artifact["reference_contract"]["tail_invented_x_grid_points"] == 0


def test_s4_2b15_transitions_are_strictly_prior_and_deterministic():
    development, protocol, research, reconstruction = _s4_2b15_inputs()
    first = build_reference_stability_evidence(
        development_dataset=development,
        protocol=protocol,
        research=research,
        reconstruction=reconstruction,
        source_main_sha="test-main-sha",
    )
    second = build_reference_stability_evidence(
        development_dataset=development,
        protocol=protocol,
        research=research,
        reconstruction=reconstruction,
        source_main_sha="test-main-sha",
    )

    assert first["stability_hash"] == second["stability_hash"]
    assert first["stability_id"] == second["stability_id"]
    assert first["family_payload_hash"] == second["family_payload_hash"]

    for family in first["families"]:
        assert family["reference_mode"] == "EXPANDING_STRICTLY_PRIOR"
        assert family["recommended_support"] is None
        assert family["minimum_prior_observations"] is None
        for transition in family["transitions"]:
            assert transition["current_observation_excluded"] is True
            assert transition["prior_count_after"] == (
                transition["prior_count_before"] + 1
            )
            assert transition["selection_status"] == "NOT_SELECTED"
            if family["method"] == TAIL_METHOD:
                assert transition["invented_x_grid_points"] == 0


def test_s4_2b15_mad_zero_scale_never_invents_relative_change():
    development, protocol, research, reconstruction = _s4_2b15_inputs()
    artifact = build_reference_stability_evidence(
        development_dataset=development,
        protocol=protocol,
        research=research,
        reconstruction=reconstruction,
        source_main_sha="test-main-sha",
    )

    zero_scale = [
        transition
        for family in artifact["families"]
        if family["method"] == MAD_METHOD
        for transition in family["transitions"]
        if transition["mad_before"] == "0"
    ]
    assert zero_scale
    assert all(
        transition["relative_mad_change"] is None
        and transition["relative_mad_change_status"]
        == "NON_COMPUTABLE_ZERO_SCALE"
        for transition in zero_scale
    )


def test_s4_2b15_common_review_points_are_union_and_direct_states():
    development, protocol, research, reconstruction = _s4_2b15_inputs()
    artifact = build_reference_stability_evidence(
        development_dataset=development,
        protocol=protocol,
        research=research,
        reconstruction=reconstruction,
        source_main_sha="test-main-sha",
    )

    expected = sorted(
        {
            int(point["minimum_prior_observations"])
            for family in reconstruction["families"]
            if family["method"] in {TAIL_METHOD, MAD_METHOD}
            for point in family["observed_support_counterfactual"]["points"]
        }
    )
    actual = [
        int(point["minimum_prior_observations"])
        for point in artifact["common_support_review_points"]
    ]
    assert actual == expected
    assert all(
        len(point["family_states"]) == 6
        and point["selection_status"] == "NOT_SELECTED"
        for point in artifact["common_support_review_points"]
    )


def test_s4_2b15_rejects_tampered_reconstruction():
    development, protocol, research, reconstruction = _s4_2b15_inputs()
    tampered = deepcopy(reconstruction)
    tampered["counts"]["raw_candidate_count"] += 1

    with pytest.raises(ValueError):
        build_reference_stability_evidence(
            development_dataset=development,
            protocol=protocol,
            research=research,
            reconstruction=tampered,
            source_main_sha="test-main-sha",
        )


def test_s4_2b15_render_is_compact_and_policy_free():
    development, protocol, research, reconstruction = _s4_2b15_inputs()
    artifact = build_reference_stability_evidence(
        development_dataset=development,
        protocol=protocol,
        research=research,
        reconstruction=reconstruction,
        source_main_sha="test-main-sha",
    )
    rendered = render_reference_stability_text(artifact)

    assert "NEXT-6B-S4.2-B.1.5 REFERENCE STABILITY EVIDENCE" in rendered
    assert "TAIL 3 / MAD 3 / EPT Excluded 3" in rendered
    assert "UNDEFINED / None / None" in rendered
    assert "no adequacy criterion or support selected" in rendered


def test_s4_2b15_cli_has_no_holdout_or_selection_arguments():
    parser = build_s4_2b15_parser()
    option_strings = {
        option
        for action in parser._actions
        for option in action.option_strings
    }

    assert "--development-artifact" in option_strings
    assert "--protocol-artifact" in option_strings
    assert "--research-artifact" in option_strings
    assert "--reconstruction-artifact" in option_strings
    assert "--write-artifact" in option_strings

    assert "--holdout-artifact" not in option_strings
    assert "--minimum-prior-observations" not in option_strings
    assert "--reference-adequacy-criterion" not in option_strings
    assert "--stability-tolerance" not in option_strings
    assert "--select" not in option_strings
    assert "--approve" not in option_strings



def _s4_2b16_inputs():
    development, protocol, research, reconstruction = _s4_2b15_inputs()
    stability = build_reference_stability_evidence(
        development_dataset=development,
        protocol=protocol,
        research=research,
        reconstruction=reconstruction,
        source_main_sha="test-main-sha",
    )
    return development, protocol, research, reconstruction, stability


def _s4_2b16_protocol():
    development, protocol, research, reconstruction, stability = _s4_2b16_inputs()
    artifact = build_reference_adequacy_protocol(
        development_dataset=development,
        protocol=protocol,
        research=research,
        reconstruction=reconstruction,
        stability=stability,
        source_main_sha="test-main-sha",
    )
    return development, protocol, research, reconstruction, stability, artifact


def test_s4_2b16_v3_reduces_to_three_policy_classes():
    development, protocol, research, reconstruction, stability, artifact = (
        _s4_2b16_protocol()
    )
    state = validate_reference_adequacy_protocol(artifact)

    assert artifact["contract_version"].endswith("_V3")
    assert artifact["policy_origin"] == "DEVELOPMENT_INFORMED"
    assert artifact["research_history"]["development_evidence_already_observed"] is True
    assert artifact["research_history"]["claim_data_blind_forbidden"] is True
    assert artifact["research_history"]["holdout_used_for_protocol_design"] is False
    assert artifact["research_history"]["r2_review"] == "PARTIAL_STRUCTURAL_REDUCTION"

    assert artifact["blockers"] == [
        "TAIL_FORWARD_ENVELOPE_TOLERANCE_UNJUSTIFIED",
        "MAD_FORWARD_ENVELOPE_TOLERANCES_UNJUSTIFIED",
        "VALIDATION_SUFFIX_SUFFICIENCY_UNRESOLVED",
    ]
    assert state["blocker_count"] == 3
    assert state["ready_for_evidence_generation"] is True
    assert state["ready_for_holdout"] is False

    policy = artifact["policy_state"]
    assert policy["reference_adequacy"] == "UNRESOLVED"
    assert policy["minimum_prior_observations"] is None
    assert policy["recommended_support"] is None
    assert policy["ready_for_evidence_generation"] is True
    assert policy["ready_for_b17"] is True
    assert policy["ready_for_b2"] is False
    assert policy["ready_for_holdout"] is False
    assert policy["rate_spike_state"] == "UNCALIBRATED"


def test_s4_2b16_v3_freezes_boundary_anchored_structure():
    *_, artifact = _s4_2b16_protocol()
    contract = artifact["validation_contract"]

    tail = contract["tail"]
    assert tail["local_append"]["role"] == "DIAGNOSTIC_ONLY"
    assert tail["local_append"]["adequacy_gate"] is False
    assert tail["local_append"]["tolerance"] is None
    assert tail["forward_envelope"]["rule"] == "BOUNDARY_ANCHORED_FORWARD_ENVELOPE"
    assert tail["forward_envelope"]["invented_x_grid_points"] == 0
    assert tail["forward_envelope"]["tolerance"]["value"] is None
    assert tail["temporal_perturbation"]["role"] == "OPTIONAL_DIAGNOSTIC_ONLY"
    assert tail["temporal_perturbation"]["adequacy_gate"] is False
    assert tail["temporal_perturbation"]["segment_length"] is None
    assert tail["temporal_perturbation"]["tolerance"] is None

    mad = contract["mad"]
    assert mad["local"]["role"] == "DIAGNOSTIC_ONLY"
    assert mad["local"]["adequacy_gate"] is False
    assert mad["local"]["tolerances"] is None
    assert mad["forward_envelope"]["rule"] == "BOUNDARY_ANCHORED_FORWARD_ENVELOPE"
    assert mad["forward_envelope"]["combination_rule"] == "ALL_AND"
    assert all(
        item["value"] is None and item["status"] == "UNJUSTIFIED"
        for item in mad["forward_envelope"]["tolerances"].values()
    )
    assert mad["temporal_perturbation"]["role"] == "OPTIONAL_DIAGNOSTIC_ONLY"
    assert mad["temporal_perturbation"]["adequacy_gate"] is False
    assert mad["weighted_stability_score"] is None

    sufficiency = contract["evidence_sufficiency"]
    assert sufficiency["violation_policy"] is None
    assert sufficiency["minimum_validation_suffix_transitions"] is None
    assert sufficiency["acceptance_form"] == "MAX_ENVELOPE_WITHIN_APPROVED_TOLERANCE"


def test_s4_2b16_v3_preserves_lineage_and_guardrails():
    development, protocol, research, reconstruction, stability, artifact = (
        _s4_2b16_protocol()
    )
    assert artifact["source"]["reconstruction_hash"] == reconstruction["reconstruction_hash"]
    assert artifact["source"]["reference_stability_hash"] == stability["stability_hash"]
    assert artifact["holdout_locked"] is True
    assert artifact["holdout_accessed"] is False
    assert artifact["network_requests"] == 0
    assert artifact["macro_db_writes"] == 0
    assert artifact["production_impact"] == "NONE"


def test_s4_2b16_v3_rejects_invented_values_or_readiness():
    *_, artifact = _s4_2b16_protocol()

    invented = deepcopy(artifact)
    invented["validation_contract"]["tail"]["forward_envelope"]["tolerance"]["value"] = "0.01"
    with pytest.raises(ValueError, match="tolerance"):
        validate_reference_adequacy_protocol(invented)

    promoted = deepcopy(artifact)
    promoted["validation_contract"]["tail"]["temporal_perturbation"]["adequacy_gate"] = True
    with pytest.raises(ValueError, match="perturbation"):
        validate_reference_adequacy_protocol(promoted)

    premature = deepcopy(artifact)
    premature["policy_state"]["ready_for_b2"] = True
    with pytest.raises(ValueError, match="policy state"):
        validate_reference_adequacy_protocol(premature)


def test_s4_2b16_v3_render_reports_evidence_ready_but_b2_blocked():
    *_, artifact = _s4_2b16_protocol()
    rendered = render_reference_adequacy_protocol_text(artifact)

    assert "REFERENCE ADEQUACY VALIDATION PROTOCOL V3" in rendered
    assert "BOUNDARY_ANCHORED_FORWARD_ENVELOPE" in rendered
    assert "Evidence generation readiness: READY (3 unresolved policy classes)" in rendered
    assert "B.2 readiness: BLOCKED" in rendered
    assert "UNRESOLVED / None / None" in rendered


def test_s4_2b16_cli_has_no_holdout_tolerance_or_selection_arguments():
    parser = build_s4_2b16_parser()
    option_strings = {
        option
        for action in parser._actions
        for option in action.option_strings
    }

    assert "--development-artifact" in option_strings
    assert "--protocol-artifact" in option_strings
    assert "--research-artifact" in option_strings
    assert "--reconstruction-artifact" in option_strings
    assert "--reference-stability-artifact" in option_strings
    assert "--write-artifact" in option_strings
    for forbidden in (
        "--holdout-artifact",
        "--minimum-prior-observations",
        "--tail-tolerance",
        "--mad-tolerance",
        "--validation-suffix",
        "--select",
        "--approve",
    ):
        assert forbidden not in option_strings


def _s4_2b16_r21_inputs():
    development, protocol, research, reconstruction, stability, adequacy = (
        _s4_2b16_protocol()
    )
    return development, protocol, research, reconstruction, stability, adequacy


def test_s4_2b16_r21_builds_complete_unselected_forward_evidence():
    development, protocol, research, reconstruction, stability, adequacy = (
        _s4_2b16_r21_inputs()
    )
    artifact = build_reference_adequacy_evidence(
        development_dataset=development,
        protocol=protocol,
        research=research,
        reconstruction=reconstruction,
        stability=stability,
        adequacy_protocol=adequacy,
        source_main_sha="test-main-sha",
    )
    state = validate_reference_adequacy_evidence(artifact)

    expected_points = [
        int(point["minimum_prior_observations"])
        for point in stability["common_support_review_points"]
    ]
    assert artifact["support_points"] == expected_points
    assert state["common_support_point_count"] == len(expected_points)
    assert artifact["analysis_status"] == "COMPLETE"
    assert artifact["evidence_contract"]["tolerance_selection_performed"] is False
    assert artifact["evidence_contract"]["minimum_n_selection_performed"] is False
    assert artifact["evidence_contract"]["validation_suffix_selection_performed"] is False
    assert artifact["policy_state"]["minimum_prior_observations"] is None
    assert artifact["policy_state"]["ready_for_b2"] is False
    assert artifact["policy_state"]["ready_for_holdout"] is False
    assert artifact["holdout_accessed"] is False
    assert artifact["network_requests"] == 0
    assert artifact["macro_db_writes"] == 0
    assert artifact["production_impact"] == "NONE"


def test_s4_2b16_r21_paths_cover_every_later_reference_state():
    development, protocol, research, reconstruction, stability, adequacy = (
        _s4_2b16_r21_inputs()
    )
    artifact = build_reference_adequacy_evidence(
        development_dataset=development,
        protocol=protocol,
        research=research,
        reconstruction=reconstruction,
        stability=stability,
        adequacy_protocol=adequacy,
        source_main_sha="test-main-sha",
    )

    for family in artifact["families"]:
        assert family["forward_rule"] == "BOUNDARY_ANCHORED_FORWARD_ENVELOPE"
        assert family["adequacy_pass"] == "UNRESOLVED"
        assert family["selection_status"] == "NOT_SELECTED"
        for anchor in family["anchors"]:
            expected = family["max_prior_count"] - anchor["anchor_n"]
            assert anchor["suffix_transition_count"] == expected
            if family["method"] == TAIL_METHOD:
                assert len(anchor["ecdf_sup_distances"]) == expected
                assert family["invented_x_grid_points"] == 0
            else:
                assert len(anchor["absolute_median_shifts"]) == expected
                assert len(anchor["absolute_mad_shifts"]) == expected
                assert len(anchor["relative_mad_shifts"]) == expected


def test_s4_2b16_r21_identity_is_deterministic():
    inputs = _s4_2b16_r21_inputs()
    kwargs = {
        "development_dataset": inputs[0],
        "protocol": inputs[1],
        "research": inputs[2],
        "reconstruction": inputs[3],
        "stability": inputs[4],
        "adequacy_protocol": inputs[5],
        "source_main_sha": "test-main-sha",
    }
    first = build_reference_adequacy_evidence(**kwargs)
    second = build_reference_adequacy_evidence(**kwargs)
    assert first["evidence_hash"] == second["evidence_hash"]
    assert first["evidence_id"] == second["evidence_id"]


def test_s4_2b16_r21_render_stays_policy_free():
    inputs = _s4_2b16_r21_inputs()
    artifact = build_reference_adequacy_evidence(
        development_dataset=inputs[0],
        protocol=inputs[1],
        research=inputs[2],
        reconstruction=inputs[3],
        stability=inputs[4],
        adequacy_protocol=inputs[5],
        source_main_sha="test-main-sha",
    )
    rendered = render_reference_adequacy_evidence_text(artifact)
    assert "BOUNDARY-ANCHORED REFERENCE ADEQUACY EVIDENCE" in rendered
    assert "Tolerance selection   : NOT PERFORMED" in rendered
    assert "Minimum N selection   : NOT PERFORMED" in rendered
    assert "B.2 readiness         : BLOCKED" in rendered
    assert "Holdout readiness     : BLOCKED" in rendered


def test_s4_2b16_r21_cli_has_no_selection_or_holdout_arguments():
    parser = build_s4_2b16_r21_parser()
    option_strings = {
        option
        for action in parser._actions
        for option in action.option_strings
    }
    assert "--reference-adequacy-protocol-artifact" in option_strings
    assert "--write-artifact" in option_strings
    for forbidden in (
        "--holdout-artifact",
        "--minimum-prior-observations",
        "--tail-tolerance",
        "--mad-tolerance",
        "--validation-suffix",
        "--select",
        "--approve",
    ):
        assert forbidden not in option_strings


def test_s4_2b16_r21_tail_distance_matches_direct_ecdf():
    inputs = _s4_2b16_r21_inputs()
    artifact = build_reference_adequacy_evidence(
        development_dataset=inputs[0],
        protocol=inputs[1],
        research=inputs[2],
        reconstruction=inputs[3],
        stability=inputs[4],
        adequacy_protocol=inputs[5],
        source_main_sha="test-main-sha",
    )
    tail_family = next(
        family for family in artifact["families"]
        if family["method"] == TAIL_METHOD
    )
    anchor = tail_family["anchors"][0]
    feature_id = tail_family["feature_id"]
    rows = sorted(
        inputs[2]["feature_results"][feature_id]["expanding"]["rows"],
        key=lambda row: int(row["prior_count"]),
    )
    anchor_n = int(anchor["anchor_n"])
    later_n = anchor_n + 1
    anchor_values = [float(row["value"]) for row in rows[:anchor_n]]
    later_values = [float(row["value"]) for row in rows[:later_n]]
    support = sorted(set(anchor_values + later_values))

    direct = max(
        abs(
            sum(value <= x for value in anchor_values) / anchor_n
            - sum(value <= x for value in later_values) / later_n
        )
        for x in support
    )
    stored = float(anchor["ecdf_sup_distances"][0])
    assert stored == pytest.approx(direct, abs=1e-15)
