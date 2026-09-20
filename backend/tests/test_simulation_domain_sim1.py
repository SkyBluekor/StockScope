from __future__ import annotations

import json
import sqlite3
from dataclasses import FrozenInstanceError
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from app.simulation.sim1_enums import (
    OrderSide,
    OrderStatus,
    OrderType,
    PortfolioStatus,
    PositionSource,
    PositionStatus,
    SimulationMode,
)
from app.simulation.sim1_models import (
    SimulationDomainError,
    SimulationOrder,
    SimulationPosition,
    SimulationTrade,
    weighted_average_entry,
)
from app.simulation.sim1_service import SimulationPortfolioService
from app.simulation.sim1_store import BaselineRegistry, SimulationRepository

NOW = datetime(2026, 9, 20, 12, 0, tzinfo=timezone.utc)
BASELINE_ID = "SS-SCANNER-0.21.3.7-testbaseline"


@pytest.fixture()
def env(tmp_path: Path):
    baseline_dir = tmp_path / "backend" / "runtime" / "baseline"
    baseline_dir.mkdir(parents=True)
    (baseline_dir / "scanner-production-baseline_0.21.3.7.json").write_text(
        json.dumps(
            {
                "baseline_id": BASELINE_ID,
                "scanner_version": "0.21.3.7",
                "production_fingerprint": "abc",
                "policy_fingerprint": "def",
            }
        ),
        encoding="utf-8",
    )
    repo = SimulationRepository(tmp_path / "backend" / "runtime" / "simulation" / "simulation.db")
    service = SimulationPortfolioService(repo, BaselineRegistry(baseline_dir))
    service.initialize()
    return tmp_path, repo, service


def portfolio(service, cash="10000000", mode=SimulationMode.HISTORICAL):
    return service.create_portfolio(name="Main Simulation", initial_cash=cash, mode=mode, now=NOW)


def position(service, p, *, qty=10, entry="80000", current="85000", source=PositionSource.SCANNER):
    return service.create_position_state(
        portfolio_id=p.id,
        stock_code="005930",
        stock_name="삼성전자",
        market="KOSPI",
        source=source,
        quantity=qty,
        average_entry_price=entry,
        current_price=current,
        opened_at=NOW,
    )


def test_01_portfolio_create_and_persist(env):
    _, repo, service = env
    p = portfolio(service)
    loaded = repo.get_portfolio(p.id)
    assert loaded == p
    assert p.cash_balance == Decimal("10000000")


def test_02_initial_cash_must_be_positive(env):
    _, _, service = env
    with pytest.raises(SimulationDomainError):
        portfolio(service, "0")
    with pytest.raises(SimulationDomainError):
        portfolio(service, "-1")


def test_03_portfolio_summary_empty(env):
    _, _, service = env
    p = portfolio(service)
    s = service.summary(p.id)
    assert s.positions_market_value == Decimal("0")
    assert s.total_equity == Decimal("10000000")
    assert s.total_return_pct == Decimal("0")


def test_04_open_position_create(env):
    _, repo, service = env
    p = portfolio(service)
    pos = position(service, p)
    assert repo.get_position(pos.id) == pos
    assert pos.status == PositionStatus.OPEN


def test_05_cost_basis(env):
    _, _, service = env
    p = portfolio(service)
    pos = position(service, p, qty=10, entry="80000")
    assert pos.cost_basis == Decimal("800000")


def test_06_unrealized_pnl(env):
    _, _, service = env
    p = portfolio(service)
    pos = position(service, p, qty=10, entry="80000", current="85000")
    assert pos.unrealized_pnl == Decimal("50000")
    assert pos.unrealized_pnl_pct == Decimal("6.25")


def test_07_decimal_precision_not_float(env):
    _, _, service = env
    p = portfolio(service, "0.3")
    assert p.initial_cash == Decimal("0.3")
    assert p.initial_cash != Decimal.from_float(0.3)


def test_08_weighted_average_entry():
    result = weighted_average_entry(10, Decimal("80000"), 5, Decimal("90000"))
    assert result == Decimal("250000") / Decimal("3")


def test_09_additional_buy_preview_does_not_mutate(env):
    _, repo, service = env
    p = portfolio(service)
    pos = position(service, p)
    qty, avg = service.preview_additional_buy(pos, added_quantity=5, added_price="90000")
    assert qty == 15
    assert avg == Decimal("250000") / Decimal("3")
    assert repo.get_position(pos.id) == pos


def test_10_quantity_validation(env):
    _, _, service = env
    p = portfolio(service)
    for qty in (0, -1):
        with pytest.raises(SimulationDomainError):
            position(service, p, qty=qty)


def test_11_price_validation(env):
    _, _, service = env
    p = portfolio(service)
    with pytest.raises(SimulationDomainError):
        position(service, p, entry="0")
    with pytest.raises(SimulationDomainError):
        position(service, p, current="-1")


def test_12_partial_sell_contract(env):
    _, _, service = env
    p = portfolio(service)
    pos = position(service, p, qty=10)
    remaining, status = service.preview_remaining_quantity(pos, 3)
    assert (remaining, status) == (7, PositionStatus.OPEN)


def test_13_full_sell_contract_closes(env):
    _, _, service = env
    p = portfolio(service)
    pos = position(service, p, qty=10)
    remaining, status = service.preview_remaining_quantity(pos, 10)
    assert (remaining, status) == (0, PositionStatus.CLOSED)


def test_14_sell_more_than_owned_rejected(env):
    _, _, service = env
    p = portfolio(service)
    pos = position(service, p, qty=10)
    with pytest.raises(SimulationDomainError):
        service.preview_remaining_quantity(pos, 11)


def test_15_realized_and_unrealized_are_separate(env):
    _, _, service = env
    p = portfolio(service)
    pos = position(service, p)
    assert p.realized_pnl == Decimal("0")
    assert pos.realized_pnl == Decimal("0")
    assert pos.unrealized_pnl == Decimal("50000")


def test_16_baseline_id_is_saved(env):
    _, _, service = env
    p = portfolio(service)
    pos = position(service, p)
    assert p.default_scanner_baseline_id == BASELINE_ID
    assert pos.scanner_baseline_id == BASELINE_ID


def test_17_invalid_baseline_is_rejected(env):
    _, _, service = env
    with pytest.raises(SimulationDomainError):
        service.create_portfolio(
            name="bad",
            initial_cash="1000",
            scanner_baseline_id="missing",
            now=NOW,
        )


def test_18_position_source_enum(env):
    _, _, service = env
    p = portfolio(service)
    assert position(service, p, source=PositionSource.MANUAL).source == PositionSource.MANUAL
    assert PositionSource.KIS_IMPORT.value == "KIS_IMPORT"


def test_19_simulation_modes(env):
    _, _, service = env
    p = portfolio(service, mode=SimulationMode.MANUAL_TRACKING)
    assert p.mode == SimulationMode.MANUAL_TRACKING
    assert SimulationMode.PAPER.value == "PAPER"


def test_20_fk_integrity_position_requires_portfolio(env):
    _, repo, _ = env
    ghost = SimulationPosition(
        id="pos-ghost",
        portfolio_id="missing",
        stock_code="005930",
        stock_name="삼성전자",
        market="KOSPI",
        source=PositionSource.MANUAL,
        status=PositionStatus.OPEN,
        quantity=1,
        average_entry_price=Decimal("1"),
        current_price=Decimal("1"),
        realized_pnl=Decimal("0"),
        scanner_baseline_id=BASELINE_ID,
        opened_at=NOW,
    )
    with pytest.raises(sqlite3.IntegrityError):
        repo.create_position(ghost)


def test_21_portfolio_summary_with_position(env):
    _, _, service = env
    p = portfolio(service)
    position(service, p, qty=10, entry="80000", current="85000")
    s = service.summary(p.id)
    assert s.positions_market_value == Decimal("850000")
    assert s.unrealized_pnl == Decimal("50000")
    # SIM.1 intentionally does not move cash; execution/cash movement belongs to SIM.2.
    assert s.total_equity == Decimal("10850000")


def test_22_revalue_position(env):
    _, _, service = env
    p = portfolio(service)
    pos = position(service, p)
    updated = service.revalue_position(pos.id, "90000")
    assert updated.current_price == Decimal("90000")
    assert updated.unrealized_pnl == Decimal("100000")


def test_23_limit_order_requires_price(env):
    with pytest.raises(SimulationDomainError):
        SimulationOrder(
            id="o1",
            portfolio_id="p1",
            position_id=None,
            stock_code="005930",
            stock_name="삼성전자",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=1,
            requested_price=None,
            status=OrderStatus.PENDING,
            requested_at=NOW,
        )


def test_24_trade_is_frozen_dataclass():
    t = SimulationTrade(
        id="t1",
        portfolio_id="p1",
        order_id="o1",
        position_id="pos1",
        stock_code="005930",
        side=OrderSide.BUY,
        quantity=1,
        price=Decimal("100"),
        gross_amount=Decimal("100"),
        fee=Decimal("0"),
        tax=Decimal("0"),
        slippage=Decimal("0"),
        net_amount=Decimal("100"),
        realized_pnl=Decimal("0"),
        executed_at=NOW,
    )
    with pytest.raises(FrozenInstanceError):
        t.price = Decimal("101")  # type: ignore[misc]


def test_25_trade_db_is_immutable(env):
    _, repo, service = env
    p = portfolio(service)
    pos = position(service, p)
    order = SimulationOrder(
        id="o1",
        portfolio_id=p.id,
        position_id=pos.id,
        stock_code=pos.stock_code,
        stock_name=pos.stock_name,
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=1,
        requested_price=None,
        status=OrderStatus.FILLED,
        requested_at=NOW,
        filled_at=NOW,
    )
    repo.create_order(order)
    trade = SimulationTrade(
        id="t1",
        portfolio_id=p.id,
        order_id=order.id,
        position_id=pos.id,
        stock_code=pos.stock_code,
        side=OrderSide.BUY,
        quantity=1,
        price=Decimal("80000"),
        gross_amount=Decimal("80000"),
        fee=Decimal("0"),
        tax=Decimal("0"),
        slippage=Decimal("0"),
        net_amount=Decimal("80000"),
        realized_pnl=Decimal("0"),
        executed_at=NOW,
    )
    repo.create_trade(trade)
    with pytest.raises(sqlite3.IntegrityError):
        repo.raw_execute("UPDATE simulation_trade SET price='1' WHERE id='t1'")
    with pytest.raises(sqlite3.IntegrityError):
        repo.raw_execute("DELETE FROM simulation_trade WHERE id='t1'")


def test_26_market_order_allows_no_requested_price():
    order = SimulationOrder(
        id="o1",
        portfolio_id="p1",
        position_id=None,
        stock_code="005930",
        stock_name="삼성전자",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=1,
        requested_price=None,
        status=OrderStatus.PENDING,
        requested_at=NOW,
    )
    assert order.requested_price is None


def test_27_closed_position_contract_requires_zero_and_closed_at():
    with pytest.raises(SimulationDomainError):
        SimulationPosition(
            id="x",
            portfolio_id="p",
            stock_code="005930",
            stock_name="삼성전자",
            market="KOSPI",
            source=PositionSource.MANUAL,
            status=PositionStatus.CLOSED,
            quantity=1,
            average_entry_price=Decimal("1"),
            current_price=Decimal("1"),
            realized_pnl=Decimal("0"),
            scanner_baseline_id=BASELINE_ID,
            opened_at=NOW,
            closed_at=NOW,
        )


def test_28_naive_datetime_rejected(env):
    _, _, service = env
    with pytest.raises(SimulationDomainError):
        service.create_portfolio(
            name="bad time",
            initial_cash="1000",
            scanner_baseline_id=BASELINE_ID,
            now=datetime(2026, 9, 20, 12, 0),
        )


def test_29_api_router_contract_importable():
    from app.simulation.sim1_api import router

    paths = {route.path for route in router.routes}
    assert "/simulation/portfolios" in paths
    assert "/simulation/portfolios/{portfolio_id}" in paths
    assert "/simulation/portfolios/{portfolio_id}/positions" in paths


def test_30_sim1_files_do_not_import_scanner_production():
    root = Path(__file__).resolve().parents[1] / "app" / "simulation"
    texts = "\n".join(path.read_text(encoding="utf-8") for path in root.glob("sim1_*.py"))
    assert "app.backtest.scanner" not in texts
    assert "candidate_priority" not in texts
