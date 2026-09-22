from __future__ import annotations

import json

import httpx
import pytest

from app.core.config import Settings
from app.integrations.kis.websocket_client import (
    KisWebSocketError,
    build_realtime_price_subscription,
    issue_ws_approval_key,
    parse_realtime_price_message,
    parse_system_message,
    websocket_url,
)


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


def _tick_payload(
    *,
    ticker: str = "005930",
    current_price: str = "277500",
) -> str:
    fields = [
        ticker,
        "151501",
        current_price,
        "2",
        "3500",
        "1.28",
        "275000",
        "283000",
        "283500",
        "271500",
        "277500",
        "277000",
        "10",
        "18157410",
        "5000000000",
        "100",
        "120",
        "20",
        "103.1",
        "1000",
        "1200",
        "1",
        "52.0",
        "110.0",
        "090001",
        "2",
        "9000",
        "090100",
        "2",
        "9500",
        "090200",
        "5",
        "2500",
        "20260922",
        "0",
        "N",
        "100",
        "200",
        "10000",
        "12000",
        "2.1",
        "17000000",
        "106.0",
        "0",
        "0",
        "276000",
    ]
    assert len(fields) == 46
    return "^".join(fields)


def test_ws_approval_contract():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        payload = json.loads(request.content.decode("utf-8"))
        seen["grant_type"] = payload["grant_type"]
        seen["appkey"] = payload["appkey"]
        seen["secretkey"] = payload["secretkey"]
        return httpx.Response(
            200,
            json={"approval_key": "approval-test"},
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        key = issue_ws_approval_key(
            _settings(),
            http_client=client,
        )

    assert key == "approval-test"
    assert seen == {
        "path": "/oauth2/Approval",
        "grant_type": "client_credentials",
        "appkey": "app-key",
        "secretkey": "app-secret",
    }


def test_ws_urls_and_subscription_contract():
    assert websocket_url("real") == "ws://ops.koreainvestment.com:21000"
    assert websocket_url("virtual") == "ws://ops.koreainvestment.com:31000"

    message = build_realtime_price_subscription(
        "approval-test",
        "005930",
    )
    assert message["header"]["approval_key"] == "approval-test"
    assert message["header"]["tr_type"] == "1"
    assert message["body"]["input"] == {
        "tr_id": "H0STCNT0",
        "tr_key": "005930",
    }

    unsubscribe = build_realtime_price_subscription(
        "approval-test",
        "005930",
        subscribe=False,
    )
    assert unsubscribe["header"]["tr_type"] == "2"


def test_parse_subscription_ack_and_pingpong():
    ack = parse_system_message(
        json.dumps(
            {
                "header": {
                    "tr_id": "H0STCNT0",
                    "tr_key": "005930",
                },
                "body": {
                    "rt_cd": "0",
                    "msg1": "SUBSCRIBE SUCCESS",
                },
            }
        )
    )
    assert ack.ok is True
    assert ack.tr_id == "H0STCNT0"
    assert ack.tr_key == "005930"
    assert ack.is_pingpong is False

    ping = parse_system_message(
        json.dumps(
            {
                "header": {"tr_id": "PINGPONG"},
            }
        )
    )
    assert ping.is_pingpong is True
    assert ping.ok is None


def test_parse_realtime_tick():
    message = "0|H0STCNT0|1|" + _tick_payload()
    ticks = parse_realtime_price_message(message)

    assert len(ticks) == 1
    tick = ticks[0]
    assert tick.ticker == "005930"
    assert tick.business_date == "20260922"
    assert tick.trade_time == "151501"
    assert str(tick.current_price) == "277500"
    assert str(tick.change_amount) == "3500"
    assert str(tick.change_rate) == "1.28"
    assert str(tick.open_price) == "283000"
    assert str(tick.high_price) == "283500"
    assert str(tick.low_price) == "271500"
    assert str(tick.trade_volume) == "10"
    assert str(tick.accumulated_volume) == "18157410"


@pytest.mark.parametrize(
    ("bad_price", "expected"),
    [
        ("", "missing"),
        ("bad", "not a valid number"),
        ("0", "greater than zero"),
        ("-1", "greater than zero"),
    ],
)
def test_bad_current_price_never_becomes_zero(bad_price, expected):
    message = (
        "0|H0STCNT0|1|"
        + _tick_payload(current_price=bad_price)
    )

    with pytest.raises(KisWebSocketError) as exc_info:
        parse_realtime_price_message(message)

    assert expected in str(exc_info.value)


def test_realtime_parser_rejects_wrong_shape():
    with pytest.raises(KisWebSocketError):
        parse_realtime_price_message("0|H0STCNT0|1|too^short")

    with pytest.raises(KisWebSocketError):
        build_realtime_price_subscription(
            "approval-test",
            "5930",
        )
