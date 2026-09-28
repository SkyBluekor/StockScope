from __future__ import annotations

from datetime import date

from app.core.config import Settings
from app.integrations.kis.client import KisAccessToken
import app.integrations.kis.holiday as holiday_module
from app.integrations.kis.holiday import KisHolidayProvider


class FakeResponse:
    status_code = 200

    def json(self):
        return {
            "rt_cd": "0",
            "output": [
                {
                    "bass_dt": "20260925",
                    "wday_dvsn_cd": "5",
                    "bzdy_yn": "Y",
                    "tr_day_yn": "Y",
                    "opnd_yn": "Y",
                    "sttl_day_yn": "Y",
                }
            ],
        }


class FakeClient:
    def __init__(self):
        self.calls = []

    def get(self, url, *, headers, params, timeout):
        self.calls.append((url, headers, params, timeout))
        return FakeResponse()

    def close(self):
        pass


def _settings() -> Settings:
    return Settings(
        _env_file=None,
        kis_app_key="app-key",
        kis_app_secret="app-secret",
        kis_env="real",
    )


def test_kis_holiday_provider_uses_official_open_day_field_and_daily_cache(monkeypatch) -> None:
    monkeypatch.setattr(
        holiday_module,
        "get_access_token",
        lambda _settings: KisAccessToken("token", "Bearer", 3600, None),
    )
    provider = KisHolidayProvider()
    client = FakeClient()
    target = date(2026, 9, 25)

    first = provider.is_open_day(target, _settings(), http_client=client)
    second = provider.is_open_day(target, _settings(), http_client=client)

    assert first is True
    assert second is True
    assert len(client.calls) == 1
    url, headers, params, _timeout = client.calls[0]
    assert url.endswith("/uapi/domestic-stock/v1/quotations/chk-holiday")
    assert headers["tr_id"] == "CTCA0903R"
    assert params["BASS_DT"] == "20260925"
    assert params["CTX_AREA_FK"] == ""
    assert params["CTX_AREA_NK"] == ""


def test_kis_holiday_provider_rejects_missing_requested_date(monkeypatch) -> None:
    monkeypatch.setattr(
        holiday_module,
        "get_access_token",
        lambda _settings: KisAccessToken("token", "Bearer", 3600, None),
    )

    class MissingDateResponse(FakeResponse):
        def json(self):
            return {"rt_cd": "0", "output": [{"bass_dt": "20260924", "opnd_yn": "Y"}]}

    class MissingDateClient(FakeClient):
        def get(self, url, *, headers, params, timeout):
            self.calls.append((url, headers, params, timeout))
            return MissingDateResponse()

    provider = KisHolidayProvider()
    try:
        provider.is_open_day(
            date(2026, 9, 25),
            _settings(),
            http_client=MissingDateClient(),
        )
    except holiday_module.KisHolidayError as exc:
        assert "requested date" in str(exc)
    else:
        raise AssertionError("missing holiday date must fail")
