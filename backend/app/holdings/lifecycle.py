from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, localcontext
from typing import Any, Iterator
from uuid import uuid4

from .catalog import HoldingsCatalog
from .domain import HoldingPosition, HoldingPositionEvent


class HoldingsLifecycleError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True, slots=True)
class PositionLifecycleResult:
    position: HoldingPosition
    event: HoldingPositionEvent


@dataclass(frozen=True, slots=True)
class InitialHoldingRegistrationResult:
    stock_id: str
    created_stock: bool
    position: HoldingPosition
    event: HoldingPositionEvent


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _decimal(value: Decimal | int | str, *, code: str, label: str) -> Decimal:
    try:
        number = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise HoldingsLifecycleError(code, f"{label} 값이 올바르지 않습니다.") from exc
    if not number.is_finite():
        raise HoldingsLifecycleError(code, f"{label}은 유한한 숫자여야 합니다.")
    return number


def _positive_decimal(
    value: Decimal | int | str,
    *,
    code: str,
    label: str,
) -> Decimal:
    number = _decimal(value, code=code, label=label)
    if number <= 0:
        raise HoldingsLifecycleError(code, f"{label}은 0보다 커야 합니다.")
    return number


def _non_negative_decimal(
    value: Decimal | int | str,
    *,
    code: str,
    label: str,
) -> Decimal:
    number = _decimal(value, code=code, label=label)
    if number < 0:
        raise HoldingsLifecycleError(code, f"{label}은 음수일 수 없습니다.")
    return number


def _decimal_text(value: Decimal) -> str:
    return format(value, "f")


def _parse_aware_datetime(value: str, *, code: str, label: str) -> datetime:
    raw = (value or "").strip()
    if not raw:
        raise HoldingsLifecycleError(code, f"{label}이 필요합니다.")
    normalized = raw[:-1] + "+00:00" if raw.endswith("Z") else raw
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise HoldingsLifecycleError(
            code,
            f"{label}은 timezone이 포함된 ISO-8601 형식이어야 합니다.",
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise HoldingsLifecycleError(
            code,
            f"{label}에는 timezone 정보가 필요합니다.",
        )
    return parsed


def _canonical_time(value: str, *, code: str, label: str) -> tuple[str, datetime]:
    parsed = _parse_aware_datetime(value, code=code, label=label)
    return parsed.isoformat(), parsed


class PositionLifecycleService:
    """Manual/virtual position ledger with atomic Position + Event updates."""

    def __init__(self, catalog: HoldingsCatalog):
        self.catalog = catalog

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        conn = self.catalog.connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    @staticmethod
    def _account_row(conn: sqlite3.Connection, account_id: str) -> sqlite3.Row:
        row = conn.execute(
            "SELECT * FROM position_account WHERE id=?",
            (account_id,),
        ).fetchone()
        if row is None or str(row["status"]) != "ACTIVE":
            raise HoldingsLifecycleError(
                "HOLD_POSITION_ACCOUNT_NOT_FOUND",
                "사용할 수 있는 Position 계좌를 찾을 수 없습니다.",
            )
        return row

    @staticmethod
    def _stock_row(conn: sqlite3.Connection, stock_id: str) -> sqlite3.Row:
        row = conn.execute(
            "SELECT * FROM monitored_stock WHERE id=?",
            (stock_id,),
        ).fetchone()
        if row is None:
            raise HoldingsLifecycleError(
                "HOLD_POSITION_STOCK_NOT_FOUND",
                "관리 대상 종목을 찾을 수 없습니다.",
            )
        return row

    @staticmethod
    def _assert_internal_account(account: sqlite3.Row) -> None:
        if str(account["account_kind"]).upper() == "BROKER":
            raise HoldingsLifecycleError(
                "HOLD_POSITION_SOURCE_MANAGED_EXTERNALLY",
                "증권사 계좌 Position은 수동 BUY/SELL/CORRECTION으로 변경할 수 없습니다.",
            )

    @staticmethod
    def _opened_reason(account: sqlite3.Row) -> str:
        kind = str(account["account_kind"]).upper()
        if kind == "MANUAL":
            return "MANUAL"
        if kind == "VIRTUAL":
            return "VIRTUAL"
        raise HoldingsLifecycleError(
            "HOLD_POSITION_SOURCE_MANAGED_EXTERNALLY",
            "증권사 계좌 Position은 외부 잔고 동기화로만 변경합니다.",
        )

    @staticmethod
    def _open_position_row(
        conn: sqlite3.Connection,
        stock_id: str,
        account_id: str,
    ) -> sqlite3.Row | None:
        return conn.execute(
            """
            SELECT * FROM holding_position
            WHERE monitored_stock_id=? AND position_account_id=? AND status='OPEN'
            """,
            (stock_id, account_id),
        ).fetchone()

    @staticmethod
    def _position_row(
        conn: sqlite3.Connection,
        position_id: str,
    ) -> sqlite3.Row:
        row = conn.execute(
            "SELECT * FROM holding_position WHERE id=?",
            (position_id,),
        ).fetchone()
        if row is None:
            raise HoldingsLifecycleError(
                "HOLD_POSITION_NOT_FOUND",
                "Position을 찾을 수 없습니다.",
            )
        return row

    @staticmethod
    def _assert_open(position: sqlite3.Row) -> None:
        if str(position["status"]).upper() != "OPEN":
            raise HoldingsLifecycleError(
                "HOLD_POSITION_ALREADY_CLOSED",
                "이미 종료된 Position은 변경할 수 없습니다.",
            )

    @staticmethod
    def _last_effective_at(
        conn: sqlite3.Connection,
        position_id: str,
    ) -> datetime | None:
        rows = conn.execute(
            """
            SELECT effective_at
            FROM holding_position_event
            WHERE position_id=? AND effective_at IS NOT NULL
            """,
            (position_id,),
        ).fetchall()
        latest: datetime | None = None
        for row in rows:
            raw = str(row["effective_at"] or "").strip()
            if not raw:
                continue
            try:
                parsed = _parse_aware_datetime(
                    raw,
                    code="HOLD_POSITION_CONFLICT",
                    label="저장된 effective_at",
                )
            except HoldingsLifecycleError as exc:
                raise HoldingsLifecycleError(
                    "HOLD_POSITION_CONFLICT",
                    "기존 Position Event의 시간이 올바르지 않아 안전하게 변경할 수 없습니다.",
                ) from exc
            absolute = parsed.astimezone(timezone.utc)
            if latest is None or absolute > latest:
                latest = absolute
        return latest

    @classmethod
    def _assert_event_order(
        cls,
        conn: sqlite3.Connection,
        position_id: str,
        effective_at: datetime,
    ) -> None:
        latest = cls._last_effective_at(conn, position_id)
        if latest is not None and effective_at.astimezone(timezone.utc) < latest:
            raise HoldingsLifecycleError(
                "HOLD_POSITION_EVENT_OUT_OF_ORDER",
                "마지막 Position Event보다 과거 시각의 이벤트를 뒤늦게 삽입할 수 없습니다.",
            )

    @staticmethod
    def _validate_revision(
        conn: sqlite3.Connection,
        *,
        revision_id: str | None,
        monitored_stock_id: str,
        effective_at: datetime,
    ) -> None:
        if revision_id is None:
            return
        row = conn.execute(
            """
            SELECT r.id,r.computed_at,d.monitored_stock_id
            FROM stock_analysis_revision r
            JOIN stock_analysis_day d ON d.id=r.analysis_day_id
            WHERE r.id=?
            """,
            (revision_id,),
        ).fetchone()
        if row is None or str(row["monitored_stock_id"]) != monitored_stock_id:
            raise HoldingsLifecycleError(
                "HOLD_POSITION_REVISION_MISMATCH",
                "BUY 대상 종목과 Analysis Revision의 종목이 일치하지 않습니다.",
            )
        computed_at = _parse_aware_datetime(
            str(row["computed_at"]),
            code="HOLD_POSITION_CONFLICT",
            label="Analysis Revision computed_at",
        )
        if computed_at.astimezone(timezone.utc) > effective_at.astimezone(timezone.utc):
            raise HoldingsLifecycleError(
                "HOLD_POSITION_REVISION_FROM_FUTURE",
                "매수 시점 이후에 계산된 Analysis Revision은 매수 당시 분석으로 연결할 수 없습니다.",
            )

    @staticmethod
    def _position_values(position: sqlite3.Row) -> tuple[Decimal, Decimal | None, Decimal]:
        quantity = _non_negative_decimal(
            str(position["current_quantity"]),
            code="HOLD_POSITION_CONFLICT",
            label="저장된 보유 수량",
        )
        average = (
            None
            if position["current_average_price"] is None
            else _positive_decimal(
                str(position["current_average_price"]),
                code="HOLD_POSITION_CONFLICT",
                label="저장된 평균단가",
            )
        )
        if quantity > 0 and average is None:
            raise HoldingsLifecycleError(
                "HOLD_POSITION_CONFLICT",
                "보유 수량이 있는데 평균단가가 없어 Position을 안전하게 변경할 수 없습니다.",
            )
        if position["current_cost_basis"] is not None:
            cost = _non_negative_decimal(
                str(position["current_cost_basis"]),
                code="HOLD_POSITION_CONFLICT",
                label="저장된 원금",
            )
        elif quantity == 0:
            cost = Decimal("0")
        else:
            assert average is not None
            cost = quantity * average
        return quantity, average, cost

    def _insert_event(
        self,
        conn: sqlite3.Connection,
        *,
        position_id: str,
        event_type: str,
        quantity_delta: Decimal,
        unit_price: Decimal | None,
        before_quantity: Decimal,
        after_quantity: Decimal,
        before_average_price: Decimal | None,
        after_average_price: Decimal | None,
        effective_at: str,
        analysis_revision_id: str | None,
        note: str | None,
    ) -> HoldingPositionEvent:
        event_id = str(uuid4())
        now = _now()
        conn.execute(
            """
            INSERT INTO holding_position_event(
                id,position_id,event_type,quantity_delta,unit_price,
                before_quantity,after_quantity,before_average_price,
                after_average_price,observed_at,effective_at,
                analysis_revision_id,account_sync_run_id,
                external_event_key,note,created_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                event_id,
                position_id,
                event_type,
                _decimal_text(quantity_delta),
                _decimal_text(unit_price) if unit_price is not None else None,
                _decimal_text(before_quantity),
                _decimal_text(after_quantity),
                _decimal_text(before_average_price)
                if before_average_price is not None
                else None,
                _decimal_text(after_average_price)
                if after_average_price is not None
                else None,
                None,
                effective_at,
                analysis_revision_id,
                None,
                None,
                note,
                now,
            ),
        )
        row = conn.execute(
            "SELECT * FROM holding_position_event WHERE id=?",
            (event_id,),
        ).fetchone()
        return self.catalog._event_from_row(row)  # noqa: SLF001

    def register_initial_holding(
        self,
        *,
        market: str,
        ticker: str,
        name: str,
        position_account_id: str,
        quantity: Decimal | int | str,
        average_price: Decimal | int | str,
        effective_at: str,
        note: str | None = None,
    ) -> InitialHoldingRegistrationResult:
        """Register an already-held position as an OPENING_BALANCE observation."""
        HOLD_LEDGER_1_OPENING_BALANCE = True
        market_value = (market or "").strip().upper()
        ticker_value = (ticker or "").strip()
        name_value = (name or "").strip()
        if market_value not in {"KOSPI", "KOSDAQ"}:
            raise HoldingsLifecycleError("HOLD_STOCK_MARKET_INVALID", "market은 KOSPI 또는 KOSDAQ이어야 합니다.")
        if len(ticker_value) != 6 or not ticker_value.isdigit():
            raise HoldingsLifecycleError("HOLD_STOCK_TICKER_INVALID", "국내주식 종목코드는 6자리 숫자여야 합니다.")
        if not name_value:
            raise HoldingsLifecycleError("HOLD_STOCK_REQUIRED", "종목명이 필요합니다.")

        opening_quantity = _positive_decimal(quantity, code="HOLD_POSITION_QUANTITY_INVALID", label="보유 수량")
        opening_price = _positive_decimal(average_price, code="HOLD_POSITION_PRICE_INVALID", label="평균단가")
        effective_text, _ = _canonical_time(effective_at, code="HOLD_POSITION_TIME_INVALID", label="effective_at")

        try:
            with self._transaction() as conn:
                stock = conn.execute(
                    "SELECT * FROM monitored_stock WHERE market=? AND ticker=?",
                    (market_value, ticker_value),
                ).fetchone()
                now = _now()
                created_stock = stock is None
                if stock is None:
                    stock_id = str(uuid4())
                    conn.execute("""
                        INSERT INTO monitored_stock(
                            id,market,ticker,name,watch_enabled,archived_at,created_at,updated_at
                        ) VALUES(?,?,?,?,?,?,?,?)
                    """, (stock_id, market_value, ticker_value, name_value, 0, None, now, now))
                else:
                    stock_id = str(stock["id"])
                    if stock["archived_at"] is not None:
                        conn.execute(
                            "UPDATE monitored_stock SET archived_at=NULL,name=?,updated_at=? WHERE id=?",
                            (name_value, now, stock_id),
                        )

                existing_open = conn.execute(
                    "SELECT id FROM holding_position WHERE monitored_stock_id=? AND status='OPEN' LIMIT 1",
                    (stock_id,),
                ).fetchone()
                if existing_open is not None:
                    raise HoldingsLifecycleError(
                        "HOLD_OPEN_POSITION_DUPLICATE",
                        "이미 보유 중인 종목입니다. 기존 보유 정보를 수정해주세요.",
                    )

                account = self._account_row(conn, position_account_id)
                self._assert_internal_account(account)
                position_id = str(uuid4())
                opening_cost = opening_quantity * opening_price
                conn.execute("""
                    INSERT INTO holding_position(
                        id,monitored_stock_id,position_account_id,status,
                        opened_at,closed_at,current_quantity,current_average_price,
                        current_cost_basis,opened_reason,last_observed_at,last_sync_run_id,
                        created_at,updated_at
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """, (
                    position_id,stock_id,position_account_id,"OPEN",effective_text,None,
                    _decimal_text(opening_quantity),_decimal_text(opening_price),_decimal_text(opening_cost),
                    self._opened_reason(account),None,None,now,now,
                ))
                event = self._insert_event(
                    conn,
                    position_id=position_id,
                    event_type="OPENING_BALANCE",
                    quantity_delta=opening_quantity,
                    unit_price=opening_price,
                    before_quantity=Decimal("0"),
                    after_quantity=opening_quantity,
                    before_average_price=None,
                    after_average_price=opening_price,
                    effective_at=effective_text,
                    analysis_revision_id=None,
                    note=note or "StockScope 추적 시작 당시 보유 상태",
                )
                stored = conn.execute("SELECT * FROM holding_position WHERE id=?", (position_id,)).fetchone()
                return InitialHoldingRegistrationResult(
                    stock_id=stock_id,
                    created_stock=created_stock,
                    position=self.catalog._position_from_row(stored),  # noqa: SLF001
                    event=event,
                )
        except sqlite3.IntegrityError as exc:
            raise HoldingsLifecycleError(
                "HOLD_POSITION_CONFLICT",
                "보유종목 등록 중 원장 충돌이 발생했습니다.",
            ) from exc

    def record_buy(
        self,
        *,
        monitored_stock_id: str,
        position_account_id: str,
        quantity: Decimal | int | str,
        unit_price: Decimal | int | str,
        effective_at: str,
        analysis_revision_id: str | None = None,
        note: str | None = None,
    ) -> PositionLifecycleResult:
        buy_quantity = _positive_decimal(
            quantity,
            code="HOLD_POSITION_QUANTITY_INVALID",
            label="매수 수량",
        )
        buy_price = _positive_decimal(
            unit_price,
            code="HOLD_POSITION_PRICE_INVALID",
            label="매수가격",
        )
        effective_text, effective_dt = _canonical_time(
            effective_at,
            code="HOLD_POSITION_TIME_INVALID",
            label="effective_at",
        )

        try:
            with self._transaction() as conn:
                self._stock_row(conn, monitored_stock_id)
                account = self._account_row(conn, position_account_id)
                self._assert_internal_account(account)
                self._validate_revision(
                    conn,
                    revision_id=analysis_revision_id,
                    monitored_stock_id=monitored_stock_id,
                    effective_at=effective_dt,
                )

                position = self._open_position_row(
                    conn,
                    monitored_stock_id,
                    position_account_id,
                )
                now = _now()
                if position is None:
                    position_id = str(uuid4())
                    before_quantity = Decimal("0")
                    before_average = None
                    after_quantity = buy_quantity
                    after_average = buy_price
                    after_cost = buy_quantity * buy_price
                    conn.execute(
                        """
                        INSERT INTO holding_position(
                            id,monitored_stock_id,position_account_id,status,
                            opened_at,closed_at,current_quantity,current_average_price,
                            current_cost_basis,opened_reason,last_observed_at,last_sync_run_id,
                            created_at,updated_at
                        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                        """,
                        (
                            position_id,
                            monitored_stock_id,
                            position_account_id,
                            "OPEN",
                            effective_text,
                            None,
                            _decimal_text(after_quantity),
                            _decimal_text(after_average),
                            _decimal_text(after_cost),
                            self._opened_reason(account),
                            None,
                            None,
                            now,
                            now,
                        ),
                    )
                else:
                    self._assert_open(position)
                    position_id = str(position["id"])
                    self._assert_event_order(conn, position_id, effective_dt)
                    before_quantity, before_average, before_cost = self._position_values(
                        position
                    )
                    after_quantity = before_quantity + buy_quantity
                    with localcontext() as context:
                        context.prec = 50
                        after_cost = before_cost + buy_quantity * buy_price
                        after_average = after_cost / after_quantity
                    cursor = conn.execute(
                        """
                        UPDATE holding_position
                        SET current_quantity=?,current_average_price=?,
                            current_cost_basis=?,updated_at=?
                        WHERE id=? AND status='OPEN'
                        """,
                        (
                            _decimal_text(after_quantity),
                            _decimal_text(after_average),
                            _decimal_text(after_cost),
                            now,
                            position_id,
                        ),
                    )
                    if cursor.rowcount != 1:
                        raise HoldingsLifecycleError(
                            "HOLD_POSITION_CONFLICT",
                            "Position이 동시에 변경되어 BUY를 적용하지 못했습니다.",
                        )

                event = self._insert_event(
                    conn,
                    position_id=position_id,
                    event_type="BUY",
                    quantity_delta=buy_quantity,
                    unit_price=buy_price,
                    before_quantity=before_quantity,
                    after_quantity=after_quantity,
                    before_average_price=before_average,
                    after_average_price=after_average,
                    effective_at=effective_text,
                    analysis_revision_id=analysis_revision_id,
                    note=note,
                )
                stored = conn.execute(
                    "SELECT * FROM holding_position WHERE id=?",
                    (position_id,),
                ).fetchone()
                result = PositionLifecycleResult(
                    position=self.catalog._position_from_row(stored),  # noqa: SLF001
                    event=event,
                )
        except sqlite3.IntegrityError as exc:
            raise HoldingsLifecycleError(
                "HOLD_POSITION_CONFLICT",
                "BUY 저장 중 Position 원장 충돌이 발생했습니다.",
            ) from exc
        return result

    def record_sell(
        self,
        *,
        position_id: str,
        quantity: Decimal | int | str,
        unit_price: Decimal | int | str,
        effective_at: str,
        note: str | None = None,
    ) -> PositionLifecycleResult:
        sell_quantity = _positive_decimal(
            quantity,
            code="HOLD_POSITION_QUANTITY_INVALID",
            label="매도 수량",
        )
        sell_price = _positive_decimal(
            unit_price,
            code="HOLD_POSITION_PRICE_INVALID",
            label="매도가격",
        )
        effective_text, effective_dt = _canonical_time(
            effective_at,
            code="HOLD_POSITION_TIME_INVALID",
            label="effective_at",
        )

        try:
            with self._transaction() as conn:
                position = self._position_row(conn, position_id)
                self._assert_open(position)
                account = self._account_row(
                    conn,
                    str(position["position_account_id"]),
                )
                self._assert_internal_account(account)
                self._assert_event_order(conn, position_id, effective_dt)

                before_quantity, before_average, _ = self._position_values(position)
                if sell_quantity > before_quantity:
                    raise HoldingsLifecycleError(
                        "HOLD_POSITION_SELL_EXCEEDS_HOLDING",
                        "현재 보유 수량보다 많이 매도할 수 없습니다.",
                    )
                if before_average is None:
                    raise HoldingsLifecycleError(
                        "HOLD_POSITION_CONFLICT",
                        "평균단가가 없어 SELL을 안전하게 적용할 수 없습니다.",
                    )

                after_quantity = before_quantity - sell_quantity
                after_average = before_average
                after_cost = (
                    Decimal("0")
                    if after_quantity == 0
                    else after_quantity * before_average
                )
                now = _now()
                status = "CLOSED" if after_quantity == 0 else "OPEN"
                closed_at = effective_text if after_quantity == 0 else None
                cursor = conn.execute(
                    """
                    UPDATE holding_position
                    SET status=?,closed_at=?,current_quantity=?,
                        current_average_price=?,current_cost_basis=?,updated_at=?
                    WHERE id=? AND status='OPEN'
                    """,
                    (
                        status,
                        closed_at,
                        _decimal_text(after_quantity),
                        _decimal_text(after_average),
                        _decimal_text(after_cost),
                        now,
                        position_id,
                    ),
                )
                if cursor.rowcount != 1:
                    raise HoldingsLifecycleError(
                        "HOLD_POSITION_CONFLICT",
                        "Position이 동시에 변경되어 SELL을 적용하지 못했습니다.",
                    )

                event = self._insert_event(
                    conn,
                    position_id=position_id,
                    event_type="SELL",
                    quantity_delta=-sell_quantity,
                    unit_price=sell_price,
                    before_quantity=before_quantity,
                    after_quantity=after_quantity,
                    before_average_price=before_average,
                    after_average_price=after_average,
                    effective_at=effective_text,
                    analysis_revision_id=None,
                    note=note,
                )
                stored = conn.execute(
                    "SELECT * FROM holding_position WHERE id=?",
                    (position_id,),
                ).fetchone()
                result = PositionLifecycleResult(
                    position=self.catalog._position_from_row(stored),  # noqa: SLF001
                    event=event,
                )
        except sqlite3.IntegrityError as exc:
            raise HoldingsLifecycleError(
                "HOLD_POSITION_CONFLICT",
                "SELL 저장 중 Position 원장 충돌이 발생했습니다.",
            ) from exc
        return result

    def record_correction(
        self,
        *,
        position_id: str,
        corrected_quantity: Decimal | int | str,
        corrected_average_price: Decimal | int | str,
        effective_at: str,
        note: str,
    ) -> PositionLifecycleResult:
        correction_note = (note or "").strip()
        if not correction_note:
            raise HoldingsLifecycleError(
                "HOLD_POSITION_CORRECTION_NOTE_REQUIRED",
                "CORRECTION에는 수정 사유가 필요합니다.",
            )
        after_quantity = _non_negative_decimal(
            corrected_quantity,
            code="HOLD_POSITION_QUANTITY_INVALID",
            label="수정 수량",
        )
        after_average = _positive_decimal(
            corrected_average_price,
            code="HOLD_POSITION_PRICE_INVALID",
            label="수정 평균단가",
        )
        effective_text, effective_dt = _canonical_time(
            effective_at,
            code="HOLD_POSITION_TIME_INVALID",
            label="effective_at",
        )

        try:
            with self._transaction() as conn:
                position = self._position_row(conn, position_id)
                self._assert_open(position)
                account = self._account_row(
                    conn,
                    str(position["position_account_id"]),
                )
                self._assert_internal_account(account)
                self._assert_event_order(conn, position_id, effective_dt)

                before_quantity, before_average, _ = self._position_values(position)
                after_cost = (
                    Decimal("0")
                    if after_quantity == 0
                    else after_quantity * after_average
                )
                status = "CLOSED" if after_quantity == 0 else "OPEN"
                closed_at = effective_text if after_quantity == 0 else None
                now = _now()
                cursor = conn.execute(
                    """
                    UPDATE holding_position
                    SET status=?,closed_at=?,current_quantity=?,
                        current_average_price=?,current_cost_basis=?,updated_at=?
                    WHERE id=? AND status='OPEN'
                    """,
                    (
                        status,
                        closed_at,
                        _decimal_text(after_quantity),
                        _decimal_text(after_average),
                        _decimal_text(after_cost),
                        now,
                        position_id,
                    ),
                )
                if cursor.rowcount != 1:
                    raise HoldingsLifecycleError(
                        "HOLD_POSITION_CONFLICT",
                        "Position이 동시에 변경되어 CORRECTION을 적용하지 못했습니다.",
                    )

                event = self._insert_event(
                    conn,
                    position_id=position_id,
                    event_type="CORRECTION",
                    quantity_delta=after_quantity - before_quantity,
                    unit_price=None,
                    before_quantity=before_quantity,
                    after_quantity=after_quantity,
                    before_average_price=before_average,
                    after_average_price=after_average,
                    effective_at=effective_text,
                    analysis_revision_id=None,
                    note=correction_note,
                )
                stored = conn.execute(
                    "SELECT * FROM holding_position WHERE id=?",
                    (position_id,),
                ).fetchone()
                result = PositionLifecycleResult(
                    position=self.catalog._position_from_row(stored),  # noqa: SLF001
                    event=event,
                )
        except sqlite3.IntegrityError as exc:
            raise HoldingsLifecycleError(
                "HOLD_POSITION_CONFLICT",
                "CORRECTION 저장 중 Position 원장 충돌이 발생했습니다.",
            ) from exc
        return result
