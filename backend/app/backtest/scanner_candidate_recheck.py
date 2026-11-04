"""P0-03 candidate recheck: annotate a real fresh Scanner result without inventing a verdict.

The current Scanner ranks a broad universe but returns only top N + limited extras.
Omission from those returned candidates is NEVER evidence of NO_TRADE.
This module does not change the frozen Scanner/strategy/Risk implementation.
"""
from __future__ import annotations

from datetime import date, timedelta
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
        # These source details are references supplied from a prior UI result.
        # They are NOT proven historical records merely by being echoed back.
        "source_input_fingerprint_id": previous.get("source_input_fingerprint_id"),
        "source_policy_id": previous.get("source_policy_id"),
        "source_policy_hash": previous.get("source_policy_hash"),
        "source_capture_id": previous.get("source_capture_id"),
        "reference_verified_against_capture": False,
        "new_data_date": latest_date or None,
        "new_scanner_input_fingerprint_id": fingerprint.get("id"),
        "new_eod_advanced": bool(latest_date and latest_date > previous_date),
        "new_result_scanner_version": scanner_result.get("version"),
        "new_policy_id": (scanner_result.get("strategy_selection_policy") or {}).get("policy_id"),
        "new_policy_hash": (scanner_result.get("strategy_selection_policy") or {}).get("policy_hash"),
        "policy_changed": (
            str(previous["source_policy_hash"]) != str((scanner_result.get("strategy_selection_policy") or {}).get("policy_hash"))
            if previous.get("source_policy_hash") and (scanner_result.get("strategy_selection_policy") or {}).get("policy_hash")
            else None
        ),
        "new_quote_checked": False,
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



def independently_recheck_unreturned_candidate(
    *,
    service: Any,
    previous: dict[str, Any],
    scanner_result: dict[str, Any],
    selection_policy_pin: Any,
) -> dict[str, Any]:
    """Run the same frozen quick/current evaluator on one stock *outside* global ranking.

    This optional target is never inserted into the official ranked Scanner
    candidates; its state is not a global rank or a production capture decision.
    A missing row, liquidity exclusion, or insufficient history is not NO_TRADE.
    """
    summary = compare_scanner_candidate(previous=previous, scanner_result=scanner_result)
    if summary["status"] != "NOT_IN_RETURNED_POOL":
        return summary

    market = summary["market"]
    code = summary["code"]
    date_text = summary["new_data_date"]
    try:
        latest = date.fromisoformat(date_text)
        key = latest.strftime("%Y%m%d")
        rows = service.market_store.stock_day_rows(market, key)
        stock = next((row for row in rows if str(row.get("code") or "") == code), None)
        if stock is None:
            return {
                **summary, "status": "TARGET_STOCK_ROW_MISSING",
                "reason": "이번 분석일의 해당 종목 원본 행이 없습니다. 거래 판단이나 NO_TRADE가 아닙니다.",
            }
        special = service._special_reason(stock)
        if special:
            return {
                **summary, "status": "TARGET_OUTSIDE_SCANNER_FILTER",
                "reason": "일반 주식 필터에서 제외되었습니다. 전략·Risk 심층 판단은 실행하지 않았습니다.",
                "filter_reason": str(special),
            }
        if float(stock.get("trade_value") or 0) < service.engine.LIQUIDITY_THRESHOLD:
            return {
                **summary, "status": "TARGET_OUTSIDE_SCANNER_FILTER",
                "reason": "현재 유동성 필터를 통과하지 못했습니다. 전략·Risk 심층 판단은 실행하지 않았습니다.",
                "filter_reason": "LOW_LIQUIDITY",
            }
        # A configured sector prefetcher could use additional provider inputs.
        # Never claim an equivalent independent calculation without those inputs.
        if getattr(service, "sector_prefetcher", None) is not None:
            return {
                **summary, "status": "NOT_EVALUABLE",
                "reason": "개별 종목 재검증에 필요한 섹터 입력을 동일하게 재현하지 못했습니다.",
            }

        start = latest - timedelta(days=service.FAST_HISTORY_CALENDAR_DAYS)
        stocks = service.market_store.stock_series(
            market, code, start.strftime("%Y%m%d"), key,
        )
        index = service.market_store.index_series(
            market, start.strftime("%Y%m%d"), key,
        )
        quick = service._quick_current_candidate(
            market=market,
            latest_date=key,
            row=stock,
            stock_rows=list(stocks.rows.values()),
            index_rows=list(index.rows.values()),
            selection_policy_pin=selection_policy_pin,
        )
        if quick is None:
            return {
                **summary, "status": "NOT_EVALUABLE",
                "reason": "해당 종목의 개별 기술지표 계산 입력이 부족합니다. NO_TRADE가 아닙니다.",
            }
        current = service._current_candidate(quick)
        if not current:
            return {
                **summary, "status": "NOT_EVALUABLE",
                "reason": "해당 종목의 개별 전략·Risk 계산 결과를 확인할 수 없습니다.",
            }
        return {
            **summary,
            "status": "TARGETED_EVALUATED_OUTSIDE_RANKING",
            "scope": "TARGETED_CORE_NO_GLOBAL_RANK",
            "reason": (
                "원래 Scanner 반환 목록 밖의 종목을 같은 버전의 전략·Risk 코어로 "
                "별도 계산했습니다. 전체 시장 순위나 정식 반환 후보 승격은 아닙니다."
            ),
            "independently_evaluated_when_not_returned": True,
            "targeted_action": current.get("action"),
            "targeted_action_label": current.get("action_label"),
            "targeted_strategy": current.get("strategy"),
            "targeted_candidate_state": current.get("candidate_state"),
            "targeted_risk_status": (current.get("risk") or {}).get("status"),
        }
    except Exception as exc:
        # The primary Scanner result stays valid, but an unverifiable private
        # targeted check cannot produce a guessed trading verdict.
        return {
            **summary,
            "status": "NOT_EVALUABLE",
            "reason": "개별 종목 계산 중 오류가 발생해 판단을 보류했습니다.",
            "error_class": type(exc).__name__,
        }



def attach_recheck_execution_lineage(
    *,
    recheck: dict[str, Any],
    source_job_id: str,
    capture: dict[str, Any],
) -> dict[str, Any]:
    """Bind a finished result to its real Job and baseline capture outcome.

    A baseline Scanner prospective capture is *not* a recording of the
    out-of-pool targeted evaluation or the user's prior candidate reference.
    Never manufacture a capture ID when the catalog could not persist one.
    """
    known_id = capture.get("canonical_capture_id") or capture.get("capture_id")
    capture_id = str(known_id) if known_id else None
    return {
        **recheck,
        "source_job_id": source_job_id,
        "baseline_scanner_capture_status": capture.get("status") or "UNKNOWN",
        "baseline_scanner_capture_id": capture_id,
        "baseline_capture_scope": "SCANNER_RETURNED_CANDIDATES_ONLY",
        "targeted_result_stored_in_capture": False,
        "prior_reference_stored_in_capture": False,
        "capture_confirmed": bool(capture_id),
    }
