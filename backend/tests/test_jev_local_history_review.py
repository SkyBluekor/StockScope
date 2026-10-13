"""S9 local JEV history counterevidence: synthetic-only, fail-closed tests."""
from __future__ import annotations

from copy import deepcopy
from datetime import date
from math import nan

import pytest

from app.jev import local_history_review as review
from app.jev.decision_reviewer_offline import DecisionReviewContractError
from app.prospective.models import digest_json
from tools.data import jev_s7_shadow as cli


def _frozen(*, expectancy=-2.0, status="WEAK", count=12):
    history = {
        "strategy": "trend_following",
        "verified": True,
        "validation_years": 3,
        "period": {"start": "2023-10-08", "end": "2026-10-08"},
        "sample_count": count,
        "sample_sufficient": count >= 10,
        "minimum_sample": 10,
        "expectancy_pct": expectancy,
        "status": status,
    }
    snapshot = {
        "action": "ENTRY_CANDIDATE",
        "verification_level": "CURRENT_AND_3Y_EVIDENCE",
        "historical_evidence": history,
    }
    capture = {"id": "synthetic-capture", "status": "COMPLETE"}
    sample = {
        "capture_run_id": capture["id"], "sample_index": 2,
        "action": "ENTRY_CANDIDATE", "strategy": "trend_following",
        "signal_date": "2026-10-08",
        "snapshot": snapshot, "snapshot_hash": digest_json(snapshot),
    }
    return capture, sample


@pytest.fixture(autouse=True)
def _stub_full_integrity_gate(monkeypatch):
    # Real gate is already exercised in local_evidence_audit's own tests.
    # Here only the contract binding after that verified gate is exercised.
    monkeypatch.setattr(
        review, "audit_frozen_evidence",
        lambda c, s: {
            "identity": {
                "capture_id": c.get("id"),
                "sample_index": s.get("sample_index"),
                "snapshot_hash": s.get("snapshot_hash"),
            },
            "category": "LOCAL_VALIDATED",
        },
    )


def test_full_verified_negative_post_rank_history_creates_observation_only_opinion():
    cap, sample = _frozen()
    original = deepcopy((cap, sample))
    result = review.review_candidate(cap, sample)
    assert result["status"] == "LOCAL_SHADOW_REVIEW_ONLY"
    assert result["shadow_only_decision"] == "REVIEW_REQUIRED"
    assert result["reason_code"] == "POST_RANK_NEGATIVE_STRATEGY_EXPECTANCY"
    assert result["evidence_basis"]["independent_of"] == "PRODUCTION_SELECTION_AND_RISK_ONLY"
    assert result["evidence_basis"]["sample_count"] == 12
    assert result["evidence_basis"]["expectancy_pct"] == -2.0
    assert result["shadow_adoption_eligible"] is False
    assert result["prospective_evaluation_eligible"] is False
    assert result["provider_status"] == "PROVIDER_HOLD"
    assert result["actual_provider_calls"] == result["db_writes"] == 0
    assert review.review_candidate(cap, sample)["review_identity"] == result["review_identity"]
    assert (cap, sample) == original


@pytest.mark.parametrize("status,expectancy", [
    ("GOOD", 2.0), ("FAIR", 0.5), ("WEAK", 0.0), ("WEAK", 1.0),
])
def test_nonnegative_or_nonadverse_historical_status_is_not_a_pass_verdict(status,expectancy):
    cap, sample = _frozen(status=status,expectancy=expectancy)
    result = review.review_candidate(cap, sample)
    assert result["status"] == "NO_ADVERSE_HISTORY_SIGNAL"
    assert result["shadow_only_decision"] is None
    assert result["prospective_evaluation_eligible"] is False


@pytest.mark.parametrize("change,reason", [
    ({"verified": False}, "HISTORICAL_EVIDENCE_IDENTITY_UNVERIFIED"),
    ({"strategy": "different"}, "HISTORICAL_EVIDENCE_IDENTITY_UNVERIFIED"),
    ({"period": {"start":"2023-10-08","end":"2026-10-09"}}, "HISTORICAL_PERIOD_NOT_ASOF_SIGNAL"),
    ({"period": {"start":"2024-10-08","end":"2026-10-08"}}, "HISTORICAL_PERIOD_NOT_ASOF_SIGNAL"),
    ({"period": {"start":"2023-10-08","end":"bad-date"}}, "HISTORICAL_PERIOD_NOT_ASOF_SIGNAL"),
    ({"validation_years": 2}, "HISTORICAL_PERIOD_UNVERIFIED"),
    ({"sample_count": 2, "sample_sufficient":False}, "HISTORICAL_SAMPLE_NOT_SUFFICIENT"),
    ({"sample_count": 12, "sample_sufficient":False}, "HISTORICAL_SAMPLE_NOT_SUFFICIENT"),
    ({"sample_count": 12, "minimum_sample": 3}, "HISTORICAL_SAMPLE_NOT_SUFFICIENT"),
    ({"expectancy_pct": nan}, "HISTORICAL_METRICS_NOT_VERIFIED"),
    ({"expectancy_pct": "-3.2"}, "HISTORICAL_METRICS_NOT_VERIFIED"),
    ({"status": "DATA_UNAVAILABLE"}, "HISTORICAL_METRICS_NOT_VERIFIED"),
])
def test_untrusted_or_insufficient_history_abstains_without_review(change, reason):
    cap, sample = _frozen()
    sample["snapshot"]["historical_evidence"].update(change)
    sample["snapshot_hash"] = digest_json(sample["snapshot"])
    result = review.review_candidate(cap, sample)
    assert result["status"] == "ABSTAIN"
    assert result["reason_code"] == reason
    assert result["shadow_only_decision"] is None
    assert result["prospective_evaluation_eligible"] is False
    assert result["actual_provider_calls"] == 0


def test_missing_history_and_verification_flag_abstain():
    cap, sample = _frozen()
    del sample["snapshot"]["historical_evidence"]
    assert review.review_candidate(cap, sample)["reason_code"] == "HISTORICAL_EVIDENCE_NOT_FROZEN"
    cap, sample = _frozen()
    sample["snapshot"]["verification_level"] = "CURRENT_ONLY"
    assert review.review_candidate(cap, sample)["reason_code"] == "HISTORY_VERIFICATION_LEVEL_UNCONFIRMED"


def test_failed_integrity_reference_and_legacy_do_not_emit_shadows(monkeypatch):
    cap, sample = _frozen()
    for category, expected in [
        ("INVALID", "BLOCKED_BASELINE_INTEGRITY"),
        ("LEGACY_LIMITED", "BLOCKED_BASELINE_INTEGRITY"),
        ("REFERENCE_ONLY", "REFERENCE_ONLY"),
    ]:
        monkeypatch.setattr(
            review, "audit_frozen_evidence",
            lambda c, s, cat=category: {"identity": {}, "category": cat},
        )
        result = review.review_candidate(cap, sample)
        assert result["status"] == expected
        assert result["shadow_only_decision"] is None
        assert result["actual_provider_calls"] == result["db_writes"] == 0


def test_readonly_capture_report_and_cli_contract(monkeypatch, tmp_path, capsys):
    cap, sample = _frozen()
    monkeypatch.setattr(
        review, "load_frozen_candidates",
        lambda *args, **kwargs: [(cap, sample)],
    )
    result = review.review_capture(tmp_path / "not-created.db", capture_id=cap["id"])
    assert result["status"] == "LOCAL_HISTORY_SHADOW_OBSERVATION_ONLY"
    assert result["provisional_review_count"] == 1
    assert result["prospective_evaluation_eligible"] is False
    assert result["actual_provider_calls"] == result["db_writes"] == 0
    assert not (tmp_path / "not-created.db").exists()
    with pytest.raises(DecisionReviewContractError, match="LOCAL_HISTORY_CAPTURE_ID_REQUIRED"):
        review.review_capture(tmp_path / "not-created.db", capture_id=None)
    with pytest.raises(DecisionReviewContractError, match="LOCAL_HISTORY_SAMPLE_NOT_FOUND"):
        review.review_capture(tmp_path / "not-created.db", capture_id=cap["id"],sample_index=7)
    with pytest.raises(DecisionReviewContractError, match="LOCAL_HISTORY_SAMPLE_INDEX_INVALID"):
        review.review_capture(tmp_path / "not-created.db", capture_id=cap["id"],sample_index=-1)

    monkeypatch.setattr(cli, "review_local_history", lambda *a, **kw: result)
    cli_args = cli.build_parser().parse_args([
        "local-history", "--capture-id", cap["id"], "--json",
    ])
    assert cli.execute(cli_args)["provisional_review_count"] == 1
    cli.display(result)
    shown = capsys.readouterr().out
    assert "과거 반대 근거 재검토 1건" in shown
    assert "Runtime DB 쓰기 0건" in shown
    cli_args.save_preflight = True
    with pytest.raises(DecisionReviewContractError, match="S7_4_DIAGNOSTIC_READ_ONLY"):
        cli.execute(cli_args)
