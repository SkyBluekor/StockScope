from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Any

from app.event_evidence.errors import EventEvidenceContractError
from app.event_evidence.time import TemporalEvidence


SOURCE_REF_CONTRACT_VERSION = "VN_P6_S1_EVENT_EVIDENCE_SOURCE_REF_V1"
REVISION_IDENTITY_CONTRACT_VERSION = "VN_P6_S1_EVENT_REVISION_IDENTITY_V1"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class EventEvidenceState(str, Enum):
    ORIGINAL = "ORIGINAL"
    CORRECTED = "CORRECTED"
    WITHDRAWN = "WITHDRAWN"
    SUPERSEDED = "SUPERSEDED"


@dataclass(frozen=True, slots=True)
class EventEvidenceSourceRef:
    source_ref_id: str
    source_kind: str
    source_native_id: str
    rights_policy_id: str
    content_hash: str
    temporal: TemporalEvidence
    source_url: str | None = None
    source_name: str | None = None
    contract_version: str = SOURCE_REF_CONTRACT_VERSION

    def __post_init__(self) -> None:
        for field_name in (
            "source_ref_id",
            "source_kind",
            "source_native_id",
            "rights_policy_id",
        ):
            if not str(getattr(self, field_name) or "").strip():
                raise EventEvidenceContractError(
                    "EVENT_EVIDENCE_SOURCE_REF_INVALID",
                    f"{field_name} 값이 필요합니다.",
                )
        if self.contract_version != SOURCE_REF_CONTRACT_VERSION:
            raise EventEvidenceContractError(
                "EVENT_EVIDENCE_SOURCE_REF_CONTRACT_MISMATCH",
                "Event Evidence Source Ref contract version이 현재 코드와 다릅니다.",
            )
        if not _SHA256.fullmatch(str(self.content_hash or "")):
            raise EventEvidenceContractError(
                "EVENT_EVIDENCE_CONTENT_HASH_INVALID",
                "content_hash는 lowercase SHA-256이어야 합니다.",
            )
        if self.source_url is not None:
            value = self.source_url.strip().lower()
            if not (value.startswith("https://") or value.startswith("http://")):
                raise EventEvidenceContractError(
                    "EVENT_EVIDENCE_SOURCE_URL_INVALID",
                    "source_url은 http(s) URL이어야 합니다.",
                )

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_version": self.contract_version,
            "source_ref_id": self.source_ref_id,
            "source_kind": self.source_kind,
            "source_native_id": self.source_native_id,
            "rights_policy_id": self.rights_policy_id,
            "content_hash": self.content_hash,
            "source_url": self.source_url,
            "source_name": self.source_name,
            "temporal": self.temporal.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class EventRevisionIdentity:
    event_id: str
    version: int
    state: EventEvidenceState
    supersedes_version: int | None = None
    contract_version: str = REVISION_IDENTITY_CONTRACT_VERSION

    def __post_init__(self) -> None:
        if not str(self.event_id or "").strip():
            raise EventEvidenceContractError(
                "EVENT_EVIDENCE_EVENT_ID_REQUIRED",
                "event_id가 필요합니다.",
            )
        if self.contract_version != REVISION_IDENTITY_CONTRACT_VERSION:
            raise EventEvidenceContractError(
                "EVENT_EVIDENCE_REVISION_CONTRACT_MISMATCH",
                "Event revision identity contract version이 현재 코드와 다릅니다.",
            )
        if self.version < 1:
            raise EventEvidenceContractError(
                "EVENT_EVIDENCE_REVISION_INVALID",
                "event version은 1 이상이어야 합니다.",
            )
        try:
            state = (
                self.state
                if isinstance(self.state, EventEvidenceState)
                else EventEvidenceState(str(self.state))
            )
        except ValueError as exc:
            raise EventEvidenceContractError(
                "EVENT_EVIDENCE_STATE_INVALID",
                f"알 수 없는 Event Evidence state입니다: {self.state}",
            ) from exc
        object.__setattr__(self, "state", state)

        if self.version == 1:
            if state is not EventEvidenceState.ORIGINAL:
                raise EventEvidenceContractError(
                    "EVENT_EVIDENCE_INITIAL_STATE_INVALID",
                    "version 1 Event Evidence는 ORIGINAL이어야 합니다.",
                )
            if self.supersedes_version is not None:
                raise EventEvidenceContractError(
                    "EVENT_EVIDENCE_INITIAL_SUPERSEDES_FORBIDDEN",
                    "version 1은 이전 version을 supersede할 수 없습니다.",
                )
            return

        if state is EventEvidenceState.ORIGINAL:
            raise EventEvidenceContractError(
                "EVENT_EVIDENCE_REVISION_STATE_INVALID",
                "version 2 이상은 ORIGINAL state가 될 수 없습니다.",
            )
        if self.supersedes_version is None:
            raise EventEvidenceContractError(
                "EVENT_EVIDENCE_SUPERSEDES_REQUIRED",
                "정정/철회/대체 version은 supersedes_version이 필요합니다.",
            )
        if self.supersedes_version < 1 or self.supersedes_version >= self.version:
            raise EventEvidenceContractError(
                "EVENT_EVIDENCE_SUPERSEDES_INVALID",
                "supersedes_version은 현재 version보다 작은 양의 정수여야 합니다.",
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_version": self.contract_version,
            "event_id": self.event_id,
            "version": self.version,
            "state": self.state.value,
            "supersedes_version": self.supersedes_version,
        }
