from __future__ import annotations

import hashlib
import json
from typing import Any

DESIGN_SCHEMA_ID = "NEXT6E_S6A_R4_METHOD_DESIGN_V1"
DIAGNOSTIC_SCHEMA_ID = "NEXT6E_S6A_R4_DEV_DIAGNOSTIC_V1"
MODEL_USE_SCHEMA_ID = "NEXT6E_S6A_R4_MODEL_USE_V1"
THEOREM_REVIEW_SCHEMA_ID = "NEXT6E_S6A_R4_THEOREM_REVIEW_V1"
GATE_SCHEMA_ID = "NEXT6E_S6A_R4_GATE_ASSESSMENT_V1"
METHOD_ID = "NEXT6E_S6A_R4_LATTICE_CDF_PROJECTION_V1"
TARGET_ID = "JOINT_SEQUENTIAL_CDF_AND_FUNCTIONAL_ERROR_COVERAGE_V1"
DESIGN_DOCUMENT_SHA256 = "c3d05f5b8471e17bbe844f6b6aca78f2745ca3e5e58360f18b3af2f010aa08cb"
BASE_MAIN_SHA = "bbee4008fafab86d336c89ea7bb79e2684414554"
R3_REFERENCE_SHA = "57bfe9ba517602e592be4e566d866be59c0616d5"
EXPECTED_DATASET_ID = "MACROCAL-DEV-7c3f6660b3aae03f"
EXPECTED_DATASET_HASH = "7c3f6660b3aae03f46c4a3cd66e6652b56c01fc9ab9a00aea67de8a451cddfc1"
ARITHMETIC_PROFILE_ID = "NEXT6E_S6A_R4_EXACT_DECIMAL_RATIONAL_V1"


class R4ContractError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def content_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def require_closed_schema(value: dict[str, Any], *, required: set[str], optional: set[str] | None = None, code: str) -> None:
    optional = optional or set()
    keys = set(value)
    unknown = keys - required - optional
    missing = required - keys
    if unknown:
        raise R4ContractError(code, f"Unknown fields: {sorted(unknown)}")
    if missing:
        raise R4ContractError(code, f"Missing fields: {sorted(missing)}")


def _nonblank(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def build_design_manifest() -> dict[str, Any]:
    base = {
        "schema_id": DESIGN_SCHEMA_ID,
        "document_sha256": DESIGN_DOCUMENT_SHA256,
        "source_refs": {
            "main_sha": BASE_MAIN_SHA,
            "r3_branch_sha": R3_REFERENCE_SHA,
            "design_path": "docs/StockScope_NEXT6E_S6A_R3_방법론_Blocker_해소_설계_2026-10-03.md",
        },
        "method_id": METHOD_ID,
        "target_id": TARGET_ID,
        "parent_method_id": "NEXT6E_S6A_R1_CONTINUOUS_REGULAR_FUNCTIONAL_ROUTE",
        "migration_mapping": {
            "A0": "RETAIN", "A1": "RETAIN", "A2": "RETAIN", "A3": "RETAIN",
            "A4": "REPLACE", "A5": "MODIFY", "A6": "MODIFY", "A7": "REPLACE",
            "A8": "MODIFY", "A9": "REPLACE", "A10": "REPLACE",
        },
        "domain": {"contract_id": "R2A_CANDIDATE_DOMAIN_V1", "kappa_num": 1, "kappa_den": 10},
        "statistic": {
            "ecdf_rule": "RIGHT_CONTINUOUS_EMPIRICAL_CDF_WITH_TIES",
            "median_rule": "MIDPOINT_OF_Q_MINUS_Q_PLUS_HALF",
            "mad_rule": "RAW_MAD_AROUND_MIDPOINT_MEDIAN",
            "zero_scale_rule": "NON_COMPUTABLE_ZERO_SCALE",
        },
        "calibration": {
            "family": "GAUSSIAN_COVARIANCE_MULTIPLIER_SPAN_ENVELOPE",
            "span_set": "ALL_INTEGERS_1_THROUGH_N",
            "covariance_kernel": "PARZEN_COVARIANCE_V1",
            "centering": "FULL_SAMPLE_EMPIRICAL",
            "coupling": "SHARED_GAUSSIAN_VECTOR_PER_REPLICATE",
        },
        "theorem_conditions": [
            "STRICT_STATIONARITY_SCOPED_MODEL_USE",
            "ALPHA_MIXING_EXISTS_A_GT_15_OVER_2",
            "NONDEGENERATE_GAUSSIAN_ROOT",
            "CRITICAL_QUANTILE_CONTINUITY",
        ],
        "proof_units": ["D1", "D2", "D3", "D4"],
        "status": "DESIGN_SELECTED_NOT_EXECUTION_APPROVED",
    }
    return {**base, "design_hash": content_hash(base)}


def validate_model_use_dossier(value: dict[str, Any] | None, *, diagnostic_hash: str, source_scope_hash: str) -> tuple[str, list[str], str | None]:
    if value is None:
        return "UNRESOLVED", ["MODEL_USE_DOSSIER_MISSING"], None
    required = {
        "schema_id", "method_id", "diagnostic_hash", "source_scope_hash", "stationarity", "dependence",
        "finite_sample_proof_claim", "owner_identity", "reviewer_identity", "authority_reference",
        "approval_reference", "approved_scope", "validity_rule", "revocation_rule", "status",
    }
    require_closed_schema(value, required=required, code="MODEL_USE_SCHEMA_INVALID")
    if value["schema_id"] != MODEL_USE_SCHEMA_ID or value["method_id"] != METHOD_ID:
        return "UNRESOLVED", ["MODEL_USE_VERSION_MISMATCH"], content_hash(value)
    if value["diagnostic_hash"] != diagnostic_hash or value["source_scope_hash"] != source_scope_hash:
        return "UNRESOLVED", ["MODEL_USE_SCOPE_HASH_MISMATCH"], content_hash(value)
    if value["finite_sample_proof_claim"] is not False:
        return "NOT_ACCEPTED", ["FINITE_SAMPLE_PROOF_CLAIM_FORBIDDEN"], content_hash(value)

    reasons: list[str] = []
    identity_fields = ("owner_identity", "reviewer_identity", "authority_reference", "approval_reference", "approved_scope", "validity_rule", "revocation_rule")
    for field in identity_fields:
        if not _nonblank(value[field]):
            reasons.append(f"{field.upper()}_MISSING")

    stationarity_required = {"class", "rationale", "evidence_refs", "contradictions", "dispositions", "decision"}
    dependence_required = {
        "class", "rate", "rationale", "evidence_refs", "contradictions", "dispositions",
        "nondegenerate_root_condition", "quantile_continuity_review", "decision",
    }
    try:
        require_closed_schema(value["stationarity"], required=stationarity_required, code="STATIONARITY_SCHEMA_INVALID")
        require_closed_schema(value["dependence"], required=dependence_required, code="DEPENDENCE_SCHEMA_INVALID")
    except (TypeError, R4ContractError):
        return "UNRESOLVED", ["MODEL_USE_NESTED_SCHEMA_INVALID"], content_hash(value)

    stationarity=value["stationarity"]
    dependence=value["dependence"]
    if stationarity["class"] != "STRICT":
        reasons.append("STATIONARITY_CLASS_INVALID")
    if stationarity["decision"] != "ACCEPTED_FOR_MODEL_USE":
        reasons.append("STATIONARITY_MODEL_USE_UNRESOLVED")
    if not _nonblank(stationarity["rationale"]) or not stationarity["evidence_refs"]:
        reasons.append("STATIONARITY_RATIONALE_OR_EVIDENCE_MISSING")
    if stationarity["contradictions"] and len(stationarity["dispositions"]) < len(stationarity["contradictions"]):
        reasons.append("STATIONARITY_CONTRADICTION_UNDISPOSED")

    if dependence["class"] != "ALPHA_MIXING" or dependence["rate"] != "exists a>15/2":
        reasons.append("DEPENDENCE_CLASS_OR_RATE_INVALID")
    if dependence["decision"] != "ACCEPTED_FOR_MODEL_USE":
        reasons.append("DEPENDENCE_MODEL_USE_UNRESOLVED")
    if not _nonblank(dependence["rationale"]) or not dependence["evidence_refs"]:
        reasons.append("DEPENDENCE_RATIONALE_OR_EVIDENCE_MISSING")
    if not _nonblank(dependence["nondegenerate_root_condition"]):
        reasons.append("DEPENDENCE_ROOT_REVIEW_MISSING")
    if not _nonblank(dependence["quantile_continuity_review"]):
        reasons.append("DEPENDENCE_QUANTILE_REVIEW_MISSING")
    if dependence["contradictions"] and len(dependence["dispositions"]) < len(dependence["contradictions"]):
        reasons.append("DEPENDENCE_CONTRADICTION_UNDISPOSED")

    if value["status"] != "MODEL_USE_ACCEPTED":
        reasons.append("MODEL_USE_STATUS_NOT_ACCEPTED")
    return ("ASSUMPTION_ACCEPTED_FOR_MODEL_USE" if not reasons else "UNRESOLVED", reasons, content_hash(value))

def validate_theorem_review(value: dict[str, Any] | None, *, design_hash: str) -> tuple[str, list[str], str | None]:
    if value is None:
        return "BLOCKED", ["THEOREM_REVIEW_DOSSIER_MISSING"], None
    required = {"schema_id", "method_id", "design_hash", "proof_units", "reviewer_identity", "approval_reference", "unresolved_objections", "status"}
    require_closed_schema(value, required=required, code="THEOREM_REVIEW_SCHEMA_INVALID")
    if value["schema_id"] != THEOREM_REVIEW_SCHEMA_ID or value["method_id"] != METHOD_ID or value["design_hash"] != design_hash:
        return "BLOCKED", ["THEOREM_REVIEW_VERSION_MISMATCH"], content_hash(value)
    reasons = []
    if not _nonblank(value["reviewer_identity"]):
        reasons.append("THEOREM_REVIEWER_MISSING")
    if not _nonblank(value["approval_reference"]):
        reasons.append("THEOREM_APPROVAL_REFERENCE_MISSING")
    proof = value["proof_units"]
    if not isinstance(proof, dict) or set(proof) != {"D1", "D2", "D3", "D4"} or any(proof.get(k) != "APPROVED" for k in ("D1","D2","D3","D4")):
        reasons.append("THEOREM_PROOF_UNIT_UNAPPROVED")
    if value["unresolved_objections"]:
        reasons.append("THEOREM_REVIEW_OBJECTIONS_OPEN")
    if value["status"] != "APPROVED":
        reasons.append("THEOREM_REVIEW_NOT_APPROVED")
    return ("PASS" if not reasons else "BLOCKED", reasons, content_hash(value))

