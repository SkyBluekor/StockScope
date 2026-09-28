from __future__ import annotations

import pytest

from app.event_evidence import (
    EvidenceCapability,
    EvidenceTimeQuality,
    EventEvidenceContractError,
    EventEvidenceSourceRef,
    EventEvidenceState,
    EventRevisionIdentity,
    TemporalEvidence,
    conservative_available_at,
    opendart_event_evidence_policy,
    policy_for_event_source,
)


def _temporal(
    *,
    quality: EvidenceTimeQuality = EvidenceTimeQuality.EXACT,
) -> TemporalEvidence:
    return TemporalEvidence(
        event_time=(
            "2026-09-28"
            if quality is EvidenceTimeQuality.DATE_ONLY
            else "2026-09-28T09:00:00+09:00"
        ),
        source_published_at="2026-09-28T09:05:00+09:00",
        provider_published_at="2026-09-28T09:11:00+09:00",
        first_seen_at="2026-09-28T09:12:00+09:00",
        available_at="2026-09-28T09:12:00+09:00",
        fetched_at="2026-09-28T09:12:03+09:00",
        time_quality=quality,
    )


@pytest.mark.parametrize("provider", ["developer_center", "api_hub"])
def test_naver_news_display_rights_do_not_grant_p6_research_or_prediction(
    provider: str,
):
    policy = policy_for_event_source(
        "NAVER_NEWS",
        provider_kind=provider,
    )

    assert policy.display_allowed is True
    assert policy.normalization_allowed is True
    assert policy.raw_retention_allowed is False
    assert policy.derived_retention_allowed is False
    assert policy.ai_transform_allowed is False
    assert policy.historical_evaluation_allowed is False
    assert policy.prediction_input_allowed is False

    policy.require(EvidenceCapability.DISPLAY)
    with pytest.raises(EventEvidenceContractError) as historical:
        policy.require(EvidenceCapability.HISTORICAL_EVALUATION)
    assert historical.value.code == "EVENT_EVIDENCE_CAPABILITY_NOT_ALLOWED"


def test_opendart_existing_product_path_does_not_auto_grant_p6_prediction():
    policy = opendart_event_evidence_policy()

    assert policy.source_kind == "OPENDART_DISCLOSURE"
    assert policy.display_allowed is True
    assert policy.normalization_allowed is True
    assert policy.raw_retention_allowed is False
    assert policy.derived_retention_allowed is False
    assert policy.ai_transform_allowed is False
    assert policy.historical_evaluation_allowed is False
    assert policy.prediction_input_allowed is False


def test_unapproved_source_and_missing_naver_provider_fail_closed():
    with pytest.raises(EventEvidenceContractError) as unknown:
        policy_for_event_source("SOME_NEW_PROVIDER")
    assert unknown.value.code == "EVENT_EVIDENCE_SOURCE_NOT_APPROVED"

    with pytest.raises(EventEvidenceContractError) as missing:
        policy_for_event_source("NAVER_NEWS")
    assert missing.value.code == "EVENT_EVIDENCE_PROVIDER_REQUIRED"


def test_exact_temporal_evidence_uses_available_at_as_cutoff():
    temporal = _temporal()

    assert temporal.historical_evaluation_eligible is True
    assert temporal.is_available_by("2026-09-28T09:11:59+09:00") is False
    assert temporal.is_available_by("2026-09-28T09:12:00+09:00") is True
    temporal.require_historical_time_quality()


@pytest.mark.parametrize(
    "quality",
    [
        EvidenceTimeQuality.DATE_ONLY,
        EvidenceTimeQuality.INFERRED,
        EvidenceTimeQuality.UNKNOWN,
    ],
)
def test_weak_time_quality_is_not_eligible_for_time_split_evaluation(
    quality: EvidenceTimeQuality,
):
    kwargs = {
        "event_time": (
            "2026-09-28"
            if quality is EvidenceTimeQuality.DATE_ONLY
            else None
        ),
        "available_at": "2026-09-28T09:12:00+09:00",
        "fetched_at": "2026-09-28T09:12:03+09:00",
        "time_quality": quality,
    }
    temporal = TemporalEvidence(**kwargs)

    assert temporal.historical_evaluation_eligible is False
    with pytest.raises(EventEvidenceContractError) as caught:
        temporal.require_historical_time_quality()
    assert caught.value.code == "EVENT_EVIDENCE_TIME_NOT_EVALUATION_ELIGIBLE"


def test_temporal_contract_rejects_naive_or_future_availability():
    with pytest.raises(EventEvidenceContractError) as naive:
        TemporalEvidence(
            available_at="2026-09-28T09:12:00",
            fetched_at="2026-09-28T09:12:03+09:00",
            time_quality=EvidenceTimeQuality.EXACT,
        )
    assert naive.value.code == "EVENT_EVIDENCE_TIMEZONE_REQUIRED"

    with pytest.raises(EventEvidenceContractError) as future:
        TemporalEvidence(
            available_at="2026-09-28T09:13:00+09:00",
            fetched_at="2026-09-28T09:12:03+09:00",
            time_quality=EvidenceTimeQuality.EXACT,
        )
    assert future.value.code == "EVENT_EVIDENCE_AVAILABLE_AFTER_FETCH"


def test_conservative_available_at_uses_latest_confirmed_candidate():
    assert (
        conservative_available_at(
            "2026-09-28T09:05:00+09:00",
            "2026-09-28T09:11:00+09:00",
            "2026-09-28T09:12:00+09:00",
        )
        == "2026-09-28T09:12:00+09:00"
    )

    with pytest.raises(EventEvidenceContractError) as missing:
        conservative_available_at(None, None)
    assert missing.value.code == "EVENT_EVIDENCE_AVAILABILITY_UNKNOWN"


def test_source_ref_binds_rights_time_and_integrity_without_raw_content():
    policy = policy_for_event_source(
        "NAVER_NEWS",
        provider_kind="api_hub",
    )
    ref = EventEvidenceSourceRef(
        source_ref_id="SRC-1",
        source_kind=policy.source_kind,
        source_native_id="naver-item-1",
        rights_policy_id=policy.policy_id,
        content_hash="a" * 64,
        source_url="https://example.com/article/1",
        source_name="example.com",
        temporal=_temporal(),
    )

    payload = ref.to_dict()
    assert payload["rights_policy_id"] == policy.policy_id
    assert payload["content_hash"] == "a" * 64
    assert payload["temporal"]["available_at"] == "2026-09-28T09:12:00+09:00"
    assert "raw_content" not in payload

    with pytest.raises(EventEvidenceContractError) as bad_hash:
        EventEvidenceSourceRef(
            source_ref_id="SRC-2",
            source_kind="NAVER_NEWS",
            source_native_id="naver-item-2",
            rights_policy_id=policy.policy_id,
            content_hash="not-a-sha256",
            temporal=_temporal(),
        )
    assert bad_hash.value.code == "EVENT_EVIDENCE_CONTENT_HASH_INVALID"


def test_event_revision_identity_never_overwrites_corrections():
    original = EventRevisionIdentity(
        event_id="EVENT-1",
        version=1,
        state=EventEvidenceState.ORIGINAL,
    )
    corrected = EventRevisionIdentity(
        event_id="EVENT-1",
        version=2,
        state=EventEvidenceState.CORRECTED,
        supersedes_version=1,
    )
    withdrawn = EventRevisionIdentity(
        event_id="EVENT-1",
        version=3,
        state=EventEvidenceState.WITHDRAWN,
        supersedes_version=2,
    )

    assert original.supersedes_version is None
    assert corrected.to_dict()["supersedes_version"] == 1
    assert withdrawn.to_dict()["state"] == "WITHDRAWN"

    with pytest.raises(EventEvidenceContractError) as overwrite:
        EventRevisionIdentity(
            event_id="EVENT-1",
            version=2,
            state=EventEvidenceState.CORRECTED,
        )
    assert overwrite.value.code == "EVENT_EVIDENCE_SUPERSEDES_REQUIRED"
