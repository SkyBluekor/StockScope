import pytest

from app.market.providers.krx import KrxProvider


def test_krx_date_format() -> None:
    assert KrxProvider._format_date("2026-09-07") == "20260907"
    assert KrxProvider._format_date("20260907") == "20260907"


@pytest.mark.parametrize("value", ["2026/09/07", "202609", "hello"])
def test_krx_invalid_date(value: str) -> None:
    with pytest.raises(ValueError):
        KrxProvider._format_date(value)


def test_krx_numeric_normalization() -> None:
    assert KrxProvider._as_int("1,234,567") == 1234567
    assert KrxProvider._as_float("-1.25") == -1.25
