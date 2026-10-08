from __future__ import annotations

import sqlite3
from copy import deepcopy
from pathlib import Path

from app.backtest.candidate_priority import priority_sort_key, rank_candidates
from tools.data.migrate_prospective_vnp2s2 import migrate_prospective_store
from tools.dev import sync_local


def _candidate(code: str, structural: float) -> dict:
    return {
        "market": "KOSPI", "code": code, "strategy": "pullback",
        "conditions": {"passed": 6, "total": 6, "missing": 0},
        "risk": {"status": "READY", "warning": False, "warnings": []},
        "candidate_state": "READY", "action": "ENTRY_CANDIDATE",
        "current_price": 100.0,
        "entry_risk_guide": {
            "price_rule": {"kind": "RANGE", "gap_pct": 0.0},
            "risk": {
                "entry_reference_price": 100.0,
                "structural_target1_price": structural,
            },
        },
        "_strategy_fit_score": 100.0,
    }


def test_rank_trace_matches_actual_sort_and_never_mutates_candidate() -> None:
    candidates = [
        _candidate("000100", 110.0),
        _candidate("000200", 105.0),
        _candidate("000300", 120.0),
    ]
    baseline, _ = rank_candidates(deepcopy(candidates))
    evidence: list[dict] = []
    ranked, _ = rank_candidates(candidates, evidence_sink=evidence)
    assert [item["code"] for item in ranked] == [item["code"] for item in baseline]
    assert [item["priority"] for item in ranked] == [item["priority"] for item in baseline]
    assert [row["final_rank"] for row in evidence] == [1, 2, 3]
    assert evidence[0]["code"] == "000200"
    assert evidence[0]["tie_resolution"]["breaker"] == "STRUCTURAL_TARGET_NEAREST_PROMOTE"
    for candidate, row in zip(ranked, evidence):
        s = row["sort_components"]
        actual = (
            s["tier_order"], s["missing"], s["risk_quality"],
            s["entry_gap_missing"], s["entry_gap_pct"],
            s["negative_strategy_fit"], s["tie_focus_order"], s["code"],
        )
        assert actual == priority_sort_key(candidate)
        assert "_sort" not in candidate["priority"]
        assert row["historical_evidence_used_in_rank"] is False


def test_local_sync_migrates_sidecar_separately(tmp_path: Path) -> None:
    db = tmp_path / "simulation.db"
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE placeholder(id INTEGER PRIMARY KEY)")
    migrate_prospective_store(db)
    paths = sync_local.RuntimePaths(
        holdings=tmp_path / "holdings.db",
        market=tmp_path / "market.db",
        simulation=db,
    )
    spec = next(item for item in sync_local.MIGRATIONS if item.key == "JEV-X1")
    assert spec.detect(paths).state == sync_local.MigrationState.MISSING
    migrated = spec.run(paths)
    assert migrated["historical_backfill_performed"] is False
    assert spec.detect(paths).state == sync_local.MigrationState.CURRENT
