"""Versioned, fail-closed KRX cash-session evidence (S21 compatibility / S23).

This module is offline and read-only. A weekday without a complete sourced
annual schedule or observed stock+index EOD is UNKNOWN, never a proved session.
Annual manifests must be reviewed and committed as source code; no downloaded
holiday list, user-local file, or empty KRX response is trusted automatically.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
import re
from typing import Iterable
from urllib.parse import urlsplit


CALENDAR_VERSION = "KRX_CASH_SESSION_EVIDENCE_S23_V2"
RULES_SOURCE = "https://global.krx.co.kr/contents/GLB/06/0602/0602010201/GLB0602010201T1.jsp"
NOTICE_SOURCE = "https://trn.krx.co.kr/index.jsp"
# KRX KOSPI/KOSDAQ disclosure division's dated 2026 closure intervals.
# Cross-checked against KRX market rules, official public holiday law, and
# KRX KONEX dated closure notice for June 3 / July 17.
KRX_2026_DISCLOSURE_SOURCE = "https://kind.krx.co.kr/external/dst/notice/11637/%5B%ED%95%9C%EA%B5%AD%EA%B1%B0%EB%9E%98%EC%86%8C%5D%202026%EB%85%84%20%EC%98%AC%EB%B9%BC%EB%AF%B8%EA%B3%B5%EC%8B%9C%20%EC%95%88%EB%82%B4.pdf"
KRX_STATUTORY_HOLIDAY_SOURCE = "https://www.law.go.kr/lsLinkCommonInfo.do?lsJoLnkSeq=1029728073"
KRX_2026_SPECIAL_NOTICE_SOURCE = "https://kind.krx.co.kr/external/2026/05/20/000110/20260520000197/32154.htm"
ANNUAL_SCHEDULE_SOURCE = (
    "https://open.krx.co.kr/contents/MKD/01/0110/01100305/MKD01100305.jsp"
)
_ALLOWED_FULL_YEAR_HOSTS = frozenset({
    "open.krx.co.kr", "www.krx.co.kr", "regulation.krx.co.kr",
})


@dataclass(frozen=True)
class AnnualSessionEvidence:
    """Reviewable, immutable representation of one cash-market calendar year.

    FULL means each weekday was individually accounted for by the *official*
    schedule. PARTIAL supports only specifically evidenced closures, not
    assumed open dates. A source SHA is an audit identifier, NOT a signature or
    proof that a remote source was actually verified.
    """

    year: int
    version: str
    coverage: str
    source_url: str
    source_sha256: str | None
    closed_days: tuple[tuple[date, str, str], ...] = ()
    open_days: tuple[date, ...] = ()

    def __post_init__(self) -> None:
        if type(self.year) is not int or not 1990 <= self.year <= 2100:
            raise ValueError("CALENDAR_YEAR_INVALID")
        if self.coverage not in ("PARTIAL", "FULL") or not self.version.strip():
            raise ValueError("CALENDAR_COVERAGE_OR_VERSION_INVALID")
        if not self.source_url.startswith("https://"):
            raise ValueError("CALENDAR_SOURCE_INVALID")
        closed = [d for d, _, _ in self.closed_days]
        opened = list(self.open_days)
        if (
            len(set(closed)) != len(closed) or len(set(opened)) != len(opened)
            or set(closed) & set(opened)
            or any(type(d) is not date or d.year != self.year or d.weekday() >= 5
                   for d in closed + opened)
        ):
            raise ValueError("CALENDAR_DUPLICATE_OR_DAY_INVALID")
        for _, reason, source in self.closed_days:
            if not isinstance(reason, str) or not reason.strip():
                raise ValueError("CALENDAR_CLOSURE_REASON_MISSING")
            if not isinstance(source, str) or not source.startswith("https://"):
                raise ValueError("CALENDAR_CLOSURE_SOURCE_MISSING")
        if self.coverage == "PARTIAL":
            if opened:
                raise ValueError("PARTIAL_CALENDAR_CANNOT_CERTIFY_OPEN_DAYS")
            return
        host = urlsplit(self.source_url).hostname
        if (
            host not in _ALLOWED_FULL_YEAR_HOSTS
            or not isinstance(self.source_sha256, str)
            or re.fullmatch(r"[0-9a-f]{64}", self.source_sha256) is None
        ):
            raise ValueError("FULL_CALENDAR_OFFICIAL_SOURCE_REQUIRED")
        cursor = date(self.year, 1, 1)
        through = date(self.year + 1, 1, 1)
        weekdays: set[date] = set()
        while cursor < through:
            if cursor.weekday() < 5:
                weekdays.add(cursor)
            cursor += timedelta(days=1)
        if set(closed) | set(opened) != weekdays:
            raise ValueError("FULL_CALENDAR_WEEKDAY_COVERAGE_INCOMPLETE")


# S23-B: 2026 dated cash-market closures cross-checked against KRX's own
# disclosure-division schedule and statutory holiday rules. This covers the
# 17 identified *weekday closures*, NOT the 244 weekdays marked open. Until
# an independently verified complete KRX cash-session schedule is recorded,
# this manifest remains PARTIAL; all other weekdays remain UNKNOWN unless
# independently proven by complete stock+index EOD data.
# Source provenance is per date; do not infer an extraordinary closure from
# the KRX simulation system's separate maintenance or replay-only notices.
_2026_PARTIAL = AnnualSessionEvidence(
    year=2026,
    version=CALENDAR_VERSION,
    coverage="PARTIAL",
    source_url=KRX_2026_DISCLOSURE_SOURCE,
    source_sha256=None,
    closed_days=(
        (date(2026, 1, 1), "신정", KRX_STATUTORY_HOLIDAY_SOURCE),
        (date(2026, 2, 16), "설 연휴", KRX_2026_DISCLOSURE_SOURCE),
        (date(2026, 2, 17), "설날", KRX_2026_DISCLOSURE_SOURCE),
        (date(2026, 2, 18), "설 연휴", KRX_2026_DISCLOSURE_SOURCE),
        (date(2026, 3, 2), "삼일절 대체공휴일", KRX_2026_DISCLOSURE_SOURCE),
        (date(2026, 5, 1), "노동절", KRX_2026_DISCLOSURE_SOURCE),
        (date(2026, 5, 5), "어린이날", KRX_STATUTORY_HOLIDAY_SOURCE),
        (date(2026, 5, 25), "부처님오신날 대체공휴일", KRX_2026_DISCLOSURE_SOURCE),
        (date(2026, 6, 3), "전국동시지방선거일", KRX_2026_SPECIAL_NOTICE_SOURCE),
        (date(2026, 7, 17), "제헌절", KRX_2026_SPECIAL_NOTICE_SOURCE),
        (date(2026, 8, 17), "광복절 대체공휴일", KRX_2026_DISCLOSURE_SOURCE),
        (date(2026, 9, 24), "추석 연휴", KRX_2026_DISCLOSURE_SOURCE),
        (date(2026, 9, 25), "추석", KRX_2026_DISCLOSURE_SOURCE),
        (date(2026, 10, 5), "개천절 대체휴일", NOTICE_SOURCE),
        (date(2026, 10, 9), "한글날", NOTICE_SOURCE),
        (date(2026, 12, 25), "성탄절", KRX_2026_DISCLOSURE_SOURCE),
        (date(2026, 12, 31), "연말 휴장", KRX_2026_DISCLOSURE_SOURCE),
    ),
)
_REVIEWED_CALENDARS = {2026: _2026_PARTIAL}


def _calendar(day: date, override: AnnualSessionEvidence | None) -> AnnualSessionEvidence | None:
    if type(day) is not date:
        raise ValueError("CALENDAR_DATE_INVALID")
    if override is not None:
        if override.year != day.year:
            raise ValueError("CALENDAR_YEAR_MISMATCH")
        return override
    return _REVIEWED_CALENDARS.get(day.year)


def closure_evidence(
    day: date, *, calendar: AnnualSessionEvidence | None = None,
) -> dict[str, str] | None:
    """Proof of a market-wide closure; never infer it from absent price rows."""
    ledger = _calendar(day, calendar)
    version = ledger.version if ledger else CALENDAR_VERSION
    if day.weekday() >= 5:
        return {
            "status": "CLOSED_VERIFIED", "reason": "WEEKEND",
            "source": RULES_SOURCE, "calendar_version": version,
        }
    if ledger is None:
        return None
    for closed_day, reason, source in ledger.closed_days:
        if closed_day == day:
            return {
                "status": "CLOSED_VERIFIED", "reason": reason,
                "source": source, "calendar_version": version,
            }
    return None


def session_evidence(
    day: date, *, calendar: AnnualSessionEvidence | None = None,
) -> dict[str, str | None]:
    """Return CLOSED_VERIFIED, OPEN_VERIFIED or UNKNOWN with explicit provenance."""
    ledger = _calendar(day, calendar)
    closed = closure_evidence(day, calendar=calendar)
    if closed is not None:
        return {
            "calendar_state": "CLOSED_VERIFIED",
            "reason": closed["reason"], "source": closed["source"],
            "calendar_version": closed["calendar_version"],
        }
    if ledger is not None and ledger.coverage == "FULL" and day in ledger.open_days:
        return {
            "calendar_state": "OPEN_VERIFIED", "reason": "OFFICIAL_YEAR_SCHEDULE",
            "source": ledger.source_url, "calendar_version": ledger.version,
        }
    return {
        "calendar_state": "UNKNOWN", "reason": "DAY_NOT_IN_REVIEWED_SCHEDULE",
        "source": None, "calendar_version": ledger.version if ledger else CALENDAR_VERSION,
    }


def market_day_evidence(
    day: date, *, stock_status: str | None = None,
    index_status: str | None = None, stock_rows: int = 0,
    index_rows: int = 0, calendar: AnnualSessionEvidence | None = None,
) -> dict[str, str | None]:
    """Combine sourced calendar with real market-wide EOD evidence.

    Individual suspended/unlisted ticker prices never establish a market-wide
    holiday. Actual complete stock+index markers can prove a stored session
    even for a date not yet included in an annual calendar.
    """
    if (
        type(stock_rows) is not int or type(index_rows) is not int
        or stock_rows < 0 or index_rows < 0
    ):
        raise ValueError("MARKET_EOD_COUNTS_INVALID")
    evidence = session_evidence(day, calendar=calendar)
    has_any = (
        stock_status is not None or index_status is not None
        or stock_rows > 0 or index_rows > 0
    )
    complete = (
        stock_status == "data" and index_status == "data"
        and stock_rows > 0 and index_rows == 1
    )
    if evidence["calendar_state"] == "CLOSED_VERIFIED":
        state = "CLOSURE_DATA_CONFLICT" if has_any else "CLOSED_VERIFIED"
    elif complete:
        state = "STORED_COMPLETE"
    elif has_any:
        state = "PARTIAL_OR_UNVERIFIED_EXISTING"
    elif evidence["calendar_state"] == "OPEN_VERIFIED":
        state = "OPEN_BUT_MISSING_EOD"
    else:
        state = "UNKNOWN"
    return {**evidence, "state": state}


def unresolved_weekdays(
    signal: date, through: date, confirmed_eod_days: Iterable[date],
    *, calendar: AnnualSessionEvidence | None = None,
) -> list[str]:
    """Unverified dates and closure/EOD conflicts across the exact interval.

    Missing weekdays are unresolved unless a dated closure is sourced. A
    complete EOD row reported for a sourced closure is a conflict, not a valid
    extra trading day. For immature windows only dates through as-of are read.
    """
    complete = set(confirmed_eod_days)
    pending: list[str] = []
    day = signal + timedelta(days=1)
    while day <= through:
        closed = closure_evidence(day, calendar=calendar) is not None
        if (closed and day in complete) or (not closed and day not in complete):
            pending.append(day.isoformat())
        day += timedelta(days=1)
    return pending
