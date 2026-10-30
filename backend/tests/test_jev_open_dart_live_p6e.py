"""P6-E OpenDART live-list regression: pages, receipt identity, DATE_ONLY, no persistence."""
from __future__ import annotations

import asyncio
from datetime import date

import pytest
from fastapi.testclient import TestClient

from app.market.providers.base import ProviderError
from app.market.providers.dart import OpenDartProvider


def entry(no: int, *, stock_code="068270", corp_code="12345678", receipt_date="20261029"):
    return {
        "rcept_no": f"{no:014d}", "corp_code": corp_code,
        "stock_code": stock_code, "corp_name": "샘플 기업",
        "report_nm": "임시 공시명", "flr_nm": "대표이사",
        "rcept_dt": receipt_date, "rm": "",
    }


@pytest.mark.asyncio
async def test_live_disclosure_paging_dedup_preserves_legacy_fields(monkeypatch):
    provider = OpenDartProvider("test-key")
    seen = []

    async def fake_get(path, params, *, allow_no_data=False):
        seen.append((path, params, allow_no_data))
        page = params["page_no"]
        return {
            "status": "000", "total_count": 3, "total_page": 2,
            "list": [entry(101), entry(102)] if page == 1
                    else [entry(102), entry(103)],
        }

    monkeypatch.setattr(provider, "_get", fake_get)
    result = await provider.disclosures(
        "12345678", "2026-10-28", "2026-10-30", page_count=2, max_pages=3,
    )
    assert [v["receipt_no"] for v in result["rows"]] == [
        "00000000000101", "00000000000102", "00000000000103",
    ]
    assert result["count"] == 3
    assert result["pages_fetched"] == 2
    assert result["total_count"] == 3
    assert result["duplicate_receipt_count"] == 1
    assert result["truncated"] is False
    assert result["rows"][0]["receipt_date"] == "20261029"
    assert result["rows"][0]["source_time_quality"] == "DATE_ONLY"
    assert result["rows"][0]["source_published_at"] is None
    assert result["rows"][0]["viewer_url"].endswith("rcpNo=00000000000101")
    assert result["model_calls"] == 0 and result["persisted"] is False
    assert [x[1]["page_no"] for x in seen] == [1, 2]
    assert all(x[2] is True for x in seen)


@pytest.mark.asyncio
async def test_no_disclosures_status_013_is_empty_not_provider_crash(monkeypatch):
    p = OpenDartProvider("key")
    async def fake_get(path, params, *, allow_no_data=False):
        assert allow_no_data
        return {"status": "013", "message": "데이터 없음"}
    monkeypatch.setattr(p, "_get", fake_get)
    out = await p.disclosures("12345678", "20261001", "20261030")
    assert out["count"] == out["total_count"] == 0
    assert out["pages_fetched"] == 1


@pytest.mark.parametrize("start,end", [
    ("2026-02-30", "2026-03-02"),
    ("202610301", "20261030"),
    ("2026-10-31", "2026-10-30"),
])
def test_dates_must_be_real_and_ordered(start, end):
    p = OpenDartProvider("fake")
    with pytest.raises(ValueError):
        asyncio.run(p.disclosures("12345678", start, end))


@pytest.mark.asyncio
@pytest.mark.parametrize("badrow", [
    entry(101, stock_code="068270", corp_code="87654321"),
    {**entry(101), "rcept_no": "INVALID"},
    {**entry(101), "rcept_dt": "20260230"},
    {**entry(101), "rcept_dt": "20261012"},
])
async def test_invalid_source_identity_date_fails_closed(monkeypatch, badrow):
    p = OpenDartProvider("fake")
    async def fake_get(path, params, *, allow_no_data=False):
        return {"status": "000", "total_count": 1, "total_page": 1, "list": [badrow]}
    monkeypatch.setattr(p, "_get", fake_get)
    with pytest.raises(ProviderError):
        await p.disclosures("12345678", "20261028", "20261030")


@pytest.mark.asyncio
async def test_incomplete_paging_explicitly_marks_truncated(monkeypatch):
    p = OpenDartProvider("fake")
    async def fake_get(path, params, *, allow_no_data=False):
        return {"status": "000", "total_count": 9, "total_page": 9,
                "list": [entry(params["page_no"])]}
    monkeypatch.setattr(p, "_get", fake_get)
    r = await p.disclosures("12345678", "20261028", "20261030", max_pages=2)
    assert r["truncated"] is True and r["count"] == 2 and r["total_count"] == 9


def test_live_by_stock_api_uses_existing_provider_read_only(monkeypatch):
    import app.api.data_sources as api
    p = OpenDartProvider("fake")
    calls = []

    async def fake_map(stock_code):
        calls.append(("resolve", stock_code))
        return "12345678"

    async def fake_disclosures(corp_code, begin_date, end_date, page_count=20, *, max_pages=1):
        calls.append(("disclosures", corp_code, begin_date, end_date, max_pages))
        return {
            "provider": "OpenDART", "corp_code": corp_code,
            "begin_date": begin_date.replace("-", ""), "end_date": end_date.replace("-", ""),
            "count": 1, "total_count": 1, "total_page": 1,
            "pages_fetched": 1, "truncated": False, "duplicate_receipt_count": 0,
            "persisted": False, "model_calls": 0,
            "rows": [{
                "receipt_no": "20261029000001", "corp_name": "검증",
                "report_name": "공시명", "receipt_date": "20261029",
                "viewer_url": "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20261029000001",
                "stock_code": "068270", "source_time_quality": "DATE_ONLY",
                "source_published_at": None,
            }],
        }
    monkeypatch.setattr(p, "resolve_corp_code", fake_map)
    monkeypatch.setattr(p, "disclosures", fake_disclosures)
    monkeypatch.setattr(api, "_providers", lambda: (None, p))
    from app.main import app
    response = TestClient(app).get(
        "/api/dart/stocks/068270/disclosures",
        params={"begin_date": "2026-10-28", "end_date": "2026-10-30"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["stock_code"] == "068270"
    assert body["count"] == 1
    assert body["event_evidence_storage"] == "NOT_PERSISTED_RIGHTS_UNVERIFIED"
    assert body["external_ai_transfer"] == "BLOCKED"
    assert body["db_writes"] == body["model_calls"] == 0
    assert calls == [
        ("resolve", "068270"),
        ("disclosures", "12345678", "2026-10-28", "2026-10-30", 2),
    ]


def test_live_by_stock_api_rejects_future_and_wrong_stock_without_persistence(monkeypatch):
    import app.api.data_sources as api
    p = OpenDartProvider("fake")
    calls = []

    async def mapping(stock_code):
        calls.append(stock_code)
        return "12345678"

    async def wrong(corp_code, begin_date, end_date, page_count=20, *, max_pages=1):
        return {"rows": [{"stock_code": "999999"}], "provider": "OpenDART"}
    monkeypatch.setattr(p, "resolve_corp_code", mapping)
    monkeypatch.setattr(p, "disclosures", wrong)
    monkeypatch.setattr(api, "_providers", lambda: (None, p))
    from app.main import app
    client = TestClient(app)
    bad = client.get("/api/dart/stocks/068270/disclosures",
                     params={"begin_date": "2026-11-02", "end_date": "2026-11-03"})
    assert bad.status_code in {400, 422}
    assert calls == []
    mismatch = client.get("/api/dart/stocks/068270/disclosures",
                          params={"begin_date": "2026-10-28", "end_date": "2026-10-30"})
    assert mismatch.status_code == 502
