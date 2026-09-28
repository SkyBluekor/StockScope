from __future__ import annotations

import json
import sqlite3
import statistics
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from app.backtest.engine import BacktestEngine
from app.backtest.models import BacktestConfig
from app.backtest.production_exit_policy import (
    ProductionExitPolicyEngine,
    production_policy_cache_token,
)
from app.backtest.scanner import StockScannerService
from app.market.providers import KrxProvider
from app.strategy.models import StrategyName


class ProspectiveEvaluationError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _decimal(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return result if result.is_finite() and result > 0 else None


def _float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if result == result else None


def _pct(value: Decimal | None, reference: Decimal | None) -> float | None:
    if value is None or reference is None or reference <= 0:
        return None
    return round(float((value - reference) / reference * Decimal("100")), 4)


def _json_dict(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def _candidate_root(snapshot: dict[str, Any]) -> dict[str, Any]:
    if isinstance(snapshot.get("entry_risk_guide"), dict):
        return snapshot
    nested = snapshot.get("candidate")
    return nested if isinstance(nested, dict) else snapshot


def _plan_from_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    root = _candidate_root(snapshot)
    guide = root.get("entry_risk_guide")
    guide = guide if isinstance(guide, dict) else {}
    price_rule = guide.get("price_rule")
    price_rule = price_rule if isinstance(price_rule, dict) else {}
    risk = guide.get("risk")
    risk = risk if isinstance(risk, dict) else {}
    return {
        "entry_rule": {
            "kind": str(price_rule.get("kind") or "UNAVAILABLE").upper(),
            "range_low": price_rule.get("range_low"),
            "range_high": price_rule.get("range_high"),
            "trigger_price": price_rule.get("trigger_price"),
        },
        "stop_price": _decimal(
            risk.get("invalidation_price")
            or risk.get("stop_zone_high")
            or risk.get("stop_price")
        ),
        "target1_price": _decimal(risk.get("target1_price")),
        "target2_price": _decimal(risk.get("target2_price")),
    }


def _entry_comparable(rule: dict[str, Any]) -> bool:
    kind = str(rule.get("kind") or "").upper()
    if kind == "RANGE":
        return _decimal(rule.get("range_low")) is not None and _decimal(rule.get("range_high")) is not None
    if kind in {"ABOVE", "AT_OR_BELOW"}:
        return _decimal(rule.get("trigger_price")) is not None
    return False


def _entry_touched(rule: dict[str, Any], *, low: Decimal, high: Decimal) -> bool:
    kind = str(rule.get("kind") or "").upper()
    if kind == "RANGE":
        lower = _decimal(rule.get("range_low"))
        upper = _decimal(rule.get("range_high"))
        if lower is None or upper is None:
            return False
        if lower > upper:
            lower, upper = upper, lower
        return high >= lower and low <= upper
    if kind == "ABOVE":
        trigger = _decimal(rule.get("trigger_price"))
        return trigger is not None and high >= trigger
    if kind == "AT_OR_BELOW":
        trigger = _decimal(rule.get("trigger_price"))
        return trigger is not None and low <= trigger
    return False


def _metric(values: list[float]) -> dict[str, Any]:
    return {
        "sample_count": len(values),
        "average_pct": round(sum(values) / len(values), 4) if values else None,
        "median_pct": round(float(statistics.median(values)), 4) if values else None,
    }


class ReadOnlyMarketEvidence:
    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)

    def connect(self) -> sqlite3.Connection:
        if not self.db_path.is_file():
            raise ProspectiveEvaluationError(
                "PROSPECTIVE_MARKET_STORE_NOT_FOUND",
                f"Market Store를 찾을 수 없습니다: {self.db_path}",
            )
        uri = self.db_path.resolve().as_uri() + "?mode=ro"
        conn = sqlite3.connect(uri, uri=True, timeout=10.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA query_only=ON")
        return conn

    @staticmethod
    def market_days(
        conn: sqlite3.Connection,
        *,
        market: str,
        after_date: str,
        limit: int,
    ) -> list[str]:
        rows = conn.execute(
            """
            SELECT bas_dd
            FROM day_status
            WHERE market=? AND kind='stock' AND status='data' AND bas_dd>?
            ORDER BY bas_dd
            LIMIT ?
            """,
            (market, after_date.replace("-", ""), int(limit)),
        ).fetchall()
        return [str(row["bas_dd"]) for row in rows]

    @staticmethod
    def stock_row(
        conn: sqlite3.Connection,
        *,
        market: str,
        ticker: str,
        bas_dd: str,
    ) -> dict[str, Any] | None:
        row = conn.execute(
            """
            SELECT row_json
            FROM stock_daily
            WHERE market=? AND stock_code=? AND bas_dd=?
            """,
            (market, ticker, bas_dd),
        ).fetchone()
        return _json_dict(str(row["row_json"])) if row is not None else None

    @staticmethod
    def stock_rows(
        conn: sqlite3.Connection,
        *,
        market: str,
        ticker: str,
        start_dd: str,
        end_dd: str,
    ) -> list[dict[str, Any]]:
        rows = conn.execute(
            """
            SELECT bas_dd,row_json
            FROM stock_daily
            WHERE market=? AND stock_code=? AND bas_dd>=? AND bas_dd<=?
            ORDER BY bas_dd
            """,
            (market, ticker, start_dd, end_dd),
        ).fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            payload = _json_dict(str(row["row_json"]))
            payload.setdefault("date", str(row["bas_dd"]))
            result.append(payload)
        return result

    @staticmethod
    def index_rows(
        conn: sqlite3.Connection,
        *,
        market: str,
        start_dd: str,
        end_dd: str,
    ) -> list[dict[str, Any]]:
        rows = conn.execute(
            """
            SELECT bas_dd,row_json
            FROM main_index_daily
            WHERE market=? AND bas_dd>=? AND bas_dd<=?
            ORDER BY bas_dd
            """,
            (market, start_dd, end_dd),
        ).fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            payload = _json_dict(str(row["row_json"]))
            payload.setdefault("date", str(row["bas_dd"]))
            result.append(payload)
        return result


class ProspectiveEvaluator:
    """Local-only evaluator for frozen prospective Scanner recommendations."""

    def __init__(self, market_store_db: Path) -> None:
        self.market = ReadOnlyMarketEvidence(market_store_db)

    @staticmethod
    def _compact(value: str) -> str:
        return str(value or "").replace("-", "")

    @staticmethod
    def _iso(value: str) -> str:
        raw = str(value or "").replace("-", "")
        if len(raw) == 8 and raw.isdigit():
            return f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}"
        return str(value or "")

    @staticmethod
    def _row_date(row: dict[str, Any]) -> str:
        return str(row.get("date") or "").replace("-", "")

    @staticmethod
    def _split_for_signal(
        signal_date: str,
        spec: dict[str, Any],
        future_days: list[str],
    ) -> tuple[str, str | None]:
        dev_start = spec.get("development_start")
        dev_end = spec.get("development_end")
        hold_start = spec.get("holdout_start")
        hold_end = spec.get("holdout_end")

        if hold_start and signal_date >= hold_start and (not hold_end or signal_date <= hold_end):
            return "HOLDOUT", None
        if dev_start and signal_date < dev_start:
            return "EXCLUDED", "BEFORE_DEVELOPMENT"
        if dev_end and signal_date <= dev_end:
            if hold_start:
                overlaps = any(
                    ProspectiveEvaluator._iso(day) >= hold_start
                    for day in future_days[: int(spec.get("purge_trading_days") or 0)]
                )
                if overlaps:
                    return "PURGED", "HOLDOUT_BOUNDARY_OVERLAP"
            return "DEVELOPMENT", None
        if not dev_start and not dev_end and not hold_start and not hold_end:
            return "UNSPLIT", "TIME_SPLIT_NOT_DEFINED"
        return "EXCLUDED", "OUTSIDE_PROTOCOL_PERIOD"

    @staticmethod
    def _observation(
        *,
        signal_row: dict[str, Any] | None,
        future_days: list[str],
        future_rows: dict[str, dict[str, Any]],
        snapshot: dict[str, Any],
        observation_windows: list[int],
    ) -> dict[str, Any]:
        reference = _decimal((signal_row or {}).get("close"))
        plan = _plan_from_snapshot(snapshot)
        returns: dict[int, float | None] = {}
        for horizon in observation_windows:
            if len(future_days) < horizon:
                returns[horizon] = None
                continue
            day = future_days[horizon - 1]
            close = _decimal((future_rows.get(day) or {}).get("close"))
            returns[horizon] = _pct(close, reference)

        highest: Decimal | None = None
        lowest: Decimal | None = None
        entry_rule = plan["entry_rule"]
        entry_comparable = _entry_comparable(entry_rule)
        entry_touched = False
        stop = plan["stop_price"]
        target1 = plan["target1_price"]
        target2 = plan["target2_price"]
        stop_touched = False
        target1_touched = False
        target2_touched = False

        for bas_dd in future_days:
            row = future_rows.get(bas_dd) or {}
            high = _decimal(row.get("high"))
            low = _decimal(row.get("low"))
            if high is None or low is None:
                continue
            highest = high if highest is None or high > highest else highest
            lowest = low if lowest is None or low < lowest else lowest
            if entry_comparable and not entry_touched and _entry_touched(entry_rule, low=low, high=high):
                entry_touched = True
            if stop is not None and low <= stop:
                stop_touched = True
            if target1 is not None and high >= target1:
                target1_touched = True
            if target2 is not None and high >= target2:
                target2_touched = True

        return {
            "reference_price": _float(reference),
            "returns": returns,
            "mfe_pct": _pct(highest, reference),
            "mae_pct": _pct(lowest, reference),
            "entry_comparable": entry_comparable,
            "entry_touched": entry_touched,
            "stop_comparable": stop is not None,
            "stop_touched": stop_touched,
            "target1_comparable": target1 is not None,
            "target1_touched": target1_touched,
            "target2_comparable": target2 is not None,
            "target2_touched": target2_touched,
        }

    @staticmethod
    def _scanner() -> StockScannerService:
        # Only pure local reconstruction methods are used. The provider has no key,
        # and evaluation never calls its network methods.
        return StockScannerService(
            KrxProvider(None),
            market_store=object(),  # type: ignore[arg-type]
            engine=BacktestEngine(),
        )

    def _execution(
        self,
        *,
        sample: dict[str, Any],
        stock_rows: list[dict[str, Any]],
        index_rows: list[dict[str, Any]],
        signal_index: int,
        spec: dict[str, Any],
        available_future_days: int,
    ) -> dict[str, Any]:
        snapshot = dict(sample["snapshot"])
        action = str(snapshot.get("action") or sample.get("action") or "").strip()
        if action != "ENTRY_CANDIDATE":
            return {
                "execution_status": "NOT_EXECUTED",
                "execution_reason": (
                    "SCANNER_WAIT" if action == "WAIT"
                    else "SCANNER_NO_TRADE" if action == "NO_TRADE"
                    else "SCANNER_NOT_ENTRY_CANDIDATE"
                ),
            }

        strategy_raw = str(sample.get("strategy") or "").strip()
        try:
            strategy = StrategyName(strategy_raw)
        except ValueError:
            return {
                "execution_status": "FAILED",
                "execution_reason": "STRATEGY_INVALID",
            }

        scanner = self._scanner()
        signal_row = dict(stock_rows[signal_index])
        signal_row.setdefault("code", sample["ticker"])
        signal_row.setdefault("name", sample.get("name") or sample["ticker"])
        asof_rows = stock_rows[: signal_index + 1]
        signal_date = str(sample["signal_date"])

        quick = scanner._quick_current_candidate(  # noqa: SLF001
            market=sample["market"],
            latest_date=self._compact(signal_date),
            row=signal_row,
            stock_rows=asof_rows,
            index_rows=index_rows,
            sector_input=None,
        )
        if quick is None:
            return {
                "execution_status": "FAILED",
                "execution_reason": "SIGNAL_RECONSTRUCTION_FAILED",
            }
        rebuilt = scanner._current_candidate(quick)  # noqa: SLF001
        if rebuilt is None:
            return {
                "execution_status": "FAILED",
                "execution_reason": "SIGNAL_RECONSTRUCTION_FAILED",
            }

        stored_state = str(
            sample.get("candidate_state")
            or sample.get("decision_status")
            or ""
        ).strip()
        stored_action = action
        rebuilt_action = str(rebuilt.get("action") or "").strip()
        rebuilt_state = str(rebuilt.get("candidate_state") or "").strip()
        rebuilt_strategy = str(quick.get("quick_strategy") or "").strip()
        if (
            rebuilt_strategy != strategy_raw
            or rebuilt_action != stored_action
            or (stored_state and rebuilt_state != stored_state)
        ):
            return {
                "execution_status": "FAILED",
                "execution_reason": "SIGNAL_PARITY_MISMATCH",
                "parity": {
                    "stored_strategy": strategy_raw,
                    "rebuilt_strategy": rebuilt_strategy,
                    "stored_action": stored_action,
                    "rebuilt_action": rebuilt_action,
                    "stored_state": stored_state,
                    "rebuilt_state": rebuilt_state,
                },
            }

        total_cost = (
            float(spec.get("round_trip_cost_pct") or 0.0)
            + float(spec.get("fee_pct") or 0.0)
            + float(spec.get("tax_pct") or 0.0)
            + float(spec.get("slippage_pct") or 0.0)
        )
        config = BacktestConfig(
            code=sample["ticker"],
            market=sample["market"],
            start_date=signal_date,
            end_date=self._iso(self._row_date(stock_rows[-1])),
            initial_capital=10_000_000,
            max_holding_days=int(spec.get("max_holding_days") or 20),
            round_trip_cost_pct=total_cost,
        )
        signal = scanner.engine._signal_snapshot(  # noqa: SLF001
            stock_rows=stock_rows,
            index_rows=index_rows,
            index=signal_index,
            config=config,
            sector_input=None,
        )
        if signal is None:
            return {
                "execution_status": "FAILED",
                "execution_reason": "SIGNAL_SNAPSHOT_FAILED",
            }
        audit = dict(signal.get("audit_context") or {})
        if bool(audit.get("future_data_used")):
            raise ProspectiveEvaluationError(
                "PROSPECTIVE_LOOKAHEAD_DETECTED",
                "D 시점 signal 재구성에서 미래 데이터 사용이 감지되었습니다.",
            )
        if self._iso(str(signal.get("signal_date") or "")) != signal_date:
            return {
                "execution_status": "FAILED",
                "execution_reason": "SIGNAL_DATE_MISMATCH",
            }
        evaluation = (signal.get("evaluations") or {}).get(strategy.value)
        if evaluation is None:
            return {
                "execution_status": "FAILED",
                "execution_reason": "STRATEGY_EVALUATION_MISSING",
            }
        signal["strategy_score"] = int(getattr(evaluation, "score", 0) or 0)
        signal["strategy_eligible"] = bool(getattr(evaluation, "eligible", False))

        current_token = production_policy_cache_token()
        expected_token = str(spec.get("exit_policy_token") or "")
        if expected_token and expected_token != current_token:
            raise ProspectiveEvaluationError(
                "PROSPECTIVE_EXIT_POLICY_CHANGED",
                "Protocol 생성 후 Production Exit Policy가 변경되었습니다. 새 protocol이 필요합니다.",
            )

        production = ProductionExitPolicyEngine(scanner.engine)
        trade, _, resolution = production.simulate_trade(
            signal=signal,
            stock_rows=stock_rows,
            config=config,
            strategy=strategy,
        )
        if trade is None:
            return {
                "execution_status": "RISK_PLAN_BLOCKED",
                "execution_reason": "PRODUCTION_EXECUTION_UNAVAILABLE",
                "policy": resolution.to_dict(),
            }

        exit_reason = str(getattr(trade, "exit_reason", "") or "")
        max_holding_days = int(spec.get("max_holding_days") or 20)
        if exit_reason == "END_OF_DATA" and available_future_days < max_holding_days:
            return {
                "execution_status": "CENSORED",
                "execution_reason": "MARKET_DATA_CUTOFF",
                "entry_date": str(getattr(trade, "entry_date", "") or "") or None,
                "entry_price": _float(getattr(trade, "entry_price", None)),
                "holding_days": int(getattr(trade, "holding_days", 0) or 0),
                "mark_return_pct": _float(getattr(trade, "net_return_pct", None)),
                "policy": resolution.to_dict(),
            }

        return {
            "execution_status": "CLOSED",
            "execution_reason": exit_reason or None,
            "entry_date": str(getattr(trade, "entry_date", "") or "") or None,
            "entry_price": _float(getattr(trade, "entry_price", None)),
            "exit_date": str(getattr(trade, "exit_date", "") or "") or None,
            "exit_price": _float(getattr(trade, "exit_price", None)),
            "exit_reason": exit_reason or None,
            "holding_days": int(getattr(trade, "holding_days", 0) or 0),
            "gross_return_pct": _float(getattr(trade, "gross_return_pct", None)),
            "net_return_pct": _float(getattr(trade, "net_return_pct", None)),
            "policy": resolution.to_dict(),
        }

    def evaluate_sample(
        self,
        *,
        sample: dict[str, Any],
        spec: dict[str, Any],
    ) -> dict[str, Any]:
        signal_date = str(sample.get("signal_date") or "")
        market = str(sample.get("market") or "").upper()
        ticker = str(sample.get("ticker") or "").upper()
        if not signal_date or not market or not ticker:
            raise ProspectiveEvaluationError(
                "PROSPECTIVE_SAMPLE_INVALID",
                "Prospective sample의 signal date/market/ticker가 없습니다.",
            )

        observation_windows = sorted(
            {
                int(value)
                for value in (spec.get("observation_windows") or [5, 10, 20])
                if int(value) > 0
            }
        )
        if not observation_windows:
            raise ProspectiveEvaluationError(
                "PROSPECTIVE_PROTOCOL_WINDOW_INVALID",
                "하나 이상의 observation window가 필요합니다.",
            )
        max_observation = max(observation_windows)
        max_holding = int(spec.get("max_holding_days") or 20)
        requested_future = max(max_observation, max_holding)
        signal_day = date.fromisoformat(signal_date)
        history_start = signal_day - timedelta(
            days=StockScannerService.FAST_HISTORY_CALENDAR_DAYS
        )

        with self.market.connect() as conn:
            future_days = self.market.market_days(
                conn,
                market=market,
                after_date=signal_date,
                limit=requested_future,
            )
            split, split_reason = self._split_for_signal(
                signal_date,
                spec,
                future_days,
            )
            signal_key = signal_date.replace("-", "")
            signal_row = self.market.stock_row(
                conn,
                market=market,
                ticker=ticker,
                bas_dd=signal_key,
            )
            rows_by_day = {}
            if future_days:
                rows = self.market.stock_rows(
                    conn,
                    market=market,
                    ticker=ticker,
                    start_dd=future_days[0],
                    end_dd=future_days[-1],
                )
                rows_by_day = {
                    self._row_date(row): row
                    for row in rows
                }
            observation = self._observation(
                signal_row=signal_row,
                future_days=future_days,
                future_rows=rows_by_day,
                snapshot=dict(sample["snapshot"]),
                observation_windows=observation_windows,
            )

            execution: dict[str, Any]
            if split in {"PURGED", "EXCLUDED"}:
                execution = {
                    "execution_status": "NOT_EVALUATED",
                    "execution_reason": split_reason,
                }
            elif str(spec.get("execution_mode") or "").upper() != "PRODUCTION_POLICY":
                execution = {
                    "execution_status": "NOT_EVALUATED",
                    "execution_reason": "EXECUTION_MODE_DISABLED",
                }
            else:
                end_dd = future_days[-1] if future_days else signal_key
                stock_rows = self.market.stock_rows(
                    conn,
                    market=market,
                    ticker=ticker,
                    start_dd=history_start.strftime("%Y%m%d"),
                    end_dd=end_dd,
                )
                signal_indices = [
                    index
                    for index, row in enumerate(stock_rows)
                    if self._row_date(row) == signal_key
                ]
                index_rows = self.market.index_rows(
                    conn,
                    market=market,
                    start_dd=history_start.strftime("%Y%m%d"),
                    end_dd=signal_key,
                )
                if len(signal_indices) != 1:
                    execution = {
                        "execution_status": "FAILED",
                        "execution_reason": "SIGNAL_DATA_MISSING",
                    }
                else:
                    execution = self._execution(
                        sample=sample,
                        stock_rows=stock_rows,
                        index_rows=index_rows,
                        signal_index=signal_indices[0],
                        spec=spec,
                        available_future_days=len(future_days),
                    )

        mature = len(future_days) >= max_observation
        if split in {"PURGED", "EXCLUDED"}:
            maturity = "EXCLUDED"
        elif mature:
            maturity = "MATURE"
        elif len(future_days) > 0:
            maturity = "IMMATURE"
        else:
            maturity = "NOT_CALCULATED"

        returns = observation["returns"]
        now = datetime.now(timezone.utc).isoformat()
        return {
            "capture_run_id": sample["capture_run_id"],
            "sample_index": int(sample["sample_index"]),
            "split": split,
            "maturity_status": maturity,
            "exclusion_reason": split_reason if split in {"PURGED", "EXCLUDED"} else None,
            "signal_date": signal_date,
            "market": market,
            "ticker": ticker,
            "strategy": sample.get("strategy"),
            "available_trading_days": len(future_days),
            "evaluated_through": self._iso(future_days[-1]) if future_days else None,
            "return_5d": returns.get(5),
            "return_10d": returns.get(10),
            "return_20d": returns.get(20),
            "mfe_pct": observation["mfe_pct"],
            "mae_pct": observation["mae_pct"],
            "entry_comparable": 1 if observation["entry_comparable"] else 0,
            "entry_touched": 1 if observation["entry_touched"] else 0,
            "stop_comparable": 1 if observation["stop_comparable"] else 0,
            "stop_touched": 1 if observation["stop_touched"] else 0,
            "target1_comparable": 1 if observation["target1_comparable"] else 0,
            "target1_touched": 1 if observation["target1_touched"] else 0,
            "target2_comparable": 1 if observation["target2_comparable"] else 0,
            "target2_touched": 1 if observation["target2_touched"] else 0,
            "execution_status": execution.get("execution_status") or "NOT_EVALUATED",
            "execution_reason": execution.get("execution_reason"),
            "entry_date": execution.get("entry_date"),
            "entry_price": execution.get("entry_price"),
            "exit_date": execution.get("exit_date"),
            "exit_price": execution.get("exit_price"),
            "exit_reason": execution.get("exit_reason"),
            "holding_days": execution.get("holding_days"),
            "gross_return_pct": execution.get("gross_return_pct"),
            "net_return_pct": execution.get("net_return_pct"),
            "mark_return_pct": execution.get("mark_return_pct"),
            "details": {
                "reference_price": observation["reference_price"],
                "execution": execution,
                "observation_windows": observation_windows,
                "future_data_used_for_signal": False,
            },
            "computed_at": now,
        }

    @staticmethod
    def summarize(
        *,
        protocol: dict[str, Any],
        units: list[dict[str, Any]],
    ) -> tuple[dict[str, int], dict[str, Any]]:
        split_counts = Counter(str(unit["split"]) for unit in units)
        maturity_counts = Counter(str(unit["maturity_status"]) for unit in units)
        execution_counts = Counter(str(unit["execution_status"]) for unit in units)
        strategy_counts = Counter(str(unit.get("strategy") or "UNKNOWN") for unit in units)
        market_counts = Counter(str(unit["market"]) for unit in units)
        eligible = [
            unit for unit in units
            if unit["split"] not in {"PURGED", "EXCLUDED"}
        ]

        observation = {}
        for horizon in (5, 10, 20):
            key = f"return_{horizon}d"
            observation[f"{horizon}d"] = _metric(
                [
                    float(unit[key])
                    for unit in eligible
                    if unit.get(key) is not None
                ]
            )
        realized = _metric(
            [
                float(unit["net_return_pct"])
                for unit in eligible
                if unit["execution_status"] == "CLOSED"
                and unit.get("net_return_pct") is not None
            ]
        )
        censored_mark = _metric(
            [
                float(unit["mark_return_pct"])
                for unit in eligible
                if unit["execution_status"] == "CENSORED"
                and unit.get("mark_return_pct") is not None
            ]
        )
        mature_count = sum(
            1 for unit in eligible if unit["maturity_status"] == "MATURE"
        )
        immature_count = sum(
            1 for unit in eligible
            if unit["maturity_status"] in {"IMMATURE", "NOT_CALCULATED"}
        )
        failed_count = sum(
            1 for unit in eligible if unit["execution_status"] == "FAILED"
        )
        excluded_count = sum(
            1 for unit in units if unit["split"] in {"PURGED", "EXCLUDED"}
        )
        capture_ids = {str(unit["capture_run_id"]) for unit in units}

        strategy_rows: list[dict[str, Any]] = []
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for unit in eligible:
            grouped[str(unit.get("strategy") or "UNKNOWN")].append(unit)
        for strategy, rows in sorted(grouped.items()):
            strategy_rows.append(
                {
                    "strategy": strategy,
                    "sample_count": len(rows),
                    "mature_count": sum(1 for row in rows if row["maturity_status"] == "MATURE"),
                    "return_20d": _metric(
                        [float(row["return_20d"]) for row in rows if row.get("return_20d") is not None]
                    ),
                    "realized_net_return": _metric(
                        [
                            float(row["net_return_pct"])
                            for row in rows
                            if row["execution_status"] == "CLOSED"
                            and row.get("net_return_pct") is not None
                        ]
                    ),
                    "execution_status": dict(
                        Counter(str(row["execution_status"]) for row in rows)
                    ),
                }
            )

        counts = {
            "source_capture_count": len(capture_ids),
            "source_sample_count": len(units),
            "development_count": int(split_counts.get("DEVELOPMENT", 0)),
            "holdout_count": int(split_counts.get("HOLDOUT", 0)),
            "purged_count": int(split_counts.get("PURGED", 0)),
            "mature_count": mature_count,
            "immature_count": immature_count,
            "excluded_count": excluded_count,
            "failed_count": failed_count,
        }
        summary = {
            "protocol_id": protocol["id"],
            "protocol_version": protocol["protocol_version"],
            "protocol_spec_hash": protocol["spec_hash"],
            "protocol": protocol["spec"],
            "counts": counts,
            "split_counts": dict(split_counts),
            "maturity_counts": dict(maturity_counts),
            "execution_counts": dict(execution_counts),
            "market_counts": dict(market_counts),
            "strategy_counts": dict(strategy_counts),
            "candidate_observation": observation,
            "virtual_execution": {
                "realized_net_return": realized,
                "censored_mark_return": censored_mark,
                "censored_is_realized_return": False,
            },
            "strategy_breakdown": strategy_rows,
            "minimum_sample_policy_defined": False,
            "performance_conclusion_allowed": False,
            "strategy_promotion_allowed": False,
            "adaptive_rotation_enabled": False,
            "evidence_state": (
                "INSUFFICIENT_EVIDENCE"
                if not eligible or (mature_count == 0 and realized["sample_count"] == 0)
                else "SAMPLE_SIZE_POLICY_UNDEFINED"
            ),
            "notes": [
                "Prospective 표본은 Scanner 완료 시점에 보존되며 사용자 Tracking 선택과 분리됩니다.",
                "Development/Holdout 경계를 넘는 관찰기간은 PURGED로 제외합니다.",
                "CENSORED는 실현손익이나 0% 수익으로 계산하지 않습니다.",
                "최소 표본·승격/강등 기준이 미정이므로 전략 우수 결론을 내리지 않습니다.",
            ],
        }
        return counts, summary
