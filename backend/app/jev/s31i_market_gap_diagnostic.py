"""S31-I local market-as-of and post-signal opening-gap diagnostic.

The 10/14 S27 receipt is retrospective; no precommit or live action proven.
Risk READY is a structure assessment, and Scanner price_rule describes a
STRATEGY CONDITION BAND, NEVER an executable order or fill.
Two timelines must never be conflated: signal-day market facts and future OHLC.
No provider, network, write, inference model, trading, or policy activation.
"""
from __future__ import annotations

from contextlib import closing
from datetime import date
from pathlib import Path
from typing import Any

from app.jev.research_scanner_s24 import ResearchCaptureError
from app.jev.s31h_frozen_risk_event_audit import audit_frozen_risk
from app.prospective.evaluation import ReadOnlyMarketEvidence, _decimal
from app.strategy.context import regime_from_index


VERSION = "JEV_ACT2_S31I_SIGNAL_ASOF_MARKET_AND_GAP_V1"
SIGNAL_DATE = "2026-10-14"
MARKET = "KOSPI"


def _pct(value: float | None, basis: float | None) -> float | None:
    return (
        round((value / basis - 1) * 100.0, 4)
        if value is not None and basis is not None and value > 0 and basis > 0
        else None
    )


def _signal_market_context(db: Path) -> dict[str, Any]:
    """Read only the 10/14 KOSPI EOD row; no later information may enter."""
    source = ReadOnlyMarketEvidence(db)
    with closing(source.connect()) as conn:
        rows = source.index_rows(
            conn, market=MARKET, start_dd="20261014", end_dd="20261014",
        )
    day = next(
        (row for row in rows
         if row.get("name") == "코스피"
         and str(row.get("date") or "").replace("-", "") == "20261014"),
        None,
    )
    raw = _decimal((day or {}).get("change_rate"))
    rate = float(raw) if raw is not None else None
    return {
        "market": MARKET, "source_date": SIGNAL_DATE,
        "original_index_daily_change_rate_pct": rate,
        "production_regime_rule": regime_from_index(rate).value,
        "market_regime_calculated_from_signal_day_only": True,
        "next_day_return_used_in_signal_regime": False,
        "exact_original_scanner_regime_recorded_in_receipt": False,
        "original_scanner_market_gate_replay_proven": False,
        "missing_index_rate_does_not_mean_range_market": rate is None,
    }


def analyze_market_gap(
    receipt: dict[str, Any], market_db: Path, *, as_of: str,
) -> dict[str, Any]:
    """One frozen record, two strictly labeled timelines."""
    audit = audit_frozen_risk(receipt, Path(market_db), as_of=as_of)
    context = _signal_market_context(Path(market_db))
    no_gap_data = audit["status"] != "LOCAL_POSTHOC_RISK_EVENT_AUDIT_ONLY"

    candidates: list[dict[str, Any]] = []
    for row in audit["records"]:
        stop = row["risk_reference_invalidation"]
        signal = row["signal_close"]
        days = []
        for day in row["sessions"]:
            ohlc = day["prices"]
            # An invalid OHLC bar cannot prove an opening gap; missing open
            # must stay null rather than borrowing the day's close.
            opening = (
                ohlc.get("open")
                if day["ohlc_valid_for_intraday_touch"] else None
            )
            gap_pct = _pct(opening, signal)
            if stop is None:
                flag = "ORIGINAL_INVALIDATION_REFERENCE_UNAVAILABLE"
            elif opening is None or opening <= 0:
                flag = "OPENING_PRICE_UNAVAILABLE_OR_INVALID_BAR"
            elif opening <= stop:
                flag = "OPEN_AT_OR_BELOW_REFERENCE_INVALIDATION"
            elif signal is None:
                flag = "OPEN_ABOVE_INVALIDATION_SIGNAL_CLOSE_UNKNOWN"
            elif opening < signal:
                flag = "OPEN_BELOW_SIGNAL_CLOSE_ABOVE_INVALIDATION"
            else:
                flag = "OPEN_AT_OR_ABOVE_SIGNAL_CLOSE"
            days.append({
                "date": day["date"],
                "session_number": day["session_number"],
                "opening_price": opening,
                "opening_gap_from_signal_close_pct": gap_pct,
                "reference_invalidation_price": stop,
                "opening_gap_class": flag,
                "risk_reference_level_not_executable_stop": True,
                "original_strategy_condition_level_touched": day["entry_rule_touched"],
                "strategy_condition_level_is_executable_entry": False,
                "risk_low_touch": day["invalidation_low_touched"],
                "risk_close_at_or_below": day["invalidation_close_at_or_below"],
                "same_bar_condition_and_risk_touch_order_unknown": (
                    day["entry_and_invalidation_same_bar_order_unknown"]
                ),
                "actual_fill_or_stop_trigger_proven": False,
                "stock_change_from_signal_close_pct": (
                    day["stock_change_from_signal_close_pct"]
                ),
                "index_change_from_signal_close_pct": (
                    day["index_change_from_signal_close_pct"]
                ),
            })
        candidates.append({
            "code": row["code"], "name": row["name"],
            "original_strategy": row["original_strategy"],
            "original_action": row["original_action"],
            "original_risk_status": row["original_risk_status"],
            "original_conditions": row["original_conditions"],
            "reference_entry": row["risk_reference_entry"],
            "reference_invalidation": stop,
            "signal_close": signal,
            "original_strategy_price_rule": {
                **row["scanner_entry_price_rule"],
                "semantic_role": "STRATEGY_CONDITION_BAND_OR_THRESHOLD",
                "is_executable_buy_range": False,
            },
            "risk_ready_means_gap_protected": False,
            "actual_entry_or_position_proven": False,
            "actual_intraday_warning_proven": False,
            "days": days,
        })

    gap_events = [
        {"code": r["code"], "name": r["name"], "date": d["date"]}
        for r in candidates for d in r["days"]
        if d["opening_gap_class"] == "OPEN_AT_OR_BELOW_REFERENCE_INVALIDATION"
    ]
    return {
        "version": VERSION,
        "status": (
            "HOLD_UNRESOLVED_MARKET_SESSIONS" if no_gap_data
            else "LOCAL_SIGNAL_ASOF_AND_POSTHOC_GAP_DIAGNOSTIC_ONLY"
        ),
        "market": MARKET, "signal_date": SIGNAL_DATE,
        "as_of_date": audit["as_of_date"],
        "receipt_payload_hash": audit["original_payload_hash"],
        "source_is_posthoc_not_prospectively_precommitted": (
            audit["source_posthoc_not_precommitted"]
        ),
        "signal_day_known_information": context,
        "later_observations_cannot_retroactively_change_signal": True,
        "original_risk_ready_has_no_guaranteed_next_open_protection": True,
        "production_risk_engine_reference_only": True,
        "production_market_circuit_breaker_from_receipt_proven": False,
        "risk_gate_timing_reconstruction_proven": False,
        "unresolved_prior_weekdays": audit["unresolved_prior_weekdays"],
        "complete_eod_sessions": audit["complete_eod_sessions"],
        "candidate_count": len(candidates),
        "post_signal_open_below_invalidation_events": gap_events,
        "post_signal_open_below_invalidation_event_count": len(gap_events),
        "candidates": candidates,
        "decisions_or_captures_recomputed": False,
        "actual_entry_or_exit_proven": False,
        "execution_returns_computable_from_this_audit": False,
        "market_network_requests": 0, "jev_model_calls": 0,
        "orders": 0, "production_db_writes": 0, "research_db_writes": 0,
        "limitations": [
            "RANGE/ABOVE는 전략의 조건 가격대이며 실제 매수 주문/체결 조건이 아닙니다.",
            "Risk READY는 기준가격의 손익 구조 평가이며 다음날 갭 보호 보장이 아닙니다.",
            "기준일 시장 레짐은 10/14 KRX 값으로 계산한 진단 재현이며 원본 Scanner 상태값 기록의 증명은 아닙니다.",
            "10/15 이후 시장 급락을 10/14 판단 입력으로 되돌려 사용하지 않습니다.",
            "시가가 참고 무효화선 이하여도 실제 손절 주문·체결가격·보유 여부는 알 수 없습니다.",
            "일봉 고저만으로 동일 일봉 내 전략 조건·위험선의 선후관계를 알 수 없습니다.",
            "임의의 신규 시장 중단 임계값이나 사후 수익률 정책은 채택하지 않았습니다.",
        ],
    }
