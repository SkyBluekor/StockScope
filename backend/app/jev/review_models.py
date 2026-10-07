from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


BASELINE_ONLY = "BASELINE_ONLY"
BASELINE_WITH_JEV = "BASELINE_WITH_JEV"

JEV_USER_FEATURE_DISABLED = "DISABLED_VALIDATION_PENDING"
JEV_USER_FEATURE_ACTIVE = "ACTIVE"

REVIEW_NOT_REQUESTED = "NOT_REQUESTED"
REVIEW_UNAVAILABLE = "UNAVAILABLE"
REVIEW_NOT_READY = "NOT_READY"
REVIEW_QUEUED = "QUEUED"
REVIEW_RUNNING = "RUNNING"
REVIEW_PASS_THROUGH = "PASS_THROUGH"
REVIEW_REQUIRED = "REVIEW_REQUIRED"
REVIEW_SKIPPED = "SKIPPED"
REVIEW_ERROR = "ERROR"

JEV_REVIEW_STATUSES = frozenset(
    {
        REVIEW_NOT_REQUESTED,
        REVIEW_UNAVAILABLE,
        REVIEW_NOT_READY,
        REVIEW_QUEUED,
        REVIEW_RUNNING,
        REVIEW_PASS_THROUGH,
        REVIEW_REQUIRED,
        REVIEW_SKIPPED,
        REVIEW_ERROR,
    }
)


@dataclass(frozen=True, slots=True)
class JevManualReviewResult:
    status: str
    reason: str
    reused: bool
    baseline_reference: dict[str, Any]
    review_id: str | None = None
    review_identity: str | None = None
    execution_mode: str = BASELINE_WITH_JEV
    feature_status: str = JEV_USER_FEATURE_DISABLED
    reason_codes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["reason_codes"] = list(self.reason_codes)
        return payload
