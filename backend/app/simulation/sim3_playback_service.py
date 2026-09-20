from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import uuid4

from .sim1_enums import PositionStatus, SimulationMode
from .sim1_models import HUNDRED, ZERO, PortfolioSummary, SimulationPosition
from .sim1_service import SimulationPortfolioService
from .sim1_store import SimulationRepository
from .sim3_clock import DateStepRecord, PositionMarkState, PriceStatus, SessionStatus, SimulationSession
from .sim3_market_provider import HistoricalMarketBar, SimulationMarketDataProvider
from .sim3_store import SimulationPlaybackStore


class SimulationPlaybackError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True, slots=True)
class PositionPlaybackResult:
    position_id: str
    stock_code: str
    previous_price: Decimal
    current_price: Decimal
    price_status: PriceStatus
    valuation_stale: bool
    bar: HistoricalMarketBar | None


@dataclass(frozen=True, slots=True)
class PlaybackResult:
    session: SimulationSession
    previous_date: date
    current_date: date
    positions: tuple[PositionPlaybackResult, ...]
    summary: PortfolioSummary
    updated_positions: int
    missing_positions: int


class MarketPlaybackService:
    def __init__(
        self,
        repository: SimulationRepository,
        portfolio_service: SimulationPortfolioService,
        market_provider: SimulationMarketDataProvider,
    ):
        self.repository = repository
        self.portfolio_service = portfolio_service
        self.market_provider = market_provider
        self.store = SimulationPlaybackStore(repository)

    def initialize(self) -> None:
        self.repository.initialize()

    def _portfolio_for_history(self, portfolio_id: str):
        portfolio = self.repository.get_portfolio(portfolio_id)
        if portfolio is None:
            raise SimulationPlaybackError("SIM_PORTFOLIO_NOT_FOUND", f"Portfolio not found: {portfolio_id}")
        if portfolio.mode != SimulationMode.HISTORICAL:
            raise SimulationPlaybackError(
                "SIM_INVALID_MODE_FOR_DATE_ENGINE",
                f"Portfolio mode {portfolio.mode.value} does not support HistoricalDateEngine",
            )
        return portfolio

    def create_session(
        self,
        portfolio_id: str,
        *,
        start_date: date,
        end_date: date | None = None,
        now: datetime | None = None,
    ) -> SimulationSession:
        self._portfolio_for_history(portfolio_id)
        if end_date is not None and end_date < start_date:
            raise SimulationPlaybackError("SIM_INVALID_DATE_RANGE", "end_date is before start_date")
        if not self.market_provider.has_trading_day(start_date):
            raise SimulationPlaybackError("SIM_INVALID_TRADING_DATE", f"No complete market day: {start_date}")
        if end_date is not None and not self.market_provider.has_trading_day(end_date):
            raise SimulationPlaybackError("SIM_INVALID_TRADING_DATE", f"No complete market day: {end_date}")
        if self.store.active_session(portfolio_id) is not None:
            raise SimulationPlaybackError("SIM_SESSION_ALREADY_ACTIVE", "Portfolio already has an ACTIVE session")
        ts = now or datetime.now(timezone.utc)
        session = SimulationSession(
            id=str(uuid4()),
            portfolio_id=portfolio_id,
            start_date=start_date,
            end_date=end_date,
            current_date=start_date,
            status=SessionStatus.ACTIVE,
            created_at=ts,
            updated_at=ts,
        )
        self.store.create_session(session)
        # Initial mark does not create a date-step: there was no movement yet.
        self._mark_current_date(session, start_date, ts, write_step=False, from_date=start_date)
        return self.store.get_session(session.id) or session

    def get_active_session(self, portfolio_id: str) -> SimulationSession:
        self._portfolio_for_history(portfolio_id)
        session = self.store.active_session(portfolio_id)
        if session is None:
            raise SimulationPlaybackError("SIM_SESSION_NOT_FOUND", "No ACTIVE historical session")
        return session

    def next_day(self, portfolio_id: str, *, now: datetime | None = None) -> PlaybackResult:
        session = self.get_active_session(portfolio_id)
        next_day = self.market_provider.next_trading_day(session.current_date)
        if next_day is None:
            raise SimulationPlaybackError("SIM_END_OF_MARKET_DATA", "No later complete trading day is available")
        if session.end_date is not None and next_day > session.end_date:
            raise SimulationPlaybackError("SIM_END_OF_RANGE", "Session end_date reached")
        return self._mark_current_date(session, next_day, now or datetime.now(timezone.utc), write_step=True, from_date=session.current_date)

    def previous_day(self, portfolio_id: str, *, now: datetime | None = None) -> PlaybackResult:
        session = self.get_active_session(portfolio_id)
        if self.repository.count_trades(portfolio_id) > 0:
            raise SimulationPlaybackError(
                "SIM_BACKWARD_AFTER_TRADE_NOT_ALLOWED",
                "Backward state movement is disabled after a trade exists",
            )
        previous = self.market_provider.previous_trading_day(session.current_date)
        if previous is None:
            raise SimulationPlaybackError("SIM_START_OF_RANGE", "No earlier complete trading day is available")
        if previous < session.start_date:
            raise SimulationPlaybackError("SIM_START_OF_RANGE", "Session start_date reached")
        return self._mark_current_date(session, previous, now or datetime.now(timezone.utc), write_step=True, from_date=session.current_date)

    def advance(self, portfolio_id: str, trading_days: int, *, now: datetime | None = None) -> list[PlaybackResult]:
        if isinstance(trading_days, bool) or not isinstance(trading_days, int) or trading_days <= 0:
            raise SimulationPlaybackError("SIM_INVALID_ADVANCE_DAYS", "trading_days must be a positive integer")
        results: list[PlaybackResult] = []
        for _ in range(trading_days):
            results.append(self.next_day(portfolio_id, now=now))
        return results

    def move_to(self, portfolio_id: str, target_date: date, *, now: datetime | None = None) -> PlaybackResult:
        session = self.get_active_session(portfolio_id)
        if not self.market_provider.has_trading_day(target_date):
            raise SimulationPlaybackError("SIM_INVALID_TRADING_DATE", f"No complete market day: {target_date}")
        if target_date < session.current_date and self.repository.count_trades(portfolio_id) > 0:
            raise SimulationPlaybackError("SIM_BACKWARD_AFTER_TRADE_NOT_ALLOWED", "Backward movement after trade is disabled")
        if target_date < session.start_date:
            raise SimulationPlaybackError("SIM_START_OF_RANGE", "target_date is before start_date")
        if session.end_date is not None and target_date > session.end_date:
            raise SimulationPlaybackError("SIM_END_OF_RANGE", "target_date is after end_date")
        return self._mark_current_date(session, target_date, now or datetime.now(timezone.utc), write_step=True, from_date=session.current_date)

    def _mark_current_date(
        self,
        session: SimulationSession,
        target_date: date,
        now: datetime,
        *,
        write_step: bool,
        from_date: date,
    ) -> PlaybackResult:
        portfolio = self._portfolio_for_history(session.portfolio_id)
        positions = self.repository.list_positions(session.portfolio_id, status=PositionStatus.OPEN)

        prepared: list[tuple[SimulationPosition, SimulationPosition, HistoricalMarketBar | None, PriceStatus]] = []
        updated_count = 0
        missing_count = 0
        for position in positions:
            bar = self.market_provider.get_bar(position.market, position.stock_code, target_date)
            if bar is None:
                prepared.append((position, position, None, PriceStatus.STALE))
                missing_count += 1
            else:
                updated = replace(position, current_price=bar.close)
                prepared.append((position, updated, bar, PriceStatus.FRESH))
                updated_count += 1

        market_value = sum((updated.market_value for _, updated, _, _ in prepared), ZERO)
        unrealized = sum((updated.unrealized_pnl for _, updated, _, _ in prepared), ZERO)
        total_equity = portfolio.cash_balance + market_value
        total_return_pct = (
            (total_equity - portfolio.initial_cash) / portfolio.initial_cash * HUNDRED
            if portfolio.initial_cash != ZERO else ZERO
        )
        summary = PortfolioSummary(
            portfolio=portfolio,
            positions_market_value=market_value,
            unrealized_pnl=unrealized,
            total_equity=total_equity,
            total_return_pct=total_return_pct,
            open_position_count=len(prepared),
        )
        updated_session = replace(session, current_date=target_date, updated_at=now)
        step = None
        if write_step:
            step = SimulationPlaybackStore.new_step(
                session_id=session.id,
                from_date=from_date,
                to_date=target_date,
                updated_positions=updated_count,
                missing_positions=missing_count,
                cash_balance=portfolio.cash_balance,
                positions_market_value=market_value,
                unrealized_pnl=unrealized,
                realized_pnl=portfolio.realized_pnl,
                total_equity=total_equity,
                created_at=now,
            )

        results: list[PositionPlaybackResult] = []
        with self.repository.transaction() as uow:
            row = uow.conn.execute('SELECT "current_date" AS current_date FROM simulation_session WHERE id=?', (session.id,)).fetchone()
            if row is None or date.fromisoformat(row["current_date"]) != session.current_date:
                raise SimulationPlaybackError("SIM_SESSION_CONFLICT", "Session date changed during playback")
            for old, updated, bar, price_status in prepared:
                if bar is not None:
                    uow.save_position(updated)
                mark = PositionMarkState(
                    position_id=old.id,
                    session_id=session.id,
                    mark_date=target_date,
                    source_bar_date=bar.trading_date if bar else None,
                    price_status=price_status,
                    valuation_stale=bar is None,
                    updated_at=now,
                )
                SimulationPlaybackStore.upsert_mark_uow(uow, mark)
                results.append(
                    PositionPlaybackResult(
                        position_id=old.id,
                        stock_code=old.stock_code,
                        previous_price=old.current_price,
                        current_price=updated.current_price,
                        price_status=price_status,
                        valuation_stale=bar is None,
                        bar=bar,
                    )
                )
            SimulationPlaybackStore.save_session_uow(uow, updated_session)
            if step is not None:
                SimulationPlaybackStore.insert_step_uow(uow, step)

        return PlaybackResult(
            session=updated_session,
            previous_date=from_date,
            current_date=target_date,
            positions=tuple(results),
            summary=summary,
            updated_positions=updated_count,
            missing_positions=missing_count,
        )
