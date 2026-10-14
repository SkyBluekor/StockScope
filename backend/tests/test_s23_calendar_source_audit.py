"""S23-C synthetic holiday export audit: no network or real market DB."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from app.market.calendar_source_audit_s23 import (
    CalendarSourceAuditError, audit_source,
)
from tools.data.krx_calendar_audit_s23 import main as audit_cli


_DATES = (
    "2026-01-01", "2026-02-16", "2026-02-17", "2026-02-18", "2026-03-02",
    "2026-05-01", "2026-05-05", "2026-05-25", "2026-06-03", "2026-07-17",
    "2026-08-17", "2026-09-24", "2026-09-25", "2026-10-05", "2026-10-09",
    "2026-12-25", "2026-12-31",
)


def _json(dates=_DATES, *, market="KRX"):
    return json.dumps({
        "gridTp": market,
        "block1": [{"calnd_dd_dy": d} for d in dates],
    }, ensure_ascii=False).encode("utf-8")


def _report(raw=None, **kw):
    return audit_source(raw if raw is not None else _json(),
                        year=2026, source_format="json", **kw)


def test_exact_known_list_is_only_consistent_not_authenticated():
    original = _json()
    result = _report(original, expected_sha256=hashlib.sha256(original).hexdigest())
    assert result["status"] == "MATCHES_REVIEWED_CLOSURES"
    assert result["matched_known_closures"] == 17
    assert result["raw_file_sha256"] == hashlib.sha256(original).hexdigest()
    assert result["sha256_matches_supplied_pin"] is True
    assert result["download_origin_authenticated"] is False
    assert result["request_year_and_market_authenticated"] is False
    assert result["original_publication_time_verified"] is False
    assert result["full_calendar_eligible"] is False
    assert result["runtime_calendar_updated"] is False
    assert result["runtime_db_writes"] == 0
    assert result["external_requests"] == 0


def test_short_query_is_not_mistaken_for_full_year():
    result = _report(_json(_DATES[:10]))
    assert result["status"] == "REVIEW_REQUIRED"
    assert len(result["missing_known_closures"]) == 7
    assert result["full_calendar_eligible"] is False


def test_new_extra_closure_requires_review_without_overwriting_frozen_calendar():
    result = _report(_json(_DATES + ("2026-11-19",)))
    assert result["status"] == "REVIEW_REQUIRED"
    assert result["unreviewed_source_closures"] == ["2026-11-19"]
    assert result["full_calendar_eligible"] is False


@pytest.mark.parametrize("bad,reason", [
    (_json(_DATES + (_DATES[0],)), "DUPLICATE_CLOSURE_DATE"),
    (_json(("2027-01-01",)), "CLOSURE_DATE_OUTSIDE_REQUESTED_YEAR"),
    (_json(("2026-01-03",)), "WEEKEND_IN_HOLIDAY_EXPORT_REQUIRES_REVIEW"),
    (_json(market="EUREX"), "NON_KRX_MARKET_SCOPE"),
    (b"{}", "KRX_BLOCK1_ARRAY_REQUIRED"),
    (b"[]", "JSON_TOP_LEVEL_OBJECT_REQUIRED"),
    (b"<html>Loading...</html>", "SOURCE_JSON_INVALID"),
    (b'{"gridTp":"KRX","block1":[{}]}', "KRX_DATE_FIELD_REQUIRED"),
    (b'{"block1": [{"calnd_dd_dy":"2026-02-30"}]}', "CLOSURE_DATE_INVALID"),
])
def test_malformed_or_wrong_market_fails_closed(bad, reason):
    with pytest.raises(CalendarSourceAuditError, match=reason):
        _report(bad)


def test_pin_validation_blocks_modified_export():
    with pytest.raises(CalendarSourceAuditError, match="SOURCE_SHA256_MISMATCH"):
        _report(_json(), expected_sha256="0" * 64)
    with pytest.raises(CalendarSourceAuditError, match="EXPECTED_SHA256_FORMAT_INVALID"):
        _report(_json(), expected_sha256="not-a-hash")


def test_csv_utf8_bom_and_cp949_parsers_produce_candidate_only():
    for encoding in ("utf-8-sig", "cp949"):
        src = ("일자,시장,비고\n" +
               "".join(f"{d},한국거래소,휴장\n" for d in _DATES)).encode(encoding)
        result = audit_source(src, year=2026, source_format="csv")
        assert result["status"] == "MATCHES_REVIEWED_CLOSURES"
        assert result["source_format"] == "csv"
        assert result["full_calendar_eligible"] is False


def test_wrong_schema_duplicates_and_excess_size_are_blocked():
    with pytest.raises(CalendarSourceAuditError, match="CSV_DATE_COLUMN_REQUIRED"):
        audit_source(b"field\nvalue\n", year=2026, source_format="csv")
    with pytest.raises(CalendarSourceAuditError, match="CSV_COLUMNS_MISSING_OR_DUPLICATED"):
        audit_source(b"Date,Date\n1,2\n", year=2026, source_format="csv")
    with pytest.raises(CalendarSourceAuditError, match="SOURCE_MISSING_OR_OVERSIZE"):
        audit_source(b" " * (2 * 1024 * 1024 + 1), year=2026, source_format="csv")
    with pytest.raises(CalendarSourceAuditError, match="S23_C_ONLY_2026_REVIEWED_LEDGER"):
        audit_source(_json(), year=2025, source_format="json")


def test_cli_never_modifies_local_source_or_creates_market_db(tmp_path: Path, capsys):
    inp = tmp_path / "official_candidate.json"
    inp.write_bytes(_json())
    before = inp.read_bytes()
    assert audit_cli(["--source-file", str(inp), "--year", "2026"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "MATCHES_REVIEWED_CLOSURES"
    assert result["full_calendar_eligible"] is False
    assert inp.read_bytes() == before
    assert list(tmp_path.iterdir()) == [inp]


def test_cli_blocks_unknown_format_and_missing_file(tmp_path: Path, capsys):
    path = tmp_path / "market.xlsx"
    path.write_bytes(b"not-csv")
    assert audit_cli(["--source-file", str(path)]) == 2
    assert json.loads(capsys.readouterr().out)["reason"] == (
        "ONLY_ORIGINAL_JSON_OR_CSV_EXPORTS_SUPPORTED"
    )
    assert audit_cli(["--source-file", str(tmp_path / "missing.json")]) == 2
    assert json.loads(capsys.readouterr().out)["reason"] == "SOURCE_FILE_NOT_FOUND"

def test_ragged_csv_records_are_rejected():
    for content in (
        "일자,시장\n2026-01-01,한국거래소,unexpected\n",
        "일자,시장,비고\n2026-01-01,한국거래소\n",
    ):
        with pytest.raises(CalendarSourceAuditError, match="CSV_ROW_COLUMN_COUNT_INVALID"):
            audit_source(content.encode("utf-8"), year=2026, source_format="csv")

