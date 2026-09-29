from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any

from app.macro.identity import content_hash


MACRO_CALIBRATION_CONTRACT_VERSION = "VN_NEXT6B_S1_MACRO_CALIBRATION_V1"


class CalibrationStatus(str, Enum):
    DRAFT = "DRAFT"
    APPROVED_RESEARCH = "APPROVED_RESEARCH"
    REJECTED = "REJECTED"
    DISABLED = "DISABLED"


@dataclass(frozen=True, slots=True)
class MacroShockCalibration:
    calibration_id: str
    version: str
    shock_type: str
    feature_contract_version: str
    training_scope: str | None
    holdout_scope: str | None
    lookback: int | None
    minimum_sample: int | None
    method: str | None
    threshold: str | None
    status: CalibrationStatus = CalibrationStatus.DISABLED
    contract_version: str = MACRO_CALIBRATION_CONTRACT_VERSION

    def __post_init__(self) -> None:
        status = (
            self.status
            if isinstance(self.status, CalibrationStatus)
            else CalibrationStatus(str(self.status))
        )
        object.__setattr__(self, "status", status)
        if status is CalibrationStatus.APPROVED_RESEARCH:
            required = (
                self.training_scope,
                self.holdout_scope,
                self.lookback,
                self.minimum_sample,
                self.method,
                self.threshold,
            )
            if any(value in (None, "") for value in required):
                raise ValueError(
                    "Approved Macro calibration requires fixed research fields."
                )

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["status"] = self.status.value
        return payload

    @property
    def calibration_hash(self) -> str:
        return content_hash(self.to_dict())


def uncalibrated_rate_spike_calibration() -> MacroShockCalibration:
    return MacroShockCalibration(
        calibration_id="RATE_SPIKE_UNCALIBRATED",
        version="UNSET",
        shock_type="RATE_SPIKE",
        feature_contract_version="VN_NEXT6B_S1_MACRO_FEATURE_V1",
        training_scope=None,
        holdout_scope=None,
        lookback=None,
        minimum_sample=None,
        method=None,
        threshold=None,
        status=CalibrationStatus.DISABLED,
    )
