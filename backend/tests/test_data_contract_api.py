from __future__ import annotations

import sqlite3
from datetime import date, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.backtest.jobs import backtest_jobs
from app.backtest.production_exit_policy import PRODUCTION_EXIT_POLICY_VERSION
from app.backtest.scanner import StockScannerService
from app.holdings.analysis import ANALYSIS_ENGINE_VERSION
from app.main import app


client = TestClient(app)


def _market_rows(end: date, count: int) -> list[str]:
    return [
        (end - timedelta(days=offset)).strftime("%Y%m%d")
        for offset in reversed(range(count))
    ]


def _create_market_db(
    path: Path,
    *,
    confirmed_date: str = "20260925",
    stock_dates: list[str] | None = None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    dates = stock_dates or _market_rows(date(2026, 9, 25), 70)
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
        conn.execute(
            "INSERT INTO day_status(market,bas_dd,kind,status) VALUES(?,?,?,?)",
            ("KOSPI", confirmed_date, "stock", "data"),
        )
        conn.executemany(
            "INSERT INTO stock_daily(market,bas_dd,stock_code,row_json) VALUES(?,?,?,?)",
            [
                ("KOSPI", bas_dd, "005930", '{"close":70000}')
                for bas_dd in dates
            ],
        )


def _create_holdings_db(
    path: Path,
    *,
    analysis_date: str = "2026-09-25",
    current_revision_id: str = "rev-1",
    create_revision: bool = True,
) -> None:
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
                "stock-1", "KOSPI", "005930", "삼성전자", 1, None,
                "2026-09-20T00:00:00+00:00", "2026-09-25T00:00:00+00:00",
            ),
        )
        conn.execute(
            """
            INSERT INTO stock_analysis_day(
                id,monitored_stock_id,market_date,current_revision_id,created_at,updated_at
            ) VALUES(?,?,?,?,?,?)
            """,
            (
                "day-1", "stock-1", analysis_date, current_revision_id,
                "2026-09-25T00:00:00+00:00", "2026-09-25T00:00:00+00:00",
            ),
        )
        if create_revision:
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
                    current_revision_id,
                    "day-1",
                    3,
                    "fingerprint-current-looking",
                    "PULLBACK",
                    "WATCH",
                    "CAUTION",
                    "70000",
                    "66500",
                    "73500",
                    "77000",
                    StockScannerService.VERSION,
                    ANALYSIS_ENGINE_VERSION,
                    f"{PRODUCTION_EXIT_POLICY_VERSION}-fixture",
                    '{"market_store":"market_history.db","price_basis":"CONFIRMED_EOD"}',
                    '{"stored":true}',
                    "test",
                    "2026-09-25T07:10:00+00:00",
                    "2026-09-25T07:10:00+00:00",
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
                "account-1", "MANUAL", "MANUAL", None, None, "수동 기록", "ACTIVE",
                "2026-09-20T00:00:00+00:00", "2026-09-20T00:00:00+00:00",
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
                "position-1", "stock-1", "account-1", "OPEN",
                "2026-09-20T02:00:00+00:00", None,
                "10", "69000", "690000", "MANUAL",
                "2026-09-25T01:23:45+00:00", "sync-1",
                "2026-09-20T02:00:00+00:00", "2026-09-25T01:23:45+00:00",
            ),
        )


def _configure_paths(
    monkeypatch: pytest.MonkeyPatch,
    market_db: Path,
    holdings_db: Path,
) -> None:
    monkeypatch.setenv("STOCKSCOPE_MARKET_STORE_DB", str(market_db))
    monkeypatch.setenv("STOCKSCOPE_HOLDINGS_DB", str(holdings_db))


def test_data_contract_returns_versioned_read_only_resource_states(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    market_db = tmp_path / "market.db"
    holdings_db = tmp_path / "holdings.db"
    _create_market_db(market_db)
    _create_holdings_db(holdings_db)
    _configure_paths(monkeypatch, market_db, holdings_db)

    from app.core.config import Settings
    import app.quotes.service as quote_service_module
    monkeypatch.setattr(
        quote_service_module,
        "get_settings",
        lambda: Settings(_env_file=None, kis_app_key=None, kis_app_secret=None),
    )

    response = client.get(
        "/api/data-contract/stocks/005930",
        params={"market": "KOSPI", "range": "3m"},
    )

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    assert body["contract_version"] == "DATA_CONTRACT_V1"
    assert body["resource_key"] == "KOSPI:005930"
    assert body["request"] == {
        "market": "KOSPI",
        "ticker": "005930",
        "range": "3m",
        "job_id": None,
    }

    assert body["resources"]["eod"]["status"] == "VALID"
    assert body["resources"]["eod"]["market_confirmed_date"] == "2026-09-25"
    assert body["resources"]["eod"]["stock_date"] == "2026-09-25"

    assert body["resources"]["chart"]["status"] == "VALID"
    assert body["resources"]["chart"]["row_count"] == 70
    assert body["resources"]["chart"]["required_rows"] == 66

    analysis = body["resources"]["analysis_result"]
    assert analysis["status"] == "UNVERIFIED"
    assert analysis["present"] is True
    assert analysis["displayable"] is True
    assert analysis["current_use_allowed"] is False
    assert analysis["reason_code"] == "CURRENT_INPUT_IDENTITY_NOT_PROVEN"

    realtime = body["resources"]["realtime"]
    assert realtime["status"] == "ABSENT"
    assert realtime["present"] is False
    assert realtime["capability"] is False
    assert realtime["source"] == "NONE"
    assert realtime["reason_code"] == "KIS_QUOTE_NOT_CONFIGURED"

    ledger = body["resources"]["ledger"]
    assert ledger["status"] == "VALID"
    assert ledger["open_position_count"] == 1
    assert ledger["positions"][0]["current_quantity"] == "10"
    assert ledger["positions"][0]["current_average_price"] == "69000"


def test_data_contract_marks_eod_and_chart_stale_without_preparing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    market_db = tmp_path / "market.db"
    holdings_db = tmp_path / "holdings.db"
    stock_dates = _market_rows(date(2026, 9, 24), 70)
    _create_market_db(
        market_db,
        confirmed_date="20260925",
        stock_dates=stock_dates,
    )
    _create_holdings_db(holdings_db)
    _configure_paths(monkeypatch, market_db, holdings_db)

    response = client.get(
        "/api/data-contract/stocks/005930",
        params={"market": "KOSPI", "range": "3m"},
    )
    body = response.json()

    assert response.status_code == 200
    assert body["resources"]["eod"]["status"] == "INVALID"
    assert body["resources"]["eod"]["reason_code"] == "STALE_TO_MARKET_CONFIRMED"
    assert body["resources"]["chart"]["status"] == "INVALID"
    assert body["resources"]["chart"]["reason_code"] == "STALE_TO_MARKET_CONFIRMED"
    assert body["preparation"]["required"] is True
    assert set(body["preparation"]["targets"]) == {"eod", "chart"}
    assert any(action["id"] == "PREPARE_CHART" for action in body["actions"])


def test_data_contract_marks_requested_chart_range_insufficient(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    market_db = tmp_path / "market.db"
    holdings_db = tmp_path / "holdings.db"
    _create_market_db(
        market_db,
        stock_dates=_market_rows(date(2026, 9, 25), 40),
    )
    _create_holdings_db(holdings_db)
    _configure_paths(monkeypatch, market_db, holdings_db)

    body = client.get(
        "/api/data-contract/stocks/005930",
        params={"market": "KOSPI", "range": "3m"},
    ).json()

    chart = body["resources"]["chart"]
    assert chart["status"] == "INVALID"
    assert chart["reason_code"] == "INSUFFICIENT_COVERAGE"
    assert chart["row_count"] == 40
    assert chart["required_rows"] == 66
    assert {
        action["id"] for action in body["actions"]
    } >= {"PREPARE_CHART"}


def test_data_contract_marks_stored_analysis_basis_stale(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    market_db = tmp_path / "market.db"
    holdings_db = tmp_path / "holdings.db"
    _create_market_db(market_db)
    _create_holdings_db(holdings_db, analysis_date="2026-09-23")
    _configure_paths(monkeypatch, market_db, holdings_db)

    body = client.get(
        "/api/data-contract/stocks/005930",
        params={"market": "KOSPI"},
    ).json()

    analysis = body["resources"]["analysis_result"]
    assert analysis["status"] == "INVALID"
    assert analysis["reason_code"] == "ANALYSIS_BASIS_STALE"
    assert analysis["displayable"] is True
    assert analysis["current_use_allowed"] is False
    assert any(
        action["id"] == "REFRESH_HOLDING_ANALYSIS"
        for action in body["actions"]
    )


def test_data_contract_marks_broken_current_revision_invalid(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    market_db = tmp_path / "market.db"
    holdings_db = tmp_path / "holdings.db"
    _create_market_db(market_db)
    _create_holdings_db(
        holdings_db,
        current_revision_id="missing-revision",
        create_revision=False,
    )
    _configure_paths(monkeypatch, market_db, holdings_db)

    body = client.get(
        "/api/data-contract/stocks/005930",
        params={"market": "KOSPI"},
    ).json()

    analysis = body["resources"]["analysis_result"]
    assert analysis["status"] == "INVALID"
    assert analysis["present"] is False
    assert analysis["reason_code"] == "CURRENT_REVISION_MISSING"


def test_data_contract_missing_stores_are_reported_without_creating_them(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    market_db = tmp_path / "missing-market" / "market.db"
    holdings_db = tmp_path / "missing-holdings" / "holdings.db"
    _configure_paths(monkeypatch, market_db, holdings_db)

    response = client.get(
        "/api/data-contract/stocks/005930",
        params={"market": "KOSPI", "range": "3m"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["resources"]["eod"]["status"] == "ABSENT"
    assert body["resources"]["chart"]["status"] == "ABSENT"
    assert body["resources"]["analysis_result"]["status"] == "ABSENT"
    assert body["resources"]["ledger"]["status"] == "ABSENT"
    assert body["resources"]["realtime"]["status"] == "ABSENT"
    assert not market_db.exists()
    assert not holdings_db.exists()
    assert not market_db.parent.exists()
    assert not holdings_db.parent.exists()


def test_data_contract_reads_known_job_without_creating_or_cancelling(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    market_db = tmp_path / "market.db"
    holdings_db = tmp_path / "holdings.db"
    _create_market_db(market_db)
    _create_holdings_db(holdings_db)
    _configure_paths(monkeypatch, market_db, holdings_db)

    job = backtest_jobs.create()
    backtest_jobs.update_progress(
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
        raise AssertionError("data-contract GET must not mutate job state")

    monkeypatch.setattr(backtest_jobs, "create", forbidden)
    monkeypatch.setattr(backtest_jobs, "cancel", forbidden)

    body = client.get(
        "/api/data-contract/stocks/005930",
        params={"market": "KOSPI", "job_id": job.job_id},
    ).json()

    assert body["active_job"]["state"] == "KNOWN"
    assert body["active_job"]["status"] == "running"
    assert body["active_job"]["current"] == 2
    assert any(action["id"] == "VIEW_ACTIVE_JOB" for action in body["actions"])

    missing = client.get(
        "/api/data-contract/stocks/005930",
        params={"market": "KOSPI", "job_id": "missing-job"},
    ).json()
    assert missing["active_job"]["state"] == "UNKNOWN"
    assert missing["active_job"]["reason_code"] == "JOB_NOT_FOUND"


def test_data_contract_get_does_not_modify_sqlite_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    market_db = tmp_path / "market.db"
    holdings_db = tmp_path / "holdings.db"
    _create_market_db(market_db)
    _create_holdings_db(holdings_db)
    _configure_paths(monkeypatch, market_db, holdings_db)

    market_before = market_db.stat()
    holdings_before = holdings_db.stat()

    response = client.get(
        "/api/data-contract/stocks/005930",
        params={"market": "KOSPI", "range": "3m"},
    )

    assert response.status_code == 200
    market_after = market_db.stat()
    holdings_after = holdings_db.stat()
    assert market_after.st_size == market_before.st_size
    assert holdings_after.st_size == holdings_before.st_size
    assert market_after.st_mtime_ns == market_before.st_mtime_ns
    assert holdings_after.st_mtime_ns == holdings_before.st_mtime_ns


def test_data_contract_requires_explicit_market_and_valid_identity() -> None:
    missing_market = client.get("/api/data-contract/stocks/005930")
    bad_ticker = client.get(
        "/api/data-contract/stocks/5930",
        params={"market": "KOSPI"},
    )
    bad_range = client.get(
        "/api/data-contract/stocks/005930",
        params={"market": "KOSPI", "range": "5y"},
    )

    assert missing_market.status_code == 422
    assert bad_ticker.status_code == 422
    assert bad_range.status_code == 422


def test_data_contract_api_has_no_mutating_service_dependencies() -> None:
    api_source = Path("backend/app/api/data_contract.py").read_text(encoding="utf-8")
    builder_source = Path("backend/app/data_contract/builder.py").read_text(encoding="utf-8")

    forbidden = (
        "KrxProvider(",
        "OpenDartProvider(",
        "StrategyAnalysisService(",
        "RiskEngine(",
        "StockScannerService(",
        "BacktestService(",
        "HoldingsChartPrepareService(",
        "HoldingsHistoryPrepareService(",
        "HoldingsMarketFreshnessService(",
        ".prepare(",
        ".create(",
        ".cancel(",
        "production_policy_cache_token(",
        "get_settings(",
    )
    combined = api_source + "\n" + builder_source
    for token in forbidden:
        assert token not in combined

def test_data_contract_realtime_reads_cached_quote_without_network(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from datetime import datetime, timezone
    from decimal import Decimal

    from app.core.config import Settings
    from app.quotes.models import QuoteCacheKey, QuoteSnapshot
    from app.quotes.store import quote_store
    import app.data_contract.reader as reader_module
    import app.quotes.service as quote_service_module

    market_db = tmp_path / "market.db"
    holdings_db = tmp_path / "holdings.db"
    _create_market_db(market_db)
    _create_holdings_db(holdings_db)
    _configure_paths(monkeypatch, market_db, holdings_db)

    settings = Settings(
        _env_file=None,
        kis_app_key="app-key",
        kis_app_secret="app-secret",
        kis_env="real",
        kis_quote_freshness_seconds=15.0,
    )
    monkeypatch.setattr(quote_service_module, "get_settings", lambda: settings)
    quote_store.clear()

    key = QuoteCacheKey(
        environment="real",
        credential_fingerprint=quote_service_module.credential_fingerprint(settings),
        market="KOSPI",
        ticker="005930",
        venue="INTEGRATED",
    )
    quote_store.put(
        key,
        QuoteSnapshot(
            market="KOSPI",
            ticker="005930",
            name="삼성전자",
            venue="INTEGRATED",
            provider_market_division="UN",
            environment="real",
            current_price=Decimal("84200"),
            change_amount=Decimal("1200"),
            change_rate=Decimal("1.45"),
            change_sign="2",
            open_price=Decimal("83300"),
            high_price=Decimal("85000"),
            low_price=Decimal("82900"),
            base_price=Decimal("83000"),
            accumulated_volume=Decimal("12345678"),
            provider_timestamp=None,
            received_at=datetime.now(timezone.utc),
        ),
    )

    def forbidden(*_args, **_kwargs):
        raise AssertionError("data-contract GET must not call KIS or issue tokens")

    monkeypatch.setattr(quote_service_module, "get_access_token", forbidden)
    monkeypatch.setattr(quote_service_module, "inquire_domestic_price", forbidden)

    response = client.get(
        "/api/data-contract/stocks/005930",
        params={"market": "KOSPI"},
    )
    realtime = response.json()["resources"]["realtime"]

    assert response.status_code == 200
    assert realtime["status"] == "VALID"
    assert realtime["present"] is True
    assert realtime["capability"] is True
    assert realtime["source"] == "KIS_REST"
    assert realtime["provider"] == "KIS"
    assert realtime["mode"] == "SNAPSHOT"
    assert realtime["venue"] == "INTEGRATED"
    assert realtime["current_price"] == "84200"
    assert realtime["provider_timestamp"] is None
    assert realtime["reason_code"] is None
    quote_store.clear()


def test_data_contract_realtime_marks_stale_snapshot_unverified(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from datetime import datetime, timedelta, timezone
    from decimal import Decimal

    from app.core.config import Settings
    from app.quotes.models import QuoteCacheKey, QuoteSnapshot
    from app.quotes.store import quote_store
    import app.quotes.service as quote_service_module

    market_db = tmp_path / "market.db"
    holdings_db = tmp_path / "holdings.db"
    _create_market_db(market_db)
    _create_holdings_db(holdings_db)
    _configure_paths(monkeypatch, market_db, holdings_db)

    settings = Settings(
        _env_file=None,
        kis_app_key="app-key",
        kis_app_secret="app-secret",
        kis_env="real",
        kis_quote_freshness_seconds=1.0,
    )
    monkeypatch.setattr(quote_service_module, "get_settings", lambda: settings)
    quote_store.clear()
    key = QuoteCacheKey(
        environment="real",
        credential_fingerprint=quote_service_module.credential_fingerprint(settings),
        market="KOSPI",
        ticker="005930",
        venue="INTEGRATED",
    )
    quote_store.put(
        key,
        QuoteSnapshot(
            market="KOSPI",
            ticker="005930",
            name="삼성전자",
            venue="INTEGRATED",
            provider_market_division="UN",
            environment="real",
            current_price=Decimal("84200"),
            change_amount=Decimal("1200"),
            change_rate=Decimal("1.45"),
            change_sign="2",
            open_price=Decimal("83300"),
            high_price=Decimal("85000"),
            low_price=Decimal("82900"),
            base_price=Decimal("83000"),
            accumulated_volume=Decimal("12345678"),
            provider_timestamp=None,
            received_at=datetime.now(timezone.utc) - timedelta(seconds=5),
        ),
    )

    realtime = client.get(
        "/api/data-contract/stocks/005930",
        params={"market": "KOSPI"},
    ).json()["resources"]["realtime"]

    assert realtime["status"] == "UNVERIFIED"
    assert realtime["present"] is True
    assert realtime["reason_code"] == "QUOTE_SNAPSHOT_STALE"
    quote_store.clear()

