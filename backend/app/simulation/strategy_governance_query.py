from __future__ import annotations

import sqlite3
from collections import Counter
from pathlib import Path
from typing import Any

from app.baseline.scanner_production_baseline import load_manifest, manifest_path
from app.core.config import PROJECT_ROOT
from app.simulation.strategy_change import (
    StrategyChangeService,
    production_blocked_approval_protocol,
)
from app.simulation.strategy_evidence import StrategyEvidenceService
from app.simulation.strategy_governance import STRATEGY_GOVERNANCE_SCHEMA_VERSION
from app.strategy.production_selection_policy import (
    ProductionStrategySelectionRegistry,
)


_REQUIRED_TABLES = frozenset(
    {
        "strategy_governance_schema_meta",
        "strategy_registry_version",
        "strategy_evaluation_artifact",
        "strategy_change_proposal",
        "strategy_change_proposal_evidence",
        "strategy_approval_artifact",
    }
)


class StrategyGovernanceQueryError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class StrategyGovernanceQueryService:
    """Read-only view over P5 strategy-governance state."""

    def __init__(
        self,
        simulation_db: Path,
        *,
        runtime_dir: Path | None = None,
    ) -> None:
        self.simulation_db = Path(simulation_db)
        self.runtime_dir = Path(runtime_dir) if runtime_dir is not None else None

    def _connect(self) -> sqlite3.Connection:
        if not self.simulation_db.is_file():
            raise StrategyGovernanceQueryError(
                "STRATEGY_GOVERNANCE_STORE_NOT_FOUND",
                f"Simulation DB를 찾을 수 없습니다: {self.simulation_db}",
            )
        conn = sqlite3.connect(self.simulation_db, timeout=20.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    @staticmethod
    def _tables(conn: sqlite3.Connection) -> set[str]:
        return {
            str(row["name"])
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }

    def require_ready(self) -> None:
        with self._connect() as conn:
            missing = sorted(_REQUIRED_TABLES - self._tables(conn))
            if missing:
                raise StrategyGovernanceQueryError(
                    "STRATEGY_GOVERNANCE_SCHEMA_NOT_READY",
                    "P5-S1 Strategy Governance migration이 필요합니다: "
                    + ", ".join(missing),
                )
            row = conn.execute(
                """
                SELECT value
                FROM strategy_governance_schema_meta
                WHERE key='schema_version'
                """
            ).fetchone()
            if row is None or str(row["value"]) != STRATEGY_GOVERNANCE_SCHEMA_VERSION:
                raise StrategyGovernanceQueryError(
                    "STRATEGY_GOVERNANCE_SCHEMA_NOT_READY",
                    "P5-S1 Strategy Governance schema version이 현재 코드와 호환되지 않습니다.",
                )

    def registry(
        self,
        *,
        strategy_key: str | None = None,
        operational_status: str | None = None,
        validation_status: str | None = None,
    ) -> list[dict[str, Any]]:
        self.require_ready()
        clauses: list[str] = []
        values: list[str] = []
        if strategy_key:
            clauses.append("r.strategy_key=?")
            values.append(strategy_key)
        if operational_status:
            clauses.append("r.operational_status=?")
            values.append(operational_status)
        if validation_status:
            clauses.append("r.validation_status=?")
            values.append(validation_status)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT
                    r.strategy_version_id,
                    r.strategy_key,
                    r.definition_version,
                    r.definition_hash,
                    r.fingerprint_contract_version,
                    r.implementation_key,
                    r.operational_status,
                    r.validation_status,
                    r.source,
                    r.created_at,
                    r.retired_at,
                    (
                        SELECT COUNT(*)
                        FROM strategy_evaluation_artifact e
                        WHERE e.strategy_version_id=r.strategy_version_id
                    ) AS evidence_count
                FROM strategy_registry_version r
                {where}
                ORDER BY r.strategy_key,r.created_at DESC,r.strategy_version_id
                """,
                tuple(values),
            ).fetchall()
        return [{key: row[key] for key in row.keys()} for row in rows]

    def evidence(
        self,
        *,
        strategy_version_id: str | None = None,
        verify_source: bool = False,
    ) -> list[dict[str, Any]]:
        self.require_ready()
        return StrategyEvidenceService(self.simulation_db).list_artifacts(
            strategy_version_id=strategy_version_id,
            verify_source=verify_source,
        )

    def evidence_item(
        self,
        artifact_id: str,
        *,
        verify_source: bool = True,
    ) -> dict[str, Any]:
        self.require_ready()
        return StrategyEvidenceService(self.simulation_db).get_artifact(
            artifact_id,
            verify_source=verify_source,
        )

    def proposals(
        self,
        *,
        limit: int = 100,
        verify: bool = False,
    ) -> list[dict[str, Any]]:
        self.require_ready()
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id
                FROM strategy_change_proposal
                ORDER BY created_at DESC,id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        service = StrategyChangeService(self.simulation_db)
        result: list[dict[str, Any]] = []
        for row in rows:
            proposal = service.get_proposal(str(row["id"]))
            if verify:
                proposal["verification"] = service.verify_proposal(
                    str(row["id"])
                )
            result.append(proposal)
        return result

    def proposal_item(
        self,
        proposal_id: str,
        *,
        verify: bool = True,
    ) -> dict[str, Any]:
        self.require_ready()
        service = StrategyChangeService(self.simulation_db)
        proposal = service.get_proposal(proposal_id)
        if verify:
            proposal["verification"] = service.verify_proposal(proposal_id)
        return proposal

    def approvals(self, *, limit: int = 100) -> list[dict[str, Any]]:
        self.require_ready()
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id
                FROM strategy_approval_artifact
                ORDER BY approved_at DESC,id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        service = StrategyChangeService(self.simulation_db)
        return [service.get_approval(str(row["id"])) for row in rows]

    def approval_item(self, approval_id: str) -> dict[str, Any]:
        self.require_ready()
        return StrategyChangeService(self.simulation_db).get_approval(
            approval_id
        )

    @staticmethod
    def scanner_baseline() -> dict[str, Any]:
        try:
            manifest = load_manifest(manifest_path(PROJECT_ROOT))
        except Exception as exc:
            raise StrategyGovernanceQueryError(
                "SCANNER_BASELINE_NOT_AVAILABLE",
                f"Scanner production baseline을 읽을 수 없습니다: {exc}",
            ) from exc
        return {
            "scanner_version": str(manifest.get("scanner_version") or ""),
            "baseline_id": str(manifest.get("baseline_id") or ""),
            "production_fingerprint": str(
                manifest.get("production_fingerprint") or ""
            ),
            "production_policy_fingerprint": str(
                manifest.get("policy_fingerprint") or ""
            ),
        }

    def production_policy(self) -> dict[str, Any]:
        kwargs: dict[str, Any] = {"simulation_db": self.simulation_db}
        if self.runtime_dir is not None:
            kwargs["runtime_dir"] = self.runtime_dir
        registry = ProductionStrategySelectionRegistry(**kwargs)
        resolution = registry.resolve_active_selection_policy()
        pin = registry.pin_active_selection_policy()

        # _load_reference performs the same validation used by activation and
        # resolution. The effective Production state below comes from the same
        # baseline-aware pin used by Scanner runs, never from a latest DB row.
        reference, reference_reason = registry._load_reference()  # noqa: SLF001
        operating = [
            {
                "strategy_version_id": strategy_version_id,
                "strategy_key": strategy_key,
                "definition_hash": definition_hash,
            }
            for strategy_version_id, strategy_key, definition_hash
            in pin.operating_strategies
        ]
        return {
            "policy_id": pin.policy_id,
            "policy_hash": pin.policy_hash,
            "policy_contract_version": pin.policy_contract_version,
            "policy_source": pin.policy_source,
            "fallback_used": pin.fallback_used,
            "fallback_reason": pin.fallback_reason,
            "active_reference_valid": resolution.active_reference_valid,
            "policy_hash_valid": resolution.policy_hash_valid,
            "operating_strategy_count": len(operating),
            "operating_strategies": operating,
            "rollback_available": bool(
                reference
                and reference.get("rollback_policy_id")
                and reference.get("rollback_policy_hash")
            ),
            "generation": (
                int(reference["generation"])
                if reference is not None
                and reference.get("generation") is not None
                else None
            ),
            "activation_source": (
                str(reference.get("activation_source"))
                if reference is not None
                and reference.get("activation_source") is not None
                else None
            ),
            "reference_reason": reference_reason,
            "scanner_baseline": self.scanner_baseline(),
        }

    def overview(self) -> dict[str, Any]:
        rows = self.registry()
        operational = Counter(str(row["operational_status"]) for row in rows)
        validation = Counter(str(row["validation_status"]) for row in rows)

        with self._connect() as conn:
            evidence_count = int(
                conn.execute(
                    "SELECT COUNT(*) FROM strategy_evaluation_artifact"
                ).fetchone()[0]
            )

        current_count = 0
        stale_or_missing_count = 0
        verification_error: dict[str, str] | None = None
        if evidence_count:
            try:
                artifacts = self.evidence(verify_source=True)
                current_count = sum(
                    1
                    for item in artifacts
                    if item.get("current_source_status") == "CURRENT"
                )
                stale_or_missing_count = sum(
                    1
                    for item in artifacts
                    if item.get("current_source_status")
                    in {"SOURCE_CHANGED", "SOURCE_MISSING"}
                )
            except Exception as exc:
                verification_error = {
                    "code": getattr(
                        exc,
                        "code",
                        "STRATEGY_EVIDENCE_STATUS_UNAVAILABLE",
                    ),
                    "message": str(exc),
                }

        proposals = self.proposals(limit=1, verify=True)
        approvals = self.approvals(limit=1)
        protocol = production_blocked_approval_protocol()
        production = self.production_policy()
        latest_proposal = proposals[0] if proposals else None
        latest_approval = approvals[0] if approvals else None

        return {
            "schema_version": STRATEGY_GOVERNANCE_SCHEMA_VERSION,
            "schema_ready": True,
            "registry": {
                "total_version_count": len(rows),
                "operating_count": operational.get("OPERATING", 0),
                "candidate_count": operational.get("CANDIDATE", 0),
                "on_hold_count": operational.get("ON_HOLD", 0),
                "demoted_count": operational.get("DEMOTED", 0),
                "validation_states": dict(sorted(validation.items())),
            },
            "evidence": {
                "artifact_count": evidence_count,
                "current_count": current_count,
                "stale_or_missing_count": stale_or_missing_count,
                "verification_error": verification_error,
            },
            "proposal": {
                "latest_id": (
                    str(latest_proposal["id"])
                    if latest_proposal is not None
                    else None
                ),
                "gate_state": (
                    str(latest_proposal["approval_gate_state"])
                    if latest_proposal is not None
                    else None
                ),
                "verification_status": (
                    str(latest_proposal["verification"]["status"])
                    if latest_proposal is not None
                    else None
                ),
            },
            "approval": {
                "latest_id": (
                    str(latest_approval["id"])
                    if latest_approval is not None
                    else None
                ),
                "production_approval_available": bool(
                    protocol.activation_eligible and protocol.q7_precommitted
                ),
                "blocked_reason": (
                    None
                    if protocol.activation_eligible
                    and protocol.q7_precommitted
                    else "Q7_APPROVAL_PROTOCOL_UNAPPROVED"
                ),
                "protocol_version": protocol.protocol_version,
            },
            "production_policy": production,
            "scanner_baseline": production["scanner_baseline"],
        }
