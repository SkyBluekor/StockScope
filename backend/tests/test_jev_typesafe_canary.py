from __future__ import annotations

import json

import httpx
import pytest

from app.core.config import PROJECT_ROOT

from app.jev.typesafe_canary import (
    CANARY_PROTOCOL_ID,
    MAX_SYSTEM_ONE_CALLS,
    MAX_TOTAL_API_CALLS,
    build_canary_protocol_artifact,
    run_real_canary,
    select_canary_model,
    validate_canary_contract,
)
from app.jev.typesafe_provider import discover_typesafe_models


def test_canary_contract_is_frozen_synthetic_only() -> None:
    artifact = validate_canary_contract()
    assert artifact["protocol_id"] == CANARY_PROTOCOL_ID
    assert artifact["status"] == "FROZEN_BEFORE_REAL_CALLS"
    assert len(artifact["spec"]["fixtures"]) == 12
    assert (
        len(artifact["spec"]["fixtures"])
        * artifact["spec"]["repetitions"]
        == MAX_SYSTEM_ONE_CALLS
    )
    assert artifact["spec"]["real_stock_data_allowed"] is False
    assert artifact["spec"]["actual_trial_activation_allowed"] is False
    assert artifact["spec"]["total_api_calls_max"] == MAX_TOTAL_API_CALLS
    frozen = json.loads(
        (PROJECT_ROOT / "docs" / "contracts" / "JEV_TYPESAFE_CANARY_PROTOCOL_V1.json").read_text(encoding="utf-8")
    )
    assert frozen == artifact


def test_canary_prefers_versioned_model_over_latest_alias() -> None:
    selected = select_canary_model(
        [
            {
                "name": "jev-latest",
                "description": "alias",
                "release_date": "2026-10-06",
            },
            {
                "name": "jev-1.2.3",
                "description": "versioned",
                "release_date": "2026-10-05",
            },
        ]
    )
    assert selected["name"] == "jev-1.2.3"
    assert selected["alias_used"] is False


@pytest.mark.asyncio
async def test_model_discovery_uses_bearer_without_exposing_secret(
    monkeypatch,
) -> None:
    sentinel = "TYPESAFE_TEST_KEY_NOT_A_REAL_SECRET"
    monkeypatch.setenv("JEV_API_KEY", sentinel)
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["authorization"] = request.headers["Authorization"]
        assert request.method == "GET"
        return httpx.Response(
            200,
            json={
                "models": [
                    {
                        "name": "jev-latest",
                        "description": "General-purpose system one model.",
                        "release_date": "2026-09-15",
                    }
                ]
            },
        )

    models = await discover_typesafe_models(
        transport=httpx.MockTransport(handler),
    )
    assert models[0]["name"] == "jev-latest"
    assert captured["authorization"] == f"Bearer {sentinel}"


@pytest.mark.asyncio
async def test_full_canary_mock_passes_with_exact_hard_call_cap(
    monkeypatch,
) -> None:
    sentinel = "TYPESAFE_TEST_KEY_NOT_A_REAL_SECRET"
    monkeypatch.setenv("JEV_API_KEY", sentinel)
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
                            "name": "jev-latest",
                            "description": "rolling alias",
                            "release_date": "2026-10-06",
                        },
                        {
                            "name": "jev-1.2.3",
                            "description": "versioned model",
                            "release_date": "2026-10-05",
                        },
                    ]
                },
            )

        counts["systemone"] += 1
        body = json.loads(request.content.decode("utf-8"))
        assert set(body) == {"state", "questions", "model"}
        assert body["model"] == "jev-1.2.3"
        state = body["state"]
        description = state["strategy_context"]["strategy_description"]
        role = state["entry_context"]["price_rule"]["semantic_role"]

        q1 = 0.05
        q2 = 0.05
        q3 = 0.05
        if (
            "requires price to remain below" in description
            or "only accepts weak participation" in description
            or "requires price below its reference" in description
        ):
            q1 = 0.95
        if role == "STRATEGY_CONDITION_THRESHOLD":
            q2 = 0.95
        if role == "UNSPECIFIED":
            q3 = 0.95
        if role == "CONDITION_BAND_NEAR_EXECUTION":
            q2 = 0.50
        if "usually prefers continuation" in description:
            q1 = 0.50

        return httpx.Response(
            200,
            json={
                "model": "jev-1.2.3",
                "answers": {
                    "strategy_context_conflict": {
                        "type": "noul",
                        "noul": q1,
                    },
                    "entry_context_conflict": {
                        "type": "noul",
                        "noul": q2,
                    },
                    "review_evidence_insufficient": {
                        "type": "noul",
                        "noul": q3,
                    },
                },
                "usage": {
                    "input_tokens": 100,
                    "output_tokens": 3,
                },
            },
        )

    report = await run_real_canary(
        transport=httpx.MockTransport(handler),
    )
    assert report["status"] == "PASS"
    assert counts == {"models": 1, "systemone": 24}
    assert report["api_calls"]["total"] == 25
    assert report["api_calls"]["systemone"] == MAX_SYSTEM_ONE_CALLS
    assert report["model_binding"]["selected_request_model"] == "jev-1.2.3"
    assert report["model_binding"]["observed_response_model"] == "jev-1.2.3"
    assert report["threshold_analysis"]["selected"] == {
        "low": 0.15,
        "high": 0.85,
        "hard_checks": report["threshold_analysis"]["selected"]["hard_checks"],
        "hard_mismatches": 0,
        "hard_instability_count": 0,
        "eligible": True,
    }
    assert report["real_stock_data_sent"] is False
    assert report["actual_trial_activation"] is False
    assert sentinel not in json.dumps(report, ensure_ascii=False)
