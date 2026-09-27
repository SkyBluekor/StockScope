from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Literal


WatchRuleKind = Literal["STOP", "TARGET1", "TARGET2"]
WatchDirection = Literal["BELOW_OR_EQUAL", "ABOVE_OR_EQUAL"]
WatchRuleState = Literal[
    "ARMED",
    "PENDING_CONFIRMATION",
    "CONFIRMED",
    "RESOLVED",
    "DISABLED",
]
WatchTransitionEvent = Literal[
    "NONE",
    "CONDITION_ENTERED",
    "CONFIRMED",
    "CONFIRMATION_RESET",
    "RESOLVED",
    "REARMED",
    "COVERAGE_GAP_RESET",
    "OUT_OF_ORDER_IGNORED",
]


@dataclass(frozen=True, slots=True)
class WatchRuleSpec:
    rule_kind: WatchRuleKind
    direction: WatchDirection
    threshold_price: Decimal

    def __post_init__(self) -> None:
        if self.threshold_price <= 0:
            raise ValueError("Watch threshold_price must be positive.")
        if self.rule_kind == "STOP" and self.direction != "BELOW_OR_EQUAL":
            raise ValueError("STOP watch rule must use BELOW_OR_EQUAL.")
        if self.rule_kind in {"TARGET1", "TARGET2"} and self.direction != "ABOVE_OR_EQUAL":
            raise ValueError("TARGET watch rule must use ABOVE_OR_EQUAL.")


@dataclass(frozen=True, slots=True)
class WatchObservation:
    price: Decimal
    observed_at: datetime
    age_seconds: float = 0.0
    coverage_ok: bool = True
    coverage_reason: str | None = None

    def __post_init__(self) -> None:
        if self.price <= 0:
            raise ValueError("Watch observation price must be positive.")
        if self.age_seconds < 0:
            raise ValueError("Watch observation age_seconds cannot be negative.")


@dataclass(frozen=True, slots=True)
class WatchRuleRuntimeState:
    state: WatchRuleState = "ARMED"
    confirmation_count: int = 0
    rearm_count: int = 0
    last_observed_at: datetime | None = None
    last_price: Decimal | None = None

    def __post_init__(self) -> None:
        if self.confirmation_count < 0 or self.rearm_count < 0:
            raise ValueError("Watch counters cannot be negative.")


@dataclass(frozen=True, slots=True)
class WatchTransition:
    previous: WatchRuleRuntimeState
    current: WatchRuleRuntimeState
    event: WatchTransitionEvent
    accepted: bool
    condition_matched: bool | None
    coverage_reason: str | None = None
