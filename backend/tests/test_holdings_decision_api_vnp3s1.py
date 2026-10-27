from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.api.holdings as holdings_api
from app.backtest.production_exit_policy import production_policy_cache_token
from app.backtest.scanner import StockScannerService
from app.holdings import HoldingsCatalog, PositionLifecycleService
from app.holdings.analysis import (
    ANALYSIS_ENGINE_VERSION,
    INPUT_FINGERPRINT_CONTRACT_VERSION,
)
from app.input_identity import read_input_generation_token
from app.holdings.management import HoldingManagementService
from tools.data.migrate_holdings_decision_vnp3s1 import (
    migrate_holdings_decision_store,
)
from tools.data.migrate_input_identity_vnp1s1 import (
    migrate_holdings as migrate_holdings_input_identity,
    migrate_market_store as migrate_market_input_identity,
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
            CREATE TABLE main_index_daily(
                market TEXT,bas_dd TEXT,row_json TEXT
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
        conn.execute(
            "INSERT INTO main_index_daily VALUES('KOSPI','20260924',?)",
            (json.dumps({"date": "2026-09-24", "close": "3000"}),),
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
    migrate_market_input_identity(market_db)
    migrate_holdings_input_identity(holdings_db)
    with sqlite3.connect(market_db) as conn:
        conn.row_factory = sqlite3.Row
        generation = read_input_generation_token(conn, "KOSPI", "005930")
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
        input_fingerprint="api-r1",
        strategy_key="trend_following",
        action_state="WATCH",
        risk_state="READY",
        reference_price="100",
        stop_price="90",
        target1_price="120",
        target2_price="130",
        scanner_version=StockScannerService.VERSION,
        analysis_engine_version=ANALYSIS_ENGINE_VERSION,
        policy_version=production_policy_cache_token(),
        source_versions={
            "fixture": "api",
            "fingerprint_contract_version": INPUT_FINGERPRINT_CONTRACT_VERSION,
            "input_generation": generation,
        },
        snapshot={"fixture": True},
        computed_at="2026-09-24T00:00:00+00:00",
    )
    catalog.promote_current_revision(
        analysis_day_id=day.id,
        revision_id=revision.id,
    )

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


def test_read_endpoint_requires_explicit_migration_but_does_not_create_state(api_env):
    client = api_env["client"]
    opened = api_env["opened"]

    response = client.get(
        f"/api/holdings/stocks/{opened.stock_id}/decision-support"
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "HOLD_DECISION_MIGRATION_REQUIRED"
    with sqlite3.connect(api_env["holdings_db"]) as conn:
        tables = {
            str(row[0])
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
    assert "holding_decision_record" not in tables


def test_get_is_read_only_and_post_evaluate_creates_decision(api_env):
    client = api_env["client"]
    opened = api_env["opened"]
    migrate_holdings_decision_store(api_env["holdings_db"])

    before = client.get(
        f"/api/holdings/stocks/{opened.stock_id}/decision-support"
    )
    assert before.status_code == 200
    assert before.json()["positions"][0]["decision"] is None
    with sqlite3.connect(api_env["holdings_db"]) as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM holding_decision_record"
        ).fetchone()[0] == 0

    created = client.post(
        f"/api/holdings/positions/{opened.position.id}/decisions/evaluate"
    )
    assert created.status_code == 200
    decision = created.json()["decision"]
    assert decision["status"] == "REVIEW_REQUIRED"
    assert decision["primary_action"] is None
    with sqlite3.connect(api_env["holdings_db"]) as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM holding_decision_record"
        ).fetchone()[0] == 1


def test_decision_api_blocks_add_and_applies_new_plan_without_ledger_event(api_env):
    client = api_env["client"]
    catalog = api_env["catalog"]
    opened = api_env["opened"]
    first_revision = api_env["revision"]
    migrate_holdings_decision_store(api_env["holdings_db"])

    first_plan = HoldingManagementService(
        catalog,
        market_store_db=api_env["market_db"],
    ).apply_analysis_plan(
        position_id=opened.position.id,
        analysis_revision_id=first_revision.id,
        applied_at="2026-09-24T10:00:00+09:00",
    )

    day = catalog.get_or_create_analysis_day(
        monitored_stock_id=opened.stock_id,
        market_date="2026-09-24",
    )
    with sqlite3.connect(api_env["market_db"]) as source_conn:
        source_conn.row_factory = sqlite3.Row
        generation = read_input_generation_token(
            source_conn, "KOSPI", "005930"
        )
    second_revision = catalog.append_analysis_revision(
        analysis_day_id=day.id,
        input_fingerprint="api-r2",
        strategy_key="trend_following",
        action_state="WATCH",
        risk_state="READY",
        reference_price="100",
        stop_price="95",
        target1_price="125",
        target2_price="135",
        scanner_version=StockScannerService.VERSION,
        analysis_engine_version=ANALYSIS_ENGINE_VERSION,
        policy_version=production_policy_cache_token(),
        source_versions={
            "fixture": "api-2",
            "fingerprint_contract_version": INPUT_FINGERPRINT_CONTRACT_VERSION,
            "input_generation": generation,
        },
        snapshot={"fixture": True},
        computed_at="2026-09-24T01:00:00+00:00",
    )
    catalog.promote_current_revision(
        analysis_day_id=day.id,
        revision_id=second_revision.id,
    )

    created = client.post(
        f"/api/holdings/positions/{opened.position.id}/decisions/evaluate"
    )
    assert created.status_code == 200
    decision = created.json()["decision"]
    event_count = len(catalog.list_position_events(opened.position.id))

    blocked = client.post(
        f"/api/holdings/decisions/{decision['decision_id']}/resolve",
        json={
            "resolution_type": "ACKNOWLEDGED",
            "selected_action": "ADD",
            "note": None,
        },
    )
    assert blocked.status_code == 409
    assert blocked.json()["detail"]["code"] == "HOLD_DECISION_ACTION_BLOCKED"

    applied = client.post(
        f"/api/holdings/decisions/{decision['decision_id']}/apply-plan",
        json={"selected_action": "HOLD", "note": "API UAT fixture"},
    )
    assert applied.status_code == 200
    assert applied.json()["plan"]["version"] == 2
    assert applied.json()["plan"]["previous_plan_id"] == first_plan.id
    assert len(catalog.list_position_events(opened.position.id)) == event_count
    position = catalog.get_position(opened.position.id)
    assert str(position.current_quantity) == "10"
    assert str(position.current_average_price) == "100"

    # Fetch through the actual read endpoints: the updated management plan
    # must survive a new catalog/service instance and the former plan is kept
    # as a superseded historical revision, not a new buy/sell transaction.
    reloaded = client.get(f"/api/holdings/stocks/{opened.stock_id}/management")
    assert reloaded.status_code == 200
    current_plan = reloaded.json()["positions"][0]["active_plan"]
    assert current_plan["plan_id"] == applied.json()["plan"]["plan_id"]
    assert current_plan["version"] == 2
    assert current_plan["stop_price"] == "95"
    assert current_plan["previous_plan_id"] == first_plan.id
    with catalog.connection() as conn:
        plan_versions = conn.execute(
            "SELECT plan_version,status FROM holding_management_plan "
            "WHERE position_id=? ORDER BY plan_version",
            (opened.position.id,),
        ).fetchall()
        assert [(row["plan_version"], row["status"]) for row in plan_versions] == [
            (1, "SUPERSEDED"), (2, "ACTIVE")
        ]

    reloaded_decision = client.get(
        f"/api/holdings/decisions/{decision['decision_id']}"
    )
    assert reloaded_decision.status_code == 200
    assert reloaded_decision.json()["decision"]["stale"] is True
    assert len(reloaded_decision.json()["decision"]["resolutions"]) == 1

    duplicate = client.post(
        f"/api/holdings/decisions/{decision['decision_id']}/apply-plan",
        json={"selected_action": "HOLD"},
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["detail"]["code"] == "HOLD_DECISION_STALE"
    assert len(catalog.list_position_events(opened.position.id)) == event_count


def _disable_current_use(monkeypatch):
    """Simulate a revoked read-only data contract without changing EOD/revision."""
    from types import SimpleNamespace
    import app.data_contract.builder as contract_builder

    original = contract_builder.build_stock_data_contract

    def blocked_contract(*args, **kwargs):
        actual = original(*args, **kwargs).resources.analysis_result
        return SimpleNamespace(
            resources=SimpleNamespace(
                analysis_result=SimpleNamespace(
                    revision_id=actual.revision_id,
                    current_use_allowed=False,
                    status=actual.status,
                    reason_code="P0_04_CURRENT_USE_REVOKED",
                ),
            ),
        )
    monkeypatch.setattr(contract_builder, "build_stock_data_contract", blocked_contract)


def test_apply_fails_closed_when_analysis_current_use_is_not_approved(api_env, monkeypatch):
    catalog = api_env["catalog"]
    client = api_env["client"]
    opened = api_env["opened"]
    migrate_holdings_decision_store(api_env["holdings_db"])
    _disable_current_use(monkeypatch)

    response = client.post(
        f"/api/holdings/positions/{opened.position.id}/decisions/evaluate"
    )
    assert response.status_code == 200
    decision = response.json()["decision"]
    assert decision["source_analysis_revision_id"] == api_env["revision"].id
    assert decision["evidence"]["proposal_ready"] is False

    before_events = len(catalog.list_position_events(opened.position.id))
    denied = client.post(
        f"/api/holdings/decisions/{decision['decision_id']}/apply-plan",
        json={"selected_action": "HOLD"},
    )
    assert denied.status_code == 409
    assert denied.json()["detail"]["code"] == "HOLD_DECISION_PLAN_NOT_READY"
    with catalog.connection() as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM holding_management_plan"
        ).fetchone()[0] == 0
        assert conn.execute(
            "SELECT COUNT(*) FROM holding_decision_resolution"
        ).fetchone()[0] == 0
    assert len(catalog.list_position_events(opened.position.id)) == before_events


def test_contract_revocation_invalidates_already_saved_decision(api_env, monkeypatch):
    client = api_env["client"]
    opened = api_env["opened"]
    migrate_holdings_decision_store(api_env["holdings_db"])

    approved = client.post(
        f"/api/holdings/positions/{opened.position.id}/decisions/evaluate"
    )
    assert approved.status_code == 200
    decision = approved.json()["decision"]
    assert decision["evidence"]["proposal_ready"] is True

    _disable_current_use(monkeypatch)
    reread = client.get(f"/api/holdings/decisions/{decision['decision_id']}")
    assert reread.status_code == 200
    assert reread.json()["decision"]["stale"] is True
    assert "PROPOSAL_READINESS_CHANGED" in reread.json()["decision"]["stale_reasons"]

    denied = client.post(
        f"/api/holdings/decisions/{decision['decision_id']}/apply-plan",
        json={"selected_action": "HOLD"},
    )
    assert denied.status_code == 409
    assert denied.json()["detail"]["code"] == "HOLD_DECISION_STALE"
    with api_env["catalog"].connection() as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM holding_management_plan"
        ).fetchone()[0] == 0
