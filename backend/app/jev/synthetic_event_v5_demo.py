"""P6-C local-only V5 authored-synthetic integration demo, persisted once.

Never accepts capture IDs, tickers, event content, or model IDs from requests.
No operational database and no network-capable provider is imported here.
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

from app.core.config import PROJECT_ROOT
from app.jev.event_v5 import (
    TEST_MODEL_ID, QUESTION_ID, authored_synthetic_fixture,
    review_synthetic_once,
)
from app.jev.typesafe_provider import FakeTypeSafeJevProvider

FLAG = "STOCKSCOPE_JEV_V5_SYNTHETIC_DEMO"
VERSION = "JEV_P6C_SYNTHETIC_FAKE_REVIEW_V1"
_MUTEX = threading.RLock()
_ACTIVE = False


def demo_enabled(client_host: str | None, request_host: str | None) -> bool:
    return (
        os.environ.get(FLAG) == "1"
        and client_host in {"127.0.0.1", "::1", "testclient"}
        and request_host in {"127.0.0.1", "::1", "testserver"}
    )


def _root() -> Path:
    namespace = hashlib.sha256(
        str(PROJECT_ROOT.resolve()).encode("utf-8"),
    ).hexdigest()[:12]
    return Path(tempfile.gettempdir()) / f"stockscope-jev-v5-synthetic-{namespace}"


def _session_path() -> Path:
    return _root() / "v5-session.json"


def _load() -> dict | None:
    path = _session_path()
    if not path.is_file():
        return None
    saved = json.loads(path.read_text(encoding="utf-8"))
    if (
        not isinstance(saved, dict) or saved.get("version") != VERSION
        or saved.get("synthetic_only") is not True
        or saved.get("fixture_id") != authored_synthetic_fixture()["fixture_id"]
    ):
        raise ValueError("P6C_SESSION_INVALID")
    return saved


def _save(saved: dict) -> None:
    path = _session_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(
        json.dumps(saved, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )
    tmp.replace(path)


def _public(saved: dict | None) -> dict:
    if saved is None:
        return {
            "version": VERSION, "enabled": True, "synthetic_only": True,
            "status": "NOT_REQUESTED", "result": None,
            "mock_provider_calls": 0, "actual_provider_calls": 0,
        }
    return {
        "version": VERSION, "enabled": True, "synthetic_only": True,
        "status": saved["status"], "fixture_id": saved["fixture_id"],
        "result": saved.get("result"),
        "mock_provider_calls": saved.get("mock_provider_calls", 0),
        "actual_provider_calls": 0,
        "reused": True,
    }


def status() -> dict:
    global _ACTIVE
    with _MUTEX:
        saved = _load()
        if saved is not None and saved["status"] in {"QUEUED", "RUNNING"} and not _ACTIVE:
            # After process restart, never auto-run an earlier job.
            saved["status"] = "INTERRUPTED"
            saved["result"] = {"failure_code": "P6C_PROCESS_RESTART_NO_RETRY"}
            _save(saved)
        return _public(saved)


def start() -> dict:
    global _ACTIVE
    with _MUTEX:
        existing = _load()
        if existing is not None:
            return {**status(), "reused": True}
        root = _root()
        root.mkdir(parents=True, exist_ok=True)
        try:
            with (root / "one-shot.claim").open("x", encoding="utf-8") as claim:
                claim.write(VERSION)
        except FileExistsError as exc:
            raise ValueError("P6C_DEMO_PREVIOUSLY_CLAIMED") from exc
        saved = {
            "version": VERSION, "fixture_id": authored_synthetic_fixture()["fixture_id"],
            "synthetic_only": True, "status": "QUEUED",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "mock_provider_calls": 0,
        }
        _save(saved)
        _ACTIVE = True
        return {**_public(saved), "reused": False}


async def run_mock() -> None:
    global _ACTIVE
    try:
        with _MUTEX:
            saved = _load()
            if saved is None or saved["status"] != "QUEUED" or not _ACTIVE:
                return
            saved["status"] = "RUNNING"
            saved["mock_provider_calls"] = 1
            _save(saved)

        await asyncio.sleep(0)
        # A fixed mock result is a plumbing test, not independent event truth.
        provider = FakeTypeSafeJevProvider(
            probabilities={QUESTION_ID: 0.81},
            returned_model=TEST_MODEL_ID,
        )
        result = await review_synthetic_once(
            authored_synthetic_fixture(), provider,
        )
        with _MUTEX:
            latest = _load()
            if latest is not None and latest["status"] == "RUNNING":
                latest["result"] = result
                latest["status"] = result["status"]
                _save(latest)
    except Exception:
        with _MUTEX:
            latest = _load()
            if latest is not None and latest["status"] == "RUNNING":
                latest["status"] = "ERROR"
                latest["result"] = {"failure_code": "P6C_SYNTHETIC_DEMO_ERROR"}
                _save(latest)
    finally:
        with _MUTEX:
            _ACTIVE = False
