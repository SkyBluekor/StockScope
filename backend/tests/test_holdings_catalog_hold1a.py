from __future__ import annotations

import sqlite3
from decimal import Decimal

import pytest

from app.holdings import HoldingsCatalog, HoldingsCatalogError, account_fingerprint


@pytest.fixture()
def catalog(tmp_path):
    value = HoldingsCatalog(tmp_path / "holdings.db")
    value.initialize()
    return value


def _manual_account(catalog: HoldingsCatalog, name: str = "수동 계좌"):
    return catalog.create_position_account(
        provider="MANUAL",
        account_kind="MANUAL",
        display_name=name,
    )


def _virtual_account(catalog: HoldingsCatalog):
    return catalog.create_position_account(
        provider="VIRTUAL",
        account_kind="VIRTUAL",
        display_name="가상 계좌",
    )


def _stock(catalog: HoldingsCatalog):
    return catalog.create_monitored_stock(
        market="KOSPI",
        ticker="005930",
        name="삼성전자",
    )


def _revision(catalog: HoldingsCatalog, stock_id: str, fingerprint: str = "fp-1"):
    day = catalog.get_or_create_analysis_day(
        monitored_stock_id=stock_id,
        market_date="2026-09-22",
    )
    revision = catalog.append_analysis_revision(
        analysis_day_id=day.id,
        input_fingerprint=fingerprint,
        strategy_key="trend_recovery",
        action_state="WATCH",
        risk_state="READY",
        reference_price="277500",
        stop_price="270000",
        target1_price="285000",
        target2_price="295000",
        scanner_version="0.21.3.7",
        analysis_engine_version="HOLD_TEST",
        policy_version="TEST",
        source_versions={"market_store": "fixture"},
        snapshot={"strategy": "trend_recovery"},
    )
    return day, revision


def test_monitored_stock_unique_and_watch_independent_from_position(catalog):
    stock = _stock(catalog)
    account = _manual_account(catalog)

    updated = catalog.set_watch_enabled(stock.id, False)
    assert updated.watch_enabled is False

    position = catalog.open_position(
        monitored_stock_id=stock.id,
        position_account_id=account.id,
        opened_reason="MANUAL",
        current_quantity="10",
        current_average_price="70000",
    )
    assert position.status == "OPEN"
    assert catalog.get_monitored_stock(stock.id).watch_enabled is False

    with pytest.raises(HoldingsCatalogError) as exc_info:
        _stock(catalog)
    assert exc_info.value.code == "HOLD_STOCK_DUPLICATE"


def test_raw_broker_account_number_is_not_persisted(catalog):
    raw_account = "12345678"
    fingerprint = account_fingerprint(
        provider="KIS",
        broker_environment="REAL",
        account_number=raw_account,
        product_code="01",
    )
    account = catalog.create_position_account(
        provider="KIS",
        account_kind="BROKER",
        broker_environment="REAL",
        external_account_fingerprint=fingerprint,
        display_name="한국투자증권",
    )

    assert account.external_account_fingerprint == fingerprint
    assert raw_account.encode() not in catalog.db_path.read_bytes()


def test_multiple_accounts_allowed_but_only_one_open_position_per_stock_account(catalog):
    stock = _stock(catalog)
    manual = _manual_account(catalog)
    virtual = _virtual_account(catalog)

    first = catalog.open_position(
        monitored_stock_id=stock.id,
        position_account_id=manual.id,
        opened_reason="MANUAL",
        current_quantity="10",
    )
    second = catalog.open_position(
        monitored_stock_id=stock.id,
        position_account_id=virtual.id,
        opened_reason="VIRTUAL",
        current_quantity="20",
    )
    assert first.position_account_id != second.position_account_id

    with pytest.raises(HoldingsCatalogError) as exc_info:
        catalog.open_position(
            monitored_stock_id=stock.id,
            position_account_id=manual.id,
            opened_reason="MANUAL",
        )
    assert exc_info.value.code == "HOLD_OPEN_POSITION_DUPLICATE"


def test_closed_position_allows_new_holding_round(catalog):
    stock = _stock(catalog)
    account = _manual_account(catalog)
    old = catalog.open_position(
        monitored_stock_id=stock.id,
        position_account_id=account.id,
        opened_reason="MANUAL",
        current_quantity="1",
    )
    catalog.close_position(old.id)

    new = catalog.open_position(
        monitored_stock_id=stock.id,
        position_account_id=account.id,
        opened_reason="MANUAL",
        current_quantity="2",
    )

    assert new.id != old.id
    assert len(catalog.list_positions(stock.id)) == 2
    assert len(catalog.list_positions(stock.id, status="OPEN")) == 1


def test_position_event_is_append_only_and_supports_balance_observation(catalog):
    stock = _stock(catalog)
    account = _manual_account(catalog)
    position = catalog.open_position(
        monitored_stock_id=stock.id,
        position_account_id=account.id,
        opened_reason="MANUAL",
    )

    event = catalog.append_position_event(
        position_id=position.id,
        event_type="BALANCE_OBSERVED",
        before_quantity="100",
        after_quantity="70",
        observed_at="2026-09-22T10:00:00+09:00",
    )
    assert event.event_type == "BALANCE_OBSERVED"
    assert event.before_quantity == Decimal("100")
    assert event.after_quantity == Decimal("70")

    with catalog.connect() as conn:
        with pytest.raises(sqlite3.DatabaseError):
            conn.execute(
                "UPDATE holding_position_event SET note='changed' WHERE id=?",
                (event.id,),
            )
        with pytest.raises(sqlite3.DatabaseError):
            conn.execute(
                "DELETE FROM holding_position_event WHERE id=?",
                (event.id,),
            )


def test_sync_run_completed_and_failed_states(catalog):
    account = _manual_account(catalog)

    completed = catalog.start_sync_run(
        position_account_id=account.id,
        observed_at="2026-09-22T10:00:00+09:00",
    )
    completed = catalog.complete_sync_run(
        completed.id,
        observed_at="2026-09-22T10:00:01+09:00",
        page_count=1,
        holding_count=0,
    )
    assert completed.status == "COMPLETED"
    assert completed.is_complete is True

    failed = catalog.start_sync_run(position_account_id=account.id)
    failed = catalog.fail_sync_run(
        failed.id,
        error_code="NETWORK",
        error_message="test",
    )
    assert failed.status == "FAILED"
    assert failed.is_complete is False


def test_analysis_day_is_idempotent(catalog):
    stock = _stock(catalog)
    first = catalog.get_or_create_analysis_day(
        monitored_stock_id=stock.id,
        market_date="2026-09-22",
    )
    second = catalog.get_or_create_analysis_day(
        monitored_stock_id=stock.id,
        market_date="2026-09-22",
    )
    assert second.id == first.id


def test_same_fingerprint_reuses_revision_and_new_input_adds_revision(catalog):
    stock = _stock(catalog)
    day, first = _revision(catalog, stock.id, "same")

    same = catalog.append_analysis_revision(
        analysis_day_id=day.id,
        input_fingerprint="same",
        strategy_key="different-value-that-must-not-overwrite",
        action_state="READY",
        risk_state="READY",
        reference_price="999999",
        stop_price=None,
        target1_price=None,
        target2_price=None,
        scanner_version="different",
        analysis_engine_version="different",
        policy_version="different",
        source_versions={},
        snapshot={},
    )
    assert same.id == first.id
    assert same.strategy_key == "trend_recovery"

    second = catalog.append_analysis_revision(
        analysis_day_id=day.id,
        input_fingerprint="changed",
        strategy_key="trend_following",
        action_state="READY",
        risk_state="READY",
        reference_price="280000",
        stop_price="270000",
        target1_price="290000",
        target2_price="300000",
        scanner_version="0.21.3.7",
        analysis_engine_version="HOLD_TEST",
        policy_version="TEST",
        source_versions={"market_store": "fixture-2"},
        snapshot={"strategy": "trend_following"},
        revision_reason="INPUT_CHANGED",
    )
    assert second.revision_no == 2


def test_revision_is_immutable_and_current_revision_can_move(catalog):
    stock = _stock(catalog)
    day, first = _revision(catalog, stock.id, "fp-1")
    second = catalog.append_analysis_revision(
        analysis_day_id=day.id,
        input_fingerprint="fp-2",
        strategy_key="trend_following",
        action_state="READY",
        risk_state="READY",
        reference_price="280000",
        stop_price=None,
        target1_price=None,
        target2_price=None,
        scanner_version="0.21.3.7",
        analysis_engine_version="HOLD_TEST",
        policy_version="TEST",
        source_versions={},
        snapshot={},
    )

    catalog.promote_current_revision(
        analysis_day_id=day.id,
        revision_id=first.id,
    )
    assert catalog.get_current_revision(day.id).id == first.id

    catalog.promote_current_revision(
        analysis_day_id=day.id,
        revision_id=second.id,
    )
    assert catalog.get_current_revision(day.id).id == second.id

    with catalog.connect() as conn:
        with pytest.raises(sqlite3.DatabaseError):
            conn.execute(
                "UPDATE stock_analysis_revision SET strategy_key='x' WHERE id=?",
                (first.id,),
            )


def test_buy_event_keeps_original_analysis_revision_reference(catalog):
    stock = _stock(catalog)
    account = _manual_account(catalog)
    position = catalog.open_position(
        monitored_stock_id=stock.id,
        position_account_id=account.id,
        opened_reason="MANUAL",
    )
    day, first = _revision(catalog, stock.id, "fp-1")
    catalog.promote_current_revision(
        analysis_day_id=day.id,
        revision_id=first.id,
    )
    event = catalog.append_position_event(
        position_id=position.id,
        event_type="BUY",
        quantity_delta="10",
        unit_price="70000",
        analysis_revision_id=first.id,
    )

    second = catalog.append_analysis_revision(
        analysis_day_id=day.id,
        input_fingerprint="fp-2",
        strategy_key="trend_following",
        action_state="READY",
        risk_state="READY",
        reference_price="280000",
        stop_price=None,
        target1_price=None,
        target2_price=None,
        scanner_version="0.21.3.7",
        analysis_engine_version="HOLD_TEST",
        policy_version="TEST",
        source_versions={},
        snapshot={},
    )
    catalog.promote_current_revision(
        analysis_day_id=day.id,
        revision_id=second.id,
    )

    stored_event = catalog.list_position_events(position.id)[0]
    assert stored_event.analysis_revision_id == first.id
    assert catalog.get_current_revision(day.id).id == second.id


def test_foreign_keys_are_enforced(catalog):
    account = _manual_account(catalog)

    with pytest.raises(HoldingsCatalogError) as exc_info:
        catalog.open_position(
            monitored_stock_id="missing-stock",
            position_account_id=account.id,
            opened_reason="MANUAL",
        )
    assert exc_info.value.code == "HOLD_POSITION_FK_INVALID"
