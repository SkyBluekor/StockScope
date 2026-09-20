from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

from .sim1_enums import OrderSide, OrderStatus, PortfolioStatus, PositionSource, PositionStatus
from .sim1_models import (
    ZERO,
    SimulationDomainError,
    SimulationOrder,
    SimulationPortfolio,
    SimulationPosition,
    SimulationTrade,
    weighted_average_entry,
)
from .sim1_store import BaselineRegistry, SimulationRepository, SimulationUnitOfWork
from .sim2_commands import BuyCommand, SellCommand


class SimulationTradingError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True, slots=True)
class BuyResult:
    order: SimulationOrder
    trade: SimulationTrade
    position: SimulationPosition
    portfolio: SimulationPortfolio
    idempotent_replay: bool = False


@dataclass(frozen=True, slots=True)
class SellResult:
    order: SimulationOrder
    trade: SimulationTrade
    position: SimulationPosition
    portfolio: SimulationPortfolio
    realized_pnl: Decimal
    idempotent_replay: bool = False


class SimulationTradingService:
    def __init__(self, repository: SimulationRepository, baseline_registry: BaselineRegistry):
        self.repository = repository
        self.baseline_registry = baseline_registry

    def initialize(self) -> None:
        self.repository.initialize()

    def buy(self, command: BuyCommand, *, now: datetime | None = None) -> BuyResult:
        ts = now or datetime.now(timezone.utc)
        if command.source == PositionSource.SCANNER and not command.scanner_baseline_id:
            raise SimulationTradingError("SIM_BASELINE_REQUIRED", "SCANNER BUY requires scanner_baseline_id")
        if command.scanner_baseline_id:
            self._require_baseline(command.scanner_baseline_id)

        with self.repository.transaction() as tx:
            replay = self._idempotent_buy(tx, command)
            if replay is not None:
                return replay

            portfolio = tx.get_portfolio(command.portfolio_id)
            if portfolio is None:
                raise SimulationTradingError("SIM_PORTFOLIO_NOT_FOUND", "Portfolio not found")
            self._require_active(portfolio)

            baseline_id = command.scanner_baseline_id or portfolio.default_scanner_baseline_id
            self._require_baseline(baseline_id)

            gross = command.execution_price * command.quantity
            if portfolio.cash_balance < gross:
                raise SimulationTradingError("SIM_INSUFFICIENT_CASH", "Insufficient cash balance")

            existing = tx.find_open_position_by_stock(portfolio.id, command.stock_code)
            if existing is None:
                position = SimulationPosition(
                    id=str(uuid4()),
                    portfolio_id=portfolio.id,
                    stock_code=command.stock_code,
                    stock_name=command.stock_name,
                    market=command.market,
                    source=command.source,
                    status=PositionStatus.OPEN,
                    quantity=command.quantity,
                    average_entry_price=command.execution_price,
                    current_price=command.execution_price,
                    realized_pnl=ZERO,
                    scanner_baseline_id=baseline_id,
                    opened_at=ts,
                )
                tx.create_position(position)
            else:
                avg = weighted_average_entry(
                    existing.quantity,
                    existing.average_entry_price,
                    command.quantity,
                    command.execution_price,
                )
                position = replace(
                    existing,
                    quantity=existing.quantity + command.quantity,
                    average_entry_price=avg,
                    current_price=command.execution_price,
                )
                tx.save_position(position)

            order = SimulationOrder(
                id=str(uuid4()),
                portfolio_id=portfolio.id,
                position_id=position.id,
                stock_code=position.stock_code,
                stock_name=position.stock_name,
                side=OrderSide.BUY,
                order_type=command.order_type,
                quantity=command.quantity,
                requested_price=command.execution_price if command.order_type.value == "LIMIT" else None,
                status=OrderStatus.PENDING,
                requested_at=ts,
            )
            tx.create_order(order, client_request_id=command.client_request_id)

            trade = SimulationTrade(
                id=str(uuid4()),
                portfolio_id=portfolio.id,
                order_id=order.id,
                position_id=position.id,
                stock_code=position.stock_code,
                side=OrderSide.BUY,
                quantity=command.quantity,
                price=command.execution_price,
                gross_amount=gross,
                fee=ZERO,
                tax=ZERO,
                slippage=ZERO,
                net_amount=gross,
                realized_pnl=ZERO,
                executed_at=ts,
            )
            tx.create_trade(trade)

            portfolio = replace(
                portfolio,
                cash_balance=portfolio.cash_balance - gross,
                updated_at=ts,
            )
            tx.save_portfolio(portfolio)
            order = tx.update_order_status(order.id, OrderStatus.FILLED, filled_at=ts)
            return BuyResult(order=order, trade=trade, position=position, portfolio=portfolio)

    def sell(self, command: SellCommand, *, now: datetime | None = None) -> SellResult:
        ts = now or datetime.now(timezone.utc)
        with self.repository.transaction() as tx:
            replay = self._idempotent_sell(tx, command)
            if replay is not None:
                return replay

            portfolio = tx.get_portfolio(command.portfolio_id)
            if portfolio is None:
                raise SimulationTradingError("SIM_PORTFOLIO_NOT_FOUND", "Portfolio not found")
            self._require_active(portfolio)

            position = tx.get_position(command.position_id)
            if position is None or position.portfolio_id != portfolio.id:
                raise SimulationTradingError("SIM_POSITION_NOT_FOUND", "Position not found in portfolio")
            if position.status != PositionStatus.OPEN:
                raise SimulationTradingError("SIM_POSITION_CLOSED", "Position is already closed")
            if command.quantity > position.quantity:
                raise SimulationTradingError("SIM_INSUFFICIENT_QUANTITY", "SELL quantity exceeds owned quantity")

            gross = command.execution_price * command.quantity
            realized = (command.execution_price - position.average_entry_price) * command.quantity
            remaining = position.quantity - command.quantity
            new_status = PositionStatus.CLOSED if remaining == 0 else PositionStatus.OPEN
            updated_position = replace(
                position,
                quantity=remaining,
                status=new_status,
                current_price=command.execution_price,
                realized_pnl=position.realized_pnl + realized,
                closed_at=ts if remaining == 0 else None,
            )

            order = SimulationOrder(
                id=str(uuid4()),
                portfolio_id=portfolio.id,
                position_id=position.id,
                stock_code=position.stock_code,
                stock_name=position.stock_name,
                side=OrderSide.SELL,
                order_type=command.order_type,
                quantity=command.quantity,
                requested_price=command.execution_price if command.order_type.value == "LIMIT" else None,
                status=OrderStatus.PENDING,
                requested_at=ts,
            )
            tx.create_order(order, client_request_id=command.client_request_id)

            trade = SimulationTrade(
                id=str(uuid4()),
                portfolio_id=portfolio.id,
                order_id=order.id,
                position_id=position.id,
                stock_code=position.stock_code,
                side=OrderSide.SELL,
                quantity=command.quantity,
                price=command.execution_price,
                gross_amount=gross,
                fee=ZERO,
                tax=ZERO,
                slippage=ZERO,
                net_amount=gross,
                realized_pnl=realized,
                executed_at=ts,
            )
            tx.create_trade(trade)
            tx.save_position(updated_position)
            portfolio = replace(
                portfolio,
                cash_balance=portfolio.cash_balance + gross,
                realized_pnl=portfolio.realized_pnl + realized,
                updated_at=ts,
            )
            tx.save_portfolio(portfolio)
            order = tx.update_order_status(order.id, OrderStatus.FILLED, filled_at=ts)
            return SellResult(
                order=order,
                trade=trade,
                position=updated_position,
                portfolio=portfolio,
                realized_pnl=realized,
            )

    def _require_baseline(self, baseline_id: str) -> None:
        try:
            self.baseline_registry.require(baseline_id)
        except SimulationDomainError as exc:
            raise SimulationTradingError("SIM_BASELINE_INVALID", str(exc)) from exc

    @staticmethod
    def _require_active(portfolio: SimulationPortfolio) -> None:
        if portfolio.status != PortfolioStatus.ACTIVE:
            raise SimulationTradingError("SIM_PORTFOLIO_INACTIVE", "Portfolio is not active")

    def _idempotent_buy(self, tx: SimulationUnitOfWork, command: BuyCommand) -> BuyResult | None:
        if not command.client_request_id:
            return None
        order = tx.find_order_by_request_id(command.portfolio_id, command.client_request_id)
        if order is None:
            return None
        if order.side != OrderSide.BUY:
            raise SimulationTradingError("SIM_DUPLICATE_REQUEST", "client_request_id already belongs to another command")
        trade = tx.get_trade_by_order(order.id)
        position = tx.get_position(order.position_id or "")
        portfolio = tx.get_portfolio(command.portfolio_id)
        if order.status != OrderStatus.FILLED or trade is None or position is None or portfolio is None:
            raise SimulationTradingError("SIM_DUPLICATE_REQUEST", "Existing request is not a completed BUY")
        if (
            order.stock_code != command.stock_code
            or order.quantity != command.quantity
            or order.order_type != command.order_type
            or trade.price != command.execution_price
        ):
            raise SimulationTradingError("SIM_DUPLICATE_REQUEST", "client_request_id was reused with different BUY parameters")
        return BuyResult(order=order, trade=trade, position=position, portfolio=portfolio, idempotent_replay=True)

    def _idempotent_sell(self, tx: SimulationUnitOfWork, command: SellCommand) -> SellResult | None:
        if not command.client_request_id:
            return None
        order = tx.find_order_by_request_id(command.portfolio_id, command.client_request_id)
        if order is None:
            return None
        if order.side != OrderSide.SELL:
            raise SimulationTradingError("SIM_DUPLICATE_REQUEST", "client_request_id already belongs to another command")
        trade = tx.get_trade_by_order(order.id)
        position = tx.get_position(order.position_id or "")
        portfolio = tx.get_portfolio(command.portfolio_id)
        if order.status != OrderStatus.FILLED or trade is None or position is None or portfolio is None:
            raise SimulationTradingError("SIM_DUPLICATE_REQUEST", "Existing request is not a completed SELL")
        if (
            order.position_id != command.position_id
            or order.quantity != command.quantity
            or order.order_type != command.order_type
            or trade.price != command.execution_price
        ):
            raise SimulationTradingError("SIM_DUPLICATE_REQUEST", "client_request_id was reused with different SELL parameters")
        return SellResult(
            order=order,
            trade=trade,
            position=position,
            portfolio=portfolio,
            realized_pnl=trade.realized_pnl,
            idempotent_replay=True,
        )
