from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from app.core.config import PROJECT_ROOT
from app.simulation.strategy_change import StrategyChangeError, StrategyChangeService
from app.simulation.strategy_evidence import StrategyEvidenceError
from app.simulation.strategy_governance_query import (
    StrategyGovernanceQueryError,
    StrategyGovernanceQueryService,
)
from app.strategy.production_selection_policy import (
    DEFAULT_RUNTIME_DIR,
    ProductionStrategySelectionRegistry,
    SelectionPolicyError,
)


router = APIRouter(
    prefix="/simulation/strategy-governance",
    tags=["strategy-governance"],
)


def _simulation_db() -> Path:
    return Path(
        os.getenv("STOCKSCOPE_SIM_DB")
        or PROJECT_ROOT
        / "backend"
        / "runtime"
        / "simulation"
        / "simulation.db"
    )


def _runtime_dir() -> Path:
    return Path(
        os.getenv("STOCKSCOPE_STRATEGY_SELECTION_RUNTIME_DIR")
        or DEFAULT_RUNTIME_DIR
    )


def _query_service() -> StrategyGovernanceQueryService:
    return StrategyGovernanceQueryService(
        _simulation_db(),
        runtime_dir=_runtime_dir(),
    )


def _change_service() -> StrategyChangeService:
    return StrategyChangeService(_simulation_db())


def _selection_registry() -> ProductionStrategySelectionRegistry:
    return ProductionStrategySelectionRegistry(
        simulation_db=_simulation_db(),
        runtime_dir=_runtime_dir(),
    )


def _http_error(error: Exception) -> None:
    code = str(getattr(error, "code", "STRATEGY_GOVERNANCE_ERROR"))
    message = str(getattr(error, "message", str(error)))

    if "NOT_FOUND" in code:
        status = 404
    elif code in {
        "STRATEGY_GOVERNANCE_SCHEMA_NOT_READY",
        "STRATEGY_EVIDENCE_MIGRATION_REQUIRED",
        "STRATEGY_CHANGE_MIGRATION_REQUIRED",
        "STRATEGY_GOVERNANCE_STORE_NOT_FOUND",
    }:
        status = 409
    elif code in {
        "ACTIVE_POLICY_CONFLICT",
        "PROPOSAL_STALE",
        "Q7_APPROVAL_PROTOCOL_UNAPPROVED",
        "Q7_APPROVAL_PROTOCOL_NOT_PRECOMMITTED",
        "PROPOSAL_NOT_APPROVAL_ELIGIBLE",
        "APPROVAL_PROTOCOL_CHANGED_SINCE_PROPOSAL",
        "ACTIVE_REFERENCE_CORRUPT",
        "ACTIVE_POLICY_CORRUPT",
        "ACTIVE_REFERENCE_NOT_AVAILABLE",
        "ROLLBACK_POLICY_NOT_AVAILABLE",
    }:
        status = 409
    else:
        status = 422
    raise HTTPException(
        status_code=status,
        detail={"code": code, "message": message},
    )


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProposalRequest(StrictModel):
    client_request_id: str = Field(min_length=1, max_length=200)
    changes: list[dict[str, Any]]
    evidence_artifact_ids: list[str]
    affected_horizons: list[str]
    affected_regimes: list[str]


class ApprovalRequest(StrictModel):
    approved_by: str = Field(
        default="LOCAL_USER",
        min_length=1,
        max_length=120,
    )


class ActivationRequest(StrictModel):
    approval_artifact_id: str = Field(min_length=1)
    expected_active_policy_id: str | None = None


class RollbackRequest(StrictModel):
    expected_active_policy_id: str = Field(min_length=1)


@router.get("/overview")
def governance_overview():
    try:
        return _query_service().overview()
    except (
        StrategyGovernanceQueryError,
        StrategyEvidenceError,
        StrategyChangeError,
        SelectionPolicyError,
    ) as error:
        _http_error(error)


@router.get("/registry")
def governance_registry(
    strategy_key: str | None = Query(default=None),
    operational_status: str | None = Query(default=None),
    validation_status: str | None = Query(default=None),
):
    try:
        return _query_service().registry(
            strategy_key=strategy_key,
            operational_status=operational_status,
            validation_status=validation_status,
        )
    except StrategyGovernanceQueryError as error:
        _http_error(error)


@router.get("/evidence")
def governance_evidence(
    strategy_version_id: str | None = Query(default=None),
    verify_source: bool = Query(default=False),
):
    try:
        return _query_service().evidence(
            strategy_version_id=strategy_version_id,
            verify_source=verify_source,
        )
    except (StrategyGovernanceQueryError, StrategyEvidenceError) as error:
        _http_error(error)


@router.get("/evidence/{artifact_id}")
def governance_evidence_item(
    artifact_id: str,
    verify_source: bool = Query(default=True),
):
    try:
        return _query_service().evidence_item(
            artifact_id,
            verify_source=verify_source,
        )
    except (StrategyGovernanceQueryError, StrategyEvidenceError) as error:
        _http_error(error)


@router.get("/proposals")
def governance_proposals(
    limit: int = Query(default=100, ge=1, le=500),
    verify: bool = Query(default=False),
):
    try:
        return _query_service().proposals(limit=limit, verify=verify)
    except (StrategyGovernanceQueryError, StrategyChangeError) as error:
        _http_error(error)


@router.post("/proposals", status_code=201)
def create_governance_proposal(request: ProposalRequest):
    try:
        return _change_service().create_proposal(
            client_request_id=request.client_request_id,
            changes=request.changes,
            evidence_artifact_ids=request.evidence_artifact_ids,
            affected_horizons=request.affected_horizons,
            affected_regimes=request.affected_regimes,
        )
    except StrategyChangeError as error:
        _http_error(error)


@router.get("/proposals/{proposal_id}")
def governance_proposal_item(
    proposal_id: str,
    verify: bool = Query(default=True),
):
    try:
        return _query_service().proposal_item(
            proposal_id,
            verify=verify,
        )
    except (StrategyGovernanceQueryError, StrategyChangeError) as error:
        _http_error(error)


@router.post("/proposals/{proposal_id}/approve")
def approve_governance_proposal(
    proposal_id: str,
    request: ApprovalRequest | None = None,
):
    try:
        return _change_service().approve_proposal(
            proposal_id=proposal_id,
            approved_by=(
                request.approved_by if request is not None else "LOCAL_USER"
            ),
        )
    except StrategyChangeError as error:
        _http_error(error)


@router.get("/approvals")
def governance_approvals(
    limit: int = Query(default=100, ge=1, le=500),
):
    try:
        return _query_service().approvals(limit=limit)
    except (StrategyGovernanceQueryError, StrategyChangeError) as error:
        _http_error(error)


@router.get("/approvals/{approval_id}")
def governance_approval_item(approval_id: str):
    try:
        return _query_service().approval_item(approval_id)
    except (StrategyGovernanceQueryError, StrategyChangeError) as error:
        _http_error(error)


@router.get("/production-policy")
def governance_production_policy():
    try:
        return _query_service().production_policy()
    except (StrategyGovernanceQueryError, SelectionPolicyError) as error:
        _http_error(error)


@router.post("/production-policy/activate")
def activate_governance_policy(request: ActivationRequest):
    try:
        return _selection_registry().activate_approved_policy(
            approval_artifact_id=request.approval_artifact_id,
            expected_active_policy_id=request.expected_active_policy_id,
        )
    except (StrategyChangeError, SelectionPolicyError) as error:
        _http_error(error)


@router.post("/production-policy/rollback")
def rollback_governance_policy(request: RollbackRequest):
    try:
        return _selection_registry().rollback_selection_policy(
            expected_active_policy_id=request.expected_active_policy_id,
        )
    except SelectionPolicyError as error:
        _http_error(error)
