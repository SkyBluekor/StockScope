from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from app.macro.identity import content_hash
from app.macro.models import MacroResearchProtocol


MACRO_CALIBRATION_PROTOCOL_CONTRACT_VERSION = (
    "VN_NEXT6B_S2_CALIBRATION_PROTOCOL_V1"
)


def _date_text(value: str, field: str) -> str:
    text = str(value or "").strip()
    try:
        date.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(f"{field} must be YYYY-MM-DD.") from exc
    return text


def validate_split_ranges(
    *,
    development_start: str,
    development_end: str,
    holdout_start: str,
    holdout_end: str,
) -> dict[str, str]:
    dev_start = _date_text(development_start, "development_start")
    dev_end = _date_text(development_end, "development_end")
    out_start = _date_text(holdout_start, "holdout_start")
    out_end = _date_text(holdout_end, "holdout_end")

    if dev_start > dev_end:
        raise ValueError("development_start must be <= development_end.")
    if out_start > out_end:
        raise ValueError("holdout_start must be <= holdout_end.")
    if dev_end >= out_start:
        raise ValueError(
            "Development and Holdout must be chronological and non-overlapping."
        )
    return {
        "development_start": dev_start,
        "development_end": dev_end,
        "holdout_start": out_start,
        "holdout_end": out_end,
    }


@dataclass(frozen=True, slots=True)
class MacroCalibrationProtocol:
    protocol_id: str
    protocol_hash: str
    base_protocol: dict[str, Any]
    development_dataset_hash: str
    holdout_dataset_hash: str
    development_vintage: str
    holdout_vintage: str
    holdout_locked: bool
    threshold_defined: bool
    minimum_sample_defined: bool
    episode_policy_defined: bool
    candidate_method_families: tuple[str, ...]
    production_decision_approved: bool
    contract_version: str = MACRO_CALIBRATION_PROTOCOL_CONTRACT_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_version": self.contract_version,
            "protocol_id": self.protocol_id,
            "protocol_hash": self.protocol_hash,
            "base_protocol": self.base_protocol,
            "development_dataset_hash": self.development_dataset_hash,
            "holdout_dataset_hash": self.holdout_dataset_hash,
            "development_vintage": self.development_vintage,
            "holdout_vintage": self.holdout_vintage,
            "holdout_locked": self.holdout_locked,
            "threshold_defined": self.threshold_defined,
            "minimum_sample_defined": self.minimum_sample_defined,
            "episode_policy_defined": self.episode_policy_defined,
            "candidate_method_families": list(self.candidate_method_families),
            "production_decision_approved": self.production_decision_approved,
        }


def build_calibration_research_protocol(
    *,
    development_dataset: dict[str, Any],
    holdout_dataset: dict[str, Any],
) -> MacroCalibrationProtocol:
    if development_dataset.get("split_role") != "DEVELOPMENT":
        raise ValueError("Development dataset split_role mismatch.")
    if holdout_dataset.get("split_role") != "HOLDOUT":
        raise ValueError("Holdout dataset split_role mismatch.")
    if development_dataset.get("status") == "NOT_PREPARED":
        raise ValueError("Development dataset is not prepared.")
    if holdout_dataset.get("status") == "NOT_PREPARED":
        raise ValueError("Holdout dataset is not prepared.")

    dev_manifest = development_dataset["manifest"]
    hold_manifest = holdout_dataset["manifest"]
    if dev_manifest["series_id"] != hold_manifest["series_id"]:
        raise ValueError("Development and Holdout series_id must match.")
    if (
        dev_manifest["feature_contract_version"]
        != hold_manifest["feature_contract_version"]
    ):
        raise ValueError("Development and Holdout feature contracts must match.")

    validate_split_ranges(
        development_start=dev_manifest["observation_start"],
        development_end=dev_manifest["observation_end"],
        holdout_start=hold_manifest["observation_start"],
        holdout_end=hold_manifest["observation_end"],
    )

    base = MacroResearchProtocol(
        protocol_id="NEXT6B_RATE_SPIKE_CALIBRATION_RESEARCH_V1",
        protocol_version="v1",
        baseline_identity="SCANNER-0.21.3.9",
        cutoff_policy="FIXED_VINTAGE_REFERENCE_ARCHIVE",
        development_rule="CHRONOLOGICAL_DEVELOPMENT_ONLY",
        holdout_rule="LOCKED_UNTIL_CALIBRATION_CANDIDATE_FREEZE",
        prospective_rule="FORWARD_ONLY_AFTER_HOLDOUT_REVIEW",
        pit_requirement=(
            "REFERENCE_RESEARCH_ONLY_DATE_ONLY_IS_NOT_HISTORICAL_PIT"
        ),
        ablation_sequence=(
            "RATE_LEVEL",
            "RATE_DELTA_1OBS",
            "RATE_DELTA_5OBS",
            "RATE_DELTA_10OBS",
        ),
        missing_data_reporting_rule=(
            "NO_IMPUTATION_NO_ZERO_FILL_REPORT_ALL_INCOMPLETE_ROWS"
        ),
        numeric_thresholds_defined=False,
    )
    identity_payload = {
        "contract_version": MACRO_CALIBRATION_PROTOCOL_CONTRACT_VERSION,
        "base_protocol_hash": base.protocol_hash,
        "development_dataset_hash": development_dataset["dataset_hash"],
        "holdout_dataset_hash": holdout_dataset["dataset_hash"],
        "development_vintage": dev_manifest["vintage_id"],
        "holdout_vintage": hold_manifest["vintage_id"],
        "holdout_locked": True,
        "threshold_defined": False,
        "minimum_sample_defined": False,
        "episode_policy_defined": False,
        "candidate_method_families": [
            "ROLLING_QUANTILE",
            "ROBUST_STANDARDIZED_DEVIATION",
        ],
        "production_decision_approved": False,
    }
    protocol_hash = content_hash(identity_payload)
    return MacroCalibrationProtocol(
        protocol_id=f"MACROCALPROTO-{protocol_hash[:16]}",
        protocol_hash=protocol_hash,
        base_protocol=base.to_dict(),
        development_dataset_hash=development_dataset["dataset_hash"],
        holdout_dataset_hash=holdout_dataset["dataset_hash"],
        development_vintage=dev_manifest["vintage_id"],
        holdout_vintage=hold_manifest["vintage_id"],
        holdout_locked=True,
        threshold_defined=False,
        minimum_sample_defined=False,
        episode_policy_defined=False,
        candidate_method_families=(
            "ROLLING_QUANTILE",
            "ROBUST_STANDARDIZED_DEVIATION",
        ),
        production_decision_approved=False,
    )
