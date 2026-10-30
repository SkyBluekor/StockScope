"""P0-04 real read-only workspace probe: no operational data or private output."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys

from app.holdings import HoldingsCatalog, PositionLifecycleService
from tools.data.migrate_holdings_decision_vnp3s1 import migrate_holdings_decision_store
from tools.data.migrate_holdings_recovery_vnp3s2 import migrate_holdings_recovery_store
from app.holdings.decision_support import HoldingDecisionSupportService
from app.holdings.recovery import HoldingRecoveryService
from tools.data.p0_04_holdings_workspace_probe import (
    inspect_workspace,
    summarize_workspace,
)

SCRIPT = Path(__file__).resolve().parents[2] / "tools" / "data" / "p0_04_holdings_workspace_probe.py"


def _fixture(tmp_path: Path) -> tuple[Path, Path]:
    hdb, mdb = tmp_path / "holdings.db", tmp_path / "market.db"
    with sqlite3.connect(mdb) as conn:
        conn.executescript(
            "CREATE TABLE day_status(market TEXT,bas_dd TEXT,kind TEXT,status TEXT);"
            "CREATE TABLE stock_daily(market TEXT,bas_dd TEXT,stock_code TEXT,row_json TEXT);"
            "CREATE TABLE main_index_daily(market TEXT,bas_dd TEXT,row_json TEXT);"
        )
        row = {
            "date": "2026-10-21", "open": "100", "high": "101",
            "low": "99", "close": "100", "volume": "1234"
        }
        conn.execute("INSERT INTO day_status VALUES('KOSPI','20261021','stock','data')")
        conn.execute("INSERT INTO day_status VALUES('KOSPI','20261021','index','data')")
        conn.execute(
            "INSERT INTO stock_daily VALUES('KOSPI','20261021','005930',?)",
            (json.dumps(row),)
        )
        conn.execute(
            "INSERT INTO main_index_daily VALUES('KOSPI','20261021',?)",
            (json.dumps({"date":"2026-10-21","close":"3000"}),)
        )

    catalog = HoldingsCatalog(hdb)
    catalog.initialize()
    account = catalog.create_position_account(
        provider="MANUAL", account_kind="MANUAL",
        display_name="SENSITIVE_ACCOUNT_NAME",
    )
    PositionLifecycleService(catalog).register_initial_holding(
        market="KOSPI", ticker="005930", name="SENSITIVE_STOCK_NAME",
        position_account_id=account.id, quantity="13",
        average_price="11800", effective_at="2026-10-21T09:00:00+09:00",
    )
    return hdb, mdb


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_projection_only_outputs_allowlisted_codes_and_no_private_fields():
    payload = {
        "stock": {"ticker": "SENSITIVE_TICKER", "name": "SENSITIVE_NAME"},
        "current_state": {"analysis_current_use_allowed": False},
        "data_contract": {"resources": {"analysis_result": {
            "status": "INVALID", "reason_code": "ANALYSIS_BASIS_STALE",
            "basis_date": "2026-10-21", "ticker": "SECRET_TICKER",
            "price": "SENSITIVE_PRICE"
        }}},
        "source_status": {"decision": {"status": "AVAILABLE"}},
        "positions": [{
            "position": {"account_name": "SENSITIVE_ACCOUNT", "quantity": "999"},
            "management": {
                "management_state": "WITHIN_PLAN",
                "active_plan": {"stop_price": "SENSITIVE_STOP", "plan_id": "PRIVATE_PLAN"},
                "proposal": {"state": "NEW_REVISION", "can_apply": True,
                             "target1_price": "SENSITIVE_TARGET"}
            },
            "decision": {"stale": True, "effective_status": "STALE",
                         "decision_id": "PRIVATE_DECISION",
                         "stale_reasons": ["POSITION_QUANTITY_CHANGED", "SECRET_REASON_CODE"]},
            "recovery": {
                "open_review": {"review_id": "PRIVATE_REVIEW", "status": "OPEN",
                                "opened_at": "2026-10-24T09:00:00+09:00",
                                "opened_note": "PRIVATE_RECOVERY_NOTE"},
                "latest_open_assessment": {
                    "thesis_state": "WEAKENED", "review_action": "HOLD",
                    "reason_note": "PRIVATE_ASSESSMENT_REASON",
                    "created_at": "2026-10-25T12:00:00+09:00",
                    "source_active_plan_id": "PRIVATE_PLAN",
                    "source_analysis_revision_id": "PRIVATE_ANALYSIS",
                    "valuation_price": "SENSITIVE_PRICE",
                },
                "review_history": [{
                    "review": {"review_id": "PRIVATE_REVIEW"},
                    "assessments": [{
                        "assessment_id": "PRIVATE_ASSESSMENT",
                        "reason_note": "PRIVATE_ASSESSMENT_NOTE",
                    }],
                }],
                "current": {"analysis": {"revision_id": "PRIVATE_ANALYSIS"}},
            },
            "review_conditions": ["ANALYSIS_REFRESH_REQUIRED", "RECOVERY_REVIEW_OPEN"],
        }]
    }
    summary = summarize_workspace(payload)
    serialized = json.dumps(summary)
    assert summary["analysis_current_use_allowed"] is False
    assert summary["analysis_contract_status"] == "INVALID"
    assert summary["positions"][0]["active_plan_present"] is True
    assert summary["positions"][0]["proposal_structurally_applicable"] is True
    assert summary["positions_with_stale_decision"] == 1
    assert summary["stale_reason_counts"] == {
        "POSITION_QUANTITY_CHANGED": 1, "UNRECOGNIZED_STALE_REASON": 1
    }
    assert summary["open_recovery_reviews"] == 1
    recovery = summary["positions"][0]["recovery"]
    assert recovery["open_review_status"] == "OPEN"
    assert recovery["open_review_assessment_count"] == 1
    assert recovery["latest_assessment_thesis_state"] == "WEAKENED"
    assert recovery["latest_assessment_review_action"] == "HOLD"
    assert recovery["assessment_source_plan_matches_active"] is True
    assert recovery["assessment_source_analysis_matches_latest"] is True
    assert recovery["opened_date"] == "2026-10-24"
    assert recovery["latest_assessment_date"] == "2026-10-25"
    for private in ("SENSITIVE_", "PRIVATE_", "999", "SENSITIVE_TICKER", "SENSITIVE_TARGET"):
        assert private not in serialized


def test_preflight_missing_migration_is_nonmutating(tmp_path: Path):
    hdb, mdb = _fixture(tmp_path)
    before = _sha(hdb), _sha(mdb)
    result = inspect_workspace(hdb, mdb)
    assert result["status"] == "BLOCKED_WORKSPACE_PREFLIGHT"
    assert result["preflight_status"] == "HOLD_DECISION_SCHEMA_PREPARATION_REQUIRED"
    assert result["ready_for_plan_write"] is False
    assert result["db_write_calls"] == result["external_requests"] == 0
    assert (_sha(hdb), _sha(mdb)) == before


def test_real_workspace_readonly_over_synthetic_stored_position(tmp_path: Path):
    hdb, mdb = _fixture(tmp_path)
    migrate_holdings_decision_store(hdb)
    before = _sha(hdb), _sha(mdb)
    result = inspect_workspace(hdb, mdb)
    assert result["status"] == "READ_ONLY_WORKSPACE_STORED_STATE_OBSERVED"
    assert result["open_positions_projected"] == 1
    assert result["held_stock_groups"] == 1
    assert result["active_plan_count"] == 0
    assert result["analysis_current_use_allowed_groups"] == 0
    assert result["groups"][0]["positions"][0]["stored_eod_management_state"] == "NO_ACTIVE_PLAN"
    assert result["ready_for_plan_write"] is False
    assert result["realtime_price_verified"] is False
    output = json.dumps(result)
    for text in ("SENSITIVE_ACCOUNT_NAME", "SENSITIVE_STOCK_NAME", "005930", "11800"):
        assert text not in output
    assert (_sha(hdb), _sha(mdb)) == before


def test_workspace_error_does_not_leak_internal_error_string(tmp_path: Path, monkeypatch):
    from tools.data import p0_04_holdings_workspace_probe as module

    hdb, mdb = _fixture(tmp_path)
    migrate_holdings_decision_store(hdb)

    def denied(self, stock_id: str):
        raise RuntimeError("PRIVATE_ACCOUNT_AND_PRICE_SHOULD_NEVER_LEAK")
    monkeypatch.setattr(module.HoldingsWorkspaceQueryService, "build", denied)
    result = inspect_workspace(hdb, mdb)
    assert result["status"] == "BLOCKED_WORKSPACE_READ_FAILED"
    assert "PRIVATE_ACCOUNT" not in json.dumps(result)


def test_detects_concurrent_position_projection_mismatch(tmp_path: Path, monkeypatch):
    from tools.data import p0_04_holdings_workspace_probe as module

    hdb, mdb = _fixture(tmp_path)
    migrate_holdings_decision_store(hdb)

    def inconsistent(self, stock_id: str):
        return {
            "positions": [],
            "current_state": {"analysis_current_use_allowed": False},
            "data_contract": {"resources": {}},
            "source_status": {},
        }
    monkeypatch.setattr(module.HoldingsWorkspaceQueryService, "build", inconsistent)
    result = inspect_workspace(hdb, mdb)
    assert result["status"] == "BLOCKED_CONCURRENT_POSITION_CHANGE"


def test_cli_outputs_aggregate_json_without_touching_original_files(tmp_path: Path):
    hdb, mdb = _fixture(tmp_path)
    migrate_holdings_decision_store(hdb)
    before = _sha(hdb), _sha(mdb)
    process = subprocess.run(
        [sys.executable, str(SCRIPT), "--holdings-db", str(hdb),
         "--market-db", str(mdb)],
        capture_output=True, text=True, check=False, timeout=30,
    )
    assert process.returncode == 0, process.stderr
    report = json.loads(process.stdout)
    assert report["status"] == "READ_ONLY_WORKSPACE_STORED_STATE_OBSERVED"
    assert "SENSITIVE_ACCOUNT_NAME" not in process.stdout
    assert (_sha(hdb), _sha(mdb)) == before


def test_stale_decision_and_open_recovery_are_projected_from_real_readonly_services(
    tmp_path: Path,
):
    hdb, mdb = _fixture(tmp_path)
    migrate_holdings_decision_store(hdb)
    migrate_holdings_recovery_store(hdb)
    catalog = HoldingsCatalog(hdb)
    with catalog.connection() as conn:
        position_id = str(conn.execute("SELECT id FROM holding_position").fetchone()[0])
    service = HoldingDecisionSupportService(catalog, market_store_db=mdb)
    before_change = service.evaluate(position_id)
    assert before_change["decision_id"]

    recovery = HoldingRecoveryService(catalog, market_store_db=mdb)
    opened = recovery.start_review(
        position_id=position_id,
        note="PRIVATE_RECOVERY_OPENING_NOTE",
    )
    review_id = opened["review"]["review_id"]
    recovery.record_assessment(
        review_id=review_id,
        thesis_state="UNKNOWN",
        review_action="UNDECIDED",
        reason_note="PRIVATE_ASSESSMENT_DETAIL",
    )
    PositionLifecycleService(catalog).record_correction(
        position_id=position_id,
        corrected_quantity="12",
        corrected_average_price="11800",
        effective_at="2026-10-22T09:00:00+09:00",
        note="PRIVATE_QUANTITY_CHANGE_REASON",
    )
    before = (_sha(hdb), _sha(mdb))
    result = inspect_workspace(hdb, mdb)
    assert result["status"] == "READ_ONLY_WORKSPACE_STORED_STATE_OBSERVED"
    assert result["stale_reason_counts"]["POSITION_QUANTITY_CHANGED"] == 1
    position = result["groups"][0]["positions"][0]
    assert position["decision_stale"] is True
    assert position["decision_stale_reasons"] == ["POSITION_QUANTITY_CHANGED"]
    recovery_view = position["recovery"]
    assert recovery_view["open_review_present"] is True
    assert recovery_view["open_review_status"] == "OPEN"
    assert recovery_view["open_review_assessment_count"] == 1
    assert recovery_view["latest_assessment_review_action"] == "UNDECIDED"
    assert recovery_view["latest_assessment_thesis_state"] == "UNKNOWN"
    assert recovery_view["assessment_source_plan_matches_active"] is None
    serialized = json.dumps(result)
    for private in (
        "PRIVATE_RECOVERY_OPENING_NOTE",
        "PRIVATE_ASSESSMENT_DETAIL",
        "PRIVATE_QUANTITY_CHANGE_REASON",
        position_id, review_id, "005930",
    ):
        assert private not in serialized
    assert (_sha(hdb), _sha(mdb)) == before


def test_unknown_stale_reason_and_recovery_assessment_codes_are_not_leaked():
    synthetic = {
        "positions": [{
            "decision": {
                "stale": True, "status": "STALE",
                "stale_reasons": ["SECRET_USER_DEFINED_REASON"],
            },
            "recovery": {
                "open_review": {"review_id": "r", "status": "SECRET_STATUS",
                                "opened_at": "SECRET_DATE"},
                "latest_open_assessment": {
                    "thesis_state": "SECRET_THESIS", "review_action": "SECRET_ACTION",
                    "created_at": "SECRET_CREATED",
                },
                "review_history": [{"review": {"review_id": "r"}, "assessments": []}],
            },
        }],
    }
    projection = summarize_workspace(synthetic)
    assert projection["positions"][0]["decision_stale_reasons"] == ["UNRECOGNIZED_STALE_REASON"]
    recovery = projection["positions"][0]["recovery"]
    assert recovery["open_review_status"] == "UNCLASSIFIED"
    assert recovery["latest_assessment_thesis_state"] == "UNCLASSIFIED"
    assert recovery["latest_assessment_review_action"] == "UNCLASSIFIED"
    assert recovery["opened_date"] is None
    assert recovery["latest_assessment_date"] is None
    rendered = json.dumps(projection)
    for raw in ("SECRET_USER_DEFINED_REASON", "SECRET_STATUS", "SECRET_THESIS",
                "SECRET_ACTION", "SECRET_DATE", "SECRET_CREATED"):
        assert raw not in rendered


def test_stale_without_reason_does_not_get_misclassified_as_fresh():
    projection = summarize_workspace({
        "positions": [{
            "decision": {"stale": True, "status": "STALE"},
            "recovery": None,
        }]
    })
    assert projection["stale_reason_counts"] == {"STALE_REASONS_UNAVAILABLE": 1}
    assert projection["open_recovery_reviews"] == 0
    assert projection["positions"][0]["recovery"]["open_review_status"] == "UNAVAILABLE"
