"""S26 synthetic KRX+SQLite: read-only plan and isolated append-only EOD prep."""
from __future__ import annotations

from datetime import datetime
from functools import partial
import json
from pathlib import Path
import sqlite3
from zoneinfo import ZoneInfo

import pytest

from app.jev.research_scanner_s24 import ResearchCaptureError, SOURCE, digest
from tools.data import q7_research_scanner as research
from tools.data.q7_research_eod_s26 import candidate_missing_days, prepare_missing_days

KST = ZoneInfo("Asia/Seoul")
FRIDAY = datetime(2026, 10, 16, 7, tzinfo=KST)
MIDDAY = datetime(2026, 10, 16, 12, tzinfo=KST)


def _market(tmp_path, *, partial=False):
    source = tmp_path / "production_market.db"
    with sqlite3.connect(source) as c:
        c.executescript("""
            CREATE TABLE day_status (
                market TEXT, bas_dd TEXT, kind TEXT, status TEXT,
                PRIMARY KEY(market, bas_dd, kind)
            );
            CREATE TABLE stock_daily(
                market TEXT,bas_dd TEXT,stock_code TEXT,row_json TEXT,
                PRIMARY KEY(market,bas_dd,stock_code)
            );
            CREATE TABLE main_index_daily(
                market TEXT,bas_dd TEXT,row_json TEXT,
                PRIMARY KEY(market,bas_dd)
            );
        """)
        for kind in ("stock", "index"):
            c.execute("INSERT INTO day_status VALUES ('KOSPI','20261014',?,'data')", (kind,))
        c.executemany(
            "INSERT INTO stock_daily VALUES ('KOSPI','20261014',?,?)",
            [(f"{i:06d}", "{}") for i in range(120)],
        )
        c.execute(
            "INSERT INTO main_index_daily VALUES ('KOSPI','20261014','{}')"
        )
        if partial:
            c.execute(
                "INSERT INTO day_status VALUES ('KOSPI','20261015','stock','data')"
            )
    return source


class FakeKRX:
    api_key = "fake-key-only"
    def __init__(self, *, stock_rows=120, empty=False, date_mismatch=False,
                 missing_index=False, error=False, budget_block=False):
        self.events = []
        self.stock_rows = stock_rows
        self.empty = empty
        self.date_mismatch = date_mismatch
        self.missing_index = missing_index
        self.error = error
        self.budget_block = budget_block

    def assert_budget(self, estimate):
        self.events.append(("budget", estimate))
        if self.budget_block:
            raise ValueError("synthetic quota exhausted")

    async def open_session(self):
        self.events.append(("open",))

    async def close_session(self):
        self.events.append(("close",))

    async def stock_daily(self, market, day):
        self.events.append(("stock", market, day))
        if self.error:
            raise ValueError("synthetic provider failed")
        compact = "20261013" if self.date_mismatch else day.replace("-", "")
        rows = [] if self.empty else [
            {"code": f"{i:06d}", "date": compact, "close": 40000 + i}
            for i in range(self.stock_rows)
        ]
        return {"date": compact, "rows": rows}

    async def index_daily(self, market, day):
        self.events.append(("index", market, day))
        compact = day.replace("-", "")
        return {
            "date": compact,
            "rows": [] if self.empty or self.missing_index else [
                {"date": compact, "name": "코스피", "close": 2900.0}
            ],
        }

    def request_stats(self):
        return {"network_requests": len([x for x in self.events if x[0] in ("stock", "index")])}


def _copy(source, folder):
    folder.mkdir(parents=True)
    out = folder / "market_snapshot.db"
    research._clone_readonly_source(source, out)
    return out


def _fake_result(policy):
    ref = policy.strategy_reference("pullback")
    return {
        "scanner_cache_hit": False,
        "requested_as_of": "2026-10-15",
        "market_scope": "KOSPI",
        "strategy_selection_policy": policy.metadata(),
        "partial_data": False,
        "preparation_required": [],
        "data_dates": {"KOSPI": "2026-10-15"},
        "input_fingerprint": {"id": "eod-fixture"},
        "candidates": [{
            "market": "KOSPI", "code": "005930", "name": "synthetic",
            "strategy": "pullback", "strategy_version_id": ref["strategy_version_id"],
            "strategy_definition_hash": ref["definition_hash"],
            "priority": {"rank": 1}, "data_date": "2026-10-15",
            "action": "ENTRY_CANDIDATE",
        }],
        "more_candidates": [],
        "version": "0.21.3.9",
        "diagnostics": {"reproducibility_audit": {
            "written": True, "result_source": "fresh_analysis",
            "network_requests": 0,
        }},
    }


def test_s26_plan_is_readonly_and_lists_only_wholly_missing_recent_days(tmp_path):
    source = _market(tmp_path)
    old = source.read_bytes()
    p = research.plan(market="KOSPI", market_db=source, now=FRIDAY)
    assert p["status"] == "PLAN_ONLY_CAPTURE_BLOCKED"
    assert p["reason_code"] == "RESEARCH_UNVERIFIED_PRIOR_WEEKDAY_GAP"
    assert p["eod_preparation_eligible"] is True
    assert p["eod_preparation_dates"] == ["2026-10-15"]
    assert p["eod_preparation_requires_explicit_opt_in"] is True
    assert p["capture_permitted_now"] is False
    assert p["network_requests"] == p["research_db_writes"] == 0
    assert source.read_bytes() == old

    midday = research.plan(market="KOSPI", market_db=source, now=MIDDAY)
    assert midday["eod_preparation_dates"] == ["2026-10-15"]
    assert midday["collection_window_open"] is False
    assert midday["capture_permitted_now"] is False

    with sqlite3.connect(source) as c:
        c.execute(
            "INSERT INTO day_status VALUES ('KOSPI','20261015','stock','data')"
        )
    partial = research.plan(market="KOSPI", market_db=source, now=FRIDAY)
    assert partial["eod_preparation_eligible"] is False
    assert partial["eod_preparation_dates"] == []
    assert partial["capture_permitted_now"] is False


@pytest.mark.asyncio
async def test_s26_real_validator_stores_complete_eod_only_in_isolated_copy(tmp_path):
    source = _market(tmp_path)
    old = source.read_bytes()
    root = tmp_path / "research" / "2026-10-15_kospi"
    copy = _copy(source, root)
    provider = FakeKRX()
    r = await prepare_missing_days(
        market="KOSPI", days=["2026-10-15"], destination_db=copy,
        research_root=root, provider=provider,
    )
    assert r["research_only_market_db_writes"] == 1
    assert r["production_market_db_writes"] == 0
    assert r["stored_days"] == [{
        "date": "2026-10-15", "stock_rows": 120, "index_rows": 1,
    }]
    assert provider.events == [
        ("budget", 2), ("open",), ("stock", "KOSPI", "2026-10-15"),
        ("index", "KOSPI", "2026-10-15"), ("close",),
    ]
    assert source.read_bytes() == old
    p = research.plan(market="KOSPI", market_db=copy, now=FRIDAY)
    assert p["capture_permitted_now"] is True
    assert p["source_date"] == "2026-10-15"


@pytest.mark.asyncio
async def test_s26_real_capture_auto_prepares_only_when_extra_opted_in(tmp_path):
    source = _market(tmp_path)
    before = source.read_bytes()
    root = tmp_path / "research"
    provider = FakeKRX()
    visited = []

    async def fake_scanner(*, root, market, source_date, policy):
        visited.append((market, source_date.isoformat()))
        assert policy.policy_source == SOURCE
        with sqlite3.connect(root / "market_snapshot.db") as c:
            assert c.execute(
                "SELECT COUNT(*) FROM stock_daily WHERE bas_dd='20261015'"
            ).fetchone()[0] == 120
        return _fake_result(policy)

    without = await research.capture(
        market="KOSPI", market_db=source, root=root, now=FRIDAY,
        acknowledge=True, prepare_missing_eod=False,
        execute_scan=fake_scanner,
    )
    assert without["status"] == "PLAN_ONLY_CAPTURE_BLOCKED"
    assert not root.exists()
    assert not provider.events

    ready = await research.capture(
        market="KOSPI", market_db=source, root=root, now=FRIDAY,
        acknowledge=True, prepare_missing_eod=True,
        execute_prepare=partial(prepare_missing_days, provider=provider),
        execute_scan=fake_scanner,
    )
    assert ready["status"] == "RESEARCH_CAPTURE_SAVED_NOT_Q7_APPROVED"
    assert ready["source_date"] == "2026-10-15"
    assert ready["eod_preparation"]["research_only_market_db_writes"] == 1
    assert visited == [("KOSPI", "2026-10-15")]
    receipt = json.loads(Path(ready["capture_file"]).read_text(encoding="utf-8"))
    assert receipt["eod_preparation"]["stored_days"][0]["date"] == "2026-10-15"
    assert receipt["payload_hash"] == digest({
        k: v for k, v in receipt.items() if k != "payload_hash"
    })
    assert receipt["q7_approval_eligible"] is False
    assert receipt["market_publication_timestamp_proven"] is False
    assert source.read_bytes() == before
    again = await research.capture(
        market="KOSPI", market_db=source, root=root, now=FRIDAY,
        acknowledge=True, prepare_missing_eod=True,
        execute_prepare=partial(prepare_missing_days, provider=provider),
        execute_scan=fake_scanner,
    )
    assert again["reason_code"] == "RESEARCH_DAY_ALREADY_ATTEMPTED"
    assert visited == [("KOSPI", "2026-10-15")]


@pytest.mark.asyncio
@pytest.mark.parametrize("mode,reason", [
    ({"empty": True}, "RESEARCH_EOD_PREP_EMPTY_KRX_NOT_CLOSURE_PROOF"),
    ({"missing_index": True}, "RESEARCH_EOD_PREP_INCOMPLETE_PROVIDER_PAIR"),
    ({"date_mismatch": True}, "RESEARCH_EOD_PREP_PROVIDER_DATE_MISMATCH"),
    ({"stock_rows": 10}, "RESEARCH_EOD_PREP_STOCK_RESPONSE_TOO_SMALL"),
    ({"error": True}, "RESEARCH_EOD_PREP_PROVIDER_UNAVAILABLE"),
    ({"budget_block": True}, "RESEARCH_EOD_PREP_KRX_BUDGET_BLOCKED"),
])
async def test_s26_bad_provider_response_never_runs_scanner_and_never_touches_source(
    tmp_path, mode, reason,
):
    source = _market(tmp_path)
    original = source.read_bytes()
    root = tmp_path / "research"
    provider = FakeKRX(**mode)
    called = []

    async def forbidden_scanner(**kw):
        called.append(kw)
        raise AssertionError("Scanner must not run on incomplete EOD")

    with pytest.raises(ResearchCaptureError) as exc:
        await research.capture(
            market="KOSPI", market_db=source, root=root,
            now=FRIDAY, acknowledge=True, prepare_missing_eod=True,
            execute_prepare=partial(prepare_missing_days, provider=provider),
            execute_scan=forbidden_scanner,
        )
    assert exc.value.code == reason
    assert called == []
    assert source.read_bytes() == original
    folder = root / "2026-10-15_kospi"
    assert folder.is_dir()  # failed attempt is not silently retried
    assert not (folder / "scanner_research_capture.json").exists()
    with sqlite3.connect(folder / "market_snapshot.db") as c:
        assert c.execute(
            "SELECT COUNT(*) FROM stock_daily WHERE bas_dd='20261015'"
        ).fetchone()[0] == 0


@pytest.mark.asyncio
async def test_s26_missing_eod_never_runs_midday_even_with_both_acknowledgements(
    tmp_path,
):
    source = _market(tmp_path)
    root = tmp_path / "research"
    called = []

    async def never_prepare(**kw):
        called.append("prep")
        raise AssertionError()

    async def never_scan(**kw):
        called.append("scanner")
        raise AssertionError()

    r = await research.capture(
        market="KOSPI", market_db=source, root=root, now=MIDDAY,
        acknowledge=True, prepare_missing_eod=True,
        execute_prepare=never_prepare, execute_scan=never_scan,
    )
    assert r["status"] == "PLAN_ONLY_CAPTURE_BLOCKED"
    assert r["capture_permitted_now"] is False
    assert called == []
    assert not root.exists()


def test_s26_command_requires_separate_eod_opt_in():
    parser = research.parser()
    args = parser.parse_args([
        "capture", "--market", "KOSPI",
        "--acknowledge-network-and-research-writes",
    ])
    assert args.prepare_missing_eod is False
    assert parser.parse_args([
        "capture", "--market", "KOSPI",
        "--acknowledge-network-and-research-writes",
        "--prepare-missing-eod",
    ]).prepare_missing_eod is True
