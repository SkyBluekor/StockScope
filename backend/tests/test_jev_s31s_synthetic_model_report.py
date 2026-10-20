"""S31-S: real model synthetic receipt projection is local/read-only and not Scanner AI."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from app.api.jev import get_jev_synthetic_actual_receipts
from app.jev.decision_reviewer_micro_canary import MicroJournal, synthetic_projection
from app.jev.synthetic_model_report_s31s import inspect_synthetic_actual_provider_receipts


def _db(tmp_path: Path) -> Path:
    path = tmp_path / "s6_micro_canary.sqlite3"
    with sqlite3.connect(path) as conn:
        MicroJournal(conn).initialize()
    return path


def _put(path: Path, *, origin: str = "ACTUAL_PROVIDER",
         case: str = "s5-condition-contradiction",
         decision: str = "REVIEW_REQUIRED", state: str = "VALID",
         hash_valid: bool = True, model_valid: bool = True) -> None:
    projection = synthetic_projection(case)
    expected = {"s5-consistent": "PASS_THROUGH",
                "s5-condition-contradiction": "REVIEW_REQUIRED",
                "s5-risk-contradiction": "REVIEW_REQUIRED",
                "s5-insufficient-evidence": "ABSTAIN",
                "s5-unresolved-ambiguity": "ABSTAIN"}[case]
    typed = {
        "decision": decision, "model": "jev-1.13.0",
        "requested_model": "jev-1.13.0" if model_valid else "unrelated",
        "model_identity_status": "PINNED_NAME_ONLY",
        "usage": {"input_tokens": 100, "output_tokens": 10},
    }
    with sqlite3.connect(path) as conn:
        n = conn.execute("SELECT COUNT(*) FROM jev_s5_synthetic").fetchone()[0]
        conn.execute(
            """INSERT INTO jev_s5_synthetic(
                review_id,protocol_hash,case_id,input_hash,request_hash,
                expected_gold,provider_id,model_id,state,decision,
                typed_response_json,reason_code,reserved_usd,computed_cost_usd,
                cost_status,execution_origin,created_at,completed_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (f"review-{n}", "test-protocol", case,
             projection["input_hash"] if hash_valid else "forged-input",
             "test-request", expected, "TYPESAFE_SYSTEM_ONE", "jev-1.13.0",
             state, decision if state == "VALID" else None,
             json.dumps(typed) if state == "VALID" else None, None, "0.01",
             "0.0000042" if state == "VALID" else None,
             "ESTIMATED_FROM_PUBLIC_STANDARD_RATE" if state == "VALID" else "UNKNOWN",
             origin, "2026-10-18T10:00:00Z",
             "2026-10-18T10:01:00Z" if state != "PENDING" else None),
        )
        conn.commit()


def test_absent_journal_is_not_created(tmp_path):
    path = tmp_path / "absent.sqlite3"
    result = inspect_synthetic_actual_provider_receipts(path)
    assert result["status"] == "NO_JOURNAL"
    assert result["actual_provider_attempts_recorded"] == 0
    assert result["model_calls_on_request"] == 0
    assert result["real_stock_models_reviewed"] == 0
    assert result["scanner_uplift_proven"] is False
    assert not path.exists()


def test_mock_only_never_appears_as_real_model(tmp_path):
    path = _db(tmp_path)
    _put(path, origin="MOCK_TEST")
    result = inspect_synthetic_actual_provider_receipts(path)
    assert result["status"] == "NO_ACTUAL_RECEIPTS"
    assert result["actual_valid_receipts"] == 0
    assert result["mock_rows_excluded"] == 1
    assert result["results"] == []


def test_actual_receipt_compares_model_choice_to_gold_read_only(tmp_path):
    path = _db(tmp_path)
    _put(path, origin="MOCK_TEST", case="s5-consistent")
    _put(path, origin="ACTUAL_PROVIDER", case="s5-condition-contradiction")
    _put(path, origin="ACTUAL_PROVIDER", case="s5-risk-contradiction", decision="ABSTAIN")
    before = path.read_bytes()
    result = inspect_synthetic_actual_provider_receipts(path)
    assert before == path.read_bytes()
    assert result["status"] == "ACTUAL_RECEIPTS_FOUND"
    assert result["actual_provider_attempts_recorded"] == 2
    assert result["actual_valid_receipts"] == 2
    assert result["correct_against_synthetic_gold"] == 1
    assert result["incorrect_against_synthetic_gold"] == 1
    assert result["mock_rows_excluded"] == 1
    assert {r["case_id"] for r in result["results"]} == {
        "s5-condition-contradiction", "s5-risk-contradiction",
    }
    assert all(r["receipt_status"] == "JOURNAL_CONSISTENCY_CHECK_PASSED"
               for r in result["results"])
    assert result["model_calls_on_request"] == 0
    assert result["external_requests_on_request"] == 0
    assert result["db_writes_on_request"] == 0
    assert result["provider_provenance"] == (
        "LOCAL_JOURNAL_ORIGIN_CLAIM_NOT_CRYPTOGRAPHICALLY_ATTESTED"
    )
    assert result["scanner_uplift_proven"] is False


def test_untrusted_actual_origin_claim_with_bad_hash_is_excluded(tmp_path):
    path = _db(tmp_path)
    _put(path, hash_valid=False)
    _put(path, model_valid=False)
    result = inspect_synthetic_actual_provider_receipts(path)
    assert result["actual_provider_attempts_recorded"] == 2
    assert result["actual_valid_receipts"] == 0
    assert result["unverified_receipt_rows"] == 2
    assert result["results"] == []


def test_errors_are_not_counted_as_valid_model_decisions(tmp_path):
    path = _db(tmp_path)
    _put(path, state="ERROR")
    result = inspect_synthetic_actual_provider_receipts(path)
    assert result["actual_provider_attempts_recorded"] == 1
    assert result["actual_valid_receipts"] == 0
    assert result["results"][0]["observed"] is None
    assert result["results"][0]["receipt_status"] == "ATTEMPT_RECORDED_NOT_VALIDATED"


def test_missing_or_incomplete_schema_is_fail_closed(tmp_path):
    p = tmp_path / "empty.sqlite3"
    with sqlite3.connect(p) as c:
        c.execute("CREATE TABLE irrelevant (x TEXT)")
    assert inspect_synthetic_actual_provider_receipts(p)["status"] == "JOURNAL_SCHEMA_UNAVAILABLE"
    with sqlite3.connect(p) as c:
        c.execute("CREATE TABLE jev_s5_synthetic (execution_origin TEXT)")
    assert inspect_synthetic_actual_provider_receipts(p)["status"] == "JOURNAL_SCHEMA_UNAVAILABLE"


def test_api_uses_exact_default_research_path_not_scanner(tmp_path, monkeypatch):
    path = _db(tmp_path)
    _put(path)
    import app.jev.synthetic_model_report_s31s as mod
    import app.api.jev as api
    monkeypatch.setattr(mod, "DEFAULT_JOURNAL", path)
    # API import has a function object using an unrelated default argument:
    # explicit injected wrapper proves the route does not ask a provider.
    monkeypatch.setattr(
        api, "inspect_synthetic_actual_provider_receipts",
        lambda: mod.inspect_synthetic_actual_provider_receipts(path),
    )
    answer = get_jev_synthetic_actual_receipts()
    assert answer["scope"] == "SYNTHETIC_ONLY"
    assert answer["actual_valid_receipts"] == 1
    assert answer["model_calls_on_request"] == 0
