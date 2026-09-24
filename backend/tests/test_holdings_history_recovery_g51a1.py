from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from app.holdings.chart import HoldingsChartService


def _row(day: str, value: int) -> dict:
    return {
        "date": f"{day[:4]}-{day[4:6]}-{day[6:]}",
        "open": value,
        "high": value + 10,
        "low": value - 10,
        "close": value + 2,
        "volume": 1000 + value,
    }


def test_chart_uses_partial_symbol_history_before_latest_confirmed_cutoff(tmp_path: Path) -> None:
    db = tmp_path / "market.db"
    with sqlite3.connect(db) as conn:
        conn.executescript(
            """
            CREATE TABLE stock_daily(
                market TEXT NOT NULL,
                bas_dd TEXT NOT NULL,
                stock_code TEXT NOT NULL,
                row_json TEXT NOT NULL,
                PRIMARY KEY(market,bas_dd,stock_code)
            );
            CREATE TABLE main_index_daily(
                market TEXT NOT NULL,
                bas_dd TEXT NOT NULL,
                row_json TEXT NOT NULL,
                PRIMARY KEY(market,bas_dd)
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
        days = [f"202609{day:02d}" for day in range(1, 23)]
        for index, day in enumerate(days):
            conn.execute(
                "INSERT INTO stock_daily VALUES(?,?,?,?)",
                ("KOSDAQ", day, "190510", json.dumps(_row(day, 15000 + index))),
            )
        # Only the latest day is market-wide complete. Older rows came from
        # selected-symbol recovery and must still be chartable.
        conn.execute(
            "INSERT INTO day_status VALUES(?,?,?,?)",
            ("KOSDAQ", "20260922", "stock", "data"),
        )

    result = HoldingsChartService(db).load(
        market="KOSDAQ",
        ticker="190510",
        chart_range="1m",
    )
    assert result.count == 22
    assert result.from_date == "2026-09-01"
    assert result.to_date == "2026-09-22"


def test_chart_never_reads_symbol_rows_after_latest_confirmed_market_day(tmp_path: Path) -> None:
    db = tmp_path / "market.db"
    with sqlite3.connect(db) as conn:
        conn.executescript(
            """
            CREATE TABLE stock_daily(market TEXT,bas_dd TEXT,stock_code TEXT,row_json TEXT,PRIMARY KEY(market,bas_dd,stock_code));
            CREATE TABLE main_index_daily(market TEXT,bas_dd TEXT,row_json TEXT,PRIMARY KEY(market,bas_dd));
            CREATE TABLE day_status(market TEXT,bas_dd TEXT,kind TEXT,status TEXT,PRIMARY KEY(market,bas_dd,kind));
            """
        )
        for day, value in [("20260922", 15000), ("20260923", 17000)]:
            conn.execute(
                "INSERT INTO stock_daily VALUES(?,?,?,?)",
                ("KOSDAQ", day, "190510", json.dumps(_row(day, value))),
            )
        conn.execute("INSERT INTO day_status VALUES('KOSDAQ','20260922','stock','data')")

    result = HoldingsChartService(db).load(market="KOSDAQ", ticker="190510", chart_range="1m")
    assert result.count == 1
    assert result.to_date == "2026-09-22"


def test_source_contracts_for_recovery_progress() -> None:
    api = Path("backend/app/api/holdings.py").read_text(encoding="utf-8")
    history = Path("backend/app/holdings/history_prepare.py").read_text(encoding="utf-8")
    krx = Path("backend/app/market/providers/krx.py").read_text(encoding="utf-8")
    frontend = Path("frontend/src/services/holdingsApi.ts").read_text(encoding="utf-8")
    workspace = Path("frontend/src/components/HoldingsWorkspace.tsx").read_text(encoding="utf-8")
    css = Path("frontend/src/holdings.css").read_text(encoding="utf-8")

    assert 'analysis/prepare-stream' in api
    assert 'application/x-ndjson' in api
    assert 'progress: Callable[[dict[str, Any]], None] | None = None' in history
    assert 'progress: Callable[[int, int], None] | None = None' in krx
    assert 'prepareHoldingAnalysisWithProgress' in frontend
    assert 'historyProgress.stock_current' in workspace
    assert 'white-space: nowrap' in css
