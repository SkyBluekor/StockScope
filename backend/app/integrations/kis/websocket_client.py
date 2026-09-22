from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx

from app.core.config import Settings, get_settings

from .client import base_url, normalize_environment, validate_settings


_APPROVAL_PATH = "/oauth2/Approval"
_REAL_WS_URL = "ws://ops.koreainvestment.com:21000"
_VIRTUAL_WS_URL = "ws://ops.koreainvestment.com:31000"
_REALTIME_PRICE_TR_ID = "H0STCNT0"
_REALTIME_PRICE_FIELD_COUNT = 46


class KisWebSocketError(RuntimeError):
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
class KisRealtimePrice:
    ticker: str
    business_date: str
    trade_time: str
    current_price: Decimal
    change_amount: Decimal
    change_rate: Decimal
    change_sign: str | None
    open_price: Decimal
    high_price: Decimal
    low_price: Decimal
    trade_volume: Decimal
    accumulated_volume: Decimal


@dataclass(frozen=True, slots=True)
class KisRealtimeSystemMessage:
    tr_id: str
    tr_key: str | None
    ok: bool | None
    message: str | None
    is_pingpong: bool


@dataclass(frozen=True, slots=True)
class KisRealtimeSmokeResult:
    connected: bool
    subscribed: bool
    ticks: tuple[KisRealtimePrice, ...]
    pingpong_count: int


def websocket_url(environment: str | None) -> str:
    return (
        _REAL_WS_URL
        if normalize_environment(environment) == "real"
        else _VIRTUAL_WS_URL
    )


def _strict_decimal(
    raw: Any,
    field_name: str,
    *,
    positive: bool = False,
    non_negative: bool = False,
) -> Decimal:
    if raw is None or str(raw).strip() == "":
        raise KisWebSocketError(
            f"KIS realtime field {field_name} is missing."
        )
    try:
        value = Decimal(str(raw).strip())
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise KisWebSocketError(
            f"KIS realtime field {field_name} is not a valid number."
        ) from exc

    if not value.is_finite():
        raise KisWebSocketError(
            f"KIS realtime field {field_name} is not finite."
        )
    if positive and value <= 0:
        raise KisWebSocketError(
            f"KIS realtime field {field_name} must be greater than zero."
        )
    if non_negative and value < 0:
        raise KisWebSocketError(
            f"KIS realtime field {field_name} must not be negative."
        )
    return value


def _normalize_ticker(ticker: str) -> str:
    value = (ticker or "").strip()
    if len(value) != 6 or not value.isdigit():
        raise KisWebSocketError(
            "Domestic stock ticker must be exactly 6 digits."
        )
    return value


def issue_ws_approval_key(
    settings: Settings | None = None,
    *,
    timeout_seconds: float = 15.0,
    http_client: httpx.Client | None = None,
) -> str:
    settings = validate_settings(settings or get_settings())

    payload = {
        "grant_type": "client_credentials",
        "appkey": settings.kis_app_key,
        "secretkey": settings.kis_app_secret,
    }

    owns_client = http_client is None
    client = http_client or httpx.Client(timeout=timeout_seconds)
    try:
        try:
            response = client.post(
                f"{base_url(settings.kis_env)}{_APPROVAL_PATH}",
                headers={"content-type": "application/json"},
                json=payload,
                timeout=timeout_seconds,
            )
        except httpx.HTTPError as exc:
            raise KisWebSocketError(
                f"KIS WebSocket approval request failed before response: {exc}"
            ) from exc

        if response.status_code != 200:
            raise KisWebSocketError(
                "KIS WebSocket approval request returned a non-200 response.",
                status_code=response.status_code,
            )

        try:
            body = response.json()
        except ValueError as exc:
            raise KisWebSocketError(
                "KIS WebSocket approval response was not valid JSON.",
                status_code=response.status_code,
            ) from exc

        if not isinstance(body, dict):
            raise KisWebSocketError(
                "KIS WebSocket approval response had an unexpected shape."
            )

        approval_key = str(body.get("approval_key") or "").strip()
        if not approval_key:
            safe_message = str(
                body.get("error_description")
                or body.get("msg1")
                or "approval_key was missing."
            )
            raise KisWebSocketError(
                f"KIS WebSocket approval failed: {safe_message}",
                status_code=response.status_code,
                code=str(body.get("msg_cd") or "") or None,
            )

        return approval_key
    finally:
        if owns_client:
            client.close()


def build_realtime_price_subscription(
    approval_key: str,
    ticker: str,
    *,
    subscribe: bool = True,
) -> dict[str, Any]:
    key = (approval_key or "").strip()
    if not key:
        raise KisWebSocketError("WebSocket approval_key is required.")

    normalized_ticker = _normalize_ticker(ticker)
    return {
        "header": {
            "approval_key": key,
            "custtype": "P",
            "tr_type": "1" if subscribe else "2",
            "content-type": "utf-8",
        },
        "body": {
            "input": {
                "tr_id": _REALTIME_PRICE_TR_ID,
                "tr_key": normalized_ticker,
            }
        },
    }


def parse_system_message(data: str) -> KisRealtimeSystemMessage:
    try:
        body = json.loads(data)
    except json.JSONDecodeError as exc:
        raise KisWebSocketError(
            "KIS WebSocket system message was not valid JSON."
        ) from exc

    if not isinstance(body, dict):
        raise KisWebSocketError(
            "KIS WebSocket system message had an unexpected shape."
        )

    header = body.get("header")
    if not isinstance(header, dict):
        raise KisWebSocketError(
            "KIS WebSocket system message is missing header."
        )

    tr_id = str(header.get("tr_id") or "").strip()
    if not tr_id:
        raise KisWebSocketError(
            "KIS WebSocket system message is missing tr_id."
        )

    if tr_id == "PINGPONG":
        return KisRealtimeSystemMessage(
            tr_id=tr_id,
            tr_key=None,
            ok=None,
            message=None,
            is_pingpong=True,
        )

    message_body = body.get("body")
    if not isinstance(message_body, dict):
        raise KisWebSocketError(
            "KIS WebSocket subscription response is missing body."
        )

    rt_cd = str(message_body.get("rt_cd") or "")
    return KisRealtimeSystemMessage(
        tr_id=tr_id,
        tr_key=str(header.get("tr_key") or "").strip() or None,
        ok=rt_cd == "0",
        message=str(message_body.get("msg1") or "").strip() or None,
        is_pingpong=False,
    )


def parse_realtime_price_message(data: str) -> tuple[KisRealtimePrice, ...]:
    parts = data.split("|", 3)
    if len(parts) != 4:
        raise KisWebSocketError(
            "KIS realtime price message had an unexpected envelope."
        )

    encrypted_flag, tr_id, count_raw, payload = parts
    if encrypted_flag != "0":
        raise KisWebSocketError(
            "KIS realtime market-price message was unexpectedly encrypted."
        )
    if tr_id != _REALTIME_PRICE_TR_ID:
        raise KisWebSocketError(
            f"Unexpected realtime TR ID: {tr_id or '<empty>'}"
        )

    try:
        count = int(count_raw)
    except ValueError as exc:
        raise KisWebSocketError(
            "KIS realtime price message count was invalid."
        ) from exc

    if count <= 0:
        raise KisWebSocketError(
            "KIS realtime price message count must be positive."
        )

    values = payload.split("^")
    expected = count * _REALTIME_PRICE_FIELD_COUNT
    if len(values) < expected:
        raise KisWebSocketError(
            "KIS realtime price payload had fewer fields than expected."
        )

    result: list[KisRealtimePrice] = []
    for index in range(count):
        row = values[
            index * _REALTIME_PRICE_FIELD_COUNT:
            (index + 1) * _REALTIME_PRICE_FIELD_COUNT
        ]
        ticker = _normalize_ticker(row[0])
        trade_time = row[1].strip()
        business_date = row[33].strip()

        if len(trade_time) != 6 or not trade_time.isdigit():
            raise KisWebSocketError(
                "KIS realtime trade time must be HHMMSS."
            )
        if (
            business_date
            and (len(business_date) != 8 or not business_date.isdigit())
        ):
            raise KisWebSocketError(
                "KIS realtime business date must be YYYYMMDD."
            )

        result.append(
            KisRealtimePrice(
                ticker=ticker,
                business_date=business_date,
                trade_time=trade_time,
                current_price=_strict_decimal(
                    row[2], "STCK_PRPR", positive=True
                ),
                change_sign=row[3].strip() or None,
                change_amount=_strict_decimal(row[4], "PRDY_VRSS"),
                change_rate=_strict_decimal(row[5], "PRDY_CTRT"),
                open_price=_strict_decimal(
                    row[7], "STCK_OPRC", non_negative=True
                ),
                high_price=_strict_decimal(
                    row[8], "STCK_HGPR", non_negative=True
                ),
                low_price=_strict_decimal(
                    row[9], "STCK_LWPR", non_negative=True
                ),
                trade_volume=_strict_decimal(
                    row[12], "CNTG_VOL", non_negative=True
                ),
                accumulated_volume=_strict_decimal(
                    row[13], "ACML_VOL", non_negative=True
                ),
            )
        )

    return tuple(result)


async def smoke_realtime_price(
    ticker: str,
    settings: Settings | None = None,
    *,
    wait_seconds: float = 8.0,
    max_ticks: int = 3,
) -> KisRealtimeSmokeResult:
    if max_ticks <= 0:
        raise ValueError("max_ticks must be positive.")
    if wait_seconds <= 0:
        raise ValueError("wait_seconds must be positive.")

    settings = validate_settings(settings or get_settings())
    normalized_ticker = _normalize_ticker(ticker)
    approval_key = issue_ws_approval_key(settings)

    try:
        import websockets
    except ImportError as exc:
        raise KisWebSocketError(
            "Python package 'websockets' is required for KIS realtime smoke."
        ) from exc

    subscribe_message = build_realtime_price_subscription(
        approval_key,
        normalized_ticker,
        subscribe=True,
    )
    unsubscribe_message = build_realtime_price_subscription(
        approval_key,
        normalized_ticker,
        subscribe=False,
    )

    ticks: list[KisRealtimePrice] = []
    pingpong_count = 0
    subscribed = False

    async with websockets.connect(
        websocket_url(settings.kis_env),
        ping_interval=None,
        close_timeout=3,
    ) as websocket:
        await websocket.send(
            json.dumps(
                subscribe_message,
                ensure_ascii=False,
                separators=(",", ":"),
            )
        )

        loop = asyncio.get_running_loop()
        deadline = loop.time() + wait_seconds

        while loop.time() < deadline and len(ticks) < max_ticks:
            remaining = deadline - loop.time()
            try:
                raw = await asyncio.wait_for(
                    websocket.recv(),
                    timeout=max(0.1, remaining),
                )
            except asyncio.TimeoutError:
                break

            if isinstance(raw, bytes):
                raw = raw.decode("utf-8")

            if raw.startswith("0|"):
                for tick in parse_realtime_price_message(raw):
                    if tick.ticker == normalized_ticker:
                        ticks.append(tick)
                        if len(ticks) >= max_ticks:
                            break
                continue

            if raw.startswith("1|"):
                # Encrypted account/order notices are outside KIS.2 scope.
                continue

            system = parse_system_message(raw)
            if system.is_pingpong:
                pingpong_count += 1
                # KIS official samples echo the PINGPONG payload.
                await websocket.send(raw)
                continue

            if system.tr_id == _REALTIME_PRICE_TR_ID:
                if system.ok is False:
                    raise KisWebSocketError(
                        system.message or "KIS realtime subscription failed."
                    )
                if system.ok is True:
                    subscribed = True

        try:
            await websocket.send(
                json.dumps(
                    unsubscribe_message,
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
            )
        except Exception:
            # Connection is about to close anyway; smoke result is already known.
            pass

    return KisRealtimeSmokeResult(
        connected=True,
        subscribed=subscribed,
        ticks=tuple(ticks),
        pingpong_count=pingpong_count,
    )
