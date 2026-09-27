from __future__ import annotations

import sqlite3
from pathlib import Path

from app.backtest.market_store import HistoricalMarketStore
from app.backtest.production_exit_policy import production_policy_cache_token
from app.backtest.scanner import StockScannerService
from app.data_contract import ReadOnlyDataStateReader, build_stock_data_contract
from app.holdings import HoldingsCatalog
from app.holdings.analysis import (
    ANALYSIS_ENGINE_VERSION,
    INPUT_MANIFEST_SCHEMA_VERSION,
    SingleStockAnalysis,
)
from app.holdings.analysis_history import HoldingAnalysisHistoryService
from app.simulation.validation_catalog import HistoricalValidationCatalog
from tools.data.migrate_vnext_p1s1 import migrate_p1_input_identity


def _core_market_db(path: Path) -> HistoricalMarketStore:
    store = HistoricalMarketStore(path)
    store.put_stock_day(
        "KOSPI",
        "20260925",
        [{"code": "005930", "name": "삼성전자", "close": 70000}],
        stable=True,
    )
    store.put_index_day(
        "KOSPI",
        "20260925",
        {"code": "KOSPI", "name": "코스피", "close": 3100},
        stable=True,
    )
    return store


def _core_holdings_db(path: Path) -> tuple[HoldingsCatalog, str]:
    catalog = HoldingsCatalog(path)
    catalog.initialize()
    stock = catalog.create_monitored_stock(
        market="KOSPI",
        ticker="005930",
        name="삼성전자",
    )
    return catalog, stock.id


def _analysis(generation: int) -> SingleStockAnalysis:
    fingerprint = "p1-fixture-fingerprint"
    policy = production_policy_cache_token()
    manifest = {
        "schema_version": INPUT_MANIFEST_SCHEMA_VERSION,
        "calculation_path": ANALYSIS_ENGINE_VERSION,
        "market": "KOSPI",
        "ticker": "005930",
        "basis_date": "2026-09-25",
        "input_fingerprint": fingerprint,
        "stock_input": {"content_sha256": "stock-fixture"},
        "index_input": {"content_sha256": "index-fixture"},
        "versions": {
            "scanner_version": StockScannerService.VERSION,
            "analysis_engine_version": ANALYSIS_ENGINE_VERSION,
            "policy_version": policy,
        },
    }
    return SingleStockAnalysis(
        market="KOSPI",
        ticker="005930",
        market_date="2026-09-25",
        strategy_key="ma20_rebound",
        action_state="WATCH",
        risk_state="READY",
        reference_price=70000.0,
        stop_price=66500.0,
        target1_price=73500.0,
        target2_price=77000.0,
        condition_state={},
        readiness_state={},
        scanner_version=StockScannerService.VERSION,
        analysis_engine_version=ANALYSIS_ENGINE_VERSION,
        policy_version=policy,
        input_fingerprint=fingerprint,
        source_versions={
            "input_manifest_schema": INPUT_MANIFEST_SCHEMA_VERSION,
        },
        snapshot={"fixture": True},
        input_manifest=manifest,
        market_store_generation=generation,
    )


class _MutableAnalyzer:
    def __init__(self, result: SingleStockAnalysis):
        self.result = result

    def __call__(self, **_kwargs):
        return self.result


def test_explicit_migration_is_additive_and_repeatable(tmp_path: Path) -> None:
    market_path = tmp_path / "market.db"
    holdings_path = tmp_path / "holdings.db"
    store = _core_market_db(market_path)
    catalog, _ = _core_holdings_db(holdings_path)

    assert store.input_generation("KOSPI") is None
    migrate_p1_input_identity(
        holdings_db=holdings_path,
        market_db=market_path,
        create_backups=False,
    )
    migrate_p1_input_identity(
        holdings_db=holdings_path,
        market_db=market_path,
        create_backups=False,
    )

    assert store.input_generation("KOSPI") == 0
    with catalog.connect() as conn:
        tables = {
            str(row["name"])
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
    assert "stock_analysis_input_manifest" in tables
    assert "stock_analysis_input_proof" in tables


def test_market_generation_changes_only_after_migrated_input_writes(
    tmp_path: Path,
) -> None:
    market_path = tmp_path / "market.db"
    holdings_path = tmp_path / "holdings.db"
    store = _core_market_db(market_path)
    _core_holdings_db(holdings_path)
    migrate_p1_input_identity(
        holdings_db=holdings_path,
        market_db=market_path,
        create_backups=False,
    )

    assert store.input_generation("KOSPI") == 0
    store.put_stock_day(
        "KOSPI",
        "20260924",
        [{"code": "000660", "name": "SK하이닉스", "close": 200000}],
        stable=True,
    )
    assert store.input_generation("KOSPI") == 1
    store.put_index_day(
        "KOSPI",
        "20260924",
        {"code": "KOSPI", "close": 3090},
        stable=True,
    )
    assert store.input_generation("KOSPI") == 2


def test_analysis_proof_becomes_valid_then_invalidates_and_reproves(
    tmp_path: Path,
) -> None:
    market_path = tmp_path / "market.db"
    holdings_path = tmp_path / "holdings.db"
    store = _core_market_db(market_path)
    catalog, stock_id = _core_holdings_db(holdings_path)
    migrate_p1_input_identity(
        holdings_db=holdings_path,
        market_db=market_path,
        create_backups=False,
    )

    analyzer = _MutableAnalyzer(_analysis(store.input_generation("KOSPI") or 0))
    service = HoldingAnalysisHistoryService(
        catalog,
        market_store_db=market_path,
        analyzer=analyzer,
    )
    first = service.analyze_and_record(
        monitored_stock_id=stock_id,
        market_date="2026-09-25",
    )
    assert first.created_revision is True

    state = ReadOnlyDataStateReader(
        market_store_db=market_path,
        holdings_db=holdings_path,
        production_policy_path=tmp_path / "missing-policy.json",
    ).read_stock_state("KOSPI", "005930")
    contract = build_stock_data_contract(state)
    assert contract.resources.analysis_result.status == "VALID"
    assert contract.resources.analysis_result.current_use_allowed is True
    assert (
        contract.resources.analysis_result.identity.proven_market_generation
        == contract.resources.analysis_result.identity.current_market_generation
    )

    store.put_stock_day(
        "KOSPI",
        "20260924",
        [{"code": "000660", "name": "SK하이닉스", "close": 200000}],
        stable=True,
    )
    changed_state = ReadOnlyDataStateReader(
        market_store_db=market_path,
        holdings_db=holdings_path,
        production_policy_path=tmp_path / "missing-policy.json",
    ).read_stock_state("KOSPI", "005930")
    changed = build_stock_data_contract(changed_state)
    assert changed.resources.analysis_result.status == "UNVERIFIED"
    assert changed.resources.analysis_result.current_use_allowed is False
    assert (
        changed.resources.analysis_result.reason_code
        == "CURRENT_INPUT_GENERATION_CHANGED"
    )

    analyzer.result = _analysis(store.input_generation("KOSPI") or 0)
    second = service.analyze_and_record(
        monitored_stock_id=stock_id,
        market_date="2026-09-25",
    )
    assert second.created_revision is False
    assert second.revision.id == first.revision.id

    reproved_state = ReadOnlyDataStateReader(
        market_store_db=market_path,
        holdings_db=holdings_path,
        production_policy_path=tmp_path / "missing-policy.json",
    ).read_stock_state("KOSPI", "005930")
    reproved = build_stock_data_contract(reproved_state)
    assert reproved.resources.analysis_result.status == "VALID"
    with sqlite3.connect(holdings_path) as conn:
        proof_count = int(
            conn.execute(
                "SELECT COUNT(*) FROM stock_analysis_input_proof WHERE analysis_revision_id=?",
                (first.revision.id,),
            ).fetchone()[0]
        )
    assert proof_count == 2



def test_simulation_validation_day_can_store_append_only_input_proof(
    tmp_path: Path,
) -> None:
    market_path = tmp_path / "market.db"
    holdings_path = tmp_path / "holdings.db"
    simulation_path = tmp_path / "simulation.db"
    _core_market_db(market_path)
    _core_holdings_db(holdings_path)
    catalog = HistoricalValidationCatalog(simulation_path)
    catalog.initialize()

    migrate_p1_input_identity(
        holdings_db=holdings_path,
        market_db=market_path,
        simulation_db=simulation_path,
        create_backups=False,
    )
    draft = catalog.create_draft(
        name="proof fixture",
        market_scope="KOSPI",
        requested_period_type="custom",
        requested_start_month="2026-09",
        requested_end_month="2026-09",
        resolved_start_date="2026-09-25",
        resolved_end_date="2026-09-25",
        trading_day_count=1,
    )
    fingerprint = {"id": "sim-proof-fp"}
    manifest = {
        "schema_version": "SIM_VALIDATION_INPUT_MANIFEST_V1",
        "calculation_path": "HISTORICAL_VALIDATION_REPLAY",
        "validation_id": draft.id,
        "trading_date": "2026-09-25",
        "input_fingerprint": fingerprint,
        "market_snapshots": {"KOSPI": {"combined_sha256": "fixture"}},
    }
    kwargs = dict(
        validation_id=draft.id,
        trading_date="2026-09-25",
        scanner_version=StockScannerService.VERSION,
        market_scope="KOSPI",
        scanner_cache_hit=False,
        partial_data=False,
        input_fingerprint=fingerprint,
        market_summary=[],
        summary={},
        methodology={},
        diagnostics={"network_requests": 0},
        candidates=[
            {
                "market": "KOSPI",
                "ticker": "005930",
                "name": "삼성전자",
                "rank": 1,
                "result_bucket": "TOP",
                "strategy": "PULLBACK",
                "decision_status": "READY",
                "snapshot": {"code": "005930"},
            }
        ],
        input_manifest=manifest,
        market_generations={"KOSPI": 0},
    )
    first = catalog.save_completed_day(**kwargs)
    second = catalog.save_completed_day(**kwargs)
    assert first.result_hash == second.result_hash

    with sqlite3.connect(simulation_path) as conn:
        manifest_count = int(
            conn.execute("SELECT COUNT(*) FROM simulation_input_manifest").fetchone()[0]
        )
        proof_count = int(
            conn.execute("SELECT COUNT(*) FROM simulation_input_proof").fetchone()[0]
        )
    assert manifest_count == 1
    assert proof_count == 1
