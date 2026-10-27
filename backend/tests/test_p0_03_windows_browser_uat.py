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
    assert out["status"] == "HOLD_OPERATIONAL_DB_MISSING"
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



def test_existing_chrome_override_is_accepted_without_download(tmp_path: Path) -> None:
    chrome = tmp_path / "chrome.exe"
    chrome.write_bytes(b"mock existing executable only")
    detected = module["find_system_chrome"](override=str(chrome))
    assert detected == chrome
    assert module["find_system_chrome"](override=str(tmp_path / "not-found.exe")) is None


def test_loopback_playwright_config_uses_google_chrome_not_managed_chromium() -> None:
    config = (SCRIPT.parents[2] / "frontend" / "playwright.p003.loopback.config.mjs"
              ).read_text(encoding="utf-8")
    assert 'channel: "chrome"' in config
    assert 'P003_CHROME_EXECUTABLE' in config
    assert "npx playwright install chromium" not in config


def test_runner_never_automatically_installs_browser() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert "find_system_chrome()" in source
    assert 'HOLD_INSTALLED_GOOGLE_CHROME_NOT_FOUND' in source
    assert 'browser_download_required' in source
    assert "playwright install chromium" not in source
    assert "subprocess.run(cmd" in source



def test_windows_redirected_estsoft_temp_is_ignored(monkeypatch, tmp_path: Path) -> None:
    import os
    private = tmp_path / "LocalAppData"
    preferred = private / "Temp"
    preferred.mkdir(parents=True)
    monkeypatch.setenv("LOCALAPPDATA", str(private))
    monkeypatch.setenv("TEMP", str(tmp_path / "ESTsoft" / "CreatorTemp"))
    monkeypatch.setenv("TMP", str(tmp_path / "ESTsoft" / "CreatorTemp"))
    assert module["_preferred_private_temp_dir"](platform="nt") == preferred


def test_cleanup_retries_transient_windows_file_lock(monkeypatch, tmp_path: Path) -> None:
    import errno
    import shutil
    import time
    scratch = tmp_path / "StockScope_P0_03_Browser_retry"
    scratch.mkdir()
    (scratch / "market_snapshot.sqlite3").write_bytes(b"fixture")
    real_remove = shutil.rmtree
    calls = []

    def first_two_locked(path):
        calls.append(path)
        if len(calls) <= 2:
            raise PermissionError(errno.EACCES, "WinError 32 simulated", str(path))
        return real_remove(path)

    monkeypatch.setattr(shutil, "rmtree", first_two_locked)
    monkeypatch.setattr(time, "sleep", lambda _: None)
    cleaned, error, retries = module["_cleanup_private_scratch"](scratch)
    assert cleaned is True
    assert error is None
    assert retries == 3
    assert not scratch.exists()


def test_cleanup_failure_returns_explicit_hold_without_masking_original(
    monkeypatch, tmp_path: Path
) -> None:
    import errno
    import shutil
    import time

    globals_ref = module["_with_private_scratch"].__globals__
    with monkeypatch.context() as patch:
        patch.setitem(globals_ref, "_preferred_private_temp_dir", lambda: tmp_path)
        patch.setattr(shutil, "rmtree",
                      lambda path: (_ for _ in ()).throw(
                          PermissionError(errno.EACCES, "WinError 32 simulated", str(path))
                      ))
        patch.setattr(time, "sleep", lambda _: None)
        outcome = module["_with_private_scratch"](
            {"version": "P003_TEST"},
            lambda scratch: {"status": "OFFLINE_WINDOWS_BROWSER_REAL_FASTAPI_VERIFIED",
                             "scratch_was_private": scratch.parent == tmp_path},
        )

    assert outcome["status"] == "HOLD_TEMP_CLEANUP_FAILED"
    assert outcome["previous_status"] == "OFFLINE_WINDOWS_BROWSER_REAL_FASTAPI_VERIFIED"
    assert outcome["scratch_was_private"] is True
    assert outcome["temp_cleanup_attempts"] == 10
    leftover = Path(outcome["temp_folder_for_manual_review"])
    assert leftover.parent == tmp_path
    assert leftover.name.startswith("StockScope_P0_03_Browser_")
    assert leftover.is_dir()
    shutil.rmtree(leftover)


def test_cleanup_success_preserves_result_and_reports_removed(
    monkeypatch, tmp_path: Path
) -> None:
    globals_ref = module["_with_private_scratch"].__globals__
    with monkeypatch.context() as patch:
        patch.setitem(globals_ref, "_preferred_private_temp_dir", lambda: tmp_path)
        report = module["_with_private_scratch"](
            {"version": "P003_TEST"},
            lambda scratch: {"status": "OFFLINE_WINDOWS_BROWSER_REAL_FASTAPI_VERIFIED",
                             "private_dir": str(scratch)},
        )
    assert report["status"] == "OFFLINE_WINDOWS_BROWSER_REAL_FASTAPI_VERIFIED"
    assert report["temp_cleanup"] == "REMOVED"
    assert not Path(report["private_dir"]).exists()
