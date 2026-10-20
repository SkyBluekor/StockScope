"""S31-P user-triggered real capture semantics, with zero JEV provider calls."""
from __future__ import annotations

from pathlib import Path

import pytest

from app.api import jev as api
from app.jev import candidate_local_review_s31p as local
from app.jev.typesafe_state import TypeSafeStateProjectionError
from app.jev.typesafe_state_v4 import TypeSafeV4Route
from app.prospective.models import digest_json
from app.horizon import HorizonPolicyError, require_horizon_activatable, resolve_horizon_context


class StubSource:
    sample = {
        "market": "KOSPI", "ticker": "001820",
        "snapshot": {"semantic_source_v2": {"test": "real-route-only"}},
    }

    def __init__(self, _path: Path) -> None:
        self.calls = 0
        self.sample = dict(type(self).sample)
        self.sample["snapshot_hash"] = digest_json(self.sample["snapshot"])

    def _load_sample(self, capture_id: str, sample_index: int):
        self.calls += 1
        return self.sample, {
            "capture_id": capture_id, "sample_index": sample_index,
            "snapshot_hash": digest_json(self.sample["snapshot"]),
        }, None


@pytest.fixture
def stub(monkeypatch):
    obj = StubSource(Path("nonexistent"))
    monkeypatch.setattr(local, "JevManualReviewService", lambda _db: obj)
    return obj


def call(**overrides):
    return local.inspect_captured_candidate_local(
        Path("/definitely-no-sim-db"),
        **{
            "capture_id": "cap-one", "sample_index": 0,
            "market": "KOSPI", "ticker": "001820",
            **overrides,
        },
    )


@pytest.mark.parametrize(
    "semantic_status,reason,suggested",
    [
        ("LOCAL_MATCH", "SKIPPED_LOCAL_MATCH", False),
        ("LOCAL_CONFLICT", "SKIPPED_LOCAL_CONFLICT", False),
        ("LOCAL_INCOMPLETE", "SKIPPED_SOURCE_INCOMPLETE", False),
        ("LOCAL_AMBIGUOUS", "SKIPPED_SOURCE_AMBIGUOUS", False),
        ("RESIDUAL_SEMANTIC_REVIEW", "PROVIDER_CALL_ELIGIBLE", True),
    ],
)
def test_local_v4_routes_real_capture_without_external_model(
    stub, monkeypatch, semantic_status, reason, suggested,
):
    called = []
    def route(sample):
        called.append(sample)
        return TypeSafeV4Route(
            local_status=semantic_status,
            reason_code=reason,
            provider_eligible=suggested,
        )
    monkeypatch.setattr(local, "route_typesafe_state_v4", route)
    result = call()
    assert called == [stub.sample]
    assert result["status"] == "LOCAL_CHECK_COMPLETE"
    assert result["local_semantic_status"] == semantic_status
    assert result["reason_code"] == reason
    assert result["provider_review_suggested_by_local_state"] is suggested
    assert result["model_result_available"] is False
    assert result["provider_call_authorized"] is False
    assert result["rights_for_real_market_transmission_verified"] is False
    assert result["review_kind"] == "LOCAL_SEMANTIC_CHECK_NOT_JEV_MODEL"
    assert result["snapshot_hash"] == digest_json(stub.sample["snapshot"])
    assert (result["jev_model_calls"], result["external_requests"],
            result["db_writes"], result["orders"]) == (0, 0, 0, 0)


def test_mismatched_candidate_identity_holds_before_router(stub, monkeypatch):
    monkeypatch.setattr(
        local, "route_typesafe_state_v4",
        lambda _sample: pytest.fail("route called on different stock"),
    )
    response = call(ticker="005830")
    assert response["status"] == "HOLD"
    assert response["reason_code"] == "CAPTURE_CANDIDATE_IDENTITY_MISMATCH"
    assert response["snapshot_hash"] is None
    assert response["model_result_available"] is False


def test_missing_capture_and_sample_error_never_fakes_ai_result(stub, monkeypatch):
    monkeypatch.setattr(stub, "_load_sample", lambda *_: (None, {}, "CAPTURE_NOT_FOUND"))
    result = call()
    assert result["reason_code"] == "CAPTURE_NOT_FOUND"
    assert result["status"] == "HOLD"
    assert result["jev_model_calls"] == 0


def test_invalid_or_missing_semantic_source_stays_hold(stub, monkeypatch):
    def reject(_sample):
        raise TypeSafeStateProjectionError("SEMANTIC_SOURCE_V2_INVALID")
    monkeypatch.setattr(local, "route_typesafe_state_v4", reject)
    result = call()
    assert result["status"] == "HOLD"
    assert result["reason_code"] == "SEMANTIC_SOURCE_V2_INVALID"
    assert result["model_result_available"] is False


@pytest.mark.parametrize("params", [
    {"capture_id": ""}, {"sample_index": -1}, {"sample_index": True},
    {"market": "NASDAQ"}, {"ticker": "XX"},
])
def test_invalid_requested_identity_fails_before_source_access(stub,params):
    result = call(**params)
    assert result["reason_code"] == "LOCAL_REVIEW_REQUEST_INVALID"
    assert stub.calls == 0


def test_api_exposes_local_check_and_no_model_dispatch(stub, monkeypatch):
    monkeypatch.setattr(api, "_db", lambda: Path("/definitely-no-sim-db"))
    monkeypatch.setattr(
        local, "route_typesafe_state_v4",
        lambda _sample: TypeSafeV4Route(
            local_status="LOCAL_MATCH", provider_eligible=False,
            reason_code="SKIPPED_LOCAL_MATCH",
        ),
    )
    answer = api.jev_candidate_local_check(
        capture_id="cap-one", sample_index=0, market="KOSPI", ticker="001820",
    )
    assert answer["status"] == "LOCAL_CHECK_COMPLETE"
    assert answer["jev_model_calls"] == 0
    assert answer["baseline_candidate_changed"] is False
    assert answer["provider_call_authorized"] is False


def test_tampered_snapshot_digest_holds_before_semantic_engine(stub, monkeypatch):
    monkeypatch.setattr(
        stub, "_load_sample",
        lambda *_: (
            stub.sample, {"capture_id": "cap-one", "snapshot_hash": "forged"}, None,
        ),
    )
    monkeypatch.setattr(
        local, "route_typesafe_state_v4",
        lambda _: pytest.fail("router must not see a forged snapshot"),
    )
    result = call()
    assert result["status"] == "HOLD"
    assert result["reason_code"] == "CAPTURE_SNAPSHOT_HASH_MISMATCH"
    assert result["snapshot_hash"] is None
    assert result["jev_model_calls"] == 0


def test_real_shape_immutable_prospective_capture_uses_actual_catalog(tmp_path):
    """Full local integration: real Catalog read + real V4 semantic router.

    The data is synthetic, but the storage shape and engine are production code.
    """
    import sqlite3
    from tests.test_jev_act2_s3_decision_reviewer import _stored

    db, capture_id = _stored(tmp_path)
    with sqlite3.connect(db) as conn:
        before = "\n".join(conn.iterdump())
    result = local.inspect_captured_candidate_local(
        db, capture_id=capture_id, sample_index=0,
        market="KOSPI", ticker="000001",
    )
    assert result["status"] == "LOCAL_CHECK_COMPLETE", result
    assert result["local_semantic_status"] == "LOCAL_MATCH"
    assert result["reason_code"] == "SKIPPED_LOCAL_MATCH"
    assert result["model_result_available"] is False
    assert result["provider_call_authorized"] is False
    assert result["jev_model_calls"] == 0
    assert result["db_writes"] == 0
    with sqlite3.connect(db) as conn:
        assert before == "\n".join(conn.iterdump())


@pytest.mark.parametrize(
    "horizon,expected_diagnostic",
    [
        ("LEGACY_UNSPECIFIED", "LEGACY_HORIZON_UNSPECIFIED"),
        ("LONG", "LONG_OUTSIDE_LOCAL_V4"),
    ],
)
def test_actual_stored_capture_horizon_not_semantic_shortage(
    tmp_path, horizon, expected_diagnostic,
):
    """No retroactive SHORT coercion or writes for user's real-shaped case."""
    import sqlite3
    from tests.test_jev_act2_s3_decision_reviewer import _stored

    db, capture_id = _stored(tmp_path, horizon=horizon)
    with sqlite3.connect(db) as conn:
        before = "\n".join(conn.iterdump())

    result = local.inspect_captured_candidate_local(
        db, capture_id=capture_id, sample_index=0,
        market="KOSPI", ticker="000001",
    )
    if horizon == "LEGACY_UNSPECIFIED":
        assert result["status"] == "LOCAL_EVIDENCE_COMPLETE"
        assert result["reason_code"] == "LEGACY_LOCAL_EVIDENCE_ONLY_LOCAL_MATCH"
        assert result["check_stage"] == "LOCAL_EVIDENCE_COMPLETE"
        assert result["local_semantic_status"] == "LOCAL_MATCH"
        assert result["local_evidence_scope"] == "HORIZON_INDEPENDENT_ONLY"
        assert result["provider_review_suggested_by_local_state"] is False
        assert "기간별 전략 적합성" in result["explanation"]
    else:
        assert result["status"] == "HOLD"
        assert result["reason_code"] == "OUT_OF_SCOPE_HORIZON"
        assert result["check_stage"] == "HORIZON_SCOPE"
    assert result["capture_horizon_intent"] == horizon
    assert result["horizon_diagnostic_status"] == expected_diagnostic
    assert result["capture_horizon_policy_version"] == "VN_P1_S2_HORIZON_CONTEXT_V1"
    assert result["local_v4_horizon_supported"] is False
    if horizon == "LEGACY_UNSPECIFIED":
        assert "SHORT/MEDIUM 정책은 미승인" in result["next_action"]
    else:
        assert "전략 조건 부족이 아니라" in result["explanation"]
        assert "장기" in result["next_action"]
    assert result["model_result_available"] is False
    assert (result["jev_model_calls"], result["external_requests"],
            result["db_writes"], result["orders"]) == (0, 0, 0, 0)
    with sqlite3.connect(db) as conn:
        assert before == "\n".join(conn.iterdump())


@pytest.mark.parametrize("horizon", ["SHORT", "MEDIUM"])
def test_actual_stored_explicit_period_proceeds_to_local_semantic_router(
    tmp_path, horizon,
):
    import sqlite3
    from tests.test_jev_act2_s3_decision_reviewer import _stored

    db, capture_id = _stored(tmp_path, horizon=horizon)
    with sqlite3.connect(db) as conn:
        before = "\n".join(conn.iterdump())
    result = local.inspect_captured_candidate_local(
        db, capture_id=capture_id, sample_index=0,
        market="KOSPI", ticker="000001",
    )
    assert result["status"] == "LOCAL_CHECK_COMPLETE"
    assert result["check_stage"] == "COMPLETE"
    assert result["capture_horizon_intent"] == horizon
    assert result["local_v4_horizon_supported"] is True
    assert result["horizon_diagnostic_status"] == "LOCAL_V4_IN_SCOPE"
    assert result["local_semantic_status"] == "LOCAL_MATCH"
    assert result["model_result_available"] is False
    with sqlite3.connect(db) as conn:
        assert before == "\n".join(conn.iterdump())


def test_current_scanner_explicit_horizon_requires_unapproved_numeric_policy():
    """Do not recommend to users a scanner re-run that is currently blocked."""
    for horizon in ("SHORT", "MEDIUM"):
        context = resolve_horizon_context(horizon)
        assert context.support_status == "EVALUATION_PENDING"
        with pytest.raises(HorizonPolicyError) as blocked:
            require_horizon_activatable(context)
        assert blocked.value.code == "HORIZON_POLICY_NOT_ACTIVE"


def test_horizon_unknown_does_not_backfill_or_invent_semantic_problem(stub, monkeypatch):
    stub.sample["horizon_intent"] = None
    monkeypatch.setattr(
        local, "route_typesafe_state_v4",
        lambda sample: (_ for _ in ()).throw(
            TypeSafeStateProjectionError("OUT_OF_SCOPE_HORIZON")
        ),
    )
    result = call()
    assert result["capture_horizon_intent"] == "UNKNOWN"
    assert result["horizon_diagnostic_status"] == "CAPTURE_HORIZON_UNKNOWN"
    assert result["status"] == "HOLD"
    assert result["check_stage"] == "HORIZON_SCOPE"
    assert result["model_result_available"] is False


def test_bad_hash_does_not_disclose_unverified_horizon(stub, monkeypatch):
    stub.sample["horizon_intent"] = "LONG"
    monkeypatch.setattr(
        stub, "_load_sample",
        lambda *_: (stub.sample, {"snapshot_hash": "forged"}, None),
    )
    result = call()
    assert result["reason_code"] == "CAPTURE_SNAPSHOT_HASH_MISMATCH"
    assert result["check_stage"] == "CAPTURE_INTEGRITY"
    assert result["capture_horizon_intent"] is None
    assert result["horizon_diagnostic_status"] == "NOT_CHECKED"


def test_semantic_source_failure_has_distinct_stage_from_horizon_gate(
    stub, monkeypatch,
):
    stub.sample["horizon_intent"] = "SHORT"
    monkeypatch.setattr(
        local, "route_typesafe_state_v4",
        lambda sample: (_ for _ in ()).throw(
            TypeSafeStateProjectionError("SEMANTIC_SOURCE_V2_INVALID")
        ),
    )
    result = call()
    assert result["reason_code"] == "SEMANTIC_SOURCE_V2_INVALID"
    assert result["check_stage"] == "SEMANTIC_INPUT"
    assert result["capture_horizon_intent"] == "SHORT"
    assert result["local_v4_horizon_supported"] is True
    assert "전략·조건 의미 근거" in result["headline"]


def test_non_entry_candidate_is_not_misdiagnosed_as_horizon_failure(
    stub, monkeypatch,
):
    stub.sample["horizon_intent"] = "LEGACY_UNSPECIFIED"
    monkeypatch.setattr(
        local, "route_typesafe_state_v4",
        lambda sample: (_ for _ in ()).throw(
            TypeSafeStateProjectionError("OUT_OF_SCOPE_ACTION")
        ),
    )
    result = call()
    assert result["reason_code"] == "OUT_OF_SCOPE_ACTION"
    assert result["check_stage"] == "ACTION_SCOPE"
    assert result["model_result_available"] is False

@pytest.mark.parametrize("outcome", [
    "LOCAL_MATCH", "LOCAL_CONFLICT", "LOCAL_INCOMPLETE",
    "LOCAL_AMBIGUOUS", "RESIDUAL_SEMANTIC_REVIEW",
])
def test_legacy_local_semantic_outcomes_are_not_provider_eligible(
    stub, monkeypatch, outcome,
):
    from app.jev.typesafe_state_v4 import TypeSafeV4Route
    stub.sample["horizon_intent"] = "LEGACY_UNSPECIFIED"
    seen = []
    def legacy_route(sample):
        seen.append(sample)
        return TypeSafeV4Route(
            local_status=outcome, provider_eligible=False,
            reason_code="LEGACY_LOCAL_EVIDENCE_ONLY_" + outcome,
        )
    monkeypatch.setattr(local, "inspect_legacy_semantic_evidence_v4", legacy_route)
    monkeypatch.setattr(
        local, "route_typesafe_state_v4",
        lambda _: pytest.fail("V4 provider route must not run for legacy"),
    )
    result = call()
    assert seen == [stub.sample]
    assert result["status"] == "LOCAL_EVIDENCE_COMPLETE"
    assert result["local_semantic_status"] == outcome
    assert result["provider_review_suggested_by_local_state"] is False
    assert result["provider_call_authorized"] is False
    assert result["rights_for_real_market_transmission_verified"] is False
    assert result["model_result_available"] is False
    assert result["baseline_candidate_changed"] is False
    assert (result["jev_model_calls"], result["external_requests"],
            result["orders"], result["db_writes"]) == (0, 0, 0, 0)


def test_legacy_semantic_source_invalid_still_holds_before_any_result(tmp_path):
    from tests.test_jev_act2_s3_decision_reviewer import _stored
    db, capture_id = _stored(
        tmp_path, horizon="LEGACY_UNSPECIFIED",
        mutate_snapshot=lambda candidate: candidate.__setitem__(
            "semantic_source_v2", {"invalid": True},
        ),
    )
    result = local.inspect_captured_candidate_local(
        db, capture_id=capture_id, sample_index=0,
        market="KOSPI", ticker="000001",
    )
    assert result["status"] == "HOLD"
    assert result["check_stage"] == "SEMANTIC_INPUT"
    assert result["model_result_available"] is False
    assert result["jev_model_calls"] == 0


def test_legacy_semantic_check_does_not_expand_existing_v4_scope(tmp_path):
    from tests.test_jev_act2_s3_decision_reviewer import _stored
    from app.jev.typesafe_state_v4 import (
        route_typesafe_state_v4, project_typesafe_state_v4,
        inspect_legacy_semantic_evidence_v4,
    )
    from app.jev.review_service import JevManualReviewService

    db, capture_id = _stored(tmp_path, horizon="LEGACY_UNSPECIFIED")
    sample, _ref, err = JevManualReviewService(db)._load_sample(capture_id, 0)
    assert err is None
    assert sample["horizon_intent"] == "LEGACY_UNSPECIFIED"
    with pytest.raises(TypeSafeStateProjectionError, match="OUT_OF_SCOPE_HORIZON"):
        route_typesafe_state_v4(sample)
    with pytest.raises(TypeSafeStateProjectionError, match="OUT_OF_SCOPE_HORIZON"):
        project_typesafe_state_v4(sample)
    local_result = inspect_legacy_semantic_evidence_v4(sample)
    assert local_result.local_status == "LOCAL_MATCH"
    assert local_result.provider_eligible is False
    assert local_result.reason_code == "LEGACY_LOCAL_EVIDENCE_ONLY_LOCAL_MATCH"


def test_legacy_non_entry_candidate_does_not_create_approved_local_result(stub):
    stub.sample["horizon_intent"] = "LEGACY_UNSPECIFIED"
    stub.sample["action"] = "WAIT"
    result = call()
    assert result["status"] == "HOLD"
    assert result["reason_code"] == "OUT_OF_SCOPE_ACTION"
    assert result["local_evidence_scope"] == "NOT_CHECKED"


def test_unknown_or_long_still_do_not_receive_legacy_evidence(stub, monkeypatch):
    monkeypatch.setattr(
        local, "inspect_legacy_semantic_evidence_v4",
        lambda _: pytest.fail("legacy semantic route must not run"),
    )
    monkeypatch.setattr(
        local, "route_typesafe_state_v4",
        lambda _: (_ for _ in ()).throw(
            TypeSafeStateProjectionError("OUT_OF_SCOPE_HORIZON")
        ),
    )
    for horizon in ("LONG", None):
        stub.sample["horizon_intent"] = horizon
        result = call()
        assert result["status"] == "HOLD"
        assert result["reason_code"] == "OUT_OF_SCOPE_HORIZON"
