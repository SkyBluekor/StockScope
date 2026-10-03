from __future__ import annotations
from typing import Any
from app.macro.r4_contract import GATE_SCHEMA_ID, content_hash, validate_model_use_dossier, validate_theorem_review

MIGRATION={"G0":"NEW","A0":"RETAIN","A1":"RETAIN","A2":"RETAIN","A3":"RETAIN","A4":"REPLACE","A5":"MODIFY","A6":"MODIFY","A7":"REPLACE","A8":"MODIFY","A9":"REPLACE","A10":"REPLACE","G1":"NEW"}


def build_gate_assessment(*, design:dict[str,Any], diagnostic:dict[str,Any], model_use:dict[str,Any]|None, theorem_review:dict[str,Any]|None)->dict[str,Any]:
    gates=[]
    def add(gid,status,reasons=None): gates.append({"gate_id":gid,"migration_action":MIGRATION[gid],"status":status,"rule_id":f"R4_{gid}_V1","evidence_refs":[],"reason_codes":reasons or [],"reviewer_reference":None})
    add("G0","PASS" if diagnostic["scope"]["clean_isolation_certified"] else "BLOCKED", [] if diagnostic["scope"]["clean_isolation_certified"] else ["ISOLATION_NOT_CERTIFIED"])
    for gid in ("A0","A1","A2","A3","A4","A7","A8","A9"): add(gid,"PASS")
    a10_reasons=[x for x in diagnostic.get("failure_codes",[]) if x=="LEGACY_R2_CANONICAL_MISMATCH"]
    calibration=diagnostic["diagnostics"]["new_calibration_contract"]
    expected_calibration={
        "span_set":"ALL_INTEGERS_1_THROUGH_N",
        "span_count":diagnostic["representation"]["n"],
        "covariance_kernel":"PARZEN_COVARIANCE_V1",
        "centering":"FULL_SAMPLE_EMPIRICAL",
        "coupling":"SHARED_GAUSSIAN_VECTOR_PER_REPLICATE",
        "symbolic_contract_verified":True,
        "stochastic_computation_performed":False,
    }
    if calibration != expected_calibration:
        a10_reasons.append("CALIBRATION_CONTRACT_INVALID")
    add("A10","BLOCKED" if a10_reasons else "PASS",a10_reasons)
    model_status, model_reasons, model_hash=validate_model_use_dossier(model_use,diagnostic_hash=diagnostic["semantic_payload_hash"],source_scope_hash=diagnostic["source_scope_hash"])
    a5_reasons=[x for x in model_reasons if x.startswith("STATIONARITY") or x.startswith("MODEL_USE") or x.startswith("FINITE")]
    a6_reasons=[x for x in model_reasons if x.startswith("DEPENDENCE") or x.startswith("MODEL_USE") or x.startswith("FINITE")]
    add("A5","PASS" if model_status=="ASSUMPTION_ACCEPTED_FOR_MODEL_USE" and not a5_reasons else "UNRESOLVED",a5_reasons or ([] if model_status=="ASSUMPTION_ACCEPTED_FOR_MODEL_USE" else ["STATIONARITY_MODEL_USE_UNRESOLVED"]))
    add("A6","PASS" if model_status=="ASSUMPTION_ACCEPTED_FOR_MODEL_USE" and not a6_reasons else "UNRESOLVED",a6_reasons or ([] if model_status=="ASSUMPTION_ACCEPTED_FOR_MODEL_USE" else ["DEPENDENCE_MODEL_USE_UNRESOLVED"]))
    theorem_status,theorem_reasons,theorem_hash=validate_theorem_review(theorem_review,design_hash=design["design_hash"])
    add("G1",theorem_status,theorem_reasons)
    blocked=[g for g in gates if g["status"]!="PASS"]
    base={"schema_id":GATE_SCHEMA_ID,"design_hash":design["design_hash"],"diagnostic_hash":diagnostic["semantic_payload_hash"],"model_use_hash":model_hash,"theorem_review_hash":theorem_hash,"gates":gates,"ga_status":"BLOCKED" if blocked else "PASS","ga_claim_scope":"METHOD_APPROVED_CONDITIONAL_ON_DECLARED_MODEL" if not blocked else "NOT_APPROVED","gb_effect":"NO_AUTOMATIC_PROMOTION","downstream_execution_authorized":False}
    return {**base,"assessment_hash":content_hash(base)}
