from __future__ import annotations

from decimal import Decimal

from .models import (
    WatchObservation,
    WatchRuleRuntimeState,
    WatchRuleSpec,
    WatchTransition,
)
from .policy import WatchPolicy


_BPS = Decimal("10000")


def _trigger_matches(rule: WatchRuleSpec, price: Decimal) -> bool:
    if rule.direction == "BELOW_OR_EQUAL":
        return price <= rule.threshold_price
    return price >= rule.threshold_price


def _rearm_matches(
    rule: WatchRuleSpec,
    price: Decimal,
    *,
    rearm_distance_bps: int,
) -> bool:
    distance = rule.threshold_price * Decimal(rearm_distance_bps) / _BPS
    if rule.direction == "BELOW_OR_EQUAL":
        return price >= rule.threshold_price + distance
    return price <= rule.threshold_price - distance


def advance_watch_rule(
    rule: WatchRuleSpec,
    runtime: WatchRuleRuntimeState,
    observation: WatchObservation,
    policy: WatchPolicy,
) -> WatchTransition:
    """
    Advance one Watch rule using an explicit policy.

    This function is deliberately pure: it cannot change Holdings positions,
    management plans, or create trades. Coverage loss resets only an unfinished
    confirmation. A previously confirmed episode remains confirmed until a new
    valid observation proves the trigger condition has cleared.
    """

    policy.require_enabled()
    confirmation_required = int(policy.confirmation_observations or 0)
    rearm_required = int(policy.rearm_observations or 0)
    rearm_distance_bps = int(policy.rearm_distance_bps or 0)
    max_age = float(policy.max_quote_age_seconds or 0)

    if runtime.state == "DISABLED":
        return WatchTransition(
            previous=runtime,
            current=runtime,
            event="NONE",
            accepted=False,
            condition_matched=None,
        )

    if (
        runtime.last_observed_at is not None
        and observation.observed_at < runtime.last_observed_at
    ):
        return WatchTransition(
            previous=runtime,
            current=runtime,
            event="OUT_OF_ORDER_IGNORED",
            accepted=False,
            condition_matched=None,
        )

    coverage_reason: str | None = None
    if not observation.coverage_ok:
        coverage_reason = observation.coverage_reason or "COVERAGE_UNAVAILABLE"
    elif observation.age_seconds > max_age:
        coverage_reason = "STALE_QUOTE"

    if coverage_reason is not None:
        if runtime.state == "PENDING_CONFIRMATION":
            current = WatchRuleRuntimeState(
                state="ARMED",
                confirmation_count=0,
                rearm_count=0,
                last_observed_at=runtime.last_observed_at,
                last_price=runtime.last_price,
            )
        elif runtime.state == "RESOLVED" and runtime.rearm_count:
            current = WatchRuleRuntimeState(
                state="RESOLVED",
                confirmation_count=0,
                rearm_count=0,
                last_observed_at=runtime.last_observed_at,
                last_price=runtime.last_price,
            )
        else:
            current = runtime
        return WatchTransition(
            previous=runtime,
            current=current,
            event="COVERAGE_GAP_RESET",
            accepted=False,
            condition_matched=None,
            coverage_reason=coverage_reason,
        )

    matched = _trigger_matches(rule, observation.price)

    def state(
        value: str,
        *,
        confirmation_count: int = 0,
        rearm_count: int = 0,
    ) -> WatchRuleRuntimeState:
        return WatchRuleRuntimeState(
            state=value,  # type: ignore[arg-type]
            confirmation_count=confirmation_count,
            rearm_count=rearm_count,
            last_observed_at=observation.observed_at,
            last_price=observation.price,
        )

    if runtime.state == "ARMED":
        if not matched:
            current = state("ARMED")
            event = "NONE"
        elif confirmation_required == 1:
            current = state("CONFIRMED")
            event = "CONFIRMED"
        else:
            current = state("PENDING_CONFIRMATION", confirmation_count=1)
            event = "CONDITION_ENTERED"

    elif runtime.state == "PENDING_CONFIRMATION":
        if not matched:
            current = state("ARMED")
            event = "CONFIRMATION_RESET"
        else:
            count = runtime.confirmation_count + 1
            if count >= confirmation_required:
                current = state("CONFIRMED")
                event = "CONFIRMED"
            else:
                current = state(
                    "PENDING_CONFIRMATION",
                    confirmation_count=count,
                )
                event = "NONE"

    elif runtime.state == "CONFIRMED":
        if matched:
            current = state("CONFIRMED")
            event = "NONE"
        else:
            # Resolution and re-arm are intentionally separate observations.
            # This prevents one boundary-crossing tick from immediately opening
            # a new episode even when the configured rearm count is one.
            current = state("RESOLVED")
            event = "RESOLVED"

    elif runtime.state == "RESOLVED":
        rearmed = _rearm_matches(
            rule,
            observation.price,
            rearm_distance_bps=rearm_distance_bps,
        )
        if not rearmed:
            current = state("RESOLVED")
            event = "NONE"
        else:
            count = runtime.rearm_count + 1
            if count >= rearm_required:
                current = state("ARMED")
                event = "REARMED"
            else:
                current = state("RESOLVED", rearm_count=count)
                event = "NONE"

    else:
        raise ValueError(f"Unsupported Watch rule state: {runtime.state}")

    return WatchTransition(
        previous=runtime,
        current=current,
        event=event,  # type: ignore[arg-type]
        accepted=True,
        condition_matched=matched,
    )
