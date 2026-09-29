from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
from enum import Enum
from typing import Any

from app.event_evidence.time import EvidenceTimeQuality, TemporalEvidence
from app.macro.errors import MacroContractError
from app.macro.identity import content_hash


MACRO_SERIES_CONTRACT_VERSION = "VN_NEXT6A_S1_MACRO_SERIES_CONTRACT_V1"
MACRO_OBSERVATION_CONTRACT_VERSION = "VN_NEXT6A_S1_MACRO_OBSERVATION_V1"
MACRO_PREPARED_RANGE_CONTRACT_VERSION = "VN_NEXT6A_S1_MACRO_PREPARED_RANGE_V1"
MACRO_RESEARCH_PROTOCOL_CONTRACT_VERSION = "VN_NEXT6A_S1_MACRO_RESEARCH_PROTOCOL_V1"


class MacroOwnerStatus(str, Enum):
    CANDIDATE = "CANDIDATE"
    APPROVED_RESEARCH = "APPROVED_RESEARCH"
    DISABLED = "DISABLED"


class MacroReadStatus(str, Enum):
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    UNAVAILABLE = "UNAVAILABLE"


def _date_text(value: str, field: str) -> str:
    text = str(value or "").strip()
    try:
        date.fromisoformat(text)
    except ValueError as exc:
        raise MacroContractError(
            "MACRO_DATE_INVALID",
            f"{field}은 YYYY-MM-DD 형식이어야 합니다.",
        ) from exc
    return text


def _clean_id(value: str, field: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise MacroContractError(
            "MACRO_IDENTIFIER_REQUIRED",
            f"{field}은 비어 있을 수 없습니다.",
        )
    return text


@dataclass(frozen=True, slots=True)
class MacroSeriesContract:
    series_id: str
    semantic_id: str
    provider: str
    provider_series_id: str
    instrument_type: str
    measurement_definition: str
    unit: str
    currency: str | None
    session_definition: str
    observation_frequency: str
    owner_status: MacroOwnerStatus = MacroOwnerStatus.CANDIDATE
    active_owner: bool = False
    allowed_usage_scope: tuple[str, ...] = ("REFERENCE_ONLY", "SHADOW_RESEARCH")
    contract_version: str = MACRO_SERIES_CONTRACT_VERSION

    def __post_init__(self) -> None:
        if self.contract_version != MACRO_SERIES_CONTRACT_VERSION:
            raise MacroContractError(
                "MACRO_SERIES_CONTRACT_VERSION_MISMATCH",
                "지원하지 않는 Macro Series contract version입니다.",
            )
        for field in (
            "series_id",
            "semantic_id",
            "provider",
            "provider_series_id",
            "instrument_type",
            "measurement_definition",
            "unit",
            "session_definition",
            "observation_frequency",
        ):
            object.__setattr__(self, field, _clean_id(getattr(self, field), field))
        status = (
            self.owner_status
            if isinstance(self.owner_status, MacroOwnerStatus)
            else MacroOwnerStatus(str(self.owner_status))
        )
        object.__setattr__(self, "owner_status", status)
        scopes = tuple(sorted({str(item).strip().upper() for item in self.allowed_usage_scope if str(item).strip()}))
        if not scopes:
            raise MacroContractError(
                "MACRO_USAGE_SCOPE_REQUIRED",
                "Macro Series에는 최소 하나의 usage scope가 필요합니다.",
            )
        if "PRODUCTION_DECISION" in scopes:
            raise MacroContractError(
                "MACRO_PRODUCTION_SCOPE_NOT_APPROVED",
                "NEXT-6A-S1은 Macro를 Production 판단 입력으로 승인하지 않습니다.",
            )
        object.__setattr__(self, "allowed_usage_scope", scopes)
        if self.active_owner and status is not MacroOwnerStatus.APPROVED_RESEARCH:
            raise MacroContractError(
                "MACRO_ACTIVE_OWNER_NOT_APPROVED",
                "active_owner는 APPROVED_RESEARCH 상태에서만 사용할 수 있습니다.",
            )

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["owner_status"] = self.owner_status.value
        payload["allowed_usage_scope"] = list(self.allowed_usage_scope)
        return payload

    @property
    def contract_hash(self) -> str:
        return content_hash(self.to_dict())


@dataclass(frozen=True, slots=True)
class MacroObservation:
    series_id: str
    native_observation_id: str
    observation_date: str
    source_value: str
    normalized_value: str
    source_unit: str
    source_payload_hash: str
    normalizer_version: str
    temporal: TemporalEvidence
    realtime_start: str | None = None
    realtime_end: str | None = None
    vintage_id: str | None = None
    contract_version: str = MACRO_OBSERVATION_CONTRACT_VERSION

    def __post_init__(self) -> None:
        if self.contract_version != MACRO_OBSERVATION_CONTRACT_VERSION:
            raise MacroContractError(
                "MACRO_OBSERVATION_CONTRACT_VERSION_MISMATCH",
                "지원하지 않는 Macro Observation contract version입니다.",
            )
        for field in (
            "series_id",
            "native_observation_id",
            "source_value",
            "normalized_value",
            "source_unit",
            "source_payload_hash",
            "normalizer_version",
        ):
            object.__setattr__(self, field, _clean_id(getattr(self, field), field))
        object.__setattr__(
            self,
            "observation_date",
            _date_text(self.observation_date, "observation_date"),
        )
        if self.realtime_start is not None:
            object.__setattr__(
                self,
                "realtime_start",
                _date_text(self.realtime_start, "realtime_start"),
            )
        if self.realtime_end is not None:
            object.__setattr__(
                self,
                "realtime_end",
                _date_text(self.realtime_end, "realtime_end"),
            )
        if self.realtime_start and self.realtime_end and self.realtime_start > self.realtime_end:
            raise MacroContractError(
                "MACRO_REALTIME_RANGE_INVALID",
                "realtime_start는 realtime_end보다 늦을 수 없습니다.",
            )

    @property
    def historical_evaluation_eligible(self) -> bool:
        return self.temporal.historical_evaluation_eligible

    def identity_payload(self) -> dict[str, Any]:
        return {
            "contract_version": self.contract_version,
            "series_id": self.series_id,
            "native_observation_id": self.native_observation_id,
            "observation_date": self.observation_date,
        }

    def normalized_payload(self) -> dict[str, Any]:
        # Operational fetch/first-seen timestamps are intentionally excluded
        # from normalization identity. Re-fetching the same provider row later
        # must remain a no-op, while a provider revision or normalizer change
        # still creates a new immutable observation revision.
        return {
            **self.identity_payload(),
            "normalized_value": self.normalized_value,
            "source_unit": self.source_unit,
            "realtime_start": self.realtime_start,
            "realtime_end": self.realtime_end,
            "vintage_id": self.vintage_id,
            "time_quality": self.temporal.time_quality.value,
            "event_time": self.temporal.event_time,
            "source_published_at": self.temporal.source_published_at,
            "provider_published_at": self.temporal.provider_published_at,
            "corrected_at": self.temporal.corrected_at,
            "normalizer_version": self.normalizer_version,
        }

    @property
    def normalized_hash(self) -> str:
        return content_hash(self.normalized_payload())


@dataclass(frozen=True, slots=True)
class MacroResearchProtocol:
    protocol_id: str
    protocol_version: str
    baseline_identity: str
    cutoff_policy: str
    development_rule: str
    holdout_rule: str
    prospective_rule: str
    pit_requirement: str
    ablation_sequence: tuple[str, ...]
    missing_data_reporting_rule: str
    numeric_thresholds_defined: bool = False
    contract_version: str = MACRO_RESEARCH_PROTOCOL_CONTRACT_VERSION

    def __post_init__(self) -> None:
        if self.contract_version != MACRO_RESEARCH_PROTOCOL_CONTRACT_VERSION:
            raise MacroContractError(
                "MACRO_RESEARCH_PROTOCOL_VERSION_MISMATCH",
                "지원하지 않는 Macro research protocol contract입니다.",
            )
        if self.numeric_thresholds_defined:
            raise MacroContractError(
                "MACRO_NUMERIC_POLICY_UNAPPROVED",
                "NEXT-6A-S1에서는 최소 표본/충격/승격 수치를 확정하지 않습니다.",
            )
        for field in (
            "protocol_id",
            "protocol_version",
            "baseline_identity",
            "cutoff_policy",
            "development_rule",
            "holdout_rule",
            "prospective_rule",
            "pit_requirement",
            "missing_data_reporting_rule",
        ):
            object.__setattr__(self, field, _clean_id(getattr(self, field), field))
        sequence = tuple(str(item).strip() for item in self.ablation_sequence if str(item).strip())
        if not sequence:
            raise MacroContractError(
                "MACRO_ABLATION_SEQUENCE_REQUIRED",
                "Macro research protocol에는 ablation sequence가 필요합니다.",
            )
        object.__setattr__(self, "ablation_sequence", sequence)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["ablation_sequence"] = list(self.ablation_sequence)
        return payload

    @property
    def protocol_hash(self) -> str:
        return content_hash(self.to_dict())


def fred_dgs10_candidate_contract() -> MacroSeriesContract:
    return MacroSeriesContract(
        series_id="US_10Y_CONSTANT_MATURITY_YIELD",
        semantic_id="US_10Y_CONSTANT_MATURITY_YIELD",
        provider="FRED",
        provider_series_id="DGS10",
        instrument_type="INTEREST_RATE",
        measurement_definition="US 10-Year Treasury Constant Maturity Rate",
        unit="PERCENT",
        currency=None,
        session_definition="SOURCE_DAILY_OBSERVATION",
        observation_frequency="DAILY",
        owner_status=MacroOwnerStatus.CANDIDATE,
        active_owner=False,
    )


def fred_dgs10_research_contract() -> MacroSeriesContract:
    return MacroSeriesContract(
        series_id="US_10Y_CONSTANT_MATURITY_YIELD",
        semantic_id="US_10Y_CONSTANT_MATURITY_YIELD",
        provider="FRED",
        provider_series_id="DGS10",
        instrument_type="INTEREST_RATE",
        measurement_definition="US 10-Year Treasury Constant Maturity Rate",
        unit="PERCENT",
        currency=None,
        session_definition="SOURCE_DAILY_OBSERVATION",
        observation_frequency="DAILY",
        owner_status=MacroOwnerStatus.APPROVED_RESEARCH,
        active_owner=True,
        allowed_usage_scope=("REFERENCE_ONLY", "SHADOW_RESEARCH"),
    )
