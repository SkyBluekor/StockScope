from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from .sim1_enums import PortfolioStatus, PositionSource, PositionStatus, SimulationMode
from .sim1_models import (
    HUNDRED,
    PortfolioSummary,
    SimulationDomainError,
    SimulationPortfolio,
    SimulationPosition,
    ZERO,
    as_decimal,
    weighted_average_entry,
)
from .sim1_store import BaselineRegistry, SimulationRepository


class SimulationNotFoundError(LookupError):
    pass


class SimulationPortfolioService:
    def __init__(self, repository: SimulationRepository, baseline_registry: BaselineRegistry):
        self.repository = repository
        self.baseline_registry = baseline_registry

    def initialize(self) -> None:
        self.repository.initialize()

    def create_portfolio(
        self,
        *,
        name: str,
        initial_cash: Decimal | str | int,
        mode: SimulationMode = SimulationMode.HISTORICAL,
        scanner_baseline_id: str | None = None,
        now: datetime | None = None,
    ) -> SimulationPortfolio:
        baseline_id = scanner_baseline_id or self.baseline_registry.first_valid_id()
        if not baseline_id:
            raise SimulationDomainError("No frozen Scanner baseline is available")
        self.baseline_registry.require(baseline_id)
        cash = as_decimal(initial_cash, field="initial_cash", allow_zero=False)
        ts = now or datetime.now(timezone.utc)
        portfolio = SimulationPortfolio(
            id=str(uuid4()),
            name=name,
            mode=mode,
            initial_cash=cash,
            cash_balance=cash,
            realized_pnl=ZERO,
            default_scanner_baseline_id=baseline_id,
            status=PortfolioStatus.ACTIVE,
            created_at=ts,
            updated_at=ts,
        )
        self.repository.create_portfolio(portfolio)
        return portfolio

    def get_portfolio(self, portfolio_id: str) -> SimulationPortfolio:
        portfolio = self.repository.get_portfolio(portfolio_id)
        if portfolio is None:
            raise SimulationNotFoundError(f"Portfolio not found: {portfolio_id}")
        return portfolio

    def create_position_state(
        self,
        *,
        portfolio_id: str,
        stock_code: str,
        stock_name: str,
        market: str,
        source: PositionSource,
        quantity: int,
        average_entry_price: Decimal | str | int,
        current_price: Decimal | str | int | None = None,
        scanner_baseline_id: str | None = None,
        opened_at: datetime | None = None,
    ) -> SimulationPosition:
        """Persist an already-established position state.

        This is a SIM.1 domain/persistence primitive, not an execution command.
        SIM.2 will own BUY/SELL cash movement and trade lifecycle.
        """
        portfolio = self.get_portfolio(portfolio_id)
        baseline_id = scanner_baseline_id or portfolio.default_scanner_baseline_id
        self.baseline_registry.require(baseline_id)
        entry = as_decimal(average_entry_price, field="average_entry_price", allow_zero=False)
        current = entry if current_price is None else as_decimal(current_price, field="current_price", allow_zero=False)
        ts = opened_at or datetime.now(timezone.utc)
        position = SimulationPosition(
            id=str(uuid4()),
            portfolio_id=portfolio_id,
            stock_code=stock_code,
            stock_name=stock_name,
            market=market,
            source=source,
            status=PositionStatus.OPEN,
            quantity=quantity,
            average_entry_price=entry,
            current_price=current,
            realized_pnl=ZERO,
            scanner_baseline_id=baseline_id,
            opened_at=ts,
        )
        self.repository.create_position(position)
        return position

    def revalue_position(self, position_id: str, current_price: Decimal | str | int) -> SimulationPosition:
        position = self.repository.get_position(position_id)
        if position is None:
            raise SimulationNotFoundError(f"Position not found: {position_id}")
        updated = replace(
            position,
            current_price=as_decimal(current_price, field="current_price", allow_zero=False),
        )
        self.repository.save_position(updated)
        return updated

    @staticmethod
    def preview_additional_buy(
        position: SimulationPosition,
        *,
        added_quantity: int,
        added_price: Decimal | str | int,
    ) -> tuple[int, Decimal]:
        """Pure SIM.1 calculation only; does not mutate cash, order, trade or DB."""
        new_average = weighted_average_entry(
            position.quantity,
            position.average_entry_price,
            added_quantity,
            as_decimal(added_price, field="added_price", allow_zero=False),
        )
        return position.quantity + added_quantity, new_average

    @staticmethod
    def preview_remaining_quantity(position: SimulationPosition, sell_quantity: int) -> tuple[int, PositionStatus]:
        if isinstance(sell_quantity, bool) or not isinstance(sell_quantity, int) or sell_quantity <= 0:
            raise SimulationDomainError("sell_quantity must be a positive integer")
        if sell_quantity > position.quantity:
            raise SimulationDomainError("SELL quantity exceeds owned quantity")
        remaining = position.quantity - sell_quantity
        return remaining, PositionStatus.CLOSED if remaining == 0 else PositionStatus.OPEN

    def list_positions(self, portfolio_id: str, *, status: PositionStatus | None = None) -> list[SimulationPosition]:
        self.get_portfolio(portfolio_id)
        return self.repository.list_positions(portfolio_id, status=status)

    def summary(self, portfolio_id: str) -> PortfolioSummary:
        portfolio = self.get_portfolio(portfolio_id)
        positions = self.repository.list_positions(portfolio_id, status=PositionStatus.OPEN)
        market_value = sum((p.market_value for p in positions), ZERO)
        unrealized = sum((p.unrealized_pnl for p in positions), ZERO)
        total_equity = portfolio.cash_balance + market_value
        total_return_pct = (
            (total_equity - portfolio.initial_cash) / portfolio.initial_cash * HUNDRED
            if portfolio.initial_cash != ZERO
            else ZERO
        )
        return PortfolioSummary(
            portfolio=portfolio,
            positions_market_value=market_value,
            unrealized_pnl=unrealized,
            total_equity=total_equity,
            total_return_pct=total_return_pct,
            open_position_count=len(positions),
        )


def default_paths(project_root: Path) -> tuple[Path, Path]:
    root = Path(project_root)
    return (
        root / "backend" / "runtime" / "simulation" / "simulation.db",
        root / "backend" / "runtime" / "baseline",
    )
