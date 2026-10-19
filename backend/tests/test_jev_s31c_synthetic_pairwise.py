"""S31-C: compare only real-origin S6 journal decisions to their synthetic gold."""
from __future__ import annotations

from copy import deepcopy
import json
import sqlite3

from app.jev.decision_reviewer_micro_canary import (
    CASES, PROVIDER_ID, MicroJournal, synthetic_projection,
)
from app.jev.s31c_synthetic_pairwise import compare_actual_s6_records
from tools.data import jev_s31c_pairwise as cli

GOLD = {case["id"]: case["gold"] for case in CASES}


def row(case: str, choice: str, *, protocol="protocol-a", model="jev-latest",
        origin="ACTUAL_PROVIDER", reported="jev-latest") -> dict:
    return {
        "review_id": case + protocol + origin,
        "execution_origin": origin,
        "state": "VALID",
        "case_id": case,
        "expected_gold": GOLD[case],
        "input_hash": synthetic_projection(case)["input_hash"],
        "provider_id": PROVIDER_ID,
        "protocol_hash": protocol,
        "model_id": model,
        "decision": choice,
        "output": {"decision": choice},
        "typed_response": {
            "decision": choice, "requested_model": model, "model": reported,
            "model_identity_status": "REVISION_UNVERIFIED",
        },
        "duration_ms": 125.0,
        "computed_cost_usd": "0.00001",
        "cost_status": "ESTIMATED_FROM_PUBLIC_STANDARD_RATE",
    }


def test_paired_five_cases_counts_real_model_responses_without_mutation():
    rows = [row(x["id"], x["gold"]) for x in CASES]
    rows[-1]["decision"] = "REVIEW_REQUIRED" if rows[-1]["expected_gold"] != "REVIEW_REQUIRED" else "ABSTAIN"
    rows[-1]["typed_response"]["decision"] = rows[-1]["decision"]
    rows[-1]["output"]["decision"] = rows[-1]["decision"]
    before = deepcopy(rows)
    report = compare_actual_s6_records(rows)
    assert rows == before
    assert report["status"] == "SYNTHETIC_PAIRED_EVIDENCE_ONLY"
    assert report["comparable_actual_responses"] == 5
    cohort = report["cohorts"][0]
    assert cohort["case_count"] == 5
    assert cohort["baseline_matches"] == 1
    assert cohort["jev_matches"] == 4
    assert cohort["paired_correct_count_difference"] == 3
    assert cohort["full_five_case_coverage"] is True
    assert report["investment_uplift_proven"] is False
    assert report["new_provider_requests"] == report["runtime_db_writes"] == 0


def test_mock_and_nonvalid_actual_not_counted_as_success():
    valid = row(CASES[0]["id"], CASES[0]["gold"])
    mock = row(CASES[1]["id"], CASES[1]["gold"], origin="MOCK_TEST")
    failed = row(CASES[2]["id"], CASES[2]["gold"])
    failed["state"] = "ERROR"
    report = compare_actual_s6_records([valid, mock, failed])
    assert report["actual_provider_journal_records"] == 2
    assert report["mock_or_nonactual_records_excluded"] == 1
    assert report["comparable_actual_responses"] == 1
    assert report["invalid_or_noncomparable_actual_records"] == 1


def test_tampered_input_and_gold_excluded_instead_of_inflating_score():
    a = row(CASES[0]["id"], CASES[0]["gold"])
    b = row(CASES[1]["id"], CASES[1]["gold"])
    a["expected_gold"] = "ABSTAIN"
    b["input_hash"] = "forged"
    report = compare_actual_s6_records([a, b])
    assert report["comparable_actual_responses"] == 0
    assert report["invalid_or_noncomparable_actual_records"] == 2
    assert report["status"] == "HOLD_NO_COMPARABLE_ACTUAL_RESPONSES"


def test_model_provenance_and_inconsistent_decision_excluded():
    a = row(CASES[0]["id"], CASES[0]["gold"])
    a["typed_response"]["decision"] = "ABSTAIN"
    b = row(CASES[1]["id"], CASES[1]["gold"])
    b["typed_response"]["requested_model"] = "other"
    result = compare_actual_s6_records([a, b])
    assert result["comparable_actual_responses"] == 0
    assert len(result["excluded"]) == 2


def test_duplicate_case_in_same_cohort_excludes_both_not_choose_favorable_one():
    x = row(CASES[0]["id"], CASES[0]["gold"])
    y = row(CASES[0]["id"], "ABSTAIN")
    result = compare_actual_s6_records([x, y])
    assert result["comparable_actual_responses"] == 0
    assert result["invalid_or_noncomparable_actual_records"] == 2
    assert all(r["reason_code"] == "DUPLICATE_CASE_IN_SAME_COHORT" for r in result["excluded"])


def test_protocols_and_reported_models_never_pooled():
    case = CASES[1]["id"]
    result = compare_actual_s6_records([
        row(case, GOLD[case], protocol="p1"),
        row(case, "ABSTAIN", protocol="p2"),
        row(CASES[2]["id"], GOLD[CASES[2]["id"]], protocol="p1", reported="jev-1.2.3"),
    ])
    assert len(result["cohorts"]) == 3
    assert result["comparable_actual_responses"] == 3
    assert all(c["case_count"] == 1 for c in result["cohorts"])
    assert any(c["reported_model_changed_within_protocol"] for c in result["cohorts"])


def test_journal_read_only_and_cli_does_not_touch_original(tmp_path, monkeypatch, capsys):
    path = tmp_path / "s6.sqlite3"
    with sqlite3.connect(path) as conn:
        MicroJournal(conn).initialize()
        fixture = row(CASES[0]["id"], GOLD[CASES[0]["id"]])
        conn.execute(
            """INSERT INTO jev_s5_synthetic (
              review_id, protocol_hash, case_id, input_hash, request_hash,
              expected_gold, provider_id, model_id, state, decision,
              output_json, typed_response_json, reserved_usd, computed_cost_usd,
              cost_status, execution_origin, created_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (fixture["review_id"], fixture["protocol_hash"], fixture["case_id"],
             fixture["input_hash"], "request-hash", fixture["expected_gold"],
             fixture["provider_id"], fixture["model_id"], "VALID",
             fixture["decision"], json.dumps(fixture["output"]),
             json.dumps(fixture["typed_response"]), "0.01", "0.00001",
             fixture["cost_status"], "ACTUAL_PROVIDER", "2026-10-19T00:00:00+00:00"),
        )
        conn.commit()
    before = path.read_bytes()
    monkeypatch.setattr(cli, "RESEARCH_DB", path)
    assert cli.main(["--json"]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["comparable_actual_responses"] == 1
    assert path.read_bytes() == before
    assert not list(tmp_path.glob("*.sqlite3-wal"))
    assert not list(tmp_path.glob("*.sqlite3-shm"))


def test_missing_research_db_exits_hold_without_creating_file(tmp_path, monkeypatch, capsys):
    absent = tmp_path / "missing.sqlite3"
    monkeypatch.setattr(cli, "RESEARCH_DB", absent)
    assert cli.main([]) == 2
    assert not absent.exists()
    result = json.loads(capsys.readouterr().out)
    assert result["reason_code"] == "S31C_S6_JOURNAL_NOT_FOUND"
    assert result["new_provider_requests"] == 0
