from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import httpx
import pytest

from app.jev import (
    FakeJevProvider,
    JevCatalog,
    JevCatalogError,
    JevShadowService,
    JevTrialProtocolSpec,
    OpenAIResponsesJevProvider,
    build_comparison_report,
    configure_trial_protocol,
    load_trial_artifact,
    trial_readiness,
)
from app.api.jev_shadow import (
    jev_shadow_status,
    list_jev_shadow_reviews,
)
from app.main import app
from app.jev.prompt import (
    JEV_OUTPUT_SCHEMA_HASH,
    JEV_PROMPT_HASH,
    JEV_PROMPT_VERSION,
)
from app.prospective import ProspectiveCatalog
from app.prospective.models import ProspectiveCaptureRequest
from tools.data.migrate_jev_shadow_v1 import migrate_jev_shadow_store
from tools.data.migrate_prospective_vnp2s2 import migrate_prospective_store


def _simulation_db(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        conn.execute(
            "CREATE TABLE simulation_placeholder(id INTEGER PRIMARY KEY)"
        )
    migrate_prospective_store(path)
    migrate_jev_shadow_store(path)
    return path


def _capture(
    path: Path,
    *,
    action: str = "ENTRY_CANDIDATE",
) -> dict:
    catalog = ProspectiveCatalog(path)
    request = ProspectiveCaptureRequest(
        market_scope="ALL",
        requested_as_of="2026-10-06",
        candidate_limit=5,
        horizon_intent="LEGACY_UNSPECIFIED",
        horizon_policy_version="VN_P1_S2_HORIZON_CONTEXT_V1",
        selection_policy_id="POLICY-TEST",
        selection_policy_hash="policy-hash",
    )
    catalog.begin_capture(
        source_job_id="jev-capture",
        request=request,
    )
    return catalog.finalize_capture(
        source_job_id="jev-capture",
        request=request,
        result={
            "version": "0.21.3.9",
            "requested_as_of": "2026-10-06",
            "market_scope": "ALL",
            "input_fingerprint": "fp-jev",
            "partial_data": False,
            "summary": {
                "candidate_count": 1,
                "shown_count": 1,
            },
            "diagnostics": {
                "reproducibility_audit": {
                    "production_baseline": "BASELINE-TEST",
                }
            },
            "candidates": [
                {
                    "market": "KOSPI",
                    "code": "005930",
                    "name": "삼성전자",
                    "rank": 1,
                    "strategy": "pullback",
                    "strategy_version_id": "STRAT-V1",
                    "strategy_definition_hash": "strategy-hash",
                    "decision_status": "READY",
                    "candidate_state": "READY",
                    "action": action,
                    "current_price": 100.0,
                    "conditions": {
                        "passed": 5,
                        "total": 5,
                        "missing": 0,
                        "top_missing": [],
                    },
                    "risk": {
                        "status": "READY",
                        "warning": False,
                        "warnings": [],
                    },
                    "entry_risk_guide": {
                        "current_price": 100.0,
                        "price_rule": {
                            "kind": "RANGE",
                            "status": "PASS",
                            "range_low": 98.0,
                            "range_high": 102.0,
                            "reference_price": 100.0,
                            "gap_pct": 0.0,
                        },
                        "risk": {
                            "available": True,
                            "status": "READY",
                            "reference_only": False,
                            "entry_reference_price": 100.0,
                            "invalidation_price": 95.0,
                            "stop_zone_low": 94.0,
                            "stop_zone_high": 96.0,
                            "target1_price": 110.0,
                            "target2_price": 120.0,
                            "risk_pct": 5.0,
                            "reward1_pct": 10.0,
                            "reward2_pct": 20.0,
                            "rr1": 2.0,
                            "rr2": 4.0,
                            "structure_rating": "GOOD",
                            "needs_recheck": False,
                        },
                        "action": {"status": action},
                        "historical_verification": {
                            "verified": True,
                            "status": "GOOD",
                            "future_return": 999.0,
                        },
                    },
                    "historical_fit": {
                        "status": "GOOD",
                        "trades": 999,
                        "win_rate": 99.0,
                    },
                    "news": {"headline": "MUST_NOT_LEAK"},
                    "event_evidence": {
                        "event": "MUST_NOT_LEAK"
                    },
                    "macro": {"state": "MUST_NOT_LEAK"},
                    "holdings": {"quantity": 123},
                    "future_outcome": {
                        "return_20d": 999.0
                    },
                }
            ],
            "more_candidates": [],
        },
    )


def _frozen_protocol(
    catalog: JevCatalog,
    *,
    fake_mode: str = "PASS_THROUGH",
) -> dict:
    protocol = catalog.create_protocol(
        client_request_id=f"protocol-{fake_mode}",
        spec=JevTrialProtocolSpec(
            name="fake shadow",
            provider_id="FAKE",
            model_id="FAKE-MODEL",
            model_revision="FAKE-REV-1",
            prompt_version="PROMPT-V1",
            prompt_hash="prompt-hash",
            generation_settings={"fake_mode": fake_mode},
            recruitment_start="2026-10-01",
            recruitment_end="2026-10-31",
            duplicate_rule="FIRST_VALID_FAKE",
            min_mature_candidates=10,
            min_disagreements=2,
            max_error_rate=0.10,
            max_abstain_rate=0.25,
            max_review_rate=0.50,
            budget_limit_usd=1.0,
            model_revision_policy="FAKE_PINNED",
        ),
    )
    assert protocol["status"] == "FROZEN"
    catalog.set_activation(
        protocol["id"],
        enabled=True,
        allow_network=False,
    )
    return protocol


@pytest.mark.asyncio
async def test_quant_only_projection_and_baseline_immutability(
    tmp_path: Path,
) -> None:
    db = _simulation_db(tmp_path / "simulation.db")
    capture = _capture(db)
    catalog = JevCatalog(db)
    _frozen_protocol(catalog)

    with sqlite3.connect(db) as conn:
        before = conn.execute(
            """
            SELECT snapshot_json,snapshot_hash
            FROM prospective_recommendation_sample
            WHERE capture_run_id=? AND sample_index=0
            """,
            (capture["id"],),
        ).fetchone()

    service = JevShadowService(
        db,
        provider_override=FakeJevProvider(
            mode="PASS_THROUGH"
        ),
    )
    reviews = await service.process_capture(capture["id"])
    assert len(reviews) == 1
    review = reviews[0]
    assert review["status"] == "VALID"
    assert review["decision"] == "PASS_THROUGH"

    encoded = json.dumps(
        review["input"],
        ensure_ascii=False,
    ).lower()
    decision_encoded = json.dumps(
        review["input"]["baseline_decision"],
        ensure_ascii=False,
    ).lower()
    evidence_encoded = json.dumps(
        review["input"]["evidence_items"],
        ensure_ascii=False,
    ).lower()
    assert "must_not_leak" not in encoded
    assert "future_outcome" not in review["input"]
    for forbidden in (
        "historical_fit",
        "historical_verification",
        "\"news\"",
        "event_evidence",
        "\"macro\"",
        "\"holdings\"",
        "future_outcome",
    ):
        assert forbidden not in decision_encoded
        assert forbidden not in evidence_encoded

    with sqlite3.connect(db) as conn:
        after = conn.execute(
            """
            SELECT snapshot_json,snapshot_hash
            FROM prospective_recommendation_sample
            WHERE capture_run_id=? AND sample_index=0
            """,
            (capture["id"],),
        ).fetchone()
    assert before == after


@pytest.mark.asyncio
async def test_output_validation_error_falls_back(
    tmp_path: Path,
) -> None:
    db = _simulation_db(tmp_path / "simulation.db")
    capture = _capture(db)
    catalog = JevCatalog(db)
    _frozen_protocol(
        catalog,
        fake_mode="UNKNOWN_EVIDENCE",
    )
    service = JevShadowService(
        db,
        provider_override=FakeJevProvider(
            mode="UNKNOWN_EVIDENCE"
        ),
    )

    review = (await service.process_capture(capture["id"]))[0]
    assert review["status"] == "ERROR"
    assert review["decision"] == "ABSTAIN"
    assert review["abstain_reason"] == "MODEL_ERROR"
    assert (
        review["failure_code"]
        == "OUTPUT_VALIDATION_ERROR"
    )


def test_idempotency_and_restart_do_not_recall(
    tmp_path: Path,
) -> None:
    db = _simulation_db(tmp_path / "simulation.db")
    capture = _capture(db)
    catalog = JevCatalog(db)
    _frozen_protocol(catalog)
    service = JevShadowService(db)

    first = service.enqueue_capture(capture["id"])
    second = service.enqueue_capture(capture["id"])
    assert len(first) == 1
    assert len(second) == 1
    assert first[0]["id"] == second[0]["id"]
    assert first[0]["status"] == "PENDING"

    assert catalog.mark_pending_interrupted() == 1
    interrupted = catalog.get_review(first[0]["id"])
    assert interrupted is not None
    assert interrupted["status"] == "INTERRUPTED"
    assert (
        interrupted["failure_code"]
        == "PROCESS_RESTART"
    )


def test_non_entry_candidate_is_skipped(
    tmp_path: Path,
) -> None:
    db = _simulation_db(tmp_path / "simulation.db")
    capture = _capture(db, action="WAIT")
    catalog = JevCatalog(db)
    _frozen_protocol(catalog)
    service = JevShadowService(db)

    reviews = service.enqueue_capture(capture["id"])
    assert len(reviews) == 1
    assert reviews[0]["status"] == "SKIPPED"
    assert (
        reviews[0]["failure_code"]
        == "OUT_OF_SCOPE_ACTION"
    )


def test_secret_value_is_not_persisted(
    monkeypatch,
    tmp_path: Path,
) -> None:
    sentinel = "JEV_SECRET_SENTINEL_DO_NOT_STORE"
    monkeypatch.setenv("JEV_API_KEY", sentinel)
    db = _simulation_db(tmp_path / "simulation.db")
    _capture(db)
    catalog = JevCatalog(db)
    _frozen_protocol(catalog)

    with sqlite3.connect(db) as conn:
        dump = "\n".join(conn.iterdump())
    assert sentinel not in dump


def test_unfrozen_real_provider_cannot_be_activated(
    tmp_path: Path,
) -> None:
    db = _simulation_db(tmp_path / "simulation.db")
    catalog = JevCatalog(db)
    protocol = catalog.create_protocol(
        client_request_id="real-unfrozen",
        spec=JevTrialProtocolSpec(
            name="real provider remains blocked",
            provider_id="UNFROZEN",
        ),
    )
    assert protocol["status"] == "UNFROZEN"

    with pytest.raises(JevCatalogError) as raised:
        catalog.set_activation(
            protocol["id"],
            enabled=True,
            allow_network=True,
        )
    assert raised.value.code == "JEV_PROTOCOL_NOT_FROZEN"


def test_comparison_uses_valid_review_required_and_closed_only() -> None:
    reviews = [
        {
            "id": "r1",
            "capture_run_id": "c1",
            "sample_index": 0,
            "requested_at": "2026-10-01T00:00:00Z",
            "attempt": 1,
            "status": "VALID",
            "decision": "REVIEW_REQUIRED",
        },
        {
            "id": "r2",
            "capture_run_id": "c1",
            "sample_index": 1,
            "requested_at": "2026-10-01T00:00:01Z",
            "attempt": 1,
            "status": "VALID",
            "decision": "REVIEW_REQUIRED",
        },
        {
            "id": "r3",
            "capture_run_id": "c1",
            "sample_index": 2,
            "requested_at": "2026-10-01T00:00:02Z",
            "attempt": 1,
            "status": "ERROR",
            "decision": "ABSTAIN",
        },
    ]
    outcomes = [
        {
            "capture_run_id": "c1",
            "sample_index": 0,
            "execution_status": "CLOSED",
            "net_return_pct": -10.0,
        },
        {
            "capture_run_id": "c1",
            "sample_index": 1,
            "execution_status": "CLOSED",
            "net_return_pct": 5.0,
        },
        {
            "capture_run_id": "c1",
            "sample_index": 2,
            "execution_status": "CLOSED",
            "net_return_pct": -2.0,
        },
        {
            "capture_run_id": "c1",
            "sample_index": 3,
            "execution_status": "CENSORED",
            "net_return_pct": None,
        },
    ]

    report = build_comparison_report(
        reviews,
        outcomes,
    )
    assert report["comparable_closed_count"] == 3
    assert report["disagreement_count"] == 2
    assert report["avoided_loss_pct_sum"] == 10.0
    assert report["missed_profit_pct_sum"] == 5.0
    assert report["baseline_mean_return_pct"] == pytest.approx(
        -7.0 / 3.0
    )
    assert report["shadow_mean_return_pct"] == pytest.approx(
        -2.0 / 3.0
    )
    assert report[
        "incremental_return_per_opportunity_pct"
    ] == pytest.approx(5.0 / 3.0)
    assert report["retained_candidate_loss_rate"] == 1.0



@pytest.mark.asyncio
async def test_monitor_api_returns_read_only_safe_projection(
    monkeypatch,
    tmp_path: Path,
) -> None:
    sentinel = "JEV_MONITOR_SECRET_MUST_NOT_LEAK"
    monkeypatch.setenv("JEV_API_KEY", sentinel)
    db = _simulation_db(tmp_path / "simulation.db")
    capture = _capture(db)
    catalog = JevCatalog(db)
    _frozen_protocol(catalog)

    service = JevShadowService(
        db,
        provider_override=FakeJevProvider(
            mode="REVIEW_REQUIRED"
        ),
    )
    review = (await service.process_capture(capture["id"]))[0]
    assert review["status"] == "VALID"
    assert review["decision"] == "REVIEW_REQUIRED"

    monkeypatch.setenv("STOCKSCOPE_SIM_DB", str(db))
    status = jev_shadow_status()
    payload = list_jev_shadow_reviews(capture["id"])

    assert status["available"] is True
    assert status["enabled"] is True
    assert status["network_enabled"] is False
    assert status["protocol_status"] == "FROZEN"

    assert payload["available"] is True
    assert payload["capture_id"] == capture["id"]
    assert payload["summary"]["total"] == 1
    assert payload["summary"]["review_required"] == 1
    assert len(payload["items"]) == 1

    item = payload["items"][0]
    assert set(item) == {
        "capture_id",
        "sample_index",
        "market",
        "ticker",
        "name",
        "status",
        "decision",
        "failure_code",
        "completed_at",
        "latency_ms",
        "reason_codes",
    }
    assert item["market"] == "KOSPI"
    assert item["ticker"] == "005930"
    assert item["name"] == "삼성전자"
    assert item["reason_codes"] == ["CONDITION_CONFLICT"]

    encoded = json.dumps(
        {
            "status": status,
            "reviews": payload,
        },
        ensure_ascii=False,
    )
    for forbidden in (
        sentinel,
        "input_json",
        "raw_response",
        "prompt_hash",
        "model_id",
        "provider_id",
        "MUST_NOT_LEAK",
    ):
        assert forbidden not in encoded


def test_monitor_api_is_non_blocking_when_schema_is_not_ready(
    monkeypatch,
    tmp_path: Path,
) -> None:
    db = tmp_path / "simulation.db"
    with sqlite3.connect(db) as conn:
        conn.execute(
            "CREATE TABLE simulation_placeholder(id INTEGER PRIMARY KEY)"
        )
    monkeypatch.setenv("STOCKSCOPE_SIM_DB", str(db))

    status = jev_shadow_status()
    reviews = list_jev_shadow_reviews("missing-capture")

    assert status["available"] is False
    assert status["enabled"] is False
    assert reviews["available"] is False
    assert reviews["items"] == []
    assert reviews["summary"]["total"] == 0


def test_jev_shadow_monitor_routes_are_registered() -> None:
    paths = {route.path for route in app.routes}
    assert "/api/simulation/jev-shadow/status" in paths
    assert "/api/simulation/jev-shadow/reviews" in paths



def test_frozen_trial_artifact_is_ready_and_not_activated(
    tmp_path: Path,
) -> None:
    readiness = trial_readiness()
    assert readiness["ready"] is True
    assert readiness["status"] == "READY_FOR_ACTIVATION"

    artifact = load_trial_artifact()
    spec = artifact["spec"]
    assert artifact["status"] == "FROZEN_READY_FOR_ACTIVATION"
    assert spec["provider_id"] == "OPENAI_RESPONSES"
    assert spec["model_id"] == "gpt-5.6-terra"
    assert spec["prompt_version"] == JEV_PROMPT_VERSION
    assert spec["prompt_hash"] == JEV_PROMPT_HASH
    assert (
        spec["generation_settings"]["structured_output_schema_hash"]
        == JEV_OUTPUT_SCHEMA_HASH
    )
    assert spec["generation_settings"]["store"] is False
    assert spec["source_transmission_approved"] is True
    assert spec["recruitment_mode"] == "ACTIVATION_FORWARD"

    db = _simulation_db(tmp_path / "simulation.db")
    result = configure_trial_protocol(JevCatalog(db))
    assert result["status"] == "READY_FOR_ACTIVATION"
    assert result["network_enabled"] is False
    assert result["model_calls_executed"] == 0

    summary = JevCatalog(db).status_summary()
    activation = summary["activation"]
    assert activation is not None
    assert activation["enabled"] == 0
    assert activation["allow_network"] == 0


@pytest.mark.asyncio
async def test_openai_provider_builds_store_false_structured_request_without_real_network(
    monkeypatch,
) -> None:
    sentinel = "JEV_TEST_KEY_NOT_A_REAL_SECRET"
    monkeypatch.setenv("JEV_API_KEY", sentinel)
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["authorization"] = request.headers.get("Authorization")
        body = json.loads(request.content.decode("utf-8"))
        captured["body"] = body
        output = {
            "decision": "PASS_THROUGH",
            "abstain_reason": None,
            "supporting_reasons": [
                {
                    "code": "CONDITION_ALIGNMENT",
                    "evidence_refs": ["E-CONDITIONS"],
                    "explanation": "조건 근거가 baseline과 일치합니다.",
                }
            ],
            "opposing_reasons": [],
        }
        return httpx.Response(
            200,
            json={
                "id": "resp-test",
                "status": "completed",
                "model": "gpt-5.6-terra",
                "output": [
                    {
                        "type": "message",
                        "content": [
                            {
                                "type": "output_text",
                                "text": json.dumps(output),
                            }
                        ],
                    }
                ],
                "usage": {
                    "input_tokens": 1000,
                    "input_tokens_details": {"cached_tokens": 200},
                    "output_tokens": 100,
                    "output_tokens_details": {"reasoning_tokens": 20},
                    "total_tokens": 1100,
                },
            },
        )

    provider = OpenAIResponsesJevProvider(
        model_id="gpt-5.6-terra",
        reasoning_effort="low",
        max_output_tokens=1200,
        transport=httpx.MockTransport(handler),
    )
    result = await provider.review(
        {
            "request_id": "test",
            "evidence_items": [
                {
                    "evidence_id": "E-CONDITIONS",
                    "value": {"passed": 5, "total": 5},
                }
            ],
        },
        deadline_seconds=12.0,
    )

    assert result.raw_response["decision"] == "PASS_THROUGH"
    assert result.usage is not None
    assert result.usage["served_model"] == "gpt-5.6-terra"
    assert result.usage["store"] is False
    assert result.cost_usd == pytest.approx(0.00284)

    body = captured["body"]
    assert isinstance(body, dict)
    assert body["model"] == "gpt-5.6-terra"
    assert body["store"] is False
    assert body["reasoning"]["effort"] == "low"
    assert body["max_output_tokens"] == 1200
    assert body["text"]["format"]["type"] == "json_schema"
    assert body["text"]["format"]["strict"] is True
    assert body["instructions"]
    assert captured["authorization"] == f"Bearer {sentinel}"

    encoded_body = json.dumps(body, ensure_ascii=False)
    assert sentinel not in encoded_body
