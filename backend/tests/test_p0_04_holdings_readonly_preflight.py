"""P0-04 Windows holdings read-only audit (synthetic TEMP databases only)."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys

from app.holdings import HoldingsCatalog, PositionLifecycleService
from tools.data.migrate_holdings_decision_vnp3s1 import migrate_holdings_decision_store
from tools.data.p0_04_holdings_readonly_preflight import inspect_holdings_environment

SCRIPT = Path(__file__).resolve().parents[2] / "tools" / "data" / "p0_04_holdings_readonly_preflight.py"


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _market(path: Path) -> Path:
    with sqlite3.connect(path) as conn:
        conn.executescript(
            "CREATE TABLE day_status(market TEXT,bas_dd TEXT,kind TEXT,status TEXT);"
            "CREATE TABLE stock_daily(market TEXT,bas_dd TEXT,stock_code TEXT,row_json TEXT);"
            "CREATE TABLE main_index_daily(market TEXT,bas_dd TEXT,row_json TEXT);"
            "INSERT INTO stock_daily VALUES ('KOSPI','20261021','005930','{}');"
        )
    return path


def _fixture(tmp_path: Path, *, register: bool = True):
    holdings = tmp_path / "holdings.db"
    market = _market(tmp_path / "market.db")
    catalog = HoldingsCatalog(holdings)
    catalog.initialize()
    if register:
        account = catalog.create_position_account(
            provider="MANUAL",
            account_kind="MANUAL",
            display_name="SECRET_ACCOUNT_NEVER_EXPOSE",
        )
        PositionLifecycleService(catalog).register_initial_holding(
            market="KOSPI", ticker="005930", name="PRIVATE_TICKER_NAME",
            position_account_id=account.id,
            quantity="17", average_price="12345",
            effective_at="2026-10-21T09:00:00+09:00",
        )
    return holdings, market


def test_missing_paths_are_blocked_without_creating_any_database(tmp_path: Path):
    h = tmp_path / "missing-holdings.db"
    m = tmp_path / "missing-market.db"
    report = inspect_holdings_environment(h, m)
    assert report["status"] == "BLOCKED_HOLDINGS_DB_MISSING"
    assert not h.exists() and not m.exists()
    assert report["db_write_calls"] == report["external_requests"] == 0

    h, _ = _fixture(tmp_path)
    report = inspect_holdings_environment(h, m)
    assert report["status"] == "BLOCKED_MARKET_DB_MISSING"
    assert not m.exists()


def test_read_only_missing_migrations_and_private_aggregate_report(tmp_path: Path):
    h, m = _fixture(tmp_path)
    before = (_hash(h), _hash(m))
    report = inspect_holdings_environment(h, m)

    assert report["status"] == "HOLD_DECISION_SCHEMA_PREPARATION_REQUIRED"
    assert report["domains"]["decision"]["status"] == "MIGRATION_REQUIRED"
    assert report["domains"]["recovery"]["status"] == "MIGRATION_REQUIRED"
    assert report["domains"]["watch"]["status"] == "MIGRATION_REQUIRED"
    assert report["counts"]["registered_accounts"] == 1
    assert report["counts"]["open_positions"] == 1
    assert report["consistency"]["open_positions_without_active_plan"] == 1
    assert report["market"]["latest_stock_date"] == "20261021"
    assert report["ready_for_plan_write"] is False
    assert report["latest_official_eod_verified"] is False
    serialized = json.dumps(report, ensure_ascii=False)
    for secret in ("SECRET_ACCOUNT_NEVER_EXPOSE", "PRIVATE_TICKER_NAME", "005930", "12345", "17"):
        # 17/12345 may occur incidentally as unrelated counts; check identifying
        # account/stock text and exact sensitive price/ticker only.
        if secret in {"17", "12345"}:
            continue
        assert secret not in serialized
    assert (_hash(h), _hash(m)) == before


def test_explicit_decision_migration_report_is_ready_for_read_only_review(tmp_path: Path):
    h, m = _fixture(tmp_path)
    migrate_holdings_decision_store(h)
    before = (_hash(h), _hash(m))
    report = inspect_holdings_environment(h, m)
    assert report["status"] == "READ_ONLY_HOLDINGS_PREFLIGHT_OBSERVED"
    assert report["domains"]["decision"]["status"] == "READY"
    assert report["counts"]["active_plans"] == 0
    assert report["ready_for_plan_write"] is False
    assert report["user_confirmation_still_required"] is True
    assert (_hash(h), _hash(m)) == before


def test_empty_holdings_is_not_misrepresented_as_user_uat(tmp_path: Path):
    h, m = _fixture(tmp_path, register=False)
    migrate_holdings_decision_store(h)
    report = inspect_holdings_environment(h, m)
    assert report["status"] == "NO_OPEN_POSITIONS_TO_UAT"
    assert report["counts"]["open_positions"] == 0


def test_partial_and_unsupported_schema_fail_closed(tmp_path: Path):
    h, m = _fixture(tmp_path)
    with sqlite3.connect(h) as conn:
        conn.execute("CREATE TABLE holding_decision_record (id TEXT,position_id TEXT)")
    partial = inspect_holdings_environment(h, m)
    assert partial["domains"]["decision"]["status"] == "PARTIAL_SCHEMA_REVIEW_REQUIRED"

    with sqlite3.connect(h) as conn:
        conn.execute("DROP TABLE holding_decision_record")
    migrate_holdings_decision_store(h)
    with sqlite3.connect(h) as conn:
        conn.execute(
            "UPDATE holding_decision_schema_meta SET value='UNSUPPORTED' WHERE key='schema_version'"
        )
    wrong = inspect_holdings_environment(h, m)
    assert wrong["domains"]["decision"]["status"] == "SCHEMA_UNSUPPORTED"
    assert wrong["status"] == "HOLD_DECISION_SCHEMA_PREPARATION_REQUIRED"


def test_missing_base_table_and_invalid_database_are_blocked(tmp_path: Path):
    h, m = _fixture(tmp_path)
    with sqlite3.connect(h) as conn:
        conn.execute("DROP TABLE holding_position_event")
    report = inspect_holdings_environment(h, m)
    assert report["status"] == "BLOCKED_HOLDINGS_BASE_SCHEMA_MISSING"

    h.write_bytes(b"Not an SQLite database - no private data")
    report = inspect_holdings_environment(h, m)
    assert report["status"] == "BLOCKED_READ_ONLY_DB_QUERY_FAILED"


def test_cli_uses_only_explicit_paths_and_does_not_mutate_db(tmp_path: Path):
    h, m = _fixture(tmp_path)
    before = (_hash(h), _hash(m))
    process = subprocess.run(
        [sys.executable, str(SCRIPT), "--holdings-db", str(h), "--market-db", str(m)],
        capture_output=True, text=True, timeout=20, check=False,
    )
    assert process.returncode == 2  # migration review needed; never auto-fix
    report = json.loads(process.stdout)
    assert report["status"] == "HOLD_DECISION_SCHEMA_PREPARATION_REQUIRED"
    assert process.stderr == ""
    assert (_hash(h), _hash(m)) == before


def test_wal_committed_holdings_are_visible_without_immutable_snapshot(tmp_path: Path):
    h, m = _fixture(tmp_path, register=False)
    migrate_holdings_decision_store(h)
    with sqlite3.connect(h) as writer:
        writer.execute("PRAGMA journal_mode=WAL")
        writer.execute("PRAGMA wal_autocheckpoint=0")
        writer.execute(
            "INSERT INTO position_account(id,provider,account_kind,display_name,status,created_at,updated_at) "
            "VALUES('ac1','MANUAL','MANUAL','PRIVATE_WAL','ACTIVE','now','now')"
        )
        writer.commit()  # committed WAL data still visible before checkpoint
        report = inspect_holdings_environment(h, m)
        assert report["counts"]["registered_accounts"] == 1
        assert report["domains"]["decision"]["status"] == "READY"
        assert "PRIVATE_WAL" not in json.dumps(report)
