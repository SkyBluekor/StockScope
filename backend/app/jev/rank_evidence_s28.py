"""S28 strictly read-only explanation of a frozen Scanner research receipt.

This does NOT re-rank, backfill missing conditions, recommend trades, attest a
precommit, or measure predictive quality. Risk multiples are transparent
arithmetic on recorded *reference* prices, not executable order instructions.
"""
from __future__ import annotations

from collections import defaultdict
from math import isfinite
from typing import Any

from app.jev.research_scanner_s24 import SOURCE, ResearchCaptureError, digest

VERSION = "Q7_S28_FROZEN_RANK_EVIDENCE_DIAGNOSTIC_V1"
REQUIRED_SOURCE_MODES = {
    "POSTHOC_TECHNICAL_SMOKE_ONLY",
    "PREMARKET_RESEARCH_CAPTURE",
}


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    num = float(value)
    return num if isfinite(num) else None


def _price_validation(risk: dict[str, Any]) -> dict[str, Any]:
    entry = _number(risk.get("entry_reference_price"))
    invalidation = _number(risk.get("invalidation_price"))
    target = _number(risk.get("target1_price"))
    structural = _number(risk.get("structural_target1_price"))
    result: dict[str, Any] = {
        "status": "REFERENCE_PRICE_UNAVAILABLE",
        "entry_reference_price": entry,
        "invalidation_reference_price": invalidation,
        "target1_reference_price": target,
        "structural_target1_reference_price": structural,
        "target1_cap_applied": risk.get("target1_cap_applied") is True,
        "target1_fallback_used": risk.get("target1_fallback_used") is True,
        "reference_only": risk.get("reference_only"),
        "risk_distance_pct": None,
        "target1_distance_pct": None,
        "target1_r_multiple": None,
        "structural_distance_pct": None,
        "structural_r_multiple": None,
        "engine_rr1": _number(risk.get("rr1")),
        "engine_rr1_consistent": None,
        "invalidation_is_not_an_executed_stop_order": True,
    }
    if entry is None or entry <= 0:
        return result
    if structural is not None and structural > entry:
        result["structural_distance_pct"] = round(
            (structural / entry - 1) * 100, 4,
        )
    if invalidation is None or target is None:
        return result
    if invalidation <= 0 or invalidation >= entry or target <= entry:
        result["status"] = "INVALID_REFERENCE_PRICE_ORDER"
        return result
    risk_amount = entry - invalidation
    ratio = (target - entry) / risk_amount
    result.update({
        "status": "REFERENCE_ARITHMETIC_CHECKED",
        "risk_distance_pct": round(risk_amount / entry * 100, 4),
        "target1_distance_pct": round((target - entry) / entry * 100, 4),
        "target1_r_multiple": round(ratio, 4),
        "engine_rr1_consistent": (
            None if result["engine_rr1"] is None
            else abs(result["engine_rr1"] - ratio) <= 0.025
        ),
    })
    if structural is not None and structural > entry:
        result["structural_r_multiple"] = round(
            (structural - entry) / risk_amount, 4,
        )
    if result["engine_rr1_consistent"] is False:
        result["status"] = "ENGINE_R_MULTIPLE_DISAGREEMENT"
    return result


def _tie_diagnostics(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[row["tie_group"]].append(row)
    result: list[dict[str, Any]] = []
    for group_number in sorted(groups):
        peers = sorted(groups[group_number], key=lambda x: x["display_rank"])
        expected = {x["tie_size"] for x in peers}
        fully_visible = len(expected) == 1 and len(peers) == next(iter(expected))
        group: dict[str, Any] = {
            "tie_group": group_number,
            "declared_size": peers[0]["tie_size"],
            "visible_members": len(peers),
            "codes": [x["code"] for x in peers],
            "first_rank": peers[0]["display_rank"],
            "last_rank": peers[-1]["display_rank"],
            "full_group_visible": fully_visible,
            "strict_superiority_proven": False,
            "winner_selected_for_presentation_only": None,
            "reason": None,
        }
        if not fully_visible:
            group["status"] = "PARTIAL_GROUP_CANNOT_VERIFY"
            result.append(group)
            continue

        if len(peers) == 1:
            okay = (peers[0]["strict_rank"] is True
                    and peers[0]["tie_focus"] is False)
            group["status"] = "SINGLE_STRICT_RANK" if okay else "INCONSISTENT_TIE_METADATA"
            group["reason"] = "다른 후보와의 동률 표시 없음" if okay else "순위 메타데이터 불일치"
            result.append(group)
            continue

        contiguous = all(
            peers[i]["display_rank"] + 1 == peers[i + 1]["display_rank"]
            for i in range(len(peers) - 1)
        )
        breaker_values = {x["tie_breaker"] for x in peers}
        strict_absent = all(x["strict_rank"] is False for x in peers)
        promotion = (
            breaker_values == {"STRUCTURAL_TARGET_NEAREST_PROMOTE"}
        )
        focus = [x for x in peers if x["tie_focus"] is True]
        structural = [
            x for x in peers if x["structural_target_distance_pct"] is not None
        ]
        if promotion:
            best = min(
                structural,
                key=lambda x: (x["structural_target_distance_pct"], x["code"]),
            ) if structural else None
            focus_valid = (
                len(focus) == 1 and best is not None
                and focus[0] is peers[0] and focus[0] is best
                and peers[0]["tie_focus_order"] == 0
                and all(x["tie_focus_order"] == 1 for x in peers[1:])
            )
            code_order_valid = (
                [x["code"] for x in peers[1:]]
                == sorted(x["code"] for x in peers[1:])
            )
            is_valid = contiguous and strict_absent and focus_valid and code_order_valid
            group["status"] = "TIE_NEAREST_STRUCTURE_THEN_CODE" if is_valid else "INCONSISTENT_TIE_METADATA"
            group["winner_selected_for_presentation_only"] = (
                peers[0]["code"] if is_valid else None
            )
            group["reason"] = (
                "동일 우선순위 그룹: 최근 저항까지 가장 가까운 1개를 먼저 표시하고 나머지는 종목코드 순"
                if is_valid else "거리·종목코드·동률 순위 기록 간 불일치"
            )
        else:
            simple = (
                breaker_values == {"CODE_STABLE_ORDER"}
                and not focus
                and all(x["tie_focus_order"] == 0 for x in peers)
                and [x["code"] for x in peers] == sorted(x["code"] for x in peers)
                and not structural
            )
            is_valid = contiguous and strict_absent and simple
            group["status"] = "TIE_CODE_ONLY" if is_valid else "INCONSISTENT_TIE_METADATA"
            group["reason"] = (
                "동률이며 구조 목표 증거가 없어 종목코드로만 순서를 표시"
                if is_valid else "동률 순위 메타데이터 불일치"
            )
        result.append(group)
    return result


def inspect_receipt(receipt: dict[str, Any]) -> dict[str, Any]:
    """Validate a frozen source first; never use reconstructed or invented values."""
    if not isinstance(receipt, dict):
        raise ResearchCaptureError("S28_RECEIPT_NOT_OBJECT")
    supplied_hash = receipt.get("payload_hash")
    if not isinstance(supplied_hash, str) or supplied_hash != digest({
        key: value for key, value in receipt.items() if key != "payload_hash"
    }):
        raise ResearchCaptureError("S28_RECEIPT_PAYLOAD_HASH_MISMATCH")
    if (receipt.get("authority") != SOURCE
            or receipt.get("execution_mode") not in REQUIRED_SOURCE_MODES
            or receipt.get("q7_approval_eligible") is not False
            or receipt.get("production_policy_activation_allowed") is not False):
        raise ResearchCaptureError("S28_RECEIPT_RESEARCH_AUTHORITY_REQUIRED")

    raw_rows = receipt.get("original_scanner_candidates")
    market, day = receipt.get("market_scope"), receipt.get("source_date")
    if not isinstance(raw_rows, list) or not 1 <= len(raw_rows) <= 20:
        raise ResearchCaptureError("S28_RECEIPT_CANDIDATES_INVALID")
    if receipt.get("candidate_count") != len(raw_rows):
        raise ResearchCaptureError("S28_RECEIPT_COUNT_MISMATCH")
    originals = receipt.get("original_strategy_rows")
    if not isinstance(originals, list) or not originals:
        raise ResearchCaptureError("S28_SOURCE_STRATEGY_IDENTITY_MISSING")
    identities = {
        (r.get("strategy_key"), r.get("strategy_version_id"), r.get("definition_hash"))
        for r in originals if isinstance(r, dict)
    }
    if len(identities) != len(originals):
        raise ResearchCaptureError("S28_SOURCE_STRATEGY_IDENTITY_MISSING")

    rows: list[dict[str, Any]] = []
    observed: set[tuple[str, str]] = set()
    for original in raw_rows:
        if not isinstance(original, dict):
            raise ResearchCaptureError("S28_RECEIPT_CANDIDATES_INVALID")
        priority = original.get("priority")
        if not isinstance(priority, dict):
            raise ResearchCaptureError("S28_PRIORITY_MISSING")
        rank, group, size = (
            priority.get("rank"), priority.get("tie_group"), priority.get("tie_size")
        )
        if any(type(v) is not int or v < 1 for v in (rank, group, size)):
            raise ResearchCaptureError("S28_PRIORITY_METADATA_INVALID")
        code = original.get("code")
        if (not isinstance(code, str) or not code
                or original.get("market") != market
                or original.get("data_date") != day
                or (market, code) in observed):
            raise ResearchCaptureError("S28_CANDIDATE_SOURCE_MISMATCH")
        observed.add((market, code))
        if (
            original.get("strategy"),
            original.get("strategy_version_id"),
            original.get("strategy_definition_hash"),
        ) not in identities:
            raise ResearchCaptureError("S28_SOURCE_STRATEGY_IDENTITY_MISMATCH")
        structural_pct = _number(priority.get("structural_target_distance_pct"))
        if structural_pct is not None and structural_pct < 0:
            raise ResearchCaptureError("S28_STRUCTURAL_DISTANCE_INVALID")
        risk_guide = original.get("entry_risk_guide")
        risk_data = risk_guide.get("risk") if isinstance(risk_guide, dict) else {}
        risk_data = risk_data if isinstance(risk_data, dict) else {}
        risk = original.get("risk") or {}
        if not isinstance(risk, dict):
            raise ResearchCaptureError("S28_RISK_STATUS_INVALID")
        rows.append({
            "display_rank": rank,
            "code": code,
            "name": original.get("name"),
            "action": original.get("action"),
            "strategy": original.get("strategy"),
            "strategy_version_id": original.get("strategy_version_id"),
            "risk_status": risk.get("status"),
            "risk_warning": risk.get("warning"),
            "tier": priority.get("tier"),
            "entry_gap_pct": _number(priority.get("entry_gap_pct")),
            "entry_gap_basis": priority.get("entry_gap_basis"),
            "historical_status": priority.get("historical_status"),
            "tie_group": group,
            "tie_size": size,
            "strict_rank": priority.get("strict_rank"),
            "tie_focus": priority.get("tie_focus"),
            "tie_focus_order": priority.get("tie_focus_order"),
            "tie_breaker": priority.get("tie_breaker"),
            "structural_target_distance_pct": structural_pct,
            "structural_target_basis": priority.get("structural_target_basis"),
            "previous_rank_is_same_run_before_sort": priority.get("previous_rank"),
            "same_run_rank_change": priority.get("rank_change"),
            "price_evidence": _price_validation(risk_data),
        })
    rows.sort(key=lambda x: x["display_rank"])
    if [x["display_rank"] for x in rows] != list(range(1, len(rows) + 1)):
        raise ResearchCaptureError("S28_RANK_SEQUENCE_INVALID")
    if receipt.get("entry_candidates") != sum(
        x["action"] == "ENTRY_CANDIDATE" for x in rows
    ):
        raise ResearchCaptureError("S28_ENTRY_COUNT_MISMATCH")

    groups = _tie_diagnostics(rows)
    inconsistent = [
        x["tie_group"] for x in groups
        if x["status"] == "INCONSISTENT_TIE_METADATA"
    ]
    risk_disagreements = [
        x["code"] for x in rows
        if x["price_evidence"]["status"] in (
            "ENGINE_R_MULTIPLE_DISAGREEMENT", "INVALID_REFERENCE_PRICE_ORDER"
        )
    ]
    if inconsistent or risk_disagreements:
        status = "EVIDENCE_INCONSISTENT_REVIEW_REQUIRED"
    else:
        status = "DESCRIPTIVE_DIAGNOSTIC_ONLY"
    return {
        "version": VERSION,
        "status": status,
        "original_payload_hash": supplied_hash,
        "source_date": day,
        "market": market,
        "execution_mode": receipt["execution_mode"],
        "source_has_independent_precommit_proof": False,
        "q7_approval_eligible": False,
        "production_policy_activation_allowed": False,
        "prediction_accuracy_or_uplift_proven": False,
        "orders": 0,
        "runtime_db_writes": 0,
        "network_requests": 0,
        "candidate_count": len(rows),
        "entry_candidates": receipt["entry_candidates"],
        "tie_groups": groups,
        "tie_metadata_inconsistent_groups": inconsistent,
        "risk_formula_review_codes": risk_disagreements,
        "candidates": rows,
        "limitations": [
            "표시 순위는 예측 수익률 순위가 아닙니다.",
            "tie_size>1이면 동일 우선순위 그룹이며 더 높은 번호가 우수함을 뜻하지 않습니다.",
            "구조 저항 거리와 RiskEngine의 실제 Target1은 서로 다를 수 있습니다.",
            "R 값은 분석 시점의 무효화 기준 참고 산술이며 체결·손절 주문이나 기대수익률이 아닙니다.",
            "과거 검증 DATA_UNAVAILABLE 상태를 임의로 통과 처리하지 않습니다.",
            "사후 기술 점검 자료는 Q7 사전 예측 증거로 편입되지 않습니다.",
        ],
    }
