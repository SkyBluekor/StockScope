"""P0-04 Windows real FastAPI + real Chrome HOLDINGS read-only UAT.

Copies both operational SQLite stores with mode=ro backup (including committed WAL)
into an access-controlled private TEMP directory. Only GET UI endpoints are
exposed by an isolated FastAPI app; writes, providers and brokerage are absent.
The private copy and browser profile are removed even on normal test failure.
No stock IDs, account names, price, quantity, notes or screenshots in reports.
"""
from __future__ import annotations

import argparse
from contextlib import closing
import json
import os
from pathlib import Path
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
from urllib.error import URLError
from urllib.request import urlopen
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
for entry in (ROOT, ROOT / "backend"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from tools.data.p0_02_offline_scanner_replay import (
    prohibit_external_connections, snapshot_sqlite_readonly,
)
from tools.data.p0_03_windows_browser_uat import (
    _cleanup_private_scratch, _port_available, _preferred_private_temp_dir,
    find_system_chrome,
)
from tools.data.p0_04_holdings_readonly_preflight import inspect_holdings_environment

VERSION = "STOCKSCOPE_P0_04_WINDOWS_REAL_READONLY_BROWSER_UAT_V1"
FRONTEND_PORT, BACKEND_PORT = 5283, 5284
OK = "WINDOWS_REAL_HOLDINGS_READONLY_BROWSER_VERIFIED"
SCRATCH_PREFIX = "StockScope_P0_04_RealUI_"


def validate_worker_snapshots(holdings: Path, market: Path) -> bool:
    """Do not let a worker accidentally run against operational files."""
    try:
        hp, mp = holdings.resolve(), market.resolve()
        return (
            hp.is_file() and mp.is_file()
            and hp.name == "holdings_snapshot.sqlite3"
            and mp.name == "market_snapshot.sqlite3"
            and hp.parent == mp.parent
            and hp.parent.name.startswith(SCRATCH_PREFIX)
        )
    except OSError:
        return False


def _one_open_position(holdings: Path) -> tuple[str, str] | None:
    with closing(sqlite3.connect(
        holdings.resolve().as_uri() + "?mode=ro", uri=True
    )) as conn:
        conn.execute("PRAGMA query_only=ON")
        rows = conn.execute(
            "SELECT monitored_stock_id, id FROM holding_position "
            "WHERE status='OPEN' LIMIT 2"
        ).fetchall()
    if len(rows) != 1:
        return None
    return str(rows[0][0]), str(rows[0][1])


def build_worker_app(holdings: Path, market: Path):
    """Restricted FastAPI app wrapping genuine GET Holdings endpoint handlers."""
    from fastapi import FastAPI
    from app.api import holdings as handlers

    if not validate_worker_snapshots(holdings, market):
        raise RuntimeError("HOLD_UNSAFE_WORKER_SNAPSHOT")
    ids = _one_open_position(holdings)
    if ids is None:
        raise RuntimeError("HOLD_REQUIRES_ONE_OPEN_POSITION")
    stock_id, position_id = ids
    os.environ["STOCKSCOPE_HOLDINGS_DB"] = str(holdings.resolve())
    os.environ["STOCKSCOPE_MARKET_STORE_DB"] = str(market.resolve())

    app = FastAPI(openapi_url=None, docs_url=None, redoc_url=None)
    # Exact allowlisted paths only. POST is not registered, even for scratch DB.
    @app.get("/__p004/health")
    def health():
        return {"ready": True, "write_endpoints": 0}

    @app.get("/__p004/seed")
    def seed():
        # IDs remain on loopback in a browser-only session, never in CLI report.
        return {"stock_id": stock_id, "position_id": position_id}

    @app.get("/api/holdings/stocks/{requested_stock}/decision-support")
    def decision(requested_stock: str):
        from fastapi import HTTPException
        if requested_stock != stock_id:
            raise HTTPException(404, "not found")
        return handlers.stock_decision_support(requested_stock)

    @app.get("/api/holdings/stocks/{requested_stock}/management")
    def management(requested_stock: str):
        from fastapi import HTTPException
        if requested_stock != stock_id:
            raise HTTPException(404, "not found")
        return handlers.stock_management(requested_stock)

    @app.get("/api/holdings/positions/{requested_position}/recovery")
    def recovery(requested_position: str):
        from fastapi import HTTPException
        if requested_position != position_id:
            raise HTTPException(404, "not found")
        return handlers.holding_recovery_context(requested_position)

    return app


def _worker(args: argparse.Namespace) -> int:
    if not validate_worker_snapshots(args.holdings_db, args.market_db):
        print("HOLD_UNSAFE_WORKER_SNAPSHOT", file=sys.stderr)
        return 2
    if not _port_available(BACKEND_PORT):
        print("HOLD_LOOPBACK_PORT_IN_USE", file=sys.stderr)
        return 2
    with prohibit_external_connections() as outbound:
        try:
            app = build_worker_app(args.holdings_db, args.market_db)
        except Exception:
            print("HOLD_WORKER_INITIALIZATION_FAILED", file=sys.stderr)
            return 2
        import uvicorn
        print("P004_READONLY_WORKER_STARTING", flush=True)
        uvicorn.run(
            app, host="127.0.0.1", port=BACKEND_PORT,
            log_level="critical", access_log=False, lifespan="off",
        )
        if outbound:
            return 2
    return 0


def _run_scratch(args: argparse.Namespace, scratch: Path, base: dict[str, Any]) -> dict[str, Any]:
    holdings = scratch / "holdings_snapshot.sqlite3"
    market = scratch / "market_snapshot.sqlite3"
    try:
        snapshot_sqlite_readonly(args.holdings_db, holdings)
        snapshot_sqlite_readonly(args.market_db, market)
    except (OSError, sqlite3.DatabaseError):
        return {**base, "status": "HOLD_SNAPSHOT_FAILED"}

    worker = subprocess.Popen(
        [sys.executable, str(Path(__file__).resolve()), "--_worker",
         "--holdings-db", str(holdings), "--market-db", str(market)],
        cwd=str(ROOT), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        ready = False
        for _ in range(100):
            if worker.poll() is not None:
                return {**base, "status": "HOLD_ISOLATED_WORKER_EXITED"}
            try:
                with urlopen(f"http://127.0.0.1:{BACKEND_PORT}/__p004/health",
                             timeout=1.5) as response:
                    ready = json.load(response).get("write_endpoints") == 0
            except (URLError, OSError, ValueError):
                pass
            if ready:
                break
            time.sleep(0.3)
        if not ready:
            return {**base, "status": "HOLD_SERVER_NOT_READY"}

        runner = ROOT / "frontend" / "node_modules" / "@playwright" / "test" / "cli.js"
        env = {
            **os.environ,
            "P004_SYSTEM_CHROME": str(args.chrome),
        }
        try:
            done = subprocess.run(
                ["node", str(runner), "test", "-c",
                 "playwright.p004.loopback.config.mjs"],
                cwd=str(ROOT / "frontend"),
                capture_output=True, text=True, encoding="utf-8",
                errors="replace", timeout=180, env=env, check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return {**base, "status": "HOLD_CHROME_UAT_EXECUTION_FAILED"}

        # Avoid retaining browser stdout; it can contain snapshots of private UI.
        tagged = [
            line.split("P004_READONLY_RESULT ", 1)[1]
            for line in done.stdout.splitlines()
            if "P004_READONLY_RESULT " in line
        ]
        try:
            summary = json.loads(tagged[-1]) if tagged else {}
        except (ValueError, TypeError):
            summary = {}
        valid = (
            done.returncode == 0
            and summary.get("status") == "READONLY_REAL_API_UI_VERIFIED"
            and summary.get("decision_get") is True
            and summary.get("management_get") is True
            and summary.get("recovery_get") is True
            and summary.get("external_requests") == 0
            and summary.get("write_requests") == 0
        )
        return {
            **base,
            "status": OK if valid else "HOLD_BROWSER_READONLY_UAT_INCOMPLETE",
            "browser_exit_code": done.returncode,
            "browser_summary": summary if valid else {},
        }
    finally:
        if worker.poll() is None:
            worker.terminate()
            try:
                worker.wait(timeout=8)
            except subprocess.TimeoutExpired:
                worker.kill()
                worker.wait(timeout=5)


def run(args: argparse.Namespace) -> dict[str, Any]:
    result: dict[str, Any] = {
        "version": VERSION,
        "status": "HOLD_PREFLIGHT",
        "operational_db_read_only": True,
        "operational_db_modified_by_uat": False,
        "browser_api_mode": "REAL_LOCAL_FASTAPI_READONLY_GET",
        "browser_mode": "EXISTING_GOOGLE_CHROME_ONLY",
        "browser_download_required": False,
        "write_endpoints_exposed": 0,
        "real_orders": False,
        "latest_official_eod_verified": False,
    }
    preflight = inspect_holdings_environment(args.holdings_db, args.market_db)
    if preflight["status"] != "READ_ONLY_HOLDINGS_PREFLIGHT_OBSERVED":
        return {**result, "status": "HOLD_PREFLIGHT_NOT_READY",
                "preflight_status": preflight["status"]}
    if preflight["counts"]["open_positions"] != 1:
        return {**result, "status": "HOLD_REQUIRES_ONE_OPEN_POSITION"}
    if not _port_available(FRONTEND_PORT) or not _port_available(BACKEND_PORT):
        return {**result, "status": "HOLD_LOOPBACK_PORT_IN_USE"}
    runner = ROOT / "frontend" / "node_modules" / "@playwright" / "test" / "cli.js"
    if not runner.is_file() or not shutil.which("node") or not shutil.which("npm"):
        return {**result, "status": "HOLD_PLAYWRIGHT_OR_NODE_MISSING"}
    chrome = find_system_chrome()
    if chrome is None:
        return {**result, "status": "HOLD_GOOGLE_CHROME_MISSING"}
    root = _preferred_private_temp_dir()
    if root is None:
        return {**result, "status": "HOLD_PRIVATE_TEMP_UNAVAILABLE"}
    try:
        scratch = Path(tempfile.mkdtemp(prefix=SCRATCH_PREFIX, dir=str(root)))
    except OSError:
        return {**result, "status": "HOLD_TEMP_CREATION_FAILED"}
    args.chrome = chrome
    try:
        report = _run_scratch(args, scratch, result)
    except KeyboardInterrupt:
        report = {**result, "status": "HOLD_USER_INTERRUPTED"}
    except Exception:
        report = {**result, "status": "HOLD_BROWSER_UAT_RUNTIME_EXCEPTION"}
    clean, error, attempts = _cleanup_private_scratch(scratch)
    if not clean:
        return {
            **report, "status": "HOLD_TEMP_CLEANUP_FAILED",
            "prior_status": report.get("status"),
            "temp_cleanup": "MANUAL_REVIEW_REQUIRED",
            "cleanup_error_class": error, "scratch_path": str(scratch),
        }
    return {**report, "temp_cleanup": "REMOVED", "cleanup_attempts": attempts}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--holdings-db", type=Path, required=True)
    parser.add_argument("--market-db", type=Path, required=True)
    parser.add_argument("--_worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    result = _worker(args) if args._worker else run(args)
    if not args._worker:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 0 if result["status"] == OK else 2
    return result


if __name__ == "__main__":
    raise SystemExit(main())
