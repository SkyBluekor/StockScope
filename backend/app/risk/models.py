from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class RiskPlanStatus(StrEnum):
    READY = "READY"
    CAUTION = "CAUTION"
    HOLD = "HOLD"
    UNAVAILABLE = "UNAVAILABLE"


@dataclass(slots=True)
class RiskPlan:
    strategy: str
    status: RiskPlanStatus
    reference_only: bool
    basis: str
    entry_price: float
    structural_anchor: float | None
    structural_anchor_label: str | None
    invalidation_price: float | None
    stop_zone_low: float | None
    stop_zone_high: float | None
    target1_price: float | None
    target1_basis: str | None
    target2_price: float | None
    target2_basis: str | None
    risk_pct: float | None
    reward1_pct: float | None
    reward2_pct: float | None
    rr1: float | None
    rr2: float | None
    structure_rating: str
    summary: str
    reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    structural_target1_price: float | None = None
    structural_target1_basis: str | None = None
    target1_cap_price: float | None = None
    target1_cap_applied: bool = False
    target1_fallback_used: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "strategy": self.strategy,
            "status": self.status.value,
            "reference_only": self.reference_only,
            "basis": self.basis,
            "entry_price": self.entry_price,
            "structural_anchor": self.structural_anchor,
            "structural_anchor_label": self.structural_anchor_label,
            "invalidation_price": self.invalidation_price,
            "stop_zone_low": self.stop_zone_low,
            "stop_zone_high": self.stop_zone_high,
            "target1_price": self.target1_price,
            "target1_basis": self.target1_basis,
            "target2_price": self.target2_price,
            "target2_basis": self.target2_basis,
            "risk_pct": self.risk_pct,
            "reward1_pct": self.reward1_pct,
            "reward2_pct": self.reward2_pct,
            "rr1": self.rr1,
            "rr2": self.rr2,
            "structure_rating": self.structure_rating,
            "summary": self.summary,
            "reasons": self.reasons,
            "warnings": self.warnings,
            "assumptions": self.assumptions,
            "structural_target1_price": self.structural_target1_price,
            "structural_target1_basis": self.structural_target1_basis,
            "target1_cap_price": self.target1_cap_price,
            "target1_cap_applied": self.target1_cap_applied,
            "target1_fallback_used": self.target1_fallback_used,
        }
