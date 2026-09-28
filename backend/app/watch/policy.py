from __future__ import annotations

from dataclasses import dataclass


WATCH_POLICY_CONTRACT_VERSION = "VN_P4_S1_WATCH_POLICY_CONTRACT_V1"
WATCH_PRODUCTION_POLICY_VERSION = "VN_P4_S1_PRODUCTION_UNAPPROVED"


class WatchPolicyError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class WatchPolicy:
    policy_version: str
    enabled: bool
    confirmation_observations: int | None
    rearm_observations: int | None
    rearm_distance_bps: int | None
    max_quote_age_seconds: float | None
    blocked_reason: str | None = None
    contract_version: str = WATCH_POLICY_CONTRACT_VERSION

    def __post_init__(self) -> None:
        if not self.policy_version.strip():
            raise WatchPolicyError("Watch policy_version is required.")
        if self.contract_version != WATCH_POLICY_CONTRACT_VERSION:
            raise WatchPolicyError("Unsupported Watch policy contract version.")

        if not self.enabled:
            if not (self.blocked_reason or "").strip():
                raise WatchPolicyError(
                    "Disabled Watch policy must explain why activation is blocked."
                )
            return

        if self.blocked_reason is not None:
            raise WatchPolicyError(
                "Enabled Watch policy cannot carry blocked_reason."
            )
        if self.confirmation_observations is None or self.confirmation_observations < 1:
            raise WatchPolicyError(
                "Enabled Watch policy requires confirmation_observations >= 1."
            )
        if self.rearm_observations is None or self.rearm_observations < 1:
            raise WatchPolicyError(
                "Enabled Watch policy requires rearm_observations >= 1."
            )
        if self.rearm_distance_bps is None or self.rearm_distance_bps <= 0:
            raise WatchPolicyError(
                "Enabled Watch policy requires positive rearm_distance_bps."
            )
        if self.max_quote_age_seconds is None or self.max_quote_age_seconds <= 0:
            raise WatchPolicyError(
                "Enabled Watch policy requires positive max_quote_age_seconds."
            )

    def require_enabled(self) -> "WatchPolicy":
        if not self.enabled:
            raise WatchPolicyError(
                f"Watch policy is not activatable: {self.blocked_reason}"
            )
        return self


def production_watch_policy() -> WatchPolicy:
    """
    Product-safe default for VN-P4-S1.

    Architecture intentionally leaves confirmation/rearm/freshness numbers unresolved.
    Do not invent operating thresholds merely to turn Watch on.
    """

    return WatchPolicy(
        policy_version=WATCH_PRODUCTION_POLICY_VERSION,
        enabled=False,
        confirmation_observations=None,
        rearm_observations=None,
        rearm_distance_bps=None,
        max_quote_age_seconds=None,
        blocked_reason="OPERATING_THRESHOLDS_UNAPPROVED",
    )
