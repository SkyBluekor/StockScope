"""Explicitly approved one-time P0-05/G1 Scanner capture into actual Windows stores.

This file never schedules work or retroactively backfills a capture.
A detached Git worktree may provide code, but it never owns the operational
Market/Simulation DB, KRX request ledger or provider API key.
"""
from __future__ import annotations

import argparse
from contextlib import closing, contextmanager
from datetime import datetime
import json
import os
from pathlib import Path
import secrets
import socket
import sqlite3
import subprocess
import sys
import time
from typing import Any, Iterator

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
for path in (ROOT, BACKEND):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from tools.data import prospective_daily as daily

VERSION = "STOCKSCOPE_P0_05_G1_OPERATOR_CAPTURE_V1"
MIN_NETWORK_CAP = 16
MAX_NETWORK_CAP = 1024


def _result(status: str, **details: Any) -> dict[str, Any]:
    return {
        "version": VERSION, "status": status,
        "scheduler_registered": False, "real_orders": 0,
        "historical_capture_backfilled": False, **details,
    }


def _paths(root: Path) -> tuple[Path, Path, Path]:
    repo = Path(root).resolve()
    market = repo / "backend/runtime/market_history/market_history.db"
    simulation = repo / "backend/runtime/simulation/simulation.db"
    budget = repo / "backend/runtime/krx/budget.sqlite3"
    if not all(path.is_file() for path in (market, simulation, budget)):
        raise daily.DailyError("HOLD_OPERATIONAL_STORE_OR_BUDGET_MISSING")
    if repo == ROOT.resolve():
        # This is permitted only when code and operational checkout coincide.
        return market, simulation, budget
    # A detached worktree must never initialize its own empty operational DB.
    return market, simulation, budget


def _budget_allowed(budget: Path, cap: int, now: datetime) -> bool:
    limit_text = (os.getenv("KRX_DAILY_SAFE_LIMIT") or "8000").strip()
    try:
        safe_limit = max(1, int(limit_text))
        if not MIN_NETWORK_CAP <= cap <= MAX_NETWORK_CAP:
            raise ValueError("cap")
        with closing(sqlite3.connect(
            budget.resolve().as_uri() + "?mode=ro", uri=True, timeout=10,
        )) as conn:
            conn.execute("PRAGMA query_only=ON")
            fields = {str(row[1]) for row in conn.execute(
                "PRAGMA table_info(krx_daily_usage)"
            )}
            if not {"day", "requests", "retries"}.issubset(fields):
                raise daily.DailyError("HOLD_OPERATIONAL_KRX_LEDGER_UNAVAILABLE")
            row = conn.execute(
                "SELECT requests,retries FROM krx_daily_usage WHERE day=?",
                (now.astimezone(daily.KST).date().isoformat(),),
            ).fetchone()
            used, retries = (int(row[0]), int(row[1])) if row else (0, 0)
            if used < 0 or retries < 0 or retries > used:
                raise daily.DailyError("HOLD_OPERATIONAL_KRX_LEDGER_UNAVAILABLE")
            return used + cap <= safe_limit
    except (sqlite3.Error, ValueError) as exc:
        raise daily.DailyError("HOLD_OPERATIONAL_KRX_LEDGER_UNAVAILABLE") from exc


def readiness(root: Path, *, scope: str, cap: int,
              now: datetime | None = None) -> dict[str, Any]:
    checked = now or daily._now()
    _, reason = daily._accepted_clock(checked)
    if reason:
        return _result("HOLD_" + reason, execution_window_open=False,
                       market_db_writes=0, external_requests=0)
    market, simulation, budget = _paths(root)
    local = daily.preflight_local_g1(
        scope=scope, candidate_limit=5,
        simulation_db=simulation, market_db=market,
        log_root=Path(root) / "data/prospective_daily",
        now=checked,
    )
    if local["status"] != "LOCAL_STORED_EOD_READY_APPROVAL_REQUIRED":
        return _result(local["status"], execution_window_open=True,
                       market_db_writes=0, external_requests=0,
                       stored_common_data_date=local.get("stored_common_data_date"))
    if not _budget_allowed(budget, cap, checked):
        return _result("HOLD_OPERATIONAL_KRX_BUDGET_INSUFFICIENT",
                       execution_window_open=True, external_requests=0, market_db_writes=0)
    return _result("LOCAL_G1_ELIGIBLE_APPROVAL_REQUIRED",
                   execution_window_open=True,
                   stored_common_data_date=local.get("stored_common_data_date"),
                   budget_cap=cap, operational_stores_checked_read_only=True,
                   external_requests=0, market_db_writes=0,
                   provider_service_entitlements_verified=False,
                   official_publication_verified=False,
                   production_capture_approved=False)


@contextmanager
def _isolated_backend(*, child_env: dict[str, str],
                      expected_nonce: str, port: int,
                      http: Any) -> Iterator[None]:
    """Always spawn a *new* worker, never reuse an unidentified local server."""
    with open(os.devnull, "wb") as quiet:
        process = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "g1_worker:app",
             "--host", "127.0.0.1", "--port", str(port)],
            cwd=daily.BACKEND, env=child_env,
            stdin=subprocess.DEVNULL, stdout=quiet, stderr=quiet,
        )
        try:
            for _ in range(90):
                if process.poll() is not None:
                    raise daily.DailyError("G1_ISOLATED_BACKEND_START_FAILED")
                try:
                    response = http("/")
                except daily.DailyError:
                    time.sleep(1)
                    continue
                if (response.get("g1_worker_nonce") != expected_nonce
                        or response.get("status") != "running"
                        or response.get("real_trading") is not False):
                    raise daily.DailyError("G1_ISOLATED_BACKEND_IDENTITY_MISMATCH")
                break
            else:
                raise daily.DailyError("G1_ISOLATED_BACKEND_NOT_READY")
            yield
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=10)


def capture_approved(
    *, root: Path, scope: str, candidate_limit: int,
    max_krx_requests: int, approve_krx: bool,
    approve_simulation_write: bool, confirm_services: bool,
    now: datetime | None = None,
) -> dict[str, Any]:
    if not all((approve_krx, approve_simulation_write, confirm_services)):
        return _result("HOLD_EXPLICIT_G1_CAPTURE_APPROVAL_REQUIRED",
                       external_requests=0, market_db_writes=0,
                       new_capture_created=False)
    if not 1 <= candidate_limit <= 10 or scope not in ("KOSPI", "KOSDAQ", "ALL"):
        return _result("HOLD_G1_INVALID_ARGUMENTS", new_capture_created=False)
    checked = now or daily._now()
    preflight = readiness(root, scope=scope, cap=max_krx_requests, now=checked)
    if preflight["status"] != "LOCAL_G1_ELIGIBLE_APPROVAL_REQUIRED":
        return preflight
    market, sim, budget = _paths(root)
    from app.core.config import Settings
    settings = Settings(_env_file=Path(root).resolve() / ".env")
    if not isinstance(settings.krx_api_key, str) or not settings.krx_api_key.strip():
        return _result("HOLD_OPERATIONAL_KRX_KEY_MISSING",
                       external_requests=0, market_db_writes=0,
                       new_capture_created=False)

    # Reserve an isolated ephemeral loopback port without adopting an existing
    # service. A random nonce identifies precisely our child worker.
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    nonce = secrets.token_hex(16)
    env = os.environ.copy()
    env.update({
        "KRX_API_KEY": settings.krx_api_key,
        "STOCKSCOPE_MARKET_STORE_DB": str(market.resolve()),
        "STOCKSCOPE_SIM_DB": str(sim.resolve()),
        "STOCKSCOPE_KRX_BUDGET_DB": str(budget.resolve()),
        "STOCKSCOPE_G1_MAX_KRX_CALLS": str(max_krx_requests),
        "STOCKSCOPE_G1_WORKER_NONCE": nonce,
        # The single-purpose Scanner worker must not open quote websockets.
        "KIS_WS_ENABLED": "false",
    })
    # Avoid modifying the operational Holdings DB just to start a Scanner
    # worker; it uses its code worktree's independent transient DB instead.
    env["STOCKSCOPE_HOLDINGS_DB"] = str(
        daily.BACKEND / "runtime" / "holdings" / "holdings.db"
    )
    base_url = "http://127.0.0.1:" + str(port)
    def local_http(path: str, **kwargs: Any) -> dict[str, Any]:
        return daily._http(path, base_url=base_url, **kwargs)
    @contextmanager
    def launch(_: Any) -> Iterator[None]:
        with _isolated_backend(
            child_env=env, expected_nonce=nonce,
            port=port, http=local_http,
        ):
            yield

    # run_once itself rechecks KST window, latest KRX EOD, exact duplicate,
    # and persistence+hashes; its scope/limit stay unchanged.
    result = daily.run_once(
        scope=scope, candidate_limit=candidate_limit,
        simulation_db=sim, market_db=market,
        log_root=Path(root).resolve() / "data/prospective_daily",
        now=checked, http=local_http, server=launch,
    )
    return _result(result["status"], s17=result,
                   user_approved_krx_cap=max_krx_requests,
                   actual_performance_verified=False)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Operator-approved single G1 Scanner capture")
    parser.add_argument("--operational-repo", type=Path, required=True)
    parser.add_argument("--scope", choices=("ALL", "KOSPI", "KOSDAQ"), default="ALL")
    parser.add_argument("--candidate-limit", type=int, default=5)
    parser.add_argument("--max-krx-requests", type=int, default=128)
    parser.add_argument("--run-approved", action="store_true")
    parser.add_argument("--approve-krx-requests", action="store_true")
    parser.add_argument("--approve-simulation-write", action="store_true")
    parser.add_argument("--confirm-krx-services", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.run_approved:
            out = capture_approved(
                root=args.operational_repo, scope=args.scope,
                candidate_limit=args.candidate_limit,
                max_krx_requests=args.max_krx_requests,
                approve_krx=args.approve_krx_requests,
                approve_simulation_write=args.approve_simulation_write,
                confirm_services=args.confirm_krx_services,
            )
        elif any((args.approve_krx_requests, args.approve_simulation_write,
                  args.confirm_krx_services)):
            out = _result("HOLD_APPROVAL_FLAGS_WITHOUT_RUN")
        else:
            out = readiness(
                args.operational_repo, scope=args.scope,
                cap=args.max_krx_requests,
            )
    except (daily.DailyError, OSError, sqlite3.Error, ValueError):
        out = _result("HOLD_LOCAL_G1_OPERATOR_UNAVAILABLE",
                      external_requests=0, new_capture_created=False)
    except Exception:
        # No API key, local path, or user market data may be disclosed.
        out = _result("HOLD_G1_OPERATOR_FAILED")
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0 if out["status"] in (
        "LOCAL_G1_ELIGIBLE_APPROVAL_REQUIRED",
        "SCANNER_CAPTURED_AND_OUTCOME_CHECKED",
        "SKIPPED_ALREADY_CAPTURED_OR_PENDING",
        "SKIPPED_NO_FRESH_CONFIRMED_EOD",
    ) else 2


if __name__ == "__main__":
    raise SystemExit(main())
