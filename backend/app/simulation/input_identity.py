from __future__ import annotations

import json
from datetime import date, timedelta
from typing import Any

from app.backtest.market_store import HistoricalMarketStore
from app.backtest.scanner import StockScannerService
from app.input_identity import VALIDATION_INPUT_MANIFEST_VERSION

from .validation_catalog import HistoricalValidationCatalog, HistoricalValidationDraft


def _markets(scope: str) -> tuple[str, ...]:
    normalized = (scope or "").strip().upper()
    if normalized == "ALL":
        return ("KOSPI", "KOSDAQ")
    if normalized in {"KOSPI", "KOSDAQ"}:
        return (normalized,)
    raise ValueError(f"지원하지 않는 market scope입니다: {scope}")


def _expected_weekdays(start_day: date, end_day: date) -> list[str]:
    values: list[str] = []
    cursor = start_day
    while cursor <= end_day:
        if cursor.weekday() < 5:
            values.append(cursor.strftime("%Y%m%d"))
        cursor += timedelta(days=1)
    return values


def build_replay_market_manifest(
    market_store: HistoricalMarketStore,
    draft: HistoricalValidationDraft,
    replay_day: date,
) -> dict[str, Any]:
    """Fingerprint only the historical range that could affect one replay day."""
    history_start = replay_day - timedelta(
        days=StockScannerService.FAST_HISTORY_CALENDAR_DAYS
    )
    expected = _expected_weekdays(history_start, replay_day)
    markets: dict[str, Any] = {}
    for market in _markets(draft.market_scope):
        markets[market] = market_store.reproducibility_snapshot(
            market,
            history_start.strftime("%Y%m%d"),
            replay_day.strftime("%Y%m%d"),
            expected_dates=expected,
        )
    return {
        "schema_version": VALIDATION_INPUT_MANIFEST_VERSION,
        "market_scope": draft.market_scope,
        "replay_date": replay_day.isoformat(),
        "markets": markets,
    }


def _expected_dates_from_snapshot(snapshot: dict[str, Any]) -> list[str]:
    status = snapshot.get("status")
    if not isinstance(status, dict):
        return []
    values: set[str] = set()
    for kind in ("stock", "index"):
        item = status.get(kind)
        if not isinstance(item, dict):
            continue
        for key in ("data_dates", "empty_dates", "missing_dates"):
            rows = item.get(key)
            if isinstance(rows, list):
                values.update(str(value) for value in rows if str(value))
    return sorted(values)


def current_manifest_from_stored(
    market_store: HistoricalMarketStore,
    stored_manifest: dict[str, Any],
) -> dict[str, Any] | None:
    if stored_manifest.get("schema_version") != VALIDATION_INPUT_MANIFEST_VERSION:
        return None
    raw_markets = stored_manifest.get("markets")
    if not isinstance(raw_markets, dict):
        return None

    markets: dict[str, Any] = {}
    for market, raw_snapshot in raw_markets.items():
        if not isinstance(raw_snapshot, dict):
            return None
        start_date = str(raw_snapshot.get("start_date") or "")
        end_date = str(raw_snapshot.get("end_date") or "")
        if not start_date or not end_date:
            return None
        markets[str(market)] = market_store.reproducibility_snapshot(
            str(market),
            start_date,
            end_date,
            expected_dates=_expected_dates_from_snapshot(raw_snapshot),
        )
    return {
        "schema_version": VALIDATION_INPUT_MANIFEST_VERSION,
        "market_scope": stored_manifest.get("market_scope"),
        "replay_date": stored_manifest.get("replay_date"),
        "markets": markets,
    }


def _canonical(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def verify_validation_input_identity(
    catalog: HistoricalValidationCatalog,
    market_store: HistoricalMarketStore,
    validation_id: str,
) -> dict[str, Any]:
    draft = catalog.get(validation_id)
    if draft is None:
        raise KeyError(validation_id)

    days = [
        day
        for day in catalog.list_days(validation_id)
        if day.status == "COMPLETED"
    ]
    counts = {
        "completed": len(days),
        "valid": 0,
        "changed": 0,
        "source_mismatch": 0,
        "unverified": 0,
    }
    details: list[dict[str, Any]] = []

    for day in days:
        proof = catalog.get_input_identity_proof(
            validation_id,
            day.trading_date,
        )
        if proof is None:
            counts["unverified"] += 1
            details.append(
                {
                    "trading_date": day.trading_date,
                    "status": "UNVERIFIED",
                    "reason": "INPUT_MANIFEST_NOT_CAPTURED",
                }
            )
            continue

        if (
            _canonical(proof["source_input_fingerprint"])
            != _canonical(day.input_fingerprint)
            or str(proof["day_result_hash"] or "") != str(day.result_hash or "")
        ):
            counts["source_mismatch"] += 1
            details.append(
                {
                    "trading_date": day.trading_date,
                    "status": "INVALID",
                    "reason": "STORED_VALIDATION_SOURCE_CHANGED",
                }
            )
            continue

        current = current_manifest_from_stored(
            market_store,
            proof["market_manifest"],
        )
        if current is None:
            counts["unverified"] += 1
            details.append(
                {
                    "trading_date": day.trading_date,
                    "status": "UNVERIFIED",
                    "reason": "INPUT_MANIFEST_UNSUPPORTED",
                }
            )
            continue

        if _canonical(current) == _canonical(proof["market_manifest"]):
            counts["valid"] += 1
            details.append(
                {
                    "trading_date": day.trading_date,
                    "status": "VALID",
                    "reason": None,
                }
            )
        else:
            counts["changed"] += 1
            details.append(
                {
                    "trading_date": day.trading_date,
                    "status": "INVALID",
                    "reason": "CURRENT_MARKET_INPUT_CHANGED",
                }
            )

    if counts["source_mismatch"] or counts["changed"]:
        status = "INVALID"
    elif counts["completed"] and counts["valid"] == counts["completed"]:
        status = "VALID"
    else:
        status = "UNVERIFIED"

    return {
        "validation_id": validation_id,
        "status": status,
        "counts": counts,
        "details": details,
    }
