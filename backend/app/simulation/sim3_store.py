from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import uuid4

from .sim1_models import money_text
from .sim1_store import SimulationRepository, SimulationUnitOfWork
from .sim3_clock import DateStepRecord, PositionMarkState, PriceStatus, SessionStatus, SimulationSession


def _session(row) -> SimulationSession:
    return SimulationSession(
        id=row["id"], portfolio_id=row["portfolio_id"], start_date=date.fromisoformat(row["start_date"]),
        end_date=date.fromisoformat(row["end_date"]) if row["end_date"] else None,
        current_date=date.fromisoformat(row["current_date"]), status=SessionStatus(row["status"]),
        created_at=datetime.fromisoformat(row["created_at"]), updated_at=datetime.fromisoformat(row["updated_at"]),
    )


def _mark(row) -> PositionMarkState:
    return PositionMarkState(
        position_id=row["position_id"], session_id=row["session_id"], mark_date=date.fromisoformat(row["mark_date"]),
        source_bar_date=date.fromisoformat(row["source_bar_date"]) if row["source_bar_date"] else None,
        price_status=PriceStatus(row["price_status"]), valuation_stale=bool(row["valuation_stale"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
    )


def _step(row) -> DateStepRecord:
    return DateStepRecord(
        id=row["id"], session_id=row["session_id"], from_date=date.fromisoformat(row["from_date"]),
        to_date=date.fromisoformat(row["to_date"]), updated_positions=int(row["updated_positions"]),
        missing_positions=int(row["missing_positions"]), cash_balance=Decimal(row["cash_balance"]),
        positions_market_value=Decimal(row["positions_market_value"]), unrealized_pnl=Decimal(row["unrealized_pnl"]),
        realized_pnl=Decimal(row["realized_pnl"]), total_equity=Decimal(row["total_equity"]),
        created_at=datetime.fromisoformat(row["created_at"]),
    )


class SimulationPlaybackStore:
    def __init__(self, repository: SimulationRepository):
        self.repository = repository

    def active_session(self, portfolio_id: str) -> SimulationSession | None:
        with self.repository.connect() as conn:
            row = conn.execute(
                "SELECT * FROM simulation_session WHERE portfolio_id=? AND status='ACTIVE' ORDER BY created_at DESC LIMIT 1",
                (portfolio_id,),
            ).fetchone()
        return _session(row) if row else None

    def get_session(self, session_id: str) -> SimulationSession | None:
        with self.repository.connect() as conn:
            row = conn.execute("SELECT * FROM simulation_session WHERE id=?", (session_id,)).fetchone()
        return _session(row) if row else None

    def create_session(self, session: SimulationSession) -> None:
        with self.repository.connect() as conn:
            conn.execute(
                """INSERT INTO simulation_session
                (id,portfolio_id,start_date,end_date,current_date,status,created_at,updated_at)
                VALUES(?,?,?,?,?,?,?,?)""",
                (session.id, session.portfolio_id, session.start_date.isoformat(),
                 session.end_date.isoformat() if session.end_date else None, session.current_date.isoformat(),
                 session.status.value, session.created_at.isoformat(), session.updated_at.isoformat()),
            )

    def list_steps(self, session_id: str) -> list[DateStepRecord]:
        with self.repository.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM simulation_date_step WHERE session_id=? ORDER BY created_at,id", (session_id,)
            ).fetchall()
        return [_step(row) for row in rows]

    def get_mark(self, position_id: str) -> PositionMarkState | None:
        with self.repository.connect() as conn:
            row = conn.execute("SELECT * FROM simulation_position_mark_state WHERE position_id=?", (position_id,)).fetchone()
        return _mark(row) if row else None

    @staticmethod
    def save_session_uow(uow: SimulationUnitOfWork, session: SimulationSession) -> None:
        cursor = uow.conn.execute(
            "UPDATE simulation_session SET current_date=?,status=?,updated_at=? WHERE id=?",
            (session.current_date.isoformat(), session.status.value, session.updated_at.isoformat(), session.id),
        )
        if cursor.rowcount != 1:
            raise RuntimeError(f"Simulation session not found: {session.id}")

    @staticmethod
    def upsert_mark_uow(uow: SimulationUnitOfWork, mark: PositionMarkState) -> None:
        uow.conn.execute(
            """INSERT INTO simulation_position_mark_state
            (position_id,session_id,mark_date,source_bar_date,price_status,valuation_stale,updated_at)
            VALUES(?,?,?,?,?,?,?)
            ON CONFLICT(position_id) DO UPDATE SET
              session_id=excluded.session_id, mark_date=excluded.mark_date, source_bar_date=excluded.source_bar_date,
              price_status=excluded.price_status, valuation_stale=excluded.valuation_stale, updated_at=excluded.updated_at""",
            (mark.position_id, mark.session_id, mark.mark_date.isoformat(),
             mark.source_bar_date.isoformat() if mark.source_bar_date else None,
             mark.price_status.value, 1 if mark.valuation_stale else 0, mark.updated_at.isoformat()),
        )

    @staticmethod
    def insert_step_uow(uow: SimulationUnitOfWork, step: DateStepRecord) -> None:
        uow.conn.execute(
            """INSERT INTO simulation_date_step
            (id,session_id,from_date,to_date,updated_positions,missing_positions,cash_balance,
             positions_market_value,unrealized_pnl,realized_pnl,total_equity,created_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
            (step.id, step.session_id, step.from_date.isoformat(), step.to_date.isoformat(), step.updated_positions,
             step.missing_positions, money_text(step.cash_balance), money_text(step.positions_market_value),
             money_text(step.unrealized_pnl), money_text(step.realized_pnl), money_text(step.total_equity),
             step.created_at.isoformat()),
        )

    @staticmethod
    def new_step(**kwargs) -> DateStepRecord:
        return DateStepRecord(id=str(uuid4()), **kwargs)
