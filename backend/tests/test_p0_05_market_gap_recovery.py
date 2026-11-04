"""P0-05 G1: synthetic KRX gap repair must be bounded and all-or-nothing."""
from __future__ import annotations

import asyncio
import hashlib
import json
import sqlite3
from datetime import date
from pathlib import Path

import pytest

from tools.data import p0_05_market_gap_recovery as repair


TODAY = date(2026, 10, 28)
DATES = ["2026-10-22", "2026-10-23", "2026-10-26", "2026-10-27"]


def _db(tmp_path: Path) -> Path:
    db = tmp_path / "OPERATING_MARKET_PRIVATE.db"
    with sqlite3.connect(db) as conn:
        conn.executescript("""
            CREATE TABLE stock_daily(
                market TEXT NOT NULL,bas_dd TEXT NOT NULL,
                stock_code TEXT NOT NULL,row_json TEXT NOT NULL,
                PRIMARY KEY(market,bas_dd,stock_code)
            );
            CREATE TABLE main_index_daily(
                market TEXT NOT NULL,bas_dd TEXT NOT NULL,
                row_json TEXT NOT NULL,PRIMARY KEY(market,bas_dd)
            );
            CREATE TABLE day_status(
                market TEXT NOT NULL,bas_dd TEXT NOT NULL,
                kind TEXT NOT NULL,status TEXT NOT NULL,
                PRIMARY KEY(market,bas_dd,kind)
            );
        """)
        conn.execute(
            "INSERT INTO stock_daily VALUES(?,?,?,?)",
            ("KOSPI", "20261021", "PRIVATE_PREEXISTING", "{}"),
        )
        conn.execute(
            "INSERT INTO main_index_daily VALUES(?,?,?)",
            ("KOSPI", "20261021", "{}"),
        )
        conn.executemany(
            "INSERT INTO day_status VALUES(?,?,?,?)",
            [( "KOSPI", "20261021", kind, "data" ) for kind in ("stock", "index")],
        )
    return db


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class FakeKRX:
    def __init__(self, *, fail: tuple[str,str,str] | None = None,
                 wrong_date: bool = False, missing_index: bool = False):
        self.fail = fail
        self.wrong_date = wrong_date
        self.missing_index = missing_index
        self.calls = []
        self.closed = False
        self.opened = False

    async def open_session(self):
        self.opened = True

    async def close_session(self):
        self.closed = True

    async def stock_daily(self, market, bas_date, *, force_refresh=False):
        self.calls.append(("stock", market, bas_date, force_refresh))
        if self.fail == ("stock", market, bas_date):
            raise repair.RecoveryHold("HOLD_SYNTHETIC_PROVIDER_FAILED")
        key = "20261001" if self.wrong_date else bas_date
        return {"rows": [
            {"date": key, "code": f"{i:06d}", "name": "PRIVATE",
             "close": 100+i, "open": 100+i, "high": 101+i,
             "low": 99+i, "volume": 100000+i}
            for i in range(120)
        ]}

    async def index_daily(self, market, bas_date, *, force_refresh=False):
        self.calls.append(("index", market, bas_date, force_refresh))
        if self.fail == ("index", market, bas_date):
            raise repair.RecoveryHold("HOLD_SYNTHETIC_PROVIDER_FAILED")
        return {"rows": ([] if self.missing_index else [
            {"date": bas_date, "name": "코스피" if market == "KOSPI" else "코스닥",
             "close": 2450.5},
        ])}


def _run(db, dates=DATES, *, provider, cap=16, requests=True,
         write=True, rights=True):
    return asyncio.run(repair.recover_approved(
        db=db, raw_dates=dates, today=TODAY, provider=provider,
        max_requests=cap, approved_requests=requests,
        approved_write=write, rights_confirmed=rights,
    ))


def test_g1_bounded_plan_is_strict_readonly_and_counts_16_calls(tmp_path):
    db = _db(tmp_path)
    old_sha = _sha(db)
    result = repair.plan(db=db, raw_dates=DATES, today=TODAY)
    assert result["status"] == "READY_TO_REQUEST_SEPARATE_APPROVAL"
    assert result["missing_market_days"] == 8
    assert result["required_provider_endpoint_calls_without_retries"] == 16
    assert result["market_db_write_approved"] is False
    assert result["source_rights_verified"] is False
    assert result["external_requests"] == result["db_writes"] == 0
    assert "PRIVATE" not in json.dumps(result)
    assert _sha(db) == old_sha


@pytest.mark.parametrize("missing_flag", ["requests", "write", "rights"])
def test_g1_independent_explicit_approvals_required_before_provider(tmp_path, missing_flag):
    db = _db(tmp_path)
    before = _sha(db)
    provider = FakeKRX()
    opts = {"requests": True, "write": True, "rights": True}
    opts[missing_flag] = False
    with pytest.raises(repair.RecoveryHold, match="HOLD_EXPLICIT_APPROVAL_REQUIRED"):
        _run(db, provider=provider, **opts)
    assert provider.calls == [] and not provider.opened
    assert _sha(db) == before


def test_g1_full_synthetic_recovery_is_atomic_and_preserves_preexisting_day(tmp_path):
    db = _db(tmp_path)
    provider = FakeKRX()
    report = _run(db, provider=provider)
    assert report["status"] == "MISSING_MARKET_DAYS_RESTORED"
    assert report["market_days_written"] == 8
    assert len(provider.calls) == 16
    assert all(call[-1] is True for call in provider.calls)
    assert provider.closed is True
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM stock_daily").fetchone()[0] == 1 + 120*8
        assert conn.execute("SELECT COUNT(*) FROM main_index_daily").fetchone()[0] == 1 + 8
        assert conn.execute("SELECT COUNT(*) FROM day_status").fetchone()[0] == 2 + 16
        assert conn.execute(
            "SELECT COUNT(*) FROM stock_daily WHERE stock_code='PRIVATE_PREEXISTING'"
        ).fetchone()[0] == 1
    # Re-running is not idempotent overwrite: existing evidence must block.
    before = _sha(db)
    with pytest.raises(repair.RecoveryHold, match="HOLD_PREEXISTING_OR_PARTIAL_MARKET_DAY"):
        _run(db, provider=FakeKRX())
    assert _sha(db) == before


@pytest.mark.parametrize("fake", [
    FakeKRX(wrong_date=True), FakeKRX(missing_index=True),
    FakeKRX(fail=("stock","KOSDAQ","20261027")),
])
def test_g1_invalid_or_partial_krx_response_never_writes_market_db(tmp_path, fake):
    db = _db(tmp_path)
    before = _sha(db)
    with pytest.raises(repair.RecoveryHold):
        _run(db, provider=fake)
    assert fake.closed
    assert _sha(db) == before
    with sqlite3.connect(db) as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM stock_daily WHERE bas_dd != '20261021'"
        ).fetchone()[0] == 0


def test_g1_concurrent_market_write_is_fail_closed_no_rollback_damage(tmp_path):
    db = _db(tmp_path)
    before = _sha(db)
    plan = repair.plan(db=db, raw_dates=["2026-10-22"], today=TODAY)
    assert plan["required_provider_endpoint_calls_without_retries"] == 4
    with sqlite3.connect(db) as conn:
        conn.execute(
            "INSERT INTO day_status VALUES(?,?,?,?)",
            ("KOSDAQ", "20261022", "stock", "data"),
        )
    concurrent_sha = _sha(db)
    with pytest.raises(repair.RecoveryHold, match="HOLD_PREEXISTING_OR_PARTIAL_MARKET_DAY"):
        _run(db, dates=["2026-10-22"], provider=FakeKRX(), cap=4)
    assert _sha(db) == concurrent_sha
    assert before != concurrent_sha


def test_g1_transaction_failure_rolls_back_all_missing_days(tmp_path):
    db = _db(tmp_path)
    with sqlite3.connect(db) as conn:
        conn.execute("""
            CREATE TRIGGER fake_sqlite_failure
            BEFORE INSERT ON main_index_daily
            WHEN NEW.market='KOSDAQ' AND NEW.bas_dd='20261027'
            BEGIN SELECT RAISE(ABORT,'synthetic failure'); END;
        """)
    before = _sha(db)
    with pytest.raises(repair.RecoveryHold, match="HOLD_ATOMIC_MARKET_INSERT_FAILED"):
        _run(db, provider=FakeKRX())
    assert _sha(db) == before


@pytest.mark.parametrize("dates", [
    ["2026-10-28"], ["2026-10-24"], ["2026-10-22","2026-10-22"],
    ["2026-10-22","2026-10-23","2026-10-26","2026-10-27","2026-10-28"],
    ["2026-01-01","2026-10-23"],
])
def test_g1_invalid_date_ranges_do_not_contact_market(tmp_path, dates):
    db = _db(tmp_path)
    before = _sha(db)
    with pytest.raises(repair.RecoveryHold):
        repair.plan(db=db, raw_dates=dates, today=TODAY)
    assert _sha(db) == before


def test_g1_unapproved_network_cap_is_rejected_before_provider(tmp_path):
    db = _db(tmp_path)
    provider = FakeKRX()
    with pytest.raises(repair.RecoveryHold, match="HOLD_NETWORK_REQUEST_CAP_INVALID"):
        _run(db, provider=provider, cap=15)
    assert provider.calls == []


def test_g1_missing_db_and_missing_schema_do_not_create_or_mutate(tmp_path):
    db = tmp_path / "NO_MARKET.db"
    with pytest.raises(repair.RecoveryHold, match="HOLD_MARKET_DB_MISSING"):
        repair.plan(db=db, raw_dates=DATES, today=TODAY)
    assert not db.exists()
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE placeholder(id INTEGER)")
    before = _sha(db)
    with pytest.raises(repair.RecoveryHold, match="HOLD_MARKET_SCHEMA_MISSING"):
        repair.plan(db=db, raw_dates=DATES, today=TODAY)
    assert _sha(db) == before


def test_g1_approved_provider_uses_explicit_operational_root_not_temp_worktree(tmp_path):
    db = _db(tmp_path)
    old_sha = _sha(db)
    with pytest.raises(repair.RecoveryHold, match="HOLD_OPERATIONAL_REPO_REQUIRED"):
        asyncio.run(repair.recover_approved(
            db=db, raw_dates=["2026-10-22"], today=TODAY,
            approved_requests=True, approved_write=True, rights_confirmed=True,
            max_requests=4,
        ))
    with pytest.raises(repair.RecoveryHold, match="HOLD_OPERATIONAL_DB_PATH_MISMATCH"):
        asyncio.run(repair.recover_approved(
            db=db, raw_dates=["2026-10-22"], today=TODAY,
            approved_requests=True, approved_write=True, rights_confirmed=True,
            max_requests=4, operational_repo=tmp_path,
        ))
    assert _sha(db) == old_sha
    assert not (tmp_path / "backend" / "runtime" / "krx" / "budget.sqlite3").exists()


def test_g1_approved_real_provider_import_is_safe_but_missing_key_blocks(tmp_path, monkeypatch):
    import shutil

    root = tmp_path / "operational"
    db = root / "backend" / "runtime" / "market_history" / "market_history.db"
    db.parent.mkdir(parents=True)
    shutil.copy2(_db(tmp_path), db)
    before = _sha(db)
    monkeypatch.delenv("KRX_API_KEY", raising=False)
    with pytest.raises(repair.RecoveryHold, match="HOLD_KRX_KEY_MISSING"):
        asyncio.run(repair.recover_approved(
            db=db, raw_dates=["2026-10-22"], today=TODAY,
            approved_requests=True, approved_write=True, rights_confirmed=True,
            max_requests=4, operational_repo=root,
        ))
    assert _sha(db) == before
    assert not (root / "backend" / "runtime" / "krx" / "budget.sqlite3").exists()


def _operational_setup(tmp_path, monkeypatch, *, key=True, ledger=True,
                       used=2, safe_limit=20):
    import shutil

    root = tmp_path / "operational"
    db = root / "backend" / "runtime" / "market_history" / "market_history.db"
    db.parent.mkdir(parents=True)
    shutil.copy2(_db(tmp_path), db)
    monkeypatch.delenv("KRX_API_KEY", raising=False)
    monkeypatch.setenv("KRX_DAILY_SAFE_LIMIT", str(safe_limit))
    if key:
        (root / ".env").write_text("KRX_API_KEY=synthetic_token_do_not_print\n")
    if ledger:
        budget = root / "backend" / "runtime" / "krx" / "budget.sqlite3"
        budget.parent.mkdir(parents=True)
        with sqlite3.connect(budget) as conn:
            conn.execute(
                "CREATE TABLE krx_daily_usage("
                "day TEXT PRIMARY KEY,requests INTEGER,retries INTEGER,updated_at TEXT)"
            )
            conn.execute(
                "INSERT INTO krx_daily_usage VALUES(?,?,?,?)",
                ("2026-10-28", used, 1 if used else 0, "2026-10-28"),
            )
    return root, db


def test_g1_setup_with_local_key_and_ledger_still_requires_separate_approval(
    tmp_path, monkeypatch,
):
    root, db = _operational_setup(tmp_path, monkeypatch)
    ledger = root / "backend/runtime/krx/budget.sqlite3"
    before = (_sha(db), _sha(ledger))
    result = repair.inspect_local_krx_setup(
        db=db, operational_repo=root, raw_dates=DATES, today=TODAY,
    )
    assert result["status"] == "LOCAL_KRX_CONFIGURATION_PRESENT_APPROVAL_REQUIRED"
    assert result["krx_credential_configured"] is True
    assert result["local_budget_allows_cap"] is True
    assert result["krx_budget_ledger_state"] == "EXISTING_READ_ONLY"
    assert result["service_entitlements_verified"] is False
    assert result["source_rights_verified"] is False
    assert result["external_requests"] == result["db_writes"] == 0
    assert (_sha(db), _sha(ledger)) == before
    payload = json.dumps(result)
    for private in ("synthetic_token", "PRIVATE", str(root), str(db)):
        assert private not in payload


def test_g1_setup_absent_credential_is_hold_no_side_effects(tmp_path, monkeypatch):
    root, db = _operational_setup(tmp_path, monkeypatch, key=False, ledger=False)
    before = _sha(db)
    result = repair.inspect_local_krx_setup(
        db=db, operational_repo=root, raw_dates=DATES, today=TODAY,
    )
    assert result["status"] == "HOLD_KRX_CREDENTIAL_NOT_CONFIGURED"
    assert result["krx_budget_ledger_state"] == "NOT_INITIALIZED"
    assert result["local_budget_allows_cap"] is None
    assert _sha(db) == before
    assert not (root / "backend/runtime/krx/budget.sqlite3").exists()


def test_g1_setup_existing_budget_insufficient_is_hold(tmp_path, monkeypatch):
    root, db = _operational_setup(tmp_path, monkeypatch, used=5, safe_limit=18)
    before = _sha(db)
    result = repair.inspect_local_krx_setup(
        db=db, operational_repo=root, raw_dates=DATES, today=TODAY,
    )
    assert result["status"] == "HOLD_KRX_LOCAL_BUDGET_INSUFFICIENT"
    assert result["local_budget_allows_cap"] is False
    assert _sha(db) == before


def test_g1_setup_missing_budget_does_not_claim_known_capacity(tmp_path, monkeypatch):
    root, db = _operational_setup(tmp_path, monkeypatch, ledger=False)
    result = repair.inspect_local_krx_setup(
        db=db, operational_repo=root, raw_dates=DATES, today=TODAY,
    )
    assert result["status"] == "LOCAL_KRX_CONFIGURATION_PRESENT_APPROVAL_REQUIRED"
    assert result["krx_budget_ledger_state"] == "NOT_INITIALIZED"
    assert result["local_budget_allows_cap"] is None
    assert not (root / "backend/runtime/krx/budget.sqlite3").exists()


def test_g1_setup_rejects_corrupt_budget_schema_and_wrong_db(tmp_path, monkeypatch):
    root, db = _operational_setup(tmp_path, monkeypatch, ledger=False)
    budget = root / "backend/runtime/krx/budget.sqlite3"
    budget.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(budget) as conn:
        conn.execute("CREATE TABLE wrong_table(col TEXT)")
    with pytest.raises(repair.RecoveryHold, match="HOLD_KRX_BUDGET_LEDGER_INVALID"):
        repair.inspect_local_krx_setup(
            db=db, operational_repo=root, raw_dates=DATES, today=TODAY,
        )
    with pytest.raises(repair.RecoveryHold, match="HOLD_OPERATIONAL_DB_PATH_MISMATCH"):
        repair.inspect_local_krx_setup(
            db=tmp_path / "wrong.db", operational_repo=root,
            raw_dates=DATES, today=TODAY,
        )


def test_g1_setup_cli_never_discloses_key_or_runs_provider(tmp_path, monkeypatch):
    import subprocess
    import sys

    root, db = _operational_setup(tmp_path, monkeypatch)
    code = Path(repair.__file__)
    argv = [
        sys.executable, str(code), "--check-local-setup",
        "--operational-repo", str(root), "--market-db", str(db),
        "--date", "2026-10-22", "--date", "2026-10-23",
        "--date", "2026-10-26", "--date", "2026-10-27",
    ]
    completed = subprocess.run(argv, capture_output=True, text=True, check=False)
    assert completed.returncode == 0
    payload = json.loads(completed.stdout)
    assert payload["status"] == "LOCAL_KRX_CONFIGURATION_PRESENT_APPROVAL_REQUIRED"
    assert payload["external_requests"] == 0 and payload["db_writes"] == 0
    for private in ("synthetic_token", "PRIVATE", str(root)):
        assert private not in completed.stdout + completed.stderr

    unsafe = subprocess.run(
        argv + ["--confirm-source-rights"],
        capture_output=True, text=True, check=False,
    )
    assert unsafe.returncode == 2
    assert json.loads(unsafe.stdout)["status"] == "HOLD_APPROVAL_FLAGS_WITHOUT_RUN"
