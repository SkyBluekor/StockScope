from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

HORIZON_POLICY_VERSION = "VN_P1_S2_HORIZON_CONTEXT_V1"

LEGACY_UNSPECIFIED = "LEGACY_UNSPECIFIED"
EXPLICIT_HORIZONS = ("SHORT", "MEDIUM", "LONG")

SUPPORT_LEGACY = "LEGACY_UNSPECIFIED"
SUPPORT_PENDING = "EVALUATION_PENDING"
SUPPORT_SUPPORTED = "SUPPORTED"
SUPPORT_UNSUPPORTED = "UNSUPPORTED"


class HorizonPolicyError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True, slots=True)
class HorizonContext:
    intent: str
    policy_version: str | None
    support_status: str
    reason_code: str | None
    review_cycle_trading_days: int | None = None
    time_stop_trading_days: int | None = None

    @property
    def is_legacy(self) -> bool:
        return self.intent == LEGACY_UNSPECIFIED

    @property
    def is_activatable(self) -> bool:
        return self.support_status == SUPPORT_SUPPORTED

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def normalize_horizon_intent(value: str | None) -> str:
    raw = (value or "").strip().upper()
    if not raw or raw == LEGACY_UNSPECIFIED:
        return LEGACY_UNSPECIFIED
    if raw not in EXPLICIT_HORIZONS:
        raise HorizonPolicyError(
            "HORIZON_INTENT_INVALID",
            f"지원하지 않는 Horizon intent입니다: {value}",
        )
    return raw


def resolve_horizon_context(
    intent: str | None,
    *,
    policy_version: str | None = None,
) -> HorizonContext:
    normalized = normalize_horizon_intent(intent)
    if normalized == LEGACY_UNSPECIFIED:
        return HorizonContext(
            intent=LEGACY_UNSPECIFIED,
            policy_version=None,
            support_status=SUPPORT_LEGACY,
            reason_code="HORIZON_NOT_RECORDED",
        )

    version = (policy_version or HORIZON_POLICY_VERSION).strip()
    if version != HORIZON_POLICY_VERSION:
        return HorizonContext(
            intent=normalized,
            policy_version=version,
            support_status=SUPPORT_UNSUPPORTED,
            reason_code="HORIZON_POLICY_VERSION_UNSUPPORTED",
        )

    # VN-P1-S2 deliberately defines the transport/storage contract before
    # approving numeric duration, review-cycle, time-stop, strategy or
    # confirmation rules. Do not invent those values here.
    return HorizonContext(
        intent=normalized,
        policy_version=HORIZON_POLICY_VERSION,
        support_status=SUPPORT_PENDING,
        reason_code="HORIZON_NUMERIC_POLICY_NOT_APPROVED",
    )


def require_horizon_activatable(context: HorizonContext) -> None:
    if context.is_legacy:
        return
    if not context.is_activatable:
        raise HorizonPolicyError(
            "HORIZON_POLICY_NOT_ACTIVE",
            "선택한 투자 기간의 수치 정책이 아직 승인되지 않아 이 판단을 실행할 수 없습니다.",
        )


def horizon_policy_catalog() -> dict[str, Any]:
    return {
        "policy_version": HORIZON_POLICY_VERSION,
        "numeric_policy_approved": False,
        "legacy": resolve_horizon_context(None).to_dict(),
        "options": [
            resolve_horizon_context(intent).to_dict()
            for intent in EXPLICIT_HORIZONS
        ],
        "rules": {
            "tracking_5_10_20_are_observation_windows": True,
            "validation_20d_is_not_horizon_intent": True,
            "legacy_backfill_forbidden": True,
        },
    }
