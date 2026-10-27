"""P0-05/G0b: map true S16 shape to bounded, safe counts; fail closed."""
from __future__ import annotations

from datetime import date
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest

from tools.data import p0_05_s16_readonly_coverage as audit
from tools.data.migrate_prospective_vnp2s2 import migrate_prospective_store


def _files(tmp_path: Path):
    sim, market = tmp_path / "simulation.db", tmp_path / "market.db"
    sqlite3.connect(sim).close()
    migrate_prospective_store(sim)
    with sqlite3.connect(market) as conn:
        conn.executescript(
            "CREATE TABLE day_status(market TEXT,bas_dd TEXT,kind TEXT,status TEXT);"
            "CREATE TABLE main_index_daily(market TEXT,bas_dd TEXT,row_json TEXT);"
        )
        for i in range(7):
            # Recognized actual dates in the synthetic market evidence.
            day = ["20261012","20261013","20261014","20261015",
                   "20261016","20261019","20261020"][i]
            conn.execute("INSERT INTO day_status VALUES('KOSPI',?,'stock','data')", (day,))
            conn.execute("INSERT INTO main_index_daily VALUES('KOSPI',?,'{}')", (day,))
    with sqlite3.connect(sim) as conn:
        conn.execute(
            "INSERT INTO prospective_capture_run("
            "id,capture_version,source_job_id,status,request_json,market_scope,"
            "horizon_intent,candidate_limit,created_at,updated_at,"
            "actual_data_date,scanner_version,scanner_baseline,"
            "input_fingerprint,horizon_policy_version,completed_at,"
            "returned_candidate_count)"
            " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            ("CAPTURE_PRIVATE_1","VERSION","job-private","COMPLETE","{}","KOSPI",
             "UNSPECIFIED",2,"2026-10-13T07:00:00+09:00","2026-10-13T07:10:00+09:00",
             "2026-10-12","scanner-1",None,"HASH_PRIVATE",None,
             "2026-10-13T07:10:00+09:00",2),
        )
        for i, action in enumerate(("ENTRY_CANDIDATE", "REFERENCE_ONLY")):
            conn.execute(
                "INSERT INTO prospective_recommendation_sample("
                "capture_run_id,sample_index,market,ticker,name,action,signal_date,"
                "snapshot_json,snapshot_hash,created_at)"
                " VALUES(?,?,?,?,?,?,?,?,?,?)",
                ("CAPTURE_PRIVATE_1",i,"KOSPI","PRIVATE_TICKER","Private Name",action,
                 "2026-10-12", '{"token":"PRIVATE_SNAPSHOT"}',
                 "PRIVATE_HASH","2026-10-13T07:10:00+09:00"),
            )
    return sim, market


def _payload():
    return {
        "version": "Q7_S16_READONLY_COHORT_MATURITY_V1",
        "status": "DESCRIPTIVE_OBSERVATIONS_ONLY",
        "counts_complete": True,
        "market_eod_cutoff_date": "2026-10-23",
        "total_complete_captures": 1,
        "sample_count": 2,
        "entry_candidates": 1,
        "reference_only": 1,
        "integrity_counts": {"LOCAL_VALIDATED": 1,"LEGACY_LIMITED": 0,"INVALID": 0},
        "invalid_check_failure_counts": {
            name: 0 for name in (
                "rank", "strategy", "policy", "engine", "dates", "risk", "strict_s3"
            )
        },
        "invalid_reason_code_counts": {},
        "invalid_without_failed_checks": 0,
        "invalid_reason_counts_can_overlap": True,
        "gap_subtypes_are_not_independent_calendar_proof": True,
        "excluded_reason_counts": {},
        "completion_timing_counts": {"NEXT_CALENDAR_DAY_BEFORE_09_KST_UNVERIFIED": 1},
        "windows": {
            "5d": {"readiness_denominator":1, "observed":1,
                   "awaiting_future_trading_days":0, "price_missing":0,
                   "market_evidence_unavailable":0, "post_as_of_data_rejected":0,
                   "unverified_calendar_or_market_gap":0,
                   "gap_with_insufficient_confirmed_sessions":0,
                   "gap_with_sufficient_confirmed_sessions":0,
                   "average_signal_close_change_pct":13.37},
            "10d": {"readiness_denominator":1, "observed":0,
                    "awaiting_future_trading_days":1, "price_missing":0,
                    "market_evidence_unavailable":0, "post_as_of_data_rejected":0,
                    "unverified_calendar_or_market_gap":0,
                    "gap_with_insufficient_confirmed_sessions":0,
                    "gap_with_sufficient_confirmed_sessions":0,
                    "average_signal_close_change_pct":None},
            "20d": {"readiness_denominator":1, "observed":0,
                    "awaiting_future_trading_days":1, "price_missing":0,
                    "market_evidence_unavailable":0, "post_as_of_data_rejected":0,
                    "unverified_calendar_or_market_gap":0,
                    "gap_with_insufficient_confirmed_sessions":0,
                    "gap_with_sufficient_confirmed_sessions":0,
                    "average_signal_close_change_pct":None},
        },
        "strategy_counts": {"PRIVATE_STRATEGY": {"SECRET":"PRIVATE"}},
        "notes": ["SECRET_NOT_OUTPUT"],
    }


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _mock_s16(monkeypatch, payload):
    import app.jev.q7_observation_s16 as s16
    monkeypatch.setattr(s16, "measure", lambda *_a, **_kw: payload)


def test_true_g0_inspection_plus_genuine_s16_shape_is_redacted(tmp_path, monkeypatch):
    sim, market = _files(tmp_path)
    _mock_s16(monkeypatch, _payload())
    before = (_sha(sim), _sha(market))
    result = audit.inspect(sim, market, as_of=date(2026, 10, 23))
    assert result["status"] == "READ_ONLY_S16_OBSERVATION_COVERAGE_OBSERVED"
    assert result["on_demand_window_status_counts"]["5d"]["observed"] == 1
    assert result["on_demand_window_status_counts"]["10d"]["awaiting_future_trading_days"] == 1
    assert result["stored_evaluation_run_rows"] == 0
    assert result["stored_evaluation_unit_rows"] == 0
    assert result["source_missing_field_counts"] == {
        "scanner_baseline":1,"horizon_policy_version":1,
    }
    assert result["q7_approval_eligible"] is False
    assert result["db_write_calls"] == result["external_requests"] == 0
    output = json.dumps(result)
    for secret in ("PRIVATE_TICKER", "PRIVATE_SNAPSHOT", "PRIVATE_STRATEGY",
                   "PRIVATE_HASH", "CAPTURE_PRIVATE_1", "13.37"):
        assert secret not in output
    assert (_sha(sim), _sha(market)) == before


def test_s16_integrity_exclusion_preserves_distinct_denominators(tmp_path, monkeypatch):
    sim, market = _files(tmp_path)
    value = _payload()
    value["integrity_counts"] = {"LOCAL_VALIDATED": 0,"LEGACY_LIMITED": 0,"INVALID": 1}
    value["excluded_reason_counts"] = {"FROZEN_INTEGRITY_INVALID":1}
    value["invalid_check_failure_counts"]["policy"] = 1
    value["invalid_reason_code_counts"] = {"POLICY_PROVENANCE_UNVERIFIED":1}
    for win in value["windows"].values():
        win["readiness_denominator"] = 0
        win["observed"] = 0
        win["awaiting_future_trading_days"] = 0
    _mock_s16(monkeypatch, value)
    result = audit.inspect(sim, market, as_of=date(2026, 10, 23))
    assert result["status"] == "READ_ONLY_S16_OBSERVATION_COVERAGE_OBSERVED"
    assert result["captured_entry_rows"] == 1
    assert result["integrity_eligible_for_readonly_observation"] == 0
    assert result["on_demand_window_status_counts"]["5d"]["observed"] == 0
    assert result["excluded_reason_counts"] == {"FROZEN_INTEGRITY_INVALID":1}


def test_window_coverage_categories_must_add_to_denominator(tmp_path, monkeypatch):
    sim, market = _files(tmp_path)
    value = _payload()
    value["windows"]["5d"]["price_missing"] = 1
    _mock_s16(monkeypatch, value)
    result = audit.inspect(sim, market, as_of=date(2026, 10, 23))
    assert result["status"] == "HOLD_S16_WINDOW_DENOMINATOR_MISMATCH"
    assert "on_demand_window_status_counts" not in result


def test_unknown_code_or_payload_never_exposes_secret_exception(tmp_path, monkeypatch):
    sim, market = _files(tmp_path)
    value = _payload()
    value["excluded_reason_counts"] = {"PRIVATE_TOKEN_LEAK!":1}
    _mock_s16(monkeypatch, value)
    assert audit.inspect(sim, market, as_of=date(2026, 10, 23))["status"] == "HOLD_S16_REASON_CONTRACT_INVALID"
    import app.jev.q7_observation_s16 as s16
    def boom(*args, **kwargs):
        raise ValueError("PRIVATE_TICKER SECRET_ACCOUNT")
    monkeypatch.setattr(s16, "measure", boom)
    output = json.dumps(audit.inspect(sim, market, as_of=date(2026, 10, 23)))
    assert "HOLD_S16_RUNTIME_EXCEPTION" in output
    assert "PRIVATE_TICKER" not in output


def test_g0_not_ready_prevents_running_s16(tmp_path, monkeypatch):
    sim, market = _files(tmp_path)
    with sqlite3.connect(sim) as conn:
        conn.execute("DELETE FROM prospective_recommendation_sample")
    import app.jev.q7_observation_s16 as s16
    monkeypatch.setattr(s16, "measure", lambda *_a, **_kw: pytest.fail("S16 should not run"))
    result = audit.inspect(sim, market, as_of=date(2026, 10, 23))
    assert result["status"] == "HOLD_G0_INVENTORY_NOT_READY"
    assert result["g0_status"] == "HOLD_INCONSISTENT_CAPTURE_EVIDENCE"


def test_real_s16_failed_integrity_does_not_claim_observed(tmp_path):
    # Source capture sample hash invalid: genuine S16 loader must fail closed.
    sim, market = _files(tmp_path)
    result = audit.inspect(sim, market, as_of=date(2026, 10, 23))
    assert result["status"].startswith("HOLD_")
    assert result["operational_db_read_only"] is True
    assert "on_demand_window_status_counts" not in result


def test_cli_fails_without_db_and_redacts_source_paths(tmp_path):
    script = Path(__file__).resolve().parents[2] / "tools/data/p0_05_s16_readonly_coverage.py"
    sim = tmp_path / "SECRET_SIMULATION.db"
    market = tmp_path / "SECRET_MARKET.db"
    cmd = [sys.executable, str(script), "--simulation-db", str(sim), "--market-db", str(market)]
    result = subprocess.run(cmd, capture_output=True, text=True)
    assert result.returncode == 2
    out = json.loads(result.stdout)
    assert out["status"] == "HOLD_G0_INVENTORY_NOT_READY"
    assert "SECRET_SIMULATION" not in result.stdout
    assert "SECRET_MARKET" not in result.stdout
    assert not sim.exists() and not market.exists()


def test_network_attempt_is_blocked_and_not_reported_as_success(tmp_path, monkeypatch):
    sim, market = _files(tmp_path)
    import app.jev.q7_observation_s16 as s16
    def go_network(*_args, **_kw):
        import socket
        sock = socket.socket()
        try:
            sock.connect(("198.51.100.23",443))
        finally:
            sock.close()
    monkeypatch.setattr(s16, "measure", go_network)
    result = audit.inspect(sim, market, as_of=date(2026, 10, 23))
    assert result["status"] in {"HOLD_S16_NETWORK_ATTEMPT_BLOCKED","HOLD_S16_RUNTIME_EXCEPTION"}
    assert result["external_requests"] == 0


def test_invalid_check_counts_can_overlap_without_claiming_unique_candidates(tmp_path, monkeypatch):
    sim, market = _files(tmp_path)
    value = _payload()
    value["integrity_counts"] = {"LOCAL_VALIDATED": 0, "LEGACY_LIMITED": 0, "INVALID": 1}
    value["invalid_check_failure_counts"].update({
        "policy": 1, "dates": 1, "strict_s3": 1,
    })
    value["invalid_reason_code_counts"] = {
        "POLICY_PROVENANCE_UNVERIFIED": 1,
        "DATE_MISMATCH": 1,
        "S3_CONTRACT_UNSATISFIED": 1,
    }
    value["excluded_reason_counts"] = {"FROZEN_INTEGRITY_INVALID":1}
    for win in value["windows"].values():
        win["readiness_denominator"] = 0
        win["observed"] = 0
        win["awaiting_future_trading_days"] = 0
    _mock_s16(monkeypatch, value)
    result = audit.inspect(sim, market, as_of=date(2026, 10, 23))
    assert result["status"] == "READ_ONLY_S16_OBSERVATION_COVERAGE_OBSERVED"
    assert result["frozen_integrity_categories"]["INVALID"] == 1
    assert result["invalid_check_failure_counts"]["policy"] == 1
    assert result["invalid_check_failure_counts"]["dates"] == 1
    assert result["invalid_reason_counts_can_overlap"] is True


def test_gap_subtypes_must_sum_to_gap_and_avoid_immaturity_claim(tmp_path, monkeypatch):
    sim, market = _files(tmp_path)
    value = _payload()
    value["windows"]["5d"]["observed"] = 0
    value["windows"]["5d"]["unverified_calendar_or_market_gap"] = 1
    value["windows"]["5d"]["gap_with_insufficient_confirmed_sessions"] = 1
    _mock_s16(monkeypatch, value)
    result = audit.inspect(sim, market, as_of=date(2026, 10, 23))
    assert result["status"] == "READ_ONLY_S16_OBSERVATION_COVERAGE_OBSERVED"
    assert result["on_demand_window_status_counts"]["5d"]["gap_with_insufficient_confirmed_sessions"] == 1
    assert result["gap_with_insufficient_sessions_is_not_proven_immature"] is True
    value["windows"]["5d"]["gap_with_insufficient_confirmed_sessions"] = 0
    assert audit.inspect(sim, market, as_of=date(2026, 10, 23))["status"] == "HOLD_S16_GAP_SUBTYPE_CONTRACT"


def test_bad_invalid_diagnostics_do_not_return_partial_output(tmp_path, monkeypatch):
    sim, market = _files(tmp_path)
    value = _payload()
    value["invalid_check_failure_counts"]["policy"] = 4
    _mock_s16(monkeypatch, value)
    result = audit.inspect(sim, market, as_of=date(2026, 10, 23))
    assert result["status"] == "HOLD_S16_INVALID_DIAGNOSTICS_CONTRACT"
    assert result["diagnostic_failure_class"] == "CHECK_BUCKET_EXCEEDS_INVALID_CANDIDATES"
    assert "on_demand_window_status_counts" not in result


def test_g0d_more_than_one_unknown_reason_from_same_invalid_is_never_accepted(
    tmp_path, monkeypatch,
):
    sim, market = _files(tmp_path)
    value = _payload()
    value["integrity_counts"] = {
        "LOCAL_VALIDATED": 0, "LEGACY_LIMITED": 0, "INVALID": 1,
    }
    value["invalid_check_failure_counts"]["policy"] = 1
    value["invalid_reason_code_counts"] = {"OTHER_S7_CODE": 2}
    value["excluded_reason_counts"] = {"FROZEN_INTEGRITY_INVALID": 1}
    for win in value["windows"].values():
        win["readiness_denominator"] = 0
        win["observed"] = 0
        win["awaiting_future_trading_days"] = 0
    _mock_s16(monkeypatch, value)
    result = audit.inspect(sim, market, as_of=date(2026, 10, 23))
    assert result["status"] == "HOLD_S16_INVALID_DIAGNOSTICS_CONTRACT"
    assert result["diagnostic_failure_class"] == "REASON_BUCKET_EXCEEDS_INVALID_CANDIDATES"
    assert "on_demand_window_status_counts" not in result
    assert "PRIVATE" not in json.dumps(result)
    assert result["db_write_calls"] == 0


def test_g0d_valid_collapsed_unknown_reason_still_requires_matching_windows(
    tmp_path, monkeypatch,
):
    sim, market = _files(tmp_path)
    value = _payload()
    value["integrity_counts"] = {
        "LOCAL_VALIDATED": 0, "LEGACY_LIMITED": 0, "INVALID": 1,
    }
    value["invalid_check_failure_counts"]["policy"] = 1
    value["invalid_reason_code_counts"] = {"OTHER_S7_CODE": 1}
    value["excluded_reason_counts"] = {"FROZEN_INTEGRITY_INVALID": 1}
    for win in value["windows"].values():
        win["readiness_denominator"] = 0
        win["observed"] = 0
        win["awaiting_future_trading_days"] = 0
    _mock_s16(monkeypatch, value)
    report = audit.inspect(sim, market, as_of=date(2026, 10, 23))
    assert report["status"] == "READ_ONLY_S16_OBSERVATION_COVERAGE_OBSERVED"
    assert report["invalid_reason_code_counts"] == {"OTHER_S7_CODE": 1}
    assert report["frozen_integrity_categories"]["INVALID"] == 1
    assert report["on_demand_window_status_counts"]["5d"]["observed"] == 0
