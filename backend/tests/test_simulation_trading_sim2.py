from __future__ import annotations

import json
import sqlite3
from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from app.simulation.sim1_enums import OrderSide, OrderStatus, PortfolioStatus, PositionSource, PositionStatus
from app.simulation.sim1_models import SimulationDomainError
from app.simulation.sim1_service import SimulationPortfolioService
from app.simulation.sim1_store import BaselineRegistry, SimulationRepository, SimulationUnitOfWork
from app.simulation.sim2_commands import BuyCommand, SellCommand
from app.simulation.sim2_trading_service import SimulationTradingError, SimulationTradingService

BASELINE_ID = "SS-SCANNER-0.21.3.7-testbaseline"
NOW = datetime(2026, 9, 20, 22, 0, tzinfo=timezone.utc)


def make_baseline(root: Path) -> Path:
    d = root / "baseline"
    d.mkdir(parents=True, exist_ok=True)
    (d / "scanner-production-baseline_0.21.3.7.json").write_text(
        json.dumps({"baseline_id": BASELINE_ID, "scanner_version": "0.21.3.7"}),
        encoding="utf-8",
    )
    return d


@pytest.fixture
def env(tmp_path: Path):
    baseline_dir = make_baseline(tmp_path)
    repo = SimulationRepository(tmp_path / "simulation.db")
    registry = BaselineRegistry(baseline_dir)
    portfolio_service = SimulationPortfolioService(repo, registry)
    portfolio_service.initialize()
    trading = SimulationTradingService(repo, registry)
    return repo, portfolio_service, trading


def create_portfolio(service: SimulationPortfolioService, cash: str = "10000000"):
    return service.create_portfolio(
        name="SIM2",
        initial_cash=cash,
        scanner_baseline_id=BASELINE_ID,
        now=NOW,
    )


def buy_cmd(portfolio_id: str, **overrides):
    data = dict(
        portfolio_id=portfolio_id,
        stock_code="005930",
        stock_name="삼성전자",
        market="KOSPI",
        quantity=10,
        execution_price=Decimal("82000"),
        source=PositionSource.MANUAL,
    )
    data.update(overrides)
    return BuyCommand(**data)


def sell_cmd(portfolio_id: str, position_id: str, **overrides):
    data = dict(
        portfolio_id=portfolio_id,
        position_id=position_id,
        quantity=5,
        execution_price=Decimal("87000"),
    )
    data.update(overrides)
    return SellCommand(**data)


def error_code(exc_info) -> str:
    return exc_info.value.code


def test_01_normal_buy(env):
    repo, ps, trading = env
    p = create_portfolio(ps)
    r = trading.buy(buy_cmd(p.id), now=NOW)
    assert r.order.status == OrderStatus.FILLED
    assert r.trade.side == OrderSide.BUY
    assert r.position.quantity == 10
    assert repo.count_trades(p.id) == 1


def test_02_buy_reduces_cash(env):
    _, ps, trading = env
    p = create_portfolio(ps)
    r = trading.buy(buy_cmd(p.id), now=NOW)
    assert r.portfolio.cash_balance == Decimal("9180000")


def test_03_buy_creates_position(env):
    repo, ps, trading = env
    p = create_portfolio(ps)
    r = trading.buy(buy_cmd(p.id), now=NOW)
    assert repo.get_position(r.position.id) == r.position
    assert r.position.status == PositionStatus.OPEN


def test_04_buy_trade_fields(env):
    _, ps, trading = env
    p = create_portfolio(ps)
    r = trading.buy(buy_cmd(p.id), now=NOW)
    assert r.trade.gross_amount == Decimal("820000")
    assert r.trade.net_amount == Decimal("820000")
    assert r.trade.fee == r.trade.tax == r.trade.slippage == Decimal("0")


def test_05_buy_order_filled_persisted(env):
    repo, ps, trading = env
    p = create_portfolio(ps)
    r = trading.buy(buy_cmd(p.id), now=NOW)
    assert repo.get_order(r.order.id).status == OrderStatus.FILLED


def test_06_insufficient_cash(env):
    repo, ps, trading = env
    p = create_portfolio(ps, "1000")
    with pytest.raises(SimulationTradingError) as e:
        trading.buy(buy_cmd(p.id), now=NOW)
    assert error_code(e) == "SIM_INSUFFICIENT_CASH"
    assert repo.count_orders(p.id) == repo.count_trades(p.id) == 0


def test_07_insufficient_cash_does_not_change_cash(env):
    repo, ps, trading = env
    p = create_portfolio(ps, "1000")
    with pytest.raises(SimulationTradingError):
        trading.buy(buy_cmd(p.id), now=NOW)
    assert repo.get_portfolio(p.id).cash_balance == Decimal("1000")


def test_08_additional_buy_merges_position(env):
    repo, ps, trading = env
    p = create_portfolio(ps)
    a = trading.buy(buy_cmd(p.id, quantity=10, execution_price=Decimal("80000")), now=NOW)
    b = trading.buy(buy_cmd(p.id, quantity=5, execution_price=Decimal("90000")), now=NOW)
    opens = repo.list_positions(p.id, status=PositionStatus.OPEN)
    assert len(opens) == 1
    assert a.position.id == b.position.id
    assert b.position.quantity == 15


def test_09_weighted_average(env):
    _, ps, trading = env
    p = create_portfolio(ps)
    trading.buy(buy_cmd(p.id, quantity=10, execution_price=Decimal("80000")), now=NOW)
    r = trading.buy(buy_cmd(p.id, quantity=5, execution_price=Decimal("90000")), now=NOW)
    assert r.position.average_entry_price == Decimal("250000") / Decimal("3")


def test_10_additional_buy_preserves_original_source(env):
    _, ps, trading = env
    p = create_portfolio(ps)
    first = trading.buy(buy_cmd(p.id, source=PositionSource.MANUAL), now=NOW)
    second = trading.buy(
        buy_cmd(p.id, source=PositionSource.SCANNER, scanner_baseline_id=BASELINE_ID, quantity=1),
        now=NOW,
    )
    assert first.position.source == second.position.source == PositionSource.MANUAL


def test_11_partial_sell(env):
    _, ps, trading = env
    p = create_portfolio(ps)
    b = trading.buy(buy_cmd(p.id), now=NOW)
    s = trading.sell(sell_cmd(p.id, b.position.id, quantity=3), now=NOW)
    assert s.position.quantity == 7
    assert s.position.status == PositionStatus.OPEN


def test_12_partial_sell_average_unchanged(env):
    _, ps, trading = env
    p = create_portfolio(ps)
    b = trading.buy(buy_cmd(p.id, execution_price=Decimal("80000")), now=NOW)
    s = trading.sell(sell_cmd(p.id, b.position.id, quantity=3), now=NOW)
    assert s.position.average_entry_price == Decimal("80000")


def test_13_sell_realized_profit(env):
    _, ps, trading = env
    p = create_portfolio(ps)
    b = trading.buy(buy_cmd(p.id, execution_price=Decimal("80000")), now=NOW)
    s = trading.sell(sell_cmd(p.id, b.position.id, quantity=3, execution_price=Decimal("90000")), now=NOW)
    assert s.realized_pnl == Decimal("30000")
    assert s.position.realized_pnl == Decimal("30000")


def test_14_sell_cash_increases(env):
    _, ps, trading = env
    p = create_portfolio(ps)
    b = trading.buy(buy_cmd(p.id, execution_price=Decimal("80000")), now=NOW)
    s = trading.sell(sell_cmd(p.id, b.position.id, quantity=3, execution_price=Decimal("90000")), now=NOW)
    assert s.portfolio.cash_balance == Decimal("9470000")


def test_15_full_sell_closes(env):
    _, ps, trading = env
    p = create_portfolio(ps)
    b = trading.buy(buy_cmd(p.id), now=NOW)
    s = trading.sell(sell_cmd(p.id, b.position.id, quantity=10), now=NOW)
    assert s.position.quantity == 0
    assert s.position.status == PositionStatus.CLOSED
    assert s.position.closed_at == NOW


def test_16_closed_position_resell_rejected(env):
    _, ps, trading = env
    p = create_portfolio(ps)
    b = trading.buy(buy_cmd(p.id), now=NOW)
    trading.sell(sell_cmd(p.id, b.position.id, quantity=10), now=NOW)
    with pytest.raises(SimulationTradingError) as e:
        trading.sell(sell_cmd(p.id, b.position.id, quantity=1), now=NOW)
    assert error_code(e) == "SIM_POSITION_CLOSED"


def test_17_oversell_rejected(env):
    _, ps, trading = env
    p = create_portfolio(ps)
    b = trading.buy(buy_cmd(p.id), now=NOW)
    with pytest.raises(SimulationTradingError) as e:
        trading.sell(sell_cmd(p.id, b.position.id, quantity=11), now=NOW)
    assert error_code(e) == "SIM_INSUFFICIENT_QUANTITY"


def test_18_oversell_rollback(env):
    repo, ps, trading = env
    p = create_portfolio(ps)
    b = trading.buy(buy_cmd(p.id), now=NOW)
    before = repo.get_portfolio(p.id)
    with pytest.raises(SimulationTradingError):
        trading.sell(sell_cmd(p.id, b.position.id, quantity=11), now=NOW)
    assert repo.get_position(b.position.id).quantity == 10
    assert repo.get_portfolio(p.id).cash_balance == before.cash_balance
    assert repo.count_trades(p.id) == 1


def test_19_negative_realized_pnl(env):
    _, ps, trading = env
    p = create_portfolio(ps)
    b = trading.buy(buy_cmd(p.id, execution_price=Decimal("80000")), now=NOW)
    s = trading.sell(sell_cmd(p.id, b.position.id, quantity=5, execution_price=Decimal("70000")), now=NOW)
    assert s.realized_pnl == Decimal("-50000")
    assert s.portfolio.realized_pnl == Decimal("-50000")


def test_20_decimal_precision(env):
    _, ps, trading = env
    p = create_portfolio(ps, "1")
    r = trading.buy(buy_cmd(p.id, quantity=3, execution_price=Decimal("0.1")), now=NOW)
    assert r.portfolio.cash_balance == Decimal("0.7")


def test_21_trade_immutable_db(env):
    repo, ps, trading = env
    p = create_portfolio(ps)
    r = trading.buy(buy_cmd(p.id), now=NOW)
    with pytest.raises(sqlite3.IntegrityError):
        repo.raw_execute("UPDATE simulation_trade SET price='1' WHERE id=?", (r.trade.id,))
    with pytest.raises(sqlite3.IntegrityError):
        repo.raw_execute("DELETE FROM simulation_trade WHERE id=?", (r.trade.id,))


def test_22_order_trade_fk_link(env):
    repo, ps, trading = env
    p = create_portfolio(ps)
    r = trading.buy(buy_cmd(p.id), now=NOW)
    t = repo.get_trade(r.trade.id)
    assert t.order_id == r.order.id
    assert t.position_id == r.position.id


def test_23_scanner_buy_requires_explicit_baseline(env):
    _, ps, trading = env
    p = create_portfolio(ps)
    with pytest.raises(SimulationTradingError) as e:
        trading.buy(buy_cmd(p.id, source=PositionSource.SCANNER), now=NOW)
    assert error_code(e) == "SIM_BASELINE_REQUIRED"


def test_24_scanner_buy_valid_baseline(env):
    _, ps, trading = env
    p = create_portfolio(ps)
    r = trading.buy(buy_cmd(p.id, source=PositionSource.SCANNER, scanner_baseline_id=BASELINE_ID), now=NOW)
    assert r.position.scanner_baseline_id == BASELINE_ID


def test_25_manual_buy_baseline_optional_uses_portfolio_context(env):
    _, ps, trading = env
    p = create_portfolio(ps)
    r = trading.buy(buy_cmd(p.id, source=PositionSource.MANUAL, scanner_baseline_id=None), now=NOW)
    assert r.position.scanner_baseline_id == BASELINE_ID


def test_26_invalid_baseline_rejected(env):
    _, ps, trading = env
    p = create_portfolio(ps)
    with pytest.raises(SimulationTradingError) as e:
        trading.buy(buy_cmd(p.id, scanner_baseline_id="missing"), now=NOW)
    assert error_code(e) == "SIM_BASELINE_INVALID"


def test_27_missing_portfolio(env):
    _, _, trading = env
    with pytest.raises(SimulationTradingError) as e:
        trading.buy(buy_cmd("missing"), now=NOW)
    assert error_code(e) == "SIM_PORTFOLIO_NOT_FOUND"


def test_28_missing_position(env):
    _, ps, trading = env
    p = create_portfolio(ps)
    with pytest.raises(SimulationTradingError) as e:
        trading.sell(sell_cmd(p.id, "missing"), now=NOW)
    assert error_code(e) == "SIM_POSITION_NOT_FOUND"


def test_29_cross_portfolio_position_rejected(env):
    _, ps, trading = env
    a = create_portfolio(ps)
    b = create_portfolio(ps)
    pos = trading.buy(buy_cmd(a.id), now=NOW).position
    with pytest.raises(SimulationTradingError) as e:
        trading.sell(sell_cmd(b.id, pos.id), now=NOW)
    assert error_code(e) == "SIM_POSITION_NOT_FOUND"


def test_30_archived_portfolio_rejected(env):
    repo, ps, trading = env
    p = create_portfolio(ps)
    repo.raw_execute("UPDATE simulation_portfolio SET status='ARCHIVED' WHERE id=?", (p.id,))
    with pytest.raises(SimulationTradingError) as e:
        trading.buy(buy_cmd(p.id), now=NOW)
    assert error_code(e) == "SIM_PORTFOLIO_INACTIVE"


def test_31_buy_transaction_rolls_back_on_trade_failure(env, monkeypatch):
    repo, ps, trading = env
    p = create_portfolio(ps)
    before = repo.get_portfolio(p.id)

    def explode(self, trade):
        raise RuntimeError("forced trade failure")

    monkeypatch.setattr(SimulationUnitOfWork, "create_trade", explode)
    with pytest.raises(RuntimeError, match="forced"):
        trading.buy(buy_cmd(p.id), now=NOW)
    assert repo.get_portfolio(p.id).cash_balance == before.cash_balance
    assert repo.list_positions(p.id) == []
    assert repo.count_orders(p.id) == repo.count_trades(p.id) == 0


def test_32_sell_transaction_rolls_back_on_trade_failure(env, monkeypatch):
    repo, ps, trading = env
    p = create_portfolio(ps)
    b = trading.buy(buy_cmd(p.id), now=NOW)
    before_portfolio = repo.get_portfolio(p.id)
    before_position = repo.get_position(b.position.id)

    def explode(self, trade):
        raise RuntimeError("forced sell trade failure")

    monkeypatch.setattr(SimulationUnitOfWork, "create_trade", explode)
    with pytest.raises(RuntimeError, match="forced"):
        trading.sell(sell_cmd(p.id, b.position.id, quantity=3), now=NOW)
    assert repo.get_portfolio(p.id).cash_balance == before_portfolio.cash_balance
    assert repo.get_position(b.position.id) == before_position
    assert repo.count_trades(p.id) == 1


def test_33_idempotent_buy(env):
    repo, ps, trading = env
    p = create_portfolio(ps)
    cmd = buy_cmd(p.id, client_request_id="buy-1")
    a = trading.buy(cmd, now=NOW)
    b = trading.buy(cmd, now=NOW)
    assert b.idempotent_replay is True
    assert a.trade.id == b.trade.id
    assert repo.count_trades(p.id) == 1
    assert repo.get_position(a.position.id).quantity == 10


def test_34_idempotent_sell(env):
    repo, ps, trading = env
    p = create_portfolio(ps)
    b = trading.buy(buy_cmd(p.id), now=NOW)
    cmd = sell_cmd(p.id, b.position.id, quantity=3, client_request_id="sell-1")
    a = trading.sell(cmd, now=NOW)
    r = trading.sell(cmd, now=NOW)
    assert r.idempotent_replay is True
    assert a.trade.id == r.trade.id
    assert repo.get_position(b.position.id).quantity == 7
    assert repo.count_trades(p.id) == 2


def test_35_request_id_cannot_switch_side(env):
    _, ps, trading = env
    p = create_portfolio(ps)
    b = trading.buy(buy_cmd(p.id, client_request_id="same"), now=NOW)
    with pytest.raises(SimulationTradingError) as e:
        trading.sell(sell_cmd(p.id, b.position.id, client_request_id="same"), now=NOW)
    assert error_code(e) == "SIM_DUPLICATE_REQUEST"


def test_36_portfolio_equity_after_buy(env):
    _, ps, trading = env
    p = create_portfolio(ps)
    trading.buy(buy_cmd(p.id), now=NOW)
    s = ps.summary(p.id)
    assert s.total_equity == Decimal("10000000")
    assert s.unrealized_pnl == Decimal("0")


def test_37_portfolio_equity_after_profitable_partial_sell(env):
    _, ps, trading = env
    p = create_portfolio(ps)
    b = trading.buy(buy_cmd(p.id, execution_price=Decimal("80000")), now=NOW)
    trading.sell(sell_cmd(p.id, b.position.id, quantity=5, execution_price=Decimal("90000")), now=NOW)
    s = ps.summary(p.id)
    assert s.portfolio.realized_pnl == Decimal("50000")
    assert s.total_equity == Decimal("10100000")


def test_38_sell_updates_remaining_current_price(env):
    _, ps, trading = env
    p = create_portfolio(ps)
    b = trading.buy(buy_cmd(p.id, execution_price=Decimal("80000")), now=NOW)
    s = trading.sell(sell_cmd(p.id, b.position.id, quantity=3, execution_price=Decimal("90000")), now=NOW)
    assert s.position.current_price == Decimal("90000")


def test_39_schema_version_is_current(env):
    repo, _, _ = env
    assert repo.schema_version() == 3


def test_40_v1_order_table_migrates_client_request_id(tmp_path: Path):
    db = tmp_path / "legacy.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE simulation_order (id TEXT PRIMARY KEY, portfolio_id TEXT NOT NULL)")
    conn.commit()
    conn.close()
    repo = SimulationRepository(db)
    # Full schema cannot reuse a deliberately incomplete legacy table for trading, but migration must add the v2 column.
    repo.initialize()
    with repo.connect() as c:
        cols = {row[1] for row in c.execute("PRAGMA table_info(simulation_order)").fetchall()}
    assert "client_request_id" in cols
    assert repo.schema_version() == 3


def test_41_api_routes_importable():
    from app.simulation.sim2_api import router

    paths = {route.path for route in router.routes}
    assert "/simulation/portfolios/{portfolio_id}/buy" in paths
    assert "/simulation/portfolios/{portfolio_id}/sell" in paths


def test_42_error_code_contract(env):
    _, ps, trading = env
    p = create_portfolio(ps, "1")
    with pytest.raises(SimulationTradingError) as e:
        trading.buy(buy_cmd(p.id), now=NOW)
    assert e.value.code == "SIM_INSUFFICIENT_CASH"


def test_43_invalid_command_quantity():
    with pytest.raises(SimulationDomainError):
        BuyCommand(
            portfolio_id="p", stock_code="x", stock_name="x", quantity=0,
            execution_price=Decimal("1"), source=PositionSource.MANUAL,
        )


def test_44_invalid_command_price():
    with pytest.raises(SimulationDomainError):
        SellCommand(portfolio_id="p", position_id="x", quantity=1, execution_price=Decimal("0"))


def test_45_sim2_does_not_import_scanner_production():
    root = Path(__file__).resolve().parents[1] / "app" / "simulation"
    texts = "\n".join(path.read_text(encoding="utf-8") for path in root.glob("sim2_*.py"))
    assert "app.backtest.scanner" not in texts
    assert "candidate_priority" not in texts


def test_46_idempotency_rejects_changed_buy_payload(env):
    _, ps, trading = env
    p = create_portfolio(ps)
    trading.buy(buy_cmd(p.id, client_request_id="buy-same"), now=NOW)
    with pytest.raises(SimulationTradingError) as e:
        trading.buy(buy_cmd(p.id, client_request_id="buy-same", quantity=9), now=NOW)
    assert error_code(e) == "SIM_DUPLICATE_REQUEST"


def test_47_idempotency_rejects_changed_sell_payload(env):
    _, ps, trading = env
    p = create_portfolio(ps)
    b = trading.buy(buy_cmd(p.id), now=NOW)
    trading.sell(sell_cmd(p.id, b.position.id, client_request_id="sell-same", quantity=2), now=NOW)
    with pytest.raises(SimulationTradingError) as e:
        trading.sell(sell_cmd(p.id, b.position.id, client_request_id="sell-same", quantity=3), now=NOW)
    assert error_code(e) == "SIM_DUPLICATE_REQUEST"


def test_48_v2_migration_preserves_existing_portfolio(tmp_path: Path):
    from app.simulation.sim1_store import SCHEMA

    db = tmp_path / "legacy_full.db"
    legacy_schema = SCHEMA.replace("    client_request_id TEXT,\n", "")
    conn = sqlite3.connect(db)
    conn.executescript(legacy_schema)
    conn.execute(
        """INSERT INTO simulation_portfolio
        (id,name,mode,initial_cash,cash_balance,realized_pnl,default_scanner_baseline_id,status,created_at,updated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?)""",
        ("p1", "legacy", "HISTORICAL", "1000", "1000", "0", BASELINE_ID, "ACTIVE", NOW.isoformat(), NOW.isoformat()),
    )
    conn.commit()
    conn.close()
    repo = SimulationRepository(db)
    repo.initialize()
    assert repo.get_portfolio("p1").name == "legacy"
    assert repo.schema_version() == 3
