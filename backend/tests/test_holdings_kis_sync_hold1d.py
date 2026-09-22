from __future__ import annotations

import sqlite3
from decimal import Decimal
from pathlib import Path

import httpx
import pytest

from app.core.config import Settings
from app.holdings import HoldingsCatalog, account_fingerprint
from app.holdings.kis_sync import (
    HoldingsKisSyncError,
    KisAccountSyncService,
)
from app.integrations.kis.account import (
    KisAccountError,
    KisDomesticBalance,
    KisHolding,
    inquire_domestic_balance,
)


def _settings(**overrides) -> Settings:
    values = {
        "kis_app_key": "app-key",
        "kis_app_secret": "app-secret",
        "kis_account_no": "12345678",
        "kis_account_product_code": "01",
        "kis_env": "real",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def _holding(
    ticker: str = "005930",
    *,
    name: str = "삼성전자",
    quantity: str = "10",
    average_price: str = "70000",
) -> KisHolding:
    qty = Decimal(quantity)
    avg = Decimal(average_price)
    return KisHolding(
        ticker=ticker,
        name=name,
        quantity=qty,
        orderable_quantity=qty,
        average_price=avg,
        purchase_amount=qty * avg,
        current_price=Decimal("80000"),
        evaluation_amount=qty * Decimal("80000"),
        pnl_amount=Decimal("0"),
        pnl_rate=Decimal("0"),
    )


def _balance(*holdings: KisHolding, complete: bool = True, pages: int = 1):
    return KisDomesticBalance(
        holdings=tuple(holdings),
        summary=None,
        page_count=pages,
        is_complete=complete,
    )


def _market_store(path: Path, rows=(("KOSPI", "005930"), ("KOSPI", "000660"))):
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            CREATE TABLE stock_daily(
                market TEXT NOT NULL,
                bas_dd TEXT NOT NULL,
                stock_code TEXT NOT NULL,
                row_json TEXT NOT NULL,
                PRIMARY KEY(market,bas_dd,stock_code)
            )
            """
        )
        for market, ticker in rows:
            conn.execute(
                "INSERT INTO stock_daily VALUES(?,?,?,?)",
                (market, "20260918", ticker, "{}"),
            )


@pytest.fixture()
def env(tmp_path):
    catalog = HoldingsCatalog(tmp_path / "holdings.db")
    catalog.initialize()
    market_db = tmp_path / "market_history.db"
    _market_store(market_db)
    return catalog, market_db


def _service(catalog, market_db, balance_or_reader):
    reader = (
        balance_or_reader
        if callable(balance_or_reader)
        else lambda settings: balance_or_reader
    )
    return KisAccountSyncService(
        catalog,
        settings=_settings(),
        market_store_db=market_db,
        balance_reader=reader,
    )


def _events(catalog: HoldingsCatalog):
    with catalog.connection() as conn:
        return conn.execute(
            "SELECT * FROM holding_position_event ORDER BY created_at,id"
        ).fetchall()


def _sync_runs(catalog: HoldingsCatalog):
    with catalog.connection() as conn:
        return conn.execute(
            "SELECT * FROM account_sync_run ORDER BY created_at,id"
        ).fetchall()


def _open_positions(catalog: HoldingsCatalog):
    with catalog.connection() as conn:
        return conn.execute(
            """
            SELECT p.*,s.ticker,s.watch_enabled
            FROM holding_position p
            JOIN monitored_stock s ON s.id=p.monitored_stock_id
            WHERE p.status='OPEN'
            ORDER BY s.ticker
            """
        ).fetchall()


def _all_positions(catalog: HoldingsCatalog):
    with catalog.connection() as conn:
        return conn.execute(
            """
            SELECT p.*,s.ticker,s.watch_enabled
            FROM holding_position p
            JOIN monitored_stock s ON s.id=p.monitored_stock_id
            ORDER BY p.created_at,p.id
            """
        ).fetchall()


def _schema(catalog: HoldingsCatalog):
    with catalog.connection() as conn:
        rows = conn.execute(
            """
            SELECT type,name,sql FROM sqlite_master
            WHERE type IN ('table','index','trigger')
            ORDER BY type,name
            """
        ).fetchall()
    return [(row["type"], row["name"], row["sql"]) for row in rows]


def test_kis_balance_strict_critical_fields_and_completeness_metadata():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"tr_cont": ""},
            json={
                "rt_cd": "0",
                "output1": [
                    {
                        "pdno": "005930",
                        "prdt_name": "삼성전자",
                        "hldg_qty": "10",
                        "ord_psbl_qty": "10",
                        "pchs_avg_pric": "70000",
                        "pchs_amt": "700000",
                        "prpr": "80000",
                        "evlu_amt": "800000",
                        "evlu_pfls_amt": "100000",
                        "evlu_pfls_rt": "14.2",
                    }
                ],
                "output2": [],
                "ctx_area_fk100": "",
                "ctx_area_nk100": "",
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = inquire_domestic_balance(
            _settings(),
            access_token="test-token",
            http_client=client,
        )
    assert result.page_count == 1
    assert result.is_complete is True
    assert result.holdings[0].quantity == Decimal("10")

    for field, bad in (("hldg_qty", "bad"), ("pchs_avg_pric", "bad")):
        def bad_handler(request: httpx.Request, field=field, bad=bad):
            row = {
                "pdno": "005930",
                "prdt_name": "삼성전자",
                "hldg_qty": "10",
                "pchs_avg_pric": "70000",
            }
            row[field] = bad
            return httpx.Response(
                200,
                headers={"tr_cont": ""},
                json={
                    "rt_cd": "0",
                    "output1": [row],
                    "output2": [],
                    "ctx_area_fk100": "",
                    "ctx_area_nk100": "",
                },
            )

        with httpx.Client(transport=httpx.MockTransport(bad_handler)) as client:
            with pytest.raises(KisAccountError):
                inquire_domestic_balance(
                    _settings(),
                    access_token="test-token",
                    http_client=client,
                )


def test_pagination_failure_never_returns_partial_snapshot():
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        if calls["count"] == 1:
            return httpx.Response(
                200,
                headers={"tr_cont": "M"},
                json={
                    "rt_cd": "0",
                    "output1": [
                        {
                            "pdno": "005930",
                            "prdt_name": "삼성전자",
                            "hldg_qty": "10",
                            "pchs_avg_pric": "70000",
                        }
                    ],
                    "output2": [],
                    "ctx_area_fk100": "NEXT",
                    "ctx_area_nk100": "NEXT",
                },
            )
        return httpx.Response(
            200,
            headers={"tr_cont": ""},
            json={
                "rt_cd": "1",
                "msg_cd": "TEST_FAIL",
                "msg1": "second page failed",
                "output1": [],
                "output2": [],
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(KisAccountError):
            inquire_domestic_balance(
                _settings(),
                access_token="test-token",
                http_client=client,
            )
    assert calls["count"] == 2


def test_first_observation_and_same_snapshot_are_idempotent(env):
    catalog, market_db = env
    service = _service(catalog, market_db, _balance(_holding()))

    first = service.sync()
    assert first.status == "COMPLETED"
    assert first.created_positions == 1
    positions = _open_positions(catalog)
    assert len(positions) == 1
    assert positions[0]["ticker"] == "005930"
    assert positions[0]["current_quantity"] == "10"
    assert positions[0]["current_average_price"] == "70000"
    assert positions[0]["opened_reason"] == "KIS_OBSERVED"
    assert positions[0]["watch_enabled"] == 0
    assert [row["event_type"] for row in _events(catalog)] == ["BALANCE_OBSERVED"]

    second = service.sync()
    assert second.created_positions == 0
    assert second.reconciled_positions == 0
    assert second.unchanged_positions == 1
    assert len(_events(catalog)) == 1
    runs = _sync_runs(catalog)
    assert [row["status"] for row in runs] == ["COMPLETED", "COMPLETED"]
    assert all(row["is_complete"] == 1 for row in runs)


def test_quantity_and_average_changes_are_reconciled_not_trades(env):
    catalog, market_db = env
    _service(catalog, market_db, _balance(_holding())).sync()

    changed = _service(
        catalog,
        market_db,
        _balance(_holding(quantity="15", average_price="73333")),
    ).sync()
    assert changed.reconciled_positions == 1

    lower = _service(
        catalog,
        market_db,
        _balance(_holding(quantity="8", average_price="73333")),
    ).sync()
    assert lower.reconciled_positions == 1

    average_only = _service(
        catalog,
        market_db,
        _balance(_holding(quantity="8", average_price="73000")),
    ).sync()
    assert average_only.reconciled_positions == 1

    event_types = [row["event_type"] for row in _events(catalog)]
    assert event_types == [
        "BALANCE_OBSERVED",
        "RECONCILED",
        "RECONCILED",
        "RECONCILED",
    ]
    assert not ({"BUY", "SELL", "CORRECTION"} & set(event_types))


def test_complete_absence_closes_and_reappearance_opens_new_episode(env):
    catalog, market_db = env
    first = _service(catalog, market_db, _balance(_holding())).sync()
    assert first.created_positions == 1

    closed = _service(catalog, market_db, _balance()).sync()
    assert closed.closed_positions == 1
    positions = _all_positions(catalog)
    assert len(positions) == 1
    assert positions[0]["status"] == "CLOSED"
    assert positions[0]["current_quantity"] == "0"
    assert positions[0]["current_cost_basis"] == "0"
    assert _events(catalog)[-1]["event_type"] == "RECONCILED"

    reopened = _service(catalog, market_db, _balance(_holding())).sync()
    assert reopened.created_positions == 1
    positions = _all_positions(catalog)
    assert len(positions) == 2
    assert [row["status"] for row in positions] == ["CLOSED", "OPEN"]


def test_failed_or_incomplete_snapshot_never_changes_positions(env):
    catalog, market_db = env
    _service(catalog, market_db, _balance(_holding())).sync()
    before = _all_positions(catalog)
    before_events = list(_events(catalog))

    incomplete_service = _service(
        catalog,
        market_db,
        _balance(complete=False, pages=1),
    )
    with pytest.raises(HoldingsKisSyncError) as exc_info:
        incomplete_service.sync()
    assert exc_info.value.code == "HOLD_KIS_SYNC_INCOMPLETE"
    assert _all_positions(catalog) == before
    assert list(_events(catalog)) == before_events
    assert _sync_runs(catalog)[-1]["status"] == "FAILED"

    def failed_reader(settings):
        raise KisAccountError("network/page failure", code="TEST")

    with pytest.raises(HoldingsKisSyncError) as exc_info:
        _service(catalog, market_db, failed_reader).sync()
    assert exc_info.value.code == "HOLD_KIS_SYNC_BALANCE_FAILED"
    assert _all_positions(catalog) == before
    assert list(_events(catalog)) == before_events
    assert _sync_runs(catalog)[-1]["status"] == "FAILED"


def test_duplicate_invalid_and_unknown_market_snapshots_fail_without_apply(env, tmp_path):
    catalog, market_db = env

    duplicate = _balance(_holding(), _holding())
    with pytest.raises(HoldingsKisSyncError) as dup_exc:
        _service(catalog, market_db, duplicate).sync()
    assert dup_exc.value.code == "HOLD_KIS_SYNC_DUPLICATE_TICKER"
    assert _open_positions(catalog) == []

    invalid = _holding()
    object.__setattr__(invalid, "quantity", Decimal("NaN"))
    with pytest.raises(HoldingsKisSyncError) as invalid_exc:
        _service(catalog, market_db, _balance(invalid)).sync()
    assert invalid_exc.value.code == "HOLD_KIS_SYNC_INVALID_HOLDING"
    assert _open_positions(catalog) == []

    unknown = _holding("123456", name="미확인종목")
    with pytest.raises(HoldingsKisSyncError) as market_exc:
        _service(catalog, market_db, _balance(unknown)).sync()
    assert market_exc.value.code == "HOLD_KIS_SYNC_MARKET_UNRESOLVED"
    assert _open_positions(catalog) == []


def test_existing_watch_intent_is_preserved(env):
    catalog, market_db = env
    stock = catalog.create_monitored_stock(
        market="KOSPI",
        ticker="005930",
        name="삼성전자",
        watch_enabled=True,
    )
    _service(catalog, market_db, _balance(_holding())).sync()
    assert catalog.get_monitored_stock(stock.id).watch_enabled is True

    _service(catalog, market_db, _balance()).sync()
    assert catalog.get_monitored_stock(stock.id).watch_enabled is True


def test_raw_account_number_is_not_persisted_and_account_is_reused(env):
    catalog, market_db = env
    service = _service(catalog, market_db, _balance())
    first = service.sync()
    second = service.sync()
    assert first.account_id == second.account_id
    assert b"12345678" not in catalog.db_path.read_bytes()

    with catalog.connection() as conn:
        account = conn.execute(
            "SELECT * FROM position_account WHERE id=?",
            (first.account_id,),
        ).fetchone()
    expected = account_fingerprint(
        provider="KIS",
        broker_environment="REAL",
        account_number="12345678",
        product_code="01",
    )
    assert account["account_kind"] == "BROKER"
    assert account["external_account_fingerprint"] == expected


def test_reconciliation_is_atomic_and_failed_run_is_preserved(env, monkeypatch):
    catalog, market_db = env
    _service(catalog, market_db, _balance(_holding())).sync()
    before = _all_positions(catalog)
    before_events = list(_events(catalog))

    service = _service(
        catalog,
        market_db,
        _balance(_holding(quantity="20", average_price="75000")),
    )

    def fail_event(*args, **kwargs):
        raise RuntimeError("forced event failure")

    monkeypatch.setattr(service, "_insert_event", fail_event)
    with pytest.raises(HoldingsKisSyncError) as exc_info:
        service.sync()
    assert exc_info.value.code == "HOLD_KIS_SYNC_STORAGE_CONFLICT"
    assert _all_positions(catalog) == before
    assert list(_events(catalog)) == before_events
    assert _sync_runs(catalog)[-1]["status"] == "FAILED"
    assert _sync_runs(catalog)[-1]["is_complete"] == 0


def test_schema_unchanged_and_sync_has_no_trade_or_analysis_dependency(env):
    catalog, market_db = env
    before = _schema(catalog)
    _service(catalog, market_db, _balance(_holding())).sync()
    after = _schema(catalog)
    assert after == before

    source = Path("backend/app/holdings/kis_sync.py").read_text(encoding="utf-8")
    assert "record_buy(" not in source
    assert "record_sell(" not in source
    assert "record_correction(" not in source
    assert "current_price" not in source
    assert "app.backtest" not in source
