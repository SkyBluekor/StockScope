"""S6 operator flow: offline by default; all API calls mocked in CI."""
from __future__ import annotations

import asyncio
from copy import deepcopy
from dataclasses import replace
from decimal import Decimal
from datetime import datetime, timezone
import json
import sqlite3

import httpx
import pytest

from tools.data.jev_s6_micro_canary import (
    RESEARCH_DB, _aggregate, _cases, _manifest, _record_owner_attestation,
    _upper_bound_check, build_parser, execute,
)
from app.jev.decision_reviewer_micro_canary import (
    FrozenMicroProtocol, MicroJournal, micro_packet, synthetic_projection,
)
from app.jev.decision_reviewer_offline import DecisionReviewContractError
from app.jev.typesafe_provider import (
    TYPESAFE_MODELS_URL, TYPESAFE_SYSTEM_ONE_URL,
)


def _args(mode="status", *overrides):
    return build_parser().parse_args([mode, *overrides])


def _mock_response(decision):
    choices = ("PASS_THROUGH", "REVIEW_REQUIRED", "ABSTAIN")
    return {
        "model": "jev-1.13.0",
        "answers": {
            "review_decision": {
                "type": "choice",
                "choice": decision,
                "confidence": 0.99,
                "probabilities": {x: 1.0 if x == decision else 0.0 for x in choices},
            }
        },
        "usage": {"input_tokens": 134, "output_tokens": 21},
    }


def _handler(request):
    if str(request.url) == TYPESAFE_MODELS_URL:
        return httpx.Response(200, json={
            "models": [{
                "name": "jev-1.13.0",
                "description": "TypeSafe test model (mock metadata)",
                "release_date": "2026-09-15",
            }]
        })
    if str(request.url) == TYPESAFE_SYSTEM_ONE_URL:
        payload = json.loads(request.content)
        assert payload["model"] == "jev-1.13.0"
        assert payload["state"]["synthetic_only"] is True
        assert "gold" not in request.content.decode()
        return httpx.Response(200, json=_mock_response("PASS_THROUGH"))
    raise AssertionError("Unexpected network endpoint")


def _trial_args(case="s5-consistent"):
    return _args(
        "run-approved",
        "--model", "jev-1.13.0",
        "--case", case,
        "--max-calls", "1",
        "--reserve-usd", "0.01",
        "--budget-usd", "0.01",
    )


def _consent_for(args):
    proto, _, _ = _manifest(args)
    return iter([
        f"RUN JEV MICRO {proto.identity_hash[:12]} {proto.max_attempts} USD {proto.total_budget_usd}"
    ])


def test_status_offline_no_key_no_db(tmp_path, monkeypatch):
    monkeypatch.delenv("JEV_API_KEY", raising=False)
    target = tmp_path / "nonexistent.sqlite3"
    result = asyncio.run(execute(_args(), journal_path=target))
    assert result["status"] == "HOLD_UNTIL_SEPARATE_AUTHORIZATION"
    assert result["provider_calls"] == 0
    assert result["db_writes"] == 0
    assert not target.exists()


def test_dry_run_without_price_still_no_network_or_write(tmp_path, monkeypatch):
    monkeypatch.delenv("JEV_API_KEY", raising=False)
    args = _args(
        "dry-run", "--model", "jev-1.13.0",
        "--case", "s5-consistent", "--max-calls", "1", "--budget-usd", "0.01",
    )
    result = asyncio.run(execute(args, journal_path=tmp_path/"none.sqlite3"))
    assert result["status"] == "AWAITING_SEPARATE_EXECUTION_CONSENT"
    assert Decimal(result["worst_case_reservation"]["upper_bound_cost_usd"]) >= 0
    assert result["public_input_usd_per_million"] == "0.042"
    assert result["public_output_usd_per_million"] == "0"
    assert result["actual_requests_executed_by_dry_run"] == 0
    assert not (tmp_path/"none.sqlite3").exists()


def test_report_missing_store_is_read_only(tmp_path):
    target = tmp_path / "absent.sqlite3"
    result = asyncio.run(execute(_args("report"), journal_path=target))
    assert result["total_records"] == 0
    assert not target.exists()
    assert result["scanner_uplift_proven"] is False


@pytest.mark.parametrize("bad", [
    ["--model", "jev-preview"], ["--model", "UNFROZEN"],
    ["--model", "jev-1.13.0", "--case", "live-capture"],
    ["--model", "jev-1.13.0", "--case", "s5-consistent"],
])
def test_dry_run_rejects_alias_or_nonregistered_or_count_mismatch(bad):
    args = _args("dry-run", *bad)
    with pytest.raises(DecisionReviewContractError):
        asyncio.run(execute(args))


def test_check_account_requires_intent_and_interactive_consent(tmp_path, monkeypatch):
    monkeypatch.setenv("JEV_API_KEY", "ci-mock-secret")
    seen = []
    def handler(req):
        seen.append(str(req.url))
        return _handler(req)
    transport = httpx.MockTransport(handler)
    args = _args("check-account", "--model", "jev-1.13.0")
    with pytest.raises(DecisionReviewContractError, match="S6_MODEL_LOOKUP_NOT_AUTHORIZED"):
        asyncio.run(execute(args, transport=transport))
    args = _args("check-account", "--model", "jev-1.13.0", "--authorize-model-lookup")
    with pytest.raises(DecisionReviewContractError, match="S6_CONSENT_PHRASE_MISMATCH"):
        asyncio.run(execute(args, input_fn=lambda prompt: "no", transport=transport))
    assert seen == []
    result = asyncio.run(execute(
        args, input_fn=lambda prompt: "TYPE S6 MODEL LOOKUP", transport=transport,
    ))
    assert result["available"] is True
    assert result["price_verified"] is False
    assert result["micro_canary_calls"] == 0
    assert seen == [TYPESAFE_MODELS_URL]


def test_run_approved_with_mock_transport_distinct_origin_and_report(tmp_path, monkeypatch):
    monkeypatch.setenv("JEV_API_KEY", "ci-mock-secret")
    seen = []
    def handler(req):
        seen.append(str(req.url))
        return _handler(req)
    transport = httpx.MockTransport(handler)
    args = _trial_args()
    consent = _consent_for(args)
    target = tmp_path/"isolated_s6.sqlite3"
    result = asyncio.run(execute(
        args, input_fn=lambda prompt: next(consent),
        transport=transport, journal_path=target,
    ))
    assert result["status"] == "EXPERIMENT_RECORDED_NOT_INVESTMENT_VALIDATED"
    assert result["by_origin"]["MOCK_TEST"]["valid"] == 1
    assert result["by_origin"]["ACTUAL_PROVIDER"]["attempts"] == 0
    assert result["by_origin"]["MOCK_TEST"]["records"][0]["choice"] == "PASS_THROUGH"
    assert result["by_origin"]["MOCK_TEST"]["records"][0]["latency_ms"] is not None
    assert result["owner_attestation"] == "ONE_EXPLICIT_RUN_CONSENT"
    assert result["pricing_basis"] == "PUBLIC_STANDARD_RATE_NOT_ACCOUNT_VERIFIED"
    assert seen == [TYPESAFE_MODELS_URL, TYPESAFE_SYSTEM_ONE_URL]
    readback = asyncio.run(execute(_args("report"), journal_path=target))
    assert readback["by_origin"]["ACTUAL_PROVIDER"]["attempts"] == 0
    assert readback["by_origin"]["MOCK_TEST"]["valid"] == 1
    with sqlite3.connect(target) as conn:
        row = conn.execute(
            "SELECT model_requested,pricing_basis,input_price_usd_per_million "
            "FROM jev_s6_2_run_consent"
        ).fetchone()
        assert row == ("jev-1.13.0", "PUBLIC_STANDARD_UNVERIFIED", "0.042")
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("DELETE FROM jev_s6_2_run_consent")
    assert result["scanner_uplift_proven"] is False


def test_run_approval_cannot_be_reduced_to_cli_boolean(tmp_path, monkeypatch):
    monkeypatch.setenv("JEV_API_KEY", "ci-mock-secret")
    calls = []
    transport = httpx.MockTransport(lambda req: (calls.append(req), _handler(req))[1])
    args = _trial_args()
    with pytest.raises(DecisionReviewContractError, match="S6_CONSENT_PHRASE_MISMATCH"):
        asyncio.run(execute(
            args, input_fn=lambda prompt: "yes",
            transport=transport, journal_path=tmp_path/"none.db",
        ))
    assert calls == []
    assert not (tmp_path/"none.db").exists()


def test_no_account_billing_pages_required_and_public_rate_is_fixed():
    args = _trial_args()
    proto, cases, preview = _manifest(args)
    assert proto.pricing_basis == "PUBLIC_STANDARD_UNVERIFIED"
    assert proto.verified_input_usd_per_million == "0.042"
    assert proto.verified_output_usd_per_million == "0"
    assert preview["pricing_basis"] == "PUBLIC_STANDARD_RATE_NOT_ACCOUNT_VERIFIED"
    assert cases == ("s5-consistent",)
    # CLI no longer accepts user-forged rates or billing-page ceremony.
    with pytest.raises(SystemExit):
        _args("dry-run", "--model", "jev-latest", "--input-price", "0")


def test_run_missing_api_key_fails_without_get_or_post(tmp_path, monkeypatch):
    monkeypatch.setenv("JEV_API_KEY", "")
    # Patch key resolver because a machine-local .env may exist.
    monkeypatch.setattr("tools.data.jev_s6_micro_canary.load_typesafe_jev_api_key", lambda: None)
    args = _trial_args()
    consent = _consent_for(args)
    seen = []
    transport = httpx.MockTransport(lambda req: (seen.append(req), _handler(req))[1])
    with pytest.raises(DecisionReviewContractError, match="S6_API_KEY_MISSING"):
        asyncio.run(execute(
            args, input_fn=lambda prompt: next(consent),
            transport=transport, journal_path=tmp_path/"none.db",
        ))
    assert seen == []


def test_account_model_pin_denied_before_billable_post(tmp_path, monkeypatch):
    monkeypatch.setenv("JEV_API_KEY", "ci-mock-secret")
    args = _trial_args()
    args.model = "jev-9.9.9"
    consent = _consent_for(args)
    seen = []
    transport = httpx.MockTransport(lambda req: (seen.append(str(req.url)), _handler(req))[1])
    with pytest.raises(DecisionReviewContractError, match="S6_PINNED_MODEL_NOT_AVAILABLE_TO_ACCOUNT"):
        asyncio.run(execute(
            args, input_fn=lambda prompt: next(consent),
            transport=transport, journal_path=tmp_path/"none.db",
        ))
    assert seen == [TYPESAFE_MODELS_URL]
    assert not (tmp_path/"none.db").exists()


def test_error_stops_remaining_cases_and_unknown_cost(tmp_path, monkeypatch):
    monkeypatch.setenv("JEV_API_KEY", "ci-mock-secret")
    args = _trial_args()
    args.case = ["s5-consistent", "s5-condition-contradiction"]
    args.max_calls = 2
    args.budget_usd = "0.02"
    consent = _consent_for(args)
    seen = []
    def handler(req):
        seen.append(str(req.url))
        if str(req.url) == TYPESAFE_SYSTEM_ONE_URL:
            return httpx.Response(503)
        return _handler(req)
    target = tmp_path/"micro.sqlite3"
    result = asyncio.run(execute(
        args, input_fn=lambda prompt: next(consent),
        transport=httpx.MockTransport(handler), journal_path=target,
    ))
    assert seen == [TYPESAFE_MODELS_URL, TYPESAFE_SYSTEM_ONE_URL]
    assert result["by_origin"]["MOCK_TEST"]["errors"] == 1
    assert result["by_origin"]["MOCK_TEST"]["unknown_cost_attempts"] == 1
    assert result["by_origin"]["MOCK_TEST"]["attempts"] == 1


def test_repeated_execution_reuses_old_result_no_billed_post(tmp_path, monkeypatch):
    monkeypatch.setenv("JEV_API_KEY", "ci-mock-secret")
    args = _trial_args()
    seen = []
    transport = httpx.MockTransport(lambda req: (seen.append(str(req.url)), _handler(req))[1])
    target = tmp_path/"micro.sqlite3"
    for _ in range(2):
        consent = _consent_for(args)
        asyncio.run(execute(
            args, input_fn=lambda prompt: next(consent),
            transport=transport, journal_path=target,
        ))
    assert seen.count(TYPESAFE_MODELS_URL) == 2  # explicit account lookups
    assert seen.count(TYPESAFE_SYSTEM_ONE_URL) == 1


def test_atomic_global_project_ceiling_across_protocol_ids(tmp_path):
    conn = sqlite3.connect(tmp_path/"global.sqlite3")
    journal = MicroJournal(conn)
    journal.initialize()
    for i in range(10):
        proto = FrozenMicroProtocol(
            protocol_id=f"s6-global-{i}", model_requested="jev-1.13.0",
            model_returned="jev-1.13.0",
            max_attempts=1, per_attempt_reservation_usd="0.05",
            total_budget_usd="0.05",
        )
        projection = synthetic_projection("s5-consistent")
        packet = micro_packet(projection, proto)
        row, reused = journal.reserve(projection, packet, proto, origin="ACTUAL_PROVIDER")
        assert row["execution_origin"] == "ACTUAL_PROVIDER"
        assert not reused
    proto = replace(proto, protocol_id="s6-global-over-ceiling")
    with pytest.raises(DecisionReviewContractError, match="S6_PROJECT_TOTAL_RESERVATION_EXCEEDED"):
        journal.reserve(projection, packet, proto, origin="ACTUAL_PROVIDER")
    conn.close()


def test_s6_does_not_mutate_product_readiness_or_v4():
    from app.jev.review_models import JEV_USER_FEATURE_DISABLED
    from app.jev.typesafe_canary_v4 import validate_canary_v4_contract
    assert JEV_USER_FEATURE_DISABLED == "DISABLED_VALIDATION_PENDING"
    assert validate_canary_v4_contract()["spec"]["partition_contract"]["provider_reachable_positive_residual_count"] == 0
