from __future__ import annotations

import json
import sqlite3
from copy import deepcopy
from pathlib import Path

from app.backtest.candidate_priority import priority_sort_key, rank_candidates
from app.backtest.reproducibility_audit import _candidate_snapshot
from app.prospective.rank_audit_adapter import extract_rank_evidence_from_audit
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


def test_reuse_existing_audit_without_changing_ranking(tmp_path: Path) -> None:
    candidates = [
        _candidate("000100", 110.0),
        _candidate("000200", 105.0),
        _candidate("000300", 120.0),
    ]
    expected, _ = rank_candidates(deepcopy(candidates))
    ranked, _ = rank_candidates(candidates)
    assert [c["code"] for c in ranked] == [c["code"] for c in expected]

    audit = {
        "scanner_version": "test",
        "analysis_date": "2026-10-07",
        "market_scope": "ALL",
        "result_source": "fresh_analysis",
        "candidate_count": len(ranked),
        "candidates": [
            _candidate_snapshot(candidate, i)
            for i, candidate in enumerate(ranked, start=1)
        ],
    }
    path = tmp_path / "scanner-repro_synthetic.json"
    path.write_text(json.dumps(audit, ensure_ascii=False), encoding="utf-8")
    result = {
        "version": "test",
        "requested_as_of": "2026-10-07",
        "market_scope": "ALL",
        "candidates": ranked,
        "more_candidates": [],
        "diagnostics": {"reproducibility_audit": {"written": True, "path": str(path)}},
    }
    rows = extract_rank_evidence_from_audit(result, audit_root=tmp_path)
    assert rows is not None and len(rows) == 3
    assert rows[0]["code"] == "000200"
    assert rows[0]["tie_resolution"]["breaker"] == "STRUCTURAL_TARGET_NEAREST_PROMOTE"
    for candidate, evidence in zip(ranked, rows):
        s = evidence["sort_components"]
        actual = (
            s["tier_order"], s["missing"], s["risk_quality"],
            s["entry_gap_missing"], s["entry_gap_pct"],
            s["negative_strategy_fit"], s["tie_focus_order"], s["code"],
        )
        assert actual == priority_sort_key(candidate)

    mismatch = deepcopy(result)
    mismatch["candidates"][0]["code"] = "999999"
    assert extract_rank_evidence_from_audit(mismatch, audit_root=tmp_path) is None
    assert extract_rank_evidence_from_audit(result, audit_root=tmp_path / "wrong") is None


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
    migration = spec.run(paths)
    assert migration["historical_backfill_performed"] is False
    assert spec.detect(paths).state == sync_local.MigrationState.CURRENT
