from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path.cwd()
KIS_DIR = ROOT / "backend" / "app" / "integrations" / "kis"
CLIENT = KIS_DIR / "client.py"
INIT = KIS_DIR / "__init__.py"
TOKEN_CACHE = KIS_DIR / "token_cache.py"
ACCOUNT = KIS_DIR / "account.py"
TEST = ROOT / "backend" / "tests" / "test_kis_account.py"

TOKEN_CACHE_CONTENT = 'from __future__ import annotations\n\nimport hashlib\nimport json\nimport time\n\nfrom app.core.config import PROJECT_ROOT, Settings, get_settings\n\nfrom .client import KisAccessToken, issue_access_token, normalize_environment, validate_settings\n\n\n_CACHE_PATH = PROJECT_ROOT / "backend" / "runtime" / "kis" / "access_token.json"\n_REFRESH_MARGIN_SECONDS = 300\n\n\ndef _credential_fingerprint(settings: Settings) -> str:\n    raw = f"{normalize_environment(settings.kis_env)}:{settings.kis_app_key or \'\'}"\n    return hashlib.sha256(raw.encode("utf-8")).hexdigest()\n\n\ndef _load_cached(settings: Settings) -> KisAccessToken | None:\n    try:\n        data = json.loads(_CACHE_PATH.read_text(encoding="utf-8"))\n    except (OSError, json.JSONDecodeError, TypeError, ValueError):\n        return None\n\n    if data.get("credential_fingerprint") != _credential_fingerprint(settings):\n        return None\n\n    try:\n        usable_until = float(data.get("usable_until_epoch") or 0)\n    except (TypeError, ValueError):\n        return None\n\n    if usable_until <= time.time():\n        return None\n\n    token = str(data.get("access_token") or "")\n    if not token:\n        return None\n\n    expires_in_raw = data.get("expires_in")\n    try:\n        expires_in = int(expires_in_raw) if expires_in_raw is not None else None\n    except (TypeError, ValueError):\n        expires_in = None\n\n    return KisAccessToken(\n        access_token=token,\n        token_type=str(data.get("token_type")) if data.get("token_type") else None,\n        expires_in=expires_in,\n        expires_at=str(data.get("expires_at")) if data.get("expires_at") else None,\n    )\n\n\ndef _save_cached(settings: Settings, token: KisAccessToken) -> None:\n    _CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)\n    lifetime = token.expires_in if token.expires_in and token.expires_in > 0 else 86400\n    usable_until = time.time() + max(60, lifetime - _REFRESH_MARGIN_SECONDS)\n\n    payload = {\n        "credential_fingerprint": _credential_fingerprint(settings),\n        "access_token": token.access_token,\n        "token_type": token.token_type,\n        "expires_in": token.expires_in,\n        "expires_at": token.expires_at,\n        "usable_until_epoch": usable_until,\n    }\n    _CACHE_PATH.write_text(\n        json.dumps(payload, ensure_ascii=False, indent=2),\n        encoding="utf-8",\n    )\n\n\ndef get_access_token(settings: Settings | None = None) -> KisAccessToken:\n    settings = validate_settings(settings or get_settings())\n\n    cached = _load_cached(settings)\n    if cached is not None:\n        return cached\n\n    token = issue_access_token(settings)\n    _save_cached(settings, token)\n    return token\n'
ACCOUNT_CONTENT = 'from __future__ import annotations\n\nfrom dataclasses import dataclass\nfrom decimal import Decimal, InvalidOperation\nimport time\nfrom typing import Any\n\nimport httpx\n\nfrom app.core.config import Settings, get_settings\n\nfrom .client import base_url, normalize_environment, validate_account_settings\nfrom .token_cache import get_access_token\n\n\n_BALANCE_PATH = "/uapi/domestic-stock/v1/trading/inquire-balance"\n\n\nclass KisAccountError(RuntimeError):\n    def __init__(\n        self,\n        message: str,\n        *,\n        status_code: int | None = None,\n        code: str | None = None,\n    ) -> None:\n        super().__init__(message)\n        self.status_code = status_code\n        self.code = code\n\n\n@dataclass(frozen=True, slots=True)\nclass KisHolding:\n    ticker: str\n    name: str\n    quantity: Decimal\n    orderable_quantity: Decimal\n    average_price: Decimal\n    purchase_amount: Decimal\n    current_price: Decimal\n    evaluation_amount: Decimal\n    pnl_amount: Decimal\n    pnl_rate: Decimal\n\n\n@dataclass(frozen=True, slots=True)\nclass KisBalanceSummary:\n    deposit_amount: Decimal\n    securities_evaluation_amount: Decimal\n    total_evaluation_amount: Decimal\n    net_asset_amount: Decimal\n    purchase_amount_total: Decimal\n    evaluation_amount_total: Decimal\n    pnl_amount_total: Decimal\n\n\n@dataclass(frozen=True, slots=True)\nclass KisDomesticBalance:\n    holdings: tuple[KisHolding, ...]\n    summary: KisBalanceSummary | None\n\n\ndef _dec(value: Any) -> Decimal:\n    if value in (None, ""):\n        return Decimal("0")\n    try:\n        return Decimal(str(value))\n    except (InvalidOperation, ValueError, TypeError):\n        return Decimal("0")\n\n\ndef _holding_from_row(row: dict[str, Any]) -> KisHolding:\n    return KisHolding(\n        ticker=str(row.get("pdno") or "").strip(),\n        name=str(row.get("prdt_name") or "").strip(),\n        quantity=_dec(row.get("hldg_qty")),\n        orderable_quantity=_dec(row.get("ord_psbl_qty")),\n        average_price=_dec(row.get("pchs_avg_pric")),\n        purchase_amount=_dec(row.get("pchs_amt")),\n        current_price=_dec(row.get("prpr")),\n        evaluation_amount=_dec(row.get("evlu_amt")),\n        pnl_amount=_dec(row.get("evlu_pfls_amt")),\n        pnl_rate=_dec(row.get("evlu_pfls_rt") or row.get("evlu_erng_rt")),\n    )\n\n\ndef _summary_from_row(row: dict[str, Any] | None) -> KisBalanceSummary | None:\n    if not row:\n        return None\n    return KisBalanceSummary(\n        deposit_amount=_dec(row.get("dnca_tot_amt")),\n        securities_evaluation_amount=_dec(row.get("scts_evlu_amt")),\n        total_evaluation_amount=_dec(row.get("tot_evlu_amt")),\n        net_asset_amount=_dec(row.get("nass_amt")),\n        purchase_amount_total=_dec(row.get("pchs_amt_smtl_amt")),\n        evaluation_amount_total=_dec(row.get("evlu_amt_smtl_amt")),\n        pnl_amount_total=_dec(row.get("evlu_pfls_smtl_amt")),\n    )\n\n\ndef _tr_id(environment: str | None) -> str:\n    return "TTTC8434R" if normalize_environment(environment) == "real" else "VTTC8434R"\n\n\ndef inquire_domestic_balance(\n    settings: Settings | None = None,\n    *,\n    access_token: str | None = None,\n    timeout_seconds: float = 15.0,\n    include_zero_quantity: bool = False,\n    http_client: httpx.Client | None = None,\n) -> KisDomesticBalance:\n    settings = validate_account_settings(settings or get_settings())\n    token_value = access_token or get_access_token(settings).access_token\n\n    headers = {\n        "content-type": "application/json; charset=utf-8",\n        "authorization": f"Bearer {token_value}",\n        "appkey": settings.kis_app_key or "",\n        "appsecret": settings.kis_app_secret or "",\n        "tr_id": _tr_id(settings.kis_env),\n        "custtype": "P",\n        "tr_cont": "",\n    }\n    params = {\n        "CANO": settings.kis_account_no or "",\n        "ACNT_PRDT_CD": settings.kis_account_product_code,\n        "AFHR_FLPR_YN": "N",\n        "OFL_YN": "",\n        "INQR_DVSN": "02",\n        "UNPR_DVSN": "01",\n        "FUND_STTL_ICLD_YN": "N",\n        "FNCG_AMT_AUTO_RDPT_YN": "N",\n        "PRCS_DVSN": "00",\n        "CTX_AREA_FK100": "",\n        "CTX_AREA_NK100": "",\n    }\n\n    owns_client = http_client is None\n    client = http_client or httpx.Client(timeout=timeout_seconds)\n    holdings: list[KisHolding] = []\n    summary: KisBalanceSummary | None = None\n    page = 0\n\n    try:\n        while True:\n            response = client.get(\n                f"{base_url(settings.kis_env)}{_BALANCE_PATH}",\n                headers=headers,\n                params=params,\n                timeout=timeout_seconds,\n            )\n\n            if response.status_code != 200:\n                raise KisAccountError(\n                    "KIS balance request returned a non-200 response.",\n                    status_code=response.status_code,\n                )\n\n            body = response.json()\n            if str(body.get("rt_cd") or "") != "0":\n                raise KisAccountError(\n                    str(body.get("msg1") or "KIS balance request failed."),\n                    status_code=response.status_code,\n                    code=str(body.get("msg_cd") or "") or None,\n                )\n\n            rows = body.get("output1") or []\n            if not isinstance(rows, list):\n                raise KisAccountError("KIS balance output1 had an unexpected shape.")\n\n            for raw in rows:\n                if not isinstance(raw, dict):\n                    continue\n                item = _holding_from_row(raw)\n                if not item.ticker:\n                    continue\n                if not include_zero_quantity and item.quantity <= 0:\n                    continue\n                holdings.append(item)\n\n            output2 = body.get("output2") or []\n            if summary is None and isinstance(output2, list) and output2:\n                first = output2[0]\n                if isinstance(first, dict):\n                    summary = _summary_from_row(first)\n\n            tr_cont = (response.headers.get("tr_cont") or "").strip().upper()\n            next_fk = str(body.get("ctx_area_fk100") or "")\n            next_nk = str(body.get("ctx_area_nk100") or "")\n\n            if tr_cont not in {"M", "F"} or not (next_fk or next_nk):\n                break\n\n            page += 1\n            if page > 10:\n                raise KisAccountError("KIS balance pagination exceeded the safety limit.")\n\n            params["CTX_AREA_FK100"] = next_fk\n            params["CTX_AREA_NK100"] = next_nk\n            headers["tr_cont"] = "N"\n            time.sleep(0.6 if normalize_environment(settings.kis_env) == "virtual" else 0.1)\n    finally:\n        if owns_client:\n            client.close()\n\n    return KisDomesticBalance(holdings=tuple(holdings), summary=summary)\n'
TEST_CONTENT = 'from __future__ import annotations\n\nimport httpx\n\nfrom app.core.config import Settings\nfrom app.integrations.kis.account import inquire_domestic_balance\n\n\ndef _settings(**overrides) -> Settings:\n    values = {\n        "kis_app_key": "app-key",\n        "kis_app_secret": "app-secret",\n        "kis_account_no": "12345678",\n        "kis_account_product_code": "01",\n        "kis_env": "real",\n    }\n    values.update(overrides)\n    return Settings(_env_file=None, **values)\n\n\ndef test_balance_request_and_parsing():\n    seen = {}\n\n    def handler(request: httpx.Request) -> httpx.Response:\n        seen["authorization"] = request.headers.get("authorization")\n        seen["tr_id"] = request.headers.get("tr_id")\n        seen["cano"] = request.url.params.get("CANO")\n        seen["product"] = request.url.params.get("ACNT_PRDT_CD")\n        return httpx.Response(\n            200,\n            headers={"tr_cont": ""},\n            json={\n                "rt_cd": "0",\n                "output1": [\n                    {\n                        "pdno": "005930",\n                        "prdt_name": "삼성전자",\n                        "hldg_qty": "10",\n                        "ord_psbl_qty": "10",\n                        "pchs_avg_pric": "70000",\n                        "pchs_amt": "700000",\n                        "prpr": "80000",\n                        "evlu_amt": "800000",\n                        "evlu_pfls_amt": "100000",\n                        "evlu_pfls_rt": "14.2857",\n                    },\n                    {"pdno": "000660", "prdt_name": "SK하이닉스", "hldg_qty": "0"},\n                ],\n                "output2": [\n                    {\n                        "dnca_tot_amt": "500000",\n                        "scts_evlu_amt": "800000",\n                        "tot_evlu_amt": "1300000",\n                        "nass_amt": "1300000",\n                        "pchs_amt_smtl_amt": "700000",\n                        "evlu_amt_smtl_amt": "800000",\n                        "evlu_pfls_smtl_amt": "100000",\n                    }\n                ],\n                "ctx_area_fk100": "",\n                "ctx_area_nk100": "",\n            },\n        )\n\n    with httpx.Client(transport=httpx.MockTransport(handler)) as client:\n        result = inquire_domestic_balance(\n            _settings(),\n            access_token="test-token",\n            http_client=client,\n        )\n\n    assert seen == {\n        "authorization": "Bearer test-token",\n        "tr_id": "TTTC8434R",\n        "cano": "12345678",\n        "product": "01",\n    }\n    assert len(result.holdings) == 1\n    item = result.holdings[0]\n    assert item.ticker == "005930"\n    assert item.name == "삼성전자"\n    assert str(item.quantity) == "10"\n    assert str(item.average_price) == "70000"\n    assert str(item.current_price) == "80000"\n    assert str(item.pnl_amount) == "100000"\n    assert result.summary is not None\n    assert str(result.summary.total_evaluation_amount) == "1300000"\n\n\ndef test_virtual_balance_uses_virtual_tr_id():\n    seen = {}\n\n    def handler(request: httpx.Request) -> httpx.Response:\n        seen["tr_id"] = request.headers.get("tr_id")\n        return httpx.Response(\n            200,\n            json={\n                "rt_cd": "0",\n                "output1": [],\n                "output2": [],\n                "ctx_area_fk100": "",\n                "ctx_area_nk100": "",\n            },\n        )\n\n    with httpx.Client(transport=httpx.MockTransport(handler)) as client:\n        inquire_domestic_balance(\n            _settings(kis_env="virtual"),\n            access_token="test-token",\n            http_client=client,\n        )\n\n    assert seen["tr_id"] == "VTTC8434R"\n'
SMOKE_CODE = 'import sys\nsys.path.insert(0, "backend")\nfrom app.core.config import get_settings\nfrom app.integrations.kis.account import inquire_domestic_balance\n\ns = get_settings()\nbalance = inquire_domestic_balance(s)\n\nprint("KIS BALANCE: OK")\nprint("ENV:", s.kis_env)\nprint("HOLDINGS:", len(balance.holdings))\nfor item in balance.holdings:\n    print(\n        f"- {item.ticker} {item.name}"\n        f" | 수량={item.quantity}"\n        f" | 평균단가={item.average_price}"\n        f" | 현재가={item.current_price}"\n        f" | 평가손익={item.pnl_amount}"\n        f" | 수익률={item.pnl_rate}%"\n    )\nif balance.summary is not None:\n    print("TOTAL_EVALUATION:", balance.summary.total_evaluation_amount)\n    print("TOTAL_PNL:", balance.summary.pnl_amount_total)\n    print("NET_ASSET:", balance.summary.net_asset_amount)\n\nprint("ACCOUNT_NO_PRINTED: NO")\nprint("APP_KEY_PRINTED: NO")\nprint("APP_SECRET_PRINTED: NO")\nprint("ORDER_API_CALLED: NO")\n'


def fail(message: str) -> None:
    raise RuntimeError(message)


def patch_init(text: str) -> str:
    if "inquire_domestic_balance" in text:
        fail("__init__.py already contains KIS account exports.")

    import_anchor = """from .client import (
    KisAccessToken,
    KisAuthenticationError,
    KisConfigurationError,
    base_url,
    issue_access_token,
    normalize_environment,
    validate_account_settings,
    validate_settings,
)
"""
    if text.count(import_anchor) != 1:
        fail("__init__.py client import block not found exactly once.")

    extra_imports = import_anchor + """from .account import (
    KisAccountError,
    KisBalanceSummary,
    KisDomesticBalance,
    KisHolding,
    inquire_domestic_balance,
)
from .token_cache import get_access_token
"""
    text = text.replace(import_anchor, extra_imports, 1)

    all_anchor = '    "validate_settings",\n]'
    if text.count(all_anchor) != 1:
        fail("__init__.py __all__ anchor not found exactly once.")

    all_replacement = """    "validate_settings",
    "KisAccountError",
    "KisBalanceSummary",
    "KisDomesticBalance",
    "KisHolding",
    "inquire_domestic_balance",
    "get_access_token",
]"""
    return text.replace(all_anchor, all_replacement, 1)


def run(cmd: list[str], label: str) -> None:
    print()
    print(f"=== {label} ===")
    print(" ".join(cmd))
    result = subprocess.run(cmd, cwd=ROOT)
    if result.returncode != 0:
        fail(f"{label} failed with exit code {result.returncode}")


def main() -> int:
    print("PROJECT ROOT:", ROOT)
    print("KIS domestic balance bootstrap v2")
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

    created = []
    try:
        TOKEN_CACHE.write_text(TOKEN_CACHE_CONTENT, encoding="utf-8", newline="\n")
        created.append(TOKEN_CACHE)
        ACCOUNT.write_text(ACCOUNT_CONTENT, encoding="utf-8", newline="\n")
        created.append(ACCOUNT)
        TEST.write_text(TEST_CONTENT, encoding="utf-8", newline="\n")
        created.append(TEST)
        INIT.write_text(init_after, encoding="utf-8", newline="\n")

        venv_python = ROOT / ".venv" / "Scripts" / "python.exe"
        python_exe = str(venv_python if venv_python.is_file() else Path(sys.executable))

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

        run([python_exe, "-c", SMOKE_CODE], "KIS REAL BALANCE SMOKE")

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
        INIT.write_text(init_before, encoding="utf-8", newline="\n")
        for path in reversed(created):
            if path.exists():
                path.unlink()
        print()
        print("FAILED — KIS account source changes were restored.")
        print("Runtime token cache may remain under backend/runtime/kis/; it is gitignored.")
        raise


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print()
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
