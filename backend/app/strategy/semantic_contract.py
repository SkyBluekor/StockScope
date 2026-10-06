from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from app.strategy.models import StrategyName
from app.simulation.strategy_governance import current_strategy_definitions


STRATEGY_SEMANTIC_CONTRACT_VERSION = "STRATEGY_SEMANTIC_CONTRACT_V1"

ROLE_CONFIRMATION_ONLY = "CONFIRMATION_ONLY"
ROLE_EXECUTABLE_ENTRY = "EXECUTABLE_ENTRY"
ALLOWED_ENTRY_ROLES = frozenset({ROLE_CONFIRMATION_ONLY, ROLE_EXECUTABLE_ENTRY})

SEMANTIC_STATUS_COMPLETE = "COMPLETE"
SEMANTIC_STATUS_MISSING = "MISSING"
SEMANTIC_STATUS_AMBIGUOUS = "AMBIGUOUS"
SEMANTIC_STATUS_UNSUPPORTED = "UNSUPPORTED"
SEMANTIC_STATUS_STALE_VERSION = "STALE_VERSION"
SEMANTIC_STATUS_INVALID_BINDING = "INVALID_BINDING"

ENTRY_RULE_IDS = (
    "high-reference",
    "support-proximity",
    "ma20-reference",
    "resistance-room",
)


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


_COMMON_DEFINITIONS: dict[str, str] = {
    "trend_structure": (
        "Trend structure means the relative ordering and direction of moving-average "
        "and higher-high/higher-low conditions already evaluated by StockScope."
    ),
    "support_integrity": (
        "Support integrity means that the already-evaluated support or higher-low "
        "conditions have not asserted a structural support failure."
    ),
    "participation": (
        "Participation means the already-evaluated volume condition supplies the "
        "kind of market participation required by the strategy."
    ),
    "relative_strength": (
        "Relative strength means the already-evaluated market or sector comparison "
        "does not contradict the strategy's required directional strength."
    ),
    "compression": (
        "Compression means the already-evaluated volatility and volume conditions "
        "describe a quiet setup without asserting a completed directional breakout."
    ),
    "recovery_structure": (
        "Recovery structure means the already-evaluated moving-average and higher-low "
        "conditions describe stabilization or recovery rather than continuing damage."
    ),
    "mean_reversion_scope": (
        "Mean-reversion scope means the setup seeks a bounded technical rebound and "
        "does not by itself claim that a durable long-term uptrend has resumed."
    ),
    "range_structure": (
        "Range structure means the already-evaluated market, support, resistance, "
        "slope and volatility conditions remain compatible with non-trending behavior."
    ),
}


# Authored semantic meaning only. Runtime code must not derive these strings from
# StrategyEngine AST, user-facing descriptions, regexes, or an LLM.
_AUTHORED: dict[str, dict[str, Any]] = {
    StrategyName.TREND_FOLLOWING.value: {
        "intent_text": (
            "The setup requires an already-established rising structure. Limited "
            "short-term softness is not a conflict when the broader passed trend and "
            "relative-strength meanings remain supportive, but passed meanings that "
            "assert structural deterioration materially conflict with the strategy."
        ),
        "required_definition_ids": ["trend_structure", "relative_strength"],
    },
    StrategyName.PULLBACK.value: {
        "intent_text": (
            "The setup assumes an underlying positive trend temporarily retraces "
            "toward support without losing its recovery structure. A passed meaning "
            "that asserts broken support or continuing structural decline materially "
            "conflicts with the pullback intent."
        ),
        "required_definition_ids": ["trend_structure", "support_integrity"],
    },
    StrategyName.BREAKOUT.value: {
        "intent_text": (
            "The setup requires price pressure near a prior high together with "
            "supportive participation and directional structure. Passed meanings that "
            "instead assert retreat from the breakout area or absent required "
            "participation materially conflict with the breakout intent."
        ),
        "required_definition_ids": ["participation", "trend_structure"],
    },
    StrategyName.SUPPORT_BOUNCE.value: {
        "intent_text": (
            "The setup requires a still-valid support area with bounded volatility "
            "and enough room for a technical rebound. A passed meaning that asserts "
            "support failure or a market state incompatible with a rebound materially "
            "conflicts with this strategy."
        ),
        "required_definition_ids": ["support_integrity", "mean_reversion_scope"],
    },
    StrategyName.OVERSOLD_BOUNCE.value: {
        "intent_text": (
            "The setup is a bounded mean-reversion attempt after oversold pressure, "
            "not a declaration that a durable uptrend has resumed. Passed meanings "
            "that assert a destroyed support structure or panic conditions materially "
            "conflict with that bounded rebound intent."
        ),
        "required_definition_ids": ["mean_reversion_scope", "support_integrity"],
    },
    StrategyName.RANGE_TRADING.value: {
        "intent_text": (
            "The setup assumes non-trending range structure with nearby support, "
            "remaining resistance room, and controlled volatility. Passed meanings "
            "that assert a directional trend break or incompatible volatility "
            "materially conflict with range-trading intent."
        ),
        "required_definition_ids": ["range_structure", "support_integrity"],
    },
    StrategyName.MOMENTUM_CONTINUATION.value: {
        "intent_text": (
            "The setup requires already-strong price structure, participation and "
            "relative strength to remain mutually supportive. A single mild condition "
            "does not define the setup; passed meanings that collectively assert lost "
            "momentum or structural deterioration materially conflict with it."
        ),
        "required_definition_ids": ["trend_structure", "participation", "relative_strength"],
    },
    StrategyName.VOLATILITY_SQUEEZE.value: {
        "intent_text": (
            "The setup requires compression while the directional structure remains "
            "intact; compression alone does not mean a breakout already occurred. "
            "Passed meanings that assert expanding instability or broken structure "
            "materially conflict with the squeeze intent."
        ),
        "required_definition_ids": ["compression", "trend_structure"],
    },
    StrategyName.MA20_REBOUND.value: {
        "intent_text": (
            "The setup requires price to remain near a rising 20-day reference while "
            "the recent structure is still supportive of a rebound. Merely touching "
            "the reference is not sufficient if passed meanings assert structural "
            "breakdown."
        ),
        "required_definition_ids": ["trend_structure", "support_integrity"],
    },
    StrategyName.TREND_RECOVERY.value: {
        "intent_text": (
            "The setup represents an early recovery after weakness, so stabilization "
            "and higher-low recovery matter more than claiming a fully established "
            "uptrend. Passed meanings that assert continuing structural damage "
            "materially conflict with the recovery intent."
        ),
        "required_definition_ids": ["recovery_structure", "support_integrity"],
    },
}


@dataclass(frozen=True, slots=True)
class StrategySemanticResolution:
    status: str
    reason_code: str | None
    contract: dict[str, Any] | None


@lru_cache(maxsize=1)
def _current_bindings() -> dict[str, tuple[str, str]]:
    return {
        item.strategy_key: (item.strategy_version_id, item.definition_hash)
        for item in current_strategy_definitions()
    }


def authored_strategy_keys() -> tuple[str, ...]:
    return tuple(sorted(_AUTHORED))


def _entry_rules() -> list[dict[str, str]]:
    return [
        {"rule_id": rule_id, "intent_role": ROLE_CONFIRMATION_ONLY}
        for rule_id in ENTRY_RULE_IDS
    ]


def resolve_strategy_semantic_contract(
    *,
    strategy_key: str,
    strategy_version_id: str | None,
    strategy_definition_hash: str | None,
) -> StrategySemanticResolution:
    key = str(strategy_key or "").strip().lower()
    version_id = str(strategy_version_id or "").strip()
    definition_hash = str(strategy_definition_hash or "").strip()
    if not key or not version_id or not definition_hash:
        return StrategySemanticResolution(
            SEMANTIC_STATUS_MISSING,
            "SEMANTIC_CONTRACT_BINDING_MISSING",
            None,
        )
    try:
        strategy = StrategyName(key)
    except ValueError:
        return StrategySemanticResolution(
            SEMANTIC_STATUS_UNSUPPORTED,
            "SEMANTIC_CONTRACT_STRATEGY_UNSUPPORTED",
            None,
        )
    if strategy is StrategyName.NO_TRADE or key not in _AUTHORED:
        return StrategySemanticResolution(
            SEMANTIC_STATUS_UNSUPPORTED,
            "SEMANTIC_CONTRACT_STRATEGY_UNSUPPORTED",
            None,
        )

    current = _current_bindings().get(key)
    if current is None:
        return StrategySemanticResolution(
            SEMANTIC_STATUS_UNSUPPORTED,
            "SEMANTIC_CONTRACT_STRATEGY_UNSUPPORTED",
            None,
        )
    if current != (version_id, definition_hash):
        return StrategySemanticResolution(
            SEMANTIC_STATUS_STALE_VERSION,
            "SEMANTIC_CONTRACT_STRATEGY_BINDING_MISMATCH",
            None,
        )

    authored = _AUTHORED[key]
    required_ids = sorted({str(item) for item in authored["required_definition_ids"]})
    definitions = [
        {"id": item, "text": _COMMON_DEFINITIONS[item]}
        for item in required_ids
    ]
    payload = {
        "contract_version": STRATEGY_SEMANTIC_CONTRACT_VERSION,
        "strategy_version_id": version_id,
        "strategy_definition_hash": definition_hash,
        "strategy_key": key,
        "q1": {
            "intent_text": str(authored["intent_text"]),
            "required_definition_ids": required_ids,
            "definitions": definitions,
            "review_mode": "SEMANTIC_COMPOSITION",
        },
        "entry_rules": _entry_rules(),
    }
    contract_hash = _digest(payload)
    return StrategySemanticResolution(
        SEMANTIC_STATUS_COMPLETE,
        None,
        {**payload, "semantic_contract_hash": contract_hash},
    )


def semantic_contract_hash(contract: dict[str, Any]) -> str:
    body = dict(contract)
    body.pop("semantic_contract_hash", None)
    return _digest(body)
