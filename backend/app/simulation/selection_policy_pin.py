from __future__ import annotations

from typing import Any

from app.strategy.production_selection_policy import SelectionPolicyPin


def serialize_selection_policy_pin(pin: SelectionPolicyPin) -> dict[str, Any]:
    return {
        **pin.metadata(),
        "operating_strategies": [
            {
                "strategy_version_id": strategy_version_id,
                "strategy_key": strategy_key,
                "definition_hash": definition_hash,
            }
            for strategy_version_id, strategy_key, definition_hash
            in pin.operating_strategies
        ],
    }


def restore_selection_policy_pin(payload: dict[str, Any] | None) -> SelectionPolicyPin:
    if not isinstance(payload, dict):
        raise ValueError("저장된 Selection Policy pin이 없습니다.")

    policy_id = str(payload.get("policy_id") or "")
    policy_hash = str(payload.get("policy_hash") or "")
    contract_version = str(payload.get("policy_contract_version") or "")
    strategies = payload.get("operating_strategies")

    if not policy_id or not policy_hash or not contract_version:
        raise ValueError("저장된 Selection Policy pin identity가 불완전합니다.")
    if not isinstance(strategies, list) or not strategies:
        raise ValueError("저장된 Selection Policy pin에 operating strategy가 없습니다.")

    operating: list[tuple[str | None, str, str | None]] = []
    for item in strategies:
        if not isinstance(item, dict):
            raise ValueError("저장된 Selection Policy strategy 형식이 올바르지 않습니다.")
        strategy_key = str(item.get("strategy_key") or "")
        if not strategy_key:
            raise ValueError("저장된 Selection Policy strategy key가 없습니다.")
        operating.append(
            (
                (
                    str(item.get("strategy_version_id"))
                    if item.get("strategy_version_id") not in (None, "")
                    else None
                ),
                strategy_key,
                (
                    str(item.get("definition_hash"))
                    if item.get("definition_hash") not in (None, "")
                    else None
                ),
            )
        )

    return SelectionPolicyPin(
        policy_id=policy_id,
        policy_hash=policy_hash,
        policy_contract_version=contract_version,
        policy_source=str(payload.get("policy_source") or "PERSISTED_RUN_PIN"),
        fallback_used=bool(payload.get("fallback_used")),
        fallback_reason=(
            str(payload.get("fallback_reason"))
            if payload.get("fallback_reason") not in (None, "")
            else None
        ),
        operating_strategies=tuple(operating),
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
