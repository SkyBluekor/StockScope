from __future__ import annotations

import json
import re
from typing import Any

from app.macro.r4_contract import (
    EXPECTED_DATASET_HASH,
    EXPECTED_DATASET_ID,
    METHOD_ID,
    TARGET_ID,
    build_design_manifest,
    content_hash,
    require_closed_schema,
    validate_model_use_dossier,
    validate_theorem_review,
)
from app.macro.r4_diagnostic import build_dev_diagnostic
from app.macro.r4_gate import build_gate_assessment

R4C_STAGE_ID = "NEXT-6E-S6A-R4C"
CLEAN_ATTESTATION_SCHEMA_ID = "NEXT6E_S6A_R4C_CLEAN_REPLAY_ATTESTATION_V1"
PHASE_A_SCHEMA_ID = "NEXT6E_S6A_R4C_PHASE_A_RESULT_V1"
FINAL_ASSESSMENT_SCHEMA_ID = "NEXT6E_S6A_R4C_GATE_ASSESSMENT_V1"
ALLOWED_INPUTS = (
    "CLEAN_REPLAY_ATTESTATION",
    "EXPLICIT_FROZEN_DEVELOPMENT",
    "METHOD_DESIGN_MANIFEST",
)
DETERMINISTIC_GATES = ("G0", "A0", "A1", "A2", "A3", "A4", "A7", "A8", "A9", "A10")


class R4CError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _nonblank(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _sha256_text(value: Any) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _git_sha_text(value: Any) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{40}", value) is not None


def validate_clean_attestation(
    value: dict[str, Any],
    *,
    expected_baseline_main_sha: str,
) -> str:
    required = {
        "schema_id", "stage_id", "baseline_main_sha", "method_id", "design_hash",
        "execution_context_id", "input_allowlist_id", "allowed_inputs",
        "development_transport_sha256", "development_dataset_id", "development_canonical_hash",
        "network_accessed", "runtime_db_accessed", "directory_discovery_performed",
        "replacement_dev_used", "holdout_accessed", "adequacy_outputs_accessed",
        "operator_identity", "attestation_reference", "status",
    }
    try:
        require_closed_schema(value, required=required, code="CLEAN_ATTESTATION_INVALID")
    except (TypeError, ValueError) as exc:
        raise R4CError("CLEAN_ATTESTATION_INVALID", str(exc)) from exc

    if not _git_sha_text(expected_baseline_main_sha):
        raise R4CError("CLEAN_ATTESTATION_INVALID", "expected baseline main SHA invalid")

    design = build_design_manifest()
    exact = {
        "schema_id": CLEAN_ATTESTATION_SCHEMA_ID,
        "stage_id": R4C_STAGE_ID,
        "baseline_main_sha": expected_baseline_main_sha,
        "method_id": METHOD_ID,
        "design_hash": design["design_hash"],
        "development_dataset_id": EXPECTED_DATASET_ID,
        "development_canonical_hash": EXPECTED_DATASET_HASH,
        "status": "CLEAN_EXECUTION_ATTESTED",
    }
    for field, expected in exact.items():
        if value.get(field) != expected:
            raise R4CError("CLEAN_ATTESTATION_INVALID", f"{field} mismatch")

    if not _sha256_text(value["development_transport_sha256"]):
        raise R4CError("CLEAN_ATTESTATION_INVALID", "development_transport_sha256 invalid")
    if not _nonblank(value["execution_context_id"]) or not _nonblank(value["input_allowlist_id"]):
        raise R4CError("CLEAN_ATTESTATION_INVALID", "execution context or allowlist id missing")
    if not _nonblank(value["operator_identity"]) or not _nonblank(value["attestation_reference"]):
        raise R4CError("CLEAN_ATTESTATION_INVALID", "operator or attestation reference missing")

    inputs = value["allowed_inputs"]
    if (
        not isinstance(inputs, list)
        or not all(isinstance(item, str) for item in inputs)
        or len(inputs) != len(set(inputs))
        or set(inputs) != set(ALLOWED_INPUTS)
    ):
        raise R4CError("INPUT_NOT_ALLOWLISTED", "allowed_inputs must match the fixed Phase A allowlist")

    forbidden_flags = (
        "network_accessed", "runtime_db_accessed", "directory_discovery_performed",
        "replacement_dev_used", "holdout_accessed", "adequacy_outputs_accessed",
    )
    for field in forbidden_flags:
        if value[field] is not False:
            raise R4CError("CLEAN_ATTESTATION_INVALID", f"{field} must be false")

    return content_hash(value)


def _verify_diagnostic_integrity(diagnostic: dict[str, Any]) -> None:
    semantic = diagnostic.get("semantic_payload_hash")
    scope_hash = diagnostic.get("source_scope_hash")
    if not _sha256_text(semantic) or not _sha256_text(scope_hash):
        raise R4CError("SEALED_EVIDENCE_HASH_MISMATCH", "diagnostic hashes missing or invalid")

    semantic_base = {
        key: val for key, val in diagnostic.items()
        if key not in {"semantic_payload_hash", "source_scope_hash"}
    }
    if content_hash(semantic_base) != semantic:
        raise R4CError("SEALED_EVIDENCE_HASH_MISMATCH", "diagnostic semantic hash mismatch")
    if content_hash(diagnostic.get("scope")) != scope_hash:
        raise R4CError("SEALED_EVIDENCE_HASH_MISMATCH", "source scope hash mismatch")

    source = diagnostic.get("source") or {}
    if source.get("dataset_id") != EXPECTED_DATASET_ID or source.get("canonical_dataset_hash") != EXPECTED_DATASET_HASH:
        raise R4CError("LINEAGE_MISMATCH", "sealed diagnostic dataset identity mismatch")
    if diagnostic.get("scope", {}).get("clean_isolation_certified") is not True:
        raise R4CError("ISOLATION_NOT_CERTIFIED", "sealed diagnostic is not clean-isolation certified")


def build_phase_a_result(
    *,
    development_bytes: bytes,
    attestation: dict[str, Any],
    expected_baseline_main_sha: str,
) -> dict[str, Any]:
    attestation_hash = validate_clean_attestation(
        attestation,
        expected_baseline_main_sha=expected_baseline_main_sha,
    )

    import hashlib
    transport_digest = hashlib.sha256(development_bytes).hexdigest()
    if transport_digest != attestation["development_transport_sha256"]:
        raise R4CError("LINEAGE_MISMATCH", "Development transport digest does not match attestation")

    try:
        dataset = json.loads(development_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise R4CError("LINEAGE_MISMATCH", "Development artifact is not valid UTF-8 JSON") from exc
    if not isinstance(dataset, dict):
        raise R4CError("LINEAGE_MISMATCH", "Development artifact root must be an object")

    design = build_design_manifest()
    diagnostic = build_dev_diagnostic(
        dataset,
        transport_digest=transport_digest,
        design_hash=design["design_hash"],
        input_allowlist_id=attestation["input_allowlist_id"],
        isolation_audit_id=attestation["attestation_reference"],
        clean_isolation_certified=True,
    )
    assessment = build_gate_assessment(
        design=design,
        diagnostic=diagnostic,
        model_use=None,
        theorem_review=None,
    )
    states = {gate["gate_id"]: gate["status"] for gate in assessment["gates"]}
    deterministic = {gate_id: states.get(gate_id, "MISSING") for gate_id in DETERMINISTIC_GATES}
    blocked = [gate_id for gate_id, state in deterministic.items() if state != "PASS"]
    if blocked:
        raise R4CError("PHASE_A_DETERMINISTIC_GATE_BLOCKED", ",".join(blocked))

    base = {
        "schema_id": PHASE_A_SCHEMA_ID,
        "stage_id": R4C_STAGE_ID,
        "baseline_main_sha": expected_baseline_main_sha,
        "method_id": METHOD_ID,
        "target_id": TARGET_ID,
        "design": design,
        "clean_attestation_hash": attestation_hash,
        "development_identity": {
            "dataset_id": EXPECTED_DATASET_ID,
            "canonical_dataset_hash": EXPECTED_DATASET_HASH,
            "transport_sha256": transport_digest,
        },
        "diagnostic": diagnostic,
        "diagnostic_hash": diagnostic["semantic_payload_hash"],
        "source_scope_hash": diagnostic["source_scope_hash"],
        "deterministic_gate_states": deterministic,
        "failure_codes": list(diagnostic.get("failure_codes", [])),
        "phase_a_status": "CLEAN_DIAGNOSTIC_COMPLETE",
    }
    return {**base, "payload_hash": content_hash(base)}


def validate_phase_a_result(
    value: dict[str, Any],
    *,
    expected_baseline_main_sha: str | None = None,
) -> None:
    required = {
        "schema_id", "stage_id", "baseline_main_sha", "method_id", "target_id",
        "design", "clean_attestation_hash", "development_identity", "diagnostic",
        "diagnostic_hash", "source_scope_hash", "deterministic_gate_states",
        "failure_codes", "phase_a_status", "payload_hash",
    }
    try:
        require_closed_schema(value, required=required, code="PHASE_A_SCHEMA_INVALID")
    except (TypeError, ValueError) as exc:
        raise R4CError("PHASE_A_SCHEMA_INVALID", str(exc)) from exc

    if value["schema_id"] != PHASE_A_SCHEMA_ID or value["stage_id"] != R4C_STAGE_ID:
        raise R4CError("PHASE_A_SCHEMA_INVALID", "Phase A version mismatch")
    if not _git_sha_text(value["baseline_main_sha"]):
        raise R4CError("PHASE_A_SCHEMA_INVALID", "baseline main SHA invalid")
    if expected_baseline_main_sha is not None:
        if not _git_sha_text(expected_baseline_main_sha):
            raise R4CError("PHASE_A_SCHEMA_INVALID", "expected baseline main SHA invalid")
        if value["baseline_main_sha"] != expected_baseline_main_sha:
            raise R4CError("PHASE_A_SCHEMA_INVALID", "baseline main mismatch")
    if value["method_id"] != METHOD_ID or value["target_id"] != TARGET_ID:
        raise R4CError("PHASE_A_SCHEMA_INVALID", "method or target mismatch")
    if value["design"] != build_design_manifest():
        raise R4CError("PHASE_A_SCHEMA_INVALID", "design manifest mismatch")
    if value["phase_a_status"] != "CLEAN_DIAGNOSTIC_COMPLETE":
        raise R4CError("PHASE_A_SCHEMA_INVALID", "Phase A is not complete")
    if not _sha256_text(value["clean_attestation_hash"]):
        raise R4CError("PHASE_A_SCHEMA_INVALID", "clean attestation hash invalid")

    sealed_base = {key: val for key, val in value.items() if key != "payload_hash"}
    if content_hash(sealed_base) != value["payload_hash"]:
        raise R4CError("SEALED_EVIDENCE_HASH_MISMATCH", "Phase A payload hash mismatch")

    diagnostic = value["diagnostic"]
    if not isinstance(diagnostic, dict):
        raise R4CError("PHASE_A_SCHEMA_INVALID", "diagnostic must be an object")
    _verify_diagnostic_integrity(diagnostic)
    if value["diagnostic_hash"] != diagnostic["semantic_payload_hash"]:
        raise R4CError("SEALED_EVIDENCE_HASH_MISMATCH", "embedded diagnostic hash mismatch")
    if value["source_scope_hash"] != diagnostic["source_scope_hash"]:
        raise R4CError("SEALED_EVIDENCE_HASH_MISMATCH", "embedded scope hash mismatch")

    identity = value["development_identity"]
    if identity != {
        "dataset_id": EXPECTED_DATASET_ID,
        "canonical_dataset_hash": EXPECTED_DATASET_HASH,
        "transport_sha256": diagnostic["source"]["transport_digest"],
    }:
        raise R4CError("LINEAGE_MISMATCH", "Phase A development identity mismatch")

    states = value["deterministic_gate_states"]
    if not isinstance(states, dict) or set(states) != set(DETERMINISTIC_GATES):
        raise R4CError("PHASE_A_SCHEMA_INVALID", "deterministic gate set mismatch")
    if any(states[gate_id] != "PASS" for gate_id in DETERMINISTIC_GATES):
        raise R4CError("PHASE_A_DETERMINISTIC_GATE_BLOCKED", "deterministic gate not PASS")
    if value["failure_codes"] != diagnostic.get("failure_codes", []):
        raise R4CError("SEALED_EVIDENCE_HASH_MISMATCH", "failure code seal mismatch")
    if value["failure_codes"]:
        raise R4CError("PHASE_A_DETERMINISTIC_GATE_BLOCKED", "Phase A contains active diagnostic blockers")


def approval_binding_status(
    *,
    phase_a_result: dict[str, Any],
    theorem_review: dict[str, Any] | None,
    model_use: dict[str, Any] | None,
) -> dict[str, Any]:
    validate_phase_a_result(phase_a_result)
    design = phase_a_result["design"]
    diagnostic_hash = phase_a_result["diagnostic_hash"]
    source_scope_hash = phase_a_result["source_scope_hash"]

    theorem_status, theorem_reasons, theorem_hash = validate_theorem_review(
        theorem_review, design_hash=design["design_hash"]
    )
    model_status, model_reasons, model_hash = validate_model_use_dossier(
        model_use,
        diagnostic_hash=diagnostic_hash,
        source_scope_hash=source_scope_hash,
    )

    if theorem_review is None:
        checkpoint = "WAITING_FOR_THEOREM_APPROVAL"
    elif theorem_status != "PASS":
        checkpoint = "APPROVAL_BINDING_INVALID"
    elif model_use is None:
        checkpoint = "WAITING_FOR_MODEL_USE_APPROVAL"
    elif model_status != "ASSUMPTION_ACCEPTED_FOR_MODEL_USE":
        checkpoint = "APPROVAL_BINDING_INVALID"
    else:
        checkpoint = "READY_FOR_PHASE_B"

    return {
        "stage_id": R4C_STAGE_ID,
        "phase_a_status": phase_a_result["phase_a_status"],
        "diagnostic_hash": diagnostic_hash,
        "source_scope_hash": source_scope_hash,
        "theorem_review": {
            "status": theorem_status,
            "reason_codes": theorem_reasons,
            "dossier_hash": theorem_hash,
        },
        "model_use": {
            "status": model_status,
            "reason_codes": model_reasons,
            "dossier_hash": model_hash,
        },
        "checkpoint_status": checkpoint,
        "ready_for_phase_b": checkpoint == "READY_FOR_PHASE_B",
        "ga_status": "BLOCKED",
        "downstream_execution_authorized": False,
    }


def build_phase_b_assessment(
    *,
    phase_a_result: dict[str, Any],
    theorem_review: dict[str, Any] | None,
    model_use: dict[str, Any] | None,
) -> dict[str, Any]:
    status = approval_binding_status(
        phase_a_result=phase_a_result,
        theorem_review=theorem_review,
        model_use=model_use,
    )
    if status["checkpoint_status"] != "READY_FOR_PHASE_B":
        code = {
            "WAITING_FOR_THEOREM_APPROVAL": "THEOREM_REVIEW_DOSSIER_MISSING",
            "WAITING_FOR_MODEL_USE_APPROVAL": "MODEL_USE_DOSSIER_MISSING",
        }.get(status["checkpoint_status"], "APPROVAL_BINDING_INVALID")
        raise R4CError(code, status["checkpoint_status"])

    diagnostic = phase_a_result["diagnostic"]
    design = phase_a_result["design"]
    gate = build_gate_assessment(
        design=design,
        diagnostic=diagnostic,
        model_use=model_use,
        theorem_review=theorem_review,
    )
    base = {
        "schema_id": FINAL_ASSESSMENT_SCHEMA_ID,
        "stage_id": R4C_STAGE_ID,
        "phase_a_payload_hash": phase_a_result["payload_hash"],
        "clean_attestation_hash": phase_a_result["clean_attestation_hash"],
        "design_hash": gate["design_hash"],
        "diagnostic_hash": gate["diagnostic_hash"],
        "model_use_hash": gate["model_use_hash"],
        "theorem_review_hash": gate["theorem_review_hash"],
        "gates": gate["gates"],
        "ga_status": gate["ga_status"],
        "ga_claim_scope": gate["ga_claim_scope"],
        "method_state": (
            "METHOD_APPROVED_CONDITIONAL_ON_DECLARED_MODEL"
            if gate["ga_status"] == "PASS"
            else "NOT_APPROVED"
        ),
        "gb_effect": gate["gb_effect"],
        "g_b_state": "NOT_STARTED" if gate["ga_status"] == "PASS" else "BLOCKED",
        "reference_adequacy": "UNRESOLVED",
        "v4_created": False,
        "evaluator_implemented": False,
        "holdout_accessed": False,
        "production_impact": "NONE",
        "downstream_execution_authorized": False,
    }
    return {**base, "assessment_hash": content_hash(base)}
