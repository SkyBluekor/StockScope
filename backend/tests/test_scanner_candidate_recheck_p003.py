"""P0-03: rechecking a prior Scanner candidate never creates a false NO_TRADE."""
from __future__ import annotations

from datetime import date
import pytest
from fastapi import HTTPException

from app.backtest.scanner_candidate_recheck import compare_scanner_candidate
from app.api.backtest import ScannerRequest, ScannerRecheckCandidate, _validate_scanner_recheck_request


def previous() -> dict:
    return {
        "market": "KOSPI", "code": "005930", "name": "Example",
        "source_data_date": "2026-10-21", "source_action": "ENTRY_CANDIDATE",
        "source_strategy": "BREAKOUT",
    }


def result() -> dict:
    return {
        "version": "0.21.3.9",
        "requested_as_of": "2026-10-23",
        "data_dates": {"KOSPI": "2026-10-23", "KOSDAQ": "2026-10-23"},
        "partial_data": False,
        "input_fingerprint": {
            "id": "fresh-fingerprint",
            "markets": {
                "KOSPI": {
                    "date": "2026-10-23", "stock_rows": 940,
                    "stock_hash": "stocks", "index_hash": "index",
                }
            },
        },
        "summary": {"candidate_count": 18},
        "candidates": [
            {"market": "KOSDAQ", "code": "000660", "data_date": "2026-10-23",
             "action": "ENTRY_CANDIDATE"},
        ],
        "more_candidates": [],
    }


def test_missing_from_top_n_is_not_no_trade() -> None:
    x = compare_scanner_candidate(previous=previous(), scanner_result=result())
    assert x["status"] == "NOT_IN_RETURNED_POOL"
    assert x["no_trade_inferred"] is False
    assert x["independently_evaluated_when_not_returned"] is False
    assert x["reported_action"] is None
    assert x["new_candidate"] is None
    assert x["new_eod_advanced"] is True


def test_found_in_extra_candidates_reports_real_current_strategy_and_risk() -> None:
    r = result()
    r["more_candidates"] = [{
        "market": "KOSPI", "code": "005930", "data_date": "2026-10-23",
        "action": "WAIT", "candidate_state": "WATCH",
        "strategy": "PULLBACK", "action_label": "관찰",
        "risk": {"status": "REVIEW"},
    }]
    x = compare_scanner_candidate(previous=previous(), scanner_result=r)
    assert x["status"] == "MATCHED_RETURNED_CANDIDATE"
    assert x["reported_action"] == "WAIT"
    assert x["reported_strategy"] == "PULLBACK"
    assert x["reported_risk_status"] == "REVIEW"
    assert x["no_trade_inferred"] is False


def test_missing_stock_input_or_stale_result_is_not_evaluable() -> None:
    r = result()
    r["input_fingerprint"]["markets"]["KOSPI"]["index_hash"] = None
    assert compare_scanner_candidate(previous=previous(), scanner_result=r)["status"] == "NOT_EVALUABLE"
    r = result()
    r["data_dates"]["KOSPI"] = "2026-10-20"
    assert compare_scanner_candidate(previous=previous(), scanner_result=r)["status"] == "NOT_EVALUABLE"
    r = result()
    r["partial_data"] = True
    assert compare_scanner_candidate(previous=previous(), scanner_result=r)["status"] == "NOT_EVALUABLE"


def test_same_date_reanalysis_is_not_claimed_as_new_eod() -> None:
    r = result()
    r["requested_as_of"] = "2026-10-21"
    r["data_dates"]["KOSPI"] = "2026-10-21"
    r["input_fingerprint"]["markets"]["KOSPI"]["date"] = "2026-10-21"
    x = compare_scanner_candidate(previous=previous(), scanner_result=r)
    assert x["status"] == "NOT_IN_RETURNED_POOL"
    assert x["new_eod_advanced"] is False


def test_recheck_must_use_newest_eod_job_not_pinned_old_date() -> None:
    old = ScannerRecheckCandidate(
        market="KOSPI", code="005930", name="Example",
        source_data_date=date(2026, 10, 21),
        source_action="ENTRY_CANDIDATE", source_strategy="BREAKOUT",
    )
    with pytest.raises(HTTPException) as exc:
        _validate_scanner_recheck_request(ScannerRequest(
            market_scope="ALL", as_of_date="2026-10-21",
            force_refresh=True, recheck_candidate=old,
        ))
    assert exc.value.status_code == 400
    assert exc.value.detail["code"] == "RECHECK_REQUIRES_LATEST_EOD"


def test_recheck_scope_and_force_refresh_are_enforced() -> None:
    old = ScannerRecheckCandidate(
        market="KOSDAQ", code="035720", name="Example",
        source_data_date=date(2026, 10, 21),
    )
    for payload in (
        ScannerRequest(market_scope="KOSPI", force_refresh=True, recheck_candidate=old),
        ScannerRequest(market_scope="ALL", force_refresh=False, recheck_candidate=old),
    ):
        with pytest.raises(HTTPException):
            _validate_scanner_recheck_request(payload)
    assert _validate_scanner_recheck_request(ScannerRequest(
        market_scope="ALL", force_refresh=True, recheck_candidate=old
    )) is None


def test_invalid_ticker_or_market_rejected_by_schema() -> None:
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        ScannerRecheckCandidate(market="KOSPI", code="BAD", source_data_date=date(2026, 10, 21))
