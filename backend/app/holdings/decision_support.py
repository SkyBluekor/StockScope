from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

from app.horizon import HorizonPolicyError, require_horizon_activatable
from app.horizon_context import get_analysis_horizon

from .catalog import HoldingsCatalog
from .chart import HoldingsChartError, HoldingsChartService
from .management import (
    HoldingManagementService,
    HoldingsManagementError,
)

HOLDING_DECISION_SCHEMA_VERSION = "VN_P3_S1_HOLDING_DECISION_STORAGE_V1"
HOLDING_DECISION_POLICY_VERSION = "VN_P3_S1_HOLDING_DECISION_POLICY_V1"
HOLDING_PLAN_CONTEXT_VERSION = "VN_P3_S1_PLAN_CONTEXT_V1"

DECISION_TABLES = {
    "holding_decision_schema_meta",
    "holding_decision_record",
    "holding_decision_resolution",
    "holding_management_plan_context_vnp3s1",
}

ACTIONS = {"HOLD", "ADD", "REDUCE", "TAKE_PROFIT", "STOP", "EXIT"}
RESOLUTION_TYPES = {
    "KEEP_CURRENT_PLAN",
    "APPLY_NEW_PLAN",
    "ACKNOWLEDGED",
    "DEFERRED",
}


class HoldingsDecisionSupportError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _decimal(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return number if number.is_finite() else None


def _decimal_text(value: Any) -> str | None:
    number = _decimal(value)
    return None if number is None else format(number, "f")


def _canonical(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def _fingerprint(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _json(raw: Any) -> Any:
    if raw in (None, ""):
        return None
    if isinstance(raw, (dict, list)):
        return raw
    return json.loads(str(raw))


class HoldingDecisionSupportService:
    """Persisted EOD holdings decision support above immutable ledger/plan state."""

    def __init__(
        self,
        catalog: HoldingsCatalog,
        *,
        market_store_db: Path | None = None,
        clock: Callable[[], str] | None = None,
    ) -> None:
        self.catalog = catalog
        self.chart = HoldingsChartService(market_store_db)
        self.management = HoldingManagementService(
            catalog,
            market_store_db=market_store_db,
            clock=clock,
        )
        self.clock = clock or _now

    @staticmethod
    def _table_names(conn: sqlite3.Connection) -> set[str]:
        return {
            str(row[0])
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }

    def require_ready(self, conn: sqlite3.Connection | None = None) -> None:
        owns = conn is None
        active = conn or self.catalog.connect()
        try:
            if not DECISION_TABLES.issubset(self._table_names(active)):
                raise HoldingsDecisionSupportError(
                    "HOLD_DECISION_MIGRATION_REQUIRED",
                    "VN-P3-S1 Holdings decision migration을 먼저 실행해야 합니다.",
                )
            row = active.execute(
                """
                SELECT value FROM holding_decision_schema_meta
                WHERE key='schema_version'
                """
            ).fetchone()
            if (
                row is None
                or str(row[0]) != HOLDING_DECISION_SCHEMA_VERSION
            ):
                raise HoldingsDecisionSupportError(
                    "HOLD_DECISION_SCHEMA_UNSUPPORTED",
                    "지원하지 않는 Holdings decision schema version입니다.",
                )
        finally:
            if owns:
                active.close()

    def _valuation(self, market: str, ticker: str) -> dict[str, Any]:
        try:
            series = self.chart.load(
                market=market,
                ticker=ticker,
                chart_range="1m",
            )
        except HoldingsChartError as exc:
            return {
                "available": False,
                "market_date": None,
                "price": None,
                "source": None,
                "message": exc.message,
            }
        latest = series.bars[-1]
        return {
            "available": True,
            "market_date": latest.date,
            "price": latest.close,
            "source": series.source,
            "message": None,
        }

    @staticmethod
    def _latest_revision(
        conn: sqlite3.Connection,
        monitored_stock_id: str,
    ) -> sqlite3.Row | None:
        return conn.execute(
            """
            SELECT r.*,d.market_date,d.monitored_stock_id
            FROM stock_analysis_day d
            JOIN stock_analysis_revision r ON r.id=d.current_revision_id
            WHERE d.monitored_stock_id=?
            ORDER BY d.market_date DESC
            LIMIT 1
            """,
            (monitored_stock_id,),
        ).fetchone()

    @staticmethod
    def _active_plan(
        conn: sqlite3.Connection,
        position_id: str,
    ) -> sqlite3.Row | None:
        return conn.execute(
            """
            SELECT * FROM holding_management_plan
            WHERE position_id=? AND status='ACTIVE'
            LIMIT 1
            """,
            (position_id,),
        ).fetchone()

    @staticmethod
    def _plan_state(
        active: sqlite3.Row | None,
        price: Decimal | None,
    ) -> str:
        if active is None:
            return "NO_ACTIVE_PLAN"
        if price is None:
            return "DATA_UNAVAILABLE"
        stop = _decimal(active["stop_price"])
        target1 = _decimal(active["target1_price"])
        target2 = _decimal(active["target2_price"])
        if stop is not None and price <= stop:
            return "STOP_BREACHED"
        if target2 is not None and price >= target2:
            return "TARGET2_REACHED"
        if target1 is not None and price >= target1:
            return "TARGET1_REACHED"
        return "WITHIN_PLAN"

    @staticmethod
    def _horizon_payload(
        conn: sqlite3.Connection,
        revision_id: str | None,
    ) -> tuple[dict[str, Any] | None, bool, str | None]:
        if revision_id is None:
            return None, False, "ANALYSIS_UNAVAILABLE"
        context = get_analysis_horizon(conn, revision_id)
        payload = context.to_dict()
        try:
            require_horizon_activatable(context)
        except HorizonPolicyError as exc:
            return payload, False, exc.code
        return payload, True, None

    @staticmethod
    def _proposal_conflict(
        latest: sqlite3.Row | None,
        active: sqlite3.Row | None,
    ) -> str | None:
        if latest is None or active is None:
            return None
        if str(active["source_analysis_revision_id"]) == str(latest["id"]):
            return None
        new_stop = _decimal(latest["stop_price"])
        active_stop = _decimal(active["stop_price"])
        if (
            new_stop is not None
            and active_stop is not None
            and new_stop < active_stop
        ):
            return "STOP_LOOSENING_BLOCKED"
        return None

    @staticmethod
    def _action_options(
        plan_state: str,
        *,
        has_active_plan: bool,
        data_ready: bool,
    ) -> list[dict[str, Any]]:
        def option(action: str, state: str, reason: str) -> dict[str, str]:
            return {"action": action, "state": state, "reason": reason}

        options: list[dict[str, Any]] = []
        if not data_ready:
            options.append(
                option(
                    "HOLD",
                    "DEFERRED",
                    "확정 EOD 또는 최신 분석이 부족해 보유 판단을 확정하지 않습니다.",
                )
            )
        elif plan_state == "STOP_BREACHED":
            options.extend(
                [
                    option(
                        "STOP",
                        "AVAILABLE",
                        "현재 확정 EOD 가격이 적용 중인 손절 기준 이하입니다.",
                    ),
                    option(
                        "REDUCE",
                        "REVIEW",
                        "전량 종료 대신 일부 축소는 사용자가 별도로 검토할 수 있습니다.",
                    ),
                    option(
                        "EXIT",
                        "REVIEW",
                        "전량 종료 여부는 사용자 선택이며 자동 주문하지 않습니다.",
                    ),
                ]
            )
        elif plan_state == "TARGET2_REACHED":
            options.extend(
                [
                    option(
                        "TAKE_PROFIT",
                        "AVAILABLE",
                        "현재 확정 EOD 가격이 적용 중인 2차 목표 이상입니다.",
                    ),
                    option(
                        "EXIT",
                        "REVIEW",
                        "전량 이익 실현 여부는 사용자가 검토합니다.",
                    ),
                    option(
                        "HOLD",
                        "REVIEW",
                        "기존 계획을 유지할 수도 있지만 목표 도달 상태를 먼저 확인해야 합니다.",
                    ),
                ]
            )
        elif plan_state == "TARGET1_REACHED":
            options.extend(
                [
                    option(
                        "TAKE_PROFIT",
                        "AVAILABLE",
                        "현재 확정 EOD 가격이 적용 중인 1차 목표 이상입니다.",
                    ),
                    option(
                        "REDUCE",
                        "REVIEW",
                        "일부 이익 실현은 검토할 수 있으나 비율은 자동 결정하지 않습니다.",
                    ),
                    option(
                        "HOLD",
                        "REVIEW",
                        "기존 계획을 유지할 수 있으나 목표 도달 상태를 확인해야 합니다.",
                    ),
                ]
            )
        elif has_active_plan:
            options.append(
                option(
                    "HOLD",
                    "AVAILABLE",
                    "현재 확정 EOD 가격이 적용 중인 손절·목표 범위 안에 있습니다.",
                )
            )
            options.append(
                option(
                    "REDUCE",
                    "MANUAL_REVIEW",
                    "일부 축소는 사용자가 검토할 수 있으나 자동 비율 정책은 없습니다.",
                )
            )
        else:
            options.append(
                option(
                    "HOLD",
                    "REVIEW",
                    "현재 적용된 관리 계획이 없어 새 계획 적용 여부를 먼저 검토해야 합니다.",
                )
            )

        options.append(
            option(
                "ADD",
                "BLOCKED",
                "추가매수를 허용할 검증된 P3-S1 정책이 아직 정의되지 않았습니다.",
            )
        )
        present = {str(item["action"]) for item in options}
        for action in ("STOP", "TAKE_PROFIT", "EXIT"):
            if action not in present:
                options.append(
                    option(
                        action,
                        "NOT_TRIGGERED",
                        "현재 적용 계획의 명시 조건에서 해당 행동이 발생하지 않았습니다.",
                    )
                )
        return options

    def _current_source(
        self,
        position_id: str,
    ) -> dict[str, Any]:
        conn = self.catalog.connect()
        try:
            self.require_ready(conn)
            position = conn.execute(
                "SELECT * FROM holding_position WHERE id=?",
                (position_id,),
            ).fetchone()
            if position is None:
                raise HoldingsDecisionSupportError(
                    "HOLD_POSITION_NOT_FOUND",
                    "보유 Position을 찾을 수 없습니다.",
                )
            stock = conn.execute(
                "SELECT * FROM monitored_stock WHERE id=?",
                (position["monitored_stock_id"],),
            ).fetchone()
            if stock is None:
                raise HoldingsDecisionSupportError(
                    "HOLD_STOCK_NOT_FOUND",
                    "Position의 종목 정보를 찾을 수 없습니다.",
                )
            latest = self._latest_revision(
                conn,
                str(position["monitored_stock_id"]),
            )
            active = self._active_plan(conn, position_id)
            horizon, horizon_activatable, horizon_reason = self._horizon_payload(
                conn,
                str(latest["id"]) if latest is not None else None,
            )
        finally:
            conn.close()

        from app.data_contract.builder import build_stock_data_contract
        from app.data_contract.reader import ReadOnlyDataStateReader

        valuation = self._valuation(str(stock["market"]), str(stock["ticker"]))
        price = _decimal(valuation["price"]) if valuation["available"] else None
        plan_state = self._plan_state(active, price)

        data_state = ReadOnlyDataStateReader(
            market_store_db=self.chart.market_store_db,
            holdings_db=self.catalog.db_path,
        ).read_stock_state(str(stock["market"]), str(stock["ticker"]))
        analysis_contract = build_stock_data_contract(
            data_state,
            chart_range=None,
        ).resources.analysis_result
        analysis_current_use_allowed = bool(
            latest is not None
            and analysis_contract.revision_id == str(latest["id"])
            and analysis_contract.current_use_allowed
        )
        proposal_ready = (
            str(position["status"]) == "OPEN"
            and valuation["available"]
            and analysis_current_use_allowed
        )
        protection_ready = (
            str(position["status"]) == "OPEN"
            and valuation["available"]
            and active is not None
        )
        data_ready = proposal_ready or protection_ready
        conflict = (
            self._proposal_conflict(latest, active)
            if proposal_ready
            else None
        )
        limitations: list[dict[str, str]] = []
        if latest is None:
            limitations.append(
                {
                    "code": "ANALYSIS_UNAVAILABLE",
                    "message": "최신 확정 EOD 분석이 없습니다.",
                }
            )
        elif not analysis_current_use_allowed:
            limitations.append(
                {
                    "code": str(
                        analysis_contract.reason_code
                        or "ANALYSIS_CURRENT_USE_NOT_ALLOWED"
                    ),
                    "message": "저장된 분석은 표시할 수 있지만 현재 새 판단·계획 제안의 근거로 사용할 수 없습니다.",
                }
            )
        if not valuation["available"]:
            limitations.append(
                {
                    "code": "VALUATION_UNAVAILABLE",
                    "message": str(
                        valuation["message"]
                        or "확정 EOD 평가가격을 사용할 수 없습니다."
                    ),
                }
            )
        if latest is not None and not horizon_activatable:
            limitations.append(
                {
                    "code": str(horizon_reason or "HORIZON_NOT_ACTIVE"),
                    "message": "현재 Horizon 문맥은 새 관리 계획 적용 정책이 아직 승인되지 않았습니다.",
                }
            )
        limitations.append(
            {
                "code": "ADD_POLICY_UNDEFINED",
                "message": "추가매수 정책·비율·금액은 P3-S1에서 정의하지 않습니다.",
            }
        )
        limitations.append(
            {
                "code": "ACCOUNT_EXPOSURE_PARTIAL",
                "message": "StockScope가 관측하지 않는 현금·계좌·자산을 전체 자산으로 추정하지 않습니다.",
            }
        )

        if str(position["status"]) != "OPEN":
            status = "DEFERRED"
            primary_action = None
        elif protection_ready and plan_state == "STOP_BREACHED":
            status = "ACTIONABLE"
            primary_action = "STOP"
        elif proposal_ready and conflict:
            status = "CONFLICT"
            primary_action = None
        elif protection_ready and plan_state in {"TARGET1_REACHED", "TARGET2_REACHED"}:
            status = "REVIEW_REQUIRED"
            primary_action = "TAKE_PROFIT"
        elif active is not None and protection_ready:
            status = "ACTIONABLE"
            primary_action = "HOLD"
        elif not proposal_ready:
            status = "INSUFFICIENT_DATA"
            primary_action = None
        elif active is None:
            status = "DEFERRED" if not horizon_activatable else "REVIEW_REQUIRED"
            primary_action = None
        else:
            status = "ACTIONABLE"
            primary_action = "HOLD"

        latest_id = str(latest["id"]) if latest is not None else None
        active_id = str(active["id"]) if active is not None else None
        active_version = (
            int(active["plan_version"]) if active is not None else None
        )
        horizon_intent = (
            str(horizon.get("intent")) if horizon else None
        )
        horizon_policy_version = (
            str(horizon.get("policy_version"))
            if horizon and horizon.get("policy_version") is not None
            else None
        )
        source = {
            "position_id": str(position["id"]),
            "monitored_stock_id": str(position["monitored_stock_id"]),
            "position_status": str(position["status"]),
            "position_quantity": str(position["current_quantity"]),
            "position_average_price": (
                str(position["current_average_price"])
                if position["current_average_price"] is not None
                else None
            ),
            "analysis_revision_id": latest_id,
            "analysis_market_date": (
                str(latest["market_date"]) if latest is not None else None
            ),
            "analysis_strategy": (
                str(latest["strategy_key"])
                if latest is not None and latest["strategy_key"] is not None
                else None
            ),
            "analysis_action_state": (
                str(latest["action_state"])
                if latest is not None and latest["action_state"] is not None
                else None
            ),
            "analysis_risk_state": (
                str(latest["risk_state"])
                if latest is not None and latest["risk_state"] is not None
                else None
            ),
            "analysis_stop_price": (
                str(latest["stop_price"])
                if latest is not None and latest["stop_price"] is not None
                else None
            ),
            "analysis_target1_price": (
                str(latest["target1_price"])
                if latest is not None and latest["target1_price"] is not None
                else None
            ),
            "analysis_target2_price": (
                str(latest["target2_price"])
                if latest is not None and latest["target2_price"] is not None
                else None
            ),
            "active_plan_id": active_id,
            "active_plan_version": active_version,
            "active_plan_source_revision_id": (
                str(active["source_analysis_revision_id"])
                if active is not None
                else None
            ),
            "active_stop_price": (
                str(active["stop_price"]) if active is not None else None
            ),
            "active_target1_price": (
                str(active["target1_price"])
                if active is not None and active["target1_price"] is not None
                else None
            ),
            "active_target2_price": (
                str(active["target2_price"])
                if active is not None and active["target2_price"] is not None
                else None
            ),
            "valuation_market_date": valuation["market_date"],
            "valuation_price": valuation["price"],
            "valuation_source": valuation["source"],
            "horizon": horizon,
            "analysis_current_use_allowed": analysis_current_use_allowed,
            "analysis_contract_status": analysis_contract.status,
            "analysis_contract_reason_code": analysis_contract.reason_code,
        }
        evidence = {
            "plan_state": plan_state,
            "proposal_ready": proposal_ready,
            "protection_ready": protection_ready,
            "proposal_conflict": conflict,
            "latest_analysis_differs_from_active_plan": bool(
                latest_id
                and active is not None
                and str(active["source_analysis_revision_id"]) != latest_id
            ),
            "new_plan_horizon_activatable": horizon_activatable,
            "source": source,
        }
        alternatives = self._action_options(
            plan_state,
            has_active_plan=active is not None,
            data_ready=data_ready,
        )
        fingerprint_payload = {
            "decision_policy_version": HOLDING_DECISION_POLICY_VERSION,
            "source": source,
            "status": status,
            "primary_action": primary_action,
            "conflict": conflict,
        }
        return {
            "position": position,
            "stock": stock,
            "latest": latest,
            "active": active,
            "valuation": valuation,
            "horizon": horizon,
            "status": status,
            "primary_action": primary_action,
            "evidence": evidence,
            "alternatives": alternatives,
            "limitations": limitations,
            "input_fingerprint": _fingerprint(fingerprint_payload),
        }

    @staticmethod
    def _decision_from_row(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "decision_id": str(row["id"]),
            "position_id": str(row["position_id"]),
            "decision_policy_version": str(row["decision_policy_version"]),
            "status": str(row["status"]),
            "primary_action": row["primary_action"],
            "source_analysis_revision_id": row["source_analysis_revision_id"],
            "source_active_plan_id": row["source_active_plan_id"],
            "source_active_plan_version": row["source_active_plan_version"],
            "source_position_status": str(row["source_position_status"]),
            "source_position_quantity": str(row["source_position_quantity"]),
            "source_position_average_price": row["source_position_average_price"],
            "valuation_market_date": row["valuation_market_date"],
            "valuation_price": row["valuation_price"],
            "valuation_source": row["valuation_source"],
            "horizon_intent": row["horizon_intent"],
            "horizon_policy_version": row["horizon_policy_version"],
            "input_fingerprint": str(row["input_fingerprint"]),
            "evidence": _json(row["evidence_json"]) or {},
            "alternatives": _json(row["alternatives_json"]) or [],
            "limitations": _json(row["limitations_json"]) or [],
            "created_at": str(row["created_at"]),
        }

    def evaluate(self, position_id: str) -> dict[str, Any]:
        source = self._current_source(position_id)
        conn = self.catalog.connect()
        try:
            self.require_ready(conn)
            conn.execute("BEGIN IMMEDIATE")
            existing = conn.execute(
                """
                SELECT * FROM holding_decision_record
                WHERE position_id=? AND input_fingerprint=?
                ORDER BY created_at DESC,id DESC
                LIMIT 1
                """,
                (position_id, source["input_fingerprint"]),
            ).fetchone()
            if existing is not None:
                payload = self._decision_from_row(existing)
                payload["reused"] = True
                payload["stale"] = False
                payload["stale_reasons"] = []
                conn.rollback()
                return payload

            decision_id = str(uuid4())
            horizon = source["horizon"] or {}
            conn.execute(
                """
                INSERT INTO holding_decision_record(
                    id,position_id,decision_policy_version,status,primary_action,
                    source_analysis_revision_id,source_active_plan_id,
                    source_active_plan_version,source_position_status,
                    source_position_quantity,source_position_average_price,
                    valuation_market_date,valuation_price,valuation_source,
                    horizon_intent,horizon_policy_version,input_fingerprint,
                    evidence_json,alternatives_json,limitations_json,created_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    decision_id,
                    position_id,
                    HOLDING_DECISION_POLICY_VERSION,
                    source["status"],
                    source["primary_action"],
                    (
                        str(source["latest"]["id"])
                        if source["latest"] is not None else None
                    ),
                    (
                        str(source["active"]["id"])
                        if source["active"] is not None else None
                    ),
                    (
                        int(source["active"]["plan_version"])
                        if source["active"] is not None else None
                    ),
                    str(source["position"]["status"]),
                    str(source["position"]["current_quantity"]),
                    (
                        str(source["position"]["current_average_price"])
                        if source["position"]["current_average_price"] is not None
                        else None
                    ),
                    source["valuation"]["market_date"],
                    source["valuation"]["price"],
                    source["valuation"]["source"],
                    horizon.get("intent"),
                    horizon.get("policy_version"),
                    source["input_fingerprint"],
                    _canonical(source["evidence"]),
                    _canonical(source["alternatives"]),
                    _canonical(source["limitations"]),
                    self.clock(),
                ),
            )
            row = conn.execute(
                "SELECT * FROM holding_decision_record WHERE id=?",
                (decision_id,),
            ).fetchone()
            conn.commit()
            payload = self._decision_from_row(row)
            payload["reused"] = False
            payload["stale"] = False
            payload["stale_reasons"] = []
            return payload
        except sqlite3.IntegrityError as exc:
            conn.rollback()
            raise HoldingsDecisionSupportError(
                "HOLD_DECISION_CONFLICT",
                "보유 판단을 저장하는 동안 충돌이 발생했습니다.",
            ) from exc
        finally:
            conn.close()

    def _stale_reasons(
        self,
        decision: dict[str, Any],
        current: dict[str, Any],
    ) -> list[str]:
        reasons: list[str] = []
        position = current["position"]
        latest = current["latest"]
        active = current["active"]
        valuation = current["valuation"]

        if str(position["status"]) != decision["source_position_status"]:
            reasons.append("POSITION_STATUS_CHANGED")
        if str(position["current_quantity"]) != decision["source_position_quantity"]:
            reasons.append("POSITION_QUANTITY_CHANGED")
        current_avg = (
            str(position["current_average_price"])
            if position["current_average_price"] is not None else None
        )
        if current_avg != decision["source_position_average_price"]:
            reasons.append("POSITION_AVERAGE_PRICE_CHANGED")

        current_revision_id = str(latest["id"]) if latest is not None else None
        if current_revision_id != decision["source_analysis_revision_id"]:
            reasons.append("ANALYSIS_REVISION_CHANGED")

        current_plan_id = str(active["id"]) if active is not None else None
        current_plan_version = (
            int(active["plan_version"]) if active is not None else None
        )
        if current_plan_id != decision["source_active_plan_id"]:
            reasons.append("ACTIVE_PLAN_CHANGED")
        elif current_plan_version != decision["source_active_plan_version"]:
            reasons.append("ACTIVE_PLAN_VERSION_CHANGED")

        if valuation["market_date"] != decision["valuation_market_date"]:
            reasons.append("VALUATION_DATE_CHANGED")
        elif (
            _decimal_text(valuation["price"])
            != _decimal_text(decision["valuation_price"])
        ):
            reasons.append("VALUATION_PRICE_CHANGED")
        return reasons

    def get_decision(self, decision_id: str) -> dict[str, Any]:
        conn = self.catalog.connect()
        try:
            self.require_ready(conn)
            row = conn.execute(
                "SELECT * FROM holding_decision_record WHERE id=?",
                (decision_id,),
            ).fetchone()
            if row is None:
                raise HoldingsDecisionSupportError(
                    "HOLD_DECISION_NOT_FOUND",
                    "보유 판단 기록을 찾을 수 없습니다.",
                )
            decision = self._decision_from_row(row)
            resolutions = [
                {
                    "resolution_id": str(item["id"]),
                    "selected_action": item["selected_action"],
                    "resolution_type": str(item["resolution_type"]),
                    "note": item["note"],
                    "resulting_plan_id": item["resulting_plan_id"],
                    "created_at": str(item["created_at"]),
                }
                for item in conn.execute(
                    """
                    SELECT * FROM holding_decision_resolution
                    WHERE decision_id=?
                    ORDER BY created_at,id
                    """,
                    (decision_id,),
                ).fetchall()
            ]
        finally:
            conn.close()
        current = self._current_source(decision["position_id"])
        reasons = self._stale_reasons(decision, current)
        decision["stale"] = bool(reasons)
        decision["stale_reasons"] = reasons
        decision["effective_status"] = "STALE" if reasons else decision["status"]
        decision["resolutions"] = resolutions
        return decision

    def latest_for_stock(self, stock_id: str) -> dict[str, Any]:
        stock = self.catalog.get_monitored_stock(stock_id)
        if stock is None:
            raise HoldingsDecisionSupportError(
                "HOLD_STOCK_NOT_FOUND",
                "등록된 종목을 찾을 수 없습니다.",
            )
        positions = self.catalog.list_positions(stock_id, status="OPEN")
        results: list[dict[str, Any]] = []
        conn = self.catalog.connect()
        try:
            self.require_ready(conn)
            for position in positions:
                row = conn.execute(
                    """
                    SELECT * FROM holding_decision_record
                    WHERE position_id=?
                    ORDER BY created_at DESC,id DESC
                    LIMIT 1
                    """,
                    (position.id,),
                ).fetchone()
                if row is None:
                    results.append(
                        {
                            "position_id": position.id,
                            "decision": None,
                        }
                    )
                    continue
                results.append(
                    {
                        "position_id": position.id,
                        "decision": self._decision_from_row(row),
                    }
                )
        finally:
            conn.close()

        for item in results:
            decision = item["decision"]
            if decision is None:
                continue
            current = self._current_source(item["position_id"])
            reasons = self._stale_reasons(decision, current)
            decision["stale"] = bool(reasons)
            decision["stale_reasons"] = reasons
            decision["effective_status"] = (
                "STALE" if reasons else decision["status"]
            )
        return {
            "stock_id": stock.id,
            "market": stock.market,
            "ticker": stock.ticker,
            "positions": results,
        }

    @staticmethod
    def _find_action(
        decision: dict[str, Any],
        action: str | None,
    ) -> dict[str, Any] | None:
        if action is None:
            return None
        for item in decision["alternatives"]:
            if str(item.get("action")) == action:
                return item
        return None

    def resolve(
        self,
        *,
        decision_id: str,
        resolution_type: str,
        selected_action: str | None,
        note: str | None = None,
    ) -> dict[str, Any]:
        resolution = resolution_type.strip().upper()
        action = selected_action.strip().upper() if selected_action else None
        if resolution not in RESOLUTION_TYPES - {"APPLY_NEW_PLAN"}:
            raise HoldingsDecisionSupportError(
                "HOLD_DECISION_RESOLUTION_INVALID",
                "이 API에서는 계획 적용 외의 resolution만 저장할 수 있습니다.",
            )
        if action is not None and action not in ACTIONS:
            raise HoldingsDecisionSupportError(
                "HOLD_DECISION_ACTION_INVALID",
                "지원하지 않는 보유 행동입니다.",
            )

        decision = self.get_decision(decision_id)
        if decision["stale"]:
            raise HoldingsDecisionSupportError(
                "HOLD_DECISION_STALE",
                "보유 상태가 변경되었습니다. 최신 판단을 다시 확인하세요.",
            )
        action_info = self._find_action(decision, action)
        if action_info and action_info.get("state") == "BLOCKED":
            raise HoldingsDecisionSupportError(
                "HOLD_DECISION_ACTION_BLOCKED",
                str(action_info.get("reason") or "현재 정책에서 선택할 수 없습니다."),
            )

        conn = self.catalog.connect()
        try:
            self.require_ready(conn)
            conn.execute("BEGIN IMMEDIATE")
            resolution_id = str(uuid4())
            conn.execute(
                """
                INSERT INTO holding_decision_resolution(
                    id,decision_id,selected_action,resolution_type,note,
                    resulting_plan_id,created_at
                ) VALUES(?,?,?,?,?,?,?)
                """,
                (
                    resolution_id,
                    decision_id,
                    action,
                    resolution,
                    (note or "").strip() or None,
                    None,
                    self.clock(),
                ),
            )
            conn.commit()
        except sqlite3.IntegrityError as exc:
            conn.rollback()
            raise HoldingsDecisionSupportError(
                "HOLD_DECISION_RESOLUTION_CONFLICT",
                "보유 판단 선택을 저장하는 동안 충돌이 발생했습니다.",
            ) from exc
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
        return self.get_decision(decision_id)

    def apply_plan(
        self,
        *,
        decision_id: str,
        selected_action: str | None = None,
        note: str | None = None,
    ) -> dict[str, Any]:
        decision = self.get_decision(decision_id)
        if decision["stale"]:
            raise HoldingsDecisionSupportError(
                "HOLD_DECISION_STALE",
                "보유 상태가 변경되었습니다. 최신 판단을 다시 확인하세요.",
            )
        revision_id = decision["source_analysis_revision_id"]
        if revision_id is None:
            raise HoldingsDecisionSupportError(
                "HOLD_DECISION_PLAN_UNAVAILABLE",
                "계획에 적용할 최신 Analysis Revision이 없습니다.",
            )
        action = (
            selected_action.strip().upper()
            if selected_action
            else decision["primary_action"]
        )
        if action is not None and action not in ACTIONS:
            raise HoldingsDecisionSupportError(
                "HOLD_DECISION_ACTION_INVALID",
                "지원하지 않는 보유 행동입니다.",
            )
        action_info = self._find_action(decision, action)
        if action_info and action_info.get("state") == "BLOCKED":
            raise HoldingsDecisionSupportError(
                "HOLD_DECISION_ACTION_BLOCKED",
                str(action_info.get("reason") or "현재 정책에서 선택할 수 없습니다."),
            )

        conn = self.catalog.connect()
        try:
            self.require_ready(conn)
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT * FROM holding_decision_record WHERE id=?",
                (decision_id,),
            ).fetchone()
            if row is None:
                raise HoldingsDecisionSupportError(
                    "HOLD_DECISION_NOT_FOUND",
                    "보유 판단 기록을 찾을 수 없습니다.",
                )
            position = conn.execute(
                "SELECT * FROM holding_position WHERE id=?",
                (decision["position_id"],),
            ).fetchone()
            if position is None:
                raise HoldingsDecisionSupportError(
                    "HOLD_POSITION_NOT_FOUND",
                    "보유 Position을 찾을 수 없습니다.",
                )
            latest = self._latest_revision(
                conn,
                str(position["monitored_stock_id"]),
            )
            active = self._active_plan(conn, decision["position_id"])

            local_stale: list[str] = []
            if str(position["status"]) != decision["source_position_status"]:
                local_stale.append("POSITION_STATUS_CHANGED")
            if str(position["current_quantity"]) != decision["source_position_quantity"]:
                local_stale.append("POSITION_QUANTITY_CHANGED")
            current_avg = (
                str(position["current_average_price"])
                if position["current_average_price"] is not None
                else None
            )
            if current_avg != decision["source_position_average_price"]:
                local_stale.append("POSITION_AVERAGE_PRICE_CHANGED")
            current_revision_id = (
                str(latest["id"]) if latest is not None else None
            )
            if current_revision_id != decision["source_analysis_revision_id"]:
                local_stale.append("ANALYSIS_REVISION_CHANGED")
            current_plan_id = str(active["id"]) if active is not None else None
            current_plan_version = (
                int(active["plan_version"]) if active is not None else None
            )
            if current_plan_id != decision["source_active_plan_id"]:
                local_stale.append("ACTIVE_PLAN_CHANGED")
            elif current_plan_version != decision["source_active_plan_version"]:
                local_stale.append("ACTIVE_PLAN_VERSION_CHANGED")
            if local_stale:
                raise HoldingsDecisionSupportError(
                    "HOLD_DECISION_STALE",
                    "보유 상태가 변경되었습니다. 최신 판단을 다시 확인하세요.",
                )

            if (
                active is not None
                and str(active["source_analysis_revision_id"]) == revision_id
            ):
                raise HoldingsDecisionSupportError(
                    "HOLD_DECISION_PLAN_UNCHANGED",
                    "현재 적용 계획이 이미 이 Analysis Revision을 사용하고 있습니다.",
                )

            try:
                plan = self.management._apply_analysis_plan_in_conn(  # noqa: SLF001
                    conn,
                    position_id=decision["position_id"],
                    analysis_revision_id=revision_id,
                    change_reason=(note or "").strip() or "P3-S1 보유 판단에서 명시 적용",
                    applied_at=self.clock(),
                )
            except HoldingsManagementError:
                raise

            now = self.clock()
            conn.execute(
                """
                INSERT INTO holding_management_plan_context_vnp3s1(
                    plan_id,context_version,source_decision_id,selected_action,
                    review_cycle_trading_days,time_stop_trading_days,
                    adjustment_context_json,created_at
                ) VALUES(?,?,?,?,?,?,?,?)
                """,
                (
                    plan.id,
                    HOLDING_PLAN_CONTEXT_VERSION,
                    decision_id,
                    action,
                    None,
                    None,
                    _canonical(
                        {
                            "numeric_horizon_policy_approved": False,
                            "partial_adjustment_ratio": None,
                            "trailing_policy": None,
                            "note": "P3-S1은 임의 Review Cycle/Time Stop/부분 조정 수치를 생성하지 않습니다.",
                        }
                    ),
                    now,
                ),
            )
            resolution_id = str(uuid4())
            conn.execute(
                """
                INSERT INTO holding_decision_resolution(
                    id,decision_id,selected_action,resolution_type,note,
                    resulting_plan_id,created_at
                ) VALUES(?,?,?,?,?,?,?)
                """,
                (
                    resolution_id,
                    decision_id,
                    action,
                    "APPLY_NEW_PLAN",
                    (note or "").strip() or None,
                    plan.id,
                    now,
                ),
            )
            conn.commit()
        except sqlite3.IntegrityError as exc:
            conn.rollback()
            raise HoldingsDecisionSupportError(
                "HOLD_DECISION_APPLY_CONFLICT",
                "보유 판단 계획을 적용하는 동안 충돌이 발생했습니다.",
            ) from exc
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

        return {
            "decision": self.get_decision(decision_id),
            "plan": plan.to_dict(),
            "plan_context": {
                "context_version": HOLDING_PLAN_CONTEXT_VERSION,
                "source_decision_id": decision_id,
                "selected_action": action,
                "review_cycle_trading_days": None,
                "time_stop_trading_days": None,
            },
        }
