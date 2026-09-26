from __future__ import annotations

import json
import sqlite3
import sys
from datetime import date, timedelta
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.api import data_sources as data_sources_api


def _build_market_store(path: Path, count: int = 80) -> None:
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
        start = date(2026, 1, 1)
        for index in range(count):
            bas_dd = (start + timedelta(days=index)).strftime("%Y%m%d")
            close = 50000 + index * 100
            payload = {
                "date": f"{bas_dd[:4]}-{bas_dd[4:6]}-{bas_dd[6:]}",
                "code": "005930",
                "name": "삼성전자",
                "open": close - 50,
                "high": close + 200,
                "low": close - 200,
                "close": close,
                "volume": 1_000_000 + index * 1000,
            }
            conn.execute(
                "INSERT INTO stock_daily VALUES(?,?,?,?)",
                ("KOSPI", bas_dd, "005930", json.dumps(payload, ensure_ascii=False)),
            )
            conn.execute(
                "INSERT INTO day_status VALUES(?,?,?,?)",
                ("KOSPI", bas_dd, "stock", "data"),
            )


def test_stock_analysis_chart_endpoint_does_not_require_holdings_registration(tmp_path: Path, monkeypatch) -> None:
    market_db = tmp_path / "market.db"
    _build_market_store(market_db)
    monkeypatch.setenv("STOCKSCOPE_MARKET_STORE_DB", str(market_db))

    app = FastAPI()
    app.include_router(data_sources_api.router, prefix="/api")
    client = TestClient(app)

    response = client.get("/api/stocks/005930/chart?market=KOSPI&range=3m")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["market"] == "KOSPI"
    assert body["ticker"] == "005930"
    assert body["range"] == "3m"
    assert body["source"] == "MARKET_STORE_CONFIRMED_EOD"
    assert body["count"] == 66
    assert len(body["bars"]) == 66


def test_stock_analysis_chart_endpoint_validates_range_and_missing_stock(tmp_path: Path, monkeypatch) -> None:
    market_db = tmp_path / "market.db"
    _build_market_store(market_db)
    monkeypatch.setenv("STOCKSCOPE_MARKET_STORE_DB", str(market_db))

    app = FastAPI()
    app.include_router(data_sources_api.router, prefix="/api")
    client = TestClient(app)

    invalid = client.get("/api/stocks/005930/chart?market=KOSPI&range=2m")
    assert invalid.status_code == 422

    missing = client.get("/api/stocks/000001/chart?market=KOSPI&range=1m")
    assert missing.status_code == 404
    assert missing.json()["detail"]["code"] == "HOLD_CHART_STOCK_NOT_FOUND"


def test_stock_analysis_frontend_contract() -> None:
    workspace = Path("frontend/src/components/StockAnalysisWorkspace.tsx").read_text(encoding="utf-8")
    app = Path("frontend/src/App.tsx").read_text(encoding="utf-8")
    chart = Path("frontend/src/components/StockAnalysisPriceChart.tsx").read_text(encoding="utf-8")

    assert "왜 이런 판단인가" in workspace
    assert "상세 기술지표 보기" in workspace
    assert "공식 확정 EOD 기준" in workspace
    assert "StockAnalysisPriceChart" in workspace
    assert "가상 분석 조건" in app
    assert "실제 보유 수량·평균단가와 원장을 변경하지 않습니다." in app
    assert "공식 확정 일봉 분석을 덮어쓰지 않습니다." in app
    assert "종목 종목 분석" not in app
    assert "INPUT UX v0.15.2" not in app
    assert "fetchStockChart" in chart
