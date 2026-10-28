"""G1 first prospective capture: bound operational paths, budget and process identity."""
from __future__ import annotations

import asyncio
from contextlib import contextmanager
from datetime import datetime
import hashlib
import json
from pathlib import Path
import sqlite3

import pytest

from tools.data import p0_05_g1_capture_once as g1
from tools.data import prospective_daily as s17

KST = s17.KST
MORNING = datetime(2026, 10, 29, 7, 0, tzinfo=KST)
OUTSIDE = datetime(2026, 10, 29, 12, 0, tzinfo=KST)


def _sha(path: Path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _operational(tmp_path: Path):
    root = tmp_path / "real_repo"
    market = root / "backend/runtime/market_history/market_history.db"
    sim = root / "backend/runtime/simulation/simulation.db"
    budget = root / "backend/runtime/krx/budget.sqlite3"
    for p in (market, sim, budget):
        p.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(market) as conn:
        conn.execute("CREATE TABLE dummy(x INTEGER)")
    with sqlite3.connect(sim) as conn:
        conn.execute("CREATE TABLE dummy(x INTEGER)")
    with sqlite3.connect(budget) as conn:
        conn.execute("CREATE TABLE krx_daily_usage("
                     "day TEXT PRIMARY KEY,requests INTEGER,retries INTEGER,updated_at TEXT)")
        conn.execute("INSERT INTO krx_daily_usage VALUES(?,?,?,?)",
                     ("2026-10-29", 3, 0, "2026-10-29"))
    return root, market, sim, budget


def test_g1_morning_window_only_and_inert_without_dbs(tmp_path):
    result = g1.readiness(tmp_path, scope="ALL", cap=128, now=OUTSIDE)
    assert result["status"] == "HOLD_OUTSIDE_PREMARKET_WINDOW"
    assert result["external_requests"] == result["market_db_writes"] == 0
    assert not (tmp_path / "backend").exists()
    with pytest.raises(s17.DailyError, match="HOLD_OPERATIONAL_STORE_OR_BUDGET_MISSING"):
        g1.readiness(tmp_path, scope="ALL", cap=128, now=MORNING)


@pytest.mark.parametrize("flags", [
    (False, True, True), (True, False, True), (True, True, False),
])
def test_g1_capture_requires_all_three_explicit_grants_without_side_effects(
    tmp_path, flags,
):
    response = g1.capture_approved(
        root=tmp_path, scope="ALL", candidate_limit=5,
        max_krx_requests=128,
        approve_krx=flags[0], approve_simulation_write=flags[1],
        confirm_services=flags[2], now=MORNING,
    )
    assert response["status"] == "HOLD_EXPLICIT_G1_CAPTURE_APPROVAL_REQUIRED"
    assert response["external_requests"] == 0
    assert not (tmp_path / "backend").exists()


def test_g1_budget_checker_is_read_only_and_shared_persistent(tmp_path, monkeypatch):
    root, market, sim, budget = _operational(tmp_path)
    monkeypatch.setenv("KRX_DAILY_SAFE_LIMIT", "130")
    before = _sha(budget)
    assert g1._budget_allowed(budget, 127, MORNING) is True
    assert g1._budget_allowed(budget, 128, MORNING) is False
    assert _sha(budget) == before
    for cap in (0, 1025):
        with pytest.raises(s17.DailyError, match="HOLD_OPERATIONAL_KRX_LEDGER_UNAVAILABLE"):
            g1._budget_allowed(budget, cap, MORNING)


def test_g1_readiness_requires_matching_operational_store(tmp_path, monkeypatch):
    root, market, sim, budget = _operational(tmp_path)
    monkeypatch.setattr(s17, "preflight_local_g1", lambda **kw: {
        "status": "LOCAL_STORED_EOD_READY_APPROVAL_REQUIRED",
        "stored_common_data_date": "2026-10-28",
    })
    result = g1.readiness(root, scope="ALL", cap=128, now=MORNING)
    assert result["status"] == "LOCAL_G1_ELIGIBLE_APPROVAL_REQUIRED"
    assert result["stored_common_data_date"] == "2026-10-28"
    assert result["production_capture_approved"] is False
    assert result["provider_service_entitlements_verified"] is False
    assert result["external_requests"] == 0
    assert result["market_db_writes"] == 0

    monkeypatch.setattr(s17, "preflight_local_g1", lambda **kw: {
        "status": "HOLD_EXISTING_CAPTURE_OR_PENDING",
        "stored_common_data_date": "2026-10-28",
    })
    held = g1.readiness(root, scope="ALL", cap=128, now=MORNING)
    assert held["status"] == "HOLD_EXISTING_CAPTURE_OR_PENDING"


def test_g1_actual_path_binding_isolated_server_and_single_s17_call(
    tmp_path, monkeypatch,
):
    root, market, sim, budget = _operational(tmp_path)
    (root / ".env").write_text("KRX_API_KEY=private-synthetic-key-never-print\\n",
                               encoding="utf-8")
    monkeypatch.delenv("KRX_API_KEY", raising=False)
    monkeypatch.setattr(s17, "preflight_local_g1", lambda **kw: {
        "status": "LOCAL_STORED_EOD_READY_APPROVAL_REQUIRED",
        "stored_common_data_date": "2026-10-28",
    })
    child = {}
    observed = {}

    @contextmanager
    def fake_isolated_backend(**kwargs):
        child.update(kwargs)
        yield

    def fake_run_once(**kwargs):
        observed.update(kwargs)
        with kwargs["server"](kwargs["http"]):
            pass
        return {"status": "SCANNER_CAPTURED_AND_OUTCOME_CHECKED",
                "persisted_capture_verified": True}

    monkeypatch.setattr(g1, "_isolated_backend", fake_isolated_backend)
    monkeypatch.setattr(s17, "run_once", fake_run_once)
    before = [_sha(x) for x in (market, sim, budget)]
    report = g1.capture_approved(
        root=root, scope="ALL", candidate_limit=5,
        max_krx_requests=128, approve_krx=True,
        approve_simulation_write=True, confirm_services=True, now=MORNING,
    )
    assert report["status"] == "SCANNER_CAPTURED_AND_OUTCOME_CHECKED"
    assert report["user_approved_krx_cap"] == 128
    assert observed["simulation_db"].resolve() == sim.resolve()
    assert observed["market_db"].resolve() == market.resolve()
    assert observed["now"] == MORNING
    assert child["child_env"]["STOCKSCOPE_SIM_DB"] == str(sim.resolve())
    assert child["child_env"]["STOCKSCOPE_MARKET_STORE_DB"] == str(market.resolve())
    assert child["child_env"]["STOCKSCOPE_KRX_BUDGET_DB"] == str(budget.resolve())
    assert child["child_env"]["STOCKSCOPE_G1_MAX_KRX_CALLS"] == "128"
    assert child["child_env"]["STOCKSCOPE_G1_WORKER_NONCE"] == child["expected_nonce"]
    assert child["port"] > 0
    assert [_sha(x) for x in (market, sim, budget)] == before
    assert not any(k in json.dumps(report) for k in ("private-synthetic-key", str(root)))
    assert "KRX_API_KEY" not in __import__("os").environ


def test_g1_wrong_worker_identity_refused_and_child_terminated(monkeypatch):
    events = []

    class FakeProcess:
        def __init__(self):
            self.dead = False
        def poll(self):
            return 0 if self.dead else None
        def terminate(self):
            events.append("terminate")
            self.dead = True
        def wait(self, timeout):
            events.append("wait")

    monkeypatch.setattr(g1.subprocess, "Popen", lambda *args, **kwargs: FakeProcess())
    with pytest.raises(s17.DailyError, match="G1_ISOLATED_BACKEND_IDENTITY_MISMATCH"):
        with g1._isolated_backend(
            child_env={}, expected_nonce="unique-worker-123",
            port=12123, http=lambda path: {
                "status": "running", "real_trading": False,
                "g1_worker_nonce": "another-service",
            },
        ):
            raise AssertionError("must never enter another server")
    assert events == ["terminate", "wait"]


def test_krx_budget_cross_provider_g1_cap_counts_retries(tmp_path, monkeypatch):
    from app.market.krx_budget import KrxApiBudget, KrxBudgetExceeded

    monkeypatch.setenv("STOCKSCOPE_G1_MAX_KRX_CALLS", "3")
    monkeypatch.setattr(KrxApiBudget, "_g1_consumed", 0)
    budget = tmp_path / "runtime" / "krx" / "budget.sqlite3"
    first = KrxApiBudget(db_path=budget, safe_limit=100)
    second = KrxApiBudget(db_path=budget, safe_limit=100)
    first.consume()
    second.consume(retry=True)
    first.consume()
    with pytest.raises(KrxBudgetExceeded, match="Approved G1"):
        second.consume()
    assert KrxApiBudget._g1_consumed == 3
    with sqlite3.connect(budget) as conn:
        row = conn.execute("SELECT requests,retries FROM krx_daily_usage").fetchone()
    assert row == (3, 1)


def test_market_store_default_respects_explicit_operational_env(tmp_path, monkeypatch):
    from app.backtest.market_store import HistoricalMarketStore

    target = tmp_path / "operational" / "market.db"
    monkeypatch.setenv("STOCKSCOPE_MARKET_STORE_DB", str(target))
    store = HistoricalMarketStore()
    assert store.db_path == target
    assert target.exists()
    override = tmp_path / "isolated" / "market.db"
    explicit = HistoricalMarketStore(db_path=override)
    assert explicit.db_path == override
    assert override.exists()


@pytest.mark.parametrize("forbidden", [
    "https://127.0.0.1:8000",
    "http://localhost:8000",
    "http://example.com:8000",
    "http://127.0.0.1:8000/extra",
    "http://user@127.0.0.1:8000",
    "http://127.0.0.1:99999",
])
def test_s17_http_backend_cannot_escape_numeric_loopback(forbidden):
    with pytest.raises(s17.DailyError, match="INVALID_LOOPBACK_BACKEND_URL"):
        s17._http("/", base_url=forbidden)


def test_g1_operator_cli_is_no_side_effects_outside_morning(tmp_path):
    import subprocess
    import sys

    script = Path(g1.__file__)
    result = subprocess.run([
        sys.executable, str(script), "--operational-repo", str(tmp_path),
        "--scope", "ALL",
    ], capture_output=True, text=True, check=False)
    report = json.loads(result.stdout)
    # Regardless of the actual runner clock this uses no KRX or server:
    assert report["status"].startswith("HOLD_")
    assert not (tmp_path / "backend").exists()
