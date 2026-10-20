"""S31-P user-triggered real capture semantics, with zero JEV provider calls."""
from __future__ import annotations

from pathlib import Path

import pytest

from app.api import jev as api
from app.jev import candidate_local_review_s31p as local
from app.jev.typesafe_state import TypeSafeStateProjectionError
from app.jev.typesafe_state_v4 import TypeSafeV4Route
from app.prospective.models import digest_json


class StubSource:
    sample = {
        "market": "KOSPI", "ticker": "001820",
        "snapshot": {"semantic_source_v2": {"test": "real-route-only"}},
    }

    def __init__(self, _path: Path) -> None:
        self.calls = 0

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


@pytest.mark.parametrize("request", [
    {"capture_id": ""}, {"sample_index": -1}, {"sample_index": True},
    {"market": "NASDAQ"}, {"ticker": "XX"},
])
def test_invalid_requested_identity_fails_before_source_access(stub,request):
    result = call(**request)
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
