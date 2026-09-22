from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path.cwd()
KIS_DIR = ROOT / "backend" / "app" / "integrations" / "kis"
CLIENT = KIS_DIR / "client.py"
INIT = KIS_DIR / "__init__.py"
TOKEN_CACHE = KIS_DIR / "token_cache.py"
ACCOUNT = KIS_DIR / "account.py"
TEST = ROOT / "backend" / "tests" / "test_kis_account.py"

TOKEN_CACHE_CONTENT = r"""from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

from app.core.config import PROJECT_ROOT, Settings, get_settings

from .client import KisAccessToken, issue_access_token, normalize_environment, validate_settings


_CACHE_PATH = PROJECT_ROOT / "backend" / "runtime" / "kis" / "access_token.json"
_REFRESH_MARGIN_SECONDS = 300


def _credential_fingerprint(settings: Settings) -> str:
    raw = f"{normalize_environment(settings.kis_env)}:{settings.kis_app_key or ''}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _load_cached(settings: Settings) -> KisAccessToken | None:
    try:
        data = json.loads(_CACHE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return None

    if data.get("credential_fingerprint") != _credential_fingerprint(settings):
        return None

    try:
        usable_until = float(data.get("usable_until_epoch") or 0)
    except (TypeError, ValueError):
        return None

    if usable_until <= time.time():
        return None

    token = str(data.get("access_token") or "")
    if not token:
        return None

    expires_in_raw = data.get("expires_in")
    try:
        expires_in = int(expires_in_raw) if expires_in_raw is not None else None
    except (TypeError, ValueError):
        expires_in = None

    return KisAccessToken(
        access_token=token,
        token_type=str(data.get("token_type")) if data.get("token_type") else None,
        expires_in=expires_in,
        expires_at=str(data.get("expires_at")) if data.get("expires_at") else None,
    )


def _save_cached(settings: Settings, token: KisAccessToken) -> None:
    _CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    lifetime = token.expires_in if token.expires_in and token.expires_in > 0 else 86400
    usable_until = time.time() + max(60, lifetime - _REFRESH_MARGIN_SECONDS)

    payload = {
        "credential_fingerprint": _credential_fingerprint(settings),
        "access_token": token.access_token,
        "token_type": token.token_type,
        "expires_in": token.expires_in,
        "expires_at": token.expires_at,
        "usable_until_epoch": usable_until,
    }
    _CACHE_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def get_access_token(settings: Settings | None = None) -> KisAccessToken:
    settings = validate_settings(settings or get_settings())

    cached = _load_cached(settings)
    if cached is not None:
        return cached

    token = issue_access_token(settings)
    _save_cached(settings, token)
    return token
"""

ACCOUNT_CONTENT = r"""from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import time
from typing import Any

import httpx

from app.core.config import Settings, get_settings

from .client import (
    KisConfigurationError,
    base_url,
    normalize_environment,
    validate_account_settings,
)
from .token_cache import get_access_token


_BALANCE_PATH = "/uapi/domestic-stock/v1/trading/inquire-balance"


class KisAccountError(RuntimeError):
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
class KisHolding:
    ticker: str
    name: str
    quantity: Decimal
    orderable_quantity: Decimal
    average_price: Decimal
    purchase_amount: Decimal
    current_price: Decimal
    evaluation_amount: Decimal
    pnl_amount: Decimal
    pnl_rate: Decimal

    def to_dict(self) -> dict[str, str]:
        return {
            "ticker": self.ticker,
            "name": self.name,
            "quantity": _decimal_text(self.quantity),
            "orderable_quantity": _decimal_text(self.orderable_quantity),
            "average_price": _decimal_text(self.average_price),
            "purchase_amount": _decimal_text(self.purchase_amount),
            "current_price": _decimal_text(self.current_price),
            "evaluation_amount": _decimal_text(self.evaluation_amount),
            "pnl_amount": _decimal_text(self.pnl_amount),
            "pnl_rate": _decimal_text(self.pnl_rate),
        }


@dataclass(frozen=True, slots=True)
class KisBalanceSummary:
    deposit_amount: Decimal
    securities_evaluation_amount: Decimal
    total_evaluation_amount: Decimal
    net_asset_amount: Decimal
    purchase_amount_total: Decimal
    evaluation_amount_total: Decimal
    pnl_amount_total: Decimal

    def to_dict(self) -> dict[str, str]:
        return {
            "deposit_amount": _decimal_text(self.deposit_amount),
            "securities_evaluation_amount": _decimal_text(
                self.securities_evaluation_amount
            ),
            "total_evaluation_amount": _decimal_text(self.total_evaluation_amount),
            "net_asset_amount": _decimal_text(self.net_asset_amount),
            "purchase_amount_total": _decimal_text(self.purchase_amount_total),
            "evaluation_amount_total": _decimal_text(self.evaluation_amount_total),
            "pnl_amount_total": _decimal_text(self.pnl_amount_total),
        }


@dataclass(frozen=True, slots=True)
class KisDomesticBalance:
    holdings: tuple[KisHolding, ...]
    summary: KisBalanceSummary | None


def _dec(value: Any) -> Decimal:
    if value in (None, ""):
        return Decimal("0")
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return Decimal("0")


def _decimal_text(value: Decimal) -> str:
    text = format(value, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def _holding_from_row(row: dict[str, Any]) -> KisHolding:
    return KisHolding(
        ticker=str(row.get("pdno") or "").strip(),
        name=str(row.get("prdt_name") or "").strip(),
        quantity=_dec(row.get("hldg_qty")),
        orderable_quantity=_dec(row.get("ord_psbl_qty")),
        average_price=_dec(row.get("pchs_avg_pric")),
        purchase_amount=_dec(row.get("pchs_amt")),
        current_price=_dec(row.get("prpr")),
        evaluation_amount=_dec(row.get("evlu_amt")),
        pnl_amount=_dec(row.get("evlu_pfls_amt")),
        pnl_rate=_dec(row.get("evlu_pfls_rt") or row.get("evlu_erng_rt")),
    )


def _summary_from_row(row: dict[str, Any] | None) -> KisBalanceSummary | None:
    if not row:
        return None
    return KisBalanceSummary(
        deposit_amount=_dec(row.get("dnca_tot_amt")),
        securities_evaluation_amount=_dec(row.get("scts_evlu_amt")),
        total_evaluation_amount=_dec(row.get("tot_evlu_amt")),
        net_asset_amount=_dec(row.get("nass_amt")),
        purchase_amount_total=_dec(row.get("pchs_amt_smtl_amt")),
        evaluation_amount_total=_dec(row.get("evlu_amt_smtl_amt")),
        pnl_amount_total=_dec(row.get("evlu_pfls_smtl_amt")),
    )


def _tr_id(environment: str | None) -> str:
    return (
        "TTTC8434R"
        if normalize_environment(environment) == "real"
        else "VTTC8434R"
    )


def inquire_domestic_balance(
    settings: Settings | None = None,
    *,
    access_token: str | None = None,
    timeout_seconds: float = 15.0,
    include_zero_quantity: bool = False,
    http_client: httpx.Client | None = None,
) -> KisDomesticBalance:
    settings = validate_account_settings(settings or get_settings())

    token_value = access_token
    if token_value is None:
        token_value = get_access_token(settings).access_token

    headers = {
        "content-type": "application/json; charset=utf-8",
        "authorization": f"Bearer {token_value}",
        "appkey": settings.kis_app_key or "",
        "appsecret": settings.kis_app_secret or "",
        "tr_id": _tr_id(settings.kis_env),
        "custtype": "P",
        "tr_cont": "",
    }

    params = {
        "CANO": settings.kis_account_no or "",
        "ACNT_PRDT_CD": settings.kis_account_product_code,
        "AFHR_FLPR_YN": "N",
        "OFL_YN": "",
        "INQR_DVSN": "02",
        "UNPR_DVSN": "01",
        "FUND_STTL_ICLD_YN": "N",
        "FNCG_AMT_AUTO_RDPT_YN": "N",
        "PRCS_DVSN": "00",
        "CTX_AREA_FK100": "",
        "CTX_AREA_NK100": "",
    }

    owns_client = http_client is None
    client = http_client or httpx.Client(timeout=timeout_seconds)
    holdings: list[KisHolding] = []
    summary: KisBalanceSummary | None = None
    depth = 0

    try:
        while True:
            try:
                response = client.get(
                    f"{base_url(settings.kis_env)}{_BALANCE_PATH}",
                    headers=headers,
                    params=params,
                    timeout=timeout_seconds,
                )
            except httpx.HTTPError as exc:
                raise KisAccountError(
                    f"KIS balance request failed before receiving a response: {exc}"
                ) from exc

            if response.status_code != 200:
                raise KisAccountError(
                    "KIS balance request returned a non-200 response.",
                    status_code=response.status_code,
                )

            try:
                body = response.json()
            except ValueError as exc:
                raise KisAccountError(
                    "KIS balance response was not valid JSON.",
                    status_code=response.status_code,
                ) from exc

            if str(body.get("rt_cd") or "") != "0":
                raise KisAccountError(
                    str(body.get("msg1") or "KIS balance request failed."),
                    status_code=response.status_code,
                    code=str(body.get("msg_cd") or "") or None,
                )

            output1 = body.get("output1") or []
            if not isinstance(output1, list):
                raise KisAccountError("KIS balance output1 had an unexpected shape.")

            for raw in output1:
                if not isinstance(raw, dict):
                    continue
                item = _holding_from_row(raw)
                if not item.ticker:
                    continue
                if not include_zero_quantity and item.quantity <= 0:
                    continue
                holdings.append(item)

            output2 = body.get("output2") or []
            if summary is None and isinstance(output2, list) and output2:
                first_summary = output2[0]
                if isinstance(first_summary, dict):
                    summary = _summary_from_row(first_summary)

            tr_cont = (response.headers.get("tr_cont") or "").strip().upper()
            next_fk = str(body.get("ctx_area_fk100") or "")
            next_nk = str(body.get("ctx_area_nk100") or "")

            if tr_cont not in {"M", "F"} or not (next_fk or next_nk):
                break

            depth += 1
            if depth > 10:
                raise KisAccountError(
                    "KIS balance pagination exceeded the safety limit."
                )

            params["CTX_AREA_FK100"] = next_fk
            params["CTX_AREA_NK100"] = next_nk
            headers["tr_cont"] = "N"

            # KIS official samples also throttle continuation calls.
            time.sleep(
                0.6
                if normalize_environment(settings.kis_env) == "virtual"
                else 0.1
            )
    finally:
        if owns_client:
            client.close()

    return KisDomesticBalance(
        holdings=tuple(holdings),
        summary=summary,
    )
"""

TEST_CONTENT = r"""from __future__ import annotations

import httpx

from app.core.config import Settings
from app.integrations.kis.account import inquire_domestic_balance


def _settings() -> Settings:
    return Settings(
        _env_file=None,
        kis_app_key="app-key",
        kis_app_secret="app-secret",
        kis_account_no="12345678",
        kis_account_product_code="01",
        kis_env="real",
    )


def test_balance_request_and_parsing():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["authorization"] = request.headers.get("authorization")
        seen["tr_id"] = request.headers.get("tr_id")
        seen["cano"] = request.url.params.get("CANO")
        seen["product"] = request.url.params.get("ACNT_PRDT_CD")
        seen["inqr_dvsn"] = request.url.params.get("INQR_DVSN")
        return httpx.Response(
            200,
            headers={"tr_cont": ""},
            json={
                "rt_cd": "0",
                "msg_cd": "MCA00000",
                "msg1": "정상처리 되었습니다.",
                "output1": [
                    {
                        "pdno": "005930",
                        "prdt_name": "삼성전자",
                        "hldg_qty": "10",
                        "ord_psbl_qty": "10",
                        "pchs_avg_pric": "70000",
                        "pchs_amt": "700000",
                        "prpr": "80000",
                        "evlu_amt": "800000",
                        "evlu_pfls_amt": "100000",
                        "evlu_pfls_rt": "14.2857",
                    },
                    {
                        "pdno": "000660",
                        "prdt_name": "SK하이닉스",
                        "hldg_qty": "0",
                    },
                ],
                "output2": [
                    {
                        "dnca_tot_amt": "500000",
                        "scts_evlu_amt": "800000",
                        "tot_evlu_amt": "1300000",
                        "nass_amt": "1300000",
                        "pchs_amt_smtl_amt": "700000",
                        "evlu_amt_smtl_amt": "800000",
                        "evlu_pfls_smtl_amt": "100000",
                    }
                ],
                "ctx_area_fk100": "",
                "ctx_area_nk100": "",
            },
        )

    transport = httpx.MockTransport(handler)
    with httpx.Client(transport=transport) as client:
        result = inquire_domestic_balance(
            _settings(),
            access_token="test-token",
            http_client=client,
        )

    assert seen == {
        "authorization": "Bearer test-token",
        "tr_id": "TTTC8434R",
        "cano": "12345678",
        "product": "01",
        "inqr_dvsn": "02",
    }
    assert len(result.holdings) == 1
    holding = result.holdings[0]
    assert holding.ticker == "005930"
    assert holding.name == "삼성전자"
    assert str(holding.quantity) == "10"
    assert str(holding.average_price) == "70000"
    assert str(holding.current_price) == "80000"
    assert str(holding.pnl_amount) == "100000"
    assert result.summary is not None
    assert str(result.summary.total_evaluation_amount) == "1300000"


def test_virtual_balance_uses_virtual_tr_id():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["tr_id"] = request.headers.get("tr_id")
        return httpx.Response(
            200,
            json={
                "rt_cd": "0",
                "output1": [],
                "output2": [],
                "ctx_area_fk100": "",
                "ctx_area_nk100": "",
            },
        )

    settings = _settings()
    settings = Settings(
        _env_file=None,
        kis_app_key=settings.kis_app_key,
        kis_app_secret=settings.kis_app_secret,
        kis_account_no=settings.kis_account_no,
        kis_account_product_code=settings.kis_account_product_code,
        kis_env="virtual",
    )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        inquire_domestic_balance(
            settings,
            access_token="test-token",
            http_client=client,
        )

    assert seen["tr_id"] == "VTTC8434R"
"""


def fail(message: str) -> None:
    raise RuntimeError(message)


def patch_init(text: str) -> str:
    if "inquire_domestic_balance" in text:
        fail("__init__.py already exports KIS account functions.")

    addition = """
from .account import (
    KisAccountError,
    KisBalanceSummary,
    KisDomesticBalance,
    KisHolding,
    inquire_domestic_balance,
)
from .token_cache import get_access_token
"""

    if "__all__ = [" not in text:
        fail("KIS __init__.py __all__ anchor not found.")

    text = text.rstrip() + "\\n" + addition
    return text


def run(cmd: list[str], label: str) -> None:
    print()
    print(f"=== {label} ===")
    print(" ".join(cmd))
    result = subprocess.run(cmd, cwd=ROOT)
    if result.returncode != 0:
        fail(f"{label} failed with exit code {result.returncode}")


def main() -> int:
    print("PROJECT ROOT:", ROOT)
    print("KIS domestic balance bootstrap")
    print("Order API called: NO")

    if not CLIENT.is_file():
        fail("KIS client.py is missing. Run the auth bootstrap first.")
    if not INIT.is_file():
        fail("KIS __init__.py is missing. Run the auth bootstrap first.")
    for path in (TOKEN_CACHE, ACCOUNT, TEST):
        if path.exists():
            fail(f"Target already exists: {path}")

    init_before = INIT.read_text(encoding="utf-8-sig")
    init_after = patch_init(init_before)

    compile(TOKEN_CACHE_CONTENT, str(TOKEN_CACHE), "exec")
    compile(ACCOUNT_CONTENT, str(ACCOUNT), "exec")
    compile(TEST_CONTENT, str(TEST), "exec")
    compile(init_after, str(INIT), "exec")

    created: list[Path] = []
    try:
        TOKEN_CACHE.write_text(
            TOKEN_CACHE_CONTENT,
            encoding="utf-8",
            newline="\\n",
        )
        created.append(TOKEN_CACHE)

        ACCOUNT.write_text(
            ACCOUNT_CONTENT,
            encoding="utf-8",
            newline="\\n",
        )
        created.append(ACCOUNT)

        TEST.write_text(
            TEST_CONTENT,
            encoding="utf-8",
            newline="\\n",
        )
        created.append(TEST)

        INIT.write_text(init_after, encoding="utf-8", newline="\\n")

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
                "-q",
            ],
            "KIS auth + account regression",
        )

        smoke = r"""import sys
sys.path.insert(0, "backend")
from app.core.config import get_settings
from app.integrations.kis.account import inquire_domestic_balance

settings = get_settings()
balance = inquire_domestic_balance(settings)

print("KIS BALANCE: OK")
print("ENV:", settings.kis_env)
print("HOLDINGS:", len(balance.holdings))

for item in balance.holdings:
    print(
        f"- {item.ticker} {item.name}"
        f" | 수량={item.quantity}"
        f" | 평균단가={item.average_price}"
        f" | 현재가={item.current_price}"
        f" | 평가손익={item.pnl_amount}"
        f" | 수익률={item.pnl_rate}%"
    )

if balance.summary is not None:
    print("TOTAL_EVALUATION:", balance.summary.total_evaluation_amount)
    print("TOTAL_PNL:", balance.summary.pnl_amount_total)
    print("NET_ASSET:", balance.summary.net_asset_amount)

print("ACCOUNT_NO_PRINTED: NO")
print("APP_KEY_PRINTED: NO")
print("APP_SECRET_PRINTED: NO")
print("ORDER_API_CALLED: NO")
"""
        run(
            [python_exe, "-c", smoke],
            "KIS REAL BALANCE SMOKE",
        )

        print()
        print("KIS ACCOUNT READ COMPLETE")
        print("Modified:")
        print(" - backend/app/integrations/kis/__init__.py")
        print("Added:")
        print(" - backend/app/integrations/kis/token_cache.py")
        print(" - backend/app/integrations/kis/account.py")
        print(" - backend/tests/test_kis_account.py")
        print("Token cache:")
        print(" - backend/runtime/kis/access_token.json (gitignored)")
        print("Secrets printed: NO")
        print("Account number printed: NO")
        print("Order API called: NO")
        return 0

    except Exception:
        INIT.write_text(init_before, encoding="utf-8", newline="\\n")
        for path in reversed(created):
            if path.exists():
                path.unlink()
        print()
        print("FAILED — KIS account source changes were restored.")
        print(
            "Note: a runtime access-token cache may remain under "
            "backend/runtime/kis/; it is gitignored."
        )
        raise


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print()
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
