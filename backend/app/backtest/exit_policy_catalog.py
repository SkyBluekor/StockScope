from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ExitPolicySpec:
    id: str
    label: str
    family: str
    activation: str
    exit_basis: str
    atr_multiplier: float | None = None


POLICY_TARGET1_FULL_EXIT = ExitPolicySpec(
    id="TARGET1_FULL_EXIT",
    label="기존 Target1 전량 종료",
    family="BASELINE",
    activation="TARGET1",
    exit_basis="INTRADAY_OHLC",
)
POLICY_ATR_15 = ExitPolicySpec(
    id="ATR_TRAIL_1_5",
    label="Target2 이후 ATR 1.5배 추적",
    family="ATR_TRAIL",
    activation="TARGET2",
    exit_basis="DAILY_CLOSE_PREVIOUS_PROTECTION",
    atr_multiplier=1.5,
)
POLICY_ATR_20 = ExitPolicySpec(
    id="ATR_TRAIL_2_0",
    label="Target2 이후 ATR 2.0배 추적",
    family="ATR_TRAIL",
    activation="TARGET2",
    exit_basis="DAILY_CLOSE_PREVIOUS_PROTECTION",
    atr_multiplier=2.0,
)
POLICY_ATR_25 = ExitPolicySpec(
    id="ATR_TRAIL_2_5",
    label="Target2 이후 ATR 2.5배 추적",
    family="ATR_TRAIL",
    activation="TARGET2",
    exit_basis="DAILY_CLOSE_PREVIOUS_PROTECTION",
    atr_multiplier=2.5,
)
POLICY_MA20 = ExitPolicySpec(
    id="MA20_TRAIL",
    label="Target2 이후 MA20 추적",
    family="MA20",
    activation="TARGET2",
    exit_basis="DAILY_CLOSE_PREVIOUS_PROTECTION",
)
POLICY_SWING_LOW = ExitPolicySpec(
    id="CONFIRMED_SWING_LOW_TRAIL",
    label="Target2 이후 최근 확정 Swing Low 추적",
    family="SWING_LOW",
    activation="TARGET2",
    exit_basis="DAILY_CLOSE_PREVIOUS_PROTECTION",
)

RESEARCH_POLICIES: tuple[ExitPolicySpec, ...] = (
    POLICY_TARGET1_FULL_EXIT,
    POLICY_ATR_15,
    POLICY_ATR_20,
    POLICY_ATR_25,
    POLICY_MA20,
    POLICY_SWING_LOW,
)

POLICY_BY_ID = {policy.id: policy for policy in RESEARCH_POLICIES}
PROFIT_PROTECTION_POLICY_IDS = frozenset(
    policy.id for policy in RESEARCH_POLICIES if policy.id != POLICY_TARGET1_FULL_EXIT.id
)


def policy_by_id(policy_id: str | None) -> ExitPolicySpec:
    return POLICY_BY_ID.get(str(policy_id or ""), POLICY_TARGET1_FULL_EXIT)
