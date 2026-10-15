"""S28 frozen-rank explanation diagnostics; never influence Scanner production ranking."""
from __future__ import annotations

from copy import deepcopy
import json

import pytest

from app.jev.rank_evidence_s28 import inspect_receipt
from app.jev.research_scanner_s24 import ResearchCaptureError, SOURCE, digest
from tools.data import q7_rank_explain as explain

CODES = ["001820", "005830", "010060", "071090", "093370"]
NAMES = ["삼화콘덴서", "DB손해보험", "OCI홀딩스", "하이스틸", "후성"]
DISTANCES = [4.0702, 4.3173, 6.6059, 11.9822, 7.0413]


def _receipt(*, group: bool = True):
    identity = {
        "strategy_key": "pullback",
        "strategy_version_id": "current-strategy-id",
        "definition_hash": "current-engine-hash",
    }
    rows = []
    for i, (code, name, distance) in enumerate(zip(CODES, NAMES, DISTANCES)):
        rows.append({
            "market": "KOSPI",
            "code": code,
            "name": name,
            "action": "ENTRY_CANDIDATE",
            "data_date": "2026-10-14",
            "strategy": identity["strategy_key"],
            "strategy_version_id": identity["strategy_version_id"],
            "strategy_definition_hash": identity["definition_hash"],
            "risk": {"status": "READY", "warning": False},
            "priority": {
                "rank": i + 1,
                "tie_group": 1 if group else i + 1,
                "tie_size": 5 if group else 1,
                "strict_rank": not group,
                "tie_focus": group and i == 0,
                "tie_focus_order": int(group and i > 0),
                "tie_breaker": "STRUCTURAL_TARGET_NEAREST_PROMOTE" if group else "NONE",
                "entry_gap_pct": 0,
                "entry_gap_basis": "지지 가격 근처 진입 구간",
                "structural_target_distance_pct": distance,
                "structural_target_basis": "최근 저항 후보",
                "historical_status": "DATA_UNAVAILABLE",
                "tier": "READY",
                "previous_rank": (3 if i == 0 else i + 1),
                "rank_change": (2 if i == 0 else 0),
            },
            "entry_risk_guide": {
                "risk": {
                    "status": "READY",
                    "entry_reference_price": 100.0,
                    "invalidation_price": 95.0,
                    "target1_price": 107.5,
                    "rr1": 1.5,
                    "structural_target1_price": 100.0 * (1 + distance / 100),
                    "target1_cap_applied": True,
                    "reference_only": False,
                },
            },
        })
    payload = {
        "version": "Q7_S24_ISOLATED_RESEARCH_SCANNER_V1",
        "authority": SOURCE,
        "execution_mode": "POSTHOC_TECHNICAL_SMOKE_ONLY",
        "evaluation_use": "TECHNICAL_SMOKE_ONLY_NOT_Q7_COHORT",
        "q7_approval_eligible": False,
        "production_policy_activation_allowed": False,
        "source_date": "2026-10-14",
        "market_scope": "KOSPI",
        "original_strategy_rows": [identity],
        "original_scanner_candidates": rows,
        "candidate_count": 5,
        "entry_candidates": 5,
    }
    payload["payload_hash"] = digest(payload)
    return payload


def _seal(payload):
    payload["payload_hash"] = digest({
        k: v for k, v in payload.items() if k != "payload_hash"
    })
    return payload


def _reject(payload, reason):
    with pytest.raises(ResearchCaptureError) as error:
        inspect_receipt(payload)
    assert error.value.code == reason


def test_real_style_five_candidate_tie_is_presentation_not_profit_rank():
    r = inspect_receipt(_receipt())
    assert r["status"] == "DESCRIPTIVE_DIAGNOSTIC_ONLY"
    assert r["candidate_count"] == r["entry_candidates"] == 5
    assert [x["code"] for x in r["candidates"]] == CODES
    assert len(r["tie_groups"]) == 1
    group = r["tie_groups"][0]
    assert group["status"] == "TIE_NEAREST_STRUCTURE_THEN_CODE"
    assert group["winner_selected_for_presentation_only"] == "001820"
    assert group["strict_superiority_proven"] is False
    assert group["codes"] == CODES
    assert all(x["strict_rank"] is False for x in r["candidates"])
    assert all(x["historical_status"] == "DATA_UNAVAILABLE" for x in r["candidates"])
    assert r["source_has_independent_precommit_proof"] is False
    assert r["prediction_accuracy_or_uplift_proven"] is False
    assert r["q7_approval_eligible"] is False
    assert r["runtime_db_writes"] == r["network_requests"] == 0


def test_target1_is_not_the_structural_resistance_or_expected_gain():
    first = inspect_receipt(_receipt())["candidates"][0]
    p = first["price_evidence"]
    assert p["status"] == "REFERENCE_ARITHMETIC_CHECKED"
    assert p["risk_distance_pct"] == 5.0
    assert p["target1_distance_pct"] == 7.5
    assert p["target1_r_multiple"] == 1.5
    assert p["structural_distance_pct"] == 4.0702
    assert p["structural_r_multiple"] == round(4.0702 / 5.0, 4)
    assert p["target1_cap_applied"] is True
    assert p["invalidation_is_not_an_executed_stop_order"] is True
    assert p["engine_rr1_consistent"] is True
    assert p["target1_r_multiple"] != p["structural_r_multiple"]


def test_previous_rank_is_explicitly_same_run_not_yesterday():
    receipt = _receipt()
    r = inspect_receipt(receipt)
    assert r["candidates"][0]["previous_rank_is_same_run_before_sort"] == 3
    assert r["candidates"][0]["same_run_rank_change"] == 2
    human = explain.korean_summary(r)
    assert "같은 실행 내 정렬 전후 순위" in human
    assert "삼화콘덴서" in human
    assert "동률 그룹 1" in human
    assert "사후/연구용 설명만 가능" in human


def test_receipt_hash_tampering_without_reseal_rejected():
    payload = _receipt()
    payload["original_scanner_candidates"][0]["priority"]["rank"] = 2
    _reject(payload, "S28_RECEIPT_PAYLOAD_HASH_MISMATCH")


def test_source_strategy_identity_mismatch_rejected_even_with_reseal():
    payload = _receipt()
    payload["original_scanner_candidates"][0]["strategy_definition_hash"] = "fake"
    _reject(_seal(payload), "S28_SOURCE_STRATEGY_IDENTITY_MISMATCH")


@pytest.mark.parametrize("change,reason", [
    ("count", "S28_RECEIPT_COUNT_MISMATCH"),
    ("entry_count", "S28_ENTRY_COUNT_MISMATCH"),
    ("wrong_date", "S28_CANDIDATE_SOURCE_MISMATCH"),
    ("duplicate", "S28_CANDIDATE_SOURCE_MISMATCH"),
    ("rank", "S28_RANK_SEQUENCE_INVALID"),
    ("bad_authority", "S28_RECEIPT_RESEARCH_AUTHORITY_REQUIRED"),
])
def test_source_integrity_fail_closed(change, reason):
    payload = _receipt()
    rows = payload["original_scanner_candidates"]
    if change == "count":
        payload["candidate_count"] += 1
    elif change == "entry_count":
        payload["entry_candidates"] -= 1
    elif change == "wrong_date":
        rows[1]["data_date"] = "2026-10-13"
    elif change == "duplicate":
        rows[1]["code"] = rows[0]["code"]
    elif change == "rank":
        rows[1]["priority"]["rank"] = 4
    elif change == "bad_authority":
        payload["q7_approval_eligible"] = True
    _reject(_seal(payload), reason)


def test_resealed_but_inconsistent_tie_metadata_is_not_silent_success():
    payload = _receipt()
    rows = payload["original_scanner_candidates"]
    rows[0]["priority"]["tie_focus"] = False
    rows[1]["priority"]["tie_focus"] = True
    report = inspect_receipt(_seal(payload))
    assert report["status"] == "EVIDENCE_INCONSISTENT_REVIEW_REQUIRED"
    assert report["tie_groups"][0]["status"] == "INCONSISTENT_TIE_METADATA"
    assert report["tie_metadata_inconsistent_groups"] == [1]


def test_missing_stop_does_not_fabricate_r_multiple():
    payload = _receipt()
    del payload["original_scanner_candidates"][0]["entry_risk_guide"]["risk"]["invalidation_price"]
    report = inspect_receipt(_seal(payload))
    assert report["candidates"][0]["price_evidence"]["status"] == "REFERENCE_PRICE_UNAVAILABLE"
    assert report["candidates"][0]["price_evidence"]["target1_r_multiple"] is None
    assert report["candidates"][0]["price_evidence"]["structural_distance_pct"] == 4.0702


def test_invalid_order_or_engine_rr1_disagreement_surfaces_hold():
    payload = _receipt()
    payload["original_scanner_candidates"][0]["entry_risk_guide"]["risk"]["invalidation_price"] = 101
    report = inspect_receipt(_seal(payload))
    assert report["status"] == "EVIDENCE_INCONSISTENT_REVIEW_REQUIRED"
    assert report["risk_formula_review_codes"] == ["001820"]

    payload = _receipt()
    payload["original_scanner_candidates"][0]["entry_risk_guide"]["risk"]["rr1"] = 99.0
    report = inspect_receipt(_seal(payload))
    assert report["status"] == "EVIDENCE_INCONSISTENT_REVIEW_REQUIRED"
    assert report["candidates"][0]["price_evidence"]["engine_rr1_consistent"] is False


def test_partial_group_cannot_claim_tie_explanation():
    payload = _receipt()
    payload["original_scanner_candidates"] = payload["original_scanner_candidates"][:4]
    payload["candidate_count"] = 4
    payload["entry_candidates"] = 4
    report = inspect_receipt(_seal(payload))
    assert report["tie_groups"][0]["status"] == "PARTIAL_GROUP_CANNOT_VERIFY"
    assert report["tie_groups"][0]["winner_selected_for_presentation_only"] is None


def test_no_structural_reference_uses_code_only_tie():
    payload = _receipt()
    for row in payload["original_scanner_candidates"]:
        row["priority"]["structural_target_distance_pct"] = None
        row["priority"]["tie_focus"] = False
        row["priority"]["tie_focus_order"] = 0
        row["priority"]["tie_breaker"] = "CODE_STABLE_ORDER"
    report = inspect_receipt(_seal(payload))
    assert report["tie_groups"][0]["status"] == "TIE_CODE_ONLY"


def test_cli_readonly_korean_and_json_and_missing_file_fail_closed(tmp_path, capsys):
    payload = _receipt()
    path = tmp_path / "capture.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    before = path.read_bytes()
    assert explain.main(["--file", str(path)]) == 0
    text = capsys.readouterr().out
    assert "삼화콘덴서" in text and "동률" in text
    assert path.read_bytes() == before
    assert explain.main(["--file", str(path), "--json"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "DESCRIPTIVE_DIAGNOSTIC_ONLY"
    assert report["runtime_db_writes"] == 0
    assert path.read_bytes() == before
    assert explain.main(["--file", str(tmp_path / "absent.json")]) == 2
    err = json.loads(capsys.readouterr().out)
    assert err["reason_code"] == "S28_RECEIPT_FILE_MISSING_OR_TOO_LARGE"
