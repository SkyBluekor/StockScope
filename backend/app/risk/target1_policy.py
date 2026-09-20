from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Iterable

TARGET1_CAP_R = 1.5
TARGET1_CAP_BASIS = "1.5R 현실성 상한"
TARGET1_FALLBACK_BASIS = "1.5R 손익 구조 참고"


@dataclass(frozen=True, slots=True)
class Target1Decision:
    """Resolved Production Target1 while retaining the original structural objective.

    The structural target remains explanatory context. Production Target1 is capped at
    1.5R only when the nearest valid structural target is farther away than that cap.
    """

    target1_price: float
    target1_basis: str
    structural_target1_price: float | None
    structural_target1_basis: str | None
    structural_target1_kind: str | None
    cap_price: float
    cap_applied: bool
    fallback_used: bool

    @property
    def legacy_target1_price(self) -> float:
        """Target1 used by the legacy structural policy.

        Target2 remains based on this value in B.2.3.2d so the Target1-only policy
        correction does not silently change the existing Target2 production formula.
        """

        return self.structural_target1_price if self.structural_target1_price is not None else self.cap_price


def select_target1(
    *,
    entry: float,
    risk_amount: float,
    structural_candidates: Iterable[tuple[float, str, str]],
) -> Target1Decision:
    """Return the Production Target1 decision for the 1.5R-cap policy.

    ``structural_candidates`` contains ``(price, display_basis, kind)`` tuples. Invalid
    or non-upside candidates are ignored. Sorting is stable, preserving the existing
    resistance-before-high20 tie behavior when both prices are equal.
    """

    entry_f = float(entry)
    risk_f = float(risk_amount)
    if not isfinite(entry_f) or not isfinite(risk_f) or entry_f <= 0 or risk_f <= 0:
        raise ValueError("Target1 policy requires positive finite entry and risk_amount")

    cap_price = entry_f + risk_f * TARGET1_CAP_R
    valid: list[tuple[float, str, str]] = []
    for raw_price, label, kind in structural_candidates:
        try:
            price = float(raw_price)
        except (TypeError, ValueError):
            continue
        if not isfinite(price) or price <= entry_f:
            continue
        valid.append((price, str(label), str(kind)))
    valid.sort(key=lambda item: item[0])

    if not valid:
        return Target1Decision(
            target1_price=cap_price,
            target1_basis=TARGET1_FALLBACK_BASIS,
            structural_target1_price=None,
            structural_target1_basis=None,
            structural_target1_kind=None,
            cap_price=cap_price,
            cap_applied=False,
            fallback_used=True,
        )

    structural_price, structural_basis, structural_kind = valid[0]
    tolerance = max(0.02, abs(cap_price) * 1e-9)
    cap_applied = structural_price > cap_price + tolerance
    if cap_applied:
        target1_price = cap_price
        target1_basis = TARGET1_CAP_BASIS
    else:
        target1_price = structural_price
        target1_basis = structural_basis

    return Target1Decision(
        target1_price=target1_price,
        target1_basis=target1_basis,
        structural_target1_price=structural_price,
        structural_target1_basis=structural_basis,
        structural_target1_kind=structural_kind,
        cap_price=cap_price,
        cap_applied=cap_applied,
        fallback_used=False,
    )
