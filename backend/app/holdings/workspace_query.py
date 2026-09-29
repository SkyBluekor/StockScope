from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.data_contract.builder import build_stock_data_contract
from app.data_contract.reader import ReadOnlyDataStateReader
from app.horizon_context import get_analysis_horizon
from app.watch.service import WatchService

from .catalog import DEFAULT_HOLDINGS_DB, HoldingsCatalogError
from .decision_context import HoldingDecisionContextService
from .decision_support import (
    HoldingDecisionSupportService,
    HoldingsDecisionSupportError,
)
from .management import HoldingManagementService, HoldingsManagementError
from .performance import HoldingPerformanceService, HoldingsPerformanceError
from .read_only_catalog import ReadOnlyHoldingsCatalog
from .recovery import HoldingRecoveryService, HoldingsRecoveryError


WORKSPACE_CONTEXT_VERSION = "HOLDINGS_WORKSPACE_CONTEXT_V1"


class HoldingsWorkspaceQueryError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _status(status: str, reason_code: str | None = None) -> dict[str, Any]:
    return {"status": status, "reason_code": reason_code}


class HoldingsWorkspaceQueryService:
    """Read-only composition facade for the Holdings workspace.

    This service only projects already-stored state. It does not initialize schema,
    refresh analysis, verify proofs, evaluate decisions, transition Watch, or apply
    plans. Commands stay on their existing explicit endpoints.
    """

    def __init__(
        self,
        holdings_db: Path | None = None,
        *,
        market_store_db: Path | None = None,
    ) -> None:
        self.catalog = ReadOnlyHoldingsCatalog(Path(holdings_db or DEFAULT_HOLDINGS_DB))
        self.market_store_db = market_store_db
        self.data_reader = ReadOnlyDataStateReader(
            holdings_db=self.catalog.db_path,
            market_store_db=market_store_db,
        )
        self.management = HoldingManagementService(
            self.catalog,
            market_store_db=market_store_db,
        )
        self.performance = HoldingPerformanceService(
            self.catalog,
            market_store_db=market_store_db,
        )
        self.decisions = HoldingDecisionSupportService(
            self.catalog,
            market_store_db=market_store_db,
        )
        self.recovery = HoldingRecoveryService(
            self.catalog,
            market_store_db=market_store_db,
        )
        self.watch = WatchService(self.catalog)

    @staticmethod
    def _position_payload(catalog: ReadOnlyHoldingsCatalog, position: Any) -> dict[str, Any]:
        account = catalog.get_position_account(position.position_account_id)
        return {
            "position_id": position.id,
            "account_id": account.id,
            "provider": account.provider,
            "account_kind": account.account_kind,
            "broker_environment": account.broker_environment,
            "account_name": account.display_name,
            "status": position.status,
            "opened_at": position.opened_at,
            "closed_at": position.closed_at,
            "quantity": format(position.current_quantity, "f"),
            "average_price": (
                format(position.current_average_price, "f")
                if position.current_average_price is not None
                else None
            ),
            "cost_basis": (
                format(position.current_cost_basis, "f")
                if position.current_cost_basis is not None
                else None
            ),
            "opened_reason": position.opened_reason,
            "last_observed_at": position.last_observed_at,
        }

    def _current_analysis(self, stock_id: str) -> dict[str, Any] | None:
        with self.catalog.connection() as conn:
            row = conn.execute(
                """
                SELECT
                    d.market_date,
                    r.id AS revision_id,
                    r.revision_no,
                    r.strategy_key,
                    r.action_state,
                    r.risk_state,
                    r.reference_price,
                    r.stop_price,
                    r.target1_price,
                    r.target2_price,
                    r.scanner_version,
                    r.analysis_engine_version,
                    r.policy_version,
                    r.revision_reason,
                    r.computed_at
                FROM stock_analysis_day d
                JOIN stock_analysis_revision r ON r.id=d.current_revision_id
                WHERE d.monitored_stock_id=?
                ORDER BY d.market_date DESC
                LIMIT 1
                """,
                (stock_id,),
            ).fetchone()
            if row is None:
                return None
            horizon_context = get_analysis_horizon(
                conn,
                str(row["revision_id"]),
            ).to_dict()

        return {
            "market_date": row["market_date"],
            "revision_id": row["revision_id"],
            "revision_no": int(row["revision_no"]),
            "strategy_key": row["strategy_key"],
            "action_state": row["action_state"],
            "risk_state": row["risk_state"],
            "reference_price": row["reference_price"],
            "stop_price": row["stop_price"],
            "target1_price": row["target1_price"],
            "target2_price": row["target2_price"],
            "scanner_version": row["scanner_version"],
            "analysis_engine_version": row["analysis_engine_version"],
            "policy_version": row["policy_version"],
            "revision_reason": row["revision_reason"],
            "computed_at": row["computed_at"],
            "horizon_context": horizon_context,
        }

    def _latest_event(self, stock_id: str) -> dict[str, Any] | None:
        with self.catalog.connection() as conn:
            row = conn.execute(
                """
                SELECT e.*
                FROM holding_position_event e
                JOIN holding_position p ON p.id=e.position_id
                WHERE p.monitored_stock_id=?
                ORDER BY e.created_at DESC,e.id DESC
                LIMIT 1
                """,
                (stock_id,),
            ).fetchone()
        if row is None:
            return None
        event = self.catalog._event_from_row(row)  # noqa: SLF001
        return {
            "event_id": event.id,
            "position_id": event.position_id,
            "event_type": event.event_type,
            "quantity_delta": (
                format(event.quantity_delta, "f")
                if event.quantity_delta is not None
                else None
            ),
            "unit_price": (
                format(event.unit_price, "f") if event.unit_price is not None else None
            ),
            "before_quantity": (
                format(event.before_quantity, "f")
                if event.before_quantity is not None
                else None
            ),
            "after_quantity": (
                format(event.after_quantity, "f")
                if event.after_quantity is not None
                else None
            ),
            "before_average_price": (
                format(event.before_average_price, "f")
                if event.before_average_price is not None
                else None
            ),
            "after_average_price": (
                format(event.after_average_price, "f")
                if event.after_average_price is not None
                else None
            ),
            "observed_at": event.observed_at,
            "effective_at": event.effective_at,
            "analysis_revision_id": event.analysis_revision_id,
            "account_sync_run_id": event.account_sync_run_id,
            "note": event.note,
            "created_at": event.created_at,
        }

    @staticmethod
    def _review_conditions(
        *,
        analysis_contract: dict[str, Any],
        management: dict[str, Any] | None,
        decision: dict[str, Any] | None,
        recovery: dict[str, Any] | None,
        watch: dict[str, Any] | None,
    ) -> list[str]:
        conditions: list[str] = []

        if not bool(analysis_contract.get("current_use_allowed")):
            conditions.append("ANALYSIS_REFRESH_REQUIRED")

        management_state = (
            str(management.get("management_state"))
            if isinstance(management, dict)
            else ""
        )
        if management_state == "STOP_BREACHED":
            conditions.append("ACTIVE_PLAN_STOP_BREACHED")
        elif management_state in {"TARGET1_REACHED", "TARGET2_REACHED"}:
            conditions.append("ACTIVE_PLAN_TARGET_REACHED")

        if isinstance(decision, dict):
            effective = str(decision.get("effective_status") or decision.get("status") or "")
            if effective == "STALE":
                conditions.append("DECISION_REVIEW_REQUIRED")
            elif effective in {"REVIEW_REQUIRED", "CONFLICT"}:
                conditions.append("DECISION_REVIEW_REQUIRED")
            if decision.get("primary_action") == "STOP":
                conditions.append("ACTIVE_PLAN_STOP_BREACHED")

        if isinstance(recovery, dict) and recovery.get("open_review") is not None:
            conditions.append("RECOVERY_REVIEW_OPEN")

        if isinstance(watch, dict):
            if watch.get("migration_required"):
                conditions.append("WATCH_PREPARATION_REQUIRED")
            elif watch.get("open_gaps"):
                conditions.append("WATCH_GAP_PRESENT")

        return list(dict.fromkeys(conditions))

    def build(self, stock_id: str) -> dict[str, Any]:
        try:
            stock = self.catalog.get_monitored_stock(stock_id)
        except HoldingsCatalogError as exc:
            raise HoldingsWorkspaceQueryError(exc.code, exc.message) from exc
        if stock is None:
            raise HoldingsWorkspaceQueryError(
                "HOLD_STOCK_NOT_FOUND",
                "등록된 종목을 찾을 수 없습니다.",
            )

        positions = self.catalog.list_positions(stock.id, status="OPEN")
        stock_payload = {
            "stock_id": stock.id,
            "market": stock.market,
            "ticker": stock.ticker,
            "name": stock.name,
            "watch_enabled": stock.watch_enabled,
            "is_held": bool(positions),
            "positions": [
                self._position_payload(self.catalog, position)
                for position in positions
            ],
            "current_analysis": self._current_analysis(stock.id),
            "decision_context": HoldingDecisionContextService(self.catalog).build(stock.id),
            "latest_position_event": self._latest_event(stock.id),
        }

        state = self.data_reader.read_stock_state(stock.market, stock.ticker)
        contract_model = build_stock_data_contract(state, chart_range=None)
        contract = contract_model.model_dump(mode="json")
        resources = contract["resources"]
        analysis_contract = resources["analysis_result"]

        source_status: dict[str, Any] = {
            "eod": _status(resources["eod"]["status"], resources["eod"].get("reason_code")),
            "analysis": _status(
                analysis_contract["status"],
                analysis_contract.get("reason_code"),
            ),
            "realtime": _status(
                resources["realtime"]["status"],
                resources["realtime"].get("reason_code"),
            ),
            "ledger": _status(
                resources["ledger"]["status"],
                resources["ledger"].get("reason_code"),
            ),
        }

        management_payload: dict[str, Any] | None = None
        try:
            management_payload = self.management.build(stock.id)
            source_status["management"] = _status("AVAILABLE")
        except (HoldingsManagementError, HoldingsCatalogError) as exc:
            source_status["management"] = _status(
                "UNAVAILABLE",
                str(getattr(exc, "code", "HOLD_MANAGEMENT_READ_FAILED")),
            )

        performance_payload: dict[str, Any] | None = None
        try:
            performance_payload = self.performance.calculate(stock.id).to_dict()
            source_status["performance"] = _status("AVAILABLE")
        except (HoldingsPerformanceError, HoldingsCatalogError) as exc:
            source_status["performance"] = _status(
                "UNAVAILABLE",
                str(getattr(exc, "code", "HOLD_PERFORMANCE_READ_FAILED")),
            )

        decision_by_position: dict[str, dict[str, Any] | None] = {
            position.id: None for position in positions
        }
        decision_status = _status("AVAILABLE")
        try:
            view = self.decisions.latest_for_stock(stock.id)
            for item in view["positions"]:
                position_id = str(item["position_id"])
                decision = item["decision"]
                if decision is not None:
                    try:
                        decision = self.decisions.get_decision(str(decision["decision_id"]))
                    except HoldingsDecisionSupportError:
                        pass
                decision_by_position[position_id] = decision
        except HoldingsDecisionSupportError as exc:
            status = (
                "MIGRATION_REQUIRED"
                if exc.code in {
                    "HOLD_DECISION_MIGRATION_REQUIRED",
                    "HOLD_DECISION_SCHEMA_UNSUPPORTED",
                }
                else "UNAVAILABLE"
            )
            decision_status = _status(status, exc.code)
        source_status["decision"] = decision_status

        management_by_position = {
            str(item["position_id"]): item
            for item in (management_payload or {}).get("positions", [])
        }
        performance_by_position = {
            str(item["position_id"]): item
            for item in (performance_payload or {}).get("positions", [])
        }

        rows: list[dict[str, Any]] = []
        recovery_failures: list[str] = []
        watch_migration = False
        watch_unavailable = False

        for position in positions:
            decision = decision_by_position.get(position.id)

            recovery_context: dict[str, Any] | None = None
            recovery_status = _status("AVAILABLE")
            try:
                recovery_context = self.recovery.get_context(position.id)
            except HoldingsRecoveryError as exc:
                status = (
                    "MIGRATION_REQUIRED"
                    if exc.code in {
                        "HOLD_RECOVERY_MIGRATION_REQUIRED",
                        "HOLD_RECOVERY_SCHEMA_UNSUPPORTED",
                    }
                    else "UNAVAILABLE"
                )
                recovery_status = _status(status, exc.code)
                recovery_failures.append(status)

            try:
                watch_status = self.watch.get_position_status(position.id)
                if watch_status.get("migration_required"):
                    watch_migration = True
            except Exception:
                watch_status = {
                    "available": False,
                    "migration_required": False,
                    "position_id": position.id,
                    "policy_enabled": False,
                    "blocked_reason": "WATCH_STATUS_READ_FAILED",
                    "setting": None,
                    "rules": [],
                    "open_gaps": [],
                    "latest_notification": None,
                }
                watch_unavailable = True

            user_choice = None
            if isinstance(decision, dict):
                resolutions = decision.get("resolutions")
                if isinstance(resolutions, list) and resolutions:
                    user_choice = resolutions[-1]

            management_item = management_by_position.get(position.id)
            review_conditions = self._review_conditions(
                analysis_contract=analysis_contract,
                management=management_item,
                decision=decision,
                recovery=recovery_context,
                watch=watch_status,
            )

            rows.append(
                {
                    "position": self._position_payload(self.catalog, position),
                    "performance": performance_by_position.get(position.id),
                    "management": management_item,
                    "decision": decision,
                    "user_choice": user_choice,
                    "recovery": recovery_context,
                    "recovery_status": recovery_status,
                    "watch": watch_status,
                    "review_conditions": review_conditions,
                }
            )

        if recovery_failures:
            source_status["recovery"] = _status(
                "MIGRATION_REQUIRED"
                if all(item == "MIGRATION_REQUIRED" for item in recovery_failures)
                else "PARTIAL"
            )
        else:
            source_status["recovery"] = _status("AVAILABLE")

        if watch_unavailable:
            source_status["watch"] = _status("PARTIAL", "WATCH_STATUS_READ_FAILED")
        elif watch_migration:
            source_status["watch"] = _status("MIGRATION_REQUIRED")
        else:
            source_status["watch"] = _status("AVAILABLE")

        all_review_conditions = list(
            dict.fromkeys(
                condition
                for row in rows
                for condition in row["review_conditions"]
            )
        )

        identity = analysis_contract.get("identity") or {}
        context_identity = {
            "stock_id": stock.id,
            "market": stock.market,
            "ticker": stock.ticker,
            "market_confirmed_date": resources["eod"].get("market_confirmed_date"),
            "analysis_revision_id": analysis_contract.get("revision_id"),
            "analysis_market_date": analysis_contract.get("basis_date"),
            "analysis_input_fingerprint": identity.get("input_fingerprint"),
            "fingerprint_contract_version": identity.get("fingerprint_contract_version"),
            "selection_policy_id": identity.get("selection_policy_id"),
            "selection_policy_hash": identity.get("selection_policy_hash"),
            "selection_policy_contract_version": identity.get(
                "selection_policy_contract_version"
            ),
            "strategy_version_id": identity.get("strategy_version_id"),
            "strategy_definition_hash": identity.get("strategy_definition_hash"),
            "positions": [
                {
                    "position_id": row["position"]["position_id"],
                    "active_plan_id": (
                        row["management"]["active_plan"]["plan_id"]
                        if row["management"] and row["management"].get("active_plan")
                        else None
                    ),
                    "active_plan_version": (
                        row["management"]["active_plan"]["version"]
                        if row["management"] and row["management"].get("active_plan")
                        else None
                    ),
                    "decision_id": (
                        row["decision"].get("decision_id")
                        if isinstance(row["decision"], dict)
                        else None
                    ),
                    "recovery_review_id": (
                        row["recovery"]["open_review"].get("review_id")
                        if isinstance(row["recovery"], dict)
                        and isinstance(row["recovery"].get("open_review"), dict)
                        else None
                    ),
                    "watch_setting_id": (
                        row["watch"]["setting"].get("setting_id")
                        if isinstance(row["watch"].get("setting"), dict)
                        else None
                    ),
                }
                for row in rows
            ],
        }

        return {
            "context_version": WORKSPACE_CONTEXT_VERSION,
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "stock": stock_payload,
            "context_identity": context_identity,
            "source_status": source_status,
            "current_state": {
                "held": bool(positions),
                "analysis_status": analysis_contract["status"],
                "analysis_current_use_allowed": bool(
                    analysis_contract.get("current_use_allowed")
                ),
                "analysis_reason_code": analysis_contract.get("reason_code"),
                "valuation": (
                    performance_payload.get("valuation")
                    if performance_payload is not None
                    else None
                ),
                "attention_required": bool(all_review_conditions),
                "review_conditions": all_review_conditions,
            },
            "data_contract": contract,
            "performance": performance_payload,
            "management": management_payload,
            "positions": rows,
        }
