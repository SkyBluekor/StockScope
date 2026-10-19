"""S31-B: inspect *real* frozen Scanner candidates, without exporting market data.

The S6 actual JEV Micro-Canary is SYNTHETIC_ONLY. Its network approval and
successful model call do not authorize KRX-derived real-market disclosure.
This module has no provider, credentials, HTTP, journal or writes. A review
request always returns a provider HOLD; never silently calls a fake or real JEV.
"""
from __future__ import annotations

from typing import Any

from app.jev.rank_evidence_s28 import inspect_receipt
from app.jev.research_scanner_s24 import ResearchCaptureError
from app.jev.scanner_eligibility_s8 import RIGHTS_ACTIONS

VERSION = "JEV_ACT2_S31B_FROZEN_REAL_CANDIDATE_TRIAL_V1"
PERMITTED_MODEL_LABEL = "jev-latest"
UNVERIFIED_RIGHTS = "UNVERIFIED"
BLOCKERS = (
    "EXTERNAL_KRX_DERIVED_DATA_PROCESSING_RIGHTS_UNVERIFIED",
    "TYPESAFE_ACCOUNT_PROCESSING_TERMS_UNVERIFIED",
    "SOURCE_RELEASE_AND_INDEPENDENT_ASOF_UNVERIFIED",
    "REAL_MARKET_PROVIDER_TRIAL_PROTOCOL_NOT_AUTHORIZED",
)
NEXT_EVIDENCE = (
    "KRX 계정에 적용되는 약관/계약 및 파생정보의 외부 AI 처리 허가",
    "TypeSafe 실제 계정의 처리·보관·재위탁 계약 확인",
    "원천 데이터 revision별 공개·가용 시점에 대한 독립 검증",
    "실제 종목 전송 범위·모델·비용을 고정한 별도 승인 프로토콜",
)


def inspect_frozen_candidates(receipt: dict[str, Any], *,
                              limit: int = 5, review: bool = False,
                              model: str | None = None) -> dict[str, Any]:
    """Read-only baseline evidence comparison. No JEV inference occurs here.

    Never infer outward rights from user confirmation or from a receipt hash.
    Fail closed on unexpected policy values or malformed source evidence.
    """
    if type(limit) is not int or not 1 <= limit <= 5:
        raise ResearchCaptureError("S31B_LIMIT_MUST_BE_1_TO_5")
    if review and model != PERMITTED_MODEL_LABEL:
        raise ResearchCaptureError("S31B_PINNED_MODEL_REQUIRED")
    if RIGHTS_ACTIONS.get("KRX_OPEN_API_DERIVED_TYPESAFE_AI") != UNVERIFIED_RIGHTS:
        raise ResearchCaptureError("S31B_RIGHTS_AUTHORITY_CHANGED_MANUAL_REVIEW")
    if RIGHTS_ACTIONS.get("TYPESAFE_ACCOUNT_PROCESSING_CONDITIONS") != UNVERIFIED_RIGHTS:
        raise ResearchCaptureError("S31B_TERMS_AUTHORITY_CHANGED_MANUAL_REVIEW")
    inspected = inspect_receipt(receipt)  # verifies hash, identities, dates, rank
    if inspected["status"] != "DESCRIPTIVE_DIAGNOSTIC_ONLY":
        raise ResearchCaptureError("S31B_SOURCE_EVIDENCE_NEEDS_REVIEW")
    if (receipt.get("trusted_precommit_timestamp_proven") is True
            or receipt.get("independent_capture_timestamp_proven") is True
            or receipt.get("market_publication_timestamp_proven") is True
            or receipt.get("jev_model_calls", 0) != 0):
        raise ResearchCaptureError("S31B_SOURCE_UNTRUSTED_AUTHORITY_CLAIM")
    candidates: list[dict[str, Any]] = []
    entry_rows = [x for x in inspected["candidates"]
                  if x["action"] == "ENTRY_CANDIDATE"]
    if not entry_rows:
        raise ResearchCaptureError("S31B_NO_ENTRY_CANDIDATES")
    raw_by_code = {
        x["code"]: x for x in receipt["original_scanner_candidates"]
    }
    incomplete_groups = {
        x["tie_group"] for x in inspected["tie_groups"]
        if not x["full_group_visible"]
    }
    for item in entry_rows[:limit]:
        raw = raw_by_code[item["code"]]
        conditions = raw.get("conditions")
        conditions_verified = (
            isinstance(conditions, dict)
            and type(conditions.get("passed")) is int
            and type(conditions.get("total")) is int
            and 0 <= conditions["passed"] <= conditions["total"]
            and conditions["total"] > 0
        )
        risk = item["price_evidence"]
        alerts: list[str] = []
        if not conditions_verified:
            alerts.append("BASELINE_CONDITION_TOTAL_UNVERIFIED")
        if item["risk_status"] != "READY" or item["risk_warning"] is not False:
            alerts.append("BASELINE_RISK_RECHECK_REQUIRED")
        if risk["status"] != "REFERENCE_ARITHMETIC_CHECKED":
            alerts.append("BASELINE_REFERENCE_PRICE_RECHECK_REQUIRED")
        if item["historical_status"] in ("DATA_UNAVAILABLE", "NOT_RUN", None):
            alerts.append("HISTORICAL_EVIDENCE_UNAVAILABLE")
        if item["tie_group"] in incomplete_groups:
            alerts.append("DISPLAY_TIE_GROUP_PARTIALLY_OBSERVED")

        # These are deterministic local consistency observations, NOT model
        # opinions. No provider request body is constructed or persisted.
        candidates.append({
            "source": "S27_FROZEN_REAL_SCANNER",
            "analysis_date": inspected["source_date"],
            "code": item["code"],
            "name": item["name"],
            "market": inspected["market"],
            "baseline": {
                "action": item["action"],
                "tier": item["tier"],
                "strategy": item["strategy"],
                "strategy_version_id": item["strategy_version_id"],
                "risk_status": item["risk_status"],
                "risk_warning": item["risk_warning"],
                "conditions_passed": conditions["passed"] if conditions_verified else None,
                "conditions_total": conditions["total"] if conditions_verified else None,
                "historical_status": item["historical_status"],
                "display_rank_not_performance_rank": item["display_rank"],
                "tie_size": item["tie_size"],
            },
            "local_evidence": {
                "check": "SOURCE_READONLY_LOCAL_ONLY",
                "alerts": alerts,
                "risk_reference_status": risk["status"],
                "entry_reference_price": risk["entry_reference_price"],
                "invalidation_reference_price": risk["invalidation_reference_price"],
                "target1_reference_price": risk["target1_reference_price"],
                "target1_r_multiple": risk["target1_r_multiple"],
                "structural_r_multiple": risk["structural_r_multiple"],
            },
            "jev": {
                "status": "NOT_RUN_PROVIDER_HOLD",
                "decision": None,
                "probabilities": None,
                "reason": "실제 종목의 JEV 응답은 아직 없습니다.",
            },
            "baseline_modified": False,
        })
    return {
        "version": VERSION,
        "status": ("REAL_MARKET_JEV_PROVIDER_BLOCKED"
                   if review else "LOCAL_REAL_CANDIDATE_COMPARISON_ONLY"),
        "mode": "review" if review else "inspect",
        "requested_model": model if review else None,
        "source_date": inspected["source_date"],
        "market": inspected["market"],
        "source_execution_mode": inspected["execution_mode"],
        "retrospective_not_prospective": (
            inspected["execution_mode"] == "POSTHOC_TECHNICAL_SMOKE_ONLY"
        ),
        "original_payload_hash": inspected["original_payload_hash"],
        "original_candidate_count": inspected["candidate_count"],
        "original_entry_count": inspected["entry_candidates"],
        "inspected_entry_count": len(candidates),
        "candidates": candidates,
        "source_rights": {
            "derived_typesafe_ai": RIGHTS_ACTIONS["KRX_OPEN_API_DERIVED_TYPESAFE_AI"],
            "typesafe_terms": RIGHTS_ACTIONS["TYPESAFE_ACCOUNT_PROCESSING_CONDITIONS"],
        },
        "blockers": list(BLOCKERS),
        "next_evidence": list(NEXT_EVIDENCE),
        "synthetic_s6_success_does_not_authorize_real_market_data": True,
        "model_results_are_real": False,
        "real_stock_provider_eligible": False,
        "q7_approval_eligible": False,
        "scanner_uplift_proven": False,
        "external_requests": 0,
        "jev_model_calls": 0,
        "orders": 0,
        "production_market_db_writes": 0,
        "production_simulation_db_writes": 0,
        "research_db_writes": 0,
    }
