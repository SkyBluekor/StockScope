from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
from typing import Any

from app.macro.errors import MacroContractError
from app.macro.identity import content_hash
from app.macro.models import MACRO_PREPARED_RANGE_CONTRACT_VERSION


@dataclass(frozen=True, slots=True)
class MacroPreparedRangeManifest:
    series_id: str
    start_date: str
    end_date: str
    expected_count: int
    stored_count: int
    missing_count: int
    unavailable_count: int
    date_only_count: int
    eligible_count: int
    source_contract_version: str
    normalizer_version: str
    source_manifest_hash: str
    prepared_at: str
    contract_version: str = MACRO_PREPARED_RANGE_CONTRACT_VERSION

    def __post_init__(self) -> None:
        if self.contract_version != MACRO_PREPARED_RANGE_CONTRACT_VERSION:
            raise MacroContractError(
                "MACRO_PREPARED_RANGE_VERSION_MISMATCH",
                "지원하지 않는 Macro prepared-range contract입니다.",
            )
        try:
            start = date.fromisoformat(self.start_date)
            end = date.fromisoformat(self.end_date)
        except ValueError as exc:
            raise MacroContractError(
                "MACRO_PREPARED_RANGE_DATE_INVALID",
                "prepared range 날짜는 YYYY-MM-DD 형식이어야 합니다.",
            ) from exc
        if start > end:
            raise MacroContractError(
                "MACRO_PREPARED_RANGE_ORDER_INVALID",
                "prepared range start_date는 end_date보다 늦을 수 없습니다.",
            )
        for field in (
            "expected_count",
            "stored_count",
            "missing_count",
            "unavailable_count",
            "date_only_count",
            "eligible_count",
        ):
            if int(getattr(self, field)) < 0:
                raise MacroContractError(
                    "MACRO_PREPARED_RANGE_COUNT_INVALID",
                    f"{field}은 음수일 수 없습니다.",
                )
        if self.stored_count + self.missing_count < self.expected_count:
            raise MacroContractError(
                "MACRO_PREPARED_RANGE_COUNT_INCONSISTENT",
                "stored_count + missing_count가 expected_count보다 작을 수 없습니다.",
            )
        if self.eligible_count > self.stored_count:
            raise MacroContractError(
                "MACRO_PREPARED_RANGE_ELIGIBLE_INVALID",
                "eligible_count는 stored_count보다 클 수 없습니다.",
            )

    @property
    def status(self) -> str:
        if (
            self.missing_count == 0
            and self.unavailable_count == 0
            and self.date_only_count == 0
            and self.eligible_count >= self.expected_count
        ):
            return "COMPLETE"
        return "PARTIAL"

    def identity_payload(self) -> dict[str, Any]:
        return {
            "contract_version": self.contract_version,
            "series_id": self.series_id,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "expected_count": self.expected_count,
            "stored_count": self.stored_count,
            "missing_count": self.missing_count,
            "unavailable_count": self.unavailable_count,
            "date_only_count": self.date_only_count,
            "eligible_count": self.eligible_count,
            "source_contract_version": self.source_contract_version,
            "normalizer_version": self.normalizer_version,
            "source_manifest_hash": self.source_manifest_hash,
            "status": self.status,
        }

    @property
    def content_hash(self) -> str:
        return content_hash(self.identity_payload())

    def to_dict(self) -> dict[str, Any]:
        return {
            **asdict(self),
            "status": self.status,
            "content_hash": self.content_hash,
        }
