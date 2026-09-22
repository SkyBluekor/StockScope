from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import sys
from datetime import date, timedelta
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.api import holdings as holdings_api
from app.holdings.chart import HoldingsChartService, RANGE_BARS


def _row(index: int, bas_dd: str) -> dict[str, object]:
    close = 70000 + index * 100
    return {
        "date": f"{bas_dd[:4]}-{bas_dd[4:6]}-{bas_dd[6:]}",
        "code": "005930",
        "name": "삼성전자",
        "open": close - 50,
        "high": close + 250,
        "low": close - 200,
        "close": close,
        "volume": 1_000_000 + index * 10_000,
    }


def _build_market_store(path: Path, count: int = 280) -> None:
    with sqlite3.connect(path) as conn:
        conn.executescript(
            """
            CREATE TABLE stock_daily(
                market TEXT NOT NULL,
                bas_dd TEXT NOT NULL,
                stock_code TEXT NOT NULL,
                row_json TEXT NOT NULL,
                PRIMARY KEY(market,bas_dd,stock_code)
            );
            CREATE TABLE day_status(
                market TEXT NOT NULL,
                bas_dd TEXT NOT NULL,
                kind TEXT NOT NULL,
                status TEXT NOT NULL,
                PRIMARY KEY(market,bas_dd,kind)
            );
            """
        )
        start = date(2025, 1, 1)
        for index in range(count):
            bas_dd = (start + timedelta(days=index)).strftime("%Y%m%d")
            conn.execute(
                "INSERT INTO stock_daily VALUES(?,?,?,?)",
                ("KOSPI", bas_dd, "005930", json.dumps(_row(index, bas_dd), ensure_ascii=False)),
            )
            conn.execute(
                "INSERT INTO day_status VALUES(?,?,?,?)",
                ("KOSPI", bas_dd, "stock", "data"),
            )
        conn.execute(
            "UPDATE day_status SET status='empty' WHERE bas_dd=(SELECT MAX(bas_dd) FROM day_status)"
        )


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_chart_service_ranges_confirmed_only_and_read_only(tmp_path: Path) -> None:
    store = tmp_path / "market.db"
    _build_market_store(store)
    before = _sha(store)
    service = HoldingsChartService(store)

    for chart_range, expected in RANGE_BARS.items():
        result = service.load(market="KOSPI", ticker="005930", chart_range=chart_range)  # type: ignore[arg-type]
        assert result.source == "MARKET_STORE_CONFIRMED_EOD"
        assert result.count == expected
        assert len(result.bars) == expected
        assert list(result.bars) == sorted(result.bars, key=lambda bar: bar.date)
        assert result.bars[-1].date == (date(2025, 1, 1) + timedelta(days=278)).isoformat()
        assert DecimalLike(result.bars[0].low) <= DecimalLike(result.bars[0].open) <= DecimalLike(result.bars[0].high)
        assert DecimalLike(result.bars[0].low) <= DecimalLike(result.bars[0].close) <= DecimalLike(result.bars[0].high)

    assert _sha(store) == before


def DecimalLike(value: str) -> float:
    return float(value)


def test_chart_endpoint_uses_monitored_stock_and_validates_range(tmp_path: Path, monkeypatch) -> None:
    holdings_db = tmp_path / "holdings.db"
    market_db = tmp_path / "market.db"
    _build_market_store(market_db)
    monkeypatch.setenv("STOCKSCOPE_HOLDINGS_DB", str(holdings_db))
    monkeypatch.setenv("STOCKSCOPE_MARKET_STORE_DB", str(market_db))

    app = FastAPI()
    app.include_router(holdings_api.router, prefix="/api")
    client = TestClient(app)

    watched = client.post(
        "/api/holdings/watch",
        json={"market": "KOSPI", "ticker": "005930", "name": "삼성전자"},
    )
    assert watched.status_code == 200, watched.text
    stock_id = watched.json()["stock"]["stock_id"]

    response = client.get(f"/api/holdings/stocks/{stock_id}/chart?range=1m")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["ticker"] == "005930"
    assert body["range"] == "1m"
    assert body["source"] == "MARKET_STORE_CONFIRMED_EOD"
    assert body["count"] == 22
    assert set(body["bars"][0]) == {"date", "open", "high", "low", "close", "volume"}

    invalid = client.get(f"/api/holdings/stocks/{stock_id}/chart?range=2m")
    assert invalid.status_code == 422

    missing = client.get("/api/holdings/stocks/not-found/chart?range=1m")
    assert missing.status_code == 404


def test_chart_implementation_has_no_network_or_paid_chart_dependency() -> None:
    chart_source = Path("backend/app/holdings/chart.py").read_text(encoding="utf-8")
    lowered = chart_source.lower()
    assert "requests" not in lowered
    assert "httpx" not in lowered
    assert "websocket" not in lowered
    assert "kis" not in lowered
    assert "mode=ro" in chart_source

    package = Path("frontend/package.json").read_text(encoding="utf-8")
    for dependency in ("recharts", "chart.js", "lightweight-charts", "highcharts", "plotly"):
        assert dependency not in package.lower()
