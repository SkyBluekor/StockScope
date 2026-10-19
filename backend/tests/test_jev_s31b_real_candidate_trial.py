"""S31-B: actual frozen Scanner evidence remains local; provider review blocked."""
from __future__ import annotations

from copy import deepcopy
import json

import pytest

from app.jev.research_scanner_s24 import SOURCE, ResearchCaptureError, digest
from app.jev.s31_real_candidate_trial import inspect_frozen_candidates
from tools.data import jev_s31_candidate_trial as cli


def frozen_real_like_receipt():
    identity = {
        "strategy_key": "pullback",
        "strategy_version_id": "current-strategy-id",
        "definition_hash": "immutable-strategy-hash",
    }
    data = []
    for i, name in enumerate(["삼화콘덴서", "DB손해보험", "OCI홀딩스", "하이스틸", "후성"]):
        data.append({
            "code": str(1820 + i).zfill(6), "name": name, "market": "KOSPI",
            "data_date": "2026-10-14", "action": "ENTRY_CANDIDATE",
            "strategy": identity["strategy_key"],
            "strategy_version_id": identity["strategy_version_id"],
            "strategy_definition_hash": identity["definition_hash"],
            "risk": {"status": "READY", "warning": False, "warnings": []},
            "conditions": {"passed": 5, "total": 5, "missing": 0},
            "priority": {
                "rank": i + 1, "tie_group": 1, "tie_size": 5,
                "strict_rank": False, "tier": "READY",
                "tie_focus": i == 0, "tie_focus_order": 0 if i == 0 else 1,
                "tie_breaker": "STRUCTURAL_TARGET_NEAREST_PROMOTE",
                "structural_target_distance_pct": 4.0 + i,
                "historical_status": "DATA_UNAVAILABLE",
            },
            "entry_risk_guide": {"risk": {
                "entry_reference_price": 100., "invalidation_price": 95.,
                "target1_price": 107.5, "structural_target1_price": 104. + i,
                "rr1": 1.5,
            }},
        })
    payload = {
        "version": "Q7_S24_ISOLATED_RESEARCH_SCANNER_V1",
        "authority": SOURCE,
        "execution_mode": "POSTHOC_TECHNICAL_SMOKE_ONLY",
        "evaluation_use": "TECHNICAL_SMOKE_ONLY_NOT_Q7_COHORT",
        "q7_approval_eligible": False,
        "production_policy_activation_allowed": False,
        "trusted_precommit_timestamp_proven": False,
        "independent_capture_timestamp_proven": False,
        "market_publication_timestamp_proven": False,
        "jev_model_calls": 0,
        "source_date": "2026-10-14", "market_scope": "KOSPI",
        "original_strategy_rows": [identity],
        "original_scanner_candidates": data,
        "candidate_count": 5, "entry_candidates": 5,
    }
    return seal(payload)


def seal(payload):
    payload["payload_hash"] = digest({
        k: v for k, v in payload.items() if k != "payload_hash"
    })
    return payload


def test_five_real_like_candidates_local_baseline_comparison_preserves_source():
    original = frozen_real_like_receipt()
    original_copy = deepcopy(original)
    report = inspect_frozen_candidates(original)
    assert original == original_copy
    assert report["status"] == "LOCAL_REAL_CANDIDATE_COMPARISON_ONLY"
    assert report["original_entry_count"] == report["inspected_entry_count"] == 5
    assert report["original_payload_hash"] == original["payload_hash"]
    assert report["retrospective_not_prospective"] is True
    assert report["external_requests"] == report["jev_model_calls"] == 0
    assert report["orders"] == report["research_db_writes"] == 0
    assert all(x["jev"]["decision"] is None for x in report["candidates"])
    assert all(x["jev"]["probabilities"] is None for x in report["candidates"])
    assert all(x["baseline"]["action"] == "ENTRY_CANDIDATE" for x in report["candidates"])
    assert all(x["local_evidence"]["target1_r_multiple"] == 1.5 for x in report["candidates"])
    assert all("HISTORICAL_EVIDENCE_UNAVAILABLE" in x["local_evidence"]["alerts"] for x in report["candidates"])


def test_review_never_calls_provider_even_with_model_and_key(monkeypatch):
    monkeypatch.setenv("JEV_API_KEY", "NOT_TO_BE_READ")
    report = inspect_frozen_candidates(
        frozen_real_like_receipt(), review=True, model="jev-latest", limit=1,
    )
    assert report["status"] == "REAL_MARKET_JEV_PROVIDER_BLOCKED"
    assert report["inspected_entry_count"] == 1
    assert report["source_rights"]["derived_typesafe_ai"] == "UNVERIFIED"
    assert report["source_rights"]["typesafe_terms"] == "UNVERIFIED"
    assert report["real_stock_provider_eligible"] is False
    assert report["synthetic_s6_success_does_not_authorize_real_market_data"] is True
    assert report["external_requests"] == report["jev_model_calls"] == 0
    assert report["candidates"][0]["jev"]["status"] == "NOT_RUN_PROVIDER_HOLD"


@pytest.mark.parametrize("limit", [0, 6, True, -1, 1.0])
def test_invalid_limits_are_blocked(limit):
    with pytest.raises(ResearchCaptureError, match="S31B_LIMIT_MUST_BE_1_TO_5"):
        inspect_frozen_candidates(frozen_real_like_receipt(), limit=limit)


def test_review_requires_named_model_and_refuses_preview():
    for model in (None, "jev-preview", "fake-jev"):
        with pytest.raises(ResearchCaptureError, match="S31B_PINNED_MODEL_REQUIRED"):
            inspect_frozen_candidates(
                frozen_real_like_receipt(), review=True, model=model,
            )


def test_source_hash_tamper_fails_closed():
    payload = frozen_real_like_receipt()
    payload["original_scanner_candidates"][0]["risk"]["warning"] = True
    with pytest.raises(ResearchCaptureError, match="S28_RECEIPT_PAYLOAD_HASH_MISMATCH"):
        inspect_frozen_candidates(payload)


def test_resealed_strategy_identity_tamper_fails_closed():
    payload = frozen_real_like_receipt()
    payload["original_scanner_candidates"][0]["strategy_version_id"] = "fabricated"
    with pytest.raises(ResearchCaptureError, match="S28_SOURCE_STRATEGY_IDENTITY_MISMATCH"):
        inspect_frozen_candidates(seal(payload))


def test_contradictory_risk_arithmetic_is_not_sent_or_silently_trusted():
    payload = frozen_real_like_receipt()
    payload["original_scanner_candidates"][0]["entry_risk_guide"]["risk"]["rr1"] = 20
    with pytest.raises(ResearchCaptureError, match="S31B_SOURCE_EVIDENCE_NEEDS_REVIEW"):
        inspect_frozen_candidates(seal(payload), review=True, model="jev-latest")


def test_missing_price_or_conditions_are_not_invented():
    payload = frozen_real_like_receipt()
    x = payload["original_scanner_candidates"][0]
    x["conditions"] = {"passed": 5}
    x["entry_risk_guide"]["risk"].pop("invalidation_price")
    report = inspect_frozen_candidates(seal(payload), limit=1)
    c = report["candidates"][0]
    assert c["baseline"]["conditions_passed"] is None
    assert "BASELINE_CONDITION_TOTAL_UNVERIFIED" in c["local_evidence"]["alerts"]
    assert c["local_evidence"]["target1_r_multiple"] is None
    assert "BASELINE_REFERENCE_PRICE_RECHECK_REQUIRED" in c["local_evidence"]["alerts"]
    assert c["jev"]["decision"] is None


def test_cli_inspect_json_is_read_only_and_review_exits_hold(tmp_path, capsys):
    path = tmp_path / "scanner_research_capture.json"
    path.write_text(json.dumps(frozen_real_like_receipt(), ensure_ascii=False), encoding="utf-8")
    saved = path.read_bytes()
    assert cli.main(["inspect", "--receipt", str(path), "--limit", "5", "--json"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "LOCAL_REAL_CANDIDATE_COMPARISON_ONLY"
    assert report["inspected_entry_count"] == 5
    assert path.read_bytes() == saved
    assert cli.main(["review", "--receipt", str(path), "--limit", "1",
                     "--model", "jev-latest"]) == 2
    output = capsys.readouterr().out
    assert "REAL_MARKET_JEV_PROVIDER_BLOCKED" in output
    assert "JEV: 미실행" in output
    assert path.read_bytes() == saved
    assert not list(tmp_path.glob("*.sqlite*"))


def test_cli_rejects_missing_file_or_modified_receipt_without_writes(tmp_path, capsys):
    missing = tmp_path / "missing.json"
    assert cli.main(["inspect", "--receipt", str(missing)]) == 2
    output = json.loads(capsys.readouterr().out)
    assert output["status"] == "HOLD_SOURCE_INVALID"
    assert output["external_requests"] == output["jev_model_calls"] == 0

    payload = frozen_real_like_receipt()
    payload["original_scanner_candidates"][0]["code"] = "000000"
    path = tmp_path / "modified.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    saved = path.read_bytes()
    assert cli.main(["review", "--receipt", str(path), "--model", "jev-latest"]) == 2
    report = json.loads(capsys.readouterr().out)
    assert report["reason_code"] == "S28_RECEIPT_PAYLOAD_HASH_MISMATCH"
    assert path.read_bytes() == saved


def test_provider_rights_changing_does_not_auto_authorize(monkeypatch):
    from app.jev import s31_real_candidate_trial as module
    monkeypatch.setitem(module.RIGHTS_ACTIONS,
                        "KRX_OPEN_API_DERIVED_TYPESAFE_AI", "VERIFIED_GRANTED")
    with pytest.raises(ResearchCaptureError, match="S31B_RIGHTS_AUTHORITY_CHANGED_MANUAL_REVIEW"):
        inspect_frozen_candidates(frozen_real_like_receipt(), review=True, model="jev-latest")
