from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any

from app.macro.calibration import MacroShockCalibration
from app.macro.identity import content_hash


MACRO_SHOCK_CONTRACT_VERSION = "VN_NEXT6B_S1_MACRO_SHOCK_V1"
MACRO_EPISODE_CONTRACT_VERSION = "VN_NEXT6B_S1_MACRO_EPISODE_V1"


class ShockType(str, Enum):
    RATE_SPIKE = "RATE_SPIKE"
    VOLATILITY_SHOCK = "VOLATILITY_SHOCK"
    FX_SHOCK = "FX_SHOCK"
    GLOBAL_EQUITY_SELL_OFF = "GLOBAL_EQUITY_SELL_OFF"
    SECTOR_SPECIFIC_SHOCK = "SECTOR_SPECIFIC_SHOCK"


class ShockState(str, Enum):
    UNCALIBRATED = "UNCALIBRATED"
    NOT_PREPARED = "NOT_PREPARED"
    UNKNOWN = "UNKNOWN"
    NORMAL = "NORMAL"
    DETECTED = "DETECTED"


@dataclass(frozen=True, slots=True)
class ShockComponentAssessment:
    shock_type: ShockType
    state: ShockState
    calibration_id: str | None
    calibration_version: str | None
    raw_feature_ids: tuple[str, ...]
    reason: str | None = None
    production_decision_approved: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "shock_type": self.shock_type.value,
            "state": self.state.value,
            "calibration_id": self.calibration_id,
            "calibration_version": self.calibration_version,
            "raw_feature_ids": list(self.raw_feature_ids),
            "reason": self.reason,
            "production_decision_approved": self.production_decision_approved,
        }


@dataclass(frozen=True, slots=True)
class ShockEpisodeContract:
    enabled: bool
    episode_id: str | None
    shock_type: str | None
    started_at: str | None
    last_updated_at: str | None
    ended_at: str | None
    member_assessment_ids: tuple[str, ...]
    calibration_version: str | None
    contract_version: str = MACRO_EPISODE_CONTRACT_VERSION

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["member_assessment_ids"] = list(self.member_assessment_ids)
        return payload


def build_uncalibrated_shock_assessment(
    *,
    feature_set: dict[str, Any],
    rate_calibration: MacroShockCalibration,
) -> dict[str, Any]:
    rate_feature_rows = [
        feature
        for feature in feature_set.get("features", [])
        if str(feature.get("feature_id", "")).startswith(("rate_level_", "delta_bp_"))
    ]
    rate_features = tuple(feature["feature_id"] for feature in rate_feature_rows)
    rate_feature_available = any(
        feature.get("status") == "AVAILABLE"
        for feature in rate_feature_rows
    )
    rate_state = (
        ShockState.UNCALIBRATED
        if rate_feature_available
        else ShockState.UNKNOWN
    )
    rate_reason = (
        "CALIBRATION_NOT_DEFINED"
        if rate_feature_available
        else "RATE_FEATURES_UNAVAILABLE"
    )
    components = [
        ShockComponentAssessment(
            shock_type=ShockType.RATE_SPIKE,
            state=rate_state,
            calibration_id=rate_calibration.calibration_id,
            calibration_version=rate_calibration.version,
            raw_feature_ids=rate_features,
            reason=rate_reason,
        ),
        ShockComponentAssessment(
            shock_type=ShockType.VOLATILITY_SHOCK,
            state=ShockState.NOT_PREPARED,
            calibration_id=None,
            calibration_version=None,
            raw_feature_ids=(),
            reason="VIX_SERIES_NOT_PREPARED",
        ),
        ShockComponentAssessment(
            shock_type=ShockType.FX_SHOCK,
            state=ShockState.NOT_PREPARED,
            calibration_id=None,
            calibration_version=None,
            raw_feature_ids=(),
            reason="FX_SERIES_NOT_PREPARED",
        ),
        ShockComponentAssessment(
            shock_type=ShockType.GLOBAL_EQUITY_SELL_OFF,
            state=ShockState.NOT_PREPARED,
            calibration_id=None,
            calibration_version=None,
            raw_feature_ids=(),
            reason="GLOBAL_EQUITY_SERIES_NOT_PREPARED",
        ),
    ]
    episode = ShockEpisodeContract(
        enabled=False,
        episode_id=None,
        shock_type=None,
        started_at=None,
        last_updated_at=None,
        ended_at=None,
        member_assessment_ids=(),
        calibration_version=None,
    )
    payload = {
        "contract_version": MACRO_SHOCK_CONTRACT_VERSION,
        "components": [component.to_dict() for component in components],
        "composite": {
            "state": (
                ShockState.UNCALIBRATED.value
                if rate_feature_available
                else ShockState.UNKNOWN.value
            ),
            "component_types": [component.shock_type.value for component in components],
            "weighted_severity": None,
            "reason": (
                "NO_APPROVED_CALIBRATION"
                if rate_feature_available
                else "FEATURES_UNAVAILABLE"
            ),
        },
        "episode": episode.to_dict(),
        "production_decision_approved": False,
    }
    return {**payload, "shock_assessment_hash": content_hash(payload)}
