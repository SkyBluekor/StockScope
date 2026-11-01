"""Stage B no-paid-CI validation: one real TypeSafe class with MOCK HTTP transport.

Only authored text appears in the provider request. Tests NEVER access the
network, and all saved claims belong to isolated temporary directories.
"""
from __future__ import annotations

import asyncio
import json
import sqlite3

import httpx
import pytest

from app.jev.owned_review_b import OwnedReviewService, OwnedReviewError, QUESTION
from app.jev.typesafe_provider import TypeSafeSystemOneProvider
from app.prospective import ProspectiveCatalog
from app.prospective.models import ProspectiveCaptureRequest
from app.simulation.strategy_governance import current_strategy_definitions
from app.strategy.condition_semantics import condition_sources
from app.strategy.models import StrategyName
from tools.data.migrate_prospective_vnp2s2 import migrate_prospective_store


def _capture(tmp_path):
    db = tmp_path / "existing-simulation.db"
    sqlite3.connect(db).close()
    migrate_prospective_store(db)
    catalog = ProspectiveCatalog(db)
    strategy = next(
        item for item in current_strategy_definitions()
        if item.strategy_key == StrategyName.TREND_FOLLOWING.value
    )
    total = len(condition_sources(StrategyName.TREND_FOLLOWING.value))
    candidate = {
        "market": "KOSPI", "code": "005930", "name": "검증종목", "rank": 1,
        "strategy": StrategyName.TREND_FOLLOWING.value,
        "strategy_version_id": strategy.strategy_version_id,
        "strategy_definition_hash": strategy.definition_hash,
        "decision_status": "READY", "candidate_state": "READY",
        "action": "ENTRY_CANDIDATE",
        "conditions": {
            "passed": total, "total": total, "missing": 0, "top_missing": [],
        },
    }
    req = ProspectiveCaptureRequest(
        market_scope="KOSPI", requested_as_of="2026-10-07",
        candidate_limit=1, horizon_intent="SHORT",
        horizon_policy_version="HORIZON-V1",
        selection_policy_id="POLICY", selection_policy_hash="POLICY-HASH",
    )
    catalog.begin_capture(source_job_id="owned-b-one-shot-fixture", request=req)
    captured = catalog.finalize_capture(
        source_job_id="owned-b-one-shot-fixture", request=req,
        result={
            "version": "scanner-fixture",
            "requested_as_of": "2026-10-07",
            "market_scope": "KOSPI",
            "data_dates": {"KOSPI": "2026-10-07"},
            "input_fingerprint": "fixture-input",
            "partial_data": False,
            "summary": {"candidate_count": 1},
            "candidates": [candidate], "more_candidates": [],
            "horizon_context": {"intent": "SHORT"},
            "strategy_selection_policy": {
                "policy_id": "POLICY", "policy_hash": "POLICY-HASH",
            },
            "diagnostics": {"reproducibility_audit": {
                "production_baseline": "BASELINE",
            }},
        }, require_policy_provenance=False,
    )
    return db, str(captured["id"])


def _input(capture_id, **overrides):
    return {
        "capture_id": capture_id, "sample_index": 0,
        "market": "KOSPI", "ticker": "005930",
        "required_condition": "내가 정한 필수 기준이 충족되어야만 진입한다.",
        "observed_meaning": "현재 내가 확인한 바로는 그 필수 기준이 충족되지 않았다.",
        **overrides,
    }


def _transport(calls, *, probability=0.86, model="jev-test-real-1", status=200):
    def responder(request):
        body = json.loads(request.content)
        calls.append(body)
        return httpx.Response(
            status, json={
                "model": model,
                "answers": {QUESTION: {"type": "noul", "noul": probability}},
                "usage": {"input_tokens": 56, "output_tokens": 3},
            },
        )
    return httpx.MockTransport(responder)


def _service(db, store, calls, *, probability=0.86, model="jev-test-real-1"):
    return OwnedReviewService(
        db, store_dir=store,
        provider_factory=lambda requested: TypeSafeSystemOneProvider(
            model_id=requested, transport=_transport(calls, probability=probability, model=model),
        ),
    )


def test_preflight_does_not_create_files_or_use_network(monkeypatch, tmp_path):
    db, cap = _capture(tmp_path)
    monkeypatch.delenv("STOCKSCOPE_JEV_B_ENABLE", raising=False)
    calls = []
    svc = _service(db, tmp_path / "reviews", calls)
    before = db.read_bytes()
    preview = svc.prepare(_input(cap))
    assert preview["ready"] is False
    assert preview["reason"] == "JEV_B_NOT_ENABLED"
    assert preview["remote_input_scope"] == "USER_AUTHORED_TEXT_ONLY"
    assert preview["market_data_sent"] is False
    assert preview["existing"] is None
    assert calls == []
    assert not (tmp_path / "reviews").exists()
    assert before == db.read_bytes()


def test_one_explicit_payment_authorization_stores_result_and_reuses(monkeypatch, tmp_path):
    db, cap = _capture(tmp_path)
    monkeypatch.setenv("STOCKSCOPE_JEV_B_ENABLE", "1")
    monkeypatch.setenv("JEV_API_KEY", "dummy-for-mock-transport")
    calls = []
    svc = _service(db, tmp_path / "reviews", calls)
    before = db.read_bytes()
    data = _input(cap)
    preview = svc.prepare(data)
    assert preview["ready"] and preview["existing"] is None
    for bad in (
        {"preflight_sha256": preview["wire_sha256"], "explicit_confirm": "no", "original_authored_attested": True},
        {"preflight_sha256": preview["wire_sha256"], "explicit_confirm": "유료 JEV 1회 실행", "original_authored_attested": False},
        {"preflight_sha256": "0" * 64, "explicit_confirm": "유료 JEV 1회 실행", "original_authored_attested": True},
    ):
        with pytest.raises(OwnedReviewError, match="JEV_B_EXPLICIT_APPROVAL_OR_READINESS_REQUIRED"):
            asyncio.run(svc.execute(data, **bad))
    assert calls == []
    saved = asyncio.run(svc.execute(
        data, preflight_sha256=preview["wire_sha256"],
        explicit_confirm="유료 JEV 1회 실행", original_authored_attested=True,
    ))
    assert saved["status"] == "VALID"
    assert saved["disposition"] == "REVIEW_REQUIRED"
    assert saved["model_returned"] == "jev-test-real-1"
    assert saved["usage"] == {"input_tokens": 56, "output_tokens": 3}
    assert saved["cost_unknown"] is True and saved["cost_usd"] is None
    assert len(calls) == 1
    assert calls[0]["model"] == "jev-latest"
    assert set(calls[0]) == {"state", "questions", "model"}
    assert set(calls[0]["state"]) == {"authored_required_condition", "authored_observation"}
    assert "005930" not in json.dumps(calls[0], ensure_ascii=False)
    assert "2026-10-07" not in json.dumps(calls[0], ensure_ascii=False)
    assert db.read_bytes() == before
    again = asyncio.run(svc.execute(
        data, preflight_sha256=preview["wire_sha256"],
        explicit_confirm="유료 JEV 1회 실행", original_authored_attested=True,
    ))
    assert again["review_id"] == saved["review_id"]
    assert again["reused"] is True
    assert len(calls) == 1
    restarted = _service(db, tmp_path / "reviews", calls)
    assert restarted.latest(cap, 0, "KOSPI", "005930")["review_id"] == saved["review_id"]
    with pytest.raises(OwnedReviewError, match="JEV_B_ONE_REVIEW_PER_STOCK_INPUT_LOCKED"):
        restarted.prepare(_input(cap, observed_meaning="지금은 내가 다시 생각해보니 기준을 충족한 것 같다."))
    assert len(calls) == 1


def test_invalid_captured_identity_and_non_original_text_block(monkeypatch, tmp_path):
    db, cap = _capture(tmp_path)
    monkeypatch.setenv("STOCKSCOPE_JEV_B_ENABLE", "1")
    monkeypatch.setenv("JEV_API_KEY", "fake-unit-key")
    calls = []
    svc = _service(db, tmp_path / "reviews", calls)
    for data in (
        _input(cap, ticker="000000"),
        _input(cap, market="KOSDAQ"),
        _input(cap, sample_index=22),
        _input(cap, required_condition="https://external.example/news/page 수집 자료를 저장한다."),
        _input(cap, observed_meaning="짧음"),
    ):
        with pytest.raises(OwnedReviewError):
            svc.prepare(data)
    assert calls == []


def test_invalid_model_result_does_not_retry_or_claim_success(monkeypatch, tmp_path):
    db, cap = _capture(tmp_path)
    monkeypatch.setenv("STOCKSCOPE_JEV_B_ENABLE", "1")
    monkeypatch.setenv("JEV_API_KEY", "fake-unit-key")
    calls = []
    svc = _service(db, tmp_path / "reviews", calls, model="FAKE-JEV-MODEL")
    data = _input(cap)
    preview = svc.prepare(data)
    result = asyncio.run(svc.execute(
        data, preflight_sha256=preview["wire_sha256"],
        explicit_confirm="유료 JEV 1회 실행", original_authored_attested=True,
    ))
    assert result["status"] == "ERROR"
    assert result["reason"] == "JEV_B_RETURNED_MODEL_INVALID"
    assert len(calls) == 1
    restart = _service(db, tmp_path / "reviews", calls, model="jev-real")
    again = asyncio.run(restart.execute(
        data, preflight_sha256=preview["wire_sha256"],
        explicit_confirm="유료 JEV 1회 실행", original_authored_attested=True,
    ))
    assert again["reused"] is True
    assert len(calls) == 1


def test_pending_request_after_restart_is_never_repeated(monkeypatch, tmp_path):
    db, cap = _capture(tmp_path)
    svc = _service(db, tmp_path / "reviews", [])
    data = _input(cap)
    preview = svc.prepare(data)
    svc.store_dir.mkdir(parents=True)
    original = {
        "version": preview["version"], "review_id": preview["review_id"],
        "selected_stock": preview["selected_stock"],
        "status": "PENDING", "wire_sha256": preview["wire_sha256"],
        "input_sha256": preview["input_sha256"], "started_at": "2026-10-30T00:00:00+00:00",
    }
    svc._path(preview["review_id"]).write_text(json.dumps(original), encoding="utf-8")
    loaded = svc.lookup(preview["review_id"])
    assert loaded["status"] == "PENDING_OR_INTERRUPTED"
    assert loaded["reason"] == "JEV_B_BILLING_UNKNOWN_NO_AUTORETRY"
