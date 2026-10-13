"""Q7 S15 research freeze; synthetic plans only, no approved thresholds."""
from __future__ import annotations

from datetime import datetime
import json
import sqlite3
from zoneinfo import ZoneInfo

import pytest

from app.jev.q7_precommit_s15 import (
    Q7PrecommitError, freeze, inventory, load, template, validate_spec,
    verify_artifact, VERSION,
)
from tools.data import q7_precommit as cli


KST = ZoneInfo("Asia/Seoul")
NOW = datetime(2026, 10, 14, 8, 0, tzinfo=KST)


def _spec():
    value = template("pullback")
    value.update({
        "study_id": "research-demo-01",
        "operator": "SYNTHETIC_TEST_OPERATOR",
        "market_scope": "KOSPI",
    })
    value["time_split"].update({
        "development_start": "2026-09-01",
        "development_end": "2026-10-01",
        "holdout_start": "2026-11-16",
        "holdout_end": "2027-03-31",
        "purge_trading_days": 20,
    })
    value["population"].update({
        "universe_rule": "KOSPI eligible universe as known to the scanner at the signal date",
        "regime_rule": "Classify regimes solely by a prior-window index price rule before signal",
        "minimum_independent_samples_total": 40,
        "minimum_independent_samples_per_regime": 8,
        "maturity_trading_days": 20,
    })
    value["comparison"].update({
        "round_trip_cost_pct": 0.2, "fee_pct": 0.05,
        "tax_pct": 0.1, "slippage_pct": 0.1,
        "min_outperformance_pct": 1.5,
        "max_drawdown_pct": 12,
        "confidence_level_pct": 95,
        "multiple_testing_rule": "Control false discoveries across all tested strategy versions",
    })
    value["decision"].update({
        "promotion_rule": "Promote only when all prior stated minimum counts and risk limits pass",
        "abstain_rule": "Abstain when any required stratum lacks mature independent observations",
        "demotion_rule": "Demote only after two prespecified holdout checks breach loss limits",
        "rollback_rule": "Rollback on persistent safety regression in an independent future cohort",
    })
    return value


def _err(fn, code):
    with pytest.raises(Q7PrecommitError) as caught:
        fn()
    assert caught.value.code == code


def test_template_has_no_invented_approval_or_numerical_cutoffs():
    draft = template("pullback")
    assert draft["contract_version"] == VERSION
    assert draft["time_split"]["holdout_start"] is None
    assert draft["population"]["minimum_independent_samples_total"] is None
    assert draft["comparison"]["min_outperformance_pct"] is None
    assert draft["comparison"]["max_drawdown_pct"] is None
    _err(lambda: validate_spec(draft, now=NOW), "Q7_STUDY_ID_INVALID")


def test_explicit_future_plan_freezes_once_and_verifies_without_mutation(tmp_path):
    spec = _spec()
    root = tmp_path / "precommits"
    before = json.dumps(spec, sort_keys=True)
    record = freeze(spec, root=root, now=NOW)
    assert record["created"] is True
    assert record["q7_approval_eligible"] is False
    assert record["production_activation_allowed"] is False
    assert json.dumps(spec, sort_keys=True) == before
    assert root.joinpath(spec["study_id"] + ".json").is_file()

    loaded = load(spec["study_id"], root=root)
    result = verify_artifact(loaded, expected_study_id=spec["study_id"])
    assert result["status"] == "VALID_LOCAL_RECORD_NOT_TRUSTED_ATTESTATION"
    assert loaded["authority"] == "RESEARCH_ONLY_NOT_Q7_APPROVED"
    assert loaded["trusted_time_attested"] is False

    retry = freeze(spec, root=root, now=NOW)
    assert retry["created"] is False
    assert retry["spec_hash"] == record["spec_hash"]
    assert json.dumps(load(spec["study_id"], root=root), sort_keys=True) == json.dumps(loaded, sort_keys=True)


def test_identity_is_not_reconstructed_from_a_legacy_capture():
    spec = _spec()
    spec["strategy"]["strategy_version_id"] = "fake-posthoc"
    _err(lambda: validate_spec(spec, now=NOW), "Q7_STRATEGY_IDENTITY_NOT_CURRENT")


@pytest.mark.parametrize("field,invalid,code", [
    ("holdout_start", "2026-10-14", "Q7_HOLDOUT_NOT_PROSPECTIVE"),
    ("holdout_start", "2026-08-01", "Q7_HOLDOUT_NOT_PROSPECTIVE"),
    ("development_end", "2026-11-30", "Q7_HOLDOUT_NOT_PROSPECTIVE"),
    ("holdout_start", "2026-99-99", "Q7_SPLIT_DATE_INVALID"),
])
def test_backdated_or_unparseable_holdout_is_refused(field, invalid, code):
    spec = _spec()
    spec["time_split"][field] = invalid
    _err(lambda: validate_spec(spec, now=NOW), code)


@pytest.mark.parametrize("part,key,invalid,code", [
    ("population", "minimum_independent_samples_total", None, "Q7_MIN_SAMPLE_REQUIRED"),
    ("population", "minimum_independent_samples_total", True, "Q7_MIN_SAMPLE_REQUIRED"),
    ("population", "minimum_independent_samples_per_regime", 0, "Q7_REGIME_MIN_SAMPLE_REQUIRED"),
    ("comparison", "min_outperformance_pct", None, "Q7_IMPROVEMENT_THRESHOLD_REQUIRED"),
    ("comparison", "min_outperformance_pct", float("nan"), "Q7_IMPROVEMENT_THRESHOLD_REQUIRED"),
    ("comparison", "confidence_level_pct", None, "Q7_CONFIDENCE_REQUIRED"),
    ("comparison", "slippage_pct", None, "Q7_COST_REQUIRED"),
    ("comparison", "multiple_testing_rule", None, "Q7_MULTIPLE_TESTING_RULE_REQUIRED"),
    ("population", "regime_rule", "UNKNOWN", "Q7_REGIME_RULE_REQUIRED"),
    ("decision", "rollback_rule", None, "Q7_ROLLBACK_RULE_REQUIRED"),
    ("evidence", "result_backfill_forbidden", False, "Q7_EVIDENCE_SAFETY_INVALID"),
])
def test_critical_threshold_and_provenance_gaps_fail_closed(part, key, invalid, code):
    spec = _spec()
    spec[part][key] = invalid
    _err(lambda: validate_spec(spec, now=NOW), code)


def test_duplicate_id_cannot_change_frozen_spec(tmp_path):
    root = tmp_path / "store"
    spec = _spec()
    freeze(spec, root=root, now=NOW)
    old = root.joinpath(spec["study_id"] + ".json").read_bytes()
    spec["comparison"]["min_outperformance_pct"] = 0.1
    _err(lambda: freeze(spec, root=root, now=NOW), "Q7_STUDY_ALREADY_FROZEN_DIFFERENT_SPEC")
    assert root.joinpath(spec["study_id"] + ".json").read_bytes() == old


def test_hash_and_file_tampering_are_detected(tmp_path):
    root = tmp_path / "store"
    spec = _spec()
    freeze(spec, root=root, now=NOW)
    path = root / (spec["study_id"] + ".json")
    record = json.loads(path.read_text(encoding="utf-8"))
    record["spec"]["comparison"]["min_outperformance_pct"] = 0
    path.write_text(json.dumps(record), encoding="utf-8")
    _err(lambda: load(spec["study_id"], root=root), "Q7_ARTIFACT_SPEC_HASH_MISMATCH")


def test_purge_maturity_and_sample_counts_are_consistent():
    spec = _spec()
    spec["time_split"]["purge_trading_days"] = 10
    _err(lambda: validate_spec(spec, now=NOW), "Q7_PURGE_SHORTER_THAN_MATURITY")
    spec = _spec()
    spec["population"]["minimum_independent_samples_per_regime"] = 100
    _err(lambda: validate_spec(spec, now=NOW), "Q7_REGIME_SAMPLE_EXCEEDS_TOTAL")


def test_inventory_is_readonly_and_does_not_invent_mature_counts(tmp_path):
    db = tmp_path / "simulation.db"
    assert inventory(db)["status"] == "NO_SIMULATION_DB"
    assert not db.exists()
    with sqlite3.connect(db) as conn:
        conn.executescript("""
            CREATE TABLE prospective_capture_run (
                id TEXT PRIMARY KEY, status TEXT
            );
            CREATE TABLE prospective_recommendation_sample (
                capture_run_id TEXT, sample_index INTEGER, action TEXT,
                signal_date TEXT, market TEXT, ticker TEXT, strategy TEXT
            );
            CREATE TABLE prospective_evaluation_report (id TEXT);
            INSERT INTO prospective_capture_run VALUES('c1','COMPLETE');
            INSERT INTO prospective_recommendation_sample VALUES
                ('c1',0,'ENTRY_CANDIDATE','2026-10-10','KOSPI','005930','pullback'),
                ('c1',1,'ENTRY_CANDIDATE','2026-10-10','KOSPI','005930','pullback'),
                ('c1',2,'REFERENCE_ONLY','2026-10-10','KOSPI','000660','pullback');
        """)
    old = db.read_bytes()
    result = inventory(db)
    assert db.read_bytes() == old
    assert result["raw_complete_captures"] == 1
    assert result["raw_samples"] == 3
    assert result["raw_entry_samples"] == 2
    assert result["strategies"][0]["distinct_keys"] == 1
    assert result["evaluation_reports"] == 0
    assert result["independent_mature_verified_count"] is None
    assert result["raw_distinct_keys_are_independent_samples"] is False
    assert result["production_activation_allowed"] is False


def test_cli_requires_ack_and_cannot_modify_runtime_db(tmp_path, monkeypatch):
    db = tmp_path / "no-runtime.db"
    spec_path = tmp_path / "q7.json"
    spec_path.write_text(json.dumps(_spec()), encoding="utf-8")
    root = tmp_path / "store"
    args = cli.parser().parse_args([
        "freeze", "--file", str(spec_path), "--store-dir", str(root),
    ])
    _err(lambda: cli.execute(args), "Q7_EXPLICIT_FREEZE_ACKNOWLEDGEMENT_REQUIRED")
    assert not root.exists()
    assert not db.exists()
    monkeypatch.setattr(cli, "freeze", lambda spec, **kwargs: {
        "status": "VALID_LOCAL_RECORD_NOT_TRUSTED_ATTESTATION",
        "q7_approval_eligible": False,
        "production_activation_allowed": False,
    })
    args.acknowledge_research_only = True
    result = cli.execute(args)
    assert result["actual_provider_calls"] == 0
    assert not db.exists()


def test_existing_frozen_record_survives_future_date_and_engine_update(
    tmp_path, monkeypatch,
):
    from app.jev import q7_precommit_s15 as s15

    root = tmp_path / "q7"
    spec = _spec()
    original = freeze(spec, root=root, now=NOW)
    future_clock = datetime(2026, 12, 15, 8, tzinfo=KST)
    monkeypatch.setattr(
        s15, "_definition",
        lambda *_: {
            "strategy_key": "pullback",
            "strategy_version_id": "next-engine-version",
            "definition_hash": "0" * 64,
        },
    )
    # Immutable history remains independently hash-verifiable; *new* freezes
    # need to match the engine currently running.
    assert load(spec["study_id"], root=root)["record_hash"]
    after = freeze(spec, root=root, now=future_clock)
    assert after["created"] is False
    assert after["spec_hash"] == original["spec_hash"]

    new_plan = _spec()
    new_plan["study_id"] = "after-engine-changed"
    _err(lambda: freeze(new_plan, root=root, now=NOW),
         "Q7_STRATEGY_IDENTITY_NOT_CURRENT")
