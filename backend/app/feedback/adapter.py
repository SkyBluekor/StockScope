from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from typing import Any, Iterator

from app.backtest.jobs import BacktestJobManager, backtest_jobs
from app.core.config import PROJECT_ROOT
from app.horizon_context import get_execution_horizon, get_validation_horizon

from .models import EvidenceSelector, FeedbackEvidence, digest_json


DEFAULT_SIMULATION_DB = PROJECT_ROOT / "backend" / "runtime" / "simulation" / "simulation.db"
DEFAULT_TRACKING_DB = PROJECT_ROOT / "backend" / "runtime" / "tracking" / "recommendation_tracking.db"


class FeedbackAdapterError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _json_value(raw: str | None) -> Any:
    if raw in (None, ""):
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def _float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _bool(value: Any) -> bool:
    return bool(int(value or 0))


class FeedbackEvidenceAdapter:
    """Read existing evidence without mutating Tracking/Validation/Execution sources."""

    def __init__(
        self,
        *,
        simulation_db: Path | None = None,
        tracking_db: Path | None = None,
        job_manager: BacktestJobManager | None = None,
    ) -> None:
        self.simulation_db = Path(
            simulation_db
            or os.getenv("STOCKSCOPE_SIM_DB")
            or DEFAULT_SIMULATION_DB
        )
        self.tracking_db = Path(
            tracking_db
            or os.getenv("STOCKSCOPE_TRACKING_DB")
            or DEFAULT_TRACKING_DB
        )
        self.job_manager = job_manager or backtest_jobs

    @staticmethod
    @contextmanager
    def _read_only(path: Path) -> Iterator[sqlite3.Connection]:
        if not path.is_file():
            raise FeedbackAdapterError(
                "FEEDBACK_SOURCE_STORE_NOT_FOUND",
                f"원본 저장소를 찾을 수 없습니다: {path}",
            )
        uri = path.resolve().as_uri() + "?mode=ro"
        conn = sqlite3.connect(uri, uri=True, timeout=5.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA query_only=ON")
        try:
            yield conn
        finally:
            conn.close()

    @staticmethod
    def _tables(conn: sqlite3.Connection) -> set[str]:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        return {str(row["name"]) for row in rows}

    @staticmethod
    def _matches(
        *,
        signal_date: str | None,
        market: str | None,
        strategy: str | None,
        selector: EvidenceSelector,
    ) -> bool:
        if selector.date_from and (not signal_date or signal_date < selector.date_from):
            return False
        if selector.date_to and (not signal_date or signal_date > selector.date_to):
            return False
        if selector.market and (market or "").upper() != selector.market:
            return False
        if selector.strategy and (strategy or "") != selector.strategy:
            return False
        return True

    def resolve(self, selector: EvidenceSelector) -> list[FeedbackEvidence]:
        normalized = selector.normalized()
        parsed_dates: dict[str, date] = {}
        for field_name, raw in (
            ("date_from", normalized.date_from),
            ("date_to", normalized.date_to),
        ):
            if raw is None:
                continue
            try:
                parsed_dates[field_name] = date.fromisoformat(raw)
            except ValueError as exc:
                raise FeedbackAdapterError(
                    "FEEDBACK_SELECTOR_DATE_INVALID",
                    f"{field_name}은 YYYY-MM-DD 형식이어야 합니다.",
                ) from exc
        if (
            "date_from" in parsed_dates
            and "date_to" in parsed_dates
            and parsed_dates["date_from"] > parsed_dates["date_to"]
        ):
            raise FeedbackAdapterError(
                "FEEDBACK_SELECTOR_RANGE_INVALID",
                "평가 시작일은 종료일보다 늦을 수 없습니다.",
            )

        if normalized.source_type == "TRACKING":
            return self._tracking(normalized)
        if normalized.source_type == "VALIDATION":
            return self._validation(normalized)
        if normalized.source_type == "EXECUTION":
            return self._execution(normalized)
        if normalized.source_type == "BACKTEST":
            return self._backtest(normalized)
        raise FeedbackAdapterError(
            "FEEDBACK_SOURCE_TYPE_UNSUPPORTED",
            f"지원하지 않는 평가 원본입니다: {normalized.source_type}",
        )

    def _tracking(self, selector: EvidenceSelector) -> list[FeedbackEvidence]:
        with self._read_only(self.tracking_db) as conn:
            required = {"tracked_recommendation", "recommendation_performance"}
            if not required.issubset(self._tables(conn)):
                raise FeedbackAdapterError(
                    "FEEDBACK_TRACKING_SCHEMA_UNAVAILABLE",
                    "Tracking 평가 원본 schema를 확인할 수 없습니다.",
                )
            if selector.source_id and selector.source_id.upper() not in {"ALL", "SCANNER"}:
                rows = conn.execute(
                    """
                    SELECT t.*, p.*
                    FROM tracked_recommendation t
                    LEFT JOIN recommendation_performance p
                      ON p.recommendation_id=t.id
                    WHERE t.id=?
                    ORDER BY t.recommendation_date,t.market,t.ticker
                    """,
                    (selector.source_id,),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT t.*, p.*
                    FROM tracked_recommendation t
                    LEFT JOIN recommendation_performance p
                      ON p.recommendation_id=t.id
                    ORDER BY t.recommendation_date,t.market,t.ticker
                    """
                ).fetchall()

        evidence: list[FeedbackEvidence] = []
        for row in rows:
            signal_date = str(row["recommendation_date"] or "") or None
            market = str(row["market"] or "") or None
            strategy = row["strategy"]
            if not self._matches(
                signal_date=signal_date,
                market=market,
                strategy=strategy,
                selector=selector,
            ):
                continue

            scanner_source = bool(row["has_scanner_source"]) or str(row["source"]).upper() == "SCANNER"
            manual_source = bool(row["has_manual_source"]) or str(row["source"]).upper() == "MANUAL"
            trading_days = _int(row["trading_days"]) if "trading_days" in row.keys() else None
            if row["recommendation_id"] is None:
                maturity = "NOT_CALCULATED"
            elif trading_days is not None and trading_days >= 20:
                maturity = "MATURE"
            elif trading_days and trading_days > 0:
                maturity = "IMMATURE"
            else:
                maturity = "NOT_CALCULATED"

            metrics = {
                "current_return_pct": _float(row["current_return_pct"]) if "current_return_pct" in row.keys() else None,
                "return_5d": _float(row["return_5d"]) if "return_5d" in row.keys() else None,
                "return_10d": _float(row["return_10d"]) if "return_10d" in row.keys() else None,
                "return_20d": _float(row["return_20d"]) if "return_20d" in row.keys() else None,
                "mfe_pct": _float(row["mfe_pct"]) if "mfe_pct" in row.keys() else None,
                "mae_pct": _float(row["mae_pct"]) if "mae_pct" in row.keys() else None,
                "entry_touched": _bool(row["entry_touched"]) if "entry_touched" in row.keys() else False,
                "stop_touched": _bool(row["stop_touched"]) if "stop_touched" in row.keys() else False,
                "target1_touched": _bool(row["target1_touched"]) if "target1_touched" in row.keys() else False,
                "target2_touched": _bool(row["target2_touched"]) if "target2_touched" in row.keys() else False,
            }
            source_payload = {
                "id": row["id"],
                "scanner_snapshot_hash": row["scanner_snapshot_hash"],
                "snapshot_hash": row["snapshot_hash"],
                "status": row["status"],
                "closed_market_date": row["closed_market_date"],
                "close_performance_status": row["close_performance_status"],
                "performance_updated_at": row["updated_at"] if row["recommendation_id"] is not None else None,
                "trading_days": trading_days,
                "metrics": metrics,
            }
            inclusion = "INCLUDED" if scanner_source else "EXCLUDED"
            exclusion = None if scanner_source else "MANUAL_ONLY"
            evidence.append(
                FeedbackEvidence(
                    source_type="TRACKING",
                    source_owner="TRACKING_DB",
                    source_id="ALL" if selector.source_id.upper() in {"ALL", "SCANNER"} else selector.source_id,
                    source_item_id=str(row["id"]),
                    source_hash=digest_json(source_payload),
                    durability="DURABLE",
                    origin_kind="OBSERVATION",
                    market=market,
                    ticker=str(row["ticker"] or "") or None,
                    name=str(row["name"] or "") or None,
                    signal_date=signal_date,
                    strategy=str(strategy) if strategy is not None else None,
                    decision_status=str(row["decision_status"]) if row["decision_status"] is not None else None,
                    scanner_version=str(row["scanner_version"]) if row["scanner_version"] is not None else None,
                    scanner_baseline=str(row["scanner_baseline"]) if row["scanner_baseline"] is not None else None,
                    horizon_intent="LEGACY_UNSPECIFIED",
                    horizon_policy_version=None,
                    metric_definition="TRACKING_DPLUS_OBSERVATION_V4",
                    execution_policy_version=None,
                    exit_policy_token=None,
                    fee_pct=None,
                    tax_pct=None,
                    slippage_pct=None,
                    maturity_status=maturity,
                    inclusion_status=inclusion,
                    exclusion_reason=exclusion,
                    available_trading_days=trading_days,
                    metrics=metrics,
                    source_observed_at=(
                        str(row["updated_at"]) if row["recommendation_id"] is not None
                        else str(row["created_at"])
                    ),
                    metadata={
                        "selection_method": "USER_TRACKING_WITH_SCANNER_PROVENANCE" if scanner_source else "MANUAL_ONLY",
                        "evaluation_window": "DPLUS_5_10_20",
                        "selector_date_from": selector.date_from,
                        "selector_date_to": selector.date_to,
                        "tracking_status": row["status"],
                        "close_performance_status": row["close_performance_status"],
                        "has_manual_source": manual_source,
                        "has_scanner_source": scanner_source,
                        "reached_price_is_execution": False,
                    },
                )
            )
        return evidence

    def _validation(self, selector: EvidenceSelector) -> list[FeedbackEvidence]:
        with self._read_only(self.simulation_db) as conn:
            required = {
                "historical_validation_run",
                "historical_validation_day",
                "historical_validation_candidate",
            }
            if not required.issubset(self._tables(conn)):
                raise FeedbackAdapterError(
                    "FEEDBACK_VALIDATION_SCHEMA_UNAVAILABLE",
                    "Historical Validation 평가 원본 schema를 확인할 수 없습니다.",
                )
            run = conn.execute(
                "SELECT * FROM historical_validation_run WHERE id=?",
                (selector.source_id,),
            ).fetchone()
            if run is None:
                raise FeedbackAdapterError(
                    "FEEDBACK_VALIDATION_NOT_FOUND",
                    "Historical Validation 원본을 찾을 수 없습니다.",
                )
            horizon = get_validation_horizon(conn, selector.source_id)
            outcome_available = "historical_validation_candidate_outcome" in self._tables(conn)
            outcome_join = (
                """
                LEFT JOIN historical_validation_candidate_outcome o
                  ON o.validation_id=c.validation_id
                 AND o.trading_date=c.trading_date
                 AND o.market=c.market
                 AND o.ticker=c.ticker
                """
                if outcome_available
                else ""
            )
            select_outcome = (
                """
                ,o.reference_price,o.available_trading_days,o.evaluated_through,
                 o.return_5d,o.return_10d,o.return_20d,o.mfe_pct,o.mae_pct,
                 o.entry_comparable,o.entry_touched,o.stop_comparable,o.stop_touched,
                 o.target1_comparable,o.target1_touched,o.target2_comparable,o.target2_touched,
                 o.computed_at AS outcome_computed_at
                """
                if outcome_available
                else """
                ,NULL AS reference_price,NULL AS available_trading_days,NULL AS evaluated_through,
                 NULL AS return_5d,NULL AS return_10d,NULL AS return_20d,NULL AS mfe_pct,NULL AS mae_pct,
                 NULL AS entry_comparable,NULL AS entry_touched,NULL AS stop_comparable,NULL AS stop_touched,
                 NULL AS target1_comparable,NULL AS target1_touched,NULL AS target2_comparable,NULL AS target2_touched,
                 NULL AS outcome_computed_at
                """
            )
            rows = conn.execute(
                f"""
                SELECT c.*,d.result_hash AS day_result_hash,d.completed_at AS day_completed_at
                       {select_outcome}
                FROM historical_validation_candidate c
                JOIN historical_validation_day d
                  ON d.validation_id=c.validation_id
                 AND d.trading_date=c.trading_date
                {outcome_join}
                WHERE c.validation_id=?
                ORDER BY c.trading_date,c.market,c.ticker
                """,
                (selector.source_id,),
            ).fetchall()

        completed = str(run["status"]) == "COMPLETED"
        evidence: list[FeedbackEvidence] = []
        for row in rows:
            signal_date = str(row["trading_date"])
            market = str(row["market"])
            strategy = row["strategy"]
            if not self._matches(
                signal_date=signal_date,
                market=market,
                strategy=strategy,
                selector=selector,
            ):
                continue
            days = _int(row["available_trading_days"])
            if days is None:
                maturity = "NOT_CALCULATED"
            elif days >= 20:
                maturity = "MATURE"
            elif days > 0:
                maturity = "IMMATURE"
            else:
                maturity = "NOT_CALCULATED"
            metrics = {
                "return_5d": _float(row["return_5d"]),
                "return_10d": _float(row["return_10d"]),
                "return_20d": _float(row["return_20d"]),
                "mfe_pct": _float(row["mfe_pct"]),
                "mae_pct": _float(row["mae_pct"]),
                "entry_comparable": _bool(row["entry_comparable"]),
                "entry_touched": _bool(row["entry_touched"]),
                "stop_comparable": _bool(row["stop_comparable"]),
                "stop_touched": _bool(row["stop_touched"]),
                "target1_comparable": _bool(row["target1_comparable"]),
                "target1_touched": _bool(row["target1_touched"]),
                "target2_comparable": _bool(row["target2_comparable"]),
                "target2_touched": _bool(row["target2_touched"]),
            }
            source_payload = {
                "snapshot_hash": row["snapshot_hash"],
                "day_result_hash": row["day_result_hash"],
                "available_trading_days": days,
                "evaluated_through": row["evaluated_through"],
                "metrics": metrics,
                "outcome_computed_at": row["outcome_computed_at"],
            }
            evidence.append(
                FeedbackEvidence(
                    source_type="VALIDATION",
                    source_owner="SIMULATION_DB",
                    source_id=selector.source_id,
                    source_item_id=f"{signal_date}|{market}|{row['ticker']}",
                    source_hash=digest_json(source_payload),
                    durability="DURABLE",
                    origin_kind="OBSERVATION",
                    market=market,
                    ticker=str(row["ticker"]),
                    name=str(row["name"]),
                    signal_date=signal_date,
                    strategy=str(strategy) if strategy is not None else None,
                    decision_status=str(row["decision_status"]) if row["decision_status"] is not None else None,
                    scanner_version=str(run["scanner_version"]),
                    scanner_baseline=str(run["scanner_baseline"]) if run["scanner_baseline"] is not None else None,
                    horizon_intent=horizon.intent,
                    horizon_policy_version=horizon.policy_version,
                    metric_definition="VAL1_DPLUS_OBSERVATION_V1",
                    execution_policy_version=None,
                    exit_policy_token=None,
                    fee_pct=None,
                    tax_pct=None,
                    slippage_pct=None,
                    maturity_status=maturity,
                    inclusion_status="INCLUDED" if completed else "EXCLUDED",
                    exclusion_reason=None if completed else "SOURCE_RUN_NOT_COMPLETED",
                    available_trading_days=days,
                    metrics=metrics,
                    source_observed_at=(
                        str(row["outcome_computed_at"])
                        if row["outcome_computed_at"] is not None
                        else str(row["day_completed_at"] or run["updated_at"])
                    ),
                    metadata={
                        "selection_method": "HISTORICAL_SCANNER_REPLAY",
                        "evaluation_window": "DPLUS_5_10_20",
                        "selector_date_from": selector.date_from,
                        "selector_date_to": selector.date_to,
                        "source_period_start": run["resolved_start_date"],
                        "source_period_end": run["resolved_end_date"],
                        "validation_status": run["status"],
                        "resolved_start_date": run["resolved_start_date"],
                        "resolved_end_date": run["resolved_end_date"],
                        "market_scope": run["market_scope"],
                        "result_bucket": row["result_bucket"],
                    },
                )
            )
        return evidence

    def _execution(self, selector: EvidenceSelector) -> list[FeedbackEvidence]:
        with self._read_only(self.simulation_db) as conn:
            required = {"historical_execution_run", "historical_execution_outcome"}
            if not required.issubset(self._tables(conn)):
                raise FeedbackAdapterError(
                    "FEEDBACK_EXECUTION_SCHEMA_UNAVAILABLE",
                    "Execution Validation 평가 원본 schema를 확인할 수 없습니다.",
                )
            run = conn.execute(
                "SELECT * FROM historical_execution_run WHERE id=?",
                (selector.source_id,),
            ).fetchone()
            if run is None:
                raise FeedbackAdapterError(
                    "FEEDBACK_EXECUTION_NOT_FOUND",
                    "Execution Validation 원본을 찾을 수 없습니다.",
                )
            horizon = get_execution_horizon(conn, selector.source_id)
            validation_run = conn.execute(
                """
                SELECT resolved_start_date,resolved_end_date,market_scope,scanner_baseline
                FROM historical_validation_run
                WHERE id=?
                LIMIT 1
                """,
                (run["validation_id"],),
            ).fetchone()
            rows = conn.execute(
                """
                SELECT *
                FROM historical_execution_outcome
                WHERE execution_run_id=?
                ORDER BY signal_date,market,ticker
                """,
                (selector.source_id,),
            ).fetchall()

        completed = str(run["status"]) == "COMPLETED"
        evidence: list[FeedbackEvidence] = []
        for row in rows:
            signal_date = str(row["signal_date"])
            market = str(row["market"])
            strategy = row["strategy"]
            if not self._matches(
                signal_date=signal_date,
                market=market,
                strategy=strategy,
                selector=selector,
            ):
                continue
            outcome_status = str(row["outcome_status"])
            if outcome_status == "CLOSED":
                maturity = "MATURE_REALIZED"
            elif outcome_status == "CENSORED":
                maturity = "CENSORED"
            elif outcome_status == "OPEN":
                maturity = "IMMATURE"
            elif outcome_status in {"NOT_EXECUTED", "NO_ENTRY_DATA", "RISK_PLAN_BLOCKED"}:
                maturity = "NON_EXECUTED"
            else:
                maturity = "UNKNOWN"
            metrics = {
                "gross_return_pct": _float(row["gross_return_pct"]),
                "net_return_pct": _float(row["net_return_pct"]),
                "mark_return_pct": _float(row["mark_return_pct"]),
                "holding_days": _int(row["holding_days"]),
                "outcome_status": outcome_status,
                "outcome_reason": row["outcome_reason"],
                "exit_reason": row["exit_reason"],
            }
            evidence.append(
                FeedbackEvidence(
                    source_type="EXECUTION",
                    source_owner="SIMULATION_DB",
                    source_id=selector.source_id,
                    source_item_id=f"{signal_date}|{market}|{row['ticker']}",
                    source_hash=str(row["outcome_hash"]),
                    durability="DURABLE",
                    origin_kind="VIRTUAL_EXECUTION",
                    market=market,
                    ticker=str(row["ticker"]),
                    name=str(row["name"]),
                    signal_date=signal_date,
                    strategy=str(strategy) if strategy is not None else None,
                    decision_status=str(row["candidate_state"]) if row["candidate_state"] is not None else None,
                    scanner_version=str(row["scanner_version"]),
                    scanner_baseline=(
                        str(validation_run["scanner_baseline"])
                        if validation_run is not None and validation_run["scanner_baseline"] is not None
                        else None
                    ),
                    horizon_intent=horizon.intent,
                    horizon_policy_version=horizon.policy_version,
                    metric_definition="VAL2_VIRTUAL_EXECUTION_V1",
                    execution_policy_version=str(row["execution_policy_version"]),
                    exit_policy_token=str(row["production_exit_policy_token"]),
                    fee_pct=_float(row["fee_pct"]),
                    tax_pct=_float(row["tax_pct"]),
                    slippage_pct=_float(row["slippage_pct"]),
                    maturity_status=maturity,
                    inclusion_status="INCLUDED" if completed else "EXCLUDED",
                    exclusion_reason=None if completed else "SOURCE_RUN_NOT_COMPLETED",
                    available_trading_days=_int(row["holding_days"]),
                    metrics=metrics,
                    source_observed_at=str(row["created_at"]),
                    metadata={
                        "selection_method": "HISTORICAL_EXECUTION_VALIDATION",
                        "evaluation_window": "ENTRY_TO_EXIT_OR_CUTOFF",
                        "selector_date_from": selector.date_from,
                        "selector_date_to": selector.date_to,
                        "source_period_start": (
                            validation_run["resolved_start_date"] if validation_run is not None else None
                        ),
                        "source_period_end": (
                            validation_run["resolved_end_date"] if validation_run is not None else None
                        ),
                        "market_scope": (
                            validation_run["market_scope"] if validation_run is not None else None
                        ),
                        "execution_status": run["status"],
                        "market_data_cutoff_date": run["market_data_cutoff_date"],
                        "validation_id": run["validation_id"],
                        "candidate_snapshot_hash": row["candidate_snapshot_hash"],
                        "day_result_hash": row["day_result_hash"],
                        "censored_is_realized_return": False,
                    },
                )
            )
        return evidence

    def _backtest(self, selector: EvidenceSelector) -> list[FeedbackEvidence]:
        job = self.job_manager.get(selector.source_id)
        if job is None:
            raise FeedbackAdapterError(
                "FEEDBACK_BACKTEST_JOB_NOT_FOUND",
                "Backtest job은 현재 backend 메모리에 존재하지 않습니다.",
            )
        if job.status != "completed" or not isinstance(job.result, dict):
            raise FeedbackAdapterError(
                "FEEDBACK_BACKTEST_NOT_COMPLETED",
                "완료된 Backtest job만 평가 원본으로 사용할 수 있습니다.",
            )
        result = job.result
        config = result.get("config") if isinstance(result.get("config"), dict) else {}
        policy = (
            result.get("production_exit_policy")
            if isinstance(result.get("production_exit_policy"), dict)
            else {}
        )
        trades = result.get("trades") if isinstance(result.get("trades"), list) else []
        market = str(config.get("market") or "") or None
        strategy = str(result.get("strategy") or "PULLBACK")
        evidence: list[FeedbackEvidence] = []
        for index, raw_trade in enumerate(trades):
            if not isinstance(raw_trade, dict):
                continue
            signal_date = str(raw_trade.get("signal_date") or "") or None
            trade_market = str(raw_trade.get("market") or market or "") or None
            if not self._matches(
                signal_date=signal_date,
                market=trade_market,
                strategy=strategy,
                selector=selector,
            ):
                continue
            net_return = _float(raw_trade.get("net_return_pct"))
            gross_return = _float(raw_trade.get("gross_return_pct"))
            payload = {
                "job_id": job.job_id,
                "trade": raw_trade,
                "config": config,
                "production_exit_policy": policy,
            }
            evidence.append(
                FeedbackEvidence(
                    source_type="BACKTEST",
                    source_owner="BACKTEST_JOB_MEMORY",
                    source_id=job.job_id,
                    source_item_id=f"trade:{index}:{signal_date or 'unknown'}",
                    source_hash=digest_json(payload),
                    durability="EPHEMERAL",
                    origin_kind="BACKTEST_SIMULATION",
                    market=trade_market,
                    ticker=str(config.get("code") or "") or None,
                    name=None,
                    signal_date=signal_date,
                    strategy=strategy,
                    decision_status=None,
                    scanner_version=str(result.get("version") or "") or None,
                    scanner_baseline=None,
                    horizon_intent="LEGACY_UNSPECIFIED",
                    horizon_policy_version=None,
                    metric_definition="BACKTEST_TRADE_RESULT_V1",
                    execution_policy_version=str(config.get("target_policy") or "") or None,
                    exit_policy_token=str(policy.get("cache_token") or "") or None,
                    fee_pct=None,
                    tax_pct=None,
                    slippage_pct=None,
                    maturity_status="MATURE_REALIZED",
                    inclusion_status="INCLUDED",
                    exclusion_reason=None,
                    available_trading_days=_int(raw_trade.get("holding_days")),
                    metrics={
                        "gross_return_pct": gross_return,
                        "net_return_pct": net_return,
                        "holding_days": _int(raw_trade.get("holding_days")),
                        "exit_reason": raw_trade.get("exit_reason"),
                    },
                    source_observed_at=job.updated_at,
                    metadata={
                        "selection_method": "BACKTEST_STRATEGY_SIMULATION",
                        "evaluation_window": "ENTRY_TO_EXIT",
                        "selector_date_from": selector.date_from,
                        "selector_date_to": selector.date_to,
                        "source_period_start": config.get("start_date"),
                        "source_period_end": config.get("end_date"),
                        "source_durability_warning": "PROCESS_MEMORY_ONLY",
                        "start_date": config.get("start_date"),
                        "end_date": config.get("end_date"),
                        "round_trip_cost_pct": config.get("round_trip_cost_pct"),
                        "max_holding_days": config.get("max_holding_days"),
                    },
                )
            )
        return evidence

    def resolve_exact(
        self,
        *,
        source_type: str,
        source_id: str,
        source_item_id: str,
    ) -> FeedbackEvidence | None:
        selector = EvidenceSelector(source_type=source_type, source_id=source_id)
        try:
            rows = self.resolve(selector)
        except FeedbackAdapterError:
            return None
        return next(
            (row for row in rows if row.source_item_id == source_item_id),
            None,
        )
