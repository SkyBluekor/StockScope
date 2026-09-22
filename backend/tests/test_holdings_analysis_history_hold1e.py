from __future__ import annotations

import sqlite3
from decimal import Decimal
from pathlib import Path

import pytest

from app.holdings import HoldingsCatalog
from app.holdings.analysis import HoldingsAnalysisError, SingleStockAnalysis
from app.holdings.analysis_history import (
    HoldingAnalysisHistoryService,
    HoldingsAnalysisHistoryError,
)
from app.holdings.lifecycle import PositionLifecycleService


def _analysis(
    *,
    market_date: str = "2026-09-18",
    fingerprint: str = "fp-1",
    strategy: str = "ma20_rebound",
    action: str = "WATCH",
    risk: str = "READY",
    reference: float = 261000.0,
    stop: float | None = 254124.8,
    target1: float | None = 271000.0,
    target2: float | None = 274750.4,
    scanner_version: str = "0.21.3.7",
    engine_version: str = "HOLD_SINGLE_STOCK_V1",
    policy_version: str = "P1",
) -> SingleStockAnalysis:
    return SingleStockAnalysis(
        market="KOSPI",
        ticker="005930",
        market_date=market_date,
        strategy_key=strategy,
        action_state=action,
        risk_state=risk,
        reference_price=reference,
        stop_price=stop,
        target1_price=target1,
        target2_price=target2,
        condition_state={"state": "READY"},
        readiness_state={"status": action},
        scanner_version=scanner_version,
        analysis_engine_version=engine_version,
        policy_version=policy_version,
        input_fingerprint=fingerprint,
        source_versions={"fixture": fingerprint},
        snapshot={"strategy": strategy, "action": action},
    )


class MutableAnalyzer:
    def __init__(self, result: SingleStockAnalysis):
        self.result = result
        self.calls = []

    def __call__(self, **kwargs):
        self.calls.append(kwargs)
        return self.result


@pytest.fixture()
def env(tmp_path):
    catalog = HoldingsCatalog(tmp_path / "holdings.db")
    catalog.initialize()
    stock = catalog.create_monitored_stock(
        market="KOSPI",
        ticker="005930",
        name="삼성전자",
        watch_enabled=True,
    )
    analyzer = MutableAnalyzer(_analysis())
    ticks = iter(
        [f"2026-09-22T12:00:{second:02d}+00:00" for second in range(40)]
    )
    service = HoldingAnalysisHistoryService(
        catalog,
        analyzer=analyzer,
        market_store_db=tmp_path / "market.db",
        clock=lambda: next(ticks),
    )
    return catalog, stock, analyzer, service


def _counts(catalog: HoldingsCatalog):
    with catalog.connection() as conn:
        return {
            "days": conn.execute(
                "SELECT COUNT(*) FROM stock_analysis_day"
            ).fetchone()[0],
            "revisions": conn.execute(
                "SELECT COUNT(*) FROM stock_analysis_revision"
            ).fetchone()[0],
        }


def _schema(catalog: HoldingsCatalog):
    with catalog.connection() as conn:
        rows = conn.execute(
            """
            SELECT type,name,sql FROM sqlite_master
            WHERE type IN ('table','index','trigger')
            ORDER BY type,name
            """
        ).fetchall()
    return [(row["type"], row["name"], row["sql"]) for row in rows]


def test_first_analysis_creates_day_revision_and_current(env):
    catalog, stock, analyzer, service = env
    stored = service.analyze_and_record(
        monitored_stock_id=stock.id,
        market_date="2026-09-18",
    )
    assert stored.created_revision is True
    assert stored.revision.revision_no == 1
    assert stored.revision.revision_reason == "INITIAL"
    assert stored.revision.strategy_key == "ma20_rebound"
    assert _counts(catalog) == {"days": 1, "revisions": 1}

    with catalog.connection() as conn:
        day = conn.execute(
            "SELECT * FROM stock_analysis_day WHERE id=?",
            (stored.analysis_day_id,),
        ).fetchone()
    assert day["current_revision_id"] == stored.revision.id
    assert analyzer.calls[0]["market"] == "KOSPI"
    assert analyzer.calls[0]["ticker"] == "005930"
    assert analyzer.calls[0]["market_date"] == "2026-09-18"


def test_same_fingerprint_reuses_revision(env):
    catalog, stock, analyzer, service = env
    first = service.analyze_and_record(
        monitored_stock_id=stock.id,
        market_date="2026-09-18",
    )
    second = service.analyze_and_record(
        monitored_stock_id=stock.id,
        market_date="2026-09-18",
    )
    assert second.revision.id == first.revision.id
    assert second.created_revision is False
    assert second.promoted_current is False
    assert _counts(catalog) == {"days": 1, "revisions": 1}


@pytest.mark.parametrize(
    ("changes", "expected_reason"),
    [
        ({"fingerprint": "fp-2", "reference": 262000.0}, "INPUT_CHANGED"),
        (
            {
                "fingerprint": "fp-engine",
                "engine_version": "HOLD_SINGLE_STOCK_V2",
            },
            "ENGINE_CHANGED",
        ),
        (
            {
                "fingerprint": "fp-policy",
                "policy_version": "P2",
            },
            "POLICY_CHANGED",
        ),
    ],
)
def test_changed_input_creates_immutable_new_revision(env, changes, expected_reason):
    catalog, stock, analyzer, service = env
    first = service.analyze_and_record(
        monitored_stock_id=stock.id,
        market_date="2026-09-18",
    )

    second_result = _analysis(
        fingerprint=changes.get("fingerprint", "fp-2"),
        reference=changes.get("reference", 261000.0),
        engine_version=changes.get("engine_version", "HOLD_SINGLE_STOCK_V1"),
        policy_version=changes.get("policy_version", "P1"),
    )
    analyzer.result = second_result
    second = service.analyze_and_record(
        monitored_stock_id=stock.id,
        market_date="2026-09-18",
    )

    assert second.created_revision is True
    assert second.revision.revision_no == 2
    assert second.revision.revision_reason == expected_reason
    revisions = service.get_day_revisions(
        monitored_stock_id=stock.id,
        market_date="2026-09-18",
    )
    assert [r.id for r in revisions] == [first.revision.id, second.revision.id]
    assert revisions[0].input_fingerprint == "fp-1"
    assert service.get_current_analysis(stock.id).id == second.revision.id


def test_new_market_date_creates_new_day_and_revision_number_restarts(env):
    catalog, stock, analyzer, service = env
    first = service.analyze_and_record(
        monitored_stock_id=stock.id,
        market_date="2026-09-18",
    )
    analyzer.result = _analysis(
        market_date="2026-09-21",
        fingerprint="day-2",
        strategy="trend_recovery",
        action="READY",
        reference=268000.0,
    )
    second = service.analyze_and_record(
        monitored_stock_id=stock.id,
        market_date="2026-09-21",
    )
    assert second.analysis_day_id != first.analysis_day_id
    assert second.revision.revision_no == 1
    assert second.revision.revision_reason == "INITIAL"
    assert _counts(catalog) == {"days": 2, "revisions": 2}


def test_analysis_failure_creates_no_revision_and_keeps_current(env):
    catalog, stock, analyzer, service = env
    first = service.analyze_and_record(
        monitored_stock_id=stock.id,
        market_date="2026-09-18",
    )

    def fail(**kwargs):
        raise HoldingsAnalysisError(
            "HOLD_ANALYSIS_MARKET_DATE_NOT_FOUND",
            "no exact eod",
        )

    service.analyzer = fail
    with pytest.raises(HoldingsAnalysisHistoryError) as exc_info:
        service.analyze_and_record(
            monitored_stock_id=stock.id,
            market_date="2026-09-21",
        )
    assert exc_info.value.code == "HOLD_ANALYSIS_HISTORY_FAILED"
    assert exc_info.value.cause_code == "HOLD_ANALYSIS_MARKET_DATE_NOT_FOUND"
    assert _counts(catalog) == {"days": 1, "revisions": 1}
    assert service.get_current_analysis(stock.id).id == first.revision.id


def test_result_date_mismatch_is_not_persisted(env):
    catalog, stock, analyzer, service = env
    analyzer.result = _analysis(market_date="2026-09-17")
    with pytest.raises(HoldingsAnalysisHistoryError) as exc_info:
        service.analyze_and_record(
            monitored_stock_id=stock.id,
            market_date="2026-09-18",
        )
    assert exc_info.value.code == "HOLD_ANALYSIS_HISTORY_DATE_INVALID"
    assert _counts(catalog) == {"days": 0, "revisions": 0}


def test_analysis_timeline_uses_current_revision_and_computes_changes(env):
    catalog, stock, analyzer, service = env
    service.analyze_and_record(
        monitored_stock_id=stock.id,
        market_date="2026-09-18",
    )
    analyzer.result = _analysis(
        fingerprint="same-day-new",
        strategy="pullback",
        reference=262000.0,
    )
    same_day = service.analyze_and_record(
        monitored_stock_id=stock.id,
        market_date="2026-09-18",
    )

    analyzer.result = _analysis(
        market_date="2026-09-21",
        fingerprint="next-day",
        strategy="trend_recovery",
        action="READY",
        reference=268000.0,
        stop=260000.0,
        target1=280000.0,
        target2=290000.0,
    )
    service.analyze_and_record(
        monitored_stock_id=stock.id,
        market_date="2026-09-21",
    )

    timeline = service.get_analysis_timeline(stock.id)
    assert [item.market_date for item in timeline] == [
        "2026-09-21",
        "2026-09-18",
    ]
    assert timeline[1].revision_id == same_day.revision.id
    newest = timeline[0]
    assert newest.previous_strategy_key == "pullback"
    assert newest.strategy_changed is True
    assert newest.action_changed is True
    assert newest.risk_changed is False
    assert newest.reference_price_delta == Decimal("6000")
    assert newest.stop_price_changed is True


def test_buy_event_revision_reference_never_moves_with_current_revision(env):
    catalog, stock, analyzer, service = env
    first = service.analyze_and_record(
        monitored_stock_id=stock.id,
        market_date="2026-09-18",
    )
    account = catalog.create_position_account(
        provider="MANUAL",
        account_kind="MANUAL",
        display_name="수동",
    )
    lifecycle = PositionLifecycleService(catalog)
    bought = lifecycle.record_buy(
        monitored_stock_id=stock.id,
        position_account_id=account.id,
        quantity="1",
        unit_price="261000",
        effective_at="2026-09-22T12:30:00+00:00",
        analysis_revision_id=first.revision.id,
    )

    analyzer.result = _analysis(
        fingerprint="fp-new",
        strategy="trend_recovery",
    )
    second = service.analyze_and_record(
        monitored_stock_id=stock.id,
        market_date="2026-09-18",
    )
    assert second.revision.id != first.revision.id
    event = catalog.list_position_events(bought.position.id)[0]
    assert event.analysis_revision_id == first.revision.id


def test_analysis_targets_are_watch_or_open_position_and_deduplicated(env):
    catalog, stock, analyzer, service = env
    catalog.set_watch_enabled(stock.id, False)
    assert service.list_analysis_targets() == ()

    manual = catalog.create_position_account(
        provider="MANUAL",
        account_kind="MANUAL",
        display_name="m1",
    )
    virtual = catalog.create_position_account(
        provider="VIRTUAL",
        account_kind="VIRTUAL",
        display_name="v1",
    )
    catalog.open_position(
        monitored_stock_id=stock.id,
        position_account_id=manual.id,
        opened_reason="MANUAL",
        current_quantity="1",
        current_average_price="1",
        current_cost_basis="1",
    )
    catalog.open_position(
        monitored_stock_id=stock.id,
        position_account_id=virtual.id,
        opened_reason="VIRTUAL",
        current_quantity="2",
        current_average_price="1",
        current_cost_basis="2",
    )
    targets = service.list_analysis_targets()
    assert [item.id for item in targets] == [stock.id]

    other = catalog.create_monitored_stock(
        market="KOSPI",
        ticker="000660",
        name="SK하이닉스",
        watch_enabled=True,
    )
    assert {item.id for item in service.list_analysis_targets()} == {
        stock.id,
        other.id,
    }


def test_combined_timeline_projects_analysis_and_position_events(env):
    catalog, stock, analyzer, service = env
    stored = service.analyze_and_record(
        monitored_stock_id=stock.id,
        market_date="2026-09-18",
    )
    account = catalog.create_position_account(
        provider="MANUAL",
        account_kind="MANUAL",
        display_name="수동",
    )
    lifecycle = PositionLifecycleService(catalog)
    lifecycle.record_buy(
        monitored_stock_id=stock.id,
        position_account_id=account.id,
        quantity="2",
        unit_price="260000",
        effective_at="2026-09-22T13:00:00+00:00",
        analysis_revision_id=stored.revision.id,
    )

    timeline = service.get_stock_timeline(stock.id)
    assert {item.kind for item in timeline} == {"ANALYSIS", "POSITION_EVENT"}
    position_item = next(item for item in timeline if item.kind == "POSITION_EVENT")
    assert position_item.event_type == "BUY"
    assert position_item.analysis_revision_id == stored.revision.id


def test_latest_confirmed_date_is_resolved_before_exact_analysis(env, tmp_path):
    catalog, stock, analyzer, service = env
    market_db = tmp_path / "market_history.db"
    with sqlite3.connect(market_db) as conn:
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
        for day in ("20260918", "20260921"):
            conn.execute(
                "INSERT INTO stock_daily VALUES(?,?,?,?)",
                ("KOSPI", day, "005930", "{}"),
            )
        conn.execute(
            "INSERT INTO day_status VALUES(?,?,?,?)",
            ("KOSPI", "20260918", "stock", "data"),
        )
        conn.execute(
            "INSERT INTO day_status VALUES(?,?,?,?)",
            ("KOSPI", "20260918", "index", "data"),
        )
        conn.execute(
            "INSERT INTO day_status VALUES(?,?,?,?)",
            ("KOSPI", "20260921", "stock", "data"),
        )
        conn.execute(
            "INSERT INTO day_status VALUES(?,?,?,?)",
            ("KOSPI", "20260921", "index", "missing"),
        )

    service.market_store_db = market_db
    assert service.latest_confirmed_market_date(stock.id) == "2026-09-18"
    analyzer.result = _analysis(market_date="2026-09-18")
    service.analyze_latest_confirmed(monitored_stock_id=stock.id)
    assert analyzer.calls[-1]["market_date"] == "2026-09-18"


def test_schema_is_unchanged_and_history_has_no_kis_scanner_or_live_price_dependency(env):
    catalog, stock, analyzer, service = env
    before = _schema(catalog)
    service.analyze_and_record(
        monitored_stock_id=stock.id,
        market_date="2026-09-18",
    )
    after = _schema(catalog)
    assert after == before

    source = Path("backend/app/holdings/analysis_history.py").read_text(
        encoding="utf-8"
    )
    assert "app.integrations.kis" not in source
    assert "StockScannerService" not in source
    assert "current_price" not in source
    assert "record_buy(" not in source
    assert "record_sell(" not in source
