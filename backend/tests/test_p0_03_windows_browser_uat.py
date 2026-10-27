"""P0-03 safe Windows localhost browser and actual API runner preparation tests."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import runpy

SCRIPT = Path(__file__).resolve().parents[2] / "tools" / "data" / "p0_03_windows_browser_uat.py"
module = runpy.run_path(str(SCRIPT), run_name="p003_loopback_safety_tests")
validate = module["validate_worker_snapshot"]
driver = module["_driver"]


def args(path: Path, repo: Path, value=date(2026, 10, 21)):
    from argparse import Namespace
    return Namespace(market_db=path, operational_repo=repo,
                     as_of=value, market_scope="ALL", _worker=False)


def test_worker_rejects_operational_db_file(tmp_path: Path) -> None:
    path = tmp_path / "operational.db"
    path.write_bytes(b"DO NOT TOUCH")
    assert not validate(path)
    assert path.read_bytes() == b"DO NOT TOUCH"


def test_worker_accepts_only_named_temporary_market_snapshot(tmp_path: Path) -> None:
    good = tmp_path / "StockScope_P0_03_Browser_unique"
    good.mkdir()
    snap = good / "market_snapshot.sqlite3"
    snap.write_bytes(b"fixture marker")
    assert validate(snap)
    assert not validate(tmp_path / "market_snapshot.sqlite3")
    assert not validate(good / "market_history.db")


def test_missing_original_is_not_created(tmp_path: Path) -> None:
    missing = tmp_path / "missing.db"
    out = driver(args(missing, tmp_path))
    assert out["status"] in {"HOLD_OPERATIONAL_DB_MISSING", "HOLD_PLAYWRIGHT_NOT_INSTALLED"}
    assert out["original_db_modified"] is False
    assert not missing.exists()


def test_current_day_blocked_before_file_access(tmp_path: Path) -> None:
    current = datetime.now(timezone(timedelta(hours=9))).date()
    out = driver(args(tmp_path / "market.db", tmp_path, current))
    assert out["status"] == "HOLD_AS_OF_NOT_HISTORICAL"
    assert not (tmp_path / "market.db").exists()


def test_isolated_app_never_routes_brokerage_or_full_lifespan() -> None:
    src = SCRIPT.read_text(encoding="utf-8")
    assert 'app = FastAPI(title="StockScope P0-03 Isolated Offline Scanner")' in src
    assert '@app.post("/api/backtest/scanner/jobs", status_code=202)' in src
    assert '@app.get("/api/backtest/jobs/{job_id}")' in src
    assert 'StockScannerService.CACHE_ROOT = scratch / "scanner_cache"' in src
    assert "app.include_router(api.router" not in src
    assert 'host="127.0.0.1"' in src
    assert "prohibit_external_connections()" in src
