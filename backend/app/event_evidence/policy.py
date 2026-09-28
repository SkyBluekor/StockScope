from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any

from app.news.policy import policy_for as news_policy_for

from app.event_evidence.errors import EventEvidenceContractError


SOURCE_POLICY_CONTRACT_VERSION = "VN_P6_S1_EVENT_EVIDENCE_SOURCE_POLICY_V1"


class EvidenceCapability(str, Enum):
    DISPLAY = "DISPLAY"
    NORMALIZE = "NORMALIZE"
    RAW_RETENTION = "RAW_RETENTION"
    DERIVED_RETENTION = "DERIVED_RETENTION"
    AI_TRANSFORM = "AI_TRANSFORM"
    HISTORICAL_EVALUATION = "HISTORICAL_EVALUATION"
    PREDICTION_INPUT = "PREDICTION_INPUT"


@dataclass(frozen=True, slots=True)
class EventEvidenceSourcePolicy:
    policy_id: str
    source_kind: str
    policy_version: str
    display_allowed: bool
    normalization_allowed: bool
    raw_retention_allowed: bool
    derived_retention_allowed: bool
    ai_transform_allowed: bool
    historical_evaluation_allowed: bool
    prediction_input_allowed: bool
    attribution_required: bool
    policy_basis: str
    effective_from: str | None = None
    contract_version: str = SOURCE_POLICY_CONTRACT_VERSION

    def __post_init__(self) -> None:
        for field_name in (
            "policy_id",
            "source_kind",
            "policy_version",
            "policy_basis",
        ):
            if not str(getattr(self, field_name) or "").strip():
                raise EventEvidenceContractError(
                    "EVENT_EVIDENCE_POLICY_INVALID",
                    f"{field_name} 값이 필요합니다.",
                )
        if self.contract_version != SOURCE_POLICY_CONTRACT_VERSION:
            raise EventEvidenceContractError(
                "EVENT_EVIDENCE_POLICY_CONTRACT_MISMATCH",
                "Event Evidence Source Policy contract version이 현재 코드와 다릅니다.",
            )

    def allows(self, capability: EvidenceCapability | str) -> bool:
        try:
            resolved = (
                capability
                if isinstance(capability, EvidenceCapability)
                else EvidenceCapability(str(capability))
            )
        except ValueError as exc:
            raise EventEvidenceContractError(
                "EVENT_EVIDENCE_CAPABILITY_UNKNOWN",
                f"알 수 없는 Event Evidence capability입니다: {capability}",
            ) from exc

        mapping = {
            EvidenceCapability.DISPLAY: self.display_allowed,
            EvidenceCapability.NORMALIZE: self.normalization_allowed,
            EvidenceCapability.RAW_RETENTION: self.raw_retention_allowed,
            EvidenceCapability.DERIVED_RETENTION: self.derived_retention_allowed,
            EvidenceCapability.AI_TRANSFORM: self.ai_transform_allowed,
            EvidenceCapability.HISTORICAL_EVALUATION: self.historical_evaluation_allowed,
            EvidenceCapability.PREDICTION_INPUT: self.prediction_input_allowed,
        }
        return bool(mapping[resolved])

    def require(self, capability: EvidenceCapability | str) -> None:
        if not self.allows(capability):
            value = (
                capability.value
                if isinstance(capability, EvidenceCapability)
                else str(capability)
            )
            raise EventEvidenceContractError(
                "EVENT_EVIDENCE_CAPABILITY_NOT_ALLOWED",
                f"{self.source_kind} source는 {value} 용도로 승인되지 않았습니다.",
            )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def naver_event_evidence_policy(
    provider_kind: str,
) -> EventEvidenceSourcePolicy:
    news_policy = news_policy_for(provider_kind)
    provider = news_policy.provider_kind

    # NEWS.1 display permissions do not automatically grant P6 retention,
    # AI transformation, historical evaluation, or prediction rights.
    return EventEvidenceSourcePolicy(
        policy_id=(
            "P6-NAVER-"
            + provider.upper()
            + "-"
            + news_policy.policy_version
        ),
        source_kind="NAVER_NEWS",
        policy_version=news_policy.policy_version,
        display_allowed=bool(news_policy.display_allowed),
        normalization_allowed=bool(
            news_policy.display_normalization_allowed
        ),
        raw_retention_allowed=False,
        derived_retention_allowed=False,
        ai_transform_allowed=False,
        historical_evaluation_allowed=False,
        prediction_input_allowed=False,
        attribution_required=bool(news_policy.attribution_required),
        policy_basis=(
            "CURRENT_CODE_POLICY:app.news.policy:"
            + news_policy.policy_version
            + "; P6 retention/evaluation/prediction use is not approved"
        ),
    )


def opendart_event_evidence_policy() -> EventEvidenceSourcePolicy:
    # OpenDART already powers a separate product-time disclosure/EventRisk
    # path. P6 must not turn that existing usage into an assumed grant for
    # retained research corpora, AI transformation, historical evaluation,
    # or prediction input without a separately reviewed source contract.
    return EventEvidenceSourcePolicy(
        policy_id="P6-OPENDART-EXISTING-PRODUCT-PATH-2026-09-28",
        source_kind="OPENDART_DISCLOSURE",
        policy_version="opendart-existing-product-path-2026-09-28",
        display_allowed=True,
        normalization_allowed=True,
        raw_retention_allowed=False,
        derived_retention_allowed=False,
        ai_transform_allowed=False,
        historical_evaluation_allowed=False,
        prediction_input_allowed=False,
        attribution_required=True,
        policy_basis=(
            "EXISTING_PRODUCT_PATH_ONLY; P6 retention/evaluation/"
            "prediction rights are not approved by this contract"
        ),
    )


def policy_for_event_source(
    source_kind: str,
    *,
    provider_kind: str | None = None,
) -> EventEvidenceSourcePolicy:
    key = (source_kind or "").strip().upper()
    if key == "NAVER_NEWS":
        if not provider_kind:
            raise EventEvidenceContractError(
                "EVENT_EVIDENCE_PROVIDER_REQUIRED",
                "NAVER_NEWS Event Evidence policy에는 provider_kind가 필요합니다.",
            )
        return naver_event_evidence_policy(provider_kind)
    if key == "OPENDART_DISCLOSURE":
        return opendart_event_evidence_policy()
    raise EventEvidenceContractError(
        "EVENT_EVIDENCE_SOURCE_NOT_APPROVED",
        f"P6 Event Evidence source policy가 정의되지 않았습니다: {source_kind}",
    )
