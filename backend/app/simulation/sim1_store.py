from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Iterable, Iterator

from .sim1_enums import (
    OrderSide,
    OrderStatus,
    OrderType,
    PortfolioStatus,
    PositionSource,
    PositionStatus,
    SimulationMode,
)
from .sim1_models import (
    SimulationDomainError,
    SimulationOrder,
    SimulationPortfolio,
    SimulationPosition,
    SimulationTrade,
    money_text,
)


class SimulationPersistenceError(RuntimeError):
    pass


class BaselineRegistry:
    def __init__(self, baseline_dir: Path):
        self.baseline_dir = Path(baseline_dir)

    def manifests(self) -> list[dict]:
        if not self.baseline_dir.is_dir():
            return []
        result: list[dict] = []
        for path in sorted(self.baseline_dir.glob("scanner-production-baseline_*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if isinstance(payload, dict) and payload.get("baseline_id"):
                result.append(payload)
        return result

    def require(self, baseline_id: str) -> dict:
        for payload in self.manifests():
            if payload.get("baseline_id") == baseline_id:
                return payload
        raise SimulationDomainError(f"Unknown scanner_baseline_id: {baseline_id}")

    def first_valid_id(self) -> str | None:
        manifests = self.manifests()
        return str(manifests[0]["baseline_id"]) if manifests else None


CURRENT_SCHEMA_VERSION = 3

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS simulation_schema_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS simulation_portfolio (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    mode TEXT NOT NULL,
    initial_cash TEXT NOT NULL,
    cash_balance TEXT NOT NULL,
    realized_pnl TEXT NOT NULL,
    default_scanner_baseline_id TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS simulation_position (
    id TEXT PRIMARY KEY,
    portfolio_id TEXT NOT NULL,
    stock_code TEXT NOT NULL,
    stock_name TEXT NOT NULL,
    market TEXT NOT NULL,
    source TEXT NOT NULL,
    status TEXT NOT NULL,
    quantity INTEGER NOT NULL CHECK(quantity >= 0),
    average_entry_price TEXT NOT NULL,
    current_price TEXT NOT NULL,
    realized_pnl TEXT NOT NULL,
    scanner_baseline_id TEXT NOT NULL,
    opened_at TEXT NOT NULL,
    closed_at TEXT,
    FOREIGN KEY(portfolio_id) REFERENCES simulation_portfolio(id) ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_sim_position_portfolio
ON simulation_position(portfolio_id, status);

CREATE TABLE IF NOT EXISTS simulation_order (
    id TEXT PRIMARY KEY,
    portfolio_id TEXT NOT NULL,
    position_id TEXT,
    stock_code TEXT NOT NULL,
    stock_name TEXT NOT NULL,
    side TEXT NOT NULL,
    order_type TEXT NOT NULL,
    quantity INTEGER NOT NULL CHECK(quantity > 0),
    requested_price TEXT,
    status TEXT NOT NULL,
    requested_at TEXT NOT NULL,
    filled_at TEXT,
    client_request_id TEXT,
    FOREIGN KEY(portfolio_id) REFERENCES simulation_portfolio(id) ON DELETE RESTRICT,
    FOREIGN KEY(position_id) REFERENCES simulation_position(id) ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS simulation_trade (
    id TEXT PRIMARY KEY,
    portfolio_id TEXT NOT NULL,
    order_id TEXT NOT NULL,
    position_id TEXT NOT NULL,
    stock_code TEXT NOT NULL,
    side TEXT NOT NULL,
    quantity INTEGER NOT NULL CHECK(quantity > 0),
    price TEXT NOT NULL,
    gross_amount TEXT NOT NULL,
    fee TEXT NOT NULL,
    tax TEXT NOT NULL,
    slippage TEXT NOT NULL,
    net_amount TEXT NOT NULL,
    realized_pnl TEXT NOT NULL,
    executed_at TEXT NOT NULL,
    FOREIGN KEY(portfolio_id) REFERENCES simulation_portfolio(id) ON DELETE RESTRICT,
    FOREIGN KEY(order_id) REFERENCES simulation_order(id) ON DELETE RESTRICT,
    FOREIGN KEY(position_id) REFERENCES simulation_position(id) ON DELETE RESTRICT
);


CREATE TABLE IF NOT EXISTS simulation_session (
    id TEXT PRIMARY KEY,
    portfolio_id TEXT NOT NULL,
    start_date TEXT NOT NULL,
    end_date TEXT,
    current_date TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(portfolio_id) REFERENCES simulation_portfolio(id) ON DELETE RESTRICT
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_sim_session_one_active
ON simulation_session(portfolio_id) WHERE status = 'ACTIVE';

CREATE TABLE IF NOT EXISTS simulation_date_step (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    from_date TEXT NOT NULL,
    to_date TEXT NOT NULL,
    updated_positions INTEGER NOT NULL,
    missing_positions INTEGER NOT NULL,
    cash_balance TEXT NOT NULL,
    positions_market_value TEXT NOT NULL,
    unrealized_pnl TEXT NOT NULL,
    realized_pnl TEXT NOT NULL,
    total_equity TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(session_id) REFERENCES simulation_session(id) ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_sim_date_step_session
ON simulation_date_step(session_id, to_date);

CREATE TABLE IF NOT EXISTS simulation_position_mark_state (
    position_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    mark_date TEXT NOT NULL,
    source_bar_date TEXT,
    price_status TEXT NOT NULL,
    valuation_stale INTEGER NOT NULL CHECK(valuation_stale IN (0,1)),
    updated_at TEXT NOT NULL,
    FOREIGN KEY(position_id) REFERENCES simulation_position(id) ON DELETE RESTRICT,
    FOREIGN KEY(session_id) REFERENCES simulation_session(id) ON DELETE RESTRICT
);

CREATE TRIGGER IF NOT EXISTS trg_simulation_trade_no_update
BEFORE UPDATE ON simulation_trade
BEGIN
    SELECT RAISE(ABORT, 'SimulationTrade is immutable');
END;

CREATE TRIGGER IF NOT EXISTS trg_simulation_trade_no_delete
BEFORE DELETE ON simulation_trade
BEGIN
    SELECT RAISE(ABORT, 'SimulationTrade is immutable');
END;
"""


def _dt(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def _dec(value: str) -> Decimal:
    return Decimal(value)


def _portfolio_from_row(row: sqlite3.Row) -> SimulationPortfolio:
    return SimulationPortfolio(
        id=row["id"],
        name=row["name"],
        mode=SimulationMode(row["mode"]),
        initial_cash=_dec(row["initial_cash"]),
        cash_balance=_dec(row["cash_balance"]),
        realized_pnl=_dec(row["realized_pnl"]),
        default_scanner_baseline_id=row["default_scanner_baseline_id"],
        status=PortfolioStatus(row["status"]),
        created_at=_dt(row["created_at"]),
        updated_at=_dt(row["updated_at"]),
    )


def _position_from_row(row: sqlite3.Row) -> SimulationPosition:
    return SimulationPosition(
        id=row["id"],
        portfolio_id=row["portfolio_id"],
        stock_code=row["stock_code"],
        stock_name=row["stock_name"],
        market=row["market"],
        source=PositionSource(row["source"]),
        status=PositionStatus(row["status"]),
        quantity=int(row["quantity"]),
        average_entry_price=_dec(row["average_entry_price"]),
        current_price=_dec(row["current_price"]),
        realized_pnl=_dec(row["realized_pnl"]),
        scanner_baseline_id=row["scanner_baseline_id"],
        opened_at=_dt(row["opened_at"]),
        closed_at=_dt(row["closed_at"]),
    )


def _order_from_row(row: sqlite3.Row) -> SimulationOrder:
    return SimulationOrder(
        id=row["id"],
        portfolio_id=row["portfolio_id"],
        position_id=row["position_id"],
        stock_code=row["stock_code"],
        stock_name=row["stock_name"],
        side=OrderSide(row["side"]),
        order_type=OrderType(row["order_type"]),
        quantity=int(row["quantity"]),
        requested_price=_dec(row["requested_price"]) if row["requested_price"] is not None else None,
        status=OrderStatus(row["status"]),
        requested_at=_dt(row["requested_at"]),
        filled_at=_dt(row["filled_at"]),
    )


def _trade_from_row(row: sqlite3.Row) -> SimulationTrade:
    return SimulationTrade(
        id=row["id"],
        portfolio_id=row["portfolio_id"],
        order_id=row["order_id"],
        position_id=row["position_id"],
        stock_code=row["stock_code"],
        side=OrderSide(row["side"]),
        quantity=int(row["quantity"]),
        price=_dec(row["price"]),
        gross_amount=_dec(row["gross_amount"]),
        fee=_dec(row["fee"]),
        tax=_dec(row["tax"]),
        slippage=_dec(row["slippage"]),
        net_amount=_dec(row["net_amount"]),
        realized_pnl=_dec(row["realized_pnl"]),
        executed_at=_dt(row["executed_at"]),
    )


class SimulationUnitOfWork:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def get_portfolio(self, portfolio_id: str) -> SimulationPortfolio | None:
        row = self.conn.execute("SELECT * FROM simulation_portfolio WHERE id=?", (portfolio_id,)).fetchone()
        return _portfolio_from_row(row) if row else None

    def save_portfolio(self, portfolio: SimulationPortfolio) -> None:
        cursor = self.conn.execute(
            """UPDATE simulation_portfolio SET cash_balance=?, realized_pnl=?, status=?, updated_at=? WHERE id=?""",
            (
                money_text(portfolio.cash_balance),
                money_text(portfolio.realized_pnl),
                portfolio.status.value,
                portfolio.updated_at.isoformat(),
                portfolio.id,
            ),
        )
        if cursor.rowcount != 1:
            raise SimulationPersistenceError(f"Portfolio not found: {portfolio.id}")

    def get_position(self, position_id: str) -> SimulationPosition | None:
        row = self.conn.execute("SELECT * FROM simulation_position WHERE id=?", (position_id,)).fetchone()
        return _position_from_row(row) if row else None

    def find_open_position_by_stock(self, portfolio_id: str, stock_code: str) -> SimulationPosition | None:
        rows = self.conn.execute(
            """SELECT * FROM simulation_position
               WHERE portfolio_id=? AND stock_code=? AND status=?
               ORDER BY opened_at, id""",
            (portfolio_id, stock_code, PositionStatus.OPEN.value),
        ).fetchall()
        if len(rows) > 1:
            raise SimulationPersistenceError(
                f"Multiple OPEN positions for portfolio={portfolio_id}, stock={stock_code}"
            )
        return _position_from_row(rows[0]) if rows else None

    def create_position(self, position: SimulationPosition) -> None:
        self.conn.execute(
            """INSERT INTO simulation_position
            (id,portfolio_id,stock_code,stock_name,market,source,status,quantity,average_entry_price,current_price,realized_pnl,scanner_baseline_id,opened_at,closed_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                position.id, position.portfolio_id, position.stock_code, position.stock_name,
                position.market, position.source.value, position.status.value, position.quantity,
                money_text(position.average_entry_price), money_text(position.current_price),
                money_text(position.realized_pnl), position.scanner_baseline_id,
                position.opened_at.isoformat(), position.closed_at.isoformat() if position.closed_at else None,
            ),
        )

    def save_position(self, position: SimulationPosition) -> None:
        cursor = self.conn.execute(
            """UPDATE simulation_position SET status=?, quantity=?, average_entry_price=?, current_price=?,
            realized_pnl=?, closed_at=? WHERE id=? AND portfolio_id=?""",
            (
                position.status.value, position.quantity, money_text(position.average_entry_price),
                money_text(position.current_price), money_text(position.realized_pnl),
                position.closed_at.isoformat() if position.closed_at else None,
                position.id, position.portfolio_id,
            ),
        )
        if cursor.rowcount != 1:
            raise SimulationPersistenceError(f"Position not found: {position.id}")

    def create_order(self, order: SimulationOrder, *, client_request_id: str | None = None) -> None:
        self.conn.execute(
            """INSERT INTO simulation_order
            (id,portfolio_id,position_id,stock_code,stock_name,side,order_type,quantity,requested_price,status,requested_at,filled_at,client_request_id)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                order.id, order.portfolio_id, order.position_id, order.stock_code, order.stock_name,
                order.side.value, order.order_type.value, order.quantity,
                money_text(order.requested_price) if order.requested_price is not None else None,
                order.status.value, order.requested_at.isoformat(),
                order.filled_at.isoformat() if order.filled_at else None, client_request_id,
            ),
        )

    def update_order_status(self, order_id: str, status: OrderStatus, *, filled_at: datetime | None = None) -> SimulationOrder:
        cursor = self.conn.execute(
            "UPDATE simulation_order SET status=?, filled_at=? WHERE id=?",
            (status.value, filled_at.isoformat() if filled_at else None, order_id),
        )
        if cursor.rowcount != 1:
            raise SimulationPersistenceError(f"Order not found: {order_id}")
        row = self.conn.execute("SELECT * FROM simulation_order WHERE id=?", (order_id,)).fetchone()
        return _order_from_row(row)

    def find_order_by_request_id(self, portfolio_id: str, client_request_id: str) -> SimulationOrder | None:
        row = self.conn.execute(
            "SELECT * FROM simulation_order WHERE portfolio_id=? AND client_request_id=?",
            (portfolio_id, client_request_id),
        ).fetchone()
        return _order_from_row(row) if row else None

    def create_trade(self, trade: SimulationTrade) -> None:
        self.conn.execute(
            """INSERT INTO simulation_trade
            (id,portfolio_id,order_id,position_id,stock_code,side,quantity,price,gross_amount,fee,tax,slippage,net_amount,realized_pnl,executed_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                trade.id, trade.portfolio_id, trade.order_id, trade.position_id, trade.stock_code,
                trade.side.value, trade.quantity, money_text(trade.price), money_text(trade.gross_amount),
                money_text(trade.fee), money_text(trade.tax), money_text(trade.slippage),
                money_text(trade.net_amount), money_text(trade.realized_pnl), trade.executed_at.isoformat(),
            ),
        )

    def get_trade_by_order(self, order_id: str) -> SimulationTrade | None:
        row = self.conn.execute("SELECT * FROM simulation_trade WHERE order_id=?", (order_id,)).fetchone()
        return _trade_from_row(row) if row else None


class SimulationRepository:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)

    def connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def initialize(self) -> None:
        with self.connect() as conn:
            conn.executescript(SCHEMA)
            cols = {row[1] for row in conn.execute("PRAGMA table_info(simulation_order)").fetchall()}
            if "client_request_id" not in cols:
                conn.execute("ALTER TABLE simulation_order ADD COLUMN client_request_id TEXT")
            conn.execute(
                """CREATE UNIQUE INDEX IF NOT EXISTS idx_sim_order_request
                   ON simulation_order(portfolio_id, client_request_id)
                   WHERE client_request_id IS NOT NULL"""
            )
            conn.execute(
                """INSERT INTO simulation_schema_meta(key,value) VALUES('schema_version',?)
                   ON CONFLICT(key) DO UPDATE SET value=excluded.value""",
                (str(CURRENT_SCHEMA_VERSION),),
            )

    @contextmanager
    def transaction(self) -> Iterator[SimulationUnitOfWork]:
        conn = self.connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            yield SimulationUnitOfWork(conn)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def schema_version(self) -> int:
        with self.connect() as conn:
            row = conn.execute("SELECT value FROM simulation_schema_meta WHERE key='schema_version'").fetchone()
        return int(row["value"]) if row else 1

    def create_portfolio(self, portfolio: SimulationPortfolio) -> None:
        with self.connect() as conn:
            conn.execute(
                """INSERT INTO simulation_portfolio
                (id,name,mode,initial_cash,cash_balance,realized_pnl,default_scanner_baseline_id,status,created_at,updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (
                    portfolio.id, portfolio.name, portfolio.mode.value, money_text(portfolio.initial_cash),
                    money_text(portfolio.cash_balance), money_text(portfolio.realized_pnl),
                    portfolio.default_scanner_baseline_id, portfolio.status.value,
                    portfolio.created_at.isoformat(), portfolio.updated_at.isoformat(),
                ),
            )

    def get_portfolio(self, portfolio_id: str) -> SimulationPortfolio | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM simulation_portfolio WHERE id = ?", (portfolio_id,)).fetchone()
        return _portfolio_from_row(row) if row else None

    def create_position(self, position: SimulationPosition) -> None:
        with self.connect() as conn:
            SimulationUnitOfWork(conn).create_position(position)

    def save_position(self, position: SimulationPosition) -> None:
        with self.connect() as conn:
            SimulationUnitOfWork(conn).save_position(position)

    def get_position(self, position_id: str) -> SimulationPosition | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM simulation_position WHERE id = ?", (position_id,)).fetchone()
        return _position_from_row(row) if row else None

    def list_positions(self, portfolio_id: str, *, status: PositionStatus | None = None) -> list[SimulationPosition]:
        sql = "SELECT * FROM simulation_position WHERE portfolio_id = ?"
        params: list[object] = [portfolio_id]
        if status is not None:
            sql += " AND status = ?"
            params.append(status.value)
        sql += " ORDER BY opened_at, id"
        with self.connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [_position_from_row(row) for row in rows]

    @staticmethod
    def _position_from_row(row: sqlite3.Row) -> SimulationPosition:
        return _position_from_row(row)

    def create_order(self, order: SimulationOrder, *, client_request_id: str | None = None) -> None:
        with self.connect() as conn:
            SimulationUnitOfWork(conn).create_order(order, client_request_id=client_request_id)

    def get_order(self, order_id: str) -> SimulationOrder | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM simulation_order WHERE id=?", (order_id,)).fetchone()
        return _order_from_row(row) if row else None

    def create_trade(self, trade: SimulationTrade) -> None:
        with self.connect() as conn:
            SimulationUnitOfWork(conn).create_trade(trade)

    def get_trade(self, trade_id: str) -> SimulationTrade | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM simulation_trade WHERE id=?", (trade_id,)).fetchone()
        return _trade_from_row(row) if row else None

    def list_trades(self, portfolio_id: str) -> list[SimulationTrade]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM simulation_trade WHERE portfolio_id=? ORDER BY executed_at,id",
                (portfolio_id,),
            ).fetchall()
        return [_trade_from_row(row) for row in rows]

    def count_orders(self, portfolio_id: str) -> int:
        with self.connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS c FROM simulation_order WHERE portfolio_id=?", (portfolio_id,)).fetchone()
        return int(row["c"])

    def count_trades(self, portfolio_id: str) -> int:
        with self.connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS c FROM simulation_trade WHERE portfolio_id=?", (portfolio_id,)).fetchone()
        return int(row["c"])

    def raw_execute(self, sql: str, params: Iterable[object] = ()) -> None:
        """Test/support escape hatch. Domain services should not use this."""
        with self.connect() as conn:
            conn.execute(sql, tuple(params))
