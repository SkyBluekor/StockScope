from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.macro import local_dji
from app.macro.capability import CapabilityStatus, ProviderCapability
from app.macro.providers.kis import probe_kis_daily_chart
from app.core.config import Settings


@pytest.fixture(autouse=True)
def _clear_cache(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(local_dji, "_CACHE", None)
    monkeypatch.setattr(local_dji, "_CACHE_UNTIL", 0.0)


def _capability(*, pair: bool = True, latest: str = "2026-10-30"):
    return ProviderCapability(
        provider="KIS",
        component="OVERSEAS_INDEX",
        status=CapabilityStatus.SUPPORTED_WITH_LIMITATIONS,
        configured=True,
        authenticated=True,
        details={
            "index_name": "다우존스 산업평균지수",
            "index_name_source": "OFFICIAL_KIS_REQUEST_CODE",
            "index_sample": {"valid_index_rows": 7, "invalid_index_rows": 0},
            "index_reference_pair": ({
                "previous_observation_date": "2026-10-29",
                "observation_date": latest,
                "previous_index_value": "51500",
                "index_value": "51770.31",
                "daily_change_pct": "0.524873786407766990291262136",
            } if pair else None),
        },
    )


def test_global01_s2_disabled_is_network_free_and_never_leaks_cached_values(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(local_dji, "probe_kis_daily_chart",
                        lambda **kwargs: pytest.fail("No network while disabled"))
    local_dji._CACHE = {"status": "PARTIAL", "index_value": "SECRET_PRICE"}
    local_dji._CACHE_UNTIL = 999999999999
    result = local_dji.read_local_dji_reference(enabled=False)
    assert result["status"] == "UNAVAILABLE"
    assert result["reason"] == "PERSONAL_LOCAL_OPT_IN_REQUIRED"
    assert result["index_value"] is None
    assert result["production_decision_approved"] is False


def test_global01_s2_collects_two_observations_once_and_caches(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(local_dji, "datetime", SimpleNamespace(
        now=lambda zone: datetime(2026, 11, 2, 6, 0, tzinfo=timezone.utc),
    ))
    calls = []
    def fake_probe(**kwargs):
        calls.append(kwargs)
        return _capability()
    monkeypatch.setattr(local_dji, "probe_kis_daily_chart", fake_probe)
    first = local_dji.read_local_dji_reference(enabled=True)
    second = local_dji.read_local_dji_reference(enabled=True)
    assert first == second
    assert len(calls) == 1
    assert calls[0]["division"] == "N"
    assert calls[0]["instrument_code"] == ".DJI"
    assert calls[0]["include_reference_pair"] is True
    assert first["status"] == "PARTIAL"
    assert first["observation_date"] == "2026-10-30"
    assert first["previous_observation_date"] == "2026-10-29"
    assert first["index_value"] == "51770.31"
    assert first["source_time_quality"] == "DATE_ONLY"
    assert first["session_close_verified"] is False
    assert first["scanner_input_approved"] is False
    assert first["risk_gate_input_approved"] is False
    assert first["retention_rights_approved"] is False
    assert first["display_rights_approved"] is False
    assert first["ai_transfer_approved"] is False


@pytest.mark.parametrize("pair,latest,expected", [
    (False, "2026-10-30", "INDEX_PAIR_UNVERIFIED"),
    (True, "2026-09-30", "INDEX_STALE_OR_FUTURE"),
    (True, "2026-11-08", "INDEX_STALE_OR_FUTURE"),
])
def test_global01_s2_absent_or_stale_data_is_not_displayed(
    monkeypatch: pytest.MonkeyPatch,
    pair: bool, latest: str, expected: str,
):
    monkeypatch.setattr(local_dji, "datetime", SimpleNamespace(
        now=lambda zone: datetime(2026, 11, 2, 6, 0, tzinfo=timezone.utc),
    ))
    monkeypatch.setattr(local_dji, "probe_kis_daily_chart",
                        lambda **kwargs: _capability(pair=pair, latest=latest))
    result = local_dji.read_local_dji_reference(enabled=True)
    assert result["status"] == "UNAVAILABLE"
    assert result["reason"] == expected
    assert result["index_value"] is None


def test_global01_s2_backend_blocks_public_or_proxied_requests(
    monkeypatch: pytest.MonkeyPatch,
):
    import app.api.macro as macro_api
    monkeypatch.setattr(macro_api, "personal_local_opted_in", lambda: True)
    monkeypatch.setattr(macro_api, "read_local_dji_reference",
                        lambda *, enabled, reason="PERSONAL_LOCAL_OPT_IN_REQUIRED":
                        {"status": "PARTIAL" if enabled else "UNAVAILABLE",
                         "reason": None if enabled else reason})
    with TestClient(app, client=("127.0.0.1", 15000)) as local:
        okay = local.get("/api/macro/overseas-index-reference",
                         headers={"host": "127.0.0.1:8000"})
        assert okay.status_code == 200
        assert okay.json()["status"] == "PARTIAL"
        assert okay.headers["cache-control"] == "no-store"
        for headers in (
            {"host": "stockscope.example.com"},
            {"host": "127.0.0.1:8000", "x-forwarded-for": "203.0.113.5"},
            {"host": "127.0.0.1:8000", "referer": "https://example.com/scanner"},
            {"host": "127.0.0.1:8000", "origin": "http://example.com"},
        ):
            rejected = local.get("/api/macro/overseas-index-reference", headers=headers)
            assert rejected.status_code == 200
            assert rejected.json()["status"] == "UNAVAILABLE"
            assert rejected.json()["reason"] == "LOCAL_ACCESS_ONLY"
    with TestClient(app, client=("198.51.100.10", 24000)) as remote:
        result = remote.get("/api/macro/overseas-index-reference",
                            headers={"host": "127.0.0.1:8000"})
        assert result.json()["status"] == "UNAVAILABLE"
        assert result.json()["reason"] == "LOCAL_ACCESS_ONLY"


def test_global01_s2_uses_real_kis_row_shape_and_two_distinct_dates():
    def handler(request: httpx.Request):
        return httpx.Response(200, json={
            "rt_cd": "0",
            "output1": {"ovrs_nmix_prpr": "51770.31"},
            "output2": [
                {"stck_bsop_date": "20261029", "ovrs_nmix_prpr": "51500"},
                {"stck_bsop_date": "20261030", "ovrs_nmix_prpr": "51770.31"},
            ],
        })
    settings = Settings(_env_file=None, kis_app_key="key", kis_app_secret="secret")
    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        result = probe_kis_daily_chart(
            division="N", instrument_code=".DJI",
            start_date="2026-10-22", end_date="2026-10-30",
            settings=settings, access_token="test-token", http_client=http,
            include_reference_pair=True,
        ).to_dict()
    assert result["status"] == "SUPPORTED_WITH_LIMITATIONS"
    assert result["details"]["index_reference_pair"]["index_value"] == "51770.31"
    assert result["details"]["index_reference_pair"]["daily_change_pct"].startswith("0.5248")
    assert result["details"]["retention_rights_approved"] is False
    assert "test-token" not in str(result)
