from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path.cwd()
WS = ROOT / "backend" / "app" / "integrations" / "kis" / "websocket_client.py"
TEST = ROOT / "backend" / "tests" / "test_kis_websocket.py"

WS_CONTENT = 'from __future__ import annotations\n\nimport asyncio\nimport json\nfrom dataclasses import dataclass\nfrom decimal import Decimal, InvalidOperation\nfrom typing import Any\n\nimport httpx\n\nfrom app.core.config import Settings, get_settings\n\nfrom .client import base_url, normalize_environment, validate_settings\n\n\n_APPROVAL_PATH = "/oauth2/Approval"\n_REAL_WS_URL = "ws://ops.koreainvestment.com:21000"\n_VIRTUAL_WS_URL = "ws://ops.koreainvestment.com:31000"\n_REALTIME_PRICE_TR_ID = "H0STCNT0"\n_REALTIME_PRICE_FIELD_COUNT = 46\n\n\nclass KisWebSocketError(RuntimeError):\n    def __init__(\n        self,\n        message: str,\n        *,\n        status_code: int | None = None,\n        code: str | None = None,\n    ) -> None:\n        super().__init__(message)\n        self.status_code = status_code\n        self.code = code\n\n\n@dataclass(frozen=True, slots=True)\nclass KisRealtimePrice:\n    ticker: str\n    business_date: str\n    trade_time: str\n    current_price: Decimal\n    change_amount: Decimal\n    change_rate: Decimal\n    change_sign: str | None\n    open_price: Decimal\n    high_price: Decimal\n    low_price: Decimal\n    trade_volume: Decimal\n    accumulated_volume: Decimal\n\n\n@dataclass(frozen=True, slots=True)\nclass KisRealtimeSystemMessage:\n    tr_id: str\n    tr_key: str | None\n    ok: bool | None\n    message: str | None\n    is_pingpong: bool\n\n\n@dataclass(frozen=True, slots=True)\nclass KisRealtimeSmokeResult:\n    connected: bool\n    subscribed: bool\n    ticks: tuple[KisRealtimePrice, ...]\n    pingpong_count: int\n\n\ndef websocket_url(environment: str | None) -> str:\n    return (\n        _REAL_WS_URL\n        if normalize_environment(environment) == "real"\n        else _VIRTUAL_WS_URL\n    )\n\n\ndef _strict_decimal(\n    raw: Any,\n    field_name: str,\n    *,\n    positive: bool = False,\n    non_negative: bool = False,\n) -> Decimal:\n    if raw is None or str(raw).strip() == "":\n        raise KisWebSocketError(\n            f"KIS realtime field {field_name} is missing."\n        )\n    try:\n        value = Decimal(str(raw).strip())\n    except (InvalidOperation, ValueError, TypeError) as exc:\n        raise KisWebSocketError(\n            f"KIS realtime field {field_name} is not a valid number."\n        ) from exc\n\n    if not value.is_finite():\n        raise KisWebSocketError(\n            f"KIS realtime field {field_name} is not finite."\n        )\n    if positive and value <= 0:\n        raise KisWebSocketError(\n            f"KIS realtime field {field_name} must be greater than zero."\n        )\n    if non_negative and value < 0:\n        raise KisWebSocketError(\n            f"KIS realtime field {field_name} must not be negative."\n        )\n    return value\n\n\ndef _normalize_ticker(ticker: str) -> str:\n    value = (ticker or "").strip()\n    if len(value) != 6 or not value.isdigit():\n        raise KisWebSocketError(\n            "Domestic stock ticker must be exactly 6 digits."\n        )\n    return value\n\n\ndef issue_ws_approval_key(\n    settings: Settings | None = None,\n    *,\n    timeout_seconds: float = 15.0,\n    http_client: httpx.Client | None = None,\n) -> str:\n    settings = validate_settings(settings or get_settings())\n\n    payload = {\n        "grant_type": "client_credentials",\n        "appkey": settings.kis_app_key,\n        "secretkey": settings.kis_app_secret,\n    }\n\n    owns_client = http_client is None\n    client = http_client or httpx.Client(timeout=timeout_seconds)\n    try:\n        try:\n            response = client.post(\n                f"{base_url(settings.kis_env)}{_APPROVAL_PATH}",\n                headers={"content-type": "application/json"},\n                json=payload,\n                timeout=timeout_seconds,\n            )\n        except httpx.HTTPError as exc:\n            raise KisWebSocketError(\n                f"KIS WebSocket approval request failed before response: {exc}"\n            ) from exc\n\n        if response.status_code != 200:\n            raise KisWebSocketError(\n                "KIS WebSocket approval request returned a non-200 response.",\n                status_code=response.status_code,\n            )\n\n        try:\n            body = response.json()\n        except ValueError as exc:\n            raise KisWebSocketError(\n                "KIS WebSocket approval response was not valid JSON.",\n                status_code=response.status_code,\n            ) from exc\n\n        if not isinstance(body, dict):\n            raise KisWebSocketError(\n                "KIS WebSocket approval response had an unexpected shape."\n            )\n\n        approval_key = str(body.get("approval_key") or "").strip()\n        if not approval_key:\n            safe_message = str(\n                body.get("error_description")\n                or body.get("msg1")\n                or "approval_key was missing."\n            )\n            raise KisWebSocketError(\n                f"KIS WebSocket approval failed: {safe_message}",\n                status_code=response.status_code,\n                code=str(body.get("msg_cd") or "") or None,\n            )\n\n        return approval_key\n    finally:\n        if owns_client:\n            client.close()\n\n\ndef build_realtime_price_subscription(\n    approval_key: str,\n    ticker: str,\n    *,\n    subscribe: bool = True,\n) -> dict[str, Any]:\n    key = (approval_key or "").strip()\n    if not key:\n        raise KisWebSocketError("WebSocket approval_key is required.")\n\n    normalized_ticker = _normalize_ticker(ticker)\n    return {\n        "header": {\n            "approval_key": key,\n            "custtype": "P",\n            "tr_type": "1" if subscribe else "2",\n            "content-type": "utf-8",\n        },\n        "body": {\n            "input": {\n                "tr_id": _REALTIME_PRICE_TR_ID,\n                "tr_key": normalized_ticker,\n            }\n        },\n    }\n\n\ndef parse_system_message(data: str) -> KisRealtimeSystemMessage:\n    try:\n        body = json.loads(data)\n    except json.JSONDecodeError as exc:\n        raise KisWebSocketError(\n            "KIS WebSocket system message was not valid JSON."\n        ) from exc\n\n    if not isinstance(body, dict):\n        raise KisWebSocketError(\n            "KIS WebSocket system message had an unexpected shape."\n        )\n\n    header = body.get("header")\n    if not isinstance(header, dict):\n        raise KisWebSocketError(\n            "KIS WebSocket system message is missing header."\n        )\n\n    tr_id = str(header.get("tr_id") or "").strip()\n    if not tr_id:\n        raise KisWebSocketError(\n            "KIS WebSocket system message is missing tr_id."\n        )\n\n    if tr_id == "PINGPONG":\n        return KisRealtimeSystemMessage(\n            tr_id=tr_id,\n            tr_key=None,\n            ok=None,\n            message=None,\n            is_pingpong=True,\n        )\n\n    message_body = body.get("body")\n    if not isinstance(message_body, dict):\n        raise KisWebSocketError(\n            "KIS WebSocket subscription response is missing body."\n        )\n\n    rt_cd = str(message_body.get("rt_cd") or "")\n    return KisRealtimeSystemMessage(\n        tr_id=tr_id,\n        tr_key=str(header.get("tr_key") or "").strip() or None,\n        ok=rt_cd == "0",\n        message=str(message_body.get("msg1") or "").strip() or None,\n        is_pingpong=False,\n    )\n\n\ndef parse_realtime_price_message(data: str) -> tuple[KisRealtimePrice, ...]:\n    parts = data.split("|", 3)\n    if len(parts) != 4:\n        raise KisWebSocketError(\n            "KIS realtime price message had an unexpected envelope."\n        )\n\n    encrypted_flag, tr_id, count_raw, payload = parts\n    if encrypted_flag != "0":\n        raise KisWebSocketError(\n            "KIS realtime market-price message was unexpectedly encrypted."\n        )\n    if tr_id != _REALTIME_PRICE_TR_ID:\n        raise KisWebSocketError(\n            f"Unexpected realtime TR ID: {tr_id or \'<empty>\'}"\n        )\n\n    try:\n        count = int(count_raw)\n    except ValueError as exc:\n        raise KisWebSocketError(\n            "KIS realtime price message count was invalid."\n        ) from exc\n\n    if count <= 0:\n        raise KisWebSocketError(\n            "KIS realtime price message count must be positive."\n        )\n\n    values = payload.split("^")\n    expected = count * _REALTIME_PRICE_FIELD_COUNT\n    if len(values) < expected:\n        raise KisWebSocketError(\n            "KIS realtime price payload had fewer fields than expected."\n        )\n\n    result: list[KisRealtimePrice] = []\n    for index in range(count):\n        row = values[\n            index * _REALTIME_PRICE_FIELD_COUNT:\n            (index + 1) * _REALTIME_PRICE_FIELD_COUNT\n        ]\n        ticker = _normalize_ticker(row[0])\n        trade_time = row[1].strip()\n        business_date = row[33].strip()\n\n        if len(trade_time) != 6 or not trade_time.isdigit():\n            raise KisWebSocketError(\n                "KIS realtime trade time must be HHMMSS."\n            )\n        if (\n            business_date\n            and (len(business_date) != 8 or not business_date.isdigit())\n        ):\n            raise KisWebSocketError(\n                "KIS realtime business date must be YYYYMMDD."\n            )\n\n        result.append(\n            KisRealtimePrice(\n                ticker=ticker,\n                business_date=business_date,\n                trade_time=trade_time,\n                current_price=_strict_decimal(\n                    row[2], "STCK_PRPR", positive=True\n                ),\n                change_sign=row[3].strip() or None,\n                change_amount=_strict_decimal(row[4], "PRDY_VRSS"),\n                change_rate=_strict_decimal(row[5], "PRDY_CTRT"),\n                open_price=_strict_decimal(\n                    row[7], "STCK_OPRC", non_negative=True\n                ),\n                high_price=_strict_decimal(\n                    row[8], "STCK_HGPR", non_negative=True\n                ),\n                low_price=_strict_decimal(\n                    row[9], "STCK_LWPR", non_negative=True\n                ),\n                trade_volume=_strict_decimal(\n                    row[12], "CNTG_VOL", non_negative=True\n                ),\n                accumulated_volume=_strict_decimal(\n                    row[13], "ACML_VOL", non_negative=True\n                ),\n            )\n        )\n\n    return tuple(result)\n\n\nasync def smoke_realtime_price(\n    ticker: str,\n    settings: Settings | None = None,\n    *,\n    wait_seconds: float = 8.0,\n    max_ticks: int = 3,\n) -> KisRealtimeSmokeResult:\n    if max_ticks <= 0:\n        raise ValueError("max_ticks must be positive.")\n    if wait_seconds <= 0:\n        raise ValueError("wait_seconds must be positive.")\n\n    settings = validate_settings(settings or get_settings())\n    normalized_ticker = _normalize_ticker(ticker)\n    approval_key = issue_ws_approval_key(settings)\n\n    try:\n        import websockets\n    except ImportError as exc:\n        raise KisWebSocketError(\n            "Python package \'websockets\' is required for KIS realtime smoke."\n        ) from exc\n\n    subscribe_message = build_realtime_price_subscription(\n        approval_key,\n        normalized_ticker,\n        subscribe=True,\n    )\n    unsubscribe_message = build_realtime_price_subscription(\n        approval_key,\n        normalized_ticker,\n        subscribe=False,\n    )\n\n    ticks: list[KisRealtimePrice] = []\n    pingpong_count = 0\n    subscribed = False\n\n    async with websockets.connect(\n        websocket_url(settings.kis_env),\n        ping_interval=None,\n        close_timeout=3,\n    ) as websocket:\n        await websocket.send(\n            json.dumps(\n                subscribe_message,\n                ensure_ascii=False,\n                separators=(",", ":"),\n            )\n        )\n\n        loop = asyncio.get_running_loop()\n        deadline = loop.time() + wait_seconds\n\n        while loop.time() < deadline and len(ticks) < max_ticks:\n            remaining = deadline - loop.time()\n            try:\n                raw = await asyncio.wait_for(\n                    websocket.recv(),\n                    timeout=max(0.1, remaining),\n                )\n            except asyncio.TimeoutError:\n                break\n\n            if isinstance(raw, bytes):\n                raw = raw.decode("utf-8")\n\n            if raw.startswith("0|"):\n                for tick in parse_realtime_price_message(raw):\n                    if tick.ticker == normalized_ticker:\n                        ticks.append(tick)\n                        if len(ticks) >= max_ticks:\n                            break\n                continue\n\n            if raw.startswith("1|"):\n                # Encrypted account/order notices are outside KIS.2 scope.\n                continue\n\n            system = parse_system_message(raw)\n            if system.is_pingpong:\n                pingpong_count += 1\n                # KIS official samples echo the PINGPONG payload.\n                await websocket.send(raw)\n                continue\n\n            if system.tr_id == _REALTIME_PRICE_TR_ID:\n                if system.ok is False:\n                    raise KisWebSocketError(\n                        system.message or "KIS realtime subscription failed."\n                    )\n                if system.ok is True:\n                    subscribed = True\n\n        try:\n            await websocket.send(\n                json.dumps(\n                    unsubscribe_message,\n                    ensure_ascii=False,\n                    separators=(",", ":"),\n                )\n            )\n        except Exception:\n            # Connection is about to close anyway; smoke result is already known.\n            pass\n\n    return KisRealtimeSmokeResult(\n        connected=True,\n        subscribed=subscribed,\n        ticks=tuple(ticks),\n        pingpong_count=pingpong_count,\n    )\n'
TEST_CONTENT = 'from __future__ import annotations\n\nimport json\n\nimport httpx\nimport pytest\n\nfrom app.core.config import Settings\nfrom app.integrations.kis.websocket_client import (\n    KisWebSocketError,\n    build_realtime_price_subscription,\n    issue_ws_approval_key,\n    parse_realtime_price_message,\n    parse_system_message,\n    websocket_url,\n)\n\n\ndef _settings(**overrides) -> Settings:\n    values = {\n        "kis_app_key": "app-key",\n        "kis_app_secret": "app-secret",\n        "kis_account_no": "12345678",\n        "kis_account_product_code": "01",\n        "kis_env": "real",\n    }\n    values.update(overrides)\n    return Settings(_env_file=None, **values)\n\n\ndef _tick_payload(\n    *,\n    ticker: str = "005930",\n    current_price: str = "277500",\n) -> str:\n    fields = [\n        ticker,\n        "151501",\n        current_price,\n        "2",\n        "3500",\n        "1.28",\n        "275000",\n        "283000",\n        "283500",\n        "271500",\n        "277500",\n        "277000",\n        "10",\n        "18157410",\n        "5000000000",\n        "100",\n        "120",\n        "20",\n        "103.1",\n        "1000",\n        "1200",\n        "1",\n        "52.0",\n        "110.0",\n        "090001",\n        "2",\n        "9000",\n        "090100",\n        "2",\n        "9500",\n        "090200",\n        "5",\n        "2500",\n        "20260922",\n        "0",\n        "N",\n        "100",\n        "200",\n        "10000",\n        "12000",\n        "2.1",\n        "17000000",\n        "106.0",\n        "0",\n        "0",\n        "276000",\n    ]\n    assert len(fields) == 46\n    return "^".join(fields)\n\n\ndef test_ws_approval_contract():\n    seen = {}\n\n    def handler(request: httpx.Request) -> httpx.Response:\n        seen["path"] = request.url.path\n        payload = json.loads(request.content.decode("utf-8"))\n        seen["grant_type"] = payload["grant_type"]\n        seen["appkey"] = payload["appkey"]\n        seen["secretkey"] = payload["secretkey"]\n        return httpx.Response(\n            200,\n            json={"approval_key": "approval-test"},\n        )\n\n    with httpx.Client(transport=httpx.MockTransport(handler)) as client:\n        key = issue_ws_approval_key(\n            _settings(),\n            http_client=client,\n        )\n\n    assert key == "approval-test"\n    assert seen == {\n        "path": "/oauth2/Approval",\n        "grant_type": "client_credentials",\n        "appkey": "app-key",\n        "secretkey": "app-secret",\n    }\n\n\ndef test_ws_urls_and_subscription_contract():\n    assert websocket_url("real") == "ws://ops.koreainvestment.com:21000"\n    assert websocket_url("virtual") == "ws://ops.koreainvestment.com:31000"\n\n    message = build_realtime_price_subscription(\n        "approval-test",\n        "005930",\n    )\n    assert message["header"]["approval_key"] == "approval-test"\n    assert message["header"]["tr_type"] == "1"\n    assert message["body"]["input"] == {\n        "tr_id": "H0STCNT0",\n        "tr_key": "005930",\n    }\n\n    unsubscribe = build_realtime_price_subscription(\n        "approval-test",\n        "005930",\n        subscribe=False,\n    )\n    assert unsubscribe["header"]["tr_type"] == "2"\n\n\ndef test_parse_subscription_ack_and_pingpong():\n    ack = parse_system_message(\n        json.dumps(\n            {\n                "header": {\n                    "tr_id": "H0STCNT0",\n                    "tr_key": "005930",\n                },\n                "body": {\n                    "rt_cd": "0",\n                    "msg1": "SUBSCRIBE SUCCESS",\n                },\n            }\n        )\n    )\n    assert ack.ok is True\n    assert ack.tr_id == "H0STCNT0"\n    assert ack.tr_key == "005930"\n    assert ack.is_pingpong is False\n\n    ping = parse_system_message(\n        json.dumps(\n            {\n                "header": {"tr_id": "PINGPONG"},\n            }\n        )\n    )\n    assert ping.is_pingpong is True\n    assert ping.ok is None\n\n\ndef test_parse_realtime_tick():\n    message = "0|H0STCNT0|1|" + _tick_payload()\n    ticks = parse_realtime_price_message(message)\n\n    assert len(ticks) == 1\n    tick = ticks[0]\n    assert tick.ticker == "005930"\n    assert tick.business_date == "20260922"\n    assert tick.trade_time == "151501"\n    assert str(tick.current_price) == "277500"\n    assert str(tick.change_amount) == "3500"\n    assert str(tick.change_rate) == "1.28"\n    assert str(tick.open_price) == "283000"\n    assert str(tick.high_price) == "283500"\n    assert str(tick.low_price) == "271500"\n    assert str(tick.trade_volume) == "10"\n    assert str(tick.accumulated_volume) == "18157410"\n\n\n@pytest.mark.parametrize(\n    ("bad_price", "expected"),\n    [\n        ("", "missing"),\n        ("bad", "not a valid number"),\n        ("0", "greater than zero"),\n        ("-1", "greater than zero"),\n    ],\n)\ndef test_bad_current_price_never_becomes_zero(bad_price, expected):\n    message = (\n        "0|H0STCNT0|1|"\n        + _tick_payload(current_price=bad_price)\n    )\n\n    with pytest.raises(KisWebSocketError) as exc_info:\n        parse_realtime_price_message(message)\n\n    assert expected in str(exc_info.value)\n\n\ndef test_realtime_parser_rejects_wrong_shape():\n    with pytest.raises(KisWebSocketError):\n        parse_realtime_price_message("0|H0STCNT0|1|too^short")\n\n    with pytest.raises(KisWebSocketError):\n        build_realtime_price_subscription(\n            "approval-test",\n            "5930",\n        )\n'
SMOKE_CODE = 'import asyncio\nimport sys\nsys.path.insert(0, "backend")\n\nfrom app.core.config import get_settings\nfrom app.integrations.kis.websocket_client import smoke_realtime_price\n\nasync def main():\n    settings = get_settings()\n    result = await smoke_realtime_price(\n        "005930",\n        settings,\n        wait_seconds=8.0,\n        max_ticks=3,\n    )\n\n    print("KIS WS: CONNECTED")\n    print("ENV:", settings.kis_env)\n    print("SUBSCRIBED:", result.subscribed)\n    print("TICKER: 005930")\n    print("TICKS:", len(result.ticks))\n\n    for index, tick in enumerate(result.ticks, start=1):\n        print(\n            f"PRICE {index}:"\n            f" {tick.ticker}"\n            f" | DATE={tick.business_date or \'-\'}"\n            f" | TIME={tick.trade_time}"\n            f" | PRICE={tick.current_price}"\n            f" | CHANGE={tick.change_amount}"\n            f" | RATE={tick.change_rate}%"\n            f" | VOLUME={tick.trade_volume}"\n        )\n\n    print("PINGPONG:", result.pingpong_count)\n    print("APPROVAL_KEY_PRINTED: NO")\n    print("APP_KEY_PRINTED: NO")\n    print("APP_SECRET_PRINTED: NO")\n    print("ACCOUNT_NO_PRINTED: NO")\n    print("ORDER_API_CALLED: NO")\n\n    if not result.subscribed:\n        raise SystemExit("KIS WebSocket connected but subscription ACK was not confirmed.")\n\n    if result.ticks:\n        print("KIS.2 LIVE TICK UAT: PASS")\n    else:\n        print("KIS.2 LIVE TICK UAT: PENDING (no trade tick during smoke window)")\n        print("KIS.2 CONNECTION/SUBSCRIPTION: PASS")\n\nasyncio.run(main())\n'


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
    print("KIS.2 WebSocket realtime-price bootstrap")
    print("TARGET: 005930 / H0STCNT0")
    print("Order API called: NO")
    print("Scanner/Strategy/Risk modified: NO")

    required = [
        ROOT / "backend" / "app" / "integrations" / "kis" / "client.py",
        ROOT / "backend" / "app" / "integrations" / "kis" / "quote.py",
        ROOT / "backend" / "tests" / "test_kis_client.py",
        ROOT / "backend" / "tests" / "test_kis_account.py",
        ROOT / "backend" / "tests" / "test_kis_quote.py",
    ]
    for path in required:
        if not path.is_file():
            fail(f"Required KIS file is missing: {path}")

    if WS.exists():
        fail(f"Target already exists: {WS}")
    if TEST.exists():
        fail(f"Target already exists: {TEST}")

    compile(WS_CONTENT, str(WS), "exec")
    compile(TEST_CONTENT, str(TEST), "exec")

    created = []
    tests_passed = False
    try:
        WS.write_text(WS_CONTENT, encoding="utf-8", newline="\n")
        created.append(WS)
        TEST.write_text(TEST_CONTENT, encoding="utf-8", newline="\n")
        created.append(TEST)

        venv_python = ROOT / ".venv" / "Scripts" / "python.exe"
        python_exe = str(
            venv_python if venv_python.is_file() else Path(sys.executable)
        )

        run(
            [python_exe, "-c", "import websockets; print('websockets:', websockets.__version__)"],
            "WebSocket dependency check",
        )

        run(
            [
                python_exe,
                "-m",
                "pytest",
                "backend/tests/test_kis_client.py",
                "backend/tests/test_kis_account.py",
                "backend/tests/test_kis_quote.py",
                "backend/tests/test_kis_websocket.py",
                "-q",
            ],
            "KIS.2 targeted regression",
        )
        tests_passed = True

        print()
        print("=== KIS.2 REAL WEBSOCKET SMOKE ===")
        print("Read-only realtime market-data connection; waits up to 8 seconds.")
        result = subprocess.run(
            [python_exe, "-c", SMOKE_CODE],
            cwd=ROOT,
        )
        if result.returncode != 0:
            print()
            print("KIS.2 LIVE SMOKE FAILED")
            print("Unit/regression tests passed, so source files are kept for diagnosis.")
            print("No order API was called.")
            return result.returncode

        print()
        print("KIS.2 APPLY COMPLETE")
        print("Added:")
        print(" - backend/app/integrations/kis/websocket_client.py")
        print(" - backend/tests/test_kis_websocket.py")
        print("Auth/account/quote regression: PASS")
        print("WebSocket connection/subscription smoke: PASS")
        print("If TICKS=0, live trade-tick UAT remains pending until market activity.")
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
            print("FAILED — KIS.2 additions were restored because local tests failed.")
        raise


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print()
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
