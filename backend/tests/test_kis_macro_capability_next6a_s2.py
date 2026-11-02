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
    assert payload["details"]["index_name"] == "다우존스"
    assert payload["details"]["index_name_source"] == "PROVIDER_RESPONSE"
    assert payload["details"]["index_sample"] == {
        "valid_index_rows": 1,
        "invalid_index_rows": 0,
        "latest_observation_date": "2026-09-28",
        "latest_index_level": "50000",
    }
    assert payload["details"]["display_rights_approved"] is False
    assert payload["details"]["ai_transfer_approved"] is False
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



def test_global01_success_status_with_zero_index_rows_is_not_usable():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"rt_cd": "0", "output1": {"hts_kor_isnm": "다우존스"}, "output2": []}
        )
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = probe_kis_daily_chart(
            division="N", instrument_code=".DJI",
            start_date="2026-10-22", end_date="2026-10-30",
            settings=_settings(), access_token="token", http_client=client,
        ).to_dict()
    assert result["status"] == "SEMANTICS_UNVERIFIED"
    assert result["details"]["row_count"] == 0
    assert result["details"]["index_sample"]["latest_observation_date"] is None
    assert "NO_PROVIDER_DATA_ROWS" in result["limitations"]


def test_global01_requires_identity_and_valid_date_and_positive_level():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={
            "rt_cd": "0", "output1": {},
            "output2": [
                {"stck_bsop_date": "20261101", "ovrs_nmix_prpr": "50000"},
                {"stck_bsop_date": "20261029", "ovrs_nmix_prpr": "-3"},
                {"stck_bsop_date": "20261030", "ovrs_nmix_prpr": "NaN"},
                {"stck_bsop_date": "20261028", "ovrs_nmix_prpr": "49000"},
            ],
        })
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = probe_kis_daily_chart(
            division="N", instrument_code=".UNKNOWN",
            start_date="2026-10-22", end_date="2026-10-30",
            settings=_settings(), access_token="token", http_client=client,
        ).to_dict()
    assert result["status"] == "SEMANTICS_UNVERIFIED"
    assert result["details"]["index_sample"]["valid_index_rows"] == 1
    assert result["details"]["index_sample"]["invalid_index_rows"] == 3
    assert result["details"]["index_sample"]["latest_observation_date"] == "2026-10-28"
    assert "INDEX_IDENTITY_UNVERIFIED" in result["limitations"]
    assert "INVALID_OR_OUT_OF_RANGE_INDEX_ROWS" in result["limitations"]


def test_global01_malformed_rows_cannot_claim_supported():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={
            "rt_cd": "0", "output1": {"hts_kor_isnm": "다우존스"},
            "output2": [{"stck_bsop_date": "2026-13-01", "ovrs_nmix_prpr": "100"}],
        })
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = probe_kis_daily_chart(
            division="N", instrument_code=".DJI",
            start_date="2026-10-22", end_date="2026-10-30",
            settings=_settings(), access_token="token", http_client=client,
        ).to_dict()
    assert result["status"] == "SEMANTICS_UNVERIFIED"
    assert result["details"]["index_sample"]["valid_index_rows"] == 0


def test_global01_official_request_code_allows_name_free_live_index_response():
    # Real KIS output1 is a numeric summary. hts_kor_isnm may not be present.
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["FID_INPUT_ISCD"] == ".DJI"
        return httpx.Response(200, json={
            "rt_cd": "0",
            "output1": {
                "ovrs_nmix_prpr": "51770.31",
                "ovrs_nmix_prdy_clpr": "51600.00",
                "prdy_ctrt": "0.33",
            },
            "output2": [
                {"stck_bsop_date": "20261022", "ovrs_nmix_prpr": "51010.00"},
                {"stck_bsop_date": "20261029", "ovrs_nmix_prpr": "51500.00"},
                {"stck_bsop_date": "20261030", "ovrs_nmix_prpr": "51770.31"},
            ],
        })
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = probe_kis_daily_chart(
            division="N", instrument_code=".DJI",
            start_date="2026-10-22", end_date="2026-10-30",
            settings=_settings(), access_token="token", http_client=client,
        ).to_dict()

    assert result["status"] == "SUPPORTED_WITH_LIMITATIONS"
    assert result["authenticated"] is True
    assert result["details"]["index_name"] == "다우존스 산업평균지수"
    assert result["details"]["index_name_source"] == "OFFICIAL_KIS_REQUEST_CODE"
    assert result["details"]["provider_index_name"] is None
    assert result["details"]["index_sample"]["valid_index_rows"] == 3
    assert result["details"]["index_sample"]["latest_observation_date"] == "2026-10-30"
    assert result["details"]["index_sample"]["latest_index_level"] == "51770.31"
    assert "INDEX_NAME_FROM_OFFICIAL_REQUEST_CODE_ONLY" in result["limitations"]
    assert "INDEX_IDENTITY_UNVERIFIED" not in result["limitations"]
    assert result["details"]["display_rights_approved"] is False
    assert result["details"]["retention_rights_approved"] is False
    assert result["details"]["production_decision_approved"] is False


def test_global01_official_code_cannot_hide_conflicting_provider_name():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={
            "rt_cd": "0",
            "output1": {"hts_kor_isnm": "나스닥 종합지수"},
            "output2": [{"stck_bsop_date": "20261030", "ovrs_nmix_prpr": "51770.31"}],
        })
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = probe_kis_daily_chart(
            division="N", instrument_code=".DJI",
            start_date="2026-10-22", end_date="2026-10-30",
            settings=_settings(), access_token="token", http_client=client,
        ).to_dict()
    assert result["status"] == "SEMANTICS_UNVERIFIED"
    assert "INDEX_NAME_CONFLICT_WITH_REQUEST_CODE" in result["limitations"]
