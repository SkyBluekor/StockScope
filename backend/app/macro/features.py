from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Any

from app.macro.identity import content_hash


MACRO_FEATURE_CONTRACT_VERSION = "VN_NEXT6B_S1_MACRO_FEATURE_V1"
DGS10_FEATURE_WINDOWS = (1, 5, 10)


class MacroFeatureStatus(str, Enum):
    AVAILABLE = "AVAILABLE"
    INSUFFICIENT_HISTORY = "INSUFFICIENT_HISTORY"
    MISSING_REFERENCE = "MISSING_REFERENCE"
    UNAVAILABLE = "UNAVAILABLE"


@dataclass(frozen=True, slots=True)
class MacroFeature:
    feature_id: str
    status: MacroFeatureStatus
    value: str | None
    unit: str
    current_observation_ref: str | None
    baseline_observation_ref: str | None = None
    current_observation_date: str | None = None
    baseline_observation_date: str | None = None
    observation_distance: int | None = None
    calendar_distance_days: int | None = None
    reason: str | None = None
    contract_version: str = MACRO_FEATURE_CONTRACT_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "feature_id": self.feature_id,
            "status": self.status.value,
            "value": self.value,
            "unit": self.unit,
            "current_observation_ref": self.current_observation_ref,
            "baseline_observation_ref": self.baseline_observation_ref,
            "current_observation_date": self.current_observation_date,
            "baseline_observation_date": self.baseline_observation_date,
            "observation_distance": self.observation_distance,
            "calendar_distance_days": self.calendar_distance_days,
            "reason": self.reason,
            "contract_version": self.contract_version,
        }


def _decimal(value: Any) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError("Macro feature input must be numeric.") from exc
    if not result.is_finite():
        raise ValueError("Macro feature input must be finite.")
    return result


def _decimal_text(value: Decimal) -> str:
    text = format(value.normalize(), "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return "0" if text in {"", "-0"} else text


def _observation_ref(row: dict[str, Any]) -> str:
    return str(row.get("normalized_hash") or row.get("id") or row.get("observation_key") or "")


def _calendar_distance(current_date: str, baseline_date: str) -> int:
    return (date.fromisoformat(current_date) - date.fromisoformat(baseline_date)).days


def build_dgs10_features(
    observations: list[dict[str, Any]] | tuple[dict[str, Any], ...],
) -> dict[str, Any]:
    rows = list(observations)
    features: list[MacroFeature] = []
    if not rows:
        unavailable = MacroFeature(
            feature_id="rate_level_pct",
            status=MacroFeatureStatus.UNAVAILABLE,
            value=None,
            unit="PERCENT",
            current_observation_ref=None,
            reason="NO_OBSERVATIONS",
        )
        features.append(unavailable)
        for distance in DGS10_FEATURE_WINDOWS:
            features.append(
                MacroFeature(
                    feature_id=f"delta_bp_{distance}obs",
                    status=MacroFeatureStatus.UNAVAILABLE,
                    value=None,
                    unit="BASIS_POINT",
                    current_observation_ref=None,
                    observation_distance=distance,
                    reason="NO_OBSERVATIONS",
                )
            )
        payload = {
            "contract_version": MACRO_FEATURE_CONTRACT_VERSION,
            "series_id": "US_10Y_CONSTANT_MATURITY_YIELD",
            "features": [feature.to_dict() for feature in features],
        }
        return {**payload, "feature_set_hash": content_hash(payload)}

    current = rows[0]
    current_date = str(current["observation_date"])
    current_ref = _observation_ref(current)
    current_value_raw = current.get("normalized_value")
    try:
        current_value = _decimal(current_value_raw)
    except ValueError:
        current_value = None

    if current_value is None:
        features.append(
            MacroFeature(
                feature_id="rate_level_pct",
                status=MacroFeatureStatus.MISSING_REFERENCE,
                value=None,
                unit="PERCENT",
                current_observation_ref=current_ref,
                current_observation_date=current_date,
                reason="CURRENT_VALUE_MISSING",
            )
        )
    else:
        features.append(
            MacroFeature(
                feature_id="rate_level_pct",
                status=MacroFeatureStatus.AVAILABLE,
                value=_decimal_text(current_value),
                unit="PERCENT",
                current_observation_ref=current_ref,
                current_observation_date=current_date,
            )
        )

    for distance in DGS10_FEATURE_WINDOWS:
        feature_id = f"delta_bp_{distance}obs"
        if len(rows) <= distance:
            features.append(
                MacroFeature(
                    feature_id=feature_id,
                    status=MacroFeatureStatus.INSUFFICIENT_HISTORY,
                    value=None,
                    unit="BASIS_POINT",
                    current_observation_ref=current_ref,
                    current_observation_date=current_date,
                    observation_distance=distance,
                    reason=f"REQUIRES_{distance + 1}_OBSERVATIONS",
                )
            )
            continue

        baseline = rows[distance]
        baseline_date = str(baseline["observation_date"])
        baseline_ref = _observation_ref(baseline)
        try:
            baseline_value = _decimal(baseline.get("normalized_value"))
        except ValueError:
            baseline_value = None

        if current_value is None or baseline_value is None:
            features.append(
                MacroFeature(
                    feature_id=feature_id,
                    status=MacroFeatureStatus.MISSING_REFERENCE,
                    value=None,
                    unit="BASIS_POINT",
                    current_observation_ref=current_ref,
                    baseline_observation_ref=baseline_ref,
                    current_observation_date=current_date,
                    baseline_observation_date=baseline_date,
                    observation_distance=distance,
                    calendar_distance_days=_calendar_distance(current_date, baseline_date),
                    reason="NUMERIC_REFERENCE_MISSING",
                )
            )
            continue

        delta_bp = (current_value - baseline_value) * Decimal("100")
        features.append(
            MacroFeature(
                feature_id=feature_id,
                status=MacroFeatureStatus.AVAILABLE,
                value=_decimal_text(delta_bp),
                unit="BASIS_POINT",
                current_observation_ref=current_ref,
                baseline_observation_ref=baseline_ref,
                current_observation_date=current_date,
                baseline_observation_date=baseline_date,
                observation_distance=distance,
                calendar_distance_days=_calendar_distance(current_date, baseline_date),
            )
        )

    payload = {
        "contract_version": MACRO_FEATURE_CONTRACT_VERSION,
        "series_id": "US_10Y_CONSTANT_MATURITY_YIELD",
        "features": [feature.to_dict() for feature in features],
    }
    return {**payload, "feature_set_hash": content_hash(payload)}
