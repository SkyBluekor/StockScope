"""S31-F datewise KRX EOD collection: no real HTTP, no production market writes."""
from __future__ import annotations

import asyncio
from datetime import date
import json
from pathlib import Path
import sqlite3

import pytest

from tools.data import krx_datewise_collector as mod


def _source(tmp_path):
    path = tmp_path / "original.db"
    with sqlite3.connect(path) as conn:
        conn.executescript("""
        CREATE TABLE stock_daily (
          market TEXT,bas_dd TEXT,stock_code TEXT,row_json TEXT,
          PRIMARY KEY(market,bas_dd,stock_code)
        );
        CREATE TABLE main_index_daily (
          market TEXT,bas_dd TEXT,row_json TEXT,
          PRIMARY KEY(market,bas_dd)
        );
        CREATE TABLE day_status (
          market TEXT,bas_dd TEXT,kind TEXT,status TEXT,
          PRIMARY KEY(market,bas_dd,kind)
        );
        """)
        for i in range(150):
            code = f"{i+1000:06d}"
            conn.execute(
                "INSERT INTO stock_daily VALUES(?,?,?,?)",
                ("KOSPI","20261014",code,json.dumps({
                    "code":code,"date":"20261014","close":100
                })),
            )
        conn.execute(
            "INSERT INTO main_index_daily VALUES(?,?,?)",
            ("KOSPI","20261014",json.dumps({
                "date":"20261014","name":"코스피","close":3000
            })),
        )
        conn.executemany(
            "INSERT INTO day_status VALUES(?,?,?,?)",
            [("KOSPI","20261014","stock","data"),
             ("KOSPI","20261014","index","data")],
        )
    return path


def _paths(tmp_path):
    root = tmp_path / "isolated" / "eod"
    return root, root / "market_research.db"


class FakeKrx:
    def __init__(self, *, empty_on=None, bad_index_on=None):
        self.empty_on = empty_on
        self.bad_index_on = bad_index_on
        self.stock_calls = []
        self.index_calls = []
        self.budget_check = None
        self.opened = False
        self.closed = False

    def assert_budget(self, estimate):
        self.budget_check = estimate

    async def open_session(self):
        self.opened = True

    async def close_session(self):
        self.closed = True

    async def stock_daily(self, market, day):
        key = day.strftime("%Y%m%d")
        self.stock_calls.append(key)
        rows = [] if key == self.empty_on else [
            {"date":key,"code":f"{1000+i:06d}","close":101,"market":market}
            for i in range(150)
        ]
        return {"date":key, "rows":rows}

    async def index_daily(self, market, day):
        key = day.strftime("%Y%m%d")
        self.index_calls.append(key)
        if key == self.empty_on:
            rows = []
        else:
            rows = [{
                "date":key,
                "name":"다른 지수" if key == self.bad_index_on else "코스피",
                "close":3020.0,
            }]
        return {"date":key,"rows":rows}

    def request_stats(self):
        return {"network_requests":len(self.stock_calls)+len(self.index_calls)}


def _collect(source, target, root, provider, *, start="2026-10-15", through="2026-10-16"):
    return asyncio.run(mod.collect(
        source, target, research_root=root, market="KOSPI",
        start=start, through=through, today=date(2026,10,19),
        acknowledge=True, provider=provider,
    ))


def test_plan_only_detects_date_gaps_without_creating_copy_or_network(tmp_path):
    source = _source(tmp_path)
    root, target = _paths(tmp_path)
    result = mod.plan(
        source,target,market="KOSPI",start="2026-10-14",
        through="2026-10-18",research_root=root,today=date(2026,10,19)
    )
    assert result["status"] == "PLAN_ONLY"
    assert result["pending_dates"] == ["2026-10-15","2026-10-16"]
    assert result["verified_closed_count"] == 2
    assert result["complete_count"] == 1
    assert result["potential_api_requests"] == 4
    assert not target.exists()
    assert not root.exists()


def test_collect_two_days_atomic_in_research_copy_and_does_not_change_original(tmp_path):
    source = _source(tmp_path)
    root,target = _paths(tmp_path)
    original = source.read_bytes()
    provider = FakeKrx()
    result = _collect(source,target,root,provider)
    assert result["status"] == "RESEARCH_DAYS_STORED"
    assert result["stored_count"] == 2
    assert result["new_research_copy"] is True
    assert provider.budget_check == 4
    assert provider.opened and provider.closed
    assert provider.stock_calls == ["20261015","20261016"]
    assert source.read_bytes() == original
    with mod._connect_ro(target) as conn:
        for day in ("20261015","20261016"):
            assert conn.execute(
                "SELECT COUNT(*) FROM stock_daily WHERE bas_dd=?", (day,)
            ).fetchone()[0] == 150
            assert conn.execute(
                "SELECT COUNT(*) FROM main_index_daily WHERE bas_dd=?", (day,)
            ).fetchone()[0] == 1
            assert conn.execute(
                "SELECT COUNT(*) FROM day_status WHERE bas_dd=?", (day,)
            ).fetchone()[0] == 2


def test_rerun_is_idempotent_and_makes_no_network_calls(tmp_path):
    source=_source(tmp_path)
    root,target=_paths(tmp_path)
    _collect(source,target,root,FakeKrx())
    before=target.read_bytes()
    provider=FakeKrx()
    result=_collect(source,target,root,provider)
    assert result["status"] == "NO_MISSING_DAYS"
    assert provider.stock_calls == provider.index_calls == []
    assert target.read_bytes() == before


def test_partial_existing_date_blocks_all_collection_without_modification(tmp_path):
    source=_source(tmp_path)
    with sqlite3.connect(source) as c:
        c.execute(
            "INSERT INTO day_status VALUES (?,?,?,?)",
            ("KOSPI","20261015","stock","data"),
        )
    before=source.read_bytes()
    root,target=_paths(tmp_path)
    with pytest.raises(mod.CollectorError,match="HOLD_EXISTING_DATA_CONFLICT"):
        _collect(source,target,root,FakeKrx())
    assert source.read_bytes()==before
    assert not target.exists()


def test_unverified_empty_day_stops_forward_collection_and_retries_are_safe(tmp_path):
    source=_source(tmp_path)
    root,target=_paths(tmp_path)
    p=FakeKrx(empty_on="20261015")
    result=_collect(source,target,root,p)
    assert result["status"] == "PARTIAL_UNVERIFIED"
    assert result["stored_count"] == 0
    assert result["errors"][0]["reason_code"] == "KRX_EMPTY_NO_INDEPENDENT_CLOSURE_PROOF"
    assert p.stock_calls == ["20261015"]
    assert source.exists() and target.exists()
    after=mod.plan(source,target,market="KOSPI",start="2026-10-15",through="2026-10-16",research_root=root,today=date(2026,10,19))
    assert after["pending_dates"] == ["2026-10-15","2026-10-16"]


def test_invalid_main_index_does_not_persist_partial_day(tmp_path):
    source=_source(tmp_path)
    root,target=_paths(tmp_path)
    p=FakeKrx(bad_index_on="20261015")
    result=_collect(source,target,root,p)
    assert result["status"] == "PARTIAL_UNVERIFIED"
    assert result["errors"][0]["reason_code"] == "KRX_MAIN_INDEX_MISSING"
    with mod._connect_ro(target) as c:
        assert c.execute(
            "SELECT COUNT(*) FROM stock_daily WHERE bas_dd='20261015'"
        ).fetchone()[0] == 0


def test_no_future_or_too_large_requests_and_no_live_market_target(tmp_path):
    source=_source(tmp_path)
    root,target=_paths(tmp_path)
    with pytest.raises(mod.CollectorError,match="TODAY_OR_FUTURE_EOD_UNVERIFIED"):
        mod.plan(source,target,market="KOSPI",start="2026-10-19",through="2026-10-19",research_root=root,today=date(2026,10,19))
    with pytest.raises(mod.CollectorError,match="DATE_RANGE_OUTSIDE_SAFE_LIMIT"):
        mod.plan(source,target,market="KOSPI",start="2026-01-01",through="2026-10-16",research_root=root,today=date(2026,10,19))
    with pytest.raises(mod.CollectorError,match="RESEARCH_DB_MUST_BE_ISOLATED"):
        mod.plan(source,source,market="KOSPI",start="2026-10-15",through="2026-10-16",research_root=root,today=date(2026,10,19))


def test_collect_requires_explicit_ack_and_does_not_copy_or_read_api_key(tmp_path):
    source=_source(tmp_path)
    root,target=_paths(tmp_path)
    with pytest.raises(mod.CollectorError,match="EXPLICIT_RESEARCH_WRITE_ACK_REQUIRED"):
        asyncio.run(mod.collect(
            source,target,research_root=root,market="KOSPI",
            start="2026-10-15",through="2026-10-16",
            today=date(2026,10,19),acknowledge=False,
        ))
    assert not root.exists()


def test_plan_against_existing_copy_preserves_identity(tmp_path):
    source=_source(tmp_path)
    root,target=_paths(tmp_path)
    _collect(source,target,root,FakeKrx())
    result=mod.plan(source,target,market="KOSPI",start="2026-10-14",through="2026-10-18",research_root=root,today=date(2026,10,19))
    assert result["read_from"] == "RESEARCH_COPY"
    assert result["complete_count"] == 3
    assert result["pending_dates"] == []


def test_date_truncation_from_krx_rejected(tmp_path):
    source=_source(tmp_path)
    root,target=_paths(tmp_path)
    class Truncated(FakeKrx):
        async def stock_daily(self, market, day):
            result=await super().stock_daily(market,day)
            result["rows"]=result["rows"][:20]
            return result
    result=_collect(source,target,root,Truncated())
    assert result["status"] == "PARTIAL_UNVERIFIED"
    assert result["errors"][0]["reason_code"] == "STOCK_RESPONSE_TOO_SMALL"
    with mod._connect_ro(target) as c:
        assert c.execute("SELECT COUNT(*) FROM stock_daily WHERE bas_dd='20261015'").fetchone()[0] == 0

def test_backup_connection_closed_before_publish_windows_like(tmp_path, monkeypatch):
    """Reproduce Windows' refusal to rename a still-open backup DB on Linux CI."""
    source = _source(tmp_path)
    root, target = _paths(tmp_path)
    real_connect = sqlite3.connect
    original_replace = Path.replace
    opened = []
    closed = []

    class WatchedConnection(sqlite3.Connection):
        def close(self):
            closed.append(self)
            return super().close()

    def observe_connect(database, *args, **kwargs):
        if str(database).endswith(".initializing"):
            kwargs["factory"] = WatchedConnection
            connection = real_connect(database, *args, **kwargs)
            opened.append(connection)
            return connection
        return real_connect(database, *args, **kwargs)

    def strict_windows_replace(self, destination):
        if self.name.endswith(".initializing"):
            assert opened, "expected temporary SQLite connection"
            assert all(c in closed for c in opened), (
                "SQLite context manager does not close DB; Windows rename would fail"
            )
        return original_replace(self, destination)

    monkeypatch.setattr(mod.sqlite3, "connect", observe_connect)
    monkeypatch.setattr(Path, "replace", strict_windows_replace)
    result = _collect(source, target, root, FakeKrx())
    assert result["status"] == "RESEARCH_DAYS_STORED"
    assert len(opened) == len(closed) == 1
    assert not list(root.glob("*.initializing"))


def test_windows_permission_error_has_stage_code_and_no_staging_leak(
    tmp_path, monkeypatch,
):
    source = _source(tmp_path)
    root, target = _paths(tmp_path)
    before = source.read_bytes()
    original_replace = Path.replace

    def reject_publish(self, destination):
        if self.name.endswith(".initializing"):
            raise PermissionError(13, "Windows file locked", str(self))
        return original_replace(self, destination)

    monkeypatch.setattr(Path, "replace", reject_publish)
    with pytest.raises(mod.CollectorError, match="RESEARCH_COPY_PUBLISH_PERMISSION_DENIED"):
        _collect(source, target, root, FakeKrx())
    assert source.read_bytes() == before
    assert not target.exists()
    assert not list(root.glob("*.initializing"))


def test_old_fixed_name_staging_file_is_ignored_without_deletion(tmp_path):
    """A failed earlier Windows run must not require deleting unknown files."""
    source = _source(tmp_path)
    root, target = _paths(tmp_path)
    root.mkdir(parents=True)
    legacy = target.with_name(target.name + ".initializing")
    legacy.write_text("old failed backup; do not reuse", encoding="utf-8")
    result = _collect(source, target, root, FakeKrx())
    assert result["status"] == "RESEARCH_DAYS_STORED"
    assert legacy.read_text(encoding="utf-8") == "old failed backup; do not reuse"
    assert target.is_file()

def test_auto_range_from_original_last_complete_to_explicit_yesterday(tmp_path):
    source = _source(tmp_path)
    root, target = _paths(tmp_path)
    report = mod.plan(
        source, target, market="KOSPI", research_root=root,
        today=date(2026, 10, 19),
    )
    assert report["status"] == "PLAN_ONLY"
    assert report["from_resolution"] == "LAST_COMPLETE_PLUS_ONE"
    assert report["last_complete_market_eod"] == "20261014"
    assert report["from"] == "2026-10-15"
    assert report["through"] == "2026-10-18"
    assert report["pending_dates"] == ["2026-10-15", "2026-10-16"]
    assert report["verified_closed_count"] == 2
    assert report["potential_api_requests"] == 4
    assert report["older_gaps_prior_to_last_complete_scanned"] is False
    assert not target.exists()


def test_auto_collect_after_copy_and_resume_with_new_cutoff(tmp_path):
    source = _source(tmp_path)
    root, target = _paths(tmp_path)
    first = FakeKrx()
    report = asyncio.run(mod.collect(
        source, target, market="KOSPI", research_root=root,
        through="2026-10-16", today=date(2026, 10, 19),
        acknowledge=True, provider=first,
    ))
    assert report["status"] == "RESEARCH_DAYS_STORED"
    assert report["stored_count"] == 2
    assert first.stock_calls == ["20261015", "20261016"]
    # Next auto run starts after the last complete day in the RESEARCH COPY,
    # even if the original source has not changed at all.
    after = mod.plan(
        source, target, market="KOSPI", research_root=root,
        today=date(2026, 10, 19),
    )
    assert after["from"] == "2026-10-17"
    assert after["through"] == "2026-10-18"
    assert after["read_from"] == "RESEARCH_COPY"
    assert after["pending_dates"] == []
    second = FakeKrx()
    noop = asyncio.run(mod.collect(
        source, target, market="KOSPI", research_root=root,
        today=date(2026, 10, 19), acknowledge=True, provider=second,
    ))
    assert noop["status"] == "NO_MISSING_DAYS"
    assert second.stock_calls == second.index_calls == []
    later = mod.plan(
        source, target, market="KOSPI", research_root=root,
        today=date(2026, 10, 20),
    )
    assert later["pending_dates"] == ["2026-10-19"]
    assert later["from"] == "2026-10-17"
    assert later["through"] == "2026-10-19"


def test_auto_noop_when_latest_complete_is_yesterday(tmp_path):
    source = _source(tmp_path)
    root, target = _paths(tmp_path)
    report = mod.plan(
        source, target, market="KOSPI", research_root=root,
        today=date(2026, 10, 15),
    )
    assert report["status"] == "UP_TO_DATE"
    assert report["days"] == []
    assert report["pending_dates"] == []
    assert report["potential_api_requests"] == 0
    provider = FakeKrx()
    noop = asyncio.run(mod.collect(
        source, target, market="KOSPI", research_root=root,
        today=date(2026, 10, 15), acknowledge=True, provider=provider,
    ))
    assert noop["status"] == "NO_MISSING_DAYS"
    assert provider.stock_calls == provider.index_calls == []
    assert not target.exists()


def test_auto_refuses_no_baseline_instead_of_guessing_start_date(tmp_path):
    source = _source(tmp_path)
    root, target = _paths(tmp_path)
    with sqlite3.connect(source) as conn:
        conn.execute("DELETE FROM day_status")
    with pytest.raises(mod.CollectorError, match="AUTO_FROM_REQUIRES_EXISTING_COMPLETE_EOD"):
        mod.plan(
            source, target, market="KOSPI", research_root=root,
            today=date(2026, 10, 19),
        )
    # Explicit date range remains possible when baseline does not exist.
    manual = mod.plan(
        source, target, market="KOSPI", research_root=root,
        start="2026-10-15", through="2026-10-16",
        today=date(2026, 10, 19),
    )
    assert manual["status"] == "PLAN_ONLY"


def test_auto_refuses_unbounded_old_backlog_without_silent_truncation(tmp_path):
    source = _source(tmp_path)
    root, target = _paths(tmp_path)
    with pytest.raises(mod.CollectorError, match="DATE_RANGE_OUTSIDE_SAFE_LIMIT"):
        mod.plan(
            source, target, market="KOSPI", research_root=root,
            today=date(2027, 1, 10),
        )
    assert not target.exists()


def test_explicit_range_reversed_remains_invalid(tmp_path):
    source = _source(tmp_path)
    root, target = _paths(tmp_path)
    with pytest.raises(mod.CollectorError, match="DATE_RANGE_OUTSIDE_SAFE_LIMIT"):
        mod.plan(
            source, target, market="KOSPI", research_root=root,
            start="2026-10-16", through="2026-10-15",
            today=date(2026, 10, 19),
        )
