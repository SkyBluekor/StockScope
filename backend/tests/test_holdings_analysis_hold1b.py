from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import date, timedelta
from pathlib import Path

import pytest

from app.backtest.scanner import StockScannerService
from app.holdings.analysis import (
    HoldingsAnalysisError,
    SingleStockAnalysisAdapter,
    analyze_single_stock,
)


TARGET_DATE = date(2026, 9, 22)


def _trading_dates(count: int = 130) -> list[date]:
    values = []
    cursor = TARGET_DATE
    while len(values) < count:
        if cursor.weekday() < 5:
            values.append(cursor)
        cursor -= timedelta(days=1)
    return sorted(values)


def _stock_row(index: int, day: date) -> dict:
    close = 70000.0 + index * 120.0
    return {
        "date": day.isoformat(),
        "code": "005930",
        "name": "삼성전자",
        "open": close - 80.0,
        "high": close + 260.0,
        "low": close - 240.0,
        "close": close,
        "volume": 1_500_000 + index * 2500,
        "trade_value": 20_000_000_000 + index * 1_000_000,
        "market_cap": 400_000_000_000_000,
        "change_rate": 0.4,
    }


def _index_row(index: int, day: date) -> dict:
    close = 3000.0 + index * 2.0
    return {
        "date": day.isoformat(),
        "open": close - 2.0,
        "high": close + 5.0,
        "low": close - 5.0,
        "close": close,
        "change_rate": 0.15,
    }


def _build_market_store(path: Path) -> tuple[list[dict], list[dict]]:
    dates = _trading_dates()
    stocks = [_stock_row(i, day) for i, day in enumerate(dates)]
    indices = [_index_row(i, day) for i, day in enumerate(dates)]

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
        for stock, index_row, day in zip(stocks, indices, dates, strict=True):
            bas_dd = day.strftime("%Y%m%d")
            conn.execute(
                "INSERT INTO stock_daily VALUES(?,?,?,?)",
                (
                    "KOSPI",
                    bas_dd,
                    "005930",
                    json.dumps(stock, ensure_ascii=False),
                ),
            )
            conn.execute(
                "INSERT INTO main_index_daily VALUES(?,?,?)",
                (
                    "KOSPI",
                    bas_dd,
                    json.dumps(index_row, ensure_ascii=False),
                ),
            )
            conn.execute(
                "INSERT INTO day_status VALUES(?,?,?,?)",
                ("KOSPI", bas_dd, "stock", "data"),
            )
            conn.execute(
                "INSERT INTO day_status VALUES(?,?,?,?)",
                ("KOSPI", bas_dd, "index", "data"),
            )
    return stocks, indices


@pytest.fixture()
def market_db(tmp_path):
    path = tmp_path / "market_history.db"
    stocks, indices = _build_market_store(path)
    return path, stocks, indices


def _decision_state(candidate_state: str) -> str:
    if candidate_state == "READY":
        return "READY"
    if candidate_state in {"WATCH", "VALIDATION"}:
        return "WATCH"
    return "NO_TRADE"


def test_adapter_matches_production_scanner_current_path(market_db):
    db_path, stocks, indices = market_db
    adapter = SingleStockAnalysisAdapter(market_store_db=db_path)

    result = adapter.analyze(
        market="KOSPI",
        ticker="005930",
        market_date=TARGET_DATE.isoformat(),
    )

    fast_start = TARGET_DATE - timedelta(
        days=StockScannerService.FAST_HISTORY_CALENDAR_DAYS
    )
    stock_rows = [
        row for row in stocks
        if date.fromisoformat(row["date"]) >= fast_start
    ]
    index_rows = [
        row for row in indices
        if date.fromisoformat(row["date"]) >= fast_start
    ]

    scanner = StockScannerService(object(), market_store=object())
    quick = scanner._quick_current_candidate(  # noqa: SLF001
        market="KOSPI",
        latest_date=TARGET_DATE.strftime("%Y%m%d"),
        row=stock_rows[-1],
        stock_rows=stock_rows,
        index_rows=index_rows,
        sector_input=None,
    )
    assert quick is not None
    candidate = scanner._current_candidate(quick)  # noqa: SLF001
    assert candidate is not None

    risk = candidate["entry_risk_guide"]["risk"]
    assert result.strategy_key == candidate["strategy"]
    assert result.action_state == _decision_state(candidate["candidate_state"])
    assert result.risk_state == candidate["risk"]["status"]
    assert result.reference_price == float(candidate["current_price"])
    assert result.stop_price == risk["invalidation_price"]
    assert result.target1_price == risk["target1_price"]
    assert result.target2_price == risk["target2_price"]


def test_same_input_same_fingerprint_and_history_change_changes_it(market_db):
    db_path, _, _ = market_db

    first = analyze_single_stock(
        market="KOSPI",
        ticker="005930",
        market_date=TARGET_DATE.isoformat(),
        market_store_db=db_path,
    )
    second = analyze_single_stock(
        market="KOSPI",
        ticker="005930",
        market_date=TARGET_DATE.isoformat(),
        market_store_db=db_path,
    )
    assert first.input_fingerprint == second.input_fingerprint

    changed_day = (TARGET_DATE - timedelta(days=7)).strftime("%Y%m%d")
    with sqlite3.connect(db_path) as conn:
        raw = conn.execute(
            """
            SELECT row_json FROM stock_daily
            WHERE market='KOSPI' AND bas_dd=? AND stock_code='005930'
            """,
            (changed_day,),
        ).fetchone()
        if raw is None:
            raw = conn.execute(
                """
                SELECT bas_dd,row_json FROM stock_daily
                WHERE market='KOSPI' AND stock_code='005930'
                ORDER BY bas_dd DESC LIMIT 10,1
                """
            ).fetchone()
            changed_day = raw[0]
            payload = json.loads(raw[1])
        else:
            payload = json.loads(raw[0])
        payload["close"] = float(payload["close"]) + 777.0
        conn.execute(
            """
            UPDATE stock_daily SET row_json=?
            WHERE market='KOSPI' AND bas_dd=? AND stock_code='005930'
            """,
            (json.dumps(payload, ensure_ascii=False), changed_day),
        )

    changed = analyze_single_stock(
        market="KOSPI",
        ticker="005930",
        market_date=TARGET_DATE.isoformat(),
        market_store_db=db_path,
    )
    assert changed.input_fingerprint != first.input_fingerprint


def test_missing_market_date_is_error_not_no_trade(market_db):
    db_path, _, _ = market_db
    with pytest.raises(HoldingsAnalysisError) as exc_info:
        analyze_single_stock(
            market="KOSPI",
            ticker="005930",
            market_date="2026-09-23",
            market_store_db=db_path,
        )
    assert exc_info.value.code == "HOLD_ANALYSIS_MARKET_DATE_NOT_FOUND"


def test_missing_stock_is_error_not_no_trade(market_db):
    db_path, _, _ = market_db
    with pytest.raises(HoldingsAnalysisError) as exc_info:
        analyze_single_stock(
            market="KOSPI",
            ticker="000001",
            market_date=TARGET_DATE.isoformat(),
            market_store_db=db_path,
        )
    assert exc_info.value.code == "HOLD_ANALYSIS_STOCK_NOT_FOUND"


def test_analysis_is_read_only_and_has_no_rank_or_live_price_input(market_db, monkeypatch):
    db_path, _, _ = market_db
    before = hashlib.sha256(db_path.read_bytes()).hexdigest()

    async def forbidden_run(*args, **kwargs):
        raise AssertionError("StockScannerService.run() must not be called")

    monkeypatch.setattr(StockScannerService, "run", forbidden_run)

    result = analyze_single_stock(
        market="KOSPI",
        ticker="005930",
        market_date=TARGET_DATE.isoformat(),
        market_store_db=db_path,
    )
    after = hashlib.sha256(db_path.read_bytes()).hexdigest()

    assert before == after
    assert "rank" not in result.to_dict()
    assert "internal_rank" not in json.dumps(result.snapshot)
    assert "scanner_rank" not in json.dumps(result.snapshot)

    with pytest.raises(TypeError):
        analyze_single_stock(
            market="KOSPI",
            ticker="005930",
            market_date=TARGET_DATE.isoformat(),
            market_store_db=db_path,
            reference_price=99999,  # type: ignore[call-arg]
        )


def test_analysis_module_has_no_kis_or_holdings_db_dependency():
    source = Path("backend/app/holdings/analysis.py").read_text(encoding="utf-8")
    assert "integrations.kis" not in source
    assert "HoldingsCatalog" not in source
    assert "holdings.db" not in source
    assert "self.scanner.run(" not in source
