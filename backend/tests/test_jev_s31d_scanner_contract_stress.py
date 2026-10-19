"""S31-D stresses real S3 validation code with independent synthetic fixtures."""
from __future__ import annotations

from copy import deepcopy
import json

import pytest

from app.jev import s31d_scanner_contract_stress as stress
from tools.data import jev_s31d_contract_stress as cli


def test_contract_stress_matches_real_s3_adapter_and_marks_scope():
    report = stress.run_s31d_contract_stress()
    assert report["status"] == "SYNTHETIC_S3_CONTRACT_STRESS_PASS"
    assert report["scenario_count"] == len(stress.CASES) == 12
    assert report["contract_expectations_met"] == 12
    assert report["actual_s3_projection_function_executed"] is True
    assert report["actual_scanner_service_executed"] is False
    assert report["investment_uplift_proven"] is False
    assert report["jev_comparison_eligible"] is False
    assert report["new_jev_provider_calls"] == 0
    assert report["production_db_writes"] == report["research_db_writes"] == 0
    assert report["orders"] == 0
    assert all(x["actual_jev_response"] is None for x in report["cases"])


def test_expected_risk_block_and_warning_behavior_are_not_conflated():
    records = {x["scenario"]: x for x in stress.run_s31d_contract_stress()["cases"]}
    assert records["risk_block"]["observed_s3_contract_result"] == "RISK_BLOCKED_OUT_OF_SCOPE"
    assert records["guide_risk_block"]["observed_s3_contract_result"] == "RISK_BLOCKED_OUT_OF_SCOPE"
    assert records["risk_warning_true"]["observed_s3_contract_result"] == "OFFLINE_INSPECTABLE_ONLY"
    assert records["risk_warning_true"]["risk_warning_accepted_without_s3_rejection"] is True
    assert records["risk_warning_missing"]["observed_s3_contract_result"] == "BASELINE_RISK_MISSING"


def test_date_policy_semantic_and_snapshot_identity_guards():
    records = {x["scenario"]: x for x in stress.run_s31d_contract_stress()["cases"]}
    assert records["eod_date_mismatch"]["observed_s3_contract_result"] == "FUTURE_OR_MISMATCHED_EVIDENCE_DATE"
    assert records["policy_evidence_missing"]["observed_s3_contract_result"] == "POLICY_PROVENANCE_UNVERIFIED"
    assert records["policy_pin_mismatch"]["observed_s3_contract_result"] == "POLICY_PIN_MISMATCH"
    assert records["condition_pass_proof_mismatch"]["observed_s3_contract_result"] == "ENGINE_PASS_PROOF_MISMATCH"
    assert records["semantic_source_hash_tampered"]["observed_s3_contract_result"] == "SEMANTIC_SOURCE_V2_HASH_MISMATCH"
    assert records["strategy_identity_forged"]["observed_s3_contract_result"] == "STRATEGY_IDENTITY_MISMATCH"
    assert records["original_snapshot_hash_tampered"]["observed_s3_contract_result"] == "SNAPSHOT_HASH_MISMATCH"


def test_fixture_uses_frozen_source_without_mutation():
    capture, sample = stress._base_source()
    before = deepcopy((capture, sample))
    stress.run_s31d_contract_stress()
    assert (capture, sample) == before


def test_stress_command_json_is_readable_and_no_model_call(capsys):
    assert cli.main(["--json"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["contract_expectations_met"] == 12
    assert report["source_market_data_used"] is False
    assert report["new_jev_provider_calls"] == 0


def test_contract_drift_returns_nonzero(monkeypatch, capsys):
    monkeypatch.setattr(stress, "build_scanner_review_input",
                        lambda *a, **kw: {"status": "INCORRECT_ALWAYS_ALLOW"})
    assert cli.main(["--json"]) == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "HOLD_S3_CONTRACT_DRIFT"
    assert payload["contract_expectations_met"] == 0


def test_exception_is_fail_closed(monkeypatch, capsys):
    monkeypatch.setattr(cli, "run_s31d_contract_stress",
                        lambda: (_ for _ in ()).throw(ValueError("fixture-broken")))
    assert cli.main([]) == 2
    output = json.loads(capsys.readouterr().out)
    assert output["status"] == "HOLD_FIXTURE_INVALID"
    assert output["new_jev_provider_calls"] == 0


def test_no_unverified_crash_or_stale_returns_are_claimed():
    report = stress.run_s31d_contract_stress()
    assert any("INTRADAY_CRASH" in x for x in report["unmeasured"])
    assert any("LIVE_QUOTE_STALENESS" in x for x in report["unmeasured"])
    assert report["scope"] == "SYNTHETIC_S3_CONTRACT_ONLY"
