from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from app.holdings.domain import (
    HoldingPosition,
    HoldingPositionEvent,
    MonitoredStock,
    PositionAccount,
)
from app.holdings.live_performance import HoldingsLivePerformanceService
from app.holdings.performance import HoldingPerformanceService, HoldingValuation
from app.quotes.models import CachedQuoteObservation


NOW = "2026-09-26T06:00:00+00:00"


class FakeCatalog:
    def __init__(
        self,
        *,
        account_kind: str = "MANUAL",
        with_events: bool = True,
        cost_basis: Decimal | None = Decimal("690000"),
    ) -> None:
        self.stock = MonitoredStock(
            id="stock-1",
            market="KOSPI",
            ticker="005930",
            name="삼성전자",
            watch_enabled=True,
            archived_at=None,
            created_at=NOW,
            updated_at=NOW,
        )
        self.account = PositionAccount(
            id="account-1",
            provider="KIS" if account_kind == "BROKER" else "MANUAL",
            account_kind=account_kind,
            broker_environment="real" if account_kind == "BROKER" else None,
            external_account_fingerprint=None,
            display_name="테스트 계좌",
            status="ACTIVE",
            created_at=NOW,
            updated_at=NOW,
        )
        self.position = HoldingPosition(
            id="position-1",
            monitored_stock_id="stock-1",
            position_account_id="account-1",
            status="OPEN",
            opened_at=NOW,
            closed_at=None,
            current_quantity=Decimal("10"),
            current_average_price=Decimal("69000"),
            current_cost_basis=cost_basis,
            opened_reason="MANUAL",
            last_observed_at=NOW,
            last_sync_run_id=None,
            created_at=NOW,
            updated_at=NOW,
        )
        self.events = (
            [
                HoldingPositionEvent(
                    id="event-1",
                    position_id="position-1",
                    event_type="OPENING_BALANCE",
                    quantity_delta=Decimal("12"),
                    unit_price=Decimal("70000"),
                    before_quantity=Decimal("0"),
                    after_quantity=Decimal("12"),
                    before_average_price=None,
                    after_average_price=Decimal("70000"),
                    observed_at=NOW,
                    effective_at=NOW,
                    analysis_revision_id=None,
                    account_sync_run_id=None,
                    external_event_key=None,
                    note="opening",
                    created_at=NOW,
                ),
                HoldingPositionEvent(
                    id="event-2",
                    position_id="position-1",
                    event_type="SELL",
                    quantity_delta=Decimal("-2"),
                    unit_price=Decimal("80000"),
                    before_quantity=Decimal("12"),
                    after_quantity=Decimal("10"),
                    before_average_price=Decimal("70000"),
                    after_average_price=Decimal("69000"),
                    observed_at=NOW,
                    effective_at=NOW,
                    analysis_revision_id=None,
                    account_sync_run_id=None,
                    external_event_key=None,
                    note="sell",
                    created_at=NOW,
                ),
            ]
            if with_events
            else []
        )

    def get_monitored_stock(self, stock_id: str):
        return self.stock if stock_id == self.stock.id else None

    def list_positions(self, monitored_stock_id: str, *, status: str | None = None):
        if monitored_stock_id != self.stock.id:
            return []
        if status is not None and status != self.position.status:
            return []
        return [self.position]

    def get_position_account(self, account_id: str):
        return self.account if account_id == self.account.id else None

    def list_position_events(self, position_id: str):
        return list(self.events) if position_id == self.position.id else []


def _observation(
    *,
    price: str = "84200",
    age_ms: int = 100,
    freshness_seconds: float = 15.0,
) -> CachedQuoteObservation:
    return CachedQuoteObservation(
        capable=True,
        present=True,
        source="KIS_REST",
        market="KOSPI",
        ticker="005930",
        venue="INTEGRATED",
        provider="KIS",
        mode="SNAPSHOT",
        current_price=Decimal(price),
        provider_timestamp=None,
        received_at=datetime.now(timezone.utc) - timedelta(milliseconds=age_ms),
        age_ms=age_ms,
        freshness_seconds=freshness_seconds,
    )


def test_confirmed_and_live_valuations_share_the_same_decimal_formula() -> None:
    catalog = FakeCatalog()
    service = HoldingPerformanceService(catalog)  # type: ignore[arg-type]

    confirmed = service.calculate_with_valuation(
        "stock-1",
        HoldingValuation(
            available=True,
            market_date="2026-09-25",
            price=Decimal("83000"),
            source="MARKET_STORE",
            message=None,
        ),
    )
    live = service.calculate_with_valuation(
        "stock-1",
        HoldingValuation(
            available=True,
            market_date=None,
            price=Decimal("84200"),
            source="KIS_REST_SNAPSHOT",
            message=None,
        ),
    )

    confirmed_position = confirmed.positions[0]
    live_position = live.positions[0]

    assert confirmed_position.quantity == live_position.quantity == Decimal("10")
    assert confirmed_position.cost_basis == live_position.cost_basis == Decimal("690000")
    assert confirmed_position.confirmed_realized_pnl == live_position.confirmed_realized_pnl == Decimal("20000")

    assert live_position.market_value == Decimal("842000")
    assert live_position.unrealized_pnl == Decimal("152000")
    assert live_position.unrealized_return_pct == Decimal("152000") / Decimal("690000") * Decimal("100")
    assert live_position.tracked_pnl == Decimal("172000")
    assert live.calculation_status == confirmed.calculation_status == "COMPLETE_SINCE_TRACKING_START"


def test_live_quote_does_not_upgrade_broker_valuation_only_provenance() -> None:
    catalog = FakeCatalog(account_kind="BROKER", with_events=False)
    service = HoldingPerformanceService(catalog)  # type: ignore[arg-type]

    live = service.calculate_with_valuation(
        "stock-1",
        HoldingValuation(
            available=True,
            market_date=None,
            price=Decimal("84200"),
            source="KIS_REST_SNAPSHOT",
            message=None,
        ),
    )

    assert live.positions[0].calculation_status == "VALUATION_ONLY"
    assert live.positions[0].confirmed_realized_pnl is None
    assert live.calculation_status == "VALUATION_ONLY"


def test_live_performance_marks_fresh_and_stale_quote_without_changing_values() -> None:
    catalog = FakeCatalog()

    fresh = HoldingsLivePerformanceService(
        catalog=catalog,  # type: ignore[arg-type]
        quote_observer=lambda **_kwargs: _observation(age_ms=100),
    ).calculate("stock-1")
    stale = HoldingsLivePerformanceService(
        catalog=catalog,  # type: ignore[arg-type]
        quote_observer=lambda **_kwargs: _observation(age_ms=20_000),
    ).calculate("stock-1")

    assert fresh.available is True
    assert fresh.state == "FRESH"
    assert fresh.reason_code is None
    assert fresh.performance is not None
    assert fresh.performance.valuation.source == "KIS_REST_SNAPSHOT"
    assert fresh.performance.valuation.market_date is None

    assert stale.available is True
    assert stale.state == "STALE"
    assert stale.reason_code == "QUOTE_SNAPSHOT_STALE"
    assert stale.performance is not None
    assert stale.performance.positions[0].market_value == fresh.performance.positions[0].market_value


def test_live_performance_falls_back_cleanly_when_quote_not_observed() -> None:
    catalog = FakeCatalog()
    unavailable = CachedQuoteObservation(
        capable=True,
        present=False,
        source="KIS_REST",
        market="KOSPI",
        ticker="005930",
        venue="INTEGRATED",
        freshness_seconds=15.0,
        reason="QUOTE_NOT_OBSERVED",
    )

    result = HoldingsLivePerformanceService(
        catalog=catalog,  # type: ignore[arg-type]
        quote_observer=lambda **_kwargs: unavailable,
    ).calculate("stock-1")

    assert result.available is False
    assert result.state == "UNAVAILABLE"
    assert result.reason_code == "QUOTE_NOT_OBSERVED"
    assert result.quote is None
    assert result.performance is None


def _create_read_only_fixture(path: Path) -> None:
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
            CREATE TABLE holding_position_event (
                id TEXT PRIMARY KEY,
                position_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                quantity_delta TEXT,
                unit_price TEXT,
                before_quantity TEXT,
                after_quantity TEXT,
                before_average_price TEXT,
                after_average_price TEXT,
                observed_at TEXT,
                effective_at TEXT,
                analysis_revision_id TEXT,
                account_sync_run_id TEXT,
                external_event_key TEXT,
                note TEXT,
                created_at TEXT NOT NULL
            );
            """
        )
        conn.execute(
            "INSERT INTO monitored_stock VALUES(?,?,?,?,?,?,?,?)",
            ("stock-1", "KOSPI", "005930", "삼성전자", 1, None, NOW, NOW),
        )
        conn.execute(
            "INSERT INTO position_account VALUES(?,?,?,?,?,?,?,?,?)",
            ("account-1", "MANUAL", "MANUAL", None, None, "수동", "ACTIVE", NOW, NOW),
        )
        conn.execute(
            "INSERT INTO holding_position VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                "position-1", "stock-1", "account-1", "OPEN", NOW, None,
                "10", "69000", "690000", "MANUAL", NOW, None, NOW, NOW,
            ),
        )
        conn.execute(
            "INSERT INTO holding_position_event VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                "event-1", "position-1", "OPENING_BALANCE", "10", "69000",
                "0", "10", None, "69000", NOW, NOW, None, None, None, "opening", NOW,
            ),
        )


def test_live_performance_reads_holdings_db_without_modifying_it(tmp_path: Path) -> None:
    db_path = tmp_path / "holdings.db"
    _create_read_only_fixture(db_path)
    before = db_path.stat()

    result = HoldingsLivePerformanceService(
        db_path,
        quote_observer=lambda **_kwargs: _observation(),
    ).calculate("stock-1")

    after = db_path.stat()
    assert result.available is True
    assert result.performance is not None
    assert result.performance.positions[0].market_value == Decimal("842000")
    assert after.st_size == before.st_size
    assert after.st_mtime_ns == before.st_mtime_ns


def test_live_performance_source_has_no_kis_network_or_token_dependency() -> None:
    source = Path("backend/app/holdings/live_performance.py").read_text(encoding="utf-8")
    for forbidden in (
        "inquire_domestic_price",
        "get_access_token",
        "issue_access_token",
        "httpx",
        "requests.",
        "websocket",
    ):
        assert forbidden not in source

def test_live_performance_api_is_registered_and_returns_local_snapshot(monkeypatch) -> None:
    from fastapi.testclient import TestClient

    import app.api.holdings as holdings_api
    from app.main import app

    class Result:
        def to_dict(self):
            return {
                "stock_id": "stock-1",
                "market": "KOSPI",
                "ticker": "005930",
                "available": True,
                "state": "FRESH",
                "reason_code": None,
                "quote": {
                    "provider": "KIS",
                    "mode": "SNAPSHOT",
                    "venue": "INTEGRATED",
                    "price": "84200",
                    "provider_timestamp": None,
                    "received_at": NOW,
                    "age_ms": 100,
                    "freshness_seconds": 15.0,
                },
                "performance": {
                    "stock_id": "stock-1",
                    "market": "KOSPI",
                    "ticker": "005930",
                    "valuation": {
                        "available": True,
                        "market_date": None,
                        "price": "84200",
                        "source": "KIS_REST_SNAPSHOT",
                        "message": None,
                    },
                    "positions": [],
                    "aggregate": {
                        "available": False,
                        "mode": "NO_ACTUAL_POSITION",
                        "position_count": 0,
                        "potential_overlap": False,
                    },
                    "calculation_status": "UNAVAILABLE",
                    "warnings": [],
                },
            }

    class Service:
        def calculate(self, stock_id: str):
            assert stock_id == "stock-1"
            return Result()

    monkeypatch.setattr(
        holdings_api,
        "_live_performance_service",
        lambda: Service(),
    )

    response = TestClient(app).get("/api/holdings/stocks/stock-1/performance/live")

    assert response.status_code == 200
    body = response.json()
    assert body["available"] is True
    assert body["state"] == "FRESH"
    assert body["quote"]["price"] == "84200"
    assert body["performance"]["valuation"]["source"] == "KIS_REST_SNAPSHOT"

