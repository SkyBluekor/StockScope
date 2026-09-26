from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

from .catalog import HoldingsCatalog
from .chart import HoldingsChartError, HoldingsChartService


class HoldingsManagementError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_time(value: str, *, code: str, label: str) -> datetime:
    raw = (value or "").strip()
    normalized = raw[:-1] + "+00:00" if raw.endswith("Z") else raw
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise HoldingsManagementError(code, f"{label} 시간이 올바르지 않습니다.") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise HoldingsManagementError(code, f"{label}에는 timezone 정보가 필요합니다.")
    return parsed.astimezone(timezone.utc)


def _decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise HoldingsManagementError("HOLD_PLAN_PRICE_INVALID", "관리 계획 가격이 숫자가 아닙니다.") from exc
    if not number.is_finite():
        raise HoldingsManagementError("HOLD_PLAN_PRICE_INVALID", "관리 계획 가격이 유효하지 않습니다.")
    return number


def _decimal_text(value: Decimal | None) -> str | None:
    return None if value is None else format(value, "f")


def management_distance(
    level: Decimal | None,
    price: Decimal | None,
) -> dict[str, str | None]:
    if level is None or price is None or price <= 0:
        return {"amount": None, "pct": None}
    delta = level - price
    return {
        "amount": _decimal_text(delta),
        "pct": _decimal_text(delta / price * Decimal("100")),
    }


@dataclass(frozen=True, slots=True)
class HoldingManagementPlan:
    id: str
    position_id: str
    plan_version: int
    status: str
    source_type: str
    source_analysis_revision_id: str
    reference_price: Decimal | None
    stop_price: Decimal
    target1_price: Decimal | None
    target2_price: Decimal | None
    confirmation_policy: str
    applied_at: str
    change_reason: str | None
    previous_plan_id: str | None
    superseded_at: str | None
    closed_at: str | None
    created_at: str
    updated_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_id": self.id,
            "position_id": self.position_id,
            "version": self.plan_version,
            "status": self.status,
            "source_type": self.source_type,
            "source_analysis_revision_id": self.source_analysis_revision_id,
            "reference_price": _decimal_text(self.reference_price),
            "stop_price": _decimal_text(self.stop_price),
            "target1_price": _decimal_text(self.target1_price),
            "target2_price": _decimal_text(self.target2_price),
            "confirmation_policy": self.confirmation_policy,
            "applied_at": self.applied_at,
            "change_reason": self.change_reason,
            "previous_plan_id": self.previous_plan_id,
            "superseded_at": self.superseded_at,
            "closed_at": self.closed_at,
        }


class HoldingManagementService:
    # Official EOD analysis is only a proposal until explicitly applied.
    def __init__(
        self,
        catalog: HoldingsCatalog,
        *,
        market_store_db: Path | None = None,
        clock: Callable[[], str] | None = None,
    ) -> None:
        self.catalog = catalog
        self.chart = HoldingsChartService(market_store_db)
        self.clock = clock or _now

    @staticmethod
    def _plan_from_row(row: sqlite3.Row) -> HoldingManagementPlan:
        return HoldingManagementPlan(
            id=str(row["id"]),
            position_id=str(row["position_id"]),
            plan_version=int(row["plan_version"]),
            status=str(row["status"]),
            source_type=str(row["source_type"]),
            source_analysis_revision_id=str(row["source_analysis_revision_id"]),
            reference_price=_decimal(row["reference_price"]),
            stop_price=_decimal(row["stop_price"]) or Decimal("0"),
            target1_price=_decimal(row["target1_price"]),
            target2_price=_decimal(row["target2_price"]),
            confirmation_policy=str(row["confirmation_policy"]),
            applied_at=str(row["applied_at"]),
            change_reason=row["change_reason"],
            previous_plan_id=row["previous_plan_id"],
            superseded_at=row["superseded_at"],
            closed_at=row["closed_at"],
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
        )

    def get_active_plan(self, position_id: str) -> HoldingManagementPlan | None:
        with self.catalog.connection() as conn:
            row = conn.execute(
                "SELECT * FROM holding_management_plan WHERE position_id=? AND status='ACTIVE' LIMIT 1",
                (position_id,),
            ).fetchone()
        return self._plan_from_row(row) if row else None

    def list_plans(self, position_id: str) -> list[HoldingManagementPlan]:
        with self.catalog.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM holding_management_plan WHERE position_id=? ORDER BY plan_version,id",
                (position_id,),
            ).fetchall()
        return [self._plan_from_row(row) for row in rows]

    def apply_analysis_plan(
        self,
        *,
        position_id: str,
        analysis_revision_id: str,
        change_reason: str | None = None,
        applied_at: str | None = None,
    ) -> HoldingManagementPlan:
        apply_text = (applied_at or self.clock()).strip()
        apply_dt = _parse_time(apply_text, code="HOLD_PLAN_TIME_INVALID", label="적용 시각")
        reason = (change_reason or "").strip() or None
        conn = self.catalog.connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            position = conn.execute("SELECT * FROM holding_position WHERE id=?", (position_id,)).fetchone()
            if position is None:
                raise HoldingsManagementError("HOLD_POSITION_NOT_FOUND", "관리 계획을 적용할 Position을 찾을 수 없습니다.")
            if position["status"] != "OPEN":
                raise HoldingsManagementError("HOLD_PLAN_POSITION_CLOSED", "종료된 Position에는 관리 계획을 적용할 수 없습니다.")

            revision = conn.execute(
                """
                SELECT r.*,d.monitored_stock_id,d.market_date
                FROM stock_analysis_revision r
                JOIN stock_analysis_day d ON d.id=r.analysis_day_id
                WHERE r.id=?
                """,
                (analysis_revision_id,),
            ).fetchone()
            if revision is None:
                raise HoldingsManagementError("HOLD_ANALYSIS_REVISION_NOT_FOUND", "적용할 Analysis Revision을 찾을 수 없습니다.")
            if str(revision["monitored_stock_id"]) != str(position["monitored_stock_id"]):
                raise HoldingsManagementError("HOLD_PLAN_REVISION_MISMATCH", "다른 종목의 Analysis Revision은 이 Position에 적용할 수 없습니다.")
            revision_dt = _parse_time(str(revision["computed_at"]), code="HOLD_PLAN_REVISION_TIME_INVALID", label="Analysis Revision")
            if revision_dt > apply_dt:
                raise HoldingsManagementError("HOLD_PLAN_REVISION_FROM_FUTURE", "적용 시점 이후에 계산된 Analysis Revision은 사용할 수 없습니다.")

            reference = _decimal(revision["reference_price"])
            stop = _decimal(revision["stop_price"])
            target1 = _decimal(revision["target1_price"])
            target2 = _decimal(revision["target2_price"])
            if stop is None or stop <= 0:
                raise HoldingsManagementError("HOLD_PLAN_NOT_APPLICABLE", "이 Analysis Revision에는 적용 가능한 손절 가격이 없습니다.")
            for label, value in (("1차 목표", target1), ("2차 목표", target2)):
                if value is not None and value <= 0:
                    raise HoldingsManagementError("HOLD_PLAN_NOT_APPLICABLE", f"{label} 가격이 유효하지 않아 계획을 적용할 수 없습니다.")

            active_row = conn.execute(
                "SELECT * FROM holding_management_plan WHERE position_id=? AND status='ACTIVE' LIMIT 1",
                (position_id,),
            ).fetchone()
            if active_row is not None:
                active = self._plan_from_row(active_row)
                if active.source_analysis_revision_id == analysis_revision_id:
                    conn.rollback()
                    return active
                if stop < active.stop_price:
                    raise HoldingsManagementError(
                        "HOLD_PLAN_STOP_LOOSENING_BLOCKED",
                        "새 분석의 손절 기준이 현재 적용 계획보다 낮아 기존 보유 위험 기준을 느슨하게 만들 수 없습니다.",
                    )

            next_version = int(conn.execute(
                "SELECT COALESCE(MAX(plan_version),0)+1 FROM holding_management_plan WHERE position_id=?",
                (position_id,),
            ).fetchone()[0])
            now = self.clock()
            previous_plan_id = str(active_row["id"]) if active_row is not None else None
            if active_row is not None:
                conn.execute(
                    "UPDATE holding_management_plan SET status='SUPERSEDED',superseded_at=?,updated_at=? WHERE id=? AND status='ACTIVE'",
                    (apply_text, now, previous_plan_id),
                )

            plan_id = str(uuid4())
            conn.execute(
                """
                INSERT INTO holding_management_plan(
                    id,position_id,plan_version,status,source_type,source_analysis_revision_id,
                    reference_price,stop_price,target1_price,target2_price,confirmation_policy,
                    applied_at,change_reason,previous_plan_id,superseded_at,closed_at,created_at,updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    plan_id, position_id, next_version, "ACTIVE", "ANALYSIS_REVISION", analysis_revision_id,
                    _decimal_text(reference), _decimal_text(stop), _decimal_text(target1), _decimal_text(target2),
                    "EOD_CONFIRMED", apply_text, reason, previous_plan_id, None, None, now, now,
                ),
            )
            row = conn.execute("SELECT * FROM holding_management_plan WHERE id=?", (plan_id,)).fetchone()
            conn.commit()
            return self._plan_from_row(row)
        except sqlite3.IntegrityError as exc:
            conn.rollback()
            raise HoldingsManagementError("HOLD_PLAN_CONFLICT", "관리 계획을 저장하는 동안 원장 충돌이 발생했습니다.") from exc
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _latest_revision(self, stock_id: str) -> sqlite3.Row | None:
        with self.catalog.connection() as conn:
            return conn.execute(
                """
                SELECT r.*,d.market_date,d.monitored_stock_id
                FROM stock_analysis_day d
                JOIN stock_analysis_revision r ON r.id=d.current_revision_id
                WHERE d.monitored_stock_id=?
                ORDER BY d.market_date DESC
                LIMIT 1
                """,
                (stock_id,),
            ).fetchone()

    def _valuation(self, market: str, ticker: str) -> dict[str, Any]:
        try:
            series = self.chart.load(market=market, ticker=ticker, chart_range="1m")
        except HoldingsChartError as error:
            return {"available": False, "market_date": None, "price": None, "source": None, "message": error.message}
        latest = series.bars[-1]
        return {"available": True, "market_date": latest.date, "price": latest.close, "source": series.source, "message": None}

    @staticmethod
    def _distance(level: Decimal | None, price: Decimal | None) -> dict[str, str | None]:
        return management_distance(level, price)

    @staticmethod
    def _state(active: HoldingManagementPlan | None, price: Decimal | None) -> str:
        if active is None:
            return "NO_ACTIVE_PLAN"
        if price is None:
            return "DATA_UNAVAILABLE"
        if price <= active.stop_price:
            return "STOP_BREACHED"
        if active.target2_price is not None and price >= active.target2_price:
            return "TARGET2_REACHED"
        if active.target1_price is not None and price >= active.target1_price:
            return "TARGET1_REACHED"
        return "WITHIN_PLAN"

    @staticmethod
    def _proposal(latest: sqlite3.Row | None, active: HoldingManagementPlan | None) -> dict[str, Any]:
        if latest is None:
            return {"state": "NONE", "can_apply": False, "reason": "최신 EOD 분석이 없습니다.", "analysis_revision_id": None}
        reference = _decimal(latest["reference_price"])
        stop = _decimal(latest["stop_price"])
        target1 = _decimal(latest["target1_price"])
        target2 = _decimal(latest["target2_price"])
        payload: dict[str, Any] = {
            "state": "NEW_REVISION", "can_apply": True, "reason": None,
            "analysis_revision_id": latest["id"], "market_date": latest["market_date"],
            "action_state": latest["action_state"], "reference_price": _decimal_text(reference),
            "stop_price": _decimal_text(stop), "target1_price": _decimal_text(target1),
            "target2_price": _decimal_text(target2),
            "deltas": {"reference_price": None, "stop_price": None, "target1_price": None, "target2_price": None},
        }
        if stop is None or stop <= 0:
            payload.update({"state": "NOT_APPLICABLE", "can_apply": False, "reason": "최신 분석에 적용 가능한 손절 가격이 없습니다."})
            return payload
        if active is not None:
            if active.source_analysis_revision_id == str(latest["id"]):
                payload.update({"state": "SAME_AS_ACTIVE", "can_apply": False, "reason": "현재 적용 계획이 이미 최신 분석을 사용하고 있습니다."})
            elif stop < active.stop_price:
                payload.update({"can_apply": False, "reason": "새 분석의 손절 기준이 현재 계획보다 낮아 위험 기준을 느슨하게 만들 수 없습니다."})
            def delta(new: Decimal | None, old: Decimal | None) -> str | None:
                return None if new is None or old is None else _decimal_text(new - old)
            payload["deltas"] = {
                "reference_price": delta(reference, active.reference_price),
                "stop_price": delta(stop, active.stop_price),
                "target1_price": delta(target1, active.target1_price),
                "target2_price": delta(target2, active.target2_price),
            }
        return payload

    def build(self, stock_id: str) -> dict[str, Any]:
        stock = self.catalog.get_monitored_stock(stock_id)
        if stock is None:
            raise HoldingsManagementError("HOLD_STOCK_NOT_FOUND", "등록된 종목을 찾을 수 없습니다.")
        valuation = self._valuation(stock.market, stock.ticker)
        price = _decimal(valuation["price"]) if valuation["available"] else None
        latest = self._latest_revision(stock.id)
        rows: list[dict[str, Any]] = []
        for position in self.catalog.list_positions(stock.id, status="OPEN"):
            account = self.catalog.get_position_account(position.position_account_id)
            active = self.get_active_plan(position.id)
            rows.append({
                "position_id": position.id,
                "account_id": position.position_account_id,
                "account_name": account.display_name if account else None,
                "provider": account.provider if account else None,
                "management_state": self._state(active, price),
                "active_plan": active.to_dict() if active else None,
                "distances": {
                    "stop": self._distance(active.stop_price if active else None, price),
                    "target1": self._distance(active.target1_price if active else None, price),
                    "target2": self._distance(active.target2_price if active else None, price),
                },
                "proposal": self._proposal(latest, active),
            })
        return {"stock_id": stock.id, "market": stock.market, "ticker": stock.ticker, "valuation": valuation, "positions": rows}
