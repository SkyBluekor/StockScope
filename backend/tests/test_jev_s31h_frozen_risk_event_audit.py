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
