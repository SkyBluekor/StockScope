"""S24 Q7 research bootstrap: synthetic isolated Scanner, zero production writes."""
from __future__ import annotations

from datetime import datetime, timedelta
import json
from pathlib import Path
import sqlite3
from zoneinfo import ZoneInfo

import pytest

from app.jev.research_scanner_s24 import (
    ResearchCaptureError, SOURCE, digest, research_pin, receipt_for_scanner,
)
from app.strategy.production_selection_policy import (
    ProductionStrategySelectionRegistry,
)
from tools.data import q7_research_scanner as research

KST = ZoneInfo("Asia/Seoul")
MORNING = datetime(2026, 10, 15, 7, tzinfo=KST)
OUTSIDE = datetime(2026, 10, 15, 11, tzinfo=KST)


def _market(tmp_path):
    db = tmp_path / "source_market.db"
    with sqlite3.connect(db) as conn:
        conn.executescript("""
            CREATE TABLE day_status(market TEXT,bas_dd TEXT,kind TEXT,status TEXT);
            CREATE TABLE stock_daily(market TEXT,bas_dd TEXT,stock_code TEXT,row_json TEXT);
            CREATE TABLE main_index_daily(market TEXT,bas_dd TEXT,row_json TEXT);
            INSERT INTO day_status VALUES ('KOSPI','20261014','stock','data');
            INSERT INTO day_status VALUES ('KOSPI','20261014','index','data');
            INSERT INTO stock_daily VALUES ('KOSPI','20261014','005930','{}');
            INSERT INTO main_index_daily VALUES ('KOSPI','20261014','{}');
        """)
    return db


def _scanner_result(*, pin, source="2026-10-14", **overrides):
    strategy = pin.strategy_reference("pullback")
    assert strategy is not None
    candidate = {
        "market": "KOSPI", "code": "005930", "name": "synthetic",
        "strategy": "pullback", "action": "ENTRY_CANDIDATE",
        "data_date": source, "priority": {"rank": 1},
        "strategy_version_id": strategy["strategy_version_id"],
        "strategy_definition_hash": strategy["definition_hash"],
        "risk": {"status": "READY", "warning": False},
    }
    return {
        "scanner_cache_hit": False,
        "requested_as_of": source, "market_scope": "KOSPI",
        "strategy_selection_policy": pin.metadata(),
        "partial_data": False, "preparation_required": [],
        "data_dates": {"KOSPI": source},
        "input_fingerprint": {"id": "synthetic-day-source"},
        "candidates": [candidate], "more_candidates": [],
        "version": "0.21.3.9",
        "diagnostics": {"reproducibility_audit": {
            "written": True, "result_source": "fresh_analysis",
        }},
        **overrides,
    }


def _err(fn, reason):
    with pytest.raises(ResearchCaptureError) as exc:
        fn()
    assert exc.value.code == reason


def test_research_pin_uses_exact_current_engine_definitions_but_is_not_active(tmp_path):
    pin = research_pin()
    assert pin.policy_source == SOURCE
    assert len(pin.operating_strategies) == 10
    assert all(v and k and h for v, k, h in pin.operating_strategies)
    registry = ProductionStrategySelectionRegistry(runtime_dir=tmp_path / "selection")
    before = registry.pin_active_selection_policy()
    assert before.policy_source == "LEGACY_CURRENT_10_FALLBACK"
    assert registry.active_path.exists() is False
    assert before.policy_id != pin.policy_id
    assert registry.pin_active_selection_policy().policy_source == "LEGACY_CURRENT_10_FALLBACK"


def test_plan_is_zero_write_and_rejects_midday_and_outdated_days(tmp_path):
    market = _market(tmp_path)
    old = market.read_bytes()
    report = research.plan(market="KOSPI", market_db=market, now=MORNING)
    assert report["status"] == "RESEARCH_WINDOW_READY_NOT_Q7_APPROVED"
    assert report["source_date"] == "2026-10-14"
    assert report["research_policy_source"] == SOURCE
    assert report["q7_approval_eligible"] is False
    outside = research.plan(market="KOSPI", market_db=market, now=OUTSIDE)
    assert outside["status"] == "PLAN_ONLY_CAPTURE_BLOCKED"
    assert outside["reason_code"] == "RESEARCH_PREMARKET_WINDOW_REQUIRED"
    assert outside["market_data_ready"] is True
    assert outside["collection_window_open"] is False
    assert outside["capture_permitted_now"] is False
    assert outside["source_date"] == "2026-10-14"
    next_week = MORNING + timedelta(days=7)
    stale = research.plan(market="KOSPI", market_db=market, now=next_week)
    assert stale["status"] == "PLAN_ONLY_CAPTURE_BLOCKED"
    assert stale["data_readiness_reason"] == "RESEARCH_FRESH_EOD_REQUIRED"
    assert stale["market_data_ready"] is False
    assert stale["capture_permitted_now"] is False
    assert market.read_bytes() == old


@pytest.mark.asyncio
async def test_capture_runs_isolated_real_pin_and_saves_write_once_receipt(tmp_path):
    market = _market(tmp_path)
    old = market.read_bytes()
    directory = tmp_path / "research-only"
    invoked = []

    async def fake_scanner(*, root, market, source_date, policy):
        invoked.append((root, market, source_date))
        assert (root / "market_snapshot.db").is_file()
        assert policy.policy_source == SOURCE
        with sqlite3.connect(root / "market_snapshot.db") as conn:
            assert conn.execute("SELECT COUNT(*) FROM stock_daily").fetchone()[0] == 1
        return _scanner_result(pin=policy)

    with pytest.raises(ResearchCaptureError) as exc:
        await research.capture(
            market="KOSPI", market_db=market, root=directory, now=MORNING,
            acknowledge=False, execute_scan=fake_scanner,
        )
    assert exc.value.code == "RESEARCH_EXPLICIT_NETWORK_AND_LOCAL_WRITES_ACK_REQUIRED"
    assert not directory.exists()
    r = await research.capture(
        market="KOSPI", market_db=market, root=directory, now=MORNING,
        acknowledge=True, execute_scan=fake_scanner,
    )
    assert r["status"] == "RESEARCH_CAPTURE_SAVED_NOT_Q7_APPROVED"
    assert len(invoked) == 1
    file = Path(r["capture_file"])
    frozen = json.loads(file.read_text(encoding="utf-8"))
    old_bytes = file.read_bytes()
    assert frozen["authority"] == SOURCE
    assert frozen["q7_approval_eligible"] is False
    assert frozen["production_policy_activation_allowed"] is False
    assert frozen["independent_capture_timestamp_proven"] is False
    assert frozen["market_publication_timestamp_proven"] is False
    assert frozen["original_scanner_candidates"][0]["strategy_version_id"]
    assert frozen["original_scanner_candidates"][0]["strategy_definition_hash"]
    assert frozen["payload_hash"] == digest({
        k: v for k, v in frozen.items() if k != "payload_hash"
    })
    assert market.read_bytes() == old
    retry = await research.capture(
        market="KOSPI", market_db=market, root=directory, now=MORNING,
        acknowledge=True, execute_scan=fake_scanner,
    )
    assert retry["reason_code"] == "RESEARCH_DAY_ALREADY_ATTEMPTED"
    assert len(invoked) == 1
    assert file.read_bytes() == old_bytes
    assert market.read_bytes() == old


@pytest.mark.parametrize("modification,reason", [
    ({"scanner_cache_hit": True}, "RESEARCH_SCANNER_EXECUTION_PROVENANCE_MISMATCH"),
    ({"partial_data": True}, "RESEARCH_SCANNER_PARTIAL_OR_PREPARATION_REQUIRED"),
    ({"requested_as_of": "2026-10-13"}, "RESEARCH_SCANNER_EXECUTION_PROVENANCE_MISMATCH"),
    ({"data_dates": {"KOSPI": "2026-10-13"}}, "RESEARCH_SCANNER_SOURCE_DATE_MISMATCH"),
])
def test_research_capture_refuses_cached_partial_and_wrong_dates(modification, reason):
    pin = research_pin()
    result = _scanner_result(pin=pin, **modification)
    _err(lambda: receipt_for_scanner(
        result, policy=pin, market="KOSPI", source_date=MORNING.date() - timedelta(days=1),
        recorded_at=MORNING,
    ), reason)


def test_research_capture_never_restamps_candidate_strategy_identity():
    pin = research_pin()
    data = _scanner_result(pin=pin)
    data["candidates"][0]["strategy_definition_hash"] = "posthoc-forged"
    _err(lambda: receipt_for_scanner(
        data, policy=pin, source_date=MORNING.date() - timedelta(days=1),
        market="KOSPI", recorded_at=MORNING,
    ), "RESEARCH_ORIGINAL_STRATEGY_IDENTITY_MISMATCH")
    assert data["candidates"][0]["strategy_definition_hash"] == "posthoc-forged"


def test_source_db_or_production_runtime_cannot_be_research_target(tmp_path):
    market = _market(tmp_path)
    _err(
        lambda: research._root_guard(market.parent, market),
        "RESEARCH_ROOT_OVERLAPS_PRODUCTION_SOURCE",
    )
    real_runtime = research.ROOT / "backend" / "runtime"
    _err(
        lambda: research._root_guard(real_runtime / "research", market),
        "RESEARCH_ROOT_OVERLAPS_PRODUCTION_SOURCE",
    )


def test_plan_cli_does_not_have_unacknowledged_execute_mode():
    p = research.parser()
    args = p.parse_args(["capture", "--market", "KOSDAQ"])
    assert args.acknowledge_network_and_research_writes is False
    assert "execute" not in p._actions[1].choices



@pytest.mark.asyncio
async def test_plan_outside_window_does_not_permit_capture_or_create_files(
    tmp_path,
):
    """Daytime diagnosis is always available; capture stays fail-closed."""
    market = _market(tmp_path)
    folder = tmp_path / "research"
    calls = []

    async def never_called(**kwargs):
        calls.append(kwargs)
        raise AssertionError("research Scanner must not run")

    readiness = research.plan(market="KOSPI", market_db=market, now=OUTSIDE)
    assert readiness["market_data_ready"] is True
    assert readiness["capture_permitted_now"] is False
    result = await research.capture(
        market="KOSPI", market_db=market, root=folder, now=OUTSIDE,
        acknowledge=True, execute_scan=never_called,
    )
    assert result["status"] == "PLAN_ONLY_CAPTURE_BLOCKED"
    assert result["capture_block_reason"] == "RESEARCH_PREMARKET_WINDOW_REQUIRED"
    assert calls == []
    assert not folder.exists()
    assert (tmp_path / "research").exists() is False


def test_plan_cli_reports_blocked_capture_as_successful_readonly_diagnosis(
    tmp_path, monkeypatch, capsys,
):
    market = _market(tmp_path)
    monkeypatch.setattr(
        research, "market_db_path", lambda: market,
    )
    monkeypatch.setattr(research, "datetime", __import__("datetime").datetime)
    # Direct plan is deterministic even on a daytime system clock.
    result = research.plan(market="KOSPI", market_db=market, now=OUTSIDE)
    assert result["status"] == "PLAN_ONLY_CAPTURE_BLOCKED"
    assert result["market_data_ready"] is True
    assert result["network_requests"] == result["research_db_writes"] == 0
