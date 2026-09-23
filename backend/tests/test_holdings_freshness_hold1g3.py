from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.api import holdings as holdings_api
from app.holdings.freshness import (
    HoldingsMarketFreshnessError,
    HoldingsMarketFreshnessResult,
    HoldingsMarketFreshnessService,
)


class _FakeScanner:
    def __init__(self, payload: dict):
        self.payload = payload
        self.calls: list[dict] = []

    async def prepare_latest_confirmed_data(self, **kwargs):
        self.calls.append(kwargs)
        return dict(self.payload)


def test_freshness_prepares_only_selected_market_and_never_runs_scanner(tmp_path: Path) -> None:
    holder: dict[str, object] = {}
    fake = _FakeScanner(
        {
            "status": "UPDATED",
            "requested_date": "2026-09-22",
            "latest_confirmed_date": "2026-09-22",
            "resolved_as_of_date": "2026-09-22",
            "known_data_date": "2026-09-21",
            "market_data_updated": True,
            "date_changed": True,
            "diagnostics": {"network_requests": 2},
            "message": "새로운 확정 시세를 확인했습니다.",
        }
    )

    def factory(provider, store):
        holder["store_path"] = store.db_path
        return fake

    service = HoldingsMarketFreshnessService(
        krx_api_key="test",
        market_store_db=tmp_path / "market.db",
        scanner_factory=factory,
    )
    result = asyncio.run(service.prepare(market="KOSPI", known_data_date="2026-09-21"))

    assert result.status == "UPDATED"
    assert result.resolved_as_of_date == "2026-09-22"
    assert result.network_requests == 2
    assert fake.calls == [{"market_scope": "KOSPI", "known_data_date": "2026-09-21"}]
    assert holder["store_path"] == tmp_path / "market.db"


def test_freshness_failure_does_not_accept_older_fallback(tmp_path: Path) -> None:
    fake = _FakeScanner(
        {
            "status": "UPDATE_FAILED",
            "resolved_as_of_date": "2026-09-21",
            "known_data_date": "2026-09-21",
            "message": "새로운 확정 시세를 가져오지 못했습니다. 현재 분석은 유지합니다.",
            "diagnostics": {"network_requests": 1},
        }
    )
    service = HoldingsMarketFreshnessService(
        krx_api_key="test",
        market_store_db=tmp_path / "market.db",
        scanner_factory=lambda provider, store: fake,
    )
    with pytest.raises(HoldingsMarketFreshnessError) as exc:
        asyncio.run(service.prepare(market="KOSPI", known_data_date="2026-09-21"))

    assert exc.value.code == "HOLD_MARKET_FRESHNESS_UPDATE_FAILED"


def test_refresh_endpoint_prepares_freshness_before_latest_confirmed_analysis(tmp_path: Path, monkeypatch) -> None:
    holdings_db = tmp_path / "holdings.db"
    monkeypatch.setenv("STOCKSCOPE_HOLDINGS_DB", str(holdings_db))

    app = FastAPI()
    app.include_router(holdings_api.router, prefix="/api")
    client = TestClient(app)

    watched = client.post(
        "/api/holdings/watch",
        json={"market": "KOSPI", "ticker": "005930", "name": "삼성전자"},
    )
    assert watched.status_code == 200, watched.text
    stock_id = watched.json()["stock"]["stock_id"]

    freshness_calls: list[dict] = []
    analysis_calls: list[dict] = []

    class FakeFreshnessService:
        async def prepare(self, **kwargs):
            freshness_calls.append(kwargs)
            return HoldingsMarketFreshnessResult(
                status="UPDATED",
                market="KOSPI",
                requested_date="2026-09-22",
                latest_confirmed_date="2026-09-22",
                resolved_as_of_date="2026-09-22",
                known_data_date="2026-09-21",
                market_data_updated=True,
                date_changed=True,
                network_requests=2,
                message="새로운 확정 시세를 확인했습니다.",
            )

    class FakeHistoryService:
        def analyze_latest_confirmed(self, **kwargs):
            analysis_calls.append(kwargs)
            return object()

    monkeypatch.setattr(holdings_api, "_freshness_service", lambda: FakeFreshnessService())
    monkeypatch.setattr(holdings_api, "_history_service", lambda catalog: FakeHistoryService())
    monkeypatch.setattr(
        holdings_api,
        "_current_analysis_payload",
        lambda catalog, sid: {"market_date": "2026-09-21"},
    )
    monkeypatch.setattr(
        holdings_api,
        "_stored_analysis_payload",
        lambda catalog, stored: {
            "market_date": "2026-09-22",
            "revision_id": "revision-1",
            "revision_no": 1,
            "created_revision": True,
            "promoted_current": True,
        },
    )

    response = client.post(f"/api/holdings/stocks/{stock_id}/analysis/refresh?prepare_latest=true")
    assert response.status_code == 200, response.text
    body = response.json()
    assert freshness_calls == [{"market": "KOSPI", "known_data_date": "2026-09-21"}]
    assert analysis_calls == [
        {"monitored_stock_id": stock_id}
    ]
    assert body["market_date"] == "2026-09-22"
    assert body["previous_analysis_date"] == "2026-09-21"
    assert body["data_freshness"]["status"] == "UPDATED"


def test_freshness_source_never_runs_market_wide_scanner() -> None:
    source = Path("backend/app/holdings/freshness.py").read_text(encoding="utf-8")
    assert "prepare_latest_confirmed_data" in source
    assert ".run(" not in source
