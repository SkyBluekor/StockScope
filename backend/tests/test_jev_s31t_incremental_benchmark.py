"""Scenario-level value audit: no denominator inflation and no stock-alpha claim."""
from __future__ import annotations

from app.jev.synthetic_incremental_benchmark_s31t import compare_synthetic_cases
from app.jev.synthetic_model_report_s31s import inspect_synthetic_actual_provider_receipts
from tests.test_jev_s31s_synthetic_model_report import _db, _put


def _row(case: str, choice: str, model: str = "jev-1.13.0", valid: bool = True):
    return {
        "case_id": case,
        "observed": choice if valid else None,
        "model": model if valid else None,
        "receipt_status": (
            "JOURNAL_CONSISTENCY_CHECK_PASSED" if valid
            else "ATTEMPT_RECORDED_NOT_VALIDATED"
        ),
    }


def test_one_duplicate_case_does_not_inflate_unique_case_accuracy(tmp_path):
    db = _db(tmp_path)
    # Six recorded provider attempts, just five authored cases.
    decisions = [
        ("s5-condition-contradiction", "REVIEW_REQUIRED"),
        ("s5-consistent", "PASS_THROUGH"),
        ("s5-insufficient-evidence", "ABSTAIN"),
        ("s5-risk-contradiction", "REVIEW_REQUIRED"),
        ("s5-unresolved-ambiguity", "REVIEW_REQUIRED"),  # deliberate error
        ("s5-condition-contradiction", "REVIEW_REQUIRED"),  # repeated
    ]
    for case, decision in decisions:
        _put(db, case=case, decision=decision)
    before = db.read_bytes()
    report = inspect_synthetic_actual_provider_receipts(db)
    assert db.read_bytes() == before
    paired = report["paired_baseline"]
    assert report["actual_valid_receipts"] == 6
    assert report["correct_against_synthetic_gold"] == 5
    assert paired["raw_actual_attempts"] == 6
    assert paired["unique_authored_cases"] == 5
    assert paired["pairable_unique_cases"] == 5
    assert paired["model_correct_paired"] == 4
    assert paired["naive_baseline_correct_paired"] == 1
    assert paired["paired_gold_label_difference"] == 3
    assert paired["repeated_cases"] == 1
    assert paired["full_case_coverage"] is True
    assert paired["status"] == "ALL_AUTHORED_SYNTHETIC_CASES_PAIRED"
    assert paired["actual_stock_comparison_available"] is False
    assert paired["jev_incremental_market_value_proven"] is False
    assert paired["naive_baseline_is_actual_scanner_algorithm"] is False
    assert (paired["external_calls"], paired["db_writes"]) == (0, 0)


def test_conflicting_responses_on_same_case_cannot_be_cherry_picked(tmp_path):
    db = _db(tmp_path)
    _put(db, case="s5-condition-contradiction", decision="REVIEW_REQUIRED")
    _put(db, case="s5-condition-contradiction", decision="ABSTAIN")
    pair = inspect_synthetic_actual_provider_receipts(db)["paired_baseline"]
    entry = next(x for x in pair["rows"] if x["case_id"] == "s5-condition-contradiction")
    assert entry["status"] == "INCONSISTENT_REPEATS"
    assert entry["model_decision"] is None
    assert entry["model_matches_gold"] is None
    assert pair["pairable_unique_cases"] == 0
    assert pair["status"] == "PARTIAL_NOT_COMPARABLE"
    assert pair["full_case_coverage"] is False


def test_mixed_model_versions_are_not_called_a_stable_repeat():
    receipts = [
        _row("s5-consistent", "PASS_THROUGH", "jev-1.13.0"),
        _row("s5-consistent", "PASS_THROUGH", "jev-1.14.0"),
    ]
    pair = compare_synthetic_cases(
        receipts, total_actual_attempts=2, malformed_rows=0, read_limit=50,
    )
    row = next(x for x in pair["rows"] if x["case_id"] == "s5-consistent")
    assert row["status"] == "MIXED_MODEL_IDENTITIES"
    assert row["repeat_stability"] == "NOT_ESTABLISHED"
    assert pair["status"] == "PARTIAL_NOT_COMPARABLE"


def test_absent_and_mock_only_report_no_actual_model_baseline(tmp_path):
    missing = tmp_path / "absent.sqlite3"
    assert inspect_synthetic_actual_provider_receipts(missing)["paired_baseline"][
        "status"
    ] == "NO_ACTUAL_MODEL_RECORDS"
    assert not missing.exists()
    db = _db(tmp_path)
    _put(db, origin="MOCK_TEST")
    result = inspect_synthetic_actual_provider_receipts(db)
    assert result["paired_baseline"]["raw_actual_attempts"] == 0
    assert result["paired_baseline"]["model_correct_paired"] == 0
    assert result["mock_rows_excluded"] == 1


def test_missing_or_invalid_receipts_never_create_full_coverage(tmp_path):
    db = _db(tmp_path)
    for case in ["s5-consistent", "s5-condition-contradiction",
                 "s5-risk-contradiction", "s5-insufficient-evidence",
                 "s5-unresolved-ambiguity"]:
        _put(db, case=case)
    _put(db, case="s5-consistent", hash_valid=False)
    compare = inspect_synthetic_actual_provider_receipts(db)["paired_baseline"]
    assert compare["pairable_unique_cases"] == 5
    assert compare["full_case_coverage"] is False
    assert compare["status"] == "PARTIAL_NOT_COMPARABLE"


def test_failed_attempt_on_case_is_not_silently_dropped(tmp_path):
    db = _db(tmp_path)
    _put(db, case="s5-consistent")
    _put(db, case="s5-consistent", state="ERROR")
    benchmark = inspect_synthetic_actual_provider_receipts(db)["paired_baseline"]
    case = next(x for x in benchmark["rows"] if x["case_id"] == "s5-consistent")
    assert case["status"] == "INCOMPLETE_ATTEMPTS"
    assert case["model_decision"] is None


def test_truncated_journal_with_over_limit_does_not_publish_five_case_score():
    rows = [_row("s5-consistent", "PASS_THROUGH")]
    result = compare_synthetic_cases(
        rows, total_actual_attempts=51, malformed_rows=50, read_limit=50,
    )
    assert result["status"] == "TRUNCATED_NOT_COMPARABLE"
    assert result["full_case_coverage"] is False
    assert result["actual_stock_comparison_available"] is False


def test_gold_does_not_create_evidence_of_real_scanner_improvement():
    rows = [
        _row("s5-condition-contradiction", "REVIEW_REQUIRED"),
        _row("s5-risk-contradiction", "REVIEW_REQUIRED"),
        _row("s5-insufficient-evidence", "ABSTAIN"),
        _row("s5-unresolved-ambiguity", "ABSTAIN"),
        _row("s5-consistent", "PASS_THROUGH"),
    ]
    result = compare_synthetic_cases(
        rows, total_actual_attempts=5, malformed_rows=0, read_limit=50,
    )
    assert result["model_correct_paired"] == 5
    assert result["paired_gold_label_difference"] == 4
    assert result["naive_baseline_is_actual_scanner_algorithm"] is False
    assert result["jev_incremental_market_value_proven"] is False
    assert result["real_market_cases"] == 0
