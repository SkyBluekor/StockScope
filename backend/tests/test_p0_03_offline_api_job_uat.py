"""P0-03 Windows UAT boundary: no original DB mutation and no invented job."""
from __future__ import annotations

from datetime import date
from pathlib import Path
import runpy
import sqlite3

SCRIPT = Path(__file__).resolve().parents[2] / "tools" / "data" / "p0_03_offline_api_job_uat.py"
module = runpy.run_path(str(SCRIPT), run_name="p0_03_offline_uat_import")
run = module["offline_job_uat"]
select_previous = module["_previous_common_data_date"]


def test_p0_03_worker_rejects_operational_db_as_worker_input(tmp_path: Path) -> None:
    db = tmp_path / "operational.db"
    db.write_bytes(b"DO NOT TOUCH")
    before = db.read_bytes()
    result = run(
        market_db=db, as_of=date(2026, 10, 21),
        market_scope="ALL", operational_repo=tmp_path,
        _snapshot_worker=True,
    )
    assert result["status"] == "HOLD_UNSAFE_WORKER_SOURCE"
    assert result["original_db_modified"] is False
    assert db.read_bytes() == before


def test_p0_03_missing_operational_db_never_created(tmp_path: Path) -> None:
    db = tmp_path / "missing.db"
    result = run(
        market_db=db, as_of=date(2026, 10, 21),
        market_scope="ALL", operational_repo=tmp_path,
    )
    assert result["status"] == "HOLD_SNAPSHOT_FAILED"
    assert not db.exists()


def test_p0_03_same_day_as_today_not_falsely_accepted(tmp_path: Path) -> None:
    import datetime
    day = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9))).date()
    result = run(
        market_db=tmp_path / "missing.db", as_of=day,
        operational_repo=tmp_path,
    )
    assert result["status"] == "HOLD_AS_OF_NOT_HISTORICAL"


def test_previous_common_day_is_not_inferred_from_non_overlapping_markers() -> None:
    from types import SimpleNamespace
    class Store:
        def latest_complete_date(self, market, kind, end_dd):
            return "20261020"
        def day_complete(self, market, key, kind):
            return not (market == "KOSDAQ" and kind == "index")
    assert select_previous(Store(), date(2026, 10, 21), ["KOSPI", "KOSDAQ"]) is None
