from __future__ import annotations

import re

_STOCK_CODE_PATTERN = re.compile(r"^[0-9A-Z]{6}$")


def normalize_stock_code(value: str) -> str:
    """Normalize a KRX short stock code.

    KRX short codes are identifiers, not integers.  They may contain
    uppercase Latin letters as well as digits (for example ``0011A0``),
    so leading zeroes and letters must never be stripped or coerced to int.
    """
    code = (value or "").strip().upper()
    if not _STOCK_CODE_PATTERN.fullmatch(code):
        raise ValueError("종목코드는 영문 대문자와 숫자로 이루어진 6자리 코드여야 합니다.")
    return code


def is_valid_stock_code(value: str) -> bool:
    try:
        normalize_stock_code(value)
        return True
    except ValueError:
        return False
