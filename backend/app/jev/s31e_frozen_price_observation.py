"""S31-E local-only price observations for the frozen S27 2026-10-14 KOSPI receipt.

Reuse StockScope's existing ProspectiveEvaluator observation-only path, with
complete EOD evidence and an explicit as-of ceiling. Unlike a prospective
precommit or backtest, the S27 receipt was a posthoc technical smoke. Returns
are changes from signal-day CLOSE, not executable entry/strategy outcomes.
No provider, market fetch, order, DB write, or rights escalation exists here.
"""
from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Any

from zoneinfo import ZoneInfo

from app.jev.s31_real_candidate_trial import inspect_frozen_candidates
from app.jev.research_scanner_s24 import ResearchCaptureError
from app.prospective.evaluation import (
    ProspectiveEvaluator, ProspectiveEvaluationError, ReadOnlyMarketEvidence,
)

VERSION = "JEV_ACT2_S31E_FROZEN_PRICE_OBSERVATION_V1"
FROZEN_SOURCE_DATE = "2026-10-14"
FROZEN_MARKET = "KOSPI"
WINDOWS = (5, 10, 20)


def _as_of_date(value: str) -> str:
    try:
        parsed = date.fromisoformat(value)
    except (ValueError, TypeError) as exc:
        raise ResearchCaptureError("S31E_AS_OF_DATE_INVALID") from exc
    if parsed.isoformat() != value:
        raise ResearchCaptureError("S31E_AS_OF_DATE_INVALID")
    if parsed < date.fromisoformat(FROZEN_SOURCE_DATE):
        raise ResearchCaptureError("S31E_AS_OF_BEFORE_FROZEN_SOURCE")
    if parsed > datetime.now(ZoneInfo("Asia/Seoul")).date():
        raise ResearchCaptureError("S31E_FUTURE_AS_OF_FORBIDDEN")
    return value


def observe_frozen_candidates(
    receipt: dict[str, Any], market_db: Path, *, as_of: str,
) -> dict[str, Any]:
    """Only genuine existing local EOD rows can contribute 5/10/20 day values."""
    as_of = _as_of_date(as_of)
    baseline = inspect_frozen_candidates(receipt, limit=5)
    if (baseline["source_date"] != FROZEN_SOURCE_DATE
            or baseline["market"] != FROZEN_MARKET
            or baseline["original_entry_count"] != 5
            or baseline["inspected_entry_count"] != 5):
        raise ResearchCaptureError("S31E_FROZEN_RECEIPT_SCOPE_MISMATCH")

    local_db = Path(market_db)
    if not local_db.is_file():
        raise ResearchCaptureError("S31E_MARKET_DB_NOT_FOUND")
    # Check that the existing DB can actually support strictly completed EOD
    # windows. Even a valid SQLite file can have an incomplete/old schema.
    source = ReadOnlyMarketEvidence(local_db)
    try:
        with source.connect() as conn:
            for table in ("day_status", "stock_daily", "main_index_daily"):
                if not conn.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                    (table,),
                ).fetchone():
                    raise ResearchCaptureError("S31E_MARKET_DB_SCHEMA_MISSING")
    except ProspectiveEvaluationError as exc:
        raise ResearchCaptureError(exc.code) from exc

    evaluator = ProspectiveEvaluator(local_db)
    raw = {row["code"]: row for row in receipt["original_scanner_candidates"]}
    rows = []
    for index, candidate in enumerate(baseline["candidates"]):
        code = candidate["code"]
        sample = {
            "capture_run_id": "S31E_LOCAL_S27_POSTHOC_NOT_PROSPECTIVE",
            "sample_index": index,
            "signal_date": baseline["source_date"],
            "market": baseline["market"],
            "ticker": code,
            "strategy": candidate["baseline"]["strategy"],
            "snapshot": raw[code],
        }
        try:
            observed = evaluator.evaluate_sample(
                sample=sample,
                spec={
                    "observation_windows": list(WINDOWS),
                    "max_holding_days": 20,
                    "execution_mode": "OBSERVATION_ONLY",
                    "require_complete_market_eod": True,
                    "as_of_date": as_of,
                },
            )
        except ProspectiveEvaluationError as exc:
            # Keep the baseline and the missing data explicit, never fabricate
            # a close or treat an unavailable outcome as a zero return.
            rows.append({
                "code": code, "name": candidate["name"],
                "baseline": candidate["baseline"],
                "observation_status": "UNAVAILABLE",
                "reason_code": exc.code,
                "signal_close_reference": None,
                "completed_market_days_after_signal": 0,
                "evaluated_through": None,
                "windows": {
                    f"{n}d": {"status": "UNAVAILABLE", "return_pct": None,
                              "end_date": None}
                    for n in WINDOWS
                },
                "jev_decision": None,
                "investment_outcome": None,
            })
            continue
        details = observed.get("details") or {}
        close = details.get("reference_price")
        count = observed["available_trading_days"]
        windows = {}
        for n in WINDOWS:
            ret = observed.get(f"return_{n}d")
            end_date = (details.get("observation_window_end_dates") or {}).get(f"{n}d")
            if close is None:
                status = "SIGNAL_CLOSE_UNAVAILABLE"
            elif count < n:
                status = "NOT_YET_N_COMPLETE_MARKET_DAYS"
            elif ret is None:
                status = "TARGET_DAY_STOCK_CLOSE_UNAVAILABLE"
            else:
                status = "OBSERVED_SIGNAL_CLOSE_CHANGE_ONLY"
            windows[f"{n}d"] = {
                "status": status, "return_pct": ret if status.startswith("OBSERVED") else None,
                "end_date": end_date if status.startswith("OBSERVED") else None,
            }
        ready = sum(v["status"].startswith("OBSERVED") for v in windows.values())
        rows.append({
            "code": code, "name": candidate["name"],
            "baseline": candidate["baseline"],
            "observation_status": (
                "ALL_THREE_WINDOWS_OBSERVED" if ready == 3 else
                "PARTIAL_OR_UNAVAILABLE"
            ),
            "reason_code": "SIGNAL_CLOSE_REFERENCE_ONLY_NOT_EXECUTABLE",
            "signal_close_reference": close,
            "completed_market_days_after_signal": count,
            "evaluated_through": observed["evaluated_through"],
            "windows": windows,
            "jev_decision": None,
            "investment_outcome": None,
        })
    observed_counts = {
        f"{n}d": sum(
            row["windows"][f"{n}d"]["status"] == "OBSERVED_SIGNAL_CLOSE_CHANGE_ONLY"
            for row in rows
        )
        for n in WINDOWS
    }
    return {
        "version": VERSION,
        "status": "LOCAL_POSTHOC_EOD_OBSERVATION_ONLY",
        "receipt_payload_hash": baseline["original_payload_hash"],
        "source_date": baseline["source_date"],
        "as_of_date": as_of,
        "market": baseline["market"],
        "candidate_count": len(rows),
        "observed_window_counts": observed_counts,
        "complete_market_day_definition": (
            "day_status stock+index data AND any stock_daily AND main_index_daily "
            "on the same market/day; candidate closing price independently required"
        ),
        "return_definition": (
            "100 * (NTH_COMPLETED_MARKET_DAY_CLOSE / SIGNAL_DATE_CLOSE - 1)"
        ),
        "signal_close_is_executable_entry": False,
        "price_observation_is_strategy_return": False,
        "q7_prospective_precommit_proven": False,
        "posthoc_technical_smoke": baseline["retrospective_not_prospective"],
        "source_release_time_independently_proven": False,
        "real_jev_model_results": False,
        "investment_uplift_proven": False,
        "real_stock_provider_eligible": False,
        "jev_model_calls": 0,
        "market_network_requests": 0,
        "production_db_writes": 0,
        "research_db_writes": 0,
        "orders": 0,
        "candidates": rows,
        "limitations": [
            "원본 S27은 사후 기술 점검으로 사전 추천·Q7 예측 적중률 근거가 아닙니다.",
            "5·10·20 거래일 종가 변화율은 가상 매수 체결·세금·수수료·슬리피지 미반영입니다.",
            "기준일 종가는 Scanner 위험관리 진입 참고가 또는 실제 체결가와 다릅니다.",
            "로컬 DB에 없는 일별 기록은 보간하거나 온라인 보충하지 않습니다.",
            "기업행위/수정주가 검증과 독립 공개 시각 검증이 없으면 투자 성과로 해석하지 않습니다.",
            "동일 후보의 실제 JEV 응답이 없으므로 JEV 추가 효과를 계산할 수 없습니다.",
        ],
    }
