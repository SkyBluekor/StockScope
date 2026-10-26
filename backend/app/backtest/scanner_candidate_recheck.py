"""P0-03 candidate recheck: annotate a real fresh Scanner result without inventing a verdict.

The current Scanner ranks a broad universe but returns only top N + limited extras.
Omission from those returned candidates is NEVER evidence of NO_TRADE.
This module does not change the frozen Scanner/strategy/Risk implementation.
"""
from __future__ import annotations

from datetime import date
from typing import Any

VERSION = "SCANNER_CANDIDATE_RECHECK_V1"


def compare_scanner_candidate(
    *,
    previous: dict[str, Any],
    scanner_result: dict[str, Any],
) -> dict[str, Any]:
    market = str(previous["market"])
    code = str(previous["code"])
    previous_date = str(previous["source_data_date"])
    latest_date = str((scanner_result.get("data_dates") or {}).get(market) or "")
    requested_date = str(scanner_result.get("requested_as_of") or "")
    fingerprint = scanner_result.get("input_fingerprint") or {}
    fingerprint_market = (fingerprint.get("markets") or {}).get(market) or {}
    base = {
        "version": VERSION,
        "reference_kind": "USER_SELECTED_PRIOR_SCANNER_CANDIDATE",
        "market": market,
        "code": code,
        "name": str(previous.get("name") or ""),
        "source_data_date": previous_date,
        "source_action": str(previous.get("source_action") or ""),
        "source_strategy": str(previous.get("source_strategy") or ""),
        "new_data_date": latest_date or None,
        "new_scanner_input_fingerprint_id": fingerprint.get("id"),
        "new_eod_advanced": bool(latest_date and latest_date > previous_date),
        "new_result_scanner_version": scanner_result.get("version"),
        "no_trade_inferred": False,
        "independently_evaluated_when_not_returned": False,
        "scope": "RETURNED_SCANNER_CANDIDATES_ONLY",
        "new_candidate": None,
    }

    result_valid = (
        bool(latest_date)
        and latest_date >= previous_date
        and latest_date == requested_date
        and not bool(scanner_result.get("partial_data"))
        and bool(fingerprint.get("id"))
        and fingerprint_market.get("date") == latest_date
        and int(fingerprint_market.get("stock_rows") or 0) > 0
        and bool(fingerprint_market.get("stock_hash"))
        and bool(fingerprint_market.get("index_hash"))
    )
    if not result_valid:
        return {
            **base,
            "status": "NOT_EVALUABLE",
            "reason": "시장 기준일, 실제 종목·지수 입력 또는 필수 데이터 정합성을 검증하지 못했습니다.",
        }

    returned = [
        *(scanner_result.get("candidates") or []),
        *(scanner_result.get("more_candidates") or []),
    ]
    found = next(
        (row for row in returned if
         row.get("market") == market and str(row.get("code") or "") == code
         and row.get("data_date") == latest_date),
        None,
    )
    if found is None:
        return {
            **base,
            "status": "NOT_IN_RETURNED_POOL",
            "reason": (
                "이번 Scanner의 반환 후보 목록에 없습니다. 상위 후보 제한·"
                "사전 필터·심층 분석 제외 등의 가능성을 구별할 근거가 없으므로 "
                "NO_TRADE나 최종 제외로 판정하지 않습니다."
            ),
            "returned_candidate_count": len(returned),
            "reported_action": None,
        }

    return {
        **base,
        "status": "MATCHED_RETURNED_CANDIDATE",
        "reason": (
            "새 확정 일봉에서 해당 후보가 반환되었습니다. 현재 표시된 전략·"
            "Risk 판단만 비교하며 3년 성과 검증이나 투자 실행을 뜻하지 않습니다."
        ),
        "reported_action": found.get("action"),
        "reported_candidate_state": found.get("candidate_state"),
        "reported_strategy": found.get("strategy"),
        "reported_action_label": found.get("action_label"),
        "reported_risk_status": (found.get("risk") or {}).get("status"),
        "new_candidate": {
            "market": market,
            "code": code,
            "data_date": latest_date,
            "strategy": found.get("strategy"),
            "action": found.get("action"),
            "candidate_state": found.get("candidate_state"),
        },
    }
