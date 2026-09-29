from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from app.macro.calibration import (
    MacroShockCalibration,
    uncalibrated_rate_spike_calibration,
)
from app.macro.features import build_dgs10_features
from app.macro.identity import content_hash
from app.macro.reader import LocalMacroReader
from app.macro.shock import build_uncalibrated_shock_assessment


MACRO_CONTEXT_CONTRACT_VERSION = "VN_NEXT6B_S1_MACRO_CONTEXT_V1"
MACRO_CUTOFF_POLICY_VERSION = "VN_NEXT6B_S1_AVAILABLE_AT_CUTOFF_V1"
DGS10_SERIES_ID = "US_10Y_CONSTANT_MATURITY_YIELD"
DGS10_CONTEXT_WINDOW_LIMIT = 11


class MacroContextUsage(str, Enum):
    REFERENCE_SHADOW = "REFERENCE_SHADOW"
    HISTORICAL_EVALUATION = "HISTORICAL_EVALUATION"


class MacroContextStatus(str, Enum):
    COMPLETE_REFERENCE = "COMPLETE_REFERENCE"
    COMPLETE_HISTORICAL = "COMPLETE_HISTORICAL"
    PARTIAL = "PARTIAL"
    UNAVAILABLE = "UNAVAILABLE"


def _normalized_cutoff(value: str) -> str:
    text = str(value or "").strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(
            "decision_cutoff must be a timezone-aware ISO-8601 datetime."
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(
            "decision_cutoff must be a timezone-aware ISO-8601 datetime."
        )
    return parsed.astimezone(timezone.utc).isoformat()


def _historical_time_eligible(observations: list[dict[str, Any]]) -> bool:
    if not observations:
        return False
    allowed = {"EXACT", "PROVIDER_TIME"}
    return all(str(row.get("time_quality")) in allowed for row in observations)


def _feature_status_counts(feature_set: dict[str, Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for feature in feature_set.get("features", []):
        key = str(feature.get("status") or "UNKNOWN")
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items()))


def build_macro_context(
    *,
    reader: LocalMacroReader,
    decision_cutoff: str,
    usage: MacroContextUsage | str,
    rate_calibration: MacroShockCalibration | None = None,
) -> dict[str, Any]:
    usage_mode = (
        usage
        if isinstance(usage, MacroContextUsage)
        else MacroContextUsage(str(usage).strip().upper())
    )
    cutoff = _normalized_cutoff(decision_cutoff)
    historical_only = usage_mode is MacroContextUsage.HISTORICAL_EVALUATION

    window = reader.read_series_window(
        DGS10_SERIES_ID,
        cutoff=cutoff,
        observation_limit=DGS10_CONTEXT_WINDOW_LIMIT,
        historical_eligible_only=historical_only,
    )
    observations = list(window.get("observations") or [])
    feature_set = build_dgs10_features(observations)
    calibration = rate_calibration or uncalibrated_rate_spike_calibration()
    shock = build_uncalibrated_shock_assessment(
        feature_set=feature_set,
        rate_calibration=calibration,
    )

    limitations: list[str] = []
    reason: str | None = None

    if window["status"] != "COMPLETE":
        status = MacroContextStatus.UNAVAILABLE
        if (
            historical_only
            and window.get("reason") == "NO_HISTORICALLY_ELIGIBLE_OBSERVATION"
        ):
            reason = "NOT_EVALUATION_ELIGIBLE"
            limitations.append("HISTORICAL_TIME_NOT_PROVEN")
        else:
            reason = str(window.get("reason") or "MACRO_INPUT_UNAVAILABLE")
            limitations.append(reason)
    else:
        feature_counts = _feature_status_counts(feature_set)
        all_feature_available = (
            feature_counts.get("AVAILABLE", 0)
            == len(feature_set.get("features", []))
        )
        if historical_only:
            status = (
                MacroContextStatus.COMPLETE_HISTORICAL
                if all_feature_available
                else MacroContextStatus.PARTIAL
            )
        else:
            status = (
                MacroContextStatus.COMPLETE_REFERENCE
                if all_feature_available
                else MacroContextStatus.PARTIAL
            )

        if not _historical_time_eligible(observations):
            limitations.append("HISTORICAL_TIME_NOT_PROVEN")
        if not all_feature_available:
            limitations.append("FEATURE_HISTORY_INCOMPLETE")

    limitations = sorted(set(limitations))

    input_manifest = {
        "series_id": DGS10_SERIES_ID,
        "window_hash": window["window_hash"],
        "observation_refs": [
            {
                "observation_key": row.get("observation_key"),
                "revision_no": row.get("revision_no"),
                "normalized_hash": row.get("normalized_hash"),
                "observation_date": row.get("observation_date"),
                "available_at": row.get("available_at"),
                "time_quality": row.get("time_quality"),
            }
            for row in observations
        ],
        "feature_contract_version": feature_set["contract_version"],
        "calibration_id": calibration.calibration_id,
        "calibration_version": calibration.version,
        "calibration_hash": calibration.calibration_hash,
        "cutoff_policy_version": MACRO_CUTOFF_POLICY_VERSION,
    }

    identity_payload = {
        "contract_version": MACRO_CONTEXT_CONTRACT_VERSION,
        "decision_cutoff": cutoff,
        "usage_mode": usage_mode.value,
        "status": status.value,
        "reason": reason,
        "input_manifest": input_manifest,
        "feature_set_hash": feature_set["feature_set_hash"],
        "shock_assessment_hash": shock["shock_assessment_hash"],
        "limitations": limitations,
        "production_decision_approved": False,
    }
    context_hash = content_hash(identity_payload)

    return {
        "contract_version": MACRO_CONTEXT_CONTRACT_VERSION,
        "context_id": f"MACROCTX-{context_hash[:16]}",
        "context_hash": context_hash,
        "decision_cutoff": cutoff,
        "usage_mode": usage_mode.value,
        "status": status.value,
        "reason": reason,
        "availability": {
            "component": DGS10_SERIES_ID,
            "reader_status": window["status"],
            "reader_reason": window.get("reason"),
            "returned_observations": window.get("returned_count", 0),
            "historical_evaluation_eligible": _historical_time_eligible(
                observations
            ),
            "time_qualities": sorted(
                {
                    str(row.get("time_quality"))
                    for row in observations
                    if row.get("time_quality")
                }
            ),
        },
        "features": feature_set,
        "shock_assessment": shock,
        "calibration": calibration.to_dict(),
        "input_manifest": input_manifest,
        "limitations": limitations,
        "production_decision_approved": False,
    }
