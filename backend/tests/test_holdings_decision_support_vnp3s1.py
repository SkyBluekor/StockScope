from __future__ import annotations

import json
import sqlite3
from decimal import Decimal
from pathlib import Path

import pytest

from app.holdings import HoldingsCatalog, PositionLifecycleService
from app.holdings.decision_support import (
    HoldingDecisionSupportService,
    HoldingsDecisionSupportError,
)
from app.holdings.management import (
    HoldingManagementService,
    HoldingsManagementError,
)
from tools.data.common import DataToolError
from tools.data.migrate_holdings_decision_vnp3s1 import (
    migrate_holdings_decision_store,
)

T0 = "2026-09-24T09:00:00+09:00"
T1 = "2026-09-24T10:00:00+09:00"
T2 = "2026-09-24T11:00:00+09:00"


def _market(path: Path, close: str = "100") -> None:
    with sqlite3.connect(path) as conn:
        conn.executescript(
            """
            CREATE TABLE day_status(
                market TEXT,bas_dd TEXT,kind TEXT,status TEXT
            );
            CREATE TABLE stock_daily(
                market TEXT,bas_dd TEXT,stock_code TEXT,row_json TEXT
            );
            """
        )
        payload = {
            "date": "2026-09-24",
            "open": close,
            "high": close,
            "low": close,
            "close": close,
            "volume": "1000",
        }
        conn.execute(
            "INSERT INTO day_status VALUES('KOSPI','20260924','stock','data')"
        )
        conn.execute(
            "INSERT INTO stock_daily VALUES('KOSPI','20260924','005930',?)",
            (json.dumps(payload),),
        )


def _env(tmp_path: Path, close: str = "100", migrate: bool = True):
    hdb = tmp_path / "holdings.db"
    mdb = tmp_path / "market.db"
    _market(mdb, close)
    catalog = HoldingsCatalog(hdb)
    catalog.initialize()
    if migrate:
        migrate_holdings_decision_store(hdb)
    life = PositionLifecycleService(catalog)
    account = catalog.create_position_account(
        provider="MANUAL",
        account_kind="MANUAL",
        display_name="수동 기록",
    )
    opened = life.register_initial_holding(
        market="KOSPI",
        ticker="005930",
        name="삼성전자",
        position_account_id=account.id,
        quantity="10",
        average_price="100",
        effective_at=T0,
    )
    return catalog, life, opened, mdb


def _rev(
    catalog: HoldingsCatalog,
    stock_id: str,
    fingerprint: str,
    stop: str,
    *,
    t1: str = "120",
    t2: str = "130",
    market_date: str = "2026-09-24",
):
    day = catalog.get_or_create_analysis_day(
        monitored_stock_id=stock_id,
        market_date=market_date,
    )
    revision = catalog.append_analysis_revision(
        analysis_day_id=day.id,
        input_fingerprint=fingerprint,
        strategy_key="trend_following",
        action_state="WATCH",
        risk_state="READY",
        reference_price="100",
        stop_price=stop,
        target1_price=t1,
        target2_price=t2,
        scanner_version="test",
        analysis_engine_version="test",
        policy_version="test",
        source_versions={"fixture": fingerprint},
        snapshot={"fixture": fingerprint},
        computed_at=f"{market_date}T00:00:00+00:00",
    )
    catalog.promote_current_revision(
        analysis_day_id=day.id,
        revision_id=revision.id,
    )
    return revision


def _apply(
    catalog: HoldingsCatalog,
    mdb: Path,
    position_id: str,
    revision_id: str,
):
    return HoldingManagementService(
        catalog,
        market_store_db=mdb,
    ).apply_analysis_plan(
        position_id=position_id,
        analysis_revision_id=revision_id,
        applied_at=T1,
    )


def test_migration_is_explicit_idempotent_and_no_backfill(tmp_path: Path):
    catalog, _, _, _ = _env(tmp_path, migrate=False)

    first = migrate_holdings_decision_store(catalog.db_path)
    second = migrate_holdings_decision_store(catalog.db_path)

    assert first == second
    assert first["historical_decision_backfill_performed"] is False
    with sqlite3.connect(catalog.db_path) as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM holding_decision_record"
        ).fetchone()[0] == 0
        assert conn.execute(
            "SELECT COUNT(*) FROM holding_decision_resolution"
        ).fetchone()[0] == 0


def test_migration_rolls_back_on_incompatible_existing_table(tmp_path: Path):
    catalog, _, _, _ = _env(tmp_path, migrate=False)
    with sqlite3.connect(catalog.db_path) as conn:
        conn.execute(
            "CREATE TABLE holding_decision_record(id TEXT PRIMARY KEY)"
        )

    with pytest.raises(DataToolError):
        migrate_holdings_decision_store(catalog.db_path)

    with sqlite3.connect(catalog.db_path) as conn:
        names = {
            str(row[0])
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        assert "holding_decision_schema_meta" not in names
        assert "holding_decision_resolution" not in names


def test_missing_migration_does_not_change_existing_holdings(tmp_path: Path):
    catalog, _, opened, mdb = _env(tmp_path, migrate=False)
    _rev(catalog, opened.stock_id, "r1", "90")
    service = HoldingDecisionSupportService(
        catalog,
        market_store_db=mdb,
    )

    with pytest.raises(HoldingsDecisionSupportError) as caught:
        service.evaluate(opened.position.id)

    assert caught.value.code == "HOLD_DECISION_MIGRATION_REQUIRED"
    position = catalog.get_position(opened.position.id)
    assert position.current_quantity == Decimal("10")
    assert position.current_average_price == Decimal("100")


@pytest.mark.parametrize(
    ("close", "expected_status", "primary"),
    [
        ("85", "ACTIONABLE", "STOP"),
        ("100", "ACTIONABLE", "HOLD"),
        ("121", "REVIEW_REQUIRED", "TAKE_PROFIT"),
        ("131", "REVIEW_REQUIRED", "TAKE_PROFIT"),
    ],
)
def test_decision_uses_only_applied_plan_price_states(
    tmp_path: Path,
    close: str,
    expected_status: str,
    primary: str,
):
    catalog, _, opened, mdb = _env(tmp_path, close=close)
    revision = _rev(catalog, opened.stock_id, "r1", "90")
    plan = _apply(
        catalog,
        mdb,
        opened.position.id,
        revision.id,
    )
    service = HoldingDecisionSupportService(
        catalog,
        market_store_db=mdb,
    )

    before = catalog.get_position(opened.position.id)
    decision = service.evaluate(opened.position.id)
    after = catalog.get_position(opened.position.id)

    assert decision["status"] == expected_status
    assert decision["primary_action"] == primary
    assert decision["source_active_plan_id"] == plan.id
    assert after.current_quantity == before.current_quantity
    assert after.current_average_price == before.current_average_price


def test_add_is_always_blocked_without_verified_policy(tmp_path: Path):
    catalog, _, opened, mdb = _env(tmp_path)
    revision = _rev(catalog, opened.stock_id, "r1", "90")
    _apply(catalog, mdb, opened.position.id, revision.id)
    service = HoldingDecisionSupportService(
        catalog,
        market_store_db=mdb,
    )

    decision = service.evaluate(opened.position.id)
    add = next(
        item for item in decision["alternatives"]
        if item["action"] == "ADD"
    )

    assert add["state"] == "BLOCKED"
    with pytest.raises(HoldingsDecisionSupportError) as caught:
        service.resolve(
            decision_id=decision["decision_id"],
            resolution_type="ACKNOWLEDGED",
            selected_action="ADD",
        )
    assert caught.value.code == "HOLD_DECISION_ACTION_BLOCKED"


def test_reading_latest_decision_never_creates_one(tmp_path: Path):
    catalog, _, opened, mdb = _env(tmp_path)
    _rev(catalog, opened.stock_id, "r1", "90")
    service = HoldingDecisionSupportService(
        catalog,
        market_store_db=mdb,
    )

    view = service.latest_for_stock(opened.stock_id)

    assert view["positions"][0]["decision"] is None
    with sqlite3.connect(catalog.db_path) as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM holding_decision_record"
        ).fetchone()[0] == 0


def test_same_source_reuses_decision_instead_of_cluttering_history(tmp_path: Path):
    catalog, _, opened, mdb = _env(tmp_path)
    revision = _rev(catalog, opened.stock_id, "r1", "90")
    _apply(catalog, mdb, opened.position.id, revision.id)
    service = HoldingDecisionSupportService(
        catalog,
        market_store_db=mdb,
    )

    first = service.evaluate(opened.position.id)
    second = service.evaluate(opened.position.id)

    assert second["decision_id"] == first["decision_id"]
    assert second["reused"] is True
    with sqlite3.connect(catalog.db_path) as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM holding_decision_record"
        ).fetchone()[0] == 1


def test_position_quantity_change_makes_decision_stale(tmp_path: Path):
    catalog, life, opened, mdb = _env(tmp_path)
    revision = _rev(catalog, opened.stock_id, "r1", "90")
    _apply(catalog, mdb, opened.position.id, revision.id)
    service = HoldingDecisionSupportService(
        catalog,
        market_store_db=mdb,
    )
    decision = service.evaluate(opened.position.id)

    life.record_buy(
        monitored_stock_id=opened.stock_id,
        position_account_id=opened.position.position_account_id,
        quantity="1",
        unit_price="100",
        effective_at=T2,
    )
    detail = service.get_decision(decision["decision_id"])

    assert detail["stale"] is True
    assert "POSITION_QUANTITY_CHANGED" in detail["stale_reasons"]
    with pytest.raises(HoldingsDecisionSupportError) as caught:
        service.resolve(
            decision_id=decision["decision_id"],
            resolution_type="KEEP_CURRENT_PLAN",
            selected_action="HOLD",
        )
    assert caught.value.code == "HOLD_DECISION_STALE"


def test_new_analysis_revision_makes_decision_stale(tmp_path: Path):
    catalog, _, opened, mdb = _env(tmp_path)
    revision = _rev(catalog, opened.stock_id, "r1", "90")
    _apply(catalog, mdb, opened.position.id, revision.id)
    service = HoldingDecisionSupportService(
        catalog,
        market_store_db=mdb,
    )
    decision = service.evaluate(opened.position.id)

    _rev(catalog, opened.stock_id, "r2", "95")
    detail = service.get_decision(decision["decision_id"])

    assert detail["effective_status"] == "STALE"
    assert "ANALYSIS_REVISION_CHANGED" in detail["stale_reasons"]


def test_plan_apply_from_decision_is_atomic_and_preserves_ledger(tmp_path: Path):
    catalog, _, opened, mdb = _env(tmp_path)
    r1 = _rev(catalog, opened.stock_id, "r1", "90")
    p1 = _apply(catalog, mdb, opened.position.id, r1.id)
    r2 = _rev(catalog, opened.stock_id, "r2", "95", t1="125", t2="135")
    service = HoldingDecisionSupportService(
        catalog,
        market_store_db=mdb,
        clock=lambda: "2026-09-24T03:00:00+00:00",
    )
    decision = service.evaluate(opened.position.id)
    before = catalog.get_position(opened.position.id)
    event_count = len(catalog.list_position_events(opened.position.id))

    result = service.apply_plan(
        decision_id=decision["decision_id"],
        selected_action="HOLD",
        note="새 분석 계획을 검토 후 적용",
    )

    after = catalog.get_position(opened.position.id)
    plans = HoldingManagementService(
        catalog,
        market_store_db=mdb,
    ).list_plans(opened.position.id)
    assert p1.id != result["plan"]["plan_id"]
    assert [item.status for item in plans] == ["SUPERSEDED", "ACTIVE"]
    assert plans[-1].plan_version == 2
    assert after.current_quantity == before.current_quantity
    assert after.current_average_price == before.current_average_price
    assert len(catalog.list_position_events(opened.position.id)) == event_count

    with sqlite3.connect(catalog.db_path) as conn:
        resolution = conn.execute(
            """
            SELECT * FROM holding_decision_resolution
            WHERE decision_id=?
            """,
            (decision["decision_id"],),
        ).fetchone()
        context = conn.execute(
            """
            SELECT * FROM holding_management_plan_context_vnp3s1
            WHERE plan_id=?
            """,
            (result["plan"]["plan_id"],),
        ).fetchone()
    assert resolution is not None
    assert resolution[3] == "APPLY_NEW_PLAN"
    assert context is not None
    assert context[4] is None
    assert context[5] is None


def test_stop_loosening_conflict_cannot_be_bypassed_by_decision_apply(tmp_path: Path):
    catalog, _, opened, mdb = _env(tmp_path)
    r1 = _rev(catalog, opened.stock_id, "r1", "90")
    p1 = _apply(catalog, mdb, opened.position.id, r1.id)
    _rev(catalog, opened.stock_id, "r2", "80")
    service = HoldingDecisionSupportService(
        catalog,
        market_store_db=mdb,
    )

    decision = service.evaluate(opened.position.id)

    assert decision["status"] == "CONFLICT"
    assert decision["evidence"]["proposal_conflict"] == "STOP_LOOSENING_BLOCKED"
    with pytest.raises(HoldingsManagementError) as caught:
        service.apply_plan(
            decision_id=decision["decision_id"],
            selected_action="HOLD",
        )
    assert caught.value.code == "HOLD_PLAN_STOP_LOOSENING_BLOCKED"
    active = HoldingManagementService(
        catalog,
        market_store_db=mdb,
    ).get_active_plan(opened.position.id)
    assert active.id == p1.id


def test_decision_and_resolution_are_append_only(tmp_path: Path):
    catalog, _, opened, mdb = _env(tmp_path)
    revision = _rev(catalog, opened.stock_id, "r1", "90")
    _apply(catalog, mdb, opened.position.id, revision.id)
    service = HoldingDecisionSupportService(
        catalog,
        market_store_db=mdb,
    )
    decision = service.evaluate(opened.position.id)
    service.resolve(
        decision_id=decision["decision_id"],
        resolution_type="KEEP_CURRENT_PLAN",
        selected_action="HOLD",
    )

    with sqlite3.connect(catalog.db_path) as conn:
        with pytest.raises(sqlite3.DatabaseError):
            conn.execute(
                """
                UPDATE holding_decision_record
                SET status='DEFERRED'
                WHERE id=?
                """,
                (decision["decision_id"],),
            )
        resolution_id = conn.execute(
            """
            SELECT id FROM holding_decision_resolution
            WHERE decision_id=?
            """,
            (decision["decision_id"],),
        ).fetchone()[0]
        with pytest.raises(sqlite3.DatabaseError):
            conn.execute(
                "DELETE FROM holding_decision_resolution WHERE id=?",
                (resolution_id,),
            )
