"""S11 proof-driven descriptive outcome link, synthetic data only."""
from __future__ import annotations

from copy import deepcopy
import sqlite3

import pytest

import app.jev.local_shadow_cohort_s10 as s10
import app.jev.local_outcome_link_s11 as s11
from app.jev.decision_reviewer_offline import DecisionReviewContractError
from tools.data import jev_s7_shadow as cli


CAPTURE = "SYNTHETIC-CAP"
RUN = "SYNTHETIC-EVAL"
COMPLETED_CAPTURE = "2026-09-02T09:00:00+00:00"
COMPLETED_RUN = "2026-10-08T10:00:00+00:00"


def _source():
    capture = {
        "id": CAPTURE, "status": "COMPLETE",
        "completed_at": COMPLETED_CAPTURE,
    }
    pairs = []
    for i, status in enumerate((s10.PROVISIONAL, s10.NO_ADVERSE)):
        sample = {
            "capture_run_id": CAPTURE, "sample_index": i,
            "action": "ENTRY_CANDIDATE", "strategy": "trend_following",
            "signal_date": "2026-09-01", "market": "KOSPI",
            "ticker": "FAKE001", "snapshot_hash": f"SYNTHETIC-hash-{i}",
            "_fake_status": status,
        }
        pairs.append((dict(capture), sample))
    run = {
        "id": RUN, "status": "COMPLETED", "protocol_id": "synthetic-protocol",
        "completed_at": COMPLETED_RUN, "evaluation_version": "SYNTHETIC",
    }
    units = []
    for i, value in enumerate((-7.0, 4.0)):
        units.append({
            "evaluation_run_id": RUN, "capture_run_id": CAPTURE,
            "sample_index": i, "signal_date": "2026-09-01",
            "market": "KOSPI", "ticker": "FAKE001",
            "strategy": "trend_following",
            "split": "HOLDOUT" if i == 0 else "DEVELOPMENT",
            "maturity_status": "MATURE", "execution_status": "CLOSED",
            "net_return_pct": value, "exit_date": "2026-09-15",
            "evaluated_through": "2026-10-01",
            "computed_at": "2026-10-05T10:00:00+00:00",
        })
    return pairs, run, units


def _fake_review(capture, sample):
    status = sample["_fake_status"]
    return {
        "identity": {
            "capture_id": capture["id"],
            "sample_index": sample["sample_index"],
            "snapshot_hash": sample["snapshot_hash"],
        },
        "status": status,
        "reason_code": (
            "POST_RANK_NEGATIVE_STRATEGY_EXPECTANCY"
            if status == s10.PROVISIONAL
            else "NO_STRICT_NEGATIVE_EXPECTANCY_CONTRAST"
        ),
        "shadow_only_decision": "REVIEW_REQUIRED" if status == s10.PROVISIONAL else None,
        "shadow_adoption_eligible": False,
        "prospective_evaluation_eligible": False,
        "provider_status": "PROVIDER_HOLD",
        "actual_provider_calls": 0,
        "db_writes": 0,
    }


@pytest.fixture(autouse=True)
def _fake_reviews(monkeypatch):
    monkeypatch.setattr(s10, "review_candidate", _fake_review)
    monkeypatch.setattr(s11, "review_candidate", _fake_review)


def _run(pairs=None, run=None, units=None, limit=60):
    p, r, u = _source()
    return s11.build_outcome_link_report(
        p if pairs is None else pairs,
        requested_capture_id=CAPTURE, limit=limit,
        run_id=RUN, run=r if run is None else run, units=u if units is None else units,
    )


def test_exact_frozen_capture_holdout_and_development_outcomes_are_only_descriptive():
    original = deepcopy(_source())
    report = _run()
    assert report["status"] == "S11_LOCAL_OUTCOME_LINK_DESCRIPTIVE_ONLY"
    assert report["entry_candidates_examined"] == 2
    assert report["cohort_counts"]["entry_candidates"] == 2
    assert report["cohort_counts"]["reviewable"] == 2
    assert report["exclusion_reasons"] == {}
    holdout = report["split_descriptive"]["HOLDOUT"]
    development = report["split_descriptive"]["DEVELOPMENT"]
    assert holdout["closed_comparable"] == 1
    assert holdout["flagged_closed"] == 1
    assert holdout["flagged_losses"] == 1
    assert holdout["mean_flagged_net_return_pct"] == -7
    assert holdout["unflagged_closed"] == 0
    assert holdout["mean_unflagged_net_return_pct"] is None
    assert development["closed_comparable"] == 1
    assert development["unflagged_closed"] == 1
    assert development["mean_unflagged_net_return_pct"] == 4
    assert report["causal_uplift_pct"] is None
    assert report["avoided_loss_claim"] is None
    assert report["incremental_investment_value"] is None
    assert report["performance_conclusion_allowed"] is False
    assert report["source_release_time_verified"] is False
    assert report["adoption_eligible"] is False
    assert report["actual_provider_calls"] == report["db_writes"] == 0
    assert _source() == original
    assert "FAKE001" not in str(report)


@pytest.mark.parametrize("field,new,reason", [
    ("market", "KOSDAQ", "SOURCE_IDENTITY_MISMATCH"),
    ("ticker", "FAKE999", "SOURCE_IDENTITY_MISMATCH"),
    ("strategy", "pullback", "SOURCE_IDENTITY_MISMATCH"),
    ("signal_date", "2026-09-02", "SOURCE_IDENTITY_MISMATCH"),
    ("computed_at", "2026-09-01T01:00:00+00:00", "OBSERVATION_TIME_UNVERIFIED"),
    ("computed_at", "2026-10-09T01:00:00+00:00", "OBSERVATION_TIME_UNVERIFIED"),
    ("split", ["HOLDOUT"], "SPLIT_NOT_VERIFIED"),
    ("split", "PURGED", "PURGED_OR_EXCLUDED"),
    ("split", "EXCLUDED", "PURGED_OR_EXCLUDED"),
    ("maturity_status", "IMMATURE", "NOT_MATURE"),
    ("execution_status", "CENSORED", "NOT_CLOSED"),
    ("execution_status", "NOT_EVALUATED", "NOT_CLOSED"),
    ("exit_date", "2026-08-31", "EXECUTION_TIME_UNVERIFIED"),
    ("exit_date", "2026-10-10", "EXECUTION_TIME_UNVERIFIED"),
    ("net_return_pct", None, "NET_RETURN_UNVERIFIED"),
    ("net_return_pct", "4.2", "NET_RETURN_UNVERIFIED"),
    ("net_return_pct", True, "NET_RETURN_UNVERIFIED"),
    ("net_return_pct", float("nan"), "NET_RETURN_UNVERIFIED"),
])
def test_invalid_or_future_evidence_does_not_enter_closed_denominator(field,new,reason):
    pairs, run, units = _source()
    units[0][field] = new
    result = _run(pairs,run,units)
    assert result["exclusion_reasons"] == {reason: 1}
    assert result["split_descriptive"]["HOLDOUT"]["closed_comparable"] == 0
    assert result["split_descriptive"]["HOLDOUT"]["mean_flagged_net_return_pct"] is None
    assert result["split_descriptive"]["DEVELOPMENT"]["closed_comparable"] == 1


@pytest.mark.parametrize("status", ["DRAFT", "FAILED", "RUNNING", "CANCELLED"])
def test_only_completed_runs_are_eligible(status):
    p,r,u=_source()
    r["status"] = status
    with pytest.raises(DecisionReviewContractError, match="S11_EVALUATION_RUN_NOT_COMPLETE"):
        _run(p,r,u)


def test_completed_run_requires_verified_timestamp():
    p,r,u=_source()
    r["completed_at"] = "not-time"
    with pytest.raises(DecisionReviewContractError, match="S11_EVALUATION_COMPLETION_TIME_UNVERIFIED"):
        _run(p,r,u)


def test_duplicate_units_and_foreign_capture_fail_closed():
    p,r,u=_source()
    with pytest.raises(DecisionReviewContractError, match="S11_UNIT_INDEX_DUPLICATED_OR_INVALID"):
        _run(p,r,u+[dict(u[0])])
    other = dict(u[0])
    other["sample_index"] = 3
    other["capture_run_id"] = "OTHER"
    with pytest.raises(DecisionReviewContractError, match="S11_MIXED_CAPTURE_UNITS"):
        _run(p,r,u+[other])


def test_truncated_capture_and_missing_outcome_not_promoted_to_success():
    p,r,u=_source()
    with pytest.raises(DecisionReviewContractError, match="S11_FULL_CAPTURE_DENOMINATOR_REQUIRED"):
        _run(p,r,u,limit=2)
    result = _run(p,r,u[:1])
    assert result["exclusion_reasons"] == {"EVALUATION_UNIT_MISSING": 1}
    assert result["split_descriptive"]["DEVELOPMENT"]["closed_comparable"] == 0


def test_unbound_evaluation_row_is_reported_not_hidden():
    p,r,u=_source()
    extra=dict(u[0])
    extra["sample_index"] = 99
    result=_run(p,r,u+[extra])
    assert result["unmatched_outcome_units"] == 1
    assert result["exclusion_reasons"]["EVALUATION_UNIT_OUTSIDE_ENTRY_COHORT"] == 1


def test_abstain_observation_can_never_count_as_closed_reviewed_candidate():
    p,r,u=_source()
    p[0][1]["_fake_status"] = s10.ABSTAIN
    result=_run(p,r,u)
    assert result["exclusion_reasons"] == {"REVIEW_NOT_COMPARABLE": 1}
    assert result["split_descriptive"]["HOLDOUT"]["closed_comparable"] == 0


def test_sqlite_readonly_reader_and_cli_do_not_mutate_runtime(monkeypatch, tmp_path, capsys):
    p,r,u=_source()
    db=tmp_path/"synthetic-eval.db"
    conn=sqlite3.connect(db)
    conn.executescript("""
        CREATE TABLE prospective_evaluation_run(
            id TEXT PRIMARY KEY,status TEXT,protocol_id TEXT,
            evaluation_version TEXT,completed_at TEXT);
        CREATE TABLE prospective_evaluation_unit(
            evaluation_run_id TEXT,capture_run_id TEXT,sample_index INTEGER,
            signal_date TEXT,market TEXT,ticker TEXT,strategy TEXT,
            split TEXT,maturity_status TEXT,execution_status TEXT,
            net_return_pct REAL,exit_date TEXT,evaluated_through TEXT,computed_at TEXT);
    """)
    conn.execute("INSERT INTO prospective_evaluation_run VALUES(?,?,?,?,?)",
                 (r["id"],r["status"],r["protocol_id"],r["evaluation_version"],r["completed_at"]))
    for unit in u:
        conn.execute("INSERT INTO prospective_evaluation_unit VALUES(" + ",".join("?"*14) + ")",
                     tuple(unit[key] for key in (
                         "evaluation_run_id","capture_run_id","sample_index","signal_date",
                         "market","ticker","strategy","split","maturity_status",
                         "execution_status","net_return_pct","exit_date",
                         "evaluated_through","computed_at")))
    conn.commit()
    conn.close()
    initial=db.read_bytes()
    loaded=s11.load_evaluation_readonly(db,run_id=RUN,capture_id=CAPTURE)
    assert len(loaded[1]) == 2
    monkeypatch.setattr(s11,"load_frozen_candidates",lambda *a,**kw:p)
    result=s11.evaluate_capture_readonly(db,capture_id=CAPTURE,evaluation_run_id=RUN,limit=60)
    assert result["split_descriptive"]["HOLDOUT"]["flagged_losses"] == 1
    assert db.read_bytes() == initial

    monkeypatch.setattr(cli,"evaluate_local_outcomes",lambda *a,**kw:result)
    args=cli.build_parser().parse_args([
        "local-outcomes","--capture-id",CAPTURE,"--evaluation-run-id",RUN
    ])
    assert cli.execute(args)["entry_candidates_examined"] == 2
    cli.display(result)
    displayed=capsys.readouterr().out
    assert "진입 후보 2건" in displayed
    assert "Runtime DB 쓰기 0건" in displayed
    args.save_preflight=True
    with pytest.raises(DecisionReviewContractError,match="S7_4_DIAGNOSTIC_READ_ONLY"):
        cli.execute(args)
    args.save_preflight=False
    args.sample_index=0
    with pytest.raises(DecisionReviewContractError,match="S11_SAMPLE_INDEX_UNSUPPORTED"):
        cli.execute(args)
    assert db.read_bytes() == initial


def test_missing_input_db_is_rejected_without_creating_database(tmp_path):
    path=tmp_path/"missing.db"
    with pytest.raises(DecisionReviewContractError,match="S11_SOURCE_DB_NOT_FOUND"):
        s11.load_evaluation_readonly(path,run_id=RUN,capture_id=CAPTURE)
    assert not path.exists()
