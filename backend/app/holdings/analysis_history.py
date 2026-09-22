from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

from app.core.config import PROJECT_ROOT

from .analysis import (
    HoldingsAnalysisError,
    SingleStockAnalysis,
    analyze_single_stock,
)
from .catalog import HoldingsCatalog
from .domain import MonitoredStock, StockAnalysisRevision


DEFAULT_MARKET_STORE_DB = (
    PROJECT_ROOT / "backend" / "runtime" / "market_history" / "market_history.db"
)


class HoldingsAnalysisHistoryError(RuntimeError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        cause_code: str | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.cause_code = cause_code


@dataclass(frozen=True, slots=True)
class StoredAnalysisResult:
    monitored_stock_id: str
    analysis_day_id: str
    revision: StockAnalysisRevision
    created_revision: bool
    promoted_current: bool


@dataclass(frozen=True, slots=True)
class AnalysisTimelineItem:
    market_date: str
    analysis_day_id: str
    revision_id: str
    revision_no: int
    computed_at: str
    strategy_key: str | None
    action_state: str | None
    risk_state: str | None
    reference_price: Decimal | None
    stop_price: Decimal | None
    target1_price: Decimal | None
    target2_price: Decimal | None
    previous_strategy_key: str | None
    previous_action_state: str | None
    previous_risk_state: str | None
    previous_reference_price: Decimal | None
    previous_stop_price: Decimal | None
    previous_target1_price: Decimal | None
    previous_target2_price: Decimal | None
    strategy_changed: bool
    action_changed: bool
    risk_changed: bool
    reference_price_changed: bool
    stop_price_changed: bool
    target1_price_changed: bool
    target2_price_changed: bool
    reference_price_delta: Decimal | None
    stop_price_delta: Decimal | None
    target1_price_delta: Decimal | None
    target2_price_delta: Decimal | None


@dataclass(frozen=True, slots=True)
class StockTimelineItem:
    kind: str
    occurred_at: str
    market_date: str | None
    analysis_revision_id: str | None
    position_id: str | None
    event_type: str | None
    payload: dict[str, Any]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_text(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def _decimal_text(value: Decimal | float | int | str | None) -> str | None:
    if value is None:
        return None
    return format(Decimal(str(value)), "f")


def _decimal_value(value: Any) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value))


def _delta(current: Decimal | None, previous: Decimal | None) -> Decimal | None:
    if current is None or previous is None:
        return None
    return current - previous


def _sort_time(value: str) -> datetime:
    raw = (value or "").strip()
    normalized = raw[:-1] + "+00:00" if raw.endswith("Z") else raw
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return datetime.min.replace(tzinfo=timezone.utc)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


class HoldingAnalysisHistoryService:
    """Persist immutable daily HOLD analysis revisions and project timelines."""

    def __init__(
        self,
        catalog: HoldingsCatalog,
        *,
        market_store_db: Path | None = None,
        analyzer: Callable[..., SingleStockAnalysis] | None = None,
        clock: Callable[[], str] | None = None,
    ) -> None:
        self.catalog = catalog
        self.market_store_db = Path(market_store_db or DEFAULT_MARKET_STORE_DB)
        self.analyzer = analyzer or analyze_single_stock
        self.clock = clock or _now

    def _stock(self, monitored_stock_id: str) -> MonitoredStock:
        try:
            return self.catalog.get_monitored_stock(monitored_stock_id)
        except Exception as exc:
            raise HoldingsAnalysisHistoryError(
                "HOLD_ANALYSIS_HISTORY_STOCK_NOT_FOUND",
                "분석 대상 종목을 찾을 수 없습니다.",
            ) from exc

    @staticmethod
    def _reason(
        previous: StockAnalysisRevision | None,
        result: SingleStockAnalysis,
    ) -> str:
        if previous is None:
            return "INITIAL"
        if (
            previous.scanner_version != result.scanner_version
            or previous.analysis_engine_version != result.analysis_engine_version
        ):
            return "ENGINE_CHANGED"
        if previous.policy_version != result.policy_version:
            return "POLICY_CHANGED"
        return "INPUT_CHANGED"

    @staticmethod
    def _revision_from_row(
        catalog: HoldingsCatalog,
        row: sqlite3.Row,
    ) -> StockAnalysisRevision:
        return catalog._revision_from_row(row)  # noqa: SLF001

    def _store_result(
        self,
        *,
        stock: MonitoredStock,
        result: SingleStockAnalysis,
        computed_at: str,
    ) -> StoredAnalysisResult:
        if result.market.upper() != stock.market.upper():
            raise HoldingsAnalysisHistoryError(
                "HOLD_ANALYSIS_HISTORY_CONFLICT",
                "분석 결과의 market이 관리 종목과 일치하지 않습니다.",
            )
        if result.ticker != stock.ticker:
            raise HoldingsAnalysisHistoryError(
                "HOLD_ANALYSIS_HISTORY_CONFLICT",
                "분석 결과의 ticker가 관리 종목과 일치하지 않습니다.",
            )

        conn = self.catalog.connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            stock_row = conn.execute(
                "SELECT id FROM monitored_stock WHERE id=?",
                (stock.id,),
            ).fetchone()
            if stock_row is None:
                raise HoldingsAnalysisHistoryError(
                    "HOLD_ANALYSIS_HISTORY_STOCK_NOT_FOUND",
                    "분석 대상 종목이 저장 중 사라졌습니다.",
                )

            day = conn.execute(
                """
                SELECT * FROM stock_analysis_day
                WHERE monitored_stock_id=? AND market_date=?
                """,
                (stock.id, result.market_date),
            ).fetchone()
            now = self.clock()
            if day is None:
                day_id = str(uuid4())
                conn.execute(
                    """
                    INSERT INTO stock_analysis_day(
                        id,monitored_stock_id,market_date,current_revision_id,
                        created_at,updated_at
                    ) VALUES(?,?,?,?,?,?)
                    """,
                    (
                        day_id,
                        stock.id,
                        result.market_date,
                        None,
                        now,
                        now,
                    ),
                )
                day = conn.execute(
                    "SELECT * FROM stock_analysis_day WHERE id=?",
                    (day_id,),
                ).fetchone()
            else:
                day_id = str(day["id"])

            current: StockAnalysisRevision | None = None
            if day["current_revision_id"]:
                current_row = conn.execute(
                    "SELECT * FROM stock_analysis_revision WHERE id=?",
                    (day["current_revision_id"],),
                ).fetchone()
                if current_row is not None:
                    current = self._revision_from_row(self.catalog, current_row)

            existing = conn.execute(
                """
                SELECT * FROM stock_analysis_revision
                WHERE analysis_day_id=? AND input_fingerprint=?
                """,
                (day_id, result.input_fingerprint),
            ).fetchone()

            created_revision = existing is None
            if existing is None:
                next_revision = int(
                    conn.execute(
                        """
                        SELECT COALESCE(MAX(revision_no),0)+1 AS next_revision
                        FROM stock_analysis_revision
                        WHERE analysis_day_id=?
                        """,
                        (day_id,),
                    ).fetchone()["next_revision"]
                )
                revision_id = str(uuid4())
                reason = self._reason(current, result)
                conn.execute(
                    """
                    INSERT INTO stock_analysis_revision(
                        id,analysis_day_id,revision_no,input_fingerprint,
                        strategy_key,action_state,risk_state,
                        reference_price,stop_price,target1_price,target2_price,
                        scanner_version,analysis_engine_version,policy_version,
                        source_versions_json,snapshot_json,revision_reason,
                        computed_at,created_at
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        revision_id,
                        day_id,
                        next_revision,
                        result.input_fingerprint,
                        result.strategy_key,
                        result.action_state,
                        result.risk_state,
                        _decimal_text(result.reference_price),
                        _decimal_text(result.stop_price),
                        _decimal_text(result.target1_price),
                        _decimal_text(result.target2_price),
                        result.scanner_version,
                        result.analysis_engine_version,
                        result.policy_version,
                        _json_text(result.source_versions),
                        _json_text(result.snapshot),
                        reason,
                        computed_at,
                        now,
                    ),
                )
                existing = conn.execute(
                    "SELECT * FROM stock_analysis_revision WHERE id=?",
                    (revision_id,),
                ).fetchone()

            revision = self._revision_from_row(self.catalog, existing)
            promoted_current = day["current_revision_id"] != revision.id
            if promoted_current:
                cursor = conn.execute(
                    """
                    UPDATE stock_analysis_day
                    SET current_revision_id=?,updated_at=?
                    WHERE id=?
                    """,
                    (revision.id, now, day_id),
                )
                if cursor.rowcount != 1:
                    raise HoldingsAnalysisHistoryError(
                        "HOLD_ANALYSIS_HISTORY_CONFLICT",
                        "현재 Analysis Revision을 저장하지 못했습니다.",
                    )
            conn.commit()
            return StoredAnalysisResult(
                monitored_stock_id=stock.id,
                analysis_day_id=day_id,
                revision=revision,
                created_revision=created_revision,
                promoted_current=promoted_current,
            )
        except sqlite3.IntegrityError as exc:
            conn.rollback()
            raise HoldingsAnalysisHistoryError(
                "HOLD_ANALYSIS_HISTORY_CONFLICT",
                "Analysis Day/Revision 저장 중 충돌이 발생했습니다.",
            ) from exc
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def analyze_and_record(
        self,
        *,
        monitored_stock_id: str,
        market_date: str,
    ) -> StoredAnalysisResult:
        stock = self._stock(monitored_stock_id)
        try:
            result = self.analyzer(
                market=stock.market,
                ticker=stock.ticker,
                market_date=market_date,
                market_store_db=self.market_store_db,
            )
        except HoldingsAnalysisError as exc:
            raise HoldingsAnalysisHistoryError(
                "HOLD_ANALYSIS_HISTORY_FAILED",
                f"종목 분석을 저장하지 못했습니다: {exc}",
                cause_code=getattr(exc, "code", None),
            ) from exc
        except Exception as exc:
            raise HoldingsAnalysisHistoryError(
                "HOLD_ANALYSIS_HISTORY_FAILED",
                f"종목 분석을 저장하지 못했습니다: {exc}",
            ) from exc

        if result.market_date != market_date:
            raise HoldingsAnalysisHistoryError(
                "HOLD_ANALYSIS_HISTORY_DATE_INVALID",
                "요청한 market_date와 실제 분석 market_date가 일치하지 않습니다.",
            )
        computed_at = self.clock()
        return self._store_result(
            stock=stock,
            result=result,
            computed_at=computed_at,
        )

    def latest_confirmed_market_date(
        self,
        monitored_stock_id: str,
    ) -> str:
        stock = self._stock(monitored_stock_id)
        if not self.market_store_db.is_file():
            raise HoldingsAnalysisHistoryError(
                "HOLD_ANALYSIS_HISTORY_DATE_INVALID",
                "Market Store를 찾을 수 없습니다.",
            )
        uri = self.market_store_db.resolve().as_uri() + "?mode=ro"
        try:
            with sqlite3.connect(uri, uri=True) as conn:
                row = conn.execute(
                    """
                    SELECT MAX(s.bas_dd)
                    FROM stock_daily s
                    WHERE s.market=?
                      AND s.stock_code=?
                      AND EXISTS (
                          SELECT 1
                          FROM day_status ds
                          WHERE ds.market=s.market
                            AND ds.bas_dd=s.bas_dd
                            AND ds.kind='stock'
                            AND ds.status='data'
                      )
                      AND EXISTS (
                          SELECT 1
                          FROM day_status di
                          WHERE di.market=s.market
                            AND di.bas_dd=s.bas_dd
                            AND di.kind='index'
                            AND di.status='data'
                      )
                    """,
                    (stock.market, stock.ticker),
                ).fetchone()
        except sqlite3.Error as exc:
            raise HoldingsAnalysisHistoryError(
                "HOLD_ANALYSIS_HISTORY_DATE_INVALID",
                "Market Store에서 최신 확정 거래일을 확인하지 못했습니다.",
            ) from exc
        bas_dd = str(row[0] or "") if row else ""
        if len(bas_dd) != 8 or not bas_dd.isdigit():
            raise HoldingsAnalysisHistoryError(
                "HOLD_ANALYSIS_HISTORY_DATE_INVALID",
                "해당 종목의 확정 EOD 거래일을 찾을 수 없습니다.",
            )
        return f"{bas_dd[:4]}-{bas_dd[4:6]}-{bas_dd[6:8]}"

    def analyze_latest_confirmed(
        self,
        *,
        monitored_stock_id: str,
    ) -> StoredAnalysisResult:
        market_date = self.latest_confirmed_market_date(monitored_stock_id)
        return self.analyze_and_record(
            monitored_stock_id=monitored_stock_id,
            market_date=market_date,
        )

    def list_analysis_targets(self) -> tuple[MonitoredStock, ...]:
        with self.catalog.connection() as conn:
            rows = conn.execute(
                """
                SELECT DISTINCT s.*
                FROM monitored_stock s
                WHERE s.archived_at IS NULL
                  AND (
                      s.watch_enabled=1
                      OR EXISTS (
                          SELECT 1
                          FROM holding_position p
                          WHERE p.monitored_stock_id=s.id
                            AND p.status='OPEN'
                      )
                  )
                ORDER BY s.market,s.ticker
                """
            ).fetchall()
        return tuple(self.catalog._stock_from_row(row) for row in rows)  # noqa: SLF001

    def get_current_analysis(
        self,
        monitored_stock_id: str,
    ) -> StockAnalysisRevision | None:
        self._stock(monitored_stock_id)
        with self.catalog.connection() as conn:
            row = conn.execute(
                """
                SELECT r.*
                FROM stock_analysis_day d
                JOIN stock_analysis_revision r ON r.id=d.current_revision_id
                WHERE d.monitored_stock_id=?
                ORDER BY d.market_date DESC
                LIMIT 1
                """,
                (monitored_stock_id,),
            ).fetchone()
        return self._revision_from_row(self.catalog, row) if row else None

    def get_day_revisions(
        self,
        *,
        monitored_stock_id: str,
        market_date: str,
    ) -> tuple[StockAnalysisRevision, ...]:
        self._stock(monitored_stock_id)
        with self.catalog.connection() as conn:
            rows = conn.execute(
                """
                SELECT r.*
                FROM stock_analysis_day d
                JOIN stock_analysis_revision r ON r.analysis_day_id=d.id
                WHERE d.monitored_stock_id=? AND d.market_date=?
                ORDER BY r.revision_no ASC
                """,
                (monitored_stock_id, market_date),
            ).fetchall()
        return tuple(self._revision_from_row(self.catalog, row) for row in rows)

    def get_analysis_timeline(
        self,
        monitored_stock_id: str,
        *,
        limit: int = 30,
    ) -> tuple[AnalysisTimelineItem, ...]:
        self._stock(monitored_stock_id)
        if limit <= 0:
            return ()
        with self.catalog.connection() as conn:
            rows = conn.execute(
                """
                SELECT d.id AS analysis_day_id,d.market_date,r.*
                FROM stock_analysis_day d
                JOIN stock_analysis_revision r ON r.id=d.current_revision_id
                WHERE d.monitored_stock_id=?
                ORDER BY d.market_date ASC
                """,
                (monitored_stock_id,),
            ).fetchall()

        items: list[AnalysisTimelineItem] = []
        previous: sqlite3.Row | None = None
        for row in rows:
            current_reference = _decimal_value(row["reference_price"])
            current_stop = _decimal_value(row["stop_price"])
            current_target1 = _decimal_value(row["target1_price"])
            current_target2 = _decimal_value(row["target2_price"])

            previous_reference = (
                _decimal_value(previous["reference_price"]) if previous else None
            )
            previous_stop = _decimal_value(previous["stop_price"]) if previous else None
            previous_target1 = (
                _decimal_value(previous["target1_price"]) if previous else None
            )
            previous_target2 = (
                _decimal_value(previous["target2_price"]) if previous else None
            )

            items.append(
                AnalysisTimelineItem(
                    market_date=str(row["market_date"]),
                    analysis_day_id=str(row["analysis_day_id"]),
                    revision_id=str(row["id"]),
                    revision_no=int(row["revision_no"]),
                    computed_at=str(row["computed_at"]),
                    strategy_key=row["strategy_key"],
                    action_state=row["action_state"],
                    risk_state=row["risk_state"],
                    reference_price=current_reference,
                    stop_price=current_stop,
                    target1_price=current_target1,
                    target2_price=current_target2,
                    previous_strategy_key=previous["strategy_key"] if previous else None,
                    previous_action_state=previous["action_state"] if previous else None,
                    previous_risk_state=previous["risk_state"] if previous else None,
                    previous_reference_price=previous_reference,
                    previous_stop_price=previous_stop,
                    previous_target1_price=previous_target1,
                    previous_target2_price=previous_target2,
                    strategy_changed=(
                        previous is not None
                        and previous["strategy_key"] != row["strategy_key"]
                    ),
                    action_changed=(
                        previous is not None
                        and previous["action_state"] != row["action_state"]
                    ),
                    risk_changed=(
                        previous is not None
                        and previous["risk_state"] != row["risk_state"]
                    ),
                    reference_price_changed=(
                        previous is not None
                        and previous_reference != current_reference
                    ),
                    stop_price_changed=(
                        previous is not None and previous_stop != current_stop
                    ),
                    target1_price_changed=(
                        previous is not None
                        and previous_target1 != current_target1
                    ),
                    target2_price_changed=(
                        previous is not None
                        and previous_target2 != current_target2
                    ),
                    reference_price_delta=_delta(current_reference, previous_reference),
                    stop_price_delta=_delta(current_stop, previous_stop),
                    target1_price_delta=_delta(current_target1, previous_target1),
                    target2_price_delta=_delta(current_target2, previous_target2),
                )
            )
            previous = row

        return tuple(reversed(items[-limit:]))

    def get_stock_timeline(
        self,
        monitored_stock_id: str,
        *,
        limit: int = 100,
    ) -> tuple[StockTimelineItem, ...]:
        self._stock(monitored_stock_id)
        if limit <= 0:
            return ()

        analysis_items = self.get_analysis_timeline(
            monitored_stock_id,
            limit=max(limit, 30),
        )
        combined: list[StockTimelineItem] = []
        for item in analysis_items:
            combined.append(
                StockTimelineItem(
                    kind="ANALYSIS",
                    occurred_at=item.computed_at,
                    market_date=item.market_date,
                    analysis_revision_id=item.revision_id,
                    position_id=None,
                    event_type=None,
                    payload={
                        "revision_no": item.revision_no,
                        "strategy_key": item.strategy_key,
                        "action_state": item.action_state,
                        "risk_state": item.risk_state,
                        "reference_price": item.reference_price,
                        "stop_price": item.stop_price,
                        "target1_price": item.target1_price,
                        "target2_price": item.target2_price,
                        "strategy_changed": item.strategy_changed,
                        "action_changed": item.action_changed,
                        "risk_changed": item.risk_changed,
                        "reference_price_delta": item.reference_price_delta,
                    },
                )
            )

        with self.catalog.connection() as conn:
            rows = conn.execute(
                """
                SELECT e.*
                FROM holding_position_event e
                JOIN holding_position p ON p.id=e.position_id
                WHERE p.monitored_stock_id=?
                """,
                (monitored_stock_id,),
            ).fetchall()
        for row in rows:
            occurred_at = (
                str(row["effective_at"] or "")
                or str(row["observed_at"] or "")
                or str(row["created_at"])
            )
            combined.append(
                StockTimelineItem(
                    kind="POSITION_EVENT",
                    occurred_at=occurred_at,
                    market_date=None,
                    analysis_revision_id=row["analysis_revision_id"],
                    position_id=str(row["position_id"]),
                    event_type=str(row["event_type"]),
                    payload={
                        "quantity_delta": _decimal_value(row["quantity_delta"]),
                        "unit_price": _decimal_value(row["unit_price"]),
                        "before_quantity": _decimal_value(row["before_quantity"]),
                        "after_quantity": _decimal_value(row["after_quantity"]),
                        "before_average_price": _decimal_value(
                            row["before_average_price"]
                        ),
                        "after_average_price": _decimal_value(
                            row["after_average_price"]
                        ),
                        "note": row["note"],
                    },
                )
            )

        combined.sort(
            key=lambda item: (_sort_time(item.occurred_at), item.kind),
            reverse=True,
        )
        return tuple(combined[:limit])
