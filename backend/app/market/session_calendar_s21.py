"""S21 conservative stock-market calendar evidence for local EOD observation.

Only specifically confirmed KRX closure dates are enumerated. Other weekdays
are UNKNOWN without an actual complete KRX EOD snapshot; a missing price is
not proof of either a holiday or a market session.

Sources:
- KRX holiday rules: https://global.krx.co.kr/contents/GLB/06/0602/0602010201/GLB0602010201T1.jsp
- KRX mock trading-system notice dated 2026-09-29 for real KRX October
  closures: https://trn.krx.co.kr/index.jsp
  (2026-10-05, 2026-10-09).
The date ledger below is deliberately limited: no guesses for other years,
provisional holidays, elections or extraordinary closings.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Iterable

CALENDAR_VERSION = "KRX_CASH_EOD_VERIFIED_CLOSURES_2026_10_V1"
RULES_SOURCE = "https://global.krx.co.kr/contents/GLB/06/0602/0602010201/GLB0602010201T1.jsp"
NOTICE_SOURCE = "https://trn.krx.co.kr/index.jsp"

_CONFIRMED_CLOSURES: dict[date, tuple[str, str]] = {
    date(2026, 10, 5): ("개천절 대체휴일", NOTICE_SOURCE),
    date(2026, 10, 9): ("한글날", NOTICE_SOURCE),
}


def closure_evidence(day: date) -> dict[str, str] | None:
    """Return independently sourced closed status, not a guess from empty KRX."""
    if day.weekday() >= 5:
        return {
            "status": "CLOSED_VERIFIED", "reason": "WEEKEND",
            "source": RULES_SOURCE, "calendar_version": CALENDAR_VERSION,
        }
    evidence = _CONFIRMED_CLOSURES.get(day)
    if evidence is None:
        return None
    reason, url = evidence
    return {
        "status": "CLOSED_VERIFIED", "reason": reason,
        "source": url, "calendar_version": CALENDAR_VERSION,
    }


def unresolved_weekdays(
    signal: date, through: date, confirmed_eod_days: Iterable[date],
) -> list[str]:
    """Dates without verified closure OR a present EOD day.

    These dates might be a holiday or a missing market bar. The result is a
    reason to withhold completion, *not* proof that a trading day occurred.
    """
    complete = set(confirmed_eod_days)
    pending: list[str] = []
    day = signal + timedelta(days=1)
    while day <= through:
        if day not in complete and closure_evidence(day) is None:
            pending.append(day.isoformat())
        day += timedelta(days=1)
    return pending
