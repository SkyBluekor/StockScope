"""GLOBAL-02-S1: personal-local, bounded FRED FX/Brent vs KRX retrospective.

Only aggregated descriptive JSON reaches stdout. No source rows on disk, no
Strategy, Risk, JEV, Holdings, Scanner or database writes. Explicit opt-in.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from contextlib import closing
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
for folder in (ROOT, ROOT / "backend"):
    if str(folder) not in sys.path:
        sys.path.insert(0, str(folder))

from app.integrations.fred.client import FredApiError, FredClient, FredConfigurationError
from app.macro.global02_fx_oil import (
    GLOBAL02_CONTRACT_VERSION, SPECS, Global02SeriesError,
    _value, normalize_observations, retrospective_relation, validate_series_metadata,
)
from tools.data.common import market_db_path

MARKETS = ("KOSPI", "KOSDAQ")


def open_krx_readonly(path: Path) -> sqlite3.Connection:
    if not path.is_file():
        raise FileNotFoundError("KRX_DB_NOT_FOUND")
    conn = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only=ON")
    return conn


def _compact(day: date) -> str:
    return day.strftime("%Y%m%d")


def read_krx_context(conn: sqlite3.Connection, *, start: date, end: date) -> dict[str, Any]:
    """Require physical rows and both markets/stock+index DATA for each session."""
    if start > end:
        raise ValueError("DATE_RANGE_INVALID")
    # Read a small prior buffer to compute first in-window KRX daily changes.
    probe_start = start - timedelta(days=12)
    recorded = conn.execute(
        """SELECT bas_dd, market, kind, status FROM day_status
           WHERE bas_dd>=? AND bas_dd<=?
             AND market IN ('KOSPI','KOSDAQ') AND kind IN ('stock','index')""",
        (_compact(probe_start), _compact(end)),
    ).fetchall()
    markers: dict[str, dict[str, str]] = {}
    for r in recorded:
        markers.setdefault(str(r["bas_dd"]), {})[str(r["market"])+":"+str(r["kind"])] = str(r["status"])
    wanted = {"KOSPI:stock", "KOSPI:index", "KOSDAQ:stock", "KOSDAQ:index"}
    good_days = [
        d for d, statuses in sorted(markers.items())
        if set(k for k,v in statuses.items() if v == "data") == wanted
    ]
    partial = sorted(
        d for d,statuses in markers.items()
        if d >= _compact(start) and d <= _compact(end)
        and any(v == "data" for v in statuses.values()) and d not in good_days
    )
    empty = sorted(
        d for d,statuses in markers.items()
        if d >= _compact(start) and d <= _compact(end)
        and all(v == "empty" for v in statuses.values())
    )
    public: dict[str, Any] = {
        "market_source": "EXISTING_LOCAL_KRX_MARKET_HISTORY_ONLY",
        "requested_start": start.isoformat(), "requested_end": end.isoformat(),
        "verified_common_sessions": 0,
        "matched_return_ready_sessions": 0,
        "ignored_empty_marker_days": len(empty),
        "partial_data_marker_days": len(partial),
        "partial_data_marker_date_sample": partial[:6],
        "invalid_physical_sessions": 0,
        "source_time_quality": "DATE_ONLY_NOT_PROVEN_PIT",
        "database_access": "SQLITE_MODE_RO_QUERY_ONLY",
    }
    if partial:
        return {**public, "status": "DATA_INSUFFICIENT",
                "reason": "PARTIAL_KRX_MARKET_DATA_MARKERS", "daily_returns": {}}
    daily_closes: dict[str, dict[str, Decimal]] = {}
    for d in good_days:
        prices = {}
        for market in MARKETS:
            row = conn.execute(
                "SELECT row_json FROM main_index_daily WHERE market=? AND bas_dd=?",
                (market, d),
            ).fetchone()
            exists = conn.execute(
                "SELECT 1 FROM stock_daily WHERE market=? AND bas_dd=? LIMIT 1",
                (market, d),
            ).fetchone()
            if not row or not exists:
                break
            try:
                raw = json.loads(row["row_json"])
                if not isinstance(raw, dict):
                    break
                observed = str(raw.get("date") or "").replace("-", "")
                val = _value(raw.get("close"))
                if observed != d or val is None:
                    break
            except (ValueError, TypeError):
                break
            prices[market] = val
        if len(prices) == 2:
            daily_closes[d] = prices
        else:
            public["invalid_physical_sessions"] += 1
    if public["invalid_physical_sessions"]:
        return {**public, "status": "DATA_INSUFFICIENT",
                "reason": "KRX_PHYSICAL_INDEX_OR_STOCK_ROWS_INVALID", "daily_returns": {}}
    keys = sorted(daily_closes)
    returns = {}
    for i, d in enumerate(keys):
        if i == 0 or d < _compact(start):
            continue
        earlier = keys[i - 1]
        if (date.fromisoformat(d[:4]+"-"+d[4:6]+"-"+d[6:]) -
                date.fromisoformat(earlier[:4]+"-"+earlier[4:6]+"-"+earlier[6:])).days > 7:
            continue
        returns[d[:4]+"-"+d[4:6]+"-"+d[6:]] = {
            market: (daily_closes[d][market] / daily_closes[earlier][market] - 1) * 100
            for market in MARKETS
        }
    public["verified_common_sessions"] = sum(d >= _compact(start) for d in keys)
    public["matched_return_ready_sessions"] = len(returns)
    public["first_valid_krx_date"] = (
        min(returns) if returns else None
    )
    public["last_valid_krx_date"] = max(returns) if returns else None
    if len(returns) < 5:
        return {**public, "status": "DATA_INSUFFICIENT",
                "reason": "FEWER_THAN_FIVE_KRX_MARKET_RETURNS", "daily_returns": returns}
    return {**public, "status": "READY", "reason": None,
            "daily_returns": returns}


def _blank(*, status: str, reason: str) -> dict[str, Any]:
    return {
        "contract_version": GLOBAL02_CONTRACT_VERSION,
        "status": status, "reason": reason,
        "claim_scope": "RETROSPECTIVE_DESCRIPTIVE_ONLY",
        "alignment": "SAME_DATE_LABEL_NOT_US_DATA_AVAILABLE_AT_KRX_CLOSE",
        "usage": "PERSONAL_NONCOMMERCIAL_LOCAL_RESEARCH_ONLY",
        "provider_rights_approved_for_publication": False,
        "data_source_rights_independently_approved": False,
        "raw_provider_rows_in_output": False,
        "raw_provider_rows_persisted": False,
        "network_requests_to_krx": 0,
        "db_writes": 0, "file_writes": 0,
        "historical_decision_eligible": False,
        "production_decision_approved": False,
        "risk_gate_input_approved": False,
        "scanner_input_approved": False,
        "jev_input_approved": False,
        "ai_transfer_approved": False,
    }


def run_research(
    *, start: date, end: date, confirm_personal_research: bool,
    metadata_only: bool, db_path: Path,
    client: Any = None, retrieved_at_utc: str | None = None,
) -> dict[str, Any]:
    if start > end or (end - start).days > 370 or end > date.today():
        return _blank(status="UNAVAILABLE", reason="INVALID_OR_FUTURE_RANGE")
    if not confirm_personal_research:
        return _blank(status="RIGHTS_UNVERIFIED", reason="PERSONAL_LOCAL_RESEARCH_OPT_IN_REQUIRED")
    stamp = retrieved_at_utc or datetime.now(timezone.utc).isoformat()
    result = _blank(status="UNAVAILABLE", reason="NOT_EVALUATED")
    result["requested_range"] = {"start": start.isoformat(), "end": end.isoformat()}
    created_client = client is None
    if metadata_only:
        # Source identity/units must be checkable even if local KRX history
        # is absent. Metadata-only never fetches FRED observation values.
        krx = {"status": "NOT_REQUIRED_FOR_METADATA", "daily_returns": {}}
    else:
        try:
            with closing(open_krx_readonly(db_path)) as conn:
                krx = read_krx_context(conn, start=start, end=end)
        except (sqlite3.Error, FileNotFoundError):
            return {**result, "status": "DATA_INSUFFICIENT",
                    "reason": "KRX_LOCAL_STORE_UNAVAILABLE"}
    result["krx"] = {k:v for k,v in krx.items() if k != "daily_returns"}
    if krx["status"] not in {"READY", "NOT_REQUIRED_FOR_METADATA"}:
        return {**result, "status": "DATA_INSUFFICIENT", "reason": krx["reason"]}
    try:
        active_client = client or FredClient()
    except FredConfigurationError:
        return {**result, "status": "SOURCE_UNAVAILABLE", "reason": "FRED_API_KEY_NOT_CONFIGURED"}
    series_reports: dict[str, Any] = {}
    relations: dict[str, Any] = {}
    try:
        for series_id in SPECS:
            try:
                metadata = active_client.series(series_id)
                if metadata_only:
                    series_reports[series_id] = validate_series_metadata(series_id, metadata)
                    continue
                # Include a preceding US baseline; never claim its publication
                # preceded any Korean market session.
                batch = active_client.observations(
                    series_id, observation_start=(start - timedelta(days=12)).isoformat(),
                    observation_end=end.isoformat(),
                )
                normalized = normalize_observations(
                    series_id, batch.observations, metadata,
                    start=start-timedelta(days=12), end=end,
                    retrieved_at_utc=stamp,
                )
                series_reports[series_id] = normalized["public"]
                relations[series_id] = retrospective_relation(normalized, krx, series_id=series_id)
            except Global02SeriesError as exc:
                series_reports[series_id] = {
                    "status": "SEMANTICS_UNVERIFIED",
                    "reason": str(exc), "series_id": series_id,
                }
            except FredApiError as exc:
                series_reports[series_id] = {
                    "status": "SOURCE_UNAVAILABLE",
                    "reason": ("FRED_AUTH_FAILED" if exc.status_code in {401, 403}
                               else "FRED_RATE_LIMITED" if exc.status_code == 429
                               else "FRED_PROVIDER_ERROR"),
                    "series_id": series_id,
                }
    finally:
        if created_client:
            active_client.close()
    result["series"] = series_reports
    if metadata_only:
        okay = all(s.get("series_id") == key and "reason" not in s
                   for key,s in series_reports.items())
        return {**result, "status": "METADATA_VERIFIED" if okay else "SEMANTICS_UNVERIFIED",
                "reason": None if okay else "SERIES_METADATA_CHECK_FAILED"}
    result["relations"] = relations
    if any(s.get("status") == "SEMANTICS_UNVERIFIED" for s in series_reports.values()):
        return {**result, "status": "SEMANTICS_UNVERIFIED",
                "reason": "PROVIDER_SERIES_CONTRACT_MISMATCH"}
    if any(s.get("status") == "SOURCE_UNAVAILABLE" for s in series_reports.values()):
        return {**result, "status": "SOURCE_UNAVAILABLE",
                "reason": "FRED_SERIES_QUERY_UNAVAILABLE"}
    if any(s.get("status") != "RETROSPECTIVE_DESCRIPTIVE_ONLY" for s in relations.values()):
        return {**result, "status": "DATA_INSUFFICIENT",
                "reason": "NOT_ENOUGH_FX_OIL_KRX_MATCHED_DAYS"}
    return {**result, "status": "RETROSPECTIVE_DESCRIPTIVE_ONLY",
            "reason": "SOURCE_PUBLISHED_TIME_AND_INDEPENDENT_PIT_UNVERIFIED"}


def main() -> int:
    parser = argparse.ArgumentParser(description="GLOBAL-02-S1 personal-local FRED FX/Brent retrospective study")
    parser.add_argument("--start", default="2026-09-01", help="YYYY-MM-DD")
    parser.add_argument("--end", default="2026-10-30", help="YYYY-MM-DD")
    parser.add_argument("--confirm-personal-research", action="store_true",
                        help="Required for FRED API access; personal noncommercial local study only")
    parser.add_argument("--metadata-only", action="store_true",
                        help="Check each official FRED series metadata, without quotations")
    args = parser.parse_args()
    try:
        start,end = date.fromisoformat(args.start),date.fromisoformat(args.end)
        report = run_research(start=start,end=end,
                              confirm_personal_research=args.confirm_personal_research,
                              metadata_only=args.metadata_only,db_path=market_db_path())
    except ValueError:
        report = _blank(status="UNAVAILABLE",reason="INVALID_DATE_ARGUMENT")
    print(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False))
    return 0 if report["status"] in {
        "METADATA_VERIFIED","RETROSPECTIVE_DESCRIPTIVE_ONLY"
    } else 2


if __name__ == "__main__":
    raise SystemExit(main())
