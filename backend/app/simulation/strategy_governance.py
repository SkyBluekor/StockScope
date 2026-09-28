from __future__ import annotations

import ast
import hashlib
import inspect
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from app.strategy.engine import StrategyEngine
from app.strategy.models import StrategyName


STRATEGY_GOVERNANCE_SCHEMA_VERSION = "VN_P5_S1_STRATEGY_GOVERNANCE_V1"
STRATEGY_FINGERPRINT_CONTRACT_VERSION = "VN_P5_S1_STRATEGY_FINGERPRINT_V1"
STRATEGY_BOOTSTRAP_DEFINITION_VERSION = "VN_P5_S1_CURRENT_10_BOOTSTRAP_V1"
STRATEGY_BOOTSTRAP_SOURCE = "CURRENT_10_BASELINE"

PRODUCTION_STRATEGIES: tuple[StrategyName, ...] = (
    StrategyName.TREND_FOLLOWING,
    StrategyName.PULLBACK,
    StrategyName.BREAKOUT,
    StrategyName.SUPPORT_BOUNCE,
    StrategyName.OVERSOLD_BOUNCE,
    StrategyName.RANGE_TRADING,
    StrategyName.MOMENTUM_CONTINUATION,
    StrategyName.VOLATILITY_SQUEEZE,
    StrategyName.MA20_REBOUND,
    StrategyName.TREND_RECOVERY,
)

_STRATEGY_METHODS: dict[StrategyName, str] = {
    StrategyName.TREND_FOLLOWING: "_trend_following",
    StrategyName.PULLBACK: "_pullback",
    StrategyName.BREAKOUT: "_breakout",
    StrategyName.SUPPORT_BOUNCE: "_support_bounce",
    StrategyName.OVERSOLD_BOUNCE: "_oversold_bounce",
    StrategyName.RANGE_TRADING: "_range_trading",
    StrategyName.MOMENTUM_CONTINUATION: "_momentum_continuation",
    StrategyName.VOLATILITY_SQUEEZE: "_volatility_squeeze",
    StrategyName.MA20_REBOUND: "_ma20_rebound",
    StrategyName.TREND_RECOVERY: "_trend_recovery",
}

_SHARED_ENGINE_METHODS = (
    "_risk_gate",
    "_action_plan",
    "_evaluate",
)


class StrategyGovernanceError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class StrategyDefinition:
    strategy_version_id: str
    strategy_key: str
    definition_version: str
    definition_hash: str
    fingerprint_contract_version: str
    implementation_key: str
    operational_status: str
    validation_status: str
    source: str
    definition: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


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


def _strategy_engine_ast() -> ast.ClassDef:
    source_path_raw = inspect.getsourcefile(StrategyEngine)
    if not source_path_raw:
        raise StrategyGovernanceError(
            "StrategyEngine source path를 확인할 수 없습니다."
        )
    source_path = Path(source_path_raw)
    try:
        tree = ast.parse(
            source_path.read_text(encoding="utf-8-sig"),
            filename=str(source_path),
        )
    except (OSError, UnicodeError, SyntaxError) as exc:
        raise StrategyGovernanceError(
            f"StrategyEngine source를 읽을 수 없습니다: {exc}"
        ) from exc

    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == "StrategyEngine":
            return node
    raise StrategyGovernanceError("StrategyEngine class AST를 찾을 수 없습니다.")


def _method_ast(class_node: ast.ClassDef, method_name: str) -> str:
    for node in class_node.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name == method_name:
                return ast.dump(
                    node,
                    annotate_fields=True,
                    include_attributes=False,
                )
    raise StrategyGovernanceError(
        f"StrategyEngine.{method_name} 구현을 찾을 수 없습니다."
    )


def strategy_definition(strategy: StrategyName) -> StrategyDefinition:
    if strategy == StrategyName.NO_TRADE:
        raise StrategyGovernanceError(
            "NO_TRADE는 전략 Registry 대상이 아니라 안전 판단 상태입니다."
        )
    method_name = _STRATEGY_METHODS.get(strategy)
    if method_name is None:
        raise StrategyGovernanceError(
            f"지원하지 않는 production strategy입니다: {strategy.value}"
        )

    class_node = _strategy_engine_ast()
    shared = {
        method: _method_ast(class_node, method)
        for method in _SHARED_ENGINE_METHODS
    }
    payload = {
        "fingerprint_contract_version": STRATEGY_FINGERPRINT_CONTRACT_VERSION,
        "strategy_key": strategy.value,
        "implementation_key": f"StrategyEngine.{method_name}",
        "strategy_method_ast": _method_ast(class_node, method_name),
        "shared_engine_ast": shared,
        "scope": {
            "risk_gate_shared": True,
            "scoring_shared": True,
            "action_plan_shared": True,
            "selection_policy_included": False,
            "no_trade_included": False,
        },
    }
    definition_hash = _digest(payload)
    version_id = str(
        uuid5(
            NAMESPACE_URL,
            (
                "stockscope:strategy-version:"
                f"{STRATEGY_FINGERPRINT_CONTRACT_VERSION}:"
                f"{strategy.value}:{definition_hash}"
            ),
        )
    )
    return StrategyDefinition(
        strategy_version_id=version_id,
        strategy_key=strategy.value,
        definition_version=STRATEGY_BOOTSTRAP_DEFINITION_VERSION,
        definition_hash=definition_hash,
        fingerprint_contract_version=STRATEGY_FINGERPRINT_CONTRACT_VERSION,
        implementation_key=f"StrategyEngine.{method_name}",
        operational_status="OPERATING",
        validation_status="UNVERIFIED",
        source=STRATEGY_BOOTSTRAP_SOURCE,
        definition=payload,
    )


def current_strategy_definitions() -> tuple[StrategyDefinition, ...]:
    definitions = tuple(
        strategy_definition(strategy)
        for strategy in PRODUCTION_STRATEGIES
    )
    keys = [item.strategy_key for item in definitions]
    if len(definitions) != 10 or len(set(keys)) != 10:
        raise StrategyGovernanceError(
            "현재 production strategy bootstrap은 정확히 10개여야 합니다."
        )
    if StrategyName.NO_TRADE.value in keys:
        raise StrategyGovernanceError(
            "NO_TRADE는 production strategy registry에 포함할 수 없습니다."
        )
    return definitions


def current_strategy_set_fingerprint() -> str:
    rows = [
        {
            "strategy_key": item.strategy_key,
            "definition_hash": item.definition_hash,
            "fingerprint_contract_version": item.fingerprint_contract_version,
        }
        for item in current_strategy_definitions()
    ]
    return _digest(rows)
