from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path.cwd()
QUOTE = ROOT / "backend" / "app" / "integrations" / "kis" / "quote.py"
TEST = ROOT / "backend" / "tests" / "test_kis_quote.py"

QUOTE_CONTENT = r'''from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx

from app.core.config import Settings, get_settings

from .client import base_url, validate_settings
from .token_cache import get_access_token


_QUOTE_PATH = "/uapi/domestic-stock/v1/quotations/inquire-price"
_QUOTE_TR_ID = "FHKST01010100"
_ALLOWED_MARKET_DIVISIONS = {"J", "NX", "UN"}


class KisQuoteError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        code: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code


@dataclass(frozen=True, slots=True)
class KisDomesticPrice:
    ticker: str
    name: str | None
    market_division: str
    current_price: Decimal
    change_amount: Decimal
    change_rate: Decimal
    change_sign: str | None
    open_price: Decimal
    high_price: Decimal
    low_price: Decimal
    base_price: Decimal
    volume: Decimal


def _required_decimal(
    row: dict[str, Any],
    field: str,
    *,
    positive: bool = False,
) -> Decimal:
    raw = row.get(field)
    if raw is None or str(raw).strip() == "":
        raise KisQuoteError(f"KIS quote output is missing required field: {field}")

    try:
        value = Decimal(str(raw).strip())
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise KisQuoteError(
            f"KIS quote field {field} is not a valid number."
        ) from exc

    if not value.is_finite():
        raise KisQuoteError(f"KIS quote field {field} is not finite.")
    if positive and value <= 0:
        raise KisQuoteError(f"KIS quote field {field} must be greater than zero.")
    if value < 0 and field in {
        "stck_oprc",
        "stck_hgpr",
        "stck_lwpr",
        "stck_sdpr",
        "acml_vol",
    }:
        raise KisQuoteError(f"KIS quote field {field} must not be negative.")
    return value


def _normalize_ticker(ticker: str) -> str:
    value = (ticker or "").strip().upper()
    if len(value) != 6 or not value.isdigit():
        raise KisQuoteError("Domestic stock ticker must be exactly 6 digits.")
    return value


def _normalize_market_division(market_division: str) -> str:
    value = (market_division or "").strip().upper()
    if value not in _ALLOWED_MARKET_DIVISIONS:
        raise KisQuoteError(
            "market_division must be one of J (KRX), NX (NXT), or UN (integrated)."
        )
    return value


def inquire_domestic_price(
    ticker: str,
    market_division: str = "J",
    settings: Settings | None = None,
    *,
    access_token: str | None = None,
    timeout_seconds: float = 15.0,
    http_client: httpx.Client | None = None,
) -> KisDomesticPrice:
    """Read a domestic-stock quote from KIS.

    This is a market-data adapter only. It must not be used to recompute the
    official EOD Strategy/Risk snapshot inside HOLD.1.
    """
    settings = validate_settings(settings or get_settings())
    normalized_ticker = _normalize_ticker(ticker)
    normalized_market = _normalize_market_division(market_division)
    token_value = access_token or get_access_token(settings).access_token

    headers = {
        "content-type": "application/json; charset=utf-8",
        "authorization": f"Bearer {token_value}",
        "appkey": settings.kis_app_key or "",
        "appsecret": settings.kis_app_secret or "",
        "tr_id": _QUOTE_TR_ID,
        "custtype": "P",
    }
    params = {
        "FID_COND_MRKT_DIV_CODE": normalized_market,
        "FID_INPUT_ISCD": normalized_ticker,
    }

    owns_client = http_client is None
    client = http_client or httpx.Client(timeout=timeout_seconds)

    try:
        try:
            response = client.get(
                f"{base_url(settings.kis_env)}{_QUOTE_PATH}",
                headers=headers,
                params=params,
                timeout=timeout_seconds,
            )
        except httpx.HTTPError as exc:
            raise KisQuoteError(
                f"KIS quote request failed before receiving a response: {exc}"
            ) from exc

        if response.status_code != 200:
            raise KisQuoteError(
                "KIS quote request returned a non-200 response.",
                status_code=response.status_code,
            )

        try:
            body = response.json()
        except ValueError as exc:
            raise KisQuoteError(
                "KIS quote response was not valid JSON.",
                status_code=response.status_code,
            ) from exc

        if not isinstance(body, dict):
            raise KisQuoteError("KIS quote response had an unexpected shape.")

        if str(body.get("rt_cd") or "") != "0":
            raise KisQuoteError(
                str(body.get("msg1") or "KIS quote request failed."),
                status_code=response.status_code,
                code=str(body.get("msg_cd") or "") or None,
            )

        output = body.get("output")
        if not isinstance(output, dict) or not output:
            raise KisQuoteError("KIS quote response did not contain output.")

        current_price = _required_decimal(output, "stck_prpr", positive=True)

        return KisDomesticPrice(
            ticker=normalized_ticker,
            name=(
                str(
                    output.get("hts_kor_isnm")
                    or output.get("prdt_name")
                    or ""
                ).strip()
                or None
            ),
            market_division=normalized_market,
            current_price=current_price,
            change_amount=_required_decimal(output, "prdy_vrss"),
            change_rate=_required_decimal(output, "prdy_ctrt"),
            change_sign=(
                str(output.get("prdy_vrss_sign")).strip()
                if output.get("prdy_vrss_sign") not in (None, "")
                else None
            ),
            open_price=_required_decimal(output, "stck_oprc"),
            high_price=_required_decimal(output, "stck_hgpr"),
            low_price=_required_decimal(output, "stck_lwpr"),
            base_price=_required_decimal(output, "stck_sdpr"),
            volume=_required_decimal(output, "acml_vol"),
        )
    finally:
        if owns_client:
            client.close()
'''

TEST_CONTENT = r'''from __future__ import annotations

import httpx
import pytest

from app.core.config import Settings
from app.integrations.kis.quote import KisQuoteError, inquire_domestic_price


def _settings(**overrides) -> Settings:
    values = {
        "kis_app_key": "app-key",
        "kis_app_secret": "app-secret",
        "kis_account_no": "12345678",
        "kis_account_product_code": "01",
        "kis_env": "real",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def _success_body(**output_overrides):
    output = {
        "hts_kor_isnm": "삼성전자",
        "stck_prpr": "84200",
        "prdy_vrss": "1200",
        "prdy_vrss_sign": "2",
        "prdy_ctrt": "1.45",
        "stck_oprc": "83300",
        "stck_hgpr": "85000",
        "stck_lwpr": "82900",
        "stck_sdpr": "83000",
        "acml_vol": "12345678",
    }
    output.update(output_overrides)
    return {
        "rt_cd": "0",
        "msg_cd": "MCA00000",
        "msg1": "정상처리 되었습니다.",
        "output": output,
    }


def test_quote_request_contract_and_parsing():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["authorization"] = request.headers.get("authorization")
        seen["tr_id"] = request.headers.get("tr_id")
        seen["market"] = request.url.params.get("FID_COND_MRKT_DIV_CODE")
        seen["ticker"] = request.url.params.get("FID_INPUT_ISCD")
        return httpx.Response(200, json=_success_body())

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        quote = inquire_domestic_price(
            "005930",
            "J",
            _settings(),
            access_token="test-token",
            http_client=client,
        )

    assert seen == {
        "path": "/uapi/domestic-stock/v1/quotations/inquire-price",
        "authorization": "Bearer test-token",
        "tr_id": "FHKST01010100",
        "market": "J",
        "ticker": "005930",
    }
    assert quote.ticker == "005930"
    assert quote.name == "삼성전자"
    assert str(quote.current_price) == "84200"
    assert str(quote.change_amount) == "1200"
    assert str(quote.change_rate) == "1.45"
    assert str(quote.open_price) == "83300"
    assert str(quote.high_price) == "85000"
    assert str(quote.low_price) == "82900"
    assert str(quote.base_price) == "83000"
    assert str(quote.volume) == "12345678"


def test_quote_rejects_kis_business_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "rt_cd": "1",
                "msg_cd": "TEST001",
                "msg1": "조회 실패",
                "output": {},
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(KisQuoteError) as exc_info:
            inquire_domestic_price(
                "005930",
                settings=_settings(),
                access_token="test-token",
                http_client=client,
            )

    assert exc_info.value.code == "TEST001"


@pytest.mark.parametrize(
    ("bad_value", "expected_fragment"),
    [
        ("", "missing required field"),
        ("not-a-number", "not a valid number"),
        ("0", "greater than zero"),
        ("-1", "greater than zero"),
    ],
)
def test_quote_never_silently_turns_bad_current_price_into_zero(
    bad_value,
    expected_fragment,
):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=_success_body(stck_prpr=bad_value),
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(KisQuoteError) as exc_info:
            inquire_domestic_price(
                "005930",
                settings=_settings(),
                access_token="test-token",
                http_client=client,
            )

    assert expected_fragment in str(exc_info.value)


def test_quote_validates_ticker_and_market_before_network():
    with pytest.raises(KisQuoteError):
        inquire_domestic_price(
            "5930",
            settings=_settings(),
            access_token="test-token",
        )

    with pytest.raises(KisQuoteError):
        inquire_domestic_price(
            "005930",
            market_division="BAD",
            settings=_settings(),
            access_token="test-token",
        )
'''

SMOKE_CODE = r'''import sys
sys.path.insert(0, "backend")

from app.integrations.kis.quote import inquire_domestic_price

quote = inquire_domestic_price("005930", "J")

print("KIS PRICE: OK")
print("TICKER:", quote.ticker)
print("NAME:", quote.name or "-")
print("MARKET:", quote.market_division)
print("CURRENT_PRICE:", quote.current_price)
print("CHANGE:", quote.change_amount)
print("CHANGE_RATE:", f"{quote.change_rate}%")
print("OPEN:", quote.open_price)
print("HIGH:", quote.high_price)
print("LOW:", quote.low_price)
print("BASE_PRICE:", quote.base_price)
print("VOLUME:", quote.volume)
print("APP_KEY_PRINTED: NO")
print("APP_SECRET_PRINTED: NO")
print("ACCOUNT_NO_PRINTED: NO")
print("ORDER_API_CALLED: NO")
'''


def fail(message: str) -> None:
    raise RuntimeError(message)


def run(cmd: list[str], label: str) -> None:
    print()
    print(f"=== {label} ===")
    print(" ".join(cmd))
    result = subprocess.run(cmd, cwd=ROOT)
    if result.returncode != 0:
        fail(f"{label} failed with exit code {result.returncode}")


def main() -> int:
    print("PROJECT ROOT:", ROOT)
    print("KIS.1 domestic current-price REST")
    print("TARGET: 005930 / J")
    print("Order API called: NO")
    print("Scanner/Strategy/Risk modified: NO")

    required = [
        ROOT / "backend" / "app" / "integrations" / "kis" / "client.py",
        ROOT / "backend" / "app" / "integrations" / "kis" / "token_cache.py",
        ROOT / "backend" / "app" / "integrations" / "kis" / "account.py",
        ROOT / "backend" / "tests" / "test_kis_client.py",
        ROOT / "backend" / "tests" / "test_kis_account.py",
    ]
    for path in required:
        if not path.is_file():
            fail(f"Required KIS file is missing: {path}")

    if QUOTE.exists():
        fail(f"Target already exists: {QUOTE}")
    if TEST.exists():
        fail(f"Target already exists: {TEST}")

    compile(QUOTE_CONTENT, str(QUOTE), "exec")
    compile(TEST_CONTENT, str(TEST), "exec")

    created: list[Path] = []
    tests_passed = False

    try:
        QUOTE.write_text(QUOTE_CONTENT, encoding="utf-8", newline="\n")
        created.append(QUOTE)
        TEST.write_text(TEST_CONTENT, encoding="utf-8", newline="\n")
        created.append(TEST)

        venv_python = ROOT / ".venv" / "Scripts" / "python.exe"
        python_exe = str(
            venv_python if venv_python.is_file() else Path(sys.executable)
        )

        run(
            [
                python_exe,
                "-m",
                "pytest",
                "backend/tests/test_kis_client.py",
                "backend/tests/test_kis_account.py",
                "backend/tests/test_kis_quote.py",
                "-q",
            ],
            "KIS.1 targeted regression",
        )
        tests_passed = True

        print()
        print("=== KIS.1 REAL QUOTE SMOKE ===")
        print("One read-only market-data request will be sent.")
        result = subprocess.run(
            [python_exe, "-c", SMOKE_CODE],
            cwd=ROOT,
        )
        if result.returncode != 0:
            print()
            print("KIS.1 LIVE SMOKE FAILED")
            print("Unit/regression tests already passed, so source files are kept for diagnosis.")
            print("No order API was called.")
            return result.returncode

        print()
        print("KIS.1 CLOSED")
        print("Added:")
        print(" - backend/app/integrations/kis/quote.py")
        print(" - backend/tests/test_kis_quote.py")
        print("Existing auth/account regression: PASS")
        print("Real 005930 quote: PASS")
        print("Secrets printed: NO")
        print("Account number printed: NO")
        print("Order API called: NO")
        print("Scanner/Strategy/Risk modified: NO")
        return 0

    except Exception:
        if not tests_passed:
            for path in reversed(created):
                if path.exists():
                    path.unlink()
            print()
            print("FAILED — KIS.1 source additions were restored because local tests failed.")
        raise


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print()
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
