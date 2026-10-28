"""Opt-in StockScope daily local Scanner+forward-outcome collection.

Runs ONLY for a fresh confirmed previous EOD on a weekday morning in Asia/Seoul.
No backfilling a missed run, no live order, no JEV provider. Starts a temporary
loopback FastAPI backend if needed; Scanner itself supplies canonical frozen
Prospective captures and refreshes the local KRX market store.

A future observed market bar is not a real trade return or a Q7 approval.
"""
from __future__ import annotations

import argparse
from contextlib import closing, contextmanager
from datetime import date, datetime, time, timedelta, timezone
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import time as time_module
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener, ProxyHandler

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
for p in (ROOT, BACKEND):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from app.jev.q7_observation_s16 import measure as observe_outcomes
from app.prospective.models import digest_json
from tools.data.common import market_db_path, simulation_db_path

VERSION = "STOCKSCOPE_PROSPECTIVE_DAILY_S17_V1"
KST = timezone(timedelta(hours=9), name="KST")
BASE_URL = "http://127.0.0.1:8000"
DEFAULT_LOG_ROOT = ROOT / "data" / "prospective_daily"
MORNING_START = time(5, 0)
MORNING_END = time(8, 45)
POLL_SECONDS = 10
JOB_TIMEOUT_SECONDS = 3600
FRESHNESS_TIMEOUT_SECONDS = 1200


class DailyError(RuntimeError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _now() -> datetime:
    return datetime.now(KST)


def _report(status: str, **details: Any) -> dict[str, Any]:
    return {
        "version": VERSION,
        "status": status,
        "actual_orders": 0,
        "external_ai_calls": 0,
        "q7_approval_eligible": False,
        "strategy_promotion_allowed": False,
        "retroactive_capture_created": False,
        **details,
    }


def _accepted_clock(now: datetime) -> tuple[date, str | None]:
    if now.tzinfo is None or now.utcoffset() is None or now.utcoffset() != timedelta(hours=9):
        raise DailyError("KOREAN_LOCAL_TIME_REQUIRED")
    local = now.astimezone(KST)
    if local.weekday() >= 5:
        return local.date(), "WEEKEND"
    if not MORNING_START <= local.time().replace(tzinfo=None) <= MORNING_END:
        return local.date(), "OUTSIDE_PREMARKET_WINDOW"
    return local.date(), None


def _fresh_date(value: dict[str, Any], today: date) -> date | None:
    if value.get("status") not in ("READY", "UPDATED"):
        return None
    raw = value.get("resolved_as_of_date")
    if type(raw) is not str:
        return None
    try:
        actual = date.fromisoformat(raw)
    except ValueError:
        return None
    # Last confirmed EOD is necessarily before today. Weekend / holiday
    # delays up to four calendar days are permitted; older bars fail closed.
    if not 1 <= (today - actual).days <= 4:
        return None
    return actual


def _existing_capture(db: Path, *, market_scope: str, data_date: date) -> dict[str, str] | None:
    """Idempotency includes manual Scanner runs and concurrent pending jobs."""
    if not db.is_file():
        raise DailyError("SIMULATION_DB_NOT_READY")
    try:
        with sqlite3.connect(db.resolve().as_uri() + "?mode=ro", uri=True, timeout=10) as conn:
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA query_only=ON")
            row = conn.execute(
                "SELECT id,status FROM prospective_capture_run "
                "WHERE market_scope=? AND (requested_as_of=? OR actual_data_date=?) "
                "AND status IN ('PENDING','COMPLETE','PARTIAL','DUPLICATE') "
                "ORDER BY created_at DESC LIMIT 1",
                (market_scope, data_date.isoformat(), data_date.isoformat()),
            ).fetchone()
    except sqlite3.Error as exc:
        raise DailyError("CAPTURE_READ_UNAVAILABLE") from exc
    return dict(row) if row else None


def _verify_persisted_capture(
    db: Path, *, source_job_id: str, capture: dict[str, Any],
    signal_date: date, market_scope: str,
) -> dict[str, Any]:
    """Fail closed if HTTP COMPLETE is not the exact immutable SQLite evidence.

    This is read-only, including on a live WAL DB. A COMPLETE capture is not
    itself S7-valid or investment-performance evidence.
    """
    capture_id = capture.get("capture_id")
    status = capture.get("status")
    canonical_id = capture.get("canonical_capture_id")
    if (type(capture_id) is not str or not capture_id
            or status not in ("COMPLETE", "DUPLICATE")
            or (canonical_id is not None and (type(canonical_id) is not str or not canonical_id))
            or not db.is_file()):
        raise DailyError("FROZEN_CAPTURE_PROOF_UNAVAILABLE")
    try:
        with closing(sqlite3.connect(
            db.resolve().as_uri() + "?mode=ro", uri=True, timeout=10,
        )) as conn:
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA query_only=ON")
            conn.execute("BEGIN")
            row = conn.execute(
                "SELECT id,status,source_job_id,market_scope,actual_data_date,"
                "canonical_capture_id,returned_candidate_count,"
                "source_execution_key,source_snapshot_hash,result_hash "
                "FROM prospective_capture_run WHERE id=?", (capture_id,),
            ).fetchone()
            if (row is None or row["source_job_id"] != source_job_id
                    or row["status"] != status
                    or row["market_scope"] != market_scope
                    or row["actual_data_date"] != signal_date.isoformat()
                    or row["canonical_capture_id"] != canonical_id
                    or not row["source_execution_key"] or not row["source_snapshot_hash"]
                    or not row["result_hash"]):
                raise DailyError("FROZEN_CAPTURE_DB_PROOF_MISMATCH")
            if status == "COMPLETE":
                if canonical_id is not None:
                    raise DailyError("FROZEN_CAPTURE_DB_PROOF_MISMATCH")
                canonical = row
            else:
                if not canonical_id or canonical_id == capture_id:
                    raise DailyError("FROZEN_CAPTURE_DB_PROOF_MISMATCH")
                canonical = conn.execute(
                    "SELECT id,status,market_scope,actual_data_date,"
                    "returned_candidate_count,source_execution_key,"
                    "source_snapshot_hash,result_hash "
                    "FROM prospective_capture_run WHERE id=?", (canonical_id,),
                ).fetchone()
                if (canonical is None or canonical["status"] != "COMPLETE"
                        or canonical["market_scope"] != market_scope
                        or canonical["actual_data_date"] != signal_date.isoformat()
                        or any(row[k] != canonical[k] for k in (
                            "returned_candidate_count", "source_execution_key",
                            "source_snapshot_hash", "result_hash",
                        ))):
                    raise DailyError("FROZEN_CAPTURE_DB_PROOF_MISMATCH")
            expected = canonical["returned_candidate_count"]
            if (type(expected) is not int or not 0 <= expected <= 100
                    or capture.get("returned_candidate_count") != expected):
                raise DailyError("FROZEN_CAPTURE_COUNT_MISMATCH")
            samples = conn.execute(
                "SELECT sample_index,signal_date,snapshot_json,snapshot_hash "
                "FROM prospective_recommendation_sample "
                "WHERE capture_run_id=? ORDER BY sample_index", (canonical["id"],),
            ).fetchall()
            if len(samples) != expected:
                raise DailyError("FROZEN_CAPTURE_COUNT_MISMATCH")
            for index, item in enumerate(samples):
                try:
                    valid = digest_json(json.loads(item["snapshot_json"])) == item["snapshot_hash"]
                except (ValueError, TypeError, UnicodeError):
                    valid = False
                if (item["sample_index"] != index
                        or item["signal_date"] != signal_date.isoformat()
                        or not valid):
                    raise DailyError("FROZEN_CAPTURE_SNAPSHOT_MISMATCH")
            return {
                "persisted_capture_verified": True,
                "persisted_snapshot_hashes_verified": True,
                "persisted_sample_count": len(samples),
                "performance_verified": False,
            }
    except sqlite3.Error as exc:
        raise DailyError("FROZEN_CAPTURE_DB_READ_UNAVAILABLE") from exc


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise DailyError("LOCAL_API_REDIRECT_FORBIDDEN")


def _http(path: str, *, method: str = "GET", payload: dict[str, Any] | None = None,
          timeout: int = 30) -> dict[str, Any]:
    """Loopback only, no credentials, proxies or remote host overrides."""
    if not path.startswith("/") or path.startswith("//"):
        raise DailyError("INVALID_LOCAL_API_PATH")
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = Request(
        BASE_URL + path, data=data, method=method,
        headers={"Content-Type": "application/json"} if data else {},
    )
    opener = build_opener(ProxyHandler({}), _NoRedirect())
    try:
        with opener.open(request, timeout=timeout) as response:
            answer = json.loads(response.read(4_000_000).decode("utf-8"))
    except (OSError, HTTPError, URLError, UnicodeError, ValueError) as exc:
        raise DailyError("LOCAL_API_UNAVAILABLE_OR_REJECTED") from exc
    if not isinstance(answer, dict):
        raise DailyError("LOCAL_API_RESPONSE_INVALID")
    return answer


def _check_backend(http: Callable[..., dict[str, Any]]) -> bool:
    try:
        response = http("/")
    except DailyError:
        return False
    if (response.get("status") != "running"
            or response.get("real_trading") is not False
            or "stockscope" not in str(response.get("service") or "").lower()):
        raise DailyError("LOOPBACK_WRONG_SERVICE")
    return True


@contextmanager
def _backend_session(http: Callable[..., dict[str, Any]]):
    if _check_backend(http):
        yield
        return
    # Launch a temporary, single-worker backend without frontend/reload.
    # The task scheduler may execute even if run-dev.ps1 was never opened.
    with open(os.devnull, "wb") as quiet:
        process = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "app.main:app",
             "--host", "127.0.0.1", "--port", "8000"],
            cwd=BACKEND, stdin=subprocess.DEVNULL,
            stdout=quiet, stderr=quiet,
        )
        try:
            for _ in range(90):
                if process.poll() is not None:
                    raise DailyError("LOCAL_BACKEND_START_FAILED")
                if _check_backend(http):
                    break
                time_module.sleep(1)
            else:
                raise DailyError("LOCAL_BACKEND_NOT_READY")
            yield
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)


def _write_result(path: Path, report: dict[str, Any]) -> None:
    """Operational log only; not a trusted timestamp or production evidence."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".{os.getpid()}.tmp")
    try:
        tmp.write_text(
            json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def run_once(*, scope: str = "KOSPI", candidate_limit: int = 5,
             simulation_db: Path | None = None, market_db: Path | None = None,
             log_root: Path = DEFAULT_LOG_ROOT,
             now: datetime | None = None,
             http: Callable[..., dict[str, Any]] = _http,
             sleep: Callable[[float], None] = time_module.sleep,
             server: Callable[..., Any] = _backend_session,
             ) -> dict[str, Any]:
    if scope not in ("KOSPI", "KOSDAQ", "ALL") or type(candidate_limit) is not int or not 1 <= candidate_limit <= 10:
        raise DailyError("DAILY_ARGUMENT_INVALID")
    today, denied = _accepted_clock(now or _now())
    if denied:
        return _report("SKIPPED_" + denied, local_date=today.isoformat())
    sim = Path(simulation_db or simulation_db_path())
    market = Path(market_db or market_db_path())
    log = Path(log_root) / (today.isoformat() + "_" + scope.lower() + ".json")
    # Exclusive file prevents concurrent scheduled/manual daily workers.
    # A stale lock must be handled manually, not bypassed by a newer process.
    lock = log.with_suffix(".lock")
    lock.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        return _report("HOLD_EXISTING_RUN_LOCK", local_date=today.isoformat())
    with os.fdopen(fd, "w", encoding="utf-8") as fp:
        fp.write(_now().isoformat())
    try:
        with server(http):
            freshness = http(
                "/api/backtest/scanner/freshness", method="POST",
                payload={"market_scope": scope}, timeout=FRESHNESS_TIMEOUT_SECONDS,
            )
            signal_date = _fresh_date(freshness, today)
            if signal_date is None:
                outcome = _report(
                    "SKIPPED_NO_FRESH_CONFIRMED_EOD",
                    local_date=today.isoformat(),
                    freshness_status=str(freshness.get("status")),
                    freshness_data_date=freshness.get("resolved_as_of_date"),
                )
                _write_result(log, outcome)
                return outcome
            prior = _existing_capture(sim, market_scope=scope, data_date=signal_date)
            if prior is not None:
                observations = observe_outcomes(sim, market, as_of=today)
                outcome = _report(
                    "SKIPPED_ALREADY_CAPTURED_OR_PENDING",
                    local_date=today.isoformat(),
                    source_data_date=signal_date.isoformat(),
                    existing_capture_id=prior["id"],
                    existing_capture_status=prior["status"],
                    outcome_status=observations["status"],
                    outcome_windows=observations.get("windows"),
                )
                _write_result(log, outcome)
                return outcome

            request = {
                "market_scope": scope,
                "as_of_date": signal_date.isoformat(),
                "candidate_limit": candidate_limit,
                "force_refresh": True,
                "allow_large_sync": False,
                "horizon_intent": None,
            }
            job = http("/api/backtest/scanner/jobs", method="POST", payload=request)
            job_id = job.get("job_id")
            if type(job_id) is not str or len(job_id) < 8:
                raise DailyError("SCANNER_JOB_ID_INVALID")
            started_at = _now().isoformat()
            _write_result(log, _report(
                "SCANNER_IN_PROGRESS", source_data_date=signal_date.isoformat(),
                scanner_started_at=started_at, scanner_job_id=job_id,
            ))
            deadline = time_module.monotonic() + JOB_TIMEOUT_SECONDS
            while True:
                job = http(f"/api/backtest/jobs/{job_id}")
                if job.get("job_id") != job_id:
                    raise DailyError("SCANNER_JOB_ID_MISMATCH")
                if job.get("status") in ("completed", "failed", "cancelled"):
                    break
                if time_module.monotonic() >= deadline:
                    raise DailyError("SCANNER_JOB_TIMEOUT")
                sleep(POLL_SECONDS)
            if job.get("status") != "completed":
                raise DailyError("SCANNER_JOB_FAILED_OR_CANCELLED")
            raw = job.get("result") or {}
            capture = raw.get("prospective_capture") if isinstance(raw, dict) else None
            if not isinstance(capture, dict) or capture.get("status") not in ("COMPLETE", "DUPLICATE"):
                raise DailyError("FROZEN_CAPTURE_NOT_COMPLETE")
            # The source date must never be silently clipped or rolled back by
            # Scanner, even if a provider returned old data in mid-run.
            if raw.get("requested_as_of") != signal_date.isoformat():
                raise DailyError("SCANNER_SOURCE_DATE_CHANGED")
            capture_id = capture.get("canonical_capture_id") or capture.get("capture_id")
            if not capture_id:
                raise DailyError("FROZEN_CAPTURE_ID_MISSING")

            persisted_proof = _verify_persisted_capture(
                sim, source_job_id=job_id, capture=capture,
                signal_date=signal_date, market_scope=scope,
            )
            observed_finished_at = _now()
            observations = observe_outcomes(sim, market, as_of=today)
            outcome = _report(
                "SCANNER_CAPTURED_AND_OUTCOME_CHECKED",
                local_date=today.isoformat(),
                source_data_date=signal_date.isoformat(),
                scanner_started_at=started_at,
                scanner_finished_at=observed_finished_at.isoformat(),
                completed_before_open=observed_finished_at.astimezone(KST).time() < time(9, 0),
                premarket_execution_is_not_independent_timestamp_attestation=True,
                scanner_job_id=job_id, capture_id=capture_id,
                capture_status=capture["status"],
                captured_candidate_count=capture.get("returned_candidate_count"),
                **persisted_proof,
                outcome_status=observations["status"],
                outcome_windows=observations.get("windows"),
                historical_evaluation_is_descriptive_only=True,
            )
            _write_result(log, outcome)
            return outcome
    except (DailyError, OSError, subprocess.SubprocessError, TimeoutError) as exc:
        reason = exc.code if isinstance(exc, DailyError) else "LOCAL_OPERATION_UNAVAILABLE"
        error = _report(
            "HOLD_MANUAL_REVIEW",
            local_date=today.isoformat(),
            error_code=reason,
            note="자동 재시도 전에 Scanner job과 Frozen Capture 상태 확인 필요",
        )
        _write_result(log, error)
        return error
    finally:
        lock.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="StockScope S17 optional daily prospective collector")
    parser.add_argument("--scope", choices=("KOSPI", "KOSDAQ", "ALL"), default="KOSPI")
    parser.add_argument("--candidate-limit", type=int, default=5)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    if args.dry_run:
        day, reason = _accepted_clock(_now())
        result = _report("DRY_RUN_NO_SIDE_EFFECTS", local_date=day.isoformat(),
                         eligibility=reason or "PREMARKET_WINDOW_OK",
                         server_started=False)
    else:
        try:
            result = run_once(scope=args.scope, candidate_limit=args.candidate_limit)
        except DailyError as exc:
            result = _report("HOLD_MANUAL_REVIEW", error_code=exc.code)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] in (
        "SCANNER_CAPTURED_AND_OUTCOME_CHECKED",
        "SKIPPED_WEEKEND", "SKIPPED_OUTSIDE_PREMARKET_WINDOW",
        "SKIPPED_NO_FRESH_CONFIRMED_EOD", "SKIPPED_ALREADY_CAPTURED_OR_PENDING",
        "DRY_RUN_NO_SIDE_EFFECTS",
    ) else 2


if __name__ == "__main__":
    raise SystemExit(main())
