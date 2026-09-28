from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from app.core.config import PROJECT_ROOT
from app.strategy.models import StrategyName

SELECTION_POLICY_SCHEMA_VERSION = 1
SELECTION_POLICY_CONTRACT_VERSION = "VN_P5_S1_SELECTION_POLICY_V1"
ACTIVE_REFERENCE_SCHEMA_VERSION = 1
LEGACY_POLICY_ID = "LEGACY_CURRENT_10_FALLBACK"

DEFAULT_RUNTIME_DIR = (
    PROJECT_ROOT / "backend" / "runtime" / "strategy_selection"
)
DEFAULT_SIMULATION_DB = (
    PROJECT_ROOT / "backend" / "runtime" / "simulation" / "simulation.db"
)


class SelectionPolicyError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True, slots=True)
class SelectionPolicyPin:
    policy_id: str
    policy_hash: str
    policy_contract_version: str
    policy_source: str
    fallback_used: bool
    fallback_reason: str | None
    operating_strategies: tuple[tuple[str | None, str, str | None], ...]
    scanner_baseline_id: str | None
    production_fingerprint: str | None
    production_policy_fingerprint: str | None

    @property
    def operating_strategy_keys(self) -> tuple[str, ...]:
        return tuple(item[1] for item in self.operating_strategies)

    @property
    def cache_token(self) -> str:
        return f"{self.policy_contract_version}-{self.policy_hash[:16]}"

    def strategy_reference(self, strategy_key: str) -> dict[str, str | None] | None:
        for strategy_version_id, key, definition_hash in self.operating_strategies:
            if key == strategy_key:
                return {
                    "strategy_version_id": strategy_version_id,
                    "strategy_key": key,
                    "definition_hash": definition_hash,
                }
        return None

    def metadata(self) -> dict[str, Any]:
        return {
            "policy_id": self.policy_id,
            "policy_hash": self.policy_hash,
            "policy_contract_version": self.policy_contract_version,
            "policy_source": self.policy_source,
            "fallback_used": self.fallback_used,
            "fallback_reason": self.fallback_reason,
            "operating_strategy_count": len(self.operating_strategies),
            "scanner_baseline_id": self.scanner_baseline_id,
            "production_fingerprint": self.production_fingerprint,
            "production_policy_fingerprint": self.production_policy_fingerprint,
        }

    def persisted_snapshot(self) -> dict[str, Any]:
        return {
            **self.metadata(),
            "operating_strategies": [
                {
                    "strategy_version_id": strategy_version_id,
                    "strategy_key": strategy_key,
                    "definition_hash": definition_hash,
                }
                for strategy_version_id, strategy_key, definition_hash
                in self.operating_strategies
            ],
        }

    @classmethod
    def from_persisted_snapshot(cls, payload: dict[str, Any]) -> "SelectionPolicyPin":
        strategies = payload.get("operating_strategies")
        if not isinstance(strategies, list) or not strategies:
            raise SelectionPolicyError(
                "SELECTION_POLICY_PIN_INVALID",
                "저장된 Selection Policy pin에 operating strategy가 없습니다.",
            )
        return cls(
            policy_id=str(payload.get("policy_id") or ""),
            policy_hash=str(payload.get("policy_hash") or ""),
            policy_contract_version=str(payload.get("policy_contract_version") or ""),
            policy_source=str(payload.get("policy_source") or "PERSISTED_RUN_PIN"),
            fallback_used=bool(payload.get("fallback_used")),
            fallback_reason=(
                str(payload.get("fallback_reason"))
                if payload.get("fallback_reason") not in (None, "")
                else None
            ),
            operating_strategies=tuple(
                (
                    (
                        str(item.get("strategy_version_id"))
                        if item.get("strategy_version_id") not in (None, "")
                        else None
                    ),
                    str(item.get("strategy_key") or ""),
                    (
                        str(item.get("definition_hash"))
                        if item.get("definition_hash") not in (None, "")
                        else None
                    ),
                )
                for item in strategies
                if isinstance(item, dict) and str(item.get("strategy_key") or "")
            ),
            scanner_baseline_id=(
                str(payload.get("scanner_baseline_id"))
                if payload.get("scanner_baseline_id") not in (None, "")
                else None
            ),
            production_fingerprint=(
                str(payload.get("production_fingerprint"))
                if payload.get("production_fingerprint") not in (None, "")
                else None
            ),
            production_policy_fingerprint=(
                str(payload.get("production_policy_fingerprint"))
                if payload.get("production_policy_fingerprint") not in (None, "")
                else None
            ),
        )


@dataclass(frozen=True, slots=True)
class SelectionPolicyResolution:
    policy: dict[str, Any]
    policy_source: str
    fallback_used: bool
    fallback_reason: str | None
    active_reference_valid: bool
    policy_hash_valid: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "policy": self.policy,
            "policy_source": self.policy_source,
            "fallback_used": self.fallback_used,
            "fallback_reason": self.fallback_reason,
            "active_reference_valid": self.active_reference_valid,
            "policy_hash_valid": self.policy_hash_valid,
        }


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


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


def _legacy_strategy_rows() -> list[dict[str, Any]]:
    return [
        {
            "strategy_version_id": None,
            "strategy_key": item.value,
            "definition_hash": None,
        }
        for item in StrategyName
        if item is not StrategyName.NO_TRADE
    ]


def legacy_selection_policy() -> dict[str, Any]:
    body = {
        "schema_version": SELECTION_POLICY_SCHEMA_VERSION,
        "policy_contract_version": SELECTION_POLICY_CONTRACT_VERSION,
        "source_kind": "LEGACY_CURRENT_10_FALLBACK",
        "operating_strategies": _legacy_strategy_rows(),
        "selection_semantics": {
            "risk_gate_preserved": True,
            "no_trade_safety_path_preserved": True,
            "score_formula_changed": False,
            "candidate_priority_changed": False,
        },
        "scanner_baseline_id": None,
        "production_fingerprint": None,
        "production_policy_fingerprint": None,
        "proposal_id": None,
        "proposal_hash": None,
        "approval_artifact_id": None,
        "approval_hash": None,
        "created_at": None,
    }
    return {
        **body,
        "policy_id": LEGACY_POLICY_ID,
        "policy_hash": _digest(body),
    }


class ProductionStrategySelectionRegistry:
    """
    Own immutable Production Strategy Selection Policy snapshots and active refs.

    Normal resolution reads runtime files only. Simulation is consulted only by
    explicit activation, where an immutable Approval Artifact is revalidated.
    """

    def __init__(
        self,
        *,
        runtime_dir: Path | None = None,
        simulation_db: Path | None = None,
        change_service: Any | None = None,
        allow_test_activation: bool = False,
        clock: Callable[[], str] | None = None,
        baseline_identity_provider: Callable[[], dict[str, str]] | None = None,
    ) -> None:
        self.runtime_dir = Path(runtime_dir or DEFAULT_RUNTIME_DIR)
        self.policies_dir = self.runtime_dir / "policies"
        self.active_path = self.runtime_dir / "active.json"
        self.simulation_db = Path(simulation_db or DEFAULT_SIMULATION_DB)
        self._change_service = change_service
        self.allow_test_activation = allow_test_activation
        self.clock = clock or _now
        self.baseline_identity_provider = (
            baseline_identity_provider or self._current_baseline_identity
        )

    @staticmethod
    def _current_baseline_identity() -> dict[str, str]:
        from app.baseline.scanner_production_baseline import (
            load_manifest,
            manifest_path,
            verify_baseline,
        )

        path = manifest_path(PROJECT_ROOT)
        manifest = load_manifest(path)
        verification = verify_baseline(PROJECT_ROOT, manifest)
        if not verification.valid:
            raise SelectionPolicyError(
                "SELECTION_POLICY_BASELINE_NOT_CURRENT",
                "현재 Scanner production baseline 검증에 실패했습니다.",
            )
        return {
            "scanner_baseline_id": str(manifest.get("baseline_id") or ""),
            "production_fingerprint": str(
                manifest.get("production_fingerprint") or ""
            ),
            "production_policy_fingerprint": str(
                manifest.get("policy_fingerprint") or ""
            ),
        }

    @staticmethod
    def _pin_from_resolution(
        resolution: SelectionPolicyResolution,
    ) -> SelectionPolicyPin:
        policy = resolution.policy
        strategies = tuple(
            (
                (
                    str(item.get("strategy_version_id"))
                    if item.get("strategy_version_id") is not None
                    else None
                ),
                str(item.get("strategy_key") or ""),
                (
                    str(item.get("definition_hash"))
                    if item.get("definition_hash") is not None
                    else None
                ),
            )
            for item in list(policy.get("operating_strategies") or [])
        )
        return SelectionPolicyPin(
            policy_id=str(policy.get("policy_id") or ""),
            policy_hash=str(policy.get("policy_hash") or ""),
            policy_contract_version=str(
                policy.get("policy_contract_version")
                or SELECTION_POLICY_CONTRACT_VERSION
            ),
            policy_source=resolution.policy_source,
            fallback_used=resolution.fallback_used,
            fallback_reason=resolution.fallback_reason,
            operating_strategies=strategies,
            scanner_baseline_id=(
                str(policy.get("scanner_baseline_id"))
                if policy.get("scanner_baseline_id") is not None
                else None
            ),
            production_fingerprint=(
                str(policy.get("production_fingerprint"))
                if policy.get("production_fingerprint") is not None
                else None
            ),
            production_policy_fingerprint=(
                str(policy.get("production_policy_fingerprint"))
                if policy.get("production_policy_fingerprint") is not None
                else None
            ),
        )

    @staticmethod
    def _baseline_matches(
        policy: dict[str, Any],
        current: dict[str, str],
    ) -> bool:
        return (
            str(policy.get("scanner_baseline_id") or "")
            == str(current.get("scanner_baseline_id") or "")
            and str(policy.get("production_fingerprint") or "")
            == str(current.get("production_fingerprint") or "")
            and str(policy.get("production_policy_fingerprint") or "")
            == str(current.get("production_policy_fingerprint") or "")
        )

    def pin_active_selection_policy(self) -> SelectionPolicyPin:
        resolution = self.resolve_active_selection_policy()
        if resolution.policy_source == "LEGACY_CURRENT_10_FALLBACK":
            return self._pin_from_resolution(resolution)

        try:
            current = self.baseline_identity_provider()
        except Exception:
            legacy = legacy_selection_policy()
            return self._pin_from_resolution(
                SelectionPolicyResolution(
                    policy=legacy,
                    policy_source="LEGACY_CURRENT_10_FALLBACK",
                    fallback_used=True,
                    fallback_reason="CURRENT_BASELINE_UNAVAILABLE",
                    active_reference_valid=resolution.active_reference_valid,
                    policy_hash_valid=True,
                )
            )

        if self._baseline_matches(resolution.policy, current):
            return self._pin_from_resolution(resolution)

        reference, _ = self._load_reference()
        if reference is not None:
            rollback, rollback_reason = self._load_snapshot(
                reference.get("rollback_policy_id"),
                reference.get("rollback_policy_hash"),
            )
            if (
                rollback is not None
                and self._baseline_matches(rollback, current)
            ):
                return self._pin_from_resolution(
                    SelectionPolicyResolution(
                        policy=rollback,
                        policy_source="ROLLBACK_FALLBACK",
                        fallback_used=True,
                        fallback_reason="ACTIVE_POLICY_BASELINE_MISMATCH",
                        active_reference_valid=True,
                        policy_hash_valid=True,
                    )
                )
            if rollback_reason is not None:
                fallback_reason = (
                    "ACTIVE_POLICY_BASELINE_MISMATCH;"
                    + rollback_reason
                )
            else:
                fallback_reason = "ACTIVE_POLICY_BASELINE_MISMATCH"
        else:
            fallback_reason = "ACTIVE_POLICY_BASELINE_MISMATCH"

        legacy = legacy_selection_policy()
        return self._pin_from_resolution(
            SelectionPolicyResolution(
                policy=legacy,
                policy_source="LEGACY_CURRENT_10_FALLBACK",
                fallback_used=True,
                fallback_reason=fallback_reason,
                active_reference_valid=resolution.active_reference_valid,
                policy_hash_valid=True,
            )
        )

    def _change(self):
        if self._change_service is None:
            from app.simulation.strategy_change import StrategyChangeService

            self._change_service = StrategyChangeService(
                self.simulation_db,
                allow_test_protocol=self.allow_test_activation,
            )
        return self._change_service

    @staticmethod
    def _read_json(path: Path) -> dict[str, Any] | None:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return value if isinstance(value, dict) else None

    @staticmethod
    def _policy_body(snapshot: dict[str, Any]) -> dict[str, Any]:
        return {
            key: value
            for key, value in snapshot.items()
            if key not in {"policy_id", "policy_hash"}
        }

    @staticmethod
    def _policy_id(policy_hash: str) -> str:
        return f"SS-SELECT-V1-{policy_hash[:16]}"

    @classmethod
    def _build_snapshot(
        cls,
        *,
        source_kind: str,
        operating_strategies: list[dict[str, Any]],
        selection_semantics: dict[str, Any],
        scanner_baseline_id: str | None,
        production_fingerprint: str | None,
        production_policy_fingerprint: str | None,
        proposal_id: str | None,
        proposal_hash: str | None,
        approval_artifact_id: str | None,
        approval_hash: str | None,
        created_at: str,
    ) -> dict[str, Any]:
        ordered = sorted(
            [
                {
                    "strategy_version_id": item.get(
                        "strategy_version_id"
                    ),
                    "strategy_key": str(item.get("strategy_key") or ""),
                    "definition_hash": item.get("definition_hash"),
                }
                for item in operating_strategies
            ],
            key=lambda item: (
                item["strategy_key"],
                str(item["strategy_version_id"] or ""),
            ),
        )
        if not ordered or any(not item["strategy_key"] for item in ordered):
            raise SelectionPolicyError(
                "SELECTION_POLICY_OPERATING_SET_INVALID",
                "Selection Policy에는 하나 이상의 유효한 운영 전략이 필요합니다.",
            )
        if any(item["strategy_key"] == StrategyName.NO_TRADE.value for item in ordered):
            raise SelectionPolicyError(
                "SELECTION_POLICY_NO_TRADE_FORBIDDEN",
                "NO_TRADE는 운영 Strategy Pool에 포함할 수 없습니다.",
            )

        semantics = {
            "risk_gate_preserved": bool(
                selection_semantics.get("risk_gate_preserved")
            ),
            "no_trade_safety_path_preserved": bool(
                selection_semantics.get(
                    "no_trade_safety_path_preserved"
                )
            ),
            "score_formula_changed": bool(
                selection_semantics.get("score_formula_changed")
            ),
            "candidate_priority_changed": bool(
                selection_semantics.get("candidate_priority_changed")
            ),
        }
        if not semantics["risk_gate_preserved"]:
            raise SelectionPolicyError(
                "SELECTION_POLICY_RISK_GATE_CHANGE_FORBIDDEN",
                "P5 Selection Policy는 기존 Risk Gate를 변경할 수 없습니다.",
            )
        if not semantics["no_trade_safety_path_preserved"]:
            raise SelectionPolicyError(
                "SELECTION_POLICY_NO_TRADE_CHANGE_FORBIDDEN",
                "P5 Selection Policy는 NO_TRADE safety path를 변경할 수 없습니다.",
            )
        if semantics["score_formula_changed"]:
            raise SelectionPolicyError(
                "SELECTION_POLICY_SCORE_CHANGE_FORBIDDEN",
                "P5 Selection Policy는 Strategy suitability score 공식을 변경할 수 없습니다.",
            )
        if semantics["candidate_priority_changed"]:
            raise SelectionPolicyError(
                "SELECTION_POLICY_PRIORITY_CHANGE_FORBIDDEN",
                "P5 Selection Policy는 기존 candidate priority를 변경할 수 없습니다.",
            )

        body = {
            "schema_version": SELECTION_POLICY_SCHEMA_VERSION,
            "policy_contract_version": SELECTION_POLICY_CONTRACT_VERSION,
            "source_kind": source_kind,
            "operating_strategies": ordered,
            "selection_semantics": semantics,
            "scanner_baseline_id": scanner_baseline_id,
            "production_fingerprint": production_fingerprint,
            "production_policy_fingerprint": production_policy_fingerprint,
            "proposal_id": proposal_id,
            "proposal_hash": proposal_hash,
            "approval_artifact_id": approval_artifact_id,
            "approval_hash": approval_hash,
            "created_at": created_at,
        }
        policy_hash = _digest(body)
        return {
            **body,
            "policy_id": cls._policy_id(policy_hash),
            "policy_hash": policy_hash,
        }

    @classmethod
    def validate_snapshot(
        cls,
        snapshot: dict[str, Any] | None,
    ) -> tuple[bool, str | None]:
        if not isinstance(snapshot, dict):
            return False, "POLICY_NOT_JSON_OBJECT"
        if snapshot.get("schema_version") != SELECTION_POLICY_SCHEMA_VERSION:
            return False, "POLICY_SCHEMA_VERSION_MISMATCH"
        if (
            snapshot.get("policy_contract_version")
            != SELECTION_POLICY_CONTRACT_VERSION
        ):
            return False, "POLICY_CONTRACT_VERSION_MISMATCH"
        policy_hash = str(snapshot.get("policy_hash") or "")
        if not policy_hash:
            return False, "POLICY_HASH_MISSING"
        expected_hash = _digest(cls._policy_body(snapshot))
        if expected_hash != policy_hash:
            return False, "POLICY_HASH_MISMATCH"
        if str(snapshot.get("policy_id") or "") != cls._policy_id(
            policy_hash
        ):
            return False, "POLICY_ID_MISMATCH"

        strategies = snapshot.get("operating_strategies")
        if not isinstance(strategies, list) or not strategies:
            return False, "POLICY_OPERATING_SET_INVALID"
        keys = [str(item.get("strategy_key") or "") for item in strategies]
        if any(not key for key in keys):
            return False, "POLICY_STRATEGY_KEY_MISSING"
        if len(keys) != len(set(keys)):
            return False, "POLICY_DUPLICATE_STRATEGY_KEY"
        if StrategyName.NO_TRADE.value in keys:
            return False, "POLICY_NO_TRADE_FORBIDDEN"
        supported_keys = {
            item.value
            for item in StrategyName
            if item is not StrategyName.NO_TRADE
        }
        if any(key not in supported_keys for key in keys):
            return False, "POLICY_STRATEGY_KEY_UNSUPPORTED"

        semantics = snapshot.get("selection_semantics")
        if not isinstance(semantics, dict):
            return False, "POLICY_SEMANTICS_MISSING"
        if semantics.get("risk_gate_preserved") is not True:
            return False, "POLICY_RISK_GATE_NOT_PRESERVED"
        if semantics.get("no_trade_safety_path_preserved") is not True:
            return False, "POLICY_NO_TRADE_PATH_NOT_PRESERVED"
        if semantics.get("score_formula_changed") is not False:
            return False, "POLICY_SCORE_FORMULA_CHANGED"
        if semantics.get("candidate_priority_changed") is not False:
            return False, "POLICY_CANDIDATE_PRIORITY_CHANGED"
        return True, None

    def _snapshot_path(self, policy_id: str) -> Path:
        if (
            not policy_id
            or "/" in policy_id
            or "\\" in policy_id
            or policy_id in {".", ".."}
        ):
            raise SelectionPolicyError(
                "SELECTION_POLICY_ID_INVALID",
                "Selection Policy ID가 올바르지 않습니다.",
            )
        return self.policies_dir / f"{policy_id}.json"

    def _load_snapshot(
        self,
        policy_id: str | None,
        expected_hash: str | None = None,
    ) -> tuple[dict[str, Any] | None, str | None]:
        if not policy_id:
            return None, "POLICY_REFERENCE_MISSING"
        path = self._snapshot_path(policy_id)
        snapshot = self._read_json(path)
        valid, reason = self.validate_snapshot(snapshot)
        if not valid:
            return None, reason
        assert snapshot is not None
        if (
            expected_hash
            and str(snapshot["policy_hash"]) != str(expected_hash)
        ):
            return None, "POLICY_REFERENCE_HASH_MISMATCH"
        return snapshot, None

    def _publish_snapshot(self, snapshot: dict[str, Any]) -> Path:
        valid, reason = self.validate_snapshot(snapshot)
        if not valid:
            raise SelectionPolicyError(
                "SELECTION_POLICY_SNAPSHOT_INVALID",
                f"Selection Policy snapshot 검증 실패: {reason}",
            )
        policy_id = str(snapshot["policy_id"])
        target = self._snapshot_path(policy_id)
        self.policies_dir.mkdir(parents=True, exist_ok=True)

        if target.exists():
            existing = self._read_json(target)
            existing_valid, _ = self.validate_snapshot(existing)
            if (
                not existing_valid
                or existing is None
                or existing != snapshot
            ):
                raise SelectionPolicyError(
                    "SELECTION_POLICY_IDENTITY_CONFLICT",
                    "같은 Policy ID에 다른 또는 손상된 snapshot이 존재합니다.",
                )
            return target

        temp = target.with_name(
            f".{target.name}.{os.getpid()}.tmp"
        )
        try:
            temp.write_text(
                json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            written = self._read_json(temp)
            written_valid, written_reason = self.validate_snapshot(written)
            if not written_valid or written != snapshot:
                raise SelectionPolicyError(
                    "SELECTION_POLICY_TEMP_VERIFY_FAILED",
                    f"임시 Selection Policy 검증 실패: {written_reason}",
                )
            try:
                os.replace(temp, target)
            except OSError as exc:
                raise SelectionPolicyError(
                    "SELECTION_POLICY_ATOMIC_PUBLISH_FAILED",
                    "Selection Policy snapshot을 원자적으로 게시하지 못했습니다.",
                ) from exc
        finally:
            if temp.exists():
                try:
                    temp.unlink()
                except OSError:
                    pass
        return target

    @staticmethod
    def _reference_body(payload: dict[str, Any]) -> dict[str, Any]:
        return {
            key: value
            for key, value in payload.items()
            if key != "reference_hash"
        }

    @classmethod
    def _validate_reference(
        cls,
        payload: dict[str, Any] | None,
    ) -> tuple[bool, str | None]:
        if not isinstance(payload, dict):
            return False, "ACTIVE_REFERENCE_NOT_JSON_OBJECT"
        if (
            payload.get("schema_version")
            != ACTIVE_REFERENCE_SCHEMA_VERSION
        ):
            return False, "ACTIVE_REFERENCE_SCHEMA_MISMATCH"
        if not str(payload.get("active_policy_id") or ""):
            return False, "ACTIVE_POLICY_ID_MISSING"
        if not str(payload.get("active_policy_hash") or ""):
            return False, "ACTIVE_POLICY_HASH_MISSING"
        try:
            generation = int(payload.get("generation"))
        except (TypeError, ValueError):
            return False, "ACTIVE_REFERENCE_GENERATION_INVALID"
        if generation < 1:
            return False, "ACTIVE_REFERENCE_GENERATION_INVALID"
        reference_hash = str(payload.get("reference_hash") or "")
        if not reference_hash:
            return False, "ACTIVE_REFERENCE_HASH_MISSING"
        if _digest(cls._reference_body(payload)) != reference_hash:
            return False, "ACTIVE_REFERENCE_HASH_MISMATCH"
        return True, None

    def _load_reference(
        self,
    ) -> tuple[dict[str, Any] | None, str | None]:
        if not self.active_path.exists():
            return None, "ACTIVE_REFERENCE_MISSING"
        payload = self._read_json(self.active_path)
        valid, reason = self._validate_reference(payload)
        if not valid:
            return None, reason
        return payload, None

    def _publish_reference(self, payload: dict[str, Any]) -> None:
        body = dict(payload)
        body.pop("reference_hash", None)
        body["reference_hash"] = _digest(body)
        valid, reason = self._validate_reference(body)
        if not valid:
            raise SelectionPolicyError(
                "ACTIVE_REFERENCE_INVALID",
                f"Active reference 검증 실패: {reason}",
            )

        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        temp = self.active_path.with_name(
            f".{self.active_path.name}.{os.getpid()}.tmp"
        )
        try:
            temp.write_text(
                json.dumps(body, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            written = self._read_json(temp)
            written_valid, written_reason = self._validate_reference(
                written
            )
            if not written_valid or written != body:
                raise SelectionPolicyError(
                    "ACTIVE_REFERENCE_TEMP_VERIFY_FAILED",
                    f"임시 active reference 검증 실패: {written_reason}",
                )
            try:
                os.replace(temp, self.active_path)
            except OSError as exc:
                # Do not copy-overwrite Production active state. If atomic
                # replacement is unavailable, preserve the previous active ref.
                raise SelectionPolicyError(
                    "SELECTION_POLICY_ATOMIC_PUBLISH_FAILED",
                    "Production active reference를 원자적으로 게시하지 못했습니다.",
                ) from exc
        finally:
            if temp.exists():
                try:
                    temp.unlink()
                except OSError:
                    pass

    def resolve_active_selection_policy(
        self,
    ) -> SelectionPolicyResolution:
        reference, reference_reason = self._load_reference()
        if reference is None:
            legacy = legacy_selection_policy()
            return SelectionPolicyResolution(
                policy=legacy,
                policy_source="LEGACY_CURRENT_10_FALLBACK",
                fallback_used=True,
                fallback_reason=reference_reason,
                active_reference_valid=False,
                policy_hash_valid=True,
            )

        active, active_reason = self._load_snapshot(
            str(reference["active_policy_id"]),
            str(reference["active_policy_hash"]),
        )
        if active is not None:
            return SelectionPolicyResolution(
                policy=active,
                policy_source="ACTIVE_SELECTION_POLICY",
                fallback_used=False,
                fallback_reason=None,
                active_reference_valid=True,
                policy_hash_valid=True,
            )

        rollback, rollback_reason = self._load_snapshot(
            reference.get("rollback_policy_id"),
            reference.get("rollback_policy_hash"),
        )
        if rollback is not None:
            return SelectionPolicyResolution(
                policy=rollback,
                policy_source="ROLLBACK_FALLBACK",
                fallback_used=True,
                fallback_reason=active_reason,
                active_reference_valid=True,
                policy_hash_valid=True,
            )

        legacy = legacy_selection_policy()
        reason = active_reason or rollback_reason or "NO_VALID_POLICY"
        return SelectionPolicyResolution(
            policy=legacy,
            policy_source="LEGACY_CURRENT_10_FALLBACK",
            fallback_used=True,
            fallback_reason=reason,
            active_reference_valid=True,
            policy_hash_valid=True,
        )

    @staticmethod
    def _approval_protocol_is_test_only(
        approval: dict[str, Any],
    ) -> bool:
        context = approval.get("approval_context") or {}
        protocol = (
            context.get("protocol")
            if isinstance(context, dict)
            else None
        )
        return bool(
            protocol.get("test_only")
            if isinstance(protocol, dict)
            else False
        )

    @staticmethod
    def _require_selection_semantics(
        proposal: dict[str, Any],
    ) -> dict[str, Any]:
        intent = proposal.get("candidate_policy_intent")
        if not isinstance(intent, dict):
            raise SelectionPolicyError(
                "CANDIDATE_POLICY_INTENT_MISSING",
                "승인 Proposal에 candidate policy intent가 없습니다.",
            )
        semantics = {
            "risk_gate_preserved": intent.get("risk_gate_preserved"),
            "no_trade_safety_path_preserved": intent.get(
                "no_trade_safety_path_preserved"
            ),
            "score_formula_changed": intent.get(
                "score_formula_changed"
            ),
            "candidate_priority_changed": intent.get(
                "candidate_priority_changed"
            ),
        }
        if semantics != {
            "risk_gate_preserved": True,
            "no_trade_safety_path_preserved": True,
            "score_formula_changed": False,
            "candidate_priority_changed": False,
        }:
            raise SelectionPolicyError(
                "SELECTION_POLICY_SEMANTICS_CHANGED",
                "승인 Proposal이 P5 Selection Policy 보존 경계를 위반합니다.",
            )
        return semantics

    def _validated_approval(
        self,
        approval_artifact_id: str,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        change = self._change()
        try:
            approval = change.get_approval(approval_artifact_id)
        except Exception as exc:
            raise SelectionPolicyError(
                "APPROVAL_ARTIFACT_NOT_AVAILABLE",
                f"Approval Artifact를 읽을 수 없습니다: {exc}",
            ) from exc

        if approval.get("approval_integrity") != "MATCH":
            raise SelectionPolicyError(
                "APPROVAL_ARTIFACT_HASH_MISMATCH",
                "Approval Artifact integrity가 일치하지 않습니다.",
            )
        if (
            self._approval_protocol_is_test_only(approval)
            and not self.allow_test_activation
        ):
            raise SelectionPolicyError(
                "TEST_APPROVAL_ACTIVATION_FORBIDDEN",
                "TEST-only Approval은 Production Selection Policy로 게시할 수 없습니다.",
            )

        proposal_id = str(approval.get("proposal_id") or "")
        try:
            proposal = change.get_proposal(proposal_id)
            verification = change.verify_proposal(proposal_id)
        except Exception as exc:
            raise SelectionPolicyError(
                "APPROVAL_PROPOSAL_NOT_AVAILABLE",
                f"Approval의 Proposal을 재검증할 수 없습니다: {exc}",
            ) from exc

        if proposal.get("proposal_integrity") != "MATCH":
            raise SelectionPolicyError(
                "APPROVAL_PROPOSAL_HASH_MISMATCH",
                "Approval의 Proposal integrity가 일치하지 않습니다.",
            )
        if verification.get("status") != "CURRENT":
            raise SelectionPolicyError(
                "APPROVAL_PROPOSAL_STALE",
                "Approval의 Proposal 근거가 현재 상태와 달라 재승인이 필요합니다.",
            )

        required_pairs = (
            ("proposal_hash", "proposal_hash"),
            ("evidence_bundle_hash", "evidence_bundle_hash"),
            ("registry_snapshot_hash", "base_registry_snapshot_hash"),
            (
                "candidate_policy_intent_hash",
                "candidate_policy_intent_hash",
            ),
            ("rollback_basis_hash", "rollback_basis_hash"),
        )
        for approval_key, proposal_key in required_pairs:
            if str(approval.get(approval_key) or "") != str(
                proposal.get(proposal_key) or ""
            ):
                raise SelectionPolicyError(
                    "APPROVAL_PROPOSAL_REFERENCE_MISMATCH",
                    f"Approval과 Proposal 참조가 일치하지 않습니다: {approval_key}",
                )

        self._require_selection_semantics(proposal)
        return approval, proposal

    def _snapshot_from_approval(
        self,
        approval: dict[str, Any],
        proposal: dict[str, Any],
    ) -> dict[str, Any]:
        intent = proposal["candidate_policy_intent"]
        return self._build_snapshot(
            source_kind="APPROVED_PROPOSAL",
            operating_strategies=list(
                intent.get("operating_strategies") or []
            ),
            selection_semantics=self._require_selection_semantics(
                proposal
            ),
            scanner_baseline_id=str(
                proposal.get("scanner_baseline_id") or ""
            ),
            production_fingerprint=str(
                proposal.get("production_fingerprint") or ""
            ),
            production_policy_fingerprint=str(
                proposal.get("production_policy_fingerprint") or ""
            ),
            proposal_id=str(proposal["id"]),
            proposal_hash=str(proposal["proposal_hash"]),
            approval_artifact_id=str(approval["id"]),
            approval_hash=str(approval["approval_hash"]),
            created_at=str(approval["approved_at"]),
        )

    def _snapshot_from_rollback_basis(
        self,
        proposal: dict[str, Any],
    ) -> dict[str, Any]:
        rollback = proposal.get("rollback_basis")
        if not isinstance(rollback, dict):
            raise SelectionPolicyError(
                "ROLLBACK_BASIS_MISSING",
                "최초 activation을 위한 rollback basis가 없습니다.",
            )
        return self._build_snapshot(
            source_kind="PRE_ACTIVATION_BASELINE",
            operating_strategies=list(
                rollback.get("operating_strategies") or []
            ),
            selection_semantics={
                "risk_gate_preserved": True,
                "no_trade_safety_path_preserved": True,
                "score_formula_changed": False,
                "candidate_priority_changed": False,
            },
            scanner_baseline_id=rollback.get("scanner_baseline_id"),
            production_fingerprint=rollback.get(
                "production_fingerprint"
            ),
            production_policy_fingerprint=rollback.get(
                "production_policy_fingerprint"
            ),
            proposal_id=str(proposal["id"]),
            proposal_hash=str(proposal["proposal_hash"]),
            approval_artifact_id=None,
            approval_hash=None,
            created_at=str(proposal["created_at"]),
        )

    def activate_approved_policy(
        self,
        *,
        approval_artifact_id: str,
        expected_active_policy_id: str | None,
    ) -> dict[str, Any]:
        approval, proposal = self._validated_approval(
            approval_artifact_id
        )
        target = self._snapshot_from_approval(approval, proposal)

        current_ref, current_reason = self._load_reference()
        if self.active_path.exists() and current_ref is None:
            raise SelectionPolicyError(
                "ACTIVE_REFERENCE_CORRUPT",
                f"기존 active reference가 손상되었습니다: {current_reason}",
            )
        actual_active = (
            str(current_ref["active_policy_id"])
            if current_ref is not None
            else None
        )
        if actual_active != expected_active_policy_id:
            raise SelectionPolicyError(
                "ACTIVE_POLICY_CONFLICT",
                "예상한 active Selection Policy와 현재 active reference가 다릅니다.",
            )

        if (
            current_ref is not None
            and actual_active == target["policy_id"]
            and str(current_ref["active_policy_hash"])
            == target["policy_hash"]
        ):
            loaded, reason = self._load_snapshot(
                actual_active,
                str(current_ref["active_policy_hash"]),
            )
            if loaded is None:
                raise SelectionPolicyError(
                    "ACTIVE_POLICY_CORRUPT",
                    f"현재 active Selection Policy가 손상되었습니다: {reason}",
                )
            return {
                "changed": False,
                "active_reference": current_ref,
                "active_policy": loaded,
            }

        self._publish_snapshot(target)

        if current_ref is None:
            rollback = self._snapshot_from_rollback_basis(proposal)
            self._publish_snapshot(rollback)
            rollback_policy_id = str(rollback["policy_id"])
            rollback_policy_hash = str(rollback["policy_hash"])
            generation = 1
        else:
            current_snapshot, reason = self._load_snapshot(
                actual_active,
                str(current_ref["active_policy_hash"]),
            )
            if current_snapshot is None:
                raise SelectionPolicyError(
                    "ACTIVE_POLICY_CORRUPT",
                    f"현재 active Selection Policy가 손상되었습니다: {reason}",
                )
            rollback_policy_id = str(
                current_snapshot["policy_id"]
            )
            rollback_policy_hash = str(
                current_snapshot["policy_hash"]
            )
            generation = int(current_ref["generation"]) + 1

        new_ref = {
            "schema_version": ACTIVE_REFERENCE_SCHEMA_VERSION,
            "active_policy_id": str(target["policy_id"]),
            "active_policy_hash": str(target["policy_hash"]),
            "rollback_policy_id": rollback_policy_id,
            "rollback_policy_hash": rollback_policy_hash,
            "last_deactivated_policy_id": actual_active,
            "activation_source": "EXPLICIT_APPROVAL",
            "approval_artifact_id": str(approval["id"]),
            "approval_hash": str(approval["approval_hash"]),
            "activated_at": self.clock(),
            "generation": generation,
        }
        self._publish_reference(new_ref)
        published_ref, reason = self._load_reference()
        if published_ref is None:
            raise SelectionPolicyError(
                "ACTIVE_REFERENCE_POST_VERIFY_FAILED",
                f"게시된 active reference를 검증하지 못했습니다: {reason}",
            )
        return {
            "changed": True,
            "active_reference": published_ref,
            "active_policy": target,
        }

    def rollback_selection_policy(
        self,
        *,
        expected_active_policy_id: str,
    ) -> dict[str, Any]:
        current_ref, reason = self._load_reference()
        if current_ref is None:
            raise SelectionPolicyError(
                "ACTIVE_REFERENCE_NOT_AVAILABLE",
                f"Rollback할 active reference가 없습니다: {reason}",
            )
        actual_active = str(current_ref["active_policy_id"])
        if actual_active != expected_active_policy_id:
            raise SelectionPolicyError(
                "ACTIVE_POLICY_CONFLICT",
                "예상한 active Selection Policy와 현재 active reference가 다릅니다.",
            )

        rollback_id = current_ref.get("rollback_policy_id")
        rollback_hash = current_ref.get("rollback_policy_hash")
        rollback, rollback_reason = self._load_snapshot(
            str(rollback_id or ""),
            str(rollback_hash or ""),
        )
        if rollback is None:
            raise SelectionPolicyError(
                "ROLLBACK_POLICY_NOT_AVAILABLE",
                f"Rollback Selection Policy가 유효하지 않습니다: {rollback_reason}",
            )

        new_ref = {
            "schema_version": ACTIVE_REFERENCE_SCHEMA_VERSION,
            "active_policy_id": str(rollback["policy_id"]),
            "active_policy_hash": str(rollback["policy_hash"]),
            "rollback_policy_id": None,
            "rollback_policy_hash": None,
            "last_deactivated_policy_id": actual_active,
            "activation_source": "EXPLICIT_ROLLBACK",
            "approval_artifact_id": None,
            "approval_hash": None,
            "activated_at": self.clock(),
            "generation": int(current_ref["generation"]) + 1,
        }
        self._publish_reference(new_ref)
        published_ref, post_reason = self._load_reference()
        if published_ref is None:
            raise SelectionPolicyError(
                "ACTIVE_REFERENCE_POST_VERIFY_FAILED",
                f"Rollback reference를 검증하지 못했습니다: {post_reason}",
            )
        return {
            "changed": True,
            "active_reference": published_ref,
            "active_policy": rollback,
        }


def resolve_active_selection_policy(
    *,
    runtime_dir: Path | None = None,
) -> SelectionPolicyResolution:
    return ProductionStrategySelectionRegistry(
        runtime_dir=runtime_dir
    ).resolve_active_selection_policy()



def pin_active_selection_policy(
    *,
    runtime_dir: Path | None = None,
) -> SelectionPolicyPin:
    return ProductionStrategySelectionRegistry(
        runtime_dir=runtime_dir
    ).pin_active_selection_policy()


def selection_policy_cache_token(
    pin: SelectionPolicyPin | None = None,
    *,
    runtime_dir: Path | None = None,
) -> str:
    resolved = pin or pin_active_selection_policy(runtime_dir=runtime_dir)
    return resolved.cache_token
