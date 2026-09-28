from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.api.holdings as holdings_api
from app.holdings import HoldingsCatalog, PositionLifecycleService
from app.holdings.management import HoldingManagementService
from tools.data.migrate_holdings_decision_vnp3s1 import (
    migrate_holdings_decision_store,
)
from tools.data.migrate_holdings_recovery_vnp3s2 import (
    migrate_holdings_recovery_store,
)


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


@pytest.fixture()
def api_env(tmp_path: Path, monkeypatch):
    holdings_db = tmp_path / "holdings.db"
    market_db = tmp_path / "market.db"
    monkeypatch.setenv("STOCKSCOPE_HOLDINGS_DB", str(holdings_db))
    monkeypatch.setenv("STOCKSCOPE_MARKET_STORE_DB", str(market_db))
    _market(market_db)

    catalog = HoldingsCatalog(holdings_db)
    catalog.initialize()
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
        effective_at="2026-09-24T09:00:00+09:00",
    )
    day = catalog.get_or_create_analysis_day(
        monitored_stock_id=opened.stock_id,
        market_date="2026-09-24",
    )
    revision = catalog.append_analysis_revision(
        analysis_day_id=day.id,
        input_fingerprint="recovery-api-r1",
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
        source_versions={"fixture": "recovery-api"},
        snapshot={"fixture": True},
        computed_at="2026-09-24T00:00:00+00:00",
    )
    catalog.promote_current_revision(
        analysis_day_id=day.id,
        revision_id=revision.id,
    )
    migrate_holdings_decision_store(holdings_db)

    app = FastAPI()
    app.include_router(holdings_api.router, prefix="/api")
    client = TestClient(app)
    return {
        "client": client,
        "catalog": catalog,
        "opened": opened,
        "revision": revision,
        "holdings_db": holdings_db,
        "market_db": market_db,
    }


def test_recovery_get_requires_explicit_migration_and_does_not_create_tables(api_env):
    response = api_env["client"].get(
        f"/api/holdings/positions/{api_env['opened'].position.id}/recovery"
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "HOLD_RECOVERY_MIGRATION_REQUIRED"
    with sqlite3.connect(api_env["holdings_db"]) as conn:
        names = {
            str(row[0])
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
    assert "holding_recovery_review" not in names


def test_recovery_get_is_read_only_and_exposes_unknowns_without_inference(api_env):
    migrate_holdings_recovery_store(api_env["holdings_db"])
    client = api_env["client"]
    position_id = api_env["opened"].position.id

    response = client.get(f"/api/holdings/positions/{position_id}/recovery")

    assert response.status_code == 200
    payload = response.json()
    assert payload["open_review"] is None
    assert payload["reviews"] == []
    current = payload["current"]
    assert current["position"]["quantity"] == "10"
    assert current["position"]["average_price"] == "100"
    assert current["valuation"] == {
        "available": True,
        "market_date": "2026-09-24",
        "price": "100",
        "source": "MARKET_STORE_CONFIRMED_EOD",
        "message": None,
    }
    assert current["performance"]["unrealized_pnl"] == "0"
    assert current["performance"]["unrealized_return_pct"] == "0"
    assert current["analysis"]["revision_id"] == api_env["revision"].id
    assert current["active_plan"] is None
    assert current["latest_decision"] is None
    assert "ACTIVE_PLAN_NOT_AVAILABLE" in current["limitations"]
    assert "HOLDING_DECISION_NOT_AVAILABLE" in current["limitations"]
    assert "ACCOUNT_TOTAL_EXPOSURE_NOT_PROVEN" in current["limitations"]
    assert "COMPANY_EVIDENCE_NOT_CONNECTED" in current["limitations"]

    with sqlite3.connect(api_env["holdings_db"]) as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM holding_recovery_review"
        ).fetchone()[0] == 0
        assert conn.execute(
            "SELECT COUNT(*) FROM holding_recovery_assessment"
        ).fetchone()[0] == 0


def test_recovery_assessment_snapshots_server_evidence_and_links_decision(api_env):
    migrate_holdings_recovery_store(api_env["holdings_db"])
    client = api_env["client"]
    catalog = api_env["catalog"]
    opened = api_env["opened"]
    revision = api_env["revision"]

    plan = HoldingManagementService(
        catalog,
        market_store_db=api_env["market_db"],
    ).apply_analysis_plan(
        position_id=opened.position.id,
        analysis_revision_id=revision.id,
        applied_at="2026-09-24T10:00:00+09:00",
    )
    decision_response = client.post(
        f"/api/holdings/positions/{opened.position.id}/decisions/evaluate"
    )
    assert decision_response.status_code == 200
    decision = decision_response.json()["decision"]

    event_count = len(catalog.list_position_events(opened.position.id))
    start = client.post(
        f"/api/holdings/positions/{opened.position.id}/recovery/start",
        json={"note": "큰 손실 상태 재검토"},
    )
    assert start.status_code == 200
    assert start.json()["created"] is True
    review = start.json()["review"]

    created = client.post(
        f"/api/holdings/recovery/{review['review_id']}/assessments",
        json={
            "thesis_state": "WEAKENED",
            "review_action": "REDUCE",
            "reason_note": "투자 논리는 남아 있으나 위험을 줄이는 방향을 검토",
            "linked_decision_id": decision["decision_id"],
        },
    )
    assert created.status_code == 200
    assessment = created.json()["assessment"]

    assert assessment["source_analysis_revision_id"] == revision.id
    assert assessment["source_active_plan_id"] == plan.id
    assert assessment["source_active_plan_version"] == 1
    assert assessment["valuation_market_date"] == "2026-09-24"
    assert assessment["valuation_price"] == "100"
    assert assessment["unrealized_pnl"] == "0"
    assert assessment["unrealized_return_pct"] == "0"
    assert assessment["linked_decision_id"] == decision["decision_id"]
    assert assessment["evidence"]["evidence_version"] == "VN_P3_S2_RECOVERY_EVIDENCE_V1"
    assert assessment["evidence"]["active_plan"]["plan_id"] == plan.id
    assert (
        assessment["evidence"]["analysis"]["revision_id"]
        == revision.id
    )
    assert (
        assessment["evidence"]["linked_decision"]["decision_id"]
        == decision["decision_id"]
    )
    assert "ACCOUNT_TOTAL_EXPOSURE_NOT_PROVEN" in assessment["limitations"]
    assert "COMPANY_EVIDENCE_NOT_CONNECTED" in assessment["limitations"]
    assert "HOLDING_DECISION_NOT_AVAILABLE" not in assessment["limitations"]
    assert "HOLDING_DECISION_STALE" not in assessment["limitations"]

    active_after = HoldingManagementService(
        catalog,
        market_store_db=api_env["market_db"],
    ).get_active_plan(opened.position.id)
    assert active_after is not None
    assert active_after.id == plan.id
    assert len(catalog.list_position_events(opened.position.id)) == event_count


def test_recovery_add_review_is_intent_only_and_start_close_are_idempotent(api_env):
    migrate_holdings_recovery_store(api_env["holdings_db"])
    client = api_env["client"]
    catalog = api_env["catalog"]
    position_id = api_env["opened"].position.id
    events_before = len(catalog.list_position_events(position_id))

    first = client.post(
        f"/api/holdings/positions/{position_id}/recovery/start",
        json={"note": "추가매수 가능성도 검토"},
    )
    second = client.post(
        f"/api/holdings/positions/{position_id}/recovery/start",
        json={"note": "중복 시작"},
    )
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["created"] is True
    assert second.json()["created"] is False
    review_id = first.json()["review"]["review_id"]
    assert second.json()["review"]["review_id"] == review_id

    assessment = client.post(
        f"/api/holdings/recovery/{review_id}/assessments",
        json={
            "thesis_state": "UNKNOWN",
            "review_action": "ADD_REVIEW",
            "reason_note": "추가매수 정책이 아니라 검토 의도만 기록",
            "linked_decision_id": None,
        },
    )
    assert assessment.status_code == 200
    assert assessment.json()["assessment"]["review_action"] == "ADD_REVIEW"
    assert len(catalog.list_position_events(position_id)) == events_before

    close1 = client.post(
        f"/api/holdings/recovery/{review_id}/close",
        json={"reason": "DECISION_RECORDED", "note": "검토 종료"},
    )
    close2 = client.post(
        f"/api/holdings/recovery/{review_id}/close",
        json={"reason": "SHOULD_NOT_OVERWRITE", "note": "중복 종료"},
    )
    assert close1.status_code == 200
    assert close2.status_code == 200
    assert close1.json()["closed"] is True
    assert close2.json()["closed"] is False
    assert close2.json()["review"]["close_reason"] == "DECISION_RECORDED"
    assert len(catalog.list_position_events(position_id)) == events_before
