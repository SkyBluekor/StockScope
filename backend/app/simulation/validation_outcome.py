from __future__ import annotations

import json
import sqlite3
import statistics
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from .validation_catalog import HistoricalValidationCandidate, HistoricalValidationCatalog


DEFAULT_MARKET_STORE_DB = (
    Path(__file__).resolve().parents[2]
    / "runtime"
    / "market_history"
    / "market_history.db"
)


class HistoricalValidationOutcomeError(RuntimeError):
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
        "stop_price": _decimal(risk.get("invalidation_price")),
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


class HistoricalValidationOutcomeService:
    """Evaluate stored VAL.1 candidates using D+1..D+20 confirmed local EOD bars."""

    HORIZON = 20

    def __init__(
        self,
        catalog: HistoricalValidationCatalog,
        market_store_db: Path | None = None,
    ) -> None:
        self.catalog = catalog
        self.catalog.initialize()
        self.market_store_db = Path(market_store_db or DEFAULT_MARKET_STORE_DB)

    def _market_conn(self) -> sqlite3.Connection:
        if not self.market_store_db.is_file():
            raise HistoricalValidationOutcomeError(
                "VAL3_MARKET_STORE_NOT_FOUND",
                f"Market Store를 찾을 수 없습니다: {self.market_store_db}",
            )
        uri = f"{self.market_store_db.resolve().as_uri()}?mode=ro"
        conn = sqlite3.connect(uri, uri=True)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA query_only=ON")
        return conn

    @staticmethod
    def _market_days(
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
    def _stock_row(
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
    def _stock_rows(
        conn: sqlite3.Connection,
        *,
        market: str,
        ticker: str,
        first_dd: str,
        last_dd: str,
    ) -> dict[str, dict[str, Any]]:
        rows = conn.execute(
            """
            SELECT bas_dd,row_json
            FROM stock_daily
            WHERE market=? AND stock_code=? AND bas_dd>=? AND bas_dd<=?
            ORDER BY bas_dd
            """,
            (market, ticker, first_dd, last_dd),
        ).fetchall()
        return {
            str(row["bas_dd"]): _json_dict(str(row["row_json"]))
            for row in rows
        }

    @staticmethod
    def _price(row: dict[str, Any] | None, key: str) -> Decimal | None:
        return _decimal(row.get(key)) if row else None

    def _evaluate_candidate(
        self,
        conn: sqlite3.Connection,
        candidate: HistoricalValidationCandidate,
    ) -> dict[str, Any]:
        signal_key = candidate.trading_date.replace("-", "")
        signal_row = self._stock_row(
            conn,
            market=candidate.market,
            ticker=candidate.ticker,
            bas_dd=signal_key,
        )
        reference = self._price(signal_row, "close")
        plan = _plan_from_snapshot(candidate.snapshot)

        market_days = self._market_days(
            conn,
            market=candidate.market,
            after_date=candidate.trading_date,
            limit=self.HORIZON,
        )
        rows_by_day = (
            self._stock_rows(
                conn,
                market=candidate.market,
                ticker=candidate.ticker,
                first_dd=market_days[0],
                last_dd=market_days[-1],
            )
            if market_days
            else {}
        )

        returns: dict[int, float | None] = {}
        for horizon in (5, 10, 20):
            if len(market_days) < horizon:
                returns[horizon] = None
                continue
            horizon_day = market_days[horizon - 1]
            returns[horizon] = _pct(
                self._price(rows_by_day.get(horizon_day), "close"),
                reference,
            )

        highest: Decimal | None = None
        lowest: Decimal | None = None

        entry_rule = plan["entry_rule"]
        entry_comparable = _entry_comparable(entry_rule)
        entry_touched = False
        entry_touch_date: str | None = None

        stop = plan["stop_price"]
        target1 = plan["target1_price"]
        target2 = plan["target2_price"]
        stop_touched = False
        stop_touch_date: str | None = None
        target1_touched = False
        target1_touch_date: str | None = None
        target2_touched = False
        target2_touch_date: str | None = None

        for bas_dd in market_days:
            row = rows_by_day.get(bas_dd)
            high = self._price(row, "high")
            low = self._price(row, "low")
            if high is None or low is None:
                continue

            highest = high if highest is None or high > highest else highest
            lowest = low if lowest is None or low < lowest else lowest
            iso = f"{bas_dd[:4]}-{bas_dd[4:6]}-{bas_dd[6:8]}"

            if entry_comparable and not entry_touched and _entry_touched(entry_rule, low=low, high=high):
                entry_touched = True
                entry_touch_date = iso

            # Independent checks: no intraday order is inferred from one daily bar.
            if stop is not None and not stop_touched and low <= stop:
                stop_touched = True
                stop_touch_date = iso
            if target1 is not None and not target1_touched and high >= target1:
                target1_touched = True
                target1_touch_date = iso
            if target2 is not None and not target2_touched and high >= target2:
                target2_touched = True
                target2_touch_date = iso

        return {
            "validation_id": candidate.validation_id,
            "trading_date": candidate.trading_date,
            "market": candidate.market,
            "ticker": candidate.ticker,
            "reference_price": None if reference is None else format(reference, "f"),
            "entry_rule_json": json.dumps(entry_rule, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
            "stop_price": None if stop is None else format(stop, "f"),
            "target1_price": None if target1 is None else format(target1, "f"),
            "target2_price": None if target2 is None else format(target2, "f"),
            "available_trading_days": len(market_days),
            "evaluated_through": (
                f"{market_days[-1][:4]}-{market_days[-1][4:6]}-{market_days[-1][6:8]}"
                if market_days else None
            ),
            "return_5d": returns[5],
            "return_10d": returns[10],
            "return_20d": returns[20],
            "mfe_pct": _pct(highest, reference),
            "mae_pct": _pct(lowest, reference),
            "entry_comparable": 1 if entry_comparable else 0,
            "entry_touched": 1 if entry_touched else 0,
            "entry_touch_date": entry_touch_date,
            "stop_comparable": 1 if stop is not None else 0,
            "stop_touched": 1 if stop_touched else 0,
            "stop_touch_date": stop_touch_date,
            "target1_comparable": 1 if target1 is not None else 0,
            "target1_touched": 1 if target1_touched else 0,
            "target1_touch_date": target1_touch_date,
            "target2_comparable": 1 if target2 is not None else 0,
            "target2_touched": 1 if target2_touched else 0,
            "target2_touch_date": target2_touch_date,
            "computed_at": datetime.now(timezone.utc).isoformat(),
        }

    def refresh(self, validation_id: str) -> dict[str, Any]:
        draft = self.catalog.get(validation_id)
        if draft is None:
            raise HistoricalValidationOutcomeError(
                "VAL3_VALIDATION_NOT_FOUND",
                "저장된 Historical Validation을 찾을 수 없습니다.",
            )
        if draft.status != "COMPLETED":
            raise HistoricalValidationOutcomeError(
                "VAL3_REPLAY_NOT_COMPLETED",
                "과거 판단 재현이 완료된 검증만 성과를 계산할 수 있습니다.",
            )

        candidates = self.catalog.list_candidates(validation_id)
        with self._market_conn() as market_conn:
            outcomes = [
                self._evaluate_candidate(market_conn, candidate)
                for candidate in candidates
            ]

        with self.catalog.connect() as conn:
            conn.execute(
                "DELETE FROM historical_validation_candidate_outcome WHERE validation_id=?",
                (validation_id,),
            )
            if outcomes:
                conn.executemany(
                    """
                    INSERT INTO historical_validation_candidate_outcome(
                        validation_id,trading_date,market,ticker,
                        reference_price,entry_rule_json,stop_price,target1_price,target2_price,
                        available_trading_days,evaluated_through,
                        return_5d,return_10d,return_20d,mfe_pct,mae_pct,
                        entry_comparable,entry_touched,entry_touch_date,
                        stop_comparable,stop_touched,stop_touch_date,
                        target1_comparable,target1_touched,target1_touch_date,
                        target2_comparable,target2_touched,target2_touch_date,
                        computed_at
                    ) VALUES(
                        :validation_id,:trading_date,:market,:ticker,
                        :reference_price,:entry_rule_json,:stop_price,:target1_price,:target2_price,
                        :available_trading_days,:evaluated_through,
                        :return_5d,:return_10d,:return_20d,:mfe_pct,:mae_pct,
                        :entry_comparable,:entry_touched,:entry_touch_date,
                        :stop_comparable,:stop_touched,:stop_touch_date,
                        :target1_comparable,:target1_touched,:target1_touch_date,
                        :target2_comparable,:target2_touched,:target2_touch_date,
                        :computed_at
                    )
                    """,
                    outcomes,
                )
        return self.summary(validation_id)

    def list_outcomes(self, validation_id: str) -> list[dict[str, Any]]:
        with self.catalog.connect() as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM historical_validation_candidate_outcome
                WHERE validation_id=?
                ORDER BY trading_date,market,ticker
                """,
                (validation_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def _metric(
        rows: list[dict[str, Any]],
        key: str,
        *,
        mature_only: bool = False,
    ) -> dict[str, Any]:
        selected = [
            row
            for row in rows
            if not mature_only or int(row.get("available_trading_days") or 0) >= 20
        ]
        values = [float(row[key]) for row in selected if row.get(key) is not None]
        return {
            "sample_count": len(values),
            "average_pct": round(sum(values) / len(values), 4) if values else None,
            "median_pct": round(float(statistics.median(values)), 4) if values else None,
        }

    @staticmethod
    def _touch(rows: list[dict[str, Any]], prefix: str) -> dict[str, Any]:
        # An immature candidate is not a failed 20D touch case.
        matured = [
            row for row in rows
            if int(row.get("available_trading_days") or 0) >= 20
        ]
        comparable = sum(1 for row in matured if int(row.get(f"{prefix}_comparable") or 0) == 1)
        touched = sum(1 for row in matured if int(row.get(f"{prefix}_touched") or 0) == 1)
        return {
            "comparable_count": comparable,
            "touched_count": touched,
            "touched_pct": round(touched / comparable * 100.0, 2) if comparable else None,
        }

    def summary(self, validation_id: str) -> dict[str, Any]:
        draft = self.catalog.get(validation_id)
        if draft is None:
            raise HistoricalValidationOutcomeError(
                "VAL3_VALIDATION_NOT_FOUND",
                "저장된 Historical Validation을 찾을 수 없습니다.",
            )

        with self.catalog.connect() as conn:
            candidate_row = conn.execute(
                "SELECT COUNT(*) AS n FROM historical_validation_candidate WHERE validation_id=?",
                (validation_id,),
            ).fetchone()
        total_candidates = int(candidate_row["n"] if candidate_row else 0)
        rows = self.list_outcomes(validation_id)

        replay = {
            "target_trading_days": int(draft.trading_day_count),
            "processed_trading_days": int(draft.processed_day_count),
            "consistent": (
                int(draft.trading_day_count) == int(draft.processed_day_count)
                if draft.status == "COMPLETED" else None
            ),
            "last_completed_date": draft.last_completed_date,
        }

        empty_metric = {"sample_count": 0, "average_pct": None, "median_pct": None}
        empty_touch = {"comparable_count": 0, "touched_count": 0, "touched_pct": None}

        if not rows:
            return {
                "validation_id": validation_id,
                "status": "NOT_CALCULATED",
                "replay": replay,
                "total_candidates": total_candidates,
                "outcome_count": 0,
                "evaluated_candidates": 0,
                "horizons": {
                    "5d": dict(empty_metric),
                    "10d": dict(empty_metric),
                    "20d": dict(empty_metric),
                },
                "mfe_20d": dict(empty_metric),
                "mae_20d": dict(empty_metric),
                "touches": {
                    "entry": dict(empty_touch),
                    "stop": dict(empty_touch),
                    "target1": dict(empty_touch),
                    "target2": dict(empty_touch),
                },
                "computed_at": None,
            }

        return {
            "validation_id": validation_id,
            "status": "READY",
            "replay": replay,
            "total_candidates": total_candidates,
            "outcome_count": len(rows),
            "evaluated_candidates": sum(
                1 for row in rows
                if row.get("reference_price") is not None
                and int(row.get("available_trading_days") or 0) > 0
            ),
            "horizons": {
                "5d": self._metric(rows, "return_5d"),
                "10d": self._metric(rows, "return_10d"),
                "20d": self._metric(rows, "return_20d"),
            },
            "mfe_20d": self._metric(rows, "mfe_pct", mature_only=True),
            "mae_20d": self._metric(rows, "mae_pct", mature_only=True),
            "touches": {
                key: self._touch(rows, key)
                for key in ("entry", "stop", "target1", "target2")
            },
            "computed_at": max(str(row.get("computed_at") or "") for row in rows) or None,
        }

    def _breakdown_rows(
        self,
        rows: list[dict[str, Any]],
        *,
        group_key: str,
        uppercase: bool = False,
    ) -> list[dict[str, Any]]:
        grouped: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            raw = str(row.get(group_key) or "").strip()
            key = raw.upper() if uppercase else raw
            if not key:
                key = "UNKNOWN"
            grouped.setdefault(key, []).append(row)

        result: list[dict[str, Any]] = []
        for key, group_rows in grouped.items():
            result.append(
                {
                    "key": key,
                    "candidate_count": len(group_rows),
                    "horizons": {
                        "5d": self._metric(group_rows, "return_5d"),
                        "10d": self._metric(group_rows, "return_10d"),
                        "20d": self._metric(group_rows, "return_20d"),
                    },
                    "mfe_20d": self._metric(group_rows, "mfe_pct", mature_only=True),
                    "mae_20d": self._metric(group_rows, "mae_pct", mature_only=True),
                    "touches": {
                        name: self._touch(group_rows, name)
                        for name in ("entry", "stop", "target1", "target2")
                    },
                }
            )

        # Candidate count is a stable browsing order only; it is not a performance rank.
        result.sort(key=lambda item: (-int(item["candidate_count"]), str(item["key"])))
        return result

    def breakdown(self, validation_id: str) -> dict[str, Any]:
        draft = self.catalog.get(validation_id)
        if draft is None:
            raise HistoricalValidationOutcomeError(
                "VAL3_VALIDATION_NOT_FOUND",
                "저장된 Historical Validation을 찾을 수 없습니다.",
            )

        # A3 reads only already-computed Simulation DB outcomes.
        # It does not open Market Store or rerun Scanner.
        with self.catalog.connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    c.strategy,
                    c.decision_status,
                    o.*
                FROM historical_validation_candidate c
                JOIN historical_validation_candidate_outcome o
                  ON o.validation_id=c.validation_id
                 AND o.trading_date=c.trading_date
                 AND o.market=c.market
                 AND o.ticker=c.ticker
                WHERE c.validation_id=?
                ORDER BY c.trading_date,c.market,c.ticker
                """,
                (validation_id,),
            ).fetchall()

        data = [dict(row) for row in rows]
        if not data:
            return {
                "validation_id": validation_id,
                "status": "NOT_CALCULATED",
                "strategy": [],
                "decision_status": [],
            }

        return {
            "validation_id": validation_id,
            "status": "READY",
            "strategy": self._breakdown_rows(data, group_key="strategy"),
            "decision_status": self._breakdown_rows(
                data,
                group_key="decision_status",
                uppercase=True,
            ),
        }

