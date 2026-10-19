"""S31-J: non-executing recheck triage for stale frozen Scanner READY labels.

Always treats S27 as retrospective explanatory evidence, never as a real
precommitted buy recommendation. Rechecks the exact 2026-10-14 KOSPI receipt
against later locally completed EOD and source-locked risk references.
No live quote, brokerage holdings, trades, network, DB writes or policy change.
"""
from __future__ import annotations

from contextlib import closing
from datetime import date
from math import isfinite
from pathlib import Path
from typing import Any

from app.jev.s31i_market_gap_diagnostic import analyze_market_gap
from app.market.session_calendar_s21 import unresolved_weekdays
from app.prospective.evaluation import ReadOnlyMarketEvidence, _float
from app.strategy.context import regime_from_index

VERSION = "JEV_ACT2_S31J_PRIOR_READY_READONLY_RECHECK_V1"


def _latest_market_context(db: Path, last_complete: str | None) -> dict[str, Any]:
    """Only a last-confirmed EOD market regime; never intraday or future rows."""
    if last_complete is None:
        return {
            "complete_eod_date": None, "daily_index_change_rate_pct": None,
            "production_regime": "UNKNOWN",
            "source": "CONFIRMED_EOD_ONLY",
        }
    key = last_complete.replace("-", "")
    with closing(ReadOnlyMarketEvidence(db).connect()) as conn:
        rows = ReadOnlyMarketEvidence.index_rows(
            conn, market="KOSPI", start_dd=key, end_dd=key,
        )
    match = next(
        (r for r in rows
         if str(r.get("date") or "").replace("-", "") == key
         and r.get("name") == "코스피"), None,
    )
    raw = _float((match or {}).get("change_rate"))
    rate = raw if raw is not None and isfinite(raw) else None
    return {
        "complete_eod_date": last_complete,
        "daily_index_change_rate_pct": rate,
        "production_regime": regime_from_index(rate).value,
        "source": "CONFIRMED_EOD_ONLY",
        "regime_is_not_a_new_trading_gate": True,
    }


def _candidate_recheck(
    candidate: dict[str, Any], *, last_complete: str | None,
    unconfirmed_dates: list[str], market_context: dict[str, Any],
) -> dict[str, Any]:
    """Fail-closed user-facing triage, NOT a price/strategy execution engine."""
    days = candidate["days"]
    last = days[-1] if days else None
    has_complete_current_bar = (
        last_complete is not None and last is not None
        and last["date"] == last_complete
        and last["opening_gap_class"] != "OPENING_PRICE_UNAVAILABLE_OR_INVALID_BAR"
        and last["opening_price"] is not None
        and last["stock_change_from_signal_close_pct"] is not None
    )
    events = [
        {"date": day["date"], "event": tag}
        for day in days
        for tag, happened in (
            ("OPEN_BELOW_OLD_INVALIDATION",
             day["opening_gap_class"] == "OPEN_AT_OR_BELOW_REFERENCE_INVALIDATION"),
            ("LOW_TOUCHED_OLD_INVALIDATION", day["risk_low_touch"] is True),
            ("CLOSE_BELOW_OLD_INVALIDATION", day["risk_close_at_or_below"] is True),
        )
        if happened
    ]
    history_breached = bool(events)
    if unconfirmed_dates:
        state = "DATA_CONFIRMATION_REQUIRED"
        reason = "요청 시점까지 완료 EOD가 확인되지 않은 날짜가 있습니다."
    elif not has_complete_current_bar:
        state = "STOCK_EOD_UNAVAILABLE"
        reason = "최신 완료 시장일의 해당 종목 시가·종가 근거가 부족합니다."
    elif history_breached:
        state = "PREVIOUS_RISK_REFERENCE_BREACHED"
        reason = "당시 Risk 참고 무효화 가격에 도달한 기록이 있어 기존 READY를 재사용할 수 없습니다."
    else:
        state = "PREVIOUS_READY_RECHECK_REQUIRED"
        reason = "이전 READY는 과거 시점 구조 평가이므로 새 진입 판단으로 재사용할 수 없습니다."

    context_warnings = []
    if market_context["production_regime"] == "TREND_DOWN":
        context_warnings.append("LATEST_COMPLETED_EOD_MARKET_TREND_DOWN")
    if market_context["production_regime"] == "UNKNOWN":
        context_warnings.append("LATEST_COMPLETED_EOD_MARKET_REGIME_UNKNOWN")
    return {
        "code": candidate["code"], "name": candidate["name"],
        "original_strategy": candidate["original_strategy"],
        "original_ready": candidate["original_risk_status"] == "READY",
        "original_action": candidate["original_action"],
        "original_signal_date": "2026-10-14",
        "original_reference_entry_not_fill": candidate["reference_entry"],
        "original_reference_invalidation_not_executed_stop": (
            candidate["reference_invalidation"]
        ),
        "last_observed_complete_eod": last_complete,
        "last_complete_eod_open_price": (
            last["opening_price"] if has_complete_current_bar else None
        ),
        "last_complete_eod_open_price_source": (
            "HISTORICAL_EOD_OPEN_NOT_LIVE_PRICE" if has_complete_current_bar else None
        ),
        "previous_reference_breach_history": events,
        "past_reference_breach_count": len(events),
        "recheck_status": state,
        "reason": reason,
        "additional_market_context": context_warnings,
        "user_message": (
            "새로운 매수 판단 전에 최신 시장 데이터와 종목 가격으로 Scanner·Risk를 다시 확인하세요. "
            "기존 READY는 현재 매수 허가가 아닙니다."
        ),
        "entry_allowed_by_this_result": False,
        "actual_position_known": False,
        "live_risk_alert_confirmed": False,
        "realized_trade_return_known": False,
    }


def evaluate_prior_ready(
    receipt: dict[str, Any], market_db: Path, *, as_of: str,
) -> dict[str, Any]:
    """No policy overrides and no inference from post-signal data to 10/14."""
    frozen = analyze_market_gap(receipt, Path(market_db), as_of=as_of)
    complete_days = sorted({
        day["date"]
        for item in frozen["candidates"] for day in item["days"]
    })
    latest = complete_days[-1] if complete_days else None
    asof = date.fromisoformat(frozen["as_of_date"])
    cutoff = date.fromisoformat(frozen["signal_date"])
    # Missing market sessions are unknown: never infer a holiday or a
    # successful EOD from an empty API/database result. Even the target date
    # may not have published a completed EOD yet.
    confirmed = [date.fromisoformat(day) for day in complete_days]
    unconfirmed = unresolved_weekdays(cutoff, asof, confirmed)
    # S31-I explicitly refuses historical session skipping; also propagate
    # its hold even if an EOD later appears.
    if frozen["status"] != "LOCAL_SIGNAL_ASOF_AND_POSTHOC_GAP_DIAGNOSTIC_ONLY":
        unconfirmed = sorted(set(unconfirmed + frozen["unresolved_prior_weekdays"]))
    index = _latest_market_context(Path(market_db), latest)
    candidates = [
        _candidate_recheck(
            row, last_complete=latest,
            unconfirmed_dates=unconfirmed, market_context=index,
        )
        for row in frozen["candidates"]
    ]
    statuses = sorted({item["recheck_status"] for item in candidates})
    return {
        "version": VERSION,
        "status": (
            "HOLD_EOD_CONFIRMATION_REQUIRED"
            if unconfirmed or frozen["status"] != "LOCAL_SIGNAL_ASOF_AND_POSTHOC_GAP_DIAGNOSTIC_ONLY"
            else "LOCAL_PRIOR_READY_RECHECK_ONLY"
        ),
        "signal_date": frozen["signal_date"],
        "as_of_date": frozen["as_of_date"],
        "source_posthoc_not_precommitted": (
            frozen["source_is_posthoc_not_prospectively_precommitted"]
        ),
        "original_receipt_hash": frozen["receipt_payload_hash"],
        "market": frozen["market"],
        "last_confirmed_market_eod": latest,
        "unconfirmed_market_dates_through_asof": unconfirmed,
        "unconfirmed_dates_are_not_proven_market_sessions": True,
        "market_context_latest_completed_eod": index,
        "signal_day_market_context": frozen["signal_day_known_information"],
        "market_regime_not_a_new_gate": True,
        "candidate_count": len(candidates),
        "recheck_states_present": statuses,
        "prior_reference_breach_candidate_count": sum(
            bool(x["previous_reference_breach_history"]) for x in candidates
        ),
        "new_entry_permission": False,
        "today_live_quote_verified": False,
        "reran_scanner_or_risk": False,
        "actual_position_or_fills_known": False,
        "realized_return_or_jev_uplift_proven": False,
        "candidates": candidates,
        "market_network_requests": 0,
        "jev_model_calls": 0, "orders": 0,
        "production_db_writes": 0, "research_db_writes": 0,
        "next_steps": [
            "누락된 날짜가 있다면 완료 KRX EOD를 확보하고 재검증",
            "신규 진입을 검토할 때 그 시점의 종목 가격·시장 데이터로 기존 Scanner/Risk 재실행",
            "실제 보유 종목은 별도의 보유·체결 근거와 현재 시세를 확인 (여기서는 읽지 않음)",
        ],
        "limitations": [
            "S27은 사후 기술 점검이며 실제 사전 추천 적중률이 아닙니다.",
            "이 도구는 기존 READY를 사용자에게 자동 매수/매도 신호로 제공하지 않습니다.",
            "유효한 최신 실시간 주가·장중 호가/거래체결·보유 수량을 수집하거나 조회하지 않습니다.",
            "전략 조건 가격대는 실제 주문 진입 가격이 아닙니다.",
            "과거 무효화선 도달은 실제 손절 실행 또는 현재 보유 포지션의 손익을 증명하지 않습니다.",
        ],
    }
