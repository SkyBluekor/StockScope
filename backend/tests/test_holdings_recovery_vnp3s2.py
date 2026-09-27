from __future__ import annotations

import sqlite3
from decimal import Decimal
from pathlib import Path

import pytest

from app.holdings import HoldingsCatalog, PositionLifecycleService
from app.holdings.management import HoldingManagementService
from app.holdings.recovery import HoldingRecoveryService, HoldingsRecoveryError
from tools.data.common import DataToolError
from tools.data.migrate_holdings_decision_vnp3s1 import (
    migrate_holdings_decision_store,
)
from tools.data.migrate_holdings_recovery_vnp3s2 import (
    migrate_holdings_recovery_store,
)


T0 = "2026-09-27T09:00:00+09:00"
T1 = "2026-09-27T10:00:00+09:00"
T2 = "2026-09-27T11:00:00+09:00"
T3 = "2026-09-27T12:00:00+09:00"


def _env(tmp_path: Path, *, migrate_recovery: bool = True):
    db = tmp_path / "holdings.db"
    catalog = HoldingsCatalog(db)
    catalog.initialize()
    migrate_holdings_decision_store(db)
    if migrate_recovery:
        migrate_holdings_recovery_store(db)

    lifecycle = PositionLifecycleService(catalog)
    account = catalog.create_position_account(
        provider="MANUAL",
        account_kind="MANUAL",
        display_name="수동 기록",
    )
    opened = lifecycle.register_initial_holding(
        market="KOSPI",
        ticker="005930",
        name="삼성전자",
        position_account_id=account.id,
        quantity="10",
        average_price="100",
        effective_at=T0,
    )
    return catalog, lifecycle, opened


def _revision_and_plan(catalog: HoldingsCatalog, opened):
    day = catalog.get_or_create_analysis_day(
        monitored_stock_id=opened.stock_id,
        market_date="2026-09-27",
    )
    revision = catalog.append_analysis_revision(
        analysis_day_id=day.id,
        input_fingerprint="recovery-r1",
        strategy_key="trend_following",
        action_state="WATCH",
        risk_state="READY",
        reference_price="100",
        stop_price="90",
        target1_price="120",
        target2_price="130",
        scanner_version="test",
        analysis_engine_version="test",
        policy_version="test",
        source_versions={"fixture": "recovery-r1"},
        snapshot={"fixture": "recovery-r1"},
        computed_at=T1,
    )
    catalog.promote_current_revision(
        analysis_day_id=day.id,
        revision_id=revision.id,
    )
    plan = HoldingManagementService(catalog).apply_analysis_plan(
        position_id=opened.position.id,
        analysis_revision_id=revision.id,
        applied_at=T1,
    )
    return revision, plan


def test_recovery_migration_is_explicit_idempotent_and_no_backfill(tmp_path: Path):
    db = tmp_path / "holdings.db"
    catalog = HoldingsCatalog(db)
    catalog.initialize()
    migrate_holdings_decision_store(db)

    first = migrate_holdings_recovery_store(db)
    second = migrate_holdings_recovery_store(db)

    assert first == second
    assert first["schema_version"] == "VN_P3_S2_RECOVERY_REVIEW_V1"
    assert first["historical_recovery_backfill_performed"] is False
    with sqlite3.connect(db) as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM holding_recovery_review"
        ).fetchone()[0] == 0
        assert conn.execute(
            "SELECT COUNT(*) FROM holding_recovery_assessment"
        ).fetchone()[0] == 0


def test_recovery_migration_requires_p3s1(tmp_path: Path):
    db = tmp_path / "holdings.db"
    catalog = HoldingsCatalog(db)
    catalog.initialize()

    with pytest.raises(DataToolError):
        migrate_holdings_recovery_store(db)

    with sqlite3.connect(db) as conn:
        names = {
            str(row[0])
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        assert "holding_recovery_schema_meta" not in names


def test_service_requires_explicit_recovery_migration(tmp_path: Path):
    catalog, _, opened = _env(tmp_path, migrate_recovery=False)
    service = HoldingRecoveryService(catalog)

    with pytest.raises(HoldingsRecoveryError) as caught:
        service.start_review(position_id=opened.position.id)

    assert caught.value.code == "HOLD_RECOVERY_MIGRATION_REQUIRED"


def test_start_review_is_idempotent_and_preserves_ledger_and_plan(tmp_path: Path):
    catalog, _, opened = _env(tmp_path)
    _, plan = _revision_and_plan(catalog, opened)
    events_before = catalog.list_position_events(opened.position.id)
    position_before = catalog.get_position(opened.position.id)
    service = HoldingRecoveryService(catalog, clock=lambda: T2)

    first = service.start_review(
        position_id=opened.position.id,
        note="큰 손실 상태 재검토",
    )
    second = service.start_review(
        position_id=opened.position.id,
        note="중복 시작",
    )

    assert first["created"] is True
    assert second["created"] is False
    assert second["review"]["review_id"] == first["review"]["review_id"]
    assert second["review"]["opened_note"] == "큰 손실 상태 재검토"

    with sqlite3.connect(catalog.db_path) as conn:
        assert conn.execute(
            """
            SELECT COUNT(*) FROM holding_recovery_review
            WHERE position_id=? AND status='OPEN'
            """,
            (opened.position.id,),
        ).fetchone()[0] == 1

    active = HoldingManagementService(catalog).get_active_plan(opened.position.id)
    position_after = catalog.get_position(opened.position.id)
    events_after = catalog.list_position_events(opened.position.id)

    assert active is not None
    assert active.id == plan.id
    assert position_after.current_quantity == position_before.current_quantity
    assert position_after.current_average_price == position_before.current_average_price
    assert len(events_after) == len(events_before)


def test_assessment_is_append_only_and_snapshots_current_sources(tmp_path: Path):
    catalog, lifecycle, opened = _env(tmp_path)
    revision, plan = _revision_and_plan(catalog, opened)
    service = HoldingRecoveryService(catalog, clock=lambda: T2)
    review = service.start_review(position_id=opened.position.id)["review"]

    first = service.record_assessment(
        review_id=review["review_id"],
        thesis_state="WEAKENED",
        review_action="HOLD",
        reason_note="사업 논리는 남아 있지만 위험을 다시 확인",
        limitations=["COMPANY_EVIDENCE_INCOMPLETE"],
        evidence={"source": "manual-review"},
    )

    assert first["source_analysis_revision_id"] == revision.id
    assert first["source_active_plan_id"] == plan.id
    assert first["source_active_plan_version"] == 1
    assert first["source_position_status"] == "OPEN"
    assert first["source_position_quantity"] == "10"
    assert first["source_position_average_price"] == "100"
    assert first["limitations"] == ["COMPANY_EVIDENCE_INCOMPLETE"]
    assert first["evidence"] == {"source": "manual-review"}

    lifecycle.record_correction(
        position_id=opened.position.id,
        corrected_quantity="8",
        corrected_average_price="105",
        effective_at=T3,
        note="assessment snapshot immutability check",
    )
    second = service.record_assessment(
        review_id=review["review_id"],
        thesis_state="BROKEN",
        review_action="REDUCE",
        reason_note="핵심 전제가 약해짐",
    )

    stored = service.list_assessments(review["review_id"])
    assert [item["assessment_id"] for item in stored] == [
        first["assessment_id"],
        second["assessment_id"],
    ]
    assert stored[0]["source_position_quantity"] == "10"
    assert stored[0]["source_position_average_price"] == "100"
    assert stored[1]["source_position_quantity"] == "8"
    assert stored[1]["source_position_average_price"] == "105"

    with sqlite3.connect(catalog.db_path) as conn:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                UPDATE holding_recovery_assessment
                SET thesis_state='INTACT'
                WHERE id=?
                """,
                (first["assessment_id"],),
            )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "DELETE FROM holding_recovery_assessment WHERE id=?",
                (first["assessment_id"],),
            )


def test_add_review_records_intent_only_without_trade_or_plan_change(tmp_path: Path):
    catalog, _, opened = _env(tmp_path)
    _, plan = _revision_and_plan(catalog, opened)
    service = HoldingRecoveryService(catalog, clock=lambda: T2)
    review = service.start_review(position_id=opened.position.id)["review"]
    events_before = catalog.list_position_events(opened.position.id)
    position_before = catalog.get_position(opened.position.id)

    assessment = service.record_assessment(
        review_id=review["review_id"],
        thesis_state="UNKNOWN",
        review_action="ADD_REVIEW",
        reason_note="추가매수 가능성은 검토만 함",
    )

    assert assessment["review_action"] == "ADD_REVIEW"
    active = HoldingManagementService(catalog).get_active_plan(opened.position.id)
    position_after = catalog.get_position(opened.position.id)
    events_after = catalog.list_position_events(opened.position.id)

    assert active is not None
    assert active.id == plan.id
    assert position_after.current_quantity == position_before.current_quantity
    assert position_after.current_average_price == position_before.current_average_price
    assert len(events_after) == len(events_before)


def test_close_review_is_idempotent_and_does_not_create_trade(tmp_path: Path):
    catalog, _, opened = _env(tmp_path)
    _, plan = _revision_and_plan(catalog, opened)
    service = HoldingRecoveryService(catalog, clock=lambda: T2)
    review = service.start_review(position_id=opened.position.id)["review"]
    events_before = catalog.list_position_events(opened.position.id)

    first = service.close_review(
        review_id=review["review_id"],
        reason="DECISION_RECORDED",
        note="현재 계획을 유지하기로 검토 완료",
    )
    second = service.close_review(
        review_id=review["review_id"],
        reason="SHOULD_NOT_OVERWRITE",
        note="중복 종료",
    )

    assert first["closed"] is True
    assert second["closed"] is False
    assert second["review"]["status"] == "CLOSED"
    assert second["review"]["close_reason"] == "DECISION_RECORDED"
    assert second["review"]["close_note"] == "현재 계획을 유지하기로 검토 완료"

    active = HoldingManagementService(catalog).get_active_plan(opened.position.id)
    assert active is not None
    assert active.id == plan.id
    assert len(catalog.list_position_events(opened.position.id)) == len(events_before)

    with pytest.raises(HoldingsRecoveryError) as caught:
        service.record_assessment(
            review_id=review["review_id"],
            thesis_state="INTACT",
            review_action="HOLD",
        )
    assert caught.value.code == "HOLD_RECOVERY_REVIEW_CLOSED"


def test_closed_position_keeps_recovery_history_and_does_not_auto_close_review(
    tmp_path: Path,
):
    catalog, lifecycle, opened = _env(tmp_path)
    service = HoldingRecoveryService(catalog, clock=lambda: T2)
    review = service.start_review(position_id=opened.position.id)["review"]
    assessment = service.record_assessment(
        review_id=review["review_id"],
        thesis_state="BROKEN",
        review_action="EXIT",
        reason_note="종료 검토",
    )

    lifecycle.record_sell(
        position_id=opened.position.id,
        quantity="10",
        unit_price="80",
        effective_at=T3,
        note="사용자 수동 전량 정리",
    )

    stored_review = service.get_review(review["review_id"])
    stored_assessments = service.list_assessments(review["review_id"])

    assert catalog.get_position(opened.position.id).status == "CLOSED"
    assert stored_review["status"] == "OPEN"
    assert stored_assessments[0]["assessment_id"] == assessment["assessment_id"]
    assert service.list_reviews(opened.position.id)[0]["review_id"] == review["review_id"]


def test_cannot_start_new_recovery_review_for_closed_position(tmp_path: Path):
    catalog, lifecycle, opened = _env(tmp_path)
    lifecycle.record_sell(
        position_id=opened.position.id,
        quantity="10",
        unit_price="80",
        effective_at=T2,
    )
    service = HoldingRecoveryService(catalog)

    with pytest.raises(HoldingsRecoveryError) as caught:
        service.start_review(position_id=opened.position.id)

    assert caught.value.code == "HOLD_RECOVERY_POSITION_NOT_OPEN"
