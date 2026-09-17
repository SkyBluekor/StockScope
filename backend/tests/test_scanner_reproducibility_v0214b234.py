from __future__ import annotations

import json
import sys
import types
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

# The overlay test can run by itself even when the base project's history_store.py
# is not present in the extracted overlay fixture used for packaging validation.
if "app.backtest.history_store" not in sys.modules:
    history_store = types.ModuleType("app.backtest.history_store")

    @dataclass
    class HistorySeries:  # pragma: no cover - tiny compatibility shim for overlay-only test runs
        rows: dict[str, dict] = field(default_factory=dict)
        checked_dates: set[str] = field(default_factory=set)

    history_store.HistorySeries = HistorySeries
    sys.modules["app.backtest.history_store"] = history_store

from app.backtest.market_store import HistoricalMarketStore
from app.backtest.reproducibility_audit import write_scanner_reproducibility_audit


def _stock(code: str, close: int) -> dict:
    return {
        "date": "20260917",
        "code": code,
        "name": f"N{code}",
        "market": "KOSPI",
        "section": "보통주",
        "open": close - 10,
        "high": close + 20,
        "low": close - 30,
        "close": close,
        "volume": 1000,
        "trade_value": close * 1000,
        "market_cap": close * 100000,
        "listed_shares": 100000,
    }


def _index(close: float) -> dict:
    return {
        "date": "20260917",
        "name": "KOSPI",
        "open": close - 1,
        "high": close + 2,
        "low": close - 2,
        "close": close,
        "volume": 100,
    }


def _populate(store: HistoricalMarketStore, rows: list[dict]) -> None:
    store.put_stock_day("KOSPI", "20260917", rows, stable=True)
    store.put_index_day("KOSPI", "20260917", _index(3000.0), stable=True)
    # 9/16 is intentionally marked empty so status differences are visible separately.
    store.put_stock_day("KOSPI", "20260916", [], stable=True)
    store.put_index_day("KOSPI", "20260916", None, stable=True)


def test_history_fingerprint_is_order_independent_and_content_sensitive(tmp_path: Path) -> None:
    first = HistoricalMarketStore(tmp_path / "a.db")
    second = HistoricalMarketStore(tmp_path / "b.db")
    changed = HistoricalMarketStore(tmp_path / "c.db")

    _populate(first, [_stock("000002", 200), _stock("000001", 100)])
    _populate(second, [_stock("000001", 100), _stock("000002", 200)])
    _populate(changed, [_stock("000001", 101), _stock("000002", 200)])

    expected = ["20260915", "20260916", "20260917"]
    snap_a = first.reproducibility_snapshot("KOSPI", "20260915", "20260917", expected_dates=expected)
    snap_b = second.reproducibility_snapshot("KOSPI", "20260915", "20260917", expected_dates=expected)
    snap_c = changed.reproducibility_snapshot("KOSPI", "20260915", "20260917", expected_dates=expected)

    assert snap_a["combined_sha256"] == snap_b["combined_sha256"]
    assert snap_a["stock_sha256"] != snap_c["stock_sha256"]
    assert snap_a["status"]["stock"]["data_days"] == 1
    assert snap_a["status"]["stock"]["empty_days"] == 1
    assert snap_a["status"]["stock"]["missing_days"] == 1
    assert snap_a["status"]["stock"]["missing_dates"] == ["20260915"]


def test_audit_file_has_machine_time_analysis_date_hashes_and_sort_key(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("STOCKSCOPE_REPRO_MACHINE", "home")
    store = HistoricalMarketStore(tmp_path / "market.db")
    _populate(store, [_stock("001450", 48500)])

    candidate = {
        "code": "001450",
        "name": "현대해상",
        "market": "KOSPI",
        "data_date": "2026-09-17",
        "current_price": 48500,
        "candidate_state": "READY",
        "candidate_label": "현재 조건상 진입 후보",
        "strategy": "SUPPORT_BOUNCE",
        "action": "ENTRY_CANDIDATE",
        "conditions": {"passed": 7, "total": 7, "missing": 0},
        "risk": {"status": "READY", "warning": False, "warnings": []},
        "historical_fit": {"status": "GOOD", "verified": True, "trades": 12},
        "historical_evidence": {"status": "GOOD", "verified": True, "trades": 12},
        "entry_risk_guide": {
            "price_rule": {"kind": "RANGE", "label": "지지 가격", "gap_pct": 0.0, "range_low": 48000, "range_high": 49000},
            "rebound_rule": {"available": False},
            "risk": {
                "entry_reference_price": 48500,
                "invalidation_price": 47000,
                "stop_zone_low": 46800,
                "stop_zone_high": 47200,
                "target1_price": 52500,
                "target1_basis": "resistance",
                "target2_price": 55000,
                "target2_basis": "extension",
                "rr1": 2.0,
                "rr2": 3.0,
            },
        },
        "_strategy_fit_score": 82.5,
        "internal_rank": 91.0,
    }

    output = tmp_path / "scanner-repro"
    result = write_scanner_reproducibility_audit(
        market_store=store,
        scanner_version="0.21.3.2",
        market_scope="KOSPI",
        analysis_date=date(2026, 9, 17),
        history_start=date(2026, 9, 15),
        candidate_history_start=date(2026, 9, 15),
        markets=["KOSPI"],
        latest_dates={"KOSPI": "2026-09-17"},
        ranked_candidates=[candidate],
        input_fingerprint={"id": "latest-day-test"},
        ranking_changes=[],
        result_source="fresh_analysis",
        candidate_pool_complete=True,
        project_root_hint=tmp_path,
        output_root=output,
    )

    assert result["written"] is True
    assert result["filename"].startswith("scanner-repro_home_")
    assert result["filename"].endswith("_analysis-20260917.json")

    payload = json.loads((output / result["filename"]).read_text(encoding="utf-8"))
    assert payload["machine"]["label"] == "home"
    assert payload["machine"]["fingerprint"]
    assert payload["analysis_date"] == "2026-09-17"
    assert payload["history_fingerprint"]["markets"]["KOSPI"]["stock_sha256"]
    assert payload["history_fingerprint"]["candidate_series"]["KOSPI:001450"]["row_hash"]
    assert payload["candidates"][0]["code"] == "001450"
    assert payload["candidates"][0]["final_sort_key"][-1] == "001450"
    assert payload["candidates"][0]["price_plan"]["target1_price"] == 52500
