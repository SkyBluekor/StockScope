from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
import sqlite3

import pytest
from fastapi.testclient import TestClient

from app.backtest.market_store import HistoricalMarketStore
from app.event_evidence.time import EvidenceTimeQuality, TemporalEvidence
from app.main import app
from app.macro import (
    MacroObservation,
    MacroStore,
    fred_dgs10_candidate_contract,
)


client = TestClient(app)
SERIES = "US_10Y_CONSTANT_MATURITY_YIELD"
CUTOFF = "2026-10-01T11:00:00+00:00"


def _create_macro_db(path: Path, *, count: int = 30) -> None:
    store = MacroStore(path)
    store.initialize()
    store.register_series_contract(fred_dgs10_candidate_contract())
    store.begin_collection_run(provider="FRED", run_id="S32-MACRO-RUN")

    start = date(2026, 9, 1)
    for index in range(count):
        current_date = (start + timedelta(days=index)).isoformat()
        value = f"{4 + (index * index) / 1000:.3f}"
        store.store_observation(
            run_id="S32-MACRO-RUN",
            observation=MacroObservation(
                series_id=SERIES,
                native_observation_id=f"DGS10:{current_date}",
                observation_date=current_date,
                source_value=value,
                normalized_value=value,
                source_unit="PERCENT",
                source_payload_hash=f"{index + 1:064x}",
                normalizer_version="TEST-NORMALIZER-V1",
                realtime_start=current_date,
                realtime_end=current_date,
                vintage_id="2026-09-30",
                temporal=TemporalEvidence(
                    event_time=current_date,
                    source_published_at=None,
                    provider_published_at=None,
                    first_seen_at="2026-09-30T10:00:00+00:00",
                    available_at="2026-09-30T10:00:00+00:00",
                    fetched_at="2026-09-30T10:00:00+00:00",
                    time_quality=EvidenceTimeQuality.DATE_ONLY,
                ),
            ),
        )
    store.publish_collection_run("S32-MACRO-RUN")


def _create_market_db(path: Path) -> None:
    store = HistoricalMarketStore(path)
    store.put_stock_day(
        "KOSPI",
        "20260929",
        [{"date": "20260929", "code": "005930", "close": 100}],
        stable=True,
    )
    store.put_index_day(
        "KOSPI",
        "20260929",
        {"date": "20260929", "close": 200},
        stable=True,
    )
    store.put_stock_day(
        "KOSPI",
        "20260930",
        [{"date": "20260930", "code": "005930", "close": 103}],
        stable=True,
    )
    store.put_index_day(
        "KOSPI",
        "20260930",
        {"date": "20260930", "close": 202},
        stable=True,
    )

    # HistoricalMarketStore writes in WAL mode. Flush fixture setup before taking
    # file-state snapshots so the API read itself is the only operation measured.
    with sqlite3.connect(path) as conn:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")


def _request() -> object:
    return client.get(
        "/api/macro/market-stock-impact",
        params={
            "market": "KOSPI",
            "ticker": "005930",
            "end_date": "2026-09-30",
            "cutoff": CUTOFF,
        },
    )


def test_market_stock_impact_api_is_read_only_and_descriptive(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    macro_db = tmp_path / "macro.db"
    market_db = tmp_path / "market_history.db"
    _create_macro_db(macro_db)
    _create_market_db(market_db)
    monkeypatch.setenv("STOCKSCOPE_MACRO_DB", str(macro_db))
    monkeypatch.setenv("STOCKSCOPE_MARKET_STORE_DB", str(market_db))

    macro_before = macro_db.stat()
    market_before = market_db.stat()
    response = _request()
    macro_after = macro_db.stat()
    market_after = market_db.stat()

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    body = response.json()

    assert (
        body["contract_version"]
        == "VN_NEXT6C_S32_MARKET_STOCK_IMPACT_API_V1"
    )
    assert body["status"] == "AVAILABLE"
    assert body["macro_context"]["context_id"].startswith("MACROCTX-")
    assert len(body["macro_context"]["context_hash"]) == 64
    assert body["macro_context"]["decision_cutoff"] == CUTOFF

    impact = body["impact"]
    assert impact["context_ref"]["macro_context_id"] == body["macro_context"][
        "context_id"
    ]
    assert impact["context_ref"]["macro_context_hash"] == body[
        "macro_context"
    ]["context_hash"]
    assert impact["window"]["start_date"] == "20260929"
    assert impact["window"]["end_date"] == "20260930"
    assert impact["market"]["unit"] == "PERCENT"
    assert impact["stock"]["unit"] == "PERCENT"
    assert impact["relative"]["unit"] == "PERCENTAGE_POINT"
    assert impact["sector"]["status"] == "UNAVAILABLE"
    assert impact["sector"]["reason"] == "PIT_MAPPING_UNAVAILABLE"

    assert (
        body["sector_route"]["historical_sector_status"]
        == "BLOCKED_EXTERNAL_SOURCE"
    )
    assert (
        body["sector_route"]["historical_impact_mode"]
        == "MARKET_STOCK_ONLY"
    )
    assert "OPENDART_STATIC_CURRENT" in body["sector_route"][
        "prohibited_unlock_inputs"
    ]
    assert body["production_decision_approved"] is False
    assert impact["governance"]["strategy_input_approved"] is False
    assert impact["governance"]["scanner_input_approved"] is False
    assert impact["governance"]["risk_gate_input_approved"] is False
    assert impact["governance"]["holdings_plan_input_approved"] is False
    assert impact["governance"]["network_access"] is False

    assert macro_after.st_size == macro_before.st_size
    assert macro_after.st_mtime_ns == macro_before.st_mtime_ns
    assert market_after.st_size == market_before.st_size
    assert market_after.st_mtime_ns == market_before.st_mtime_ns


def test_market_stock_impact_api_fails_closed_when_macro_store_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    missing_macro = tmp_path / "missing" / "macro.db"
    market_db = tmp_path / "market_history.db"
    _create_market_db(market_db)
    monkeypatch.setenv("STOCKSCOPE_MACRO_DB", str(missing_macro))
    monkeypatch.setenv("STOCKSCOPE_MARKET_STORE_DB", str(market_db))

    response = _request()

    assert response.status_code == 503
    assert response.headers["cache-control"] == "no-store"
    detail = response.json()["detail"]
    assert detail["code"] == "MACRO_IMPACT_CONTEXT_UNAVAILABLE"
    assert detail["reason"] == "STORE_NOT_FOUND"
    assert not missing_macro.exists()


def test_market_stock_impact_api_fails_closed_when_market_store_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    macro_db = tmp_path / "macro.db"
    missing_market = tmp_path / "missing" / "market_history.db"
    _create_macro_db(macro_db)
    monkeypatch.setenv("STOCKSCOPE_MACRO_DB", str(macro_db))
    monkeypatch.setenv("STOCKSCOPE_MARKET_STORE_DB", str(missing_market))

    response = _request()

    assert response.status_code == 503
    assert response.headers["cache-control"] == "no-store"
    detail = response.json()["detail"]
    assert detail["code"] == "MARKET_IMPACT_STORE_UNAVAILABLE"
    assert detail["reason"] == "STORE_NOT_FOUND"
    assert not missing_market.exists()


def test_market_stock_impact_api_returns_unavailable_for_insufficient_sessions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    macro_db = tmp_path / "macro.db"
    market_db = tmp_path / "market_history.db"
    _create_macro_db(macro_db)

    store = HistoricalMarketStore(market_db)
    store.put_stock_day(
        "KOSPI",
        "20260930",
        [{"date": "20260930", "code": "005930", "close": 100}],
        stable=True,
    )
    store.put_index_day(
        "KOSPI",
        "20260930",
        {"date": "20260930", "close": 200},
        stable=True,
    )

    monkeypatch.setenv("STOCKSCOPE_MACRO_DB", str(macro_db))
    monkeypatch.setenv("STOCKSCOPE_MARKET_STORE_DB", str(market_db))

    response = _request()

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "UNAVAILABLE"
    assert body["impact"]["reason"] == "INSUFFICIENT_COMMON_SESSIONS"
    assert body["impact"]["market"]["return_pct"] is None
    assert body["impact"]["stock"]["return_pct"] is None
    assert body["impact"]["relative"]["stock_vs_market_pctp"] is None


def test_market_stock_impact_api_rejects_timezone_less_cutoff(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    macro_db = tmp_path / "macro.db"
    market_db = tmp_path / "market_history.db"
    _create_macro_db(macro_db)
    _create_market_db(market_db)
    monkeypatch.setenv("STOCKSCOPE_MACRO_DB", str(macro_db))
    monkeypatch.setenv("STOCKSCOPE_MARKET_STORE_DB", str(market_db))

    response = client.get(
        "/api/macro/market-stock-impact",
        params={
            "market": "KOSPI",
            "ticker": "005930",
            "end_date": "2026-09-30",
            "cutoff": "2026-10-01T11:00:00",
        },
    )

    assert response.status_code == 400
    assert response.headers["cache-control"] == "no-store"
    detail = response.json()["detail"]
    assert detail["code"] == "MACRO_IMPACT_INVALID_REQUEST"
    assert "timezone-aware" in detail["message"]


def test_market_stock_impact_api_rejects_invalid_market_and_date(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    macro_db = tmp_path / "macro.db"
    market_db = tmp_path / "market_history.db"
    _create_macro_db(macro_db)
    _create_market_db(market_db)
    monkeypatch.setenv("STOCKSCOPE_MACRO_DB", str(macro_db))
    monkeypatch.setenv("STOCKSCOPE_MARKET_STORE_DB", str(market_db))

    invalid_market = client.get(
        "/api/macro/market-stock-impact",
        params={
            "market": "NYSE",
            "ticker": "005930",
            "end_date": "2026-09-30",
            "cutoff": CUTOFF,
        },
    )
    assert invalid_market.status_code == 400
    assert invalid_market.json()["detail"]["code"] == (
        "MACRO_IMPACT_INVALID_REQUEST"
    )

    invalid_date = client.get(
        "/api/macro/market-stock-impact",
        params={
            "market": "KOSPI",
            "ticker": "005930",
            "end_date": "09/30/2026",
            "cutoff": CUTOFF,
        },
    )
    assert invalid_date.status_code == 400
    assert invalid_date.json()["detail"]["code"] == (
        "MACRO_IMPACT_INVALID_REQUEST"
    )


def test_future_market_rows_do_not_change_past_api_impact_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    macro_db = tmp_path / "macro.db"
    market_db = tmp_path / "market_history.db"
    _create_macro_db(macro_db)
    _create_market_db(market_db)
    monkeypatch.setenv("STOCKSCOPE_MACRO_DB", str(macro_db))
    monkeypatch.setenv("STOCKSCOPE_MARKET_STORE_DB", str(market_db))

    before = _request()
    assert before.status_code == 200
    before_impact = before.json()["impact"]

    store = HistoricalMarketStore(market_db)
    store.put_stock_day(
        "KOSPI",
        "20261001",
        [{"date": "20261001", "code": "005930", "close": 999}],
        stable=True,
    )
    store.put_index_day(
        "KOSPI",
        "20261001",
        {"date": "20261001", "close": 999},
        stable=True,
    )
    store.put_stock_day(
        "KOSPI",
        "20261002",
        [{"date": "20261002", "code": "005930", "close": 888}],
        stable=True,
    )
    store.put_index_day(
        "KOSPI",
        "20261002",
        {"date": "20261002", "close": 888},
        stable=True,
    )

    after = _request()
    assert after.status_code == 200
    after_impact = after.json()["impact"]

    assert after_impact["impact_id"] == before_impact["impact_id"]
    assert after_impact["impact_hash"] == before_impact["impact_hash"]
    assert after_impact["window"] == before_impact["window"]
    assert after_impact["market"] == before_impact["market"]
    assert after_impact["stock"] == before_impact["stock"]
    assert after_impact["relative"] == before_impact["relative"]
