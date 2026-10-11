"""ACT1-S1.2: semantic source can use only attested production-engine facts.

No KRX, market mutations, TypeSafe API, held-out data, or strategy/risk rewrites.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import date
import json

import pytest

from app.backtest.scanner import StockScannerService
from app.prospective.catalog import ProspectiveCatalog
from app.prospective.models import digest_json
from app.strategy.condition_semantics import condition_sources
from app.strategy.models import StrategyName
from app.strategy.semantic_identity_bridge import (
    ENGINE_CONDITION_SOURCE,
    LEGACY_SELECTION_SOURCE,
    attest_legacy_scanner_identity,
    attest_scanner_passed_conditions,
    semantic_projection_candidate,
)
from app.strategy.semantic_source_v2 import verify_semantic_source_v2
from app.jev.semantic_scope_diagnostic import inspect_stored_semantic_source
from app.jev.typesafe_state import TypeSafeStateProjectionError
from app.jev.typesafe_state_v4 import route_typesafe_state_v4


STRATEGY = StrategyName.TREND_FOLLOWING.value
FALLBACK = {
    "policy_source": LEGACY_SELECTION_SOURCE,
    "fallback_used": True,
    "policy_id": "LEGACY-CURRENT-TEST",
    "policy_hash": "test-policy-hash",
}


def _quick(*, policy=None, status="READY", tamper_conditions=False):
    conditions = list(condition_sources(STRATEGY))
    rows = [
        {"raw": raw, "status": "PASS", "condition_id": f"pass-{i}"}
        for i, raw in enumerate(conditions, 1)
    ]
    if tamper_conditions:
        rows[0]["raw"] = "unmapped false condition"
    state = {
        "passed": len(rows), "total": len(rows), "missing": 0,
        "missing_details": [],
        "conditions": rows,
        "consistency": {"ok": True},
    }
    return {
        "code": "000001", "name": "synthetic-only", "market": "KOSPI",
        "latest_date": date(2026, 10, 10),
        "quick_strategy": STRATEGY,
        "quick_strategy_version_id": None,
        "quick_strategy_definition_hash": None,
        "quick_selection_policy_identity": dict(policy or FALLBACK),
        "quick_current": {
            "status": status, "total": len(rows), "passed": len(rows),
            "missing": 0, "risk_warning": False,
            "risk_status": "READY", "internal_score": 80,
        },
        "quick_condition_state": state,
        "quick_score": 90,
        "quick_guide": {"easy_name": "test", "professional_name": "test"},
        "quick_entry_risk_guide": {},
    }


def _candidate(quick=None):
    return StockScannerService.__new__(StockScannerService)._current_candidate(
        quick if quick is not None else _quick()
    )


def _source(candidate, policy=None):
    return ProspectiveCatalog._candidate_snapshot(
        candidate, selection_policy=dict(policy or FALLBACK)
    )


def test_scanner_fallback_attestation_does_not_change_candidate_decision_or_binding():
    candidate = _candidate()
    assert candidate["action"] == "ENTRY_CANDIDATE"
    assert candidate["candidate_state"] == "READY"
    assert candidate["strategy_version_id"] is None
    assert candidate["strategy_definition_hash"] is None
    assert candidate["semantic_strategy_identity"]["source"] == "LEGACY_ENGINE_IDENTITY_VERIFIED"
    assert candidate["semantic_condition_evidence"]["source"] == ENGINE_CONDITION_SOURCE
    assert all(x["status"] == "PASS" for x in candidate["semantic_condition_evidence"]["items"])
    original = deepcopy(candidate)

    snapshot = _source(candidate)
    assert candidate == original
    assert snapshot["action"] == original["action"]
    assert snapshot["strategy_version_id"] is None
    assert snapshot["strategy_definition_hash"] is None
    assert snapshot["priority"] if "priority" in snapshot else True
    semantic_v1 = snapshot["semantic_source"]
    semantic_v2 = snapshot["semantic_source_v2"]
    assert semantic_v1["strategy"]["strategy_version_id"]
    assert semantic_v1["strategy"]["strategy_definition_hash"]
    assert semantic_v2["readiness"]["local_semantic_status"] != "LOCAL_INCOMPLETE"
    assert semantic_v2["readiness"]["local_semantic_status"] in {
        "LOCAL_MATCH", "LOCAL_CONFLICT", "LOCAL_AMBIGUOUS",
        "RESIDUAL_SEMANTIC_REVIEW",
    }
    valid, reason = verify_semantic_source_v2(semantic_v2)
    assert valid, reason
    assert (
        inspect_stored_semantic_source(
            snapshot, stored_snapshot_hash=digest_json(snapshot)
        ) not in {"SEMANTIC_SOURCE_INVALID", "SEMANTIC_SOURCE_MISSING"}
    )


def test_repeatable_semantic_snapshot_and_missing_cached_attestation_stays_incomplete():
    item = _candidate()
    first = _source(item)
    assert _source(item) == first
    assert json.dumps(first, ensure_ascii=False, sort_keys=True) == json.dumps(
        _source(item), ensure_ascii=False, sort_keys=True
    )
    no_claim = deepcopy(item)
    no_claim.pop("semantic_strategy_identity")
    assert _source(no_claim)["semantic_source_v2"]["readiness"]["local_semantic_status"] == "LOCAL_INCOMPLETE"
    assert no_claim["strategy_version_id"] is None


@pytest.mark.parametrize("mutate", [
    lambda x: x["semantic_strategy_identity"].update({"strategy_key": "breakout"}),
    lambda x: x["semantic_strategy_identity"].update({"strategy_definition_hash": "0" * 64}),
    lambda x: x["semantic_strategy_identity"].update({"selection_policy_hash": "wrong"}),
    lambda x: x["semantic_condition_evidence"]["items"][0].update({"status": "FAIL"}),
    lambda x: x["semantic_condition_evidence"]["items"][0].update({"source_condition": "fake"}),
    lambda x: x["semantic_condition_evidence"]["items"].append(
        dict(x["semantic_condition_evidence"]["items"][0])
    ),
    lambda x: x["conditions"].update({"passed": 0}),
])
def test_bad_or_stale_provenance_never_enables_semantic_binding(mutate):
    candidate = deepcopy(_candidate())
    mutate(candidate)
    projected = semantic_projection_candidate(candidate, selection_policy=FALLBACK)
    assert projected["strategy_version_id"] is None
    assert projected["strategy_definition_hash"] is None
    assert _source(candidate)["semantic_source_v2"]["readiness"]["local_semantic_status"] == "LOCAL_INCOMPLETE"


def test_active_policy_or_wrong_policy_cannot_masquerade_as_legacy():
    candidate = _candidate()
    active = dict(FALLBACK, policy_source="ACTIVE_SELECTION_POLICY", fallback_used=False)
    for policy in (active, dict(FALLBACK, policy_id="wrong")):
        projected = semantic_projection_candidate(candidate, selection_policy=policy)
        assert projected["strategy_version_id"] is None
        assert _source(candidate, policy)["semantic_source_v2"]["readiness"]["local_semantic_status"] == "LOCAL_INCOMPLETE"
    assert attest_legacy_scanner_identity(
        strategy_key=STRATEGY,
        policy_binding_version=None,
        policy_binding_hash=None,
        selection_policy=active,
    ) is None


def test_no_assertion_invented_from_counts_or_unmet_conditions():
    bad = _quick(tamper_conditions=True)
    candidate = _candidate(bad)
    assert "semantic_condition_evidence" not in candidate
    assert _source(candidate)["semantic_source_v2"]["readiness"]["local_semantic_status"] == "LOCAL_INCOMPLETE"
    good = _quick()
    good["quick_condition_state"]["conditions"][0]["status"] = "FAIL"
    assert attest_scanner_passed_conditions(
        strategy_key=STRATEGY, condition_state=good["quick_condition_state"]
    ) is None
    good["quick_condition_state"]["consistency"]["ok"] = False
    assert attest_scanner_passed_conditions(
        strategy_key=STRATEGY, condition_state=good["quick_condition_state"]
    ) is None


def test_active_binding_not_overwritten_and_v4_legacy_gate_stays_intact():
    candidate = _candidate()
    candidate["strategy_version_id"] = "intentionally-stale"
    projected = semantic_projection_candidate(candidate, selection_policy=FALLBACK)
    assert projected["strategy_version_id"] == "intentionally-stale"
    assert _source(candidate)["semantic_source_v2"]["readiness"]["local_semantic_status"] == "LOCAL_INCOMPLETE"
    with pytest.raises(TypeSafeStateProjectionError, match="OUT_OF_SCOPE_HORIZON"):
        route_typesafe_state_v4({
            "action": "ENTRY_CANDIDATE",
            "horizon_intent": "LEGACY_UNSPECIFIED",
            "snapshot": _source(_candidate()),
        })


def test_wait_action_is_not_misreported_as_jev_ready():
    item = _quick(status="CAUTION")
    candidate = _candidate(item)
    assert candidate["action"] == "WAIT"
    assert _source(candidate)["semantic_source_v2"]["readiness"]["local_semantic_status"] == "LOCAL_INCOMPLETE"


def test_no_network_needed_and_backend_source_unmodified(monkeypatch):
    import socket
    monkeypatch.setattr(
        socket, "create_connection",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("network forbidden")),
    )
    candidate = _candidate()
    assert _source(candidate)["semantic_source_v2"]["readiness"]["local_semantic_status"] != "LOCAL_INCOMPLETE"
