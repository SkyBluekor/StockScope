"""P0-03 Windows loopback browser ↔ real FastAPI Scanner ↔ ephemeral capture UAT.

Offline historical only. The live operational Market DB is never opened writable.
The worker exposes ONLY the three Scanner endpoints required by the UI and
the UAT seed/health endpoints. No full app lifespan, KRX or brokerage.
"""
from __future__ import annotations

import argparse
import asyncio
from contextlib import closing, redirect_stdout
from datetime import date, datetime, timedelta, timezone
import io
import json
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys
import time
from tempfile import TemporaryDirectory
from types import MethodType, SimpleNamespace
from typing import Any
from urllib.error import URLError
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[2]
for item in (ROOT, ROOT / "backend"):
    if str(item) not in sys.path:
        sys.path.insert(0, str(item))

from app.api.backtest import ScannerRequest

from tools.data.p0_02_offline_scanner_replay import (
    OfflineKrx, prohibit_external_connections, snapshot_sqlite_readonly,
)
from tools.data.p0_03_offline_api_job_uat import (
    _previous_common_data_date, MARKETS, _sha,
)

KST = timezone(timedelta(hours=9))
VERSION = "P0_03_WINDOWS_LOOPBACK_REAL_API_BROWSER_UAT_V1"
BACKEND_PORT = 5280
FRONTEND_PORT = 5279
OK_STATUS = "OFFLINE_WINDOWS_BROWSER_REAL_FASTAPI_VERIFIED"
MAX_RUNTIME_SECONDS = 330


def validate_worker_snapshot(market_db: Path) -> bool:
    p = market_db.resolve()
    return (p.name == "market_snapshot.sqlite3"
            and p.parent.name.startswith("StockScope_P0_03_Browser_")
            and p.is_file())


def _port_available(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False


def _safe_worker_app(*, snapshot: Path, scratch: Path, operational_repo: Path,
                     as_of: date, scope: str):
    from fastapi import FastAPI, HTTPException
    from app.api import backtest as api
    from app.backtest.market_store import HistoricalMarketStore
    from app.backtest.scanner import StockScannerService
    from app.backtest import scanner as scanner_module
    from app.backtest.jobs import BacktestJobManager
    from app.prospective.service import ProspectiveService
    from app.strategy.production_selection_policy import ProductionStrategySelectionRegistry
    from tools.data.migrate_prospective_vnp2s2 import migrate_prospective_store

    markets = list(MARKETS) if scope == "ALL" else [scope]
    store = HistoricalMarketStore(snapshot)
    previous = _previous_common_data_date(store, as_of, markets)
    if previous is None:
        raise RuntimeError("HOLD_NO_PREVIOUS_COMMON_EOD")
    registry = ProductionStrategySelectionRegistry(
        runtime_dir=operational_repo / "backend" / "runtime" / "strategy_selection"
    )
    pin = registry.pin_active_selection_policy()
    provider = OfflineKrx(as_of)
    service = StockScannerService(provider, market_store=store, selection_registry=registry)
    for target in (previous, as_of):
        for market in markets:
            plan = service._history_plan(
                market=market,
                start=target - timedelta(days=service.FAST_HISTORY_CALENDAR_DAYS),
                end=target,
            )
            if plan["work"]:
                raise RuntimeError("HOLD_OFFLINE_HISTORY_MISSING")

    simulation = scratch / "simulation_browser_uat.db"
    with closing(sqlite3.connect(simulation)) as conn:
        conn.execute("CREATE TABLE simulation_placeholder(id INTEGER PRIMARY KEY)")
        conn.commit()
    migrate_prospective_store(simulation)
    prospect = ProspectiveService(simulation, snapshot)

    # Every real Scanner creation path uses ONLY the offline KRX stub and
    # the single read-only snapshot; no default MarketStore or writes elsewhere.
    StockScannerService.CACHE_ROOT = scratch / "scanner_cache"
    scanner_module.write_scanner_reproducibility_audit = lambda **_: {
        "written": False, "skipped": "ISOLATED_BROWSER_UAT"
    }
    api.KrxProvider = lambda _key: provider
    api.StockScannerService = lambda _: service
    api.ProductionStrategySelectionRegistry = lambda: registry
    api.get_settings = lambda: SimpleNamespace(krx_api_key=None)
    api._prospective_service = lambda: prospect
    api._prospective_reference_capture_service = lambda: SimpleNamespace(
        try_capture=lambda cid: {
            "status": "SKIPPED_REFERENCE_CAPTURE_OFFLINE", "capture_id": cid
        }
    )
    api.backtest_jobs = BacktestJobManager()

    async def latest_stored(self: Any, *, market_scope: str,
                            known_data_date: str | None = None,
                            progress: Any = None) -> dict[str, Any]:
        return {
            "status": "READY",
            "resolved_as_of_date": as_of.isoformat(),
            "date_changed": known_data_date != as_of.isoformat(),
            "message": "Offline fixed historical EOD; not official current KRX.",
            "diagnostics": {"network_requests": 0},
        }
    service.prepare_latest_confirmed_data = MethodType(latest_stored, service)
    # Prepare a *real*, old-dated Scanner result. This baseline becomes
    # browser session input; the browser does not synthesize any stock data.
    with redirect_stdout(io.StringIO()):
        prior = asyncio.run(service.run(
            market_scope=scope, as_of_date=previous.isoformat(),
            candidate_limit=5, force_refresh=True, allow_large_sync=False,
            selection_policy_pin=pin,
        ))
    candidate_rows = [*(prior.get("candidates") or []),
                      *(prior.get("more_candidates") or [])]
    if not candidate_rows:
        raise RuntimeError("HOLD_NO_PREVIOUS_SCANNER_CANDIDATE")
    selected = candidate_rows[0]
    if str(selected.get("data_date")) != previous.isoformat():
        raise RuntimeError("HOLD_PRIOR_RESULT_DATE_MISMATCH")

    app = FastAPI(title="StockScope P0-03 Isolated Offline Scanner")
    # Unlike app.main, NOT the full router/lifespan. There are no endpoints
    # for brokerage, data fetch, KRX, holdings mutation, or strategy activation.
    @app.post("/api/backtest/scanner/data-plan")
    async def safe_preflight(body: dict) -> dict:
        if body.get("market_scope") != scope or body.get("as_of_date") is not None:
            raise HTTPException(400, "P003_PLAN_SCOPE_DENIED")
        return {
            "status": "AUTO_ALLOWED", "estimated_missing_krx_slots": 0,
            "provider_calls": 0, "db_writes": 0,
            "version": "P0_03_OFFLINE_MARKET_SNAPSHOT_PREFLIGHT",
        }

    @app.post("/api/backtest/scanner/jobs", status_code=202)
    async def create_job(payload: ScannerRequest) -> dict:
        if (payload.market_scope != scope or payload.allow_large_sync
                or payload.recheck_candidate is None
                or payload.recheck_candidate.market != selected["market"]
                or payload.recheck_candidate.code != str(selected["code"])
                or payload.recheck_candidate.source_data_date != previous):
            raise HTTPException(400, detail="P003_UNAPPROVED_REQUEST")
        return await api.create_scanner_job(payload)

    @app.get("/api/backtest/jobs/{job_id}")
    async def get_job(job_id: str) -> dict:
        return await api.get_backtest_job(job_id)

    @app.get("/__p003/health")
    async def health() -> dict:
        return {"ready": True, "version": VERSION}

    @app.get("/__p003/seed")
    async def seed() -> dict:
        return {
            "prior": prior, "selected_market": selected["market"],
            "selected_code": str(selected["code"]),
            "previous_date": previous.isoformat(),
            "new_date": as_of.isoformat(), "market_scope": scope,
            "offline_historical": True,
        }
    return app, provider


def _server_worker(args: argparse.Namespace) -> int:
    if not validate_worker_snapshot(args.market_db):
        print("HOLD_UNSAFE_WORKER_SOURCE", file=sys.stderr, flush=True)
        return 2
    if args.as_of >= datetime.now(KST).date():
        print("HOLD_AS_OF_NOT_HISTORICAL", file=sys.stderr, flush=True)
        return 2
    if not _port_available(BACKEND_PORT):
        print("HOLD_BACKEND_PORT_IN_USE", file=sys.stderr, flush=True)
        return 2
    # Outbound connections are denied, even if a process were to try to
    # bypass OfflineKrx; loopback browser-to-server remains available.
    with prohibit_external_connections() as attempts:
        try:
            app, provider = _safe_worker_app(
                snapshot=args.market_db, scratch=args.market_db.parent,
                operational_repo=args.operational_repo, as_of=args.as_of,
                scope=args.market_scope,
            )
        except Exception as exc:
            print("HOLD_WORKER_INITIALIZATION " + type(exc).__name__ + " "
                  + str(exc)[:180], file=sys.stderr, flush=True)
            return 2
        import uvicorn
        print("P003_SERVER_STARTING", flush=True)
        uvicorn.run(app, host="127.0.0.1", port=BACKEND_PORT, log_level="warning",
                    access_log=False, lifespan="off")
        if attempts or provider.attempts:
            print("HOLD_EXTERNAL_ATTEMPTS", file=sys.stderr)
            return 2
    return 0


def _driver(args: argparse.Namespace) -> dict[str, Any]:
    result: dict[str, Any] = {
        "version": VERSION, "code_sha": _sha(),
        "as_of": args.as_of.isoformat(), "market_scope": args.market_scope,
        "operational_db_read_only": True, "original_db_modified": False,
        "external_network_blocked": True, "latest_krx_eod_confirmed": False,
        "real_brokerage_orders": False, "browser_api_mode": "REAL_LOCAL_FASTAPI",
    }
    if args.as_of >= datetime.now(KST).date():
        return {**result, "status": "HOLD_AS_OF_NOT_HISTORICAL"}
    if args.market_scope not in ("ALL", *MARKETS):
        return {**result, "status": "HOLD_INVALID_SCOPE"}
    if not all(_port_available(port) for port in (FRONTEND_PORT, BACKEND_PORT)):
        return {**result, "status": "HOLD_LOOPBACK_PORT_IN_USE"}
    frontend = ROOT / "frontend"
    node_runner = frontend / "node_modules" / "@playwright" / "test" / "cli.js"
    if not node_runner.is_file():
        return {**result, "status": "HOLD_PLAYWRIGHT_NOT_INSTALLED"}
    if not args.market_db.is_file():
        return {**result, "status": "HOLD_OPERATIONAL_DB_MISSING"}
    with TemporaryDirectory(prefix="StockScope_P0_03_Browser_") as tmp:
        scratch = Path(tmp)
        snapshot = scratch / "market_snapshot.sqlite3"
        try:
            snapshot_sqlite_readonly(args.market_db, snapshot)
        except (OSError, sqlite3.DatabaseError) as exc:
            return {**result, "status": "HOLD_SNAPSHOT_FAILED",
                    "error_class": type(exc).__name__}
        worker = subprocess.Popen([
            sys.executable, str(Path(__file__).resolve()), "--_worker",
            "--market-db", str(snapshot), "--operational-repo",
            str(args.operational_repo), "--as-of", args.as_of.isoformat(),
            "--market-scope", args.market_scope,
        ], cwd=str(ROOT), stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
           text=True, encoding="utf-8", errors="replace")
        try:
            deadline = time.monotonic() + 110
            ready = False
            while time.monotonic() < deadline:
                if worker.poll() is not None:
                    return {**result, "status": "HOLD_ISOLATED_SERVER_FAILED",
                            "worker_returncode": worker.returncode,
                            "worker_stderr": (worker.stderr.read() or "")[-800:]}
                try:
                    with urlopen("http://127.0.0.1:5280/__p003/health",
                                 timeout=2) as response:
                        ready = json.loads(response.read()).get("ready") is True
                except (OSError, URLError, ValueError):
                    pass
                if ready:
                    break
                time.sleep(0.5)
            if not ready:
                return {**result, "status": "HOLD_SERVER_NOT_READY"}
            cmd = ["node", str(node_runner), "test",
                   "-c", "playwright.p003.loopback.config.mjs"]
            try:
                run = subprocess.run(cmd, cwd=str(frontend), text=True,
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    encoding="utf-8", errors="replace", timeout=MAX_RUNTIME_SECONDS,
                    env={**os.environ, "P003_LOOPBACK_UAT": "1"},
                )
            except (OSError, subprocess.TimeoutExpired) as exc:
                return {**result, "status": "HOLD_BROWSER_EXECUTION_FAILED",
                        "error_class": type(exc).__name__}
            # Browser emits exactly one minimal summary line, no market rows.
            lines = [line.split("P003_LOOPBACK_RESULT ", 1)[1] for line in
                     run.stdout.splitlines() if "P003_LOOPBACK_RESULT " in line]
            try:
                report = json.loads(lines[-1]) if lines else {}
            except json.JSONDecodeError:
                report = {}
            valid = (
                run.returncode == 0
                and report.get("status") == "BROWSER_REAL_API_VERIFIED"
                and report.get("previous_date") < report.get("new_date")
                and report.get("job_status") == "completed"
                and report.get("capture_status") in ("COMPLETE", "DUPLICATE")
                and report.get("capture_id")
                and report.get("job_id")
                and report.get("api_post_status") == 202
                and report.get("api_get_status") == 200
                and report.get("external_requests") == 0
                and report.get("recheck_status") in {
                    "MATCHED_RETURNED_CANDIDATE",
                    "TARGETED_EVALUATED_OUTSIDE_RANKING",
                    "TARGET_OUTSIDE_SCANNER_FILTER",
                }
                and (
                    report.get("recheck_status") != "TARGET_OUTSIDE_SCANNER_FILTER"
                    or bool(report.get("filter_reason"))
                )
            )
            return {
                **result,
                "status": OK_STATUS if valid else "HOLD_BROWSER_REAL_API_INCOMPLETE",
                "browser_exit_code": run.returncode,
                "browser_summary": report,
                "browser_log_tail": None if valid else run.stdout[-1800:],
                "capture_db_writes": "TEMP_ONLY",
                "official_latest_eod_verified": False,
            }
        finally:
            if worker.poll() is None:
                worker.terminate()
                try:
                    worker.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    worker.kill()
                    worker.wait(timeout=5)
            if worker.stderr:
                worker.stderr.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--market-db", type=Path, required=True)
    parser.add_argument("--operational-repo", type=Path, required=True)
    parser.add_argument("--as-of", type=date.fromisoformat, required=True)
    parser.add_argument("--market-scope", choices=("ALL", *MARKETS), default="ALL")
    parser.add_argument("--_worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args._worker:
        return _server_worker(args)
    out = _driver(args)
    print(json.dumps(out, indent=2, ensure_ascii=False, sort_keys=True))
    return 0 if out["status"] == OK_STATUS else 2


if __name__ == "__main__":
    raise SystemExit(main())
