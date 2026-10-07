from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.jev.protocol_canonical import (
    JEV_PROTOCOL_CANONICALIZATION_VERSION,
    JEV_PROTOCOL_HASH_ALGORITHM,
    digest_protocol_json_v2,
    validate_protocol_identity_v2,
)
from app.jev.typesafe_canary_v4 import (
    CANARY_V4_PROTOCOL_PATH,
    CANARY_V4_REPETITIONS,
    CANARY_V4_SYSTEM_ONE_ATTEMPTS,
    CANARY_V4_TOTAL_API_ATTEMPTS_MAX,
    TypeSafeCanaryV4Error,
    evaluate_locked_threshold_v4,
    load_frozen_canary_v4_protocol,
    select_threshold_from_selection_v4,
    synthetic_canary_v4_fixtures,
    threshold_candidate_grid_v4,
    validate_canary_v4_contract,
)
from app.jev.typesafe_questions_v4 import STRATEGY_RELATION_CONFLICT


def _records(
    artifact: dict,
    partition: str,
    *,
    positive: float,
    negative: float,
    soft: float,
) -> list[dict]:
    rows = [
        item
        for item in artifact["spec"]["fixtures"]
        if item["partition"] == partition
        and item["route"] == "PROVIDER_CALL"
    ]
    unique = {}
    for item in rows:
        unique.setdefault(item["projected_state_hash"], item)

    records = []
    for state_hash, fixture in sorted(unique.items()):
        gold = fixture["expected_q1_gold"]
        probability = positive if gold is True else negative if gold is False else soft
        for repetition in range(1, CANARY_V4_REPETITIONS + 1):
            records.append(
                {
                    "projected_state_hash": state_hash,
                    "repetition": repetition,
                    "probability": probability,
                }
            )
    return records


def test_v4_fixture_partitions_and_unique_wire_budget_are_frozen() -> None:
    artifact = validate_canary_v4_contract()
    fixtures = artifact["spec"]["fixtures"]
    assert len(fixtures) == 18
    assert len({item["fixture_id"] for item in fixtures}) == 18
    assert threshold_candidate_grid_v4() == [0.5, 0.7, 0.9]
    assert artifact["spec"]["partition_contract"] == {
        "selection_fixture_rows": 9,
        "validation_fixture_rows": 9,
        "selection_unique_provider_wires": 4,
        "validation_unique_provider_wires": 4,
        "provider_reachable_positive_residual_count": 0,
    }
    assert artifact["spec"]["planned_systemone_calls"] == 40
    assert CANARY_V4_SYSTEM_ONE_ATTEMPTS == 40
    assert CANARY_V4_TOTAL_API_ATTEMPTS_MAX == 41
    assert artifact["spec"]["budget"]["max_reserved_exposure_usd"] == 0.04
    assert artifact["spec"]["budget"]["reserved_exposure_ceiling_usd"] == 0.05
    assert artifact["spec"]["budget"]["project_absolute_ceiling_usd"] == 0.25


def test_v4_required_failure_modes_and_partition_leakage_rule() -> None:
    fixtures = synthetic_canary_v4_fixtures()
    required = {
        "DIRECT_CONTRADICTION",
        "REQUIRED_CONDITION_COLLAPSE",
        "COMPOSITIONAL_CONFLICT",
        "ALLOWED_EXCEPTION",
        "WEAK_SEMANTIC_PHRASING",
        "NEAR_BOUNDARY_AMBIGUITY",
        "NEGATIVE_TRAP",
        "LOCAL_DETERMINISTIC_CONFLICT",
        "LOCAL_MISSING",
        "LOCAL_AMBIGUOUS",
        "Q1_Q2_ISOLATION",
    }
    assert required <= {item["failure_mode"] for item in fixtures}
    selection = {
        item["semantic_scenario_id"]
        for item in fixtures
        if item["partition"] == "selection"
    }
    validation = {
        item["semantic_scenario_id"]
        for item in fixtures
        if item["partition"] == "validation"
    }
    assert selection.isdisjoint(validation)


def test_v4_provider_wire_has_only_four_allowed_areas_and_no_gold() -> None:
    artifact = validate_canary_v4_contract()
    forbidden = set(artifact["spec"]["forbidden_wire_keys"])
    for fixture in artifact["spec"]["fixtures"]:
        if fixture["route"] != "PROVIDER_CALL":
            continue
        state = fixture["projected_state"]
        assert set(state) == {
            "strategy_intent",
            "term_definitions",
            "authored_relations",
            "passed_condition_meanings",
        }
        encoded = json.dumps(state, ensure_ascii=False).lower()
        for key in forbidden:
            assert f'"{key.lower()}"' not in encoded
        assert STRATEGY_RELATION_CONFLICT not in state


def test_v4_local_only_rows_never_have_provider_state() -> None:
    fixtures = synthetic_canary_v4_fixtures()
    local = [item for item in fixtures if item["route"] == "LOCAL_ONLY"]
    assert local
    assert all(item["projected_state"] is None for item in local)
    assert {
        item["expected_local_status"]
        for item in local
    } >= {
        "LOCAL_MATCH",
        "LOCAL_CONFLICT",
        "LOCAL_INCOMPLETE",
        "LOCAL_AMBIGUOUS",
    }


def test_v4_isolation_pairs_share_q1_wire_but_not_q2_variant() -> None:
    fixtures = synthetic_canary_v4_fixtures()
    for family in ("SEL-Q2", "VAL-Q2"):
        rows = [
            item
            for item in fixtures
            if item.get("isolation_family_id") == family
        ]
        assert len(rows) == 2
        assert rows[0]["projected_state_hash"] == rows[1]["projected_state_hash"]
        assert rows[0]["projected_state"] == rows[1]["projected_state"]
        assert rows[0]["q2_variant"] != rows[1]["q2_variant"]


def test_v4_threshold_margin_and_tie_break_are_precommitted() -> None:
    artifact = validate_canary_v4_contract()
    records = _records(
        artifact,
        "selection",
        positive=0.90,
        negative=0.30,
        soft=0.10,
    )
    result = select_threshold_from_selection_v4(records, artifact)
    assert result["selected"] is not None
    # 0.50 and 0.70 both have worst margin 0.20; soft counts tie,
    # therefore the final frozen tie-break chooses the lower threshold.
    assert result["selected"]["threshold_strategy"] == 0.5
    assert result["selected"]["worst_class_margin"] == pytest.approx(0.2)

    by_threshold = {
        item["threshold_strategy"]: item
        for item in result["candidates"]
    }
    assert by_threshold[0.9]["eligible"] is False


def test_v4_soft_review_count_precedes_lower_threshold_tie_break() -> None:
    artifact = validate_canary_v4_contract()
    records = _records(
        artifact,
        "selection",
        positive=0.90,
        negative=0.30,
        soft=0.60,
    )
    result = select_threshold_from_selection_v4(records, artifact)
    assert result["selected"] is not None
    assert result["selected"]["threshold_strategy"] == 0.7
    assert result["selected"]["soft_review_required_count"] == 0


def test_v4_validation_uses_only_locked_threshold_no_rescue() -> None:
    artifact = validate_canary_v4_contract()
    selection = _records(
        artifact,
        "selection",
        positive=0.95,
        negative=0.05,
        soft=0.20,
    )
    selected = select_threshold_from_selection_v4(selection, artifact)["selected"]
    assert selected is not None

    validation = _records(
        artifact,
        "validation",
        positive=0.55,
        negative=0.05,
        soft=0.20,
    )
    result = evaluate_locked_threshold_v4(
        validation,
        artifact,
        selected,
    )
    assert result["threshold_strategy"] == selected["threshold_strategy"]
    assert result["eligible"] is False


def test_v4_protocol_file_is_v2_canonical_and_exactly_frozen() -> None:
    runtime = validate_canary_v4_contract()
    stored = load_frozen_canary_v4_protocol()
    assert CANARY_V4_PROTOCOL_PATH.is_file()
    assert stored == runtime
    assert stored["canonicalization_version"] == JEV_PROTOCOL_CANONICALIZATION_VERSION
    assert stored["hash_algorithm"] == JEV_PROTOCOL_HASH_ALGORITHM
    assert stored["protocol_hash"] == digest_protocol_json_v2(stored["spec"])
    body = dict(stored)
    artifact_hash = body.pop("artifact_hash")
    assert artifact_hash == digest_protocol_json_v2(body)
    identity = validate_protocol_identity_v2(
        stored_artifact=stored,
        runtime_artifact=runtime,
    )
    assert identity["protocol_hash"] == stored["protocol_hash"]


def test_v4_protocol_drift_is_rejected(tmp_path: Path) -> None:
    artifact = validate_canary_v4_contract()
    changed = json.loads(json.dumps(artifact))
    changed["spec"]["threshold_candidates"].append(0.8)
    path = tmp_path / "V4.json"
    path.write_text(
        json.dumps(changed, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(TypeSafeCanaryV4Error):
        load_frozen_canary_v4_protocol(path)
