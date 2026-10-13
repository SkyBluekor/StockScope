"""Synthetic-only S10 denominator tests; no real market/provider/DB access."""
from __future__ import annotations

from copy import deepcopy

import pytest

from app.jev import local_shadow_cohort_s10 as cohort
from app.jev.decision_reviewer_offline import DecisionReviewContractError
from tools.data import jev_s7_shadow as cli


def _pairs():
    cap = {"id": "synthetic-canonical-capture", "status": "COMPLETE"}
    specs = [
        ("ENTRY_CANDIDATE", "trend_following", cohort.PROVISIONAL,
         "POST_RANK_NEGATIVE_STRATEGY_EXPECTANCY"),
        ("ENTRY_CANDIDATE", "trend_following", cohort.NO_ADVERSE,
         "NO_STRICT_NEGATIVE_EXPECTANCY_CONTRAST"),
        ("ENTRY_CANDIDATE", "pullback", cohort.ABSTAIN,
         "HISTORICAL_EVIDENCE_NOT_FROZEN"),
        ("ENTRY_CANDIDATE", "pullback", cohort.BLOCKED,
         "FULLY_VALIDATED_FROZEN_CANDIDATE_REQUIRED"),
        ("WAIT", "pullback", cohort.REFERENCE, "NOT_ENTRY_CANDIDATE"),
    ]
    pairs = []
    for idx, (action, strategy, status, reason) in enumerate(specs):
        sample = {
            "capture_run_id": cap["id"], "sample_index": idx,
            "snapshot_hash": f"synthetic-hash-{idx}",
            "action": action, "strategy": strategy,
            "name": "SECRET-MARKET-LABEL",
            "snapshot": {"secret_market_input": "SECRET-PRICE"},
            "_fake_status": status, "_fake_reason": reason,
        }
        pairs.append((dict(cap), sample))
    return pairs


def _mock_review(cap, sample):
    status = sample["_fake_status"]
    return {
        "identity": {
            "capture_id": cap["id"],
            "sample_index": sample["sample_index"],
            "snapshot_hash": sample["snapshot_hash"],
        },
        "status": status,
        "reason_code": sample["_fake_reason"],
        "shadow_only_decision": (
            "REVIEW_REQUIRED" if status == cohort.PROVISIONAL else None
        ),
        "shadow_adoption_eligible": False,
        "prospective_evaluation_eligible": False,
        "provider_status": "PROVIDER_HOLD",
        "actual_provider_calls": 0,
        "db_writes": 0,
    }


def test_all_entry_denominators_reference_and_strategies_are_preserved(monkeypatch):
    monkeypatch.setattr(cohort, "review_candidate", _mock_review)
    pairs = _pairs()
    immutable = deepcopy(pairs)
    report = cohort.build_cohort_report(
        pairs, requested_capture_id="synthetic-canonical-capture", limit=60,
    )
    counts = report["counts"]
    assert counts == {
        "entry_candidates": 4,
        "reviewable": 2,
        "provisional_recheck": 1,
        "no_adverse_signal": 1,
        "abstained": 1,
        "integrity_blocked": 1,
        "reference_only": 1,
    }
    assert report["scope"]["completeness"] == "COMPLETE_WITHIN_CAPTURE"
    assert report["scope"]["full_capture_claim_allowed"] is True
    assert report["rates_pct"] == {
        "reviewable_of_entries": 50.0,
        "provisional_of_entries": 25.0,
        "provisional_of_reviewable": 50.0,
        "abstained_of_entries": 25.0,
        "blocked_of_entries": 25.0,
    }
    assert report["strategy_counts"]["trend_following"]["provisional_recheck"] == 1
    assert report["strategy_counts"]["pullback"]["integrity_blocked"] == 1
    assert report["reason_counts"]["HISTORICAL_EVIDENCE_NOT_FROZEN"] == 1
    assert report["outcome_comparison"] is None
    assert report["incremental_investment_value"] is None
    assert report["adoption_eligible"] is False
    assert report["provider_status"] == "PROVIDER_HOLD"
    assert report["actual_provider_calls"] == report["db_writes"] == 0
    assert "SECRET-PRICE" not in str(report)
    assert "SECRET-MARKET-LABEL" not in str(report)
    assert pairs == immutable


def test_reaching_limit_never_claims_full_denominator(monkeypatch):
    monkeypatch.setattr(cohort, "review_candidate", _mock_review)
    pairs = _pairs()
    report = cohort.build_cohort_report(
        pairs, requested_capture_id="synthetic-canonical-capture", limit=5,
    )
    assert report["scope"]["completeness"] == "UNKNOWN_LIMIT_REACHED"
    assert report["scope"]["full_capture_claim_allowed"] is False
    assert report["counts"]["entry_candidates"] == 4
    assert report["evaluation_status"] == "NOT_EVALUATED_NO_APPROVED_OUTCOME_BINDING"


def test_no_candidates_has_no_fake_percentages(monkeypatch):
    monkeypatch.setattr(cohort, "review_candidate", _mock_review)
    report = cohort.build_cohort_report([], requested_capture_id="none", limit=60)
    assert report["counts"]["entry_candidates"] == 0
    assert all(x is None for x in report["rates_pct"].values())
    assert report["outcome_comparison"] is None


@pytest.mark.parametrize("corruption,error", [
    ("duplicate", "LOCAL_COHORT_DUPLICATE_SAMPLE"),
    ("mixed", "LOCAL_COHORT_MIXED_CAPTURE"),
    ("identity", "LOCAL_COHORT_CAPTURE_IDENTITY_INVALID"),
    ("oversize", "LOCAL_COHORT_RETURN_LIMIT_VIOLATED"),
])
def test_corrupt_cohort_fails_closed(monkeypatch, corruption, error):
    monkeypatch.setattr(cohort, "review_candidate", _mock_review)
    rows = _pairs()
    if corruption == "duplicate":
        rows[1][1]["sample_index"] = rows[0][1]["sample_index"]
    elif corruption == "mixed":
        rows[1][0]["id"] = "other-capture"
        rows[1][1]["capture_run_id"] = "other-capture"
    elif corruption == "identity":
        rows[1][1]["capture_run_id"] = "unrelated"
    elif corruption == "oversize":
        rows.append(rows[0])
    with pytest.raises(DecisionReviewContractError, match=error):
        cohort.build_cohort_report(
            rows, requested_capture_id="synthetic-canonical-capture",
            limit=5,
        )


@pytest.mark.parametrize("corruption,error", [
    ("identity", "LOCAL_COHORT_REVIEW_IDENTITY_MISMATCH"),
    ("scope", "LOCAL_COHORT_REVIEW_SCOPE_MISMATCH"),
    ("decision", "LOCAL_COHORT_UNSUPPORTED_DECISION"),
    ("provider", "LOCAL_COHORT_UNAUTHORIZED_SIDE_EFFECT"),
    ("adoption", "LOCAL_COHORT_UNAUTHORIZED_SIDE_EFFECT"),
    ("invalid_status", "LOCAL_COHORT_REVIEW_STATUS_INVALID"),
])
def test_untrusted_review_cannot_inflate_measured_results(
    monkeypatch, corruption, error,
):
    original = _mock_review
    def tampered(cap, sample):
        row = original(cap, sample)
        if sample["sample_index"] == 0:
            if corruption == "identity":
                row["identity"]["snapshot_hash"] = "other"
            elif corruption == "scope":
                row["status"] = cohort.REFERENCE
            elif corruption == "decision":
                row["shadow_only_decision"] = "PASS_THROUGH"
            elif corruption == "provider":
                row["actual_provider_calls"] = 1
            elif corruption == "adoption":
                row["shadow_adoption_eligible"] = True
            elif corruption == "invalid_status":
                row["status"] = "CERTAIN_BUY"
        return row
    monkeypatch.setattr(cohort, "review_candidate", tampered)
    with pytest.raises(DecisionReviewContractError, match=error):
        cohort.build_cohort_report(
            _pairs(), requested_capture_id="synthetic-canonical-capture",
            limit=60,
        )


def test_reason_and_strategy_output_sanitized(monkeypatch):
    rows = _pairs()
    rows[0][1]["strategy"] = "SECRET-CUSTOM-TICKER"
    rows[0][1]["_fake_reason"] = "SECRET-MARKET-SIGNAL"
    monkeypatch.setattr(cohort, "review_candidate", _mock_review)
    report = cohort.build_cohort_report(
        rows, requested_capture_id="synthetic-canonical-capture",
        limit=60,
    )
    assert "UNKNOWN_STRATEGY" in report["strategy_counts"]
    assert "UNSPECIFIED_REASON" in report["reason_counts"]
    assert "SECRET-CUSTOM-TICKER" not in str(report)
    assert "SECRET-MARKET-SIGNAL" not in str(report)


def test_readonly_entrypoint_and_cli_never_create_db(monkeypatch, tmp_path, capsys):
    rows = _pairs()
    monkeypatch.setattr(cohort, "review_candidate", _mock_review)
    path = tmp_path / "must-not-create.db"
    calls = []
    def loader(db, **kwargs):
        calls.append((db, kwargs))
        return rows
    monkeypatch.setattr(cohort, "load_frozen_candidates", loader)
    report = cohort.measure_capture(
        path, capture_id="synthetic-canonical-capture", limit=60,
    )
    assert calls == [(path, {"capture_id":"synthetic-canonical-capture","limit":60})]
    assert report["counts"]["entry_candidates"] == 4
    assert not path.exists()
    monkeypatch.setattr(cli, "measure_local_cohort", lambda *args, **kw: report)
    args = cli.build_parser().parse_args([
        "local-cohort", "--capture-id", "synthetic-canonical-capture",
    ])
    assert cli.execute(args)["counts"]["reviewable"] == 2
    cli.display(report)
    output = capsys.readouterr().out
    assert "진입 후보 4건" in output
    assert "재검토 1건" in output
    assert "Runtime DB 쓰기 0건" in output
    args.save_preflight = True
    with pytest.raises(DecisionReviewContractError, match="S7_4_DIAGNOSTIC_READ_ONLY"):
        cli.execute(args)
    with pytest.raises(DecisionReviewContractError, match="LOCAL_COHORT_CAPTURE_ID_REQUIRED"):
        cohort.measure_capture(path, capture_id=None)
    with pytest.raises(DecisionReviewContractError, match="LOCAL_COHORT_LIMIT_INVALID"):
        cohort.measure_capture(path, capture_id="synthetic-canonical-capture",limit=0)


def test_non_dict_and_unhashable_review_outputs_fail_closed(monkeypatch):
    rows = _pairs()
    monkeypatch.setattr(cohort, "review_candidate", lambda c, s: [])
    with pytest.raises(DecisionReviewContractError, match="LOCAL_COHORT_REVIEW_STATUS_INVALID"):
        cohort.build_cohort_report(
            rows, requested_capture_id="synthetic-canonical-capture", limit=60,
        )

    def unhashable(cap, sample):
        row = _mock_review(cap, sample)
        row["status"] = ["LOCAL_SHADOW_REVIEW_ONLY"]
        return row
    monkeypatch.setattr(cohort, "review_candidate", unhashable)
    with pytest.raises(DecisionReviewContractError, match="LOCAL_COHORT_REVIEW_STATUS_INVALID"):
        cohort.build_cohort_report(
            rows, requested_capture_id="synthetic-canonical-capture", limit=60,
        )


def test_actual_s9_observation_function_binds_to_s10_denominator(monkeypatch):
    """Only the full integrity source is stubbed; S9 real rules execute."""
    from app.jev import local_history_review
    from app.prospective.models import digest_json

    def frozen_identity(capture, sample):
        return {
            "identity": {
                "capture_id": capture["id"],
                "sample_index": sample["sample_index"],
                "snapshot_hash": sample["snapshot_hash"],
            },
            "category": "LOCAL_VALIDATED",
        }
    monkeypatch.setattr(
        local_history_review, "audit_frozen_evidence", frozen_identity,
    )
    capture = {"id":"SYNTHETIC-ONLY", "status":"COMPLETE"}
    rows = []
    for i, (status, expectancy) in enumerate((("WEAK",-1.0),("GOOD",1.0))):
        snapshot = {
            "action":"ENTRY_CANDIDATE",
            "verification_level":"CURRENT_AND_3Y_EVIDENCE",
            "historical_evidence": {
                "verified":True, "strategy":"trend_following",
                "validation_years":3,
                "period":{"start":"2023-10-08","end":"2026-10-08"},
                "sample_count":12, "sample_sufficient":True,
                "minimum_sample":10, "status":status,
                "expectancy_pct":expectancy,
            },
        }
        sample = {
            "capture_run_id":capture["id"],
            "sample_index":i,
            "snapshot_hash":digest_json(snapshot),
            "snapshot":snapshot,
            "action":"ENTRY_CANDIDATE",
            "signal_date":"2026-10-08",
            "strategy":"trend_following",
        }
        rows.append((dict(capture),sample))
    report = cohort.build_cohort_report(
        rows, requested_capture_id="SYNTHETIC-ONLY", limit=60,
    )
    assert report["counts"]["entry_candidates"] == 2
    assert report["counts"]["reviewable"] == 2
    assert report["counts"]["provisional_recheck"] == 1
    assert report["counts"]["no_adverse_signal"] == 1
    assert report["rates_pct"]["provisional_of_reviewable"] == 50.0
    assert report["outcome_comparison"] is None
    assert report["actual_provider_calls"] == report["db_writes"] == 0
