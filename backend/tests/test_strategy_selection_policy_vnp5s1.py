from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from app.strategy.models import StrategyName
from app.strategy.production_selection_policy import (
    LEGACY_POLICY_ID,
    ProductionStrategySelectionRegistry,
    SelectionPolicyError,
    legacy_selection_policy,
)


NOW = "2026-09-28T01:30:00+00:00"


def _operating(
    *,
    include_breakout: bool = True,
) -> list[dict]:
    keys = [
        item.value
        for item in StrategyName
        if item is not StrategyName.NO_TRADE
    ]
    if not include_breakout:
        keys.remove(StrategyName.BREAKOUT.value)
    return [
        {
            "strategy_version_id": f"version-{key}",
            "strategy_key": key,
            "definition_hash": f"hash-{key}",
        }
        for key in keys
    ]


def _proposal(
    proposal_id: str,
    *,
    include_breakout: bool,
    proposal_hash: str,
    evidence_hash: str,
    registry_hash: str,
    intent_hash: str,
    rollback_hash: str,
) -> dict:
    return {
        "id": proposal_id,
        "proposal_hash": proposal_hash,
        "proposal_integrity": "MATCH",
        "evidence_bundle_hash": evidence_hash,
        "base_registry_snapshot_hash": registry_hash,
        "candidate_policy_intent_hash": intent_hash,
        "rollback_basis_hash": rollback_hash,
        "candidate_policy_intent": {
            "operating_strategies": _operating(
                include_breakout=include_breakout
            ),
            "risk_gate_preserved": True,
            "no_trade_safety_path_preserved": True,
            "score_formula_changed": False,
            "candidate_priority_changed": False,
            "production_activation_performed": False,
        },
        "rollback_basis": {
            "operating_strategies": _operating(
                include_breakout=True
            ),
            "scanner_baseline_id": "BASELINE-A",
            "production_fingerprint": "PROD-A",
            "production_policy_fingerprint": "POLICY-A",
        },
        "scanner_baseline_id": "BASELINE-A",
        "production_fingerprint": "PROD-A",
        "production_policy_fingerprint": "POLICY-A",
        "created_at": NOW,
    }


def _approval(
    approval_id: str,
    *,
    proposal: dict,
    approval_hash: str,
    test_only: bool = True,
) -> dict:
    return {
        "id": approval_id,
        "approval_hash": approval_hash,
        "approval_integrity": "MATCH",
        "proposal_id": proposal["id"],
        "proposal_hash": proposal["proposal_hash"],
        "evidence_bundle_hash": proposal["evidence_bundle_hash"],
        "registry_snapshot_hash": proposal[
            "base_registry_snapshot_hash"
        ],
        "candidate_policy_intent_hash": proposal[
            "candidate_policy_intent_hash"
        ],
        "rollback_basis_hash": proposal["rollback_basis_hash"],
        "approved_at": NOW,
        "approval_context": {
            "protocol": {
                "test_only": test_only,
            },
            "research_validation_approval_only": True,
            "production_activation_performed": False,
        },
    }


class _FakeChangeService:
    def __init__(self, rows: dict[str, tuple[dict, dict]]) -> None:
        self.rows = rows
        self.calls = 0
        self.stale_proposals: set[str] = set()

    def get_approval(self, approval_id: str) -> dict:
        self.calls += 1
        return dict(self.rows[approval_id][0])

    def get_proposal(self, proposal_id: str) -> dict:
        self.calls += 1
        for _, proposal in self.rows.values():
            if proposal["id"] == proposal_id:
                return dict(proposal)
        raise KeyError(proposal_id)

    def verify_proposal(self, proposal_id: str) -> dict:
        self.calls += 1
        return {
            "proposal_id": proposal_id,
            "status": (
                "STALE"
                if proposal_id in self.stale_proposals
                else "CURRENT"
            ),
            "reasons": (
                ["TEST_STALE"]
                if proposal_id in self.stale_proposals
                else []
            ),
        }


def _fake_rows() -> dict[str, tuple[dict, dict]]:
    p1 = _proposal(
        "proposal-1",
        include_breakout=False,
        proposal_hash="proposal-hash-1",
        evidence_hash="evidence-hash-1",
        registry_hash="registry-hash-1",
        intent_hash="intent-hash-1",
        rollback_hash="rollback-hash-1",
    )
    p2 = _proposal(
        "proposal-2",
        include_breakout=True,
        proposal_hash="proposal-hash-2",
        evidence_hash="evidence-hash-2",
        registry_hash="registry-hash-2",
        intent_hash="intent-hash-2",
        rollback_hash="rollback-hash-2",
    )
    return {
        "approval-1": (
            _approval(
                "approval-1",
                proposal=p1,
                approval_hash="approval-hash-1",
            ),
            p1,
        ),
        "approval-2": (
            _approval(
                "approval-2",
                proposal=p2,
                approval_hash="approval-hash-2",
            ),
            p2,
        ),
    }


def _registry(
    tmp_path: Path,
    *,
    service: _FakeChangeService | None = None,
    allow_test_activation: bool = True,
) -> ProductionStrategySelectionRegistry:
    return ProductionStrategySelectionRegistry(
        runtime_dir=tmp_path / "selection",
        change_service=service,
        allow_test_activation=allow_test_activation,
        clock=lambda: NOW,
    )


def test_resolver_without_runtime_state_uses_legacy_current_ten_without_simulation(
    tmp_path: Path,
):
    fake = _FakeChangeService(_fake_rows())
    registry = _registry(tmp_path, service=fake)

    resolution = registry.resolve_active_selection_policy()

    assert fake.calls == 0
    assert resolution.policy_source == "LEGACY_CURRENT_10_FALLBACK"
    assert resolution.fallback_used is True
    assert resolution.policy["policy_id"] == LEGACY_POLICY_ID
    keys = {
        row["strategy_key"]
        for row in resolution.policy["operating_strategies"]
    }
    assert len(keys) == 10
    assert StrategyName.NO_TRADE.value not in keys
    assert (
        resolution.policy["selection_semantics"][
            "risk_gate_preserved"
        ]
        is True
    )
    assert (
        resolution.policy["selection_semantics"][
            "candidate_priority_changed"
        ]
        is False
    )


def test_test_approval_cannot_activate_without_explicit_test_gate(
    tmp_path: Path,
):
    fake = _FakeChangeService(_fake_rows())
    registry = _registry(
        tmp_path,
        service=fake,
        allow_test_activation=False,
    )

    with pytest.raises(SelectionPolicyError) as exc:
        registry.activate_approved_policy(
            approval_artifact_id="approval-1",
            expected_active_policy_id=None,
        )

    assert exc.value.code == "TEST_APPROVAL_ACTIVATION_FORBIDDEN"
    assert not registry.active_path.exists()


def test_first_activation_creates_target_and_rollback_snapshots(
    tmp_path: Path,
):
    fake = _FakeChangeService(_fake_rows())
    registry = _registry(tmp_path, service=fake)

    result = registry.activate_approved_policy(
        approval_artifact_id="approval-1",
        expected_active_policy_id=None,
    )

    assert result["changed"] is True
    active = result["active_reference"]
    assert active["generation"] == 1
    assert active["rollback_policy_id"]
    assert (
        active["rollback_policy_id"]
        != active["active_policy_id"]
    )

    resolution = registry.resolve_active_selection_policy()
    assert resolution.policy_source == "ACTIVE_SELECTION_POLICY"
    assert resolution.fallback_used is False
    keys = {
        row["strategy_key"]
        for row in resolution.policy["operating_strategies"]
    }
    assert StrategyName.BREAKOUT.value not in keys
    assert StrategyName.NO_TRADE.value not in keys

    rollback, reason = registry._load_snapshot(  # noqa: SLF001
        active["rollback_policy_id"],
        active["rollback_policy_hash"],
    )
    assert reason is None
    assert rollback is not None
    assert len(rollback["operating_strategies"]) == 10


def test_same_approval_is_idempotent_and_cas_is_enforced(tmp_path: Path):
    fake = _FakeChangeService(_fake_rows())
    registry = _registry(tmp_path, service=fake)

    first = registry.activate_approved_policy(
        approval_artifact_id="approval-1",
        expected_active_policy_id=None,
    )
    active_id = first["active_reference"]["active_policy_id"]

    second = registry.activate_approved_policy(
        approval_artifact_id="approval-1",
        expected_active_policy_id=active_id,
    )
    assert second["changed"] is False
    assert second["active_reference"]["generation"] == 1

    with pytest.raises(SelectionPolicyError) as exc:
        registry.activate_approved_policy(
            approval_artifact_id="approval-2",
            expected_active_policy_id="wrong-policy",
        )
    assert exc.value.code == "ACTIVE_POLICY_CONFLICT"


def test_stale_proposal_blocks_activation(tmp_path: Path):
    fake = _FakeChangeService(_fake_rows())
    fake.stale_proposals.add("proposal-1")
    registry = _registry(tmp_path, service=fake)

    with pytest.raises(SelectionPolicyError) as exc:
        registry.activate_approved_policy(
            approval_artifact_id="approval-1",
            expected_active_policy_id=None,
        )
    assert exc.value.code == "APPROVAL_PROPOSAL_STALE"
    assert not registry.active_path.exists()


def test_corrupt_active_snapshot_resolves_to_recorded_rollback(
    tmp_path: Path,
):
    fake = _FakeChangeService(_fake_rows())
    registry = _registry(tmp_path, service=fake)
    result = registry.activate_approved_policy(
        approval_artifact_id="approval-1",
        expected_active_policy_id=None,
    )
    active = result["active_reference"]

    registry._snapshot_path(  # noqa: SLF001
        active["active_policy_id"]
    ).write_text("{}", encoding="utf-8")

    resolution = registry.resolve_active_selection_policy()
    assert resolution.policy_source == "ROLLBACK_FALLBACK"
    assert resolution.fallback_used is True
    assert (
        resolution.policy["policy_id"]
        == active["rollback_policy_id"]
    )


def test_corrupt_active_and_rollback_snapshots_resolve_to_legacy(
    tmp_path: Path,
):
    fake = _FakeChangeService(_fake_rows())
    registry = _registry(tmp_path, service=fake)
    result = registry.activate_approved_policy(
        approval_artifact_id="approval-1",
        expected_active_policy_id=None,
    )
    active = result["active_reference"]

    registry._snapshot_path(  # noqa: SLF001
        active["active_policy_id"]
    ).write_text("{}", encoding="utf-8")
    registry._snapshot_path(  # noqa: SLF001
        active["rollback_policy_id"]
    ).write_text("{}", encoding="utf-8")

    resolution = registry.resolve_active_selection_policy()
    assert resolution.policy_source == "LEGACY_CURRENT_10_FALLBACK"
    assert resolution.policy["policy_id"] == LEGACY_POLICY_ID


def test_explicit_rollback_is_one_way_until_new_activation(tmp_path: Path):
    fake = _FakeChangeService(_fake_rows())
    registry = _registry(tmp_path, service=fake)
    activated = registry.activate_approved_policy(
        approval_artifact_id="approval-1",
        expected_active_policy_id=None,
    )
    first_active = activated["active_reference"]["active_policy_id"]
    rollback_id = activated["active_reference"]["rollback_policy_id"]

    rolled = registry.rollback_selection_policy(
        expected_active_policy_id=first_active
    )
    ref = rolled["active_reference"]
    assert ref["active_policy_id"] == rollback_id
    assert ref["rollback_policy_id"] is None
    assert ref["last_deactivated_policy_id"] == first_active
    assert ref["generation"] == 2

    with pytest.raises(SelectionPolicyError) as exc:
        registry.rollback_selection_policy(
            expected_active_policy_id=rollback_id
        )
    assert exc.value.code == "ROLLBACK_POLICY_NOT_AVAILABLE"


def test_atomic_active_publish_failure_preserves_previous_active_reference(
    tmp_path: Path,
    monkeypatch,
):
    fake = _FakeChangeService(_fake_rows())
    registry = _registry(tmp_path, service=fake)
    first = registry.activate_approved_policy(
        approval_artifact_id="approval-1",
        expected_active_policy_id=None,
    )
    first_id = first["active_reference"]["active_policy_id"]
    original_bytes = registry.active_path.read_bytes()

    real_replace = os.replace

    def fail_active_replace(src, dst):
        if Path(dst) == registry.active_path:
            raise PermissionError(5, "Access is denied")
        return real_replace(src, dst)

    monkeypatch.setattr(
        "app.strategy.production_selection_policy.os.replace",
        fail_active_replace,
    )

    with pytest.raises(SelectionPolicyError) as exc:
        registry.activate_approved_policy(
            approval_artifact_id="approval-2",
            expected_active_policy_id=first_id,
        )
    assert exc.value.code == "SELECTION_POLICY_ATOMIC_PUBLISH_FAILED"
    assert registry.active_path.read_bytes() == original_bytes

    resolution = registry.resolve_active_selection_policy()
    assert resolution.policy_source == "ACTIVE_SELECTION_POLICY"
    assert resolution.policy["policy_id"] == first_id


def test_selection_semantics_change_is_rejected_before_publish(
    tmp_path: Path,
):
    rows = _fake_rows()
    approval, proposal = rows["approval-1"]
    proposal = dict(proposal)
    proposal["candidate_policy_intent"] = dict(
        proposal["candidate_policy_intent"]
    )
    proposal["candidate_policy_intent"][
        "candidate_priority_changed"
    ] = True
    rows["approval-1"] = (approval, proposal)
    fake = _FakeChangeService(rows)
    registry = _registry(tmp_path, service=fake)

    with pytest.raises(SelectionPolicyError) as exc:
        registry.activate_approved_policy(
            approval_artifact_id="approval-1",
            expected_active_policy_id=None,
        )
    assert exc.value.code == "SELECTION_POLICY_SEMANTICS_CHANGED"


def test_legacy_policy_contract_excludes_no_trade():
    policy = legacy_selection_policy()
    assert policy["policy_id"] == LEGACY_POLICY_ID
    keys = [
        item["strategy_key"]
        for item in policy["operating_strategies"]
    ]
    assert len(keys) == 10
    assert StrategyName.NO_TRADE.value not in keys



def test_pin_uses_active_policy_when_baseline_identity_matches(tmp_path: Path):
    rows = _fake_rows()
    fake = _FakeChangeService(rows)
    baseline = {
        "scanner_baseline_id": "BASELINE-A",
        "production_fingerprint": "PROD-A",
        "production_policy_fingerprint": "POLICY-A",
    }
    registry = ProductionStrategySelectionRegistry(
        runtime_dir=tmp_path / "selection",
        change_service=fake,
        allow_test_activation=True,
        clock=lambda: NOW,
        baseline_identity_provider=lambda: dict(baseline),
    )

    activated = registry.activate_approved_policy(
        approval_artifact_id="approval-1",
        expected_active_policy_id=None,
    )
    pin = registry.pin_active_selection_policy()

    assert pin.policy_id == activated["active_policy"]["policy_id"]
    assert pin.policy_source == "ACTIVE_SELECTION_POLICY"
    assert pin.fallback_used is False
    assert "breakout" not in pin.operating_strategy_keys
    assert pin.strategy_reference("pullback") is not None


def test_pin_falls_back_to_rollback_when_active_baseline_mismatches(
    tmp_path: Path,
):
    rows = _fake_rows()
    approval2, proposal2 = rows["approval-2"]
    proposal2 = dict(proposal2)
    proposal2["scanner_baseline_id"] = "BASELINE-B"
    proposal2["production_fingerprint"] = "PROD-B"
    proposal2["production_policy_fingerprint"] = "POLICY-B"
    rows["approval-2"] = (approval2, proposal2)

    fake = _FakeChangeService(rows)
    baseline = {
        "scanner_baseline_id": "BASELINE-A",
        "production_fingerprint": "PROD-A",
        "production_policy_fingerprint": "POLICY-A",
    }
    registry = ProductionStrategySelectionRegistry(
        runtime_dir=tmp_path / "selection",
        change_service=fake,
        allow_test_activation=True,
        clock=lambda: NOW,
        baseline_identity_provider=lambda: dict(baseline),
    )
    first = registry.activate_approved_policy(
        approval_artifact_id="approval-1",
        expected_active_policy_id=None,
    )
    first_id = first["active_policy"]["policy_id"]
    second = registry.activate_approved_policy(
        approval_artifact_id="approval-2",
        expected_active_policy_id=first_id,
    )

    assert second["active_policy"]["scanner_baseline_id"] == "BASELINE-B"
    pin = registry.pin_active_selection_policy()
    assert pin.policy_id == first_id
    assert pin.policy_source == "ROLLBACK_FALLBACK"
    assert pin.fallback_used is True
    assert pin.fallback_reason == "ACTIVE_POLICY_BASELINE_MISMATCH"


def test_snapshot_rejects_unknown_strategy_key():
    snapshot = ProductionStrategySelectionRegistry._build_snapshot(  # noqa: SLF001
        source_kind="TEST",
        operating_strategies=[
            {
                "strategy_version_id": "unknown-v1",
                "strategy_key": "unknown_strategy",
                "definition_hash": "x",
            }
        ],
        selection_semantics={
            "risk_gate_preserved": True,
            "no_trade_safety_path_preserved": True,
            "score_formula_changed": False,
            "candidate_priority_changed": False,
        },
        scanner_baseline_id="BASELINE-A",
        production_fingerprint="PROD-A",
        production_policy_fingerprint="POLICY-A",
        proposal_id=None,
        proposal_hash=None,
        approval_artifact_id=None,
        approval_hash=None,
        created_at=NOW,
    )

    valid, reason = ProductionStrategySelectionRegistry.validate_snapshot(
        snapshot
    )
    assert valid is False
    assert reason == "POLICY_STRATEGY_KEY_UNSUPPORTED"
