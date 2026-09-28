from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from enum import Enum
from typing import Any

from app.event_evidence.errors import EventEvidenceContractError


TEMPORAL_EVIDENCE_CONTRACT_VERSION = "VN_P6_S1_TEMPORAL_EVIDENCE_V1"


class EvidenceTimeQuality(str, Enum):
    EXACT = "EXACT"
    PROVIDER_TIME = "PROVIDER_TIME"
    DATE_ONLY = "DATE_ONLY"
    INFERRED = "INFERRED"
    UNKNOWN = "UNKNOWN"


def _aware_datetime(value: str | None, field_name: str) -> datetime | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise EventEvidenceContractError(
            "EVENT_EVIDENCE_TIME_INVALID",
            f"{field_name}은 timezone이 포함된 ISO-8601 시각이어야 합니다.",
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise EventEvidenceContractError(
            "EVENT_EVIDENCE_TIMEZONE_REQUIRED",
            f"{field_name}에는 timezone offset이 필요합니다.",
        )
    return parsed


def _event_time_value(
    value: str | None,
    quality: EvidenceTimeQuality,
) -> datetime | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if quality is EvidenceTimeQuality.DATE_ONLY:
        try:
            datetime.strptime(text, "%Y-%m-%d")
        except ValueError as exc:
            raise EventEvidenceContractError(
                "EVENT_EVIDENCE_DATE_ONLY_INVALID",
                "DATE_ONLY event_time은 YYYY-MM-DD 형식이어야 합니다.",
            ) from exc
        return None
    return _aware_datetime(text, "event_time")


@dataclass(frozen=True, slots=True)
class TemporalEvidence:
    available_at: str
    fetched_at: str
    time_quality: EvidenceTimeQuality
    event_time: str | None = None
    source_published_at: str | None = None
    provider_published_at: str | None = None
    first_seen_at: str | None = None
    corrected_at: str | None = None
    contract_version: str = TEMPORAL_EVIDENCE_CONTRACT_VERSION

    def __post_init__(self) -> None:
        if self.contract_version != TEMPORAL_EVIDENCE_CONTRACT_VERSION:
            raise EventEvidenceContractError(
                "EVENT_EVIDENCE_TIME_CONTRACT_MISMATCH",
                "Temporal Evidence contract version이 현재 코드와 다릅니다.",
            )

        try:
            quality = (
                self.time_quality
                if isinstance(self.time_quality, EvidenceTimeQuality)
                else EvidenceTimeQuality(str(self.time_quality))
            )
        except ValueError as exc:
            raise EventEvidenceContractError(
                "EVENT_EVIDENCE_TIME_QUALITY_INVALID",
                f"알 수 없는 time_quality입니다: {self.time_quality}",
            ) from exc
        object.__setattr__(self, "time_quality", quality)

        available = _aware_datetime(self.available_at, "available_at")
        fetched = _aware_datetime(self.fetched_at, "fetched_at")
        assert available is not None
        assert fetched is not None

        _event_time_value(self.event_time, quality)
        source_published = _aware_datetime(
            self.source_published_at,
            "source_published_at",
        )
        provider_published = _aware_datetime(
            self.provider_published_at,
            "provider_published_at",
        )
        first_seen = _aware_datetime(self.first_seen_at, "first_seen_at")
        corrected = _aware_datetime(self.corrected_at, "corrected_at")

        if available > fetched:
            raise EventEvidenceContractError(
                "EVENT_EVIDENCE_AVAILABLE_AFTER_FETCH",
                "available_at은 fetched_at보다 늦을 수 없습니다.",
            )
        if provider_published is not None and provider_published > available:
            raise EventEvidenceContractError(
                "EVENT_EVIDENCE_PROVIDER_AFTER_AVAILABLE",
                "provider_published_at 이후에만 available_at이 될 수 있습니다.",
            )
        if source_published is not None and source_published > available:
            raise EventEvidenceContractError(
                "EVENT_EVIDENCE_SOURCE_AFTER_AVAILABLE",
                "source_published_at 이후에만 available_at이 될 수 있습니다.",
            )
        if first_seen is not None and first_seen > fetched:
            raise EventEvidenceContractError(
                "EVENT_EVIDENCE_FIRST_SEEN_AFTER_FETCH",
                "first_seen_at은 fetched_at보다 늦을 수 없습니다.",
            )
        if corrected is not None and corrected < available:
            raise EventEvidenceContractError(
                "EVENT_EVIDENCE_CORRECTION_BEFORE_AVAILABLE",
                "corrected_at은 available_at보다 이를 수 없습니다.",
            )

    @property
    def historical_evaluation_eligible(self) -> bool:
        return self.time_quality in {
            EvidenceTimeQuality.EXACT,
            EvidenceTimeQuality.PROVIDER_TIME,
        }

    def is_available_by(self, cutoff: str) -> bool:
        cutoff_dt = _aware_datetime(cutoff, "cutoff")
        available_dt = _aware_datetime(self.available_at, "available_at")
        assert cutoff_dt is not None
        assert available_dt is not None
        return available_dt <= cutoff_dt

    def require_historical_time_quality(self) -> None:
        if not self.historical_evaluation_eligible:
            raise EventEvidenceContractError(
                "EVENT_EVIDENCE_TIME_NOT_EVALUATION_ELIGIBLE",
                "DATE_ONLY/INFERRED/UNKNOWN 시각 근거는 시간 분리 평가에 사용할 수 없습니다.",
            )

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["time_quality"] = self.time_quality.value
        return payload


def conservative_available_at(*timestamps: str | None) -> str:
    parsed: list[datetime] = []
    for index, value in enumerate(timestamps):
        item = _aware_datetime(value, f"availability_candidate_{index}")
        if item is not None:
            parsed.append(item)
    if not parsed:
        raise EventEvidenceContractError(
            "EVENT_EVIDENCE_AVAILABILITY_UNKNOWN",
            "available_at을 만들 수 있는 확인된 시각 근거가 없습니다.",
        )
    latest = max(parsed)
    return latest.isoformat()
