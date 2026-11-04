"""Offline replay of the *real* frozen StockScannerService against a DB backup.

No KRX, TypeSafe, HTTP, brokerage, production DB writes, or production jobs.
The full strategy / Risk calculation runs locally only if every required market
history slot already has a stored day-status marker. Results are EOD-only and
are not an API job, persisted capture, or live trading recommendation.
"""
from __future__ import annotations

import argparse
import asyncio
from contextlib import closing, contextmanager, nullcontext
from datetime import date, datetime, timedelta, timezone
import json
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys
from tempfile import TemporaryDirectory
from typing import Any, Iterator

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
for path in (ROOT, BACKEND):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from tools.data.p0_02_operational_store_audit import inspect_operational_store

VERSION = "P0_02_REAL_SCANNER_OFFLINE_REPLAY_V1"
KST = timezone(timedelta(hours=9))
MARKETS = ("KOSPI", "KOSDAQ")


class NetworkAttemptBlocked(RuntimeError):
    pass


class OfflineKrx:
    """Deliberately has no HTTP client, credential or disk-cache reader."""

    def __init__(self, cutoff: date):
        self.cutoff = cutoff
        self.attempts = 0
        self.stats = {
            "network_requests": 0,
            "memory_hits": 0,
            "disk_hits": 0,
            "empty_marker_hits": 0,
            "retries": 0,
            "forced_network_requests": 0,
        }

    def _today_kst(self) -> date:
        # A fixed next-day clock verifies historical EOD without seeking today.
        return self.cutoff + timedelta(days=1)

    def request_stats(self) -> dict[str, int]:
        return dict(self.stats)

    def has_cached_day(self, _market: str, _day: date, _kind: str) -> bool:
        return False

    def assert_budget(self, estimated_requests: int) -> dict[str, int]:
        if estimated_requests:
            self.attempts += 1
            raise NetworkAttemptBlocked("OFFLINE_MARKET_DATA_REQUIRED")
        return {"used": 0, "safe_limit": 0, "remaining": 0}

    def budget_snapshot(self) -> dict[str, int]:
        return {"used": 0, "safe_limit": 0, "remaining": 0}

    async def open_session(self) -> None:
        return None

    async def close_session(self) -> None:
        return None

    async def stock_daily(self, *_args: Any, **_kwargs: Any) -> dict:
        self.attempts += 1
        raise NetworkAttemptBlocked("OFFLINE_KRX_STOCK_CALL_BLOCKED")

    async def index_daily(self, *_args: Any, **_kwargs: Any) -> dict:
        self.attempts += 1
        raise NetworkAttemptBlocked("OFFLINE_KRX_INDEX_CALL_BLOCKED")

    @staticmethod
    def _select_main_index(rows: list[dict], market: str) -> dict | None:
        return rows[0] if rows else None


@contextmanager
def prohibit_external_connections() -> Iterator[list[str]]:
    """Deny external TCP while allowing Windows asyncio's loopback self-pipe."""
    old_connect = socket.socket.connect
    old_connect_ex = socket.socket.connect_ex
    old_create_connection = socket.create_connection
    blocked: list[str] = []

    def is_internal_loopback(address: Any) -> bool:
        if not isinstance(address, tuple) or not address:
            return False
        host = address[0]
        return host in {"127.0.0.1", "::1"}

    def connect(sock: socket.socket, address: Any) -> Any:
        if is_internal_loopback(address):
            return old_connect(sock, address)
        blocked.append("SOCKET_CONNECT_DENIED")
        raise NetworkAttemptBlocked("EXTERNAL_SOCKET_CONNECT_DENIED")

    def connect_ex(sock: socket.socket, address: Any) -> int:
        if is_internal_loopback(address):
            return old_connect_ex(sock, address)
        blocked.append("SOCKET_CONNECT_EX_DENIED")
        raise NetworkAttemptBlocked("EXTERNAL_SOCKET_CONNECT_EX_DENIED")

    def create_connection(address: Any, *args: Any, **kwargs: Any) -> Any:
        if is_internal_loopback(address):
            return old_create_connection(address, *args, **kwargs)
        blocked.append("CREATE_CONNECTION_DENIED")
        raise NetworkAttemptBlocked("EXTERNAL_CREATE_CONNECTION_DENIED")

    socket.socket.connect = connect
    socket.socket.connect_ex = connect_ex
    socket.create_connection = create_connection
    try:
        yield blocked
    finally:
        socket.socket.connect = old_connect
        socket.socket.connect_ex = old_connect_ex
        socket.create_connection = old_create_connection


def snapshot_sqlite_readonly(source_path: Path, destination_path: Path) -> None:
    """Consistent SQLite backup includes committed WAL; original is read-only."""
    if not source_path.is_file():
        raise FileNotFoundError("OPERATIONAL_DB_NOT_FOUND")
    with closing(sqlite3.connect(source_path.resolve().as_uri() + "?mode=ro", uri=True)) as source:
        source.execute("PRAGMA query_only=ON")
        with closing(sqlite3.connect(destination_path)) as destination:
            source.backup(destination)
            destination.commit()


def _git_sha() -> str | None:
    try:
        completed = subprocess.run(
            ["git", "-C", str(ROOT), "rev-parse", "HEAD"],
            check=False, capture_output=True, text=True, timeout=5,
        )
        sha = completed.stdout.strip()
        return sha if completed.returncode == 0 and len(sha) == 40 else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def offline_replay(
    market_db: Path, *,
    as_of: date,
    market_scope: str = "ALL",
    candidate_limit: int = 5,
    operational_repo: Path | None = None,
    _snapshot_worker: bool = False,
) -> dict[str, Any]:
    if market_scope not in {"ALL", *MARKETS}:
        raise ValueError("INVALID_MARKET_SCOPE")
    if not 1 <= candidate_limit <= 10:
        raise ValueError("INVALID_CANDIDATE_LIMIT")
    if as_of >= datetime.now(KST).date():
        raise ValueError("AS_OF_MUST_BE_BEFORE_KST_TODAY")

    base = {
        "version": VERSION,
        "code_sha": _git_sha(),
        "as_of": as_of.isoformat(),
        "market_scope": market_scope,
        "real_scanner_service": True,
        "api_job_executed": False,
        "prospective_capture_persisted": False,
        "market_db_original_modified": False,
        "krx_calls": 0,
        "typesafe_calls": 0,
        "external_connections_blocked": True,
        "provider_publication_verified": False,
        "official_holiday_calendar_verified": False,
    }
    # On Windows the production MarketStore uses SQLite connections in
    # transaction context managers, which do NOT close sqlite3.Connection.
    # If those handles survive until TemporaryDirectory cleanup, Windows
    # denies deletion and hides the real Scanner result as PermissionError.
    # The worker opens only a copied DB and exits before the parent cleans it.
    if _snapshot_worker:
        worker_db = Path(market_db).resolve()
        if (
            worker_db.name != "market_snapshot.sqlite3"
            or not worker_db.parent.name.startswith("StockScope_P0_02_OfflineScanner_")
        ):
            return {**base, "status": "HOLD_UNSAFE_WORKER_SNAPSHOT_PATH"}
        scratch_context = nullcontext(worker_db.parent)
    else:
        scratch_context = TemporaryDirectory(prefix="StockScope_P0_02_OfflineScanner_")

    with scratch_context as tmp:
        scratch = Path(tmp)
        snapshot = Path(market_db) if _snapshot_worker else scratch / "market_snapshot.sqlite3"
        if not _snapshot_worker:
            try:
                snapshot_sqlite_readonly(market_db, snapshot)
            except (OSError, sqlite3.DatabaseError) as exc:
                return {**base, "status": "HOLD_SOURCE_SNAPSHOT_FAILED", "error_class": type(exc).__name__}

        if os.name == "nt" and not _snapshot_worker:
            # Important: never pass the ORIGINAL DB path to the child. Exit
            # closes the worker's SQLite file handles before parent cleanup.
            cmd = [
                sys.executable, str(Path(__file__).resolve()),
                "--_snapshot-worker",
                "--market-db", str(snapshot),
                "--as-of", as_of.isoformat(),
                "--market-scope", market_scope,
                "--candidate-limit", str(candidate_limit),
            ]
            if operational_repo is not None:
                cmd.extend(["--operational-repo", str(operational_repo)])
            try:
                worker_env = dict(os.environ)
                worker_env["PYTHONIOENCODING"] = "utf-8"
                worker = subprocess.run(
                    cmd, capture_output=True, text=True, encoding="utf-8",
                    errors="replace", timeout=600, env=worker_env,
                )
            except (OSError, subprocess.TimeoutExpired) as exc:
                return {**base, "status": "HOLD_WORKER_START_OR_TIMEOUT", "error_class": type(exc).__name__}
            try:
                payload = json.loads(worker.stdout)
            except (TypeError, json.JSONDecodeError):
                return {
                    **base, "status": "HOLD_WORKER_INVALID_OUTPUT",
                    "worker_returncode": worker.returncode,
                }
            if not isinstance(payload, dict) or payload.get("version") != VERSION:
                return {**base, "status": "HOLD_WORKER_INVALID_REPORT"}
            if worker.returncode not in (0, 2):
                return {
                    **base, "status": "HOLD_WORKER_ABNORMAL_EXIT",
                    "worker_returncode": worker.returncode,
                }
            return payload

        audit = inspect_operational_store(
            snapshot, as_of=as_of, market_scope=market_scope, lookback_calendar_days=220,
        )
        expected = audit.get("last_common_marked_stock_index_date")
        if expected != as_of.isoformat():
            return {
                **base, "status": "HOLD_COMMON_AS_OF_MISMATCH",
                "observed_common_date": expected,
                "weekday_unverified_slots": {
                    market: audit.get("markets", {}).get(market, {}).get("weekdays_without_both_marked_rows")
                    for market in (MARKETS if market_scope == "ALL" else (market_scope,))
                },
            }

        # Import here, after taking the isolated operational DB snapshot.
        from app.backtest.market_store import HistoricalMarketStore
        from app.backtest import scanner as scanner_module
        from app.backtest.scanner import StockScannerService
        from app.strategy.production_selection_policy import ProductionStrategySelectionRegistry

        store = HistoricalMarketStore(snapshot)
        provider = OfflineKrx(as_of)
        # The active selection policy is read-only from its real local runtime
        # source; do not silently assume the temporary checkout's fallback is
        # necessarily the user's current policy. No policy activation is called.
        original_root = Path(operational_repo) if operational_repo else Path(market_db).resolve().parents[3]
        registry = ProductionStrategySelectionRegistry(
            runtime_dir=original_root / "backend" / "runtime" / "strategy_selection"
        )
        service = StockScannerService(provider, market_store=store, selection_registry=registry)
        markets = list(MARKETS) if market_scope == "ALL" else [market_scope]
        plans = {
            market: service._history_plan(
                market=market,
                start=as_of - timedelta(days=StockScannerService.FAST_HISTORY_CALENDAR_DAYS),
                end=as_of,
            )
            for market in markets
        }
        missing = {
            market: len(plan["work"])
            for market, plan in plans.items()
        }
        if any(missing.values()):
            return {
                **base,
                "status": "HOLD_OFFLINE_LOOKBACK_INCOMPLETE",
                "stored_common_date": expected,
                "missing_history_slots_by_market": missing,
                "next_action": "Prepare required dates only via the existing authorized Scanner data path.",
            }

        # Scanner cache writes are isolated to scratch. Reproducibility audit
        # file writing is disabled here; input_fingerprint still comes from
        # the unmodified production Scanner calculation.
        original_cache_root = StockScannerService.CACHE_ROOT
        original_write_audit = scanner_module.write_scanner_reproducibility_audit
        StockScannerService.CACHE_ROOT = scratch / "scanner-cache"
        scanner_module.write_scanner_reproducibility_audit = (
            lambda **_kwargs: {"written": False, "skipped": "OFFLINE_EPHEMERAL_REPLAY"}
        )
        blocked: list[str] = []
        try:
            with prohibit_external_connections() as blocked:
                result = asyncio.run(
                    service.run(
                        market_scope=market_scope,
                        as_of_date=as_of.isoformat(),
                        candidate_limit=candidate_limit,
                        force_refresh=True,
                        allow_large_sync=False,
                    )
                )
        except Exception as exc:
            return {
                **base,
                "status": "HOLD_OFFLINE_SCANNER_EXECUTION_FAILED",
                "error_class": type(exc).__name__,
                "network_attempts": provider.attempts + len(blocked),
                "missing_history_slots_by_market": missing,
            }
        finally:
            StockScannerService.CACHE_ROOT = original_cache_root
            scanner_module.write_scanner_reproducibility_audit = original_write_audit

        data_dates = result.get("data_dates") or {}
        fingerprint = result.get("input_fingerprint") or {}
        diagnostics = result.get("diagnostics") or {}
        policy = result.get("strategy_selection_policy") or {}
        no_net = (
            provider.attempts == 0 and not blocked
            and int(diagnostics.get("network_requests") or 0) == 0
        )
        aligned = all(data_dates.get(market) == as_of.isoformat() for market in markets)
        has_proof = bool(fingerprint.get("id")) and all(
            (fingerprint.get("markets") or {}).get(market, {}).get("date") == as_of.isoformat()
            and int((fingerprint.get("markets") or {}).get(market, {}).get("stock_rows") or 0) > 0
            and (fingerprint.get("markets") or {}).get(market, {}).get("stock_hash")
            and (fingerprint.get("markets") or {}).get(market, {}).get("index_hash")
            for market in markets
        )
        valid = no_net and aligned and has_proof and not result.get("partial_data")
        summary = dict(result.get("summary") or {})
        safe_summary = {
            key: summary.get(key) for key in (
                "universe_total", "quick_analyzed", "deep_analyzed",
                "candidate_count", "shown_count", "data_insufficient",
                "three_year_evidence_verified", "three_year_evidence_data_unavailable",
            )
        }
        return {
            **base,
            "status": "OFFLINE_SCANNER_COMPUTATION_VERIFIED" if valid else "HOLD_SCANNER_OUTPUT_MISMATCH",
            "stored_common_date": expected,
            "scanner_version": result.get("version"),
            "scanner_requested_as_of": result.get("requested_as_of"),
            "scanner_data_dates": data_dates,
            "scanner_input_fingerprint": {
                "id": fingerprint.get("id"),
                "markets": {
                    market: {
                        "date": (fingerprint.get("markets") or {}).get(market, {}).get("date"),
                        "stock_rows": (fingerprint.get("markets") or {}).get(market, {}).get("stock_rows"),
                        "stock_hash": (fingerprint.get("markets") or {}).get(market, {}).get("stock_hash"),
                        "index_hash": (fingerprint.get("markets") or {}).get(market, {}).get("index_hash"),
                    }
                    for market in markets
                },
            },
            "selection_policy_source": policy.get("source") or policy.get("policy_source"),
            "selection_policy_id": policy.get("policy_id"),
            "selection_policy_fallback": policy.get("fallback_used"),
            "scanner_cache_hit": result.get("scanner_cache_hit"),
            "partial_data": result.get("partial_data"),
            "missing_history_slots_by_market": missing,
            "scanner_summary": safe_summary,
            "network_attempts": provider.attempts + len(blocked),
            "budget_real_calls": 0,
        }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the real Scanner calculation offline on a throwaway SQLite backup.")
    parser.add_argument("--market-db", required=True, type=Path)
    parser.add_argument("--as-of", required=True)
    parser.add_argument("--market-scope", default="ALL", choices=("ALL", *MARKETS))
    parser.add_argument("--candidate-limit", default=5, type=int)
    parser.add_argument("--operational-repo", type=Path, default=None)
    parser.add_argument("--_snapshot-worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    try:
        result = offline_replay(
            args.market_db,
            as_of=date.fromisoformat(args.as_of),
            market_scope=args.market_scope,
            candidate_limit=args.candidate_limit,
            operational_repo=args.operational_repo,
            _snapshot_worker=args._snapshot_worker,
        )
    except (ValueError, OSError) as exc:
        result = {"version": VERSION, "status": "HOLD_INVALID_REPLAY_INPUT", "error_class": type(exc).__name__}
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["status"] == "OFFLINE_SCANNER_COMPUTATION_VERIFIED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
