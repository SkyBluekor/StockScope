"""LIVE-04: one local-only, authored-synthetic, manually triggered Mock review.

No operational Scanner capture, account keys, market stores or real provider
can enter this path. It deliberately uses the existing V4 reviewer and catalog,
but replaces the provider with the already existing FakeTypeSafeJevProvider.

This dev demo is disabled by default, opt-in, single-shot and fail-closed.
No implicit retry/rebilling on process restart. The persistent store is under
the operating system's temp directory, never backend/runtime or STOCKSCOPE_SIM_DB.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from app.core.config import PROJECT_ROOT
from app.jev.review_models import JEV_USER_FEATURE_ACTIVE
from app.jev.review_service import JevManualReviewService
# The original synthetic fixture imports developer-only tools.data migrators.
# Never import it at application startup; load only after explicit local opt-in.
FIXTURE_ID = "JEV-LIVE-01-AUTHORED-SYNTHETIC"

def _prepare_synthetic_service(*args, **kwargs):
    import sys
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))
    from app.jev.synthetic_live_01 import prepare_synthetic_service
    return prepare_synthetic_service(*args, **kwargs)

from app.jev.typesafe_catalog import TypeSafeJevCatalog
from app.jev.typesafe_provider import FakeTypeSafeJevProvider
from app.jev.typesafe_questions_v4 import STRATEGY_RELATION_CONFLICT

FLAG = "STOCKSCOPE_JEV04_SYNTHETIC_DEMO"
VERSION = "JEV_LIVE04_SYNTHETIC_MOCK_V1"
_MUTEX = threading.RLock()
_ACTIVE: set[str] = set()
_SYNTHETIC_EVIDENCE = {
    "provider_policy_checked_at": "MOCK_ONLY",
    "retention_status": "MOCK_ONLY",
    "model_discovery_ref": "MOCK_ONLY",
    "model_discovery_hash": "MOCK_ONLY",
}


def demo_enabled(client_host: str | None, request_host: str | None) -> bool:
    return (
        os.environ.get(FLAG) == "1"
        and client_host in {"127.0.0.1", "::1", "testclient"}
        and request_host in {"127.0.0.1", "::1", "testserver"}
    )


def _root() -> Path:
    # Controlled by the server, not by a client request or arbitrary env path.
    namespace = hashlib.sha256(str(PROJECT_ROOT.resolve()).encode()).hexdigest()[:12]
    return Path(tempfile.gettempdir()) / f"stockscope-jev04-synthetic-mock-{namespace}"


def _session_path() -> Path:
    return _root() / "session.json"


def _read_session() -> dict | None:
    path = _session_path()
    if not path.exists():
        return None
    content = json.loads(path.read_text(encoding="utf-8"))
    if (content.get("version") != VERSION or content.get("fixture") != FIXTURE_ID
        or content.get("synthetic_only") is not True):
        raise ValueError("JEV04_DEMO_SESSION_INTEGRITY_FAILED")
    return content


def _save_session(session: dict) -> None:
    path = _session_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    pending = path.with_suffix(".tmp")
    pending.write_text(json.dumps(session, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    pending.replace(path)


def _public(session: dict | None) -> dict:
    if session is None:
        return {
            "version": VERSION, "enabled": True, "synthetic_only": True,
            "status": "NOT_REQUESTED", "fixture": FIXTURE_ID,
            "mock_provider_requests": 0, "actual_provider_calls": 0,
        }
    return {
        "version": VERSION, "enabled": True, "synthetic_only": True,
        "fixture": FIXTURE_ID,
        "status": session["status"], "job_id": session["job_id"],
        "capture_id": session["capture_id"], "sample_index": session["sample_index"],
        "snapshot_hash": session["snapshot_hash"],
        "result": session.get("result"),
        "mock_provider_requests": session.get("mock_provider_requests", 0),
        "actual_provider_calls": 0,
    }


def status() -> dict:
    with _MUTEX:
        session = _read_session()
        if session is not None and session["status"] in {"QUEUED", "RUNNING"}:
            if session["job_id"] not in _ACTIVE:
                # Server restart: never silently retry a potentially begun job.
                session["status"] = "INTERRUPTED"
                session["result"] = {"failure_code": "PROCESS_RESTARTED_NO_RETRY"}
                _save_session(session)
                TypeSafeJevCatalog(_root() / "synthetic.db").mark_pending_interrupted()
        return _public(session)


def start() -> dict:
    with _MUTEX:
        existing = _read_session()
        if existing is not None:
            result = status()
            result["reused"] = True
            return result

        root = _root()
        # Atomic one-shot claim across processes. Never create a second fixture
        # if previous initialization/crash left an ambiguous partial database.
        root.mkdir(parents=True, exist_ok=True)
        try:
            with (root / "one-shot.claim").open("x", encoding="utf-8") as f:
                f.write(VERSION)
        except FileExistsError as exc:
            raise ValueError("JEV04_DEMO_ALREADY_CLAIMED_OR_INTERRUPTED") from exc

        _service, preview = _prepare_synthetic_service(
            root / "synthetic.db",
            model_requested="jev-latest",
            expected_model_returned="jev-mock-returned",
            evidence=_SYNTHETIC_EVIDENCE,
            budget_usd=1.0,
            reservation_usd=0.10,
        )
        session = {
            "version": VERSION,
            "fixture": FIXTURE_ID,
            "synthetic_only": True,
            "job_id": str(uuid4()),
            "capture_id": preview["capture_id"],
            "sample_index": preview["sample_index"],
            "snapshot_hash": preview["snapshot_hash"],
            "protocol_id": _service.protocol["id"],
            "status": "QUEUED",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "mock_provider_requests": 0,
        }
        _save_session(session)
        _ACTIVE.add(session["job_id"])
        result = _public(session)
        result["reused"] = False
        return result


async def run_mock(job_id: str) -> None:
    """Run once after the HTTP POST response, with Fake provider only."""
    try:
        with _MUTEX:
            session = _read_session()
            if session is None or session["job_id"] != job_id or session["status"] != "QUEUED":
                return
            session["status"] = "RUNNING"
            session["mock_provider_requests"] = 1
            _save_session(session)

        # Yield at least once, so a running job can be observed in real ASGI.
        await asyncio.sleep(0)
        protocol = TypeSafeJevCatalog(_root() / "synthetic.db").get_protocol(
            session["protocol_id"]
        )
        if protocol is None or protocol.get("status") != "FROZEN":
            raise ValueError("JEV04_FROZEN_PROTOCOL_MISSING")
        service = JevManualReviewService(
            _root() / "synthetic.db",
            feature_status=JEV_USER_FEATURE_ACTIVE,
            protocol=protocol,
            provider_override=FakeTypeSafeJevProvider(
                probabilities={STRATEGY_RELATION_CONFLICT: 0.82},
                returned_model="jev-mock-returned",
            ),
        )
        result = await service.request_review(
            capture_id=session["capture_id"],
            sample_index=session["sample_index"],
        )
        review = service.typesafe.get_review(result["review_id"]) if result.get("review_id") else None
        terminal = (
            "VALID" if review is not None and review["status"] == "VALID"
            else "ERROR"
        )
        report = {
            "disposition": review["disposition"] if review else None,
            "model_returned": review["model_returned"] if review else None,
            "model_identity_status": review["model_identity_status"] if review else None,
            "review_id": result.get("review_id"),
            "review_identity": result.get("review_identity"),
            "reason_codes": result.get("reason_codes", []),
            "usage": json.loads(review["usage_json"]) if review and review.get("usage_json") else None,
            "cost_usd": review["cost_usd"] if review else None,
            "cost_unknown": bool(review["cost_unknown"]) if review else True,
            "failure_code": review["failure_code"] if review else result["reason"],
        }
        with _MUTEX:
            latest = _read_session()
            if latest is not None and latest["job_id"] == job_id:
                latest["status"] = terminal
                latest["result"] = report
                _save_session(latest)
    except Exception:
        # Do not leak payloads, keys, filesystem paths or provider responses.
        with _MUTEX:
            latest = _read_session()
            if latest is not None and latest["job_id"] == job_id:
                latest["status"] = "ERROR"
                latest["result"] = {"failure_code": "JEV04_SYNTHETIC_MOCK_EXECUTION_ERROR"}
                _save_session(latest)
    finally:
        with _MUTEX:
            _ACTIVE.discard(job_id)
