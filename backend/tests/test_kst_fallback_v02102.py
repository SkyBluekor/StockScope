from __future__ import annotations

from datetime import timedelta
from zoneinfo import ZoneInfoNotFoundError

from app.market import kst


def test_seoul_timezone_falls_back_to_fixed_kst_when_iana_data_is_missing(monkeypatch):
    def missing(_key: str):
        raise ZoneInfoNotFoundError("simulated missing tzdata")

    monkeypatch.setattr(kst, "ZoneInfo", missing)
    fallback = kst._build_seoul_tz()

    assert fallback.utcoffset(None) == timedelta(hours=9)
    assert fallback.tzname(None) == "KST"


def test_kst_helpers_return_aware_values():
    now = kst.now_kst()
    assert now.tzinfo is not None
    assert now.utcoffset() == timedelta(hours=9)
    assert kst.today_kst() == now.date()
