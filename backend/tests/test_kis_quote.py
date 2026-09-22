from __future__ import annotations

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
