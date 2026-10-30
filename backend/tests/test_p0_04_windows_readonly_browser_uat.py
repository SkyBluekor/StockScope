"""P0-04 real FastAPI GET-only Windows Holdings UI worker isolation tests."""
from __future__ import annotations

import hashlib
from pathlib import Path
import sqlite3

from fastapi.testclient import TestClient

from app.holdings import HoldingsCatalog, PositionLifecycleService
from tools.data.migrate_holdings_decision_vnp3s1 import migrate_holdings_decision_store
from tools.data.migrate_holdings_recovery_vnp3s2 import migrate_holdings_recovery_store
from tools.data.p0_02_offline_scanner_replay import snapshot_sqlite_readonly
from tools.data.p0_04_windows_readonly_browser_uat import (
    build_worker_app,
    validate_worker_snapshots,
    SCRATCH_PREFIX,
)


def _stores(tmp_path: Path):
    source = tmp_path / "original"
    source.mkdir()
    original_holdings = source / "holdings.db"
    original_market = source / "market.db"
    with sqlite3.connect(original_market) as conn:
        conn.executescript(
            "CREATE TABLE day_status(market TEXT,bas_dd TEXT,kind TEXT,status TEXT);"
            "CREATE TABLE stock_daily(market TEXT,bas_dd TEXT,stock_code TEXT,row_json TEXT);"
            "CREATE TABLE main_index_daily(market TEXT,bas_dd TEXT,row_json TEXT);"
        )
        conn.execute(
            "INSERT INTO day_status VALUES('KOSPI','20261021','stock','data')"
        )
        conn.execute(
            "INSERT INTO stock_daily VALUES("
            "'KOSPI','20261021','000001',"
            "'{\"date\":\"2026-10-21\",\"open\":\"100\",\"high\":\"102\","
            "\"low\":\"98\",\"close\":\"100\",\"volume\":\"500\"}')"
        )
    catalog = HoldingsCatalog(original_holdings)
    catalog.initialize()
    account = catalog.create_position_account(
        provider="MANUAL", account_kind="MANUAL", display_name="SECRET_ACCOUNT"
    )
    opened = PositionLifecycleService(catalog).register_initial_holding(
        market="KOSPI", ticker="000001", name="SECRET_STOCK",
        position_account_id=account.id,
        quantity="11", average_price="100",
        effective_at="2026-10-21T10:00:00+09:00",
    )
    migrate_holdings_decision_store(original_holdings)
    migrate_holdings_recovery_store(original_holdings)

    scratch = tmp_path / (SCRATCH_PREFIX + "pytest")
    scratch.mkdir()
    holdings = scratch / "holdings_snapshot.sqlite3"
    market = scratch / "market_snapshot.sqlite3"
    snapshot_sqlite_readonly(original_holdings, holdings)
    snapshot_sqlite_readonly(original_market, market)
    return original_holdings, original_market, holdings, market, opened


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_real_get_handlers_work_on_private_snapshot_without_original_mutation(
    tmp_path: Path, monkeypatch
):
    original_holdings, original_market, holdings, market, opened = _stores(tmp_path)
    before = (_sha(original_holdings), _sha(original_market))
    monkeypatch.setenv("STOCKSCOPE_HOLDINGS_DB", str(holdings))
    monkeypatch.setenv("STOCKSCOPE_MARKET_STORE_DB", str(market))
    app = build_worker_app(holdings, market)
    with TestClient(app) as client:
        seed = client.get("/__p004/seed")
        assert seed.status_code == 200
        assert seed.json()["position_id"] == opened.position.id
        assert seed.json()["stock_id"] == opened.stock_id
        dec = client.get(
            f"/api/holdings/stocks/{opened.stock_id}/decision-support"
        )
        mgmt = client.get(
            f"/api/holdings/stocks/{opened.stock_id}/management"
        )
        rec = client.get(
            f"/api/holdings/positions/{opened.position.id}/recovery"
        )
        assert [x.status_code for x in (dec, mgmt, rec)] == [200, 200, 200]
        assert dec.json()["positions"][0]["position_id"] == opened.position.id
        assert mgmt.json()["positions"][0]["position_id"] == opened.position.id
        assert rec.json()["position_id"] == opened.position.id

        # Genuine production mutation routes are ABSENT from this server.
        assert client.post(
            f"/api/holdings/positions/{opened.position.id}/decisions/evaluate"
        ).status_code in (404, 405)
        assert client.post(
            "/api/holdings/decisions/fake-decision/apply-plan",
            json={},
        ).status_code in (404, 405)
        assert client.post(
            f"/api/holdings/positions/{opened.position.id}/recovery/start",
            json={},
        ).status_code in (404, 405)
        assert client.post(
            "/api/holdings/recovery/fake-review/assessments",
            json={},
        ).status_code in (404, 405)
        assert client.post(
            "/api/holdings/recovery/fake-review/close",
            json={},
        ).status_code in (404, 405)
        assert client.get("/api/holdings/stocks").status_code == 404
        assert client.get("/docs").status_code == 404
    assert (_sha(original_holdings), _sha(original_market)) == before


def test_worker_refuses_to_point_at_operational_database(tmp_path: Path):
    original_holdings, original_market, holdings, market, opened = _stores(tmp_path)
    assert not validate_worker_snapshots(original_holdings, original_market)
    assert not validate_worker_snapshots(original_holdings, market)
    assert not validate_worker_snapshots(holdings, original_market)
    assert validate_worker_snapshots(holdings, market)


def test_snapshot_contains_committed_wal_and_does_not_modify_original(tmp_path: Path):
    source = tmp_path / "committed.db"
    writer = sqlite3.connect(source)
    try:
        writer.execute("PRAGMA journal_mode=WAL")
        writer.execute("CREATE TABLE wal_probe(id INTEGER PRIMARY KEY, status TEXT)")
        writer.execute("INSERT INTO wal_probe(status) VALUES('COMMITTED')")
        writer.commit()
        before = _sha(source)
        scratch = tmp_path / (SCRATCH_PREFIX + "wal")
        scratch.mkdir()
        snapshot = scratch / "holdings_snapshot.sqlite3"
        snapshot_sqlite_readonly(source, snapshot)
        with sqlite3.connect(snapshot) as check:
            assert check.execute(
                "SELECT status FROM wal_probe"
            ).fetchone()[0] == "COMMITTED"
        assert _sha(source) == before
    finally:
        writer.close()


def test_worker_does_not_expose_other_positions_or_stocks(tmp_path: Path, monkeypatch):
    original_holdings, original_market, holdings, market, opened = _stores(tmp_path)
    monkeypatch.setenv("STOCKSCOPE_HOLDINGS_DB", str(holdings))
    monkeypatch.setenv("STOCKSCOPE_MARKET_STORE_DB", str(market))
    with TestClient(build_worker_app(holdings, market)) as client:
        assert client.get(
            "/api/holdings/stocks/private-other-stock/management"
        ).status_code == 404
        assert client.get(
            "/api/holdings/stocks/private-other-stock/decision-support"
        ).status_code == 404
        assert client.get(
            "/api/holdings/positions/private-other-position/recovery"
        ).status_code == 404
        assert client.get("/openapi.json").status_code == 404
