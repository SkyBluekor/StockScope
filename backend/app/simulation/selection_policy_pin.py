from __future__ import annotations

from typing import Any

from app.strategy.production_selection_policy import (
    SelectionPolicyError,
    SelectionPolicyPin,
)


def serialize_selection_policy_pin(pin: SelectionPolicyPin) -> dict[str, Any]:
    return {
        **pin.metadata(),
        "operating_strategies": [
            {
                "strategy_version_id": version_id,
                "strategy_key": strategy_key,
                "definition_hash": definition_hash,
            }
            for version_id, strategy_key, definition_hash
            in pin.operating_strategies
        ],
    }


def deserialize_selection_policy_pin(
    payload: dict[str, Any] | None,
) -> SelectionPolicyPin:
    if not isinstance(payload, dict):
        raise SelectionPolicyError(
            "SELECTION_POLICY_PIN_INVALID",
            "저장된 Selection Policy pin 형식이 올바르지 않습니다.",
        )
    policy_id = str(payload.get("policy_id") or "").strip()
    policy_hash = str(payload.get("policy_hash") or "").strip()
    contract = str(payload.get("policy_contract_version") or "").strip()
    raw_strategies = payload.get("operating_strategies")
    if (
        not policy_id
        or not policy_hash
        or not contract
        or not isinstance(raw_strategies, list)
    ):
        raise SelectionPolicyError(
            "SELECTION_POLICY_PIN_INVALID",
            "저장된 Selection Policy pin identity가 불완전합니다.",
        )

    operating: list[tuple[str | None, str, str | None]] = []
    for item in raw_strategies:
        if not isinstance(item, dict):
            raise SelectionPolicyError(
                "SELECTION_POLICY_PIN_INVALID",
                "Selection Policy strategy identity 형식이 올바르지 않습니다.",
            )
        key = str(item.get("strategy_key") or "").strip()
        if not key:
            raise SelectionPolicyError(
                "SELECTION_POLICY_PIN_INVALID",
                "Selection Policy strategy key가 비어 있습니다.",
            )
        operating.append(
            (
                (
                    str(item.get("strategy_version_id"))
                    if item.get("strategy_version_id") is not None
                    else None
                ),
                key,
                (
                    str(item.get("definition_hash"))
                    if item.get("definition_hash") is not None
                    else None
                ),
            )
        )

    return SelectionPolicyPin(
        policy_id=policy_id,
        policy_hash=policy_hash,
        policy_contract_version=contract,
        policy_source=str(payload.get("policy_source") or "STORED_RUN_PIN"),
        fallback_used=bool(payload.get("fallback_used")),
        fallback_reason=(
            str(payload.get("fallback_reason"))
            if payload.get("fallback_reason") is not None
            else None
        ),
        operating_strategies=tuple(operating),
        scanner_baseline_id=(
            str(payload.get("scanner_baseline_id"))
            if payload.get("scanner_baseline_id") is not None
            else None
        ),
        production_fingerprint=(
            str(payload.get("production_fingerprint"))
            if payload.get("production_fingerprint") is not None
            else None
        ),
        production_policy_fingerprint=(
            str(payload.get("production_policy_fingerprint"))
            if payload.get("production_policy_fingerprint") is not None
            else None
        ),
    )
