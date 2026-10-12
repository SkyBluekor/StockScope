"""Offline structural check of JEV V4 routes using the current authored rules.

No Scanner execution, market data, stored capture mutation or provider calls.
Synthesized PASS condition rows are contract probes, NOT observed market evidence.
"""
from __future__ import annotations

from typing import Any

from app.simulation.strategy_governance import current_strategy_definitions
from app.strategy.condition_assertions import (
    STANCE_SUPPORTS,
    assertion_sources,
    project_passed_condition_assertions,
)
from app.strategy.semantic_composition import (
    LOCAL_MATCH,
    RESIDUAL_SEMANTIC_REVIEW,
    compose_semantics,
)
from app.strategy.semantic_contract import SEMANTIC_STATUS_COMPLETE
from app.strategy.semantic_relations import resolve_strategy_semantic_relation_contract


DIAGNOSTIC_VERSION = "JEV_ACT2_S2_PASS_MAPPING_REACHABILITY_V1"


def audit_current_pass_mapping_reachability() -> dict[str, Any]:
    """Check complete, current PASS-condition mappings of every production strategy.

    This is a structural probe only. A strategy marked LOCAL_MATCH here may
    still have no market candidates, and a future contract change can alter
    reachability. Incomplete contracts must NEVER be treated as no-residual.
    """
    rows: list[dict[str, Any]] = []
    for definition in current_strategy_definitions():
        key = definition.strategy_key
        sources = assertion_sources(key)
        relation = resolve_strategy_semantic_relation_contract(
            strategy_key=key,
            strategy_version_id=definition.strategy_version_id,
            strategy_definition_hash=definition.definition_hash,
        )
        # Never invent a real Scanner candidate or market PASS: these probes
        # exercise only the authored PASS mapping and relationship contracts.
        probe = project_passed_condition_assertions(
            strategy_key=key,
            condition_items=[
                {
                    "status": "PASS",
                    "source_condition": source,
                    "condition_id": f"contract-probe-{index}",
                    "observed_meaning": "STRUCTURAL_PROBE_NOT_MARKET_EVIDENCE",
                }
                for index, source in enumerate(sources)
            ],
        )
        contract = relation.contract
        reasons: list[str] = []
        if relation.status != SEMANTIC_STATUS_COMPLETE or not isinstance(contract, dict):
            reasons.append(relation.reason_code or "RELATION_CONTRACT_UNAVAILABLE")
        if probe.status != SEMANTIC_STATUS_COMPLETE:
            reasons.extend(probe.reason_codes or ("ASSERTION_MAPPING_UNAVAILABLE",))

        composition_status: str | None = None
        relation_kinds: list[str] = []
        relation_materialities: list[str] = []
        if not reasons and isinstance(contract, dict):
            relationships = list(contract.get("relations") or [])
            relation_kinds = sorted({str(r.get("kind") or "") for r in relationships})
            relation_materialities = sorted({
                str(r.get("materiality") or "") for r in relationships
            })
            composition_status = compose_semantics(
                relation_contract=contract,
                assertions=list(probe.items),
            ).status

        if reasons or not composition_status:
            verdict = "UNDETERMINED"
        elif composition_status == RESIDUAL_SEMANTIC_REVIEW:
            verdict = "RESIDUAL_FROM_PASS_MAPPING"
        elif composition_status == LOCAL_MATCH:
            verdict = "LOCAL_MATCH_FROM_PASS_MAPPING"
        else:
            verdict = "OTHER_LOCAL_RESULT_FROM_PASS_MAPPING"

        rows.append({
            "strategy": key,
            "pass_conditions": len(sources),
            "assertion_stances": sorted({str(item["stance"]) for item in probe.items}),
            "relation_kinds": relation_kinds,
            "relation_materialities": relation_materialities,
            "composition_status": composition_status,
            "verdict": verdict,
            "reason_codes": sorted(set(reasons)),
        })

    complete = sum(row["composition_status"] is not None for row in rows)
    matches = sum(row["verdict"] == "LOCAL_MATCH_FROM_PASS_MAPPING" for row in rows)
    residual = sum(row["verdict"] == "RESIDUAL_FROM_PASS_MAPPING" for row in rows)
    unresolved = len(rows) - complete
    # A complete PASS projection has exactly the fixed authored stances,
    # because project_passed_condition_assertions requires the full set.
    if unresolved:
        conclusion = "UNDETERMINED_CONTRACTS"
    elif residual:
        conclusion = "RESIDUAL_POSSIBLE_FROM_PASS_MAPPING"
    elif matches == len(rows) and rows:
        conclusion = "NO_RESIDUAL_FROM_CURRENT_COMPLETE_PASS_MAPPINGS"
    else:
        conclusion = "OTHER_LOCAL_ROUTES_NO_RESIDUAL_FROM_PASS_MAPPING"

    return {
        "version": DIAGNOSTIC_VERSION,
        "scope": "STRUCTURAL_ONLY_CURRENT_AUTHORED_COMPLETE_PASS_MAPPINGS",
        "real_market_samples_tested": 0,
        "provider_calls": 0,
        "strategy_count": len(rows),
        "complete_contracts": complete,
        "local_match_routes": matches,
        "residual_routes": residual,
        "undetermined_contracts": unresolved,
        "conclusion": conclusion,
        "strategies": rows,
    }
