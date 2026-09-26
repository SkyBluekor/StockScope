from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

from .catalog import HoldingsCatalog
from .chart import HoldingsChartError, HoldingsChartService
from .domain import HoldingPosition, HoldingPositionEvent, MonitoredStock


class HoldingsPerformanceError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _decimal_text(value: Decimal | None) -> str | None:
    return None if value is None else format(value, "f")


@dataclass(frozen=True, slots=True)
class HoldingValuation:
    available: bool
    market_date: str | None
    price: Decimal | None
    source: str | None
    message: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "available": self.available,
            "market_date": self.market_date,
            "price": _decimal_text(self.price),
            "source": self.source,
            "message": self.message,
        }


@dataclass(frozen=True, slots=True)
class PositionPerformance:
    position_id: str
    account_id: str
    provider: str
    account_kind: str
    account_name: str | None
    quantity: Decimal
    average_price: Decimal | None
    cost_basis: Decimal | None
    market_value: Decimal | None
    unrealized_pnl: Decimal | None
    unrealized_return_pct: Decimal | None
    confirmed_realized_pnl: Decimal | None
    recorded_sell_count: int
    calculable_sell_count: int
    tracked_pnl: Decimal | None
    calculation_status: str
    calculation_message: str
    warnings: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "position_id": self.position_id,
            "account_id": self.account_id,
            "provider": self.provider,
            "account_kind": self.account_kind,
            "account_name": self.account_name,
            "quantity": _decimal_text(self.quantity),
            "average_price": _decimal_text(self.average_price),
            "cost_basis": _decimal_text(self.cost_basis),
            "market_value": _decimal_text(self.market_value),
            "unrealized_pnl": _decimal_text(self.unrealized_pnl),
            "unrealized_return_pct": _decimal_text(self.unrealized_return_pct),
            "confirmed_realized_pnl": _decimal_text(self.confirmed_realized_pnl),
            "recorded_sell_count": self.recorded_sell_count,
            "calculable_sell_count": self.calculable_sell_count,
            "tracked_pnl": _decimal_text(self.tracked_pnl),
            "calculation_status": self.calculation_status,
            "calculation_message": self.calculation_message,
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True, slots=True)
class HoldingPerformance:
    stock_id: str
    market: str
    ticker: str
    valuation: HoldingValuation
    positions: tuple[PositionPerformance, ...]
    aggregate: dict[str, Any]
    calculation_status: str
    warnings: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "stock_id": self.stock_id,
            "market": self.market,
            "ticker": self.ticker,
            "valuation": self.valuation.to_dict(),
            "positions": [position.to_dict() for position in self.positions],
            "aggregate": self.aggregate,
            "calculation_status": self.calculation_status,
            "warnings": list(self.warnings),
        }


class HoldingPerformanceService:
    # HOLD-PNL.1: read-only derived P&L over the current ledger.

    def __init__(
        self,
        catalog: HoldingsCatalog,
        *,
        market_store_db: Path | None = None,
    ) -> None:
        self.catalog = catalog
        self.chart = HoldingsChartService(market_store_db)

    def _valuation(self, stock: MonitoredStock) -> HoldingValuation:
        try:
            series = self.chart.load(
                market=stock.market,
                ticker=stock.ticker,
                chart_range="1m",
            )
        except HoldingsChartError as error:
            return HoldingValuation(
                available=False,
                market_date=None,
                price=None,
                source=None,
                message=error.message,
            )
        latest = series.bars[-1]
        return HoldingValuation(
            available=True,
            market_date=latest.date,
            price=Decimal(latest.close),
            source=series.source,
            message=None,
        )

    @staticmethod
    def _realized(
        events: list[HoldingPositionEvent],
    ) -> tuple[Decimal, int, int, list[str]]:
        realized = Decimal("0")
        sell_count = 0
        calculable_count = 0
        warnings: list[str] = []
        for event in events:
            if event.event_type != "SELL":
                continue
            sell_count += 1
            if (
                event.quantity_delta is None
                or event.unit_price is None
                or event.before_average_price is None
            ):
                warnings.append(
                    "일부 SELL 기록에 수량·가격·매도 직전 평균단가가 없어 실현손익에서 제외했습니다."
                )
                continue
            quantity = abs(event.quantity_delta)
            realized += quantity * (event.unit_price - event.before_average_price)
            calculable_count += 1
        return realized, sell_count, calculable_count, warnings

    @staticmethod
    def _coverage(
        position: HoldingPosition,
        events: list[HoldingPositionEvent],
        *,
        account_kind: str,
        sell_count: int,
        calculable_sell_count: int,
    ) -> tuple[str, str, list[str]]:
        warnings: list[str] = []
        kinds = [event.event_type for event in events]

        if position.current_cost_basis is None or position.current_cost_basis <= 0:
            return (
                "UNAVAILABLE",
                "현재 잔여 원가가 없어 손익을 계산할 수 없습니다.",
                warnings,
            )

        if sell_count != calculable_sell_count:
            return (
                "PARTIAL",
                "일부 매도 기록만 실현손익 계산에 사용할 수 있습니다.",
                warnings,
            )

        if account_kind == "BROKER" and not any(
            kind in {"OPENING_BALANCE", "BUY", "SELL"} for kind in kinds
        ):
            return (
                "VALUATION_ONLY",
                "증권사 잔고 관찰만 있어 현재 보유 평가는 가능하지만 과거 실현손익은 확인할 수 없습니다.",
                warnings,
            )

        if not events:
            return (
                "VALUATION_ONLY",
                "현재 Position은 있지만 거래 원장 이력이 없어 보유 평가만 제공합니다.",
                warnings,
            )

        if any(
            kind in {"CORRECTION", "BALANCE_OBSERVED", "RECONCILED"}
            for kind in kinds
        ):
            warnings.append(
                "보정 또는 잔고 대사 이력이 있어 전체 거래 성과가 아닌 확인된 기록 범위로 계산합니다."
            )
            return (
                "PARTIAL",
                "보정·잔고 대사 이력이 있어 확인된 기록 범위의 손익입니다.",
                warnings,
            )

        if kinds[0] == "OPENING_BALANCE":
            return (
                "COMPLETE_SINCE_TRACKING_START",
                "StockScope 추적 시작 이후 기록된 거래 기준으로 계산했습니다.",
                warnings,
            )

        if kinds[0] == "BUY":
            warnings.append(
                "첫 BUY의 과거 provenance를 자동으로 단정하지 않아 전체 이력으로 표현하지 않습니다."
            )
            return (
                "PARTIAL",
                "기록된 BUY/SELL 기준 손익이며 추적 시작 이전 이력은 포함되지 않을 수 있습니다.",
                warnings,
            )

        return (
            "PARTIAL",
            "원장 시작 상태를 완전히 확인할 수 없어 확인된 기록 범위로 계산합니다.",
            warnings,
        )

    def _position_performance(
        self,
        position: HoldingPosition,
        valuation: HoldingValuation,
    ) -> PositionPerformance:
        account = self.catalog.get_position_account(position.position_account_id)
        if account is None:
            raise HoldingsPerformanceError(
                "HOLD_PERFORMANCE_ACCOUNT_NOT_FOUND",
                "Position의 계좌 정보를 찾을 수 없습니다.",
            )

        events = self.catalog.list_position_events(position.id)
        realized, sell_count, calculable_sell_count, realized_warnings = self._realized(events)
        coverage_status, coverage_message, coverage_warnings = self._coverage(
            position,
            events,
            account_kind=account.account_kind,
            sell_count=sell_count,
            calculable_sell_count=calculable_sell_count,
        )

        market_value: Decimal | None = None
        unrealized_pnl: Decimal | None = None
        unrealized_return_pct: Decimal | None = None
        tracked_pnl: Decimal | None = None
        warnings = [*realized_warnings, *coverage_warnings]

        confirmed_realized_pnl: Decimal | None
        if coverage_status == "VALUATION_ONLY":
            confirmed_realized_pnl = None
        else:
            confirmed_realized_pnl = realized

        final_status = coverage_status
        final_message = coverage_message
        if not valuation.available or valuation.price is None:
            warnings.append(
                valuation.message
                or "최신 확정 종가가 없어 현재 평가손익을 계산할 수 없습니다."
            )
            final_status = "UNAVAILABLE"
            final_message = (
                "최신 확정 종가가 없어 현재 평가손익을 계산할 수 없습니다. "
                "확인 가능한 거래 실현손익은 별도로 유지합니다."
            )
        elif position.current_cost_basis is not None and position.current_cost_basis > 0:
            market_value = position.current_quantity * valuation.price
            unrealized_pnl = market_value - position.current_cost_basis
            unrealized_return_pct = (
                unrealized_pnl / position.current_cost_basis * Decimal("100")
            )
            if confirmed_realized_pnl is not None:
                tracked_pnl = unrealized_pnl + confirmed_realized_pnl

        return PositionPerformance(
            position_id=position.id,
            account_id=account.id,
            provider=account.provider,
            account_kind=account.account_kind,
            account_name=account.display_name,
            quantity=position.current_quantity,
            average_price=position.current_average_price,
            cost_basis=position.current_cost_basis,
            market_value=market_value,
            unrealized_pnl=unrealized_pnl,
            unrealized_return_pct=unrealized_return_pct,
            confirmed_realized_pnl=confirmed_realized_pnl,
            recorded_sell_count=sell_count,
            calculable_sell_count=calculable_sell_count,
            tracked_pnl=tracked_pnl,
            calculation_status=final_status,
            calculation_message=final_message,
            warnings=tuple(dict.fromkeys(warnings)),
        )

    @staticmethod
    def _aggregate(positions: list[PositionPerformance]) -> tuple[dict[str, Any], list[str]]:
        actual = [position for position in positions if position.account_kind != "VIRTUAL"]
        warnings: list[str] = []
        if not actual:
            return (
                {
                    "available": False,
                    "mode": "NO_ACTUAL_POSITION",
                    "position_count": 0,
                    "potential_overlap": False,
                },
                warnings,
            )

        kinds = {position.account_kind for position in actual}
        potential_overlap = "MANUAL" in kinds and "BROKER" in kinds
        if potential_overlap:
            warnings.append(
                "수동 보유와 증권사 보유가 함께 있어 같은 실제 보유의 중복 여부를 자동 판단하지 않았습니다."
            )

        def sum_optional(name: str) -> Decimal | None:
            values = [getattr(position, name) for position in actual]
            if any(value is None for value in values):
                return None
            return sum((value for value in values if value is not None), Decimal("0"))

        quantity = sum((position.quantity for position in actual), Decimal("0"))
        cost_basis = sum_optional("cost_basis")
        market_value = sum_optional("market_value")
        unrealized_pnl = sum_optional("unrealized_pnl")
        confirmed_realized_pnl = sum_optional("confirmed_realized_pnl")
        tracked_pnl = sum_optional("tracked_pnl")
        unrealized_return_pct = (
            unrealized_pnl / cost_basis * Decimal("100")
            if unrealized_pnl is not None and cost_basis is not None and cost_basis > 0
            else None
        )

        return (
            {
                "available": True,
                "mode": "SINGLE_POSITION" if len(actual) == 1 else "ACCOUNT_RECORD_SUM",
                "position_count": len(actual),
                "potential_overlap": potential_overlap,
                "quantity": _decimal_text(quantity),
                "cost_basis": _decimal_text(cost_basis),
                "market_value": _decimal_text(market_value),
                "unrealized_pnl": _decimal_text(unrealized_pnl),
                "unrealized_return_pct": _decimal_text(unrealized_return_pct),
                "confirmed_realized_pnl": _decimal_text(confirmed_realized_pnl),
                "tracked_pnl": _decimal_text(tracked_pnl),
            },
            warnings,
        )

    def calculate_with_valuation(
        self,
        stock_id: str,
        valuation: HoldingValuation,
    ) -> HoldingPerformance:
        stock = self.catalog.get_monitored_stock(stock_id)
        if stock is None:
            raise HoldingsPerformanceError(
                "HOLD_STOCK_NOT_FOUND",
                "등록된 종목을 찾을 수 없습니다.",
            )

        open_positions = self.catalog.list_positions(stock.id, status="OPEN")
        positions = [
            self._position_performance(position, valuation)
            for position in open_positions
        ]
        aggregate, aggregate_warnings = self._aggregate(positions)

        warnings = list(aggregate_warnings)
        for position in positions:
            warnings.extend(position.warnings)
        if not valuation.available and valuation.message:
            warnings.append(valuation.message)

        if not positions:
            status = "UNAVAILABLE"
        elif any(position.calculation_status == "UNAVAILABLE" for position in positions):
            status = "UNAVAILABLE"
        elif any(position.calculation_status == "PARTIAL" for position in positions):
            status = "PARTIAL"
        elif any(position.calculation_status == "VALUATION_ONLY" for position in positions):
            status = "VALUATION_ONLY"
        else:
            status = "COMPLETE_SINCE_TRACKING_START"

        return HoldingPerformance(
            stock_id=stock.id,
            market=stock.market,
            ticker=stock.ticker,
            valuation=valuation,
            positions=tuple(positions),
            aggregate=aggregate,
            calculation_status=status,
            warnings=tuple(dict.fromkeys(warnings)),
        )

    def calculate(self, stock_id: str) -> HoldingPerformance:
        stock = self.catalog.get_monitored_stock(stock_id)
        if stock is None:
            raise HoldingsPerformanceError(
                "HOLD_STOCK_NOT_FOUND",
                "등록된 종목을 찾을 수 없습니다.",
            )
        return self.calculate_with_valuation(
            stock_id,
            self._valuation(stock),
        )
