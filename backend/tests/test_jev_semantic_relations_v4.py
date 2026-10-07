from __future__ import annotations

from app.simulation.strategy_governance import current_strategy_definitions
from app.strategy.condition_assertions import (
    CONDITION_SEMANTIC_ASSERTION_MAPPING_VERSION,
    STANCE_CONTRADICTS,
    STANCE_SUPPORTS,
    STANCE_UNRESOLVED,
    STANCE_WEAKENS,
    assertion_sources,
    project_passed_condition_assertions,
)
from app.strategy.condition_semantics import condition_sources
from app.strategy.models import StrategyName
from app.strategy.semantic_composition import (
    LOCAL_AMBIGUOUS,
    LOCAL_CONFLICT,
    LOCAL_INCOMPLETE,
    LOCAL_MATCH,
    RESIDUAL_SEMANTIC_REVIEW,
    compose_semantics,
)
from app.strategy.semantic_contract import (
    JEV_SEMANTIC_SOURCE_VERSION if False else SEMANTIC_STATUS_COMPLETE,
)
from app.strategy.semantic_relations import (
    RELATION_ALLOWS_IF,
    RELATION_EXCLUDES,
    RELATION_REQUIRES_ALL,
    RELATION_REQUIRES_ANY,
    STRATEGY_SEMANTIC_RELATION_CONTRACT_VERSION,
    authored_relation_strategy_keys,
    resolve_strategy_semantic_relation_contract,
)
from app.strategy.semantic_source import JEV_SEMANTIC_SOURCE_VERSION
from app.strategy.semantic_source_v2 import (
    JEV_SEMANTIC_SOURCE_VERSION_V2,
    build_semantic_source_v2,
    verify_semantic_source_v2,
)


OPERATING_STRATEGIES = {
    StrategyName.TREND_FOLLOWING.value,
    StrategyName.PULLBACK.value,
    StrategyName.BREAKOUT.value,
    StrategyName.SUPPORT_BOUNCE.value,
    StrategyName.OVERSOLD_BOUNCE.value,
    StrategyName.RANGE_TRADING.value,
    StrategyName.MOMENTUM_CONTINUATION.value,
    StrategyName.VOLATILITY_SQUEEZE.value,
    StrategyName.MA20_REBOUND.value,
    StrategyName.TREND_RECOVERY.value,
}


def _current_binding_by_key() -> dict[str, object]:
    return {
        item.strategy_key: item
        for item in current_strategy_definitions()
    }


def _relation_contract(
    *,
    kind: str = RELATION_REQUIRES_ALL,
    members: list[str] | None = None,
    guards: list[str] | None = None,
    materiality: str = "HARD",
) -> dict:
    concept_ids = ["a", "b", "guard"]
    return {
        "concepts": [
            {"concept_id": item, "definition_id": item, "text": item}
            for item in concept_ids
        ],
        "relations": [
            {
                "relation_id": "r1",
                "kind": kind,
                "members": list(members or ["a", "b"]),
                "guards": list(guards or []),
                "materiality": materiality,
            }
        ],
    }


def _assertion(concept: str, stance: str, index: int) -> dict:
    return {
        "condition_id": f"c{index}",
        "source_condition": f"source-{index}",
        "concept_refs": [concept],
        "stance": stance,
        "observed_meaning": f"meaning-{index}",
    }


def test_v4_relation_contract_covers_exactly_10_operating_strategies() -> None:
    assert set(authored_relation_strategy_keys()) == OPERATING_STRATEGIES
    assert StrategyName.NO_TRADE.value not in authored_relation_strategy_keys()


def test_condition_assertion_sources_match_existing_v1_condition_sources() -> None:
    for strategy_key in sorted(OPERATING_STRATEGIES):
        assert set(assertion_sources(strategy_key)) == set(
            condition_sources(strategy_key)
        )


def test_all_relation_members_and_condition_assertions_reference_valid_concepts() -> None:
    bindings = _current_binding_by_key()

    for strategy_key in sorted(OPERATING_STRATEGIES):
        binding = bindings[strategy_key]
        resolution = resolve_strategy_semantic_relation_contract(
            strategy_key=strategy_key,
            strategy_version_id=binding.strategy_version_id,
            strategy_definition_hash=binding.definition_hash,
        )
        assert resolution.status == SEMANTIC_STATUS_COMPLETE
        assert resolution.contract is not None

        concept_ids = {
            item["concept_id"] for item in resolution.contract["concepts"]
        }
        assert concept_ids

        for relation in resolution.contract["relations"]:
            assert set(relation["members"]) <= concept_ids
            assert set(relation["guards"]) <= concept_ids

        v1_items = [
            {
                "condition_id": f"condition-{index:02d}",
                "source_condition": source,
                "status": "PASS",
                "observed_meaning": f"meaning-{index}",
            }
            for index, source in enumerate(condition_sources(strategy_key), start=1)
        ]
        projected = project_passed_condition_assertions(
            strategy_key=strategy_key,
            condition_items=v1_items,
        )
        assert projected.status == SEMANTIC_STATUS_COMPLETE
        for item in projected.items:
            assert set(item["concept_refs"]) <= concept_ids


def test_local_match() -> None:
    result = compose_semantics(
        relation_contract=_relation_contract(),
        assertions=[
            _assertion("a", STANCE_SUPPORTS, 1),
            _assertion("b", STANCE_SUPPORTS, 2),
        ],
    )
    assert result.status == LOCAL_MATCH


def test_local_conflict() -> None:
    result = compose_semantics(
        relation_contract=_relation_contract(),
        assertions=[
            _assertion("a", STANCE_SUPPORTS, 1),
            _assertion("b", STANCE_CONTRADICTS, 2),
        ],
    )
    assert result.status == LOCAL_CONFLICT


def test_local_incomplete() -> None:
    result = compose_semantics(
        relation_contract=_relation_contract(),
        assertions=[_assertion("a", STANCE_SUPPORTS, 1)],
    )
    assert result.status == LOCAL_INCOMPLETE


def test_local_ambiguous() -> None:
    result = compose_semantics(
        relation_contract=_relation_contract(members=["a"]),
        assertions=[
            _assertion("a", STANCE_SUPPORTS, 1),
            _assertion("a", STANCE_CONTRADICTS, 2),
        ],
    )
    assert result.status == LOCAL_AMBIGUOUS


def test_residual_semantic_review() -> None:
    result = compose_semantics(
        relation_contract=_relation_contract(),
        assertions=[
            _assertion("a", STANCE_SUPPORTS, 1),
            _assertion("b", STANCE_WEAKENS, 2),
        ],
    )
    assert result.status == RESIDUAL_SEMANTIC_REVIEW


def test_requires_any_allows_if_and_excludes_are_deterministic() -> None:
    any_result = compose_semantics(
        relation_contract=_relation_contract(
            kind=RELATION_REQUIRES_ANY,
            members=["a", "b"],
        ),
        assertions=[
            _assertion("a", STANCE_CONTRADICTS, 1),
            _assertion("b", STANCE_SUPPORTS, 2),
        ],
    )
    assert any_result.status == LOCAL_MATCH

    allowed = compose_semantics(
        relation_contract=_relation_contract(
            kind=RELATION_ALLOWS_IF,
            members=["a"],
            guards=["guard"],
        ),
        assertions=[
            _assertion("a", STANCE_WEAKENS, 1),
            _assertion("guard", STANCE_SUPPORTS, 2),
        ],
    )
    assert allowed.status == LOCAL_MATCH

    unresolved = compose_semantics(
        relation_contract=_relation_contract(
            kind=RELATION_ALLOWS_IF,
            members=["a"],
            guards=["guard"],
        ),
        assertions=[
            _assertion("a", STANCE_UNRESOLVED, 1),
            _assertion("guard", STANCE_SUPPORTS, 2),
        ],
    )
    assert unresolved.status == RESIDUAL_SEMANTIC_REVIEW

    excluded = compose_semantics(
        relation_contract=_relation_contract(
            kind=RELATION_EXCLUDES,
            members=["a"],
        ),
        assertions=[_assertion("a", STANCE_SUPPORTS, 1)],
    )
    assert excluded.status == LOCAL_CONFLICT


def test_current_production_pass_meanings_do_not_create_fake_jev_work() -> None:
    bindings = _current_binding_by_key()

    for strategy_key in sorted(OPERATING_STRATEGIES):
        binding = bindings[strategy_key]
        total = len(condition_sources(strategy_key))
        candidate = {
            "strategy": strategy_key,
            "strategy_version_id": binding.strategy_version_id,
            "strategy_definition_hash": binding.definition_hash,
            "action": "ENTRY_CANDIDATE",
            "conditions": {
                "passed": total,
                "total": total,
                "missing": 0,
            },
        }

        source = build_semantic_source_v2(candidate)
        valid, reason = verify_semantic_source_v2(source)

        assert valid is True, (strategy_key, reason)
        assert source["local_semantic_composition"]["status"] == LOCAL_MATCH
        assert source["readiness"]["residual_review_eligible"] is False


def test_v1_source_identity_remains_historical_and_v2_is_separate() -> None:
    assert JEV_SEMANTIC_SOURCE_VERSION == "JEV_SEMANTIC_SOURCE_V1"
    assert JEV_SEMANTIC_SOURCE_VERSION_V2 == "JEV_SEMANTIC_SOURCE_V2"
    assert JEV_SEMANTIC_SOURCE_VERSION_V2 != JEV_SEMANTIC_SOURCE_VERSION
    assert (
        STRATEGY_SEMANTIC_RELATION_CONTRACT_VERSION
        == "STRATEGY_SEMANTIC_RELATION_CONTRACT_V1"
    )
    assert (
        CONDITION_SEMANTIC_ASSERTION_MAPPING_VERSION
        == "CONDITION_SEMANTIC_ASSERTION_MAPPING_V1"
    )
