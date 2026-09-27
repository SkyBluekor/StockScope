from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Callable
from uuid import uuid4

from .catalog import HoldingsCatalog


RECOVERY_SCHEMA_VERSION = "VN_P3_S2_RECOVERY_REVIEW_V1"
THESIS_STATES = frozenset({"INTACT", "WEAKENED", "BROKEN", "UNKNOWN"})
REVIEW_ACTIONS = frozenset({"UNDECIDED", "HOLD", "REDUCE", "EXIT", "ADD_REVIEW"})


class HoldingsRecoveryError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_text(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _json_value(raw: str | None, *, fallback: Any) -> Any:
    if raw in (None, ""):
        return fallback
    try:
        return json.loads(str(raw))
    except json.JSONDecodeError:
        return fallback


def _decimal(value: Any, *, code: str, label: str) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise HoldingsRecoveryError(code, f"{label} 값이 올바르지 않습니다.") from exc
    if not number.is_finite():
        raise HoldingsRecoveryError(code, f"{label} 값이 유효하지 않습니다.")
    return number


def _decimal_text(value: Decimal | None) -> str | None:
    return None if value is None else format(value, "f")


@dataclass(frozen=True, slots=True)
class HoldingRecoveryReview:
    id: str
    position_id: str
    status: str
    opened_at: str
    opened_note: str | None
    closed_at: str | None
    close_reason: str | None
    close_note: str | None
    created_at: str
    updated_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "review_id": self.id,
            "position_id": self.position_id,
            "status": self.status,
            "opened_at": self.opened_at,
            "opened_note": self.opened_note,
            "closed_at": self.closed_at,
            "close_reason": self.close_reason,
            "close_note": self.close_note,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass(frozen=True, slots=True)
class HoldingRecoveryAssessment:
    id: str
    review_id: str
    position_id: str
    thesis_state: str
    review_action: str
    reason_note: str | None
    source_analysis_revision_id: str | None
    source_active_plan_id: str | None
    source_active_plan_version: int | None
    source_position_status: str
    source_position_quantity: Decimal
    source_position_average_price: Decimal | None
    valuation_market_date: str | None
    valuation_price: Decimal | None
    unrealized_pnl: Decimal | None
    unrealized_return_pct: Decimal | None
    linked_decision_id: str | None
    limitations: list[Any]
    evidence: dict[str, Any]
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "assessment_id": self.id,
            "review_id": self.review_id,
            "position_id": self.position_id,
            "thesis_state": self.thesis_state,
            "review_action": self.review_action,
            "reason_note": self.reason_note,
            "source_analysis_revision_id": self.source_analysis_revision_id,
            "source_active_plan_id": self.source_active_plan_id,
            "source_active_plan_version": self.source_active_plan_version,
            "source_position_status": self.source_position_status,
            "source_position_quantity": _decimal_text(self.source_position_quantity),
            "source_position_average_price": _decimal_text(
                self.source_position_average_price
            ),
            "valuation_market_date": self.valuation_market_date,
            "valuation_price": _decimal_text(self.valuation_price),
            "unrealized_pnl": _decimal_text(self.unrealized_pnl),
            "unrealized_return_pct": _decimal_text(self.unrealized_return_pct),
            "linked_decision_id": self.linked_decision_id,
            "limitations": self.limitations,
            "evidence": self.evidence,
            "created_at": self.created_at,
        }


class HoldingRecoveryService:
    """Manual Recovery review context. It never creates trades or applies plans."""

    def __init__(
        self,
        catalog: HoldingsCatalog,
        *,
        clock: Callable[[], str] | None = None,
    ) -> None:
        self.catalog = catalog
        self.clock = clock or _now

    @staticmethod
    def _review_from_row(row: sqlite3.Row) -> HoldingRecoveryReview:
        return HoldingRecoveryReview(
            id=str(row["id"]),
            position_id=str(row["position_id"]),
            status=str(row["status"]),
            opened_at=str(row["opened_at"]),
            opened_note=row["opened_note"],
            closed_at=row["closed_at"],
            close_reason=row["close_reason"],
            close_note=row["close_note"],
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
        )

    @staticmethod
    def _assessment_from_row(row: sqlite3.Row) -> HoldingRecoveryAssessment:
        limitations = _json_value(row["limitations_json"], fallback=[])
        evidence = _json_value(row["evidence_json"], fallback={})
        return HoldingRecoveryAssessment(
            id=str(row["id"]),
            review_id=str(row["review_id"]),
            position_id=str(row["position_id"]),
            thesis_state=str(row["thesis_state"]),
            review_action=str(row["review_action"]),
            reason_note=row["reason_note"],
            source_analysis_revision_id=row["source_analysis_revision_id"],
            source_active_plan_id=row["source_active_plan_id"],
            source_active_plan_version=(
                int(row["source_active_plan_version"])
                if row["source_active_plan_version"] is not None
                else None
            ),
            source_position_status=str(row["source_position_status"]),
            source_position_quantity=(
                _decimal(
                    row["source_position_quantity"],
                    code="HOLD_RECOVERY_STORED_QUANTITY_INVALID",
                    label="저장된 수량",
                )
                or Decimal("0")
            ),
            source_position_average_price=_decimal(
                row["source_position_average_price"],
                code="HOLD_RECOVERY_STORED_AVERAGE_PRICE_INVALID",
                label="저장된 평균단가",
            ),
            valuation_market_date=row["valuation_market_date"],
            valuation_price=_decimal(
                row["valuation_price"],
                code="HOLD_RECOVERY_STORED_VALUATION_INVALID",
                label="저장된 평가가격",
            ),
            unrealized_pnl=_decimal(
                row["unrealized_pnl"],
                code="HOLD_RECOVERY_STORED_PNL_INVALID",
                label="저장된 평가손익",
            ),
            unrealized_return_pct=_decimal(
                row["unrealized_return_pct"],
                code="HOLD_RECOVERY_STORED_RETURN_INVALID",
                label="저장된 수익률",
            ),
            linked_decision_id=row["linked_decision_id"],
            limitations=list(limitations) if isinstance(limitations, list) else [],
            evidence=dict(evidence) if isinstance(evidence, dict) else {},
            created_at=str(row["created_at"]),
        )

    @staticmethod
    def _require_ready(conn: sqlite3.Connection) -> None:
        tables = {
            str(row[0])
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        required = {
            "holding_recovery_schema_meta",
            "holding_recovery_review",
            "holding_recovery_assessment",
        }
        if not required.issubset(tables):
            raise HoldingsRecoveryError(
                "HOLD_RECOVERY_MIGRATION_REQUIRED",
                "VN-P3-S2 Recovery migration을 먼저 실행해야 합니다.",
            )
        row = conn.execute(
            """
            SELECT value FROM holding_recovery_schema_meta
            WHERE key='schema_version'
            """
        ).fetchone()
        if row is None or str(row[0]) != RECOVERY_SCHEMA_VERSION:
            raise HoldingsRecoveryError(
                "HOLD_RECOVERY_SCHEMA_UNSUPPORTED",
                "지원하지 않는 Recovery schema version입니다.",
            )

    @staticmethod
    def _position_row(conn: sqlite3.Connection, position_id: str) -> sqlite3.Row:
        row = conn.execute(
            "SELECT * FROM holding_position WHERE id=?",
            (position_id,),
        ).fetchone()
        if row is None:
            raise HoldingsRecoveryError(
                "HOLD_RECOVERY_POSITION_NOT_FOUND",
                "Recovery 검토 대상 Position을 찾을 수 없습니다.",
            )
        return row

    @staticmethod
    def _review_row(conn: sqlite3.Connection, review_id: str) -> sqlite3.Row:
        row = conn.execute(
            "SELECT * FROM holding_recovery_review WHERE id=?",
            (review_id,),
        ).fetchone()
        if row is None:
            raise HoldingsRecoveryError(
                "HOLD_RECOVERY_REVIEW_NOT_FOUND",
                "Recovery 검토 기록을 찾을 수 없습니다.",
            )
        return row

    @staticmethod
    def _latest_analysis_revision_id(
        conn: sqlite3.Connection,
        monitored_stock_id: str,
    ) -> str | None:
        row = conn.execute(
            """
            SELECT d.current_revision_id
            FROM stock_analysis_day d
            WHERE d.monitored_stock_id=?
              AND d.current_revision_id IS NOT NULL
            ORDER BY d.market_date DESC,d.id DESC
            LIMIT 1
            """,
            (monitored_stock_id,),
        ).fetchone()
        return str(row[0]) if row is not None and row[0] is not None else None

    @staticmethod
    def _active_plan_row(
        conn: sqlite3.Connection,
        position_id: str,
    ) -> sqlite3.Row | None:
        return conn.execute(
            """
            SELECT id,plan_version,source_analysis_revision_id
            FROM holding_management_plan
            WHERE position_id=? AND status='ACTIVE'
            LIMIT 1
            """,
            (position_id,),
        ).fetchone()

    @staticmethod
    def _validate_linked_decision(
        conn: sqlite3.Connection,
        *,
        decision_id: str | None,
        position_id: str,
    ) -> str | None:
        if not decision_id:
            return None
        row = conn.execute(
            """
            SELECT id,position_id
            FROM holding_decision_record
            WHERE id=?
            """,
            (decision_id,),
        ).fetchone()
        if row is None:
            raise HoldingsRecoveryError(
                "HOLD_RECOVERY_DECISION_NOT_FOUND",
                "연결할 보유 판단 기록을 찾을 수 없습니다.",
            )
        if str(row["position_id"]) != position_id:
            raise HoldingsRecoveryError(
                "HOLD_RECOVERY_DECISION_POSITION_MISMATCH",
                "다른 Position의 보유 판단은 Recovery 기록에 연결할 수 없습니다.",
            )
        return str(row["id"])

    def start_review(
        self,
        *,
        position_id: str,
        note: str | None = None,
    ) -> dict[str, Any]:
        conn = self.catalog.connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            self._require_ready(conn)
            position = self._position_row(conn, position_id)
            if str(position["status"]) != "OPEN":
                raise HoldingsRecoveryError(
                    "HOLD_RECOVERY_POSITION_NOT_OPEN",
                    "OPEN Position에서만 Recovery 검토를 시작할 수 있습니다.",
                )
            existing = conn.execute(
                """
                SELECT * FROM holding_recovery_review
                WHERE position_id=? AND status='OPEN'
                LIMIT 1
                """,
                (position_id,),
            ).fetchone()
            if existing is not None:
                conn.commit()
                return {
                    "created": False,
                    "review": self._review_from_row(existing).to_dict(),
                }

            now = self.clock()
            review_id = str(uuid4())
            opened_note = (note or "").strip() or None
            conn.execute(
                """
                INSERT INTO holding_recovery_review(
                    id,position_id,status,opened_at,opened_note,
                    closed_at,close_reason,close_note,created_at,updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    review_id,
                    position_id,
                    "OPEN",
                    now,
                    opened_note,
                    None,
                    None,
                    None,
                    now,
                    now,
                ),
            )
            row = self._review_row(conn, review_id)
            conn.commit()
            return {
                "created": True,
                "review": self._review_from_row(row).to_dict(),
            }
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def get_review(self, review_id: str) -> dict[str, Any]:
        with self.catalog.connection() as conn:
            self._require_ready(conn)
            row = self._review_row(conn, review_id)
        return self._review_from_row(row).to_dict()

    def get_open_review(self, position_id: str) -> dict[str, Any] | None:
        with self.catalog.connection() as conn:
            self._require_ready(conn)
            self._position_row(conn, position_id)
            row = conn.execute(
                """
                SELECT * FROM holding_recovery_review
                WHERE position_id=? AND status='OPEN'
                LIMIT 1
                """,
                (position_id,),
            ).fetchone()
        return self._review_from_row(row).to_dict() if row is not None else None

    def list_reviews(self, position_id: str) -> list[dict[str, Any]]:
        with self.catalog.connection() as conn:
            self._require_ready(conn)
            self._position_row(conn, position_id)
            rows = conn.execute(
                """
                SELECT * FROM holding_recovery_review
                WHERE position_id=?
                ORDER BY created_at DESC,id DESC
                """,
                (position_id,),
            ).fetchall()
        return [self._review_from_row(row).to_dict() for row in rows]

    def list_assessments(self, review_id: str) -> list[dict[str, Any]]:
        with self.catalog.connection() as conn:
            self._require_ready(conn)
            self._review_row(conn, review_id)
            rows = conn.execute(
                """
                SELECT * FROM holding_recovery_assessment
                WHERE review_id=?
                ORDER BY created_at,id
                """,
                (review_id,),
            ).fetchall()
        return [self._assessment_from_row(row).to_dict() for row in rows]

    def record_assessment(
        self,
        *,
        review_id: str,
        thesis_state: str,
        review_action: str,
        reason_note: str | None = None,
        linked_decision_id: str | None = None,
        valuation_market_date: str | None = None,
        valuation_price: Decimal | int | float | str | None = None,
        unrealized_pnl: Decimal | int | float | str | None = None,
        unrealized_return_pct: Decimal | int | float | str | None = None,
        limitations: list[Any] | None = None,
        evidence: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        thesis = thesis_state.strip().upper()
        action = review_action.strip().upper()
        if thesis not in THESIS_STATES:
            raise HoldingsRecoveryError(
                "HOLD_RECOVERY_THESIS_STATE_INVALID",
                "지원하지 않는 투자 논리 상태입니다.",
            )
        if action not in REVIEW_ACTIONS:
            raise HoldingsRecoveryError(
                "HOLD_RECOVERY_ACTION_INVALID",
                "지원하지 않는 Recovery 검토 방향입니다.",
            )

        value_price = _decimal(
            valuation_price,
            code="HOLD_RECOVERY_VALUATION_INVALID",
            label="평가가격",
        )
        pnl = _decimal(
            unrealized_pnl,
            code="HOLD_RECOVERY_PNL_INVALID",
            label="평가손익",
        )
        return_pct = _decimal(
            unrealized_return_pct,
            code="HOLD_RECOVERY_RETURN_INVALID",
            label="수익률",
        )

        conn = self.catalog.connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            self._require_ready(conn)
            review = self._review_row(conn, review_id)
            if str(review["status"]) != "OPEN":
                raise HoldingsRecoveryError(
                    "HOLD_RECOVERY_REVIEW_CLOSED",
                    "종료된 Recovery 검토에는 새 판단 기록을 추가할 수 없습니다.",
                )

            position_id = str(review["position_id"])
            position = self._position_row(conn, position_id)
            linked = self._validate_linked_decision(
                conn,
                decision_id=linked_decision_id,
                position_id=position_id,
            )
            analysis_revision_id = self._latest_analysis_revision_id(
                conn,
                str(position["monitored_stock_id"]),
            )
            active_plan = self._active_plan_row(conn, position_id)

            assessment_id = str(uuid4())
            now = self.clock()
            conn.execute(
                """
                INSERT INTO holding_recovery_assessment(
                    id,review_id,position_id,thesis_state,review_action,reason_note,
                    source_analysis_revision_id,source_active_plan_id,
                    source_active_plan_version,source_position_status,
                    source_position_quantity,source_position_average_price,
                    valuation_market_date,valuation_price,unrealized_pnl,
                    unrealized_return_pct,linked_decision_id,
                    limitations_json,evidence_json,created_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    assessment_id,
                    review_id,
                    position_id,
                    thesis,
                    action,
                    (reason_note or "").strip() or None,
                    analysis_revision_id,
                    str(active_plan["id"]) if active_plan is not None else None,
                    (
                        int(active_plan["plan_version"])
                        if active_plan is not None
                        else None
                    ),
                    str(position["status"]),
                    str(position["current_quantity"]),
                    (
                        str(position["current_average_price"])
                        if position["current_average_price"] is not None
                        else None
                    ),
                    (valuation_market_date or "").strip() or None,
                    _decimal_text(value_price),
                    _decimal_text(pnl),
                    _decimal_text(return_pct),
                    linked,
                    _json_text(limitations or []),
                    _json_text(evidence or {}),
                    now,
                ),
            )
            row = conn.execute(
                "SELECT * FROM holding_recovery_assessment WHERE id=?",
                (assessment_id,),
            ).fetchone()
            conn.commit()
            return self._assessment_from_row(row).to_dict()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def close_review(
        self,
        *,
        review_id: str,
        reason: str | None = None,
        note: str | None = None,
    ) -> dict[str, Any]:
        conn = self.catalog.connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            self._require_ready(conn)
            row = self._review_row(conn, review_id)
            if str(row["status"]) == "CLOSED":
                conn.commit()
                return {
                    "closed": False,
                    "review": self._review_from_row(row).to_dict(),
                }

            now = self.clock()
            conn.execute(
                """
                UPDATE holding_recovery_review
                SET status='CLOSED',closed_at=?,close_reason=?,close_note=?,updated_at=?
                WHERE id=? AND status='OPEN'
                """,
                (
                    now,
                    (reason or "").strip() or None,
                    (note or "").strip() or None,
                    now,
                    review_id,
                ),
            )
            closed = self._review_row(conn, review_id)
            conn.commit()
            return {
                "closed": True,
                "review": self._review_from_row(closed).to_dict(),
            }
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
