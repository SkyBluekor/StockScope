from __future__ import annotations

from app.macro.r4_contract import (
    METHOD_ID,
    MODEL_USE_SCHEMA_ID,
    THEOREM_REVIEW_SCHEMA_ID,
    build_design_manifest,
)
from tools.data.preflight_macro_r4_approval import run_preflight


def _theorem_template():
    design = build_design_manifest()
    return {
        "schema_id": THEOREM_REVIEW_SCHEMA_ID,
        "method_id": METHOD_ID,
        "design_hash": design["design_hash"],
        "proof_units": {"D1": "UNRESOLVED", "D2": "UNRESOLVED", "D3": "UNRESOLVED", "D4": "UNRESOLVED"},
        "reviewer_identity": "",
        "approval_reference": "",
        "unresolved_objections": [],
        "status": "UNRESOLVED",
    }


def _model_template():
    return {
        "schema_id": MODEL_USE_SCHEMA_ID,
        "method_id": METHOD_ID,
        "diagnostic_hash": "<CLEAN_REPLAY_DIAGNOSTIC_HASH>",
        "source_scope_hash": "<CLEAN_REPLAY_SOURCE_SCOPE_HASH>",
        "stationarity": {
            "class": "STRICT",
            "rationale": "",
            "evidence_refs": [],
            "contradictions": [],
            "dispositions": [],
            "decision": "UNRESOLVED",
        },
        "dependence": {
            "class": "ALPHA_MIXING",
            "rate": "exists a>15/2",
            "rationale": "",
            "evidence_refs": [],
            "contradictions": [],
            "dispositions": [],
            "nondegenerate_root_condition": "",
            "quantile_continuity_review": "",
            "decision": "UNRESOLVED",
        },
        "finite_sample_proof_claim": False,
        "owner_identity": "",
        "reviewer_identity": "",
        "authority_reference": "",
        "approval_reference": "",
        "approved_scope": "",
        "validity_rule": "",
        "revocation_rule": "",
        "status": "UNRESOLVED",
    }


def test_r4b_no_dossiers_is_review_ready_but_gate_blocked():
    result = run_preflight(
        theorem_review=None,
        model_use=None,
        expected_diagnostic_hash=None,
        expected_source_scope_hash=None,
    )
    assert result["ready_for_external_review"] is True
    assert result["theorem_review"]["status"] == "BLOCKED"
    assert result["model_use"]["status"] == "UNRESOLVED"
    assert result["formal_clean_replay_executed"] is False
    assert result["ga_status"] == "BLOCKED"
    assert result["downstream_execution_authorized"] is False


def test_unapproved_templates_never_count_as_approval():
    result = run_preflight(
        theorem_review=_theorem_template(),
        model_use=_model_template(),
        expected_diagnostic_hash=None,
        expected_source_scope_hash=None,
    )
    assert result["theorem_review"]["status"] == "BLOCKED"
    assert "THEOREM_PROOF_UNIT_UNAPPROVED" in result["theorem_review"]["reason_codes"]
    assert result["model_use"]["status"] == "UNRESOLVED"
    assert result["model_use"]["reason_codes"] == ["CLEAN_DIAGNOSTIC_BINDING_REQUIRED"]
    assert result["approval_inputs_ready_for_clean_gate_assessment"] is False
    assert result["ga_status"] == "BLOCKED"


def test_even_valid_approval_inputs_do_not_make_preflight_grant_ga():
    design = build_design_manifest()
    diagnostic_hash = "a" * 64
    scope_hash = "b" * 64
    theorem = {
        "schema_id": THEOREM_REVIEW_SCHEMA_ID,
        "method_id": METHOD_ID,
        "design_hash": design["design_hash"],
        "proof_units": {"D1": "APPROVED", "D2": "APPROVED", "D3": "APPROVED", "D4": "APPROVED"},
        "reviewer_identity": "TEST_REVIEWER",
        "approval_reference": "TEST_APPROVAL",
        "unresolved_objections": [],
        "status": "APPROVED",
    }
    model = {
        "schema_id": MODEL_USE_SCHEMA_ID,
        "method_id": METHOD_ID,
        "diagnostic_hash": diagnostic_hash,
        "source_scope_hash": scope_hash,
        "stationarity": {
            "class": "STRICT",
            "rationale": "synthetic contract test only",
            "evidence_refs": ["TEST"],
            "contradictions": [],
            "dispositions": [],
            "decision": "ACCEPTED_FOR_MODEL_USE",
        },
        "dependence": {
            "class": "ALPHA_MIXING",
            "rate": "exists a>15/2",
            "rationale": "synthetic contract test only",
            "evidence_refs": ["TEST"],
            "contradictions": [],
            "dispositions": [],
            "nondegenerate_root_condition": "synthetic reviewed",
            "quantile_continuity_review": "synthetic reviewed",
            "decision": "ACCEPTED_FOR_MODEL_USE",
        },
        "finite_sample_proof_claim": False,
        "owner_identity": "TEST_OWNER",
        "reviewer_identity": "TEST_REVIEWER",
        "authority_reference": "TEST_AUTHORITY",
        "approval_reference": "TEST_APPROVAL",
        "approved_scope": "SYNTHETIC_TEST_ONLY",
        "validity_rule": "SYNTHETIC_TEST_ONLY",
        "revocation_rule": "SYNTHETIC_TEST_ONLY",
        "status": "MODEL_USE_ACCEPTED",
    }

    result = run_preflight(
        theorem_review=theorem,
        model_use=model,
        expected_diagnostic_hash=diagnostic_hash,
        expected_source_scope_hash=scope_hash,
    )
    assert result["theorem_review"]["status"] == "PASS"
    assert result["model_use"]["status"] == "ASSUMPTION_ACCEPTED_FOR_MODEL_USE"
    assert result["approval_inputs_ready_for_clean_gate_assessment"] is True
    assert result["formal_clean_replay_executed"] is False
    assert result["ga_status"] == "BLOCKED"
    assert result["downstream_execution_authorized"] is False
