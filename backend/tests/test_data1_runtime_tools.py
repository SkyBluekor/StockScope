from __future__ import annotations

import json
import os
import sqlite3
from datetime import date, timedelta
from pathlib import Path

import pytest

from app.holdings import HoldingsCatalog, PositionLifecycleService
from app.holdings.management import HoldingManagementService
from tools.data.backup_runtime import create_backup
from tools.data.bootstrap_runtime import bootstrap_runtime
from tools.data.common import (
    DataToolError,
    holdings_counts,
    sha256_file,
)
from tools.data.doctor import collect_report
from tools.data.restore_runtime import restore_backup


T0 = "2026-09-24T09:00:00+09:00"
T1 = "2026-09-24T10:00:00+09:00"


def _holdings_db(path: Path) -> Path:
    catalog = HoldingsCatalog(path)
    catalog.initialize()
    account = catalog.create_position_account(
        provider="MANUAL",
        account_kind="MANUAL",
        display_name="수동 기록",
    )
    opened = PositionLifecycleService(catalog).register_initial_holding(
        market="KOSPI",
        ticker="005930",
        name="삼성전자",
        position_account_id=account.id,
        quantity="10",
        average_price="100",
        effective_at=T0,
    )
    day = catalog.get_or_create_analysis_day(
        monitored_stock_id=opened.stock_id,
        market_date="2026-09-24",
    )
    revision = catalog.append_analysis_revision(
        analysis_day_id=day.id,
        input_fingerprint="data1-fixture",
        strategy_key="trend_following",
        action_state="READY",
        risk_state="READY",
        reference_price="100",
        stop_price="90",
        target1_price="120",
        target2_price="130",
        scanner_version="test",
        analysis_engine_version="test",
        policy_version="test",
        source_versions={},
        snapshot={},
        computed_at="2026-09-24T00:00:00+00:00",
    )
    catalog.promote_current_revision(
        analysis_day_id=day.id,
        revision_id=revision.id,
    )
    HoldingManagementService(catalog).apply_analysis_plan(
        position_id=opened.position.id,
        analysis_revision_id=revision.id,
        applied_at=T1,
    )
    return path


def _market_db(path: Path, rows: int = 70) -> Path:
    with sqlite3.connect(path) as conn:
        conn.executescript(
            """
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
            CREATE TABLE day_status(
                market TEXT NOT NULL,
                bas_dd TEXT NOT NULL,
                kind TEXT NOT NULL,
                status TEXT NOT NULL,
                PRIMARY KEY(market,bas_dd,kind)
            );
            """
        )
        cursor = date(2026, 6, 1)
        dates = []
        while len(dates) < rows:
            if cursor.weekday() < 5:
                dates.append(cursor.strftime("%Y%m%d"))
            cursor += timedelta(days=1)
        for bas_dd in dates:
            conn.execute(
                "INSERT INTO stock_daily VALUES(?,?,?,?)",
                ("KOSPI", bas_dd, "005930", "{}"),
            )
            conn.execute(
                "INSERT INTO main_index_daily VALUES(?,?,?)",
                ("KOSPI", bas_dd, "{}"),
            )
            conn.execute(
                "INSERT INTO day_status VALUES(?,?,?,?)",
                ("KOSPI", bas_dd, "stock", "data"),
            )
            conn.execute(
                "INSERT INTO day_status VALUES(?,?,?,?)",
                ("KOSPI", bas_dd, "index", "data"),
            )
    return path


def test_default_backup_excludes_market_and_secrets(tmp_path):
    holdings = _holdings_db(tmp_path / "holdings.db")
    market = _market_db(tmp_path / "market.db")
    backup = create_backup(
        destination=tmp_path / "backup",
        include_market=False,
        holdings_db=holdings,
        market_db=market,
    )
    manifest = json.loads(
        (backup / "backup_manifest.json").read_text(encoding="utf-8")
    )
    assert (backup / "holdings.db").is_file()
    assert not (backup / "market_history.db").exists()
    assert manifest["contents"]["market_history_db"] is False
    assert manifest["secret_files_included"] == []
    assert not any(path.name == ".env" for path in backup.rglob("*"))


def test_full_backup_includes_market_and_plan_counts(tmp_path):
    holdings = _holdings_db(tmp_path / "holdings.db")
    market = _market_db(tmp_path / "market.db")
    backup = create_backup(
        destination=tmp_path / "full",
        include_market=True,
        holdings_db=holdings,
        market_db=market,
    )
    manifest = json.loads(
        (backup / "backup_manifest.json").read_text(encoding="utf-8")
    )
    assert (backup / "market_history.db").is_file()
    assert manifest["contents"]["market_history_db"] is True
    assert manifest["counts"]["holding_management_plan"] == 1
    assert manifest["counts"]["holding_position_event"] >= 1


def test_restore_roundtrip_preserves_holdings_and_creates_pre_restore_backup(tmp_path):
    source = _holdings_db(tmp_path / "source.db")
    backup = create_backup(
        destination=tmp_path / "backup",
        holdings_db=source,
        include_market=False,
    )
    target = tmp_path / "target.db"
    HoldingsCatalog(target).initialize()
    before_source = holdings_counts(source)

    result = restore_backup(
        backup,
        target_holdings=target,
    )
    assert holdings_counts(target) == before_source
    pre = result["pre_restore_backups"]["holdings"]
    assert pre is not None
    assert Path(pre).is_file()


def test_corrupt_backup_is_blocked_before_target_change(tmp_path):
    source = _holdings_db(tmp_path / "source.db")
    backup = create_backup(
        destination=tmp_path / "backup",
        holdings_db=source,
    )
    target = tmp_path / "target.db"
    HoldingsCatalog(target).initialize()
    before_hash = sha256_file(target)

    with (backup / "holdings.db").open("ab") as fp:
        fp.write(b"corrupt")

    with pytest.raises(DataToolError):
        restore_backup(
            backup,
            target_holdings=target,
        )
    assert sha256_file(target) == before_hash


def test_doctor_is_read_only_and_makes_no_network_request(tmp_path):
    holdings = _holdings_db(tmp_path / "holdings.db")
    market = _market_db(tmp_path / "market.db")
    before_h = sha256_file(holdings)
    before_m = sha256_file(market)

    report = collect_report(
        holdings_path=holdings,
        market_path=market,
    )

    assert report["network_requests"] == 0
    assert report["read_only_preserved"] is True
    assert sha256_file(holdings) == before_h
    assert sha256_file(market) == before_m
    assert report["holdings"]["status"] == "PASS"
    assert report["market_store"]["status"] == "PASS"
    assert report["requirements"]["analysis_min_rows"] > 0
    assert report["requirements"]["analysis_calendar_days"] > 0
    assert report["requirements"]["full_chart_rows"] >= 252


def test_bootstrap_runtime_is_repeatable_and_does_not_create_market_db(tmp_path, monkeypatch):
    holdings = tmp_path / "runtime" / "holdings.db"
    market = tmp_path / "runtime" / "market_history.db"
    monkeypatch.setenv("STOCKSCOPE_HOLDINGS_DB", str(holdings))
    monkeypatch.setenv("STOCKSCOPE_MARKET_STORE_DB", str(market))

    backup_root = tmp_path / "backups"
    first = bootstrap_runtime(backup_root=backup_root)
    second = bootstrap_runtime(backup_root=backup_root)

    assert holdings.is_file()
    assert not market.exists()
    assert first["holdings_db"] == second["holdings_db"]


def test_data_tools_do_not_run_scanner_ranking_or_delete_market_store():
    root = Path(__file__).resolve().parents[2]
    prepare_source = (
        root / "tools" / "data" / "prepare.py"
    ).read_text(encoding="utf-8")
    doctor_source = (
        root / "tools" / "data" / "doctor.py"
    ).read_text(encoding="utf-8")
    restore_source = (
        root / "tools" / "data" / "restore_runtime.py"
    ).read_text(encoding="utf-8")

    assert "scanner.run(" not in prepare_source
    assert "StockScannerService.run" not in prepare_source
    assert "KrxProvider" not in doctor_source
    assert "httpx" not in doctor_source
    assert 'market_history.db").unlink' not in restore_source


def test_setup_and_env_template_expose_data1_entrypoints():
    root = Path(__file__).resolve().parents[2]
    setup = (root / "setup.ps1").read_text(encoding="utf-8")
    env_example = (root / ".env.example").read_text(encoding="utf-8")

    assert "DATA.1 runtime bootstrap" in setup
    assert "tools\\data\\bootstrap_runtime.py" in setup
    assert "tools\\data\\doctor.py" in setup
    assert "STOCKSCOPE_HOLDINGS_DB=" in env_example
    assert "STOCKSCOPE_MARKET_STORE_DB=" in env_example
