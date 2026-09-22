from __future__ import annotations

import sqlite3
from decimal import Decimal
from pathlib import Path

import pytest

from app.holdings import (
    HoldingsCatalog,
    HoldingsLifecycleError,
    PositionLifecycleService,
)


T0 = "2026-09-18T09:00:00+09:00"
T1 = "2026-09-18T10:00:00+09:00"
T2 = "2026-09-18T11:00:00+09:00"
T3 = "2026-09-18T12:00:00+09:00"
T4 = "2026-09-18T13:00:00+09:00"


@pytest.fixture()
def env(tmp_path):
    catalog = HoldingsCatalog(tmp_path / "holdings.db")
    catalog.initialize()
    service = PositionLifecycleService(catalog)
    return catalog, service


def _manual_account(catalog: HoldingsCatalog):
    return catalog.create_position_account(
        provider="MANUAL",
        account_kind="MANUAL",
        display_name="수동 계좌",
    )


def _virtual_account(catalog: HoldingsCatalog):
    return catalog.create_position_account(
        provider="VIRTUAL",
        account_kind="VIRTUAL",
        display_name="가상 계좌",
    )


def _broker_account(catalog: HoldingsCatalog):
    return catalog.create_position_account(
        provider="KIS",
        account_kind="BROKER",
        broker_environment="REAL",
        external_account_fingerprint="a" * 64,
        display_name="KIS 실계좌",
    )


def _stock(
    catalog: HoldingsCatalog,
    ticker: str = "005930",
    name: str = "삼성전자",
    *,
    watch_enabled: bool = True,
):
    return catalog.create_monitored_stock(
        market="KOSPI",
        ticker=ticker,
        name=name,
        watch_enabled=watch_enabled,
    )


def _revision(
    catalog: HoldingsCatalog,
    stock_id: str,
    *,
    fingerprint: str,
    computed_at: str,
):
    day = catalog.get_or_create_analysis_day(
        monitored_stock_id=stock_id,
        market_date="2026-09-18",
    )
    revision = catalog.append_analysis_revision(
        analysis_day_id=day.id,
        input_fingerprint=fingerprint,
        strategy_key="ma20_rebound",
        action_state="WATCH",
        risk_state="READY",
        reference_price="261000",
        stop_price="254124.8",
        target1_price="271000",
        target2_price="274750.4",
        scanner_version="0.21.3.7",
        analysis_engine_version="HOLD_SINGLE_STOCK_V1",
        policy_version="TEST",
        source_versions={"market_store": "fixture"},
        snapshot={"strategy": "ma20_rebound"},
        computed_at=computed_at,
    )
    return day, revision


def _schema_snapshot(catalog: HoldingsCatalog):
    with catalog.connection() as conn:
        rows = conn.execute(
            """
            SELECT type,name,sql
            FROM sqlite_master
            WHERE type IN ('table','index','trigger')
            ORDER BY type,name
            """
        ).fetchall()
    return [(row["type"], row["name"], row["sql"]) for row in rows]


def test_first_and_additional_buy_use_one_position_and_decimal_moving_average(env):
    catalog, service = env
    account = _manual_account(catalog)
    stock = _stock(catalog, watch_enabled=False)

    first = service.record_buy(
        monitored_stock_id=stock.id,
        position_account_id=account.id,
        quantity="10",
        unit_price="70000",
        effective_at=T1,
    )
    second = service.record_buy(
        monitored_stock_id=stock.id,
        position_account_id=account.id,
        quantity="5",
        unit_price="80000",
        effective_at=T2,
    )

    assert second.position.id == first.position.id
    assert second.position.status == "OPEN"
    assert second.position.current_quantity == Decimal("15")
    assert second.position.current_cost_basis == Decimal("1100000")
    with __import__("decimal").localcontext() as context:
        context.prec = 50
        expected_average = Decimal("1100000") / Decimal("15")
    assert second.position.current_average_price == expected_average
    assert catalog.get_monitored_stock(stock.id).watch_enabled is False

    events = catalog.list_position_events(first.position.id)
    assert [event.event_type for event in events] == ["BUY", "BUY"]
    assert events[0].before_quantity == Decimal("0")
    assert events[0].after_quantity == Decimal("10")
    assert events[1].before_quantity == Decimal("10")
    assert events[1].after_quantity == Decimal("15")


def test_virtual_buy_uses_virtual_open_reason(env):
    catalog, service = env
    account = _virtual_account(catalog)
    stock = _stock(catalog)

    result = service.record_buy(
        monitored_stock_id=stock.id,
        position_account_id=account.id,
        quantity="2",
        unit_price="12345",
        effective_at=T1,
    )
    assert result.position.opened_reason == "VIRTUAL"


def test_partial_sell_keeps_average_full_sell_closes_and_rebuy_starts_new_episode(env):
    catalog, service = env
    account = _manual_account(catalog)
    stock = _stock(catalog)

    opened = service.record_buy(
        monitored_stock_id=stock.id,
        position_account_id=account.id,
        quantity="15",
        unit_price="73333.333333333333333333333333333333333333333333333333",
        effective_at=T1,
    )
    original_average = opened.position.current_average_price

    partial = service.record_sell(
        position_id=opened.position.id,
        quantity="5",
        unit_price="85000",
        effective_at=T2,
    )
    assert partial.position.status == "OPEN"
    assert partial.position.current_quantity == Decimal("10")
    assert partial.position.current_average_price == original_average
    assert partial.position.current_cost_basis == Decimal("10") * original_average

    closed = service.record_sell(
        position_id=opened.position.id,
        quantity="10",
        unit_price="86000",
        effective_at=T3,
    )
    assert closed.position.status == "CLOSED"
    assert closed.position.current_quantity == Decimal("0")
    assert closed.position.current_cost_basis == Decimal("0")
    assert closed.position.current_average_price == original_average
    assert closed.position.closed_at == T3

    with pytest.raises(HoldingsLifecycleError) as exc_info:
        service.record_sell(
            position_id=opened.position.id,
            quantity="1",
            unit_price="87000",
            effective_at=T4,
        )
    assert exc_info.value.code == "HOLD_POSITION_ALREADY_CLOSED"

    rebuy = service.record_buy(
        monitored_stock_id=stock.id,
        position_account_id=account.id,
        quantity="3",
        unit_price="80000",
        effective_at=T4,
    )
    assert rebuy.position.id != opened.position.id
    assert rebuy.position.status == "OPEN"
    positions = catalog.list_positions(stock.id)
    assert [item.status for item in positions] == ["CLOSED", "OPEN"]


def test_oversell_rolls_back_without_event_or_position_change(env):
    catalog, service = env
    account = _manual_account(catalog)
    stock = _stock(catalog)
    opened = service.record_buy(
        monitored_stock_id=stock.id,
        position_account_id=account.id,
        quantity="10",
        unit_price="70000",
        effective_at=T1,
    )
    before = catalog.get_position(opened.position.id)
    events_before = catalog.list_position_events(opened.position.id)

    with pytest.raises(HoldingsLifecycleError) as exc_info:
        service.record_sell(
            position_id=opened.position.id,
            quantity="11",
            unit_price="71000",
            effective_at=T2,
        )
    assert exc_info.value.code == "HOLD_POSITION_SELL_EXCEEDS_HOLDING"

    after = catalog.get_position(opened.position.id)
    events_after = catalog.list_position_events(opened.position.id)
    assert after == before
    assert events_after == events_before


def test_correction_updates_snapshot_and_zero_closes_without_becoming_sell(env):
    catalog, service = env
    account = _manual_account(catalog)
    stock = _stock(catalog)
    opened = service.record_buy(
        monitored_stock_id=stock.id,
        position_account_id=account.id,
        quantity="10",
        unit_price="70000",
        effective_at=T1,
    )

    corrected = service.record_correction(
        position_id=opened.position.id,
        corrected_quantity="12",
        corrected_average_price="71500",
        effective_at=T2,
        note="초기 입력 수량을 실제 잔고에 맞게 수정",
    )
    assert corrected.position.current_quantity == Decimal("12")
    assert corrected.position.current_average_price == Decimal("71500")
    assert corrected.position.current_cost_basis == Decimal("858000")
    assert corrected.event.event_type == "CORRECTION"
    assert corrected.event.quantity_delta == Decimal("2")

    zeroed = service.record_correction(
        position_id=opened.position.id,
        corrected_quantity="0",
        corrected_average_price="71500",
        effective_at=T3,
        note="실제 보유 없음으로 원장 수정",
    )
    assert zeroed.position.status == "CLOSED"
    assert zeroed.position.current_quantity == Decimal("0")
    assert zeroed.position.current_cost_basis == Decimal("0")
    assert zeroed.position.current_average_price == Decimal("71500")
    assert zeroed.event.event_type == "CORRECTION"
    assert [e.event_type for e in catalog.list_position_events(opened.position.id)] == [
        "BUY",
        "CORRECTION",
        "CORRECTION",
    ]


def test_correction_requires_note_and_keeps_state_on_failure(env):
    catalog, service = env
    account = _manual_account(catalog)
    stock = _stock(catalog)
    opened = service.record_buy(
        monitored_stock_id=stock.id,
        position_account_id=account.id,
        quantity="10",
        unit_price="70000",
        effective_at=T1,
    )

    with pytest.raises(HoldingsLifecycleError) as exc_info:
        service.record_correction(
            position_id=opened.position.id,
            corrected_quantity="12",
            corrected_average_price="71000",
            effective_at=T2,
            note="   ",
        )
    assert exc_info.value.code == "HOLD_POSITION_CORRECTION_NOTE_REQUIRED"
    assert catalog.get_position(opened.position.id) == opened.position
    assert len(catalog.list_position_events(opened.position.id)) == 1


def test_event_time_must_be_timezone_aware_and_not_go_backwards(env):
    catalog, service = env
    account = _manual_account(catalog)
    stock = _stock(catalog)

    with pytest.raises(HoldingsLifecycleError) as exc_info:
        service.record_buy(
            monitored_stock_id=stock.id,
            position_account_id=account.id,
            quantity="1",
            unit_price="70000",
            effective_at="2026-09-18T10:00:00",
        )
    assert exc_info.value.code == "HOLD_POSITION_TIME_INVALID"

    opened = service.record_buy(
        monitored_stock_id=stock.id,
        position_account_id=account.id,
        quantity="10",
        unit_price="70000",
        effective_at=T2,
    )
    with pytest.raises(HoldingsLifecycleError) as exc_info:
        service.record_sell(
            position_id=opened.position.id,
            quantity="1",
            unit_price="71000",
            effective_at=T1,
        )
    assert exc_info.value.code == "HOLD_POSITION_EVENT_OUT_OF_ORDER"
    assert catalog.get_position(opened.position.id).current_quantity == Decimal("10")
    assert len(catalog.list_position_events(opened.position.id)) == 1


def test_broker_position_is_externally_managed_for_buy_sell_and_correction(env):
    catalog, service = env
    account = _broker_account(catalog)
    stock = _stock(catalog)

    with pytest.raises(HoldingsLifecycleError) as exc_info:
        service.record_buy(
            monitored_stock_id=stock.id,
            position_account_id=account.id,
            quantity="1",
            unit_price="70000",
            effective_at=T1,
        )
    assert exc_info.value.code == "HOLD_POSITION_SOURCE_MANAGED_EXTERNALLY"
    assert catalog.list_positions(stock.id) == []

    observed = catalog.open_position(
        monitored_stock_id=stock.id,
        position_account_id=account.id,
        opened_reason="KIS_OBSERVED",
        opened_at=T0,
        current_quantity="10",
        current_average_price="70000",
        current_cost_basis="700000",
    )
    with pytest.raises(HoldingsLifecycleError) as sell_exc:
        service.record_sell(
            position_id=observed.id,
            quantity="1",
            unit_price="71000",
            effective_at=T1,
        )
    assert sell_exc.value.code == "HOLD_POSITION_SOURCE_MANAGED_EXTERNALLY"

    with pytest.raises(HoldingsLifecycleError) as correction_exc:
        service.record_correction(
            position_id=observed.id,
            corrected_quantity="9",
            corrected_average_price="70000",
            effective_at=T1,
            note="test",
        )
    assert correction_exc.value.code == "HOLD_POSITION_SOURCE_MANAGED_EXTERNALLY"


def test_buy_revision_must_match_stock_and_exist_before_buy(env):
    catalog, service = env
    account = _manual_account(catalog)
    stock = _stock(catalog)
    other = _stock(catalog, "000660", "SK하이닉스")

    day, good = _revision(
        catalog,
        stock.id,
        fingerprint="good",
        computed_at="2026-09-18T08:30:00+09:00",
    )
    bought = service.record_buy(
        monitored_stock_id=stock.id,
        position_account_id=account.id,
        quantity="1",
        unit_price="261000",
        effective_at=T1,
        analysis_revision_id=good.id,
    )
    assert bought.event.analysis_revision_id == good.id

    later = catalog.append_analysis_revision(
        analysis_day_id=day.id,
        input_fingerprint="later-current",
        strategy_key="trend_following",
        action_state="READY",
        risk_state="READY",
        reference_price="262000",
        stop_price=None,
        target1_price=None,
        target2_price=None,
        scanner_version="0.21.3.7",
        analysis_engine_version="HOLD_SINGLE_STOCK_V1",
        policy_version="TEST",
        source_versions={},
        snapshot={},
        computed_at="2026-09-18T10:30:00+09:00",
    )
    catalog.promote_current_revision(
        analysis_day_id=day.id,
        revision_id=later.id,
    )
    assert catalog.list_position_events(bought.position.id)[0].analysis_revision_id == good.id

    _, wrong_stock = _revision(
        catalog,
        other.id,
        fingerprint="wrong-stock",
        computed_at="2026-09-18T08:00:00+09:00",
    )
    account2 = catalog.create_position_account(
        provider="MANUAL",
        account_kind="MANUAL",
        display_name="수동 계좌 2",
    )
    with pytest.raises(HoldingsLifecycleError) as mismatch_exc:
        service.record_buy(
            monitored_stock_id=stock.id,
            position_account_id=account2.id,
            quantity="1",
            unit_price="261000",
            effective_at=T1,
            analysis_revision_id=wrong_stock.id,
        )
    assert mismatch_exc.value.code == "HOLD_POSITION_REVISION_MISMATCH"

    future_day, future_revision = _revision(
        catalog,
        stock.id,
        fingerprint="future",
        computed_at="2026-09-18T12:00:00+09:00",
    )
    assert future_day.id == day.id
    with pytest.raises(HoldingsLifecycleError) as future_exc:
        service.record_buy(
            monitored_stock_id=stock.id,
            position_account_id=account2.id,
            quantity="1",
            unit_price="261000",
            effective_at=T1,
            analysis_revision_id=future_revision.id,
        )
    assert future_exc.value.code == "HOLD_POSITION_REVISION_FROM_FUTURE"
    assert catalog.list_positions(stock.id, status="OPEN") == [bought.position]


def test_position_and_event_are_one_atomic_transaction(env, monkeypatch):
    catalog, service = env
    account = _manual_account(catalog)
    stock = _stock(catalog)
    opened = service.record_buy(
        monitored_stock_id=stock.id,
        position_account_id=account.id,
        quantity="10",
        unit_price="70000",
        effective_at=T1,
    )
    before = catalog.get_position(opened.position.id)
    events_before = catalog.list_position_events(opened.position.id)

    def fail_event(*args, **kwargs):
        raise RuntimeError("forced event failure")

    monkeypatch.setattr(service, "_insert_event", fail_event)
    with pytest.raises(RuntimeError, match="forced event failure"):
        service.record_buy(
            monitored_stock_id=stock.id,
            position_account_id=account.id,
            quantity="5",
            unit_price="80000",
            effective_at=T2,
        )

    assert catalog.get_position(opened.position.id) == before
    assert catalog.list_position_events(opened.position.id) == events_before


def test_quantity_and_price_validation(env):
    catalog, service = env
    account = _manual_account(catalog)
    stock = _stock(catalog)

    for quantity in ("0", "-1"):
        with pytest.raises(HoldingsLifecycleError) as exc_info:
            service.record_buy(
                monitored_stock_id=stock.id,
                position_account_id=account.id,
                quantity=quantity,
                unit_price="70000",
                effective_at=T1,
            )
        assert exc_info.value.code == "HOLD_POSITION_QUANTITY_INVALID"

    with pytest.raises(HoldingsLifecycleError) as exc_info:
        service.record_buy(
            monitored_stock_id=stock.id,
            position_account_id=account.id,
            quantity="1",
            unit_price="0",
            effective_at=T1,
        )
    assert exc_info.value.code == "HOLD_POSITION_PRICE_INVALID"


def test_lifecycle_does_not_change_schema_or_depend_on_scanner_kis_or_analysis(env):
    catalog, service = env
    before = _schema_snapshot(catalog)
    account = _manual_account(catalog)
    stock = _stock(catalog)
    service.record_buy(
        monitored_stock_id=stock.id,
        position_account_id=account.id,
        quantity="1",
        unit_price="70000",
        effective_at=T1,
    )
    after = _schema_snapshot(catalog)
    assert after == before

    source = Path("backend/app/holdings/lifecycle.py").read_text(encoding="utf-8")
    assert "integrations.kis" not in source
    assert "app.backtest" not in source
    assert "analysis.py" not in source
    assert "float(" not in source
