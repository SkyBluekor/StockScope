from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from app.jev.models import digest_json
from app.jev.typesafe_canary_v3 import (
    CANARY_V3_API_BUDGET_USD,
    CANARY_V3_PROTOCOL_PATH,
    MAX_SYSTEM_ONE_ATTEMPTS,
    MAX_TOTAL_API_ATTEMPTS,
    STABLE_ALIAS,
    TypeSafeCanaryV3Error,
    evaluate_locked_threshold,
    load_frozen_canary_v3_protocol,
    run_real_canary_v3,
    select_threshold_from_selection,
    synthetic_canary_v3_fixtures,
    threshold_candidate_grid,
    validate_canary_v3_contract,
)
from app.jev.typesafe_questions_v3 import JEV_TYPESAFE_QUESTION_IDS_V3


def _gold_probability_by_state_hash() -> dict[str, float]:
    mapping: dict[str, float] = {}
    for fixture in synthetic_canary_v3_fixtures():
        if fixture["route"] != "PROVIDER_CALL":
            continue
        gold = fixture["expected_q1_gold"]
        probability = 0.95 if gold is True else 0.05 if gold is False else 0.60
        state_hash = str(fixture["projected_state_hash"])
        existing = mapping.get(state_hash)
        if existing is not None:
            assert existing == probability
        mapping[state_hash] = probability
    return mapping


def _models_response() -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "models": [
                {
                    "name": "jev-preview",
                    "description": "preview version",
                    "release_date": "2026-10-07T00:00:01Z",
                },
                {
                    "name": "jev-latest",
                    "description": "stable rolling alias",
                    "release_date": "2026-10-07T00:00:00Z",
                },
            ]
        },
    )


def test_v3_protocol_has_exact_40_context_architecture() -> None:
    artifact = validate_canary_v3_contract()
    fixtures = artifact["spec"]["fixtures"]
    assert len(fixtures) == 40
    assert len({item["fixture_id"] for item in fixtures}) == 40
    for partition in ("selection", "validation"):
        rows = [item for item in fixtures if item["partition"] == partition]
        assert len(rows) == 20
        assert sum(item["route"] == "PROVIDER_CALL" for item in rows) == 12
        assert sum(item["route"] == "LOCAL_ONLY" for item in rows) == 8
        hard = [
            item for item in rows
            if item["route"] == "PROVIDER_CALL" and item["hard_expectation"]
        ]
        soft = [
            item for item in rows
            if item["route"] == "PROVIDER_CALL" and not item["hard_expectation"]
        ]
        assert len(hard) == 10
        assert len(soft) == 2
        assert sum(item["expected_q1_gold"] is False for item in hard) == 6
        assert sum(item["expected_q1_gold"] is True for item in hard) == 4

    assert threshold_candidate_grid() == [0.5, 0.7, 0.9]
    assert artifact["spec"]["selected_threshold"] is None
    assert artifact["spec"]["final_threshold_frozen"] is False
    assert artifact["spec"]["systemone_attempts_max"] == 72
    assert artifact["spec"]["total_api_attempts_max"] == 73


def test_v3_callable_wire_is_minimized_and_gold_free() -> None:
    artifact = validate_canary_v3_contract()
    forbidden = tuple(artifact["spec"]["forbidden_wire_tokens"])
    for fixture in artifact["spec"]["fixtures"]:
        if fixture["route"] != "PROVIDER_CALL":
            continue
        state = fixture["projected_state"]
        assert set(state) == {
            "strategy_intent",
            "term_definitions",
            "passed_condition_meanings",
        }
        encoded = json.dumps(state, ensure_ascii=False, sort_keys=True).lower()
        wire_keys: set[str] = set()

        def collect_keys(value) -> None:
            if isinstance(value, dict):
                for key, child in value.items():
                    wire_keys.add(str(key).lower())
                    collect_keys(child)
            elif isinstance(value, list):
                for child in value:
                    collect_keys(child)

        collect_keys(state)
        assert all(
            token.lower() not in wire_keys
            and (len(token) <= 3 or token.lower() not in encoded)
            for token in forbidden
        )
        assert fixture["projected_state_hash"] == digest_json(state)


def test_v3_isolation_pairs_have_identical_q1_wire_and_different_local_result() -> None:
    fixtures = synthetic_canary_v3_fixtures()
    for family in ("S-A", "S-B", "V-A", "V-B"):
        rows = [item for item in fixtures if item["isolation_family_id"] == family]
        assert len(rows) == 2
        assert rows[0]["projected_state_hash"] == rows[1]["projected_state_hash"]
        assert rows[0]["projected_state"] == rows[1]["projected_state"]
        assert rows[0]["expected_local_entry_result"] != rows[1]["expected_local_entry_result"]


def test_v3_local_only_contexts_are_no_call_with_expected_local_semantics() -> None:
    fixtures = synthetic_canary_v3_fixtures()
    local = [item for item in fixtures if item["route"] == "LOCAL_ONLY"]
    assert len(local) == 16
    assert all(item["projected_state"] is None for item in local)
    assert all(item["expected_preflight_error"] for item in local)

    conflict_reasons = {
        item["expected_q2_reason"]
        for item in local
        if item["expected_local_entry_result"]["status"] == "CONFLICT"
    }
    assert conflict_reasons == {
        "CONFLICT_CONFIRMATION_AS_EXECUTION",
        "CONFLICT_EXECUTION_AS_CONFIRMATION",
    }
    assert any(item["expected_q2_status"] == "MISSING" for item in local)
    assert any(item["expected_q2_status"] == "AMBIGUOUS" for item in local)


def test_v3_protocol_file_is_exactly_frozen() -> None:
    artifact = validate_canary_v3_contract()
    loaded = load_frozen_canary_v3_protocol()
    assert CANARY_V3_PROTOCOL_PATH.is_file()
    assert loaded == artifact
    assert loaded["protocol_hash"] == artifact["protocol_hash"]


def test_v3_protocol_drift_is_rejected(tmp_path: Path) -> None:
    artifact = validate_canary_v3_contract()
    path = tmp_path / "JEV_TYPESAFE_CANARY_PROTOCOL_V3.json"
    path.write_text(
        json.dumps(artifact, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    assert load_frozen_canary_v3_protocol(path) == artifact
    changed = json.loads(path.read_text(encoding="utf-8"))
    changed["spec"]["threshold_candidates"].append(0.8)
    path.write_text(
        json.dumps(changed, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(TypeSafeCanaryV3Error, match="CANARY_V3_PROTOCOL_DRIFT"):
        load_frozen_canary_v3_protocol(path)


def test_v3_offline_selection_uses_only_frozen_grid_and_tie_break() -> None:
    artifact = validate_canary_v3_contract()
    records = []
    for fixture in artifact["spec"]["fixtures"]:
        if fixture["partition"] != "selection" or fixture["route"] != "PROVIDER_CALL":
            continue
        gold = fixture["expected_q1_gold"]
        probability = 0.95 if gold is True else 0.05 if gold is False else 0.60
        for repetition in range(1, 4):
            records.append(
                {
                    "fixture_id": fixture["fixture_id"],
                    "repetition": repetition,
                    "probability": probability,
                }
            )
    result = select_threshold_from_selection(records, artifact)
    assert result["selected"] is not None
    assert result["selected"]["threshold_strategy"] == 0.9
    assert {item["threshold_strategy"] for item in result["candidates"]} == {
        0.5,
        0.7,
        0.9,
    }
    validation = evaluate_locked_threshold(records, artifact, result["selected"])
    assert validation["eligible"] is True


@pytest.mark.asyncio
async def test_full_v3_mock_canary_passes_with_73_attempt_cap(monkeypatch) -> None:
    sentinel = "TYPESAFE_TEST_KEY_NOT_A_REAL_SECRET"
    monkeypatch.setenv("JEV_API_KEY", sentinel)
    probabilities = _gold_probability_by_state_hash()
    counts = {"models": 0, "systemone": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == f"Bearer {sentinel}"
        if request.method == "GET":
            counts["models"] += 1
            return _models_response()

        counts["systemone"] += 1
        body = json.loads(request.content.decode("utf-8"))
        assert body["model"] == "jev-latest"
        assert set(body["questions"]) == set(JEV_TYPESAFE_QUESTION_IDS_V3)
        assert len(body["questions"]) == 1
        probability = probabilities[digest_json(body["state"])]
        return httpx.Response(
            200,
            json={
                "model": "jev-1.13.0",
                "answers": {
                    "strategy_context_conflict": {
                        "type": "noul",
                        "noul": probability,
                    }
                },
                "usage": {"input_tokens": 100, "output_tokens": 1},
            },
        )

    report = await run_real_canary_v3(
        per_call_reservation_usd=0.001,
        transport=httpx.MockTransport(handler),
    )
    assert report["status"] == "PASS"
    assert counts == {"models": 1, "systemone": 72}
    assert report["api_attempts"]["total"] == MAX_TOTAL_API_ATTEMPTS
    assert report["systemone_counts"] == {
        "planned": 72,
        "attempted": 72,
        "completed": 72,
        "valid": 72,
        "failed": 0,
    }
    assert report["selected_threshold"] == {"threshold_strategy": 0.9}
    assert report["model_binding"]["selected_request_model"] == "jev-latest"
    assert report["model_binding"]["request_channel_class"] == STABLE_ALIAS
    assert report["model_binding"]["observed_response_model"] == "jev-1.13.0"
    assert report["budget"]["reserved_exposure_usd"] == pytest.approx(0.072)
    assert report["budget"]["reserved_exposure_usd"] <= CANARY_V3_API_BUDGET_USD
    assert report["real_stock_data_sent"] is False
    assert report["actual_trial_activation"] is False
    assert report["final_threshold_frozen"] is False
    assert sentinel not in json.dumps(report, ensure_ascii=False)


@pytest.mark.asyncio
async def test_v3_selection_failure_never_calls_validation(monkeypatch) -> None:
    sentinel = "TYPESAFE_TEST_KEY_NOT_A_REAL_SECRET"
    monkeypatch.setenv("JEV_API_KEY", sentinel)
    calls = {"systemone": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return _models_response()
        calls["systemone"] += 1
        return httpx.Response(
            200,
            json={
                "model": "jev-1.13.0",
                "answers": {
                    "strategy_context_conflict": {"type": "noul", "noul": 0.05}
                },
                "usage": {"input_tokens": 10, "output_tokens": 1},
            },
        )

    report = await run_real_canary_v3(
        per_call_reservation_usd=0.001,
        transport=httpx.MockTransport(handler),
    )
    assert report["status"] == "FAIL"
    assert "CANARY_V3_NO_ELIGIBLE_THRESHOLD" in report["errors"]
    assert calls["systemone"] == 36
    assert report["records"]["validation"] == []
    assert report["selected_threshold"] is None


@pytest.mark.asyncio
async def test_v3_failed_provider_call_counts_attempt_and_keeps_reservation(monkeypatch) -> None:
    sentinel = "TYPESAFE_TEST_KEY_NOT_A_REAL_SECRET"
    monkeypatch.setenv("JEV_API_KEY", sentinel)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return _models_response()
        return httpx.Response(500, json={"error": "fixture"})

    report = await run_real_canary_v3(
        per_call_reservation_usd=0.001,
        transport=httpx.MockTransport(handler),
    )
    assert report["status"] == "FAIL"
    assert report["api_attempts"]["systemone"] == 1
    assert report["systemone_counts"]["attempted"] == 1
    assert report["systemone_counts"]["completed"] == 0
    assert report["systemone_counts"]["failed"] == 1
    assert report["budget"]["reserved_exposure_usd"] == pytest.approx(0.001)


@pytest.mark.asyncio
async def test_v3_model_identity_change_fails(monkeypatch) -> None:
    sentinel = "TYPESAFE_TEST_KEY_NOT_A_REAL_SECRET"
    monkeypatch.setenv("JEV_API_KEY", sentinel)
    calls = {"systemone": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return _models_response()
        calls["systemone"] += 1
        body = json.loads(request.content.decode("utf-8"))
        probability = _gold_probability_by_state_hash()[digest_json(body["state"])]
        returned = "jev-1.13.0" if calls["systemone"] == 1 else "jev-1.14.0"
        return httpx.Response(
            200,
            json={
                "model": returned,
                "answers": {
                    "strategy_context_conflict": {
                        "type": "noul",
                        "noul": probability,
                    }
                },
                "usage": {"input_tokens": 10, "output_tokens": 1},
            },
        )

    report = await run_real_canary_v3(
        per_call_reservation_usd=0.001,
        transport=httpx.MockTransport(handler),
    )
    assert report["status"] == "FAIL"
    assert "CANARY_V3_MODEL_IDENTITY_CHANGED" in report["errors"]
    assert calls["systemone"] == 2


@pytest.mark.asyncio
async def test_v3_budget_preflight_blocks_before_network(monkeypatch) -> None:
    sentinel = "TYPESAFE_TEST_KEY_NOT_A_REAL_SECRET"
    monkeypatch.setenv("JEV_API_KEY", sentinel)
    transport = httpx.MockTransport(
        lambda request: (_ for _ in ()).throw(AssertionError("network called"))
    )
    report = await run_real_canary_v3(
        per_call_reservation_usd=0.01,
        transport=transport,
    )
    assert report["status"] == "BLOCKED"
    assert report["api_attempts"]["total"] == 0
    assert "BLOCKED_COST_RESERVATION_EXCEEDS_BUDGET" in report["errors"]