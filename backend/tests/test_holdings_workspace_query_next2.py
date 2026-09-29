from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from app.holdings.catalog import HoldingsCatalog
from app.holdings.lifecycle import PositionLifecycleService
from app.holdings.workspace_query import (
    HoldingsWorkspaceQueryService,
    WORKSPACE_CONTEXT_VERSION,
)
from app.main import app


client = TestClient(app)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _market(path: Path) -> None:
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
            CREATE TABLE main_index_daily(
                market TEXT NOT NULL,
                bas_dd TEXT NOT NULL,
                row_json TEXT NOT NULL,
                PRIMARY KEY(market,bas_dd)
            );
            """
        )
        row = {
            "date": "2026-09-29",
            "open": "100",
            "high": "101",
            "low": "99",
            "close": "100",
            "volume": "1000",
        }
        conn.execute(
            "INSERT INTO day_status VALUES('KOSPI','20260929','stock','data')"
        )
        conn.execute(
            "INSERT INTO day_status VALUES('KOSPI','20260929','index','data')"
        )
        conn.execute(
            "INSERT INTO stock_daily VALUES('KOSPI','20260929','005930',?)",
            (json.dumps(row),),
        )
        conn.execute(
            "INSERT INTO main_index_daily VALUES('KOSPI','20260929',?)",
            (json.dumps({"date": "2026-09-29", "close": "3000"}),),
        )


def _holdings(path: Path) -> tuple[HoldingsCatalog, str]:
    catalog = HoldingsCatalog(path)
    catalog.initialize()
    account = catalog.create_position_account(
        provider="MANUAL",
        account_kind="MANUAL",
        display_name="수동 기록",
    )
    result = PositionLifecycleService(catalog).register_initial_holding(
        market="KOSPI",
        ticker="005930",
        name="삼성전자",
        position_account_id=account.id,
        quantity="10",
        average_price="100",
        effective_at="2026-09-29T09:00:00+09:00",
    )
    return catalog, result.stock_id


def test_workspace_query_is_read_only_and_isolates_optional_domain_migrations(
    tmp_path: Path,
) -> None:
    market = tmp_path / "market.db"
    holdings = tmp_path / "holdings.db"
    _market(market)
    _, stock_id = _holdings(holdings)

    before_holdings = _sha(holdings)
    before_market = _sha(market)

    payload = HoldingsWorkspaceQueryService(
        holdings,
        market_store_db=market,
    ).build(stock_id)

    assert payload["context_version"] == WORKSPACE_CONTEXT_VERSION
    assert payload["stock"]["stock_id"] == stock_id
    assert payload["stock"]["ticker"] == "005930"
    assert payload["current_state"]["held"] is True
    assert payload["source_status"]["ledger"]["status"] == "VALID"
    assert payload["source_status"]["decision"]["status"] == "MIGRATION_REQUIRED"
    assert payload["source_status"]["recovery"]["status"] == "MIGRATION_REQUIRED"
    assert payload["source_status"]["watch"]["status"] == "MIGRATION_REQUIRED"
    assert payload["positions"][0]["position"]["position_id"]
    assert payload["positions"][0]["decision"] is None
    assert payload["positions"][0]["recovery"] is None
    assert payload["positions"][0]["watch"]["migration_required"] is True

    assert _sha(holdings) == before_holdings
    assert _sha(market) == before_market


def test_workspace_endpoint_uses_read_only_context_without_initializing_schema(
    tmp_path: Path,
    monkeypatch,
) -> None:
    market = tmp_path / "market.db"
    holdings = tmp_path / "holdings.db"
    _market(market)
    _, stock_id = _holdings(holdings)

    before_holdings = _sha(holdings)
    before_market = _sha(market)
    monkeypatch.setenv("STOCKSCOPE_HOLDINGS_DB", str(holdings))
    monkeypatch.setenv("STOCKSCOPE_MARKET_STORE_DB", str(market))

    response = client.get(f"/api/holdings/stocks/{stock_id}/workspace-context")

    assert response.status_code == 200
    body = response.json()
    assert body["context_version"] == WORKSPACE_CONTEXT_VERSION
    assert body["stock"]["stock_id"] == stock_id
    assert body["context_identity"]["stock_id"] == stock_id
    assert body["data_contract"]["contract_version"] == "DATA_CONTRACT_V1"

    assert _sha(holdings) == before_holdings
    assert _sha(market) == before_market


def test_review_conditions_surface_missing_decision_and_plan_for_current_analysis() -> None:
    conditions = HoldingsWorkspaceQueryService._review_conditions(
        analysis_contract={"current_use_allowed": True},
        management={"management_state": "NO_ACTIVE_PLAN", "active_plan": None},
        decision=None,
        recovery=None,
        watch={"migration_required": False, "open_gaps": []},
        decision_domain_available=True,
        management_domain_available=True,
    )

    assert conditions == [
        "DECISION_NOT_CREATED",
        "ACTIVE_PLAN_NOT_APPLIED",
    ]


def test_review_conditions_do_not_prompt_new_decision_or_plan_when_analysis_is_stale() -> None:
    conditions = HoldingsWorkspaceQueryService._review_conditions(
        analysis_contract={"current_use_allowed": False},
        management={"management_state": "NO_ACTIVE_PLAN", "active_plan": None},
        decision=None,
        recovery=None,
        watch={"migration_required": False, "open_gaps": []},
        decision_domain_available=True,
        management_domain_available=True,
    )

    assert conditions == ["ANALYSIS_REFRESH_REQUIRED"]


def test_review_conditions_keep_active_stop_protection_even_when_analysis_is_stale() -> None:
    conditions = HoldingsWorkspaceQueryService._review_conditions(
        analysis_contract={"current_use_allowed": False},
        management={
            "management_state": "STOP_BREACHED",
            "active_plan": {"plan_id": "plan-1"},
        },
        decision=None,
        recovery=None,
        watch={"migration_required": False, "open_gaps": []},
        decision_domain_available=True,
        management_domain_available=True,
    )

    assert conditions == [
        "ANALYSIS_REFRESH_REQUIRED",
        "ACTIVE_PLAN_STOP_BREACHED",
    ]
