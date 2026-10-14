"""S23-C strict, offline audit of a user-supplied KRX annual holiday export.

Only compares bytes and dates to the already-reviewed S23-B closure ledger.
It cannot authenticate the download origin or certify 244 open sessions.
No HTTP requests, SQLite, writes, migrations, scheduler, or provider/model calls.
"""
from __future__ import annotations

import csv
from datetime import date, timedelta
from hashlib import sha256
import io
import json
import re
from typing import Any

from app.market.session_calendar_s21 import CALENDAR_VERSION, closure_evidence


SOURCE_PAGE = "https://open.krx.co.kr/contents/MKD/01/0110/01100305/MKD01100305.jsp"
MAX_SOURCE_BYTES = 2 * 1024 * 1024
MAX_CLOSURE_ROWS = 366
_DATE_FIELD_JSON = "calnd_dd_dy"  # legacy KRX holiday grid JSON's date field
_DATE_FIELDS_CSV = ("일자", "Date", "date")
_KRX_MARKET_FIELDS = ("gridTp", "grid_tp", "market", "시장", "구분")
_KRX_MARKET_NAMES = ("KRX", "한국거래소")


class CalendarSourceAuditError(ValueError):
    """S23-C malformed or inappropriate market calendar source."""


def _decode(raw: bytes, source_format: str) -> str:
    if type(raw) is not bytes or not raw or len(raw) > MAX_SOURCE_BYTES:
        raise CalendarSourceAuditError("SOURCE_MISSING_OR_OVERSIZE")
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        if source_format != "csv":
            raise CalendarSourceAuditError("JSON_MUST_BE_UTF8") from None
        try:
            return raw.decode("cp949")
        except UnicodeDecodeError as exc:
            raise CalendarSourceAuditError("CSV_CHARSET_UNSUPPORTED") from exc


def _parse_day(value: Any, year: int) -> date:
    if type(value) is not str:
        raise CalendarSourceAuditError("CLOSURE_DATE_NOT_A_STRING")
    text = value.strip()
    if re.fullmatch(r"\d{8}", text):
        formatted = f"{text[:4]}-{text[4:6]}-{text[6:]}"
    elif re.fullmatch(r"\d{4}[-./]\d{2}[-./]\d{2}", text):
        formatted = re.sub(r"[./]", "-", text)
    else:
        raise CalendarSourceAuditError("CLOSURE_DATE_FORMAT_INVALID")
    try:
        day = date.fromisoformat(formatted)
    except ValueError as exc:
        raise CalendarSourceAuditError("CLOSURE_DATE_INVALID") from exc
    if day.year != year:
        raise CalendarSourceAuditError("CLOSURE_DATE_OUTSIDE_REQUESTED_YEAR")
    if day.weekday() >= 5:
        raise CalendarSourceAuditError("WEEKEND_IN_HOLIDAY_EXPORT_REQUIRES_REVIEW")
    return day


def _validate_market_scope(row: dict[str, Any]) -> None:
    for field in _KRX_MARKET_FIELDS:
        if field in row and row[field] is not None:
            scope = str(row[field]).strip()
            if scope and scope not in _KRX_MARKET_NAMES:
                raise CalendarSourceAuditError("NON_KRX_MARKET_SCOPE")


def _rows_from_json(raw: bytes) -> list[Any]:
    try:
        data = json.loads(
            _decode(raw, "json"),
            parse_constant=lambda _: (_ for _ in ()).throw(
                CalendarSourceAuditError("JSON_NONFINITE_VALUE")
            ),
        )
    except (ValueError, UnicodeError) as exc:
        if isinstance(exc, CalendarSourceAuditError):
            raise
        raise CalendarSourceAuditError("SOURCE_JSON_INVALID") from exc
    if not isinstance(data, dict):
        raise CalendarSourceAuditError("JSON_TOP_LEVEL_OBJECT_REQUIRED")
    _validate_market_scope(data)
    # Do not mistake an HTML spinner, a prefiltered slice, or a generic JSON
    # array for the KRX holiday endpoint's documented legacy data shape.
    rows = data.get("block1")
    if not isinstance(rows, list):
        raise CalendarSourceAuditError("KRX_BLOCK1_ARRAY_REQUIRED")
    return rows


def _rows_from_csv(raw: bytes) -> list[Any]:
    try:
        parser = csv.DictReader(io.StringIO(_decode(raw, "csv"), newline=""))
        columns = parser.fieldnames
        if not columns or len(set(columns)) != len(columns):
            raise CalendarSourceAuditError("CSV_COLUMNS_MISSING_OR_DUPLICATED")
        if not any(name in columns for name in _DATE_FIELDS_CSV):
            raise CalendarSourceAuditError("CSV_DATE_COLUMN_REQUIRED")
        rows = []
        for row in parser:
            if len(rows) >= MAX_CLOSURE_ROWS:
                raise CalendarSourceAuditError("HOLIDAY_SOURCE_ROW_LIMIT")
            if None in row or any(field_value is None for field_value in row.values()):
                raise CalendarSourceAuditError("CSV_ROW_COLUMN_COUNT_INVALID")
            rows.append(row)
        return rows
    except csv.Error as exc:
        raise CalendarSourceAuditError("SOURCE_CSV_INVALID") from exc


def _known_weekday_closures(year: int) -> set[date]:
    cursor = date(year, 1, 1)
    through = date(year + 1, 1, 1)
    result = set()
    while cursor < through:
        if cursor.weekday() < 5 and closure_evidence(cursor) is not None:
            result.add(cursor)
        cursor += timedelta(days=1)
    return result


def audit_source(
    raw: bytes,
    *,
    year: int,
    source_format: str,
    expected_sha256: str | None = None,
) -> dict[str, Any]:
    """Return a candidate-only report, never an authenticated FULL calendar.

    The SHA pins *these local bytes*, not who produced them. A matching
    list of 17 known dates also cannot establish an exhaustive future
    official open-day schedule or absence of later extraordinary closures.
    """
    if type(year) is not int or year != 2026:
        raise CalendarSourceAuditError("S23_C_ONLY_2026_REVIEWED_LEDGER")
    if source_format not in ("json", "csv"):
        raise CalendarSourceAuditError("UNSUPPORTED_SOURCE_FORMAT")
    _decode(raw, source_format)  # size/encoding check before hashing or parsing
    source_hash = sha256(raw).hexdigest()
    if expected_sha256 is not None:
        if (
            type(expected_sha256) is not str
            or re.fullmatch("[0-9a-f]{64}", expected_sha256) is None
        ):
            raise CalendarSourceAuditError("EXPECTED_SHA256_FORMAT_INVALID")
        if source_hash != expected_sha256:
            raise CalendarSourceAuditError("SOURCE_SHA256_MISMATCH")

    rows = (_rows_from_json(raw) if source_format == "json"
            else _rows_from_csv(raw))
    if not rows or len(rows) > MAX_CLOSURE_ROWS:
        raise CalendarSourceAuditError("HOLIDAY_SOURCE_EMPTY_OR_OVERSIZE")
    dates: set[date] = set()
    for row in rows:
        if not isinstance(row, dict):
            raise CalendarSourceAuditError("HOLIDAY_ROW_OBJECT_REQUIRED")
        _validate_market_scope(row)
        if source_format == "json":
            if _DATE_FIELD_JSON not in row:
                raise CalendarSourceAuditError("KRX_DATE_FIELD_REQUIRED")
            value = row[_DATE_FIELD_JSON]
        else:
            value = next(
                (row[field] for field in _DATE_FIELDS_CSV if field in row), None
            )
        day = _parse_day(value, year)
        if day in dates:
            raise CalendarSourceAuditError("DUPLICATE_CLOSURE_DATE")
        dates.add(day)
    known = _known_weekday_closures(year)
    missing = sorted(known - dates)
    extra = sorted(dates - known)
    candidate = not missing and not extra
    return {
        "version": "S23_C_KRX_HOLIDAY_SOURCE_AUDIT_V1",
        "status": "MATCHES_REVIEWED_CLOSURES" if candidate else "REVIEW_REQUIRED",
        "year": year,
        "calendar_evidence_version": CALENDAR_VERSION,
        "source_page": SOURCE_PAGE,
        "source_format": source_format,
        "raw_file_sha256": source_hash,
        "sha256_matches_supplied_pin": expected_sha256 is not None,
        "source_rows": len(rows),
        "known_s23_b_weekday_closures": len(known),
        "matched_known_closures": len(known & dates),
        "missing_known_closures": [d.isoformat() for d in missing],
        "unreviewed_source_closures": [d.isoformat() for d in extra],
        "download_origin_authenticated": False,
        "request_year_and_market_authenticated": False,
        "original_publication_time_verified": False,
        "full_calendar_eligible": False,
        "runtime_calendar_updated": False,
        "external_requests": 0,
        "runtime_db_writes": 0,
        "note": (
            "Local bytes only; KRX export origin, full-year query parameters, "
            "completeness and future schedule revisions require independent "
            "review before a FULL manifest can be proposed."
        ),
    }
