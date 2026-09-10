from __future__ import annotations

import asyncio
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from time import monotonic
from typing import Any
from uuid import uuid4




class BacktestJobCancelled(Exception):
    """Internal signal used to stop a worker/thread after the user cancels a job."""

@dataclass
class BacktestJob:
    job_id: str
    status: str = "queued"
    stage: str = "queued"
    message: str = "대기 중"
    current: int = 0
    total: int = 1
    details: dict[str, Any] = field(default_factory=dict)
    result: dict[str, Any] | None = None
    error: str | None = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    started_monotonic: float = field(default_factory=monotonic)
    task: asyncio.Task[Any] | None = field(default=None, repr=False)

    def public(self) -> dict[str, Any]:
        total = max(int(self.total), 1)
        percent = 100.0 if self.status == "completed" else min(100.0, max(0.0, self.current / total * 100.0))
        return {
            "job_id": self.job_id,
            "status": self.status,
            "stage": self.stage,
            "progress": {
                "current": self.current,
                "total": self.total,
                "percent": round(percent, 1),
                "message": self.message,
                "details": dict(self.details),
            },
            "result": self.result if self.status == "completed" else None,
            "error": self.error,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "elapsed_seconds": round(max(0.0, monotonic() - self.started_monotonic), 1),
        }


class BacktestJobManager:
    MAX_JOBS = 30

    def __init__(self) -> None:
        self._jobs: dict[str, BacktestJob] = {}
        self._lock = threading.RLock()

    def create(self) -> BacktestJob:
        with self._lock:
            self._cleanup_locked()
            job = BacktestJob(job_id=uuid4().hex)
            self._jobs[job.job_id] = job
            return job

    def get(self, job_id: str) -> BacktestJob | None:
        with self._lock:
            return self._jobs.get(job_id)

    def is_cancelled(self, job_id: str) -> bool:
        with self._lock:
            job = self._jobs.get(job_id)
            return job is None or job.status == "cancelled"

    def attach_task(self, job_id: str, task: asyncio.Task[Any]) -> None:
        with self._lock:
            job = self._jobs[job_id]
            job.task = task

    def update_progress(self, job_id: str, payload: dict[str, Any]) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None or job.status in {"completed", "failed", "cancelled"}:
                return
            job.status = "running"
            job.stage = str(payload.get("stage") or job.stage)
            job.message = str(payload.get("message") or job.message)
            job.current = max(0, int(payload.get("current", job.current)))
            job.total = max(1, int(payload.get("total", job.total)))
            details = payload.get("details")
            if isinstance(details, dict):
                job.details = dict(details)
            job.updated_at = datetime.now(timezone.utc).isoformat()

    def complete(self, job_id: str, result: dict[str, Any]) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            job.status = "completed"
            job.stage = "completed"
            job.message = "백테스트 완료"
            job.current = 1
            job.total = 1
            job.result = result
            job.error = None
            job.updated_at = datetime.now(timezone.utc).isoformat()

    def fail(self, job_id: str, error: str) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            job.status = "failed"
            job.stage = "failed"
            job.message = "백테스트 실패"
            job.error = error
            job.updated_at = datetime.now(timezone.utc).isoformat()

    def mark_cancelled(self, job_id: str) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            job.status = "cancelled"
            job.stage = "cancelled"
            job.message = "사용자가 백테스트를 취소했습니다."
            job.error = None
            job.updated_at = datetime.now(timezone.utc).isoformat()

    def cancel(self, job_id: str) -> bool:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return False
            if job.status in {"completed", "failed", "cancelled"}:
                return True
            task = job.task
            job.status = "cancelled"
            job.stage = "cancelled"
            job.message = "취소 요청 처리 중"
            job.updated_at = datetime.now(timezone.utc).isoformat()
        if task is not None and not task.done():
            task.cancel()
        return True

    def _cleanup_locked(self) -> None:
        if len(self._jobs) < self.MAX_JOBS:
            return
        terminal = [
            job for job in self._jobs.values()
            if job.status in {"completed", "failed", "cancelled"}
        ]
        terminal.sort(key=lambda job: job.updated_at)
        remove_count = max(1, len(self._jobs) - self.MAX_JOBS + 1)
        for job in terminal[:remove_count]:
            self._jobs.pop(job.job_id, None)


backtest_jobs = BacktestJobManager()
