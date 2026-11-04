"""JEV-LIVE-01: isolated, authored synthetic V4 -> real service integration.

No operational capture, market store, or user packet is accepted.  This fixture
is authored from fixed strategy semantics, NOT sampled from market observations.
Network permission belongs exclusively to the caller/CLI; never to Scanner.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any

import httpx

from app.jev.review_models import JEV_USER_FEATURE_ACTIVE
from app.jev.review_service import JevManualReviewService
from app.jev.typesafe_catalog import TypeSafeJevCatalog
from app.jev.typesafe_models import (
    JEV_TYPESAFE_ALLOWED_PAYLOAD_CLASS_V4,
    JEV_TYPESAFE_DISPOSITION_POLICY_VERSION_V4,
    JEV_TYPESAFE_PROJECTOR_VERSION_V4,
    JEV_TYPESAFE_PROVIDER_ID,
    JEV_TYPESAFE_QUESTION_CONTRACT_VERSION_V4,
    JEV_TYPESAFE_STATE_CONTRACT_VERSION_V4,
    TypeSafeJevTrialProtocolSpec,
    canonical_json,
    digest_json,
)
from app.jev.typesafe_policy_v4 import JEV_TYPESAFE_DISPOSITION_POLICY_HASH_V4
from app.jev.typesafe_provider import provider_from_typesafe_spec
from app.jev.typesafe_questions_v4 import JEV_TYPESAFE_QUESTION_SET_HASH_V4
from app.jev.typesafe_service import build_system_one_request
from app.jev.typesafe_state_v4 import (
    JEV_TYPESAFE_PROJECTOR_HASH_V4,
    JEV_TYPESAFE_STATE_CONTRACT_HASH_V4,
    route_typesafe_state_v4,
)
from app.prospective import ProspectiveCatalog
from app.prospective.models import ProspectiveCaptureRequest
from app.simulation.strategy_governance import current_strategy_definitions
from app.strategy.condition_semantics import condition_sources
from app.strategy.models import StrategyName
from app.strategy.semantic_composition import RESIDUAL_SEMANTIC_REVIEW, compose_semantics
from app.strategy.semantic_source_v2 import verify_semantic_source_v2
from tools.data.migrate_jev_typesafe_v2 import migrate_jev_typesafe
from tools.data.migrate_prospective_vnp2s2 import migrate_prospective_store


FIXTURE_ID = "JEV-LIVE-01-AUTHORED-SYNTHETIC"
FIXTURE_DATE = "2026-10-07"
FIXTURE_TICKER = "999991"  # Invented: never use a real stock/sample.


def _synthetic_candidate() -> dict[str, Any]:
    strategy = StrategyName.TREND_FOLLOWING.value
    binding = next(
        row for row in current_strategy_definitions() if row.strategy_key == strategy
    )
    count = len(condition_sources(strategy))
    return {
        "market": "KOSPI",  # Schema label only; no KRX price/quote is loaded.
        "code": FIXTURE_TICKER,
        "name": FIXTURE_ID,
        "rank": 1,
        "strategy": strategy,
        "strategy_version_id": binding.strategy_version_id,
        "strategy_definition_hash": binding.definition_hash,
        "decision_status": "READY",
        "candidate_state": "READY",
        "action": "ENTRY_CANDIDATE",
        "conditions": {"passed": count, "total": count, "missing": 0, "top_missing": []},
    }


def _make_isolated_capture(db: Path) -> tuple[str, int, str]:
    catalog = ProspectiveCatalog(db)
    request = ProspectiveCaptureRequest(
        market_scope="KOSPI",
        requested_as_of=FIXTURE_DATE,
        candidate_limit=1,
        horizon_intent="SHORT",
        horizon_policy_version="HORIZON-V1",
        selection_policy_id="SYNTHETIC-ONLY",
        selection_policy_hash="SYNTHETIC-ONLY-HASH",
    )
    source_job = "jev-live01-synthetic-only"
    catalog.begin_capture(source_job_id=source_job, request=request)
    capture = catalog.finalize_capture(
        source_job_id=source_job,
        request=request,
        result={
            "version": "jev-live01-authored-synthetic",
            "requested_as_of": FIXTURE_DATE,
            "market_scope": "KOSPI",
            "data_dates": {"KOSPI": FIXTURE_DATE},
            "input_fingerprint": FIXTURE_ID,
            "partial_data": False,
            "summary": {"candidate_count": 1},
            "candidates": [_synthetic_candidate()],
            "more_candidates": [],
            "horizon_context": {"intent": "SHORT"},
            "strategy_selection_policy": {
                "policy_id": "SYNTHETIC-ONLY",
                "policy_hash": "SYNTHETIC-ONLY-HASH",
            },
            "diagnostics": {"reproducibility_audit": {"production_baseline": "SYNTHETIC"}},
        },
        require_policy_provenance=False,  # Only this private synthetic fixture.
    )
    sample = catalog.list_samples(capture_run_id=capture["id"])[0]
    snapshot = sample["snapshot"]
    source = snapshot["semantic_source_v2"]
    rows = [
        item for item in source["conditions"]["items"]
        if "relative_strength" in item["concept_refs"]
    ]
    if not rows:
        raise ValueError("JEV_LIVE01_SYNTHETIC_RELATION_MISSING")
    for item in rows:
        item["stance"] = "WEAKENS"
    composition = compose_semantics(
        relation_contract=source["relations"],
        assertions=source["conditions"]["items"],
    )
    if composition.status != RESIDUAL_SEMANTIC_REVIEW:
        raise ValueError("JEV_LIVE01_SYNTHETIC_ROUTE_NOT_RESIDUAL")
    source["local_semantic_composition"] = {
        "status": composition.status,
        "reason_codes": list(composition.reason_codes),
        "relation_results": [dict(row) for row in composition.relation_results],
    }
    source["readiness"]["local_semantic_status"] = composition.status
    source["readiness"]["local_semantic_reasons"] = list(composition.reason_codes)
    source["readiness"]["residual_review_eligible"] = True
    body = dict(source)
    body.pop("source_snapshot_hash", None)
    source["source_snapshot_hash"] = hashlib.sha256(
        json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    if verify_semantic_source_v2(source) != (True, None):
        raise ValueError("JEV_LIVE01_SYNTHETIC_SOURCE_INVALID")
    snapshot_hash = digest_json(snapshot)
    with sqlite3.connect(db) as conn:
        conn.execute(
            """INSERT INTO prospective_recommendation_sample(
                capture_run_id,sample_index,market,ticker,name,rank,
                strategy,decision_status,candidate_state,action,
                signal_date,snapshot_json,snapshot_hash,created_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                capture["id"], 1, sample["market"], FIXTURE_TICKER, FIXTURE_ID,
                sample["rank"], sample["strategy"], sample["decision_status"],
                sample["candidate_state"], sample["action"], sample["signal_date"],
                canonical_json(snapshot), snapshot_hash, sample["created_at"],
            ),
        )
    return str(capture["id"]), 1, snapshot_hash


def prepare_synthetic_service(
    db_path: Path,
    *,
    model_requested: str,
    expected_model_returned: str,
    evidence: dict[str, str],
    budget_usd: float = 1.0,
    reservation_usd: float = 0.10,
) -> tuple[JevManualReviewService, dict[str, Any]]:
    """Create a new dedicated SQLite file. Existing files are never opened."""
    db = Path(db_path)
    if db.exists():
        raise ValueError("JEV_LIVE01_DB_MUST_NOT_EXIST")
    if not (0 < reservation_usd <= budget_usd):
        raise ValueError("JEV_LIVE01_BUDGET_INVALID")
    for key in (
        "provider_policy_checked_at", "retention_status",
        "model_discovery_ref", "model_discovery_hash",
    ):
        if not str(evidence.get(key) or "").strip():
            raise ValueError(f"JEV_LIVE01_EVIDENCE_REQUIRED:{key}")
    db.parent.mkdir(parents=True, exist_ok=True)
    sqlite3.connect(db).close()
    migrate_prospective_store(db)
    migrate_jev_typesafe(db)
    capture_id, sample_index, snapshot_hash = _make_isolated_capture(db)
    spec = TypeSafeJevTrialProtocolSpec(
        name="JEV-LIVE-01 authored synthetic only",
        provider_id=JEV_TYPESAFE_PROVIDER_ID,
        model_requested=model_requested,
        expected_model_returned=expected_model_returned,
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
        max_recruited_candidates=1,
        budget_limit_usd=budget_usd,
        per_call_reservation_usd=reservation_usd,
        allowed_payload_class=JEV_TYPESAFE_ALLOWED_PAYLOAD_CLASS_V4,
        source_transmission_approved=True,  # Fixed original synthetic fixture ONLY.
        provider_policy_checked_at=evidence["provider_policy_checked_at"],
        retention_status=evidence["retention_status"],
        model_discovery_ref=evidence["model_discovery_ref"],
        model_discovery_hash=evidence["model_discovery_hash"],
        deadline_seconds=10.0,
        retry_count=0,
    )
    protocol = TypeSafeJevCatalog(db).create_protocol(
        client_request_id=FIXTURE_ID,
        spec=spec,
    )
    if protocol["status"] != "FROZEN":
        raise ValueError("JEV_LIVE01_V4_PROTOCOL_NOT_FROZEN")
    service = JevManualReviewService(
        db,
        feature_status=JEV_USER_FEATURE_ACTIVE,  # Never an HTTP API feature flag.
        protocol=protocol,
    )
    sample = service.prospective.list_samples(capture_run_id=capture_id)[sample_index]
    route = route_typesafe_state_v4(sample)
    if route.local_status != RESIDUAL_SEMANTIC_REVIEW:
        raise ValueError("JEV_LIVE01_ROUTE_MISMATCH")
    request, projection = build_system_one_request(sample, protocol["spec"])
    if set(request) != {"state", "questions", "model"}:
        raise ValueError("JEV_LIVE01_WIRE_SHAPE_INVALID")
    wire = canonical_json(request)
    if FIXTURE_TICKER in wire or FIXTURE_ID in wire or "snapshot_json" in wire:
        raise ValueError("JEV_LIVE01_SYNTHETIC_WIRE_CONTAMINATED")
    preview = {
        "fixture": FIXTURE_ID,
        "synthetic_only": True,
        "capture_id": capture_id,
        "sample_index": sample_index,
        "snapshot_hash": snapshot_hash,
        "protocol_hash": protocol["spec_hash"],
        "wire_sha256": hashlib.sha256(wire.encode("utf-8")).hexdigest(),
        "wire_bytes": len(wire.encode("utf-8")),
        "masked_wire_preview": {
            "state": "[FIXED SYNTHETIC STRATEGY TEXT MASKED]",
            "questions": {key: "[V4 QUESTION MASKED]" for key in request["questions"]},
            "model": request["model"],
        },
        "projected_state_hash": projection.state_hash,
        "max_calls": 1,
        "per_call_reservation_usd": reservation_usd,
        "budget_limit_usd": budget_usd,
        "market_data_outbound_allowed": False,
    }
    return service, preview


async def execute_synthetic_service(
    service: JevManualReviewService,
    preview: dict[str, Any],
    *,
    transport: httpx.AsyncBaseTransport | None = None,
) -> dict[str, Any]:
    """Same real TypeSafe provider -> V4 reviewer -> catalog as the future UI."""
    if preview.get("fixture") != FIXTURE_ID or not preview.get("synthetic_only"):
        raise ValueError("JEV_LIVE01_SYNTHETIC_FIXTURE_REQUIRED")
    if service.provider_override is not None or service.protocol is None:
        raise ValueError("JEV_LIVE01_SERVICE_MUST_BE_FRESH")
    sample = service.prospective.list_samples(
        capture_run_id=preview["capture_id"]
    )[preview["sample_index"]]
    if sample["snapshot_hash"] != preview["snapshot_hash"]:
        raise ValueError("JEV_LIVE01_SNAPSHOT_CHANGED")
    request, _ = build_system_one_request(sample, service.protocol["spec"])
    if hashlib.sha256(canonical_json(request).encode()).hexdigest() != preview["wire_sha256"]:
        raise ValueError("JEV_LIVE01_WIRE_CHANGED")
    service.provider_override = provider_from_typesafe_spec(
        service.protocol["spec"], allow_network=True, transport=transport
    )
    result = await service.request_review(
        capture_id=preview["capture_id"], sample_index=preview["sample_index"]
    )
    stored = None
    if result["review_id"]:
        stored = service.typesafe.get_review(result["review_id"])
    return {
        "result": result,
        "stored_status": stored["status"] if stored else None,
        "stored_disposition": stored["disposition"] if stored else None,
        "model_returned": stored["model_returned"] if stored else None,
        "model_identity_status": stored["model_identity_status"] if stored else None,
        "usage": json.loads(stored["usage_json"]) if stored and stored["usage_json"] else None,
        "cost_usd": stored["cost_usd"] if stored else None,
        "cost_unknown": bool(stored["cost_unknown"]) if stored else True,
        "failure_code": stored["failure_code"] if stored else None,
    }
