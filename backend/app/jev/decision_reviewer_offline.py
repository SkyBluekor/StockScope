"""JEV-ACT2-S3 offline Scanner Decision Reviewer proof-of-contract.

This module never initializes a model provider, creates/migrates a database,
runs Scanner, accesses Holdout, or enables the user-facing JEV API. The
historical V4 residual-only reviewer remains completely independent.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import date
import json
from pathlib import Path
import re
import sqlite3
from typing import Any

from app.prospective.models import digest_json
from app.strategy.semantic_policy_provenance import VERIFIED_POLICY
from app.strategy.semantic_source_v2 import verify_semantic_source_v2


INPUT_VERSION = "JEV_SCANNER_REVIEW_INPUT_V1"
OUTPUT_VERSION = "JEV_SCANNER_REVIEW_OUTPUT_V1"
ADAPTER_VERSION = "JEV_ACT2_S3_OFFLINE_PROJECTION_V1"
ALLOWED_DECISIONS = frozenset({"PASS_THROUGH", "REVIEW_REQUIRED", "ABSTAIN"})
ABSTAIN_REASONS = frozenset({
    "INSUFFICIENT_EVIDENCE", "CONFLICT_UNRESOLVED", "OUT_OF_SCOPE", "STALE_INPUT",
})
REASON_CODES = frozenset({
    "CONDITION_ALIGNMENT", "CONDITION_CONFLICT", "ENTRY_CONTEXT_CONFLICT",
    "RISK_CAUTION", "EVIDENCE_LIMITATION",
})
BLOCKED_RISK_STATUSES = frozenset({
    "BLOCK", "BLOCKED", "RISK_BLOCKED", "REFERENCE_ONLY",
})
_EXPLICIT_HORIZONS = frozenset({"SHORT", "MEDIUM"})
_NUMBER = re.compile(r"(?<![A-Za-z0-9])\d+(?:\.\d+)?")
_MAX_REASONS = 10


class DecisionReviewContractError(ValueError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _date(value: Any) -> date:
    if not isinstance(value, str):
        raise DecisionReviewContractError("SIGNAL_DATE_INVALID")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise DecisionReviewContractError("SIGNAL_DATE_INVALID") from exc
    if value != parsed.isoformat():
        raise DecisionReviewContractError("SIGNAL_DATE_INVALID")
    return parsed


def load_canonical_candidate_readonly(
    simulation_db: Path, *, capture_id: str, sample_index: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Read a real Prospective schema with SQLite mode=ro (including duplicates)."""
    if not capture_id or sample_index < 0:
        raise DecisionReviewContractError("CAPTURE_REFERENCE_INVALID")
    path = Path(simulation_db).resolve()
    if not path.is_file():
        raise DecisionReviewContractError("CAPTURE_DB_NOT_FOUND")
    try:
        with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True) as conn:
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA query_only=ON")
            row = conn.execute(
                "SELECT * FROM prospective_capture_run WHERE id=?", (capture_id,)
            ).fetchone()
            if row is None:
                raise DecisionReviewContractError("CAPTURE_NOT_FOUND")
            capture = dict(row)
            if capture["status"] == "DUPLICATE":
                canonical = str(capture.get("canonical_capture_id") or "")
                row = conn.execute(
                    "SELECT * FROM prospective_capture_run WHERE id=?", (canonical,)
                ).fetchone()
                if row is None:
                    raise DecisionReviewContractError("CANONICAL_CAPTURE_MISSING")
                capture = dict(row)
            if capture["status"] != "COMPLETE":
                raise DecisionReviewContractError("CAPTURE_NOT_COMPLETE")
            sample_row = conn.execute(
                "SELECT * FROM prospective_recommendation_sample "
                "WHERE capture_run_id=? AND sample_index=?",
                (capture["id"], sample_index),
            ).fetchone()
            if sample_row is None:
                raise DecisionReviewContractError("CAPTURE_SAMPLE_NOT_FOUND")
            sample = dict(sample_row)
            sample["snapshot"] = json.loads(str(sample["snapshot_json"]))
    except (sqlite3.Error, ValueError, TypeError) as exc:
        if isinstance(exc, DecisionReviewContractError):
            raise
        raise DecisionReviewContractError("CAPTURE_READ_FAILED") from exc
    return capture, sample


def build_scanner_review_input(
    capture: dict[str, Any], sample: dict[str, Any], *,
    protocol_id: str,
) -> dict[str, Any]:
    """Project frozen baseline facts; never infer missing identity or a price."""
    if not protocol_id or str(capture.get("status")) != "COMPLETE":
        raise DecisionReviewContractError("CAPTURE_OR_PROTOCOL_NOT_READY")
    snapshot = sample.get("snapshot")
    if not isinstance(snapshot, dict):
        raise DecisionReviewContractError("SNAPSHOT_MISSING")
    if (
        not sample.get("snapshot_hash")
        or digest_json(snapshot) != sample["snapshot_hash"]
    ):
        raise DecisionReviewContractError("SNAPSHOT_HASH_MISMATCH")
    if str(sample.get("capture_run_id") or "") != str(capture.get("id") or ""):
        raise DecisionReviewContractError("CAPTURE_IDENTITY_MISMATCH")
    if (
        sample.get("action") != "ENTRY_CANDIDATE"
        or snapshot.get("action") != "ENTRY_CANDIDATE"
    ):
        raise DecisionReviewContractError("ACTION_OUT_OF_SCOPE")
    for key in ("market", "strategy", "decision_status", "candidate_state"):
        if str(sample.get(key) or "") != str(snapshot.get(key) or ""):
            raise DecisionReviewContractError("CANDIDATE_IDENTITY_MISMATCH")
    if str(sample.get("ticker") or "") != str(snapshot.get("code") or ""):
        raise DecisionReviewContractError("CANDIDATE_IDENTITY_MISMATCH")
    if str(sample.get("name") or "") != str(snapshot.get("name") or ""):
        raise DecisionReviewContractError("CANDIDATE_IDENTITY_MISMATCH")

    priority = snapshot.get("priority")
    risk = snapshot.get("risk")
    conditions = snapshot.get("conditions")
    guide = snapshot.get("entry_risk_guide")
    if not all(isinstance(v, dict) for v in (priority, risk, conditions, guide)):
        raise DecisionReviewContractError("BASELINE_EVIDENCE_INCOMPLETE")
    rank = priority.get("rank")
    if type(rank) is not int or rank <= 0 or sample.get("rank") != rank:
        raise DecisionReviewContractError("BASELINE_RANK_MISMATCH")
    risk_status = str(risk.get("status") or "").upper()
    if not risk_status:
        raise DecisionReviewContractError("BASELINE_RISK_MISSING")
    if risk_status in BLOCKED_RISK_STATUSES or (
        isinstance(guide.get("action"), dict)
        and guide["action"].get("status") == "RISK_BLOCKED"
    ):
        raise DecisionReviewContractError("RISK_BLOCKED_OUT_OF_SCOPE")
    if not isinstance(risk.get("warning"), bool):
        raise DecisionReviewContractError("BASELINE_RISK_MISSING")

    provenance = snapshot.get("semantic_policy_provenance")
    if not isinstance(provenance, dict) or provenance.get("status") != VERIFIED_POLICY:
        raise DecisionReviewContractError("POLICY_PROVENANCE_UNVERIFIED")
    request = capture.get("request")
    if not isinstance(request, dict):
        raw = capture.get("request_json")
        try:
            request = json.loads(raw) if isinstance(raw, str) else {}
        except (ValueError, TypeError) as exc:
            raise DecisionReviewContractError("POLICY_PROVENANCE_UNVERIFIED") from exc
    if not isinstance(request, dict):
        raise DecisionReviewContractError("POLICY_PROVENANCE_UNVERIFIED")
    if not all([
        provenance.get("policy_id"),
        provenance.get("policy_hash"),
        request.get("selection_policy_id") == provenance.get("policy_id"),
        request.get("selection_policy_hash") == provenance.get("policy_hash"),
    ]):
        raise DecisionReviewContractError("POLICY_PIN_MISMATCH")

    source = snapshot.get("semantic_source_v2")
    valid, reason = verify_semantic_source_v2(source)
    if not valid:
        raise DecisionReviewContractError(reason or "SEMANTIC_SOURCE_INVALID")
    assert isinstance(source, dict)
    read = source.get("readiness")
    items = source.get("conditions", {}).get("items")
    strategy = source.get("strategy")
    if (
        not isinstance(read, dict)
        or read.get("q2_status") != "COMPLETE"
        or not isinstance(items, list)
        or not items
        or not isinstance(strategy, dict)
    ):
        raise DecisionReviewContractError("ENGINE_EVIDENCE_INCOMPLETE")
    if (
        str(strategy.get("strategy_version_id") or "")
        != str(snapshot.get("strategy_version_id") or "")
        or str(strategy.get("strategy_definition_hash") or "")
        != str(snapshot.get("strategy_definition_hash") or "")
        or not snapshot.get("strategy_version_id")
        or not snapshot.get("strategy_definition_hash")
    ):
        raise DecisionReviewContractError("STRATEGY_IDENTITY_MISMATCH")

    signal = _date(sample.get("signal_date"))
    if _date(snapshot.get("data_date")) != signal:
        raise DecisionReviewContractError("FUTURE_OR_MISMATCHED_EVIDENCE_DATE")
    actual = capture.get("actual_data_date")
    if actual and _date(actual) != signal:
        raise DecisionReviewContractError("FUTURE_OR_MISMATCHED_EVIDENCE_DATE")
    horizon = str(capture.get("horizon_intent") or "")
    if horizon not in _EXPLICIT_HORIZONS and horizon != "LEGACY_UNSPECIFIED":
        raise DecisionReviewContractError("HORIZON_OUT_OF_SCOPE")

    evidence: list[dict[str, Any]] = []
    for i, condition in enumerate(items):
        if not isinstance(condition, dict) or not all(
            isinstance(condition.get(field), str) and condition[field]
            for field in ("condition_id", "source_condition", "observed_meaning")
        ):
            raise DecisionReviewContractError("ENGINE_EVIDENCE_INCOMPLETE")
        evidence.append({
            "evidence_id": f"condition-{i + 1}",
            "owner": "SCANNER_ENGINE",
            "field_path": f"semantic_source_v2.conditions.items[{i}]",
            "value": {
                "source_condition": condition["source_condition"],
                "observed_meaning": condition["observed_meaning"],
            },
            "source_ref": source["source_snapshot_hash"],
            "available_on": signal.isoformat(),
            "available_at": None,
            "limitations": ["EOD_DATE_ONLY_EXACT_RELEASE_TIME_UNPROVEN"],
            "source_policy_ref": provenance["policy_hash"],
        })
    evidence.append({
        "evidence_id": "risk-status",
        "owner": "SCANNER_RISK",
        "field_path": "risk",
        "value": {"status": risk_status, "warning": risk["warning"]},
        "source_ref": sample["snapshot_hash"],
        "available_on": signal.isoformat(),
        "available_at": None,
        "limitations": ["EOD_DATE_ONLY_EXACT_RELEASE_TIME_UNPROVEN"],
        "source_policy_ref": provenance["policy_hash"],
    })
    body: dict[str, Any] = {
        "schema_version": INPUT_VERSION,
        "adapter_version": ADAPTER_VERSION,
        "evaluation_protocol_id": protocol_id,
        "source_kind": "PROSPECTIVE_CAPTURE",
        "source_ref": {
            "canonical_capture_id": capture["id"],
            "source_execution_key": capture.get("source_execution_key"),
        },
        "candidate_ref": {
            "sample_index": sample["sample_index"],
            "snapshot_hash": sample["snapshot_hash"],
        },
        "as_of": {
            "signal_date": signal.isoformat(),
            "source_date": signal.isoformat(),
            "captured_at": capture.get("completed_at"),
            "time_proof": "EOD_DATE_ONLY_EXACT_RELEASE_TIME_UNPROVEN",
        },
        "baseline_identity": {
            "scanner_version": capture.get("scanner_version"),
            "scanner_baseline": capture.get("scanner_baseline"),
            "input_fingerprint": capture.get("input_fingerprint"),
            "strategy_version_id": snapshot["strategy_version_id"],
            "strategy_definition_hash": snapshot["strategy_definition_hash"],
            "selection_policy_id": provenance["policy_id"],
            "selection_policy_hash": provenance["policy_hash"],
            "horizon_intent": horizon,
            "horizon_policy_version": capture.get("horizon_policy_version"),
        },
        "baseline_decision": {
            "action": "ENTRY_CANDIDATE",
            "decision_status": sample["decision_status"],
            "candidate_state": sample["candidate_state"],
            "rank": rank,
            "tier": priority.get("tier"),
            "strategy": sample["strategy"],
            "conditions": {
                "passed": conditions.get("passed"),
                "total": conditions.get("total"),
                "missing": conditions.get("missing"),
            },
            "risk": {"status": risk_status, "warning": risk["warning"]},
            "entry_risk_guide": deepcopy(guide),
        },
        "evidence_items": evidence,
        "allowed_decisions": sorted(ALLOWED_DECISIONS),
        "missing_evidence": ["EXACT_SOURCE_RELEASE_TIMESTAMP"],
        "limitations": [
            "NOT_AUTHORIZED_FOR_PROVIDER_TRANSMISSION",
            "HORIZON_NUMERIC_POLICY_NOT_APPROVED",
        ],
    }
    # This input is a local diagnostic. It is never a provider request.
    body["request_id"] = digest_json({
        "capture": capture["id"], "sample": sample["snapshot_hash"],
        "protocol_id": protocol_id, "adapter": ADAPTER_VERSION,
    })
    body["input_hash"] = digest_json(body)
    return {
        "status": "OFFLINE_INSPECTABLE_ONLY" if horizon in _EXPLICIT_HORIZONS
                  else "LEGACY_INSPECTION_ONLY",
        "reason_code": (
            "HORIZON_NUMERIC_POLICY_NOT_APPROVED" if horizon in _EXPLICIT_HORIZONS
            else "LEGACY_HORIZON_CANNOT_BE_BACKFILLED"
        ),
        "input": body,
        "input_hash": body["input_hash"],
        "actual_provider_eligible": False,
        "external_requests": 0,
    }


def validate_decision_review_response(
    review_input: dict[str, Any], response: dict[str, Any],
) -> dict[str, Any]:
    """Validate structure, cited evidence and numeric claims (not economic truth)."""
    if not isinstance(response, dict) or set(response) != {
        "decision", "abstain_reason", "supporting_reasons", "opposing_reasons",
    }:
        raise DecisionReviewContractError("RESPONSE_SCHEMA_INVALID")
    decision = response["decision"]
    if decision not in ALLOWED_DECISIONS:
        raise DecisionReviewContractError("REVIEW_DECISION_INVALID")
    if (decision == "ABSTAIN") != (response["abstain_reason"] in ABSTAIN_REASONS):
        raise DecisionReviewContractError("ABSTAIN_REASON_INVALID")
    if decision != "ABSTAIN" and response["abstain_reason"] is not None:
        raise DecisionReviewContractError("ABSTAIN_REASON_INVALID")

    evidence = {
        item["evidence_id"]: item
        for item in review_input["evidence_items"]
    }
    for field in ("supporting_reasons", "opposing_reasons"):
        reasons = response[field]
        if not isinstance(reasons, list) or len(reasons) > _MAX_REASONS:
            raise DecisionReviewContractError("RESPONSE_REASONS_INVALID")
        for reason in reasons:
            if not isinstance(reason, dict) or set(reason) != {
                "code", "evidence_refs", "explanation",
            } or reason["code"] not in REASON_CODES:
                raise DecisionReviewContractError("RESPONSE_REASON_SCHEMA_INVALID")
            refs = reason["evidence_refs"]
            explanation = reason["explanation"]
            if (
                not isinstance(refs, list) or not refs
                or len(set(refs)) != len(refs)
                or not all(isinstance(ref, str) and ref in evidence for ref in refs)
                or not isinstance(explanation, str)
                or not explanation.strip() or len(explanation) > 300
            ):
                raise DecisionReviewContractError("RESPONSE_EVIDENCE_UNGROUNDED")
            # A lightweight numeric guard; qualitative hallucinations still
            # require prospective measurement. Never claim LLM truth from this.
            known = " ".join(
                json.dumps(evidence[ref]["value"], ensure_ascii=False)
                for ref in refs
            )
            if set(_NUMBER.findall(explanation)) - set(_NUMBER.findall(known)):
                raise DecisionReviewContractError("RESPONSE_UNSUPPORTED_NUMBER")
    if decision == "PASS_THROUGH" and not response["supporting_reasons"]:
        raise DecisionReviewContractError("SUPPORTING_EVIDENCE_REQUIRED")
    if decision == "REVIEW_REQUIRED" and not response["opposing_reasons"]:
        raise DecisionReviewContractError("OPPOSING_EVIDENCE_REQUIRED")
    return deepcopy(response)


class OfflineFakeShadowSession:
    """In-memory, explicit fake-only review journal; no production persistence."""

    def __init__(self) -> None:
        self._records: dict[str, dict[str, Any]] = {}

    def inspect(
        self, projection: dict[str, Any], response: dict[str, Any],
        *, provider_id: str = "FAKE",
    ) -> dict[str, Any]:
        if provider_id != "FAKE":
            raise DecisionReviewContractError("EXTERNAL_PROVIDER_FORBIDDEN")
        if projection.get("status") != "OFFLINE_INSPECTABLE_ONLY":
            raise DecisionReviewContractError("HORIZON_NOT_FAKE_TEST_SCOPE")
        review_input = projection["input"]
        if review_input.get("input_hash") != projection.get("input_hash"):
            raise DecisionReviewContractError("INPUT_IDENTITY_MISMATCH")
        body = dict(review_input)
        digest = body.pop("input_hash")
        if digest_json(body) != digest:
            raise DecisionReviewContractError("INPUT_IDENTITY_MISMATCH")
        identity = digest_json({
            "input_hash": digest,
            "output_contract": OUTPUT_VERSION,
            "provider": "FAKE",
        })
        if identity in self._records:
            return {**deepcopy(self._records[identity]), "reused": True}
        try:
            verified = validate_decision_review_response(review_input, response)
            status, failure = "VALID", None
        except DecisionReviewContractError as exc:
            verified, status, failure = None, "ERROR", exc.code
        record = {
            "review_identity": identity,
            "input_hash": digest,
            "source_ref": deepcopy(review_input["source_ref"]),
            "candidate_ref": deepcopy(review_input["candidate_ref"]),
            "protocol_id": review_input["evaluation_protocol_id"],
            "model_id": "FAKE-ACT2-S3",
            "provider_id": "FAKE",
            "output_contract_version": OUTPUT_VERSION,
            "status": status,
            "decision": verified["decision"] if verified else "ABSTAIN",
            "abstain_reason": (
                verified["abstain_reason"] if verified else "MODEL_ERROR"
            ),
            "validated_output": verified,
            "failure_code": failure,
            "baseline_action": review_input["baseline_decision"]["action"],
            "shadow_action": "DEFER_THIS_OPPORTUNITY" if (
                verified and verified["decision"] == "REVIEW_REQUIRED"
            ) else "BASELINE_UNCHANGED",
            "outcome_status": "NOT_EVALUATED",
            "outcome_return": None,
            "reused": False,
            "external_requests": 0,
            "production_activation": False,
        }
        self._records[identity] = deepcopy(record)
        return deepcopy(record)

    def list_records(self) -> list[dict[str, Any]]:
        return [deepcopy(record) for record in self._records.values()]
