"""ACT2-S6.1 moving TypeSafe aliases: no actual remote calls and no paid trials."""
from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import datetime, timezone
import json
import sqlite3

import httpx
import pytest

from app.jev.decision_reviewer_micro_canary import (
    ActualTrialApproval, FrozenMicroProtocol, MicroJournal, MicroCanaryRunner,
    SystemOneMicroProvider, synthetic_projection, micro_packet,
)
from app.jev.decision_reviewer_offline import DecisionReviewContractError
from app.jev.typesafe_provider import TYPESAFE_MODELS_URL, TYPESAFE_SYSTEM_ONE_URL
from tools.data.jev_s6_micro_canary import (
    _fixed_model, _manifest, build_parser, execute,
)


def _args(mode, *, model="jev-latest", cases=None, extra=None):
    params = [mode, "--model", model]
    chosen = cases or ["s5-consistent"]
    for case in chosen:
        params += ["--case", case]
    params += [
        "--max-calls", str(len(chosen)),
        "--budget-usd", f"{len(chosen)*0.01:.2f}",
        "--reserve-usd", "0.01",
    ]
    params += extra or []
    return build_parser().parse_args(params)


def _approved_args(*, model="jev-latest", cases=None):
    return _args("run-approved", model=model, cases=cases)


def _approval_answers(args):
    proto, _, _ = _manifest(args)
    return iter([
        f"RUN JEV MICRO {proto.identity_hash[:12]} {proto.max_attempts} USD {proto.total_budget_usd}"
    ])


def _catalog(variant=0):
    return {
        "models": [
            {
                "name": "jev-latest",
                "description": "The latest iteration of TypeSafe's System One Model: Jev"
                               + (" UPDATED" if variant else ""),
                "release_date": "2026-09-10T18:38:01.391457+00:00",
            },
            {
                "name": "jev-preview",
                "description": "A preview version of jev-latest: should be better in most ways",
                "release_date": "2026-09-10T18:39:06.057655+00:00",
            },
        ]
    }


def _choice(model="jev-latest", value="PASS_THROUGH"):
    names = ("PASS_THROUGH", "REVIEW_REQUIRED", "ABSTAIN")
    return {
        "model": model,
        "answers": {
            "review_decision": {
                "type": "choice", "choice": value,
                "confidence": 1.0,
                "probabilities": {
                    name: 1.0 if name == value else 0.0 for name in names
                },
            },
        },
        "usage": {"input_tokens": 100, "output_tokens": 3},
    }


def _handler(*, returned="jev-latest", catalog_variant=0, calls=None):
    def mock(request):
        if calls is not None:
            calls.append(str(request.url))
        if str(request.url) == TYPESAFE_MODELS_URL:
            return httpx.Response(200, json=_catalog(catalog_variant))
        if str(request.url) == TYPESAFE_SYSTEM_ONE_URL:
            data = json.loads(request.content)
            assert data["model"] == "jev-latest"
            assert data["state"]["synthetic_only"] is True
            assert "gold" not in json.dumps(data)
            return httpx.Response(200, json=_choice(returned))
        raise AssertionError("unexpected endpoint")
    return mock


def test_real_account_aliases_no_pinned_model():
    assert _fixed_model("jev-latest") == "jev-latest"
    with pytest.raises(DecisionReviewContractError, match="S6_PREVIEW_NOT_APPROVED"):
        _fixed_model("jev-preview")
    with pytest.raises(DecisionReviewContractError, match="S6_ALIAS_NOT_APPROVED"):
        _fixed_model("not-really-latest")
    assert "jev-1.13.0" not in {x["name"] for x in _catalog()["models"]}


def test_check_account_alias_records_metadata_but_not_immutable_revision(monkeypatch):
    monkeypatch.setenv("JEV_API_KEY", "ci-fake")
    args = build_parser().parse_args([
        "check-account", "--model", "jev-latest", "--authorize-model-lookup",
    ])
    result = asyncio.run(execute(
        args, input_fn=lambda p: "TYPE S6 MODEL LOOKUP",
        transport=httpx.MockTransport(_handler()),
    ))
    assert result["available"] is True
    assert result["model_kind"] == "MOVING_ALIAS_SYNTHETIC_ONLY"
    assert result["model_revision_status"] == "REVISION_UNVERIFIED"
    assert result["model_catalog_snapshot"]["revision_proven"] is False
    assert len(result["model_catalog_snapshot"]["snapshot_hash"]) == 64
    assert [i["name"] for i in result["models"]] == ["jev-latest", "jev-preview"]


def test_dry_run_alias_no_network_or_db(tmp_path, monkeypatch):
    monkeypatch.delenv("JEV_API_KEY", raising=False)
    args = _args("dry-run")
    location = tmp_path/"no.sqlite3"
    result = asyncio.run(execute(args, journal_path=location))
    assert result["status"] == "AWAITING_SEPARATE_EXECUTION_CONSENT"
    assert result["model_identity_policy"] == "SYNTHETIC_JEV_LATEST_V1"
    assert result["model_revision_status"] == "REVISION_UNVERIFIED"
    assert result["account_price_state"] == "PUBLIC_STANDARD_RATE_NOT_ACCOUNT_VERIFIED"
    assert result["actual_requests_executed_by_dry_run"] == 0
    assert not location.exists()


def test_alias_single_consent_rejection_before_get_or_post(tmp_path, monkeypatch):
    monkeypatch.setenv("JEV_API_KEY", "ci-fake")
    args = _approved_args()
    called = []
    with pytest.raises(DecisionReviewContractError, match="S6_CONSENT_PHRASE_MISMATCH"):
        asyncio.run(execute(
            args,
            input_fn=lambda p: "NO",
            transport=httpx.MockTransport(_handler(calls=called)),
            journal_path=tmp_path/"missing.sqlite3",
        ))
    assert called == []
    assert not (tmp_path/"missing.sqlite3").exists()


@pytest.mark.parametrize("returned", ["jev-latest", "jev-1.13.0"])
def test_alias_execution_mock_records_catalog_and_reported_model(
    tmp_path, monkeypatch, returned,
):
    monkeypatch.setenv("JEV_API_KEY", "ci-fake")
    target = tmp_path/"research.sqlite3"
    args = _approved_args()
    answers = _approval_answers(args)
    called = []
    result = asyncio.run(execute(
        args, input_fn=lambda p: next(answers),
        transport=httpx.MockTransport(_handler(returned=returned, calls=called)),
        journal_path=target,
    ))
    assert called == [TYPESAFE_MODELS_URL, TYPESAFE_SYSTEM_ONE_URL]
    assert result["by_origin"]["MOCK_TEST"]["valid"] == 1
    assert result["by_origin"]["ACTUAL_PROVIDER"]["attempts"] == 0
    row = result["by_origin"]["MOCK_TEST"]["records"][0]
    assert row["requested_model"] == "jev-latest"
    assert row["reported_model"] == returned
    assert row["revision_status"] == "REVISION_UNVERIFIED"
    assert result["model_revision_proven"] is False
    assert result["account_pricing_state"] == "PUBLIC_STANDARD_RATE_NOT_ACCOUNT_VERIFIED"
    assert len(result["model_catalog_snapshots"]) == 1
    snap = result["model_catalog_snapshots"][0]
    assert snap["model_revision_status"] == "REVISION_UNVERIFIED"
    assert [m["name"] for m in snap["models_at_check"]] == ["jev-latest", "jev-preview"]
    assert snap["catalog_hash"] == result["model_catalog_snapshot_hash"]
    with sqlite3.connect(target) as conn:
        old = conn.execute(
            "SELECT model_requested,pricing_basis FROM jev_s6_2_run_consent"
        ).fetchone()
        assert old == ("jev-latest", "PUBLIC_STANDARD_UNVERIFIED")


def test_alias_catalog_changed_no_second_paid_request(tmp_path, monkeypatch):
    monkeypatch.setenv("JEV_API_KEY", "ci-fake")
    target = tmp_path/"research.sqlite3"
    args = _approved_args()
    answers = _approval_answers(args)
    asyncio.run(execute(
        args, input_fn=lambda p: next(answers),
        transport=httpx.MockTransport(_handler()),
        journal_path=target,
    ))
    calls = []
    answers = _approval_answers(args)
    with pytest.raises(
        DecisionReviewContractError,
        match="S6_CATALOG_CHANGED_NEW_PROTOCOL_REQUIRED",
    ):
        asyncio.run(execute(
            args, input_fn=lambda p: next(answers),
            transport=httpx.MockTransport(_handler(catalog_variant=1, calls=calls)),
            journal_path=target,
        ))
    assert calls == [TYPESAFE_MODELS_URL]


def test_alias_returned_version_change_stops_after_first_valid(tmp_path, monkeypatch):
    monkeypatch.setenv("JEV_API_KEY", "ci-fake")
    args = _approved_args(cases=["s5-consistent", "s5-condition-contradiction"])
    answers = _approval_answers(args)
    seen = []
    returns = iter(["jev-1.13.0", "jev-1.13.1"])
    def handler(req):
        seen.append(str(req.url))
        if str(req.url) == TYPESAFE_MODELS_URL:
            return httpx.Response(200, json=_catalog())
        return httpx.Response(200, json=_choice(next(returns)))
    target = tmp_path/"shift.sqlite3"
    result = asyncio.run(execute(
        args, input_fn=lambda p: next(answers),
        transport=httpx.MockTransport(handler), journal_path=target,
    ))
    rows = result["by_origin"]["MOCK_TEST"]["records"]
    assert len(rows) == 2
    assert rows[0]["state"] == "VALID"
    assert rows[0]["reported_model"] == "jev-1.13.0"
    assert rows[1]["state"] == "ERROR"
    assert rows[1]["reason"] == "S6_ALIAS_MODEL_CHANGED"
    assert rows[1]["reported_model"] == "jev-1.13.1"
    assert seen == [TYPESAFE_MODELS_URL, TYPESAFE_SYSTEM_ONE_URL, TYPESAFE_SYSTEM_ONE_URL]


def test_alias_preview_response_rejected(tmp_path, monkeypatch):
    monkeypatch.setenv("JEV_API_KEY", "ci-fake")
    args = _approved_args()
    answers = _approval_answers(args)
    result = asyncio.run(execute(
        args, input_fn=lambda p: next(answers),
        transport=httpx.MockTransport(_handler(returned="jev-preview")),
        journal_path=tmp_path/"rejected.sqlite3",
    ))
    record = result["by_origin"]["MOCK_TEST"]["records"][0]
    assert record["state"] == "ERROR"
    assert record["reason"] == "S6_ALIAS_RETURNED_MODEL_UNEXPECTED"
    assert record["cost_status"] == "UNKNOWN"


def test_s6_2_no_billing_url_required_and_no_price_override():
    args = _approved_args()
    proto, _, preview = _manifest(args)
    assert proto.pricing_basis == "PUBLIC_STANDARD_UNVERIFIED"
    assert preview["pricing_basis"] == "PUBLIC_STANDARD_RATE_NOT_ACCOUNT_VERIFIED"
    with pytest.raises(SystemExit):
        _args("dry-run", extra=["--account-price-ref", "https://typesafe.ai/billing"])



def test_no_s5_legacy_case_mutation_or_feature_enablement():
    from app.jev.review_models import JEV_USER_FEATURE_DISABLED
    from app.jev.decision_reviewer_micro_canary import CASE_SET_HASH, CASES, QUESTION_HASH
    assert len(CASES) == 5
    assert len(CASE_SET_HASH) == len(QUESTION_HASH) == 64
    assert JEV_USER_FEATURE_DISABLED == "DISABLED_VALIDATION_PENDING"
