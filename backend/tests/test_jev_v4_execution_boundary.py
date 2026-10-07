from __future__ import annotations

import hashlib
import inspect
import json
import sqlite3
from pathlib import Path

import pytest

from app.api import backtest as backtest_api
from app.jev.review_models import (
    JEV_USER_FEATURE_ACTIVE,
    REVIEW_REQUIRED,
    REVIEW_SKIPPED,
    REVIEW_UNAVAILABLE,
)
from app.jev.review_service import JevManualReviewService
from app.jev.typesafe_catalog import TypeSafeJevCatalog
from app.jev.typesafe_models import (
    JEV_TYPESAFE_ALLOWED_PAYLOAD_CLASS_V4,
    JEV_TYPESAFE_DISPOSITION_POLICY_VERSION_V4,
    JEV_TYPESAFE_PROJECTOR_VERSION_V4,
    JEV_TYPESAFE_QUESTION_CONTRACT_VERSION_V4,
    JEV_TYPESAFE_STATE_CONTRACT_VERSION_V4,
    TypeSafeJevTrialProtocolSpec,
)
from app.jev.typesafe_policy_v4 import JEV_TYPESAFE_DISPOSITION_POLICY_HASH_V4
from app.jev.typesafe_provider import FakeTypeSafeJevProvider
from app.jev.typesafe_questions_v4 import (
    JEV_TYPESAFE_QUESTION_SET_HASH_V4,
    STRATEGY_RELATION_CONFLICT,
)
from app.jev.typesafe_state_v4 import (
    JEV_TYPESAFE_PROJECTOR_HASH_V4,
    JEV_TYPESAFE_STATE_CONTRACT_HASH_V4,
)
from app.prospective import ProspectiveCatalog
from app.prospective.models import (
    ProspectiveCaptureRequest,
    canonical_json,
    digest_json,
)
from app.simulation.strategy_governance import current_strategy_definitions
from app.strategy.condition_semantics import condition_sources
from app.strategy.models import StrategyName
from app.strategy.semantic_composition import compose_semantics
from app.strategy.semantic_source_v2 import verify_semantic_source_v2
from tools.data.migrate_jev_typesafe_v2 import migrate_jev_typesafe
from tools.data.migrate_prospective_vnp2s2 import migrate_prospective_store


class CountingFakeProvider(FakeTypeSafeJevProvider):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.calls = 0

    async def review(self, request, *, deadline_seconds):
        self.calls += 1
        return await super().review(
            request,
            deadline_seconds=deadline_seconds,
        )


def _db(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    sqlite3.connect(path).close()
    migrate_prospective_store(path)
    migrate_jev_typesafe(path)
    return path


def _candidate() -> dict:
    binding = next(
        item
        for item in current_strategy_definitions()
        if item.strategy_key == StrategyName.TREND_FOLLOWING.value
    )
    total = len(condition_sources(StrategyName.TREND_FOLLOWING.value))
    return {
        "market": "KOSPI",
        "code": "005930",
        "name": "fixture",
        "rank": 1,
        "strategy": StrategyName.TREND_FOLLOWING.value,
        "strategy_version_id": binding.strategy_version_id,
        "strategy_definition_hash": binding.definition_hash,
        "decision_status": "READY",
        "candidate_state": "READY",
        "action": "ENTRY_CANDIDATE",
        "conditions": {
            "passed": total,
            "total": total,
            "missing": 0,
            "top_missing": [],
        },
    }


def _capture(db: Path) -> dict:
    catalog = ProspectiveCatalog(db)
    request = ProspectiveCaptureRequest(
        market_scope="KOSPI",
        requested_as_of="2026-10-07",
        candidate_limit=1,
        horizon_intent="SHORT",
        horizon_policy_version="HORIZON-V1",
        selection_policy_id="POLICY",
        selection_policy_hash="POLICY-HASH",
    )
    catalog.begin_capture(source_job_id="v4-review-boundary", request=request)
    return catalog.finalize_capture(
        source_job_id="v4-review-boundary",
        request=request,
        result={
            "version": "scanner-fixture",
            "requested_as_of": "2026-10-07",
            "market_scope": "KOSPI",
            "data_dates": {"KOSPI": "2026-10-07"},
            "input_fingerprint": "fixture-input",
            "partial_data": False,
            "summary": {"candidate_count": 1},
            "candidates": [_candidate()],
            "more_candidates": [],
            "horizon_context": {"intent": "SHORT"},
            "strategy_selection_policy": {
                "policy_id": "POLICY",
                "policy_hash": "POLICY-HASH",
            },
            "diagnostics": {
                "reproducibility_audit": {
                    "production_baseline": "BASELINE"
                }
            },
        },
    )


def _v4_protocol(db: Path) -> dict:
    catalog = TypeSafeJevCatalog(db)
    protocol = catalog.create_protocol(
        client_request_id="manual-v4-fake-protocol",
        spec=TypeSafeJevTrialProtocolSpec(
            name="manual V4 fake",
            provider_id="FAKE",
            model_requested="fake-jev-v4",
            expected_model_returned="fake-jev-v4",
            state_contract_version=JEV_TYPESAFE_STATE_CONTRACT_VERSION_V4,
            state_contract_hash=JEV_TYPESAFE_STATE_CONTRACT_HASH_V4,
            projector_version=JEV_TYPESAFE_PROJECTOR_VERSION_V4,
            projector_hash=JEV_TYPESAFE_PROJECTOR_HASH_V4,
            question_contract_version=JEV_TYPESAFE_QUESTION_CONTRACT_VERSION_V4,
            question_set_hash=JEV_TYPESAFE_QUESTION_SET_HASH_V4,
            disposition_policy_version=JEV_TYPESAFE_DISPOSITION_POLICY_VERSION_V4,
            disposition_policy_hash=JEV_TYPESAFE_DISPOSITION_POLICY_HASH_V4,
            threshold_strategy=0.70,
            recruitment_duration_calendar_days=30,
            max_recruited_candidates=20,
            budget_limit_usd=1.0,
            per_call_reservation_usd=0.001,
            allowed_payload_class=JEV_TYPESAFE_ALLOWED_PAYLOAD_CLASS_V4,
        ),
    )
    assert protocol["status"] == "FROZEN"
    return protocol


def _insert_residual_sample(db: Path, capture_id: str) -> str:
    catalog = ProspectiveCatalog(db)
    sample = catalog.list_samples(capture_run_id=capture_id)[0]
    snapshot = sample["snapshot"]
    source = snapshot["semantic_source_v2"]

    relative_rows = [
        item
        for item in source["conditions"]["items"]
        if "relative_strength" in item["concept_refs"]
    ]
    assert relative_rows
    for item in relative_rows:
        item["stance"] = "WEAKENS"

    composition = compose_semantics(
        relation_contract=source["relations"],
        assertions=source["conditions"]["items"],
    )
    assert composition.status == "RESIDUAL_SEMANTIC_REVIEW"
    source["local_semantic_composition"] = {
        "status": composition.status,
        "reason_codes": list(composition.reason_codes),
        "relation_results": [dict(item) for item in composition.relation_results],
    }
    source["readiness"]["local_semantic_status"] = composition.status
    source["readiness"]["local_semantic_reasons"] = list(composition.reason_codes)
    source["readiness"]["residual_review_eligible"] = True

    source_body = dict(source)
    source_body.pop("source_snapshot_hash", None)
    source["source_snapshot_hash"] = hashlib.sha256(
        json.dumps(
            source_body,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    assert verify_semantic_source_v2(source) == (True, None)

    snapshot["semantic_source_v2"] = source
    snapshot_hash = digest_json(snapshot)
    with sqlite3.connect(db) as conn:
        conn.execute(
            """
            INSERT INTO prospective_recommendation_sample(
                capture_run_id,sample_index,market,ticker,name,rank,
                strategy,decision_status,candidate_state,action,
                signal_date,snapshot_json,snapshot_hash,created_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                capture_id,
                1,
                sample["market"],
                sample["ticker"],
                sample["name"],
                sample["rank"],
                sample["strategy"],
                sample["decision_status"],
                sample["candidate_state"],
                sample["action"],
                sample["signal_date"],
                canonical_json(snapshot),
                snapshot_hash,
                sample["created_at"],
            ),
        )
    return snapshot_hash


def test_baseline_scanner_has_no_automatic_jev_schedule_path() -> None:
    source = inspect.getsource(backtest_api)
    run_source = inspect.getsource(backtest_api._run_scanner_job)
    assert "JevShadowService" not in source
    assert "try_schedule_capture" not in run_source
    assert '"execution_mode"] = "BASELINE_ONLY"' in run_source
    assert '"status": "NOT_REQUESTED"' in run_source


def test_new_capture_keeps_v1_and_adds_v2_semantic_snapshot(
    tmp_path: Path,
) -> None:
    db = _db(tmp_path / "simulation.db")
    capture = _capture(db)
    sample = ProspectiveCatalog(db).list_samples(
        capture_run_id=capture["id"]
    )[0]

    assert "semantic_source" in sample["snapshot"]
    assert "semantic_source_v2" in sample["snapshot"]
    assert verify_semantic_source_v2(
        sample["snapshot"]["semantic_source_v2"]
    ) == (True, None)


@pytest.mark.asyncio
async def test_feature_disabled_returns_unavailable_without_touching_db(
    tmp_path: Path,
) -> None:
    missing_db = tmp_path / "does-not-exist.db"
    service = JevManualReviewService(missing_db)
    result = await service.request_review(
        capture_id="capture-does-not-matter",
        sample_index=0,
    )
    assert result["status"] == REVIEW_UNAVAILABLE
    assert result["reason"] == "FEATURE_NOT_ACTIVATED"
    assert missing_db.exists() is False


@pytest.mark.asyncio
async def test_local_match_skips_provider_call(
    tmp_path: Path,
) -> None:
    db = _db(tmp_path / "simulation.db")
    capture = _capture(db)
    protocol = _v4_protocol(db)
    provider = CountingFakeProvider(
        probabilities={STRATEGY_RELATION_CONFLICT: 0.82},
        returned_model="fake-jev-v4",
    )
    service = JevManualReviewService(
        db,
        feature_status=JEV_USER_FEATURE_ACTIVE,
        protocol=protocol,
        provider_override=provider,
    )

    result = await service.request_review(capture_id=capture["id"])

    assert result["status"] == REVIEW_SKIPPED
    assert result["reason"] == "NO_RESIDUAL_SEMANTIC_REVIEW"
    assert provider.calls == 0


@pytest.mark.asyncio
async def test_same_residual_snapshot_calls_provider_once_and_reuses_result(
    tmp_path: Path,
) -> None:
    db = _db(tmp_path / "simulation.db")
    capture = _capture(db)
    original_sample = ProspectiveCatalog(db).list_samples(
        capture_run_id=capture["id"]
    )[0]
    original_baseline_fields = {
        key: original_sample[key]
        for key in (
            "capture_run_id",
            "sample_index",
            "market",
            "ticker",
            "rank",
            "strategy",
            "action",
        )
    }
    residual_snapshot_hash = _insert_residual_sample(db, capture["id"])
    protocol = _v4_protocol(db)
    provider = CountingFakeProvider(
        probabilities={STRATEGY_RELATION_CONFLICT: 0.82},
        returned_model="fake-jev-v4",
    )
    service = JevManualReviewService(
        db,
        feature_status=JEV_USER_FEATURE_ACTIVE,
        protocol=protocol,
        provider_override=provider,
    )

    first = await service.request_review(
        capture_id=capture["id"],
        sample_index=1,
    )
    second = await service.request_review(
        capture_id=capture["id"],
        sample_index=1,
    )

    assert first["status"] == REVIEW_REQUIRED
    assert first["reused"] is False
    assert second["status"] == REVIEW_REQUIRED
    assert second["reused"] is True
    assert second["review_id"] == first["review_id"]
    assert second["review_identity"] == first["review_identity"]
    assert provider.calls == 1

    samples_after = ProspectiveCatalog(db).list_samples(
        capture_run_id=capture["id"]
    )
    baseline_after = next(
        item for item in samples_after if int(item["sample_index"]) == 0
    )
    residual_after = next(
        item for item in samples_after if int(item["sample_index"]) == 1
    )
    assert {
        key: baseline_after[key]
        for key in original_baseline_fields
    } == original_baseline_fields
    assert baseline_after["snapshot_hash"] == original_sample["snapshot_hash"]
    assert residual_after["snapshot_hash"] == residual_snapshot_hash


@pytest.mark.asyncio
async def test_provider_error_does_not_mutate_baseline(
    tmp_path: Path,
) -> None:
    db = _db(tmp_path / "simulation.db")
    capture = _capture(db)
    residual_snapshot_hash = _insert_residual_sample(db, capture["id"])
    protocol = _v4_protocol(db)
    provider = CountingFakeProvider(
        returned_model="fake-jev-v4",
        mode="ERROR",
    )
    service = JevManualReviewService(
        db,
        feature_status=JEV_USER_FEATURE_ACTIVE,
        protocol=protocol,
        provider_override=provider,
    )

    result = await service.request_review(
        capture_id=capture["id"],
        sample_index=1,
    )
    assert result["status"] == "ERROR"
    assert provider.calls == 1

    samples_after = ProspectiveCatalog(db).list_samples(
        capture_run_id=capture["id"]
    )
    residual_after = next(
        item for item in samples_after if int(item["sample_index"]) == 1
    )
    assert residual_after["snapshot_hash"] == residual_snapshot_hash
