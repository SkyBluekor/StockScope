from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
from uuid import NAMESPACE_URL, uuid5

from app.baseline.scanner_production_baseline import (
    load_manifest,
    manifest_path,
    verify_baseline,
)
from app.core.config import PROJECT_ROOT
from app.horizon import (
    EXPLICIT_HORIZONS,
    LEGACY_UNSPECIFIED,
    horizon_policy_catalog,
)
from app.simulation.strategy_evidence import StrategyEvidenceService
from app.strategy.models import MarketRegime

STRATEGY_CHANGE_PROPOSAL_VERSION = "VN_P5_S1_STRATEGY_CHANGE_PROPOSAL_V1"
STRATEGY_APPROVAL_ARTIFACT_VERSION = "VN_P5_S1_STRATEGY_APPROVAL_V1"
STRATEGY_APPROVAL_PROTOCOL_CONTRACT_VERSION = (
    "VN_P5_S1_APPROVAL_PROTOCOL_CONTRACT_V1"
)
PRODUCTION_BLOCKED_PROTOCOL_VERSION = "VN_P5_S1_Q7_UNAPPROVED_V1"

_ALLOWED_OPERATIONAL_STATUS = frozenset(
    {"CANDIDATE", "OPERATING", "ON_HOLD", "DEMOTED"}
)
_ALLOWED_HORIZONS = frozenset({LEGACY_UNSPECIFIED, *EXPLICIT_HORIZONS})
_ALLOWED_REGIMES = frozenset(item.value for item in MarketRegime)


class StrategyChangeError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class StrategyApprovalProtocol:
    protocol_version: str
    activation_eligible: bool
    q7_precommitted: bool
    allowed_evidence_states: tuple[str, ...]
    allow_legacy_horizon: bool
    allow_explicit_horizons: bool
    source: str
    criteria: dict[str, Any]
    test_only: bool = False

    def payload(self) -> dict[str, Any]:
        return {
            "contract_version": STRATEGY_APPROVAL_PROTOCOL_CONTRACT_VERSION,
            "protocol_version": self.protocol_version,
            "activation_eligible": self.activation_eligible,
            "q7_precommitted": self.q7_precommitted,
            "allowed_evidence_states": sorted(
                {str(item) for item in self.allowed_evidence_states}
            ),
            "allow_legacy_horizon": self.allow_legacy_horizon,
            "allow_explicit_horizons": self.allow_explicit_horizons,
            "source": self.source,
            "criteria": self.criteria,
            "test_only": self.test_only,
        }

    @property
    def protocol_hash(self) -> str:
        return _digest(self.payload())


def production_blocked_approval_protocol() -> StrategyApprovalProtocol:
    return StrategyApprovalProtocol(
        protocol_version=PRODUCTION_BLOCKED_PROTOCOL_VERSION,
        activation_eligible=False,
        q7_precommitted=False,
        allowed_evidence_states=(),
        allow_legacy_horizon=True,
        allow_explicit_horizons=False,
        source="Q7_PROTOCOL_UNAPPROVED",
        criteria={},
        test_only=False,
    )


def test_only_approval_protocol(
    *,
    allowed_evidence_states: tuple[str, ...] = (
        "SAMPLE_SIZE_POLICY_UNDEFINED",
        "INSUFFICIENT_EVIDENCE",
    ),
) -> StrategyApprovalProtocol:
    """
    Synthetic protocol for automated pipeline tests only.

    Production callers cannot use it unless StrategyChangeService was
    explicitly constructed with allow_test_protocol=True.
    """
    return StrategyApprovalProtocol(
        protocol_version="VN_P5_S1_TEST_APPROVAL_PROTOCOL_V1",
        activation_eligible=True,
        q7_precommitted=True,
        allowed_evidence_states=allowed_evidence_states,
        allow_legacy_horizon=True,
        allow_explicit_horizons=False,
        source="TEST_ONLY_SYNTHETIC",
        criteria={
            "purpose": "exercise proposal-to-approval lifecycle",
            "production_thresholds": False,
        },
        test_only=True,
    )


def _default_baseline_provider() -> dict[str, str]:
    path = manifest_path(PROJECT_ROOT)
    manifest = load_manifest(path)
    verification = verify_baseline(PROJECT_ROOT, manifest)
    if not verification.valid:
        raise StrategyChangeError(
            "PRODUCTION_BASELINE_STALE",
            "현재 production code/policy가 고정된 Scanner baseline과 일치하지 않습니다.",
        )
    baseline_id = str(manifest.get("baseline_id") or "")
    production_fingerprint = str(
        manifest.get("production_fingerprint") or ""
    )
    policy_fingerprint = str(manifest.get("policy_fingerprint") or "")
    if not baseline_id or not production_fingerprint or not policy_fingerprint:
        raise StrategyChangeError(
            "PRODUCTION_BASELINE_INVALID",
            "Scanner production baseline의 필수 fingerprint가 없습니다.",
        )
    return {
        "scanner_baseline_id": baseline_id,
        "production_fingerprint": production_fingerprint,
        "production_policy_fingerprint": policy_fingerprint,
    }


class StrategyChangeService:
    """
    Owns Simulation-side strategy change proposals and approval artifacts.

    Approval is research/validation approval only. This service never publishes
    a Production Selection Policy, never changes Scanner behavior and never
    mutates Strategy Registry operational state.
    """

    def __init__(
        self,
        simulation_db: Path,
        *,
        evidence_service: StrategyEvidenceService | None = None,
        baseline_provider: Callable[[], dict[str, str]] | None = None,
        clock: Callable[[], str] | None = None,
        allow_test_protocol: bool = False,
    ) -> None:
        from datetime import datetime, timezone

        self.simulation_db = Path(simulation_db)
        self.evidence_service = evidence_service or StrategyEvidenceService(
            self.simulation_db
        )
        self.baseline_provider = baseline_provider or _default_baseline_provider
        self.clock = clock or (
            lambda: datetime.now(timezone.utc).isoformat()
        )
        self.allow_test_protocol = allow_test_protocol

    def _connect(self) -> sqlite3.Connection:
        if not self.simulation_db.is_file():
            raise StrategyChangeError(
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

    def _require_ready(self, conn: sqlite3.Connection) -> None:
        required = {
            "strategy_registry_version",
            "strategy_evaluation_artifact",
            "strategy_change_proposal",
            "strategy_change_proposal_evidence",
            "strategy_approval_artifact",
        }
        missing = sorted(required - self._tables(conn))
        if missing:
            raise StrategyChangeError(
                "STRATEGY_CHANGE_MIGRATION_REQUIRED",
                "P5-S1 Strategy Change schema가 준비되지 않았습니다: "
                + ", ".join(missing),
            )

    @staticmethod
    def _registry_rows(conn: sqlite3.Connection) -> list[sqlite3.Row]:
        return conn.execute(
            """
            SELECT strategy_version_id,strategy_key,definition_version,
                   definition_hash,fingerprint_contract_version,
                   implementation_key,operational_status,validation_status,
                   source,created_at,retired_at
            FROM strategy_registry_version
            ORDER BY strategy_key,strategy_version_id
            """
        ).fetchall()

    @classmethod
    def _registry_snapshots(
        cls,
        conn: sqlite3.Connection,
    ) -> tuple[list[dict[str, Any]], str, str]:
        rows = cls._registry_rows(conn)
        snapshot = [
            {
                "strategy_version_id": str(row["strategy_version_id"]),
                "strategy_key": str(row["strategy_key"]),
                "definition_version": str(row["definition_version"]),
                "definition_hash": str(row["definition_hash"]),
                "fingerprint_contract_version": str(
                    row["fingerprint_contract_version"]
                ),
                "implementation_key": str(row["implementation_key"]),
                "operational_status": str(row["operational_status"]),
                "validation_status": str(row["validation_status"]),
                "source": str(row["source"]),
                "retired_at": (
                    str(row["retired_at"])
                    if row["retired_at"] is not None
                    else None
                ),
            }
            for row in rows
        ]
        definition_set = [
            {
                "strategy_version_id": item["strategy_version_id"],
                "strategy_key": item["strategy_key"],
                "definition_hash": item["definition_hash"],
            }
            for item in snapshot
        ]
        return snapshot, _digest(snapshot), _digest(definition_set)

    @staticmethod
    def _normalize_scope(
        *,
        affected_horizons: list[str] | tuple[str, ...],
        affected_regimes: list[str] | tuple[str, ...],
        approval_protocol: StrategyApprovalProtocol | None = None,
    ) -> dict[str, Any]:
        horizons = sorted(
            {str(item).strip().upper() for item in affected_horizons}
        )
        regimes = sorted(
            {str(item).strip().upper() for item in affected_regimes}
        )
        if not horizons:
            raise StrategyChangeError(
                "PROPOSAL_HORIZON_SCOPE_REQUIRED",
                "변경 제안에는 영향 Horizon 범위가 필요합니다.",
            )
        if not regimes:
            raise StrategyChangeError(
                "PROPOSAL_REGIME_SCOPE_REQUIRED",
                "변경 제안에는 영향 Regime 범위가 필요합니다.",
            )
        invalid_horizon = sorted(set(horizons) - _ALLOWED_HORIZONS)
        if invalid_horizon:
            raise StrategyChangeError(
                "PROPOSAL_HORIZON_SCOPE_INVALID",
                "지원하지 않는 Horizon 범위입니다: "
                + ", ".join(invalid_horizon),
            )
        invalid_regime = sorted(set(regimes) - _ALLOWED_REGIMES)
        if invalid_regime:
            raise StrategyChangeError(
                "PROPOSAL_REGIME_SCOPE_INVALID",
                "지원하지 않는 Regime 범위입니다: "
                + ", ".join(invalid_regime),
            )
        return {
            "affected_horizons": horizons,
            "affected_regimes": regimes,
        }

    @staticmethod
    def _normalize_baseline(value: dict[str, str]) -> dict[str, str]:
        result = {
            "scanner_baseline_id": str(
                value.get("scanner_baseline_id") or ""
            ),
            "production_fingerprint": str(
                value.get("production_fingerprint") or ""
            ),
            "production_policy_fingerprint": str(
                value.get("production_policy_fingerprint") or ""
            ),
        }
        if not all(result.values()):
            raise StrategyChangeError(
                "PRODUCTION_BASELINE_INVALID",
                "Production baseline provider가 필수 fingerprint를 반환하지 않았습니다.",
            )
        return result

    @staticmethod
    def _change_set(
        registry: list[dict[str, Any]],
        changes: list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        if not changes:
            raise StrategyChangeError(
                "PROPOSAL_CHANGE_REQUIRED",
                "하나 이상의 Strategy 변경이 필요합니다.",
            )
        by_id = {
            item["strategy_version_id"]: item
            for item in registry
        }
        seen: set[str] = set()
        normalized: list[dict[str, Any]] = []
        post_status = {
            item["strategy_version_id"]: item["operational_status"]
            for item in registry
        }

        for raw in changes:
            strategy_version_id = str(
                raw.get("strategy_version_id") or ""
            ).strip()
            proposed = str(
                raw.get("proposed_operational_status") or ""
            ).strip().upper()
            if not strategy_version_id:
                raise StrategyChangeError(
                    "PROPOSAL_STRATEGY_VERSION_REQUIRED",
                    "Strategy Version ID가 필요합니다.",
                )
            if strategy_version_id in seen:
                raise StrategyChangeError(
                    "PROPOSAL_DUPLICATE_STRATEGY_VERSION",
                    "한 Proposal에서 같은 Strategy Version을 중복 변경할 수 없습니다.",
                )
            seen.add(strategy_version_id)
            row = by_id.get(strategy_version_id)
            if row is None:
                raise StrategyChangeError(
                    "STRATEGY_VERSION_NOT_FOUND",
                    f"Strategy Version을 찾을 수 없습니다: {strategy_version_id}",
                )
            if row["strategy_key"] == "no_trade":
                raise StrategyChangeError(
                    "NO_TRADE_NOT_STRATEGY",
                    "NO_TRADE safety path는 Strategy Pool 변경 대상이 아닙니다.",
                )
            if proposed not in _ALLOWED_OPERATIONAL_STATUS:
                raise StrategyChangeError(
                    "PROPOSAL_OPERATIONAL_STATUS_INVALID",
                    f"지원하지 않는 운영 상태입니다: {proposed}",
                )
            expected = str(row["operational_status"])
            if proposed == expected:
                raise StrategyChangeError(
                    "PROPOSAL_NOOP_CHANGE",
                    "현재 상태와 동일한 변경은 Proposal에 넣을 수 없습니다.",
                )
            supplied_expected = raw.get("expected_operational_status")
            if (
                supplied_expected is not None
                and str(supplied_expected).strip().upper() != expected
            ):
                raise StrategyChangeError(
                    "PROPOSAL_EXPECTED_STATUS_MISMATCH",
                    "요청한 expected status가 현재 Registry 상태와 다릅니다.",
                )

            normalized.append(
                {
                    "strategy_version_id": strategy_version_id,
                    "strategy_key": row["strategy_key"],
                    "definition_hash": row["definition_hash"],
                    "expected_operational_status": expected,
                    "proposed_operational_status": proposed,
                }
            )
            post_status[strategy_version_id] = proposed

        operating: list[dict[str, str]] = []
        operating_by_key: dict[str, str] = {}
        for item in registry:
            sid = item["strategy_version_id"]
            if post_status[sid] != "OPERATING":
                continue
            key = item["strategy_key"]
            if key in operating_by_key:
                raise StrategyChangeError(
                    "PROPOSAL_MULTIPLE_OPERATING_VERSION",
                    f"{key}에 둘 이상의 OPERATING version을 제안할 수 없습니다.",
                )
            operating_by_key[key] = sid
            operating.append(
                {
                    "strategy_version_id": sid,
                    "strategy_key": key,
                    "definition_hash": item["definition_hash"],
                }
            )
        if not operating:
            raise StrategyChangeError(
                "PROPOSAL_NO_OPERATING_STRATEGY",
                "제안 결과 최소 하나의 OPERATING Strategy가 필요합니다.",
            )

        normalized.sort(
            key=lambda item: (
                item["strategy_key"],
                item["strategy_version_id"],
            )
        )
        operating.sort(
            key=lambda item: (
                item["strategy_key"],
                item["strategy_version_id"],
            )
        )
        candidate_policy_intent = {
            "operating_strategies": operating,
            "operating_strategy_count": len(operating),
            "risk_gate_preserved": True,
            "no_trade_safety_path_preserved": True,
            "score_formula_changed": False,
            "candidate_priority_changed": False,
            "production_activation_performed": False,
        }
        return normalized, candidate_policy_intent

    def _evidence_bundle(
        self,
        *,
        changed_version_ids: set[str],
        artifact_ids: list[str] | tuple[str, ...],
    ) -> tuple[list[dict[str, Any]], str]:
        unique_ids = [str(item).strip() for item in artifact_ids]
        if not unique_ids or any(not item for item in unique_ids):
            raise StrategyChangeError(
                "PROPOSAL_EVIDENCE_REQUIRED",
                "Proposal에는 하나 이상의 Evaluation Artifact가 필요합니다.",
            )
        if len(unique_ids) != len(set(unique_ids)):
            raise StrategyChangeError(
                "PROPOSAL_DUPLICATE_EVIDENCE",
                "같은 Evaluation Artifact를 중복 연결할 수 없습니다.",
            )

        bundle: list[dict[str, Any]] = []
        covered: set[str] = set()
        for artifact_id in unique_ids:
            try:
                artifact = self.evidence_service.get_artifact(
                    artifact_id,
                    verify_source=True,
                )
            except Exception as exc:
                raise StrategyChangeError(
                    "PROPOSAL_EVIDENCE_NOT_AVAILABLE",
                    f"Evaluation Artifact를 검증할 수 없습니다: {artifact_id}: {exc}",
                ) from exc
            if artifact.get("artifact_integrity") != "MATCH":
                raise StrategyChangeError(
                    "PROPOSAL_EVIDENCE_HASH_MISMATCH",
                    f"Evaluation Artifact hash가 일치하지 않습니다: {artifact_id}",
                )
            if artifact.get("current_source_status") != "CURRENT":
                raise StrategyChangeError(
                    "PROPOSAL_EVIDENCE_SOURCE_STALE",
                    f"Evaluation Artifact 원본이 현재 유효하지 않습니다: {artifact_id}",
                )
            sid = str(artifact["strategy_version_id"])
            if sid not in changed_version_ids:
                raise StrategyChangeError(
                    "PROPOSAL_EVIDENCE_STRATEGY_MISMATCH",
                    "변경 대상 Strategy Version과 Evidence Artifact가 일치하지 않습니다.",
                )
            covered.add(sid)
            bundle.append(
                {
                    "artifact_id": artifact_id,
                    "artifact_hash": str(artifact["artifact_hash"]),
                    "strategy_version_id": sid,
                    "strategy_key": str(artifact["strategy_key"]),
                    "source_kind": str(artifact["source_kind"]),
                    "evidence_state": str(artifact["evidence_state"]),
                    "source_report_id": str(artifact["source_report_id"]),
                    "source_set_hash": str(artifact["source_set_hash"]),
                }
            )
        missing = sorted(changed_version_ids - covered)
        if missing:
            raise StrategyChangeError(
                "PROPOSAL_EVIDENCE_COVERAGE_INCOMPLETE",
                "모든 변경 대상 Strategy Version에 근거가 필요합니다: "
                + ", ".join(missing),
            )
        bundle.sort(
            key=lambda item: (
                item["strategy_version_id"],
                item["artifact_id"],
            )
        )
        return bundle, _digest(bundle)

    @staticmethod
    def _approval_gate_state(
        scope: dict[str, Any],
        protocol: StrategyApprovalProtocol,
    ) -> tuple[str, dict[str, Any]]:
        catalog = horizon_policy_catalog()
        explicit = [
            item
            for item in scope["affected_horizons"]
            if item != LEGACY_UNSPECIFIED
        ]
        horizon_approved = bool(catalog.get("numeric_policy_approved"))
        if explicit and not horizon_approved:
            state = "BLOCKED_HORIZON_POLICY"
        elif not protocol.activation_eligible or not protocol.q7_precommitted:
            state = "REVIEW_ONLY_Q7_UNAPPROVED"
        else:
            state = "APPROVAL_ELIGIBLE"
        return (
            state,
            {
                "q7_protocol_approved": bool(
                    protocol.activation_eligible
                    and protocol.q7_precommitted
                ),
                "proposal_protocol_version": protocol.protocol_version,
                "proposal_protocol_hash": protocol.protocol_hash,
                "horizon_numeric_policy_approved": horizon_approved,
                "automatic_rotation_enabled": False,
                "production_activation_performed": False,
            },
        )

    @staticmethod
    def _proposal_payload(
        *,
        client_request_id: str,
        base_registry_snapshot_hash: str,
        base_strategy_set_fingerprint: str,
        change_set: list[dict[str, Any]],
        change_set_hash: str,
        scope: dict[str, Any],
        candidate_policy_intent: dict[str, Any],
        candidate_policy_intent_hash: str,
        evidence_bundle_hash: str,
        rollback_basis: dict[str, Any],
        rollback_basis_hash: str,
        baseline: dict[str, str],
        proposal_protocol_version: str,
        proposal_protocol_hash: str,
        approval_gate_state: str,
        limitations: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "proposal_version": STRATEGY_CHANGE_PROPOSAL_VERSION,
            "client_request_id": client_request_id,
            "base_registry_snapshot_hash": base_registry_snapshot_hash,
            "base_strategy_set_fingerprint": base_strategy_set_fingerprint,
            "change_set": change_set,
            "change_set_hash": change_set_hash,
            "scope": scope,
            "candidate_policy_intent": candidate_policy_intent,
            "candidate_policy_intent_hash": candidate_policy_intent_hash,
            "evidence_bundle_hash": evidence_bundle_hash,
            "rollback_basis": rollback_basis,
            "rollback_basis_hash": rollback_basis_hash,
            "scanner_baseline_id": baseline["scanner_baseline_id"],
            "production_fingerprint": baseline["production_fingerprint"],
            "production_policy_fingerprint": baseline[
                "production_policy_fingerprint"
            ],
            "proposal_protocol_version": proposal_protocol_version,
            "proposal_protocol_hash": proposal_protocol_hash,
            "approval_gate_state": approval_gate_state,
            "limitations": limitations,
        }

    @staticmethod
    def _proposal_from_row(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": str(row["id"]),
            "proposal_version": str(row["proposal_version"]),
            "client_request_id": str(row["client_request_id"]),
            "base_registry_snapshot_hash": str(
                row["base_registry_snapshot_hash"]
            ),
            "base_strategy_set_fingerprint": str(
                row["base_strategy_set_fingerprint"]
            ),
            "change_set": json.loads(str(row["change_set_json"])),
            "change_set_hash": str(row["change_set_hash"]),
            "scope": json.loads(str(row["scope_json"])),
            "candidate_policy_intent": json.loads(
                str(row["candidate_policy_intent_json"])
            ),
            "candidate_policy_intent_hash": str(
                row["candidate_policy_intent_hash"]
            ),
            "evidence_bundle_hash": str(row["evidence_bundle_hash"]),
            "rollback_basis": json.loads(str(row["rollback_basis_json"])),
            "rollback_basis_hash": str(row["rollback_basis_hash"]),
            "scanner_baseline_id": str(row["scanner_baseline_id"]),
            "production_fingerprint": str(row["production_fingerprint"]),
            "production_policy_fingerprint": str(
                row["production_policy_fingerprint"]
            ),
            "proposal_protocol_version": str(
                row["proposal_protocol_version"]
            ),
            "proposal_protocol_hash": str(row["proposal_protocol_hash"]),
            "approval_gate_state": str(row["approval_gate_state"]),
            "limitations": json.loads(str(row["limitations_json"])),
            "proposal_hash": str(row["proposal_hash"]),
            "created_at": str(row["created_at"]),
        }

    def _proposal_evidence_rows(
        self,
        conn: sqlite3.Connection,
        proposal_id: str,
    ) -> list[dict[str, Any]]:
        rows = conn.execute(
            """
            SELECT sequence,artifact_id,artifact_hash,strategy_version_id,
                   source_kind,evidence_state
            FROM strategy_change_proposal_evidence
            WHERE proposal_id=?
            ORDER BY sequence,artifact_id
            """,
            (proposal_id,),
        ).fetchall()
        return [
            {
                "sequence": int(row["sequence"]),
                "artifact_id": str(row["artifact_id"]),
                "artifact_hash": str(row["artifact_hash"]),
                "strategy_version_id": str(row["strategy_version_id"]),
                "source_kind": str(row["source_kind"]),
                "evidence_state": str(row["evidence_state"]),
            }
            for row in rows
        ]

    def create_proposal(
        self,
        *,
        client_request_id: str,
        changes: list[dict[str, Any]],
        evidence_artifact_ids: list[str] | tuple[str, ...],
        affected_horizons: list[str] | tuple[str, ...],
        affected_regimes: list[str] | tuple[str, ...],
    ) -> dict[str, Any]:
        request_id = client_request_id.strip()
        if not request_id:
            raise StrategyChangeError(
                "PROPOSAL_IDEMPOTENCY_KEY_REQUIRED",
                "Change Proposal 생성에는 client_request_id가 필요합니다.",
            )

        proposal_protocol = (
            approval_protocol or production_blocked_approval_protocol()
        )
        if proposal_protocol.test_only and not self.allow_test_protocol:
            raise StrategyChangeError(
                "TEST_APPROVAL_PROTOCOL_FORBIDDEN",
                "TEST-only approval protocol은 production 경로에서 사용할 수 없습니다.",
            )

        baseline = self._normalize_baseline(self.baseline_provider())
        scope = self._normalize_scope(
            affected_horizons=affected_horizons,
            affected_regimes=affected_regimes,
        )

        with self._connect() as conn:
            self._require_ready(conn)
            existing = conn.execute(
                """
                SELECT * FROM strategy_change_proposal
                WHERE client_request_id=?
                """,
                (request_id,),
            ).fetchone()

            registry, registry_hash, strategy_set_fp = (
                self._registry_snapshots(conn)
            )
            change_set, candidate_policy_intent = self._change_set(
                registry,
                changes,
            )
            changed_ids = {
                item["strategy_version_id"] for item in change_set
            }
            evidence_bundle, evidence_bundle_hash = self._evidence_bundle(
                changed_version_ids=changed_ids,
                artifact_ids=evidence_artifact_ids,
            )
            change_set_hash = _digest(change_set)
            candidate_intent_hash = _digest(candidate_policy_intent)

            current_operating = [
                {
                    "strategy_version_id": item["strategy_version_id"],
                    "strategy_key": item["strategy_key"],
                    "definition_hash": item["definition_hash"],
                }
                for item in registry
                if item["operational_status"] == "OPERATING"
            ]
            current_operating.sort(
                key=lambda item: (
                    item["strategy_key"],
                    item["strategy_version_id"],
                )
            )
            rollback_basis = {
                "registry_snapshot_hash": registry_hash,
                "strategy_set_fingerprint": strategy_set_fp,
                "operating_strategies": current_operating,
                "scanner_baseline_id": baseline["scanner_baseline_id"],
                "production_fingerprint": baseline[
                    "production_fingerprint"
                ],
                "production_policy_fingerprint": baseline[
                    "production_policy_fingerprint"
                ],
                "production_policy_reference_created": False,
            }
            rollback_basis_hash = _digest(rollback_basis)
            gate_state, gate_limits = self._approval_gate_state(
                scope,
                proposal_protocol,
            )
            limitations = {
                **gate_limits,
                "performance_ranking_created": False,
                "minimum_sample_threshold_invented": False,
                "approval_is_production_activation": False,
                "risk_gate_change_allowed": False,
                "no_trade_change_allowed": False,
            }
            payload = self._proposal_payload(
                client_request_id=request_id,
                base_registry_snapshot_hash=registry_hash,
                base_strategy_set_fingerprint=strategy_set_fp,
                change_set=change_set,
                change_set_hash=change_set_hash,
                scope=scope,
                candidate_policy_intent=candidate_policy_intent,
                candidate_policy_intent_hash=candidate_intent_hash,
                evidence_bundle_hash=evidence_bundle_hash,
                rollback_basis=rollback_basis,
                rollback_basis_hash=rollback_basis_hash,
                baseline=baseline,
                proposal_protocol_version=proposal_protocol.protocol_version,
                proposal_protocol_hash=proposal_protocol.protocol_hash,
                approval_gate_state=gate_state,
                limitations=limitations,
            )
            proposal_hash = _digest(payload)
            proposal_id = str(
                uuid5(
                    NAMESPACE_URL,
                    (
                        "stockscope:strategy-change:"
                        f"{STRATEGY_CHANGE_PROPOSAL_VERSION}:"
                        f"{request_id}:{proposal_hash}"
                    ),
                )
            )

            if existing is not None:
                current = self._proposal_from_row(existing)
                if current["proposal_hash"] != proposal_hash:
                    raise StrategyChangeError(
                        "PROPOSAL_IDEMPOTENCY_CONFLICT",
                        "동일 client_request_id에 다른 Proposal 내용이 존재합니다.",
                    )
                current["evidence"] = self._proposal_evidence_rows(
                    conn,
                    current["id"],
                )
                return current

            conn.execute(
                """
                INSERT INTO strategy_change_proposal(
                    id,proposal_version,client_request_id,
                    base_registry_snapshot_hash,base_strategy_set_fingerprint,
                    change_set_json,change_set_hash,scope_json,
                    candidate_policy_intent_json,candidate_policy_intent_hash,
                    evidence_bundle_hash,rollback_basis_json,
                    rollback_basis_hash,scanner_baseline_id,
                    production_fingerprint,production_policy_fingerprint,
                    proposal_protocol_version,proposal_protocol_hash,
                    approval_gate_state,limitations_json,proposal_hash,
                    created_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    proposal_id,
                    STRATEGY_CHANGE_PROPOSAL_VERSION,
                    request_id,
                    registry_hash,
                    strategy_set_fp,
                    _canonical_json(change_set),
                    change_set_hash,
                    _canonical_json(scope),
                    _canonical_json(candidate_policy_intent),
                    candidate_intent_hash,
                    evidence_bundle_hash,
                    _canonical_json(rollback_basis),
                    rollback_basis_hash,
                    baseline["scanner_baseline_id"],
                    baseline["production_fingerprint"],
                    baseline["production_policy_fingerprint"],
                    proposal_protocol.protocol_version,
                    proposal_protocol.protocol_hash,
                    gate_state,
                    _canonical_json(limitations),
                    proposal_hash,
                    self.clock(),
                ),
            )
            for sequence, item in enumerate(evidence_bundle, start=1):
                conn.execute(
                    """
                    INSERT INTO strategy_change_proposal_evidence(
                        proposal_id,sequence,artifact_id,artifact_hash,
                        strategy_version_id,source_kind,evidence_state
                    ) VALUES(?,?,?,?,?,?,?)
                    """,
                    (
                        proposal_id,
                        sequence,
                        item["artifact_id"],
                        item["artifact_hash"],
                        item["strategy_version_id"],
                        item["source_kind"],
                        item["evidence_state"],
                    ),
                )

            row = conn.execute(
                "SELECT * FROM strategy_change_proposal WHERE id=?",
                (proposal_id,),
            ).fetchone()
            if row is None:
                raise StrategyChangeError(
                    "PROPOSAL_INSERT_FAILED",
                    "Strategy Change Proposal 저장에 실패했습니다.",
                )
            result = self._proposal_from_row(row)
            result["evidence"] = self._proposal_evidence_rows(
                conn,
                proposal_id,
            )
            return result

    def _proposal_expected_hash(self, proposal: dict[str, Any]) -> str:
        baseline = {
            "scanner_baseline_id": proposal["scanner_baseline_id"],
            "production_fingerprint": proposal["production_fingerprint"],
            "production_policy_fingerprint": proposal[
                "production_policy_fingerprint"
            ],
        }
        return _digest(
            self._proposal_payload(
                client_request_id=proposal["client_request_id"],
                base_registry_snapshot_hash=proposal[
                    "base_registry_snapshot_hash"
                ],
                base_strategy_set_fingerprint=proposal[
                    "base_strategy_set_fingerprint"
                ],
                change_set=proposal["change_set"],
                change_set_hash=proposal["change_set_hash"],
                scope=proposal["scope"],
                candidate_policy_intent=proposal[
                    "candidate_policy_intent"
                ],
                candidate_policy_intent_hash=proposal[
                    "candidate_policy_intent_hash"
                ],
                evidence_bundle_hash=proposal["evidence_bundle_hash"],
                rollback_basis=proposal["rollback_basis"],
                rollback_basis_hash=proposal["rollback_basis_hash"],
                baseline=baseline,
                proposal_protocol_version=proposal[
                    "proposal_protocol_version"
                ],
                proposal_protocol_hash=proposal[
                    "proposal_protocol_hash"
                ],
                approval_gate_state=proposal["approval_gate_state"],
                limitations=proposal["limitations"],
            )
        )

    def get_proposal(self, proposal_id: str) -> dict[str, Any]:
        with self._connect() as conn:
            self._require_ready(conn)
            row = conn.execute(
                "SELECT * FROM strategy_change_proposal WHERE id=?",
                (proposal_id,),
            ).fetchone()
            if row is None:
                raise StrategyChangeError(
                    "PROPOSAL_NOT_FOUND",
                    "Strategy Change Proposal을 찾을 수 없습니다.",
                )
            result = self._proposal_from_row(row)
            result["evidence"] = self._proposal_evidence_rows(
                conn,
                proposal_id,
            )
            result["proposal_integrity"] = (
                "MATCH"
                if self._proposal_expected_hash(result)
                == result["proposal_hash"]
                else "HASH_MISMATCH"
            )
            return result

    def verify_proposal(self, proposal_id: str) -> dict[str, Any]:
        proposal = self.get_proposal(proposal_id)
        reasons: list[str] = []

        if proposal["proposal_integrity"] != "MATCH":
            reasons.append("PROPOSAL_HASH_MISMATCH")
        if _digest(proposal["change_set"]) != proposal["change_set_hash"]:
            reasons.append("CHANGE_SET_HASH_MISMATCH")
        if (
            _digest(proposal["candidate_policy_intent"])
            != proposal["candidate_policy_intent_hash"]
        ):
            reasons.append("CANDIDATE_POLICY_INTENT_HASH_MISMATCH")
        if (
            _digest(proposal["rollback_basis"])
            != proposal["rollback_basis_hash"]
        ):
            reasons.append("ROLLBACK_BASIS_HASH_MISMATCH")

        with self._connect() as conn:
            self._require_ready(conn)
            registry, registry_hash, strategy_set_fp = (
                self._registry_snapshots(conn)
            )
            if registry_hash != proposal["base_registry_snapshot_hash"]:
                reasons.append("REGISTRY_SNAPSHOT_CHANGED")
            if (
                strategy_set_fp
                != proposal["base_strategy_set_fingerprint"]
            ):
                reasons.append("STRATEGY_SET_CHANGED")
            by_id = {
                item["strategy_version_id"]: item for item in registry
            }
            for change in proposal["change_set"]:
                row = by_id.get(change["strategy_version_id"])
                if row is None:
                    reasons.append(
                        "STRATEGY_VERSION_MISSING:"
                        + change["strategy_version_id"]
                    )
                    continue
                if row["definition_hash"] != change["definition_hash"]:
                    reasons.append(
                        "STRATEGY_DEFINITION_CHANGED:"
                        + change["strategy_version_id"]
                    )
                if (
                    row["operational_status"]
                    != change["expected_operational_status"]
                ):
                    reasons.append(
                        "STRATEGY_STATUS_CHANGED:"
                        + change["strategy_version_id"]
                    )

        live_evidence: list[dict[str, Any]] = []
        for row in proposal["evidence"]:
            try:
                artifact = self.evidence_service.get_artifact(
                    row["artifact_id"],
                    verify_source=True,
                )
            except Exception:
                reasons.append(
                    "EVIDENCE_MISSING:" + row["artifact_id"]
                )
                continue
            live = {
                "artifact_id": row["artifact_id"],
                "artifact_hash": str(artifact.get("artifact_hash") or ""),
                "strategy_version_id": str(
                    artifact.get("strategy_version_id") or ""
                ),
                "source_kind": str(artifact.get("source_kind") or ""),
                "evidence_state": str(
                    artifact.get("evidence_state") or ""
                ),
            }
            live_evidence.append(live)
            if artifact.get("artifact_integrity") != "MATCH":
                reasons.append(
                    "EVIDENCE_HASH_MISMATCH:" + row["artifact_id"]
                )
            if artifact.get("current_source_status") != "CURRENT":
                reasons.append(
                    "EVIDENCE_SOURCE_STALE:" + row["artifact_id"]
                )
            if live["artifact_hash"] != row["artifact_hash"]:
                reasons.append(
                    "EVIDENCE_REFERENCE_CHANGED:" + row["artifact_id"]
                )
            if (
                live["strategy_version_id"]
                != row["strategy_version_id"]
            ):
                reasons.append(
                    "EVIDENCE_STRATEGY_CHANGED:" + row["artifact_id"]
                )

        bundle_for_hash = [
            {
                "artifact_id": row["artifact_id"],
                "artifact_hash": row["artifact_hash"],
                "strategy_version_id": row["strategy_version_id"],
                "strategy_key": str(
                    self.evidence_service.get_artifact(
                        row["artifact_id"],
                        verify_source=False,
                    ).get("strategy_key")
                    or ""
                ),
                "source_kind": row["source_kind"],
                "evidence_state": row["evidence_state"],
                "source_report_id": str(
                    self.evidence_service.get_artifact(
                        row["artifact_id"],
                        verify_source=False,
                    ).get("source_report_id")
                    or ""
                ),
                "source_set_hash": str(
                    self.evidence_service.get_artifact(
                        row["artifact_id"],
                        verify_source=False,
                    ).get("source_set_hash")
                    or ""
                ),
            }
            for row in proposal["evidence"]
            if not any(
                reason.endswith(row["artifact_id"])
                and reason.startswith("EVIDENCE_MISSING:")
                for reason in reasons
            )
        ]
        bundle_for_hash.sort(
            key=lambda item: (
                item["strategy_version_id"],
                item["artifact_id"],
            )
        )
        if (
            len(bundle_for_hash) != len(proposal["evidence"])
            or _digest(bundle_for_hash)
            != proposal["evidence_bundle_hash"]
        ):
            reasons.append("EVIDENCE_BUNDLE_CHANGED")

        try:
            baseline = self._normalize_baseline(self.baseline_provider())
        except Exception:
            baseline = None
            reasons.append("PRODUCTION_BASELINE_UNAVAILABLE")
        if baseline is not None:
            if (
                baseline["scanner_baseline_id"]
                != proposal["scanner_baseline_id"]
                or baseline["production_fingerprint"]
                != proposal["production_fingerprint"]
                or baseline["production_policy_fingerprint"]
                != proposal["production_policy_fingerprint"]
            ):
                reasons.append("PRODUCTION_BASELINE_CHANGED")

        unique_reasons = sorted(set(reasons))
        return {
            "proposal_id": proposal_id,
            "status": "CURRENT" if not unique_reasons else "STALE",
            "reasons": unique_reasons,
            "proposal_integrity": proposal["proposal_integrity"],
            "approval_gate_state": proposal["approval_gate_state"],
            "live_evidence": live_evidence,
        }

    @staticmethod
    def _approval_from_row(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": str(row["id"]),
            "approval_version": str(row["approval_version"]),
            "proposal_id": str(row["proposal_id"]),
            "proposal_hash": str(row["proposal_hash"]),
            "approval_protocol_version": str(
                row["approval_protocol_version"]
            ),
            "approval_protocol_hash": str(row["approval_protocol_hash"]),
            "evidence_bundle_hash": str(row["evidence_bundle_hash"]),
            "registry_snapshot_hash": str(row["registry_snapshot_hash"]),
            "candidate_policy_intent_hash": str(
                row["candidate_policy_intent_hash"]
            ),
            "rollback_basis_hash": str(row["rollback_basis_hash"]),
            "source_verification": json.loads(
                str(row["source_verification_json"])
            ),
            "approval_context": json.loads(
                str(row["approval_context_json"])
            ),
            "approval_hash": str(row["approval_hash"]),
            "approved_at": str(row["approved_at"]),
        }

    @staticmethod
    def _approval_payload(
        *,
        proposal: dict[str, Any],
        protocol: StrategyApprovalProtocol,
        source_verification: dict[str, Any],
        approval_context: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "approval_version": STRATEGY_APPROVAL_ARTIFACT_VERSION,
            "proposal_id": proposal["id"],
            "proposal_hash": proposal["proposal_hash"],
            "approval_protocol_version": protocol.protocol_version,
            "approval_protocol_hash": protocol.protocol_hash,
            "evidence_bundle_hash": proposal["evidence_bundle_hash"],
            "registry_snapshot_hash": proposal[
                "base_registry_snapshot_hash"
            ],
            "candidate_policy_intent_hash": proposal[
                "candidate_policy_intent_hash"
            ],
            "rollback_basis_hash": proposal["rollback_basis_hash"],
            "source_verification": source_verification,
            "approval_context": approval_context,
        }

    def approve_proposal(
        self,
        *,
        proposal_id: str,
        protocol: StrategyApprovalProtocol | None = None,
        approved_by: str = "LOCAL_USER",
    ) -> dict[str, Any]:
        active_protocol = protocol or production_blocked_approval_protocol()
        if active_protocol.test_only and not self.allow_test_protocol:
            raise StrategyChangeError(
                "TEST_APPROVAL_PROTOCOL_FORBIDDEN",
                "TEST-only approval protocol은 production 경로에서 사용할 수 없습니다.",
            )
        if not active_protocol.activation_eligible:
            raise StrategyChangeError(
                "Q7_APPROVAL_PROTOCOL_UNAPPROVED",
                "Q7 평가 기준이 사전 승인되지 않아 Strategy 운영 변경을 승인할 수 없습니다.",
            )
        if not active_protocol.q7_precommitted:
            raise StrategyChangeError(
                "Q7_APPROVAL_PROTOCOL_NOT_PRECOMMITTED",
                "승인 기준은 평가 결과를 보기 전에 고정되어야 합니다.",
            )

        proposal = self.get_proposal(proposal_id)
        if (
            proposal["proposal_protocol_version"]
            != active_protocol.protocol_version
            or proposal["proposal_protocol_hash"]
            != active_protocol.protocol_hash
        ):
            raise StrategyChangeError(
                "APPROVAL_PROTOCOL_CHANGED_SINCE_PROPOSAL",
                "Proposal 생성 후 Approval Protocol이 변경되어 새 Proposal이 필요합니다.",
            )
        if proposal["approval_gate_state"] != "APPROVAL_ELIGIBLE":
            raise StrategyChangeError(
                "PROPOSAL_NOT_APPROVAL_ELIGIBLE",
                "이 Proposal은 생성 시점의 정책 기준에서 승인 가능 상태가 아닙니다.",
            )
        verification = self.verify_proposal(proposal_id)
        if verification["status"] != "CURRENT":
            raise StrategyChangeError(
                "PROPOSAL_STALE",
                "Proposal의 Registry/Evidence/Baseline이 변경되어 재검증이 필요합니다.",
            )

        horizons = proposal["scope"]["affected_horizons"]
        explicit = [
            item for item in horizons if item != LEGACY_UNSPECIFIED
        ]
        catalog = horizon_policy_catalog()
        if explicit and not bool(catalog.get("numeric_policy_approved")):
            raise StrategyChangeError(
                "HORIZON_POLICY_NOT_APPROVED",
                "명시적 Horizon 수치 정책이 승인되지 않아 운영 변경을 승인할 수 없습니다.",
            )
        if explicit and not active_protocol.allow_explicit_horizons:
            raise StrategyChangeError(
                "APPROVAL_PROTOCOL_HORIZON_UNSUPPORTED",
                "Approval Protocol이 명시적 Horizon 변경을 지원하지 않습니다.",
            )
        if (
            LEGACY_UNSPECIFIED in horizons
            and not active_protocol.allow_legacy_horizon
        ):
            raise StrategyChangeError(
                "APPROVAL_PROTOCOL_HORIZON_UNSUPPORTED",
                "Approval Protocol이 legacy Horizon을 지원하지 않습니다.",
            )

        allowed_states = set(active_protocol.allowed_evidence_states)
        evidence_states = {
            str(row["evidence_state"]) for row in proposal["evidence"]
        }
        unsupported_states = sorted(evidence_states - allowed_states)
        if unsupported_states:
            raise StrategyChangeError(
                "APPROVAL_EVIDENCE_STATE_NOT_ALLOWED",
                "Approval Protocol이 허용하지 않는 evidence state입니다: "
                + ", ".join(unsupported_states),
            )

        approved_by_value = approved_by.strip()
        if not approved_by_value:
            raise StrategyChangeError(
                "APPROVAL_ACTOR_REQUIRED",
                "Approval Artifact에는 승인 주체가 필요합니다.",
            )
        source_verification = {
            "verified_at_approval": True,
            "proposal_verification": verification,
            "evidence_source_status_required": "CURRENT",
        }
        approval_context = {
            "approved_by": approved_by_value,
            "approval_mode": "EXPLICIT",
            "research_validation_approval_only": True,
            "production_activation_performed": False,
            "automatic_rotation_enabled": False,
            "protocol": active_protocol.payload(),
        }
        payload = self._approval_payload(
            proposal=proposal,
            protocol=active_protocol,
            source_verification=source_verification,
            approval_context=approval_context,
        )
        approval_hash = _digest(payload)
        approval_id = str(
            uuid5(
                NAMESPACE_URL,
                (
                    "stockscope:strategy-approval:"
                    f"{STRATEGY_APPROVAL_ARTIFACT_VERSION}:"
                    f"{proposal['id']}:{proposal['proposal_hash']}:"
                    f"{active_protocol.protocol_hash}:"
                    f"{proposal['evidence_bundle_hash']}"
                ),
            )
        )

        with self._connect() as conn:
            self._require_ready(conn)
            existing = conn.execute(
                """
                SELECT * FROM strategy_approval_artifact
                WHERE id=?
                """,
                (approval_id,),
            ).fetchone()
            if existing is not None:
                result = self._approval_from_row(existing)
                if result["approval_hash"] != approval_hash:
                    raise StrategyChangeError(
                        "APPROVAL_IDENTITY_CONFLICT",
                        "동일 Approval identity에 다른 payload가 존재합니다.",
                    )
                return result

            conn.execute(
                """
                INSERT INTO strategy_approval_artifact(
                    id,approval_version,proposal_id,proposal_hash,
                    approval_protocol_version,approval_protocol_hash,
                    evidence_bundle_hash,registry_snapshot_hash,
                    candidate_policy_intent_hash,rollback_basis_hash,
                    source_verification_json,approval_context_json,
                    approval_hash,approved_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    approval_id,
                    STRATEGY_APPROVAL_ARTIFACT_VERSION,
                    proposal["id"],
                    proposal["proposal_hash"],
                    active_protocol.protocol_version,
                    active_protocol.protocol_hash,
                    proposal["evidence_bundle_hash"],
                    proposal["base_registry_snapshot_hash"],
                    proposal["candidate_policy_intent_hash"],
                    proposal["rollback_basis_hash"],
                    _canonical_json(source_verification),
                    _canonical_json(approval_context),
                    approval_hash,
                    self.clock(),
                ),
            )
            row = conn.execute(
                "SELECT * FROM strategy_approval_artifact WHERE id=?",
                (approval_id,),
            ).fetchone()
            if row is None:
                raise StrategyChangeError(
                    "APPROVAL_INSERT_FAILED",
                    "Strategy Approval Artifact 저장에 실패했습니다.",
                )
            return self._approval_from_row(row)

    def get_approval(self, approval_id: str) -> dict[str, Any]:
        with self._connect() as conn:
            self._require_ready(conn)
            row = conn.execute(
                """
                SELECT * FROM strategy_approval_artifact
                WHERE id=?
                """,
                (approval_id,),
            ).fetchone()
            if row is None:
                raise StrategyChangeError(
                    "APPROVAL_NOT_FOUND",
                    "Strategy Approval Artifact를 찾을 수 없습니다.",
                )
            result = self._approval_from_row(row)

        proposal = self.get_proposal(result["proposal_id"])
        context = result["approval_context"]
        protocol_payload = context.get("protocol") or {}
        protocol_hash = _digest(protocol_payload)
        result["approval_integrity"] = (
            "MATCH"
            if (
                result["proposal_hash"] == proposal["proposal_hash"]
                and result["approval_protocol_hash"] == protocol_hash
                and result["evidence_bundle_hash"]
                == proposal["evidence_bundle_hash"]
                and result["registry_snapshot_hash"]
                == proposal["base_registry_snapshot_hash"]
                and result["candidate_policy_intent_hash"]
                == proposal["candidate_policy_intent_hash"]
                and result["rollback_basis_hash"]
                == proposal["rollback_basis_hash"]
                and _digest(
                    {
                        "approval_version": result["approval_version"],
                        "proposal_id": result["proposal_id"],
                        "proposal_hash": result["proposal_hash"],
                        "approval_protocol_version": result[
                            "approval_protocol_version"
                        ],
                        "approval_protocol_hash": result[
                            "approval_protocol_hash"
                        ],
                        "evidence_bundle_hash": result[
                            "evidence_bundle_hash"
                        ],
                        "registry_snapshot_hash": result[
                            "registry_snapshot_hash"
                        ],
                        "candidate_policy_intent_hash": result[
                            "candidate_policy_intent_hash"
                        ],
                        "rollback_basis_hash": result[
                            "rollback_basis_hash"
                        ],
                        "source_verification": result[
                            "source_verification"
                        ],
                        "approval_context": result["approval_context"],
                    }
                )
                == result["approval_hash"]
            )
            else "HASH_MISMATCH"
        )
        return result
