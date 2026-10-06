from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .models import canonical_json, digest_json
from .typesafe_models import (
    JEV_TYPESAFE_PROJECTOR_VERSION,
    JEV_TYPESAFE_STATE_CONTRACT_VERSION,
)


MAX_STATE_BYTES = 8 * 1024
MAX_CONDITIONS = 12
MAX_SEMANTIC_TEXT = 160
MAX_STRATEGY_DESCRIPTION = 360

CONDITION_SEMANTIC_LABELS: dict[str, str] = {
    "price_vs_ma20": "price relation to the 20-day moving average",
    "ma20_vs_ma60": "20-day versus 60-day moving-average relation",
    "ma60_vs_ma120": "60-day versus 120-day moving-average relation",
    "ma20_slope": "20-day moving-average slope condition",
    "higher_high": "higher-high price-structure condition",
    "higher_low": "higher-low price-structure condition",
    "relative_strength_market": "relative strength versus the broad market",
    "relative_strength_sector": "relative strength versus the sector",
    "market_regime": "market-regime condition",
    "volume_ratio_20": "volume versus 20-day average condition",
    "rsi14": "14-period RSI condition",
    "atr_pct": "ATR percentage condition",
    "support_distance": "distance to support condition",
    "resistance_distance": "distance to resistance condition",
    "distance_to_20d_high": "distance to the 20-day high condition",
    "distance_to_ma20": "distance to the 20-day moving average condition",
}

PROJECTOR_DEFINITION = {
    "version": JEV_TYPESAFE_PROJECTOR_VERSION,
    "state_contract": JEV_TYPESAFE_STATE_CONTRACT_VERSION,
    "max_state_bytes": MAX_STATE_BYTES,
    "max_conditions": MAX_CONDITIONS,
    "condition_semantics": CONDITION_SEMANTIC_LABELS,
}
JEV_TYPESAFE_PROJECTOR_HASH = digest_json(PROJECTOR_DEFINITION)
JEV_TYPESAFE_STATE_CONTRACT_HASH = digest_json(
    {
        "version": JEV_TYPESAFE_STATE_CONTRACT_VERSION,
        "top_level": [
            "context",
            "strategy_context",
            "condition_context",
            "entry_context",
            "baseline",
        ],
        "projector_hash": JEV_TYPESAFE_PROJECTOR_HASH,
    }
)


class TypeSafeStateProjectionError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class TypeSafeStateProjection:
    state: dict[str, Any]
    audit: dict[str, Any]
    state_hash: str
    state_bytes: int
    projector_hash: str = JEV_TYPESAFE_PROJECTOR_HASH


def _bounded(value: Any, *, limit: int = MAX_SEMANTIC_TEXT) -> Any:
    if value is None or isinstance(value, (bool, int, float)):
        return value
    rendered = str(value)
    if len(rendered) > limit:
        raise TypeSafeStateProjectionError("STATE_LIMIT_EXCEEDED")
    return rendered


def project_typesafe_state(sample: dict[str, Any]) -> TypeSafeStateProjection:
    if str(sample.get("action") or "") != "ENTRY_CANDIDATE":
        raise TypeSafeStateProjectionError("OUT_OF_SCOPE_ACTION")
    horizon = str(sample.get("horizon_intent") or "")
    if horizon not in {"SHORT", "MEDIUM"}:
        raise TypeSafeStateProjectionError("OUT_OF_SCOPE_HORIZON")

    snapshot = sample.get("snapshot")
    if not isinstance(snapshot, dict):
        raise TypeSafeStateProjectionError("CANONICAL_SNAPSHOT_MISSING")
    risk = snapshot.get("risk")
    if not isinstance(risk, dict):
        raise TypeSafeStateProjectionError("RISK_CONTEXT_INSUFFICIENT")
    if str(risk.get("status") or "") != "READY" or bool(risk.get("warning")):
        raise TypeSafeStateProjectionError("LOCAL_RISK_NOT_READY")

    conditions = snapshot.get("conditions")
    if not isinstance(conditions, dict):
        raise TypeSafeStateProjectionError("CONDITION_CONTEXT_INSUFFICIENT")
    if int(conditions.get("missing") or 0) != 0 or int(conditions.get("total") or 0) <= 0:
        raise TypeSafeStateProjectionError("LOCAL_CONDITIONS_NOT_COMPLETE")

    details = snapshot.get("_repro_condition_details")
    if not isinstance(details, list) or not details:
        raise TypeSafeStateProjectionError("CONDITION_DETAILS_MISSING")
    if len(details) > MAX_CONDITIONS:
        raise TypeSafeStateProjectionError("STATE_LIMIT_EXCEEDED")

    condition_context: list[dict[str, Any]] = []
    for detail in details:
        if not isinstance(detail, dict) or str(detail.get("status") or "") != "PASS":
            raise TypeSafeStateProjectionError("SEMANTIC_MAPPING_INCOMPLETE")
        metric_key = str(detail.get("metric_key") or "")
        semantic_label = CONDITION_SEMANTIC_LABELS.get(metric_key)
        if not metric_key or semantic_label is None:
            raise TypeSafeStateProjectionError("SEMANTIC_MAPPING_INCOMPLETE")
        condition_context.append(
            {
                "metric_key": metric_key,
                "status": "PASS",
                "current_value": _bounded(detail.get("current_value")),
                "required_value": _bounded(detail.get("required_value")),
                "semantic_label": semantic_label,
            }
        )

    strategy_key = str(snapshot.get("strategy") or sample.get("strategy") or "").strip()
    strategy_description = str(snapshot.get("strategy_description") or "").strip()
    if not strategy_key or not strategy_description:
        raise TypeSafeStateProjectionError("STRATEGY_CONTEXT_INSUFFICIENT")
    if len(strategy_description) > MAX_STRATEGY_DESCRIPTION:
        raise TypeSafeStateProjectionError("STATE_LIMIT_EXCEEDED")

    guide = snapshot.get("entry_risk_guide")
    if not isinstance(guide, dict):
        raise TypeSafeStateProjectionError("ENTRY_CONTEXT_INSUFFICIENT")
    price_rule = guide.get("price_rule")
    guide_action = guide.get("action")
    consistency = guide.get("price_consistency")
    if not isinstance(price_rule, dict) or not isinstance(guide_action, dict):
        raise TypeSafeStateProjectionError("ENTRY_CONTEXT_INSUFFICIENT")
    if not isinstance(consistency, dict):
        raise TypeSafeStateProjectionError("ENTRY_CONTEXT_INSUFFICIENT")
    status = str(consistency.get("status") or "")
    if status in {"INVALID", "WARNING"}:
        raise TypeSafeStateProjectionError("LOCAL_PRICE_PLAN_NOT_CLEAN")
    if status != "OK":
        raise TypeSafeStateProjectionError("ENTRY_CONTEXT_INSUFFICIENT")
    if str(guide_action.get("status") or "") != "ENTRY_CANDIDATE":
        raise TypeSafeStateProjectionError("ENTRY_CONTEXT_INSUFFICIENT")

    price_kind = str(price_rule.get("kind") or "")
    price_status = str(price_rule.get("status") or "")
    semantic_role = str(price_rule.get("semantic_role") or "")
    if not price_kind or not price_status or not semantic_role:
        raise TypeSafeStateProjectionError("ENTRY_CONTEXT_INSUFFICIENT")

    state = {
        "context": {
            "market": str(sample.get("market") or snapshot.get("market") or ""),
            "as_of_date": str(sample.get("signal_date") or snapshot.get("data_date") or ""),
            "horizon_intent": horizon,
        },
        "strategy_context": {
            "strategy_key": strategy_key,
            "strategy_description": strategy_description,
        },
        "condition_context": condition_context,
        "entry_context": {
            "price_rule": {
                "kind": price_kind,
                "status": price_status,
                "semantic_role": semantic_role,
                "executable_entry_range": bool(
                    price_rule.get("executable_entry_range", False)
                ),
            },
            "action": {"status": "ENTRY_CANDIDATE"},
            "price_consistency": {
                "classification": str(consistency.get("classification") or ""),
                "semantic_overlap": bool(consistency.get("semantic_overlap", False)),
            },
        },
        "baseline": {
            "action": "ENTRY_CANDIDATE",
            "candidate_state": str(
                sample.get("candidate_state")
                or snapshot.get("candidate_state")
                or "READY"
            ),
        },
    }
    if not state["context"]["market"] or not state["context"]["as_of_date"]:
        raise TypeSafeStateProjectionError("BASELINE_IDENTITY_INSUFFICIENT")
    encoded = canonical_json(state).encode("utf-8")
    if len(encoded) > MAX_STATE_BYTES:
        raise TypeSafeStateProjectionError("STATE_LIMIT_EXCEEDED")

    audit = {
        "capture_run_id": sample.get("capture_run_id"),
        "sample_index": sample.get("sample_index"),
        "snapshot_hash": sample.get("snapshot_hash"),
        "scanner_version": sample.get("scanner_version"),
        "scanner_baseline": sample.get("scanner_baseline"),
        "input_fingerprint": sample.get("input_fingerprint"),
        "strategy_version_id": snapshot.get("strategy_version_id"),
        "strategy_definition_hash": snapshot.get("strategy_definition_hash"),
        "horizon_policy_version": sample.get("horizon_policy_version"),
    }
    return TypeSafeStateProjection(
        state=state,
        audit=audit,
        state_hash=digest_json(state),
        state_bytes=len(encoded),
    )
