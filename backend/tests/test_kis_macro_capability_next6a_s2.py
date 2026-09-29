from __future__ import annotations

import httpx

from app.core.config import Settings
from app.macro.providers.kis import probe_kis_daily_chart, probe_kis_macro_capabilities


def _settings(**kwargs) -> Settings:
    values = {
        "kis_app_key": "app-key",
        "kis_app_secret": "app-secret",
        "kis_env": "real",
    }
    values.update(kwargs)
    return Settings(_env_file=None, **values)


def test_kis_index_probe_uses_official_daily_endpoint_without_secret_projection():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith(
            "/uapi/overseas-price/v1/quotations/inquire-daily-chartprice"
        )
        assert request.headers["appkey"] == "app-key"
        assert request.headers["appsecret"] == "app-secret"
        assert request.headers["tr_id"] == "FHKST03030100"
        params = dict(request.url.params)
        assert params["FID_COND_MRKT_DIV_CODE"] == "N"
        assert params["FID_INPUT_ISCD"] == ".DJI"
        return httpx.Response(
            200,
            headers={"tr_cont": ""},
            json={
                "rt_cd": "0",
                "msg_cd": "MCA00000",
                "msg1": "정상처리",
                "output1": {"hts_kor_isnm": "다우존스"},
                "output2": [
                    {
                        "stck_bsop_date": "20260928",
                        "ovrs_nmix_prpr": "50000",
                    }
                ],
            },
        )

    http = httpx.Client(transport=httpx.MockTransport(handler))
    result = probe_kis_daily_chart(
        division="N",
        instrument_code=".DJI",
        start_date="2026-09-20",
        end_date="2026-09-28",
        settings=_settings(),
        access_token="token",
        http_client=http,
    )
    payload = result.to_dict()

    assert payload["status"] == "SUPPORTED_WITH_LIMITATIONS"
    assert payload["authenticated"] is True
    assert payload["details"]["row_count"] == 1
    assert payload["details"]["production_decision_approved"] is False
    serialized = str(payload)
    assert "app-key" not in serialized
    assert "app-secret" not in serialized
    assert "token" not in serialized


def test_kis_fx_and_treasury_codes_are_not_guessed(monkeypatch):
    monkeypatch.setattr(
        "app.macro.providers.kis.get_access_token",
        lambda settings: type("Token", (), {"access_token": "token"})(),
    )
    results = probe_kis_macro_capabilities(
        start_date="2026-09-20",
        end_date="2026-09-28",
        index_code="",
        fx_code=None,
        treasury_code=None,
        settings=_settings(),
    )

    assert [item.status.value for item in results] == [
        "SEMANTICS_UNVERIFIED",
        "SEMANTICS_UNVERIFIED",
        "SEMANTICS_UNVERIFIED",
    ]
    assert all(
        "OFFICIAL_INSTRUMENT_CODE_REQUIRED" in item.limitations
        for item in results
    )


def test_kis_not_configured_is_explicit_and_does_not_probe():
    results = probe_kis_macro_capabilities(
        start_date="2026-09-20",
        end_date="2026-09-28",
        settings=Settings(
            _env_file=None,
            kis_app_key=None,
            kis_app_secret=None,
        ),
    )

    assert len(results) == 3
    assert all(item.status.value == "NOT_CONFIGURED" for item in results)
