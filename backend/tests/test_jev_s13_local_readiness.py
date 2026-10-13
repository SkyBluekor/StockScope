"""S13 real SQLite read-only readiness; synthetic capture evidence, no providers."""
from __future__ import annotations

import sqlite3
from collections import Counter

import pytest

from app.jev import local_readiness_s13 as s13
from app.jev.decision_reviewer_offline import DecisionReviewContractError
from tools.data import jev_s7_shadow as cli


def _db(tmp_path):
    path = tmp_path / "s13-only.db"
    with sqlite3.connect(path) as conn:
        conn.executescript("""
            CREATE TABLE prospective_capture_run(
                id TEXT PRIMARY KEY, status TEXT, completed_at TEXT
            );
            CREATE TABLE prospective_recommendation_sample(
                capture_run_id TEXT, sample_index INTEGER, action TEXT
            );
        """)
    return path


def _policy(*, active=False):
    return {
        "q7_activation_eligible": False,
        "q7_precommitted": False,
        "selection_policy_source": (
            "ACTIVE_SELECTION_POLICY" if active else "LEGACY_CURRENT_10_FALLBACK"
        ),
        "active_policy_effective": active,
        "fallback_reason": None if active else "ACTIVE_REFERENCE_MISSING",
    }


def _rows(path, ids):
    with sqlite3.connect(path) as conn:
        for i, capture_id in enumerate(ids):
            conn.execute(
                "INSERT INTO prospective_capture_run VALUES(?,?,?)",
                (capture_id, "COMPLETE", f"2026-10-{i+1:02d}T16:00:00+09:00"),
            )


def _sample(capture_id, index, category, *codes):
    return (
        {"id": capture_id, "status": "COMPLETE"},
        {
            "capture_run_id": capture_id,
            "sample_index": index,
            "action": "REFERENCE_ONLY" if category == "REFERENCE_ONLY"
                      else "ENTRY_CANDIDATE",
            "_category": category,
            "_codes": list(codes),
        },
    )


def _fake_integrity(monkeypatch, pairs):
    monkeypatch.setattr(
        s13, "load_frozen_candidates",
        lambda db, *, capture_id, limit: list(pairs[capture_id]),
    )
    monkeypatch.setattr(
        s13, "diagnose_candidate",
        lambda capture, sample: {
            "category": sample["_category"],
            "reason_code": "INTEGRITY_NOT_VERIFIED",
        },
    )
    monkeypatch.setattr(
        s13, "assess_frozen_candidate",
        lambda capture, sample: {
            "category": sample["_category"],
            "codes": sample["_codes"],
        },
    )


def test_no_db_and_no_schema_do_not_create_anything(tmp_path, monkeypatch):
    monkeypatch.setattr(s13, "_current_policy_state", lambda *args: _policy())
    missing = tmp_path / "missing.db"
    result = s13.diagnose_local_readiness(missing)
    assert result["status"] == "NO_LOCAL_SIMULATION_DB"
    assert not missing.exists()
    assert result["actual_provider_calls"] == result["db_writes"] == 0

    empty = tmp_path / "empty.db"
    sqlite3.connect(empty).close()
    assert s13.diagnose_local_readiness(empty)["status"] == "PROSPECTIVE_SCHEMA_NOT_READY"


def test_no_complete_capture_is_distinct_from_bad_policy(tmp_path, monkeypatch):
    monkeypatch.setattr(s13, "_current_policy_state", lambda *args: _policy())
    db = _db(tmp_path)
    result = s13.diagnose_local_readiness(db)
    assert result["status"] == "NO_COMPLETED_CAPTURE"
    assert result["total_complete_captures"] == 0


def test_real_sqlite_denominators_and_reasons_are_safe_and_complete(tmp_path, monkeypatch):
    db = _db(tmp_path)
    _rows(db, ["capture-a"])
    pairs = {"capture-a": [
        _sample("capture-a", 0, "INVALID", "RANK_MISSING", "POLICY_PROVENANCE_UNVERIFIED"),
        _sample("capture-a", 1, "INVALID", "RANK_MISSING"),
        _sample("capture-a", 2, "LEGACY_LIMITED", "LEGACY_DERIVED_IDENTITY", "STRATEGY_IDENTITY_MISMATCH"),
        _sample("capture-a", 3, "LOCAL_VALIDATED"),
        _sample("capture-a", 4, "REFERENCE_ONLY"),
    ]}
    with sqlite3.connect(db) as conn:
        conn.executemany(
            "INSERT INTO prospective_recommendation_sample VALUES(?,?,?)",
            [("capture-a", i, "ENTRY_CANDIDATE") for i in range(4)]
            + [("capture-a", 4, "REFERENCE_ONLY")],
        )
    monkeypatch.setattr(s13, "_current_policy_state", lambda *args: _policy())
    _fake_integrity(monkeypatch, pairs)
    before = db.read_bytes()
    result = s13.diagnose_local_readiness(db)
    assert db.read_bytes() == before
    assert result["status"] == "NO_ACTIVE_SELECTION_POLICY"
    assert result["next_action"] == "Q7_APPROVAL_PROTOCOL_UNAPPROVED"
    assert result["total_complete_captures"] == result["audited_captures"] == 1
    assert result["counts_complete"] is True
    assert result["inspected_samples"] == 5
    assert result["entry_candidates"] == 4
    assert result["reference_only"] == 1
    assert result["categories"] == {
        "LOCAL_VALIDATED": 1, "LEGACY_LIMITED": 1, "INVALID": 2,
    }
    assert result["invalid_reason_counts"] == {
        "POLICY_PROVENANCE_UNVERIFIED": 1, "RANK_MISSING": 2,
    }
    assert result["legacy_limitation_counts"] == {
        "LEGACY_DERIVED_IDENTITY": 1, "STRATEGY_IDENTITY_MISMATCH": 1,
    }
    assert result["provider_status"] == "PROVIDER_HOLD"
    assert not result["investment_improvement_verified"]
    assert not result["production_policy_changed"]
    assert result["db_writes"] == result["actual_provider_calls"] == 0


def test_active_policy_does_not_imply_real_model_permission(tmp_path, monkeypatch):
    db = _db(tmp_path)
    _rows(db, ["capture-a"])
    with sqlite3.connect(db) as conn:
        conn.execute(
            "INSERT INTO prospective_recommendation_sample VALUES(?,?,?)",
            ("capture-a", 0, "ENTRY_CANDIDATE"),
        )
    _fake_integrity(monkeypatch, {"capture-a": [
        _sample("capture-a", 0, "LOCAL_VALIDATED"),
    ]})
    monkeypatch.setattr(s13, "_current_policy_state", lambda *args: _policy(active=True))
    result = s13.diagnose_local_readiness(db)
    assert result["status"] == "LOCAL_BASELINE_READY_PROVIDER_HOLD"
    assert result["next_action"] == "OBSERVE_ONLY_NO_REAL_PROVIDER_AUTHORIZATION"
    assert not result["investment_improvement_verified"]
    assert result["actual_provider_calls"] == 0


def test_overlimit_capture_fails_closed_without_partial_denominator(tmp_path, monkeypatch):
    db = _db(tmp_path)
    _rows(db, ["capture-a"])
    with sqlite3.connect(db) as conn:
        conn.executemany(
            "INSERT INTO prospective_recommendation_sample VALUES(?,?,?)",
            [("capture-a", i, "ENTRY_CANDIDATE") for i in range(500)],
        )
    monkeypatch.setattr(s13, "_current_policy_state", lambda *args: _policy())
    monkeypatch.setattr(s13, "load_frozen_candidates",
                        lambda *a, **k: pytest.fail("must not inspect incomplete cohort"))
    report = s13.diagnose_local_readiness(db)
    assert report["status"] == "CAPTURE_SAMPLE_LIMIT_REACHED"
    assert report["counts_complete"] is False
    assert "entry_candidates" not in report


def test_changed_capture_is_not_silently_claimed_complete(tmp_path, monkeypatch):
    db = _db(tmp_path)
    _rows(db, ["capture-a"])
    with sqlite3.connect(db) as conn:
        conn.execute(
            "INSERT INTO prospective_recommendation_sample VALUES(?,?,?)",
            ("capture-a", 0, "ENTRY_CANDIDATE"),
        )
    monkeypatch.setattr(s13, "_current_policy_state", lambda *args: _policy())
    monkeypatch.setattr(s13, "load_frozen_candidates", lambda *a, **k: [])
    report = s13.diagnose_local_readiness(db)
    assert report["status"] == "CAPTURE_CHANGED_DURING_READ"
    assert report["counts_complete"] is False


def test_latest_twenty_never_claim_all_when_more_exist(tmp_path, monkeypatch):
    db = _db(tmp_path)
    _rows(db, [f"capture-{i}" for i in range(21)])
    monkeypatch.setattr(s13, "_current_policy_state", lambda *args: _policy())
    _fake_integrity(monkeypatch, {f"capture-{i}": [] for i in range(21)})
    result = s13.diagnose_local_readiness(db)
    assert result["total_complete_captures"] == 21
    assert result["audited_captures"] == 20
    assert result["counts_complete"] is False


def test_cli_one_command_and_guardrails(tmp_path, monkeypatch, capsys):
    db = tmp_path / "never-created.db"
    monkeypatch.setattr(cli, "diagnose_local_readiness",
                        lambda db: s13._result(
                            "NO_LOCAL_SIMULATION_DB", policy=_policy(),
                        ))
    args = cli.build_parser().parse_args([
        "local-readiness", "--simulation-db", str(db),
    ])
    result = cli.execute(args)
    assert result["status"] == "NO_LOCAL_SIMULATION_DB"
    cli.display(result)
    output = capsys.readouterr().out
    assert "Q7 운영 승인 기준" in output
    assert "Runtime DB 쓰기 0건" in output
    assert not db.exists()

    args.capture_id = "manually-selected"
    with pytest.raises(DecisionReviewContractError, match="S13_AUTO_DISCOVERY_ARGUMENT_CONFLICT"):
        cli.execute(args)
    args.capture_id = None
    args.save_preflight = True
    with pytest.raises(DecisionReviewContractError, match="S7_4_DIAGNOSTIC_READ_ONLY"):
        cli.execute(args)
