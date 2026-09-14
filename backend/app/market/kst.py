from __future__ import annotations

from datetime import date, datetime, timedelta, timezone, tzinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def _build_seoul_tz() -> tzinfo:
    """Return Asia/Seoul when IANA tzdata exists, otherwise fixed KST (UTC+9).

    Windows Python installations may not ship an IANA timezone database. StockScope
    only needs Korea's current local date/time for KRX cache volatility and the
    daily API budget ledger, so fixed UTC+9 is a safe fallback for these paths.
    """
    try:
        return ZoneInfo("Asia/Seoul")
    except ZoneInfoNotFoundError:
        return timezone(timedelta(hours=9), name="KST")


SEOUL_TZ = _build_seoul_tz()


def now_kst() -> datetime:
    return datetime.now(SEOUL_TZ)


def today_kst() -> date:
    return now_kst().date()
