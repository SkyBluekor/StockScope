from __future__ import annotations

import json
import sys
import types
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

# Use the real project history_store/service modules in an installed project.

from app.backtest.candidate_priority import priority_sort_key, rank_candidates
from app.backtest.market_store import HistoricalMarketStore
from app.backtest.reproducibility_audit import build_scanner_reproducibility_payload


def _candidate(code: str, *, historical_status: str, fit: float = 80.0) -> dict:
    return {
        "code": code,
        "name": code,
        "market": "KOSPI",
        "data_date": "2026-09-17",
        "candidate_state": "READY",
        "conditions": {"passed": 6, "total": 6, "missing": 0},
        "risk": {"status": "READY", "warning": False, "warnings": []},
        "historical_evidence": {"status": historical_status, "verified": historical_status == "GOOD"},
        "entry_risk_guide": {
            "price_rule": {"kind": "RANGE", "label": "entry", "gap_pct": 0.0},
            "rebound_rule": {"available": False},
            "risk": {},
        },
        "_strategy_fit_score": fit,
        "internal_rank": fit,
        "strategy": "ma20_rebound",
    }


def test_historical_evidence_does_not_change_production_sort_key() -> None:
    good = _candidate("000001", historical_status="GOOD", fit=80.0)
    weak = _candidate("000001", historical_status="WEAK", fit=80.0)
    assert priority_sort_key(good) == priority_sort_key(weak)


def test_current_strategy_fit_and_ticker_are_deterministic_tiebreakers() -> None:
    candidates = [
        _candidate("000003", historical_status="GOOD", fit=80.0),
        _candidate("000002", historical_status="WEAK", fit=90.0),
        _candidate("000001", historical_status="DATA_UNAVAILABLE", fit=90.0),
    ]
    ranked, _ = rank_candidates(candidates)
    assert [item["code"] for item in ranked] == ["000001", "000002", "000003"]
    assert all("3년 과거 근거" not in item["priority"]["ranking_rule"] for item in ranked)


def test_market_store_day_status_range_is_bulk_and_complete(tmp_path: Path) -> None:
    store = HistoricalMarketStore(tmp_path / "market.db")
    store.put_stock_day("KOSPI", "20260916", [], stable=True)
    store.put_index_day("KOSPI", "20260916", None, stable=True)
    store.put_stock_day("KOSPI", "20260917", [{"code": "000001", "close": 100}], stable=True)
    store.put_index_day("KOSPI", "20260917", {"name": "KOSPI", "close": 3000}, stable=True)
    statuses = store.day_status_range("KOSPI", "20260916", "20260917")
    assert statuses[("20260916", "stock")] == "empty"
    assert statuses[("20260916", "index")] == "empty"
    assert statuses[("20260917", "stock")] == "data"
    assert statuses[("20260917", "index")] == "data"


def test_audit_declares_current_only_policy_and_history_coverage(tmp_path: Path) -> None:
    store = HistoricalMarketStore(tmp_path / "market.db")
    for dd in ("20260916", "20260917"):
        store.put_stock_day(
            "KOSPI",
            dd,
            [{"date": dd, "code": "000001", "close": 100, "open": 99, "high": 101, "low": 98, "volume": 1}],
            stable=True,
        )
        store.put_index_day("KOSPI", dd, {"date": dd, "name": "KOSPI", "close": 3000}, stable=True)
    candidate = _candidate("000001", historical_status="DATA_UNAVAILABLE")
    payload = build_scanner_reproducibility_payload(
        market_store=store,
        scanner_version="0.21.3.4",
        market_scope="KOSPI",
        analysis_date=date(2026, 9, 17),
        history_start=date(2026, 9, 16),
        candidate_history_start=date(2026, 9, 16),
        markets=["KOSPI"],
        latest_dates={"KOSPI": "2026-09-17"},
        ranked_candidates=[candidate],
        input_fingerprint={"id": "test"},
        ranking_changes=[],
        result_source="fresh_analysis",
        candidate_pool_complete=True,
        project_root_hint=tmp_path,
        runtime_root=tmp_path / "runtime",
    )
    assert payload["decision_pipeline"] == "CURRENT_ONLY_V1"
    assert payload["ranking_policy"] == "CURRENT_DETERMINISTIC_V1"
    assert payload["historical_evidence_affects_rank"] is False
    assert payload["current_history_window"]["fingerprint"] == payload["history_fingerprint"]["combined_sha256"]
    assert payload["historical_coverage"]["candidate_rows_min"] == 2
    assert payload["historical_coverage"]["candidate_rows_max"] == 2


def test_scanner_source_no_long_history_branch_in_production_loop() -> None:
    source = (Path(__file__).parents[1] / "app" / "backtest" / "scanner.py").read_text(encoding="utf-8")
    assert 'VERSION = "0.21.3.7"' in source
    assert "enough_history = (" not in source
    assert "deep = self._current_candidate(item)" in source
    assert "day_status_range" in source
