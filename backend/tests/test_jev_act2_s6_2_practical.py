"""ACT2-S6.2: published-rate, single-consent and human report; NO paid calls."""
from __future__ import annotations

import asyncio
import json
import sqlite3
from decimal import Decimal

import httpx
import pytest

from app.jev.decision_reviewer_micro_canary import (
    CASES, FrozenMicroProtocol, MicroJournal, _model_to_review,
    micro_packet, synthetic_case_ids, synthetic_projection,
)
from app.jev.decision_reviewer_offline import DecisionReviewContractError
from app.jev.typesafe_provider import TYPESAFE_MODELS_URL, TYPESAFE_SYSTEM_ONE_URL
from tools.data.jev_s6_micro_canary import (
    _display, _manifest, _read_report, build_parser, execute,
)


def _trial_cli(mode="run-approved"):
    return build_parser().parse_args([mode, "--model", "jev-latest"])


def _owner_phrase(args):
    proto, _, _ = _manifest(args)
    return f"RUN JEV MICRO {proto.identity_hash[:12]} {proto.max_attempts} USD {proto.total_budget_usd}"


def test_default_dry_run_uses_public_rate_and_five_cases_without_key(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "tools.data.jev_s6_micro_canary.load_typesafe_jev_api_key",
        lambda: (_ for _ in ()).throw(AssertionError("must not inspect key")),
    )
    target = tmp_path / "absent.sqlite3"
    result = asyncio.run(execute(_trial_cli("dry-run"), journal_path=target))
    assert result["attempt_cap"] == 5
    assert result["budget_usd"] == "0.05"
    assert result["reservation_per_call_usd"] == "0.01"
    assert result["public_input_usd_per_million"] == "0.042"
    assert result["public_output_usd_per_million"] == "0"
    assert result["pricing_basis"] == "PUBLIC_STANDARD_RATE_NOT_ACCOUNT_VERIFIED"
    assert result["account_price_state"] == "PUBLIC_STANDARD_RATE_NOT_ACCOUNT_VERIFIED"
    assert result["model_revision_status"] == "REVISION_UNVERIFIED"
    assert set(result["selected_cases"]) == set(synthetic_case_ids())
    assert Decimal(result["worst_case_reservation"]["upper_bound_cost_usd"]) <= Decimal("0.01")
    assert not target.exists()


def test_single_consent_contains_model_alias_and_public_rate_warning(tmp_path, monkeypatch):
    monkeypatch.setenv("JEV_API_KEY", "ci-fake-key")
    seen = []
    prompts = []
    args = _trial_cli()
    def handler(req):
        seen.append(str(req.url))
        if str(req.url) == TYPESAFE_MODELS_URL:
            return httpx.Response(200, json={"models": [
                {"name": "jev-latest", "description": "live alias", "release_date": "2026-09-10"},
                {"name": "jev-preview", "description": "preview alias", "release_date": "2026-09-10"},
            ]})
        if str(req.url) == TYPESAFE_SYSTEM_ONE_URL:
            return httpx.Response(503, text="provider unavailable")
        raise AssertionError("unexpected endpoint")
    def approved(prompt):
        prompts.append(prompt)
        return _owner_phrase(args)
    result = asyncio.run(execute(
        args, input_fn=approved, transport=httpx.MockTransport(handler),
        journal_path=tmp_path/"research.sqlite3",
    ))
    assert len(prompts) == 1
    assert "jev-latest" in prompts[0]
    assert "$0.042" in prompts[0]
    assert "실제 계정 청구액 보증 아님" in prompts[0]
    assert "변경 가능한 별칭" in prompts[0]
    assert seen == [TYPESAFE_MODELS_URL, TYPESAFE_SYSTEM_ONE_URL]
    assert result["by_origin"]["MOCK_TEST"]["errors"] == 1
    assert result["by_origin"]["ACTUAL_PROVIDER"]["attempts"] == 0
    assert result["pricing_basis"] == "PUBLIC_STANDARD_RATE_NOT_ACCOUNT_VERIFIED"


def test_wrong_consent_never_requests_catalog_or_provider(tmp_path, monkeypatch):
    monkeypatch.setenv("JEV_API_KEY", "ci-fake-key")
    seen = []
    with pytest.raises(DecisionReviewContractError, match="S6_CONSENT_PHRASE_MISMATCH"):
        asyncio.run(execute(
            _trial_cli(),
            input_fn=lambda _: "yes",
            transport=httpx.MockTransport(lambda req: (seen.append(req), httpx.Response(500))[1]),
            journal_path=tmp_path/"absent.db",
        ))
    assert not seen
    assert not (tmp_path/"absent.db").exists()


def test_human_readable_report_five_synthetic_cases_without_real_api(tmp_path, capsys):
    target = tmp_path/"research.sqlite3"
    gold = {case["id"]: case["gold"] for case in CASES}
    with sqlite3.connect(target) as conn:
        journal = MicroJournal(conn)
        journal.initialize()
        proto = FrozenMicroProtocol(
            protocol_id="s6-2-mock-report-only",
            model_requested="jev-latest", model_returned="jev-latest",
            alias_identity_policy="SYNTHETIC_JEV_LATEST_V1",
            pricing_basis="PUBLIC_STANDARD_UNVERIFIED",
            max_attempts=5,
            per_attempt_reservation_usd="0.01", total_budget_usd="0.05",
            verified_input_usd_per_million="0.042",
            verified_output_usd_per_million="0",
        )
        for case_id in synthetic_case_ids():
            projection = synthetic_projection(case_id)
            packet = micro_packet(projection, proto)
            row, reused = journal.reserve(projection, packet, proto, origin="MOCK_TEST")
            assert not reused
            decision = gold[case_id]
            typed = {
                "model": "jev-latest", "requested_model": "jev-latest",
                "model_identity_status": "REVISION_UNVERIFIED",
                "decision": decision, "confidence": 1.0,
                "probabilities": {
                    k: 1.0 if k == decision else 0.0
                    for k in ("PASS_THROUGH", "REVIEW_REQUIRED", "ABSTAIN")
                },
                "usage": {"input_tokens": 200, "output_tokens": 10},
            }
            journal.finish(
                row["review_id"], output=_model_to_review(projection, decision),
                typed=typed, error=None, protocol=proto, duration_ms=42,
            )
    data = _read_report(target)
    assert data["by_origin"]["MOCK_TEST"]["correct"] == 5
    assert data["by_origin"]["MOCK_TEST"]["valid"] == 5
    assert data["by_origin"]["ACTUAL_PROVIDER"]["attempts"] == 0
    assert all(
        r["cost_status"] == "ESTIMATED_FROM_PUBLIC_STANDARD_RATE"
        for r in data["by_origin"]["MOCK_TEST"]["records"]
    )
    _display(data, as_json=False)
    shown = capsys.readouterr().out
    assert "실제 Jev 호출: 0건" in shown
    assert "Mock 테스트 기록: 5건" in shown
    assert "아직 실제 Jev 실험 결과가 없습니다" in shown
    assert "실전 투자 수익·손실 개선을 증명하지 않습니다" in shown
    assert '"by_origin":' not in shown
    _display(data, as_json=True)
    assert json.loads(capsys.readouterr().out)["by_origin"]["MOCK_TEST"]["valid"] == 5
