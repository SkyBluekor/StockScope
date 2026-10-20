"""S31-T: paired, unique-scenario comparison of S6 synthetic actual-model receipts.

Do not treat repeated attempts as independent scenarios or gold-label matching
as economic uplift. The only baseline here is a deliberately naïve
PASS_THROUGH proxy for the S6 fixture's authored ENTRY_CANDIDATE baseline.
This is NOT a production Scanner algorithm, nor an evaluation on market data.
No model/network/DB access in this pure projection.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Mapping

from app.jev.decision_reviewer_micro_canary import CASES

VERSION = "JEV_ACT2_S31T_PAIRED_SYNTHETIC_CHALLENGE_V1"
GOLD = {item["id"]: item["gold"] for item in CASES}
BASELINE_CHOICE = "PASS_THROUGH"


def compare_synthetic_cases(
    receipts: list[Mapping[str, Any]],
    *,
    total_actual_attempts: int,
    malformed_rows: int,
    read_limit: int,
) -> dict[str, Any]:
    """Compare only pairable unique scenarios, not six tries as six problems."""
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in receipts:
        case = row.get("case_id")
        if case in GOLD:
            grouped[str(case)].append(row)

    comparisons = []
    for case in GOLD:
        attempts = grouped.get(case, [])
        decisions = {
            str(row.get("observed"))
            for row in attempts
            if row.get("receipt_status") == "JOURNAL_CONSISTENCY_CHECK_PASSED"
        }
        models = {
            str(row.get("model"))
            for row in attempts
            if row.get("receipt_status") == "JOURNAL_CONSISTENCY_CHECK_PASSED"
        }
        valid_count = sum(
            row.get("receipt_status") == "JOURNAL_CONSISTENCY_CHECK_PASSED"
            for row in attempts
        )
        if not attempts:
            status = "NO_ATTEMPT"
        elif any(row.get("receipt_status") != "JOURNAL_CONSISTENCY_CHECK_PASSED"
                 for row in attempts):
            status = "INCOMPLETE_ATTEMPTS"
        elif valid_count == 0:
            status = "NO_VALID_RECEIPT"
        elif len(models) != 1:
            status = "MIXED_MODEL_IDENTITIES"
        elif len(decisions) != 1:
            status = "INCONSISTENT_REPEATS"
        else:
            status = "PAIRABLE"
        paired = status == "PAIRABLE"
        decision = next(iter(decisions)) if paired else None
        gold = GOLD[case]
        comparisons.append({
            "case_id": case,
            "attempt_count": len(attempts),
            "valid_receipt_count": valid_count,
            "status": status,
            "model_decision": decision,
            "gold": gold,
            "model_matches_gold": decision == gold if paired else None,
            "baseline_choice": BASELINE_CHOICE,
            "naive_baseline_matches_gold": BASELINE_CHOICE == gold,
            "repeat_stability": (
                "AGREED_REPEATS" if paired and len(attempts) > 1
                else "SINGLE_RECEIPT" if paired else "NOT_ESTABLISHED"
            ),
        })

    pairable = [x for x in comparisons if x["status"] == "PAIRABLE"]
    baseline_correct = sum(x["naive_baseline_matches_gold"] for x in pairable)
    model_correct = sum(x["model_matches_gold"] is True for x in pairable)
    full = (
        len(pairable) == len(GOLD)
        and total_actual_attempts <= read_limit
        and malformed_rows == 0
        and sum(x["attempt_count"] for x in comparisons) == total_actual_attempts
    )
    if total_actual_attempts > read_limit:
        verdict = "TRUNCATED_NOT_COMPARABLE"
    elif total_actual_attempts == 0:
        verdict = "NO_ACTUAL_MODEL_RECORDS"
    elif not full:
        verdict = "PARTIAL_NOT_COMPARABLE"
    else:
        verdict = "ALL_AUTHORED_SYNTHETIC_CASES_PAIRED"
    return {
        "version": VERSION,
        "scope": "AUTHOR_CREATED_SYNTHETIC_CASES_ONLY",
        "status": verdict,
        "unique_authored_cases": len(GOLD),
        "pairable_unique_cases": len(pairable),
        "raw_actual_attempts": total_actual_attempts,
        "raw_valid_receipts": sum(x["valid_receipt_count"] for x in comparisons),
        "repeated_cases": sum(x["attempt_count"] > 1 for x in comparisons),
        "inconsistent_repeats": sum(
            x["status"] in {"INCONSISTENT_REPEATS", "MIXED_MODEL_IDENTITIES"}
            for x in comparisons
        ),
        "matched_model_and_baseline_cases": len(pairable),
        "model_correct_paired": model_correct,
        "naive_baseline_correct_paired": baseline_correct,
        "paired_gold_label_difference": model_correct - baseline_correct,
        "full_case_coverage": full,
        "rows": comparisons,
        "naive_baseline_is_actual_scanner_algorithm": False,
        "actual_stock_comparison_available": False,
        "jev_incremental_market_value_proven": False,
        "real_market_cases": 0,
        "external_calls": 0,
        "db_writes": 0,
        "interpretation": (
            "한정된 사전 작성 합성 사례에서 PASS_THROUGH 단순 대조군과 모델 응답을 "
            "같은 사례별로 비교했습니다. 테스트 답안과의 일치는 모델의 새 정보 발견, "
            "실제 Scanner 추천 성능 또는 투자 성과 개선을 증명하지 않습니다."
        ),
    }
