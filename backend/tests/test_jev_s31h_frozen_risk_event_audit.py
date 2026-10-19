"""S31-H: source-locked risk prices versus subsequent synthetic OHLC."""
from __future__ import annotations

from copy import deepcopy
from datetime import date
import json
from pathlib import Path
import sqlite3

import pytest

from app.jev.research_scanner_s24 import SOURCE, ResearchCaptureError, digest
from app.jev.s31h_frozen_risk_event_audit import audit_frozen_risk
from tools.data import jev_s31h_risk_audit as cli


def _receipt():
    ident = {
        "strategy_key": "pullback",
        "strategy_version_id": "locked-version",
        "definition_hash": "locked-hash",
    }
    rows = []
    for i in range(5):
        rows.append({
            "code": f"{1800 + i:06d}", "name": f"합성종목{i}",
            "market": "KOSPI", "data_date": "2026-10-14",
            "strategy": "pullback",
            "strategy_version_id": ident["strategy_version_id"],
            "strategy_definition_hash": ident["definition_hash"],
            "action": "ENTRY_CANDIDATE",
            "risk": {"status": "READY", "warning": False},
            "conditions": {"passed": 9, "total": 9},
            "priority": {
                "rank": i + 1, "tie_group": 1, "tie_size": 5,
                "strict_rank": False,
                "tie_focus": i == 0, "tie_focus_order": 0 if i == 0 else 1,
                "tie_breaker": "STRUCTURAL_TARGET_NEAREST_PROMOTE",
                "structural_target_distance_pct": 2.0 + i,
                "historical_status": "DATA_UNAVAILABLE",
            },
            "entry_risk_guide": {
                "price_rule": {"kind": "RANGE", "range_low": 98, "range_high": 102},
                "risk": {
                    "entry_reference_price": 100,
                    "invalidation_price": 95,
                    "target1_price": 110,
                    "structural_target1_price": 104 + i,
                    "rr1": 2.0,
                },
            },
        })
    payload = {
        "version": "Q7_S24_ISOLATED_RESEARCH_SCANNER_V1",
        "authority": SOURCE, "execution_mode": "POSTHOC_TECHNICAL_SMOKE_ONLY",
        "source_date": "2026-10-14", "market_scope": "KOSPI",
        "q7_approval_eligible": False,
        "production_policy_activation_allowed": False,
        "trusted_precommit_timestamp_proven": False,
        "independent_capture_timestamp_proven": False,
        "market_publication_timestamp_proven": False,
        "jev_model_calls": 0,
        "original_strategy_rows": [ident],
        "original_scanner_candidates": rows,
        "candidate_count": 5, "entry_candidates": 5,
    }
    return {**payload, "payload_hash": digest(payload)}


def _seal(receipt):
    new = deepcopy(receipt)
    new.pop("payload_hash", None)
    return {**new, "payload_hash": digest(new)}


def _db(tmp_path, *, omit_day=None, omit_source_index=False, invalid_ohlc=False):
    db = tmp_path / "research.db"
    with sqlite3.connect(db) as conn:
        conn.executescript("""
        CREATE TABLE day_status (
          market TEXT, bas_dd TEXT, kind TEXT, status TEXT
        );
        CREATE TABLE stock_daily (
          market TEXT, bas_dd TEXT, stock_code TEXT, row_json TEXT
        );
        CREATE TABLE main_index_daily (
          market TEXT, bas_dd TEXT, row_json TEXT
        );
        """)
        for day, price, idx in (
            ("20261014", {"open": 100, "high": 101, "low": 99, "close": 100}, 3000),
            ("20261015", {"open": 99, "high": 101, "low": 94, "close": 96}, 2970),
            ("20261016", {"open": 94, "high": 97, "low": 91, "close": 92}, 2940),
        ):
            if day == omit_day:
                continue
            conn.executemany(
                "INSERT INTO day_status VALUES(?,?,?,?)",
                [("KOSPI", day, "stock", "data"), ("KOSPI", day, "index", "data")],
            )
            if not (omit_source_index and day == "20261014"):
                conn.execute("INSERT INTO main_index_daily VALUES(?,?,?)",
                    ("KOSPI", day, json.dumps({
                        "date": day, "name": "코스피", "close": idx,
                    })))
            for i in range(5):
                bar = dict(price)
                if invalid_ohlc and day == "20261015" and i == 0:
                    bar["high"] = 92  # below close and low-to-open range
                conn.execute(
                    "INSERT INTO stock_daily VALUES(?,?,?,?)",
                    ("KOSPI", day, f"{1800 + i:06d}",
                     json.dumps({"date": day, "code": f"{1800 + i:06d}", **bar})),
                )
    return db


def test_risk_reference_touch_with_market_context_and_no_execution(tmp_path):
    db = _db(tmp_path)
    receipt = _receipt()
    original = deepcopy(receipt)
    original_db = db.read_bytes()
    report = audit_frozen_risk(receipt, db, as_of="2026-10-16")
    assert receipt == original
    assert db.read_bytes() == original_db
    assert report["status"] == "LOCAL_POSTHOC_RISK_EVENT_AUDIT_ONLY"
    assert report["complete_eod_sessions"] == 2
    assert report["stock_count_with_invalidation_touch"] == 5
    assert report["stock_count_below_invalidation_at_close"] == 5
    assert report["stock_count_with_proven_real_entry"] == 0
    assert report["executed_stop_orders"] == 0
    assert report["jev_model_calls"] == report["orders"] == 0
    row = report["records"][0]
    assert row["risk_reference_invalidation"] == 95
    assert row["risk_reference_target1"] == 110
    assert row["risk_reference_rr1"] == 2.0
    assert row["signal_close_equals_entry_reference"] is True
    assert row["earliest_eod_flags"]["invalidation_low_touch"] == "2026-10-15"
    assert row["earliest_eod_flags"]["close_below_invalidation"] == "2026-10-16"
    assert row["earliest_eod_flags"]["open_at_or_below_invalidation"] == "2026-10-16"
    first = row["sessions"][0]
    assert first["stock_change_from_signal_close_pct"] == -4.0
    assert first["index_change_from_signal_close_pct"] == -1.0
    assert first["stock_minus_index_change_pp"] == -3.0
    assert first["entry_rule_touched"] is True
    assert first["invalidation_low_touched"] is True
    assert first["invalidation_close_at_or_below"] is False
    assert first["entry_and_invalidation_same_bar_order_unknown"] is True
    assert row["actual_position_or_entry_confirmed"] is False
    assert row["risk_response_at_the_time_verified"] is False


def test_as_of_cutoff_cannot_include_future_days(tmp_path):
    report = audit_frozen_risk(_receipt(), _db(tmp_path), as_of="2026-10-15")
    assert report["complete_eod_sessions"] == 1
    assert all(len(r["sessions"]) == 1 for r in report["records"])
    assert all(r["sessions"][0]["date"] == "2026-10-15" for r in report["records"])
    assert report["stock_count_below_invalidation_at_close"] == 0


def test_unknown_missing_market_weekday_holds_sequential_risk_inference(tmp_path):
    db = _db(tmp_path, omit_day="20261015")
    report = audit_frozen_risk(_receipt(), db, as_of="2026-10-16")
    assert report["status"] == "HOLD_UNRESOLVED_MARKET_SESSIONS"
    assert report["unresolved_prior_weekdays"] == ["2026-10-15"]
    assert report["complete_eod_sessions"] == 0
    assert all(not r["sessions"] for r in report["records"])
    assert report["stock_count_with_invalidation_touch"] == 0


def test_invalid_ohlc_does_not_prove_intraday_touches(tmp_path):
    db = _db(tmp_path, invalid_ohlc=True)
    report = audit_frozen_risk(_receipt(), db, as_of="2026-10-15")
    a = report["records"][0]["sessions"][0]
    assert a["ohlc_valid_for_intraday_touch"] is False
    assert a["entry_rule_touched"] is None
    assert a["invalidation_low_touched"] is None
    # Close value remains separately observed without inventing a valid high/low.
    assert a["stock_change_from_signal_close_pct"] == -4.0


def test_original_price_rule_missing_has_unknown_entry_touch(tmp_path):
    payload = _receipt()
    payload["original_scanner_candidates"][0]["entry_risk_guide"]["price_rule"] = {}
    report = audit_frozen_risk(_seal(payload), _db(tmp_path), as_of="2026-10-15")
    row = report["records"][0]
    assert row["scanner_entry_price_rule"]["comparable_with_daily_high_low"] is False
    assert row["sessions"][0]["entry_rule_touched"] is None
    assert row["sessions"][0]["invalidation_low_touched"] is True


def test_signal_benchmark_missing_does_not_fabricate_relative_alpha(tmp_path):
    db = _db(tmp_path, omit_source_index=True)
    report = audit_frozen_risk(_receipt(), db, as_of="2026-10-16")
    row = report["records"][0]["sessions"][0]
    assert row["index_change_from_signal_close_pct"] is None
    assert row["stock_minus_index_change_pp"] is None
    assert row["invalidation_low_touched"] is True


def test_tampered_receipt_fails_before_price_queries(tmp_path):
    receipt = _receipt()
    receipt["original_scanner_candidates"][0]["entry_risk_guide"]["risk"]["invalidation_price"] = 50
    with pytest.raises(ResearchCaptureError, match="S28_RECEIPT_PAYLOAD_HASH_MISMATCH"):
        audit_frozen_risk(receipt, tmp_path / "missing.db", as_of="2026-10-16")
    assert not (tmp_path / "missing.db").exists()


def test_missing_db_holds_without_creation(tmp_path):
    missing = tmp_path / "no.db"
    with pytest.raises(ResearchCaptureError, match="PROSPECTIVE_MARKET_STORE_NOT_FOUND"):
        audit_frozen_risk(_receipt(), missing, as_of="2026-10-16")
    assert not missing.exists()


def test_invalid_future_as_of_fails_closed(tmp_path):
    with pytest.raises(ResearchCaptureError, match="S31E_FUTURE_AS_OF_FORBIDDEN"):
        audit_frozen_risk(_receipt(), tmp_path / "missing", as_of="2099-01-01")


def test_cli_reports_reference_only_without_network_or_writes(tmp_path, capsys):
    db = _db(tmp_path)
    receipt_path = tmp_path / "receipt.json"
    receipt_path.write_text(json.dumps(_receipt(), ensure_ascii=False), encoding="utf-8")
    original = db.read_bytes()
    assert cli.main([
        "--receipt", str(receipt_path), "--market-db", str(db),
        "--as-of", "2026-10-16",
    ]) == 0
    rendered = capsys.readouterr().out
    assert "참고 무효화선" in rendered
    assert "2026-10-15" in rendered
    assert "원본·연구 DB 수정 0회" in rendered
    assert db.read_bytes() == original
    assert cli.main([
        "--receipt", str(receipt_path), "--market-db", str(db),
        "--as-of", "2026-10-16", "--json",
    ]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["complete_eod_sessions"] == 2
    assert result["realized_performance_or_jev_uplift_verified"] is False


def test_cli_missing_receipt_is_safe(tmp_path, capsys):
    assert cli.main([
        "--receipt", str(tmp_path / "absent.json"),
        "--market-db", str(tmp_path / "absent.db"),
        "--as-of", "2026-10-16",
    ]) == 2
    result = json.loads(capsys.readouterr().out)
    assert result["reason_code"] == "S31H_RECEIPT_MISSING_OR_TOO_LARGE"
    assert result["production_db_writes"] == 0

from app.jev.s31i_market_gap_diagnostic import analyze_market_gap
from tools.data import jev_s31i_gap_diagnostic as gap_cli


def test_s31i_observed_open_gap_and_risk_are_not_executions(tmp_path):
    db = _db(tmp_path)
    frozen = _receipt()
    before_receipt = deepcopy(frozen)
    before_db = db.read_bytes()
    result = analyze_market_gap(frozen, db, as_of="2026-10-16")
    assert result["status"] == "LOCAL_SIGNAL_ASOF_AND_POSTHOC_GAP_DIAGNOSTIC_ONLY"
    assert result["complete_eod_sessions"] == 2
    assert result["post_signal_open_below_invalidation_event_count"] == 5
    assert result["signal_day_known_information"]["production_regime_rule"] == "UNKNOWN"
    assert result["signal_day_known_information"]["next_day_return_used_in_signal_regime"] is False
    row = result["candidates"][0]
    assert row["original_risk_status"] == "READY"
    assert row["risk_ready_means_gap_protected"] is False
    assert row["original_strategy_price_rule"]["is_executable_buy_range"] is False
    assert row["actual_entry_or_position_proven"] is False
    assert row["days"][0]["opening_price"] == 99
    assert row["days"][0]["opening_gap_from_signal_close_pct"] == -1.0
    assert row["days"][0]["opening_gap_class"] == "OPEN_BELOW_SIGNAL_CLOSE_ABOVE_INVALIDATION"
    assert row["days"][1]["opening_price"] == 94
    assert row["days"][1]["opening_gap_from_signal_close_pct"] == -6.0
    assert row["days"][1]["opening_gap_class"] == "OPEN_AT_OR_BELOW_REFERENCE_INVALIDATION"
    assert row["days"][1]["actual_fill_or_stop_trigger_proven"] is False
    assert result["actual_entry_or_exit_proven"] is False
    assert result["decisions_or_captures_recomputed"] is False
    assert (result["market_network_requests"], result["jev_model_calls"],
            result["orders"], result["production_db_writes"]) == (0, 0, 0, 0)
    assert frozen == before_receipt
    assert db.read_bytes() == before_db


def test_s31i_signal_day_market_regime_is_asof_only(tmp_path):
    db = _db(tmp_path)
    with sqlite3.connect(db) as conn:
        conn.execute(
            "UPDATE main_index_daily SET row_json=? WHERE bas_dd='20261014'",
            (json.dumps({"date":"20261014", "name":"코스피",
                         "close":3000, "change_rate":-2.25}),),
        )
        conn.execute(
            "UPDATE main_index_daily SET row_json=? WHERE bas_dd='20261015'",
            (json.dumps({"date":"20261015", "name":"코스피",
                         "close":2970, "change_rate":+9.99}),),
        )
    result = analyze_market_gap(_receipt(), db, as_of="2026-10-15")
    market = result["signal_day_known_information"]
    assert market["original_index_daily_change_rate_pct"] == -2.25
    assert market["production_regime_rule"] == "TREND_DOWN"
    assert market["source_date"] == "2026-10-14"
    assert market["exact_original_scanner_regime_recorded_in_receipt"] is False
    assert result["complete_eod_sessions"] == 1
    assert all(len(record["days"]) == 1 for record in result["candidates"])
    assert result["post_signal_open_below_invalidation_event_count"] == 0


def test_s31i_invalid_ohlc_cannot_claim_open_gap(tmp_path):
    db = _db(tmp_path, invalid_ohlc=True)
    result = analyze_market_gap(_receipt(), db, as_of="2026-10-15")
    item = result["candidates"][0]["days"][0]
    assert item["opening_price"] is None
    assert item["opening_gap_from_signal_close_pct"] is None
    assert item["opening_gap_class"] == "OPENING_PRICE_UNAVAILABLE_OR_INVALID_BAR"
    assert item["original_strategy_condition_level_touched"] is None
    assert item["actual_fill_or_stop_trigger_proven"] is False


def test_s31i_missing_signal_index_does_not_guess_market_regime(tmp_path):
    db = _db(tmp_path, omit_source_index=True)
    result = analyze_market_gap(_receipt(), db, as_of="2026-10-16")
    info = result["signal_day_known_information"]
    assert info["original_index_daily_change_rate_pct"] is None
    assert info["production_regime_rule"] == "UNKNOWN"
    assert info["missing_index_rate_does_not_mean_range_market"] is True


def test_s31i_missing_intermediate_trading_day_holds(tmp_path):
    db = _db(tmp_path, omit_day="20261015")
    result = analyze_market_gap(_receipt(), db, as_of="2026-10-16")
    assert result["status"] == "HOLD_UNRESOLVED_MARKET_SESSIONS"
    assert result["unresolved_prior_weekdays"] == ["2026-10-15"]
    assert result["post_signal_open_below_invalidation_events"] == []
    assert all(not r["days"] for r in result["candidates"])


def test_s31i_tampered_frozen_receipt_fails_without_market_db(tmp_path):
    payload = _receipt()
    payload["original_scanner_candidates"][0]["name"] = "위조"
    missing = tmp_path / "does-not-exist.db"
    with pytest.raises(ResearchCaptureError, match="S28_RECEIPT_PAYLOAD_HASH_MISMATCH"):
        analyze_market_gap(payload, missing, as_of="2026-10-16")
    assert not missing.exists()


def test_s31i_cli_output_separates_strategy_conditions_from_trades(tmp_path, capsys):
    db = _db(tmp_path)
    receipt_path = tmp_path / "receipt.json"
    receipt_path.write_text(json.dumps(_receipt(), ensure_ascii=False), encoding="utf-8")
    before = db.read_bytes()
    assert gap_cli.main([
        "--receipt", str(receipt_path), "--market-db", str(db),
        "--as-of", "2026-10-16",
    ]) == 0
    output = capsys.readouterr().out
    assert "RANGE/ABOVE는 전략 조건" in output
    assert "시가부터 참고 무효화선 이하" in output
    assert "실제 매수·보유·손절 주문/체결" in output
    assert db.read_bytes() == before
    assert gap_cli.main([
        "--receipt", str(receipt_path), "--market-db", str(db),
        "--as-of", "2026-10-16", "--json",
    ]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["post_signal_open_below_invalidation_event_count"] == 5
    assert report["source_is_posthoc_not_prospectively_precommitted"] is True


def test_s31i_cli_missing_receipt_fails_closed(tmp_path, capsys):
    assert gap_cli.main([
        "--receipt", str(tmp_path / "no.json"),
        "--market-db", str(tmp_path / "no.db"), "--as-of", "2026-10-16",
    ]) == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "HOLD"
    assert payload["reason_code"] == "S31I_RECEIPT_MISSING_OR_TOO_LARGE"
    assert payload["production_db_writes"] == 0

from app.jev.s31j_prior_ready_recheck import evaluate_prior_ready
from tools.data import jev_s31j_recheck as recheck_cli


def test_s31j_prior_ready_rechecks_existing_risk_breach_without_executions(tmp_path):
    receipt = _receipt()
    db = _db(tmp_path)
    original = deepcopy(receipt)
    market_bytes = db.read_bytes()
    result = evaluate_prior_ready(receipt, db, as_of="2026-10-16")
    assert result["status"] == "LOCAL_PRIOR_READY_RECHECK_ONLY"
    assert result["last_confirmed_market_eod"] == "2026-10-16"
    assert result["unconfirmed_market_dates_through_asof"] == []
    assert result["prior_reference_breach_candidate_count"] == 5
    assert result["candidate_count"] == 5
    assert result["new_entry_permission"] is False
    assert result["today_live_quote_verified"] is False
    assert result["reran_scanner_or_risk"] is False
    assert (result["market_network_requests"], result["jev_model_calls"],
            result["orders"], result["production_db_writes"]) == (0, 0, 0, 0)
    candidate = result["candidates"][0]
    assert candidate["original_ready"] is True
    assert candidate["original_reference_invalidation_not_executed_stop"] == 95
    assert candidate["recheck_status"] == "PREVIOUS_RISK_REFERENCE_BREACHED"
    assert candidate["original_signal_date"] == "2026-10-14"
    assert candidate["actual_position_known"] is False
    assert candidate["entry_allowed_by_this_result"] is False
    assert candidate["past_reference_breach_count"] == 4
    assert candidate["last_stock_eod_price_field"] == "HISTORICAL_EOD_OPEN_NOT_LIVE_PRICE"
    assert candidate["last_stock_eod_price"] == 94
    assert db.read_bytes() == market_bytes
    assert receipt == original


def test_s31j_asof_missing_recent_weekday_holds_while_preserving_prior_events(tmp_path):
    result = evaluate_prior_ready(_receipt(), _db(tmp_path), as_of="2026-10-19")
    assert result["status"] == "HOLD_EOD_CONFIRMATION_REQUIRED"
    assert result["last_confirmed_market_eod"] == "2026-10-16"
    assert result["unconfirmed_market_dates_through_asof"] == ["2026-10-19"]
    assert result["unconfirmed_dates_are_not_proven_market_sessions"] is True
    assert all(r["recheck_status"] == "DATA_CONFIRMATION_REQUIRED"
               for r in result["candidates"])
    assert all(r["past_reference_breach_count"] > 0 for r in result["candidates"])
    assert result["new_entry_permission"] is False


def test_s31j_weekend_only_does_not_fabricate_data_gap(tmp_path):
    result = evaluate_prior_ready(_receipt(), _db(tmp_path), as_of="2026-10-18")
    assert result["status"] == "LOCAL_PRIOR_READY_RECHECK_ONLY"
    assert result["unconfirmed_market_dates_through_asof"] == []
    assert result["last_confirmed_market_eod"] == "2026-10-16"


def test_s31j_uncrossed_reference_still_expires_old_ready(tmp_path):
    db = _db(tmp_path)
    with sqlite3.connect(db) as conn:
        for day in ("20261015", "20261016"):
            for i in range(5):
                code = f"{1800+i:06d}"
                bar = {
                    "date": day, "code": code,
                    "open": 99, "high": 101, "low": 96, "close": 98,
                }
                conn.execute(
                    "UPDATE stock_daily SET row_json=? WHERE bas_dd=? AND stock_code=?",
                    (json.dumps(bar), day, code),
                )
    result = evaluate_prior_ready(_receipt(), db, as_of="2026-10-16")
    assert result["prior_reference_breach_candidate_count"] == 0
    assert all(x["recheck_status"] == "PREVIOUS_READY_RECHECK_REQUIRED"
               for x in result["candidates"])
    assert all(x["entry_allowed_by_this_result"] is False for x in result["candidates"])


def test_s31j_stock_latest_eod_unavailable_not_classified_safe(tmp_path):
    db = _db(tmp_path)
    with sqlite3.connect(db) as conn:
        conn.execute(
            "DELETE FROM stock_daily WHERE bas_dd='20261016' AND stock_code='001800'"
        )
    result = evaluate_prior_ready(_receipt(), db, as_of="2026-10-16")
    first = result["candidates"][0]
    assert first["recheck_status"] == "STOCK_EOD_UNAVAILABLE"
    assert first["last_stock_eod_price"] is None
    assert first["past_reference_breach_count"] >= 1
    assert all(x["entry_allowed_by_this_result"] is False for x in result["candidates"])


def test_s31j_negative_market_rate_only_latest_confirmed_eod(tmp_path):
    db = _db(tmp_path)
    with sqlite3.connect(db) as conn:
        conn.execute(
            "UPDATE main_index_daily SET row_json=? WHERE bas_dd='20261014'",
            (json.dumps({"date":"20261014", "name":"코스피",
                         "close":3000, "change_rate":-0.44}),),
        )
        conn.execute(
            "UPDATE main_index_daily SET row_json=? WHERE bas_dd='20261016'",
            (json.dumps({"date":"20261016", "name":"코스피",
                         "close":2940, "change_rate":-2.0}),),
        )
    result = evaluate_prior_ready(_receipt(), db, as_of="2026-10-16")
    asof = result["signal_day_market_context"]
    recent = result["market_context_latest_completed_eod"]
    assert asof["original_index_daily_change_rate_pct"] == -0.44
    assert asof["production_regime_rule"] == "RANGE"
    assert recent["daily_index_change_rate_pct"] == -2.0
    assert recent["production_regime"] == "TREND_DOWN"
    assert "LATEST_COMPLETED_EOD_MARKET_TREND_DOWN" in result["candidates"][0]["additional_market_context"]
    assert result["market_regime_not_a_new_gate"] is True


def test_s31j_missing_index_regime_is_unknown_and_not_assumed_safe(tmp_path):
    result = evaluate_prior_ready(_receipt(), _db(tmp_path), as_of="2026-10-16")
    assert result["market_context_latest_completed_eod"]["production_regime"] == "UNKNOWN"
    assert "LATEST_COMPLETED_EOD_MARKET_REGIME_UNKNOWN" in result["candidates"][0]["additional_market_context"]


def test_s31j_partial_source_day_data_stops_unknown_eod_sequence(tmp_path):
    result = evaluate_prior_ready(
        _receipt(), _db(tmp_path, omit_day="20261015"), as_of="2026-10-16",
    )
    assert result["status"] == "HOLD_EOD_CONFIRMATION_REQUIRED"
    assert result["unconfirmed_market_dates_through_asof"] == ["2026-10-15", "2026-10-16"]
    assert result["new_entry_permission"] is False


def test_s31j_invalid_ohlc_blocks_candidate_specific_eod(tmp_path):
    result = evaluate_prior_ready(
        _receipt(), _db(tmp_path, invalid_ohlc=True), as_of="2026-10-15",
    )
    assert result["candidates"][0]["recheck_status"] == "STOCK_EOD_UNAVAILABLE"
    assert result["candidates"][0]["last_stock_eod_price"] is None
    assert result["candidates"][1]["recheck_status"] == "PREVIOUS_RISK_REFERENCE_BREACHED"


def test_s31j_cli_readonly_and_json_report(tmp_path, capsys):
    db = _db(tmp_path)
    receipt_path = tmp_path / "receipt.json"
    receipt_path.write_text(json.dumps(_receipt(), ensure_ascii=False), encoding="utf-8")
    original = db.read_bytes()
    assert recheck_cli.main([
        "--receipt", str(receipt_path), "--market-db", str(db),
        "--as-of", "2026-10-16",
    ]) == 0
    human = capsys.readouterr().out
    assert "기존 READY 신규 진입 전 재검증" in human
    assert "과거 READY는 현재 매수 허가가 아닙니다" in human
    assert "실시간 호가" in human
    assert recheck_cli.main([
        "--receipt", str(receipt_path), "--market-db", str(db),
        "--as-of", "2026-10-16", "--json",
    ]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["candidate_count"] == 5
    assert payload["new_entry_permission"] is False
    assert db.read_bytes() == original


def test_s31j_cli_missing_eod_returns_hold_not_trade_approval(tmp_path, capsys):
    db = _db(tmp_path)
    receipt_path = tmp_path / "receipt.json"
    receipt_path.write_text(json.dumps(_receipt(), ensure_ascii=False), encoding="utf-8")
    assert recheck_cli.main([
        "--receipt", str(receipt_path), "--market-db", str(db),
        "--as-of", "2026-10-19", "--json",
    ]) == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "HOLD_EOD_CONFIRMATION_REQUIRED"
    assert payload["new_entry_permission"] is False


def test_s31j_tampered_receipt_aborts_before_market_read(tmp_path):
    receipt = _receipt()
    receipt["original_scanner_candidates"][0]["name"] = "forged"
    missing = tmp_path / "missing.sqlite"
    with pytest.raises(ResearchCaptureError, match="S28_RECEIPT_PAYLOAD_HASH_MISMATCH"):
        evaluate_prior_ready(receipt, missing, as_of="2026-10-16")
    assert not missing.exists()
