from __future__ import annotations

import json

import httpx
import pytest

from app.jev.models import digest_json
from app.jev.typesafe_canary_v2 import (
    CANARY_V2_API_BUDGET_USD,
    MAX_SYSTEM_ONE_ATTEMPTS,
    MAX_TOTAL_API_ATTEMPTS,
    PREVIEW_ALIAS,
    STABLE_ALIAS,
    classify_model_channel,
    run_real_canary_v2,
    select_canary_v2_model,
    select_threshold_from_selection,
    synthetic_canary_v2_fixtures,
    threshold_candidate_grid,
    validate_canary_v2_contract,
)
from app.jev.typesafe_questions_v2 import JEV_TYPESAFE_QUESTION_IDS_V2


def test_v2_contract_has_exact_partitions_and_preflight() -> None:
    artifact = validate_canary_v2_contract()
    fixtures = artifact["spec"]["fixtures"]
    assert len(fixtures) == 24
    assert sum(item["partition"] == "selection" for item in fixtures) == 12
    assert sum(item["partition"] == "validation" for item in fixtures) == 12
    assert sum(item["hard_expectation"] for item in fixtures) == 22
    assert len(threshold_candidate_grid()) == 27
    assert artifact["spec"]["systemone_attempts_max"] == 72
    assert artifact["spec"]["total_api_attempts_max"] == 73
    assert artifact["spec"]["real_stock_data_allowed"] is False
    assert artifact["spec"]["actual_trial_activation_allowed"] is False


def test_v2_model_channel_does_not_treat_preview_as_versioned() -> None:
    preview = {
        "name": "jev-preview",
        "description": "preview version",
        "release_date": "2026-10-06",
    }
    latest = {
        "name": "jev-latest",
        "description": "stable rolling alias",
        "release_date": "2026-10-06",
    }
    version_like = {
        "name": "jev-1.13.0",
        "description": "version-looking name without immutable guarantee",
        "release_date": "2026-10-06",
    }
    assert classify_model_channel(preview) == PREVIEW_ALIAS
    assert classify_model_channel(latest) == STABLE_ALIAS
    assert classify_model_channel(version_like) == "UNKNOWN"
    selected = select_canary_v2_model([preview, latest, version_like])
    assert selected["name"] == "jev-latest"
    assert selected["request_channel_class"] == STABLE_ALIAS
    with pytest.raises(Exception):
        select_canary_v2_model([preview, latest], override="jev-preview")


def _gold_probability_map() -> dict[str, dict[str, float]]:
    mapping = {}
    for fixture in synthetic_canary_v2_fixtures():
        values = {}
        for question_id, expected in fixture["expected_propositions"].items():
            values[question_id] = 0.95 if expected is True else 0.05
        mapping[fixture["state_hash"]] = values
    return mapping


@pytest.mark.asyncio
async def test_full_v2_mock_canary_passes_with_73_attempt_cap(monkeypatch) -> None:
    sentinel = "TYPESAFE_TEST_KEY_NOT_A_REAL_SECRET"
    monkeypatch.setenv("JEV_API_KEY", sentinel)
    probabilities = _gold_probability_map()
    counts = {"models": 0, "systemone": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == f"Bearer {sentinel}"
        if request.method == "GET":
            counts["models"] += 1
            return httpx.Response(
                200,
                json={
                    "models": [
                        {
                            "name": "jev-preview",
                            "description": "preview version",
                            "release_date": "2026-10-06T00:00:01Z",
                        },
                        {
                            "name": "jev-latest",
                            "description": "stable rolling alias",
                            "release_date": "2026-10-06T00:00:00Z",
                        },
                    ]
                },
            )

        counts["systemone"] += 1
        body = json.loads(request.content.decode("utf-8"))
        assert body["model"] == "jev-latest"
        assert set(body["questions"]) == set(JEV_TYPESAFE_QUESTION_IDS_V2)
        state_hash = digest_json(body["state"])
        values = probabilities[state_hash]
        return httpx.Response(
            200,
            json={
                "model": "jev-1.13.0",
                "answers": {
                    question_id: {"type": "noul", "noul": values[question_id]}
                    for question_id in JEV_TYPESAFE_QUESTION_IDS_V2
                },
                "usage": {"input_tokens": 100, "output_tokens": 3},
            },
        )

    report = await run_real_canary_v2(
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
    assert report["model_binding"]["selected_request_model"] == "jev-latest"
    assert report["model_binding"]["request_channel_class"] == STABLE_ALIAS
    assert report["model_binding"]["observed_response_model"] == "jev-1.13.0"
    assert report["selected_threshold"] == {
        "threshold_strategy": 0.8,
        "threshold_entry": 0.8,
        "threshold_evidence": 0.9,
    }
    assert report["budget"]["reserved_exposure_usd"] == pytest.approx(0.072)
    assert report["budget"]["reserved_exposure_usd"] <= CANARY_V2_API_BUDGET_USD
    assert report["real_stock_data_sent"] is False
    assert report["actual_trial_activation"] is False
    assert report["final_threshold_frozen"] is False
    assert sentinel not in json.dumps(report, ensure_ascii=False)


@pytest.mark.asyncio
async def test_selection_failure_never_calls_validation(monkeypatch) -> None:
    sentinel = "TYPESAFE_TEST_KEY_NOT_A_REAL_SECRET"
    monkeypatch.setenv("JEV_API_KEY", sentinel)
    calls = {"systemone": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(
                200,
                json={
                    "models": [
                        {
                            "name": "jev-latest",
                            "description": "stable rolling alias",
                            "release_date": "2026-10-06",
                        }
                    ]
                },
            )
        calls["systemone"] += 1
        return httpx.Response(
            200,
            json={
                "model": "jev-1.13.0",
                "answers": {
                    question_id: {"type": "noul", "noul": 0.05}
                    for question_id in JEV_TYPESAFE_QUESTION_IDS_V2
                },
                "usage": {"input_tokens": 10, "output_tokens": 3},
            },
        )

    report = await run_real_canary_v2(
        per_call_reservation_usd=0.001,
        transport=httpx.MockTransport(handler),
    )
    assert report["status"] == "FAIL"
    assert "CANARY_V2_NO_ELIGIBLE_THRESHOLD" in report["errors"]
    assert calls["systemone"] == 36
    assert report["records"]["validation"] == []


@pytest.mark.asyncio
async def test_failed_provider_call_is_counted_as_attempt(monkeypatch) -> None:
    sentinel = "TYPESAFE_TEST_KEY_NOT_A_REAL_SECRET"
    monkeypatch.setenv("JEV_API_KEY", sentinel)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(
                200,
                json={
                    "models": [
                        {
                            "name": "jev-latest",
                            "description": "stable rolling alias",
                            "release_date": "2026-10-06",
                        }
                    ]
                },
            )
        return httpx.Response(500, json={"error": "fixture"})

    report = await run_real_canary_v2(
        per_call_reservation_usd=0.001,
        transport=httpx.MockTransport(handler),
    )
    assert report["status"] == "FAIL"
    assert report["api_attempts"]["systemone"] == 1
    assert report["systemone_counts"]["attempted"] == 1
    assert report["systemone_counts"]["completed"] == 0
    assert report["systemone_counts"]["valid"] == 0
    assert report["systemone_counts"]["failed"] == 1


@pytest.mark.asyncio
async def test_budget_preflight_blocks_before_network(monkeypatch) -> None:
    sentinel = "TYPESAFE_TEST_KEY_NOT_A_REAL_SECRET"
    monkeypatch.setenv("JEV_API_KEY", sentinel)
    transport = httpx.MockTransport(
        lambda request: (_ for _ in ()).throw(AssertionError("network called"))
    )
    report = await run_real_canary_v2(
        per_call_reservation_usd=0.01,
        transport=transport,
    )
    assert report["status"] == "BLOCKED"
    assert report["api_attempts"]["total"] == 0
    assert "BLOCKED_COST_RESERVATION_EXCEEDS_BUDGET" in report["errors"]


def test_offline_selection_locks_only_pre_registered_grid() -> None:
    artifact = validate_canary_v2_contract()
    records = []
    for fixture in artifact["spec"]["fixtures"]:
        if fixture["partition"] != "selection":
            continue
        values = {
            question_id: (0.95 if expected is True else 0.05)
            for question_id, expected in fixture["expected_propositions"].items()
        }
        for repetition in range(1, 4):
            records.append(
                {
                    "fixture_id": fixture["fixture_id"],
                    "repetition": repetition,
                    "probabilities": values,
                }
            )
    result = select_threshold_from_selection(records, artifact)
    assert result["selected"] is not None
    selected = result["selected"]
    assert {
        selected["threshold_strategy"],
        selected["threshold_entry"],
    } <= {0.50, 0.65, 0.80}
    assert selected["threshold_evidence"] in {0.60, 0.75, 0.90}
