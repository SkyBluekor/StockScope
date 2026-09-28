from __future__ import annotations

import hashlib
import json
import sqlite3
import statistics
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from enum import Enum
from pathlib import Path
from typing import Any, Callable
from uuid import NAMESPACE_URL, uuid5

from app.event_evidence.errors import EventEvidenceContractError
from app.event_evidence.quality import EventEvidenceQualityService


EVENT_EVALUATION_CONTRACT_VERSION = "VN_P6_S1_EVENT_EVALUATION_V1"
EVENT_EVALUATION_PROTOCOL_CONTRACT_VERSION = (
    "VN_P6_S1_EVENT_EVALUATION_PROTOCOL_V1"
)
EVENT_OUTCOME_CONTRACT_VERSION = "VN_P6_S1_EVENT_OUTCOME_V1"
EVENT_EVALUATION_REPORT_CONTRACT_VERSION = "VN_P6_S1_EVENT_REPORT_V1"

EVENT_OBSERVATION_WINDOWS = (1, 5, 20)
REFERENCE_PRICE_RULE = "PREVIOUS_CONFIRMED_DAILY_CLOSE"
MARKET_BENCHMARK_RULE = "MAIN_MARKET_INDEX"


class ControlMethod(str, Enum):
    NONE = "NONE"
    EXPLICIT_MATCH_SET = "EXPLICIT_MATCH_SET"


class HorizonStatus(str, Enum):
    MATURE = "MATURE"
    NOT_MATURED = "NOT_MATURED"
    MISSING_MARKET_DATA = "MISSING_MARKET_DATA"


@dataclass(frozen=True, slots=True)
class EventEvaluationProtocol:
    protocol_id: str
    control_method: ControlMethod = ControlMethod.NONE
    control_approved: bool = False
    observation_windows: tuple[int, ...] = EVENT_OBSERVATION_WINDOWS
    reference_price_rule: str = REFERENCE_PRICE_RULE
    benchmark_rule: str = MARKET_BENCHMARK_RULE
    statistical_test_status: str = "NOT_CONFIGURED"
    minimum_control_count: int | None = None
    contract_version: str = EVENT_EVALUATION_PROTOCOL_CONTRACT_VERSION

    def __post_init__(self) -> None:
        if not str(self.protocol_id or "").strip():
            raise EventEvidenceContractError(
                "EVENT_EVALUATION_PROTOCOL_ID_REQUIRED",
                "Event Evaluation protocol_id가 필요합니다.",
            )
        if self.contract_version != EVENT_EVALUATION_PROTOCOL_CONTRACT_VERSION:
            raise EventEvidenceContractError(
                "EVENT_EVALUATION_PROTOCOL_CONTRACT_MISMATCH",
                "Event Evaluation Protocol contract version이 현재 코드와 다릅니다.",
            )
        try:
            control_method = (
                self.control_method
                if isinstance(self.control_method, ControlMethod)
                else ControlMethod(str(self.control_method))
            )
        except ValueError as exc:
            raise EventEvidenceContractError(
                "EVENT_EVALUATION_CONTROL_METHOD_INVALID",
                f"알 수 없는 control_method입니다: {self.control_method}",
            ) from exc
        object.__setattr__(self, "control_method", control_method)

        windows = tuple(int(value) for value in self.observation_windows)
        if windows != EVENT_OBSERVATION_WINDOWS:
            raise EventEvidenceContractError(
                "EVENT_EVALUATION_WINDOWS_UNAPPROVED",
                "V1 Event Evaluation observation window는 1/5/20 거래일로 고정됩니다.",
            )
        object.__setattr__(self, "observation_windows", windows)
        if self.reference_price_rule != REFERENCE_PRICE_RULE:
            raise EventEvidenceContractError(
                "EVENT_EVALUATION_REFERENCE_RULE_UNAPPROVED",
                "V1 reference price rule은 이전 확정 일봉 종가만 지원합니다.",
            )
        if self.benchmark_rule != MARKET_BENCHMARK_RULE:
            raise EventEvidenceContractError(
                "EVENT_EVALUATION_BENCHMARK_RULE_UNAPPROVED",
                "V1 benchmark rule은 main market index만 지원합니다.",
            )
        if self.minimum_control_count is not None:
            raise EventEvidenceContractError(
                "EVENT_EVALUATION_SAMPLE_THRESHOLD_UNAPPROVED",
                "P6 control 최소 표본 수는 아직 승인되지 않았습니다.",
            )
        if self.control_approved and control_method is not ControlMethod.EXPLICIT_MATCH_SET:
            raise EventEvidenceContractError(
                "EVENT_EVALUATION_CONTROL_PROTOCOL_INVALID",
                "승인된 V1 control은 EXPLICIT_MATCH_SET 방식만 지원합니다.",
            )
        if str(self.statistical_test_status) != "NOT_CONFIGURED":
            raise EventEvidenceContractError(
                "EVENT_EVALUATION_STAT_TEST_UNAPPROVED",
                "P6 통계 검정 기준은 아직 구성되지 않았습니다.",
            )

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["control_method"] = self.control_method.value
        payload["observation_windows"] = list(self.observation_windows)
        return payload


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical_json(value: Any) -> str:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise EventEvidenceContractError(
            "EVENT_EVALUATION_JSON_INVALID",
            "Event Evaluation payload는 canonical JSON으로 직렬화할 수 있어야 합니다.",
        ) from exc


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


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
    return round(float((value / reference - Decimal("1")) * Decimal("100")), 4)


def _parse_aware(value: str, field_name: str) -> datetime:
    text = str(value or "").strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise EventEvidenceContractError(
            "EVENT_EVALUATION_TIME_INVALID",
            f"{field_name}은 timezone이 포함된 ISO-8601 시각이어야 합니다.",
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise EventEvidenceContractError(
            "EVENT_EVALUATION_TIMEZONE_REQUIRED",
            f"{field_name}에는 timezone offset이 필요합니다.",
        )
    return parsed


def _compact_date(value: str) -> str:
    text = str(value or "").strip().replace("-", "")
    if len(text) != 8 or not text.isdigit():
        raise EventEvidenceContractError(
            "EVENT_EVALUATION_DATE_INVALID",
            "날짜는 YYYY-MM-DD 또는 YYYYMMDD 형식이어야 합니다.",
        )
    return text


def _iso_date(value: str) -> str:
    raw = _compact_date(value)
    return f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}"


def _metric(values: list[float]) -> dict[str, Any]:
    return {
        "sample_count": len(values),
        "average_pct": (
            round(sum(values) / len(values), 4) if values else None
        ),
        "median_pct": (
            round(float(statistics.median(values)), 4) if values else None
        ),
        "observed_positive_rate_pct": (
            round(sum(1 for value in values if value > 0) / len(values) * 100, 4)
            if values
            else None
        ),
    }


class ReadOnlyEventMarketEvidence:
    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)

    def connect(self) -> sqlite3.Connection:
        if not self.db_path.is_file():
            raise EventEvidenceContractError(
                "EVENT_EVALUATION_MARKET_STORE_NOT_FOUND",
                f"Market Store를 찾을 수 없습니다: {self.db_path}",
            )
        uri = self.db_path.resolve().as_uri() + "?mode=ro"
        conn = sqlite3.connect(uri, uri=True, timeout=10.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA query_only=ON")
        return conn

    @staticmethod
    def _json(raw: str | None) -> dict[str, Any]:
        if not raw:
            return {}
        try:
            value = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        return value if isinstance(value, dict) else {}

    @staticmethod
    def reference_day(
        conn: sqlite3.Connection,
        *,
        market: str,
        ticker: str,
        before_date: str,
    ) -> str | None:
        row = conn.execute(
            """
            SELECT s.bas_dd
            FROM stock_daily s
            JOIN day_status ds
              ON ds.market=s.market
             AND ds.bas_dd=s.bas_dd
             AND ds.kind='stock'
             AND ds.status='data'
            JOIN day_status di
              ON di.market=s.market
             AND di.bas_dd=s.bas_dd
             AND di.kind='index'
             AND di.status='data'
            JOIN main_index_daily i
              ON i.market=s.market
             AND i.bas_dd=s.bas_dd
            WHERE s.market=? AND s.stock_code=? AND s.bas_dd<?
            ORDER BY s.bas_dd DESC
            LIMIT 1
            """,
            (market, ticker, _compact_date(before_date)),
        ).fetchone()
        return str(row["bas_dd"]) if row is not None else None

    @staticmethod
    def reaction_days(
        conn: sqlite3.Connection,
        *,
        market: str,
        after_date: str,
        limit: int,
    ) -> list[str]:
        rows = conn.execute(
            """
            SELECT s.bas_dd
            FROM day_status s
            JOIN day_status i
              ON i.market=s.market
             AND i.bas_dd=s.bas_dd
             AND i.kind='index'
             AND i.status='data'
            WHERE s.market=?
              AND s.kind='stock'
              AND s.status='data'
              AND s.bas_dd>?
            ORDER BY s.bas_dd
            LIMIT ?
            """,
            (market, _compact_date(after_date), int(limit)),
        ).fetchall()
        return [str(row["bas_dd"]) for row in rows]

    @staticmethod
    def raw_stock_row(
        conn: sqlite3.Connection,
        *,
        market: str,
        ticker: str,
        bas_dd: str,
    ) -> tuple[dict[str, Any] | None, str | None]:
        row = conn.execute(
            """
            SELECT row_json FROM stock_daily
            WHERE market=? AND stock_code=? AND bas_dd=?
            """,
            (market, ticker, bas_dd),
        ).fetchone()
        if row is None:
            return None, None
        raw = str(row["row_json"])
        return ReadOnlyEventMarketEvidence._json(raw), raw

    @staticmethod
    def raw_index_row(
        conn: sqlite3.Connection,
        *,
        market: str,
        bas_dd: str,
    ) -> tuple[dict[str, Any] | None, str | None]:
        row = conn.execute(
            """
            SELECT row_json FROM main_index_daily
            WHERE market=? AND bas_dd=?
            """,
            (market, bas_dd),
        ).fetchone()
        if row is None:
            return None, None
        raw = str(row["row_json"])
        return ReadOnlyEventMarketEvidence._json(raw), raw


class HistoricalEventEvaluator:
    def __init__(
        self,
        simulation_db: Path,
        market_store_db: Path,
        *,
        clock: Callable[[], str] | None = None,
    ) -> None:
        self.simulation_db = Path(simulation_db)
        self.market_store_db = Path(market_store_db)
        self.clock = clock or _now
        self.quality = EventEvidenceQualityService(
            self.simulation_db,
            clock=self.clock,
        )
        self.market = ReadOnlyEventMarketEvidence(self.market_store_db)

    def _connect(self) -> sqlite3.Connection:
        if not self.simulation_db.is_file():
            raise EventEvidenceContractError(
                "EVENT_EVIDENCE_STORE_NOT_FOUND",
                f"Simulation DB를 찾을 수 없습니다: {self.simulation_db}",
            )
        conn = sqlite3.connect(self.simulation_db, timeout=20.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    @staticmethod
    def _tables(conn: sqlite3.Connection) -> set[str]:
        return {
            str(row["name"])
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }

    def _require_ready(self, conn: sqlite3.Connection) -> None:
        required = {
            "event_evidence_evaluation_protocol",
            "event_evidence_outcome_observation",
            "event_evidence_control_match",
            "event_evidence_evaluation_report",
            "event_evidence_quality_assessment",
            "event_evidence_entity",
        }
        missing = sorted(required - self._tables(conn))
        if missing:
            raise EventEvidenceContractError(
                "EVENT_EVALUATION_MIGRATION_REQUIRED",
                "P6 Historical Event Evaluation schema가 준비되지 않았습니다: "
                + ", ".join(missing),
            )

    def register_protocol(
        self,
        protocol: EventEvaluationProtocol,
    ) -> dict[str, Any]:
        payload = protocol.to_dict()
        protocol_json = _canonical_json(payload)
        protocol_hash = _digest(payload)
        with self._connect() as conn:
            self._require_ready(conn)
            conn.execute("BEGIN IMMEDIATE")
            existing = conn.execute(
                """
                SELECT protocol_json,protocol_hash
                FROM event_evidence_evaluation_protocol
                WHERE protocol_id=?
                """,
                (protocol.protocol_id,),
            ).fetchone()
            if existing is not None:
                if (
                    str(existing["protocol_json"]) == protocol_json
                    and str(existing["protocol_hash"]) == protocol_hash
                ):
                    conn.commit()
                    return self.get_protocol(protocol.protocol_id)
                raise EventEvidenceContractError(
                    "EVENT_EVALUATION_PROTOCOL_CONFLICT",
                    "같은 protocol_id가 다른 내용으로 이미 저장되어 있습니다.",
                )
            conn.execute(
                """
                INSERT INTO event_evidence_evaluation_protocol(
                    protocol_id,protocol_contract_version,
                    control_method,control_approved,
                    observation_windows_json,reference_price_rule,
                    benchmark_rule,statistical_test_status,
                    minimum_control_count,protocol_json,protocol_hash,created_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    protocol.protocol_id,
                    protocol.contract_version,
                    protocol.control_method.value,
                    int(protocol.control_approved),
                    _canonical_json(list(protocol.observation_windows)),
                    protocol.reference_price_rule,
                    protocol.benchmark_rule,
                    protocol.statistical_test_status,
                    protocol.minimum_control_count,
                    protocol_json,
                    protocol_hash,
                    self.clock(),
                ),
            )
            conn.commit()
        return self.get_protocol(protocol.protocol_id)

    def get_protocol(self, protocol_id: str) -> dict[str, Any]:
        with self._connect() as conn:
            self._require_ready(conn)
            row = conn.execute(
                """
                SELECT * FROM event_evidence_evaluation_protocol
                WHERE protocol_id=?
                """,
                (protocol_id,),
            ).fetchone()
            if row is None:
                raise EventEvidenceContractError(
                    "EVENT_EVALUATION_PROTOCOL_NOT_FOUND",
                    "Event Evaluation Protocol을 찾을 수 없습니다.",
                )
            return {
                "protocol_id": str(row["protocol_id"]),
                "control_method": str(row["control_method"]),
                "control_approved": bool(row["control_approved"]),
                "observation_windows": json.loads(
                    str(row["observation_windows_json"])
                ),
                "reference_price_rule": str(row["reference_price_rule"]),
                "benchmark_rule": str(row["benchmark_rule"]),
                "statistical_test_status": str(row["statistical_test_status"]),
                "minimum_control_count": row["minimum_control_count"],
                "protocol_hash": str(row["protocol_hash"]),
                "protocol": json.loads(str(row["protocol_json"])),
                "created_at": str(row["created_at"]),
            }

    @staticmethod
    def _entity_market_ticker(
        conn: sqlite3.Connection,
        entity_id: str,
    ) -> tuple[str, str, str]:
        row = conn.execute(
            """
            SELECT entity_type,market,ticker,identity_hash
            FROM event_evidence_entity
            WHERE entity_id=?
            """,
            (entity_id,),
        ).fetchone()
        if row is None:
            raise EventEvidenceContractError(
                "EVENT_ENTITY_NOT_FOUND",
                "Historical Event Evaluation의 Entity를 찾을 수 없습니다.",
            )
        if str(row["entity_type"]) != "LISTED_COMPANY":
            raise EventEvidenceContractError(
                "EVENT_EVALUATION_ENTITY_UNSUPPORTED",
                "V1 Historical Event Evaluation은 LISTED_COMPANY만 지원합니다.",
            )
        market = str(row["market"] or "").strip().upper()
        ticker = str(row["ticker"] or "").strip()
        if not market or not ticker:
            raise EventEvidenceContractError(
                "EVENT_EVALUATION_ENTITY_MARKET_TICKER_MISSING",
                "상장사 Entity에 market/ticker가 없습니다.",
            )
        return market, ticker, str(row["identity_hash"])

    @staticmethod
    def _quality_row(
        conn: sqlite3.Connection,
        assessment_id: str,
    ) -> sqlite3.Row:
        row = conn.execute(
            """
            SELECT * FROM event_evidence_quality_assessment
            WHERE assessment_id=?
            """,
            (assessment_id,),
        ).fetchone()
        if row is None:
            raise EventEvidenceContractError(
                "EVENT_QUALITY_NOT_FOUND",
                "Historical Event Evaluation의 Quality Assessment를 찾을 수 없습니다.",
            )
        return row

    def _require_eligible_quality(
        self,
        assessment_id: str,
    ) -> tuple[dict[str, Any], sqlite3.Row]:
        verified = self.quality.verify_assessment(assessment_id)
        assessment = self.quality.get_assessment(assessment_id)
        if verified["status"] != "MATCH":
            raise EventEvidenceContractError(
                "EVENT_EVALUATION_QUALITY_INTEGRITY_BLOCKED",
                "Quality Assessment 무결성이 확인되지 않았습니다.",
            )
        if assessment["assessment_scope"] != "HISTORICAL_EVALUATION":
            raise EventEvidenceContractError(
                "EVENT_EVALUATION_SCOPE_BLOCKED",
                "HISTORICAL_EVALUATION Quality Assessment만 평가할 수 있습니다.",
            )
        if assessment["quality_state"] != "USABLE":
            raise EventEvidenceContractError(
                "EVENT_EVALUATION_QUALITY_BLOCKED",
                "USABLE Quality Assessment만 Historical Event Evaluation에 사용할 수 있습니다.",
            )
        with self._connect() as conn:
            self._require_ready(conn)
            row = self._quality_row(conn, assessment_id)
        return assessment, row

    def _market_snapshot(
        self,
        *,
        market: str,
        ticker: str,
        as_of_date: str,
        windows: tuple[int, ...],
    ) -> dict[str, Any]:
        max_horizon = max(windows)
        with self.market.connect() as conn:
            reference_day = self.market.reference_day(
                conn,
                market=market,
                ticker=ticker,
                before_date=as_of_date,
            )
            reaction_days = self.market.reaction_days(
                conn,
                market=market,
                after_date=as_of_date,
                limit=max_horizon,
            )
            if reference_day is None:
                return {
                    "status": "DATA_UNAVAILABLE",
                    "reason": "REFERENCE_DAY_NOT_AVAILABLE",
                    "market": market,
                    "ticker": ticker,
                    "as_of_date": _iso_date(as_of_date),
                    "reference_day": None,
                    "reference_price": None,
                    "benchmark_reference_price": None,
                    "horizons": {
                        str(horizon): {
                            "status": HorizonStatus.MISSING_MARKET_DATA.value,
                            "trading_day": None,
                            "stock_return_pct": None,
                            "market_return_pct": None,
                            "market_adjusted_return_pct": None,
                        }
                        for horizon in windows
                    },
                    "price_basis": "MARKET_STORE_CLOSE_AS_STORED",
                    "adjustment_basis": "PROVIDER_AS_STORED",
                    "market_evidence_rows": [],
                }

            ref_stock, ref_stock_raw = self.market.raw_stock_row(
                conn,
                market=market,
                ticker=ticker,
                bas_dd=reference_day,
            )
            ref_index, ref_index_raw = self.market.raw_index_row(
                conn,
                market=market,
                bas_dd=reference_day,
            )
            ref_stock_close = _decimal((ref_stock or {}).get("close"))
            ref_index_close = _decimal((ref_index or {}).get("close"))
            rows: list[dict[str, Any]] = [
                {
                    "kind": "REFERENCE_STOCK",
                    "bas_dd": reference_day,
                    "row_hash": (
                        hashlib.sha256(ref_stock_raw.encode("utf-8")).hexdigest()
                        if ref_stock_raw is not None else None
                    ),
                },
                {
                    "kind": "REFERENCE_INDEX",
                    "bas_dd": reference_day,
                    "row_hash": (
                        hashlib.sha256(ref_index_raw.encode("utf-8")).hexdigest()
                        if ref_index_raw is not None else None
                    ),
                },
            ]
            horizons: dict[str, dict[str, Any]] = {}
            mature = 0
            missing = 0
            for horizon in windows:
                if len(reaction_days) < horizon:
                    horizons[str(horizon)] = {
                        "status": HorizonStatus.NOT_MATURED.value,
                        "trading_day": None,
                        "close": None,
                        "benchmark_close": None,
                        "stock_return_pct": None,
                        "market_return_pct": None,
                        "market_adjusted_return_pct": None,
                    }
                    continue
                target_day = reaction_days[horizon - 1]
                stock, stock_raw = self.market.raw_stock_row(
                    conn,
                    market=market,
                    ticker=ticker,
                    bas_dd=target_day,
                )
                index, index_raw = self.market.raw_index_row(
                    conn,
                    market=market,
                    bas_dd=target_day,
                )
                rows.extend(
                    [
                        {
                            "kind": f"H{horizon}_STOCK",
                            "bas_dd": target_day,
                            "row_hash": (
                                hashlib.sha256(stock_raw.encode("utf-8")).hexdigest()
                                if stock_raw is not None else None
                            ),
                        },
                        {
                            "kind": f"H{horizon}_INDEX",
                            "bas_dd": target_day,
                            "row_hash": (
                                hashlib.sha256(index_raw.encode("utf-8")).hexdigest()
                                if index_raw is not None else None
                            ),
                        },
                    ]
                )
                stock_close = _decimal((stock or {}).get("close"))
                index_close = _decimal((index or {}).get("close"))
                if (
                    ref_stock_close is None
                    or ref_index_close is None
                    or stock_close is None
                    or index_close is None
                ):
                    missing += 1
                    horizons[str(horizon)] = {
                        "status": HorizonStatus.MISSING_MARKET_DATA.value,
                        "trading_day": _iso_date(target_day),
                        "close": float(stock_close) if stock_close is not None else None,
                        "benchmark_close": (
                            float(index_close) if index_close is not None else None
                        ),
                        "stock_return_pct": None,
                        "market_return_pct": None,
                        "market_adjusted_return_pct": None,
                    }
                    continue
                stock_return = _pct(stock_close, ref_stock_close)
                market_return = _pct(index_close, ref_index_close)
                mature += 1
                horizons[str(horizon)] = {
                    "status": HorizonStatus.MATURE.value,
                    "trading_day": _iso_date(target_day),
                    "close": float(stock_close),
                    "benchmark_close": float(index_close),
                    "stock_return_pct": stock_return,
                    "market_return_pct": market_return,
                    "market_adjusted_return_pct": (
                        round(stock_return - market_return, 4)
                        if stock_return is not None and market_return is not None
                        else None
                    ),
                }

        if ref_stock_close is None or ref_index_close is None:
            status = "DATA_UNAVAILABLE"
            reason = "REFERENCE_CLOSE_NOT_AVAILABLE"
        elif mature == len(windows):
            status = "COMPLETE"
            reason = None
        elif mature > 0:
            status = "PARTIAL"
            reason = "HORIZON_NOT_MATURED_OR_MISSING"
        elif missing > 0:
            status = "DATA_UNAVAILABLE"
            reason = "HORIZON_MARKET_DATA_MISSING"
        else:
            status = "NOT_MATURED"
            reason = "OBSERVATION_WINDOW_NOT_MATURED"

        return {
            "status": status,
            "reason": reason,
            "market": market,
            "ticker": ticker,
            "as_of_date": _iso_date(as_of_date),
            "reference_day": _iso_date(reference_day),
            "reference_price": (
                float(ref_stock_close) if ref_stock_close is not None else None
            ),
            "benchmark_reference_price": (
                float(ref_index_close) if ref_index_close is not None else None
            ),
            "horizons": horizons,
            "price_basis": "MARKET_STORE_CLOSE_AS_STORED",
            "adjustment_basis": "PROVIDER_AS_STORED",
            "market_evidence_rows": rows,
        }

    @staticmethod
    def _market_evidence_identity(snapshot: dict[str, Any]) -> str:
        payload = {
            "market": snapshot["market"],
            "ticker": snapshot["ticker"],
            "as_of_date": snapshot["as_of_date"],
            "reference_day": snapshot["reference_day"],
            "price_basis": snapshot["price_basis"],
            "adjustment_basis": snapshot["adjustment_basis"],
            "rows": snapshot["market_evidence_rows"],
        }
        return _digest(payload)

    def evaluate_outcome(
        self,
        *,
        quality_assessment_id: str,
        protocol_id: str,
    ) -> dict[str, Any]:
        assessment, quality_row = self._require_eligible_quality(
            quality_assessment_id
        )
        protocol = self.get_protocol(protocol_id)
        windows = tuple(int(value) for value in protocol["observation_windows"])
        as_of = _parse_aware(
            str(assessment["assessment_as_of"]),
            "assessment_as_of",
        )
        as_of_date = as_of.date().isoformat()

        with self._connect() as conn:
            self._require_ready(conn)
            market, ticker, entity_hash = self._entity_market_ticker(
                conn,
                assessment["entity_id"],
            )

        snapshot = self._market_snapshot(
            market=market,
            ticker=ticker,
            as_of_date=as_of_date,
            windows=windows,
        )
        market_evidence_hash = self._market_evidence_identity(snapshot)
        quality_payload = assessment["quality"]
        canonical_event_id = quality_payload.get("canonical_event_id")
        sample_identity = str(
            canonical_event_id or assessment["event_id"]
        )

        observation_id = str(
            uuid5(
                NAMESPACE_URL,
                (
                    "stockscope:event-outcome:"
                    f"{EVENT_OUTCOME_CONTRACT_VERSION}:"
                    f"{protocol['protocol_hash']}:"
                    f"{assessment['assessment_id']}:"
                    f"{assessment['quality_hash']}:"
                    f"{market_evidence_hash}"
                ),
            )
        )
        observation_payload = {
            "evaluation_contract_version": EVENT_EVALUATION_CONTRACT_VERSION,
            "outcome_contract_version": EVENT_OUTCOME_CONTRACT_VERSION,
            "observation_id": observation_id,
            "protocol_id": protocol_id,
            "protocol_hash": protocol["protocol_hash"],
            "quality_assessment_id": assessment["assessment_id"],
            "quality_hash": assessment["quality_hash"],
            "event_id": assessment["event_id"],
            "event_version": assessment["event_version"],
            "entity_id": assessment["entity_id"],
            "entity_hash": entity_hash,
            "canonical_event_id": canonical_event_id,
            "sample_identity": sample_identity,
            "assessment_as_of": assessment["assessment_as_of"],
            "market": market,
            "ticker": ticker,
            "reference_price_rule": protocol["reference_price_rule"],
            "benchmark_rule": protocol["benchmark_rule"],
            "sector_benchmark_status": "UNAVAILABLE",
            "market_evidence_hash": market_evidence_hash,
            "market_evidence_rows": snapshot["market_evidence_rows"],
            "evaluation_status": snapshot["status"],
            "evaluation_reason": snapshot["reason"],
            "reference_trading_day": snapshot["reference_day"],
            "reference_close": snapshot["reference_price"],
            "benchmark_reference_close": snapshot["benchmark_reference_price"],
            "price_basis": snapshot["price_basis"],
            "adjustment_basis": snapshot["adjustment_basis"],
            "horizons": snapshot["horizons"],
            "guardrail": (
                "관찰된 시장 대비 수익률은 사건의 인과 효과나 미래 상승 확률을 뜻하지 않습니다."
            ),
        }
        observation_json = _canonical_json(observation_payload)
        observation_hash = _digest(observation_payload)

        with self._connect() as conn:
            self._require_ready(conn)
            conn.execute("BEGIN IMMEDIATE")
            existing = conn.execute(
                """
                SELECT observation_json,observation_hash
                FROM event_evidence_outcome_observation
                WHERE observation_id=?
                """,
                (observation_id,),
            ).fetchone()
            if existing is not None:
                if (
                    str(existing["observation_json"]) == observation_json
                    and str(existing["observation_hash"]) == observation_hash
                ):
                    conn.commit()
                    return self.get_observation(observation_id)
                raise EventEvidenceContractError(
                    "EVENT_OUTCOME_IDENTITY_CONFLICT",
                    "같은 Event Outcome identity가 다른 결과로 이미 저장되어 있습니다.",
                )
            conn.execute(
                """
                INSERT INTO event_evidence_outcome_observation(
                    observation_id,evaluation_contract_version,
                    outcome_contract_version,protocol_id,protocol_hash,
                    quality_assessment_id,quality_hash,
                    event_id,event_version,entity_id,entity_hash,
                    canonical_event_id,sample_identity,assessment_as_of,
                    market,ticker,reference_price_rule,benchmark_rule,
                    sector_benchmark_status,market_evidence_hash,
                    evaluation_status,evaluation_reason,
                    reference_trading_day,reference_close,
                    benchmark_reference_close,price_basis,adjustment_basis,
                    horizons_json,observation_json,observation_hash,created_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    observation_id,
                    EVENT_EVALUATION_CONTRACT_VERSION,
                    EVENT_OUTCOME_CONTRACT_VERSION,
                    protocol_id,
                    protocol["protocol_hash"],
                    assessment["assessment_id"],
                    assessment["quality_hash"],
                    assessment["event_id"],
                    assessment["event_version"],
                    assessment["entity_id"],
                    entity_hash,
                    canonical_event_id,
                    sample_identity,
                    assessment["assessment_as_of"],
                    market,
                    ticker,
                    protocol["reference_price_rule"],
                    protocol["benchmark_rule"],
                    "UNAVAILABLE",
                    market_evidence_hash,
                    snapshot["status"],
                    snapshot["reason"],
                    snapshot["reference_day"],
                    snapshot["reference_price"],
                    snapshot["benchmark_reference_price"],
                    snapshot["price_basis"],
                    snapshot["adjustment_basis"],
                    _canonical_json(snapshot["horizons"]),
                    observation_json,
                    observation_hash,
                    self.clock(),
                ),
            )
            conn.commit()
        return self.get_observation(observation_id)

    def get_observation(self, observation_id: str) -> dict[str, Any]:
        with self._connect() as conn:
            self._require_ready(conn)
            row = conn.execute(
                """
                SELECT * FROM event_evidence_outcome_observation
                WHERE observation_id=?
                """,
                (observation_id,),
            ).fetchone()
            if row is None:
                raise EventEvidenceContractError(
                    "EVENT_OUTCOME_NOT_FOUND",
                    "Event Outcome Observation을 찾을 수 없습니다.",
                )
            return {
                "observation_id": str(row["observation_id"]),
                "protocol_id": str(row["protocol_id"]),
                "protocol_hash": str(row["protocol_hash"]),
                "quality_assessment_id": str(row["quality_assessment_id"]),
                "quality_hash": str(row["quality_hash"]),
                "event_id": str(row["event_id"]),
                "event_version": int(row["event_version"]),
                "entity_id": str(row["entity_id"]),
                "canonical_event_id": row["canonical_event_id"],
                "sample_identity": str(row["sample_identity"]),
                "assessment_as_of": str(row["assessment_as_of"]),
                "market": str(row["market"]),
                "ticker": str(row["ticker"]),
                "evaluation_status": str(row["evaluation_status"]),
                "evaluation_reason": row["evaluation_reason"],
                "reference_trading_day": row["reference_trading_day"],
                "reference_close": row["reference_close"],
                "benchmark_reference_close": row["benchmark_reference_close"],
                "market_evidence_hash": str(row["market_evidence_hash"]),
                "horizons": json.loads(str(row["horizons_json"])),
                "observation_hash": str(row["observation_hash"]),
                "observation": json.loads(str(row["observation_json"])),
                "created_at": str(row["created_at"]),
            }

    def verify_observation(self, observation_id: str) -> dict[str, Any]:
        observation = self.get_observation(observation_id)
        payload = observation["observation"]
        if _digest(payload) != observation["observation_hash"]:
            raise EventEvidenceContractError(
                "EVENT_OUTCOME_INTEGRITY_MISMATCH",
                "Event Outcome Observation hash가 저장 내용과 일치하지 않습니다.",
            )
        protocol = self.get_protocol(observation["protocol_id"])
        if protocol["protocol_hash"] != observation["protocol_hash"]:
            raise EventEvidenceContractError(
                "EVENT_OUTCOME_PROTOCOL_HASH_MISMATCH",
                "Outcome이 pin한 Evaluation Protocol hash가 다릅니다.",
            )
        verified = self.quality.verify_assessment(
            observation["quality_assessment_id"]
        )
        if verified["quality_hash"] != observation["quality_hash"]:
            raise EventEvidenceContractError(
                "EVENT_OUTCOME_QUALITY_HASH_MISMATCH",
                "Outcome이 pin한 Quality Assessment hash가 다릅니다.",
            )

        pinned_rows = list(payload.get("market_evidence_rows") or [])
        identity_payload = {
            "market": observation["market"],
            "ticker": observation["ticker"],
            "as_of_date": str(observation["assessment_as_of"])[:10],
            "reference_day": observation["reference_trading_day"],
            "price_basis": payload.get("price_basis"),
            "adjustment_basis": payload.get("adjustment_basis"),
            "rows": pinned_rows,
        }
        if _digest(identity_payload) != observation["market_evidence_hash"]:
            raise EventEvidenceContractError(
                "EVENT_OUTCOME_MARKET_EVIDENCE_IDENTITY_MISMATCH",
                "Outcome의 Market Store evidence identity가 observation payload와 다릅니다.",
            )
        with self.market.connect() as market_conn:
            for item in pinned_rows:
                bas_dd = _compact_date(str(item.get("bas_dd") or ""))
                kind = str(item.get("kind") or "")
                if kind.endswith("_STOCK"):
                    _, raw = self.market.raw_stock_row(
                        market_conn,
                        market=observation["market"],
                        ticker=observation["ticker"],
                        bas_dd=bas_dd,
                    )
                elif kind.endswith("_INDEX"):
                    _, raw = self.market.raw_index_row(
                        market_conn,
                        market=observation["market"],
                        bas_dd=bas_dd,
                    )
                else:
                    raise EventEvidenceContractError(
                        "EVENT_OUTCOME_MARKET_EVIDENCE_KIND_INVALID",
                        f"알 수 없는 pinned market evidence kind입니다: {kind}",
                    )
                current_hash = (
                    hashlib.sha256(raw.encode("utf-8")).hexdigest()
                    if raw is not None else None
                )
                if current_hash != item.get("row_hash"):
                    raise EventEvidenceContractError(
                        "EVENT_OUTCOME_MARKET_EVIDENCE_MISMATCH",
                        "Outcome이 pin한 Market Store row가 현재 row와 다릅니다.",
                    )
        return {
            "status": "MATCH",
            "observation_id": observation_id,
            "observation_hash": observation["observation_hash"],
        }

    def create_control_match(
        self,
        *,
        observation_id: str,
        control_as_of_date: str,
    ) -> dict[str, Any]:
        observation = self.get_observation(observation_id)
        self.verify_observation(observation_id)
        protocol = self.get_protocol(observation["protocol_id"])
        if (
            not protocol["control_approved"]
            or protocol["control_method"] != ControlMethod.EXPLICIT_MATCH_SET.value
        ):
            raise EventEvidenceContractError(
                "CONTROL_COMPARISON_NOT_APPROVED",
                "이 Evaluation Protocol은 no-event control 비교가 승인되지 않았습니다.",
            )
        control_date = _iso_date(control_as_of_date)
        snapshot = self._market_snapshot(
            market=observation["market"],
            ticker=observation["ticker"],
            as_of_date=control_date,
            windows=tuple(protocol["observation_windows"]),
        )
        mature_target_dates = [
            item["trading_day"]
            for item in snapshot["horizons"].values()
            if item.get("trading_day")
        ]
        end_date = max(mature_target_dates) if mature_target_dates else control_date

        contaminated_by: list[str] = []
        with self._connect() as conn:
            self._require_ready(conn)
            rows = conn.execute(
                """
                SELECT assessment_id,event_id,assessment_as_of
                FROM event_evidence_quality_assessment
                WHERE entity_id=?
                  AND assessment_scope='HISTORICAL_EVALUATION'
                  AND quality_state='USABLE'
                ORDER BY assessment_as_of,assessment_id
                """,
                (observation["entity_id"],),
            ).fetchall()
        for row in rows:
            event_date = str(row["assessment_as_of"])[:10]
            if control_date <= event_date <= end_date:
                contaminated_by.append(str(row["event_id"]))

        contamination_state = (
            "CONTAMINATED" if contaminated_by else "CLEAN"
        )
        control_market_hash = self._market_evidence_identity(snapshot)
        control_id = str(
            uuid5(
                NAMESPACE_URL,
                (
                    "stockscope:event-control:"
                    f"{EVENT_EVALUATION_CONTRACT_VERSION}:"
                    f"{observation_id}:{protocol['protocol_hash']}:"
                    f"{control_date}:{control_market_hash}"
                ),
            )
        )
        control_payload = {
            "evaluation_contract_version": EVENT_EVALUATION_CONTRACT_VERSION,
            "control_id": control_id,
            "observation_id": observation_id,
            "protocol_id": observation["protocol_id"],
            "protocol_hash": protocol["protocol_hash"],
            "control_as_of_date": control_date,
            "contamination_state": contamination_state,
            "contaminated_by_event_ids": sorted(set(contaminated_by)),
            "market_evidence_hash": control_market_hash,
            "evaluation_status": (
                "CONTROL_CONTAMINATED"
                if contaminated_by
                else snapshot["status"]
            ),
            "reference_trading_day": snapshot["reference_day"],
            "reference_close": snapshot["reference_price"],
            "benchmark_reference_close": snapshot["benchmark_reference_price"],
            "horizons": snapshot["horizons"],
            "guardrail": (
                "Control은 명시적으로 지정된 비교 날짜이며 자동으로 인과 대조군을 의미하지 않습니다."
            ),
        }
        control_json = _canonical_json(control_payload)
        control_hash = _digest(control_payload)

        with self._connect() as conn:
            self._require_ready(conn)
            conn.execute("BEGIN IMMEDIATE")
            existing = conn.execute(
                """
                SELECT control_json,control_hash
                FROM event_evidence_control_match
                WHERE control_id=?
                """,
                (control_id,),
            ).fetchone()
            if existing is not None:
                if (
                    str(existing["control_json"]) == control_json
                    and str(existing["control_hash"]) == control_hash
                ):
                    conn.commit()
                    return self.get_control_match(control_id)
                raise EventEvidenceContractError(
                    "EVENT_CONTROL_IDENTITY_CONFLICT",
                    "같은 Control Match identity가 다른 결과로 이미 저장되어 있습니다.",
                )
            conn.execute(
                """
                INSERT INTO event_evidence_control_match(
                    control_id,evaluation_contract_version,
                    observation_id,protocol_id,protocol_hash,
                    control_as_of_date,contamination_state,
                    contaminated_by_json,market_evidence_hash,
                    evaluation_status,reference_trading_day,
                    reference_close,benchmark_reference_close,
                    horizons_json,control_json,control_hash,created_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    control_id,
                    EVENT_EVALUATION_CONTRACT_VERSION,
                    observation_id,
                    observation["protocol_id"],
                    protocol["protocol_hash"],
                    control_date,
                    contamination_state,
                    _canonical_json(sorted(set(contaminated_by))),
                    control_market_hash,
                    control_payload["evaluation_status"],
                    snapshot["reference_day"],
                    snapshot["reference_price"],
                    snapshot["benchmark_reference_price"],
                    _canonical_json(snapshot["horizons"]),
                    control_json,
                    control_hash,
                    self.clock(),
                ),
            )
            conn.commit()
        return self.get_control_match(control_id)

    def get_control_match(self, control_id: str) -> dict[str, Any]:
        with self._connect() as conn:
            self._require_ready(conn)
            row = conn.execute(
                """
                SELECT * FROM event_evidence_control_match
                WHERE control_id=?
                """,
                (control_id,),
            ).fetchone()
            if row is None:
                raise EventEvidenceContractError(
                    "EVENT_CONTROL_NOT_FOUND",
                    "Event Control Match를 찾을 수 없습니다.",
                )
            return {
                "control_id": str(row["control_id"]),
                "observation_id": str(row["observation_id"]),
                "protocol_id": str(row["protocol_id"]),
                "control_as_of_date": str(row["control_as_of_date"]),
                "contamination_state": str(row["contamination_state"]),
                "contaminated_by_event_ids": json.loads(
                    str(row["contaminated_by_json"])
                ),
                "evaluation_status": str(row["evaluation_status"]),
                "market_evidence_hash": str(row["market_evidence_hash"]),
                "horizons": json.loads(str(row["horizons_json"])),
                "control_hash": str(row["control_hash"]),
                "control": json.loads(str(row["control_json"])),
                "created_at": str(row["created_at"]),
            }

    def create_report(
        self,
        *,
        protocol_id: str,
        observation_ids: list[str] | tuple[str, ...],
    ) -> dict[str, Any]:
        protocol = self.get_protocol(protocol_id)
        if not observation_ids:
            raise EventEvidenceContractError(
                "EVENT_EVALUATION_REPORT_EMPTY",
                "Evaluation Report에는 Observation이 하나 이상 필요합니다.",
            )
        observations = [self.get_observation(item) for item in observation_ids]
        for observation in observations:
            self.verify_observation(observation["observation_id"])
            if observation["protocol_id"] != protocol_id:
                raise EventEvidenceContractError(
                    "EVENT_EVALUATION_PROTOCOL_MISMATCH",
                    "Report Observation의 protocol이 서로 다릅니다.",
                )

        by_sample: dict[str, dict[str, Any]] = {}
        deduplicated: list[str] = []
        for observation in sorted(
            observations,
            key=lambda item: (
                str(item["assessment_as_of"]),
                str(item["observation_id"]),
            ),
        ):
            key = str(observation["sample_identity"])
            if key in by_sample:
                deduplicated.append(observation["observation_id"])
                continue
            by_sample[key] = observation
        selected = list(by_sample.values())

        control_rows: list[dict[str, Any]] = []
        if protocol["control_approved"]:
            with self._connect() as conn:
                self._require_ready(conn)
                placeholders = ",".join("?" for _ in selected)
                if selected:
                    rows = conn.execute(
                        f"""
                        SELECT control_id
                        FROM event_evidence_control_match
                        WHERE observation_id IN ({placeholders})
                        ORDER BY observation_id,control_as_of_date,control_id
                        """,
                        tuple(item["observation_id"] for item in selected),
                    ).fetchall()
                    control_rows = [
                        self.get_control_match(str(row["control_id"]))
                        for row in rows
                    ]

        horizon_metrics: dict[str, Any] = {}
        for horizon in protocol["observation_windows"]:
            key = str(horizon)
            stock_values: list[float] = []
            market_values: list[float] = []
            adjusted_values: list[float] = []
            for observation in selected:
                item = observation["horizons"].get(key) or {}
                if item.get("status") != HorizonStatus.MATURE.value:
                    continue
                if item.get("stock_return_pct") is not None:
                    stock_values.append(float(item["stock_return_pct"]))
                if item.get("market_return_pct") is not None:
                    market_values.append(float(item["market_return_pct"]))
                if item.get("market_adjusted_return_pct") is not None:
                    adjusted_values.append(
                        float(item["market_adjusted_return_pct"])
                    )

            clean_controls = [
                row for row in control_rows
                if row["contamination_state"] == "CLEAN"
                and (row["horizons"].get(key) or {}).get("status")
                == HorizonStatus.MATURE.value
            ]
            control_adjusted = [
                float(row["horizons"][key]["market_adjusted_return_pct"])
                for row in clean_controls
                if row["horizons"][key].get("market_adjusted_return_pct")
                is not None
            ]
            event_adjusted = _metric(adjusted_values)
            control_metric = _metric(control_adjusted)
            observed_difference = None
            if (
                event_adjusted["average_pct"] is not None
                and control_metric["average_pct"] is not None
            ):
                observed_difference = round(
                    float(event_adjusted["average_pct"])
                    - float(control_metric["average_pct"]),
                    4,
                )
            horizon_metrics[key] = {
                "stock_return": _metric(stock_values),
                "market_return": _metric(market_values),
                "market_adjusted_return": event_adjusted,
                "control_market_adjusted_return": control_metric,
                "observed_event_minus_control_pct_points": observed_difference,
            }

        complete_count = sum(
            1 for item in selected if item["evaluation_status"] == "COMPLETE"
        )
        mature_any = any(
            metrics["stock_return"]["sample_count"] > 0
            for metrics in horizon_metrics.values()
        )
        if complete_count == len(selected):
            report_status = "COMPLETE"
        elif mature_any:
            report_status = "PARTIAL"
        else:
            report_status = "DATA_UNAVAILABLE_OR_NOT_MATURED"

        pinned = [
            {
                "observation_id": item["observation_id"],
                "observation_hash": item["observation_hash"],
                "sample_identity": item["sample_identity"],
            }
            for item in selected
        ]
        control_pins = [
            {
                "control_id": item["control_id"],
                "control_hash": item["control_hash"],
                "observation_id": item["observation_id"],
            }
            for item in control_rows
        ]
        report_identity_payload = {
            "report_contract_version": EVENT_EVALUATION_REPORT_CONTRACT_VERSION,
            "protocol_id": protocol_id,
            "protocol_hash": protocol["protocol_hash"],
            "observations": pinned,
            "controls": control_pins,
        }
        report_id = str(
            uuid5(
                NAMESPACE_URL,
                "stockscope:event-evaluation-report:"
                + _digest(report_identity_payload),
            )
        )
        report_payload = {
            **report_identity_payload,
            "report_id": report_id,
            "report_status": report_status,
            "sample_count": len(selected),
            "sample_sufficiency": "UNDECIDED",
            "statistical_test_status": "NOT_CONFIGURED",
            "deduplicated_observation_ids": sorted(deduplicated),
            "horizons": horizon_metrics,
            "control_summary": {
                "approved": bool(protocol["control_approved"]),
                "method": protocol["control_method"],
                "clean_match_count": sum(
                    1
                    for item in control_rows
                    if item["contamination_state"] == "CLEAN"
                ),
                "contaminated_match_count": sum(
                    1
                    for item in control_rows
                    if item["contamination_state"] == "CONTAMINATED"
                ),
            },
            "guardrail": (
                "관찰 결과와 control 차이는 사건의 인과 효과, 미래 수익 또는 상승 확률을 증명하지 않습니다."
            ),
        }
        report_json = _canonical_json(report_payload)
        report_hash = _digest(report_payload)

        with self._connect() as conn:
            self._require_ready(conn)
            conn.execute("BEGIN IMMEDIATE")
            existing = conn.execute(
                """
                SELECT report_json,report_hash
                FROM event_evidence_evaluation_report
                WHERE report_id=?
                """,
                (report_id,),
            ).fetchone()
            if existing is not None:
                if (
                    str(existing["report_json"]) == report_json
                    and str(existing["report_hash"]) == report_hash
                ):
                    conn.commit()
                    return self.get_report(report_id)
                raise EventEvidenceContractError(
                    "EVENT_EVALUATION_REPORT_IDENTITY_CONFLICT",
                    "같은 Evaluation Report identity가 다른 결과로 이미 저장되어 있습니다.",
                )
            conn.execute(
                """
                INSERT INTO event_evidence_evaluation_report(
                    report_id,report_contract_version,
                    protocol_id,protocol_hash,report_status,
                    sample_count,sample_sufficiency,
                    statistical_test_status,observation_bundle_json,
                    report_json,report_hash,created_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    report_id,
                    EVENT_EVALUATION_REPORT_CONTRACT_VERSION,
                    protocol_id,
                    protocol["protocol_hash"],
                    report_status,
                    len(selected),
                    "UNDECIDED",
                    "NOT_CONFIGURED",
                    _canonical_json(pinned),
                    report_json,
                    report_hash,
                    self.clock(),
                ),
            )
            conn.commit()
        return self.get_report(report_id)

    def get_report(self, report_id: str) -> dict[str, Any]:
        with self._connect() as conn:
            self._require_ready(conn)
            row = conn.execute(
                """
                SELECT * FROM event_evidence_evaluation_report
                WHERE report_id=?
                """,
                (report_id,),
            ).fetchone()
            if row is None:
                raise EventEvidenceContractError(
                    "EVENT_EVALUATION_REPORT_NOT_FOUND",
                    "Historical Event Evaluation Report를 찾을 수 없습니다.",
                )
            return {
                "report_id": str(row["report_id"]),
                "protocol_id": str(row["protocol_id"]),
                "protocol_hash": str(row["protocol_hash"]),
                "report_status": str(row["report_status"]),
                "sample_count": int(row["sample_count"]),
                "sample_sufficiency": str(row["sample_sufficiency"]),
                "statistical_test_status": str(row["statistical_test_status"]),
                "observation_bundle": json.loads(
                    str(row["observation_bundle_json"])
                ),
                "report_hash": str(row["report_hash"]),
                "report": json.loads(str(row["report_json"])),
                "created_at": str(row["created_at"]),
            }
