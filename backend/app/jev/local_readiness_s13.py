"""S13: one-command, read-only gate for the actual local Scanner→JEV pipeline.

This cannot approve Q7, repair historical snapshots, or authorize an AI provider.
It separates the *effective current selection policy* from immutable past
captures. Counts are complete only when every selected capture fits the limit.
"""
from __future__ import annotations

from collections import Counter
from pathlib import Path
import sqlite3
from typing import Any

from app.simulation.strategy_change import production_blocked_approval_protocol
from app.strategy.production_selection_policy import (
    DEFAULT_RUNTIME_DIR,
    ProductionStrategySelectionRegistry,
    SelectionPolicyError,
)
from .decision_reviewer_offline import DecisionReviewContractError
from .local_evidence_audit import diagnose_candidate
from .scanner_integrity_s7_1 import assess_frozen_candidate
from .scanner_shadow_s7 import load_frozen_candidates


VERSION = "JEV_LOCAL_PIPELINE_READINESS_S13_V1"
_MAX_CAPTURES = 20
_MAX_SAMPLES = 500
_REQUIRED = frozenset({
    "prospective_capture_run", "prospective_recommendation_sample",
})
_CATEGORIES = ("LOCAL_VALIDATED", "LEGACY_LIMITED", "INVALID")


def _result(status: str, **details: Any) -> dict[str, Any]:
    return {
        "version": VERSION,
        "status": status,
        "provider_status": "PROVIDER_HOLD",
        "actual_provider_calls": 0,
        "db_writes": 0,
        "investment_improvement_verified": False,
        "production_policy_changed": False,
        **details,
    }


def _safe_code(value: Any) -> str:
    # Never surface dynamic error text, candidate names, prices or secrets.
    if (type(value) is str and 1 <= len(value) <= 80
            and all(ch in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_" for ch in value)):
        return value
    return "UNSPECIFIED_DIAGNOSTIC"


def _current_policy_state(simulation_db: Path, runtime_dir: Path) -> dict[str, Any]:
    approval = production_blocked_approval_protocol()
    state: dict[str, Any] = {
        "q7_activation_eligible": approval.activation_eligible,
        "q7_precommitted": approval.q7_precommitted,
        "selection_policy_source": "UNRESOLVED",
        "active_policy_effective": False,
        "fallback_reason": None,
    }
    try:
        registry = ProductionStrategySelectionRegistry(
            simulation_db=simulation_db, runtime_dir=runtime_dir,
        )
        # The pinned policy also checks current production baseline identity.
        pin = registry.pin_active_selection_policy()
        state.update({
            "selection_policy_source": pin.policy_source,
            "active_policy_effective": pin.policy_source in {
                "ACTIVE_SELECTION_POLICY", "ROLLBACK_FALLBACK",
            },
            "fallback_reason": pin.fallback_reason,
        })
    except (SelectionPolicyError, OSError, ValueError):
        state["selection_policy_source"] = "POLICY_RESOLUTION_FAILED"
    return state


def diagnose_local_readiness(
    simulation_db: Path,
    *,
    runtime_dir: Path | None = None,
) -> dict[str, Any]:
    """Check local approval/policy and *frozen* capture evidence without writes.

    Never turns an old invalid/legacy capture into locally validated evidence.
    Reads up to 20 most recent COMPLETE captures, with a strict <500 row bound
    per capture. A partial audit must not claim full capture coverage.
    """
    db = Path(simulation_db).resolve()
    policy = _current_policy_state(db, Path(runtime_dir or DEFAULT_RUNTIME_DIR))
    if not db.is_file():
        return _result("NO_LOCAL_SIMULATION_DB", policy=policy)

    try:
        with sqlite3.connect(db.as_uri() + "?mode=ro", uri=True, timeout=10) as conn:
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA query_only=ON")
            existing = {str(x["name"]) for x in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )}
            if not _REQUIRED <= existing:
                return _result("PROSPECTIVE_SCHEMA_NOT_READY", policy=policy)
            captures_total = int(conn.execute(
                "SELECT COUNT(*) FROM prospective_capture_run WHERE status='COMPLETE'"
            ).fetchone()[0])
            rows = conn.execute(
                "SELECT r.id, COUNT(s.sample_index) AS sample_count "
                "FROM prospective_capture_run r "
                "LEFT JOIN prospective_recommendation_sample s ON s.capture_run_id=r.id "
                "WHERE r.status='COMPLETE' GROUP BY r.id "
                "ORDER BY r.completed_at DESC, r.id DESC LIMIT ?",
                (_MAX_CAPTURES,),
            ).fetchall()
    except sqlite3.Error:
        return _result("LOCAL_SIMULATION_READ_UNAVAILABLE", policy=policy)

    if not rows:
        return _result(
            "NO_COMPLETED_CAPTURE", policy=policy,
            total_complete_captures=0, audited_captures=0,
        )

    if any(int(row["sample_count"]) >= _MAX_SAMPLES for row in rows):
        return _result(
            "CAPTURE_SAMPLE_LIMIT_REACHED", policy=policy,
            total_complete_captures=captures_total,
            audited_captures=0,
            capture_limit=_MAX_CAPTURES, sample_limit=_MAX_SAMPLES,
            counts_complete=False,
        )

    counts: Counter[str] = Counter()
    invalid_codes: Counter[str] = Counter()
    legacy_codes: Counter[str] = Counter()
    entries = 0
    references = 0
    inspected = 0

    try:
        for row in rows:
            pairs = load_frozen_candidates(
                db, capture_id=str(row["id"]), limit=_MAX_SAMPLES,
            )
            # A changed database or incomplete loader must not invent totals.
            if len(pairs) != int(row["sample_count"]):
                return _result(
                    "CAPTURE_CHANGED_DURING_READ", policy=policy,
                    counts_complete=False,
                )
            inspected += len(pairs)
            for capture, sample in pairs:
                if sample.get("action") != "ENTRY_CANDIDATE":
                    references += 1
                    continue
                entries += 1
                audit = diagnose_candidate(capture, sample)
                category = audit.get("category")
                if category not in _CATEGORIES:
                    return _result(
                        "CAPTURE_AUDIT_CONTRACT_INVALID", policy=policy,
                        counts_complete=False,
                    )
                counts[category] += 1
                if category == "LOCAL_VALIDATED":
                    continue
                if audit.get("reason_code") in (
                    "SNAPSHOT_HASH_MISMATCH", "CAPTURE_IDENTITY_MISMATCH",
                ):
                    invalid_codes[_safe_code(audit["reason_code"])] += 1
                    continue
                try:
                    integrity = assess_frozen_candidate(capture, sample)
                    if integrity.get("category") != category:
                        return _result(
                            "CAPTURE_AUDIT_CONTRACT_INVALID", policy=policy,
                            counts_complete=False,
                        )
                    destination = (
                        legacy_codes if category == "LEGACY_LIMITED"
                        else invalid_codes
                    )
                    for code in set(integrity.get("codes", [])):
                        destination[_safe_code(code)] += 1
                except (DecisionReviewContractError, KeyError, TypeError, ValueError) as exc:
                    invalid_codes[_safe_code(getattr(exc, "code", "INTEGRITY_CHECK_FAILED"))] += 1
    except (DecisionReviewContractError, sqlite3.Error, KeyError, TypeError, ValueError):
        return _result(
            "CAPTURE_AUDIT_FAILED", policy=policy,
            counts_complete=False,
        )

    if not policy["active_policy_effective"]:
        status = "NO_ACTIVE_SELECTION_POLICY"
        next_action = (
            "Q7_APPROVAL_PROTOCOL_UNAPPROVED"
            if not policy["q7_activation_eligible"] or not policy["q7_precommitted"]
            else "APPROVED_ACTIVE_POLICY_REQUIRED"
        )
    elif counts["LOCAL_VALIDATED"]:
        status = "LOCAL_BASELINE_READY_PROVIDER_HOLD"
        next_action = "OBSERVE_ONLY_NO_REAL_PROVIDER_AUTHORIZATION"
    else:
        status = "NO_LOCALLY_VALIDATED_CANDIDATE"
        next_action = "VERIFY_NEW_CAPTURE_POLICY_RANK_ENGINE_EVIDENCE"

    return _result(
        status,
        policy=policy,
        next_action=next_action,
        total_complete_captures=captures_total,
        audited_captures=len(rows),
        counts_complete=captures_total == len(rows),
        capture_limit=_MAX_CAPTURES,
        sample_limit=_MAX_SAMPLES,
        inspected_samples=inspected,
        entry_candidates=entries,
        reference_only=references,
        categories={name: counts[name] for name in _CATEGORIES},
        invalid_reason_counts=dict(sorted(invalid_codes.items())),
        legacy_limitation_counts=dict(sorted(legacy_codes.items())),
        original_captures_modified=False,
    )
