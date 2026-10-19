"""S31-D offline stress of the EXISTING S3 Scanner-review eligibility contract.

All inputs are authored synthetic examples. The actual S3
build_scanner_review_input function is exercised without a model, market feed,
SQLite, API keys, orders, or touching Scanner/Strategy/Risk source code.

This is an integration/contract regression test, NOT a backtest, a live Scanner
execution, a TypeSafe evaluation, or proof of investing performance.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Callable

from app.jev.decision_reviewer_offline import (
    DecisionReviewContractError, build_scanner_review_input,
)
from app.prospective.models import digest_json
from app.simulation.strategy_governance import current_strategy_definitions
from app.strategy.condition_semantics import condition_sources
from app.strategy.semantic_source_v2 import build_semantic_source_v2

VERSION = "JEV_ACT2_S31D_S3_SYNTHETIC_CONTRACT_STRESS_V1"
DATE = "2026-10-08"
STRATEGY = "trend_following"
PROTOCOL_ID = "S31D-SYNTHETIC-LOCAL-NO-PROVIDER"

# Deliberately no simulated post-open prices, market crash data, or fabricated
# JEV classifications. S3 doesn't enforce a market-release-time clock or
# independent post-signal outcome evidence.
UNMEASURED = (
    "INTRADAY_CRASH_RISK_REQUIRES_MARKET_AND_TIME_PROOF",
    "LIVE_QUOTE_STALENESS_REQUIRES_SOURCE_TIMESTAMP_AND_QUOTE",
    "FORWARD_RETURN_AND_JEV_INVESTMENT_UPLIFT_NOT_AVAILABLE",
    "SAME_CASE_ACTUAL_JEV_RESPONSES_NOT_AVAILABLE",
)


def _base_source() -> tuple[dict[str, Any], dict[str, Any]]:
    # Use real registered strategy definition and condition semantic builder.
    # This creates a *fake* snapshot for the actual S3 adapter, never calls
    # the real scanner service to fetch securities.
    definition = next(
        d for d in current_strategy_definitions()
        if d.strategy_key == STRATEGY
    )
    sources = list(condition_sources(STRATEGY))
    candidate: dict[str, Any] = {
        "market": "KOSPI", "code": "000001", "name": "synthetic-only",
        "strategy": STRATEGY, "action": "ENTRY_CANDIDATE",
        "candidate_state": "READY", "decision_status": "READY",
        "data_date": DATE,
        "strategy_version_id": definition.strategy_version_id,
        "strategy_definition_hash": definition.definition_hash,
        "priority": {"rank": 1, "tier": "READY"},
        "conditions": {
            "passed": len(sources), "total": len(sources),
            "missing": 0, "top_missing": [],
        },
        "risk": {"status": "READY", "warning": False},
        "entry_risk_guide": {"price_rule": {
            "basis": "합성 전략 기준선 위", "semantic_role": "STRATEGY_REFERENCE",
            "executable_entry_range": False,
        }},
        "semantic_policy_provenance": {
            "status": "VERIFIED_PINNED_EXECUTION",
            "policy_id": "synthetic-policy",
            "policy_hash": "synthetic-policy-hash",
        },
        "semantic_condition_evidence": {
            "source": "SCANNER_REPRO_EVIDENCE",
            "strategy_key": STRATEGY,
            "passed": len(sources), "total": len(sources), "missing": 0,
            "items": [
                {"condition_id": f"condition-{i}",
                 "source_condition": condition, "status": "PASS"}
                for i, condition in enumerate(sources, 1)
            ],
        },
    }
    candidate["semantic_source_v2"] = build_semantic_source_v2(candidate)
    if candidate["semantic_source_v2"]["readiness"]["q2_status"] != "COMPLETE":
        raise ValueError("S31D_SYNTHETIC_CONTRACT_FIXTURE_NOT_READY")

    capture = {
        "id": "s31d-synthetic-capture", "status": "COMPLETE",
        "actual_data_date": DATE, "horizon_intent": "SHORT",
        "request": {
            "selection_policy_id": "synthetic-policy",
            "selection_policy_hash": "synthetic-policy-hash",
        },
    }
    sample = {
        "capture_run_id": capture["id"], "sample_index": 0,
        "market": candidate["market"], "ticker": candidate["code"],
        "name": candidate["name"], "rank": 1, "strategy": STRATEGY,
        "decision_status": "READY", "candidate_state": "READY",
        "action": "ENTRY_CANDIDATE", "signal_date": DATE,
        "snapshot": candidate, "snapshot_hash": digest_json(candidate),
    }
    return capture, sample


def _recompute_sample_hash(_: dict[str, Any], sample: dict[str, Any]) -> None:
    sample["snapshot_hash"] = digest_json(sample["snapshot"])


def _no_change(_: dict[str, Any], sample: dict[str, Any]) -> None:
    _recompute_sample_hash(_, sample)


def _blocked_risk(_: dict[str, Any], sample: dict[str, Any]) -> None:
    sample["snapshot"]["risk"]["status"] = "BLOCK"
    _recompute_sample_hash(_, sample)


def _blocked_guide(_: dict[str, Any], sample: dict[str, Any]) -> None:
    sample["snapshot"]["entry_risk_guide"]["action"] = {"status": "RISK_BLOCKED"}
    _recompute_sample_hash(_, sample)


def _warning(_: dict[str, Any], sample: dict[str, Any]) -> None:
    sample["snapshot"]["risk"]["warning"] = True
    _recompute_sample_hash(_, sample)


def _risk_missing(_: dict[str, Any], sample: dict[str, Any]) -> None:
    sample["snapshot"]["risk"].pop("warning")
    _recompute_sample_hash(_, sample)


def _date_mismatch(_: dict[str, Any], sample: dict[str, Any]) -> None:
    sample["snapshot"]["data_date"] = "2026-10-09"
    _recompute_sample_hash(_, sample)


def _policy_missing(_: dict[str, Any], sample: dict[str, Any]) -> None:
    sample["snapshot"].pop("semantic_policy_provenance")
    _recompute_sample_hash(_, sample)


def _policy_pin(capture: dict[str, Any], _: dict[str, Any]) -> None:
    capture["request"]["selection_policy_hash"] = "different-policy-hash"


def _condition_evidence_missing(_: dict[str, Any], sample: dict[str, Any]) -> None:
    sample["snapshot"]["semantic_condition_evidence"]["items"][0]["status"] = "FAIL"
    _recompute_sample_hash(_, sample)


def _semantic_hash_tamper(_: dict[str, Any], sample: dict[str, Any]) -> None:
    sample["snapshot"]["semantic_source_v2"]["source_snapshot_hash"] = "tampered"
    _recompute_sample_hash(_, sample)


def _strategy_forgery(_: dict[str, Any], sample: dict[str, Any]) -> None:
    sample["snapshot"]["strategy_version_id"] = "forged"
    _recompute_sample_hash(_, sample)


def _snapshot_hash_tamper(_: dict[str, Any], sample: dict[str, Any]) -> None:
    sample["snapshot"]["risk"]["warning"] = True
    # Deliberately do NOT update the independently frozen snapshot hash.


# Explicitly enumerated expectations, not model-generated expected labels.
# The warning case documents a S3 contract boundary, NOT an authorization to
# trade. Risk warnings may require a separate review policy.
CASES: tuple[tuple[str, Callable[..., None], str], ...] = (
    ("consistent_complete", _no_change, "OFFLINE_INSPECTABLE_ONLY"),
    ("risk_block", _blocked_risk, "RISK_BLOCKED_OUT_OF_SCOPE"),
    ("guide_risk_block", _blocked_guide, "RISK_BLOCKED_OUT_OF_SCOPE"),
    ("risk_warning_true", _warning, "OFFLINE_INSPECTABLE_ONLY"),
    ("risk_warning_missing", _risk_missing, "BASELINE_RISK_MISSING"),
    ("eod_date_mismatch", _date_mismatch, "FUTURE_OR_MISMATCHED_EVIDENCE_DATE"),
    ("policy_evidence_missing", _policy_missing, "POLICY_PROVENANCE_UNVERIFIED"),
    ("policy_pin_mismatch", _policy_pin, "POLICY_PIN_MISMATCH"),
    ("condition_pass_proof_mismatch", _condition_evidence_missing, "ENGINE_PASS_PROOF_MISMATCH"),
    ("semantic_source_hash_tampered", _semantic_hash_tamper, "SEMANTIC_SOURCE_V2_HASH_MISMATCH"),
    ("strategy_identity_forged", _strategy_forgery, "STRATEGY_IDENTITY_MISMATCH"),
    ("original_snapshot_hash_tampered", _snapshot_hash_tamper, "SNAPSHOT_HASH_MISMATCH"),
)


def run_s31d_contract_stress() -> dict[str, Any]:
    capture, sample = _base_source()
    source_identity = digest_json({"capture": capture, "sample": sample})
    rows: list[dict[str, Any]] = []
    for case_id, mutate, expected in CASES:
        # Every mutation affects a fresh DEEP COPY, never stored user facts.
        trial_capture, trial_sample = deepcopy((capture, sample))
        mutate(trial_capture, trial_sample)
        try:
            projection = build_scanner_review_input(
                trial_capture, trial_sample, protocol_id=PROTOCOL_ID,
            )
            observed = projection["status"]
        except DecisionReviewContractError as exc:
            observed = exc.code
        rows.append({
            "scenario": case_id,
            "expected_s3_contract_result": expected,
            "observed_s3_contract_result": observed,
            "contract_expectation_match": observed == expected,
            "risk_warning_accepted_without_s3_rejection": (
                case_id == "risk_warning_true"
                and observed == "OFFLINE_INSPECTABLE_ONLY"
            ),
            "actual_jev_response": None,
            "market_outcome": None,
            "real_stock_data_used": False,
        })
    if digest_json({"capture": capture, "sample": sample}) != source_identity:
        raise ValueError("S31D_SOURCE_MUTATED")
    passed = sum(x["contract_expectation_match"] for x in rows)
    return {
        "version": VERSION,
        "status": (
            "SYNTHETIC_S3_CONTRACT_STRESS_PASS" if passed == len(rows)
            else "HOLD_S3_CONTRACT_DRIFT"
        ),
        "scope": "SYNTHETIC_S3_CONTRACT_ONLY",
        "actual_scanner_service_executed": False,
        "actual_s3_projection_function_executed": True,
        "real_stock_provider_eligible": False,
        "new_jev_provider_calls": 0,
        "source_market_data_used": False,
        "production_db_writes": 0,
        "research_db_writes": 0,
        "orders": 0,
        "scenario_count": len(rows),
        "contract_expectations_met": passed,
        "risk_warning_boundary_is_not_trade_permission": True,
        "s3_risk_warning_remains_inspectable": next(
            r["risk_warning_accepted_without_s3_rejection"]
            for r in rows if r["scenario"] == "risk_warning_true"
        ),
        "cases": rows,
        "unmeasured": list(UNMEASURED),
        "jev_comparison_eligible": False,
        "investment_uplift_proven": False,
        "note": (
            "실제 S3 계약 검사 함수만 호출한 합성 시나리오 회귀검사입니다. "
            "Risk warning은 S3의 hard block과 다르며, 외부 전송·투자 승인 근거가 아닙니다. "
            "S6 JEV 응답과는 입력이 달라 성능 쌍별 비교가 불가능합니다."
        ),
    }
