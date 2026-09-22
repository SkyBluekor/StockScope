from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

from app.core.config import PROJECT_ROOT, Settings, get_settings
from app.integrations.kis.account import (
    KisAccountError,
    KisDomesticBalance,
    KisHolding,
    inquire_domestic_balance,
)
from app.integrations.kis.client import (
    KisConfigurationError,
    normalize_environment,
    validate_account_settings,
)

from .catalog import HoldingsCatalog
from .domain import account_fingerprint


DEFAULT_MARKET_STORE_DB = (
    PROJECT_ROOT / "backend" / "runtime" / "market_history" / "market_history.db"
)


class HoldingsKisSyncError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True, slots=True)
class KisAccountSyncResult:
    sync_run_id: str
    account_id: str
    status: str
    observed_at: str
    page_count: int
    holding_count: int
    created_positions: int
    reconciled_positions: int
    closed_positions: int
    unchanged_positions: int


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _decimal(value: Any, *, field: str, non_negative: bool = False, positive: bool = False) -> Decimal:
    try:
        number = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise HoldingsKisSyncError(
            "HOLD_KIS_SYNC_INVALID_HOLDING",
            f"KIS holding field {field} is not a valid decimal.",
        ) from exc
    if not number.is_finite():
        raise HoldingsKisSyncError(
            "HOLD_KIS_SYNC_INVALID_HOLDING",
            f"KIS holding field {field} must be finite.",
        )
    if positive and number <= 0:
        raise HoldingsKisSyncError(
            "HOLD_KIS_SYNC_INVALID_HOLDING",
            f"KIS holding field {field} must be greater than zero.",
        )
    if non_negative and number < 0:
        raise HoldingsKisSyncError(
            "HOLD_KIS_SYNC_INVALID_HOLDING",
            f"KIS holding field {field} must not be negative.",
        )
    return number


def _decimal_text(value: Decimal) -> str:
    return format(value, "f")


class KisAccountSyncService:
    """Read a complete KIS balance snapshot and reconcile BROKER positions.

    This service never infers trades. KIS balance changes are recorded only as
    BALANCE_OBSERVED or RECONCILED events.
    """

    def __init__(
        self,
        catalog: HoldingsCatalog,
        *,
        settings: Settings | None = None,
        market_store_db: Path | None = None,
        balance_reader: Callable[[Settings], KisDomesticBalance] | None = None,
    ) -> None:
        self.catalog = catalog
        self.settings = settings
        self.market_store_db = Path(market_store_db or DEFAULT_MARKET_STORE_DB)
        self.balance_reader = balance_reader or inquire_domestic_balance

    @staticmethod
    def _account_display_name(environment: str) -> str:
        return "한국투자증권 실계좌" if environment == "REAL" else "한국투자증권 모의계좌"

    def _start_sync(self, settings: Settings) -> tuple[str, str]:
        environment = normalize_environment(settings.kis_env).upper()
        fingerprint = account_fingerprint(
            provider="KIS",
            broker_environment=environment,
            account_number=settings.kis_account_no or "",
            product_code=settings.kis_account_product_code,
        )
        now = _now()
        conn = self.catalog.connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            account = conn.execute(
                """
                SELECT * FROM position_account
                WHERE provider='KIS'
                  AND broker_environment=?
                  AND external_account_fingerprint=?
                """,
                (environment, fingerprint),
            ).fetchone()
            if account is None:
                account_id = str(uuid4())
                conn.execute(
                    """
                    INSERT INTO position_account(
                        id,provider,account_kind,broker_environment,
                        external_account_fingerprint,display_name,status,
                        created_at,updated_at
                    ) VALUES(?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        account_id,
                        "KIS",
                        "BROKER",
                        environment,
                        fingerprint,
                        self._account_display_name(environment),
                        "ACTIVE",
                        now,
                        now,
                    ),
                )
            else:
                if str(account["account_kind"]) != "BROKER" or str(account["status"]) != "ACTIVE":
                    raise HoldingsKisSyncError(
                        "HOLD_KIS_SYNC_ACCOUNT_CONFLICT",
                        "기존 KIS 계좌 항목이 BROKER/ACTIVE 상태가 아닙니다.",
                    )
                account_id = str(account["id"])

            sync_run_id = str(uuid4())
            conn.execute(
                """
                INSERT INTO account_sync_run(
                    id,position_account_id,status,started_at,completed_at,
                    is_complete,observed_at,page_count,holding_count,
                    error_code,error_message,created_at,updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    sync_run_id,
                    account_id,
                    "RUNNING",
                    now,
                    None,
                    0,
                    None,
                    0,
                    0,
                    None,
                    None,
                    now,
                    now,
                ),
            )
            conn.commit()
            return account_id, sync_run_id
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _mark_failed(self, sync_run_id: str, *, code: str, message: str) -> None:
        now = _now()
        conn = self.catalog.connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                """
                UPDATE account_sync_run
                SET status='FAILED',completed_at=?,is_complete=0,
                    error_code=?,error_message=?,updated_at=?
                WHERE id=? AND status='RUNNING'
                """,
                (now, code, message[:1000], now, sync_run_id),
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    @staticmethod
    def _validate_snapshot(balance: KisDomesticBalance) -> tuple[list[KisHolding], int]:
        if balance.is_complete is not True:
            raise HoldingsKisSyncError(
                "HOLD_KIS_SYNC_INCOMPLETE",
                "KIS 잔고 Snapshot이 끝까지 완료되지 않았습니다.",
            )
        try:
            page_count = int(balance.page_count)
        except (TypeError, ValueError) as exc:
            raise HoldingsKisSyncError(
                "HOLD_KIS_SYNC_INCOMPLETE",
                "KIS 잔고 page_count가 올바르지 않습니다.",
            ) from exc
        if page_count < 1:
            raise HoldingsKisSyncError(
                "HOLD_KIS_SYNC_INCOMPLETE",
                "완료된 KIS 잔고 Snapshot에는 최소 1페이지가 필요합니다.",
            )

        validated: list[KisHolding] = []
        seen: set[str] = set()
        for item in balance.holdings:
            ticker = str(item.ticker or "").strip()
            if len(ticker) != 6 or not ticker.isdigit():
                raise HoldingsKisSyncError(
                    "HOLD_KIS_SYNC_INVALID_HOLDING",
                    "KIS 보유 종목코드는 6자리 숫자여야 합니다.",
                )
            if ticker in seen:
                raise HoldingsKisSyncError(
                    "HOLD_KIS_SYNC_DUPLICATE_TICKER",
                    f"KIS 잔고 Snapshot에 종목코드 {ticker}가 중복되었습니다.",
                )
            seen.add(ticker)

            quantity = _decimal(
                item.quantity,
                field="quantity",
                non_negative=True,
            )
            if quantity > 0:
                _decimal(
                    item.average_price,
                    field="average_price",
                    positive=True,
                )
            if quantity > 0:
                validated.append(item)
        return validated, page_count

    def _existing_stock_market(self, ticker: str) -> str | None:
        with self.catalog.connection() as conn:
            rows = conn.execute(
                """
                SELECT market
                FROM monitored_stock
                WHERE ticker=?
                ORDER BY market
                """,
                (ticker,),
            ).fetchall()
        markets = sorted({str(row["market"]).upper() for row in rows})
        if len(markets) > 1:
            raise HoldingsKisSyncError(
                "HOLD_KIS_SYNC_MARKET_UNRESOLVED",
                f"{ticker} 종목이 여러 market으로 등록되어 있어 자동 동기화할 수 없습니다.",
            )
        return markets[0] if markets else None

    def _market_from_store(self, ticker: str) -> str:
        if not self.market_store_db.is_file():
            raise HoldingsKisSyncError(
                "HOLD_KIS_SYNC_MARKET_UNRESOLVED",
                "Market Store가 없어 신규 KIS 보유 종목의 market을 확인할 수 없습니다.",
            )
        uri = self.market_store_db.resolve().as_uri() + "?mode=ro"
        try:
            with sqlite3.connect(uri, uri=True) as conn:
                rows = conn.execute(
                    """
                    SELECT DISTINCT market
                    FROM stock_daily
                    WHERE stock_code=?
                    ORDER BY market
                    """,
                    (ticker,),
                ).fetchall()
        except sqlite3.Error as exc:
            raise HoldingsKisSyncError(
                "HOLD_KIS_SYNC_MARKET_UNRESOLVED",
                "Market Store에서 신규 KIS 보유 종목의 market을 확인하지 못했습니다.",
            ) from exc
        markets = sorted(
            {
                str(row[0]).upper()
                for row in rows
                if str(row[0]).upper() in {"KOSPI", "KOSDAQ"}
            }
        )
        if len(markets) != 1:
            raise HoldingsKisSyncError(
                "HOLD_KIS_SYNC_MARKET_UNRESOLVED",
                f"{ticker} 종목의 KOSPI/KOSDAQ market을 하나로 확정하지 못했습니다.",
            )
        return markets[0]

    def _resolve_markets(self, holdings: list[KisHolding]) -> dict[str, str]:
        result: dict[str, str] = {}
        for item in holdings:
            ticker = str(item.ticker).strip()
            market = self._existing_stock_market(ticker)
            result[ticker] = market or self._market_from_store(ticker)
        return result

    @staticmethod
    def _insert_event(
        conn: sqlite3.Connection,
        *,
        position_id: str,
        event_type: str,
        before_quantity: Decimal,
        after_quantity: Decimal,
        before_average_price: Decimal | None,
        after_average_price: Decimal | None,
        observed_at: str,
        sync_run_id: str,
        note: str,
    ) -> None:
        if event_type not in {"BALANCE_OBSERVED", "RECONCILED"}:
            raise HoldingsKisSyncError(
                "HOLD_KIS_SYNC_STORAGE_CONFLICT",
                "KIS 잔고 동기화는 거래 Event를 생성할 수 없습니다.",
            )
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
                str(uuid4()),
                position_id,
                event_type,
                _decimal_text(after_quantity - before_quantity),
                None,
                _decimal_text(before_quantity),
                _decimal_text(after_quantity),
                _decimal_text(before_average_price)
                if before_average_price is not None
                else None,
                _decimal_text(after_average_price)
                if after_average_price is not None
                else None,
                observed_at,
                observed_at,
                None,
                sync_run_id,
                None,
                note,
                now,
            ),
        )

    @staticmethod
    def _position_values(row: sqlite3.Row) -> tuple[Decimal, Decimal | None]:
        quantity = _decimal(
            row["current_quantity"],
            field="stored_quantity",
            non_negative=True,
        )
        average = (
            None
            if row["current_average_price"] is None
            else _decimal(
                row["current_average_price"],
                field="stored_average_price",
                positive=True,
            )
        )
        if quantity > 0 and average is None:
            raise HoldingsKisSyncError(
                "HOLD_KIS_SYNC_STORAGE_CONFLICT",
                "기존 KIS Position의 평균단가가 비어 있습니다.",
            )
        return quantity, average

    def _apply_complete_snapshot(
        self,
        *,
        account_id: str,
        sync_run_id: str,
        holdings: list[KisHolding],
        page_count: int,
        markets: dict[str, str],
        observed_at: str,
    ) -> KisAccountSyncResult:
        conn = self.catalog.connect()
        created = 0
        reconciled = 0
        closed = 0
        unchanged = 0
        desired_stock_ids: set[str] = set()
        now = _now()

        try:
            conn.execute("BEGIN IMMEDIATE")
            sync_row = conn.execute(
                "SELECT status FROM account_sync_run WHERE id=? AND position_account_id=?",
                (sync_run_id, account_id),
            ).fetchone()
            if sync_row is None or str(sync_row["status"]) != "RUNNING":
                raise HoldingsKisSyncError(
                    "HOLD_KIS_SYNC_STORAGE_CONFLICT",
                    "RUNNING 상태의 KIS Sync Run을 찾을 수 없습니다.",
                )

            for item in sorted(holdings, key=lambda value: value.ticker):
                ticker = str(item.ticker).strip()
                market = markets[ticker]
                rows = conn.execute(
                    "SELECT * FROM monitored_stock WHERE ticker=? ORDER BY market",
                    (ticker,),
                ).fetchall()
                if len(rows) > 1:
                    raise HoldingsKisSyncError(
                        "HOLD_KIS_SYNC_MARKET_UNRESOLVED",
                        f"{ticker} 종목이 여러 market으로 등록되어 있습니다.",
                    )
                if rows:
                    stock = rows[0]
                else:
                    stock_id = str(uuid4())
                    conn.execute(
                        """
                        INSERT INTO monitored_stock(
                            id,market,ticker,name,watch_enabled,archived_at,
                            created_at,updated_at
                        ) VALUES(?,?,?,?,?,?,?,?)
                        """,
                        (
                            stock_id,
                            market,
                            ticker,
                            str(item.name or "").strip() or ticker,
                            0,
                            None,
                            now,
                            now,
                        ),
                    )
                    stock = conn.execute(
                        "SELECT * FROM monitored_stock WHERE id=?",
                        (stock_id,),
                    ).fetchone()

                stock_id = str(stock["id"])
                desired_stock_ids.add(stock_id)
                quantity = _decimal(
                    item.quantity,
                    field="quantity",
                    positive=True,
                )
                average = _decimal(
                    item.average_price,
                    field="average_price",
                    positive=True,
                )
                cost_basis = quantity * average

                position = conn.execute(
                    """
                    SELECT * FROM holding_position
                    WHERE monitored_stock_id=? AND position_account_id=?
                      AND status='OPEN'
                    """,
                    (stock_id, account_id),
                ).fetchone()

                if position is None:
                    position_id = str(uuid4())
                    conn.execute(
                        """
                        INSERT INTO holding_position(
                            id,monitored_stock_id,position_account_id,status,
                            opened_at,closed_at,current_quantity,current_average_price,
                            current_cost_basis,opened_reason,last_observed_at,
                            last_sync_run_id,created_at,updated_at
                        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                        """,
                        (
                            position_id,
                            stock_id,
                            account_id,
                            "OPEN",
                            observed_at,
                            None,
                            _decimal_text(quantity),
                            _decimal_text(average),
                            _decimal_text(cost_basis),
                            "KIS_OBSERVED",
                            observed_at,
                            sync_run_id,
                            now,
                            now,
                        ),
                    )
                    self._insert_event(
                        conn,
                        position_id=position_id,
                        event_type="BALANCE_OBSERVED",
                        before_quantity=Decimal("0"),
                        after_quantity=quantity,
                        before_average_price=None,
                        after_average_price=average,
                        observed_at=observed_at,
                        sync_run_id=sync_run_id,
                        note="KIS complete balance snapshot first observation",
                    )
                    created += 1
                    continue

                before_quantity, before_average = self._position_values(position)
                changed = before_quantity != quantity or before_average != average
                conn.execute(
                    """
                    UPDATE holding_position
                    SET current_quantity=?,current_average_price=?,
                        current_cost_basis=?,last_observed_at=?,
                        last_sync_run_id=?,updated_at=?
                    WHERE id=? AND status='OPEN'
                    """,
                    (
                        _decimal_text(quantity),
                        _decimal_text(average),
                        _decimal_text(cost_basis),
                        observed_at,
                        sync_run_id,
                        now,
                        str(position["id"]),
                    ),
                )
                if changed:
                    self._insert_event(
                        conn,
                        position_id=str(position["id"]),
                        event_type="RECONCILED",
                        before_quantity=before_quantity,
                        after_quantity=quantity,
                        before_average_price=before_average,
                        after_average_price=average,
                        observed_at=observed_at,
                        sync_run_id=sync_run_id,
                        note="KIS complete balance snapshot reconciliation",
                    )
                    reconciled += 1
                else:
                    unchanged += 1

            open_rows = conn.execute(
                """
                SELECT * FROM holding_position
                WHERE position_account_id=? AND status='OPEN'
                """,
                (account_id,),
            ).fetchall()
            for position in open_rows:
                stock_id = str(position["monitored_stock_id"])
                if stock_id in desired_stock_ids:
                    continue
                before_quantity, before_average = self._position_values(position)
                conn.execute(
                    """
                    UPDATE holding_position
                    SET status='CLOSED',closed_at=?,current_quantity='0',
                        current_cost_basis='0',last_observed_at=?,
                        last_sync_run_id=?,updated_at=?
                    WHERE id=? AND status='OPEN'
                    """,
                    (
                        observed_at,
                        observed_at,
                        sync_run_id,
                        now,
                        str(position["id"]),
                    ),
                )
                self._insert_event(
                    conn,
                    position_id=str(position["id"]),
                    event_type="RECONCILED",
                    before_quantity=before_quantity,
                    after_quantity=Decimal("0"),
                    before_average_price=before_average,
                    after_average_price=before_average,
                    observed_at=observed_at,
                    sync_run_id=sync_run_id,
                    note="KIS complete balance snapshot no longer contains this holding",
                )
                closed += 1

            cursor = conn.execute(
                """
                UPDATE account_sync_run
                SET status='COMPLETED',completed_at=?,is_complete=1,
                    observed_at=?,page_count=?,holding_count=?,
                    error_code=NULL,error_message=NULL,updated_at=?
                WHERE id=? AND status='RUNNING'
                """,
                (
                    now,
                    observed_at,
                    page_count,
                    len(holdings),
                    now,
                    sync_run_id,
                ),
            )
            if cursor.rowcount != 1:
                raise HoldingsKisSyncError(
                    "HOLD_KIS_SYNC_STORAGE_CONFLICT",
                    "KIS Sync Run 완료 상태를 원자적으로 저장하지 못했습니다.",
                )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

        return KisAccountSyncResult(
            sync_run_id=sync_run_id,
            account_id=account_id,
            status="COMPLETED",
            observed_at=observed_at,
            page_count=page_count,
            holding_count=len(holdings),
            created_positions=created,
            reconciled_positions=reconciled,
            closed_positions=closed,
            unchanged_positions=unchanged,
        )

    def sync(self) -> KisAccountSyncResult:
        try:
            settings = validate_account_settings(self.settings or get_settings())
        except KisConfigurationError as exc:
            raise HoldingsKisSyncError(
                "HOLD_KIS_SYNC_CONFIGURATION_ERROR",
                "KIS 계좌 설정이 올바르지 않습니다.",
            ) from exc

        account_id, sync_run_id = self._start_sync(settings)

        try:
            balance = self.balance_reader(settings)
        except Exception as exc:
            error = HoldingsKisSyncError(
                "HOLD_KIS_SYNC_BALANCE_FAILED",
                f"KIS 잔고 조회에 실패했습니다: {exc}",
            )
            self._mark_failed(sync_run_id, code=error.code, message=error.message)
            raise error from exc

        try:
            holdings, page_count = self._validate_snapshot(balance)
            markets = self._resolve_markets(holdings)
            observed_at = _now()
            return self._apply_complete_snapshot(
                account_id=account_id,
                sync_run_id=sync_run_id,
                holdings=holdings,
                page_count=page_count,
                markets=markets,
                observed_at=observed_at,
            )
        except HoldingsKisSyncError as exc:
            self._mark_failed(sync_run_id, code=exc.code, message=exc.message)
            raise
        except Exception as exc:
            error = HoldingsKisSyncError(
                "HOLD_KIS_SYNC_STORAGE_CONFLICT",
                f"KIS 잔고를 StockScope Position에 반영하지 못했습니다: {exc}",
            )
            self._mark_failed(sync_run_id, code=error.code, message=error.message)
            raise error from exc


def sync_configured_kis_account(
    *,
    catalog: HoldingsCatalog | None = None,
    market_store_db: Path | None = None,
) -> KisAccountSyncResult:
    target_catalog = catalog or HoldingsCatalog()
    if catalog is None:
        target_catalog.initialize()
    return KisAccountSyncService(
        target_catalog,
        market_store_db=market_store_db,
    ).sync()
