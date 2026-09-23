from __future__ import annotations

import json
import sqlite3
from datetime import date, timedelta
from pathlib import Path

from app.simulation.validation_catalog import HistoricalValidationCatalog
from app.simulation.validation_outcome import HistoricalValidationOutcomeService


def _business_days(start: date, count: int) -> list[date]:
    rows: list[date] = []
    cursor = start
    while len(rows) < count:
        if cursor.weekday() < 5:
            rows.append(cursor)
        cursor += timedelta(days=1)
    return rows


def _write_market_db(path: Path) -> tuple[str, list[str]]:
    signal = date(2026, 1, 2)
    future = _business_days(signal + timedelta(days=1), 20)
    signal_key = signal.strftime("%Y%m%d")
    future_keys = [day.strftime("%Y%m%d") for day in future]

    with sqlite3.connect(path) as conn:
        conn.executescript(
            """
            CREATE TABLE day_status(
                market TEXT NOT NULL,
                bas_dd TEXT NOT NULL,
                kind TEXT NOT NULL,
                status TEXT NOT NULL,
                PRIMARY KEY(market,bas_dd,kind)
            );
            CREATE TABLE stock_daily(
                market TEXT NOT NULL,
                bas_dd TEXT NOT NULL,
                stock_code TEXT NOT NULL,
                row_json TEXT NOT NULL,
                PRIMARY KEY(market,bas_dd,stock_code)
            );
            """
        )
        conn.executemany(
            "INSERT INTO day_status(market,bas_dd,kind,status) VALUES('KOSPI',?,'stock','data')",
            [(key,) for key in [signal_key, *future_keys]],
        )

        def row(code: str, key: str, close: float, high: float | None = None, low: float | None = None):
            payload = {
                "date": key, "code": code, "open": close,
                "high": high if high is not None else close + 1,
                "low": low if low is not None else close - 1,
                "close": close, "volume": 1000,
            }
            conn.execute(
                "INSERT INTO stock_daily(market,bas_dd,stock_code,row_json) VALUES('KOSPI',?,?,?)",
                (key, code, json.dumps(payload)),
            )

        row("000001", signal_key, 100)
        for index, key in enumerate(future_keys, start=1):
            close, high, low = 100 + index, 101 + index, 99 + index
            if index == 3:
                high, low = 116, 89
            if index == 12:
                high = 126
            if index == 5:
                close = 105
            elif index == 10:
                close = 110
            elif index == 20:
                close = 120
            row("000001", key, close, high=high, low=low)

        second_signal_key = future_keys[12]
        row("000002", second_signal_key, 200)
        for index, key in enumerate(future_keys[13:], start=1):
            row("000002", key, 200 + index)

    return signal.isoformat(), [f"{key[:4]}-{key[4:6]}-{key[6:8]}" for key in future_keys]


def _snapshot() -> dict:
    return {
        "action": "WAIT",
        "candidate_state": "WATCH",
        "entry_risk_guide": {
            "price_rule": {"kind": "RANGE", "range_low": 99, "range_high": 101, "trigger_price": None},
            "risk": {"invalidation_price": 90, "target1_price": 115, "target2_price": 125},
        },
    }


def _validation(tmp_path: Path, signal_date: str, future_dates: list[str]):
    catalog = HistoricalValidationCatalog(tmp_path / "simulation.db")
    catalog.initialize()
    draft = catalog.create_draft(
        name="VAL.3-A1 fixture",
        market_scope="KOSPI",
        requested_period_type="custom",
        requested_start_month="2026-01",
        requested_end_month="2026-02",
        resolved_start_date=signal_date,
        resolved_end_date=future_dates[12],
        trading_day_count=2,
    )
    catalog.save_completed_day(
        validation_id=draft.id, trading_date=signal_date,
        scanner_version=draft.scanner_version, market_scope="KOSPI",
        scanner_cache_hit=False, partial_data=False,
        input_fingerprint={"fixture": 1}, market_summary={}, summary={}, methodology={},
        diagnostics={"network_requests": 0},
        candidates=[{
            "market": "KOSPI", "ticker": "000001", "name": "Fixture A",
            "rank": 1, "result_bucket": "TOP",
            "strategy": "momentum_continuation", "decision_status": "WATCH",
            "snapshot": _snapshot(),
        }],
    )
    catalog.save_completed_day(
        validation_id=draft.id, trading_date=future_dates[12],
        scanner_version=draft.scanner_version, market_scope="KOSPI",
        scanner_cache_hit=False, partial_data=False,
        input_fingerprint={"fixture": 2}, market_summary={}, summary={}, methodology={},
        diagnostics={"network_requests": 0},
        candidates=[{
            "market": "KOSPI", "ticker": "000002", "name": "Fixture B",
            "rank": 1, "result_bucket": "TOP",
            "strategy": "pullback", "decision_status": "READY",
            "snapshot": _snapshot(),
        }],
    )
    with catalog.connect() as conn:
        conn.execute(
            "UPDATE historical_validation_run SET status='COMPLETED',processed_day_count=trading_day_count WHERE id=?",
            (draft.id,),
        )
    return catalog, draft.id


def test_forward_outcomes_are_d_plus_1_and_maturity_aware(tmp_path: Path):
    market_db = tmp_path / "market.db"
    signal_date, future_dates = _write_market_db(market_db)
    catalog, validation_id = _validation(tmp_path, signal_date, future_dates)

    service = HistoricalValidationOutcomeService(catalog, market_db)
    summary = service.refresh(validation_id)
    outcomes = service.list_outcomes(validation_id)
    first = next(row for row in outcomes if row["ticker"] == "000001")
    second = next(row for row in outcomes if row["ticker"] == "000002")

    assert first["reference_price"] == "100"
    assert first["return_5d"] == 5.0
    assert first["return_10d"] == 10.0
    assert first["return_20d"] == 20.0
    assert first["available_trading_days"] == 20
    assert second["available_trading_days"] == 7
    assert second["return_5d"] is not None
    assert second["return_10d"] is None
    assert second["return_20d"] is None
    assert summary["horizons"]["5d"]["sample_count"] == 2
    assert summary["horizons"]["10d"]["sample_count"] == 1
    assert summary["horizons"]["20d"]["sample_count"] == 1
    assert summary["replay"]["consistent"] is True


def test_mfe_mae_and_same_day_touch_order_is_not_inferred(tmp_path: Path):
    market_db = tmp_path / "market.db"
    signal_date, future_dates = _write_market_db(market_db)
    catalog, validation_id = _validation(tmp_path, signal_date, future_dates)

    service = HistoricalValidationOutcomeService(catalog, market_db)
    service.refresh(validation_id)
    first = next(row for row in service.list_outcomes(validation_id) if row["ticker"] == "000001")

    assert first["mfe_pct"] == 26.0
    assert first["mae_pct"] == -11.0
    assert first["entry_touched"] == 1
    assert first["stop_touched"] == 1
    assert first["target1_touched"] == 1
    assert first["target2_touched"] == 1
    assert first["stop_touch_date"] == first["target1_touch_date"]


def test_market_store_is_read_only_and_scanner_is_not_called() -> None:
    source = Path("backend/app/simulation/validation_outcome.py").read_text(encoding="utf-8")
    assert "?mode=ro" in source
    assert "PRAGMA query_only=ON" in source
    assert "StockScannerService" not in source
    assert "KrxProvider" not in source
    assert "requests." not in source
    assert "httpx." not in source
    assert "HistoricalMarketStore(" not in source
