"""S31-H: fact-check the 2026-10-14 frozen Scanner risk references vs local EOD.

Only AFTER-the-fact descriptive touches of original price thresholds; no
retroactive order, execution, fill, realized P/L or predictive efficacy claim.
The S27 record is POSTHOC and not an independently precommitted recommendation.
No market provider/model, writes, scheduling or trading permission.
"""
from __future__ import annotations

from contextlib import closing
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from app.jev.research_scanner_s24 import ResearchCaptureError
from app.jev.s31_real_candidate_trial import inspect_frozen_candidates
from app.jev.s31e_frozen_price_observation import (
    FROZEN_MARKET, FROZEN_SOURCE_DATE, _as_of_date,
)
from app.market.session_calendar_s21 import closure_evidence
from app.prospective.evaluation import (
    ReadOnlyMarketEvidence, ProspectiveEvaluationError,
    _decimal, _entry_comparable, _entry_touched, _plan_from_snapshot,
    _pct,
)

VERSION = "JEV_S31H_FROZEN_RISK_EVENT_AUDIT_V1"
HORIZON_DAYS = 20


def _close(row: dict[str, Any] | None) -> Any:
    return _decimal((row or {}).get("close"))


def _ohlc(row: dict[str, Any] | None) -> tuple[dict[str, float | None], bool]:
    if row is None:
        return {"open": None, "high": None, "low": None, "close": None}, False
    raw = {key: _decimal(row.get(key)) for key in ("open", "high", "low", "close")}
    high, low, open_, close = (raw["high"], raw["low"], raw["open"], raw["close"])
    # Neither a missing OHLC bar nor an inconsistent high/low can substantiate
    # an intraday stop touch or gap-through event.
    valid = bool(
        high is not None and low is not None and high >= low
        and (open_ is None or low <= open_ <= high)
        and (close is None or low <= close <= high)
    )
    return {key: float(value) if value is not None else None for key, value in raw.items()}, valid


def _market_days(
    source: ReadOnlyMarketEvidence, *, as_of: str,
) -> tuple[list[str], list[str]]:
    """Verified complete EOD only; no jumping over unresolved missing weekdays."""
    with closing(source.connect()) as conn:
        days = source.market_days(
            conn, market=FROZEN_MARKET, after_date=FROZEN_SOURCE_DATE,
            through_date=as_of, limit=HORIZON_DAYS, complete_only=True,
        )
    if not days:
        return [], []
    latest = date.fromisoformat(days[-1][:4] + "-" + days[-1][4:6] + "-" + days[-1][6:8])
    found = set(days)
    missing = []
    current = date.fromisoformat(FROZEN_SOURCE_DATE) + timedelta(days=1)
    while current <= latest:
        if (current.strftime("%Y%m%d") not in found
                and closure_evidence(current) is None):
            missing.append(current.isoformat())
        current += timedelta(days=1)
    # Withhold session-count conclusions rather than compressing an unknown
    # missing market session into the 1d/2d/3d sequence.
    return ([] if missing else days), missing


def audit_frozen_risk(
    receipt: dict[str, Any], market_db: Path, *, as_of: str,
) -> dict[str, Any]:
    """Original locked reference levels versus existing actual OHLC (read only)."""
    as_of = _as_of_date(as_of)
    baseline = inspect_frozen_candidates(receipt, limit=5)
    if (baseline["source_date"] != FROZEN_SOURCE_DATE
            or baseline["market"] != FROZEN_MARKET
            or baseline["original_entry_count"] != 5
            or baseline["inspected_entry_count"] != 5):
        raise ResearchCaptureError("S31H_FROZEN_SCOPE_MISMATCH")

    source = ReadOnlyMarketEvidence(Path(market_db))
    try:
        with closing(source.connect()) as conn:
            required = {"day_status", "stock_daily", "main_index_daily"}
            tables = {
                str(r[0]) for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
            if not required.issubset(tables):
                raise ResearchCaptureError("S31H_MARKET_SCHEMA_INCOMPLETE")
        days, unknown_sessions = _market_days(source, as_of=as_of)
        with closing(source.connect()) as conn:
            signal_index_rows = source.index_rows(
                conn, market=FROZEN_MARKET,
                start_dd=FROZEN_SOURCE_DATE.replace("-", ""),
                end_dd=FROZEN_SOURCE_DATE.replace("-", ""),
            )
            index_by_day = {
                str(r["date"]).replace("-", ""): r for r in
                source.index_rows(
                    conn, market=FROZEN_MARKET,
                    start_dd=days[0], end_dd=days[-1],
                )
            } if days else {}
            signal_index = next(
                (r for r in signal_index_rows
                 if str(r.get("name")) == "코스피"), None,
            )
            index_ref = _close(signal_index)
            raw_by_code = {r["code"]: r for r in receipt["original_scanner_candidates"]}
            records = []
            for entry in baseline["candidates"]:
                code = entry["code"]
                raw = raw_by_code[code]
                risk = entry["local_evidence"]
                trusted_reference = risk["risk_reference_status"] == "REFERENCE_ARITHMETIC_CHECKED"
                level_entry = _decimal(risk["entry_reference_price"]) if trusted_reference else None
                level_stop = _decimal(risk["invalidation_reference_price"]) if trusted_reference else None
                level_target = _decimal(risk["target1_reference_price"]) if trusted_reference else None
                plan = _plan_from_snapshot(raw)
                # A Risk arithmetic reference is not an entry order. The only
                # permitted entry-touch interpretation is the original scanner
                # price_rule, using the preexisting Prospective evaluator rules.
                entry_rule = plan["entry_rule"]
                rule_known = _entry_comparable(entry_rule)
                signal = source.stock_row(
                    conn, market=FROZEN_MARKET, ticker=code,
                    bas_dd=FROZEN_SOURCE_DATE.replace("-", ""),
                )
                signal_price = _close(signal)
                first = {"rule_touch": None, "invalidation_low_touch": None,
                         "close_below_invalidation": None,
                         "open_at_or_below_invalidation": None}
                sessions = []
                for pos, key in enumerate(days, 1):
                    row = source.stock_row(conn, market=FROZEN_MARKET, ticker=code, bas_dd=key)
                    prices, valid_bar = _ohlc(row)
                    day_close = _close(row)
                    idx_close = _close(index_by_day.get(key))
                    stock_pct = _pct(day_close, signal_price)
                    index_pct = _pct(idx_close, index_ref)
                    low = _decimal((row or {}).get("low")) if valid_bar else None
                    high = _decimal((row or {}).get("high")) if valid_bar else None
                    open_ = _decimal((row or {}).get("open")) if valid_bar else None

                    rule_touch = (
                        _entry_touched(entry_rule, low=low, high=high)
                        if rule_known and low is not None and high is not None
                        else None
                    )
                    stop_low = (
                        low <= level_stop if low is not None and level_stop is not None
                        else None
                    )
                    close_below = (
                        day_close <= level_stop if day_close is not None and level_stop is not None
                        else None
                    )
                    open_below = (
                        open_ <= level_stop if open_ is not None and level_stop is not None
                        else None
                    )
                    target_high = (
                        high >= level_target if high is not None and level_target is not None
                        else None
                    )
                    for k, touched in (
                        ("rule_touch", rule_touch),
                        ("invalidation_low_touch", stop_low),
                        ("close_below_invalidation", close_below),
                        ("open_at_or_below_invalidation", open_below),
                    ):
                        if touched is True and first[k] is None:
                            first[k] = f"{key[:4]}-{key[4:6]}-{key[6:8]}"
                    sessions.append({
                        "session_number": pos,
                        "date": f"{key[:4]}-{key[4:6]}-{key[6:8]}",
                        "prices": prices,
                        "ohlc_valid_for_intraday_touch": valid_bar,
                        "stock_change_from_signal_close_pct": stock_pct,
                        "index_change_from_signal_close_pct": index_pct,
                        "stock_minus_index_change_pp": (
                            round(stock_pct - index_pct, 4)
                            if stock_pct is not None and index_pct is not None else None
                        ),
                        "entry_rule_touched": rule_touch,
                        "invalidation_low_touched": stop_low,
                        "invalidation_close_at_or_below": close_below,
                        "invalidation_open_at_or_below": open_below,
                        "target1_high_touched": target_high,
                        "entry_and_invalidation_same_bar_order_unknown": (
                            rule_touch is True and stop_low is True
                        ),
                    })
                records.append({
                    "code": code, "name": entry["name"],
                    "original_action": entry["baseline"]["action"],
                    "original_strategy": entry["baseline"]["strategy"],
                    "original_rank_not_expected_return": (
                        entry["baseline"]["display_rank_not_performance_rank"]
                    ),
                    "original_risk_status": entry["baseline"]["risk_status"],
                    "original_risk_warning": entry["baseline"]["risk_warning"],
                    "original_conditions": {
                        "passed": entry["baseline"]["conditions_passed"],
                        "total": entry["baseline"]["conditions_total"],
                    },
                    "historical_evidence": entry["baseline"]["historical_status"],
                    "baseline_alerts": entry["local_evidence"]["alerts"],
                    "risk_reference_status": risk["risk_reference_status"],
                    "risk_reference_entry": float(level_entry) if level_entry else None,
                    "risk_reference_invalidation": float(level_stop) if level_stop else None,
                    "risk_reference_target1": float(level_target) if level_target else None,
                    "risk_reference_rr1": risk["target1_r_multiple"],
                    "scanner_entry_price_rule": {
                        "kind": entry_rule["kind"],
                        "comparable_with_daily_high_low": rule_known,
                        "trigger_price": entry_rule["trigger_price"],
                        "range_low": entry_rule["range_low"],
                        "range_high": entry_rule["range_high"],
                    },
                    "signal_close": float(signal_price) if signal_price else None,
                    "signal_close_equals_entry_reference": (
                        float(signal_price) == float(level_entry)
                        if signal_price is not None and level_entry is not None else None
                    ),
                    "earliest_eod_flags": first,
                    "completed_eod_sessions": len(days),
                    "sessions": sessions,
                    "actual_position_or_entry_confirmed": False,
                    "stop_order_executed": False,
                    "risk_response_at_the_time_verified": False,
                    "jev_result": None,
                })
    except ProspectiveEvaluationError as exc:
        raise ResearchCaptureError(exc.code) from exc

    return {
        "version": VERSION,
        "status": (
            "HOLD_UNRESOLVED_MARKET_SESSIONS" if unknown_sessions else
            "LOCAL_POSTHOC_RISK_EVENT_AUDIT_ONLY"
        ),
        "source_date": FROZEN_SOURCE_DATE, "market": FROZEN_MARKET,
        "as_of_date": as_of,
        "original_payload_hash": baseline["original_payload_hash"],
        "source_posthoc_not_precommitted": baseline["retrospective_not_prospective"],
        "unresolved_prior_weekdays": unknown_sessions,
        "candidate_count": len(records),
        "complete_eod_sessions": len(days),
        "stock_count_with_invalidation_touch": sum(
            any(s["invalidation_low_touched"] is True for s in r["sessions"])
            for r in records
        ),
        "stock_count_below_invalidation_at_close": sum(
            any(s["invalidation_close_at_or_below"] is True for s in r["sessions"])
            for r in records
        ),
        "stock_count_with_proven_real_entry": 0,
        "executed_stop_orders": 0,
        "market_network_requests": 0, "jev_model_calls": 0, "orders": 0,
        "production_db_writes": 0, "research_db_writes": 0,
        "scan_or_risk_recomputed": False,
        "stock_index_differences_are_descriptive_not_alpha": True,
        "realized_performance_or_jev_uplift_verified": False,
        "records": records,
        "limitations": [
            "S27 원본은 사후 기술 점검이므로 사전 추천 실적을 증명하지 않습니다.",
            "손절·목표가·진입가 모두 원본 참고가격이며 주문·체결을 의미하지 않습니다.",
            "OHLC 일봉에서 intraday 도달만 확인하며 진입과 손절의 선후관계/체결가/갭 손실을 알 수 없습니다.",
            "진입 규칙이 일봉 고저로 표현되지 않으면 달성 여부를 임의 추정하지 않습니다.",
            "KRX 원본 종가·고저가의 기업행위/수정주가 동일성은 별도 검증이 필요합니다.",
            "현재의 가격 데이터를 과거 판단 당시의 정보처럼 되돌려 사용하지 않습니다.",
            "실제 포지션·손절 주문·JEV 실종목 응답 및 투자 성과는 관측하지 않았습니다.",
        ],
    }
