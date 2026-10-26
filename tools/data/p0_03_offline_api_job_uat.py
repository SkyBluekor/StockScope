"""P0-03 Windows UAT: historical two-date Scanner API job on read-only DB snapshot.

Runs the real frozen Scanner core and the real API job/prospective catalog.
It NEVER fetches KRX, TypeSafe, orders, or mutates operational runtime data.
The replay is *historical*; it cannot certify today's latest KRX EOD.
"""
from __future__ import annotations

import argparse
import asyncio
from contextlib import closing, nullcontext
from datetime import date, datetime, timedelta, timezone
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
from tempfile import TemporaryDirectory
from types import MethodType, SimpleNamespace
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
for path in (ROOT, ROOT / "backend"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from tools.data.p0_02_offline_scanner_replay import (
    OfflineKrx,
    prohibit_external_connections,
    snapshot_sqlite_readonly,
)

VERSION = "P0_03_REAL_SCANNER_API_JOB_OFFLINE_UAT_V1"
KST = timezone(timedelta(hours=9))
MARKETS = ("KOSPI", "KOSDAQ")


def _sha() -> str | None:
    try:
        run = subprocess.run(
            ["git", "-C", str(ROOT), "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=5,
        )
        value = run.stdout.strip()
        return value if run.returncode == 0 and len(value) == 40 else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def _previous_common_data_date(store: Any, as_of: date, markets: list[str]) -> date | None:
    yesterday = (as_of - timedelta(days=1)).strftime("%Y%m%d")
    options = [
        store.latest_complete_date(market, "stock", end_dd=yesterday)
        for market in markets
    ] + [
        store.latest_complete_date(market, "index", end_dd=yesterday)
        for market in markets
    ]
    if any(not value for value in options):
        return None
    # Find the most recent common stock/index date even when one market skipped a day.
    day = date.fromisoformat(min(str(v) for v in options)[:4] + "-" +
                            min(str(v) for v in options)[4:6] + "-" +
                            min(str(v) for v in options)[6:8])
    limit = as_of - timedelta(days=25)
    while day >= limit:
        key = day.strftime("%Y%m%d")
        if all(store.day_complete(market, key, kind) for market in markets for kind in ("stock", "index")):
            return day
        day -= timedelta(days=1)
    return None


async def _run_api_worker(
    *,
    snapshot: Path,
    as_of: date,
    operational_repo: Path,
    scope: str,
    scratch: Path,
) -> dict[str, Any]:
    from app.backtest.market_store import HistoricalMarketStore
    from app.backtest.scanner import StockScannerService
    from app.backtest import scanner as scanner_module
    from app.api import backtest as api
    from app.backtest.jobs import BacktestJobManager
    from app.prospective.service import ProspectiveService
    from app.strategy.production_selection_policy import ProductionStrategySelectionRegistry
    from tools.data.migrate_prospective_vnp2s2 import migrate_prospective_store

    markets = list(MARKETS) if scope == "ALL" else [scope]
    store = HistoricalMarketStore(snapshot)
    previous = _previous_common_data_date(store, as_of, markets)
    if previous is None:
        return {"status": "HOLD_NO_PREVIOUS_COMMON_EOD"}

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
                return {
                    "status": "HOLD_OFFLINE_HISTORY_MISSING",
                    "missing_market": market,
                    "missing_as_of": target.isoformat(),
                    "missing_slots": len(plan["work"]),
                }

    # Only scratch runtime paths may ever be writable.
    simulation = scratch / "simulation_uat.db"
    with closing(sqlite3.connect(simulation)) as conn:
        conn.execute("CREATE TABLE simulation_placeholder(id INTEGER PRIMARY KEY)")
        conn.commit()
    migrate_prospective_store(simulation)
    prospect = ProspectiveService(simulation, snapshot)

    original_cache = StockScannerService.CACHE_ROOT
    original_audit = scanner_module.write_scanner_reproducibility_audit
    originals = {
        "KrxProvider": api.KrxProvider,
        "StockScannerService": api.StockScannerService,
        "ProductionStrategySelectionRegistry": api.ProductionStrategySelectionRegistry,
        "_prospective_service": api._prospective_service,
        "_prospective_reference_capture_service": api._prospective_reference_capture_service,
        "get_settings": api.get_settings,
        "backtest_jobs": api.backtest_jobs,
    }
    blocked: list[str] = []
    try:
        StockScannerService.CACHE_ROOT = scratch / "scanner_cache"
        scanner_module.write_scanner_reproducibility_audit = (
            lambda **_: {"written": False, "skipped": "OFFLINE_UAT_EPHEMERAL"}
        )
        api.KrxProvider = lambda _: provider
        api.StockScannerService = lambda _: service
        api.ProductionStrategySelectionRegistry = lambda: registry
        api._prospective_service = lambda: prospect
        api.get_settings = lambda: SimpleNamespace(krx_api_key=None)
        api.backtest_jobs = BacktestJobManager()
        # Reference capture has its own separate migration and macro inputs.
        # Never claim its completion in this market-only replay.
        api._prospective_reference_capture_service = lambda: SimpleNamespace(
            try_capture=lambda cid: {
                "status": "SKIPPED_REFERENCE_CAPTURE_IN_OFFLINE_UAT",
                "capture_id": cid,
            }
        )

        async def latest_stored_eod(self: Any, *, market_scope: str,
                                    known_data_date: str | None = None,
                                    progress: Any = None) -> dict[str, Any]:
            return {
                "status": "READY",
                "resolved_as_of_date": as_of.isoformat(),
                "date_changed": known_data_date != as_of.isoformat(),
                "message": "Offline historical EOD pin; not an official live KRX confirmation.",
                "diagnostics": {"network_requests": 0},
            }

        service.prepare_latest_confirmed_data = MethodType(latest_stored_eod, service)
        with prohibit_external_connections() as blocked:
            prior = await service.run(
                market_scope=scope, as_of_date=previous.isoformat(),
                candidate_limit=5, force_refresh=True, allow_large_sync=False,
                selection_policy_pin=pin,
            )
            previously_returned = [
                *(prior.get("candidates") or []), *(prior.get("more_candidates") or [])
            ]
            if not previously_returned:
                return {
                    "status": "HOLD_NO_PREVIOUS_SCANNER_CANDIDATE",
                    "previous_date": previous.isoformat(),
                    "new_date": as_of.isoformat(),
                    "previous_universe_count": (prior.get("summary") or {}).get("universe_total"),
                }

            previous_candidate = previously_returned[0]
            old_policy = prior.get("strategy_selection_policy") or {}
            old_fp = prior.get("input_fingerprint") or {}
            selected = api.ScannerRecheckCandidate(
                market=previous_candidate["market"], code=str(previous_candidate["code"]),
                name=str(previous_candidate.get("name") or ""),
                source_data_date=date.fromisoformat(previous_candidate["data_date"]),
                source_action=str(previous_candidate.get("action") or ""),
                source_strategy=str(previous_candidate.get("strategy") or ""),
                source_input_fingerprint_id=old_fp.get("id"),
                source_policy_id=old_policy.get("policy_id"),
                source_policy_hash=old_policy.get("policy_hash"),
            )
            payload = api.ScannerRequest(
                market_scope=scope,
                known_data_date=previous.isoformat(),
                as_of_date=None, force_refresh=True,
                candidate_limit=5, allow_large_sync=False,
                recheck_candidate=selected,
            )
            created = await api.create_scanner_job(payload)
            job_id = created["job_id"]
            job = api.backtest_jobs.get(job_id)
            if job is None or job.task is None:
                return {"status": "HOLD_JOB_NOT_ATTACHED"}
            await job.task
            public = await api.get_backtest_job(job_id)
            if public["status"] != "completed" or not public["result"]:
                return {
                    "status": "HOLD_SCANNER_JOB_FAILED",
                    "job_id": job_id, "job_status": public["status"],
                    "job_error": public.get("error"),
                }
            response = public["result"]
            recheck = response.get("candidate_recheck") or {}
            reported_capture = response.get("prospective_capture") or {}
            captured = prospect.catalog.get_capture_by_job(job_id)
            capture_id = reported_capture.get("capture_id")
            captured_id = captured.get("id") if captured else None
            diagnostics = response.get("diagnostics") or {}
            market_dates = response.get("data_dates") or {}
            passed = (
                recheck.get("source_job_id") == job_id
                and bool(recheck.get("new_eod_advanced"))
                and recheck.get("source_data_date") == previous.isoformat()
                and recheck.get("new_data_date") == as_of.isoformat()
                and recheck.get("source_input_fingerprint_id") == old_fp.get("id")
                and recheck.get("new_scanner_input_fingerprint_id") == (response.get("input_fingerprint") or {}).get("id")
                and recheck.get("reference_verified_against_capture") is False
                and recheck.get("targeted_result_stored_in_capture") is False
                and recheck.get("baseline_capture_scope") == "SCANNER_RETURNED_CANDIDATES_ONLY"
                and all(market_dates.get(m) == as_of.isoformat() for m in markets)
                and capture_id is not None
                and capture_id == captured_id
                and captured.get("source_job_id") == job_id
                and captured.get("status") in {"COMPLETE", "DUPLICATE"}
                and recheck.get("baseline_scanner_capture_id")
                   == (reported_capture.get("canonical_capture_id") or capture_id)
                and int(diagnostics.get("network_requests") or 0) == 0
                and provider.attempts == 0
                and not blocked
            )
            return {
                "status": "OFFLINE_API_JOB_CAPTURE_VERIFIED" if passed else "HOLD_API_JOB_CAPTURE_MISMATCH",
                "previous_date": previous.isoformat(),
                "new_date": as_of.isoformat(),
                "selected_market": selected.market,
                "selected_code": selected.code,
                "selected_from_real_previous_scanner_result": True,
                "job_id": job_id,
                "job_status": public["status"],
                "recheck_status": recheck.get("status"),
                "new_eod_advanced": recheck.get("new_eod_advanced"),
                "source_input_fingerprint_id": old_fp.get("id"),
                "new_input_fingerprint_id": recheck.get("new_scanner_input_fingerprint_id"),
                "policy_changed": recheck.get("policy_changed"),
                "selection_policy_fallback": old_policy.get("fallback_used"),
                "baseline_scanner_capture_status": reported_capture.get("status"),
                "baseline_scanner_capture_id": recheck.get("baseline_scanner_capture_id"),
                "persisted_capture_status": captured.get("status") if captured else None,
                "persisted_sample_count": captured.get("returned_candidate_count") if captured else None,
                "targeted_result_stored_in_capture": recheck.get("targeted_result_stored_in_capture"),
                "network_attempts": provider.attempts + len(blocked),
                "typesafe_calls": 0,
                "operation_db_writes": 0,
                "capture_db_writes": "TEMP_ONLY",
                "online_krx_eod_confirmed": False,
                "browser_ui_tested": False,
            }
    finally:
        StockScannerService.CACHE_ROOT = original_cache
        scanner_module.write_scanner_reproducibility_audit = original_audit
        for key, obj in originals.items():
            setattr(api, key, obj)


def offline_job_uat(
    *, market_db: Path, as_of: date, market_scope: str = "ALL",
    operational_repo: Path, _snapshot_worker: bool = False,
) -> dict[str, Any]:
    base = {
        "version": VERSION,
        "code_sha": _sha(),
        "market_scope": market_scope,
        "as_of": as_of.isoformat(),
        "operational_db_read_only": True,
        "original_db_modified": False,
        "external_connections_blocked": True,
        "live_krx_calls": 0,
        "live_typesafe_calls": 0,
        "mode": "HISTORICAL_OFFLINE_REPLAY",
    }
    if market_scope not in ("ALL", *MARKETS):
        return {**base, "status": "HOLD_INVALID_SCOPE"}
    if as_of >= datetime.now(KST).date():
        return {**base, "status": "HOLD_AS_OF_NOT_HISTORICAL"}
    if _snapshot_worker:
        snap = market_db.resolve()
        if (
            snap.name != "market_snapshot.sqlite3"
            or not snap.parent.name.startswith("StockScope_P0_03_ApiJob_")
        ):
            return {**base, "status": "HOLD_UNSAFE_WORKER_SOURCE"}
        scope = nullcontext(snap.parent)
    else:
        scope = TemporaryDirectory(prefix="StockScope_P0_03_ApiJob_")
    with scope as tmp:
        scratch = Path(tmp)
        snapshot = market_db if _snapshot_worker else scratch / "market_snapshot.sqlite3"
        if not _snapshot_worker:
            try:
                snapshot_sqlite_readonly(market_db, snapshot)
            except (OSError, sqlite3.DatabaseError) as exc:
                return {**base, "status": "HOLD_SNAPSHOT_FAILED", "error_class": type(exc).__name__}
        if os.name == "nt" and not _snapshot_worker:
            cmd = [
                sys.executable, str(Path(__file__).resolve()), "--_snapshot-worker",
                "--market-db", str(snapshot), "--as-of", as_of.isoformat(),
                "--market-scope", market_scope, "--operational-repo", str(operational_repo),
            ]
            try:
                child = subprocess.run(
                    cmd, capture_output=True, text=True, encoding="utf-8",
                    errors="replace", timeout=600,
                    env={**os.environ, "PYTHONIOENCODING": "utf-8"},
                )
            except (OSError, subprocess.TimeoutExpired) as exc:
                return {**base, "status": "HOLD_WORKER_FAILED", "error_class": type(exc).__name__}
            try:
                data = json.loads(child.stdout)
            except (json.JSONDecodeError, TypeError):
                return {**base, "status": "HOLD_WORKER_INVALID_OUTPUT", "returncode": child.returncode}
            if child.returncode not in (0, 2) or data.get("version") != VERSION:
                return {**base, "status": "HOLD_WORKER_EXIT", "returncode": child.returncode}
            return data
        try:
            detail = asyncio.run(_run_api_worker(
                snapshot=snapshot, as_of=as_of,
                operational_repo=operational_repo, scope=market_scope,
                scratch=scratch,
            ))
        except Exception as exc:
            detail = {"status": "HOLD_API_JOB_REPLAY_FAILED", "error_class": type(exc).__name__}
        return {**base, **detail}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Offline historical real Scanner job + temporary capture UAT (no KRX/TypeSafe)."
    )
    parser.add_argument("--market-db", type=Path, required=True)
    parser.add_argument("--operational-repo", type=Path, required=True)
    parser.add_argument("--as-of", type=date.fromisoformat, required=True)
    parser.add_argument("--market-scope", choices=("ALL", *MARKETS), default="ALL")
    parser.add_argument("--_snapshot-worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    output = offline_job_uat(
        market_db=args.market_db,
        as_of=args.as_of,
        market_scope=args.market_scope,
        operational_repo=args.operational_repo,
        _snapshot_worker=args._snapshot_worker,
    )
    print(json.dumps(output, indent=2, ensure_ascii=False, sort_keys=True))
    return 0 if output["status"] == "OFFLINE_API_JOB_CAPTURE_VERIFIED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
