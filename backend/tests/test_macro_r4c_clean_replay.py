from __future__ import annotations

import copy

import pytest

from app.macro.r4_contract import (
    ARITHMETIC_PROFILE_ID,
    DIAGNOSTIC_SCHEMA_ID,
    EXPECTED_DATASET_HASH,
    EXPECTED_DATASET_ID,
    METHOD_ID,
    MODEL_USE_SCHEMA_ID,
    THEOREM_REVIEW_SCHEMA_ID,
    build_design_manifest,
    content_hash,
)
from app.macro.r4c_replay import (
    ALLOWED_INPUTS,
    CLEAN_ATTESTATION_SCHEMA_ID,
    DETERMINISTIC_GATES,
    PHASE_A_SCHEMA_ID,
    R4C_STAGE_ID,
    R4CError,
    approval_binding_status,
    build_phase_b_assessment,
    validate_clean_attestation,
    validate_phase_a_result,
)

TEST_BASELINE_SHA = "f" * 40


def _attestation():
    design = build_design_manifest()
    return {
        "schema_id": CLEAN_ATTESTATION_SCHEMA_ID,
        "stage_id": R4C_STAGE_ID,
        "baseline_main_sha": TEST_BASELINE_SHA,
        "method_id": METHOD_ID,
        "design_hash": design["design_hash"],
        "execution_context_id": "TEST_CLEAN_CONTEXT",
        "input_allowlist_id": "TEST_ALLOWLIST",
        "allowed_inputs": list(ALLOWED_INPUTS),
        "development_transport_sha256": "c" * 64,
        "development_dataset_id": EXPECTED_DATASET_ID,
        "development_canonical_hash": EXPECTED_DATASET_HASH,
        "network_accessed": False,
        "runtime_db_accessed": False,
        "directory_discovery_performed": False,
        "replacement_dev_used": False,
        "holdout_accessed": False,
        "adequacy_outputs_accessed": False,
        "operator_identity": "TEST_OPERATOR",
        "attestation_reference": "TEST_ATTESTATION",
        "status": "CLEAN_EXECUTION_ATTESTED",
    }


def _synthetic_phase_a():
    design = build_design_manifest()
    scope = {
        "development_only": True,
        "input_allowlist_id": "TEST_ALLOWLIST",
        "isolation_audit_id": "TEST_ATTESTATION",
        "clean_isolation_certified": True,
    }
    diagnostic_base = {
        "schema_id": DIAGNOSTIC_SCHEMA_ID,
        "design_hash": design["design_hash"],
        "source": {
            "dataset_id": EXPECTED_DATASET_ID,
            "canonical_dataset_hash": EXPECTED_DATASET_HASH,
            "canonicalization_version": "STOCKSCOPE_CONTENT_HASH_V1",
            "transport_digest": "c" * 64,
            "native_map_hash": "d" * 64,
        },
        "scope": scope,
        "representation": {"n": 1999},
        "diagnostics": {
            "new_calibration_contract": {
                "span_set": "ALL_INTEGERS_1_THROUGH_N",
                "span_count": 1999,
                "covariance_kernel": "PARZEN_COVARIANCE_V1",
                "centering": "FULL_SAMPLE_EMPIRICAL",
                "coupling": "SHARED_GAUSSIAN_VECTOR_PER_REPLICATE",
                "symbolic_contract_verified": True,
                "stochastic_computation_performed": False,
            }
        },
        "arithmetic_profile_id": ARITHMETIC_PROFILE_ID,
        "computation_status": "COMPLETE",
        "failure_codes": [],
    }
    diagnostic = {
        **diagnostic_base,
        "source_scope_hash": content_hash(scope),
        "semantic_payload_hash": content_hash(diagnostic_base),
    }
    base = {
        "schema_id": PHASE_A_SCHEMA_ID,
        "stage_id": R4C_STAGE_ID,
        "baseline_main_sha": TEST_BASELINE_SHA,
        "method_id": METHOD_ID,
        "target_id": design["target_id"],
        "design": design,
        "clean_attestation_hash": "e" * 64,
        "development_identity": {
            "dataset_id": EXPECTED_DATASET_ID,
            "canonical_dataset_hash": EXPECTED_DATASET_HASH,
            "transport_sha256": "c" * 64,
        },
        "diagnostic": diagnostic,
        "diagnostic_hash": diagnostic["semantic_payload_hash"],
        "source_scope_hash": diagnostic["source_scope_hash"],
        "deterministic_gate_states": {gate: "PASS" for gate in DETERMINISTIC_GATES},
        "failure_codes": [],
        "phase_a_status": "CLEAN_DIAGNOSTIC_COMPLETE",
    }
    return {**base, "payload_hash": content_hash(base)}


def _approved_theorem():
    design = build_design_manifest()
    return {
        "schema_id": THEOREM_REVIEW_SCHEMA_ID,
        "method_id": METHOD_ID,
        "design_hash": design["design_hash"],
        "proof_units": {"D1": "APPROVED", "D2": "APPROVED", "D3": "APPROVED", "D4": "APPROVED"},
        "reviewer_identity": "TEST_REVIEWER",
        "approval_reference": "TEST_THEOREM_APPROVAL",
        "unresolved_objections": [],
        "status": "APPROVED",
    }


def _approved_model(phase_a):
    return {
        "schema_id": MODEL_USE_SCHEMA_ID,
        "method_id": METHOD_ID,
        "diagnostic_hash": phase_a["diagnostic_hash"],
        "source_scope_hash": phase_a["source_scope_hash"],
        "stationarity": {
            "class": "STRICT",
            "rationale": "synthetic test-only scoped working model",
            "evidence_refs": ["TEST_ONLY"],
            "contradictions": [],
            "dispositions": [],
            "decision": "ACCEPTED_FOR_MODEL_USE",
        },
        "dependence": {
            "class": "ALPHA_MIXING",
            "rate": "exists a>15/2",
            "rationale": "synthetic test-only scoped working model",
            "evidence_refs": ["TEST_ONLY"],
            "contradictions": [],
            "dispositions": [],
            "nondegenerate_root_condition": "TEST_ONLY reviewed",
            "quantile_continuity_review": "TEST_ONLY reviewed",
            "decision": "ACCEPTED_FOR_MODEL_USE",
        },
        "finite_sample_proof_claim": False,
        "owner_identity": "TEST_OWNER",
        "reviewer_identity": "TEST_REVIEWER",
        "authority_reference": "TEST_AUTHORITY",
        "approval_reference": "TEST_MODEL_APPROVAL",
        "approved_scope": "SYNTHETIC_TEST_ONLY",
        "validity_rule": "SYNTHETIC_TEST_ONLY",
        "revocation_rule": "SYNTHETIC_TEST_ONLY",
        "status": "MODEL_USE_ACCEPTED",
    }


def test_clean_attestation_accepts_only_fixed_fail_closed_scope():
    value = _attestation()
    assert len(validate_clean_attestation(value, expected_baseline_main_sha=TEST_BASELINE_SHA)) == 64

    for field in (
        "network_accessed",
        "runtime_db_accessed",
        "directory_discovery_performed",
        "replacement_dev_used",
        "holdout_accessed",
        "adequacy_outputs_accessed",
    ):
        bad = copy.deepcopy(value)
        bad[field] = True
        with pytest.raises(R4CError) as exc:
            validate_clean_attestation(bad, expected_baseline_main_sha=TEST_BASELINE_SHA)
        assert exc.value.code == "CLEAN_ATTESTATION_INVALID"


def test_clean_attestation_rejects_unknown_field_wrong_baseline_and_allowlist():
    bad = _attestation()
    bad["extra"] = 1
    with pytest.raises(R4CError) as exc:
        validate_clean_attestation(bad, expected_baseline_main_sha=TEST_BASELINE_SHA)
    assert exc.value.code == "CLEAN_ATTESTATION_INVALID"

    bad = _attestation()
    bad["baseline_main_sha"] = "0" * 40
    with pytest.raises(R4CError) as exc:
        validate_clean_attestation(bad, expected_baseline_main_sha=TEST_BASELINE_SHA)
    assert exc.value.code == "CLEAN_ATTESTATION_INVALID"

    bad = _attestation()
    bad["allowed_inputs"].append("HOLDOUT")
    with pytest.raises(R4CError) as exc:
        validate_clean_attestation(bad, expected_baseline_main_sha=TEST_BASELINE_SHA)
    assert exc.value.code == "INPUT_NOT_ALLOWLISTED"


def test_phase_a_seal_detects_tampering_and_can_bind_expected_checkout():
    phase_a = _synthetic_phase_a()
    validate_phase_a_result(phase_a, expected_baseline_main_sha=TEST_BASELINE_SHA)

    with pytest.raises(R4CError) as exc:
        validate_phase_a_result(phase_a, expected_baseline_main_sha="0" * 40)
    assert exc.value.code == "PHASE_A_SCHEMA_INVALID"

    tampered = copy.deepcopy(phase_a)
    tampered["diagnostic"]["representation"]["n"] = 2000
    with pytest.raises(R4CError) as exc:
        validate_phase_a_result(tampered)
    assert exc.value.code == "SEALED_EVIDENCE_HASH_MISMATCH"


def test_checkpoint_distinguishes_missing_external_approvals():
    phase_a = _synthetic_phase_a()

    status = approval_binding_status(
        phase_a_result=phase_a,
        theorem_review=None,
        model_use=None,
    )
    assert status["checkpoint_status"] == "WAITING_FOR_THEOREM_APPROVAL"
    assert status["ga_status"] == "BLOCKED"

    status = approval_binding_status(
        phase_a_result=phase_a,
        theorem_review=_approved_theorem(),
        model_use=None,
    )
    assert status["checkpoint_status"] == "WAITING_FOR_MODEL_USE_APPROVAL"
    assert status["ga_status"] == "BLOCKED"


def test_hash_mismatch_blocks_model_use_binding():
    phase_a = _synthetic_phase_a()
    model = _approved_model(phase_a)
    model["diagnostic_hash"] = "0" * 64

    status = approval_binding_status(
        phase_a_result=phase_a,
        theorem_review=_approved_theorem(),
        model_use=model,
    )
    assert status["checkpoint_status"] == "APPROVAL_BINDING_INVALID"
    assert "MODEL_USE_SCOPE_HASH_MISMATCH" in status["model_use"]["reason_codes"]

    with pytest.raises(R4CError) as exc:
        build_phase_b_assessment(
            phase_a_result=phase_a,
            theorem_review=_approved_theorem(),
            model_use=model,
        )
    assert exc.value.code == "APPROVAL_BINDING_INVALID"


def test_synthetic_phase_b_can_pass_ga_without_authorizing_downstream():
    phase_a = _synthetic_phase_a()
    result = build_phase_b_assessment(
        phase_a_result=phase_a,
        theorem_review=_approved_theorem(),
        model_use=_approved_model(phase_a),
    )

    assert result["ga_status"] == "PASS"
    assert result["method_state"] == "METHOD_APPROVED_CONDITIONAL_ON_DECLARED_MODEL"
    assert result["g_b_state"] == "NOT_STARTED"
    assert result["reference_adequacy"] == "UNRESOLVED"
    assert result["v4_created"] is False
    assert result["evaluator_implemented"] is False
    assert result["holdout_accessed"] is False
    assert result["production_impact"] == "NONE"
    assert result["downstream_execution_authorized"] is False
    assert len(result["assessment_hash"]) == 64
