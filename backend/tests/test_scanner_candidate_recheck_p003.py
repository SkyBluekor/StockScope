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



def test_targeted_recheck_produces_out_of_rank_signal_without_rewriting_top_n() -> None:
    from types import SimpleNamespace
    from app.backtest.scanner_candidate_recheck import independently_recheck_unreturned_candidate

    class Store:
        def stock_day_rows(self, market, day):
            return [{"code": "005930", "name": "Example", "trade_value": 2_000_000_000}]
        def stock_series(self, market, code, start, end):
            return SimpleNamespace(rows={"20261023": {"date": "20261023"}})
        def index_series(self, market, start, end):
            return SimpleNamespace(rows={"20261023": {"date": "20261023"}})

    class Service:
        market_store = Store()
        engine = SimpleNamespace(LIQUIDITY_THRESHOLD=100)
        sector_prefetcher = None
        FAST_HISTORY_CALENDAR_DAYS = 220
        def _special_reason(self, row):
            return None
        def _quick_current_candidate(self, **kwargs):
            assert kwargs["selection_policy_pin"] == "PIN"
            return {"quick_current": True}
        def _current_candidate(self, quick):
            return {
                "action": "NO_TRADE", "action_label": "관망",
                "strategy": "PULLBACK", "candidate_state": "EXCLUDED",
                "risk": {"status": "REVIEW"},
            }

    r = result()
    x = independently_recheck_unreturned_candidate(
        service=Service(), previous=previous(), scanner_result=r,
        selection_policy_pin="PIN",
    )
    assert x["status"] == "TARGETED_EVALUATED_OUTSIDE_RANKING"
    assert x["scope"] == "TARGETED_CORE_NO_GLOBAL_RANK"
    assert x["targeted_action"] == "NO_TRADE"  # computed, never inferred from omission
    assert x["no_trade_inferred"] is False
    assert x["independently_evaluated_when_not_returned"] is True
    assert len(r["candidates"]) == 1
    assert r["candidates"][0]["code"] == "000660"


def test_targeted_recheck_stops_at_liquidity_before_strategy() -> None:
    from types import SimpleNamespace
    from app.backtest.scanner_candidate_recheck import independently_recheck_unreturned_candidate

    class Store:
        def stock_day_rows(self, market, day):
            return [{"code": "005930", "name": "Example", "trade_value": 10}]

    class Service:
        market_store = Store()
        engine = SimpleNamespace(LIQUIDITY_THRESHOLD=100)
        def _special_reason(self, row):
            return None
        def _quick_current_candidate(self, **kwargs):
            raise AssertionError("Must not evaluate non-liquid stock")

    x = independently_recheck_unreturned_candidate(
        service=Service(), previous=previous(), scanner_result=result(),
        selection_policy_pin=None,
    )
    assert x["status"] == "TARGET_OUTSIDE_SCANNER_FILTER"
    assert x["independently_evaluated_when_not_returned"] is False
    assert x.get("targeted_action") is None


def test_targeted_does_not_run_when_returned_candidate_already_has_real_decision() -> None:
    from app.backtest.scanner_candidate_recheck import independently_recheck_unreturned_candidate
    r = result()
    r["more_candidates"] = [{
        "market": "KOSPI", "code": "005930", "data_date": "2026-10-23",
        "action": "WAIT", "risk": {"status": "REVIEW"},
    }]
    x = independently_recheck_unreturned_candidate(
        service=object(), previous=previous(), scanner_result=r,
        selection_policy_pin=None,
    )
    assert x["status"] == "MATCHED_RETURNED_CANDIDATE"
    assert x["reported_action"] == "WAIT"



def test_recheck_report_carries_unverified_source_and_policy_mismatch() -> None:
    p = previous()
    p.update({
        "source_input_fingerprint_id": "old-hash",
        "source_policy_id": "POLICY-A",
        "source_policy_hash": "HASH-A",
        "source_capture_id": "old-capture",
    })
    r = result()
    r["strategy_selection_policy"] = {
        "policy_id": "POLICY-B", "policy_hash": "HASH-B",
    }
    outcome = compare_scanner_candidate(previous=p, scanner_result=r)
    assert outcome["source_input_fingerprint_id"] == "old-hash"
    assert outcome["source_capture_id"] == "old-capture"
    assert outcome["reference_verified_against_capture"] is False
    assert outcome["new_policy_id"] == "POLICY-B"
    assert outcome["policy_changed"] is True
    assert outcome["new_quote_checked"] is False


def test_old_policy_unknown_never_claims_policy_same() -> None:
    r = result()
    r["strategy_selection_policy"] = {"policy_id": "NEW", "policy_hash": "HASH"}
    p = previous()
    outcome = compare_scanner_candidate(previous=p, scanner_result=r)
    assert outcome["policy_changed"] is None


def test_result_binds_real_job_and_capture_but_not_outside_rank_capture() -> None:
    from app.backtest.scanner_candidate_recheck import attach_recheck_execution_lineage
    baseline = {"status": "CAPTURED", "capture_id": "base-capture-id"}
    outcome = attach_recheck_execution_lineage(
        recheck={"status": "TARGETED_EVALUATED_OUTSIDE_RANKING", "targeted_action": "WAIT"},
        source_job_id="job-abc",
        capture=baseline,
    )
    assert outcome["source_job_id"] == "job-abc"
    assert outcome["baseline_scanner_capture_id"] == "base-capture-id"
    assert outcome["baseline_scanner_capture_status"] == "CAPTURED"
    assert outcome["baseline_capture_scope"] == "SCANNER_RETURNED_CANDIDATES_ONLY"
    assert outcome["targeted_result_stored_in_capture"] is False
    assert outcome["prior_reference_stored_in_capture"] is False
    assert outcome["capture_confirmed"] is True
    assert outcome["targeted_action"] == "WAIT"


def test_failed_capture_must_not_invent_capture_id() -> None:
    from app.backtest.scanner_candidate_recheck import attach_recheck_execution_lineage
    outcome = attach_recheck_execution_lineage(
        recheck={"status": "NOT_EVALUABLE"},
        source_job_id="job-123",
        capture={"status": "SKIPPED_BASE_CAPTURE_NOT_READY"},
    )
    assert outcome["baseline_scanner_capture_id"] is None
    assert outcome["capture_confirmed"] is False
    assert outcome["baseline_scanner_capture_status"] == "SKIPPED_BASE_CAPTURE_NOT_READY"
