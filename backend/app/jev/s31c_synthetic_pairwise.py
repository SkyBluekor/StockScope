"""S31-C: paired synthetic decision diagnostics over already recorded S6 calls.

Never execute a model, infer stock outcomes, or pool different model/protocol
cohorts. The comparison baseline is the S6 authored ENTRY_CANDIDATE assumption,
NOT a production Scanner execution. Synthetic labels are not investment truth.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from math import isfinite
from typing import Any

from app.jev.decision_reviewer_micro_canary import (
    CASES, CHOICES, PROVIDER_ID, synthetic_projection,
)

VERSION = "JEV_ACT2_S31C_SYNTHETIC_PAIRED_EVIDENCE_V1"
_BASELINE = "PASS_THROUGH"
_GOLDS = {case["id"]: case["gold"] for case in CASES}
_CASE_IDS = set(_GOLDS)


def _reason(row: dict[str, Any]) -> str | None:
    """Re-check journal provenance against CURRENT authored S6 fixtures."""
    if row.get("state") != "VALID":
        return "ACTUAL_PROVIDER_RESPONSE_NOT_VALID"
    case_id = row.get("case_id")
    if case_id not in _CASE_IDS:
        return "CASE_NOT_IN_CURRENT_FROZEN_SYNTHETIC_SET"
    if (row.get("expected_gold") != _GOLDS[case_id]
            or row.get("input_hash") != synthetic_projection(case_id)["input_hash"]):
        return "CASE_LABEL_OR_INPUT_IDENTITY_MISMATCH"
    if row.get("provider_id") != PROVIDER_ID:
        return "PROVIDER_IDENTITY_MISMATCH"
    if (not isinstance(row.get("protocol_hash"), str)
            or not row["protocol_hash"]):
        return "PROTOCOL_IDENTITY_MISSING"
    typed, output = row.get("typed_response"), row.get("output")
    if not isinstance(typed, dict) or not isinstance(output, dict):
        return "VALID_OUTPUT_PROVENANCE_MISSING"
    choice = row.get("decision")
    if (choice not in CHOICES or typed.get("decision") != choice
            or output.get("decision") != choice):
        return "MODEL_DECISION_INCONSISTENT"
    requested, returned = typed.get("requested_model"), typed.get("model")
    if (not isinstance(requested, str) or not requested
            or requested != row.get("model_id")
            or not isinstance(returned, str) or not returned):
        return "MODEL_IDENTITY_MISSING_OR_INCONSISTENT"
    if typed.get("model_identity_status") not in (
        "REVISION_UNVERIFIED", "PINNED_NAME_ONLY"
    ):
        return "MODEL_REVISION_STATUS_UNVERIFIED"
    return None


def _latency(value: Any) -> float | None:
    if type(value) not in (float, int):
        return None
    numeric = float(value)
    return numeric if isfinite(numeric) and numeric >= 0 else None


def compare_actual_s6_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    """A fresh offline view, not a new AI experiment or performance approval."""
    if not isinstance(records, list):
        raise ValueError("S31C_RECORDS_MUST_BE_LIST")
    grouped: dict[tuple[str, str, str, str], list[dict[str, Any]]] = defaultdict(list)
    excluded: list[dict[str, str]] = []
    actual_count = 0
    mock_count = 0
    invalid_count = 0

    for row in records:
        if not isinstance(row, dict):
            invalid_count += 1
            excluded.append({"case": "UNKNOWN", "reason_code": "RECORD_NOT_OBJECT"})
            continue
        if row.get("execution_origin") != "ACTUAL_PROVIDER":
            mock_count += 1
            continue
        actual_count += 1
        reason = _reason(row)
        if reason:
            invalid_count += 1
            excluded.append({
                "case": str(row.get("case_id") or "UNKNOWN"),
                "reason_code": reason,
            })
            continue
        typed = row["typed_response"]
        key = (
            row["protocol_hash"], typed["requested_model"],
            typed["model"], typed["model_identity_status"],
        )
        grouped[key].append(row)

    cohorts: list[dict[str, Any]] = []
    reported_per_protocol: dict[str, set[str]] = defaultdict(set)
    for key in grouped:
        reported_per_protocol[key[0]].add(key[2])

    for key in sorted(grouped):
        protocol, requested, returned, revision = key
        rows = grouped[key]
        counts = Counter(x["case_id"] for x in rows)
        duplicates = {case for case, count in counts.items() if count > 1}
        if duplicates:
            for row in rows:
                if row["case_id"] in duplicates:
                    invalid_count += 1
                    excluded.append({
                        "case": row["case_id"],
                        "reason_code": "DUPLICATE_CASE_IN_SAME_COHORT",
                    })
        unique = sorted(
            (r for r in rows if r["case_id"] not in duplicates),
            key=lambda r: r["case_id"],
        )
        paired = []
        for row in unique:
            gold, decision = _GOLDS[row["case_id"]], row["decision"]
            paired.append({
                "case": row["case_id"],
                "synthetic_expected": gold,
                "authored_baseline": _BASELINE,
                "actual_jev_decision": decision,
                "baseline_matches_synthetic_gold": gold == _BASELINE,
                "jev_matches_synthetic_gold": decision == gold,
                "latency_ms": _latency(row.get("duration_ms")),
                "estimated_cost_usd": row.get("computed_cost_usd"),
                "cost_status": row.get("cost_status"),
            })
        baseline_correct = sum(r["baseline_matches_synthetic_gold"] for r in paired)
        jev_correct = sum(r["jev_matches_synthetic_gold"] for r in paired)
        latency = [r["latency_ms"] for r in paired if r["latency_ms"] is not None]
        cohorts.append({
            "protocol_hash": protocol,
            "model_requested": requested,
            "model_reported": returned,
            "model_revision_status": revision,
            "moving_alias_or_revision_not_proven": revision == "REVISION_UNVERIFIED",
            "reported_model_changed_within_protocol": len(reported_per_protocol[protocol]) > 1,
            "case_count": len(paired),
            "cases": paired,
            "baseline_matches": baseline_correct,
            "jev_matches": jev_correct,
            "paired_correct_count_difference": jev_correct - baseline_correct,
            "explicit_conflicts_missed": sum(
                r["synthetic_expected"] == "REVIEW_REQUIRED"
                and r["actual_jev_decision"] != "REVIEW_REQUIRED" for r in paired
            ),
            "normal_cases_falsely_flagged": sum(
                r["synthetic_expected"] == "PASS_THROUGH"
                and r["actual_jev_decision"] != "PASS_THROUGH" for r in paired
            ),
            "insufficient_cases_not_abstained": sum(
                r["synthetic_expected"] == "ABSTAIN"
                and r["actual_jev_decision"] != "ABSTAIN" for r in paired
            ),
            "mean_latency_ms": round(sum(latency) / len(latency), 2) if latency else None,
            "full_five_case_coverage": {r["case"] for r in paired} == _CASE_IDS,
        })
    comparable = sum(c["case_count"] for c in cohorts)
    return {
        "version": VERSION,
        "status": (
            "SYNTHETIC_PAIRED_EVIDENCE_ONLY" if comparable else
            "HOLD_NO_COMPARABLE_ACTUAL_RESPONSES"
        ),
        "baseline_definition": "S6_AUTHORED_ENTRY_CANDIDATE_ALWAYS_PASS_THROUGH",
        "baseline_is_real_scanner_execution": False,
        "synthetic_gold_is_real_investment_truth": False,
        "real_stock_model_calls": 0,
        "new_provider_requests": 0,
        "runtime_db_writes": 0,
        "research_db_writes": 0,
        "orders": 0,
        "scanner_or_risk_modified": False,
        "investment_uplift_proven": False,
        "actual_provider_journal_records": actual_count,
        "mock_or_nonactual_records_excluded": mock_count,
        "invalid_or_noncomparable_actual_records": invalid_count,
        "comparable_actual_responses": comparable,
        "authored_case_set_size": len(CASES),
        "cohorts": cohorts,
        "excluded": excluded,
        "interpretation": (
            "같은 합성 사례에 대한 가정된 진입유지 판단과 JEV의 분류 차이만 비교합니다. "
            "서로 다른 프로토콜·반환 모델을 합산한 성능 점수는 만들지 않습니다. "
            "별칭의 실제 모델 리비전은 증명되지 않았으며 주가/투자 성과 개선은 알 수 없습니다."
        ),
    }
