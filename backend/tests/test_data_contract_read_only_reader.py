from __future__ import annotations

import sqlite3
from dataclasses import fields
from pathlib import Path

import pytest

from app.backtest.jobs import BacktestJobManager
from app.data_contract import ReadOnlyDataStateReader
import app.data_contract.reader as reader_module


def _tables(path: Path) -> set[str]:
    with sqlite3.connect(path) as conn:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
    return {str(row[0]) for row in rows}


def _create_market_db(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        conn.executescript(
            """
            CREATE TABLE stock_daily (
                market TEXT NOT NULL,
                bas_dd TEXT NOT NULL,
                stock_code TEXT NOT NULL,
                row_json TEXT NOT NULL,
                PRIMARY KEY (market, bas_dd, stock_code)
            );
            CREATE TABLE day_status (
                market TEXT NOT NULL,
                bas_dd TEXT NOT NULL,
                kind TEXT NOT NULL,
                status TEXT NOT NULL,
                PRIMARY KEY (market, bas_dd, kind)
            );
            """
        )
        conn.executemany(
            "INSERT INTO day_status(market,bas_dd,kind,status) VALUES(?,?,?,?)",
            [
                ("KOSPI", "20260923", "stock", "data"),
                ("KOSPI", "20260924", "stock", "data"),
                ("KOSPI", "20260925", "stock", "data"),
            ],
        )
        conn.executemany(
            "INSERT INTO stock_daily(market,bas_dd,stock_code,row_json) VALUES(?,?,?,?)",
            [
                ("KOSPI", "20260923", "005930", '{"close":70000}'),
                ("KOSPI", "20260924", "005930", '{"close":71000}'),
                # Deliberately newer than the confirmed market date. The reader must
                # not silently treat this unconfirmed row as confirmed EOD coverage.
                ("KOSPI", "20260926", "005930", '{"close":72000}'),
            ],
        )


def _create_holdings_db(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        conn.executescript(
            """
            CREATE TABLE monitored_stock (
                id TEXT PRIMARY KEY,
                market TEXT NOT NULL,
                ticker TEXT NOT NULL,
                name TEXT NOT NULL,
                watch_enabled INTEGER NOT NULL,
                archived_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE stock_analysis_day (
                id TEXT PRIMARY KEY,
                monitored_stock_id TEXT NOT NULL,
                market_date TEXT NOT NULL,
                current_revision_id TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE stock_analysis_revision (
                id TEXT PRIMARY KEY,
                analysis_day_id TEXT NOT NULL,
                revision_no INTEGER NOT NULL,
                input_fingerprint TEXT NOT NULL,
                strategy_key TEXT,
                action_state TEXT,
                risk_state TEXT,
                reference_price TEXT,
                stop_price TEXT,
                target1_price TEXT,
                target2_price TEXT,
                scanner_version TEXT,
                analysis_engine_version TEXT,
                policy_version TEXT,
                source_versions_json TEXT NOT NULL,
                snapshot_json TEXT NOT NULL,
                revision_reason TEXT,
                computed_at TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE position_account (
                id TEXT PRIMARY KEY,
                provider TEXT NOT NULL,
                account_kind TEXT NOT NULL,
                broker_environment TEXT,
                external_account_fingerprint TEXT,
                display_name TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE holding_position (
                id TEXT PRIMARY KEY,
                monitored_stock_id TEXT NOT NULL,
                position_account_id TEXT NOT NULL,
                status TEXT NOT NULL,
                opened_at TEXT NOT NULL,
                closed_at TEXT,
                current_quantity TEXT NOT NULL,
                current_average_price TEXT,
                current_cost_basis TEXT,
                opened_reason TEXT NOT NULL,
                last_observed_at TEXT,
                last_sync_run_id TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """
        )
        conn.execute(
            """
            INSERT INTO monitored_stock(
                id,market,ticker,name,watch_enabled,archived_at,created_at,updated_at
            ) VALUES(?,?,?,?,?,?,?,?)
            """,
            (
                "stock-1",
                "KOSPI",
                "005930",
                "삼성전자",
                1,
                None,
                "2026-09-20T00:00:00+00:00",
                "2026-09-25T00:00:00+00:00",
            ),
        )
        conn.execute(
            """
            INSERT INTO stock_analysis_day(
                id,monitored_stock_id,market_date,current_revision_id,created_at,updated_at
            ) VALUES(?,?,?,?,?,?)
            """,
            (
                "day-1",
                "stock-1",
                "2026-09-23",
                "rev-1",
                "2026-09-23T07:00:00+00:00",
                "2026-09-23T07:00:00+00:00",
            ),
        )
        conn.execute(
            """
            INSERT INTO stock_analysis_revision(
                id,analysis_day_id,revision_no,input_fingerprint,
                strategy_key,action_state,risk_state,
                reference_price,stop_price,target1_price,target2_price,
                scanner_version,analysis_engine_version,policy_version,
                source_versions_json,snapshot_json,revision_reason,
                computed_at,created_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                "rev-1",
                "day-1",
                3,
                "fingerprint-abc",
                "PULLBACK",
                "WATCH",
                "CAUTION",
                "70000",
                "66500",
                "73500",
                "77000",
                "scanner-v1",
                "analysis-v2",
                "policy-v3",
                '{"market":"2026-09-23"}',
                '{"stored":true}',
                "test",
                "2026-09-23T07:10:00+00:00",
                "2026-09-23T07:10:00+00:00",
            ),
        )
        conn.execute(
            """
            INSERT INTO position_account(
                id,provider,account_kind,broker_environment,
                external_account_fingerprint,display_name,status,created_at,updated_at
            ) VALUES(?,?,?,?,?,?,?,?,?)
            """,
            (
                "account-1",
                "MANUAL",
                "MANUAL",
                None,
                None,
                "수동 기록",
                "ACTIVE",
                "2026-09-20T00:00:00+00:00",
                "2026-09-20T00:00:00+00:00",
            ),
        )
        conn.execute(
            """
            INSERT INTO holding_position(
                id,monitored_stock_id,position_account_id,status,opened_at,closed_at,
                current_quantity,current_average_price,current_cost_basis,opened_reason,
                last_observed_at,last_sync_run_id,created_at,updated_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                "position-1",
                "stock-1",
                "account-1",
                "OPEN",
                "2026-09-20T02:00:00+00:00",
                None,
                "10",
                "69000",
                "690000",
                "MANUAL",
                "2026-09-25T01:23:45+00:00",
                "sync-1",
                "2026-09-20T02:00:00+00:00",
                "2026-09-25T01:23:45+00:00",
            ),
        )


def test_missing_stores_do_not_create_directories_or_databases(tmp_path: Path) -> None:
    market_db = tmp_path / "missing-market" / "market_history.db"
    holdings_db = tmp_path / "missing-holdings" / "holdings.db"
    reader = ReadOnlyDataStateReader(
        market_store_db=market_db,
        holdings_db=holdings_db,
        job_manager=BacktestJobManager(),
    )

    state = reader.read_stock_state("KOSPI", "005930")

    assert state.eod.reason == "STORE_NOT_FOUND"
    assert state.chart.reason == "STORE_NOT_FOUND"
    assert state.analysis.reason == "STORE_NOT_FOUND"
    assert state.ledger.reason == "STORE_NOT_FOUND"
    assert not market_db.exists()
    assert not holdings_db.exists()
    assert not market_db.parent.exists()
    assert not holdings_db.parent.exists()


def test_missing_schema_is_reported_without_creating_tables(tmp_path: Path) -> None:
    market_db = tmp_path / "market.db"
    holdings_db = tmp_path / "holdings.db"
    sqlite3.connect(market_db).close()
    sqlite3.connect(holdings_db).close()
    market_before = _tables(market_db)
    holdings_before = _tables(holdings_db)
    market_stat = market_db.stat()
    holdings_stat = holdings_db.stat()

    reader = ReadOnlyDataStateReader(
        market_store_db=market_db,
        holdings_db=holdings_db,
        job_manager=BacktestJobManager(),
    )
    state = reader.read_stock_state("KOSPI", "005930")

    assert state.eod.reason == "SCHEMA_UNAVAILABLE"
    assert state.chart.reason == "SCHEMA_UNAVAILABLE"
    assert state.analysis.reason == "SCHEMA_UNAVAILABLE"
    assert state.ledger.reason == "SCHEMA_UNAVAILABLE"
    assert _tables(market_db) == market_before == set()
    assert _tables(holdings_db) == holdings_before == set()
    assert market_db.stat().st_size == market_stat.st_size
    assert holdings_db.stat().st_size == holdings_stat.st_size
    assert market_db.stat().st_mtime_ns == market_stat.st_mtime_ns
    assert holdings_db.stat().st_mtime_ns == holdings_stat.st_mtime_ns


def test_reader_keeps_resource_dates_separate_and_reads_only_stored_values(tmp_path: Path) -> None:
    market_db = tmp_path / "market.db"
    holdings_db = tmp_path / "holdings.db"
    _create_market_db(market_db)
    _create_holdings_db(holdings_db)

    reader = ReadOnlyDataStateReader(
        market_store_db=market_db,
        holdings_db=holdings_db,
        job_manager=BacktestJobManager(),
    )
    state = reader.read_stock_state("KOSPI", "005930")

    assert state.eod.available is True
    assert state.eod.present is True
    assert state.eod.market_confirmed_date == "20260925"
    assert state.eod.stock_first_date == "20260923"
    assert state.eod.stock_latest_date == "20260924"
    assert state.eod.stock_row_count == 2

    assert state.chart.market_confirmed_date == "20260925"
    assert state.chart.first_date == "20260923"
    assert state.chart.last_date == "20260924"
    assert state.chart.row_count == 2

    assert state.analysis.present is True
    assert state.analysis.market_date == "2026-09-23"
    assert state.analysis.revision_id == "rev-1"
    assert state.analysis.revision_no == 3
    assert state.analysis.input_fingerprint == "fingerprint-abc"
    assert state.analysis.analysis_engine_version == "analysis-v2"
    assert state.analysis.policy_version == "policy-v3"
    assert state.analysis.source_versions == {"market": "2026-09-23"}

    assert state.ledger.present is True
    assert state.ledger.open_position_count == 1
    position = state.ledger.positions[0]
    assert position.current_quantity == "10"
    assert position.current_average_price == "69000"
    assert position.current_cost_basis == "690000"
    assert position.opened_reason == "MANUAL"
    assert position.last_observed_at == "2026-09-25T01:23:45+00:00"

    # J-8.1 never collapses these independent timestamps into one synthetic data_date.
    assert state.eod.market_confirmed_date != state.eod.stock_latest_date
    assert state.analysis.market_date != "2026-09-25"


def test_stored_analysis_presence_is_not_promoted_to_validity(tmp_path: Path) -> None:
    market_db = tmp_path / "market.db"
    holdings_db = tmp_path / "holdings.db"
    _create_market_db(market_db)
    _create_holdings_db(holdings_db)
    reader = ReadOnlyDataStateReader(
        market_store_db=market_db,
        holdings_db=holdings_db,
        job_manager=BacktestJobManager(),
    )

    analysis = reader.read_stored_analysis("KOSPI", "005930")

    assert analysis.present is True
    field_names = {field.name for field in fields(type(analysis))}
    assert "status" not in field_names
    assert "valid" not in field_names
    assert "validity" not in field_names
    assert analysis.input_fingerprint == "fingerprint-abc"
    assert analysis.analysis_engine_version == "analysis-v2"
    assert analysis.policy_version == "policy-v3"


def test_reader_executes_no_sql_writes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    market_db = tmp_path / "market.db"
    holdings_db = tmp_path / "holdings.db"
    _create_market_db(market_db)
    _create_holdings_db(holdings_db)

    statements: list[str] = []
    real_connect = reader_module.sqlite3.connect

    def traced_connect(*args, **kwargs):
        conn = real_connect(*args, **kwargs)
        conn.set_trace_callback(statements.append)
        return conn

    monkeypatch.setattr(reader_module.sqlite3, "connect", traced_connect)
    reader = ReadOnlyDataStateReader(
        market_store_db=market_db,
        holdings_db=holdings_db,
        job_manager=BacktestJobManager(),
    )
    reader.read_stock_state("KOSPI", "005930")

    forbidden = (
        "CREATE ",
        "ALTER ",
        "DROP ",
        "INSERT ",
        "UPDATE ",
        "DELETE ",
        "REPLACE ",
        "VACUUM",
        "BEGIN ",
        "COMMIT",
    )
    normalized = [statement.strip().upper() for statement in statements]
    assert normalized
    assert all(not statement.startswith(forbidden) for statement in normalized)


def test_known_job_reader_never_creates_or_cancels_jobs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = BacktestJobManager()
    job = manager.create()
    manager.update_progress(
        job.job_id,
        {
            "stage": "scanner_prepare",
            "message": "준비 중",
            "current": 2,
            "total": 5,
            "details": {"market": "KOSPI"},
        },
    )

    def forbidden(*_args, **_kwargs):
        raise AssertionError("J-8.1 reader must not mutate job state")

    monkeypatch.setattr(manager, "create", forbidden)
    monkeypatch.setattr(manager, "cancel", forbidden)

    reader = ReadOnlyDataStateReader(
        market_store_db=tmp_path / "none-market.db",
        holdings_db=tmp_path / "none-holdings.db",
        job_manager=manager,
    )
    observed = reader.read_known_job(job.job_id)
    missing = reader.read_known_job("missing-job")

    assert observed.present is True
    assert observed.status == "running"
    assert observed.stage == "scanner_prepare"
    assert observed.current == 2
    assert observed.total == 5
    assert observed.details == {"market": "KOSPI"}
    assert missing.present is False
    assert missing.reason == "JOB_NOT_FOUND"


def test_reader_has_no_provider_analysis_prepare_or_token_dependencies() -> None:
    source = Path(reader_module.__file__).read_text(encoding="utf-8")

    forbidden_dependencies = (
        "KrxProvider",
        "OpenDartProvider",
        "StrategyAnalysisService",
        "StrategyEngine",
        "RiskEngine",
        "StockScannerService",
        "BacktestService",
        "KisAccountSyncService",
        "HoldingsHistoryPrepareService",
        "HoldingsMarketFreshnessService",
        "get_settings",
    )
    for dependency in forbidden_dependencies:
        assert dependency not in source

    assert ".create(" not in source
    assert ".cancel(" not in source
    assert "mkdir(" not in source
    assert "journal_mode" not in source.lower()
