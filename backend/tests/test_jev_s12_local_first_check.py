"""S12 first local check: real SQLite read-only, synthetic rows only."""
from __future__ import annotations

import sqlite3

import pytest

from app.jev import local_first_check_s12 as first
from app.jev.decision_reviewer_offline import DecisionReviewContractError
from tools.data import jev_s7_shadow as cli


def _db(tmp_path):
    path = tmp_path / "synthetic-only.db"
    with sqlite3.connect(path) as conn:
        conn.executescript("""
        CREATE TABLE prospective_capture_run(id TEXT PRIMARY KEY,status TEXT);
        CREATE TABLE prospective_recommendation_sample(
            capture_run_id TEXT,sample_index INTEGER);
        CREATE TABLE prospective_evaluation_run(
            id TEXT PRIMARY KEY,status TEXT,completed_at TEXT);
        CREATE TABLE prospective_evaluation_unit(
            evaluation_run_id TEXT,capture_run_id TEXT,signal_date TEXT);
        """)
    return path


def _insert(path, captures=(), runs=(), units=(), samples=()):
    with sqlite3.connect(path) as conn:
        conn.executemany("INSERT INTO prospective_capture_run VALUES(?,?)", captures)
        conn.executemany(
            "INSERT INTO prospective_evaluation_run VALUES(?,?,?)", runs,
        )
        conn.executemany(
            "INSERT INTO prospective_evaluation_unit VALUES(?,?,?)", units,
        )
        conn.executemany(
            "INSERT INTO prospective_recommendation_sample VALUES(?,?)",
            samples,
        )


def _synthetic_observation(*, closed=1):
    def slice_result():
        return {
            "closed_comparable": closed,
            "flagged_closed": closed,
            "unflagged_closed": 0,
        }
    return {
        "cohort_counts": {
            "entry_candidates": 3,
            "reviewable": 2,
            "provisional_recheck": 1,
            "abstained": 1,
            "integrity_blocked": 0,
        },
        "split_descriptive": {
            "DEVELOPMENT": slice_result(),
            "HOLDOUT": {
                "closed_comparable": 0,
                "flagged_closed": 0,
                "unflagged_closed": 0,
            },
        },
        "exclusion_reasons": {"NOT_CLOSED": 1},
        "evaluation_status": "DESCRIPTIVE_ONLY_NOT_CAUSAL",
    }


def test_database_missing_or_schema_missing_never_creates_data(tmp_path):
    missing = tmp_path / "not-created.db"
    report = first.first_local_check(missing)
    assert report["status"] == "NO_LOCAL_SIMULATION_DB"
    assert report["db_writes"] == report["external_model_calls"] == 0
    assert not missing.exists()

    empty = tmp_path / "schema-absent.db"
    sqlite3.connect(empty).close()
    report = first.first_local_check(empty)
    assert report["status"] == "PROSPECTIVE_SCHEMA_NOT_READY"


def test_missing_captures_and_completed_evaluation_are_distinguished(tmp_path):
    path = _db(tmp_path)
    assert first.first_local_check(path)["status"] == "NO_COMPLETED_FROZEN_CAPTURE"
    _insert(path, captures=[("capture-a", "COMPLETE")])
    report = first.first_local_check(path)
    assert report["status"] == "NO_COMPLETED_PROSPECTIVE_EVALUATION"
    assert report["complete_capture_count"] == 1
    assert report["completed_evaluation_count"] == 0


def test_latest_evaluation_without_units_does_not_steal_older_evaluation(tmp_path):
    path = _db(tmp_path)
    _insert(path, captures=[("capture-a", "COMPLETE")],
            runs=[
                ("eval-old", "COMPLETED", "2026-10-05T00:00:00+00:00"),
                ("eval-latest", "COMPLETED", "2026-10-09T00:00:00+00:00"),
            ],
            units=[("eval-old", "capture-a", "2026-10-01")],
            samples=[("capture-a", 0)])
    report = first.first_local_check(path)
    assert report["status"] == "LATEST_EVALUATION_HAS_NO_UNITS"
    assert report["latest_evaluation_run_id"] == "eval-latest"


def test_picks_latest_signal_capture_even_in_multi_capture_run(monkeypatch, tmp_path, capsys):
    path = _db(tmp_path)
    _insert(path,
        captures=[
            ("capture-new", "COMPLETE"), ("capture-old", "COMPLETE"),
        ],
        runs=[("eval-one", "COMPLETED", "2026-10-10T00:00:00+00:00")],
        units=[
            ("eval-one", "capture-old", "2026-10-01"),
            ("eval-one", "capture-new", "2026-10-09"),
            ("eval-one", "capture-new", "2026-10-09"),
        ],
        samples=[
            ("capture-old", 0), ("capture-new", 0), ("capture-new", 1),
        ],
    )
    calls = []
    def fake_evaluation(db, **kwargs):
        calls.append((db, kwargs))
        return _synthetic_observation()
    monkeypatch.setattr(first, "evaluate_capture_readonly", fake_evaluation)
    before = path.read_bytes()
    report = first.first_local_check(path)
    assert path.read_bytes() == before
    assert report["status"] == "DESCRIPTIVE_OUTCOMES_AVAILABLE"
    assert report["captures_in_evaluation_run"] == 2
    assert report["selection_scope"] == "LATEST_SIGNAL_CAPTURE_IN_LATEST_COMPLETED_RUN"
    assert report["selected_capture_id"] == "capture-new"
    assert report["selected_evaluation_run_id"] == "eval-one"
    assert report["frozen_sample_count"] == 2
    assert report["evaluation_unit_count"] == 2
    assert calls == [(path,{
        "capture_id": "capture-new", "evaluation_run_id": "eval-one", "limit": 500,
    })]
    assert report["investment_improvement_verified"] is False
    assert report["performance_conclusion_allowed"] is False
    assert report["causal_uplift_pct"] is None
    assert report["incremental_investment_value"] is None
    assert report["provider_status"] == "PROVIDER_HOLD"
    assert report["external_model_calls"] == report["db_writes"] == 0

    cli.display(report)
    output = capsys.readouterr().out
    assert "로컬 검토 가능 2건" in output
    assert "Runtime DB 쓰기 0건" in output


def test_no_closed_outcomes_is_not_misreported_as_improvement(monkeypatch, tmp_path):
    path = _db(tmp_path)
    _insert(path,
        captures=[("capture", "COMPLETE")],
        runs=[("run", "COMPLETED", "2026-10-09T00:00:00+00:00")],
        units=[("run", "capture", "2026-10-05")],
        samples=[("capture", 0)])
    monkeypatch.setattr(
        first, "evaluate_capture_readonly",
        lambda *a, **kw: _synthetic_observation(closed=0),
    )
    report = first.first_local_check(path)
    assert report["status"] == "NO_COMPARABLE_CLOSED_OUTCOMES"
    assert report["performance_conclusion_allowed"] is False


def test_missing_or_too_many_samples_fail_without_reading_outcomes(monkeypatch, tmp_path):
    path = _db(tmp_path)
    _insert(path,
        captures=[("capture", "COMPLETE")],
        runs=[("run", "COMPLETED", "2026-10-09T00:00:00+00:00")],
        units=[("run", "capture", "2026-10-05")],
    )
    monkeypatch.setattr(
        first, "evaluate_capture_readonly",
        lambda *a, **kw: pytest.fail("must not run S11 on incomplete cohorts"),
    )
    assert first.first_local_check(path)["status"] == "EVALUATED_CAPTURE_HAS_NO_FROZEN_SAMPLES"
    _insert(path, samples=[("capture", i) for i in range(500)])
    report = first.first_local_check(path)
    assert report["status"] == "FROZEN_SAMPLE_COUNT_EXCEEDS_READ_LIMIT"
    assert report["safe_max_samples"] == 499


def test_unfinished_selected_capture_is_not_silently_swapped(tmp_path):
    path = _db(tmp_path)
    _insert(path,
        captures=[("old", "COMPLETE"), ("new", "PARTIAL")],
        runs=[("run", "COMPLETED", "2026-10-10T00:00:00+00:00")],
        units=[
            ("run", "old", "2026-10-01"), ("run", "new", "2026-10-09"),
        ],
        samples=[("old", 0), ("new", 0)])
    assert first.first_local_check(path)["status"] == "EVALUATION_CAPTURE_NOT_COMPLETE"


def test_s11_contract_failure_becomes_fail_closed_reason(monkeypatch, tmp_path):
    path = _db(tmp_path)
    _insert(path,
        captures=[("capture", "COMPLETE")],
        runs=[("run", "COMPLETED", "2026-10-10T00:00:00+00:00")],
        units=[("run", "capture", "2026-10-09")],
        samples=[("capture", 0)])
    def blocked(*a,**kw):
        raise DecisionReviewContractError("S11_FULL_CAPTURE_DENOMINATOR_REQUIRED")
    monkeypatch.setattr(first, "evaluate_capture_readonly", blocked)
    r = first.first_local_check(path)
    assert r["status"] == "LOCAL_EVIDENCE_NOT_COMPARABLE"
    assert r["reason_code"] == "S11_FULL_CAPTURE_DENOMINATOR_REQUIRED"
    assert r["db_writes"] == r["external_model_calls"] == 0


def test_cli_mode_is_nonmutating_and_disallows_ambiguous_args(monkeypatch, tmp_path):
    path = tmp_path / "never-created.db"
    monkeypatch.setattr(cli, "first_local_check", lambda db: first._status("NO_LOCAL_SIMULATION_DB"))
    args = cli.build_parser().parse_args(["local-first-check", "--simulation-db", str(path)])
    assert cli.execute(args)["status"] == "NO_LOCAL_SIMULATION_DB"
    assert not path.exists()
    args.capture_id = "user-selected"
    with pytest.raises(DecisionReviewContractError, match="S12_AUTO_DISCOVERY_ARGUMENT_CONFLICT"):
        cli.execute(args)
    args.capture_id = None
    args.save_preflight = True
    with pytest.raises(DecisionReviewContractError, match="S7_4_DIAGNOSTIC_READ_ONLY"):
        cli.execute(args)
