import pytest

from app.core.stock_code import is_valid_stock_code, normalize_stock_code


def test_numeric_stock_code_preserves_leading_zeroes():
    assert normalize_stock_code("005930") == "005930"


def test_alphanumeric_stock_code_is_supported():
    assert normalize_stock_code("0011a0") == "0011A0"
    assert is_valid_stock_code("0011A0") is True


@pytest.mark.parametrize("value", ["5930", "0011-A0", "0011A00", "0011_0", ""])
def test_invalid_stock_codes_are_rejected(value: str):
    with pytest.raises(ValueError):
        normalize_stock_code(value)
