from __future__ import annotations

import json
import sqlite3
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from app.macro.identity import content_hash


MARKET_STOCK_IMPACT_CONTRACT_VERSION = "VN_NEXT6C_S1_MARKET_STOCK_IMPACT_V1"
MARKET_STOCK_IMPACT_WINDOW_MODE = "COMMON_CONFIRMED_SESSION"

_ALLOWED_MARKETS = {"KOSPI", "KOSDAQ"}
_ALLOWED_SECTOR_TEMPORAL = {
    None,
    "POINT_IN_TIME",
    "STATIC_CURRENT",
    "UNKNOWN",
}


def _market(value: str) -> str:
    market = str(value or "").strip().upper()
    if market not in _ALLOWED_MARKETS:
        raise ValueError("market must be KOSPI or KOSDAQ.")
    return market


def _compact_date(value: Any) -> str:
    text = str(value or "").strip().replace("-", "")
    if len(text) != 8 or not text.isdigit():
        return ""
    return text


def _decimal(value: Any) -> Decimal | None:
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    if not parsed.is_finite() or parsed <= 0:
        return None
    return parsed


def _decimal_text(value: Decimal | None) -> str | None:
    if value is None:
        return None
    text = format(value.normalize(), "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return "0" if text in {"", "-0"} else text


def _close_by_date(
    rows: list[dict[str, Any]] | tuple[dict[str, Any], ...],
    *,
    end_date: str,
) -> tuple[dict[str, Decimal], int]:
    end_dd = _compact_date(end_date)
    if not end_dd:
        raise ValueError("end_date must be YYYY-MM-DD or YYYYMMDD.")

    result: dict[str, Decimal] = {}
    future_rows_ignored = 0
    for row in rows:
        row_date = _compact_date(row.get("date") or row.get("bas_dd"))
        if not row_date:
            continue
        if row_date > end_dd:
            future_rows_ignored += 1
            continue
        close = _decimal(row.get("close"))
        if close is not None:
            result[row_date] = close
    return result, future_rows_ignored


def _return_pct(start: Decimal, end: Decimal) -> Decimal:
    return (end / start - Decimal("1")) * Decimal("100")


def _sector_projection(temporal_status: str | None) -> dict[str, Any]:
    if temporal_status not in _ALLOWED_SECTOR_TEMPORAL:
        raise ValueError("Unsupported sector temporal status.")

    if temporal_status == "POINT_IN_TIME":
        reason = "SECTOR_PROJECTION_NOT_IMPLEMENTED_NEXT6C_S1"
    else:
        reason = "PIT_MAPPING_UNAVAILABLE"

    return {
        "status": "UNAVAILABLE",
        "temporal_status": temporal_status,
        "return_pct": None,
        "sector_vs_market_pctp": None,
        "stock_vs_sector_pctp": None,
        "reason": reason,
        "production_safe": False,
    }


def build_market_stock_impact(
    *,
    stock_rows: list[dict[str, Any]] | tuple[dict[str, Any], ...],
    market_rows: list[dict[str, Any]] | tuple[dict[str, Any], ...],
    market: str,
    ticker: str,
    end_date: str,
    macro_context_id: str,
    macro_context_hash: str,
    decision_cutoff: str,
    sector_temporal_status: str | None = None,
) -> dict[str, Any]:
    """Build a descriptive 1-common-session Market/Stock impact projection.

    This contract is intentionally causal-neutral and policy-neutral. It uses only
    confirmed EOD rows already supplied by the caller, ignores rows after end_date,
    and does not invoke Strategy, Risk, Scanner, Holdings, provider or network code.
    """

    market_key = _market(market)
    ticker_key = str(ticker or "").strip().upper()
    if not ticker_key:
        raise ValueError("ticker is required.")
    if not str(macro_context_id or "").strip():
        raise ValueError("macro_context_id is required.")
    if len(str(macro_context_hash or "").strip()) != 64:
        raise ValueError("macro_context_hash must be a 64-character hash.")
    if not str(decision_cutoff or "").strip():
        raise ValueError("decision_cutoff is required.")

    stock, _ = _close_by_date(stock_rows, end_date=end_date)
    benchmark, _ = _close_by_date(market_rows, end_date=end_date)
    common_dates = sorted(set(stock) & set(benchmark))

    base = {
        "contract_version": MARKET_STOCK_IMPACT_CONTRACT_VERSION,
        "context_ref": {
            "macro_context_id": str(macro_context_id),
            "macro_context_hash": str(macro_context_hash),
            "decision_cutoff": str(decision_cutoff),
        },
        "scope": {
            "market": market_key,
            "ticker": ticker_key,
            "price_basis": "CONFIRMED_EOD",
        },
        "window": {
            "mode": MARKET_STOCK_IMPACT_WINDOW_MODE,
            "session_count": 1,
            "requested_end_date": _compact_date(end_date),
            "start_date": None,
            "end_date": None,
            "common_session_count": len(common_dates),
        },
        "market": {
            "start_close": None,
            "end_close": None,
            "return_pct": None,
        },
        "stock": {
            "start_close": None,
            "end_close": None,
            "return_pct": None,
        },
        "relative": {
            "stock_vs_market_pctp": None,
        },
        "sector": _sector_projection(sector_temporal_status),
        "lineage": {
            "stock_rows_considered": len(stock),
            "market_rows_considered": len(benchmark),
            "common_dates_hash": content_hash(common_dates),
            "future_rows_policy": "IGNORE_AFTER_REQUESTED_END_DATE",
        },
        "limitations": [
            "DESCRIPTIVE_ONLY",
            "NO_CAUSAL_ATTRIBUTION",
            "NO_SHOCK_CLASSIFICATION",
            "SECTOR_PIT_MAPPING_UNAVAILABLE"
            if sector_temporal_status != "POINT_IN_TIME"
            else "SECTOR_PROJECTION_NOT_IMPLEMENTED_NEXT6C_S1",
        ],
        "governance": {
            "claim_scope": "DESCRIPTIVE_ONLY",
            "production_decision_approved": False,
            "strategy_input_approved": False,
            "scanner_input_approved": False,
            "risk_gate_input_approved": False,
            "holdings_plan_input_approved": False,
            "network_access": False,
        },
    }

    if len(common_dates) < 2:
        identity_payload = {
            **base,
            "status": "UNAVAILABLE",
            "reason": "INSUFFICIENT_COMMON_SESSIONS",
        }
        impact_hash = content_hash(identity_payload)
        return {
            **identity_payload,
            "impact_id": f"MSIMPACT-{impact_hash[:16]}",
            "impact_hash": impact_hash,
        }

    start_date, final_date = common_dates[-2], common_dates[-1]
    market_start = benchmark[start_date]
    market_end = benchmark[final_date]
    stock_start = stock[start_date]
    stock_end = stock[final_date]

    market_return = _return_pct(market_start, market_end)
    stock_return = _return_pct(stock_start, stock_end)
    relative = stock_return - market_return

    complete = {
        **base,
        "status": "AVAILABLE",
        "reason": None,
        "window": {
            **base["window"],
            "start_date": start_date,
            "end_date": final_date,
        },
        "market": {
            "start_close": _decimal_text(market_start),
            "end_close": _decimal_text(market_end),
            "return_pct": _decimal_text(market_return),
            "unit": "PERCENT",
        },
        "stock": {
            "start_close": _decimal_text(stock_start),
            "end_close": _decimal_text(stock_end),
            "return_pct": _decimal_text(stock_return),
            "unit": "PERCENT",
        },
        "relative": {
            "stock_vs_market_pctp": _decimal_text(relative),
            "unit": "PERCENTAGE_POINT",
        },
    }
    impact_hash = content_hash(complete)
    return {
        **complete,
        "impact_id": f"MSIMPACT-{impact_hash[:16]}",
        "impact_hash": impact_hash,
    }


class LocalMarketImpactReader:
    """Strict read-only reader for the existing HistoricalMarketStore database."""

    REQUIRED_TABLES = {"stock_daily", "main_index_daily", "day_status"}

    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)

    def _connect(self) -> sqlite3.Connection:
        uri = self.db_path.resolve().as_uri() + "?mode=ro"
        conn = sqlite3.connect(uri, uri=True, timeout=5.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA query_only=ON")
        return conn

    def _schema_state(self) -> tuple[bool, str | None]:
        if not self.db_path.is_file():
            return False, "STORE_NOT_FOUND"
        try:
            with self._connect() as conn:
                tables = {
                    str(row[0])
                    for row in conn.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    ).fetchall()
                }
                if not self.REQUIRED_TABLES.issubset(tables):
                    return False, "SCHEMA_UNAVAILABLE"
        except sqlite3.Error:
            return False, "READ_FAILED"
        return True, None

    @staticmethod
    def _load_row(raw: str, bas_dd: str) -> dict[str, Any]:
        try:
            value = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        if not isinstance(value, dict):
            return {}
        result = dict(value)
        result.setdefault("date", bas_dd)
        result["bas_dd"] = bas_dd
        return result

    def read_pair_as_of(
        self,
        *,
        market: str,
        ticker: str,
        end_date: str,
    ) -> dict[str, Any]:
        market_key = _market(market)
        ticker_key = str(ticker or "").strip().upper()
        end_dd = _compact_date(end_date)
        if not ticker_key:
            raise ValueError("ticker is required.")
        if not end_dd:
            raise ValueError("end_date must be YYYY-MM-DD or YYYYMMDD.")

        ready, reason = self._schema_state()
        if not ready:
            payload = {
                "status": "UNAVAILABLE",
                "reason": reason,
                "market": market_key,
                "ticker": ticker_key,
                "end_date": end_dd,
                "stock_rows": [],
                "market_rows": [],
            }
            return {**payload, "reader_hash": content_hash(payload)}

        try:
            with self._connect() as conn:
                stock_rows = conn.execute(
                    """
                    SELECT s.bas_dd,s.row_json
                    FROM stock_daily AS s
                    JOIN day_status AS d
                      ON d.market=s.market
                     AND d.bas_dd=s.bas_dd
                     AND d.kind='stock'
                     AND d.status='data'
                    WHERE s.market=? AND s.stock_code=? AND s.bas_dd<=?
                    ORDER BY s.bas_dd
                    """,
                    (market_key, ticker_key, end_dd),
                ).fetchall()
                market_rows = conn.execute(
                    """
                    SELECT i.bas_dd,i.row_json
                    FROM main_index_daily AS i
                    JOIN day_status AS d
                      ON d.market=i.market
                     AND d.bas_dd=i.bas_dd
                     AND d.kind='index'
                     AND d.status='data'
                    WHERE i.market=? AND i.bas_dd<=?
                    ORDER BY i.bas_dd
                    """,
                    (market_key, end_dd),
                ).fetchall()
        except sqlite3.Error:
            payload = {
                "status": "UNAVAILABLE",
                "reason": "READ_FAILED",
                "market": market_key,
                "ticker": ticker_key,
                "end_date": end_dd,
                "stock_rows": [],
                "market_rows": [],
            }
            return {**payload, "reader_hash": content_hash(payload)}

        stock = [
            self._load_row(str(row["row_json"]), str(row["bas_dd"]))
            for row in stock_rows
        ]
        benchmark = [
            self._load_row(str(row["row_json"]), str(row["bas_dd"]))
            for row in market_rows
        ]
        status = "COMPLETE" if stock and benchmark else "UNAVAILABLE"
        reason = None if status == "COMPLETE" else "DATA_ABSENT"
        payload = {
            "status": status,
            "reason": reason,
            "market": market_key,
            "ticker": ticker_key,
            "end_date": end_dd,
            "stock_rows": stock,
            "market_rows": benchmark,
        }
        return {**payload, "reader_hash": content_hash(payload)}
