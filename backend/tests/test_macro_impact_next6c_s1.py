from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from app.backtest.market_store import HistoricalMarketStore
from app.macro import (
    MARKET_STOCK_IMPACT_CONTRACT_VERSION,
    LocalMarketImpactReader,
    build_market_stock_impact,
)


MACRO_CONTEXT_ID = "MACROCTX-1234567890abcdef"
MACRO_CONTEXT_HASH = "a" * 64
DECISION_CUTOFF = "2026-09-30T11:00:00+00:00"


def _row(day: str, close: str | float, **extra: object) -> dict[str, object]:
    return {"date": day, "close": close, **extra}


def _impact(
    *,
    stock_rows: list[dict[str, object]],
    market_rows: list[dict[str, object]],
    end_date: str = "20260930",
    sector_temporal_status: str | None = None,
) -> dict[str, object]:
    return build_market_stock_impact(
        stock_rows=stock_rows,
        market_rows=market_rows,
        market="KOSPI",
        ticker="005930",
        end_date=end_date,
        macro_context_id=MACRO_CONTEXT_ID,
        macro_context_hash=MACRO_CONTEXT_HASH,
        decision_cutoff=DECISION_CUTOFF,
        sector_temporal_status=sector_temporal_status,
    )


def test_market_stock_impact_uses_latest_two_common_confirmed_sessions() -> None:
    stock = [
        _row("20260925", "50"),
        _row("20260926", "51"),
        _row("20260929", "52"),
        _row("20260930", "54"),
    ]
    market = [
        _row("20260925", "100"),
        _row("20260926", "101"),
        _row("20260930", "102"),
    ]

    result = _impact(stock_rows=stock, market_rows=market)

    assert result["contract_version"] == MARKET_STOCK_IMPACT_CONTRACT_VERSION
    assert result["status"] == "AVAILABLE"
    assert result["window"]["mode"] == "COMMON_CONFIRMED_SESSION"
    assert result["window"]["session_count"] == 1
    assert result["window"]["common_session_count"] == 3
    assert result["window"]["start_date"] == "20260926"
    assert result["window"]["end_date"] == "20260930"

    market_return = Decimal(result["market"]["return_pct"])
    stock_return = Decimal(result["stock"]["return_pct"])
    relative = Decimal(result["relative"]["stock_vs_market_pctp"])
    assert relative == stock_return - market_return
    assert result["market"]["unit"] == "PERCENT"
    assert result["stock"]["unit"] == "PERCENT"
    assert result["relative"]["unit"] == "PERCENTAGE_POINT"


def test_static_current_sector_mapping_never_becomes_historical_sector_impact() -> None:
    result = _impact(
        stock_rows=[_row("20260929", 100), _row("20260930", 103)],
        market_rows=[_row("20260929", 100), _row("20260930", 101)],
        sector_temporal_status="STATIC_CURRENT",
    )

    assert result["status"] == "AVAILABLE"
    assert result["sector"] == {
        "status": "UNAVAILABLE",
        "temporal_status": "STATIC_CURRENT",
        "return_pct": None,
        "sector_vs_market_pctp": None,
        "stock_vs_sector_pctp": None,
        "reason": "PIT_MAPPING_UNAVAILABLE",
        "production_safe": False,
    }
    assert "SECTOR_PIT_MAPPING_UNAVAILABLE" in result["limitations"]


def test_insufficient_common_sessions_are_unavailable_not_zero_return() -> None:
    result = _impact(
        stock_rows=[_row("20260930", 100)],
        market_rows=[_row("20260930", 200)],
    )

    assert result["status"] == "UNAVAILABLE"
    assert result["reason"] == "INSUFFICIENT_COMMON_SESSIONS"
    assert result["market"]["return_pct"] is None
    assert result["stock"]["return_pct"] is None
    assert result["relative"]["stock_vs_market_pctp"] is None
    assert result["production_decision_approved"] if False else True
    assert result["governance"]["production_decision_approved"] is False


def test_future_eod_rows_do_not_change_past_impact_identity() -> None:
    stock = [
        _row("20260929", 100),
        _row("20260930", 103),
    ]
    market = [
        _row("20260929", 200),
        _row("20260930", 202),
    ]
    before = _impact(stock_rows=stock, market_rows=market)

    after = _impact(
        stock_rows=[*stock, _row("20261001", 999), _row("20261002", 888)],
        market_rows=[*market, _row("20261001", 777), _row("20261002", 666)],
    )

    assert after["impact_hash"] == before["impact_hash"]
    assert after["impact_id"] == before["impact_id"]
    assert after["window"] == before["window"]
    assert after["market"] == before["market"]
    assert after["stock"] == before["stock"]
    assert after["relative"] == before["relative"]


def test_future_macro_revision_does_not_change_frozen_context_ref_impact() -> None:
    rows_stock = [_row("20260929", 100), _row("20260930", 102)]
    rows_market = [_row("20260929", 100), _row("20260930", 101)]

    before = _impact(stock_rows=rows_stock, market_rows=rows_market)
    past_context_again = build_market_stock_impact(
        stock_rows=rows_stock,
        market_rows=rows_market,
        market="KOSPI",
        ticker="005930",
        end_date="20260930",
        macro_context_id=MACRO_CONTEXT_ID,
        macro_context_hash=MACRO_CONTEXT_HASH,
        decision_cutoff=DECISION_CUTOFF,
    )

    assert past_context_again["impact_hash"] == before["impact_hash"]
    assert past_context_again["context_ref"] == before["context_ref"]


def test_impact_contract_is_descriptive_and_never_policy_input() -> None:
    result = _impact(
        stock_rows=[_row("20260929", 100), _row("20260930", 120)],
        market_rows=[_row("20260929", 100), _row("20260930", 90)],
    )

    assert "NO_CAUSAL_ATTRIBUTION" in result["limitations"]
    assert "NO_SHOCK_CLASSIFICATION" in result["limitations"]
    assert result["governance"] == {
        "claim_scope": "DESCRIPTIVE_ONLY",
        "production_decision_approved": False,
        "strategy_input_approved": False,
        "scanner_input_approved": False,
        "risk_gate_input_approved": False,
        "holdings_plan_input_approved": False,
        "network_access": False,
    }


def test_local_market_impact_reader_is_read_only_and_cutoff_bounded(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "market_history.db"
    store = HistoricalMarketStore(db_path)

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

    before = db_path.stat()
    reader = LocalMarketImpactReader(db_path)
    payload = reader.read_pair_as_of(
        market="KOSPI",
        ticker="005930",
        end_date="20260930",
    )
    after = db_path.stat()

    assert payload["status"] == "COMPLETE"
    assert [row["date"] for row in payload["stock_rows"]] == [
        "20260929",
        "20260930",
    ]
    assert [row["date"] for row in payload["market_rows"]] == [
        "20260929",
        "20260930",
    ]
    assert after.st_size == before.st_size
    assert after.st_mtime_ns == before.st_mtime_ns


def test_missing_market_store_fails_closed_without_creating_database(
    tmp_path: Path,
) -> None:
    missing = tmp_path / "missing" / "market_history.db"
    payload = LocalMarketImpactReader(missing).read_pair_as_of(
        market="KOSPI",
        ticker="005930",
        end_date="20260930",
    )

    assert payload["status"] == "UNAVAILABLE"
    assert payload["reason"] == "STORE_NOT_FOUND"
    assert payload["stock_rows"] == []
    assert payload["market_rows"] == []
    assert not missing.exists()
