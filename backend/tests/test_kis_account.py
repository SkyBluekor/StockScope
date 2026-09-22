from __future__ import annotations

import httpx

from app.core.config import Settings
from app.integrations.kis.account import inquire_domestic_balance


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


def test_balance_request_and_parsing():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["authorization"] = request.headers.get("authorization")
        seen["tr_id"] = request.headers.get("tr_id")
        seen["cano"] = request.url.params.get("CANO")
        seen["product"] = request.url.params.get("ACNT_PRDT_CD")
        return httpx.Response(
            200,
            headers={"tr_cont": ""},
            json={
                "rt_cd": "0",
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
                    {"pdno": "000660", "prdt_name": "SK하이닉스", "hldg_qty": "0"},
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

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
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
    }
    assert len(result.holdings) == 1
    item = result.holdings[0]
    assert item.ticker == "005930"
    assert item.name == "삼성전자"
    assert str(item.quantity) == "10"
    assert str(item.average_price) == "70000"
    assert str(item.current_price) == "80000"
    assert str(item.pnl_amount) == "100000"
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

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        inquire_domestic_balance(
            _settings(kis_env="virtual"),
            access_token="test-token",
            http_client=client,
        )

    assert seen["tr_id"] == "VTTC8434R"
